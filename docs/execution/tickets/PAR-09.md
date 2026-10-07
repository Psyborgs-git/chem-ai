# PAR-09 — primary task navigation + deep links + Relay consistency

Parity continuation PAR-09（audit
`docs/execution/audit/2026-10-parity/CHEMISTRY_STUDIO_PARITY_AUDIT.md`
§PAR-09）。TaskWorkspace 此前是 13 个平铺 section（button 驱动的
`useState` 视图切换，刷新/后退/深链全部丢失上下文，且不反映
contract/workflow 状态）；home 是装饰性欢迎页。本 ticket 将任务工作
区重组为审定的六个主组 + advanced 渐进披露，group/subview 全部进入
URL，并补齐 Relay 分页与诚实状态。

## Status

- **状态**: 完成（6 组导航 + URL 状态 + 上下文头部 + home 真实数据 +
  三处列表 Relay 分页 + mutation 连接更新；47/47 e2e 全绿，其中新增
  par-09.spec.ts 9 条覆盖全部要求回归）
- **Baseline**: `origin/main` @ `80c6db5`（PAR-01..08 已落地）
- **依赖**: 无 schema 之外的新 infra；新增 `Query.tasks` 一个解析器

## 实现内容

### 后端（services/studio-api）

- `api/graphql/schema.py`：新增 `Query.tasks(workflowState: String,
  first/after)` —— workspace-scoped、keyset 分页
  `(created_at DESC, id DESC)`，供 home 的 recent tasks /
  pending decisions 列表用（`workflowState="awaiting_review"`）。
- `packages/contracts/schema.graphql` 经 `make schema-export` 重新
  导出。

### 前端（apps/studio-web）

#### 导航重组（features/tasks/TaskWorkspace.tsx 重写为壳层）

- 六个主组 `overview/research/candidates/experiments/evidence/
  decisions` + `advanced` 渐进披露桶（runs/datasets/training/models/
  evaluations/optimization/analysis 七个既有 panel 原样映射，**未改
  panel 内部逻辑**）。subview 表：experiments→plans/results，
  evidence→claims/source quality，decisions→decision log/closeout/
  report，advanced→七项。
- 路由 `/tasks/:taskId/:group?view=<subview>`（AppRoutes 新增带
  group 段的路由）；无效 group → `<Navigate>` 回 overview。group nav
  与 subview nav 都是真 `<a>`（`nav[aria-label="task sections"]` /
  `nav[aria-label="section views"]`，`aria-current="page"`）——刷新、
  后退、深链全部恢复上下文。
- **持久上下文头部** `.cs-task-context`：objective、mode/cycle
  badges、project 链接、selected contract revision/status
  （`data-field="contract-state"`）、blocking questions/rejected
  claims/needs-reassessment 聚合（`aria-label="blockers"`）、next
  authorized action —— 全部由 `TaskDetailQuery` 扩展字段真实推导
  （workflowState + contract status + candidate/plan statuses +
  reassessment flag），并带跳转链接；不是装饰。

#### Home 真实数据（features/home/，新）

- `homeWorkspaceQuery`：`tasks(first:8)` 最近任务 +
  `tasks(workflowState:"awaiting_review", first:20)` 待决项；渲染为
  `data-field="pending-decisions"` / `data-field="recent-tasks"`
  真链接（深链到 `decisions?view=closeout` / `overview`）。替换原
  装饰性 stub。

#### Relay 一致性（§8.2 patterns）

- `CandidatePanel_list`、`EvidencePanel_claims`、
  `DecisionsPanel_list` 三个 fragment 改为 `@argumentDefinitions` +
  `@refetchable` + `@connection` + `usePaginationFragment`：
  pageInfo 驱动 "load more"（page size 20），
  `loadNext(n,{onComplete:e=>…})` 错误经共享
  `components/molecules/PaginationControls`（role=alert + retry）
  呈现——不再是吞掉的错误。
- `CandidateRevisionPickerQuery`：registry picker 需要的非分页查询
  独立成自己的 operation（fragment 化后不能再借道），
  `fetchPolicy:"network-only"` 保留。
- **mutation 连接更新**：`candidatesCreateMutation` 新增
  `updater`——经 response `candidate.id` → `store.get` +
  `ConnectionHandler.getConnectionID/insertEdgeBefore` 把新 edge
  同步插入分页连接。修复一个真实竞态 flake：onCompleted 里的
  setState 可触发兄弟组件 suspense→边界 remount→丢掉 in-flight
  `refetch`（par-07 曾 3 分钟超时两次）；现在 edge 在 commit 时即
  落 store，refetch（`network-only`，CS-1201 修正保留）只是补充
  完整字段。无第二个 server-state cache——全部是 Relay store
  规范路径。
- `infra/ci/check_relay_boundaries.py`：`fetch\(` 正则误伤
  `refetch(`（Relay API 不是 transport）→ 改为 `(?<!re)fetch\(`。

#### 诚实状态（沿用既有机制，未发明新层）

- ContractEditor `useSaveState`：dirty/saving/saved/conflict/
  read_only_revision 照旧；API 断线时 `lastError` 如实报 "save
  failed — API unreachable or rejected; not persisted"，无
  saved-offline 谎报（at-0206 模式，par-09 spec 有独立 outage 回归）。

### e2e

- 新增 `tests/e2e/par-09.spec.ts`（9 条）：bare→/overview 跳转、
  group/subview 深链、refresh/back、无效 group 回退、advanced 深链；
  上下文头部 objective/contract/gaps/next action（含 freeze 后动作
  变化）；candidates+claims 各 seed 25 条跨页分页；sourceRevoke →
  刷新后 superseded；外部并发 contract freeze → 界面如实显示拒绝
  并更新状态；route-abort 断网保存 → "not persisted" + 恢复后重试
  成功；home 待决项/最近任务链接；1280px 小屏；纯键盘走完全部
  group/subview。
- 既有 11 个 spec 的平铺 button 选择器更新为真链接 + 双跳导航
  （at-0206/0304/0406/0503/0504/cs-1201/par-01/07/08a/08b），且
  group/subview 点击按 `nav[aria-label=…]` 作用域定位，避免与上下
  文头部的 next-action 链接发生子串误匹配；at-1103 键盘遍历适配
  link nav（focused() 描述器加 `inSubNav`/`current`）。

## Acceptance tests（PAR-09 要求回归清单）

- [x] deep links / back / refresh（par-09 spec 1–3：每个主组可深链）
- [x] 超过一页的 candidates / evidence 分页（spec 4：25 条 → 20 +
      load more → 25）
- [x] source-revocation 后列表如实刷新（spec 5）
- [x] 冲突的 contract 编辑（spec 6：外部 freeze → freeze 拒绝提示 +
      状态更新）
- [x] save 时 API outage → 如实 unsaved，无假 offline 声明（spec 7）
- [x] ~1280px 小屏（spec 8）+ 纯键盘完成（spec 9 + at-1103 回归）
- [x] 无新增视觉重设计 / 无虚构设计参考——复用 `.cs-tab`、Badge、
      section landmarks 既有 atom
- [x] home 是真实 recent tasks / pending decisions，非装饰 dashboard

## 验证命令与结果

```
make verify-core        → 385 passed（unit+contracts+lint，relay
                          boundaries 检查绿）
make typecheck          → relay 138 reader/133 normalization/141
                          operation + tsc + pyright 全绿
pnpm --filter studio-web typecheck → clean
pnpm --filter studio-web test      → 33 passed (10 files)
pnpm --filter studio-web build     → ✓ built (vite preview 同源)
make test-e2e           → 47 passed（含 par-09.spec.ts 9/9）
```

## 已知限制

- group 切换是整页 `QueryBoundary` remount（ShellContent 按 pathname
  key），DOM focus 会丢；键盘 spec 以 `aria-current` 断言当前组而
  非焦点位置。视作既有 shell 语义，非本 ticket 新增缺陷。
- mutation updater 插入的 edge 节点只含 mutation 选择的字段
  （id/revision/status/eligibility）；紧随的 `network-only` refetch
  补齐其余 fragment 字段。若 refetch 被 remount 丢弃，行仍在但部分
  字段空到下一次 fetch——只影响同一 tick 内的首屏呈现。
- advanced 组内七个 panel 为原样映射；其内部的 schema 缺失面板
  （例如 training/models 尚无查询）维持原状如实提示，未在
  PAR-09 虚构接口。
