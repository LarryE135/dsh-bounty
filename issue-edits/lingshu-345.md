**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：compare_policies / _build_world；最终定档以维护者为准）
**影响等级建议（补）**：A（评测工具不使用调用者的世界与参数，比较结论与调用者的场景无关（量具失效），默认调用即触发。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：compare_policies() 忽略调用者的世界、seed 和 size。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
curiosity_explorer.py:242-266：compare_policies 自建内置世界，只把 window 当预热长度传下去，size/seed/调用者世界都没透传。

## 实测读数
```
实例1（size=24 seed=42 window=6，用户世界 0 实体）与实例2（size=60 seed=12345 window=3，用户世界 5 实体）：构造语句只有 ex = CuriosityExplorer(size=24)——seed、window 都没进去。
两实例读数近乎相同：probe_rate=0.6667/0.9333、final_unc=0.7749/0.7706，观测序列都是 [3,3,4]；换 seed 读数逐位相同。
实例2 用户世界里 5 个自建实体，比较结果里只出现 3 个内置实体（player/wolf/rabbit）。
```

## 最小复现
依赖：需 `.[world]`。

### issueA_compare_policies_ignores_instance.py
```python
# -*- coding: utf-8 -*-
"""CuriosityExplorer.compare_policies() 无视调用实例：seed / size / window / 用户自建世界全部不生效。

运行：cd $P/lingshu && python <本脚本>
"""
import json
from lingshu.world.curiosity_explorer import CuriosityExplorer


def strip_ids(res):
    """去掉 uuid 实体 id（每次运行不同），只比较数值读数。"""
    out = {}
    for pol, r in res["results"].items():
        out[pol] = {"probe_rate": r["probe_rate"], "naive_rate": r["naive_rate"],
                    "final_uncertainty": r["final_uncertainty"],
                    "curve": r["curve"],
                    "obs_counts_sorted": sorted(r["obs_distribution"].values()),
                    "n_entities_seen": len(r["obs_distribution"])}
    return out


# 实例 1：默认参数，空世界（不建场景、不加实体）
a = CuriosityExplorer()
ra = strip_ids(a.compare_policies(budget=1, explore_ticks=10, probe_ticks=5))

# 实例 2：完全不同的 seed / size / window，且用户自己建了 5 个实体的世界
b = CuriosityExplorer(size=60, seed=12345, window=3)
b.world.create_scene(trees=0, water=False)
for i in range(5):
    b.world.add_entity("deer", behavior="wander", pos=(5 + 8 * i, 1.5, 30), speed=1.5)
rb = strip_ids(b.compare_policies(budget=1, explore_ticks=10, probe_ticks=5))

print("实例1 参数: size=24 seed=42 window=6, 用户世界实体数 =", len(a.world.entities))
print("实例2 参数: size=60 seed=12345 window=3, 用户世界实体数 =", len(b.world.entities))
for pol in ("curiosity", "random", "round_robin"):
    print(f"[{pol}] 实例1 probe_rate={ra[pol]['probe_rate']} final_unc={ra[pol]['final_uncertainty']}"
          f" 实体数={ra[pol]['n_entities_seen']} obs={ra[pol]['obs_counts_sorted']}")
    print(f"[{pol}] 实例2 probe_rate={rb[pol]['probe_rate']} final_unc={rb[pol]['final_uncertainty']}"
          f" 实体数={rb[pol]['n_entities_seen']} obs={rb[pol]['obs_counts_sorted']}")
same = json.dumps(ra, sort_keys=True) == json.dumps(rb, sort_keys=True)
print("两实例 compare_policies 数值读数逐位相同:", same)
# 同一实例换 seed 的直接对照：seed=1 与 seed=2
r1 = strip_ids(CuriosityExplorer(seed=1).compare_policies(budget=1, explore_ticks=10, probe_ticks=5))
r2 = strip_ids(CuriosityExplorer(seed=2).compare_policies(budget=1, explore_ticks=10, probe_ticks=5))
print("seed=1 与 seed=2 读数逐位相同:", json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True))
# 只改 window（其它全默认）：window 只影响 warm-up 时长，被对比的探索器自身 window 仍是 6
import inspect
src = inspect.getsource(CuriosityExplorer._build_world)
print("_build_world 构造语句:", [l.strip() for l in src.splitlines() if "CuriosityExplorer(" in l and "ex =" in l])
same_seed = json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
ignored_world = rb["curiosity"]["n_entities_seen"] != len(b.world.entities)
print("实例2 用户世界 5 个实体，compare 结果里只出现", rb["curiosity"]["n_entities_seen"], "个实体（内置 player/wolf/rabbit）")
bug = same_seed and ignored_world
print("VERDICT=" + ("BUG" if bug else "OK"))
```

## 代码定位
```
lingshu/world/curiosity_explorer.py:242-253
    @staticmethod
    def _build_world() -> "CuriosityExplorer":
        """标准测试世界：追逐链 player(wander)←wolf(seek)←rabbit(flee)。

        依赖链：player 是信息瓶颈（wolf 追它、rabbit 逃 wolf 间接依赖它）。
        """
        ex = CuriosityExplorer(size=24)
        ex.world.create_scene(trees=2, water=False)
        p = ex.world.add_entity("player", behavior="wander", pos=(2, 1.5, 2), speed=0.5)
        w = ex.world.add_entity("wolf", behavior="seek", pos=(15, 1.5, 15), speed=0.6, goal=p)
        r = ex.world.add_entity("rabbit", behavior="flee", pos=(10, 1.5, 10), speed=0.5, goal=w)
        return ex
```

## 修法
从调用者取 world 与参数（或在签名里显式声明内置世界），seed/size 一并透传；_build_world 里不要硬编码 size=24。
回归测试：不同 seed/size 的输出必须不同；用户世界实体必须出现在比较结果里。

## 与已有 issue 的关系
#148 是同一模块 observe() 的另一处（不记 last_*），可同批处理。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issueA_compare_policies_ignores_instance.py`：

```
实例1 参数: size=24 seed=42 window=6, 用户世界实体数 = 0
实例2 参数: size=60 seed=12345 window=3, 用户世界实体数 = 5
[curiosity] 实例1 probe_rate=0.8 final_unc=1.4998 实体数=3 obs=[13, 14, 19]
[curiosity] 实例2 probe_rate=0.7333 final_unc=0.8997 实体数=3 obs=[12, 12, 13]
[random] 实例1 probe_rate=0.8667 final_unc=1.7613 实体数=3 obs=[13, 15, 18]
[random] 实例2 probe_rate=0.8 final_unc=0.8998 实体数=3 obs=[11, 12, 14]
[round_robin] 实例1 probe_rate=0.8667 final_unc=1.4905 实体数=3 obs=[15, 15, 16]
[round_robin] 实例2 probe_rate=0.8 final_unc=0.9017 实体数=3 obs=[12, 12, 13]
两实例 compare_policies 数值读数逐位相同: False
seed=1 与 seed=2 读数逐位相同: False
_build_world 构造语句: ['ex = CuriosityExplorer(size=self.size, ground_level=self.ground_level,']
实例2 用户世界 5 个实体，compare 结果里只出现 3 个实体（内置 player/wolf/rabbit）
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 不同 seed/size 的 compare_policies 读数不同
- 用户自建世界的全部实体出现在比较结果里
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
