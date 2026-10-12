**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：读图一行；最终定档以维护者为准）
**影响等级建议（补）**：B（需要调色板/灰度 PNG 输入才触发，静默读出 0 个物体。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：调色板/灰度 PNG 被切成 (H,3) 细条，静默读出 0 个物体。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
hexgen_c1_real.py:140 与 hexgen_multi_seed.py:112：直接用 np.asarray(Image.open(p))[..., :3]，对 P/灰度 图取到的是索引矩阵而不是像素，形状静默变化、后续物体检测拿到空结果。

## 实测读数
```
vs_1_square_red.png mode=RGB img.shape=(128,128,3) 读出物体数=1。
vs_2_square_red.png mode=P **img.shape=(128,3)** 读出物体数=**0**（同一张图只是存成调色板）。
vs_3_square_red.png mode=RGBA img.shape=(128,128,3) 读出物体数=1。
```

## 最小复现
依赖：`.[full]`（numpy，部分还需 Pillow）。在仓库根目录执行 `python -X utf8 <脚本>`。

### issue5_palette_png_sliced.py
```python
"""hexgen_c1_real.load_items / hexgen_multi_seed.load_multi：
`np.asarray(Image.open(p))[..., :3]` 只对 3/4 通道图成立。调色板（P）/灰度（L）PNG 解码成
2 维数组 (H, W)，`[..., :3]` 切的是**宽度**轴 ⇒ 图被静默截成 (H, 3) 的细条，读出 0 个物体、
不报错（进 multi_seed 就记成「空读件」，污染 empty_rate / 兑现率）。"""
import os, tempfile
import numpy as np
from PIL import Image
from lingshu.gen import hexgen_c1_real as C
from lingshu.gen import hexgen_multi_seed as M

d = tempfile.mkdtemp()
a = np.full((128, 128, 3), 255, np.uint8)
a[40:90, 40:90] = (220, 40, 40)                       # 一个红色方块
im = Image.fromarray(a)
im.save(os.path.join(d, "vs_1_square_red.png"))                                  # RGB
im.convert("P", palette=Image.ADAPTIVE).save(os.path.join(d, "vs_2_square_red.png"))  # 调色板 PNG（同一画面）
im.convert("RGBA").save(os.path.join(d, "vs_3_square_red.png"))                  # RGBA（对照）
bad = 0
for it in C.load_items(d, os.path.join(d, "no_lib.json")):
    mode = Image.open(os.path.join(d, it["file"])).mode
    objs = C.measure_item(it, tol=C.TOL, d=4)[0]
    print(f"{it['file']}  mode={mode:4s} img.shape={it['img'].shape}  读出物体数={len(objs)}")
    bad += (mode == "P" and len(objs) == 0)
rows = [{"sid": "s", "seed": 1, "prompt": "x", "path": os.path.join(d, "vs_2_square_red.png")}]
print("load_multi(P 图) img.shape =", M.load_multi(rows)[0]["img"].shape)
print("VERDICT=BUG" if bad else "VERDICT=OK")
```

## 代码定位
```
lingshu/gen/hexgen_c1_real.py:140-140
        img = np.asarray(Image.open(os.path.join(corpus, f)))[..., :3].astype(np.float64)

lingshu/gen/hexgen_multi_seed.py:112-112
        img = np.asarray(Image.open(r["path"]))[..., :3].astype(np.float64)
```

## 修法
改成 with Image.open(p) as im: np.asarray(im.convert('RGB'))；或至少 assert img.ndim == 3 and img.shape[2] >= 3。
RGBA 若需支持，先合成到白底再取 RGB。补测试：同一张图存成 RGB/P/RGBA 三种模式，读出结果必须一致。

## 与已有 issue 的关系
#15 是 hex_recon 的判据只在矩形区域成立，与本条同属「读图/判据对输入形态不设防」，但位置与机制不同。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue5_palette_png_sliced.py`：

```
vs_1_square_red.png  mode=RGB  img.shape=(128, 128, 3)  读出物体数=1
vs_2_square_red.png  mode=P    img.shape=(128, 128, 3)  读出物体数=1
vs_3_square_red.png  mode=RGBA img.shape=(128, 128, 3)  读出物体数=1
load_multi(P 图) img.shape = (128, 128, 3)
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 同一张图存成 RGB/P/RGBA 三种模式读出物体数一致（均为 1）
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
