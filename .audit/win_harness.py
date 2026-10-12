"""Windows/Ubuntu 对照 harness：逐条运行守卫与生成器，记录 rc / 耗时 / 输出（不改仓）。"""
import json, os, platform, subprocess, sys, time, locale, shutil, hashlib, tempfile
out = os.path.abspath(sys.argv[1]); os.makedirs(out, exist_ok=True)
repo = os.getcwd()
def sh(args, cwd=None):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    except Exception as e:
        return f"ERR {e}"
def crlf_count(p):
    b = open(p, "rb").read(); return b.count(b"\r\n"), b.count(b"\n")
env_info = {
  "platform": platform.platform(), "python": sys.version, "executable": sys.executable,
  "preferred_encoding": locale.getpreferredencoding(False),
  "fs_encoding": sys.getfilesystemencoding(),
  "git_autocrlf": sh(["git", "config", "--get", "core.autocrlf"]),
  "git_autocrlf_show": sh(["git", "config", "--show-origin", "--get-all", "core.autocrlf"]),
  "head": sh(["git", "rev-parse", "HEAD"]),
  "crlf_scripts_bounty_board": crlf_count("scripts/bounty_board.py"),
  "crlf_tests_test_bounty_board": crlf_count("tests/test_bounty_board.py"),
  "crlf_site_index": crlf_count("site/index.html"),
}
CMDS = [
  ("test_bounty_board", ["tests/test_bounty_board.py"]),
  ("test_bounty_board_mutate", ["tests/test_bounty_board.py", "--mutate"]),
  ("test_build_site", ["tests/test_build_site.py"]),
  ("test_build_site_mutate", ["tests/test_build_site.py", "--mutate"]),
  ("build_site_print", ["scripts/build_site.py", "--print"]),
  ("bounty_dry_run", ["scripts/bounty_board.py", "--dry-run"]),
]
def clean_env():
    e = dict(os.environ)
    for k in ("PYTHONUTF8", "PYTHONIOENCODING"): e.pop(k, None)
    return e
def run_set(tag, cwd, flags):
    res = []
    for name, argv in CMDS:
        t = time.time()
        try:
            p = subprocess.run([sys.executable, *flags, *argv], cwd=cwd, env=clean_env(),
                               capture_output=True, timeout=420)
            rc, so, se = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired as ex:
            rc, so, se = "TIMEOUT", ex.stdout or b"", ex.stderr or b""
        dt = round(time.time() - t, 1)
        txt = so.decode("utf-8", "replace"); err = se.decode("utf-8", "replace")
        with open(os.path.join(out, f"{tag}__{name}.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"# cmd: python {' '.join(flags + argv)}  (cwd={tag})\n# rc={rc} secs={dt}\n")
            fh.write("## stdout\n" + txt.replace("\r\n", "\n") + "\n## stderr\n" + err.replace("\r\n", "\n"))
        last = [l for l in txt.replace("\r\n","\n").splitlines() if l.strip()][-1:] or [""]
        res.append({"set": tag, "name": name, "rc": rc, "secs": dt,
                    "stdout_sha1": hashlib.sha1(so.replace(b"\r\n", b"\n")).hexdigest()[:12],
                    "stdout_lines": txt.count("\n"), "stderr_tail": err.strip().splitlines()[-1:] ,
                    "stdout_last": last[0][:200]})
        print(tag, name, rc, dt, flush=True)
    return res
results = []
results += run_set("utf8", repo, ["-X", "utf8"])
results += run_set("bare", repo, [])
# LF 副本（只在检出为 CRLF 时有意义）：把文本文件换回 LF 再跑一遍，分离「换行」与「其他 Windows 因素」
if env_info["crlf_scripts_bounty_board"][0] > 0:
    lf = os.path.join(tempfile.gettempdir(), "lfcopy")
    shutil.copytree(repo, lf, ignore=shutil.ignore_patterns(".git"))
    for root, _d, files in os.walk(lf):
        for f in files:
            if f.endswith((".py", ".md", ".html", ".json", ".yml", ".txt")):
                p = os.path.join(root, f); b = open(p, "rb").read()
                open(p, "wb").write(b.replace(b"\r\n", b"\n"))
    results += run_set("lfcopy_utf8", lf, ["-X", "utf8"])
# 生成站点到临时目录，与仓内 site/ 逐字节对比（原样 / 去 CR 后）
tmpd = tempfile.mkdtemp(prefix="site_")
p = subprocess.run([sys.executable, "-X", "utf8", "scripts/build_site.py", "--out", tmpd],
                   env=clean_env(), capture_output=True)
cmp = {"rc": p.returncode, "stdout": p.stdout.decode("utf-8","replace")[-300:], "files": {}}
for n in sorted(os.listdir(tmpd)):
    a = open(os.path.join(tmpd, n), "rb").read()
    bp = os.path.join("site", n)
    b = open(bp, "rb").read() if os.path.exists(bp) else b""
    cmp["files"][n] = {"gen_crlf": a.count(b"\r\n"), "repo_crlf": b.count(b"\r\n"),
                       "equal_raw": a == b, "equal_lf": a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")}
env_info["git_status_after"] = sh(["git", "status", "--porcelain"])
json.dump({"env": env_info, "results": results, "site_compare": cmp},
          open(os.path.join(out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(env_info, ensure_ascii=False, indent=1))
