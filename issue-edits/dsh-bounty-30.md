**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：easy（单点：due_at 只有 `_do_claim` 一处写入，contest 流程不经过它；最终定档以维护者为准）
**影响等级建议（补）**：B（只在招标模式触发：投标截止从未写入，截止检查成死代码。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：招标模式的投标截止在正常流程里没有写入面，截止后仍能投标。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯逻辑层，另做了源码扫描

## 现象
招标模式的「投标截止 = due_at」在正常流程里根本没有地方写入：contest 任务从不经过 `/claim`，而 due_at 只由 `_do_claim` 产生，所以截止检查是死代码，任何时候都能投标

## 实测读数
本机实跑（`repro/rA-statemachine/a2_contest_deadline_unset.py`）：

```
源码中计算新 due_at 的位置数: 1 （只在 _do_claim）
 2099 年 alice /bid: 通过 contest->contest holder=None rounds=0 delta=0 | @alice 投标（第 1 份）
 2109 年 bob   /bid: 通过 contest->contest holder=None rounds=0 delta=0 | @bob 投标（第 2 份）
 招标 issue 的 due_at: None
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 a2_contest_deadline_unset.py`；只读导入上游、不写仓库文件、不触网。

### a2_contest_deadline_unset.py
```python
# -*- coding: utf-8 -*-
"""A2-5：招标模式的「投标截止 = due_at」在正常流程里没有任何写入面——
contest 态从不经过 /claim，而 due_at 只由 _do_claim 产生 ⇒ 截止检查是死代码，任何时候都能投标。"""
import re, os, datetime as _dt
from _common import bb, Thread, CFG, MAINT, show, CLONE

src = open(os.path.join(CLONE, "scripts", "bounty_board.py"), encoding="utf-8").read()
producers = [m.start() for m in re.finditer(r"timedelta\(hours=cfg\.claim_hours\)", src)]
print("源码中计算新 due_at 的位置数:", len(producers), "（只在 _do_claim）")
t = Thread(labels=("bounty", "bounty:contest", "difficulty:hard"))
far = _dt.datetime(2099, 1, 1, tzinfo=_dt.timezone.utc)
d1 = t.run("alice", "/bid https://e.com/a", far)
d2 = t.run("bob", "/bid https://e.com/b", far + _dt.timedelta(days=3650))
print(" 2099 年 alice /bid:", show(d1))
print(" 2109 年 bob   /bid:", show(d2))
print(" 招标 issue 的 due_at:", t.state().due_at)
print("VERDICT=BUG" if d1.ok and d2.ok and t.state().due_at is None and len(producers) == 1 else "VERDICT=OK")
```

## 代码定位
- `scripts/bounty_board.py:626-633` `_do_bid` 只在 `st.due_at` 为真时才检查截止。
- 全文件只有 `:611` `_do_claim` 会计算新的 `due_at`。contest 任务靠打 `bounty:contest` 标签开启，没有「开标」命令，发布模板 `.github/ISSUE_TEMPLATE/bounty.yml` 里也没有截止时间字段，`build_state` 也不会从任何地方读截止时间。
- 测试（`tests/test_bounty_board.py:364` 附近）是直接构造 `IssueState(due_at=…)` 来测截止逻辑的，没有覆盖「截止时间从哪里来」。
- 讽刺的是，现在唯一能设截止的办法，就是 issue-01 那种手写标记。

```
scripts/bounty_board.py:626-633
    if st.due_at:
        try:
            if now >= parse_ts(st.due_at):
                return _decide(st, "/bid",
                               f"投标截止时间已过（{st.due_at}）——截止后不得投标或修改",
                               now, actor, "bid_deadline_passed")
        except ValueError:
            pass

scripts/bounty_board.py:611-611
    due = fmt_ts(now + timedelta(hours=cfg.claim_hours))

tests/test_bounty_board.py:364-364
        labels=("bounty", "bounty:" + kw.get("state", "contest"), kw.get("diff", "difficulty:hard")),
```

## 影响
招标永远不截止：后来的投标人可以看着别人公开的方案再投（`/bid` 的链接和证据都在评论里公开），等于「截止后修改」。招投标法类比里最关键的公平性保证失效了。`/select` 也不检查截止是否已过，维护者可以在任何时间定标。

## 修法
1. 增加维护者的开标命令（比如 `/contest <截止 ISO8601>`），写标记 `state=contest, due_at=…`；或者从 issue 正文或模板字段解析截止时间。
2. `/select` 要求 `now ≥ due_at`（或者显式写明「提前定标」）。
3. 补守卫：从零开始的 contest 流程（不手工构造 IssueState）截止后 `/bid` 必须被拒。

## 与已有 issue 的关系
bodies.txt 里 grep `截止`，命中的 3 处都是 #9 讲 dsh-memory 的有效期，和本仓无关；`/bid` 只出现在规则引用里。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a2_contest_deadline_unset.py`：

```
源码中计算新 due_at 的位置数: 1 （只在 _do_claim）
 2099 年 alice /bid: 通过 contest->contest holder=None rounds=0 delta=0 | @alice 投标（第 1 份）
 2109 年 bob   /bid: 通过 contest->contest holder=None rounds=0 delta=0 | @bob 投标（第 2 份）
 招标 issue 的 due_at: None
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 5 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 从零开始的 contest 流程（不手工构造 IssueState）里能设定截止时间，截止后 `/bid` 被拒（`bid_deadline_passed`）
- `a2_contest_deadline_unset.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
