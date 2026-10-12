**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（涉及 GitHubClient 分页与 build_state，用假服务器构造 1001 条评论；最终定档以维护者为准）
**影响等级建议（补）**：B（需要一个 issue 上评论数超过 1000 才触发（可刷屏制造，但属特定路径），触发后状态冻结、可重复结算。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：评论超过 1000 条后被静默截断，机器人后写的标记看不见，状态停在旧值。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· ；本地假 GitHub，`apply=False`；**只用了机器人自己的合法标记加普通刷屏评论，没有伪造任何标记**

## 现象
评论超过 1000 条后被静默截断，机器人后写的标记全部看不见，状态冻结在旧值：已结算的任务仍是 verified，再 `/settle` 就重复记分

issue 线程的评论总数达到 1000 条（10 页 × 100 条）。人工刷屏，或者一个热门 issue 自然讨论，都能到这个数。

## 实测读数
本机实跑（`repro/rA-statemachine/a1_comment_cap_rollback.py`）：

```
第 1 次 /settle：线程评论总数=1000，client 读到=1000，裁决=settle verified->settled delta=20
第 2 次 /settle：线程评论总数=1001，client 读到=1000，裁决=settle verified->settled delta=20
同一 issue 结算总分 = 40 （expert 一次过应为 20）
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 a1_comment_cap_rollback.py`；只读导入上游、不写仓库文件、不触网。

### a1_comment_cap_rollback.py
```python
# -*- coding: utf-8 -*-
"""A1-4：GitHubClient.comments() 最多读 10 页×100=1000 条且静默截断（docstring 说「调用方按评论面未全量处置」，但没有任何调用方处置）。
评论数超过 1000 后，机器人新写的标记都看不见 ⇒ 状态冻结在旧标记：已结算的任务仍显示 verified，维护者再 /settle 就重复记分。
（这里只用机器人自己的合法标记 + 普通刷屏评论，不需要伪造标记。）"""
import json, io, contextlib
from _common import bb, CFG, MAINT
from _fakegh import FakeGH, event

def mk(d):
    return "**[悬赏板]**\n<!-- bounty:v1 " + json.dumps(d) + " -->"

gh = FakeGH()
L = ["bounty", "bounty:verified", "difficulty:expert"]
gh.add_issue(101, L)
gh.add_comment(101, "github-actions[bot]", mk({"state": "claimed", "holder": "alice", "rounds": 0, "seq": 1}))
gh.add_comment(101, "github-actions[bot]", mk({"state": "delivered", "holder": "alice", "rounds": 1, "seq": 2}))
gh.add_comment(101, "github-actions[bot]", mk({"state": "verified", "holder": "alice", "rounds": 1, "seq": 3}))
for i in range(997):
    gh.add_comment(101, "spammer%d" % (i % 7), "+1")       # 普通评论把总数推到 1000
cl = bb.GitHubClient("FuRongJun-1999/dsh-bounty", "dummy", api_base=gh.base)
totals = []
for rnd in (1, 2):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code, evs = bb.handle_issue_comment(event(101, L, MAINT, "/settle", assoc="OWNER"), CFG, cl)
    ev = evs[0]
    print(f"第 {rnd} 次 /settle：线程评论总数={len(gh.comments[101])}，client 读到={len(cl.comments(101))}，裁决={ev['action']} {ev['from']}->{ev['to']} delta={ev['delta']}")
    totals.append(ev["delta"] if ev["action"] == "settle" else 0)
    # 模拟 --apply 时机器人把「已结算」评论写进线程（第 1001 条之后）
    gh.add_comment(101, "github-actions[bot]", mk({"state": "settled", "holder": "alice", "rounds": 1, "seq": 4 + rnd}))
gh.stop()
print("同一 issue 结算总分 =", sum(totals), "（expert 一次过应为 20）")
print("VERDICT=BUG" if sum(totals) == 40 else "VERDICT=OK")
```

## 代码定位
- `scripts/bounty_board.py:1169-1181` `comments()` 写死了 `for page in range(1, 11)`，第 10 页读满就停。docstring 写的是「达上限即截断，**调用方按『评论面未全量』处置**」，但这个函数既不返回「被截断」的信号，也没有任何调用方处置：`handle_issue_comment` 在 `:1582`，`count_active_claims` 在 `:1239-1241`，`handle_sweep_live` 在 `:1613-1614`。
- 评论按时间升序返回，被截掉的恰好是**最新**的那些，也就是最新的标记。

```
scripts/bounty_board.py:1169-1181
    # 生效条件：n 为 issue 号时返回该 issue 全部评论正文列表（per_page=100 分页，最多 10 页 = 1000 条；达上限即截断，调用方按「评论面未全量」处置）。
    def comments(self, n):
        out = []
        for page in range(1, 11):
            chunk = self._req(
                "GET", f"/repos/{self.repo}/issues/{int(n)}/comments"
                       f"?per_page=100&page={page}")
            if not chunk:
                break
            out += [c.get("body") or "" for c in chunk]
            if len(chunk) < 100:
                break
        return out

scripts/bounty_board.py:1-1
# -*- coding: utf-8 -*-

scripts/bounty_board.py:11-11
分层（白箱判据：每一层可单独复核）
```

## 影响
- 状态回到 1000 条以内最后一个标记：重复结算（复现里 expert +20 记了两次，账本事件 ts 不同，id 也不同，幂等去重拦不住）。
- 同理会出现：已交付的任务又显示 claimed，sweep 再扣一次超时分；已释放的认领看起来还被占着。
- 攻击面：任何人都能刷评论把线程推到 1000 条，配合 issue-01 更容易利用。就算 issue-01 修好了，这条仍然成立。

## 修法
1. 分页读到空页为止，不设硬上限；或者读到上限时抛 `BoardError`，按 fail-closed 处理，并回评「线程过长，请维护者处理」。
2. 更稳的做法：先用 `?sort=created&direction=desc` 倒序读，只取最近的 bot 标记（权威记录只需要最新一条）。
3. 补守卫：假服务器上放 1001 条评论，断言状态取的是最后一条标记。

## 与已有 issue 的关系
bodies.txt 里 grep `1000`、`截断`、`comments(`：「1000」只出现在检索基准的数据规模里，「截断」只出现在其他仓库的实验报告里，和本仓无关。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a1_comment_cap_rollback.py`：

```
第 1 次 /settle：线程评论总数=1000，client 读到=1000，裁决=settle verified->settled delta=20
第 2 次 /settle：线程评论总数=1001，client 读到=1000，裁决=settle verified->settled delta=20
同一 issue 结算总分 = 40 （expert 一次过应为 20）
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 4 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 假服务器上放 1001 条评论时，`build_state` 取到的是最后一条机器人标记
- 第二次 `/settle` 被拒，expert 一次过只记 20 分（不是 40）
- `a1_comment_cap_rollback.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
