**项目归属（补）**：`project:memory`（lingshu 的提交在评估表里按 #6、#8 的先例归 memory；如维护者另有 lingshu 归属请改） · **难度自申请（补）**：easy（单点：gate.yml 一行 deselect 与 README 一处标注；最终定档以维护者为准）
**影响等级建议（补）**：C（CI 配置与 README 陈化：门禁对一条已转绿的用例失明，不影响运行结果。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：已修复的用例仍被门禁排除，回归保护是关着的。

**基线**：`83cce59`（main HEAD；原审计 `e18562f`）· Python 3.14.3 / Windows 11（原审计 Python 3.12.15 / Linux）· 隔离临时目录；仓库只读复核，未改动任何文件

## 现象
54cb5cb（采纳 #70，hex_hier 形状辅助损失改连续分组）已让该判据转绿，但合入时没同步摘掉 gate.yml 的 --deselect 与 README / docs/intake/body-export-v0.2/README.md §五 的已知红标注。

## 实测读数
```
跑 python -X utf8 -m pytest tests/test_hex_text.py -v（e18562f）：test_multimodal_check_clean_vs_corrupt **PASSED**；同文件的 test_spatial_detect_finds_single_object FAILED（6/16，仍红）。
在 83cce59（HEAD）上再跑：**两条都 PASSED（6 passed）**。
而 gate.yml:143-155 仍以「7/12 < 阈值」把它写进 known-fail 并 --deselect，README.md:58-61 仍列它为「已知红…在全部版本组合下逐位一致」。
二分：54cb5cb^ FAILED → 54cb5cb passed，指向采纳 PR #70 的那次改动。
```

## 最小复现
依赖：pytest。在仓库根目录执行（先用 pytest 跑 tests/test_hex_text.py 复现绿/红差异，再用本脚本二分定位引入点）。

### bisect_multimodal.sh
```bash
#!/usr/bin/env bash
# 在 54cb5cb^ 与 54cb5cb 两个 worktree 上各跑一次 test_multimodal_check_clean_vs_corrupt（各约 60s）
# 用法：在 lingshu 仓库根运行：bash <本脚本>   需要已装 numpy/Pillow/pytest 的 python（PY 环境变量可覆盖）
set -u; PY=${PY:-python}
git worktree add -q /tmp/ls-a 54cb5cb^ 2>/dev/null; git worktree add -q /tmp/ls-b 54cb5cb 2>/dev/null
for w in a b; do (cd /tmp/ls-$w && PYTHONPATH=/tmp/ls-$w $PY -m pytest tests/test_hex_text.py -q -p no:cacheprovider -k multimodal_check 2>&1 | grep -E 'passed|failed|E  ' | sed "s/^/$w: /"); done
```

## 代码定位
```
.github/workflows/gate.yml:145-157
        #   · tests/test_hex_text.py::test_spatial_detect_finds_single_object    （6/16 < 0.6 阈值）
        #   · tests/test_hex_text.py::test_multimodal_check_clean_vs_corrupt      （7/12 < 阈值）
        # 全部 numpy/Pillow 版本组合下读数**逐位一致** ⇒ 与依赖版本无关，上游同跑同红。
        # 处置：**显式 deselect**（不改任何断言）。待上游修复后，同处摘除本条并与 README 同步。
        run: |
          set -euo pipefail
          pytest_args=(tests/ -v)
          for t in $SCRIPT_TESTS; do
            pytest_args+=(--ignore="$t")
          done
          python -X utf8 -m pytest "${pytest_args[@]}" \
            --deselect tests/test_hex_text.py::test_spatial_detect_finds_single_object \
            --deselect tests/test_hex_text.py::test_multimodal_check_clean_vs_corrupt

README.md:58-61
> 已知红（如实标注）：`tests/test_hex_text.py` 两处断言（`test_spatial_detect_finds_single_object`
> = 6/16、`test_multimodal_check_clean_vs_corrupt` = 7/12，均低于阈值）在上述**全部版本组合**下
> 读数**逐位一致**——**与 numpy / Pillow 版本无关**，上游同跑读数相同。详见
> [issue #4](https://github.com/FuRongJun-1999/lingshu/issues/4)。
```

## 修法
从 gate.yml 删掉这一条 --deselect，已知红只保留 test_spatial_detect_finds_single_object。
更稳的做法是改用 pytest.mark.xfail(strict=True)：一旦意外转绿就 XPASS 报错，陈化会被自动发现。

## 与已有 issue 的关系
#24 报的是这两条判据在任何环境下都不可复算（2 failed）、#87 提出用 strict xfail 托住。本条不重复那两条结论，只补**状态已变**这一硬事实：其中一条（HEAD 上两条）已经绿了仍在被 deselect。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`cb3a6ea`（lingshu main 最新，2026-10-11 22:25 +0800）· Debian 13 / Linux 6.12 · Python 3.12.15 · numpy 2.5.3 · Pillow 12.3.0 · PyYAML 6.0.3 · 在仓根运行、`PYTHONPATH` 指向该克隆，脚本只写临时目录。

静态核对（未跑 pytest）：

```
$ grep -n deselect .github/workflows/gate.yml
22:#     （曾 deselect 两条 known-fail，已随 `9bc4985` 转绿而摘除——见下「pytest 式测试」步。）
170:        # 曾 deselect 的两条 known-fail（README「代码主体」节 / issue #4）**已转绿并摘除 deselect**：
178:        # 两条现**随 tests/ 自动收集真跑**（不再 deselect）。判据来源＝经验标定（上述实跑读数）。
179:        # 守卫 `tests/test_gate_deselect_justified.py` 断言「凡被 deselect 的用例必须真红」——
180:        #   再想 deselect 一条已转绿的用例会当场判红（静默关掉回归保护即本件要防的缺陷）。
196:            echo "- pytest 式：tests/ 自动收集（排除上述脚本式测试；无 deselect——曾登记的两条 known-fail 已转绿）"
$ git rev-parse --short HEAD
cb3a6ea
$ grep -n '已知红' README.md
58:> 曾登记为「已知红」的 `tests/test_hex_text.py` 两处断言（`test_spatial_detect_finds_single_object`
```

**主现象在 `cb3a6ea` 上已不复现**，应是上游已修（本 issue 仍为 open）。本条保留作记录，建议请维护者确认修复提交后关闭。本次读数：gate.yml 已无该 deselect，README 改为「曾登记为已知红」（静态核对 cb3a6ea，未跑 pytest）

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- `gate.yml` 不再 deselect `test_multimodal_check_clean_vs_corrupt`，该用例随 tests/ 真跑并通过
- README 不再把它列为已知红

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红——注：本条在 cb3a6ea 上已经转绿，守卫应直接绿），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `e18562f`（Linux，Python 3.12.15）；提交时 main HEAD `83cce59`（Windows 11，Python 3.14.3）；本次 `cb3a6ea`（Linux，Python 3.12.15）读数见上一节。
**未验**：没有写补丁，修法未经测试；没有跑上游 pytest 全量；没有在 macOS 上跑。
**不确定**：`cb3a6ea` 上脚本已转绿，但没有逐一找到对应的修复提交（上游批量修复提交 c22385c / df6e629 / abb52d0 / 777e18f 的说明里不一定写 issue 号）；影响等级和难度以维护者定档为准。
