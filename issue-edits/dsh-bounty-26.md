**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（涉及 _do_verify 和 sweep 两处并构造时间线；最终定档以维护者为准）
**影响等级建议（补）**：A（常规流程（维护者审得比剩余租约慢）即可触发，按时交付的人被扣 −2×base，违反 README §四.2「退回不扣分」，属计分语义错误。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：/verify fail 退回时沿用旧 due_at，按时交付的人会在之后的 sweep 里被判超时扣分。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯逻辑层

## 现象
`/verify fail` 退回返工时沿用认领时的 due_at，不续期：维护者审得比剩余租约慢，按时交付的人会在下一次 6h 扫描里被判「超时未交付」，扣 −2base

认领后按时 `/deliver`，维护者 `/verify fail` 的时间点已经过了（或接近）原 due_at。招标模式 `/select` 之后再 fail 也是同一条路径。

## 实测读数
本机实跑（`repro/rA-statemachine/a3_fail_keeps_stale_due.py`）：

```
t=0h   alice /claim  : 通过 open->claimed holder=alice rounds=0 delta=0 | @alice 认领，锁至 2026-10-12T00:00:00Z
 t=10h  alice /deliver: 通过 claimed->delivered holder=alice rounds=1 delta=0 | @alice 第 1 轮交付（https://e.com/pr/1）
 t=80h  维护者 /verify fail（审了 70 小时）: 通过 delivered->claimed holder=alice rounds=1 delta=0 | 验收不通过：第3条判据未过
        退回后 due_at = 2026-10-12T00:00:00Z （仍是认领时的 72h 到期点）
 t=84h  sweep: 通过 claimed->open holder=None rounds=0 delta=-20 | @alice 认领超时未交付，自动回板 | 扣分归属: alice
 alice 本任务净分 = -20
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 a3_fail_keeps_stale_due.py`；只读导入上游、不写仓库文件、不触网。

### a3_fail_keeps_stale_due.py
```python
# -*- coding: utf-8 -*-
"""A3-1：/verify fail 退回 claimed 时沿用原 due_at（不续期）——维护者审得比剩余租约慢，
按时交付的人会在下一次 6h 扫描被判「超时未交付」记 −2base（规则写明「退回返工不扣分」）。"""
from _common import bb, Thread, at, CFG, MAINT, show

t = Thread(labels=("bounty", "bounty:open", "difficulty:expert"))
print(" t=0h   alice /claim  :", show(t.run("alice", "/claim", at(0))))
print(" t=10h  alice /deliver:", show(t.run("alice", "/deliver https://e.com/pr/1", at(10))))
print(" t=80h  维护者 /verify fail（审了 70 小时）:", show(t.run(MAINT, "/verify fail 第3条判据未过", at(80))))
st = t.state(); print("        退回后 due_at =", st.due_at, "（仍是认领时的 72h 到期点）")
ds = bb.sweep([st], at(84), CFG)
for d in ds:
    print(" t=84h  sweep:", show(d), "| 扣分归属:", d.event["holder"])
print(" alice 本任务净分 =", sum(e["delta"] for e in t.ledger + [d.event for d in ds] if e.get("holder") == "alice"))
print("VERDICT=BUG" if ds and ds[0].event["delta"] == -20 and ds[0].event["holder"] == "alice" else "VERDICT=OK")
```

## 代码定位
- `scripts/bounty_board.py:823` fail 分支 `_accept(st, "/verify", …, "claimed", st.holder, st.due_at, …)` 原样带着旧的 `due_at`。
- `scripts/bounty_board.py:857-886` `sweep` 只看 `state == "claimed" ∧ now ≥ due`，分不出「从没交过」和「交过、被退回、正在返工」。

```
scripts/bounty_board.py:823-825
        return _accept(st, "/verify", now, actor, "claimed", st.holder, st.due_at,
                       st.rounds, f"验收不通过：{reason or '（未写理由）'}", bullets,
                       delta=0, criteria=())

scripts/bounty_board.py:857-869
# 生效条件：states 为 IssueState 可迭代、now 为带时区 datetime、cfg 为 Config 时返回 Decision 列表——逐条判「态为 claimed ∧ 有 due_at ∧ now ≥ due ⇒ 超时回板 open（记 SCORE_TIMEOUT，负分归属原持有者）」；未超期/无到期/非 claimed 一律不动。
def sweep(states, now: datetime, cfg: Config):
    """超时回收（`schedule` 每 6 小时调用）：`bounty:claimed` 且到期未交付 → 回板。"""
    out = []
    for st in states:
        if st.state != "claimed" or not st.due_at:
            continue
        try:
            due = parse_ts(st.due_at)
        except ValueError:
            continue
        if now < due:
            continue
```

## 影响
违反 README §4.2、设计 §4.4.3 「发布者点退回返工 → 不扣分，只计轮次」。按时交付的贡献者被记成「行为不一致」，扣最重的 −2base（expert −20），反而比「轮次用尽、无效交付」的 −base 更重，正是设计 §4.4.6 ③ 要杜绝的反向激励。扣分发生与否取决于维护者审得快不快，贡献者自己控制不了。

## 修法
1. fail 退回时重新给一个返工租约：`due_at = now + claim_hours`（或者单独配置一个返工期）。
2. 或者在标记里记 `last_delivered_at`，sweep 只对「本轮还没交付」的 claim 扣超时分。
3. 补守卫：「deliver 后过期才 fail → 下一次 sweep 不扣分」。

## 与已有 issue 的关系
bodies.txt 里 grep `due_at`、`租约`，命中 0；`超时` 只出现在规则引用（#4）和别的仓库里。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a3_fail_keeps_stale_due.py`：

```
 t=0h   alice /claim  : 通过 open->claimed holder=alice rounds=0 delta=0 | @alice 认领，锁至 2026-10-12T00:00:00Z
 t=10h  alice /deliver: 通过 claimed->delivered holder=alice rounds=1 delta=0 | @alice 第 1 轮交付（https://e.com/pr/1）
 t=80h  维护者 /verify fail（审了 70 小时）: 通过 delivered->claimed holder=alice rounds=1 delta=0 | 验收不通过：第3条判据未过
        退回后 due_at = 2026-10-12T00:00:00Z （仍是认领时的 72h 到期点）
 t=84h  sweep: 通过 claimed->open holder=None rounds=0 delta=-20 | @alice 认领超时未交付，自动回板 | 扣分归属: alice
 alice 本任务净分 = -20
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 7 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 10h 交付、80h 被退回后，84h 的 sweep 不扣分（扣分为 0）
- 退回后有新的返工期（或 sweep 只对本轮未交付的 claim 计超时）
- `a3_fail_keeps_stale_due.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
