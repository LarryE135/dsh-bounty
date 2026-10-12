**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（要分析梯度量级与 L1 归一化的相互作用；最终定档以维护者为准）
**影响等级建议（补）**：A（selfsup_finetune 的 lr 参数实际无效，默认路径即触发，训练功能失效。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：selfsup_finetune 的 lr 跨 5000 倍结果几乎不变。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
hex_cnn.py:250-253：lum 保持 0..255 量纲（hex_train.py:74 的 images_to_lattices 是归一化的），lr·grad 约为 |w| 的 3400 倍，每一步都被 L1 归一化抹掉旧核，实际更新与 lr 无关。

## 实测读数
```
lr=0.001 → final_loss=1565.41772 kernel=[0.0, 0.1285, 0.1955, ...]；lr=0.05 → 1562.81982；lr=0.3 → 1562.77673；lr=5.0 → 1562.76843。
lr 跨 5000 倍，核向量几乎不动：每步都被 −grad/‖grad‖₁ 决定。
```

## 最小复现
依赖：`.[full]`（numpy，部分还需 Pillow）。在仓库根目录执行 `python -X utf8 <脚本>`。

### issue4_selfsup_lr_noop.py
```python
# -*- coding: utf-8 -*-
"""复现：selfsup_finetune 的 lr 参数实际无效——亮度在 0..255 量纲下梯度 ~1e4，
lr·grad ≫ |w|，随后 L1 归一化把旧 w 抹掉，每步核≈ -grad/‖grad‖₁。
lr 跨 5 个数量级（1e-3 … 5.0）得到同一核与同一损失曲线；更新不累积。
运行：cd $P/lingshu && python <本脚本>"""
import numpy as np
from lingshu.nn import hex_cnn
from lingshu.nn.hex_cnn import selfsup_finetune, image_to_grid, hex_conv

yy, xx = np.mgrid[0:120, 0:160]
img = np.zeros((120, 160, 3), np.uint8)
img[..., 0] = (128 + 100 * np.sin(xx / 7.0) * np.cos(yy / 9.0)).astype(np.uint8)
img[..., 1] = img[..., 0]
img[..., 2] = (xx + yy) % 256
ks = {}
for lr in (1e-3, 0.05, 0.3, 5.0):
    r = selfsup_finetune(img, epochs=10, lr=lr, cells_across=32)
    ks[lr] = r["kernel"]
    print(f"lr={lr:<6} final_loss={r['final_loss']:<10} kernel={np.round(r['kernel'], 4).tolist()}")
spread = max(float(np.abs(ks[a] - ks[0.05]).max()) for a in ks)
print("lr 跨 5000 倍，核最大逐元差 =", round(spread, 5))

# 量纲：第 1 步的梯度范数 vs 核范数
gray = (0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]).astype(np.float32)
lum = image_to_grid(gray[..., None].repeat(3, axis=2), 32)[0][..., :1]
rng = np.random.default_rng(7); rng.random(lum.shape[:2]); hole = rng.random(lum.shape[:2]) < 0.25
w = hex_cnn.DEFAULT_KERNELS["center_surround"].copy()
def L(wv):
    m = lum.copy(); m[hole] = 0
    return float(((hex_conv(m, wv)[..., :1][hole] - lum[hole]) ** 2).mean())
g = np.array([(L(w + e) - L(w - e)) / 2e-3 for e in np.eye(7, dtype=np.float32) * 1e-3])
print(f"第1步 |grad|_1={np.abs(g).sum():.1f}  |w|_1={np.abs(w).sum():.3f}  lr=0.05 时 |lr·grad|_1/|w|_1={0.05*np.abs(g).sum()/np.abs(w).sum():.0f}")
w1 = w - 0.05 * g; w1 /= np.abs(w1).sum()
print("第1步更新后 w 与 -grad/|grad|_1 的最大差 =", round(float(np.abs(w1 - (-g / np.abs(g).sum())).max()), 5))
print("VERDICT=" + ("BUG" if spread < 1e-2 else "OK"))
```

## 代码定位
```
lingshu/nn/hex_cnn.py:250-253
    以重建误差的数值梯度微调 7 参数（有限差分——梯度本身可审计）。
    返回 {kernel, loss_curve, init_loss, final_loss}。"""
    gray = (0.299 * img_arr[..., 0] + 0.587 * img_arr[..., 1]
            + 0.114 * img_arr[..., 2]).astype(np.float32) if img_arr.ndim == 3 else img_arr.astype(np.float32)

lingshu/nn/hex_train.py:74-74
        g = feat[..., :1] / 255.0          # 归一化 [0,1]——有限差分步长标定基准
```

## 修法
先把 lum 归一化到 [0,1]（与 images_to_lattices 一致），或按 ‖g‖ 缩放 / 改符号更新（与 train_infogap、train_hier 一致）；要保持能量约束就投影到 ‖w‖₁=1 球面，并要求 lr·‖g‖ ≪ 1。
补测试：lr 相差 10 倍时第 1 步核必须不同。

## 与已有 issue 的关系
#17 是同一函数里数值差分每次重抽掩码的问题（应改步内共用掩码），与本条相邻。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue4_selfsup_lr_noop.py`：

```
lr=0.001  final_loss=1164.49377 kernel=[0.0, 0.16910000145435333, 0.1687999963760376, 0.15729999542236328, 0.1509000062942505, 0.18880000710487366, 0.16519999504089355]
lr=0.05   final_loss=1163.61292 kernel=[0.0, 0.17000000178813934, 0.16869999468326569, 0.15620000660419464, 0.1500999927520752, 0.1898999959230423, 0.16509999334812164]
lr=0.3    final_loss=1163.59558 kernel=[0.0, 0.17000000178813934, 0.16869999468326569, 0.15620000660419464, 0.15000000596046448, 0.1898999959230423, 0.16509999334812164]
lr=5.0    final_loss=1163.59534 kernel=[0.0, 0.17000000178813934, 0.16869999468326569, 0.15620000660419464, 0.1500999927520752, 0.1898999959230423, 0.16509999334812164]
lr 跨 5000 倍，核最大逐元差 = 0.00111
第1步 |grad|_1=270826.2  |w|_1=2.000  lr=0.05 时 |lr·grad|_1/|w|_1=6771
第1步更新后 w 与 -grad/|grad|_1 的最大差 = 7e-05
VERDICT=BUG
```
**仍复现**。本次读数：VERDICT=BUG，仍复现

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- lr 相差 10 倍时第 1 步更新后的核明显不同
- 复现脚本中「lr 跨 5000 倍，核最大逐元差」远大于当前的 0.00111
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：影响等级和难度是自评；影响等级和难度以维护者定档为准。
