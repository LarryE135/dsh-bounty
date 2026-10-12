**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：easy（单点：`append_events` 的去重集合没有在循环里更新；最终定档以维护者为准）
**影响等级建议（补）**：B（需要同一批 JSONL 里出现重复事件（例如重复并入同一 artifact）才触发；触发后同一结算重复计分且无法撤回。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：「按 id 幂等」只和已有账本比，同一批里的重复事件会全部入账。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯逻辑层

## 现象
「按 id 幂等」只对已有账本生效，同一批次里的重复事件全部入账：同一笔结算并入两次，荣誉榜分数翻倍，而且 append-only 账本没法撤回

`--ledger-append` 读入的 JSONL 里，同一事件（同一个 `id`）出现两次以上。现实中的来源：
- workflow 每次运行都上传一个同名 artifact `bounty-ledger-events/bounty_events.jsonl`（`.github/workflows/bounty.yml`）。维护者批量下载后用 `cat */bounty_events.jsonl > all.jsonl` 合并，同一个 artifact 下载了两次，就会出现重复行；
- 手工整理 JSONL 时复制粘贴多了一行。

## 实测读数
本机实跑（`repro/rB-ledger/b1_batch_dup_double_count.py`）：

```
① append_events([], [ev, ev]) → 条数 = 2 ；ids = ['evt_2f5b385765ab', 'evt_2f5b385765ab']
   score_board alice = 24 （应为 12）
   再投递一次（跨批次）→ 条数 = 2 （跨批次去重是生效的）
② --ledger-append 同一事件×2：rc=0 账本并入：读入 2 条 → 账本现 2 条 → C:\Users\Larry\AppData\Local\Temp\rB_dup_dvpt0i5f\ledger.json
   账本 events 条数 = 2 ；不同 id 数 = 1
   board.md alice 行： | @alice | 24 | 2 | 0 | 0 | 0 | 0 | 2026-10-09T01:00:00Z | 2026-10-09T01:00:00Z |
③ 同一 JSONL 再并一次： 账本并入：读入 2 条 → 账本现 2 条 → C:\Users\Larry\AppData\Local\Temp\rB_dup_dvpt0i5f\ledger.json （账本已有该 id → 0 新增，但前一次的重复行已经永久留在 append-only 账本里）
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 b1_batch_dup_double_count.py`；只读导入上游、不写仓库文件、不触网。

### b1_batch_dup_double_count.py
```python
# -*- coding: utf-8 -*-
"""B1-1：append_events 只拿「既有账本」去重，同一批次内部的重复 id 不去重
⇒ 一份 JSONL 里同一事件出现两次（重复下载/拼接 artifact），--ledger-append 照单全收，荣誉榜双倍计分。"""
import os, json, tempfile
from _b import bb, mkev, cli

ev = mkev()                                    # alice 一次 hard 结算 +12
# ① 纯函数
merged = bb.append_events([], [ev, dict(ev)])
print("① append_events([], [ev, ev]) → 条数 =", len(merged), "；ids =", [e["id"] for e in merged])
print("   score_board alice =", bb.score_board(merged)["alice"]["score"], "（应为 12）")
merged2 = bb.append_events(merged, [dict(ev)])
print("   再投递一次（跨批次）→ 条数 =", len(merged2), "（跨批次去重是生效的）")

# ② CLI：维护者把两次下载的 artifact 拼成一份再并入（README §八 的收口命令）
d = tempfile.mkdtemp(prefix="rB_dup_")
jl = os.path.join(d, "events.jsonl"); led = os.path.join(d, "ledger.json"); bd = os.path.join(d, "board.md")
line = json.dumps(ev, ensure_ascii=False, sort_keys=True)
open(jl, "w", encoding="utf-8").write(line + "\n" + line + "\n")
rc, out, err = cli("--ledger-append", jl, "--ledger", led)
print("② --ledger-append 同一事件×2：rc=%d %s" % (rc, out.strip()))
doc = json.load(open(led, encoding="utf-8"))
ids = [e["id"] for e in doc["events"]]
print("   账本 events 条数 =", len(ids), "；不同 id 数 =", len(set(ids)))
rc, out, err = cli("--board-out", bd, "--ledger", led)
row = [l for l in open(bd, encoding="utf-8") if l.startswith("| @alice")]
print("   board.md alice 行：", row[0].strip() if row else None)
rc2, out2, _ = cli("--ledger-append", jl, "--ledger", led)
print("③ 同一 JSONL 再并一次：", out2.strip(), "（账本已有该 id → 0 新增，但前一次的重复行已经永久留在 append-only 账本里）")
bug = len(merged) == 2 and len(ids) == 2 and len(set(ids)) == 1
print("VERDICT=BUG" if bug else "VERDICT=OK")
```

## 代码定位
`scripts/bounty_board.py:901-902`：
```python
seen = {e.get("id") for e in events or []}
added = [e for e in (new or []) if e.get("id") and e.get("id") not in seen]
```
`seen` 只从**既有账本**算一次，筛选 `new` 时没有把刚放进 `added` 的 id 加进 `seen`，所以同批次内部的重复项都能通过。docstring（`:898`）和 README §四、§八都承诺「按 id 幂等（重复投递不重复入账）」。

```
scripts/bounty_board.py:901-902
    seen = {e.get("id") for e in events or []}
    added = [e for e in (new or []) if e.get("id") and e.get("id") not in seen]
```

## 影响
- 荣誉榜（`render_board`）和 build_site 的荣誉页直接对账本求和，重复的结算会让分数翻倍（复现里 hard 一次过 +12 变成 +24，「已结算」也从 1 变成 2）。
- 账本按规则「禁手改既有行」，重复行一旦提交就只能违反 append-only 去删除。
- 现有守卫 `tests/test_bounty_board.py:279-284` 只测了「跨批次重复」，没有测「同批次重复」，所以 88/88 全绿也发现不了。

## 修法
```python
seen = {e.get("id") for e in events or []}
added = []
for e in new or []:
    i = e.get("id")
    if i and i not in seen:
        seen.add(i); added.append(e)
```
再补一条守卫：`append_events([], [ev, ev])` 必须只有 1 条（定点变异：去掉 `seen.add` 必须被抓到）。

## 与已有 issue 的关系
bodies.txt 里 `append_events`、`幂等`、`ledger-append` 都是 0 命中（`evidence/rB-ledger/dedup_grep.txt`）。A 轮 17 篇都没有涉及 `append_events`。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 b1_batch_dup_double_count.py`：

```
① append_events([], [ev, ev]) → 条数 = 2 ；ids = ['evt_2f5b385765ab', 'evt_2f5b385765ab']
   score_board alice = 24 （应为 12）
   再投递一次（跨批次）→ 条数 = 2 （跨批次去重是生效的）
② --ledger-append 同一事件×2：rc=0 账本并入：读入 2 条 → 账本现 2 条 → /tmp/rB_dup_3ufc82sn/ledger.json
   账本 events 条数 = 2 ；不同 id 数 = 1
   board.md alice 行： | @alice | 24 | 2 | 0 | 0 | 0 | 0 | 2026-10-09T01:00:00Z | 2026-10-09T01:00:00Z |
③ 同一 JSONL 再并一次： 账本并入：读入 2 条 → 账本现 2 条 → /tmp/rB_dup_3ufc82sn/ledger.json （账本已有该 id → 0 新增，但前一次的重复行已经永久留在 append-only 账本里）
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 8 行输出中 6 行能在正文代码块里找到同样的行；其余 2 行不同：`② --ledger-append 同一事件×2：rc=0 账本并入：读入 2 条 → 账本现 2 条 → /tmp/rB_dup_3ufc82sn/ledger.json`；`③ 同一 JSONL 再并一次： 账本并入：读入 2 条 → 账本现 2 条 → /tmp/rB_dup_3ufc82sn/ledger.json （账本已有该 id → 0 新增`。结论（末行 VERDICT=BUG）一致。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- `append_events([], [ev, ev])` 只留 1 条
- 同一结算在一个 JSONL 里出现 2 次时，账本只增 1 条，alice 荣誉榜 12 分（不是 24）
- `b1_batch_dup_double_count.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
