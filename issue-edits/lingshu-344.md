**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（要构造多进程交错读改写；最终定档以维护者为准）
**影响等级建议（补）**：B（多进程下 no_forget 标签静默丢失、节点被归档（数据损坏），需多进程并发写同一节点。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：tag_node / protect_node 的读改写不在同一事务，多进程下标签会静默丢失。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
longterm_gate.py:217-224 / core.py:1211-1218：先 SELECT tags 再在 Python 里改，最后整列 UPDATE 覆盖；两次操作之间没有事务或乐观锁，并发写互相覆盖，且 protect_node 的标签与 protections 表不同源。

## 实测读数
```
2 进程 × 300 次 tag_node：期望 600 个标签，实际留存 **363**（原审计）/ **300**（我复跑），异常 0 次。
单进程路径同样丢：写 protect_node 的 no_forget 后 tags 里没有它（no_forget 仍在 tags = False），protections 表里却有该节点。
随后 forget_advisor: {'archived': 1, 'kept': 0}，importance 0.15 → 0.10，tags=[..., 'archived']——被保护对象照样归档。
```

## 最小复现
依赖：纯标准库。在仓库根目录执行 `python -X utf8 <脚本>`（先 `python -m pip install -e .`）。

### issue2_tags_lost_update_multiprocess.py
```python
# -*- coding: utf-8 -*-
"""issue2：LayeredStore.tag_node / protect_node 对 nodes.tags 做「进程内读 → 改 → 整列覆盖写」，
读和写不在同一事务里。多进程共享同一文件库（官方部署形态：3×MCP server+循环+心跳）时
互相覆盖：0 异常，但标签静默丢失——包括 protect_node 写下的 no_forget 保护标签。

[A] 确定性复现：两个独立 LayeredStore（各自连接，等价于两个进程），让 A 在
    「读完旧 tags、尚未写回」时，B 完成 protect_node；A 写回后 no_forget 消失。
[B] 真实多进程：2 个进程各对同一节点 tag_node 300 个不同标签，统计最终留存数。
用法：cd <仓根> && python <本脚本>
"""
import json
import multiprocessing as mp
import os
import sys
import tempfile
import time

from lingshu.core.core import (LayeredStore, SpacetimeMemoryEngine, MemoryLayer)


def part_a(db):
    eng = SpacetimeMemoryEngine(db)
    n = eng.add_context("需要长期保护的情境记忆：设计者口述的第一条约束", importance=0.15)
    nid = n.id
    eng.close()

    a = LayeredStore(db)       # 进程 A 的连接（例如：MCP server 做 M5 去重打 duplicate 标签）
    b = LayeredStore(db)       # 进程 B 的连接（例如：门控/巩固循环给同一节点 protect_node）

    orig_get = a.get_node

    def get_node_then_other_process_runs(node_id):
        node = orig_get(node_id)                 # A 已读到旧 tags
        b.protect_node(node_id, "LongTermMemoryGate:snapshot")   # 此刻 B 提交保护
        return node

    a.get_node = get_node_then_other_process_runs
    a.tag_node(nid, "duplicate")                 # A 用旧 tags 整列覆盖写回

    c = LayeredStore(db)
    tags = json.loads(c.conn.execute("SELECT tags FROM nodes WHERE id=?", (nid,)).fetchone()[0])
    prot = [r[0] for r in c.conn.execute("SELECT node_id FROM protections")]
    print("[A] 最终 tags            =", tags)
    print("[A] protections 表含该节点 =", nid in prot)
    print("[A] no_forget 仍在 tags   =", "no_forget" in tags)

    # 后果：forget_advisor 只看 tags 里的 no_forget，受保护的情境记忆被归档降权
    eng2 = SpacetimeMemoryEngine(db)
    before = eng2.store.get_node(nid).importance
    r = eng2.forget_advisor()
    after = eng2.store.get_node(nid)
    print("[A] forget_advisor:", {k: r[k] for k in ("archived", "kept")},
          "| importance %.2f -> %.2f | tags=%s" % (before, after.importance, after.tags))
    eng2.close()
    return ("no_forget" not in tags) and (nid in prot)


def _worker(db, nid, prefix, n, q):
    st = LayeredStore(db)
    errors = 0
    for i in range(n):
        try:
            st.tag_node(nid, "%s%03d" % (prefix, i))
        except Exception:
            errors += 1
    q.put(errors)


def part_b(db, n=300):
    eng = SpacetimeMemoryEngine(db)
    nid = eng.add_perception("多进程共享的一条知识节点", skip_dedup=True).id
    eng.close()
    q = mp.Queue()
    ps = [mp.Process(target=_worker, args=(db, nid, p, n, q)) for p in ("a", "b")]
    t0 = time.time()
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    errors = sum(q.get() for _ in ps)
    st = LayeredStore(db)
    tags = json.loads(st.conn.execute("SELECT tags FROM nodes WHERE id=?", (nid,)).fetchone()[0])
    mine = [t for t in tags if t[:1] in ("a", "b") and t[1:].isdigit()]
    print("[B] 2 进程 × %d 次 tag_node：期望 %d 个标签，实际留存 %d 个，异常 %d 次，耗时 %.1fs"
          % (n, 2 * n, len(mine), errors, time.time() - t0))
    return len(mine) < 2 * n


def main():
    d = tempfile.mkdtemp(prefix="r2c_i2_")
    bug_a = part_a(os.path.join(d, "a.db"))
    bug_b = part_b(os.path.join(d, "b.db"))
    print("VERDICT=" + ("BUG" if (bug_a or bug_b) else "OK"))


if __name__ == "__main__":
    main()
```

## 代码定位
```
lingshu/core/longterm_gate.py:217-224
                node = engine.store.get_node(existing_id)
                tags_merged = list(dict.fromkeys((node.tags or []) + (tags or [])))
                engine.store.conn.execute(
                    "UPDATE nodes SET importance=?, tags=?, confidence=? WHERE id=?",
                    (max(node.importance, imp),
                     _json.dumps(tags_merged, ensure_ascii=False),
                     node.confidence, existing_id))
                engine.store.conn.commit()

lingshu/core/core.py:1211-1218
                c.execute(f"SELECT * FROM nodes WHERE {' AND '.join(conds)} LIMIT 500", params)
            else:
                c.execute("SELECT * FROM nodes LIMIT 500")
            rows = c.fetchall()
        scored = []
        # 评分用原查询二元组 Jaccard（含并集分母，与 char_bigram_jaccard 同式）；
        # 扩展词只负责预筛召回不稀释评分
        for row in rows:
```

## 修法
把标签改动收进单条 SQL（同一事务内读改写，或 BEGIN IMMEDIATE），或给 nodes 加版本列做乐观锁重试。
protect_node 的标签应是 protections 表的派生视图，或写入时校验两者一致。

## 与已有 issue 的关系
与 #197（HexNet.get_vec/set_vec 非原子读改写）同类；#181/#183 是 tags 的编码与检索问题，不是本条。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue2_tags_lost_update_multiprocess.py`：

```
  from entity_registry import EntityRegistry
  from semantic_space import SemanticSpaceProvider
  from attention_policy import AttentionPolicy
  from prediction_engine import PredictionEngine
  from spacetime_memory_core import LayeredStore as _LayeredStore
  from lifecycle_engine import LifecycleEngine
  from flywheel_engine import FlywheelEngine
  from self_cognition_engine import SelfCognitionEngine
  from body import build_default_registry
Traceback (most recent call last):
  File "<包>/repro/r2-core/issue2_tags_lost_update_multiprocess.py", line 97, in <module>
    main()
  File "<包>/repro/r2-core/issue2_tags_lost_update_multiprocess.py", line 91, in main
    bug_a = part_a(os.path.join(d, "a.db"))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<包>/repro/r2-core/issue2_tags_lost_update_multiprocess.py", line 38, in part_a
    a.tag_node(nid, "duplicate")                 # A 用旧 tags 整列覆盖写回
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<仓根>/lingshu/core/core.py", line 925, in wrapper
    return fn(self, *args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<仓根>/lingshu/core/core.py", line 2624, in tag_node
    node = self.get_node(node_id)
           ^^^^^^^^^^^^^^^^^^^^^^
  File "<包>/repro/r2-core/issue2_tags_lost_update_multiprocess.py", line 34, in get_node_then_other_process_runs
    b.protect_node(node_id, "LongTermMemoryGate:snapshot")   # 此刻 B 提交保护
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<仓根>/lingshu/core/core.py", line 925, in wrapper
    return fn(self, *args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<仓根>/lingshu/core/core.py", line 3004, in protect_node
    self.conn.execute("BEGIN IMMEDIATE")
sqlite3.OperationalError: database is locked
```
**无法判定**。本次读数：上游 protect_node 已改为 BEGIN IMMEDIATE；原脚本在单进程内模拟交错，新代码下第二个连接拿不到写锁，抛 `sqlite3.OperationalError: database is locked`，丢写没有发生也没法判定

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 两个进程交错执行 tag_node / protect_node 后，两边的标签都在
- 受保护节点不会因标签丢失被归档

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：原脚本用单进程模拟交错，在加了事务的新代码上不再适用；要判定是否真修好，需要改写成真正的多进程脚本；影响等级和难度以维护者定档为准。
