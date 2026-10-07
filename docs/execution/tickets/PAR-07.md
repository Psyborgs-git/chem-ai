# PAR-07 — materials/formulation/candidate 真实工作流 + pickers + diffs

## Status

- **状态**: 完成。Audit §PAR-07 的全部要求落地：所有 baseline/
  reference/material 选择改为按名搜索的 picker（正常工作中再无任何
  原始 UUID 文本输入）；结构化配方编辑器产出真实 formulation
  revision payload；candidate 对 baseline 的成分级/工艺级 diff 渲染
  （added/removed/changed，非 JSON dump）；被接受的 revision 以精确
  uuid 绑定进 manual experiment plan。
- **Nav**: Materials & Products 主链**已恢复** —— 指向真实存在的
  `/materials` registry 页（identities/grades/reference products/
  formulation families 四个真实查询驱动的区块），不是死链
  （CS-1201 允许的条件即此）。cs-1201.spec.ts 断言已更新为“链接
  存在且落地于真实页面”。
- **依赖**: PAR-01..06 已在 main 上；本 lane 在其上构建。PAR-06 的
  登录 UI 未在 e2e 中依赖（helper 仅 bootstrap auth/project）。

## 实现内容

### 1. 后端：registry 搜索查询 + formulations mutation 组（schema.py/types.py）

- 新增 Query fields（均 keyset connection、CAP_READ_PROJECT、
  scope_signature 隔离）：
  `materialIdentities(search)`、`materialGrades(materialId,search)`、
  `referenceProducts(search)`、`referenceProductRevisions(productId)`、
  `formulationFamilies(search)`、`formulationRevisions(familyId,search)`
  （familyId 缺省时为跨 family 搜索 —— 按 family 名或 payload
  ilike 匹配，node 携带 `familyName`，供 baseline picker 直接按
  “配方名”搜索）、`processRevisions(familyId)`；`nodes(ids:)` 可读
  FormulationRevision/ProcessRevision（含 `parentRevisionId` —
  baseline 关系的唯一事实来源）。
- 新增 `formulations` mutation 组（CAP_EDIT_TASK）：
  `familyCreate`、`revisionDraft`（payload 原样入库 + malformed
  amount 记为 `invalid_amount` validationFinding，绝不静默改写）、
  `revisionAccept`（declared-total gate：completeness=complete +
  ≥1 ingredient + declaredTotal 在 tolerance 内才可通过；
  accept 新 rev 时旧 accepted → `superseded`）、`processDraft`、
  `processAccept`（order-significant 步骤签名，AT-0204-3）。
- `quantities.py`：补 `check_declared_total`/`Quantity` 对
  `{value, unit, basis}` 量纲与 concentration-without-basis 的
  完整性判定（accept gate 复用，不虚构科学默认）。
- `packages/contracts/schema.graphql` 经
  `infra/ci/export_schema.py` 重新生成并通过 `--check`。

### 2. 前端：`features/registry/` 新模块

- `operations.ts`：7 查询 + 5 mutation（Relay 命名与文件 stem
  对齐，codegen 130 ops）。
- `pickers.tsx`：`MaterialIdentityPicker`、`ReferenceProductPicker`、
  `FormulationRevisionPicker({statusFilter})`、`CandidateRevisionPicker`
  （仅列 accepted_for_research）、`ContractRevisionPicker`（frozen/
  accepted）。统一 `PickerShell`（combobox + `aria-expanded`/
  `aria-controls` + 选中态 “change” 按钮）+ `PickerList`
  （`role=listbox/option`）+ 250ms debounce + `network-only`
  fetch；全部**按名/标识符搜索**，选择回传 `Picked{globalId,uuid,
  label}`，UI 内永不出现可编辑的 uuid 输入框。固定列表 picker 的
  输入框 `readOnly`（仅作 listbox launcher，不假扮过滤）。
- `FormulationEditor.tsx`：成分行编辑器（name + material picker
  链接 + amount DecimalField + unit/basis UnitSelect + role），
  `amountBasis`/`declaredTotal`/`tolerance`/`completeness` 元字段；
  “copy parent contents into the editor” 从 latestAccepted payload
  水合行（`rowsFromPayload`）；保存走 `revisionDraft`
  （`parentRevisionId` 以 GlobalID 编码、每调用唯一
  `idempotencyKey`），validationFindings 如实呈现。
- `diff.ts` + `RevisionDiff.tsx`：纯函数 `ingredientDiff`
  （materialId/alias/name 键控、顺序无关 → added/removed/changed/
  unchanged + 字段级 change 描述）、`metaDiff`
  （declaredTotal/amountBasis/tolerance/completeness/
  processRevisionId）、`processStepDiff`（位置对齐、order 显著）；
  `RevisionDiff{baselineUuid, candidateUuid}` 自动经
  `nodes(ids:)` 解析 candidate 的 `parentRevisionId` 为 baseline
  （candidate payload 不存 baseline —— 谱系在 revision 上）。
- `MaterialsPage.tsx` + `FamilySection.tsx`：`/materials` 页四区块
  （identities 搜索/创建/structure-review；grades 搜索/创建 +
  activeContent；products 搜索/创建 + revision draft/freeze +
  `compositionKnowledge` 诚实展示 “unknown stays unknown”；
  families 搜索/创建 + 详情：revision 列表（status badge/
  payloadSummary/findings/accept/“diff vs parent”）+
  FormulationEditor + ProcessEditor + ProcessRevisionList）。
  全部 fetchKey+network-only 重取、EmptyState/LoadingState/
  InlineFinding 如实状态。
- `TaskCreateForm.tsx`：baseline `FormulationRevisionPicker`
  （`statusFilter="accepted"`）+ reference `ReferenceProductPicker`
  —— 两个 uuid 文本输入删除。
- `CandidatePanel.tsx`：propose 表单绑 entity revision
  （formulation/material picker → `entityRevisionId` uuid）+
  proposedDifferences；row 展示 status/eligibility/child-of/
  DifferencesList + “view diff vs baseline”（formulation kind →
  entityRevisionId → RevisionDiff）+ “view content”（revision
  comparison，AT-0206-3 保留面）+ submit→review(accept:true/
  reject:false) 动作 + accepted 态 “link into Lab”。
- `PlansPanel.tsx`：PlanCreateForm 重写为结构化表单（title +
  CandidateRevisionPicker + ContractRevisionPicker + method +
  batch count→samplePlan + 可选 acceptanceCriteria/hazardNotes/
  resourceNeeds）—— PAYLOAD_TEMPLATE JSON textarea 删除。
- `AppRoutes.tsx`：`/materials` 路由 + NAV “Materials & Products”
  恢复（真实 surface 已存在，CS-1201 条件满足）。

### 3. 规则遵守

- 未编造任何科学内容：配方/工艺数据全部来自 UI 输入或既有
  payload；unknown recipes 保持 unknown（products 区块只如实展示
  `compositionKnowledge`，创建表单默认 `unknown`）。
- Candidate payload 仍仅 `{proposedDifferences, evidenceIds}`；
  baseline 经 revision `parentRevisionId` 解析，不伪造 payload
  字段。

## Changed files

- `services/studio-api/src/studio/api/graphql/schema.py`（7 查询 +
  formulations mutation 组）
- `services/studio-api/src/studio/api/graphql/types.py`
- `services/studio-api/src/studio/domain/materials/quantities.py`
- `packages/contracts/schema.graphql`（schema-export 再生成，1849 行）
- `services/studio-api/tests/integration/test_par07_registry.py`（新，7）
- `apps/studio-web/src/features/registry/`（新模块：operations.ts /
  pickers.tsx / FormulationEditor.tsx / MaterialsPage.tsx /
  FamilySection.tsx / RevisionDiff.tsx / diff.ts / diff.test.ts）
- `apps/studio-web/src/features/tasks/TaskCreateForm.tsx`
- `apps/studio-web/src/features/candidates/CandidatePanel.tsx`（重写）+
  `operations.ts`（entityRevisionId）
- `apps/studio-web/src/features/lab/plans/PlansPanel.tsx`
- `apps/studio-web/src/routes/AppRoutes.tsx`（/materials + nav）
- `tests/e2e/par-07.spec.ts`（新，1 长回归）
- `tests/e2e/at-0206.spec.ts`（AT-0206-1 picker 化 + AT-0206-3
  断言作用域）
- `tests/e2e/cs-1201.spec.ts`（nav 断言更新为“链接存在且真实”）

## Acceptance tests

### PAR-07-A [e2e] required regression（逐字覆盖）

`par-07.spec.ts` 单测一条链走完全部要求 —— **除 auth/project
bootstrap 外全部 UI 驱动，无任何一步从 SQL 复制 uuid**：

1. `/materials` UI 注册 3 个 material identities（合成数据，
   “允许合成的 baseline”）；
2. formulations 区块 UI 建 family → FormulationEditor 录入
   water 70/resin 30、declaredTotal 100、complete → save →
   “accept revision” → rev 1 `accepted`（allowed synthetic
   baseline）；
3. `/projects/:id` TaskCreateForm `improve` —— **baseline 按名
   搜索选中**（combobox 输 `par07-… base coat` → listbox 点
   “rev 1 · accepted”，回写 canonical uuid）+ variationScope →
   create → `/tasks/:id`；
4. 回 `/materials` family → “copy parent contents” → 改
   water→65、加 coalescent 5 → save rev 2 → accept（继承
   parentRevisionId=rev1 → baseline 关系真实落库）；
5. `/tasks/:id` candidates tab → propose（hypothesis +
   proposedDifferences + entity revision picker 选
   “rev 2 · accepted”）→ submit → “accept for research” →
   `accepted_for_research`；
6. “view diff vs baseline” → `[data-field=ingredient-diff]`：
   `tr[data-status=changed]` 唯一且含 “value: 70 → 65”、
   `tr[data-status=added]` 含 coalescent、`unchanged` 1 行 ——
   渲染 diff 非 JSON dump；
7. `/lab` → plan 表单选该 accepted candidate revision +
   method/batches → create → submit → 填 rationale → approve →
   “export manual packet” → `MANUAL EXECUTION` 徽章 +
   `candidate-revision` 绑定非空（exact accepted revision 已链入
   manual experiment plan）。

### PAR-07-B [integration] registry 查询 + accept gate

`test_par07_registry.py` 7 例：identity 按名/标识符搜索、product
搜索 + revision feed、workspace 隔离、family draft→accept +
process draft→accept roundtrip、malformed amount 记
`invalid_amount` finding 且不可 accept、parent 跨 family 拒绝、
跨 family 搜索返回双 revision + familyName。

### PAR-07-C [unit] diff 纯函数

`diff.test.ts`：ingredientDiff 的 added/removed/changed/unchanged
四态、键控顺序无关、amount 数值变化 → changed detail、metaDiff、
processStepDiff 位置语义。

### 既有规格适配（PAR-07 删除的旧行为）

- `at-0206.spec.ts`：AT-0206-1 改为经 picker 选 baseline/
  reference（fixture 经 gql seed，UI 动作仍是真）；AT-0206-3
  断言收进 `rows`/comparison group（picker 选项引入重名）。
- `cs-1201.spec.ts`：nav 断言从 “无 Materials & Products 链”
  更新为 “链接存在且点击落地真实 /materials 页”。

## 验证命令与结果

| 步骤 | 命令 | 结果 |
|---|---|---|
| verify-core | `make verify-core` | PASS（ruff 全绿；contracts 一致；schema.graphql in sync；relay boundaries 100 files；contract mirrors in sync；unit **379 passed**） |
| typecheck | `make typecheck` | mypy 230 files no issues + `pnpm --filter studio-web typecheck`（relay 130 ops + tsc）OK |
| 前端 typecheck | `pnpm --filter studio-web typecheck` | OK |
| 前端单测 | `pnpm --filter studio-web test` | 10 files / **33 passed** |
| 前端构建 | `pnpm --filter studio-web build` | OK（chunk-size 警告为既有，非新引入） |
| e2e | `make test-e2e`（playwright 37 specs） | **37 passed**（1.6m，含 par-07.spec.ts 12.5s） |
| 后端集成 | `make test-integration` | **370 passed / 1 skipped**（4:55；修复后重跑 par07 文件 8/8） |
| 新增集成 | `pytest tests/integration/test_par07_registry.py` | **8 passed**（含 canonical fraction 正反例） |

## 后续修复（live e2e 走查发现）

- 浏览器实测发现 `_validate_payload` 的 `fraction_out_of_range` 把
  `mass_percent` 原始值（70）与 [0,1] 比较 → 每个合法配方都误报
  警告。已修：比较 `q.convert("mass_fraction")` 的 canonical 值，
  150% 仍会如实 flag（detail 含 canonical 与原始输入）。新增
  `test_fraction_range_check_uses_canonical_value` 正反例。

## 已知限制

- 跨 family 搜索以 `ilike` 匹配 family 名/payload 文本（first=50
  截断）；超页容量时 pageInfo.hasNextPage 如实置位，前端 picker
  未做翻页（搜索缩小范围即可），不虚构“已列全”。
- Candidate→entity 绑定仅 formulation/material 两类 picker；
  molecule 走 MaterialIdentityPicker 以外的值仍需后续 ticket
  （propose 表单 kind 选择即如实暴露此边界）。
- baseline picker 按 `status=accepted` 过滤 —— 被 supersede 的
  历史 revision 不作为新 task baseline 候选（e2e 顺序即按此
  业务语义编排：先建 baseline task，再 draft successor）。
- Process diff 渲染为位置对齐表（order 显著签名内置于 domain）；
  跨步的重排以多行 changed 呈现，未做 LCS 最小编辑距离。
