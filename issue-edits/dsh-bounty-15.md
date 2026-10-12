**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（跨 apply_live、事件落盘和路由层，要用桩客户端模拟中途失败；最终定档以维护者为准）
**影响等级建议（补）**：B（需要 GitHub API 在一批写入中途失败才触发（瞬时错误路径），触发后已真实生效的扣分事件进不了账本。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：真模式一批写入中途失败时，前面已经写到 GitHub 的事件会从账本里消失。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 全程使用不联网的桩客户端（`_c.py::StubClient`，`apply=True` 只打到桩上），未使用 `--apply`、未触网

## 现象
schedule 腿一次回板多条超期认领时（`handle_sweep_live` → `apply_live`），事件列表是函数内的局部变量，循环里逐条「改标签 → 发评论」且没有 `try`。处理到第 k 条时任何一次 HTTP 写失败（5xx、超时、二级限流——见 C-06：客户端不重试），`BoardError` 直接上抛：函数不返回，**前面已经真写成功的那些裁决的事件跟着一起丢**。

`main` 只在 handler 正常返回后才 `write_jsonl(args.ledger_out, events)`；异常走 `except BoardError` 直接退 2，JSONL 根本没生成。workflow 的 artifact 步骤虽然写了 `if: always()`，但文件不存在，而 `if-no-files-found: ignore` 让这件事悄无声息。

## 实测读数
本机实跑（`repro/rC-github-ci/c2_partial_apply_loses_events.py`）：

```
扫描 `bounty:claimed` 3 条：超期 3 条 → 回板
APPLY #1 claimed → open ｜ @alice 认领超时未交付，自动回板
APPLY #2 claimed → open ｜ @bob 认领超时未交付，自动回板
handle_sweep_live 结果： 抛出 BoardError → GitHub API POST /repos/FuRongJun-1999/dsh-bounty/issues/2/comments → H
main 拿到的事件（将写进 --ledger-out 的 JSONL）： 无（异常上抛，main 走 except 退 2，write_jsonl 未执行）

#1 远端标签=['bounty:open'] 权威态=open holder=None
#2 远端标签=['bounty:open'] 权威态=claimed holder=bob
#3 远端标签=['bounty:claimed'] 权威态=claimed holder=carol
桩上实际写入： [('set_labels', 1), ('comment', 1), ('set_labels', 2)]
#1 已真写（回板评论含 expire 标记、应记 alice -12），但这条事件不在任何 artifact 里：True

== 下一次 sweep（6 小时后，桩恢复正常）==
扫描 `bounty:claimed` 1 条：超期 1 条 → 回板
APPLY #3 claimed → open ｜ @carol 认领超时未交付，自动回板
第二次 sweep 记到的超时持有者： ['carol']
#2 权威态仍是 claimed（超期 34h），但标签已是 open → 不在 sweep 初筛里，bob 永不被扣分
汇总：alice 的 -12 永久丢失；bob 永久逃逸；只有 carol 被记
VERDICT=BUG
```

## 最小复现
依赖：纯标准库 + PyYAML（脚本会读模板/ workflow 时用到）。脚本默认在本目录跑，GitHub 侧全部指向 127.0.0.1 假服务器或桩客户端，不触网。

### c2_partial_apply_loses_events.py
```python
# -*- coding: utf-8 -*-
"""C2：apply_live 逐条「先改标签、再发评论」，任何一步抛 BoardError 就整体上抛：
(1) 同批中已经真写成功的裁决（标签+含标记的评论都已落地），其账本事件随异常一起丢失——
    main 只在 handler 正常返回后才 write_jsonl，artifact 里一条都没有；
(2) 失败那条停在「标签已改、评论（=权威标记）没发」的半截态；sweep 只按 `bounty:claimed` 标签初筛，
    于是这条超期认领从此再也扫不到，超时扣分永久逃逸。
用不联网的 StubClient（apply=True 只打到桩上），不使用 --apply、不触网。"""
from datetime import timedelta
from _c import StubClient, bb, CFG, T0


def claimed(n, holder, diff="difficulty:hard"):
    due = bb.fmt_ts(T0 + timedelta(hours=72))
    mk = '<!-- bounty:v1 {"state":"claimed","holder":"%s","due_at":"%s","rounds":0,"seq":1} -->' % (holder, due)
    return {"n": n, "labels": ["bounty", "bounty:claimed", diff], "comments": [mk]}


world = {1: claimed(1, "alice"), 2: claimed(2, "bob"), 3: claimed(3, "carol")}


class LiveStub(StubClient):
    """桩：同时扮演只读面（issues_with_label/comments），写面落到 world 里。"""

    def issues_with_label(self, label, limit=10):
        return [{"number": n, "labels": [{"name": l} for l in w["labels"]], "user": {"login": "m"}}
                for n, w in world.items() if label in w["labels"]]

    def comments(self, n):
        return list(world[n]["comments"])

    def set_labels(self, n, add, remove):
        super().set_labels(n, add, remove)
        for l in remove:
            if l in world[n]["labels"]:
                world[n]["labels"].remove(l)
        for l in add:
            if l not in world[n]["labels"]:
                world[n]["labels"].append(l)

    def comment(self, n, body):
        super().comment(n, body)
        world[n]["comments"].append(body)


now = T0 + timedelta(hours=100)
cli = LiveStub(fail_on={("comment", 2)})      # #2 的评论 POST 失败（如 502/超时）
events, err = None, None
try:
    _code, events = bb.handle_sweep_live(CFG, cli, apply=True, out=print, now=now)
except bb.BoardError as e:
    err = e
print("handle_sweep_live 结果：", "抛出 BoardError → " + str(err)[:70] if err else f"返回 {len(events)} 条事件")
print("main 拿到的事件（将写进 --ledger-out 的 JSONL）：", events if events is not None else "无（异常上抛，main 走 except 退 2，write_jsonl 未执行）")
print()
for n in (1, 2, 3):
    st = bb.build_state(n, world[n]["labels"], world[n]["comments"])
    print(f"#{n} 远端标签={[l for l in world[n]['labels'] if l.startswith('bounty:')]} 权威态={st.state} holder={st.holder}")
print("桩上实际写入：", [(c[0], c[1]) for c in cli.calls if c[0] != "ensure_labels"])
w1 = any(c[0] == "comment" and c[1] == 1 for c in cli.calls)
print(f"#1 已真写（回板评论含 expire 标记、应记 alice {bb.timeout_delta(6)[0]}），但这条事件不在任何 artifact 里：{w1 and events is None}")

print()
print("== 下一次 sweep（6 小时后，桩恢复正常）==")
cli2 = LiveStub()
_c2, ev2 = bb.handle_sweep_live(CFG, cli2, apply=True, out=print, now=now + timedelta(hours=6))
who = sorted({e.get("holder") for e in ev2})
print("第二次 sweep 记到的超时持有者：", who)
st2 = bb.build_state(2, world[2]["labels"], world[2]["comments"])
print(f"#2 权威态仍是 {st2.state}（超期 {(now + timedelta(hours=6) - T0).total_seconds()/3600 - 72:.0f}h），但标签已是 open → 不在 sweep 初筛里，bob 永不被扣分")
lost = (events is None and w1) and ("bob" not in who) and ("alice" not in who)
print(f"汇总：alice 的 {bb.timeout_delta(6)[0]} 永久丢失；bob 永久逃逸；只有 carol 被记")
print("VERDICT=BUG" if lost else "VERDICT=OK")
```

## 代码定位
```
scripts/bounty_board.py:1542-1562
def apply_live(client, states, decisions, apply=False, out=print):
    """把裁决打到远端（`apply=False` 只打印计划）；返回本批事件列表。"""
    events = []
    for st, dec in zip(states, decisions):
        events.append(dec.event)
        out(f"{'APPLY ' if apply else 'PLAN  '}#{st.number} {dec.from_state} → "
            f"{dec.to_state} ｜ {dec.reason}")
        if apply:
            if not client.labels_ready:
                # 首跑幂等建标签体系（`gh label create --force` 形态）：
                # 缺标签时加标签会被 GitHub 拒（422），故在第一次真写前补一次。
                made = client.ensure_labels(LABEL_SPECS)
                client.labels_ready = True
                if made:
                    out(f"（首跑建标签 {len(made)} 个：{', '.join(made)}）")
            client.set_labels(st.number, dec.labels_add, dec.labels_remove)
            client.comment(st.number, dec.comment)
    return events


# 生效条件：payload 为 issue_comment 事件体、cfg 为 Config、client 为 GitHubClient 时处理一条评论命令并返回 (退出码, 事件列表)——PR 评论/自带标记的评论/非命令评论一律无动作；维护者面 = 名单 ∨ author_association ∈ {OWNER,MEMBER,COLLABORATOR}。

scripts/bounty_board.py:1770-1785
                                 "——令牌只从环境变量读，绝不硬编码")
            client = GitHubClient(repo, token)
            if name == "issue_comment":
                code, events = handle_issue_comment(payload, cfg, client,
                                                    apply=args.apply)
            elif name in ("schedule", "workflow_dispatch"):
                code, events = handle_sweep_live(cfg, client, apply=args.apply)
            else:
                print(f"未识别的事件（{name or '未知'}）→ 无动作")
                code, events = 0, []
            if args.ledger_out and events:
                write_jsonl(args.ledger_out, events)
                print(f"本批事件 {len(events)} 条 → {args.ledger_out}")
            return code

        if args.sweep_live:

.github/workflows/bounty.yml:86-96
      #   python -X utf8 scripts/bounty_board.py --ledger-append <events.jsonl>
      #   python -X utf8 scripts/bounty_board.py --board-out docs/bounty/board.md
      - name: 本批账本事件（artifact；供维护者并入账本）
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: bounty-ledger-events
          path: ${{ runner.temp }}/bounty_events.jsonl
          if-no-files-found: ignore
          retention-days: 90
```

## 影响
- #1 的回板评论（含 `expire` 标记）已经发出、状态已回到 open；下一次 sweep 看到 open 不会再扣，alice 的 −2base（hard 任务 −12）永久缺失，荣誉榜偏高。
- 同理适用于 issue_comment 腿：`/settle` 的评论已发出而后续步骤失败时，结算分也会丢（单条批次里评论是最后一步，所以命令腿概率低于 sweep 腿）。
- 附带现象（B-07 已报告，此处不重复计数）：失败那条停在「标签已改、标记未写」的半截态，被真模式 sweep 的标签初筛漏掉，任务被锁。

## 修法
1. `apply_live` 每成功写完一条（评论落地后）就把该条事件追加进结果并**立即**追加写入 `--ledger-out`（或至少在 `finally` 里写出已成功部分）；失败条目单独记告警、继续处理其余条目，最后以非零退出码收尾。
2. 采纳 B-07 的建议「先发评论（权威标记）、再改标签」，让失败点只留下「标记已写、标签落后」，这一侧可由下次命令用 `label_patch` 自愈。
3. 补路由层守卫：桩客户端在第 2 条评论处抛错，断言 JSONL 里仍有第 1 条的 `expire` 事件；配一条「去掉逐条落盘就转红」的定点变异。

## 与已有 issue 的关系
A 轮 REPORT「三、线索」只提到「先改标签后发评论 → 人眼视图暂时不一致」；B-07（#24）报告的是半截态造成的标签/标记不一致及其对计数、sweep 的影响。两者都没有涉及**已成功条目的事件随异常丢失**。bodies.txt 中 `apply_live`、`部分写` 0 命中。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 c2_partial_apply_loses_events.py`：

```
扫描 `bounty:claimed` 3 条：超期 3 条 → 回板
APPLY #1 claimed → open ｜ @alice 认领超时未交付，自动回板
APPLY #2 claimed → open ｜ @bob 认领超时未交付，自动回板
handle_sweep_live 结果： 抛出 BoardError → GitHub API POST /repos/FuRongJun-1999/dsh-bounty/issues/2/comments → H
main 拿到的事件（将写进 --ledger-out 的 JSONL）： 无（异常上抛，main 走 except 退 2，write_jsonl 未执行）
#1 远端标签=['bounty:open'] 权威态=open holder=None
#2 远端标签=['bounty:open'] 权威态=claimed holder=bob
#3 远端标签=['bounty:claimed'] 权威态=claimed holder=carol
桩上实际写入： [('set_labels', 1), ('comment', 1), ('set_labels', 2)]
#1 已真写（回板评论含 expire 标记、应记 alice -12），但这条事件不在任何 artifact 里：True
== 下一次 sweep（6 小时后，桩恢复正常）==
扫描 `bounty:claimed` 1 条：超期 1 条 → 回板
APPLY #3 claimed → open ｜ @carol 认领超时未交付，自动回板
第二次 sweep 记到的超时持有者： ['carol']
#2 权威态仍是 claimed（超期 34h），但标签已是 open → 不在 sweep 初筛里，bob 永不被扣分
汇总：alice 的 -12 永久丢失；bob 永久逃逸；只有 carol 被记
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 17 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 桩客户端在第 2 条评论处抛错时，`--ledger-out` 的 JSONL 里仍保留第 1 条已落地的事件（如 `expire`）
- 进程以非零退出码结束并告警失败条目
- `c2_partial_apply_loses_events.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
