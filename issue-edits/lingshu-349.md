**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：load_consolidated / save_consolidated；最终定档以维护者为准）
**影响等级建议（补）**：B（需要形状不对的固化核文件或 meta 同名键才触发；触发后核被静默截断或落盘为空（数据损坏）。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：固化核 JSON 不校验 7 参数契约，meta 同名键还能覆盖 kernels。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
hex_cnn.py:299-303 一带：load_consolidated 不校验 shape[-1] == 7 也不校验 consolidated is True，hex_conv 同样不校验；save_consolidated 展开 meta 时被同名字段覆盖。

## 实测读数
```
资产核形状 {'smooth': (7,), 'edge_v': (7,), ...}，而 load_consolidated 接受了 {'k8': (8,), 'k6': (6,), 'k2d': (2,2)}。
8 参数核（末位=100）与前 7 个的结果**逐位相同**（多余参数被静默丢弃）。
6 参数核 → IndexError: index 6 is out of bounds for axis 1 with size 6。
meta 里带 kernels/consolidated 时落盘 kernels = {}、consolidated = False。
```

## 最小复现
依赖：`.[full]`（numpy，部分还需 Pillow）。在仓库根目录执行 `python -X utf8 <脚本>`。

### issue5_consolidated_kernel_shape.py
```python
# -*- coding: utf-8 -*-
"""复现：固化核 JSON 的加载 / 消费全程不校验「7 参数」契约。
(1) 仓内资产 kernels_img0.json 形状核对；(2) 8 参数核被 hex_conv 静默截断成前 7 个；
(3) 6 参数核在 hex_conv 深处 IndexError；(4) save_consolidated 的 meta 可静默覆盖
kernels / consolidated 字段，落盘后学习核丢失。
运行：cd $P/lingshu && python <本脚本>"""
import json, os, tempfile
import numpy as np
import lingshu.nn.hex_cnn as hc
from lingshu.nn.hex_cnn import load_consolidated, save_consolidated, hex_conv, DEFAULT_KERNELS

asset = os.path.join(os.path.dirname(hc.__file__), "assets", "kernels_img0.json")
ks = load_consolidated(asset)
print("(1) 资产核形状:", {k: v.shape for k, v in ks.items()})

tmp = tempfile.mkdtemp()
p = os.path.join(tmp, "k.json")
json.dump({"kernels": {"k8": [0.1] * 7 + [100.0], "k6": [0.1] * 6, "k2d": [[1, 2], [3, 4]]}}, open(p, "w"))
bad = load_consolidated(p)
print("    load_consolidated 接受了:", {k: v.shape for k, v in bad.items()})
feat = np.random.default_rng(0).random((6, 8, 3)).astype(np.float32)
same = np.array_equal(hex_conv(feat, bad["k8"]), hex_conv(feat, bad["k8"][:7]))
print("(2) 8 参数核(末位=100) 与其前 7 个结果逐位相同:", same)
try:
    hex_conv(feat, bad["k6"]); r3 = "无异常"
except Exception as e:
    r3 = f"{type(e).__name__}: {e}"
print("(3) 6 参数核:", r3)

learned = np.array([0.3, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2], np.float32)
q = os.path.join(tmp, "c.json")
save_consolidated({"learned": learned}, {"source": "x", "kernels": {}, "consolidated": False}, q)
back = json.load(open(q))
print("(4) meta 含 kernels/consolidated 时落盘: kernels =", back["kernels"], " consolidated =", back["consolidated"])
print("VERDICT=" + ("BUG" if (same and back["kernels"] == {}) else "OK"))
```

## 代码定位
```
lingshu/nn/hex_cnn.py:299-303


def load_consolidated(path: str) -> Dict[str, np.ndarray]:
    """加载固化核（确定性模块——零训练依赖运行）。"""
    with open(path, encoding="utf-8") as f:
```

## 修法
load_consolidated 逐核校验 ndim in (1,2) and shape[-1] == 7 且 payload.get('consolidated') is True，否则抛点名核名的 ValueError；hex_conv 入口加 assert k.shape[-1] == 7。
save_consolidated 改成 {**meta, 'algo':..., 'consolidated': True, 'kernels': ...}（保留字段放后），或冲突键直接报错。

## 与已有 issue 的关系
#339 是 grow_kernel 的核族回绕问题，同属核契约面。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue5_consolidated_kernel_shape.py`：

```
(1) 资产核形状: {'smooth': (7,), 'edge_v': (7,), 'edge_h': (7,), 'laplacian': (7,), 'center_surround': (7,), 'learned_img0': (7,)}
    load_consolidated 接受了: {'k8': (8,), 'k6': (6,), 'k2d': (2, 2)}
(2) 8 参数核(末位=100) 与其前 7 个结果逐位相同: True
(3) 6 参数核: IndexError: index 6 is out of bounds for axis 1 with size 6
(4) meta 含 kernels/consolidated 时落盘: kernels = {}  consolidated = False
VERDICT=BUG
```
**仍复现**。本次读数：VERDICT=BUG，仍复现

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- `load_consolidated` 拒绝 8 参数、6 参数和二维核，报出点名核名的 ValueError
- meta 含 `kernels`/`consolidated` 时落盘不被覆盖（或直接报错）
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：影响等级和难度是自评；影响等级和难度以维护者定档为准。
