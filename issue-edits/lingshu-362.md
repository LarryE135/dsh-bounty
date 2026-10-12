**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（要覆盖缩进围栏、引用块和孙进程超时三种情形；最终定档以维护者为准）
**影响等级建议（补）**：A（repro-bot 是四闸②的读数来源，合法复现被判失败会让读数不可信（量具失效）。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：repro-bot 会把三类合法复现判成失败。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
scripts/extract_and_run_issue_repro.py:96-120：抽取时不做 dedent、只认顶层围栏（不含 blockquote），执行侧按总超时判定而不看脚本自身退出码/进程组。

## 实测读数
```
[list_item] 执行核 rc=1，抽取到正文第 6-8 行的 python 块，报 IndentationError: unexpected indent。
[blockquote] 执行核 rc=2，报「未抽取（正文没有任何围栏代码块）」——引用块里的围栏整块漏掉。
[grandchild] 执行核 rc=1，标注「超时终止（5 s）」，而脚本自己输出 VISIBLE_OK script finished, exit 0（后台子进程未退出导致判超时）。
```

## 最小复现
依赖：纯标准库。

### issue1_repro_false_fail.py
```python
# -*- coding: utf-8 -*-
"""repro-bot 执行核把合法复现判成失败：①列表项内缩进围栏 → IndentationError；
②引用块内围栏 → 判「无 python 块」；③脚本已 exit 0 但留后台子进程 → 报「超时终止」。
运行：cd $P/lingshu && python <本脚本>"""
import os, subprocess, sys, tempfile, time
SCRIPT = os.path.join(os.getcwd(), "scripts", "extract_and_run_issue_repro.py")
assert os.path.isfile(SCRIPT), "请在 lingshu 仓根运行"
F = "`" * 3
d = tempfile.mkdtemp(prefix="r6i1_")

def run(name, body, timeout="20"):
    p = os.path.join(d, name + ".md")
    open(p, "w", encoding="utf-8").write(body)
    rep = os.path.join(d, name + "_report.md")
    t0 = time.time()
    r = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, "--body-file", p,
                        "--out-dir", os.path.join(d, name), "--timeout", timeout,
                        "--report-file", rep], capture_output=True, text=True, encoding="utf-8")
    txt = open(rep, encoding="utf-8").read()
    lines = [l for l in txt.splitlines() if l.startswith("- **抽取**") or l.startswith("- **退出码**")
             or "IndentationError" in l or "VISIBLE_OK" in l]
    print("[%s] 执行核 rc=%d 用时 %.1fs" % (name, r.returncode, time.time() - t0))
    for l in lines:
        print("   ", l)
    return r.returncode, txt

# ① GitHub issue 模板里最常见的写法：有序列表项下缩进 3 格的围栏
body1 = "\n".join(["复现步骤：", "", "1. 运行下面的脚本：", "",
                   "   " + F + "python", "   import sys", "   if True:",
                   "       print('VISIBLE_OK', sys.version_info[:2])", "   " + F, ""])
rc1, t1 = run("list_item", body1)
# ② 引用块里的围栏（GitHub 同样渲染为 python 代码块）
body2 = "\n".join(["> 复现：", ">", "> " + F + "python", "> print('VISIBLE_OK')", "> " + F, ""])
rc2, t2 = run("blockquote", body2)
# ③ 脚本自身立即 exit 0，只是起了一个后台进程（如本地 server）没回收
body3 = "\n".join([F + "python", "import subprocess, sys",
                   "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
                   "print('VISIBLE_OK script finished, exit 0')", F, ""])
rc3, t3 = run("grandchild", body3, timeout="5")

bug1 = rc1 == 1 and "IndentationError" in t1
bug2 = rc2 == 2 and "未抽取" in t2
bug3 = rc3 == 1 and "超时终止" in t3 and "script finished" in t3
print("①缩进围栏误判失败=%s ②引用块漏抽=%s ③exit0 报超时=%s" % (bug1, bug2, bug3))
print("VERDICT=%s" % ("BUG" if (bug1 or bug2 or bug3) else "OK"))
```

## 代码定位
```
scripts/extract_and_run_issue_repro.py:96-107
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        m = _FENCE_OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        delim = m.group(1)
        info = lines[i][m.end():].strip()
        lang = info.split()[0].lower() if info else ""
        j = i + 1
```

## 修法
抽取时对块内容 dedent；扫描块级容器（引用、列表）内的围栏。
超时判定改为「脚本已 exit 0 且剩余输出只有后台进程」时按脚本退出码判定，或在结束时清理进程组。

## 与已有 issue 的关系
#144 是 repro-bot 的安全模型（打标签后才取正文的 TOCTOU 等），#120 是 Windows cp936 下 --help 的问题——本条是同一工具的判定正确性。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue1_repro_false_fail.py`：

```
[list_item] 执行核 rc=0 用时 0.1s
    - **抽取**：第 1 个围栏块（正文第 6–8 行的 python 块，共 3 行；正文围栏块 1 个：`python`×1）
    - **退出码**：0
    VISIBLE_OK (3, 12)
[blockquote] 执行核 rc=0 用时 0.1s
    - **抽取**：第 1 个围栏块（正文第 4–4 行的 python 块，共 1 行；正文围栏块 1 个：`python`×1）
    - **退出码**：0
    VISIBLE_OK
[grandchild] 执行核 rc=0 用时 0.1s
    - **抽取**：第 1 个围栏块（正文第 2–4 行的 python 块，共 3 行；正文围栏块 1 个：`python`×1）
    - **退出码**：0
    VISIBLE_OK script finished, exit 0
①缩进围栏误判失败=False ②引用块漏抽=False ③exit0 报超时=False
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 缩进围栏、引用块围栏能被正确抽取执行；脚本 exit 0 但留后台孙进程时按 exit 0 判
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
