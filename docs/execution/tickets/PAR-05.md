# PAR-05 — record-derived provenance vs scientific validation readiness

## Status

- **状态**: 完成。P0 修复 —— `fixtureOnly` 不再是硬编码常量：
  每条 evidence 的 origin（synthetic_fixture / historical_report /
  lab_observation / prediction / unknown）由 domain 已存的 record
  字段在 packet-build/read 时推导（declared markers → naming
  markers → import provenance `execution.historical` →
  `plan_recorded` → unknown），packet 的 `provenance` 块按三轴
  分解报告；`fixtureOnly` 由 composition 推导 —— 全 synthetic
  （或空）才为 true，mixed/real/unknown 一律 false 且 scientific
  validation 保持 `not_validated`。
- **Scope**: `services/studio-api` provenance 模块 + evaluation/
  report/datasets/property_models/sft/export-transform 消费侧 +
  errors（`PROVENANCE_UNKNOWN`）+ apps/studio-web
  （CloseoutPanel/DecisionsPanel/DatasetsPanel + 共享
  `provenance.ts` helper）。无 DB migration —— 全部落在 packet/
  manifest JSONB additive 字段与推导逻辑。
- **依赖**: 基于 PAR-04 合入后的 main（`origin/main` 顶部）。

## 实现内容（审计六条要求 → 落地）

1. **per-record provenance 模型**（requirement 1）：新增
   `studio/domain/provenance.py` —— `measurement_origin()` 沿
   measurement conditions → sample.payload → batch.payload →
   execution.actual → plan.payload 整条链推导 origin（declared
   `provenance.*`/`evidenceOrigin`/`fixture` 标记优先，其次
   method/metric/pipeline_version 命名标记，其次
   `execution.historical` 与 plan-recorded 路径；不认识的 declared
   值与无链记录一律 `unknown`，绝不为旧记录补写字段）；
   `claim_origin()`（document_claim 仅当 import chain 可解析才
   historical_report，否则 unknown；inferred_suggestion →
   prediction；measured_outcome → lab_observation）；
   `session_origin()` → prediction；`summarize()` 组合
   composition（none/synthetic_only/real_only/mixed/unknown_only）。
   `evaluate()`/`closeout_packet()` 的 `fixtureOnly` 由
   `fixture_only(composition)` 推导 —— `fixtureOnly=True` 常量
   全部移除；packet/report 新增 `provenance` 块
   `{evidenceOrigin:{composition,counts,classesPresent,records[]},
   methodValidation:{status:"missing"},
   independentValidation:{status:"not_validated"}, readiness[],
   missingScientificInputs[]}`；manifest 每条 evidence 记
   `origin`/`originVia` 并附 `provenanceSummary`。
2. **三轴分离**（requirement 2）：evidence origin /
   `engineApplicable` / method+independent validation 是 packet 里
   三个互不相干的字段 —— real-origin 证据只升级第一轴；
   `scientificValidation` 恒为 `not_validated`，`readiness` 逐轴
   列出，real_only composition 下 missingScientificInputs 仍完整
   列出 method validation、independent replication、review —
   真实上传绝不自动 fulfill U14。
3. **corpus eligibility 强制**（requirement 3）：datasets build 时
   每条 manifest entry 记 `evidenceOrigin`/`originVia`/`reviewState`
   并把 `unknown` origin 以 `provenance:unknown` 排除；freeze 对
   included 但无已建立 provenance 的记录抛
   `DomainError(PROVENANCE_UNKNOWN, safe_details={recordIds})`
   （rights=unknown 仍按原 plane 先抛 `DATA_RIGHTS_UNKNOWN`）；
   新增 `provenance_violations()` 对 frozen 快照逐条重推导 —
   recorded 缺失（旧 manifest）/当前 unknown/与记录不符均判违规；
   `prepare_run` 在 drift 检查之后以 `reason="provenance_unresolved"`
   阻断；sft `_gate` 在 live-rights 重检同一 plane 加 provenance
   重推导（2b 步）；export `_collect` 在 rights plane 之后对
   `unknown` origin 排除 `provenance_unknown`，record envelope
   带 `evidenceOrigin`，export manifest `snapshot.provenance`
   携带快照 summary。
4. **UI 推导式 summary**（requirement 4）：新增共享
   `features/tasks/provenance.ts`（`provenanceSummary()`/
   `originLabel()`/`originCountsText()`）；CloseoutPanel 的
   常量 badge 变为推导文本 —— 全 synthetic 仍显示 "evidence:
   fixture-only (synthetic) — not scientific validation"，mixed 显示
   "evidence: mixed (N fixture, M historical report…)"，real_only
   显示 "evidence: real provenance (…) — method validation:
   missing; independent validation: missing"，unknown 显示 origin
   unknown；DecisionsPanel 的 signed packet 增加 `provenance` 行；
   DatasetsPanel 的 corpus 行由 `manifest.provenance` 推导
   （legacy manifest 无 provenance 块则回退诚实文案）+ 每条
   record 新增 `evidence origin` 列（synthetic 灰/unknown 警告/
   real 绿）。
5. **不升级 readiness**（requirement 5）：`readiness[]` 各轴状态
   为 `real/synthetic_only/…`、`per_record`、`missing`、
   `not_validated` —— 真实 provenance 不产生任何绿色升级；
   `missingScientificInputs` 恒列三个科学缺口（method
   validation、independent replication、review）；report 的
   limitations 首条由 composition 推导，全 synthetic 保留原
   "fixture-only software output — not scientific validation" 文案。
6. **old records / immutable 语义**：signed packet 与 frozen
   manifest 绝不改写 —— provenance 一律在 packet-build/read 时
   从已存字段推导；`reassessment_status` 对 recorded `origin`
   与当前推导不符的 evidence 判 `provenance_changed` stale
   （无 recorded origin 的旧 manifest 记录跳过该项检查，不
   变异）；pre-PAR-05 manifest 在 prepare/export 路径按 live
   推导补判，unknown 或不符一律阻断 —— 补标签走 rebuild。

## 回归测试（先红后绿）

`services/studio-api/tests/integration/test_par05_provenance.py`
（14 tests）：实现前跑 **14 红**（`provenance` KeyError、
`fixtureOnly` 常量、FORBIDDEN ctx 调整后依然红）→ 实现后全绿：

- `TestPacketProvenance`（6）：全 synthetic → `fixtureOnly` True +
  composition `synthetic_only` + manifest 行 `origin=synthetic_
  fixture`；加入 real-origin 记录 → `fixtureOnly` False +
  `mixed` + `{synthetic_fixture:1, historical_report:1}`，fixture
  历史行仍是 synthetic、scientificValidation 仍 not_validated；
  纯 real → `real_only` + 三轴 `{evidence_origin: real,
  engine_applicability: per_record, method_validation: missing,
  independent_validation: not_validated}`；`historical=False` →
  lab_observation；`prediction-qcengine` method → prediction；
  declared `provenance.origin="an-undeclared-source"` → unknown。
- `TestCorpusProvenance`（5）：manifest entries 带
  `evidenceOrigin`；`manifest["provenance"]["composition"]=="mixed"`；
  `evidenceOrigin:"bogus-class"` → build 时
  `provenance:unknown` 排除；included 记录剥掉
  `evidenceOrigin` → freeze 抛 `PROVENANCE_UNKNOWN` 且
  `safe_details["recordIds"]` 点名；全 synthetic 语料 freeze 成功
  + composition `synthetic_only` + scientificStatus not_validated；
  readiness 对 fixture 记录以 `evidence_origin:synthetic_fixture`
  排除（eligible 0、not_ready），real origin → eligible 1。
- `TestProvenanceGate`（2）：`provenance_violations()` 对
  pipeline_version 突变为 synthetic 的记录返回
  `{recorded:"historical_report", current:"synthetic_fixture"}`
  且 `drift_status` 仍为 clean（provenance 漂移不混进内容漂移）；
  `prepare_run` 对 provenance 违规快照返回
  `{"ok":False,"reason":"provenance_unresolved","recordIds":[…]}`。
- `TestExportProvenance`（1）：`_collect` 的 records 顶层带
  `evidenceOrigin`（measurement 与 claim 均 `historical_report`），
  fields 集合不变。

## 既有测试适配（语义升级，非弱化）

- `test_property_models.py`：`_measurement` 默认 method 与
  `TARGET` 由 `"fixture-method"` 改为 `"assay-method"` ——
  method 名本身是 provenance marker，`fixture-*` 在新模型下
  诚实推导 `synthetic_fixture` 并被 readiness 以
  `evidence_origin:*` 排除；该文件的语义是 coverage/groups
  报表（需要 real-origin 可计入的记录），改名保留原断言
  （eligible 2 / target_mismatch 1）且不加任何豁免路径。
- 其余以 `fixture-method`/`fixture-index` 造数的套件
  （`test_task_evaluation`、`test_par03`、`test_par04`、
  `test_task_report`、`test_dataset_snapshots`、`test_export_*`、
  `test_evidence_binding`、e2e `at-05*`/`at-1103-helpers`）不动
  —— 它们即 synthetic 证据，`fixtureOnly` 推导结果仍为 True，
  dataset 条目带 `synthetic_fixture` 标签而非被排除。
- e2e `at-0503.spec.ts` 的 `text=fixture-only` 断言不变 —
  全 synthetic packet 的推导文案仍含 "fixture-only"。
- `EVALUATOR_VERSION` `par-04.1` → `par-05.1`。

## 验证命令与结果（本分支）

| 步骤 | 命令 | 结果 |
|---|---|---|
| verify-core | `make verify-core` | ruff clean、contracts checksum-verified、schema.graphql in-sync、unit **385 passed** |
| typecheck | `make typecheck` | mypy **231 files no issues**；relay 130 docs；tsc **OK** |
| 全量后端 | `uv run --no-sync pytest services/studio-api/tests tests -m 'not engine' --timeout 300` | **1197 collected（61 deselected）→ 0 failed / 3 skipped**（exit 0） |
| 安全 | `make test-security` | **221 passed / 1 skipped / 9 deselected**（114.56s） |
| 集成 | `make test-integration` | **430 passed / 1 skipped**（371.19s） |
| 前端 typecheck | `pnpm --filter studio-web typecheck` | relay 编译 + tsc **OK** |
| 前端单测 | `pnpm --filter studio-web test` | 10 files / **33 passed** |
| e2e | `make test-e2e` | **38 passed**（1.8m；含 AT-0503/0504 close journeys 的 fixture-only 断言） |
| 新增回归 | `pytest …/test_par05_provenance.py` | **14 passed**（实现前 14 红） |

注：首次 `make test-e2e` 全 38 例因 Playwright chromium
binary 缺失而环境性失败；`pnpm exec playwright install chromium`
后全绿（环境问题，与本改动无关）。

## Migration / rollback 含义

- 无 DB migration：全部改动为推导逻辑 + packet/manifest JSONB
  additive 字段（`provenance`、`provenanceSummary`、每条 evidence
  `origin`/`originVia`、dataset entry `evidenceOrigin`/`originVia`/
  `reviewState`、export record `evidenceOrigin`、export manifest
  `snapshot.provenance`）。
- 不可变性保留：signed packet 不改写 —— 旧 packet 无
  `provenance` 键，UI 回退旧 fixture-only 文案；
  `reassessment_status` 只对 manifest 里**记录过** `origin` 的行
  判 `provenance_changed`（旧 manifest 行跳过，不变异）。
- pre-PAR-05 frozen manifest（无 `evidenceOrigin`）：
  `provenance_violations`/`prepare_run` 判 `provenance_unresolved`
  阻断训练 —— 需要 `build()` 重建快照获得标签；export
  `_collect` 现场推导，unknown 排除 `provenance_unknown`。
- 回退本提交恢复常量 `fixtureOnly=True` 与全部 gating；无数据
  改写步骤需要回滚。

## 已知限制 / 保留行为

- `provenance.origin` 的 declared-marker 词汇表
  （`_ORIGIN_ALIASES`）覆盖 repo 现用的 fixture/synthetic/
  historical/imported/lab/measured/prediction/unknown 词族；
  未识别 declared 值一律 `unknown` —— 保守，不会误判为 real。
- `measurement.conditions`/`pipeline_version` 不参与 entry 内容
  hash（既有语义）—— provenance 漂移由 `provenance_violations`
  单独检查，不冒充内容 drift。
- `training run`/`model`/`promotion`/`rl`/`optimization`/`models`
  面板里的 `capability["dataStatus"]`/`fixture_only` 文案仅渲染
  后端值或静态说明（"fixture-only data is never scientific
  validation"），随 `corpus_data_status` 自动反映真实
  composition；EvaluationsPanel 的 hidden-suite 注记为静态说明
  保留。
- `provenance.readiness` 各轴为状态枚举（`missing`/
  `not_validated`/`per_record`），不做计数或门槛 —— 评审输入
  仍由 human reviewer 决定；U14 保持 unknown。
- 旧评估报告（`evaluate` 返回的 `candidates[]` 内 per-scope
  provenance）对多 accepted candidates 采用 union 汇总 —
  verdict 从不 pooling，provenance 只合并计数汇总。
