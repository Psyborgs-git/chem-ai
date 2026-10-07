# PAR-03 — hard gates fail safe on unknowns + dependency-aware reassessment

## Status

- **状态**: 完成。P0 修复 —— `ingredient_absent` 硬门禁不再把「没有
  数据」当成「没有成分」：无候选、无实体链接、配方未评审/不完整、
  reference product 配方未知、成分行身份不可解析时一律
  `not_evaluated` + 具体 finding，绝不 `pass`。closeout manifest 现
  携带硬门禁证据与全部依赖锚点；`reassessment_status` 覆盖
  applicability 翻转、组分漂移、目标身份变化、approval 撤销。
- **Scope**: `services/studio-api` evaluation（gate 语义 + manifest +
  reassessment）。PAR-04 聚合语义、PAR-05 provenance 不在本
  ticket；无 DB migration（manifest 全部落在 packet JSONB ——
  additive，无 schema 变更）。
- **依赖**: 基于 PAR-02 合入后的 main（`origin/main` 顶部）。

## 实现内容（审计五条要求 → 落地）

1. **absence 检查的成立条件**：`ingredient_absent` gate 要求 (a) 合法
   target identity（`materialIdentityId` 可解析；注册表缺失记
   `unknown` finding 但仍按字面匹配继续），(b) 一个适用的 candidate
   表征，(c) 针对该 claim 的充分已评审组分覆盖 —— formulation
   必须 `accepted` + `completeness="complete"`；reference product
   必须 `composition_knowledge="known"` + 有 frozen revision +
   非空 composition；material/molecule 以 material_identity 为组分
   （kind ∈ {commercial_mixture, substance_class, unknown} →
   `composition_unknown`）。任一不满足 → `not_evaluated`。
   `check.basis` 非 `"declared"` → `basis_not_supported`：绝不把
   配方核查升级成分析/合规结论。pass 的 gate 携带
   `claimBasis`（declared_composition/declared_identity）+
   `claimBound` 文本 —— 明确 bounded 到该 revision 的声明式
   组分陈述，**不是** 分析测定、不是 toxicology/compliance
   证书。
2. **未知分类覆盖**（requirement 2）：`no_bound_candidate` /
   `entity_link_missing` / `composition_revision_missing` /
   `composition_unreviewed`（draft）/ `composition_superseded` /
   `composition_empty` / `composition_incomplete` /
   `composition_unknown` / `ingredient_identity_unresolved`
   （supplier-only 行等）/ `reference_link_missing` /
   `target_identity_missing` / `basis_not_supported` —— 每个
   finding 进 `unknowns`，同时聚合进 scope 级 `blocks[]`（
   供 research 视图展示候选阻塞原因；candidate 仍出现在报告里）。
   成分行解析顺序：`materialId` 字面命中 → 已注册 identity →
   alias/name/identifier 索引 → IdentityMatch union-find 等价类
   （accepted match 视为同一身份）；无法解析 → `unresolved` →
   not_evaluated（无解析不行）。
3. **manifest 携带硬门禁证据与依赖**（requirement 3）：
   `packet.manifest` 新增 —— 每条 measurement 记
   `method`/`methodRevisionId`/`pipelineVersion`/`valueHash`/
   `supersededBy`/`included`；`gateDependencies[]`（按
   (gateId, candidateRevisionId) 去重）记 subject、
   materialIdentityId、basis、compositionKind、
   compositionRevisionId/ContentHash/Status/Completeness/
   ApprovalId、referenceProductVersion、targetIdentityVersion、
   ingredientCount；`dependencies` 记 `contractRevision`、逐
   candidate `{id, revision, contentHash, status, eligibility,
   entityKind, entityRevisionId}`、`materialIdentityIds`、
   `compositionRevisionIds`、`approvalIds`（plan/contract/
   candidate/composition source approvals）。报告级
   `evidenceIds` 现并入 gate evidence（metric 门禁自己的
   measurement 也计入）。
4. **依赖漂移即 reassessment**（requirement 4）：
   `reassessment_status` 遍历 manifest 全量 evidence 行（status 漂
   移 → stale；仅 supporting 集合 —— packet evidenceIds ∪
   evidenceSelection.includedIds ∪ gate evidenceIds —— 才算
   missing/applicability 漂移）；`changedDependencies` 新增
   `composition_changed`（formulation hash/status/completeness、
   reference product knowledge/version/currentRevisionId/rev
   hash、material_identity version 漂移）、`target_identity_changed`
   （版本/缺失）、`candidate_entity_changed` /
   `candidate_changed` / `candidate_withdrawn`、
   `approval_revoked`（manifest approvalIds 中任一 missing/
   revoked/decision≠approved/expired）。**applicable 翻转而
   integrity status 保持 accepted** 时同样触发
   `applicability_changed`（requirement 4 关键路径）。signed
   packet 本体永不改写 —— 历史 packet 原样保留。
5. **close 仍由服务端把守**（requirement 5）：`TaskService.close`
   的 `_success_evidence_gate` 对 `supported_success` 校验全部
   required metrics met + 全部 hard gates pass + 无 unbound
   evidence —— UI 按钮只是显示层；任何 gate `not_evaluated` /
   `fail` → `EVIDENCE_INSUFFICIENT`（`unprovenGates` 携带
   verdict）。未引入任何 blanket safety override。

## 回归测试（先红后绿）

`services/studio-api/tests/integration/test_par03_gate_failsafe.py`
（21 tests；实现前 21 红）：

- `TestAbsenceGateFailSafe`（10）：无 candidate / 无 entity link /
  无效 entity link / draft 配方 / 空成分 / completeness=draft /
  supplier-only 未解析行 / reference product 配方 unknown /
  basis=analytical / 空 materialIdentityId → 全部
  `not_evaluated` + 对应 finding kind + `inconclusive` +
  close 抛 `EVIDENCE_INSUFFICIENT`。
- `TestAbsenceGateVerdicts`（4）：已知禁用成分按 materialId /
  alias / identifier 命中 → `fail` + `excluded_ingredient_present`
  + `supported_failure` + close 拒绝；干净配方 → `pass` +
  `claimBasis=declared_composition` + `claimBound` 含
  "declared composition" 与 "not an analytical"。
- `TestGateEvidenceManifest`（1）：gate measurement 进
  `packet.evidenceIds`；manifest evidence 行含 method/
  pipelineVersion/status；`gateDependencies` 记
  materialIdentityId/compositionRevisionId/ContentHash/
  Completeness/candidateRevisionId；`dependencies` 记
  materialIdentityIds/compositionRevisionIds。
- `TestDependencyReassessment`（5）：gate-only measurement
  amend → `staleEvidenceIds` 精确命中（ordinary measurement
  不动、packet evidenceIds 不变）；applicability 撤回/翻转
  （status 仍 accepted）→ `applicability_changed`；formulation
  superseded → `composition_changed`；target identity 版本漂移
  → `target_identity_changed`；approval 撤销 →
  `approval_revoked` + `needsReassessment`。

## 既有测试适配（语义升级，非弱化）

- `tests/security/test_task_evaluation.py`（AT-0503）：
  `_candidate_with_banned` fixture 的 formulation 改为
  `accepted` + `completeness="complete"` + `declaredTotal` —
  旧 draft 配方在新语义下正确地 `not_evaluated`；
  `test_agent_cannot_close_even_when_eligible` 补建已评审的
  干净 candidate（registered water identity + accepted 配方 +
  `record_applicability` 绑定）—— absence claim 现在要求适用
  的 candidate 表征，「无成分数据」不再是 pass。断言路径不变。
- 评估器版本 `par-02.1` → `par-03.1`。

## 验证命令与结果（本分支）

| 步骤 | 命令 | 结果 |
|---|---|---|
| verify-core | `make verify-core` | 规格 52 tickets/156 cases、ruff、contracts、schema.graphql in-sync、unit **379 passed** |
| typecheck | `make typecheck` | mypy **230 files no issues**；tsc -b **OK** |
| 全量后端 | `uv run --no-sync pytest services/studio-api/tests tests -m 'not engine' --timeout 300` | **1154 passed / 3 skipped / 0 failed**（1157 collected） |
| 安全 | `make test-security` | **221 passed / 1 skipped** |
| 集成 | `make test-integration` | **396 passed / 1 skipped** |
| 前端 typecheck | `pnpm --filter studio-web typecheck` | relay 编译 + tsc **OK** |
| 前端单测 | `pnpm --filter studio-web test` | 9 files / **27 passed** |
| e2e | `make test-e2e` | **37 passed**（含 AT-0503-3 close journey、AT-0504-1/2/3、AT-1103-2） |
| 新增回归 | `pytest services/studio-api/tests/integration/test_par03_gate_failsafe.py` | **21 passed** |

## Migration / rollback 含义

- 无 DB migration：manifest 依赖信息全部落在 packet JSONB
  （additive 字段），signed packet 语义不变 —— 旧 packet 不重写、
  不迁移；`reassessment_status` 对旧 packet 兼容（无
  gateDependencies/approvalIds 字段时按空集合处理，仅保留原有
  measurement 漂移检测）。
- 回退本提交即恢复旧 gate 语义；无任何数据改写步骤需要回滚。

## 已知限制 / 保留行为

- `check.basis` 仅支持 `"declared"`；`"analytical"` 等明确拒绝
  （`basis_not_supported`）——分析级 absence 属 PAR 之外的能力，
  不可用配方数据冒充。
- 未注册 target identity 时 gate 仍按字面 materialId 匹配执行并
  记 `unknown` finding（`materialIdentityResolved=False`）——
  宁可给出有标记的判定也不静默放行。
- `blocks[]` 与 `claimBasis/claimBound` 为 additive 报告字段；
  CloseoutPanel 本轮未改 UI（JSON blob 直通，后续 ticket 可
  按需渲染）。
- PAR-04 聚合语义（`single`/`fixture-single-value`/`any(compare())`
  等）未动；PAR-05 provenance 未动。
