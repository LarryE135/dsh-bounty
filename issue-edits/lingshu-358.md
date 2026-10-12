**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：export 阶段 id 检测；最终定档以维护者为准）
**影响等级建议（补）**：B（需要两个文件写同一 front matter id 才触发，查看器显示错位。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：export_coggraph 不检测重复节点 id。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
tools/coggraph/export_coggraph.py:136 一带按出现顺序输出节点、不检查 id 唯一性；build_viewer.py:292-301 的 BY_ID 用字典直接覆盖，双方对「同 id」的取舍不一致。

## 实测读数
```
export 退出码 0，stdout 有无「重复/冲突」告警：False。
graph.json counts.nodes=2，去重后 id 数=1，id 计数={'note-1': 2}；viewer_graph.json 里 note-1×2，边为 [('note-1','bucket:aaa'), ('note-1','bucket:bbb')]。
serve.py 的 BY_ID['note-1'] 只剩 title=笔记甲 bucket=aaa（另一条不可达）。
cytoscape 3.30.2（headless）：传入 4 节点实建 3；note-1 显示为「笔记乙」，却连到 ['bucket:bbb','bucket:aaa']。
```

## 最小复现
依赖：纯标准库；脚本末段会用 node + cytoscape（headless）复核查看器行为，没有 node 时该段跳过、前段读数照常。

### issue6_export_duplicate_id.py
```python
# -*- coding: utf-8 -*-
"""export_coggraph 不检测重复 id：两个文件写同一 front matter id → graph.json 出现两条同 id 节点、
counts.nodes 与去重 id 数不一致；build_viewer 照写；cytoscape 静默丢掉其中一个，
另一个继承两份边（被挂到两个桶）；serve.py 的 BY_ID 只保留最后一个。
运行：cd $P/lingshu && python <本脚本>（需 PyYAML；cytoscape 检查需 node+npm 包，可选）"""
import collections, json, os, shutil, subprocess, sys, tempfile
ROOT = os.getcwd()
T = lambda n: os.path.join(ROOT, "tools", "coggraph", n)
assert os.path.isfile(T("build_viewer.py")), "请在 lingshu 仓根运行"
d = tempfile.mkdtemp(prefix="r6i6_")
src = os.path.join(d, "mdcg"); out = os.path.join(d, "out")
for b, t in (("aaa", "笔记甲"), ("bbb", "笔记乙")):
    p = os.path.join(src, "knowledge", b); os.makedirs(p)
    open(os.path.join(p, "note.md"), "w", encoding="utf-8").write(
        "---\nid: note-1\nlayer: knowledge\n---\n# 功能名：%s\n%s 的正文\n" % (t, t))
os.makedirs(out)
# 避免联网下载：放一个 >100KB 的占位 cytoscape.min.js（真实库若在 /tmp/cy 则用真库）
real = "/tmp/cy/node_modules/cytoscape/dist/cytoscape.min.js"
if os.path.isfile(real): shutil.copy(real, out)
else: open(os.path.join(out, "cytoscape.min.js"), "w").write("//" + "x" * 200000)
def run(*a):
    return subprocess.run([sys.executable, "-X", "utf8"] + list(a), check=True, capture_output=True,
                          text=True, encoding="utf-8")
r = run(T("export_coggraph.py"), "--root", src, "--out", out, "--write")
g = json.load(open(os.path.join(out, "graph.json"), encoding="utf-8"))
print("export 退出码 0，stdout 有无『重复/冲突』告警：", ("重复" in r.stdout or "冲突" in r.stdout))
print("graph.json counts.nodes=%d，去重 id 数=%d，id 计数=%s" % (
    g["meta"]["counts"]["nodes"], len({n["id"] for n in g["nodes"]}), dict(collections.Counter(n["id"] for n in g["nodes"]))))
run(T("derive_edges.py"), "--graph", os.path.join(out, "graph.json"), "--out", out, "--write")
run(T("build_viewer.py"), "--graph", os.path.join(out, "graph.json"),
    "--derived", os.path.join(out, "derived_edges.json"), "--out", out)
v = json.load(open(os.path.join(out, "viewer_graph.json"), encoding="utf-8"))
ids = collections.Counter(n["id"] for n in v["nodes"])
edges_note = sorted((e["s"], e["t"]) for e in v["edges"] if "note-1" in (e["s"], e["t"]))
print("viewer_graph.json 同 id 节点数：note-1×%d；note-1 的边：%s" % (ids["note-1"], edges_note))
by_id = {n["id"]: n for n in v["nodes"]}   # 与 viewer_serve.tmpl:23 同款
print("serve.py BY_ID['note-1'] 只剩：title=%s bucket=%s（另一条不可达）" % (by_id["note-1"]["title"], by_id["note-1"]["bucket"]))
cy = None
if shutil.which("node") and os.path.isdir("/tmp/cy/node_modules/cytoscape"):
    js = ("const cytoscape=require('/tmp/cy/node_modules/cytoscape');const G=require(%r);"
          "const els=[];for(const n of G.nodes)els.push({data:{id:n.id,label:n.title}});"
          "for(const e of G.edges)els.push({data:{id:e.s+'|'+e.t+'|'+e.type+'|'+(e.derived?1:0),source:e.s,target:e.t}});"
          "const cy=cytoscape({headless:true,elements:els});"
          "console.log(JSON.stringify({passed:G.nodes.length,kept:cy.nodes().length,"
          "note:cy.getElementById('note-1').data('label'),deg:cy.getElementById('note-1').connectedEdges().map(e=>e.target().id())}))"
          % os.path.join(out, "viewer_graph.json"))
    cy = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True).stdout)
    print("cytoscape 3.30.2（headless）：传入 %d 节点，实建 %d；note-1 显示为『%s』，连到 %s" % (
        cy["passed"], cy["kept"], cy["note"], cy["deg"]))
else:
    print("（未找到 node/cytoscape，跳过前端核对）")
bug = g["meta"]["counts"]["nodes"] != len({n["id"] for n in g["nodes"]}) and ids["note-1"] == 2
print("VERDICT=%s" % ("BUG" if bug else "OK"))
```

## 代码定位
```
tools/coggraph/export_coggraph.py:136-136
            nid = fm.get("id") or os.path.splitext(fn)[0]

tools/coggraph/build_viewer.py:292-301
    vnodes = []
    for n in g["nodes"]:
        if n["id"] in alias_to_canon:
            continue
        vnodes.append({"id": n["id"], "layer": n["layer"], "title": n["title"],
                       "bucket": n.get("bucket", ""), "tags": n.get("tags", []),
                       "importance": n.get("importance", 0), "degree": deg.get(n["id"], 0),
                       "path": n.get("path", ""),
                       "ncls": title2cls.get((n.get("title") or "").strip(), ""),
                       "hub": n["id"] in hub_ids})
```

## 修法
导出阶段检测重复 id：报错退出（或按来源路径加后缀保证唯一），并在 counts 里显式给出 raw_nodes / unique_ids。
查看器侧做同样校验并在 UI 上标注冲突。

## 与已有 issue 的关系
#290 / #291 / #298 是同一文件对畸形 frontmatter、标量 doc_ref、derived_from 的处理缺陷，属 export_coggraph 的相邻问题族。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue6_export_duplicate_id.py`：

```
export 退出码 0，stdout 有无『重复/冲突』告警： False
graph.json counts.nodes=2，去重 id 数=2，id 计数={'note-1': 1, 'note-1#e516124bfc04': 1}
Traceback (most recent call last):
  File "<包>/repro/r6-tools-ci/issue6_export_duplicate_id.py", line 30, in <module>
    run(T("build_viewer.py"), "--graph", os.path.join(out, "graph.json"),
  File "<包>/repro/r6-tools-ci/issue6_export_duplicate_id.py", line 22, in run
    return subprocess.run([sys.executable, "-X", "utf8"] + list(a), check=True, capture_output=True,
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/subprocess.py", line 571, in run
    raise CalledProcessError(retcode, process.args,
subprocess.CalledProcessError: Command '['<python>', '-X', 'utf8', '<仓根>/tools/coggraph/build_viewer.py', '--graph', '/tmp/r6i6_mdxvqmpp/out/graph.json', '--derived', '/tmp/r6i6_mdxvqmpp/out/derived_edges.json', '--out', '/tmp/r6i6_mdxvqmpp/out']' returned non-zero exit status 1.
```
**部分已修**。本次读数：主现象已修：重复 id 被改名为 `note-1#e516124bfc04`，counts 与去重 id 数一致；脚本后半段因上游新增 cytoscape.min.js sha256 校验、占位文件被拒而中止（脚本过时，不是新缺陷）；另有 segujushi-lang 2026-10-11 在本 issue 下报了三份同 id 的残余边界

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 重复 id 被报错或改名保证唯一，counts 与去重 id 数一致
- 查看器里两份笔记各自可点开、正文不串

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：上一节写的部分修复是本次读数，没有核对上游是否还有后续计划；影响等级和难度以维护者定档为准。
