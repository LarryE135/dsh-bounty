**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：check_pr_title 参数解析与校验；最终定档以维护者为准）
**影响等级建议（补）**：B（需要构造特殊标题才触发，PR 标题门被绕过。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：pr-lint 标题门可被以 - 开头、含零宽字符或超长 Revert 的标题绕过。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
scripts/check_pr_title.py:150-170：标题从 argv 位置参数取，但 argparse/手写解析在标题以 - 开头时把它当选项处理，未校验的分支直接以 0 退出。

## 实测读数
```
'--help' rc=0（打印 check_pr_title 用法，期望 1）；'-h' rc=0；'--list-types' rc=0（输出 init）；'--selftest' rc=0（输出 OK: type=fix scope=world ...）。
零宽字符摘要/scope、以及超长 Revert 标题同样放行。
```

## 最小复现
依赖：纯标准库。

### issue3_pr_title_bypass.py
```python
# -*- coding: utf-8 -*-
"""check_pr_title 门禁绕过：PR 标题按 pr-lint.yml 的方式作为第 1 个 argv 传入，
标题恰为 --help / -h / --list-types / --selftest 时被当成选项、退出码 0（判合规）；
另：零宽字符摘要/scope 放行、Revert 特例跳过 300 字上限。
运行：cd $P/lingshu && python <本脚本>"""
import os, subprocess, sys
SCRIPT = os.path.join(os.getcwd(), "scripts", "check_pr_title.py")
assert os.path.isfile(SCRIPT), "请在 lingshu 仓根运行"
def rc(title):
    # 与 pr-lint.yml:51-52 一致：env PR_TITLE → "$PR_TITLE" 作为唯一 argv
    env = dict(os.environ, PR_TITLE=title)
    r = subprocess.run(["bash", "-c", 'exec "$0" -X utf8 "$1" "$PR_TITLE"', sys.executable, SCRIPT],
                       env=env, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout + r.stderr).strip().splitlines()[:1]
cases = [("--help", 1), ("-h", 1), ("--list-types", 1), ("--selftest", 1),
         ("fix: \u200b", 1), ("fix(\u200b): \u200b", 1),
         ('Revert "' + "x" * 5000 + '"', 1),
         ("修复了一个 bug", 1), ("fix: 正常标题", 0)]
bad = 0
for t, want in cases:
    got, first = rc(t)
    shown = (t[:40] + "…") if len(t) > 40 else t
    flag = "" if got == want else "   <-- 期望 %d" % want
    if got != want: bad += 1
    print("%-48r rc=%d  %s%s" % (shown, got, (first[0][:60] if first else ""), flag))
print("不符预期 %d 例" % bad)
print("VERDICT=%s" % ("BUG" if bad else "OK"))
```

## 代码定位
```
scripts/check_pr_title.py:150-161
def main(argv) -> int:
    args = list(argv[1:])
    if not args:
        return check(os.environ.get("PR_TITLE"))
    if args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--list-types":
        print("\n".join(ALLOWED_TYPES))
        return 0
    if args[0] == "--selftest":
        return _selftest()
```

## 修法
解析前插 -- 分隔，或直接从 sys.argv[1:] 取原始字符串再校验；对空/缺失标题显式报错。
校验前剔除零宽字符（U+200B/200C/200D/FEFF 等）并按码点（而非字节）限制 Revert 标题长度。
补测试：以 - 开头的标题、含零宽字符的标题、超长 Revert 标题都必须非零退出。

## 与已有 issue 的关系
#87 是测试基建（pytest 收集 + xfail 门禁），本条是同一条门禁链上的标题校验，互不覆盖。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue3_pr_title_bypass.py`：

```
'--help'                                         rc=1  FAIL: 标题不符合约定 `type(scope): 摘要`：'--help'
'-h'                                             rc=1  FAIL: 标题不符合约定 `type(scope): 摘要`：'-h'
'--list-types'                                   rc=1  FAIL: 标题不符合约定 `type(scope): 摘要`：'--list-types'
'--selftest'                                     rc=1  FAIL: 标题不符合约定 `type(scope): 摘要`：'--selftest'
'fix: \u200b'                                    rc=0  OK: type=fix scope=- breaking=False summary=​   <-- 期望 1
'fix(\u200b): \u200b'                            rc=0  OK: type=fix scope=​ breaking=False summary=​   <-- 期望 1
'Revert "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx…'      rc=0  OK（Revert 特例放行）：Revert "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   <-- 期望 1
'修复了一个 bug'                                      rc=1  FAIL: 标题不符合约定 `type(scope): 摘要`：'修复了一个 bug'
'fix: 正常标题'                                      rc=0  OK: type=fix scope=- breaking=False summary=正常标题
不符预期 3 例
VERDICT=BUG
```
**部分已修**。本次读数：`--help` 等四种已修（rc=1）；`fix: \u200b`、`fix(\u200b): \u200b`、超长 Revert 三例仍 rc=0，VERDICT=BUG

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- `--help` / `-h` / `--list-types` / `--selftest`、`fix: \u200b`、`fix(\u200b): \u200b`、超长 Revert 标题都以非零退出
- 复现脚本「不符预期」为 0 例，末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：上一节写的部分修复是本次读数，没有核对上游是否还有后续计划；影响等级和难度以维护者定档为准。
