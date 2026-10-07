# PAR-01 — canonical success-contract schema + editable round-trip

## Status

- **状态**: 完成。P0 不一致修复 —— UI 保存的 `requiredMetrics` 旧词汇此前
  在 evaluator 中等价于“零指标”；现在单一 contract 词汇贯穿校验、
  GraphQL、编辑器与评估，旧 payload 走显式 legacy 读路径，不改写已
  冻结历史。
- **Scope**: `services/studio-api` 领域校验 + GraphQL + 编辑器重写 +
  legacy 读取；PAR-02..05 的 evaluator 语义（binding/gates/aggregation）
  不在本 ticket 内，未改动。
- **依赖**: 保留 PR #22 的 task-row `SELECT FOR UPDATE`；不触碰
  workplan.json。

## 实现内容

### 1. 单一版本化 contract 词汇（domain/tasks/contract.py）

pack `docs/chemistry-studio/contracts/domain.schema.json` 的
`SuccessContract`/`Metric`/`HardConstraint` $defs 即原计划的 canonical
词汇（evaluator、fixtures、e2e helpers 已在使用）——本 ticket 把它落成
一个 pydantic DTO 模块（`extra="forbid"`），而不是再发明第二套词汇：

- `CONTRACT_SCHEMA_VERSION = "1.0.0"`；`ContractMetric` /
  `ContractConditions` / `ContractHardConstraint` 覆盖全部已持久化
  形态（canonical `target_values`+`operator`+`unit`、宽松
  `{name, target}` 字符串界、UI 旧 camelCase `target`/`targetValues`/
  `requiredEvidence`）。
- `validate_draft_payload`：拒绝非 dict、row-owned 字段
  （id/task_id/revision/status/content_hash/created_*）伪装进
  payload、非受控 `schema_version`、非法枚举值；未知 top-level 字段
  与显式 `unknowns` 在 draft 中**保留**（诚实未知，不静默丢、不
  编造默认值）。
- `validate_freeze_payload`：draft 规则之上再加 —— 拒绝未知字段、
  拒绝未解决的 `unknowns`、要求 ≥1 个可解析指标（id/name/label +
  `metric_bound` 可解析的 bound）。缺指标/条件绝不转成“有科学
  含义的默认”。
- `resolve_metrics(payload)`：`metrics` 权威；无 `metrics` 时
  `requiredMetrics` 走显式 legacy 翻译（`{name, operator, target:
  {value, unit}}` → canonical bound）；`constraints` 裸字符串列表按
  gate 计入；双词汇并存或歧义条目 → `issues[]` 如实列出，不静默。

### 2. 服务端校验 + GraphQL 面

- `draft_contract`（service.py）：payload 过 `validate_draft_payload`
  后再取 task 行锁；`freeze_contract`：状态检查后过
  `validate_freeze_payload`。VALIDATION → typed `errors[]`
  （DomainError code/fieldPath），与 SQLAlchemyError → 可重试
  CONFLICT 区分开；行锁原样保留。
- `ContractRevision` 类型暴露 `payload`（JSON）；新增
  `taskContractRevisions(taskId, first/after/last/before)` keyset
  connection（CAP_READ_PROJECT，scope_signature
  `task_contract_revisions`），`schema.graphql` 经
  `make schema-export` 重新生成并通过 `--check`。

### 3. evaluator 接 canonical + 冻结历史诚实

- `evaluation.py`：`evaluate()` 改用 `resolve_metrics()` —— canonical
  `metrics`、legacy `requiredMetrics`、`constraints`-gate 三路并进；
  report 增加 `assessable`、`reason`、`legacyPayload`、
  `contractIssues`；closeout packet 同步携带。已冻结的非 canonical
  历史（如 `thresholds`-only）评估为 `assessable=false` +
  inconclusive + issues —— 不再被读成“零要求已满足”，也绝不改写
  存储字节。
- `verification.py`：`_closure` 循环 resolved metrics；packet 增加
  `legacyPayload`/`contractIssues`；`report.py` 的
  metricCount/gateCount 同步走 `resolve_metrics`。

### 4. 编辑器重写（ContractEditor.tsx + contractForm.ts）

- `contractForm.ts`：canonical payload emit（`schema_version`、
  `metrics[]` 全字段、`hard_constraints`、`unknowns`），反向
  `formFromPayload` 水合 canonical/宽松/legacy 三形态；模块级
  `pendingForm` 存未保存编辑。
- `ContractEditor`：`useLazyLoadQuery` + `fetchKey`/`network-only`
  重取（CS-1201 约定）；按 head revision 变化水合（同 head 的
  re-render 不覆盖用户编辑 —— mutation 自身节点写触发的 refetch
  曾把刚保存的表单恢复成 unsaved，已在 onCompleted 内同步清
  pending 并收紧水合 deps 修复）。
- 完整工作流：revision 标识（revision/status/hash）、legacy banner、
  指标行（label/id/required/operator/target values/unit/method
  revision/conditions/aggregation/min batches/required evidence）、
  hard constraints、unknowns 增/解、save draft（dirty gating、
  双提交防护、失败保留输入）、freeze（仅对 latestDraft 且在
  saved 态可用）、revision history 只读回看、CONFLICT →
  `conflict` 态 + beforeunload 守卫。
- `useSaveState` 增加 `markSaved`/`markConflict`；`unsaved` 与
  `conflict` 均 armed beforeunload。

## Changed files

- `services/studio-api/src/studio/domain/tasks/contract.py`（新）
- `services/studio-api/src/studio/domain/tasks/evaluation.py`
- `services/studio-api/src/studio/domain/tasks/service.py`
- `services/studio-api/src/studio/domain/tasks/report.py`
- `services/studio-api/src/studio/domain/candidates/verification.py`
- `services/studio-api/src/studio/api/graphql/schema.py`（
  taskContractRevisions connection）
- `services/studio-api/src/studio/api/graphql/types.py`（payload 字段）
- `packages/contracts/schema.graphql`（schema-export 再生成）
- `apps/studio-web/src/features/tasks/ContractEditor.tsx`（重写）
- `apps/studio-web/src/features/tasks/contractForm.ts`（新）
- `apps/studio-web/src/features/tasks/operations.ts`（Revisions 查询 +
  draft mutation 选 payload）
- `apps/studio-web/src/features/tasks/useSaveState.ts`（markSaved/
  markConflict + conflict beforeunload）
- `services/studio-api/tests/unit/test_contract_schema.py`（新，29）
- `services/studio-api/tests/integration/test_contract_parity.py`（新，9）
- `services/studio-api/tests/integration/test_task_lifecycle.py`（三处
  非 canonical freeze payload → canonical）
- `tests/e2e/par-01.spec.ts`（新，3）
- `tests/e2e/at-0206.spec.ts`（AT-0206-2 适配新编辑器控件名）

## Acceptance tests

### PAR-01-A [e2e] UI 保存 → reload → UI freeze → evaluator 收到精确指标

`par-01.spec.ts` 测试 1：真实 UI 填 metric label=viscosity、
id=metric.viscosity、operator gte、target "500"、unit "mPa·s"、
conditions "25 °C, spindle A" → save draft → 整页 reload 水合校验
（`draft revision 1`，字段逐值断言）→ UI 点 freeze → `frozen` →
GraphQL `taskEvaluation` 断言 `assessable=true`、`legacyPayload=false`、
`metrics[0].metricId=="metric.viscosity"`、`label=="viscosity"`、
verdict inconclusive（未测量 → 如实 inconclusive，suggestedDecision
同）。**UI 保存路径即被测对象**，helper 仅 bootstrap
auth/project/task。

### PAR-01-B [e2e + unit] 未知/不兼容 draft 字段不能静默冻结成可评 contract

`par-01.spec.ts` 测试 2：API 存含 `thresholds`（未知字段）+
`unknowns` 的 draft → freeze 返回 VALIDATION typed error 且
`contractRevision=null`；改用 canonical successor draft → freeze 成
revision 2 且 evaluate 拿到 `gloss` 指标。
`test_contract_schema.py` freeze-gate 套件：未知字段/空 metrics/
声明 unknowns/匿名指标/未知 metric 字段/row-owned 字段逐一拒绝。

### PAR-01-C [integration] legacy `requiredMetrics` 显式读路径，历史不改写

`test_contract_parity.py`：legacy payload freeze+evaluate →
metricId `viscosity` 到达 evaluator、`legacyPayload=true`、
存储 payload 逐字节不变；歧义 legacy 条目 → `contractIssues`
列出；已冻结的 `thresholds`-only 行 → `assessable=false` +
inconclusive，payload 原样。

### PAR-01-D [e2e + integration] 保存/冲突/历史/未保存恢复工作流

`par-01.spec.ts` 测试 3：UI save+freeze → 再编辑 → `unsaved` →
切到 runs section → 回 overview → 未保存表单恢复 +
"restored unsaved edits" badge → `revision history` 展开 → view 按钮
→ `viewing revision 1` + `read_only_revision` + 冻结指标可见。
`at-0206.spec.ts` AT-0206-2（适配后）：API 断线时 save → alert +
保持 unsaved、无 "saved offline" 假象。cs-1201 并发 draft
序列化测试仍绿（行锁未动）。

## 验证命令与结果

| 步骤 | 命令 | 结果 |
|---|---|---|
| verify-core | `make verify-core` | PASS（ruff 全绿；contracts 52 tickets/156 cases/20-20 fixtures；schema.graphql in sync；relay boundaries 91 files；contract mirrors in sync；unit 379 passed） |
| typecheck | `make typecheck` | mypy 230 files no issues + `pnpm --filter studio-web typecheck`（relay 115 reader/113 normalization/115 operation + tsc）OK |
| 全量后端 | `uv run --no-sync pytest services/studio-api/tests tests -m 'not engine' --timeout 300` | **1114 passed / 3 skipped / 0 failed** |
| 安全 | `make test-security` | **221 passed / 1 skipped / 9 deselected**（99.8s） |
| 前端 typecheck | `pnpm --filter studio-web typecheck` | OK |
| 前端单测 | `pnpm --filter studio-web test` | 8 files / **18 passed** |
| 前端构建 | `pnpm --filter studio-web build` | OK（877kB chunk 警告为 CS-1103 已知） |
| e2e | `pnpm --filter studio-web exec playwright test --config ../../tests/e2e/playwright.config.ts`（= `make test-e2e` 同一命令） | **31 passed**（57.1s，含 par-01.spec.ts 3/3 与适配后 AT-0206-2） |
| 新增单测 | `pytest tests/unit/test_contract_schema.py` | 29 passed |
| 新增集成 | `pytest tests/integration/test_contract_parity.py` | 9 passed（testcontainers postgres:16.10） |

## 后续修复（dev-mode 缺陷）

- 录制走查发现：vite dev + React 19 StrictMode 下 `ContractRevisionsQuery`
  每 ~300ms 无限重取、编辑器永远停在 "loading contract…"（生产构建
  不受影响）。根因：mount 后在 `useEffect` 里 `setState` 水合 —
  post-commit 的二次 commit 让 `network-only` 的
  `useLazyLoadQuery` 在 Suspense hide/reveal 间反复触发 Relay 的
  remount `forceUpdate`，每次变更 `cacheBreaker` → 新 fetch。修复：
  水合改为 render-time derived state（React 官方 "adjust state
  during render" 模式，不产生额外 commit）。dev 实测：mount=2 次
  POST（StrictMode 正常双取）→ save→refetch→freeze→refetch→稳定；
  `pnpm --filter studio-web typecheck|test|build`、par-01+at-0206
  e2e 6/6 全绿。

## 已知限制

- freeze gate 比 pack 完整冻结规则**窄**：当前只要求 canonical 词汇 +
  ≥1 个可解析指标 bound；pack domain.schema.json 中还规定了
  `target_kind != "unknown"`、`approval_id` uuid、baseline/reference
  revision 链接等冻结前置 —— 这些依赖 PAR-02..05 的 evaluator/审批
  语义，本 ticket 不替它们定案，冻结不虚构这些字段。
- `constraints`/`warnings`/宽松 `{name,target}` 等已持久化形态按
  “可评即可冻结”处理（metrics 权威、constraints 计入 gates）；
  已冻结的非 canonical 行用 `assessable=false` 诚实呈现，不做
  就地重写 —— 内容 hash 与旧 evidence packet 均保留。
- legacy `requiredMetrics` payload 在编辑器内经翻译渲染（带 legacy
  banner），编辑再保存即写 canonical；存储字节永不就地改写。
- 未做 DB migration —— 修复全部在读取/校验路径，歧义 payload 经
  `contractIssues` 浮出水面由人审或 successor revision 接续。
- e2e 并发 caps：`workers: 1` 为仓库既有配置，未改动。
