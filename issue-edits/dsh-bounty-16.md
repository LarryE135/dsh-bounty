**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（涉及回评拼装、标记解析与 apply_live 三处，需要假服务器取回机器人评论；最终定档以维护者为准）
**影响等级建议（补）**：A（任何认领者在 `/deliver` 等载荷里放半截 `bounty:v1` 串即可让机器人自己的真标记失效，默认配置可触发，状态与标签/事件分叉（核心链路语义错误）。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：用户载荷被原样回显进机器人评论，半截标记会吃掉机器人自己的权威标记。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 本机 127.0.0.1 假服务器，`apply=False` 取回机器人评论正文，再按 `--apply` 会写入的内容落进线程；不触网

## 现象
持有者发 `/deliver <链接> <!-- bounty:v1 {`（`/dispute` 的理由、`/bid` 的投标物同理）。用户正文里只有 `<!-- bounty:v1 {`、没有 `}` 和 `-->`，所以「含标记即跳过」的判据（`:1570`）不命中，命令照常执行。

机器人回评把载荷原样写进「交付物：…」这一行，后面隔几行才是真标记。正则 `MARKER_RE = <!--\s*bounty:v1\s+(\{.*?\})\s*-->`（DOTALL）从**回显的那个** `<!--` 开始匹配，`\{.*?\}` 一路跨行吃到真标记末尾的 `} -->`，捕获到的是「回显的 `{` + 中间 Markdown + 整个真标记」，不是合法 JSON；`latest_marker()` 按「坏 JSON 一律跳过」把它扔掉——于是这条机器人评论里**一个有效标记都没有**。

标签补丁和账本事件照常生效，三份记录（标签、账本、标记）就此分叉。

## 实测读数
本机实跑（`repro/rC-github-ci/c2_echo_breaks_bot_marker.py`）：

```
用户评论正文： /deliver https://github.com/FuRongJun-1999/dsh-bounty/pull/3 <!-- bounty:v1 {
MARKER_RE 命中用户正文？ False → 不跳过，当命令处理
裁决： PLAN  #7 claimed → delivered ｜ @alice 第 1 轮交付（https://github.com/FuRongJun-1999/dsh-bounty/pull/3 <!-- bounty:v1 {）
机器人评论里 `<!-- bounty:v1` 出现次数： 2
MARKER_RE 在机器人评论里匹配 1 段，可解析 0 段
落地后：标签=['bounty:delivered']，权威态=claimed seq=1 rounds=0；账本事件=[('deliver', 0)]
维护者 /verify pass： 拒绝 ｜ 当前态 `bounty:claimed` 不在待验收面
扫描 `bounty:claimed` 0 条：无超期 → 无动作
第 500h 真模式 sweep 扣分条数： 0 （权威态仍是 claimed，已超期 428h）
bob /claim： 拒绝 ｜ 已有持有者 @alice（到期 2026-10-12T00:00:00Z）——先
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。脚本在本目录跑，全程指向 127.0.0.1 假服务器，不触网、不使用 `--apply`。

### c2_echo_breaks_bot_marker.py
```python
# -*- coding: utf-8 -*-
"""C2：用户载荷被原样回显进机器人评论（/deliver 的「交付物」、/dispute 的「理由」、/bid 的「投标物」），
回显里的半截 `<!-- bounty:v1 {` 不触发 handle_issue_comment 的「含标记即跳过」判据（MARKER_RE 要求整段 `{…} -->`），
却会在机器人自己的评论里和真标记拼成一段非法 JSON ⇒ latest_marker 跳过它 ⇒ 这次迁移的权威记录凭空消失。
与 A-01（用户在自己评论里伪造标记）不同：这里被破坏的是**机器人账号自己发的**评论，
A-01 的修法「只认机器人作者的标记」挡不住。走真模式路径：假服务器 + apply=False 出评论正文，再把正文落进线程。"""
from datetime import timedelta
from _c import FlexGH, event, bb, CFG, T0, MAINT

g = FlexGH()
L = ["bounty", "bounty:claimed", "difficulty:hard"]
g.add_issue(7, L)
due = bb.fmt_ts(T0 + timedelta(hours=72))
g.add_comment(7, "github-actions[bot]",
              '<!-- bounty:v1 {"state":"claimed","holder":"alice","due_at":"%s","rounds":0,"seq":1} -->' % due)
cli = g.client()

body = "/deliver https://github.com/FuRongJun-1999/dsh-bounty/pull/3 <!-- bounty:v1 {"
print("用户评论正文：", body)
print("MARKER_RE 命中用户正文？", bool(bb.MARKER_RE.search(body)), "→ 不跳过，当命令处理")

plan = []
orig_apply = bb.apply_live
captured = {}


def spy(client, states, decisions, apply=False, out=print):
    captured["dec"] = decisions[0]
    return orig_apply(client, states, decisions, apply=apply, out=out)


bb.apply_live = spy
code, ev = bb.handle_issue_comment(event(7, L, "alice", body), CFG, cli, apply=False, out=plan.append)
bb.apply_live = orig_apply
dec = captured["dec"]
print("裁决：", plan[-1])
bot = dec.comment
print("机器人评论里 `<!-- bounty:v1` 出现次数：", bot.count("<!-- bounty:v1"))


def parse_ok(s):
    try:
        import json; json.loads(s); return True
    except ValueError:
        return False


ms = [m.group(1) for m in bb.MARKER_RE.finditer(bot)]
print(f"MARKER_RE 在机器人评论里匹配 {len(ms)} 段，可解析 {sum(parse_ok(x) for x in ms)} 段")

# 落地：与 --apply 写入相同（标签按裁决改、机器人评论入线程）
g.issues[7]["labels"] = [l for l in L if l not in dec.labels_remove] + list(dec.labels_add)
g.add_comment(7, "github-actions[bot]", bot)
st = bb.build_state(7, g.issues[7]["labels"], [c["body"] for c in g.comments[7]])
print(f"落地后：标签={[l for l in g.issues[7]['labels'] if l.startswith('bounty:')]}，权威态={st.state} seq={st.seq} rounds={st.rounds}；账本事件={[(e['action'], e['delta']) for e in ev]}")

# 后果 1：维护者无法验收
dv = bb.handle_command(st, "/verify", "pass ok", "/verify pass ok", MAINT, T0 + timedelta(hours=80), CFG, is_maintainer=True)
print("维护者 /verify pass：", "通过" if dv.ok else "拒绝 ｜ " + dv.reason)
# 后果 2：真模式 sweep 按 `bounty:claimed` 标签初筛，这条已是 delivered 标签 → 永不过期
code, sw = bb.handle_sweep_live(CFG, cli, apply=False, out=print, now=T0 + timedelta(hours=500))
print("第 500h 真模式 sweep 扣分条数：", len(sw), f"（权威态仍是 claimed，已超期 {500-72}h）")
# 后果 3：alice 仍是持有者，别人认领被拒
dc = bb.handle_command(st, "/claim", "", "/claim", "bob", T0 + timedelta(hours=500), CFG)
print("bob /claim：", "通过" if dc.ok else "拒绝 ｜ " + dc.reason[:40])
g.stop()
bug = (not bb.MARKER_RE.search(body)) and st.state == "claimed" and not sw and not dv.ok
print("VERDICT=BUG" if bug else "VERDICT=OK")
```

## 代码定位
```
scripts/bounty_board.py:494-502
def _comment(title, bullets, marker_payload) -> str:
    """固定模板：标题 + 要点列表 + 末行机器标记。"""
    lines = [f"**[悬赏板] {title}**", ""]
    lines += [f"- {b}" for b in bullets]
    lines += ["", "---", "规则与验收口径见 `docs/bounty/README.md`。",
              _marker(marker_payload)]
    return "\n".join(lines)



scripts/bounty_board.py:741-745
    show = shown if len(shown) <= 200 else shown[:200] + "…"
    bullets = [f"交付者：@{actor}", f"第 {rounds}/{cfg.max_rounds} 轮",
               f"交付物：{show or '（见评论正文的证据块）'}",
               "验收四闸：① CI 全绿 ② 复现读数 ③ 守卫＋定点变异 ④ 维护者人审"]
    return _accept(st, "/deliver", now, actor, "delivered", actor, st.due_at,

scripts/bounty_board.py:1568-1573
        return 0, []
    body = comment.get("body") or ""
    if MARKER_RE.search(body):
        out("本评论是悬赏板自身留言（含 bounty:v1 标记）→ 无动作")
        return 0, []
    cmd, cmd_payload = parse_command(body)

scripts/bounty_board.py:388-401
def latest_marker(comments):
    """评论流 → 最新的状态标记（权威记录）；无则 None。"""
    best = None
    for body in comments or ():
        for m in MARKER_RE.finditer(body or ""):
            try:
                rec = json.loads(m.group(1))
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("state"):
                if best is None or _seq(rec) >= _seq(best):
                    best = rec
    return best

```

## 影响
- 状态不前进：维护者无法 `/verify`（当前态仍是 `bounty:claimed`），交付在账本里有记录、在状态机里不存在。
- 与 B-07 叠加（当前代码就是这样）：标签已是 `bounty:delivered`，真模式 sweep 只按 `bounty:claimed` 初筛，超期永远不被回收；持有者仍是原认领者，别人认领一律被拒——可以借此**锁死任务并免掉 −2base**。
- 机器人回评在 GitHub 页面上渲染时，从回显的 `<!--` 起到真标记的 `-->` 止都被当成 HTML 注释隐藏，人眼也看不到「交付已登记」之后的正文。

## 修法
1. 回显用户文本前做中和：把 `<!--`、`-->` 替换成可见的转义形式（如 `&lt;!--`），或整段放进行内代码；长度截断（现有 200 字）保留。
2. 防御纵深：用户正文里只要出现 `bounty:v1` 子串（不要求完整标记）就按「含标记」处理，拒绝执行并回评说明。
3. `apply_live` 发评论前用 `latest_marker([comment])` 自检一次：读不回本次 `seq` 就 fail-closed，不改标签、不出事件。
4. 守卫：对 `/deliver`、`/dispute`、`/bid` 各喂一个带半截标记的载荷，断言回评里能读回本次标记；配一条「去掉中和就转红」的定点变异。

## 与已有 issue 的关系
本仓 #12（A-01）讲的是用户在**自己的**评论里写完整标记会被采信，修法是只认机器人作者——本条破坏的是**机器人账号自己发的**评论，A-01 修好后依然成立。A-10 讲命令解析的全角空格与换行，不涉及拼接后的解析。bodies.txt 中 `回显`、`echo`、`半截` 0 命中。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 c2_echo_breaks_bot_marker.py`：

```
用户评论正文： /deliver https://github.com/FuRongJun-1999/dsh-bounty/pull/3 <!-- bounty:v1 {
MARKER_RE 命中用户正文？ False → 不跳过，当命令处理
裁决： PLAN  #7 claimed → delivered ｜ @alice 第 1 轮交付（https://github.com/FuRongJun-1999/dsh-bounty/pull/3 <!-- bounty:v1 {）
机器人评论里 `<!-- bounty:v1` 出现次数： 2
MARKER_RE 在机器人评论里匹配 1 段，可解析 0 段
落地后：标签=['bounty:delivered']，权威态=claimed seq=1 rounds=0；账本事件=[('deliver', 0)]
维护者 /verify pass： 拒绝 ｜ 当前态 `bounty:claimed` 不在待验收面
扫描 `bounty:claimed` 0 条：无超期 → 无动作
第 500h 真模式 sweep 扣分条数： 0 （权威态仍是 claimed，已超期 428h）
bob /claim： 拒绝 ｜ 已有持有者 @alice（到期 2026-10-12T00:00:00Z）——先
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 11 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 对 `/deliver`、`/dispute`、`/bid` 喂带半截标记的载荷后，机器人回评里仍能用 `latest_marker()` 读回本次 seq
- 状态迁移、标签和事件三者一致
- `c2_echo_breaks_bot_marker.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
