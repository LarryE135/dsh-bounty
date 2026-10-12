**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：frames_to_voxel 三行归一化；最终定档以维护者为准）
**影响等级建议（补）**：A（静止画面加任意小噪声就被判为运动，运动检测结论失效（量具失效），默认路径即触发。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：frames_to_voxel 整段 min-max 把任意小噪声放大到满量程。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/nn/stcnn.py:24-26：frames_to_voxel 用整段 min-max 归一化，没有噪声地板或量程锚点。

## 实测读数
```
静止画面 + σ=1e-6 噪声：motion_magnitude = 236.9，**大于**真实滚动小球的 90.0。
归一化按整段（跨帧）min/max 做，任何非零噪声都被拉到满量程。
```

## 最小复现
依赖：`.[full]`（numpy，部分还需 Pillow）。在仓库根目录执行 `python -X utf8 <脚本>`。

### issue3_stcnn_minmax_noise.py
```python
# -*- coding: utf-8 -*-
"""复现：frames_to_voxel 对整段视频做 min-max 归一化，把任意小的噪声放大到满量程；
motion_magnitude / moving 因此与真实运动幅度无关：静止画面 + 1e-6 噪声的
motion_magnitude 比真实滚动小球还大，moving=True。
运行：cd $P/lingshu && python <本脚本>"""
import numpy as np
from lingshu.nn.stcnn import (extract_spatiotemporal_primitives, frames_to_voxel,
                              frame_diff, synth_static, synth_ball_rolling)

rng = np.random.default_rng(0)
ball = extract_spatiotemporal_primitives(synth_ball_rolling(frames=10, speed_px=2))[0]
print("真实运动(小球, 对比度1.0): motion_magnitude=%s moving=%s direction=%s"
      % (ball["motion_magnitude"], ball["moving"], ball["direction"]))
bad = 0
for amp in (0.0, 1e-6, 1e-4, 1e-2):
    fr = [f + amp * rng.standard_normal(f.shape).astype(np.float32) for f in synth_static(frames=6)]
    p = extract_spatiotemporal_primitives(fr)[0]
    vox = frames_to_voxel(fr)
    print(f"静止画面 + 噪声σ={amp:g}: 原始帧极差={np.ptp(np.asarray(fr)):.2e} "
          f"→ voxel 极差={np.ptp(vox):.3f}; motion_magnitude={p['motion_magnitude']} moving={p['moving']}")
    if amp > 0 and p["moving"]:
        bad += 1
# 若按 #256 的建议改用 voxel 做帧差，放大会进一步传进方向/质心
fr = [f + 1e-6 * rng.standard_normal(f.shape).astype(np.float32) for f in synth_static(frames=6)]
d = frame_diff(frames_to_voxel(fr))
print("σ=1e-6 静止画面: frame_diff(voxel) 每帧运动像素数 =", [int(x.sum()) for x in d], "/ 1024")
print("VERDICT=" + ("BUG" if bad else "OK"))
```

## 代码定位
```
lingshu/nn/stcnn.py:24-26
    amin, amax = arr.min(), arr.max()
    if amax > amin:
        arr = (arr - amin) / (amax - amin)
```

## 修法
改用固定量纲（0..255 → /255）或加噪声地板阈值（低于阈值视为静止），不要把每段自己的 min/max 当量程。
补测试：静止画面 + 小噪声的 motion 必须接近 0，且小于真实运动画面。

## 与已有 issue 的关系
#76 是同一模块 frame_diff 的双沿问题，可同批处理。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue3_stcnn_minmax_noise.py`：

```
真实运动(小球, 对比度1.0): motion_magnitude=90.0 moving=True direction=向右
静止画面 + 噪声σ=0: 原始帧极差=0.00e+00 → voxel 极差=0.000; motion_magnitude=0.0 moving=False
静止画面 + 噪声σ=1e-06: 原始帧极差=7.33e-06 → voxel 极差=1.000; motion_magnitude=236.8889 moving=True
静止画面 + 噪声σ=0.0001: 原始帧极差=7.85e-04 → voxel 极差=1.000; motion_magnitude=222.4357 moving=True
静止画面 + 噪声σ=0.01: 原始帧极差=8.40e-02 → voxel 极差=1.000; motion_magnitude=198.9389 moving=True
σ=1e-6 静止画面: frame_diff(voxel) 每帧运动像素数 = [698, 680, 702, 704, 681] / 1024
VERDICT=BUG
```
**仍复现**。本次读数：VERDICT=BUG，仍复现

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 静止画面 + σ=1e-6 噪声：moving=False，motion_magnitude 接近 0 且小于真实滚动小球（90.0）
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：影响等级和难度是自评；影响等级和难度以维护者定档为准。
