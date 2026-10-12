**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（涉及站点生成器、账本推演与 workflow 触发，需要读两三个文件；最终定档以维护者为准）
**影响等级建议（补）**：A（默认（账本推演）模式下悬赏板永远是空的，与空板文案承诺相反，悬赏板主功能失效；不影响计分。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：默认模式下新发布的悬赏和招标中的任务都上不了悬赏板。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯逻辑层

## 现象
默认（账本推演）模式下，新发布的悬赏永远上不了悬赏板；招标中的任务也不上板。空板文案却承诺「打 `bounty` 标签并发布后此处自动出现」

：不带 `--tasks` 运行 `scripts/build_site.py`（README 的标准命令、`site/` 的生成方式）。维护者给 issue 打上 `bounty` + `bounty:open`（或 `bounty:contest`）后，在任何人发命令之前。

## 实测读数
本机实跑（`repro/rD-site/d3_new_bounty_never_on_board.py`）：

```
#21 当前态（状态机重建）： open ｜ 产生事件数： 0
#23 当前态（状态机重建）： contest ｜ 任何人都可 /bid
生成器 rc= 0 ｜ 悬赏板上的任务： （空）
空板文案承诺「打 bounty 标签并发布后此处自动出现」： True
对照：#21 上一条被拒命令后 open_tasks = ['21']
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 d3_new_bounty_never_on_board.py`；只读导入上游、不写仓库文件、不触网。

### d3_new_bounty_never_on_board.py
```python
# -*- coding: utf-8 -*-
"""D-01：默认（账本推演）模式下，新发布的悬赏永远上不了悬赏板；招标中的任务也不上板。
用真实状态机（rA 线程模拟器）走流程，账本 = 各线程产出事件之和；再按默认参数（无 --tasks）真跑生成器。"""
from _d import *

# #21 维护者刚发布：打了 bounty + bounty:open + difficulty:hard，还没人发命令
t21 = Thread(number=21, labels=("bounty", "bounty:open", "difficulty:hard"))
# #22 alice 认领中
t22 = Thread(number=22, labels=("bounty", "bounty:open", "difficulty:easy")); t22.run("alice", "/claim", at(0))
# #23 招标中：已有一份投标，仍在接受 /bid
t23 = Thread(number=23, labels=("bounty", "bounty:contest", "difficulty:expert")); t23.run("bob", "/bid https://github.com/o/r/pull/9", at(1))
print("#21 当前态（状态机重建）：", t21.state().state, "｜ 产生事件数：", len(t21.ledger))
print("#23 当前态（状态机重建）：", t23.state().state, "｜ 任何人都可 /bid")
ledger = t21.ledger + t22.ledger + t23.ledger
d = tmpdir(); lp = os.path.join(d, "ledger.json"); bb.write_ledger(lp, ledger)
r = run_impl("--ledger", lp, "--out", os.path.join(d, "s"))
board = open(os.path.join(d, "s", "board.html"), encoding="utf-8").read()
shown = [n for n in ("#21", "#22", "#23") if f"<td>{n}</td>" in board]
print("生成器 rc=", r.returncode, "｜ 悬赏板上的任务：", shown or "（空）")
promise = "维护者打 `bounty` 标签并发布后此处自动出现" in board
print("空板文案承诺「打 bounty 标签并发布后此处自动出现」：", promise)
# 对照：有人在 #21 上发了一条被拒命令（非持有者 /deliver），#21 才「出现」
t21.run("mallory", "/deliver https://x.example", at(2))
print("对照：#21 上一条被拒命令后 open_tasks =", [x["number"] for x in bs.open_tasks(t21.ledger + t22.ledger + t23.ledger)])
bug = r.returncode == 0 and "#21" not in shown and "#23" not in shown and promise
print("VERDICT=" + ("BUG" if bug else "OK"))
```

## 代码定位
- `scripts/build_site.py:160-164` 账本分支只从 `latest_by_issue(events)` 取任务。而账本里**只有命令产生的事件**，「发布悬赏」（打标签）不产生任何事件（`bounty_board.py` 里没有 publish/open 事件）。于是账本模式能上板的只有「曾被认领、后来 withdraw/expire 回板」的任务，或碰巧有人发过一条被拒命令的任务（对照行）。
- `CLAIMABLE = ("open", "expired")`（`:56`）不含 `contest`；招标中的任务接受任何人 `/bid`，但板上没有入口。
- `:297-298` 的空板文案「维护者打 `bounty` 标签并发布后此处自动出现」在默认模式下不成立。

```
scripts/build_site.py:160-164
        for num, ev in latest_by_issue(events).items():
            recs.append({"number": num, "title": "", 
                         "difficulty": str(ev.get("difficulty") or ""),
                         "state": str(ev.get("to") or ""),
                         "holder": str(ev.get("holder") or ""), "url": ""})

scripts/build_site.py:56-56
CLAIMABLE = ("open", "expired")

scripts/build_site.py:297-298
        table = ('<p class="muted">（当前没有可认领的悬赏——账本里没有 '
                 "`open` 态的任务；维护者打 `bounty` 标签并发布后此处自动出现。）</p>")
```

## 影响
外部贡献者打开悬赏板看到「当前没有可认领的悬赏」，实际上可能有一批新任务在等人。板面反而只展示「被别人放弃过」的任务，选择偏差明显。账本还要等维护者手动并入 artifact 才更新，进一步滞后。

## 修法
悬赏板的任务列表本质是 issue 面的数据，账本只适合做荣誉榜。二选一：
1. 让 `--tasks` 成为悬赏板的唯一真源（定义并文档化快照 schema，见 D-04），无快照时板面明确写「本页未接入 issue 快照，请到 GitHub 按 `label:bounty:open` 筛选」并给链接；
2. 或在 workflow 里加一个 `issues: labeled` 触发，打 `bounty` 标签时写一条 `publish` 事件进账本。
同时决定 `contest` 是否上板（建议上板并标「招标中」）。空板文案按实际能力改写。

## 与已有 issue 的关系
bodies.txt 里 `build_site`、`open_tasks`、`可认领` 0 命中（`evidence/rD-site/dedup_grep.txt`）。A/B/C 三轮没有涉及悬赏板任务来源。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 d3_new_bounty_never_on_board.py`：

```
#21 当前态（状态机重建）： open ｜ 产生事件数： 0
#23 当前态（状态机重建）： contest ｜ 任何人都可 /bid
生成器 rc= 0 ｜ 悬赏板上的任务： （空）
空板文案承诺「打 bounty 标签并发布后此处自动出现」： True
对照：#21 上一条被拒命令后 open_tasks = ['21']
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 6 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 默认模式下打 `bounty` 标签并发布后，悬赏板列出该任务；招标中的任务按设计上板或明确不上板
- 空板文案与实际能力一致
- `d3_new_bounty_never_on_board.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
