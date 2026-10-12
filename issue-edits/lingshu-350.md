**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：run_rust_train 的 env 构造；最终定档以维护者为准）
**影响等级建议（补）**：B（需要调用方环境里设了 HEX_LR / RAYON_NUM_THREADS 才触发，子进程静默用错超参。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：run_rust_train 默认参数下子进程继承调用方环境变量。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
lingshu/nn/rust_bridge.py:120-129：只有 threads 或 lr != 0.1 时才构造 env = dict(os.environ) 并覆盖两个键；否则 env=None，子进程继承**整个**父环境（含 HEX_LR）。调用方设过 HEX_LR 时，Rust 后端的实际学习率与 Python 参考执行器不一致。

## 实测读数
```
父进程 HEX_LR=0.5 RAYON_NUM_THREADS=8：run_rust_train default(lr=0.1) → 子进程看到 HEX_LR=0.5 RAYON=8；lr=0.2 → HEX_LR=0.2 RAYON=8；lr=0.1,threads=1 → HEX_LR=0.1 RAYON=1。
导入后改 AEIS_HEX_NN，HEX_EXE 仍是旧值（True）。
exe 缺失时抛 FileNotFoundError，并在工作目录残留 data.bin 等中间文件。
```

## 最小复现
依赖：`.[full]` + 已编译的 `hex_nn` 可执行文件。注：脚本内联生成的子进程片段用了 `-c` 与 Windows 反斜杠路径，Windows 上会先触发 `SyntaxError: truncated \UXXXXXXXX escape`（脚本自身缺陷，非被测代码）；Linux 下正常。

### issue2_rust_bridge_env_leak.py
```python
# -*- coding: utf-8 -*-
"""复现：rust_bridge.run_rust_train 在 lr==0.1 且未给 threads 时 env=None，
子进程继承父进程的 HEX_LR / RAYON_NUM_THREADS——Rust 侧实际学习率≠Python 参考
执行器的 0.1；另：AEIS_HEX_NN 只在 import 时读一次，导入后再设无效；
exe 不存在时没有任何回退，且已先往 CWD/data/rust_bridge 写盘。
用一个假 hex_nn（记录收到的环境变量并写合法 out.bin）代替真实 Rust 二进制。
运行：cd $P/lingshu && python <本脚本>"""
import json, os, struct, subprocess, sys, tempfile, textwrap
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
fake = tmp / "fake_hex_nn"
fake.write_text("#!" + sys.executable + "\n" + textwrap.dedent('''
    import os, sys, struct, json
    mode, data, plan, vec, out = sys.argv[1:6]
    raw = open(plan, 'rb').read(); steps = struct.unpack('<Q', raw[8:16])[0]
    v = open(vec, 'rb').read()[16:]
    json.dump({"HEX_LR": os.environ.get("HEX_LR"),
               "RAYON_NUM_THREADS": os.environ.get("RAYON_NUM_THREADS")},
              open(os.path.join(os.path.dirname(out), 'seen_env.json'), 'w'))
    with open(out, 'wb') as f:
        f.write(struct.pack('<QQ', 0x4845584E4E4F5554, steps))
        f.write(struct.pack('<%dd' % steps, *([1.0] * steps)))
        f.write(v); f.write(struct.pack('<d', 0.0))
'''))
fake.chmod(0o755)

child = textwrap.dedent(f'''
    import json, numpy as np
    from pathlib import Path
    from lingshu.nn import rust_bridge as rb
    lat = np.zeros((4, 3, 3, 3)); oi = np.zeros(4, int); si = np.zeros(4, int)
    plan = rb.make_plan(4, 2, 2, 3, seed=1)
    vec0 = np.zeros(375)
    res = {{}}
    for name, kw in [("default(lr=0.1)", {{}}), ("lr=0.2", {{"lr": 0.2}}),
                     ("lr=0.1,threads=1", {{"threads": 1}})]:
        wd = Path("{tmp}") / name.replace("=", "_").replace(",", "_").replace("(", "").replace(")", "")
        rb.run_rust_train(lat, oi, si, vec0, plan, workdir=wd, **kw)
        res[name] = json.loads((wd / "seen_env.json").read_text())
    print(json.dumps(res, ensure_ascii=False))
''')
env = dict(os.environ, AEIS_HEX_NN=str(fake), HEX_LR="0.5", RAYON_NUM_THREADS="8")
out = subprocess.run([sys.executable, "-c", child], env=env, capture_output=True, text=True)
print("stderr:", out.stderr.strip()[-300:])
seen = json.loads(out.stdout.strip().splitlines()[-1])
print("父进程环境: HEX_LR=0.5 RAYON_NUM_THREADS=8")
for k, v in seen.items():
    print(f"  run_rust_train {k:<18} → 子进程看到 HEX_LR={v['HEX_LR']} RAYON={v['RAYON_NUM_THREADS']}")
leak = seen["default(lr=0.1)"]["HEX_LR"] == "0.5"

# B) AEIS_HEX_NN 导入后再设置无效
child2 = textwrap.dedent(f'''
    import os
    os.environ.pop("AEIS_HEX_NN", None)
    from lingshu.nn import rust_bridge as rb
    before = str(rb.HEX_EXE)
    os.environ["AEIS_HEX_NN"] = "{fake}"
    print(before == str(rb.HEX_EXE), repr(str(rb.HEX_EXE)))
''')
o2 = subprocess.run([sys.executable, "-c", child2], capture_output=True, text=True).stdout.strip()
print("B) 导入后设置 AEIS_HEX_NN，HEX_EXE 仍为旧值:", o2)
stale = o2.startswith("True")

# C) exe 缺失：无回退，且先在 CWD 写盘
cwd = Path(tempfile.mkdtemp())
child3 = textwrap.dedent('''
    import os, numpy as np
    os.environ.pop("AEIS_HEX_NN", None)
    from lingshu.nn import rust_bridge as rb
    lat = np.zeros((4, 3, 3, 3)); oi = np.zeros(4, int)
    try:
        rb.run_rust_train(lat, oi, oi, np.zeros(375), rb.make_plan(4, 2, 2, 3, 1))
    except Exception as e:
        print(type(e).__name__)
''')
env3 = {k: v for k, v in os.environ.items() if k != "AEIS_HEX_NN"}
env3["PYTHONPATH"] = os.getcwd()
o3 = subprocess.run([sys.executable, "-c", child3], cwd=cwd, env=env3,
                    capture_output=True, text=True)
left = sorted(p.name for p in (cwd / "data" / "rust_bridge").glob("*")) if (cwd / "data" / "rust_bridge").exists() else []
print("C) exe 缺失时异常:", o3.stdout.strip() or o3.stderr.strip()[-200:], "| 残留文件:", left)
print("VERDICT=" + ("BUG" if (leak or stale) else "OK"))
```

## 代码定位
```
lingshu/nn/rust_bridge.py:120-129
    env = None
    if threads or lr != 0.1:
        import os
        env = dict(os.environ)
        if threads:
            env["RAYON_NUM_THREADS"] = str(threads)
        env["HEX_LR"] = str(lr)
    subprocess.run([str(HEX_EXE), mode, str(wd / "data.bin"),
                    str(wd / "plan.bin"), str(wd / "vec.bin"),
                    str(wd / "out.bin")], check=True, env=env)
```

## 修法
给子进程传白名单环境（PATH 等最小集 + 显式 HEX_LR / RAYON_NUM_THREADS），不要 dict(os.environ) 全量透传。
AEIS_HEX_NN 改成每次调用时解析；中间文件用 tempfile.TemporaryDirectory。

## 与已有 issue 的关系
#227 报的是 world/brain_store._brain_env 复制 os.environ 把设计者密钥交给脑侧子进程（同类信任边界问题的另一处）；#294 是同一文件里 make_plan 参数写死。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

`python -X utf8 issue2_rust_bridge_env_leak.py`：

```
stderr:
父进程环境: HEX_LR=0.5 RAYON_NUM_THREADS=8
  run_rust_train default(lr=0.1)    → 子进程看到 HEX_LR=0.5 RAYON=8
  run_rust_train lr=0.2             → 子进程看到 HEX_LR=0.2 RAYON=8
  run_rust_train lr=0.1,threads=1   → 子进程看到 HEX_LR=0.1 RAYON=1
B) 导入后设置 AEIS_HEX_NN，HEX_EXE 仍为旧值: True 'hex_nn/target/release/hex_nn.exe'
C) exe 缺失时异常: FileNotFoundError | 残留文件: ['data.bin', 'plan.bin', 'vec.bin']
VERDICT=BUG
```
**仍复现**。本次读数：VERDICT=BUG，仍复现

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- 默认参数 `run_rust_train(lr=0.1)` 时子进程看到 HEX_LR=0.1，不受父进程 HEX_LR=0.5 影响
- 末行 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：影响等级和难度是自评；影响等级和难度以维护者定档为准。
