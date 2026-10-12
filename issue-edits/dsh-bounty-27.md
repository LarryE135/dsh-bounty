**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（要逐一核对 9 种命令和标签/标记优先级，读两三个文件；最终定档以维护者为准）
**影响等级建议（补）**：A（任何一方 /dispute 后任务永久卡死，README 写的复位方式也无效，常规流程可触发，核心链路失效。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：disputed 态进得去出不来，README 说的手改标签复位也不生效。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯逻辑层

## 现象
`disputed` 是死胡同：没有任何命令能离开它，README 说的「维护者手改标签复位」也不管用（标记优先于标签）；持有者临到期发一条 `/dispute` 就能永久躲开 −2base 超时，同时一直占着任务

任何当事人（持有者、issue 作者、维护者）发 `/dispute <理由>`；或者第 4 次交付被判无效，自动转成 disputed。

## 实测读数
本机实跑（`repro/rA-statemachine/a2_disputed_sink.py`）：

```
t=71h alice /dispute: 通过 claimed->disputed holder=alice rounds=0 delta=0 | @alice 提起争议：我觉得验收标准不清楚
   FuRongJun-1999  /verify pass 仲裁通过        → 仍 disputed（当前态 `bounty:disputed` 不在待验收面）
   FuRongJun-1999  /verify fail 仲裁驳回        → 仍 disputed（当前态 `bounty:disputed` 不在待验收面）
   FuRongJun-1999  /settle                  → 仍 disputed（当前态 `bounty:disputed` 不可结算（须先过验收 `bounty）
   FuRongJun-1999  /select alice            → 仍 disputed（当前态 `bounty:disputed` 不在招标面）
   alice           /deliver https://e.com/p → 仍 disputed（当前态 `bounty:disputed` 不可交付（先 `/claim`））
   alice           /withdraw                → 仍 disputed（当前态 `bounty:disputed` 无需释放）
   bob             /claim                   → 仍 disputed（已有持有者 @alice（到期 2026-10-12T00:00:00Z）——先）
   FuRongJun-1999  /claim                   → 仍 disputed（已有持有者 @alice（到期 2026-10-12T00:00:00Z）——先）
   FuRongJun-1999  /dispute 维护者再提争议         → 仍 disputed（@FuRongJun-1999 提起争议：维护者再提争议）
 能离开 disputed 的命令数: 0
 维护者手改标签为 bounty:claimed 后重建态: disputed （标记优先，手改无效）
 一年后 sweep 条数: 0 → alice 永不吃超时扣分；bob 也永远认领不了
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 a2_disputed_sink.py`；只读导入上游、不写仓库文件、不触网。

### a2_disputed_sink.py
```python
# -*- coding: utf-8 -*-
"""A2-3：disputed 是死胡同——没有任何命令能离开它；README 说的「维护者手改标签复位」也无效（标记优先于标签）。
连带：持有者临期 /dispute 即可永久躲开 −2base 超时，并一直占着任务。"""
from _common import bb, Thread, at, CFG, MAINT, show

t = Thread(labels=("bounty", "bounty:open", "difficulty:expert"))
t.run("alice", "/claim", at(0))
print(" t=71h alice /dispute:", show(t.run("alice", "/dispute 我觉得验收标准不清楚", at(71))))
exits = 0
for actor, body, m in [(MAINT, "/verify pass 仲裁通过", True), (MAINT, "/verify fail 仲裁驳回", True),
                       (MAINT, "/settle", True), (MAINT, "/select alice", True), ("alice", "/deliver https://e.com/p", False),
                       ("alice", "/withdraw", False), ("bob", "/claim", False), (MAINT, "/claim", True),
                       (MAINT, "/dispute 维护者再提争议", True)]:
    d = t.run(actor, body, at(80), maint=m)
    left = d.ok and d.to_state != "disputed"
    exits += left
    print(f"   {actor:<15} {body:<24} → {'离开 disputed' if left else '仍 disputed'}（{d.reason[:40]}）")
print(" 能离开 disputed 的命令数:", exits)
# README §九：「disputed 之后的状态复位……仍由维护者手改标签」
t.labels = [l for l in t.labels if not l.startswith("bounty:")] + ["bounty:claimed"]
st = t.state(); print(" 维护者手改标签为 bounty:claimed 后重建态:", st.state, "（标记优先，手改无效）")
ds = bb.sweep([st], at(24 * 365), CFG)
print(" 一年后 sweep 条数:", len(ds), "→ alice 永不吃超时扣分；bob 也永远认领不了")
print("VERDICT=BUG" if exits == 0 and st.state == "disputed" and not ds else "VERDICT=OK")
```

## 代码定位
- 各命令的前置态（`CLAIMABLE_STATES`、`DELIVERABLE_STATES`、`WITHDRAWABLE_STATES`，`_do_verify` 要求 `delivered`，`_do_settle` 要求 `verified`）都不含 `disputed`（`scripts/bounty_board.py:211-215`、`:788`、`:838`），`_do_claim` 又被 `holder` 挡住（`:602-604`）。没有任何仲裁或复位命令。
- `build_state`（`:404-410`）规定「标记 > 标签」，所以 README §九 「disputed 之后的状态复位……由维护者手改标签」这条唯一的出路也是无效的。
- `sweep`（`:862`）只回收 `claimed`。`_do_dispute`（`:765-779`）对持有者没有任何限制：在 claimed 态、临到期时也能发。

```
scripts/bounty_board.py:211-215
CLAIMABLE_STATES = ("open", "expired")
#: 可交付态（`delivered` 可再交付 = 返工轮）。
DELIVERABLE_STATES = ("claimed", "delivered")
#: 可主动释放态。
WITHDRAWABLE_STATES = ("claimed", "delivered")

scripts/bounty_board.py:788-788
    if st.state != "delivered":

scripts/bounty_board.py:838-838
    if st.state != "verified":
```

## 影响
- 每个进入争议的任务都永久冻结，`/settle` 不了，也回不了板。README §五写的「维护者仲裁」在机器层面无法落地。
- 规避扣分：持有者在 71h 时发 `/dispute`，就永远不会被扣 72h 超时的 −2base；轮次用尽之前发 `/dispute`，也就避开了 −base。
- issue 作者（外部人开的 issue 被打上 bounty 标签后）也能把一个没人认领的任务直接冻结。

## 修法
1. 加维护者专用的仲裁命令，比如 `/resolve <delivered|claimed|open|verified> <理由>`，写新标记、留痕；或者允许 `/verify` 在 disputed 态执行。
2. 持有者在 claimed 态发的 dispute 不应冻结租约：sweep 也覆盖 disputed 态里「来自 claimed 且已过期」的情况；或者规定 dispute 不改主状态（设计 §3.2.1 本来就说 disputed 是「旁路标记，**不改变主状态**」）。
3. 把 README §九 改成实际可行的复位方式。

## 与已有 issue 的关系
bodies.txt 里 grep `disputed`、`争议`，命中 0。不重复。README §九把「disputed 之后的复位」列为待裁，但给的出路（手改标签）实测无效，所以本条是新问题。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a2_disputed_sink.py`：

```
 t=71h alice /dispute: 通过 claimed->disputed holder=alice rounds=0 delta=0 | @alice 提起争议：我觉得验收标准不清楚
   FuRongJun-1999  /verify pass 仲裁通过        → 仍 disputed（当前态 `bounty:disputed` 不在待验收面）
   FuRongJun-1999  /verify fail 仲裁驳回        → 仍 disputed（当前态 `bounty:disputed` 不在待验收面）
   FuRongJun-1999  /settle                  → 仍 disputed（当前态 `bounty:disputed` 不可结算（须先过验收 `bounty）
   FuRongJun-1999  /select alice            → 仍 disputed（当前态 `bounty:disputed` 不在招标面）
   alice           /deliver https://e.com/p → 仍 disputed（当前态 `bounty:disputed` 不可交付（先 `/claim`））
   alice           /withdraw                → 仍 disputed（当前态 `bounty:disputed` 无需释放）
   bob             /claim                   → 仍 disputed（已有持有者 @alice（到期 2026-10-12T00:00:00Z）——先）
   FuRongJun-1999  /claim                   → 仍 disputed（已有持有者 @alice（到期 2026-10-12T00:00:00Z）——先）
   FuRongJun-1999  /dispute 维护者再提争议         → 仍 disputed（@FuRongJun-1999 提起争议：维护者再提争议）
 能离开 disputed 的命令数: 0
 维护者手改标签为 bounty:claimed 后重建态: disputed （标记优先，手改无效）
 一年后 sweep 条数: 0 → alice 永不吃超时扣分；bob 也永远认领不了
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 14 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 存在一条有效的离开 disputed 的路径（如维护者仲裁命令），并留痕
- 持有者在 claimed 态 dispute 后租约照常到期、sweep 能扫到
- `a2_disputed_sink.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
