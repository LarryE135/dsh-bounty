**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（要读状态机里 withdraw/claim/sweep 三处并构造计分对照；最终定档以维护者为准）
**影响等级建议（补）**：A（任何认领者用 /withdraw + /claim 两条命令就能把被退回的轮次清零、改写计分（−10 → +20），默认配置可触发，属计分被操纵（量具失效）。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：/withdraw 后立即 /claim 会把轮次和租约都重置，计分和超时规则都能被绕开。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯逻辑层；只读导入 `scripts/bounty_board.py`，未改上游文件、未触网

## 现象
持有者在 `claimed` 或 `delivered` 态先发 `/withdraw`（规则明确写「主动释放**不影响声誉**」），紧接着自己再发 `/claim`——两条评论间隔几秒即可，别人很难抢在中间认领。于是：

- `_do_withdraw` 把态切回 `open` 时，标记里**留了** `st.rounds`（`:760`），但紧接着的 `_do_claim` 完全不读它：`_accept(..., rounds=0, ...)` 是写死的（`:615`），`due` 也按 `now + claim_hours` 重新计算（`:611`）。
- 轮次因此清零，而计分完全建立在轮次上：`_do_deliver` 用 `rounds = st.rounds + 1` 判「第 4 轮超出上限 → 无效交付 −base」（`:731-738`），`quality_delta` 用 `r = rounds - 1` 给出 2×/递减的档位（`:133-143`）。
- 租约同样被重置：72h 快到期时 withdraw + claim，`due_at` 变成新的 72h 之后，超时 −2base 永远不会触发，任务被一直占着。

不需要伪造任何东西，也不需要额外权限——持有人在合法命令面内就能做到。

## 实测读数
本机实跑（`repro/rA-statemachine/a2_withdraw_resets_rounds.py`，同一份工作、同一台机器）：

```
== 规则路径（不 withdraw）：第 4 次交付应判无效交付 −base
   3 轮退回后： state=claimed rounds=3
   第4次 /deliver : 通过 claimed->disputed holder=alice rounds=3 delta=-10 | @alice 第 4 轮交付超出上限，判无效交付（-10 分）
   alice 本任务净分 = -10
== 绕过路径（withdraw + 立即重新 claim）
   3 轮退回后： state=claimed rounds=3
   alice /withdraw: 通过 claimed->open holder=None rounds=3 delta=0 | @alice 主动释放认领，任务回板
   alice /claim   : 通过 open->claimed holder=alice rounds=0 delta=0 | @alice 认领，锁至 2026-10-12T07:00:36Z
   第4次 /deliver : 通过 claimed->delivered holder=alice rounds=1 delta=0 | @alice 第 1 轮交付（https://e.com/try4）
   /settle        : 通过 verified->settled holder=alice rounds=1 delta=20 | 结算 20 分（expert（base 10））
   alice 本任务净分 = 20
== 续租：72h 租约临期前 withdraw+claim，到期时间被重置，sweep 不扣分
   新到期: 2026-10-14T23:54:36Z | 第 72h sweep 条数 = 0
规则路径净分=-10，绕过路径净分=20（expert base=10）
VERDICT=BUG
```

规则路径（不 withdraw）第 4 次交付判无效交付，alice 本任务净分 **−10**；绕过路径净分 **+20**（expert，base=10）。续租那一幕：新到期 `2026-10-14T23:54:36Z`，第 72h 的 sweep 条数 **0**。

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 a2_withdraw_resets_rounds.py`；脚本只读导入上游、不写仓库文件、不触网。

### a2_withdraw_resets_rounds.py
```python
# -*- coding: utf-8 -*-
"""A2-2：/withdraw → 立即再 /claim 会把轮次清零、租约重开——
被退回 3 轮的人不吃 −base（无效交付），下一次通过反而按「一次过闸」拿 2×base；临期也可续租躲开 −2base 超时。"""
from _common import bb, Thread, at, CFG, MAINT, show

def run(path_withdraw):
    t = Thread(labels=("bounty", "bounty:open", "difficulty:expert"))
    t.run("alice", "/claim", at(0))
    for r in range(3):
        t.run("alice", f"/deliver https://e.com/try{r}", at(1 + r * 2))
        t.run(MAINT, "/verify fail 不达标", at(2 + r * 2))
    print("   3 轮退回后：", "state=%s rounds=%d" % (t.state().state, t.state().rounds))
    if path_withdraw:
        print("   alice /withdraw:", show(t.run("alice", "/withdraw", at(7))))
        print("   alice /claim   :", show(t.run("alice", "/claim", at(7.01))))
    d4 = t.run("alice", "/deliver https://e.com/try4", at(8))
    print("   第4次 /deliver :", show(d4))
    if d4.to_state == "delivered":
        t.run(MAINT, "/verify pass 终于好了", at(9))
        print("   /settle        :", show(t.run(MAINT, "/settle", at(10))))
    return sum(e["delta"] for e in t.ledger if e.get("holder") == "alice" or e.get("actor") == "alice" and e["action"] != "reject")

print("== 规则路径（不 withdraw）：第 4 次交付应判无效交付 −base")
a = run(False)
print("   alice 本任务净分 =", a)
print("== 绕过路径（withdraw + 立即重新 claim）")
b = run(True)
print("   alice 本任务净分 =", b)

print("== 续租：72h 租约临期前 withdraw+claim，到期时间被重置，sweep 不扣分")
t = Thread(labels=("bounty", "bounty:open", "difficulty:expert"))
t.run("alice", "/claim", at(0))
t.run("alice", "/withdraw", at(71.9)); t.run("alice", "/claim", at(71.91))
print("   新到期:", t.state().due_at, "| 第 72h sweep 条数 =", len(bb.sweep([t.state()], at(72), CFG)))
print("规则路径净分=%d，绕过路径净分=%d（expert base=10）" % (a, b))
print("VERDICT=BUG" if (a == -10 and b == 20) else "VERDICT=OK")
```

## 代码定位
```
scripts/bounty_board.py:605-616
    ok_label, why_label = _check_claimable(st)
    if not ok_label:
        return _decide(st, "/claim", why_label, now, actor, "state_not_claimable")
    ok_conc, why_conc = _check_concurrency(active_claims, actor, cfg.max_concurrent)
    if not ok_conc:
        return _decide(st, "/claim", why_conc, now, actor, "concurrency_limit")
    due = fmt_ts(now + timedelta(hours=cfg.claim_hours))
    bullets = [f"持有者：@{actor}",
               f"到期：{due}（逾期自动回板 `bounty:open` 并记 {SCORE_TIMEOUT} 分）",
               "交付：评论 `/deliver <PR 链接或证据块>`；放弃：`/withdraw`"]
    return _accept(st, "/claim", now, actor, "claimed", actor, due, 0,
                   f"@{actor} 认领，锁至 {due}", bullets)

scripts/bounty_board.py:751-761
def _do_withdraw(st, actor, now, cfg):
    ok_holder, why_holder = _check_is_holder(st, actor)
    if not ok_holder:
        return _decide(st, "/withdraw", why_holder, now, actor, "not_holder")
    if st.state not in WITHDRAWABLE_STATES:
        return _decide(st, "/withdraw", f"当前态 `bounty:{st.state}` 无需释放",
                       now, actor, "state_not_withdrawable")
    bullets = [f"释放者：@{actor}", "任务已回板 `bounty:open`，任何人可重新认领",
               "主动释放**不影响声誉**"]
    return _accept(st, "/withdraw", now, actor, "open", None, None, st.rounds,
                   f"@{actor} 主动释放认领，任务回板", bullets)

scripts/bounty_board.py:725-746
        return _decide(st, "/deliver",
                       f"当前态 `bounty:{st.state}` 不可交付（先 `/claim`）",
                       now, actor, "state_not_deliverable")
    ok_pay, why_pay = _check_payload(payload, body)
    if not ok_pay:
        return _decide(st, "/deliver", why_pay, now, actor, "payload_missing")
    rounds = st.rounds + 1
    if rounds > cfg.max_rounds:
        _d, _f = invalid_delta(base_of(st.difficulty))
        _bl = [f"交付者：@{actor}",
               f"第 {rounds} 轮交付超出上限 {cfg.max_rounds}——本 claim 判为**无效交付**（记 {_d} 分 = −base）",
               "已转 `bounty:disputed`：由维护者仲裁并留痕"]
        return _accept(st, "/deliver", now, actor, "disputed", st.holder, st.due_at,
                       st.rounds, f"@{actor} 第 {rounds} 轮交付超出上限，判无效交付（{_d} 分）",
                       _bl, delta=_d, formula=_f)
    shown = (payload or "").strip()
    show = shown if len(shown) <= 200 else shown[:200] + "…"
    bullets = [f"交付者：@{actor}", f"第 {rounds}/{cfg.max_rounds} 轮",
               f"交付物：{show or '（见评论正文的证据块）'}",
               "验收四闸：① CI 全绿 ② 复现读数 ③ 守卫＋定点变异 ④ 维护者人审"]
    return _accept(st, "/deliver", now, actor, "delivered", actor, st.due_at,
                   rounds, f"@{actor} 第 {rounds} 轮交付（{show[:80]}）", bullets,

scripts/bounty_board.py:131-143
# 生效条件：base 为正整数、rounds 为 1-based 交付次数时返回 (delta, formula)——round = max(0, rounds-1)；
# delta = max(1, round_half_up(base*2/(round+1)))；formula 为可独立复算的快照。
def quality_delta(base: int, rounds: int, e_pass=None, e_total=None):
    r = max(0, int(rounds) - 1)
    if e_total:
        _p, _t = max(0, int(e_pass or 0)), int(e_total)
        _e = max(0.0, min(1.0, _p / _t)) if _t else 1.0
    else:
        _p, _t, _e = None, None, 1.0
    raw = base * 2.0 * _e / (r + 1)
    d = max(1, _round_half_up(raw))
    f = {"rule": SCORE_RULE, "kind": "complete", "base": int(base),
         "rounds": int(rounds), "round": r, "num": 2, "den": r + 1,
```

## 影响
- 质量化计分的核心就是用返工轮次惩罚低质量交付（《质量化计分标准》S2/S3、设计 §4.4.6 ⑤「`round` = 已发生返工次数」）。用这招以后，返工多少轮都能把 round 清回 0：2× 首过档可以无限重来，轮次用尽的 −base 也永远不会触发——同一份工作从 −10 变成 +20。
- 72h 租约名存实亡：临期 withdraw + claim 即可无限续期，超时 −2base 不会发生，任务被一直占住、别人无法认领。
- 这两条都不依赖任何异常输入或外部攻击者，纯逻辑层的普通命令序列即可触发，且退出码、账本、标签三处记录都「一致」，事后对账看不出来。

## 修法
1. 轮次按「同一人 × 同一 issue」累计：withdraw 后同一人再 claim 时继承 `rounds`（标记里本来就带着，`_do_withdraw` 也传了），或规定 withdraw 后同一人在冷却期（如 72h）内不能认领同一任务。
2. 更干净的口径：withdraw 前已被退回 ≥1 轮的，按设计 §4.4.3「轮次用尽或显式判定无效」处理——至少不清零，并让 `due_at` 从**首次** claim 起算或按剩余时间继承。
3. 补守卫：`withdraw → 同一人 reclaim → rounds 继承`、`临期 withdraw + claim 后原 due 仍生效`，各配一条定点变异（去掉继承逻辑就转红）。

## 与已有 issue 的关系
bodies.txt（#2–#11）里 `withdraw`、`租约` 命中 0；`轮次` 只出现在规则引用里（没有针对本仓这条实现缺陷）。与本仓 #12 无重叠：#12 是**外部用户伪造标记**改写权威记录（修法为只认机器人作者），本条是**持有人在合法命令面内**利用轮次/租约语义漏洞操纵计分——#12 修好后本条依然成立，两者需要各自修。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a2_withdraw_resets_rounds.py`：

```
== 规则路径（不 withdraw）：第 4 次交付应判无效交付 −base
   3 轮退回后： state=claimed rounds=3
   第4次 /deliver : 通过 claimed->disputed holder=alice rounds=3 delta=-10 | @alice 第 4 轮交付超出上限，判无效交付（-10 分）
   alice 本任务净分 = -10
== 绕过路径（withdraw + 立即重新 claim）
   3 轮退回后： state=claimed rounds=3
   alice /withdraw: 通过 claimed->open holder=None rounds=3 delta=0 | @alice 主动释放认领，任务回板
   alice /claim   : 通过 open->claimed holder=alice rounds=0 delta=0 | @alice 认领，锁至 2026-10-12T07:00:36Z
   第4次 /deliver : 通过 claimed->delivered holder=alice rounds=1 delta=0 | @alice 第 1 轮交付（https://e.com/try4）
   /settle        : 通过 verified->settled holder=alice rounds=1 delta=20 | 结算 20 分（expert（base 10））
   alice 本任务净分 = 20
== 续租：72h 租约临期前 withdraw+claim，到期时间被重置，sweep 不扣分
   新到期: 2026-10-14T23:54:36Z | 第 72h sweep 条数 = 0
规则路径净分=-10，绕过路径净分=20（expert base=10）
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 15 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 同一人 withdraw 后再 claim 同一任务，`rounds` 被继承（不清零）
- 临期 withdraw + claim 后，原 `due_at` 仍生效，sweep 能扫到
- `a2_withdraw_resets_rounds.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
