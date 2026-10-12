**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：argparse 与 pick_prompts；最终定档以维护者为准）
**影响等级建议（补）**：B（需要传入越界的 --seeds / --prompts 才触发，张数被静默改写。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：--seeds / --prompts 不校验，负数和超量被静默改写。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
hexgen_multi_seed.py:255 一带直接用切片/取前 n 条，argparse 层没有值域约束，越界输入被静默解释成另一种语义。

## 实测读数
```
pick_prompts(0) -> 1 条；pick_prompts(-3) -> 1 条；pick_prompts(2) -> 2 条。
--seeds -1 -> seeds=[11,22,33,44]；--seeds -4 -> seeds=[11]；--seeds 0 -> seeds=[]；--seeds 10 -> seeds=[11,22,33,44,55]。
```

## 最小复现
依赖：`.[full]`（numpy，部分还需 Pillow）。在仓库根目录执行 `python -X utf8 <脚本>`。

### issue4_multi_seed_cli_counts.py
```python
"""hexgen_multi_seed CLI：--seeds / --prompts 不校验。
  · seeds = SEEDS[:a.seeds] ⇒ --seeds -1 → 4 个 seed、--seeds 0 → 0 个、--seeds 10 → 静默只有 5 个；
  · pick_prompts 先 append 再判 len>=n ⇒ --prompts 0 / -3 仍返回 1 条。
  --seeds 1（或负数切到 1）正好把语料变成「每 prompt 1 张」，再进 summarize 就是 issue1 的 0.0 假最优。"""
import json, os, sys, tempfile
from unittest import mock
from lingshu.gen import hexgen_multi_seed as M

lib = [{"name": f"vs_s{i}_circle_red", "tags": {"prompt":
        f"flat vector illustration, one red circle(s) in the {z}"}}
       for i, z in enumerate(("center", "top left", "bottom right", "top", "left side"))]
d = tempfile.mkdtemp()
p = os.path.join(d, "lib.json")
json.dump(lib, open(p, "w"))
ok_parse = sum(M.C.parse_prompt(r["tags"]["prompt"]) is not None for r in lib)
print("可解析 prompt 数:", ok_parse)
bad = 0
for n in (0, -3, 2):
    got = len(M.pick_prompts(n, p))
    print(f"pick_prompts({n}) -> {got} 条"); bad += (n <= 0 and got != 0)

# 复刻 main() 的参数 → seeds 映射（L248-255，原样调用 argparse）
for argv in (["--seeds", "-1"], ["--seeds", "-4"], ["--seeds", "0"], ["--seeds", "10"]):
    with mock.patch.object(sys, "argv", ["x"] + argv + ["--measure"]):
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--prompts", type=int, default=8)
        ap.add_argument("--seeds", type=int, default=len(M.SEEDS))
        ap.add_argument("--gen", action="store_true"); ap.add_argument("--measure", action="store_true")
        a = ap.parse_args()
        seeds = M.SEEDS[:a.seeds]
        print(f"{' '.join(argv):12s} -> seeds={list(seeds)}"); bad += (len(seeds) != max(0, min(a.seeds, 99)))
print("VERDICT=BUG" if bad else "VERDICT=OK")
```

## 代码定位
```
lingshu/gen/hexgen_multi_seed.py:255-255
    seeds = SEEDS[:a.seeds]
```

## 修法
argparse 里限定 1 <= --prompts、2 <= --seeds <= len(SEEDS)（或 >5 时按规则生成更多 seed），越界 ap.error(...)。
pick_prompts 在循环前加 if n <= 0: return []。

## 与已有 issue 的关系
#58 / #60 是同一文件 ③ 号尺子的分组问题，本条是 CLI 入参校验，可同批修。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue4_multi_seed_cli_counts.py`：

```
可解析 prompt 数: 5
pick_prompts(0) -> 1 条
pick_prompts(-3) -> 1 条
pick_prompts(2) -> 2 条
--seeds -1   -> seeds=[11, 22, 33, 44]
--seeds -4   -> seeds=[11]
--seeds 0    -> seeds=[]
--seeds 10   -> seeds=[11, 22, 33, 44, 55]
VERDICT=BUG
```
**仍复现**。本次读数：VERDICT=BUG，仍复现

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- `--seeds -1`、`--seeds 0`、`--seeds 10`、`--prompts 0` 都以 argparse 错误退出（或按文档明确处理）
- `pick_prompts(0)` 返回空列表
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：影响等级和难度是自评；影响等级和难度以维护者定档为准。
