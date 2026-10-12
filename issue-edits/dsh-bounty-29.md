**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：easy（单点：`apply_live` 少收 `extra_events` 一行；最终定档以维护者为准）
**影响等级建议（补）**：B（只在招标模式（`bounty:contest`）的真模式下触发，落选分事件丢失。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：真模式下 /select 产生的落选分事件进不了 JSONL，也就进不了账本。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· ；本地假 GitHub，`apply=False`（事件列表与 `--apply` 时相同）

## 现象
真模式只收 `dec.event`，丢了 `dec.extra_events`：`/select` 定标产生的落选分事件进不了 JSONL artifact，也就进不了账本（纯逻辑层和离线 store_apply 都会写，唯独线上丢）

## 实测读数
本机实跑（`repro/rA-statemachine/a2_select_live_drops_losers.py`）：

```
纯逻辑 Decision：event=1 条（select），extra_events=2 条 [('bob', 4), ('carol', 4)]
命令 `/select` · 触发者 @FuRongJun-1999 · 维护者=True · 并发认领=0 · 当前态 bounty:contest
PLAN  #300 contest → delivered ｜ 定标：@alice 中标（3 份投标）
handle_issue_comment 返回事件: [('select', None, 0)]
--ledger-out 写出的 JSONL 行数: 1 动作: ['select']
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 a2_select_live_drops_losers.py`；只读导入上游、不写仓库文件、不触网。

### a2_select_live_drops_losers.py
```python
# -*- coding: utf-8 -*-
"""A2-4：/select 的落选分事件放在 Decision.extra_events，但真模式 apply_live 只收 dec.event ——
落选分永远进不了 JSONL artifact / 账本（纯逻辑层与离线 store_apply 都会写，真模式丢）。"""
import json, io, os, tempfile, contextlib
from _common import bb, CFG, MAINT
from _fakegh import FakeGH, event

gh = FakeGH()
L = ["bounty", "bounty:contest", "difficulty:expert"]
gh.add_issue(300, L)
bids = [("github-actions[bot]", {"state": "contest", "bidders": ["alice"], "seq": 1}),
        ("github-actions[bot]", {"state": "contest", "bidders": ["alice", "bob"], "seq": 2}),
        ("github-actions[bot]", {"state": "contest", "bidders": ["alice", "bob", "carol"], "seq": 3})]
for who, m in bids:
    gh.add_comment(300, who, "**[悬赏板] 状态已更新**\n<!-- bounty:v1 " + json.dumps(m) + " -->")
cl = bb.GitHubClient("FuRongJun-1999/dsh-bounty", "dummy", api_base=gh.base)

# 纯逻辑层的裁决
st = bb.build_state(300, L, [c["body"] for c in gh.comments[300]])
dec = bb.handle_command(st, "/select", "alice 方案最完整", "/select alice 方案最完整", MAINT,
                        bb.datetime.now(bb.timezone.utc), CFG, is_maintainer=True)
print("纯逻辑 Decision：event=1 条（%s），extra_events=%d 条 %s" % (
    dec.event["action"], len(dec.extra_events), [(e["holder"], e["delta"]) for e in dec.extra_events]))

# 真模式路由（apply=False：只打印计划，不写）
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    code, evs = bb.handle_issue_comment(event(300, L, MAINT, "/select alice 方案最完整", assoc="OWNER"), CFG, cl, apply=False)
print(buf.getvalue().strip())
print("handle_issue_comment 返回事件:", [(e["action"], e.get("holder"), e["delta"]) for e in evs])
p = os.path.join(tempfile.mkdtemp(), "bounty_events.jsonl")
bb.write_jsonl(p, evs)
lines = [json.loads(x) for x in open(p, encoding="utf-8")]
print("--ledger-out 写出的 JSONL 行数:", len(lines), "动作:", [x["action"] for x in lines])
gh.stop()
lost = len(dec.extra_events) == 2 and not any(x["action"] == "lose" for x in lines)
print("VERDICT=BUG" if lost else "VERDICT=OK")
```

## 代码定位
- `scripts/bounty_board.py:1542-1546` `apply_live()` 只做了 `events.append(dec.event)`，没有追加 `dec.extra_events`。
- 但 `Decision.extra_events` 的定义（`:376-377`）写明「一次裁决可附带多条账本事件……**写入面须一并入账**」；离线 `store_apply`（`:1376-1377`）确实一并入账了，测试走的是离线或纯逻辑路径，所以没有发现。

```
scripts/bounty_board.py:1542-1546
def apply_live(client, states, decisions, apply=False, out=print):
    """把裁决打到远端（`apply=False` 只打印计划）；返回本批事件列表。"""
    events = []
    for st, dec in zip(states, decisions):
        events.append(dec.event)

scripts/bounty_board.py:376-377
    #: 一次裁决可附带多条账本事件（如 `/select` 同时记多个落选分）——写入面须一并入账。
    extra_events: tuple = ()

scripts/bounty_board.py:1376-1378
    before = len(store.get("ledger") or [])
    store["ledger"] = append_events(store.get("ledger") or [],
                                    [dec.event] + list(dec.extra_events))
```

## 影响
README §4.5 承诺「落标者按难度记落选分（0 分也写事件，否则与未投标同形）」。workflow 产出的 JSONL 里一条 `lose` 事件都没有，账本和荣誉榜上落选者「与未投标同形」，正好是规格要避免的情况。

## 修法
1. `apply_live` 改成 `events.append(dec.event); events.extend(dec.extra_events)`。
2. 补一条路由层守卫（假服务器，或者直接给 `apply_live` 喂一个带 extra_events 的 Decision），断言 JSONL 里有 `lose`；配一条删掉 extend 就转红的定点变异。

## 与已有 issue 的关系
bodies.txt 里 grep `extra_events`，命中 0；`落选`、`/select` 只出现在 #4 和 #6 对规则的引用里。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a2_select_live_drops_losers.py`：

```
纯逻辑 Decision：event=1 条（select），extra_events=2 条 [('bob', 4), ('carol', 4)]
命令 `/select` · 触发者 @FuRongJun-1999 · 维护者=True · 并发认领=0 · 当前态 bounty:contest
PLAN  #300 contest → delivered ｜ 定标：@alice 中标（3 份投标）
handle_issue_comment 返回事件: [('select', None, 0)]
--ledger-out 写出的 JSONL 行数: 1 动作: ['select']
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 6 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 真模式 `/select` 后，`--ledger-out` 的 JSONL 里除 `select` 外还有每个落选者的 `lose` 事件
- `a2_select_live_drops_losers.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
