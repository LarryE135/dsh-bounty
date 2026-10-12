**项目归属（补）**：`project:bounty_site` · **难度自申请（补）**：easy（单点：只涉及 `_do_verify` 里判定词解析的几行；最终定档以维护者为准）
**影响等级建议（补）**：A（维护者按中文习惯写「不通过」或 `fail，` 就会被静默判通过，默认配置可触发，验收语义错误。按《价值评价规格 v0.1》§四「不做会怎样」判）
**意图（补）**：让维护者知道：/verify 不认识的判定词会被默认当成「通过」。

**基线**：`1e75766`（审计基准，2026-10-11）· 当前 HEAD `af41c07` 上仍复现 · Python 3.14.3 / Windows 11（原审计 Python 3.12 / Linux）· 纯逻辑层

## 现象
`/verify` 的判定词只要不是 pass/fail/partial，一律按「通过」处理：维护者写 `failed`、`fail:`、`fail，`、`不通过`、`reject`、`no`，都会被判 verified

## 实测读数
本机实跑（`repro/rA-statemachine/a2_verify_default_pass.py`）：

```
'/verify fail 读数不可复跑'                → claimed   验收不通过：读数不可复跑
  '/verify FAIL 读数不可复跑'                → claimed   验收不通过：读数不可复跑
  '/verify failed 读数不可复跑'              → verified  验收通过：failed 读数不可复跑  ← 意图为不通过却判通过
  '/verify fail: 读数不可复跑'               → verified  验收通过：fail: 读数不可复跑  ← 意图为不通过却判通过
  '/verify fail，读数不可复跑'                → verified  验收通过：fail，读数不可复跑  ← 意图为不通过却判通过
  '/verify 不通过 读数不可复跑'                 → verified  验收通过：不通过 读数不可复跑  ← 意图为不通过却判通过
  '/verify reject 读数不可复跑'              → verified  验收通过：reject 读数不可复跑  ← 意图为不通过却判通过
  '/verify no'                         → verified  验收通过：no  ← 意图为不通过却判通过
  '/verify'                            → verified  验收通过：（未写理由）
意图不通过却进入 verified 的写法数: 6
VERDICT=BUG
```

## 最小复现
依赖：纯标准库。设 `DSH_BOUNTY_REPO` 指向本仓克隆，在脚本目录下 `python -X utf8 a2_verify_default_pass.py`；只读导入上游、不写仓库文件、不触网。

### a2_verify_default_pass.py
```python
# -*- coding: utf-8 -*-
"""A2-1：/verify 判定词不在 {pass,fail,partial} 时一律按 pass 处理——维护者写「不通过」「failed」「fail:」都会被判通过。"""
from _common import bb, CFG, at, MAINT

def delivered():
    return bb.IssueState(number=1, labels=("bounty", "bounty:delivered", "difficulty:hard"), has_bounty=True,
                         state="delivered", holder="alice", due_at=None, rounds=1, seq=2)

cases = ["/verify fail 读数不可复跑", "/verify FAIL 读数不可复跑",
         "/verify failed 读数不可复跑", "/verify fail: 读数不可复跑", "/verify fail，读数不可复跑",
         "/verify 不通过 读数不可复跑", "/verify reject 读数不可复跑", "/verify no", "/verify"]
wrong = 0
for body in cases:
    cmd, payload = bb.parse_command(body)
    d = bb.handle_command(delivered(), cmd, payload, body, MAINT, at(1), CFG, is_maintainer=True)
    intended_fail = body != "/verify"
    flag = "  ← 意图为不通过却判通过" if intended_fail and d.to_state == "verified" and not body.lower().startswith("/verify fail ") else ""
    wrong += bool(flag)
    print(f"  {body!r:<36} → {d.to_state:<9} {d.reason}{flag}")
print("意图不通过却进入 verified 的写法数:", wrong)
print("VERDICT=BUG" if wrong >= 5 else "VERDICT=OK")
```

## 代码定位
`scripts/bounty_board.py:791-796`：`head.lower() in ("pass","fail","partial")` 不成立时走 `else: verdict, reason = "pass", text`。判定词识别失败时默认放行（fail-open），而且不要求写理由。

```
scripts/bounty_board.py:791-796
    text = (payload or "").strip()
    head, _sep, rest = text.partition(" ")
    if head.lower() in ("pass", "fail", "partial"):
        verdict, reason = head.lower(), rest.strip()
    else:
        verdict, reason = "pass", text
```

## 影响
中文用户很自然会写「不通过」，或者「fail，」这种中文标点紧跟的形式，结果被静默判成通过，回评标题还是「验收通过」。维护者如果随后批量 `/settle`，就把不合格的交付记成满分（hard 一次过 +12）。这和本仓「不通过就说不通过」「判据不设反面证明就等于没有判据」的纪律相反。

## 修法
1. 判定词必须显式给出：不认识的词就拒绝（`verdict_missing`），回评提示合法写法，而不是默认 pass。
2. 先做规范化：去掉判定词后面紧跟的 `:：,，` 标点；可以考虑接受「通过 / 不通过 / 部分」这样的中文别名。
3. `pass` 也要求写理由（README §三 第④闸要「给出判定与理由」）。
4. 补守卫：`/verify 不通过 x` 和 `/verify failed x` 必须不能进入 verified。

## 与已有 issue 的关系
bodies.txt 里 `/verify` 有 13 处命中，全部是交付帖对 `/verify partial` 规则的引用，没有一条谈到判定词解析。不重复。

本仓 #12（权威记录可伪造）、#17（/withdraw 清零轮次）是另外两条独立缺陷，本条与它们不重叠。

## 在当前 HEAD 上复跑（补，2026-10-12）

被测提交：`af41c07`（dsh-bounty main 最新，2026-10-12 拉取）· Debian 13 / Linux 6.12 · Python 3.12.15 · 纯标准库 · 用 `git archive` 导出到临时目录，`DSH_BOUNTY_REPO` 指向它；脚本只写 /tmp、不触网。
说明：`1e75766`→`af41c07` 之间 `scripts/` 只改了 `build_site.py`（规则页文案），`scripts/bounty_board.py` 未变。

`python -B -X utf8 a2_verify_default_pass.py`：

```
  '/verify fail 读数不可复跑'                → claimed   验收不通过：读数不可复跑
  '/verify FAIL 读数不可复跑'                → claimed   验收不通过：读数不可复跑
  '/verify failed 读数不可复跑'              → verified  验收通过：failed 读数不可复跑  ← 意图为不通过却判通过
  '/verify fail: 读数不可复跑'               → verified  验收通过：fail: 读数不可复跑  ← 意图为不通过却判通过
  '/verify fail，读数不可复跑'                → verified  验收通过：fail，读数不可复跑  ← 意图为不通过却判通过
  '/verify 不通过 读数不可复跑'                 → verified  验收通过：不通过 读数不可复跑  ← 意图为不通过却判通过
  '/verify reject 读数不可复跑'              → verified  验收通过：reject 读数不可复跑  ← 意图为不通过却判通过
  '/verify no'                         → verified  验收通过：no  ← 意图为不通过却判通过
  '/verify'                            → verified  验收通过：（未写理由）
意图不通过却进入 verified 的写法数: 6
VERDICT=BUG
```
与正文 Windows 读数逐行比对：本次 11 行输出全部能在正文代码块里找到同样的行。

## 预期结果（补）

修复后，维护者用同一脚本复跑应看到：

- `/verify failed x`、`/verify fail: x`、`/verify fail，x`、`/verify 不通过 x`、`/verify reject x`、`/verify no` 都不进入 verified（被拒或按 fail 处理）
- `a2_verify_default_pass.py` 中「意图不通过却进入 verified 的写法数」为 0，末行打印 `VERDICT=OK`

## 守卫与定点变异（补，验收判据，尚未实测）

本条只报缺陷、没有附补丁，所以**还没有**修前红 / 修后绿的读数。建议按这两步验收：
1. 把上面的复现脚本改写成守卫：在当前 HEAD 上必须红（上一节已经是红），修复后必须绿；
2. 定点变异：在修复上把关键的那一处改回原样（正文「修法」里提到的那行），守卫必须转红并点名对应断言，还原后转绿。

## 可信边界（补）

**已验**：原审计 `1e75766`（Linux，Python 3.12）；作者本机 `af41c07`（Windows 11，Python 3.14.3）；本次 `af41c07`（Linux，Python 3.12.15）——三处末行都是 `VERDICT=BUG`。
**未验**：没有在真实 GitHub 仓库和真实 Actions 上跑（GitHub 侧用的是假服务器 / 桩客户端 / 纯逻辑层）；没有写补丁，所以修法没有经过测试；没有跑上游 `tests/test_bounty_board.py` 全量。
**不确定**：影响等级和难度是自评，以维护者定档为准。
