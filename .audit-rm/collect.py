"""rM 读回器：只读。req.json = {"issues":[...], "runs":[...]}。"""
import io, json, os, subprocess, sys, zipfile
out = os.path.abspath(sys.argv[1]); os.makedirs(out, exist_ok=True)
R = os.environ["GITHUB_REPOSITORY"]
req = json.load(open(".audit-rm/req.json", encoding="utf-8"))
def gh(path, raw=False):
    p = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path], capture_output=True)
    if p.returncode != 0:
        return None if raw else {"_error": p.stderr.decode("utf-8", "replace")[:500]}
    return p.stdout if raw else json.loads(p.stdout.decode("utf-8") or "null")
def pages(path):
    p = subprocess.run(["gh", "api", "--paginate", "--slurp", path], capture_output=True)
    if p.returncode != 0: return {"_error": p.stderr.decode()[:500]}
    flat = []
    for pg in json.loads(p.stdout.decode("utf-8")): flat += pg if isinstance(pg, list) else [pg]
    return flat
for n in req.get("issues", []):
    iss = gh(f"repos/{R}/issues/{n}")
    com = pages(f"repos/{R}/issues/{n}/comments?per_page=100")
    json.dump({"number": n, "state": iss.get("state"), "labels": [l["name"] for l in iss.get("labels", [])],
               "comments": [{"id": c["id"], "user": c["user"]["login"], "assoc": c.get("author_association"),
                             "created_at": c["created_at"], "len": len(c.get("body") or ""),
                             "head": (c.get("body") or "")[:300], "tail": (c.get("body") or "")[-400:]} for c in com]},
              open(f"{out}/issue-{n}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
idx = []
for rid in req.get("runs", []):
    r = gh(f"repos/{R}/actions/runs/{rid}")
    jobs = gh(f"repos/{R}/actions/runs/{rid}/jobs")
    row = {"id": rid, "event": r.get("event"), "title": r.get("display_title"), "status": r.get("status"),
           "conclusion": r.get("conclusion"), "created": r.get("created_at"), "updated": r.get("updated_at"),
           "jobs": [{"name": j["name"], "conclusion": j.get("conclusion"), "started": j.get("started_at"),
                     "completed": j.get("completed_at"), "steps": [(s["name"], s.get("conclusion")) for s in j.get("steps", [])]}
                    for j in (jobs or {}).get("jobs", [])]}
    z = gh(f"repos/{R}/actions/runs/{rid}/logs", raw=True)
    if z:
        zf = zipfile.ZipFile(io.BytesIO(z))
        txt = [f"===== {nm}\n" + zf.read(nm).decode("utf-8", "replace") for nm in sorted(zf.namelist()) if "/" in nm]
        open(f"{out}/run-{rid}.log", "w", encoding="utf-8").write("\n".join(txt))
    arts = gh(f"repos/{R}/actions/runs/{rid}/artifacts")
    row["artifacts"] = []
    for a in (arts or {}).get("artifacts", []):
        b = gh(f"repos/{R}/actions/artifacts/{a['id']}/zip", raw=True)
        if b:
            zf = zipfile.ZipFile(io.BytesIO(b))
            for nm in zf.namelist():
                open(f"{out}/run-{rid}__{nm}", "wb").write(zf.read(nm))
            row["artifacts"].append({"name": a["name"], "files": zf.namelist()})
    idx.append(row)
json.dump(idx, open(f"{out}/runs_index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
