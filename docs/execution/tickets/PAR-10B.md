# PAR-10B — browser-first journeys + adversarial evaluation coverage

Parity continuation PAR-10 的验收部分（audit
`docs/execution/audit/2026-10-parity/CHEMISTRY_STUDIO_PARITY_AUDIT.md`）。
PAR-10A（CI 脚手架，#24）已合入 main；本 ticket 交付三条端到端
浏览器旅程与 PAR-01..05 对抗性评估用例。

## Status

- **状态**: 完成（54/54 e2e 全量通过，零回归）
- **Baseline**: `origin/main` @ `17ee58b`（含 PAR-01..09 修复与 #24 CI）
- **依赖**: PAR-01..09 已落地的真实 UI 表面 + PAR-10A CI 脚手架

## 实现内容

### `tests/e2e/par-10.spec.ts`（新文件，7 个用例）

三条旅程完全经 UI 驱动真实表面。helper 只允许做 UI 表达不了的
引导工作（账号 bootstrap、fixture 字节上传 vault、对抗态的
API 播种、以及 UI 不暴露的 draft→active reviewer 过渡）——
被测动作本身一律走 UI。

#### Journey 1 — improve（UI 全链）

PAR-06 真实 sign-in → UI project create → 2 个 identity +
formulation family + accepted baseline rev 1（water 70 / resin 30，
declared total 100，均经 materials UI）→ improve task（baseline
picker）→ PAR-01 契约编辑器逐字段录入 + save + reload 水合回环 +
freeze → 结构化后继 rev 2（copy-parent，water→65 resin→35）+
accept → candidate bound rev 2（propose→submit→accept，全 UI）→
PAR-07 diff 面板断言两条 `changed` 行（water 70→65、resin 30→35）
→ 手动 plan（candidate+contract picker）draft→submit→approve→
export "MANUAL EXECUTION" packet → results 视图开手动执行 →
batch/sample → 记录 manual-index 测量值 7 → review accept →
reviewer 过渡 active（API，UI 无此入口）→ closeout：
`suggestion: supported_success` + `real provenance … independent
validation: missing` badge + selected-candidate-report `met` 行 →
send to review → close-form 勾选确认 → close → `closed`。
后置断言 `taskCloseoutPacket`：`fixtureOnly=false`、
`evidenceIds` 绑定该测量、`provenance.evidenceOrigin.composition
="real_only"`、`scientificValidation="not_validated"`。

#### Journey 2 — match（未知配方参照）

UI 注册 unknown-composition 的 reference product → match_reference
task（product picker 断言 `knowledge: unknown` 徽标，`#match-scope`
= functional_and_analytical）→ 契约 editor（metric.gloss gte 80）
→ API 过渡 active（analytical ingest 领域要求）→ 两条 csv-xy
fixture 字节经 vault 三步上传（helper 仅上传字节）→ analysis
视图逐条 UI 填 IngestSpec 摄取 → "Series recorded." → Left/Right
combobox → "Compute scoped similarity" → comparison section 断言
`not_composition_evidence` 徽标与 SIMILARITY_LIMITS 解释文本
（功能相似不恢复配方）→ API 播种一条 document_claim（UI 表达
范围外的命题播种）→ evidence 视图 proposed→"accept claim"→
accepted → 两个 material-bound candidates → closeout：
pooled-verdict 提示 + 两个 candidate-row + per-candidate
inconclusive metric-row —— 不接受“功能相似 ⇒ 配方恢复”的
池化结论；registry 仍显示 `composition: unknown`。

#### Journey 3 — discover（研究 + 人工反馈环）

discover task（`#target-kind`=formulation + objective）→ research
视图 "start research session" → summary "stream" → composer 发送
→ 断言 `model unavailable — …question is recorded` 徽标（无
runtime 的确定性诚实态，不是 coerce 成可用）→ "raise a
question" 持久化 → overview → 契约 editor 录入 declared unknown
+ metric → save → freeze **被拒**：`VALIDATION: a contract with
declared unknowns cannot be frozen — resolve: …`（未解决项可见
地阻止冻结，断言为期望行为）→ UI resolve → save → freeze 成功
→ 断言 frozen rev 存在 + working draft 上 unknown 仍可见 +
`cannot be frozen` alert 仍显示 + method revision 输入仍为空
（missing method 保持 visibly unresolved）→ candidate（UI）→
approved manual plan + recorded/reviewed measurement（UI）→
advanced→models：`No model releases registered yet.`（引擎相关
能力如实报不可用）→ 过渡 active → closeout
supported_success → close。

#### 对抗性评估（PAR-01..05）

- **PAR-02 候选人不可池化**：两指标 {alpha, beta} + 两 accepted
  候选 A、B；A 绑 alpha=7/beta=2，B 绑 alpha=1/beta=9 —— 池化
  恰好能双双通过。断言每个候选各 1 个 `met` + 1 个 `misses`、
  per-candidate `suggestedDecision="supported_failure"`、
  `supportedSuccessEligible=false`；`taskClose` 无候选 →
  `VALIDATION`（多 accepted 候选必须选）；带 A 关闭 →
  `EVIDENCE_INSUFFICIENT`。UI：两个 `supported_failure` 行 +
  no-pooled 提示 + `supported_success` 选项禁用。
- **PAR-03 缺失成分证据不通过缺席门**：结构化
  `ingredient_absent` 门经 API 播种（契约 editor 无法表达结构化
  检查 —— 这是播种态，非被测动作）+ unbound composition
  candidate + 1 条 met 测量。断言 gate verdict `not_evaluated`、
  `supportedSuccessEligible=false`、taskClose →
  `EVIDENCE_INSUFFICIENT`；UI `gate-row[data-verdict=
  "not_evaluated"]` + success 选项禁用。
- **PAR-04 冲突读数不可判合格**：aggregation `single` + 两条
  bound accepted 读数 7 与 2 → metric verdict `inconclusive`、
  `findings[0].kind="conflicting_readings"`、
  `suggestedDecision="inconclusive"`、close →
  `EVIDENCE_INSUFFICIENT`；UI metric-row`[inconclusive]` +
  `data-finding-kind="conflicting_readings"` + 禁用 success。
- **PAR-05 真实记录不把 fixture 来源刷成已验证**：fixture-index
  测量（→synthetic_fixture）+ manual-index 历史导入测量
  （→historical_report）同绑。断言 `provenance.evidenceOrigin.
  composition="mixed"`、counts {synthetic_fixture:1,
  historical_report:1}、`fixtureOnly=false`、
  `methodValidation.status="missing"`、
  `independentValidation.status="not_validated"`；UI mixed 徽标
  `…not scientific validation` + `historical report` + met 行。

### `tests/e2e/cs-1201.spec.ts`

复查后**无需改动**：PAR-07 已将 nav 更新为真实状态（Materials &
Products 存在并可导航，Settings 仍为 absent 断言）。负向断言
与现实一致，保留全部既有检查。

## Requirement → implementation → test 矩阵（PAR-01..10 验收项）

| 审计要求 | 实现表面 | 用例 |
| --- | --- | --- |
| Improve 旅程端到端 | PAR-06 sign-in、PAR-07 pickers/diffs、PAR-01 contract editor、closeout | `improve: …closeout` |
| Match 旅程：未知配方、scope 目标、证据评审、候选人比较 | ReferenceAnalysisPanel ingest/compare、evidence claims、per-candidate report | `match: …comparison` |
| Discover 旅程：目标定义、有界研究、候选人选择、人工反馈 | ResearchPanel composer/questions、contract unknowns、lab manual 环 | `discover: …closeout` |
| 相似性不声称配方恢复 | `not_composition_evidence` 徽标 + SIMILARITY_LIMITS | match 旅程内联断言 |
| missing method/model 保持未解决 | declared-unknown freeze 拒绝、unbound method、models 空注册表 | discover 旅程内联断言 |
| 候选人不可池化（PAR-02） | per-candidate metrics/gates/suggestedDecision | `PAR-02 …supported_failure` |
| 缺席门缺证据 → not_evaluated（PAR-03） | gate verdict + success-close 拒绝 | `PAR-03 …not_evaluated` |
| `single` 冲突读数不判合格（PAR-04） | inconclusive verdict + conflicting_readings finding | `PAR-04 …inconclusive` |
| 混合来源不算已验证（PAR-05） | provenance composition + validation blocks | `PAR-05 …mixed provenance` |
| helper 不代做被测动作 | 所有领域动作经 UI；API 仅 bootstrap/字节/不可表达态 | 全部 7 用例 |
| 非评态如实报告 | `inconclusive`/`not_evaluated`/`EVIDENCE_INSUFFICIENT`/model unavailable 断言为期望 | 全部对抗用例 |

## Changed files

- `tests/e2e/par-10.spec.ts` — 新 spec（3 旅程 + 4 对抗用例）
- `docs/execution/tickets/PAR-10B.md` — 本证据文档

## Acceptance tests

- [x] Improve 旅程全程 UI：项目 → baseline → 契约录入/冻结 →
      候选修订 → approved 手动 plan → 记录/评审测量 →
      比较/closeout
- [x] Match 旅程：未知配方参照 + scoped 目标 + 证据评审 +
      per-candidate 比较；不声称配方恢复
- [x] Discover 旅程：目标定义 + 有界研究 + 候选人选择 + 人工
      反馈；missing method/model 保持 visibly unresolved
- [x] PAR-02..05 对抗用例，非评态断言为期望结果
- [x] helper 仅 bootstrap/字节/不可表达态 —— 不执行被测动作
- [x] disposable-db 隔离不变（serve.sh truncate + per-suite auth）
- [x] 引擎/模型能力如实报不可用（model_unavailable、空模型
      注册表、not_composition_evidence）
- [x] cs-1201 负向断言与现实核对（无需改动）

## 验证命令与结果

```text
$ make test-e2e
Running 54 tests using 1 worker
…
54 passed (2.9m)

$ make verify-core
uv run --group dev ruff check .
All checks passed!
Specification validation: PASS; 52 tickets; 156 acceptance cases; 20/20 fixture expectations matched.
uv run --group dev pytest tests/unit/test_contracts.py tests/unit/test_design_map.py -q
.............................                                            [100%]
schema.graphql is in sync with backend definitions
relay boundaries clean (106 files checked)
contract mirrors in sync (checksum-verified)
uv run --group dev pytest services/studio-api/tests/unit -m "not integration" --timeout 120
385 passed in 2.86s
verify-core: deterministic checks passed (unit+contracts+lint)

$ make typecheck
Success: no issues found in 231 source files
pnpm --filter studio-web typecheck   # relay + tsc -b，clean

$ pnpm --filter studio-web build
✓ 439 modules transformed.
dist/assets/index-*.js   1,021.13 kB │ gzip: 233.28 kB
✓ built in 738ms
```

后端无改动；pytest 电池已由 verify-core 单测覆盖。

## 边界与未覆盖

- `transition`（draft→active）与结构化 `ingredient_absent` 门
  经 API 播种：UI 无入口/无法表达 —— 属引导态，非被测动作；
  对照 PAR-03 的 UI 断言仍是 gate-row + 禁用选项。
- 引擎依赖检查（native rdkit、真实分析引擎数值）保持
  `UNAVAILABLE`/`model unavailable` —— 如审计要求单独上报，不
  计入科学验证通过。
- 合成 fixture only；无外部服务/凭据/支出。
