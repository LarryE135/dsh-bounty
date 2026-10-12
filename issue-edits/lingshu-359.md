**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：medium（要读 derive_edges 的 R1/R5 与 naming_report 的 Q1/Q3；最终定档以维护者为准）
**影响等级建议（补）**：A（naming_report 的 alias 候选档在真实管线中不可达，报告结论失效（量具失效）。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：naming_report 的 alias 候选档在真实管线里永远到不了。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
derive_edges.py:150-153 / 289-306：Q1 的「稳定概念」判据把 R1 桶枢纽这种结构性推导边计入连接；Q3 的正文互引又把节点自己的标题行（同名文本）当正文，于是 alias 候选在真实数据里永远不成立。

## 实测读数
```
A_无bodies_root（仅 R1）：显式边=0、推导边=[('ccc-n','bucket:ccc','R1_same_bucket'), ('bbb-n','bucket:bbb',...), ('aaa-n','bucket:aaa',...)]，naming 行 n=3 q1=True q2=True q3=True → 判为「已锚定」。
B_view_memory 同款（带 bodies_root）：推导边出现 ('bbb-n','ccc-n','R5_body_crossref')、('aaa-n','ccc-n','R5_body_crossref')，已锚定判定被结构性边撑起来。
```

## 最小复现
依赖：纯标准库。

### issue5_naming_alias_unreachable.py
```python
# -*- coding: utf-8 -*-
"""真实管线（export→derive_edges→naming_report）下「alias候选」不可达：
① naming_report 的 Q1 用 deg 计入所有推导边，R1 桶枢纽边让任何分桶节点 q1=True；
② derive_edges R5 把同名节点自己的「# 功能名：<标题>」标题行当正文提及，同名节点互连 body_crossref。
夹具：3 个同名、无任何显式边、无任何正文互引的节点（文档语义 = 「同一概念被切碎」→ alias候选）。
运行：cd $P/lingshu && python <本脚本>（需 PyYAML）"""
import json, os, subprocess, sys, tempfile
ROOT = os.getcwd()
T = lambda n: os.path.join(ROOT, "tools", "coggraph", n)
assert os.path.isfile(T("naming_report.py")), "请在 lingshu 仓根运行"
d = tempfile.mkdtemp(prefix="r6i5_")
src = os.path.join(d, "mdcg")
for b in ("aaa", "bbb", "ccc"):
    p = os.path.join(src, "knowledge", b); os.makedirs(p)
    open(os.path.join(p, "n.md"), "w", encoding="utf-8").write(
        "---\nid: %s-n\nlayer: knowledge\n---\n# 功能名：重复切碎的概念名\n只有这一行正文。\n" % b)
def run(*a):
    subprocess.run([sys.executable, "-X", "utf8"] + list(a), check=True, capture_output=True)
def pipeline(tag, bodies):
    out = os.path.join(d, tag)
    run(T("export_coggraph.py"), "--root", src, "--out", out, "--write")
    extra = ["--bodies-root", src] if bodies else []
    run(T("derive_edges.py"), "--graph", os.path.join(out, "graph.json"), "--out", out, "--write", *extra)
    run(T("naming_report.py"), "--graph", os.path.join(out, "graph.json"),
        "--derived", os.path.join(out, "derived_edges.json"), "--out", out, "--write")
    g = json.load(open(os.path.join(out, "graph.json"), encoding="utf-8"))
    de = json.load(open(os.path.join(out, "derived_edges.json"), encoding="utf-8"))
    row = json.load(open(os.path.join(out, "naming_report.json"), encoding="utf-8"))["rows"][0]
    print("[%s] 显式边=%d 推导边=%s" % (tag, len(g["edges"]), [(e["s"], e["t"], e["rule"]) for e in de["edges"]]))
    print("   naming 行：n=%d q1=%s q2=%s q3=%s → %s" % (row["n"], row["q1"], row["q2"], row["q3"], row["class"]))
    return row, de
row_a, _ = pipeline("A_无bodies_root（仅R1）", False)
row_b, de_b = pipeline("B_view_memory同款（带bodies_root）", True)
r5_same_title = [e for e in de_b["edges"] if e["rule"] == "R5_body_crossref"]
bug = row_a["class"] != "alias候选" and row_a["q1"] and bool(r5_same_title)
print("期望 alias候选；A 实得 %s，B 实得 %s；B 中同名节点间 R5 边 %d 条（正文里并无对方标题之外的提及）"
      % (row_a["class"], row_b["class"], len(r5_same_title)))
print("VERDICT=%s" % ("BUG" if bug else "OK"))
```

## 代码定位
```
tools/coggraph/derive_edges.py:150-153
    for b, ids in by_bucket.items():
        hid = hub("bucket:" + b, "bucket", "桶 " + b, len(ids))
        for nid in ids:
            if add(nid, hid, "in_bucket", "R1_same_bucket", 0.4):
```

## 修法
Q1 排除结构性推导边（R1/R5 之类），只认显式边与人工锚定；Q3 的正文统计排除节点标题行本身。
补测试：只有结构性边的图上，naming_report 必须报「未锚定」并给出 alias 候选。

## 与已有 issue 的关系
#100 / #102 是 naming_report Q2/Q3 把「提及者」也算进去的问题，#315 是 Q4 的规范标识正则形同虚设——本条是 Q1/Q3 的同一判据族。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue5_naming_alias_unreachable.py`：

```
[A_无bodies_root（仅R1）] 显式边=0 推导边=[('aaa-n', 'bucket:aaa', 'R1_same_bucket'), ('bbb-n', 'bucket:bbb', 'R1_same_bucket'), ('ccc-n', 'bucket:ccc', 'R1_same_bucket')]
   naming 行：n=3 q1=False q2=True q3=True → alias候选
[B_view_memory同款（带bodies_root）] 显式边=0 推导边=[('bbb-n', 'aaa-n', 'R5_body_crossref'), ('ccc-n', 'aaa-n', 'R5_body_crossref'), ('aaa-n', 'bucket:aaa', 'R1_same_bucket'), ('bbb-n', 'bucket:bbb', 'R1_same_bucket'), ('ccc-n', 'bucket:ccc', 'R1_same_bucket')]
   naming 行：n=3 q1=False q2=True q3=True → alias候选
期望 alias候选；A 实得 alias候选，B 实得 alias候选；B 中同名节点间 R5 边 2 条（正文里并无对方标题之外的提及）
VERDICT=OK
```
**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：VERDICT=OK

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 只有结构性边的图上，A/B 两种管线都报 alias 候选
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
