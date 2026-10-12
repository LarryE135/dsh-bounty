**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（涉及 build_state、count_active_claims 和 sweep，需要跨 issue 构造；最终定档以维护者为准）
**影响等级建议（补）**：A（任意在途 issue 上一条畸形标记就让全仓所有命令和定时 sweep 崩溃（退出码 2），默认配置可触发，核心链路失效。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：标记字段不做类型和范围校验，一条 `"rounds":"abc"` 就能让全仓命令停摆。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· ；本地假 GitHub，`apply=False`

## 现象
标记字段完全没有类型和范围校验：任意一个在途 issue 上出现一条 `"rounds":"abc"`，全仓所有命令和定时 sweep 都会崩溃（退出码 2）；`"rounds":-100` 能绕过 3 轮上限

任意一个带 `bounty:claimed` 或 `bounty:delivered` 标签的 issue 上，出现一条字段类型不对的标记。

## 实测读数
本机实跑（`repro/rA-statemachine/a1_malformed_marker_dos.py`）：

```
== 纯逻辑：build_state 对畸形字段的反应
  rounds 为字符串             : 抛 ValueError: invalid literal for int() with base 10: 'abc'
  rounds 为浮点串             : 抛 ValueError: invalid literal for int() with base 10: '1.5'
  bidders 为字符串            : 不抛；rounds=0 bidders=('a', 'b', 'c')
  rounds 为 -100（绕过轮次上限）   : 不抛；rounds=-100 bidders=()
  rounds=-100 时连续 10 次 /deliver 均登记为正常轮次: 10/10（上限应为 3）
  criteria=["a","b"] 时 /settle：抛 ValueError: invalid literal for int() with base 10: 'a'
== 真模式（本地假服务器，apply=False）：#200 上有一条畸形标记，影响无关的 #101
  #101 上 carol 的 /claim: 抛 ValueError: invalid literal for int() with base 10: 'abc'  → main() 捕获 ValueError 后退出码 2
  定时 sweep: 抛 ValueError: invalid literal for int() with base 10: 'abc'  → main() 捕获 ValueError 后退出码 2
命中: [True, True, True, True]
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 a1_malformed_marker_dos.py`；只读导入上游、不写仓库文件、不触网。

### a1_malformed_marker_dos.py
```python
# -*- coding: utf-8 -*-
"""A1-2：标记字段无类型校验——任何一条 bounty:claimed/delivered issue 上一条 `"rounds":"x"` 的标记，
让全仓所有命令（count_active_claims 每条命令都会扫全部在途 issue）与定时 sweep 一起崩溃退 2。"""
import json, io, contextlib
from _common import bb, CFG
from _fakegh import FakeGH, event

def mk(d):
    return "<!-- bounty:v1 " + json.dumps(d) + " -->"

res = []
print("== 纯逻辑：build_state 对畸形字段的反应")
for name, rec in [("rounds 为字符串", {"state": "claimed", "holder": "x", "rounds": "abc", "seq": 3}),
                  ("rounds 为浮点串", {"state": "claimed", "holder": "x", "rounds": "1.5", "seq": 3}),
                  ("bidders 为字符串", {"state": "contest", "bidders": "abc", "seq": 3}),
                  ("rounds 为 -100（绕过轮次上限）", {"state": "claimed", "holder": "x", "rounds": -100, "seq": 3})]:
    try:
        st = bb.build_state(1, ["bounty"], [mk(rec)])
        print(f"  {name:<24}: 不抛；rounds={st.rounds} bidders={st.bidders}")
    except Exception as e:
        print(f"  {name:<24}: 抛 {type(e).__name__}: {e}")

st = bb.build_state(1, ["bounty"], [mk({"state": "claimed", "holder": "x", "rounds": -100, "seq": 3})])
n_ok = 0
for i in range(10):
    d = bb.handle_command(st, "/deliver", "https://e.com/p", "/deliver https://e.com/p", "x", bb.datetime.now(bb.timezone.utc), CFG)
    st = bb.build_state(1, ["bounty"], [d.comment]) if d.ok else st
    n_ok += d.ok and d.to_state == "delivered"
print(f"  rounds=-100 时连续 10 次 /deliver 均登记为正常轮次: {n_ok}/10（上限应为 3）")
res.append(n_ok == 10)

try:
    st = bb.build_state(1, ["bounty", "difficulty:hard"], [mk({"state": "verified", "holder": "x", "rounds": 1, "criteria": ["a", "b"], "seq": 3})])
    bb.handle_command(st, "/settle", "", "/settle", "FuRongJun-1999", bb.datetime.now(bb.timezone.utc), CFG, is_maintainer=True)
    print("  criteria=[\"a\",\"b\"] 时 /settle：不抛"); res.append(False)
except Exception as e:
    print(f"  criteria=[\"a\",\"b\"] 时 /settle：抛 {type(e).__name__}: {e}"); res.append(True)

print("== 真模式（本地假服务器，apply=False）：#200 上有一条畸形标记，影响无关的 #101")
gh = FakeGH()
gh.add_issue(101, ["bounty", "bounty:open", "difficulty:easy"])
gh.add_issue(200, ["bounty", "bounty:claimed", "difficulty:easy"])
gh.add_comment(200, "mallory", "lol\n" + mk({"state": "claimed", "holder": "mallory", "rounds": "abc", "seq": 9}))
cl = bb.GitHubClient("FuRongJun-1999/dsh-bounty", "dummy", api_base=gh.base)
for label, fn in [("#101 上 carol 的 /claim", lambda: bb.handle_issue_comment(event(101, gh.issues[101]["labels"], "carol", "/claim"), CFG, cl)),
                  ("定时 sweep", lambda: bb.handle_sweep_live(CFG, cl))]:
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            fn()
        print(f"  {label}: 正常完成"); res.append(False)
    except Exception as e:
        print(f"  {label}: 抛 {type(e).__name__}: {e}  → main() 捕获 ValueError 后退出码 2"); res.append(True)
gh.stop()
print("命中:", res)
print("VERDICT=BUG" if all(res) else "VERDICT=OK")
```

## 代码定位
- `scripts/bounty_board.py:415` `rounds=int(marker.get("rounds") or 0)` 遇到非数字直接抛异常；负数照单全收。`:417-418` 的 `tuple(marker.get("criteria"/"bidders"))` 对字符串会拆成单个字符。
- `scripts/bounty_board.py:1232-1245` `count_active_claims()` 在**每一条命令**之前（`:1596`）都会扫描全仓所有 claimed/delivered issue，并对每个调用 `build_state`。所以只要有一处坏标记，**全仓所有命令**都失败。`handle_sweep_live` 也一样会崩。
- `_do_deliver`（`:731-732`）用 `rounds = st.rounds + 1`、`rounds > cfg.max_rounds` 判上限，负数永远到不了上限。

```
scripts/bounty_board.py:415-415
        rounds=int(marker.get("rounds") or 0), seq=_seq(marker),

scripts/bounty_board.py:0--1


scripts/bounty_board.py:417-418
        criteria=tuple(marker.get("criteria") or ()),
        bidders=tuple(marker.get("bidders") or ()),
```

## 影响
一条评论就能让整个悬赏板停摆：所有 `/claim`、`/deliver`、`/verify`、`/settle` 都退出码 2，超时回收也停了，直到有人手工找出那条坏标记。负的 rounds 让「最多 3 轮」和「轮次用尽记 −base」完全失效。

## 修法
1. `build_state` 对标记做 schema 校验：`rounds` 必须是 0…max_rounds 之间的 int；`criteria` 必须是两个非负 int 且 p≤t；`bidders` 必须是由字符串组成的 list；`holder` 必须是 str 或 None；`due_at` 必须能被 `parse_ts` 解析。不合格的标记直接**忽略**（退回上一条合格标记），并在输出里告警，而不是抛异常。
2. `count_active_claims` 对单个 issue 的异常做隔离，不能一处坏、全仓停。
3. 先做 issue-01 的作者过滤，从源头收窄。

## 与已有 issue 的关系
bodies.txt 里 grep `build_state`、`rounds`、`标记`：`rounds` 只出现在 #3 对计分公式的引用里，没有校验或崩溃相关的内容。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a1_malformed_marker_dos.py`：

```
== 纯逻辑：build_state 对畸形字段的反应
  rounds 为字符串             : 抛 ValueError: invalid literal for int() with base 10: 'abc'
  rounds 为浮点串             : 抛 ValueError: invalid literal for int() with base 10: '1.5'
  bidders 为字符串            : 不抛；rounds=0 bidders=('a', 'b', 'c')
  rounds 为 -100（绕过轮次上限）   : 不抛；rounds=-100 bidders=()
  rounds=-100 时连续 10 次 /deliver 均登记为正常轮次: 10/10（上限应为 3）
  criteria=["a","b"] 时 /settle：抛 ValueError: invalid literal for int() with base 10: 'a'
== 真模式（本地假服务器，apply=False）：#200 上有一条畸形标记，影响无关的 #101
  #101 上 carol 的 /claim: 抛 ValueError: invalid literal for int() with base 10: 'abc'  → main() 捕获 ValueError 后退出码 2
  定时 sweep: 抛 ValueError: invalid literal for int() with base 10: 'abc'  → main() 捕获 ValueError 后退出码 2
命中: [True, True, True, True]
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 12 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 无关 issue 上的 `/claim` 和定时 sweep 不再抛 ValueError，退出码 0
- `rounds=-100` 的标记被忽略，连续第 4 次交付按上限 3 被拒
- `a1_malformed_marker_dos.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
