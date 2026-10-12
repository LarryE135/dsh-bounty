**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：三处空掩膜判断；最终定档以维护者为准）
**影响等级建议（补）**：B（合法区域为空时才触发（特定半径），抛异常而不是判无解。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：合法区域为空时 certify_* 抛 ValueError。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/gen/hexgen_pack_certify.py:144 一带在包围盒裁剪 / 取最值前没有空集分支。

## 实测读数
```
合法掩膜全 False 时三个入口直接抛 ValueError，而不是返回 feasible=False。
与 #188 的「合法掩膜退化为全图」正好是同一判据的两端：一个空集、一个全集，都没被当正常输入处理。
```

## 最小复现
依赖：`.[full]`（numpy，部分还需 Pillow）。在仓库根目录执行 `python -X utf8 <脚本>`。

### issue2_certify_empty_mask.py
```python
"""hexgen_pack_certify：合法区域为空（半径大到实物放不进允许格）时，
certify_radius / certify_p1 / witness_at 在 `ys.min()` 抛 ValueError，
而不是给出它存在的意义——「该半径无解」(feasible=False)。
用**带冻结方位标定**的口径（与 #188 的「无标定切点量纲错」无关）。"""
from lingshu.gen import hexgen_pack_certify as P
from lingshu.gen import hexgen_self_source as S

ZC = {"row": {"cuts": [0.5236, 0.6484]}, "col": {"cuts": [0.264, 0.6234]}}  # 源码注释给的冻结切点
cells = ("r0",)     # 左上格：列切点 0.264*512≈135px
SHAPE = "rectangle"  # 画笔外延 1.35r
crash = 0
for r in (90, 96, 97, 100):
    m = P.legal_mask(cells, SHAPE, r, ZC)
    row = f"r={r} legal_px={int(m.sum())}"
    for name, fn in (("certify_radius", lambda: P.certify_radius(cells, 3, SHAPE, r, ZC, max_p1=3)),
                     ("certify_p1", lambda: P.certify_p1(60, 60, cells, 3, SHAPE, r, ZC)),
                     ("witness_at", lambda: P.witness_at(cells, 3, SHAPE, r, ZC))):
        try:
            out = fn()
            v = out.get("feasible") if isinstance(out, dict) else ("None" if out is None else "ok")
            row += f" | {name}: {v}"
        except ValueError as e:
            crash += 1
            row += f" | {name}: ValueError({str(e)[:45]})"
    print(row, flush=True)
# 对照：生产求解器在同一题面上照常返回（会缩径到下限 16），不会崩
r_c, pts = S._solve_centroid(list(cells), 3, 100, 512, SHAPE, ZC)
print("production _solve_centroid(r0, n=3, rad=100):", r_c, pts)
print("VERDICT=BUG" if crash else "VERDICT=OK")
```

## 代码定位
```
lingshu/gen/hexgen_pack_certify.py:144-144
    by0, by1 = int(ys.min()), int(ys.max())
```

## 修法
三处都在裁剪前加 if not L.any(): return dict(feasible=False, max_slack=-inf, best_p1=None, n_p1=0, per_p1=[])（certify_p1 返回 (-inf, 0)、witness_at 返回 None）。
守门加一条「空掩膜 ⇒ feasible=False」的断言。

## 与已有 issue 的关系
#188 修的是同一文件 _rank_ok_vec 无标定分支把合法掩膜退化成全图；本条是空掩膜，两条一起才覆盖边界。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue2_certify_empty_mask.py`：

```
r=90 legal_px=1584 | certify_radius: False | certify_p1: ok | witness_at: None
r=96 legal_px=408 | certify_radius: False | certify_p1: ok | witness_at: None
r=97 legal_px=270 | certify_radius: False | certify_p1: ok | witness_at: None
r=100 legal_px=0 | certify_radius: False | certify_p1: ok | witness_at: None
production _solve_centroid(r0, n=3, rad=100): 60 [(84, 84), (84, 176), (84, 268)]
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 空掩膜时 certify_radius 返回 feasible=False、certify_p1 返回 (-inf, 0)、witness_at 返回 None
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
