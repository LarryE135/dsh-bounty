**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：两处 clamp；最终定档以维护者为准）
**影响等级建议（补）**：B（需要非有限坐标输入才触发；触发后 NaN 被静默改成世界角落、non_finite 检查失效。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：NaN 坐标被 clamp 静默改写成世界角落。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
scene_simulator.py:188-189 与 spacetime_consistency.py:126-127 的 clamp 用 max/min 直接夹；NaN 参与比较时按「保留非 NaN 操作数」被静默替换成边界值，而不变量检查只看值是否有限——值已经被改成有限了。

## 实测读数
```
Python 语义：min(23.5, nan) = 23.5、max(0.5, min(23.5, nan)) = 23.5。
step 前 ghost=(nan,1.5,nan)，step 后 ghost=(23.5,1.5,23.5)；追逐者 wolf 同样被带到角落，**单 tick 位移 26.163**（speed=0.3）。
teleport(NaN) 后位置 (23.5,1.5,23.5)；invariants_ok = True、invariant_issues = []、invariant_violations = 0。
```

## 最小复现
依赖：需 `.[world]`。

### issueD_nan_pos_clamped_to_corner.py
```python
# -*- coding: utf-8 -*-
"""非有限坐标（NaN）被 clamp 静默改写成世界角落 (size-0.5)：
SceneSimulator.step / SpacetimeConsistency 的 non_finite 不变量对 x/z 成了死代码，
且 NaN 会通过 seek 决策「传染」给追逐者，追逐者同样瞬移到角落。

运行：cd $P/lingshu && python <本脚本>
"""
import math
from lingshu.world.scene_simulator import SceneSimulator
from lingshu.world.spacetime_consistency import SpacetimeConsistency

NAN = float("nan")
print("Python 语义: min(23.5, nan) =", min(23.5, NAN), "; max(0.5, min(23.5, nan)) =", max(0.5, min(23.5, NAN)))

# 1) SceneSimulator：wander 实体初始位置带 NaN
s = SceneSimulator(size=24, seed=42)
# wolf 先插入（先决策），目标 ghost 的坐标是 NaN
w = s.add_entity("wolf", behavior="seek", pos=(5, 1.5, 5), speed=0.3)
a = s.add_entity("ghost", behavior="wander", pos=(NAN, 1.5, NAN), speed=0.3)
s.entities[w].goal = a
print("step 前 ghost =", s.entities[a].pos, "wolf =", s.entities[w].pos)
s.step(1)
print("step 后 ghost =", s.entities[a].pos, " wolf =", s.entities[w].pos,
      " (wolf 一步 0.3 的速度却从 (5,5) 跳到角落)")
wolf_jump = math.dist((5, 5), (s.entities[w].pos[0], s.entities[w].pos[2]))
print("wolf 单 tick 位移 =", round(wolf_jump, 3), "（speed=0.3）")

# 2) SpacetimeConsistency：teleport 注入 NaN，不变量检查报告一切正常
stc = SpacetimeConsistency(size=24)
e = stc.add_entity("rabbit", behavior="wander", pos=(10, 1.5, 10), speed=0.3)
stc.teleport(e, (NAN, 1.5, NAN))
rec = stc.step_verified()
print("teleport(NaN) 后实体位置 =", stc.scene.entities[e].pos)
print("invariants_ok =", rec["invariants_ok"], " invariant_issues =", rec["invariant_issues"],
      " invariant_violations =", stc.consistency_report()["invariant_violations"])

bug = (s.entities[a].pos[0] == 23.5 and wolf_jump > 1.0 and rec["invariants_ok"]
       and stc.scene.entities[e].pos[0] == 23.5)
print("VERDICT=" + ("BUG" if bug else "OK"))
```

## 代码定位
```
lingshu/world/scene_simulator.py:188-189
                nx = max(0.5, min(self.world.size - 0.5, nx))
                nz = max(0.5, min(self.world.size - 0.5, nz))

lingshu/world/spacetime_consistency.py:126-127
        nx = max(0.5, min(self.scene.world.size - 0.5, nx))
        nz = max(0.5, min(self.scene.world.size - 0.5, nz))
```

## 修法
clamp 前先判 math.isfinite，NaN/Inf 一律拒绝写入（抛错或标 non_finite），不要夹到边界。
不变量检查改为在 clamp **之前**对原始值判定；seek/追逐逻辑对非有限目标应跳过而不是移动。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issueD_nan_pos_clamped_to_corner.py`：

```
  s.step(1)
  s.step(1)
  self.scene.step(n=1)
Python 语义: min(23.5, nan) = 23.5 ; max(0.5, min(23.5, nan)) = 23.5
step 前 ghost = (nan, 1.5, nan) wolf = (5.0, 1.5, 5.0)
step 后 ghost = (nan, 1.5, nan)  wolf = (5.0, 1.5, 5.0)  (wolf 一步 0.3 的速度却从 (5,5) 跳到角落)
wolf 单 tick 位移 = 0.0 （speed=0.3）
teleport(NaN) 后实体位置 = (nan, 1.5, nan)
invariants_ok = False  invariant_issues = ['out_of_bounds:scene_da0fc32d', 'non_finite:scene_da0fc32d']  invariant_violations = 1
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK（NaN 保留并报 non_finite）

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- NaN/Inf 坐标被拒绝或标 non_finite，不被夹到边界
- 不变量检查报出 non_finite
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
