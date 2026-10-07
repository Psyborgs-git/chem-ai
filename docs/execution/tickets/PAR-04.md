# PAR-04 — aggregation rules + verified correction lineage

## Status

- **状态**: 完成。P0 修复 —— 聚合规则不再默认为
  `fixture-single-value` 用 `any(compare())` 投机取最优值：未声明
  聚合规则的 live 评估一律 `aggregation_unresolved` +
  `inconclusive`；`single`/`fixture-single-value` 采用全一致语义
  （冲突读数 → `conflicting_readings` inconclusive，绝不 silently
  best-of）；`mean` 按独立 batch 分组先算组内均值再取均值（读数
  多的 batch 不再压过其它 batch）；`min`/`max` flat。amendment
  链路打通：superseded + 可解析 `MeasurementAmendment` 的
  measurement 以「评审后的修正值/条件」进入评估、manifest、
  reassessment、dataset 快照、optimization 与 GraphQL
  `effective_value` —— 修正值恰好使用一次，绝不新旧并存。
  reviewer 记录超出 evaluator 建议的 `supported_failure` 必须
  rationale + 绑定进 packet 的 evidenceIds。
- **Scope**: `services/studio-api` evaluation/datasets/
  optimization/task close + GraphQL `Measurement.effectiveValue` +
  ResultsPanel 生效值展示。PAR-05 provenance（`fixtureOnly`
  硬编码等）不在本 ticket；无 DB migration（全部落在 packet
  JSONB additive 字段 + 既有 `measurement_amendments` 表）。
- **依赖**: 基于 PAR-03 合入后的 main（`origin/main` 顶部）。

## 实现内容（审计六条要求 → 落地）

1. **显式聚合规则**（requirement 1）：`assess_metric` 中
   `metric.get("aggregation")` 缺失或空白 → finding
   `kind="aggregation_unresolved"`（`action="declare_aggregation_rule"`
   ，文本明确 "an unspecified rule is unresolved — never best-of"）
   + verdict `inconclusive`。未知规则字符串 → `kind="unknown"`
   inconclusive。报告新增 `amendedIds`/`observations`/
   `aggregation`/`independentBatches` 字段。
2. **single 语义 + 已声明策略**（requirement 2）：
   `single`/`fixture-single-value` 采用「全部读数一致」规则 —
   全过 → `met`，全 miss → `misses`，部分冲突 →
   `conflicting_readings` finding（携带每条 outcome 明细
   `passingReadings`/`failingReadings`）+ `inconclusive`，
   绝不 `any()`。`mean`/`min`/`max` 为显式已声明策略；审计
   不替用户选科学阈值 —— 无规则即 unresolved。
3. **独立单元区分**（requirement 3）：`mean` 聚合按
   `batch_id` 分组 —— 同一 batch 的技术重复先取组内均值，
   再对各 batch 均值取 mean（`batch_id=None` 的读数各自成
   组）；`independentBatches` 仍按 distinct batch_id 计，
   同一 aliquot 的 `same_sample` 重复计一次。批次多的仪器
   读数不再 overweight。
4. **amendment 有效版本贯通**（requirement 4）：复用既有
   `LabMeasurementService.amend` hook（未改动、未重复实现）。
   `_Evidence` 携带 `amendment` + `effective_value`/
   `effective_conditions`；`_bind` 中 superseded 且 amendment
   可解析的行以该 measurement 自身 id 绑入一次（值取
   `amd.value`，条件取 `amd.conditions or m.conditions`）；
   superseded 且无 amendment 的行仍排除。`_manifest` 每条记
   `effectiveAmendmentId` + `amendment{id,reason,source,
   createdBy,createdAt}`，`valueHash` 对 effective value 计算；
   `reassessment_status` 对 superseded 行比较记录的
   `effectiveAmendmentId` —— 修正前签发的 packet 判 stale，
   修正后签发的不 stale（signed packet 永不改写）。datasets：
   `_measurement_fields/_semantics_measurement` 对修正行记
   修正值 + `effective_amendment` + `effectiveFromAmendment`/
   `correctionReason`/`correctionSource`/`correctedBy` 语义键，
   快照恰含一条修正后记录；`amend` 本已 trip `_current_hash`
   漂移检测（旧快照 drift → `staleRecordIds`）。optimization：
   accepted 或 superseded+amendment 均可行，unit/actual/
   outcome 一律读 effective value。GraphQL `Measurement` 新增
   `effectiveValue` 字段；ResultsPanel 在 superseded 行展示
   「effective value · corrected」徽标。
5. **原始完整性 vs 版本适用性分离**（requirement 5）：
   `status="superseded"` 保留原行（不可变原件），修正以独立
   `MeasurementAmendment` 行承载 reason/source/createdBy —
   approval 历史不丢；dataset entry 仍记 `status`/原 hash 字段
   加 `effective_amendment`；评估/训练谱系随 amendment 变化
   自动失效（manifest `effectiveAmendmentId` 比对 + snapshot
   哈希漂移）。
6. **outcome label 防冒充**（requirement 6）：
   `TaskService.close` 新增 `_failure_evidence_gate` —
   `suggestedDecision=="supported_failure"` 时直通（实测失败
   无需额外证明）；否则 reviewer-recorded `supported_failure`
   要求非空 `reviewerPacket.rationale` 且
   `reviewerPacket.evidenceIds` ⊆ 已绑定集合
   （`evidenceSelection.includedIds` ∪ exclusions 的
   measurementId ∪ packet `evidenceIds`），否则
   `DomainError(EVIDENCE_INSUFFICIENT, safe_details=
   {suggestedDecision, rationaleProvided, unboundEvidenceIds})`。
   未测量/无支撑的实验只能 `inconclusive`/`stopped` —
   永远进不了训练真值。
- 评估器版本 `par-03.1` → `par-04.1`。

## 回归测试（先红后绿）

`services/studio-api/tests/integration/test_par04_aggregation_corrections.py`
（12 tests）+ `tests/unit/test_task_evaluation.py`（+6 tests）；
实现前 stash 源改动跑 **13 红**（9 integration + 4 unit）：

- `TestExplicitAggregation`（4）：`single` 冲突读数（6 vs 3，
  gte 5）→ `conflicting_readings` inconclusive + close 拒绝；
  一致重复读数 corroborate `met`；缺 `aggregation` 键 / 空白
  字符串 → `aggregation_unresolved` inconclusive。
- `TestReplicationUnits`（2）：同一 aliquot 3 条 same_sample
  读数 + 1 条独立 batch → `independentBatches==2`，min 3 →
  `insufficient_replication`；`mean` 批加权 [9,9,9]+[1] vs
  target 6 → 组均值 9 与 1 → 5 → `misses`（旧 flat mean 7
  会让多读的 batch 胜出）。
- `TestCorrectionLineage`（4）：miss(4) → amend 到 7 → 同
  metric 变 `met`；报告 `amendedIds`；manifest
  `effectiveAmendmentId` + `amendment{reason,source,createdBy}`；
  修正前签发的 packet `staleEvidenceIds`/`needsReassessment`
  而 packet 本体不改；dataset 快照 drift + 新快照恰一条
  修正记录（无旧值）。
- `TestOutcomeLabels`（2）：evaluator 建议 supported_failure
  直通 close；inconclusive + reviewer supported_failure 仅有
  rationale 无绑定证据 → `EVIDENCE_INSUFFICIENT`；
  rationale + evidenceIds ⊆ packet → 通过。

## 既有测试适配（语义升级，非弱化）

- 声明缺失的 metric fixtures 补 `"aggregation":
  "fixture-single-value"`：`test_task_lifecycle.py`（4 处）、
  `test_task_report.py`、`security/test_task_evaluation.py`、
  `test_par03_gate_failsafe.py::_metric_gate()` check、
  `tests/e2e/at-1103-helpers.ts`（metric + gate check）、
  `tests/e2e/at-0504.spec.ts`（5 处）、`tests/e2e/cs-1201.spec.ts`。
- `test_contract_parity.py::test_legacy_ui_payload_evaluates_…`
  —— legacy `requiredMetrics` 载荷无聚合规则，断言由
  `met` 改为 `inconclusive` + `aggregation_unresolved` finding
  （正确的新语义：声明缺失即 unresolved，不是弱化）。
- `test_task_lifecycle.py::test_full_close_reopen_new_contract_
  keeps_link` —— 未测量实验的 closure 由 `supported_failure`
  改为 `inconclusive`（§6 语义）；close→reopen→新 contract
  链路断言不变。
- `tests/integration/migrations/legacy_seed.py` 未动 —— legacy
  `{"name","target"}` metrics 只走迁移完整性路径，不进
  `assess_metric`。
- `test_task_memory.py`/`test_revocation_quality.py` 的 metrics
  不进入评估路径，无需适配。

## 验证命令与结果（本分支）

| 步骤 | 命令 | 结果 |
|---|---|---|
| verify-core | `make verify-core` | 规格 52 tickets/156 cases、ruff、contracts、schema.graphql in-sync、unit **385 passed** |
| typecheck | `make typecheck` | mypy **230 files no issues**；relay 130 docs；tsc **OK** |
| 全量后端 | `uv run --no-sync pytest services/studio-api/tests tests -m 'not engine' --timeout 300` | **1181 passed / 3 skipped / 0 failed**（1184 collected） |
| 安全 | `make test-security` | **221 passed / 1 skipped** |
| 集成 | `make test-integration` | **416 passed / 1 skipped** |
| 前端 typecheck | `pnpm --filter studio-web typecheck` | relay 编译 + tsc **OK** |
| 前端单测 | `pnpm --filter studio-web test` | 10 files / **33 passed** |
| e2e | `make test-e2e` | **38 passed**（含 AT-0502-1 same-aliquot replication、AT-0502-3 amendment supersedes、AT-0503/0504 close journeys、par-01 编辑器链路） |
| 新增回归 | `pytest …/test_par04_aggregation_corrections.py …/unit/test_task_evaluation.py` | **28 passed**（实现前 13 红） |

## Migration / rollback 含义

- 无 DB migration：`measurement_amendments` 表与 `amend()` 服务
  hook 为既有结构，全部改动为消费侧读取 + packet JSONB additive
  字段（`effectiveAmendmentId`、`amendment{...}`、`amendedIds`、
  `aggregation`、`independentBatches`、`observations`）。
- signed packet / 冻结快照永不改写：旧 packet 在
  `reassessment_status` 下因 `effectiveAmendmentId` 不匹配判
  stale（正确失效），数据本身不变；旧 dataset 快照同样只
  drift 不重写。
- 回退本提交恢复旧 `any()` + accepted-only 语义；无数据改写
  步骤需要回滚。

## 已知限制 / 保留行为

- `evaluate()` 的 `fixtureOnly=True` 硬编码与 candidate-
  provenance 绑定属 PAR-05 范围，本 ticket 未动。
- 声明缺失聚合规则的既有 frozen contract 在新语义下评估为
  `aggregation_unresolved` inconclusive —— 有意为之：合约需
  补声明规则（新 revision）后才可判 met/misses。
- `batch_id=None` 的读数在 `mean` 下各自成组（保守：无批次
  归属不假装独立 batch）；`min`/`max` 保持 flat（语义不依赖
  单元权重）。
- ResultsPanel 的 effective value 直接渲染 `amendments` 最后
  一条的 `value`（复用既有 fragment），未为 `effectiveValue`
  新增 fragment 字段 —— GraphQL 字段已存在供后续按需使用。
- 单一评审 `amend` 的审批链（approval history）沿用既有
  `MeasurementAmendment` 行 + audit 事件，未新增审批工作流。
- PAR-05 provenance（`fixtureOnly`、run/manifest lineage
  收紧）未动。
