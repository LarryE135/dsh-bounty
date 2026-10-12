**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（要连真实脑端（dsh-memory MCP）做端到端复现；最终定档以维护者为准）
**影响等级建议（补）**：S（调用方按文档传 sensitivity=private 的观测被静默降成 internal 落盘，访客可重建（安全破坏），默认配置即可触发；若维护者认为需调用方显式传参属特定路径，可按 B。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：add_perception 用 **_kw 静默吞掉 sensitivity / condition_space。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/world/brain_store.py:431-440：BrainEngine.add_perception 用 **_kw 接收透传参数，sensitivity / condition_space 既没进入脑端调用的参数表，也没被拒绝；脑端按默认 internal 落盘，身体侧的声明被静默丢弃。

## 实测读数
```
add_perception(sensitivity='private', condition_space=…) 返回 id = mem_...（无异常、无告警）。
盘面 frontmatter：condition_space: {"time_window": [...]} 被写入，而 **sensitivity: "internal"**。
同身份直接 mdcg_remember(sensitivity='private') → 拒绝 {"error": "AccessDenied: 写入敏感度 private 超出 clearance internal"}。
无令牌连接 role=guest，重建世界 = {'保险箱': (1.0, 0.0, 1.0)}——private 声明的实体被访客读到。
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

### issue4_kwargs_swallowed.py
```python
"""[world/brain_store] BrainEngine.add_perception 用 **_kw 静默吞掉 sensitivity / condition_space：
声明 private 的观测按脑端缺省 internal 落盘（脑端对同身份直写 private 会拒绝），无令牌访客可重建出来。"""
import sys, os, glob; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import isolated, open_agent
from lingshu.world.brain_store import load_world_from_brain, BrainError

root, base = isolated()
a = open_agent(root, base)
try:
    ref = a.engine.add_perception(
        "场景实体 保险箱（safe）位于 (1,0,1)，状态 locked",
        sensitivity="private", condition_space={"observation_position": "卧室"},
        spatial_coordinates={"x": 1, "y": 0, "z": 1},
        tags=["spatial", "cat:safe", "ent:保险箱"], entities=["保险箱"])
    print("add_perception(sensitivity='private', condition_space=…) 返回 id =", ref.id, "（无异常、无告警）")
    f = glob.glob(os.path.join(root, "**", ref.id + ".md"), recursive=True)[0]
    fm = open(f, encoding="utf-8").read().split("---")[1]
    print("盘面 frontmatter：", [l for l in fm.splitlines() if l.split(":")[0] in ("sensitivity", "condition_space")])
    try:
        a.store.client.call("mdcg_remember", {"content": "对照", "layer": "contextual", "gated": False,
                                              "sensitivity": "private"})
        direct = "接受"
    except BrainError as e:
        direct = "拒绝：" + str(e).split("：", 1)[1][:80]
    print("同身份直接 mdcg_remember(sensitivity='private') ->", direct)
finally:
    a.store.client.close()
g = open_agent(root, base, identity=False)            # 无令牌：脑端降级为只读 guest
try:
    role = g.store.client.call("mdcg_service_info", {})["principal"]["role"]
    wm = load_world_from_brain(g)
    print("无令牌连接 role=%s，重建世界 =" % role, {k: v.pos for k, v in wm.entities.items()})
    bug = 'sensitivity: "internal"' in fm and "保险箱" in wm.entities
finally:
    g.store.client.close()
print("VERDICT=BUG" if bug else "VERDICT=OK")
```

## 代码定位
```
lingshu/world/brain_store.py:431-440
    def add_perception(self, content: str, importance: float = 0.6,
                       spatial_coordinates: Optional[Dict[str, float]] = None,
                       tags: Optional[List[str]] = None,
                       entities: Optional[List[str]] = None, **_kw) -> NodeRef:
        args = {"content": content, "layer": "contextual", "gated": False,
                "importance": float(importance), "tags": list(tags or [])}
        if spatial_coordinates:
            args["spatial"] = {"coords3d": {k: float(v)
                                            for k, v in spatial_coordinates.items()}}
        r = self.store.client.call("mdcg_remember", args)
```

## 修法
改成显式白名单参数，未知键直接抛错（不要 **_kw 吞掉）；sensitivity 要在写入前与本身份的 clearance 比较，超限拒绝而不是降级。
回归测试：声明 private 必须落成 private（或明确拒绝）；无令牌访客不得重建出该实体。

## 与已有 issue 的关系
#227 是脑侧子进程继承密钥的信任边界问题，#331/#292/#223 是 add_perception 的其它缺陷（content 类型、skip_dedup、M5 去重丢字段）——本条是同一入口的敏感度降级。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 脑端 dsh-memory `a3dba48` · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue4_kwargs_swallowed.py`：

```
Traceback (most recent call last):
  File "<包>/repro/r7-dsh-link/issue4_kwargs_swallowed.py", line 10, in <module>
    ref = a.engine.add_perception(
          ^^^^^^^^^^^^^^^^^^^^^^^^
  File "<仓根>/lingshu/world/brain_store.py", line 618, in add_perception
    r = self.store.client.call("mdcg_remember", args)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<仓根>/lingshu/world/brain_store.py", line 315, in call
    raise BrainError("工具 %s 返回 isError：%s" % (name, text[:400]))
lingshu.world.brain_store.BrainError: 工具 mdcg_remember 返回 isError：{"error": "AccessDenied: 写入敏感度 private 超出 clearance internal"}
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：写入 private 现在被脑端以 AccessDenied 拒绝（上游 abb52d0 引用 #364），不再静默降级

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 声明 private 的观测按 private 落盘，或在超出 clearance 时明确拒绝
- 无令牌访客不能重建出该实体

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑；r7 组依赖真实脑端 dsh-memory，只测了 `a3dba48` 这一个版本。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
