**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（涉及 perceive/verify 的快照时刻语义；最终定档以维护者为准）
**影响等级建议（补）**：A（verify 用旧观测反复计分，命中率可被抬高（量具失效），常规调用即触发。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：verify() 不核对观测快照时刻，同一快照可反复计分。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
world_model.py:321-398 / 419-458：verify() 记录了 _obs_tick 却从不读它，判定只比实体存在与距离，不比「预测时刻 vs 观测时刻」。

## 实测读数
```
正常闭环 8 tick 后 tick = 8、_obs_tick = 8，generate() 基于 tick=8 预测下一时刻，而 verify 用的快照时刻仍是 8。
verify 结果 hits=2 total=3 pending=0 hit_rate=0.6667；bounded_stochastic / chase_stochastic 都记为 verified distance=0.0。
不做任何事再 verify 一次：三条仍是 ['verified','verified','verified']。
```

## 最小复现
依赖：需 `.[world]`。

### issueH_verify_ignores_obs_tick.py
```python
# -*- coding: utf-8 -*-
"""UnifiedWorldModel.verify() 不核对观测快照时刻：用 tick t 的观测去「验证」对 t+1 的预测，
并把结果记为 verified（计入 hits/total）；同一快照可被反复验证。
perceive() 已保存 self._obs_tick，但 verify() 从不读取它。

运行：cd $P/lingshu && python <本脚本>
"""
from lingshu.world.world_model import UnifiedWorldModel

wm = UnifiedWorldModel(seed=42)
wm.world.create_scene(trees=0, water=False)
r = wm.world.add_entity("rabbit", behavior="wander", pos=(10, 1.5, 10), speed=0.3)
wf = wm.world.add_entity("wolf", behavior="seek", pos=(4, 1.5, 4), speed=0.6, goal=r)
wm.world.add_path("line", [(2, 1.5, 20), (22, 1.5, 20)])
pt = wm.world.add_entity("patrol", behavior="follow", pos=(2, 1.5, 20), speed=1.0, goal="line")

# 正常闭环先跑几轮，让模型学到 wolf 追 rabbit
wm.verify_run(n=8)
print("正常闭环 8 tick 后 tick =", wm.tick, " _obs_tick =", wm._obs_tick)

# 现在：只 generate（预测 tick+1），不推进世界、不 perceive，直接 verify
g = wm.generate(horizon=1)
v = wm.verify()
print("generate() 基于 tick =", g["tick"], "预测下一时刻；verify 使用的快照时刻 _obs_tick =", wm._obs_tick)
print("verify 结果: hits=%d total=%d pending=%d hit_rate=%s" % (v["hits"], v["total"], v["pending"], v["hit_rate"]))
for d in v["details"]:
    print("   ", d["mode"], "status=", d["status"], "distance=", d["distance"], "hit=", d["hit"])
v2 = wm.verify()
print("不做任何事再 verify 一次: total=%d status=%s" % (v2["total"], [d["status"] for d in v2["details"]]))

# 对照：正确的时刻对齐（推进世界 + perceive 后再 verify）
wm.world.step(1); wm.perceive(); v3 = wm.verify()
print("对照（step+perceive 后）: hits=%d total=%d hit_rate=%s _obs_tick=%s" % (v3["hits"], v3["total"], v3["hit_rate"], wm._obs_tick))

stale_patrol = next(d for d in v["details"] if d["mode"] == "bounded_noisy")
real_patrol = next(d for d in v3["details"] if d["mode"] == "bounded_noisy")
print("patrol: 陈旧快照判定 hit=%s(distance=%s)  真实下一时刻判定 hit=%s(distance=%s)" % (
    stale_patrol["hit"], stale_patrol["distance"], real_patrol["hit"], real_patrol["distance"]))
bug = v["total"] > 0 and wm._obs_tick is not None and g["tick"] == v["tick"] and all(
    d["status"] == "verified" for d in v["details"])
print("VERDICT=" + ("BUG" if bug else "OK"))
```

## 代码定位
```
lingshu/world/world_model.py:321-332
    def generate(self, horizon: int = 1, use_patterns: bool = True) -> Dict:
        """生成端口：世界图 → 候选未来（顺序语义外推 + 不确定边界）。

        模式：
          - exact：确定性追逐（目标可精确预测）→ 单候选，bound=hit_threshold
          - bounded_noisy：确定性方向但有扰动/转弯（flee/follow）→ 略宽
          - bounded_stochastic：随机行为 → 可达域（预测=当前位置）
          - chase_stochastic：追逐随机目标 → max(自身,目标)可达域 + 阈值（D1）
        """
        if use_patterns:
            self.infer_patterns()
        shadow = {eid: tuple(n.pos) for eid, n in self.nodes.items()}
```

## 修法
verify 时要求 _obs_tick > 预测所依据的 tick，否则判 stale/pending；同一快照只允许计分一次（记录已用快照 id）。
补测试：拿旧快照 verify 不得给 verified；同一快照二次 verify 不得重复计分。

## 与已有 issue 的关系
#74 是 anchor_verify 的通道一致判据用平均值替换全称量词，同属「验证判据不严」这一类。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issueH_verify_ignores_obs_tick.py`：

```
正常闭环 8 tick 后 tick = 8  _obs_tick = 8
generate() 基于 tick = 8 预测下一时刻；verify 使用的快照时刻 _obs_tick = 8
verify 结果: hits=0 total=0 pending=3 hit_rate=None
    bounded_stochastic status= pending distance= None hit= None
    chase_stochastic status= pending distance= None hit= None
    bounded_noisy status= pending distance= None hit= None
不做任何事再 verify 一次: total=0 status=['pending', 'pending', 'pending']
对照（step+perceive 后）: hits=3 total=3 hit_rate=1.0 _obs_tick=9
patrol: 陈旧快照判定 hit=None(distance=None)  真实下一时刻判定 hit=True(distance=0.0)
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK（旧快照判 pending）

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 用旧快照 verify 不给 verified（判 pending/stale）
- 同一快照二次 verify 不重复计分
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
