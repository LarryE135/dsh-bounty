**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（要比对标定/无标定两分支和 _cell_of_pt 的取整口径；最终定档以维护者为准）
**影响等级建议（补）**：A（无标定分支（默认）下判决格原像差 1px，r8 同格被误缩径 51→40，产物数据错误。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：legal_win 无标定分支用 int 截断，与标定分支 ceil 不一致。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
hexgen_self_source.py:833 的无标定分支写作 int(k*size/3.0), int((k+1)*size/3.0)-1（下取整后再减一），标定分支用的是归一化分数与 ceil，两支口径不一致。

## 实测读数
```
legal_win(None) 与 _cell_of_pt 判决原像（r=0，排除画布内缩干扰）：col0 legal_win x∈[3,169] 而判决原像 x∈[0,170]；col1 [170,340] vs [171,341]；col2 [341,509] vs [342,511]。
_cell_of_pt(170,170) = r0、_cell_of_pt(341,341) = r4（边界像素被判给下一格）。
端到端 place_objects(centroid 档, zone_calib=None)，标称半径 51：('r8',) n=3 circle 现状 r=40 [(373,469),(469,373),(469,469)]，原像修正后 r=51。
```

## 最小复现
依赖：`.[full]`（numpy，部分还需 Pillow）。在仓库根目录执行 `python -X utf8 <脚本>`。

### issue3_legal_win_nocalib_preimage.py
```python
"""hexgen_self_source.legal_win：无方位标定（zone_calib=None，render_prompt_v3 /
reference_masks / place_objects 的缺省）时，`preimg` 用 int(k*size/3) 截断，
与判决函数 `_cell_of_pt`（min(2,int(y/size*3))）的原像差 1px：
每条带丢掉自己最高的一个合法像素、并把上一带的最高像素（非法）收进来。
后果：同格多件的铺位求解在 r8 等格被误缩径（51 → 40）。"""
import math, time
from lingshu.gen import hexgen_self_source as S
from lingshu.gen import hexgen_pack_certify as P

SIZE = 512
print("== ① legal_win(None) 窗口 vs _cell_of_pt 判决原像（r=0，排除画布内缩干扰）")
mismatch = 0
for k in range(3):
    x0, x1, _, _ = S.legal_win(f"r{k}", "circle", 0, SIZE, None)     # 列 k
    true = [x for x in range(SIZE) if int(S._cell_of_pt(x, 0, SIZE, None)[1]) == k]
    print(f"  col{k}: legal_win x∈[{x0},{x1}]  判决原像 x∈[{true[0]},{true[-1]}]")
    mismatch += (x0 != max(true[0], 3)) + (x1 != min(true[-1], SIZE - 3))
for v in (170, 341):
    print(f"  _cell_of_pt({v},{v}) = {S._cell_of_pt(v, v, SIZE, None)}")

orig = S.legal_win
def fixed(cell, shape, r, size=SIZE, zone_calib=None):
    """只改无标定分支：原像取 ceil（与有标定分支同式）。"""
    if zone_calib:
        return orig(cell, shape, r, size, zone_calib)
    qy, qx = divmod(int(cell[1]), 3)
    pre = lambda k: (0 if k == 0 else math.ceil(k * size / 3.0),
                     size - 1 if k == 2 else math.ceil((k + 1) * size / 3.0) - 1)
    x0, x1 = pre(qx); y0, y1 = pre(qy)
    e = math.ceil(S.paint_extent(shape, r) + 2.0)
    return max(x0, e), min(x1, size - e), max(y0, e), min(y1, size - e)

print("== ② 端到端：place_objects(centroid 档，zone_calib=None)，标称半径 51")
shrunk = 0
for cells, n, sh in ((("r8",), 3, "circle"), (("r8",), 3, "triangle"), (("r0",), 3, "circle")):
    t = time.time()
    S.legal_win = orig
    pa, ra = S.place_objects(cells, n, 51, SIZE, shape=sh, zone_calib=None)
    S.legal_win = fixed
    pb, rb = S.place_objects(cells, n, 51, SIZE, shape=sh, zone_calib=None)
    S.legal_win = orig
    ok_b = P.check_witness(pb, cells, n, sh, rb, None)
    print(f"  {cells} n={n} {sh:8s} 现状 r={ra} {pa} | 原像修正 r={rb} {pb} "
          f"check_witness=(合法={ok_b[0]}, 最小余量={ok_b[1]:.2f}) {time.time()-t:.1f}s", flush=True)
    shrunk += ra < rb
print(f"window_mismatch={mismatch} shrunk_cases={shrunk}")
print("VERDICT=BUG" if (mismatch and shrunk) else "VERDICT=OK")
```

## 代码定位
```
lingshu/gen/hexgen_self_source.py:833-833
        return int(k * size / 3.0), int((k + 1) * size / 3.0) - 1
```

## 修法
无标定分支改成与标定分支同式（用 ceil 定右边界），保证 legal_win 与 _cell_of_pt 的判决原像逐格一致。
补测试：对每个格子，legal_win 窗口端点必须包含该格判决原像的全部像素。

## 与已有 issue 的关系
#188 是 hexgen_pack_certify 无标定分支的另一处（_rank_ok_vec 拿像素切点比归一化坐标）；#218 是 hexgen_self_source 的 _solve_centroid 锚点问题——三处同属「无标定分支口径不一致」。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue3_legal_win_nocalib_preimage.py`：

```
== ① legal_win(None) 窗口 vs _cell_of_pt 判决原像（r=0，排除画布内缩干扰）
  col0: legal_win x∈[3,170]  判决原像 x∈[0,170]
  col1: legal_win x∈[171,341]  判决原像 x∈[171,341]
  col2: legal_win x∈[342,509]  判决原像 x∈[342,511]
  _cell_of_pt(170,170) = r0
  _cell_of_pt(341,341) = r4
== ② 端到端：place_objects(centroid 档，zone_calib=None)，标称半径 51
  ('r8',) n=3 circle   现状 r=51 [(342, 342), (371, 458), (458, 371)] | 原像修正 r=51 [(342, 342), (371, 458), (458, 371)] check_witness=(合法=True, 最小余量=1.57) 0.4s
  ('r8',) n=3 triangle 现状 r=51 [(342, 342), (371, 458), (458, 371)] | 原像修正 r=51 [(342, 342), (371, 458), (458, 371)] check_witness=(合法=True, 最小余量=1.57) 0.4s
  ('r0',) n=3 circle   现状 r=51 [(54, 54), (83, 170), (170, 83)] | 原像修正 r=51 [(54, 54), (83, 170), (170, 83)] check_witness=(合法=True, 最小余量=1.57) 0.4s
window_mismatch=0 shrunk_cases=0
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK（window_mismatch=0 shrunk_cases=0）

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 每个格子 legal_win 窗口端点都包含该格判决原像的全部像素：window_mismatch=0、shrunk_cases=0
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
