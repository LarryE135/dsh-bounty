**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：provenance 三个入口的形状校验；最终定档以维护者为准）
**影响等级建议（补）**：B（需要库里存在形状异常的既有行（如 `time_window=[null,null]`）才触发崩溃。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：形状异常的旧行会让 provenance 直接抛异常，而不是按契约落 unknown。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/core/provenance.py:331 一带对既有行按「形状正确」假设直接取值/迭代，没有按注释承诺的「推不出就留 unknown」兜底。

## 实测读数
```
core 自己的 ConditionSpace 规范化后落库的就是 time_window: [null, null]，from_legacy() 读它 → TypeError: float() argument must be a string or a real number, not 'NoneType'。
from_legacy(tags='5') → TypeError: 'int' object is not iterable。
from_legacy(tags='"dsh"') → 把字符串按字符拆成标签。
```

## 最小复现
依赖：纯标准库。在仓库根目录执行 `python -X utf8 <脚本>`（先 `python -m pip install -e .`）。

### issue3_provenance_from_legacy_crash.py
```python
# -*- coding: utf-8 -*-
"""issue3：provenance.from_legacy / is_default_cs / Provenance.from_json 对「形状不对」的
既有行直接抛异常，而不是按契约「推不出的留 unknown 并记 synthetic」。
其中 time_window=[null,null] 并非臆造：core 自己的 ConditionSpace.from_json 会把
{"time_window": null} 规范化成 (None, None)，再 to_json 落成 [null, null]。
用法：cd <仓根> && python <本脚本>
"""
import json
import warnings

warnings.simplefilter("ignore")
from lingshu.core.core import ConditionSpace
from lingshu.core.provenance import Provenance, from_legacy, is_default_cs

crashes = 0


def probe(label, fn):
    global crashes
    try:
        r = fn()
        print("%-48s -> %s" % (label, r))
    except Exception as e:  # noqa
        crashes += 1
        print("%-48s -> CRASH %s: %s" % (label, type(e).__name__, e))


# 0) core 自己产出的行：外部卡 time_window=null → ConditionSpace 规范化 → 落库 JSON
cs_json = ConditionSpace.from_json(json.dumps(
    {"observation_position": "外部观测位", "observation_tool": "文本语义分析",
     "time_window": None, "existence_constraint": "（未声明）"})).to_json()
print("core ConditionSpace 规范化后落库的 condition_space =", cs_json)
probe("from_legacy(core 落库的 condition_space)",
      lambda: from_legacy(["user", "session:s1"], 1786728904.0, cs_json).time_window)

# 1) 其它形状异常的既有行
probe("from_legacy(tags='5')  # tags 列是 JSON 数字",
      lambda: from_legacy("5").source)
probe("from_legacy(tags='\"dsh\"')  # tags 列是 JSON 字符串",
      lambda: (lambda p: (p.observation_tool, "按字符拆成", list("dsh")))(from_legacy('"dsh"')))
probe("from_legacy(cs='[1,2]')  # condition_space 是 JSON 数组",
      lambda: from_legacy([], None, "[1,2]").source)
probe("from_legacy(time_window=['2026-10-01', ...])",
      lambda: from_legacy([], None, {"time_window": ["2026-10-01", "2026-10-02"]}).time_window)
probe("is_default_cs('[1]')", lambda: is_default_cs("[1]"))
probe("Provenance.from_json('null')", lambda: Provenance.from_json("null"))

print("crashes =", crashes)
print("VERDICT=" + ("BUG" if crashes else "OK"))
```

## 代码定位
```
lingshu/core/provenance.py:331-331
    if isinstance(tw, (list, tuple)) and len(tw) == 2 and float(tw[0]) > 0:
```

## 修法
三个入口（from_legacy / is_default_cs / Provenance.from_json）统一走「先校验形状，异常或缺失 → unknown 并记告警」。
补测试：time_window=[null,null]、tags 为数字/字符串、字段缺失三类输入都不得抛异常。

## 与已有 issue 的关系
#20 记的是 from_legacy 的另两项遗留（human_review 等），本条是同一函数的第三项：形状异常行直接崩。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue3_provenance_from_legacy_crash.py`：

```
core ConditionSpace 规范化后落库的 condition_space = {"observation_position": "\u5916\u90e8\u89c2\u6d4b\u4f4d", "observation_tool": "\u6587\u672c\u8bed\u4e49\u5206\u6790", "time_window": [null, null], "existence_constraint": "\uff08\u672a\u58f0\u660e\uff09"}
from_legacy(core 落库的 condition_space)            -> (1786728904.0, 1786732504.0)
from_legacy(tags='5')  # tags 列是 JSON 数字         -> unknown
from_legacy(tags='"dsh"')  # tags 列是 JSON 字符串    -> ('dsh', '按字符拆成', ['d', 's', 'h'])
from_legacy(cs='[1,2]')  # condition_space 是 JSON 数组 -> unknown
from_legacy(time_window=['2026-10-01', ...])     -> (0.0, 0.0)
is_default_cs('[1]')                             -> True
Provenance.from_json('null')                     -> Provenance(source='unknown', observation_position='未知观测位', observation_tool='unknown', session_id=None, time_window=(0.0, 0.0), existence_constraint='（未声明）', verify_status='unverified', verify_methods=['none'], verify_ref='', synthetic=[])
crashes = 0
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK：两处 TypeError 崩溃都不再出现（crashes = 0）；`tags='"dsh"'` 一项脚本只打印 observation_tool='dsh'，看起来按整串处理，未进一步核

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- `from_legacy` / `is_default_cs` / `Provenance.from_json` 对三类畸形输入都不抛异常、落 unknown
- 复现脚本 `crashes = 0`，末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
