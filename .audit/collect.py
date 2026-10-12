"""读回器：把 bounty.yml 各 run 的日志 / artifact / 步骤结论，以及指定 issue 的评论与标签，落到 out/。
只读：用 GITHUB_TOKEN（actions: read, issues: read）。"""
import io, json, os, subprocess, sys, zipfile
out = os.path.abspath(sys.argv[1]); os.makedirs(out, exist_ok=True)
R = os.environ["GITHUB_REPOSITORY"]
req = json.load(open(".audit/collect_req.json", encoding="utf-8"))
def gh(path, raw=False, paginate=False):
    args = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate: args.insert(2, "--paginate")
    p = subprocess.run(args, capture_output=True)
    if p.returncode != 0:
        return {"_error": p.stderr.decode("utf-8", "replace")[:500]} if not raw else None
    return p.stdout if raw else json.loads(p.stdout.decode("utf-8") or "null")
def gh_pages(path):
    # --paginate 对数组会拼接成多个 JSON 数组，统一用 --slurp 逻辑
    p = subprocess.run(["gh", "api", "--paginate", "--slurp", path], capture_output=True)
    if p.returncode != 0: return {"_error": p.stderr.decode()[:500]}
    pages = json.loads(p.stdout.decode("utf-8"))
    flat = []
    for pg in pages:
        if isinstance(pg, list): flat += pg
        elif isinstance(pg, dict) and "workflow_runs" in pg: flat += pg["workflow_runs"]
        else: flat.append(pg)
    return flat
os.makedirs(f"{out}/issues", exist_ok=True)
for n in req.get("issues", []):
    iss = gh(f"repos/{R}/issues/{n}")
    com = gh_pages(f"repos/{R}/issues/{n}/comments?per_page=100")
    slim = [{"id": c.get("id"), "user": (c.get("user") or {}).get("login"), "assoc": c.get("author_association"),
             "created_at": c.get("created_at"), "body": c.get("body")} for c in (com if isinstance(com, list) else [])]
    json.dump({"number": n, "state": iss.get("state"), "title": iss.get("title"),
               "labels": [l["name"] for l in iss.get("labels", [])], "comments_count": len(slim),
               "comments": slim}, open(f"{out}/issues/{n}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
since = req.get("since", "")
wfs = req.get("workflows", ["bounty.yml"])
os.makedirs(f"{out}/runs", exist_ok=True)
index = []
for wf in wfs:
    q = f"repos/{R}/actions/workflows/{wf}/runs?per_page=100" + (f"&created=%3E%3D{since}" if since else "")
    runs = gh_pages(q)
    if isinstance(runs, dict): runs = []
    for r in runs:
        rid = r["id"]
        jobs = gh(f"repos/{R}/actions/runs/{rid}/jobs")
        steps = []
        for j in (jobs.get("jobs") or []) if isinstance(jobs, dict) else []:
            steps.append({"job": j["name"], "conclusion": j.get("conclusion"), "started": j.get("started_at"),
                          "completed": j.get("completed_at"),
                          "steps": [(s["name"], s.get("conclusion")) for s in j.get("steps", [])]})
        row = {"id": rid, "wf": wf, "event": r["event"], "title": r.get("display_title"),
               "status": r["status"], "conclusion": r.get("conclusion"), "created": r["created_at"],
               "run_started": r.get("run_started_at"), "updated": r.get("updated_at"),
               "head_branch": r.get("head_branch"), "jobs": steps}
        if req.get("logs", True) and r["status"] == "completed":
            z = gh(f"repos/{R}/actions/runs/{rid}/logs", raw=True)
            if z:
                try:
                    zf = zipfile.ZipFile(io.BytesIO(z)); txt = []
                    for name in sorted(zf.namelist()):
                        if name.count("/") == 0 and name.endswith(".txt"):
                            continue  # 顶层是整 job 合并日志，与分步重复
                        txt.append(f"===== {name}\n" + zf.read(name).decode("utf-8", "replace"))
                    if not txt:
                        txt = [f"===== {n}\n" + zf.read(n).decode("utf-8", "replace") for n in zf.namelist()]
                    open(f"{out}/runs/{rid}.log", "w", encoding="utf-8").write("\n".join(txt))
                except Exception as e:
                    row["log_error"] = str(e)
            arts = gh(f"repos/{R}/actions/runs/{rid}/artifacts")
            row["artifacts"] = []
            for a in (arts.get("artifacts") or []) if isinstance(arts, dict) else []:
                b = gh(f"repos/{R}/actions/artifacts/{a['id']}/zip", raw=True)
                ent = {"name": a["name"], "size": a["size_in_bytes"]}
                if b:
                    zf = zipfile.ZipFile(io.BytesIO(b))
                    for nm in zf.namelist():
                        open(f"{out}/runs/{rid}__{nm}", "wb").write(zf.read(nm)); ent.setdefault("files", []).append(nm)
                row["artifacts"].append(ent)
        index.append(row)
json.dump(index, open(f"{out}/runs_index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(gh("rate_limit"), open(f"{out}/rate_limit.json", "w"), indent=1)
print("issues", len(req.get("issues", [])), "runs", len(index))
