**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：masked_loss 函数体；最终定档以维护者为准）
**影响等级建议（补）**：A（masked_loss 与模型无关，学习前后损失逐位相同，评测信号失效（量具失效）。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：masked_loss() 不随学得模型和 mask_last 变化。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
world_learner.py:300-322：masked_loss 走的是最后一点线性外推基线，既不调用 predict()/learn() 的模型分支，也没实现 mask_last。

## 实测读数
```
mask_last -> loss: {1: 0.6166, 2: 0.6166, 5: 0.6166, 20: 0.6166}——参数完全不生效。
未 learn: 0.6166 / learn(window=3): 0.6166 / learn(window=30): 0.6166 / 清空 model: 0.6166。
history 40 帧 loss = 0.6166；截到最后 3 帧 loss = 0.6166。
```

## 最小复现
依赖：需 `.[world]`。

### issueE_masked_loss_ignores_model.py
```python
# -*- coding: utf-8 -*-
"""WorldLearner.masked_loss()：mask_last 参数被忽略；损失与学得模型/观测量无关（只看最后 3 个点），
「随观测增多→重建损失下降（学习信号收敛）」的声明在实现上不可能成立。

运行：cd $P/lingshu && python <本脚本>
"""
import copy
from lingshu.world.world_learner import WorldLearner


def build():
    wl = WorldLearner(seed=42)
    wl.world.create_scene(trees=0, water=False)
    p = wl.world.add_entity("player", behavior="wander", pos=(5, 1.5, 5), speed=0.5)
    wl.world.add_entity("wolf", behavior="seek", pos=(15, 1.5, 15), speed=0.6, goal=p)
    wl.world.add_path("sq", [(3, 1.5, 3), (20, 1.5, 3), (20, 1.5, 20), (3, 1.5, 20)])
    wl.world.add_entity("guard", behavior="follow", pos=(3, 1.5, 3), speed=0.7, goal="sq")
    return wl


wl = build()
wl.run(n=40)
base = copy.deepcopy(wl)

# 1) mask_last 取不同值
res = {k: copy.deepcopy(base).masked_loss(mask_last=k)["loss"] for k in (1, 2, 5, 20)}
print("mask_last -> loss:", res)

# 2) 学 / 不学 / 用不同窗口学
no_learn = copy.deepcopy(base).masked_loss()["loss"]
w_learn = copy.deepcopy(base); w_learn.learn(window=3); l3 = w_learn.masked_loss()["loss"]
w_learn2 = copy.deepcopy(base); w_learn2.learn(window=30); l30 = w_learn2.masked_loss()["loss"]
w_learn3 = copy.deepcopy(base); w_learn3.model = {"per_entity": {}, "relations": [], "stochastic_targets": []}
lmod = w_learn3.masked_loss()["loss"]
print("未 learn: %s | learn(window=3): %s | learn(window=30): %s | 清空 model: %s" % (no_learn, l3, l30, lmod))

# 3) 只保留最后 3 帧观测 vs 全部 40 帧：损失相同 → 与「观测增多」无关
short = copy.deepcopy(base); short.history = short.history[-3:]
print("history 40 帧 loss = %s ; 截到最后 3 帧 loss = %s" % (no_learn, short.masked_loss()["loss"]))

independent = (len(set(res.values())) == 1 and no_learn == l3 == l30 == lmod
               and short.masked_loss()["loss"] == no_learn)
print("VERDICT=" + ("BUG" if independent else "OK"))
```

## 代码定位
```
lingshu/world/world_learner.py:300-311
    def masked_loss(self, mask_last: int = 1) -> Dict:
        """遮挡预测：遮住每实体最近一个未知时刻，用轨迹外推重建 → 损失。

        重建 = 最近两点线性外推（速度 × 方向持续性加权）。损失 = 均方距离。
        随观测增多，速度/方向估计更稳 → 重建损失下降（学习信号收敛）。
        """
        losses = []
        n_used = 0
        for eid, n in self.nodes.items():
            traj = [rec["entities"][eid]["pos"] for rec in self.history
                    if eid in rec["entities"]]
            if len(traj) < 3:
```

## 修法
用学得模型重建（复用 predict() 分支，遮掉的时刻之前截断历史再外推），或实现 mask_last（遮最后 k 点、多步外推）。
若只想保留线性外推基线，就改名 linear_extrapolation_loss 并删掉「学习信号收敛」的表述。回归测试：learn 前后损失必须能变、不同 mask_last 必须产生不同遮挡集合。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issueE_masked_loss_ignores_model.py`：

```
Traceback (most recent call last):
  File "<包>/repro/r3-world/issueE_masked_loss_ignores_model.py", line 26, in <module>
    res = {k: copy.deepcopy(base).masked_loss(mask_last=k)["loss"] for k in (1, 2, 5, 20)}
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<仓根>/lingshu/world/world_learner.py", line 341, in masked_loss
    raise ValueError("masked_loss currently supports mask_last=1 only")
ValueError: masked_loss currently supports mask_last=1 only
```
**部分已修**。本次读数：mask_last≠1 现在抛 ValueError（上游 df6e629 引用 #346）；维护者 2026-10-11 回复「前半已修，后半成立但属设计」

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 不同 mask_last 产生不同遮挡集合（或明确只支持 mask_last=1 并拒绝其它值）
- learn 前后损失能变化（或改名为线性外推基线并删掉「学习信号」表述）

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：上一节写的部分修复是本次读数，没有核对上游是否还有后续计划；影响等级和难度以维护者定档为准。
