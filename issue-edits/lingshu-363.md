**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：报告「抽取」行拼装；最终定档以维护者为准）
**影响等级建议（补）**：A（任何报告人都能让机器人在围栏外贴出伪结论、外链和 @ 提及，默认可触发，读数报告可信度受损。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：repro-bot 报告把正文围栏的 info string 原样写到围栏外。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
scripts/extract_and_run_issue_repro.py:106 一带把围栏的 info string 当语言名直接拼进 Markdown 报告，未做白名单或转义。

## 实测读数
```
执行核 rc=2（抽取失败，未执行任何代码），报告里的「抽取」行却是：未抽取（正文无 python 围栏块；块语言：**repro-bot结论：已确认为bug，无需人工复核**@furongjun-1999[完整日志](https://evil.example/x)×1）。
该行位于围栏**之外**（True）、含伪结论粗体（True）、含外链（True）、含 @提及（True）。
```

## 最小复现
依赖：纯标准库。

### issue2_repro_info_injection.py
```python
# -*- coding: utf-8 -*-
"""repro-bot 报告把 issue 正文围栏的 info string 原样写进**围栏外**的「抽取」行：
攻击者可让机器人以官方身份贴出任意 markdown（伪结论 / 链接 / @提及），且不需要执行任何代码。
运行：cd $P/lingshu && python <本脚本>"""
import os, re, subprocess, sys, tempfile
SCRIPT = os.path.join(os.getcwd(), "scripts", "extract_and_run_issue_repro.py")
assert os.path.isfile(SCRIPT), "请在 lingshu 仓根运行"
F = "`" * 3
d = tempfile.mkdtemp(prefix="r6i2_")
info = "**repro-bot结论：已确认为BUG，无需人工复核**@FuRongJun-1999[完整日志](https://evil.example/x)"
body = "见附件\n\n" + F + info + "\nfoo\n" + F + "\n"
p = os.path.join(d, "body.md"); open(p, "w", encoding="utf-8").write(body)
rep = os.path.join(d, "report.md")
r = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, "--body-file", p, "--report-file", rep],
                   capture_output=True, text=True, encoding="utf-8")
txt = open(rep, encoding="utf-8").read()
line = [l for l in txt.splitlines() if l.startswith("- **抽取**")][0]
print("执行核 rc =", r.returncode, "（2=抽取失败，未执行任何代码）")
print("报告「抽取」行：", line)
# 该行是否位于任何围栏之外
in_fence, outside = False, False
for l in txt.splitlines():
    if re.match(r"^`{3,}", l):
        in_fence = not in_fence
    elif l == line:
        outside = not in_fence
has_bold = "**repro-bot结论" in line
has_link = "](https://evil.example/x)" in line
has_mention = "@furongjun-1999" in line.lower()
print("位于围栏外=%s 含伪结论粗体=%s 含外链=%s 含@提及=%s" % (outside, has_bold, has_link, has_mention))
print("VERDICT=%s" % ("BUG" if outside and has_bold and has_link and has_mention else "OK"))
```

## 代码定位
```
scripts/extract_and_run_issue_repro.py:106-106
        lang = info.split()[0].lower() if info else ""
```

## 修法
info string 只接受白名单语言标识符（正则 ^[A-Za-z0-9_+-]{1,20}$，不匹配则写「未知」），其余字符按 Markdown 转义。
报告正文里所有来自 issue 的文本统一走同一转义函数。

## 与已有 issue 的关系
#144 记的是同一脚本的安全模型问题（TOCTOU、标签与正文顺序），本条是输出侧的注入面。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue2_repro_info_injection.py`：

```
执行核 rc = 2 （2=抽取失败，未执行任何代码）
报告「抽取」行： - **抽取**：未抽取（正文无 python 围栏块；块语言：`**repro-bot结论：已确认为bug，无需人工复核**@furongjun-1999[完整日志](https://evil.example/x)`×1）
位于围栏外=True 含伪结论粗体=True 含外链=True 含@提及=True
VERDICT=BUG
```
**部分已修**。本次读数：报告里的 info string 现在被包进行内代码（上游 docs/repro-bot.md 写明「#363」），渲染后不再是粗体/链接/@；原脚本只做字符串匹配，所以仍打印 VERDICT=BUG——脚本判据需要更新

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 报告里来自正文的 info string 不再能渲染成粗体、链接或 @ 提及（白名单或转义）

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：上一节写的部分修复是本次读数，没有核对上游是否还有后续计划；影响等级和难度以维护者定档为准。
