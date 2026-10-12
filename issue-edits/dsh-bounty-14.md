**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：medium（涉及 write_ledger / save_store / --board-out 三处写盘和 CLI 并发，要读两三个文件、带真实子进程读数；最终定档以维护者为准）
**影响等级建议（补）**：B（账本被写成 0 字节属于数据丢失，但需要写入中途被杀或两个 `--ledger-append` 并发，属特定路径；若维护者认为并发并入是常规操作可上调 A。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：账本和镜像都是「先清空再重写」，中途出错就丢账，并发就丢事件。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯标准库，真实子进程 + 真实 CLI；只在临时副本里写盘，未改上游文件

## 现象
账本是声誉分的唯一真源，但所有写盘入口都是「先清空、再重写」：`open(path, "w")` 一打开文件就被截成 0 字节，随后 `json.dump` 才开始写；`--ledger-append` 的流程是「读整本 → 内存合并 → 整体重写」，中间没有锁，也不检查文件在读之后是否被改过。

因此有三类触发：

- (a) 重写途中进程被终止（Ctrl-C、CI 超时、OOM）或磁盘写满；
- (b) 两个 `--ledger-append` 并发（脚本里循环并入多个 artifact 用了 `&`，或两位维护者共享工作区）；
- (c) `--state` 离线镜像的 `save_store` 写到一半失败。

## 实测读数
本机实跑（`repro/rB-ledger/b1_nonatomic_write.py`，真实子进程与真实 CLI）：

```
初始账本：60000 条事件，18098781 字节
(a) 写入途中 SIGTERM：第 1 次命中，账本剩 0 字节（原 18098781）→ load_ledger BoardError：账本不是合法 JSON：C:\Users\Larry\AppData\Local\Temp\rB_atomic_flf6vyga\ledger.json（Exp
(b) 并发 --ledger-append 20 轮（每轮 2 条新事件）：进程退出码 [0]；丢失事件 20 条（其中账本读坏 0 轮）
(b') 交错读改写：最终 4 条，anna 的事件在不在：False
(c) save_store 写到一半失败： [Errno 28] No space left on device（模拟）
    load_store → 状态文件不是合法 JSON：C:\Users\Larry\AppData\Local\Temp\rB_atomic_flf6vyga\state.json（Expecting pr
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 b1_nonatomic_write.py`。平台差异：原脚本用 `socket.SIGKILL`；Windows 没有该常量，这里的版本改用 `SIGTERM`（对无信号处理的 Python 进程同样是硬终止）。

### b1_nonatomic_write.py
```python
# -*- coding: utf-8 -*-
"""B1-3：write_ledger / save_store / --board-out 都是「open(path,'w') 先清空、再整体重写」，无临时文件+rename、无锁
⇒ (a) 写到一半进程被杀/磁盘满：账本只剩半截，下次读直接报「不是合法 JSON」，既有事件全不可读；
   (b) 两个 --ledger-append 并发（读-改-写无锁）：后写者覆盖先写者，先写者的事件静默丢失；
   (c) 离线镜像 save_store 同样问题。"""
import os, json, tempfile, subprocess, sys, time, signal
from _b import bb, mkev, cli, SCRIPT

d = tempfile.mkdtemp(prefix="rB_atomic_")
led = os.path.join(d, "ledger.json")
old = [mkev(issue=i, holder="u%d" % (i % 50), ts="2026-10-09T%02d:00:00Z" % (i % 24)) for i in range(1, 60001)]
bb.write_ledger(led, old)
size0 = os.path.getsize(led)
print("初始账本：%d 条事件，%d 字节" % (len(old), size0))

# (a) 真实杀进程：子进程并入 1 条新事件，在它重写账本的过程中 SIGTERM
jl = os.path.join(d, "new.jsonl")
open(jl, "w", encoding="utf-8").write(json.dumps(mkev(issue=99999, holder="zed")) + "\n")
hit = None
for trial in range(40):
    bb.write_ledger(led, old)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.Popen([sys.executable, "-X", "utf8", "-B", SCRIPT, "--ledger-append", jl, "--ledger", led],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=d)
    # 等到文件被截断（说明已进入 open(path,'w')），立即杀
    t_end = time.time() + 10
    while time.time() < t_end and p.poll() is None:
        try:
            sz = os.path.getsize(led)
        except OSError:
            sz = -1
        if 0 <= sz < size0 - 1000:
            p.send_signal(signal.SIGTERM); break
    p.wait()
    sz = os.path.getsize(led)
    if sz < size0:
        try:
            n = len(bb.load_ledger(led))
            res = "仍可读 %d 条" % n
        except bb.BoardError as exc:
            res = "BoardError：" + str(exc)[:80]
        hit = (trial + 1, sz, res)
        break
print("(a) 写入途中 SIGTERM：第 %s 次命中，账本剩 %s 字节（原 %d）→ load_ledger %s" % (
    hit[0] if hit else "-", hit[1] if hit else "-", size0, hit[2] if hit else "未命中"))

# (b) 两个并发 --ledger-append，各并入 1 条不同事件；重复 20 轮，数丢失
small = os.path.join(d, "small.json")
lost = 0; rounds = 20; rcs = []; broken = 0
for r in range(rounds):
    bb.write_ledger(small, old[:20000])
    ja, jb = os.path.join(d, "a.jsonl"), os.path.join(d, "b.jsonl")
    ea, eb = mkev(issue=500000 + r, holder="anna"), mkev(issue=600000 + r, holder="bert")
    open(ja, "w").write(json.dumps(ea) + "\n"); open(jb, "w").write(json.dumps(eb) + "\n")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    ps = [subprocess.Popen([sys.executable, "-X", "utf8", "-B", SCRIPT, "--ledger-append", j, "--ledger", small],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=d) for j in (ja, jb)]
    for p in ps: rcs.append(p.wait())
    try:
        ids = {e["id"] for e in bb.load_ledger(small)}
        lost += (ea["id"] not in ids) + (eb["id"] not in ids)
    except bb.BoardError:
        lost += 2; broken += 1
print("(b) 并发 --ledger-append %d 轮（每轮 2 条新事件）：进程退出码 %s；丢失事件 %d 条（其中账本读坏 %d 轮）" % (rounds, sorted(set(rcs)), lost, broken))

# (b') 确定性交错（不靠调度运气）：A 读 → B 读 → A 写 → B 写
bb.write_ledger(small, old[:3])
A = bb.load_ledger(small); B = bb.load_ledger(small)
bb.write_ledger(small, bb.append_events(A, [mkev(issue=7001, holder="anna")]))
bb.write_ledger(small, bb.append_events(B, [mkev(issue=7002, holder="bert")]))
fin = bb.load_ledger(small)
print("(b') 交错读改写：最终 %d 条，anna 的事件在不在：%s" % (len(fin), any(e["holder"] == "anna" for e in fin)))

# (c) save_store 同款：模拟写到一半抛错
st = os.path.join(d, "state.json")
store = {"issues": {}, "ledger": old[:2000]}
bb.save_store(st, store)
real_dump = bb.json.dump
def half_dump(obj, fh, **kw):
    s = json.dumps(obj, **kw); fh.write(s[: len(s) // 2]); raise OSError(28, "No space left on device（模拟）")
bb.json.dump = half_dump
try:
    bb.save_store(st, store)
except OSError as exc:
    print("(c) save_store 写到一半失败：", exc)
finally:
    bb.json.dump = real_dump
try:
    bb.load_store(st); print("    load_store 仍可读")
except bb.BoardError as exc:
    print("    load_store →", str(exc)[:90])
bug = bool(hit and "BoardError" in hit[2]) and (lost > 0 or len(fin) == 4)
print("VERDICT=BUG" if bug else "VERDICT=OK")
```

## 代码定位
```
scripts/bounty_board.py:1069-1076
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path



scripts/bounty_board.py:1308-1313
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    return path

scripts/bounty_board.py:1096-1101
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for ev in events or []:
            fh.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")
    return path

scripts/bounty_board.py:1672-1680

        if args.ledger_append:
            events = read_jsonl(args.ledger_append)
            merged = append_events(load_ledger(args.ledger), events)
            write_ledger(args.ledger, merged)
            print(f"账本并入：读入 {len(events)} 条 → 账本现 {len(merged)} 条 → "
                  f"{args.ledger}")
            return 0

```

## 影响
- (a) 让整本账本不可读：后续 `--board-out`、`build_site` 全部退 2；维护者没注意就提交的话，git 历史里会出现一个空账本的提交。
- (b) 静默丢分：两个进程都返回 0、都打印「账本并入」，但每轮都有一条事件没进账本，CI 也发现不了。
- (c) 离线镜像没有 git 兜底，直接丢失。

## 修法
1. 抽一个 `_atomic_write_text(path, text)`：写同目录临时文件 → `fh.flush(); os.fsync(fh.fileno())` → `os.replace(tmp, path)`（POSIX / Windows 都是原子替换），`write_ledger`、`save_store`、`--board-out`、`write_jsonl` 四处共用。
2. `--ledger-append` 加独占写锁（stdlib 可用 `os.open(lock, O_CREAT|O_EXCL)` 锁文件），或在写前比对文件的 mtime/哈希，发现被改过就拒绝写入并退 2。
3. 补守卫：模拟 `json.dump` 中途抛错后，原账本必须保持完整可读。

## 与已有 issue 的关系
bodies.txt（#2–#11）里 `原子`、`atomic`、`rename`、`write_ledger`、`save_store` 均为 0 命中；A 轮（状态机）不涉及写盘。与本仓 #12 无重叠：那条是权威记录可被伪造，这条是写盘非原子导致的丢失。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 b1_nonatomic_write.py`：

```
初始账本：60000 条事件，18098781 字节
(a) 写入途中 SIGKILL：第 1 次命中，账本剩 0 字节（原 18098781）→ load_ledger BoardError：账本不是合法 JSON：/tmp/rB_atomic_v0kvh82p/ledger.json（Expecting value: line 1 column 1
(b) 并发 --ledger-append 20 轮（每轮 2 条新事件）：进程退出码 [0]；丢失事件 20 条（其中账本读坏 0 轮）
(b') 交错读改写：最终 4 条，anna 的事件在不在：False
(c) save_store 写到一半失败： [Errno 28] No space left on device（模拟）
    load_store → 状态文件不是合法 JSON：/tmp/rB_atomic_v0kvh82p/state.json（Expecting property name enclosed in doubl
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 7 行输出中 5 行能在正文代码块里找到同样的行；其余 2 行不同：`(a) 写入途中 SIGKILL：第 1 次命中，账本剩 0 字节（原 18098781）→ load_ledger BoardError：账本不是合法 JSON：/tmp/rB_`；`load_store → 状态文件不是合法 JSON：/tmp/rB_atomic_v0kvh82p/state.json（Expecting property name encl`。结论（末行 VERDICT=BUG）一致。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 写入中途 SIGKILL 后，`ledger.json` 仍是完整、可读的旧版本（`load_ledger` 不报错）
- 两个 `--ledger-append` 并发跑 20 轮，丢失事件数为 0（或其中一个以退出码 2 明确拒绝）
- `save_store` 写到一半失败时，`state.json` 仍可被 `load_store` 读取
- `b1_nonatomic_write.py` 末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
