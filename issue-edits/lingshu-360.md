**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（涉及 export 与 derive_edges 两处、需要构造目录顺序和时区对照；最终定档以维护者为准）
**影响等级建议（补）**：B（同一真源在不同目录创建顺序或时区下产出不同推导边，复现性受损。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：coggraph 同一真源会产出不同的推导边。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
tools/coggraph/export_coggraph.py:111 的 os.walk(root) 未对 dirnames 排序（节点顺序即文件系统顺序），derive_edges 的 R5 同名标题归并依赖该顺序；日枢纽用本地时区。

## 实测读数
```
① 目录遍历顺序：w1 创建顺序 ['aaa','bbb','ccc'] → os.walk 子目录顺序 ['ccc','bbb','aaa']，nodes=['c1','bbb1','aaa1']，R5 边=[('aaa1','bbb1'),('c1','bbb1')]。
w2 把创建顺序反过来 → os.walk 顺序 ['aaa','bbb','ccc']，nodes=['aaa1','bbb1','c1']，R5 边=[('bbb1','aaa1'),('c1','aaa1')]；两次 **source_sha 相同（dc40697ac44b97b3）而边集合不同**。
② derive_edges.py:232 用 time.strftime('%Y-%m-%d', time.localtime(ts)) 分日枢纽，跨 TZ 机器的 R4 读数随之改变。
平台说明：我在 Windows 11 上复跑该脚本得到 VERDICT=OK（NTFS 的 os.walk 子目录序恰为字母序、TZ 差异未触发）；代码路径与 Linux 上的读数一致，本条按代码判据 + 原审计 Linux 证据判断。
```

## 最小复现
依赖：纯标准库。注：本脚本在 Windows 上会打印 VERDICT=OK（NTFS 目录序恰为字母序、TZ 差异未触发），Linux 上复现的读数是本条的原始证据。

### issue4_coggraph_nondeterminism.py
```python
# -*- coding: utf-8 -*-
"""coggraph 产物不可复现：同一真源（graph.meta.source_sha 相同）
① 仅目录创建顺序不同 → export 节点顺序不同 → derive_edges R5 的 title_owner 取 ids[0] → 推导边指向不同节点；
② 同一 graph.json 在不同 TZ 下跑 derive_edges → R4 日枢纽与边不同。
运行：cd $P/lingshu && python <本脚本>（需 PyYAML）"""
import json, os, subprocess, sys, tempfile
ROOT = os.getcwd()
EXP = os.path.join(ROOT, "tools", "coggraph", "export_coggraph.py")
DER = os.path.join(ROOT, "tools", "coggraph", "derive_edges.py")
assert os.path.isfile(EXP), "请在 lingshu 仓根运行"
d = tempfile.mkdtemp(prefix="r6i4_")

def mk(root, order):
    for b in order:
        p = os.path.join(root, "knowledge", b); os.makedirs(p)
        if b == "ccc":
            open(os.path.join(p, "c1.md"), "w", encoding="utf-8").write(
                "---\nid: c1\nlayer: knowledge\n---\n# 功能名：引用者节点\n正文提到 认知图导出器使用说明 。\n")
        else:
            open(os.path.join(p, b + "1.md"), "w", encoding="utf-8").write(
                "---\nid: %s1\nlayer: knowledge\n---\n# 功能名：认知图导出器使用说明\n" % b)

def run(*a, env=None):
    subprocess.run([sys.executable, "-X", "utf8"] + list(a), check=True, capture_output=True,
                   env=dict(os.environ, **(env or {})))

print("== ① 目录遍历顺序 ==")
res = {}
for name, order in (("w1", ["aaa", "bbb", "ccc"]), ("w2", ["ccc", "bbb", "aaa"])):
    src = os.path.join(d, name); out = os.path.join(d, "o" + name)
    mk(src, order)
    run(EXP, "--root", src, "--out", out, "--write")
    run(DER, "--graph", os.path.join(out, "graph.json"), "--out", out, "--bodies-root", src, "--write")
    g = json.load(open(os.path.join(out, "graph.json"), encoding="utf-8"))
    de = json.load(open(os.path.join(out, "derived_edges.json"), encoding="utf-8"))
    r5 = sorted((e["s"], e["t"]) for e in de["edges"] if e["rule"] == "R5_body_crossref")
    res[name] = (g["meta"]["source_sha"], [n["id"] for n in g["nodes"]], r5)
    print("%s 目录创建顺序=%s  os.walk 子目录顺序=%s" % (name, order,
          [os.path.basename(p) for p, _, _ in os.walk(os.path.join(src, "knowledge"))][1:]))
    print("   source_sha=%s nodes=%s" % res[name][:2])
    print("   R5 边=%s" % r5)
c1 = [t for s, t in res["w1"][2] if s == "c1"], [t for s, t in res["w2"][2] if s == "c1"]
bug1 = res["w1"][0] == res["w2"][0] and res["w1"][2] != res["w2"][2]
print("source_sha 相同=%s  R5 边集合不同=%s  c1 的提及目标：w1=%s w2=%s" %
      (res["w1"][0] == res["w2"][0], res["w1"][2] != res["w2"][2], c1[0], c1[1]))

print("== ② 时区 ==")
gpath = os.path.join(d, "tz_graph.json")
# a: 2026-10-08 20:00Z ; b: 2026-10-09 02:00Z
json.dump({"meta": {"source_sha": "x"}, "edges": [], "nodes": [
    {"id": "a", "title": "A", "layer": "knowledge", "bucket": "", "created": 1791489600, "tags": []},
    {"id": "b", "title": "B", "layer": "knowledge", "bucket": "", "created": 1791511200, "tags": []}]},
    open(gpath, "w", encoding="utf-8"))
outs = {}
for tz in ("UTC", "Asia/Shanghai", "America/Los_Angeles"):
    out = os.path.join(d, "tz_" + tz.replace("/", "_"))
    run(DER, "--graph", gpath, "--out", out, "--write", env={"TZ": tz})
    de = json.load(open(os.path.join(out, "derived_edges.json"), encoding="utf-8"))
    outs[tz] = (sorted(h["id"] for h in de["hubs"]), sorted((e["s"], e["t"]) for e in de["edges"]))
    print("TZ=%-20s hubs=%s edges=%s" % (tz, outs[tz][0], outs[tz][1]))
bug2 = len({json.dumps(v) for v in outs.values()}) > 1
print("同一 graph.json 跨时区产物不同=%s" % bug2)
print("VERDICT=%s" % ("BUG" if (bug1 or bug2) else "OK"))
```

## 代码定位
```
tools/coggraph/export_coggraph.py:111-111
    for dirpath, dirnames, filenames in os.walk(root):
```

## 修法
os.walk 里 dirnames.sort()、filenames 已排序（116 行）；分日枢纽统一用 UTC（或把 TZ 写进 source_sha 的输入）。
补一条「同一真源两次导出必须字节/边集合一致」的回归测试（含不同创建顺序的目录树）。

## 与已有 issue 的关系
#84（已关闭）修的是固定 --seed 时 R3 边仍随 PYTHONHASHSEED 变——那是集合/字典序轴；本条是文件系统目录序 + 本地时区轴，机制不同。#45 是 R4 日枢纽 count 虚增，与本条 TZ 轴相邻。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue4_coggraph_nondeterminism.py`：

```
== ① 目录遍历顺序 ==
w1 目录创建顺序=['aaa', 'bbb', 'ccc']  os.walk 子目录顺序=['ccc', 'bbb', 'aaa']
   source_sha=dc40697ac44b97b3 nodes=['aaa1', 'bbb1', 'c1']
   R5 边=[('bbb1', 'aaa1'), ('c1', 'aaa1')]
w2 目录创建顺序=['ccc', 'bbb', 'aaa']  os.walk 子目录顺序=['aaa', 'bbb', 'ccc']
   source_sha=dc40697ac44b97b3 nodes=['aaa1', 'bbb1', 'c1']
   R5 边=[('bbb1', 'aaa1'), ('c1', 'aaa1')]
source_sha 相同=True  R5 边集合不同=False  c1 的提及目标：w1=['aaa1'] w2=['aaa1']
== ② 时区 ==
TZ=UTC                  hubs=['day:2026-10-08', 'day:2026-10-09'] edges=[('a', 'day:2026-10-08'), ('b', 'day:2026-10-09')]
TZ=Asia/Shanghai        hubs=['day:2026-10-08', 'day:2026-10-09'] edges=[('a', 'day:2026-10-08'), ('b', 'day:2026-10-09')]
TZ=America/Los_Angeles  hubs=['day:2026-10-08', 'day:2026-10-09'] edges=[('a', 'day:2026-10-08'), ('b', 'day:2026-10-09')]
同一 graph.json 跨时区产物不同=False
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 同一真源两次导出（不同目录创建顺序、不同 TZ）推导边集合一致
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
