**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（要连真实脑端、跨场景构造；最终定档以维护者为准）
**影响等级建议（补）**：A（多场景（常规用法）下同名实体互相改写状态，数据损坏。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：状态台账以实体名作全局 subject，跨场景同名实体互相覆盖。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/world/brain_store.py:344-350 / 417-421：状态单元以实体名（「桌子」）作全局 subject，两个场景的同名实体共用一个键，后写覆盖先写。

## 实测读数
```
写 bedroom 前 kitchen：桌子=broken 门=locked。
写 bedroom 后 kitchen：桌子=**neutral**（kitchen 从未改过，应为 broken），pos=(0.0,0.45,1.0)；bedroom：桌子=neutral pos=(5.0,0.45,5.0)。
台账 active 单元（subject, slot, value）= [('桌子','状态','neutral'), ('门','状态','locked')]。
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

### issue2_state_cross_scene.py
```python
"""[world/brain_store] 状态台账以「实体名」为全局 subject：不同场景（tag）里的同名实体共享/互相覆盖状态。"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import isolated, open_agent
from lingshu.world.brain_store import ingest_scene_to_brain, load_world_from_brain

root, base = isolated()
a = open_agent(root, base)
try:
    ingest_scene_to_brain(a, "桌子|table|0,0.45,1|broken\n门|door|1,1,0|locked", tag="kitchen")
    w1 = load_world_from_brain(a, tag="kitchen")
    print("写 bedroom 前 kitchen：桌子=%s 门=%s" % (w1.entities["桌子"].state, w1.entities["门"].state))
    ingest_scene_to_brain(a, "桌子|table|5,0.45,5|neutral", tag="bedroom")   # 另一场景的同名实体
    wk = load_world_from_brain(a, tag="kitchen"); wb = load_world_from_brain(a, tag="bedroom")
    print("写 bedroom 后 kitchen：桌子=%s（kitchen 从未改过，应为 broken） pos=%s" % (wk.entities["桌子"].state, wk.entities["桌子"].pos))
    print("bedroom：桌子=%s pos=%s" % (wb.entities["桌子"].state, wb.entities["桌子"].pos))
    sc = a.store.client.call("stg", {"op": "state_chain", "limit": 500})
    print("台账 active 单元（subject, slot, value）=", [(u.get("subject"), u.get("slot"), u.get("value")) for u in sc.get("items", []) if u.get("state") == "active"])
    bug = w1.entities["桌子"].state == "broken" and wk.entities["桌子"].state != "broken"
finally:
    a.store.client.close()
print("VERDICT=BUG" if bug else "VERDICT=OK")
```

## 代码定位
```
lingshu/world/brain_store.py:344-350
    def _state_map(self) -> Dict[str, str]:
        """活动状态槽位投影：subject → value（slot=「状态」；一次查询全量取回）。"""
        resp = self.client.call("stg", {"op": "state_chain", "limit": 500})
        m: Dict[str, str] = {}
        for u in (resp.get("items") or []):
            if u.get("slot") == STATE_SLOT and u.get("state") == "active":
                m[str(u.get("subject"))] = u.get("value")
```

## 修法
subject 带上场景作用域（如 f"{tag}/{ent}" 或用节点 id）；读写两侧同时改并兼容旧数据（旧 subject 可作回退）。
补守卫：两个 tag 的同名实体分别写不同状态，各自重建后互不影响。

## 与已有 issue 的关系
#28 是同一模块「状态写入失败全程静默」，#2（已关闭）是读取条数问题——本条是状态键的作用域。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 脑端 dsh-memory `a3dba48` · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue2_state_cross_scene.py`：

```
写 bedroom 前 kitchen：桌子=broken 门=locked
写 bedroom 后 kitchen：桌子=broken（kitchen 从未改过，应为 broken） pos=(0.0, 0.45, 1.0)
bedroom：桌子=neutral pos=(5.0, 0.45, 5.0)
台账 active 单元（subject, slot, value）= [('mem_1791778817118_52d739', '状态', 'broken'), ('mem_1791778817130_4756fc', '状态', 'locked'), ('mem_1791778817153_c370c2', '状态', 'neutral')]
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK（上游 abb52d0 引用 #366）

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 两个 tag 的同名实体分别写不同状态后，各自重建互不影响（kitchen 桌子仍为 broken）
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑；r7 组依赖真实脑端 dsh-memory，只测了 `a3dba48` 这一个版本。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
