**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：_state_map 不看 truncated；最终定档以维护者为准）
**影响等级建议（补）**：B（全库实体超过 500 时才触发，本场景实体状态被补成 None。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：_state_map 固定读 500 条并丢弃 truncated=True。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/world/brain_store.py:346：_state_map 固定传 limit=500，既不检查返回体的 truncated 字段，也不做分页或按场景过滤。

## 实测读数
```
脑端 state_chain 返回：count=503 items=500 truncated=True。
返回 items 前 2 / 后 2 个 subject：['crate000','crate001'] / ['crate498','crate499']；「肥鱼」是否在返回 items 中：False。
适配器 _state_map 中 肥鱼 = None；get_nodes_by_tag('kitchen', limit=1000) 状态 = {'肥鱼': None, '桌子': None, '树': None}（实写 shy/broken/withered，台账已入账）。
```

## 最小复现
依赖：真实脑端（dsh-memory 的 MCP stdio 服务）+ 同目录的 `_common.py`。运行前：
1. `git clone https://github.com/FuRongJun-1999/dsh-memory`（脑端）与本仓库；
2. 本仓库 `python -m pip install -e .`；
3. `export PYTHONPATH=<本仓库克隆>`、`export MDCG_BRAIN_PYTHONPATH=<dsh-memory 克隆>`；
4. 在仓库根目录 `python -X utf8 <脚本>`。
注：Windows 上 `_common.py` 把脑端 `MDCG_AUX_ROOT` 指到 `<tmp>/aux`，会撞上脑端的保留设备名守卫而拒启动，需改成非保留名（如 `auxstore`）后再跑；下面给出的是改过名的那一版。

### _common.py
```python
"""共用：隔离连接真实脑端（dsh-memory MCP stdio）。只用临时目录。"""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.environ.get("MDCG_BRAIN_PYTHONPATH") or os.path.normpath(
    os.path.join(HERE, "..", "..", "r1-baseline", "dsh-memory"))
from lingshu.world.brain_store import connect  # noqa: E402
#: 与 tests/test_brain_store.py 相同的隔离身份（legacy 三开关）
LEGACY_ID = {"MDCG_LEGACY_ENV_AUTH": "1", "MDCG_CAN_ADMIN": "1",
             "MDCG_LEGACY_ENV_ADMIN": "1"}

def isolated(prefix="r7_"):
    root = tempfile.mkdtemp(prefix=prefix)
    home = tempfile.mkdtemp(prefix=prefix + "home_")
    return root, {"HOME": home, "MDCG_AUX_ROOT": os.path.join(home, "auxstore")}

def open_agent(root, base, identity=True):
    env = dict(base)
    if identity:
        env.update(LEGACY_ID)
    return connect(root=root, pythonpath=BRAIN, extra_env=env)
```

### issue3_state_truncated_ignored.py
```python
"""[world/brain_store] _state_map 固定 stg(state_chain, limit=500) 且丢弃返回体 truncated/count：
全库实体 >500 时，新场景实体的状态被静默丢弃（state_attributes=None → 重建回落 neutral）。"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import isolated, open_agent
from lingshu.world.brain_store import ingest_scene_to_brain

root, base = isolated()
a = open_agent(root, base)
try:
    ingest_scene_to_brain(a, "\n".join("crate%03d|crate|%d,0,1|idle" % (i, i) for i in range(500)), tag="archive")
    # 新场景：3 个中文名实体（与 tests/test_brain_store.py 的「肥鱼/桌子/树」同类）
    ingest_scene_to_brain(a, "肥鱼|fatfish|0,0.85,5|shy\n桌子|table|1.5,0.45,6|broken\n树|tree|-2,1,7|withered", tag="kitchen")
    sc = a.store.client.call("stg", {"op": "state_chain", "limit": 500})
    items = sc.get("items") or []
    print("脑端 state_chain 返回：count=%s items=%d truncated=%s" % (sc.get("count"), len(items), sc.get("truncated")))
    print("返回 items 前 2 / 后 2 个 subject：", [u.get("subject") for u in items[:2]], [u.get("subject") for u in items[-2:]])
    print("肥鱼 是否在返回 items 中：", any(u.get("subject") == "肥鱼" for u in items))
    print("适配器 _state_map 中 肥鱼 =", a.store._state_map().get("肥鱼"))
    ns = a.store.get_nodes_by_tag("kitchen", limit=1000)
    got = {next(t[4:] for t in n.tags if t.startswith("ent:")): n.state_attributes for n in ns}
    print("get_nodes_by_tag('kitchen', limit=1000) 状态 =", got, "（实写 shy/broken/withered，台账已入账）")
    bug = sc.get("truncated") and all(v is None for v in got.values()) and len(got) == 3
finally:
    a.store.client.close()
print("VERDICT=BUG" if bug else "VERDICT=OK")
```

## 代码定位
```
lingshu/world/brain_store.py:346-346
        resp = self.client.call("stg", {"op": "state_chain", "limit": 500})
```

## 修法
检查 truncated：为真就分页取全（或用按场景过滤的查询），取不全时明确报错而不是补 None。
补测试：全库 > limit 条时，目标场景的实体状态必须完整且非 None。

## 与已有 issue 的关系
#35 是库端检索按插入序硬截断无 ORDER BY（同类「静默截断」），#2（已关闭）是读取条数未传到脑端——本条是适配器层丢弃 truncated 标记。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 脑端 dsh-memory `a3dba48` · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue3_state_truncated_ignored.py`：

```
脑端 state_chain 返回：count=503 items=500 truncated=True
返回 items 前 2 / 后 2 个 subject： ['mem_1791778817043_95a39f', 'mem_1791778817051_163b76'] ['mem_1791778829354_15232c', 'mem_1791778829380_fa725b']
肥鱼 是否在返回 items 中： False
Traceback (most recent call last):
  File "<包>/repro/r7-dsh-link/issue3_state_truncated_ignored.py", line 18, in <module>
    print("适配器 _state_map 中 肥鱼 =", a.store._state_map().get("肥鱼"))
                                         ^^^^^^^^^^^^^^^^^^^^
  File "<仓根>/lingshu/world/brain_store.py", line 452, in _state_map
    raise BrainError(
lingshu.world.brain_store.BrainError: 状态槽位投影被截断（count=503 > limit=500）且未给出主体清单，无法取全——不静默补 None（issue #365）
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：截断时 `_state_map` 显式抛 BrainError（报错信息里写明 issue #365），不再补 None

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 全库超过 limit 时，目标场景实体状态完整且非 None，或明确报错而不是补 None

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑；r7 组依赖真实脑端 dsh-memory，只测了 `a3dba48` 这一个版本。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
