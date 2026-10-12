**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：tag 过滤在适配器侧而非脑端；最终定档以维护者为准）
**影响等级建议（补）**：B（需要另一场景条目数 ≥ limit 才触发，本场景返回 0 个实体。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：get_nodes_by_tag 先取全库 top-k 再过滤，别的场景占满名额时本场景返回 0。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/world/brain_store.py:378-387：先向脑端取全库 top-k（k=limit），再在身体侧按 tag 过滤；另一场景的节点先占满 k 个名额，本场景就被过滤成空。scene_model.py:345 的调用方按场景取 limit 个实体，正好踩中。

## 实测读数
```
get_nodes_by_tag('roomA', limit=5) -> **0** 个（roomA 实有 5 个）；limit=10 -> 0；limit=25 -> 0；limit=30 -> 5。
load_world_from_brain(tag='roomA') 实体 = ['apple0'...'apple4']（limit 足够时正常）。
另写 archive 200 个后：load_world_from_brain(tag='kitchen') 实体 = []（实写 cup0..cup2）。
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

### issue1_tag_crowding.py
```python
"""[world/brain_store] get_nodes_by_tag 先取全库 top-k 再按 tag 过滤：
另一个场景写满 k 条后，本场景 limit 再大于实体数也返回 0，整个世界重建为空。"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import isolated, open_agent
from lingshu.world.brain_store import ingest_scene_to_brain, load_world_from_brain

root, base = isolated()
a = open_agent(root, base)
try:
    # 场景 B（仓库/档案）先写 25 个实体；场景 A（厨房）后写 5 个
    ingest_scene_to_brain(a, "\n".join("box%d|box|%d,0,1|neutral" % (i, i) for i in range(25)), tag="roomB")
    ingest_scene_to_brain(a, "\n".join("apple%d|apple|%d,0,2|ripe" % (i, i) for i in range(5)), tag="roomA")
    res = {}
    for lim in (5, 10, 25, 30):
        res[lim] = len(a.store.get_nodes_by_tag("roomA", limit=lim))
        print("get_nodes_by_tag('roomA', limit=%d) -> %d 个（roomA 实有 5 个）" % (lim, res[lim]))
    print("load_world_from_brain(tag='roomA') 实体 =", sorted(load_world_from_brain(a, tag="roomA").entities))
    # 规模化：另一场景 ≥200 条时，scene_model 固定 limit=200 的世界重建直接为空
    ingest_scene_to_brain(a, "\n".join("crate%03d|crate|%d,0,3|idle" % (i, i) for i in range(200)), tag="archive")
    ingest_scene_to_brain(a, "\n".join("cup%d|cup|%d,0,4|full" % (i, i) for i in range(3)), tag="kitchen")
    kw = sorted(load_world_from_brain(a, tag="kitchen").entities)
    print("另写 archive 200 个后：load_world_from_brain(tag='kitchen') 实体 =", kw, "（实写 cup0..cup2）")
    raw = a.store.client.call("cg", {"op": "read", "query": "场景实体", "k": 5})
    items = raw.get("results") or raw.get("items") or []
    print("脑端 cg(read, k=5) 返回的前 5 条 tags 里的场景 =",
          [next((t for t in ((it.get("node") or it).get("frontmatter") or it.get("frontmatter") or {}).get("tags", []) if t in ("roomA", "roomB", "archive", "kitchen")), None) for it in items])
    bug = res[5] == 0 and res[25] == 0 and kw == []
finally:
    a.store.client.close()
print("VERDICT=BUG" if bug else "VERDICT=OK")
```

## 代码定位
```
lingshu/world/brain_store.py:378-387
        resp = self.client.call("cg", {"op": "read", "query": self.seed_query,
                                       "k": max(1, int(limit))})
        states = self._state_map()
        out: List[BrainNode] = []
        for item in (resp.get("results") or resp.get("items") or []):
            node = item.get("node") or item
            fm = node.get("frontmatter") or item.get("frontmatter") or {}
            tags = list(fm.get("tags") or [])
            if tag not in tags:
                continue                      # 裁定三：过滤在适配器侧

lingshu/world/scene_model.py:345-345
    nodes = store.get_nodes_by_tag(tag, limit=200)
```

## 修法
把 tag 条件下推到脑端查询（或在脑端按 tag 过滤后再取 k）；取不到时区分「无匹配」与「被截断」。
补测试：两个场景各有 N 条时，任意 limit >= N 的查询都必须返回本场景全部实体。

## 与已有 issue 的关系
#2（已关闭）是「读取条数未传到脑端」的同类读回契约问题（21 个实体只重建 20 个），本条是 limit 与过滤顺序的错配。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 脑端 dsh-memory `a3dba48` · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue1_tag_crowding.py`：

```
get_nodes_by_tag('roomA', limit=5) -> 5 个（roomA 实有 5 个）
get_nodes_by_tag('roomA', limit=10) -> 5 个（roomA 实有 5 个）
get_nodes_by_tag('roomA', limit=25) -> 5 个（roomA 实有 5 个）
get_nodes_by_tag('roomA', limit=30) -> 5 个（roomA 实有 5 个）
load_world_from_brain(tag='roomA') 实体 = ['apple0', 'apple1', 'apple2', 'apple3', 'apple4']
另写 archive 200 个后：load_world_from_brain(tag='kitchen') 实体 = ['cup0', 'cup1', 'cup2'] （实写 cup0..cup2）
脑端 cg(read, k=5) 返回的前 5 条 tags 里的场景 = ['roomB', 'roomB', 'roomB', 'roomB', 'roomB']
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 两个场景各有 N 条时，limit ≥ N 的查询返回本场景全部实体
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑；r7 组依赖真实脑端 dsh-memory，只测了 `a3dba48` 这一个版本。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
