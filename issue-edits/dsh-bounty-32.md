**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（要对照 GitHub 并发组文档语义做离散事件模拟，并解析 workflow；最终定档以维护者为准）
**影响等级建议（补）**：B（需要一个 run 在跑时同一 issue 连来两条评论（特定时序），前一条命令被静默取消。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：并发组没设排队，前一条命令会被 GitHub 静默取消，普通讨论评论也会挤掉排队的命令。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· ；静态解析 workflow（PyYAML）＋按 GitHub 文档语义做的离散事件模拟。**没有跑真实 Actions 调度**，模拟只复现文档写明的排队规则

**依据（GitHub 官方文档，2026-10-11 抓取）**
https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency ：
「By default, any existing `pending` job or workflow in the same concurrency group will be canceled and the new queued job or workflow will take its place.」以及 `queue` 属性：`single`（默认）组内最多 1 个 pending，新来的替换旧的；`max` 最多 100 个 pending 排队

## 现象
同一 issue 的并发组没有设 `queue: max`：一个 run 在跑时连来两条评论，前一条被 GitHub 静默取消；普通讨论评论也会挤掉排队中的命令

同一 issue 上，一个 run 正在执行（checkout + setup-python + 脚本，保守约 45 秒）时，又来了 2 条及以上评论（任何评论都算，见下）。

## 实测读数
本机实跑（`repro/rC-github-ci/c3_pending_cancel_drops_commands.py`）：

```
concurrency = {'group': 'bounty-${{ github.event.issue.number || github.event_name }}', 'cancel-in-progress': False}
queue 设置 = （未设 ⇒ 默认 single）
job if = github.event_name != 'issue_comment' || github.event.issue.pull_request == null
job if 是否过滤非命令评论： False

执行的 run：
  t=  0s @alice           /claim                                     命令 /claim
  t= 15s @carol           这个任务需要先读哪几个文件？                             （非命令，空跑）
  t= 80s @erin            期待                                         （非命令，空跑）
被取消的 run（无回评、无事件）：
  t=  8s @bob             /claim                                     ⚠ 命令 /claim 丢失
  t= 60s @alice           /deliver https://github.com/FuRongJun-19   ⚠ 命令 /deliver 丢失
  t= 70s @dave            +1                                         （非命令）
  t= 75s @FuRongJun-1999  /verify pass CI 全绿                         ⚠ 命令 /verify 丢失
丢失的命令：3 条 → [('bob', '/claim'), ('alice', '/deliver'), ('FuRongJun-1999', '/verify')]
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 c3_pending_cancel_drops_commands.py`；只读导入上游、不写仓库文件、不触网。

### c3_pending_cancel_drops_commands.py
```python
# -*- coding: utf-8 -*-
"""C3：concurrency 组按 issue 号分组、未设 `queue: max`。GitHub 文档（Control workflow concurrency）：
「默认 queue: single——组内最多 1 个 pending；新 run 入队时，已有的 pending run 被取消并被替换」。
而 job 级 `if` 只滤掉 PR 评论，**普通讨论评论也会起一个 run** 进同一组。
⇒ 同一 issue 上，一个 run 在跑时连来两条评论，前一条就被静默取消：命令没有任何回评，也不进账本。
本脚本：①静态读取 workflow 确认组键与 queue 设置；②按文档语义做离散事件模拟（不是真 Actions 调度）。"""
import json, os, subprocess
from _c import CLONE, bb

PY = os.environ.get("DSH_YAML_PYTHON") or __import__("sys").executable  # 需能 import yaml
wf = json.loads(subprocess.run([PY, "-c", "import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1])),default=str))",
                                os.path.join(CLONE, ".github/workflows/bounty.yml")],
                               capture_output=True, text=True, check=True).stdout)
conc = wf["concurrency"]
print("concurrency =", conc)
print("queue 设置 =", conc.get("queue", "（未设 ⇒ 默认 single）"))
job_if = wf["jobs"]["route"]["if"]
print("job if =", " ".join(job_if.split()))
print("job if 是否过滤非命令评论：", "parse_command" in job_if or "startsWith" in job_if)

RUN_SECONDS = 45   # checkout + setup-python + 脚本（含 count_active_claims 扫描），保守估计


def simulate(arrivals, run_seconds=RUN_SECONDS):
    """queue: single 语义：组内 1 running + 至多 1 pending；新来者替换 pending。"""
    running_until, pending, done, cancelled, t_now = None, None, [], [], 0
    timeline = sorted(arrivals)
    i = 0
    while i < len(timeline) or pending is not None:
        nxt_arr = timeline[i][0] if i < len(timeline) else None
        if running_until is not None and (nxt_arr is None or running_until <= nxt_arr):
            t_now = running_until
            running_until = None
            if pending is not None:
                done.append(pending); running_until = t_now + run_seconds; pending = None
            continue
        t, who, body = timeline[i]; i += 1
        if running_until is None:
            done.append((t, who, body)); running_until = t + run_seconds
        else:
            if pending is not None:
                cancelled.append(pending)
            pending = (t, who, body)
    return done, cancelled


arrivals = [
    (0, "alice", "/claim"),
    (8, "bob", "/claim"),
    (15, "carol", "这个任务需要先读哪几个文件？"),   # 普通讨论
    (60, "alice", "/deliver https://github.com/FuRongJun-1999/dsh-bounty/pull/12"),
    (70, "dave", "+1"),
    (75, "FuRongJun-1999", "/verify pass CI 全绿"),
    (80, "erin", "期待"),
]
done, cancelled = simulate(arrivals)
print()
print("执行的 run：")
for t, who, body in done:
    cmd, _ = bb.parse_command(body)
    print(f"  t={t:>3}s @{who:<15} {body[:40]:<42} {'命令 '+cmd if cmd else '（非命令，空跑）'}")
print("被取消的 run（无回评、无事件）：")
for t, who, body in cancelled:
    cmd, _ = bb.parse_command(body)
    print(f"  t={t:>3}s @{who:<15} {body[:40]:<42} {'⚠ 命令 '+cmd+' 丢失' if cmd else '（非命令）'}")
lost_cmds = [c for c in cancelled if bb.parse_command(c[2])[0]]
print(f"丢失的命令：{len(lost_cmds)} 条 → {[(c[1], bb.parse_command(c[2])[0]) for c in lost_cmds]}")
print("VERDICT=BUG" if lost_cmds and conc.get("queue") != "max" else "VERDICT=OK")
```

## 代码定位
- `.github/workflows/bounty.yml:43-48`：注释写的是「同一 issue 上串行（防两条命令并发改标签）」，`cancel-in-progress: false` 只保证**正在跑的**不被打断，但默认 `queue: single` 会取消**排队中的**那个。作者的意图（逐条串行处理）需要 `queue: max` 才能实现。
- `:58-60` job 级 `if` 只过滤 PR 评论。并发组在 workflow 级求值，普通讨论评论（「+1」「期待」）同样会起一个 run、占据唯一的 pending 位，把前面排队的命令挤掉。
- 命令 run 的耗时随在途悬赏数线性增长（见 C-07），run 越慢，窗口越大。

```
.github/workflows/bounty.yml:43-48

# 同一 issue 上串行（防两条命令并发改标签）；不同 issue 互不阻塞。
# cancel-in-progress: false —— 认领/交付是**状态迁移**，中途打断会留下半截痕。
concurrency:
  group: bounty-${{ github.event.issue.number || github.event_name }}
  cancel-in-progress: false

.github/workflows/bounty.yml:58-60
    if: >-
      github.event_name != 'issue_comment' ||
      github.event.issue.pull_request == null

.github/workflows/bounty.yml:1-1
name: bounty
```

## 影响
- 新悬赏刚发布时多人抢 `/claim`、维护者紧接着 `/verify`、讨论区刷「+1」，这些都是常见场景。被取消的命令在 issue 里没有任何回评，用户只能自己发现、重发。
- `/deliver` 被吞且用户没察觉 → 到期后被 sweep 扣 −2base。

## 修法
1. `concurrency` 加 `queue: max`（文档明确与 `cancel-in-progress: true` 不能同用，本 workflow 是 false，可以直接加）。注意：本次用的 actionlint 1.7.12 对 workflow 本身 0 报错，加 `queue` 后需确认所用 lint 版本认识该键。
2. job 级 `if` 再加一道「评论以 `/` 开头」的粗筛（例如 `startsWith(github.event.comment.body, '/')`；只是省 run，权威判定仍在 `parse_command`），让讨论评论不再进组。
3. 作为兜底，在 README 里写明「命令无回评即未处理，可重发」。

## 与已有 issue 的关系
B-08 讲的是**不同 issue** 之间的认领竞态（组按 issue 分导致不互斥）；本篇是**同一 issue 组内**排队被取消导致命令丢失，机理相反。bodies.txt 中 `concurrency` 0 命中，`queue`/`cancel`/`取消` 的命中都在其他仓库的交付帖里（`evidence/rC-github-ci/dedup_grep.txt`）。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 c3_pending_cancel_drops_commands.py`：

```
concurrency = {'group': 'bounty-${{ github.event.issue.number || github.event_name }}', 'cancel-in-progress': False}
queue 设置 = （未设 ⇒ 默认 single）
job if = github.event_name != 'issue_comment' || github.event.issue.pull_request == null
job if 是否过滤非命令评论： False
执行的 run：
  t=  0s @alice           /claim                                     命令 /claim
  t= 15s @carol           这个任务需要先读哪几个文件？                             （非命令，空跑）
  t= 80s @erin            期待                                         （非命令，空跑）
被取消的 run（无回评、无事件）：
  t=  8s @bob             /claim                                     ⚠ 命令 /claim 丢失
  t= 60s @alice           /deliver https://github.com/FuRongJun-19   ⚠ 命令 /deliver 丢失
  t= 70s @dave            +1                                         （非命令）
  t= 75s @FuRongJun-1999  /verify pass CI 全绿                         ⚠ 命令 /verify 丢失
丢失的命令：3 条 → [('bob', '/claim'), ('alice', '/deliver'), ('FuRongJun-1999', '/verify')]
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 15 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- `bounty.yml` 的 `concurrency` 带 `queue: max`（或等效设置），模拟中连续两条命令都被执行
- 非命令评论不进入并发组
- `c3_pending_cancel_drops_commands.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准；并发组的排队行为是按 GitHub 文档语义模拟的，没有在真实 runner 上观测。
