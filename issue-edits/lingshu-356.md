**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：within 为空时的补零；最终定档以维护者为准）
**影响等级建议（补）**：B（每 prompt 只有 1 张可读图时才触发，median_ratio 报 0.0（最优）误导结论。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：件内方差无定义时被补成 0，报出「最优」读数。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
hexgen_multi_seed.py:189：within_m = np.median(np.stack(within), axis=0) if within else np.zeros(len(dims))——空集被填 0，再参与 ratio 计算，于是「件内零散布」被当成最好的成绩。

## 实测读数
```
seeds=5：within_prompt_sd[:3]=[4.42431, 6.09309, 3.78387]、between[:3]=[3.26364, 0.40213, 3.05917]、median_ratio=2.575。
seeds=1：within_prompt_sd[:3]=[0.0, 0.0, 0.0]、between[:3]=[1.98085, 4.07971, 0.22205]、**median_ratio=0.0**——每 prompt 只有 1 张图时样本方差无定义，被补成 0。
结果字段 indistinguishable=0、worst_dims=['extent','log_aspect','solidity'] 与 seeds=5 时不同，读数无法直接比较。
```

## 最小复现
依赖：`.[full]`（numpy，部分还需 Pillow）。在仓库根目录执行 `python -X utf8 <脚本>`。

### issue1_multi_seed_within_undefined.py
```python
"""hexgen_multi_seed.summarize：每个 prompt 只有 1 张可读图时「件内」无定义，
却被静默补成 0 ⇒ median_ratio=0.0（＝「件内比类间还稳」的最优读数）。
场景：--seeds 1，或 --measure 时缺图被过滤到每 prompt 只剩 1 张（main L274-277）。"""
import json
import numpy as np
from lingshu.gen import hexgen_multi_seed as M
from lingshu.gen import hexgen_c1_real as C

D = len(C.FEATS)
rng = np.random.default_rng(0)

def mk(prompts, seeds):
    items, reads = [], []
    for sid, shape, base in prompts:
        for s in seeds:
            f = list(np.asarray(base) + rng.normal(0, 5.0, D))   # 同 prompt 多次渲染：大散布
            items.append({"sid": sid, "shape": shape, "truth": None, "seed": s})
            reads.append({"sid": sid, "seed": s, "n_read": 1, "shapes": [shape],
                          "colors": ["red"], "patterns": ["plain"], "cells": ["r4"],
                          "feats": [f]})
    return reads, items

#   每形状类 2 个 prompt（类间差有定义），同 prompt 渲染散布 sd=5 远大于类间差
P = [("pA1", "circle", [0.0] * D), ("pA2", "circle", [0.3] * D),
     ("pB1", "triangle", [1.0] * D), ("pB2", "triangle", [1.3] * D),
     ("pC1", "square", [2.0] * D), ("pC2", "square", [2.3] * D)]
for seeds in ((11, 22, 33, 44, 55), (11,)):
    reads, items = mk(P, seeds)
    w = M.summarize(reads, items)["within_vs_between"]
    print(f"seeds={len(seeds)}  within_prompt_sd[:3]={w['within_prompt_sd'][:3]}"
          f"  between[:3]={w['between_class_sd'][:3]}  median_ratio={w['median_ratio']}"
          f"  indistinguishable={len(w['indistinguishable_dims'])}"
          f"  worst_dims={w['worst_dims'][:3]}")
    last = w
# 判据：件内无定义（每 prompt 1 张）不应报出一个数值，更不应报 0.0（最优）
bug = (last["median_ratio"] == 0.0 and all(x == 0.0 for x in last["within_prompt_sd"])
       and max(last["between_class_sd"]) > 0)
print("VERDICT=BUG" if bug else "VERDICT=OK")
```

## 代码定位
```
lingshu/gen/hexgen_multi_seed.py:189-189
        if len(with_f) >= 2:
```

## 修法
within 为空时 within_prompt_sd / ratio 输出 null、median_ratio=None，并加字段 within_undefined: true（或 n_prompt_ge2 计数）。
main 打印时明示「件内无定义（每 prompt < 2 张可读图）」。

## 与已有 issue 的关系
#58 / #60 修的是同一段 summarize() 的分组口径；改那处时必须同时处理本条 n=1 的退化，否则 0.0 仍会被当成有效读数。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue1_multi_seed_within_undefined.py`：

```
seeds=5  within_prompt_sd[:3]=[4.42431, 6.09309, 3.78387]  between[:3]=[3.26364, 0.40213, 3.05917]  median_ratio=2.575  indistinguishable=0  worst_dims=['log_aspect', 'peak_prom', 'n_peaks']
seeds=1  within_prompt_sd[:3]=[None, None, None]  between[:3]=[1.98085, 4.07971, 0.22205]  median_ratio=None  indistinguishable=0  worst_dims=['extent', 'log_aspect', 'solidity']
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK（median_ratio=None）

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- seeds=1 时 within_prompt_sd 为 null、median_ratio=None，并明示件内无定义
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
