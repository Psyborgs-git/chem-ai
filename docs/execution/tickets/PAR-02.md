# PAR-02 — evaluation binds exact candidate / contract / evidence

## Status

- **状态**: 完成。P0 修复 —— evaluation 不再按“任务下所有已接受
  measurement 的名称匹配池化”判定；每条证据必须经 plan lineage
  （`candidateRevisionId`/`formulationRevisionId`/`contractRevisionId`
  ref，任意链级）或经人工 review 的 `EvidenceApplicability` 映射，
  才计入某个 candidate 的报告。
- **Scope**: `services/studio-api` evaluation/service/measurements +
  GraphQL + migration 0029 + CloseoutPanel UI。PAR-03 gate 语义与
  PAR-04 聚合语义不在本 ticket 内（binding 所需的最小路径除外）。
- **依赖**: 基于 `3a9530b`（PAR-01 修复合入后的 main）。

## 实现内容（审计七条要求 → 落地）

1. **显式 evaluation 请求/记录**：`taskEvaluation(taskId,
   candidateRevisionId)` / `taskCloseoutPacket(taskId,
   candidateRevisionId)` 解析器接受显式 scope；report 头部携带
   `evaluationCycle`、`evaluatorVersion="par-02.1"`、
   `contractRevisionId`、`contractRevision`、
   `evidenceSelection{includedIds, exclusions[]}` 与
   `candidates[]`（每个 accepted candidate 一份独立报告）。
   全部为权威 id，非名称。
2. **lineage 解析**：`_evidence_rows` 沿
   measurement→sample→batch→execution→plan 载荷链收集
   `candidateRevisionId`/`formulationRevisionId`/`contractRevisionId`
   ref（camelCase + snake_case，顶层与 `planned`/`actual` 子对象内
   均识别）；`formulationRevisionId` 经
   `_formulation_candidate_map` 折到指向该 formulation 的本任务
   candidate。无 linkage 的历史 measurement 留在 research evidence，
   不进任何 candidate 报告。
3. **比对前适用性检查**：`_bind` 先做绑定判定（`status_not_accepted`、
   `marked_inapplicable`、`mapped_not_applicable`、`conflicting_lineage`、
   `bound_to_candidate`/`bound_to_other_candidate`、
   `no_candidate_binding`、`different_contract`），再由
   `_evaluate_metric` 做方法/底物检查（`method_unresolved`、
   `method_mismatch`、`substrate_unresolved`、`substrate_mismatch`）——
   每条排除给出 `reason` + `detail` + `action`，报告进
   `evidenceSelection.exclusions`。
4. **历史复用仅经 review 映射**：新增 `EvidenceApplicability`
   （migration `0029_evidence_applicability`，唯一键
   `(workspace, measurement, candidate_revision)`，status
   `applicable|not_applicable`，`revoked_at` 标记撤回、行保留为
   历史）。`LabMeasurementService.record_applicability` 需要
   CAP_REVIEW_MEASUREMENT + 必填 rationale；
   `withdraw_applicability` 保留行并标 revoked。GraphQL 新增
   `measurementMapApplicability` mutation（`withdraw` flag）。
5. **逐 candidate 报告**：多 accepted candidate 时 evaluator 不合成
   top-level 结论 —— `candidates[]` 各自有完整 metrics/gates/
   suggestedDecision + `multiple_candidates` finding；绝不按 revision
   号挑选胜者。
6. **closeout 绑定 reviewer 所见的报告**：`task.close` 在多 accepted
   candidate 且无显式 `candidateRevisionId` 时拒绝（VALIDATION +
   `safe_details.candidateRevisionIds`）；packet 绑定
   `contractRevisionId`+`candidateRevisionId`+manifest digest；
   `reassessment_status` 报告依赖漂移（新 accepted candidate →
   `new_candidate` 进 `changedDependencies`；applicability 翻转 →
   `staleEvidenceIds`），signed packet 本体不可变。
7. **mode-input 校验**：`invalid_inputs(db, task)` 校验
   `baselineRevisionId`（formulation_revisions /
   reference_product_revisions / candidate_revisions 表）与
   `referenceProductId`（reference_products）——必须解析为
   workspace 内真实存在的行；`baseline-rev-1` 这类字符串进
   `invalidInputs`（report `unknowns` + `Task.invalidInputs`
   GraphQL 字段），空白/缺失保持 unresolved，绝不计为有效 baseline。

### UI（apps/studio-web CloseoutPanel）

- 新增 candidates 摘要表（revision/kind/eligibility/suggestion/
  evidence 数），radio 选择后展开该 candidate 自己的 metrics/gates
  报告；`candidates.length === 0` 时才渲染任务级 MetricsGates（避免
  重复表格）。
- CloseForm 在有 ≥1 candidate 时提供「candidate this closure binds」
  select；多 candidate 未选则 close 按钮禁用并提示 —— wire 上以
  `btoa("CandidateRevision:"+uuid)` GlobalID 编码发送
  `candidateRevisionId`（修复了 raw UUID 触发 strawberry
  GlobalIDValueError 的真实缺陷）。

## 回归测试（先红后绿）

`tests/integration/test_evidence_binding.py`（12 tests）：

- `TestPooledCandidates`：A 过 X 败 Y、B 败 X 过 Y → 无池化
  supported_success、`candidates[]` 各报各的、显式选择生效、
  close 缺候选 → VALIDATION 带 candidateRevisionIds、未知/他任务
  candidate → VALIDATION
- `TestApplicabilityChecks`：method_mismatch / substrate_unresolved /
  substrate_mismatch / different_contract 各自正确排除；
  `record_applicability` 可恢复绑定
- `TestHistoricalMapping`：无绑定证据仅经 reviewed mapping 计入；
  `applicable=False` → `mapped_not_applicable`
- `TestPacketImmutability`：signed packet 绑定精确 candidate +
  manifestDigest；新 accepted candidate → needsReassessment +
  `new_candidate`；applicability 翻转 → reassessment
- `TestModeInputValidation`：bogus baselineRevisionId /
  referenceProductId → `invalidInputs`；真实实体 id → 清除

## 既有测试适配（语义升级，非弱化）

- `tests/security/test_task_evaluation.py`：fixture 改为经
  `record_applicability` 显式绑定 measurement → candidate（同一
  gate/metric 判定路径不变）。
- `tests/integration/test_task_report.py`：plan payload 携带
  `candidateRevisionId` 声明 lineage（测量不变）。
- `tests/e2e/at-0503.spec.ts`、`at-0504.spec.ts`、`at-1103-helpers.ts`：
  `candidates.create` 后补真实 draft→submitted→accepted_for_research
  lifecycle（submit + review mutation）——先前 fixture 停留在 draft，
  PAR-02 下正确地被排除出报告；现驱动真实路径。
- `.github/workflows/ci.yml`：e2e job `timeout-minutes` 30→20
  （§23.3 core cap；既有 `test_ci_job_timeouts` 红灯修复）。

## 验证命令与结果（本分支）

| 步骤 | 命令 | 结果 |
|---|---|---|
| verify-core | `make verify-core` | ruff + contracts + schema.graphql in-sync + unit **379 passed** |
| typecheck | `make typecheck` | mypy **230 files no issues** |
| 全量后端 | `uv run --no-sync pytest services/studio-api/tests tests -m 'not engine' --timeout 300` | **1133 passed / 3 skipped / 0 failed**（1136 collected） |
| 安全 | `make test-security` | **221 passed / 1 skipped** |
| 集成 | `make test-integration` | **375 passed / 1 skipped** |
| 前端 typecheck | `pnpm --filter studio-web typecheck` | relay 编译 + tsc **OK** |
| 前端单测 | `pnpm --filter studio-web test` | 9 files / **27 passed** |
| e2e | `make test-e2e` | **36 passed**（含修复后的 AT-0503-3 / AT-0504-1/2 / AT-1103-2 键盘旅程） |
| 新增回归 | `pytest tests/integration/test_evidence_binding.py` | **12 passed** |

## Migration / rollback 含义

- `0029_evidence_applicability`：新增 `evidence_applicabilities`
  表 + 唯一约束 + revoked_at；`downgrade()` drop 该表。对既有行零
  影响；回退后历史映射消失（新评测按无映射处理 —— 与 PAR-02 之前
  的池化不同，不会暗中扩大计数）。
- `schema.graphql` 经 `make schema-export` 重生成并已通过
  `--check`。

## 已知限制 / 保留行为

- 无绑定证据不会在 UI 里被静默算进任何 candidate —— 这正是修复
  目标；reviewer 需经 `measurementMapApplicability` 显式授权历史
  复用。
- `baselineRevisionId` 非法值现在会如实出现在 `invalidInputs` /
  `unknowns`；旧数据不受影响（不做就地重写）。
- e2e fixture 更新后流程仍覆盖相同的 close/gate 判定 —— 只是先
  走完 candidate review lifecycle。
- Gate 失败语义（PAR-03）与聚合/修正语义（PAR-04）未动。
