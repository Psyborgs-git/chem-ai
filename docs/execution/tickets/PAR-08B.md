# PAR-08B — real research composer：turn request / cancel 接入

Parity continuation PAR-08 的 composer 部分（audit
`docs/execution/audit/2026-10-parity/CHEMISTRY_STUDIO_PARITY_AUDIT.md`
§PAR-08：stream 恢复部分见 PAR-08A）。ResearchPanel 此前只能
start/end session 与记录 question，无 composer、无 turn 入口。

## Status

- **状态**: 完成（mutation + runner cancel + composer UI；集成 7/7、
  e2e 2/2、AT-0406/0405 回归全绿）
- **Baseline**: `devin/1791332166-par08a-stream-recovery`（PAR-08 的
  stream 一半与 composer 同一 ticket，同一分支交付）
- **依赖**: CS-0405 已有的 `AgentTurnRunner` / closed tool catalog /
  `TurnBudget` / `LlamaCppRuntime` ——本 ticket 只接 GraphQL + UI 两条
  断线，未新建推理层

## 实现内容

### 后端（services/studio-api）

- `application/agent_tools/turn.py`
  - `run_turn(session_id, user_text, *, turn_id=None,
    cancel_check=None)`：用户消息**先持久化**（refs 携带
    `turn_id`），再做 runtime 检查——model 不可用时问题仍是 durable
    session 记录（AT-0405-3 语义不变）。
  - `cancel_check` 在每个 tool-loop 迭代头与 loop 收尾处求值；
    命中 → assistant `kind=message` `refs={turn_id, cancelled:true}`
    + `finished_reason="cancelled"`。无新表、无 migration——取消
    marker 复用 `session_messages`（kind=message, refs 任意 JSONB）。
- `api/graphql/schema.py`
  - `research.turnRequest(input: {sessionId, content, turnId,
    idempotencyKey, clientMutationId})`：客户端铸造 `turnId`
    （composer 在请求未返回前即可取消）；经 `_mutate` 幂等
    （`turn:<turnId>` fallback key），同步执行有界 turn，返回
    `finishedReason/finalMessage/toolCalls/detail`。
  - `research.turnCancel(input: {sessionId, turnId, ...})`：持久化
    `refs={turn_cancel: turnId}` 的 user 消息（"cancel requested"），
    running turn 在下一次迭代头部观察到即终止；迟到 cancel 是无害
    durable 记录而非 error。
  - `packages/contracts/schema.graphql` 重新导出（CI `schema --check`
    同步）。

### 前端（apps/studio-web）

- `features/research/operations.ts`：`TurnRequestMutation` /
  `TurnCancelMutation`（Relay 生成类型同步）。
- `features/research/ResearchPanel.tsx`：新增 `Composer`，挂在 active
  session 的 stream details 内（ended session 无 composer）：
  - send → `turnRequest`；请求 in-flight 时按钮变为 `cancel turn` →
    `turnCancel` → `cancel requested…`；
  - 结果诚实分流：`model_unavailable` → warning badge "model
    unavailable — …; the question is recorded and manual work is
    unaffected"；`cancelled` → "turn cancelled"；非 `final` 的
    `budget`/`error` 带 detail 展示；`errors[]` → role=alert。
  - 不渲染占位回复、不暗改合同、不调用任何 UI 之外的服务——composer
    走的就是 `research.*` mutation（与 UI 同一 versioned surface）。
- `SessionStream` 的 `MessageView` 已覆盖 `tool_call`/`tool_result`/
  `proposal`/`rationale`/`message`——turn 产物（含 cancel marker 与
  cancelled 记录）如实渲染，无需新增样式。

## Acceptance tests（PAR-08 composer 回归清单）

- [x] UI send → 持久化 user message + 可见 outcome（e2e-1）
- [x] model unavailable → 真实可操作状态，非合成回复
      （e2e-1 断言 assistant 消息数为 0；integration-1）
- [x] cancel in-flight turn → durable marker + runner 迭代间终止
      （e2e-2 + runner 单测 ×2）
- [x] 幂等：同 turnId+key 重放不重复发帖（integration-2）
- [x] ended session → CONFLICT（request 与 cancel 两侧）
- [x] tool catalog 无 approve/export/promote/close 动词（CS-0405 既有
      边界，未放宽）

## 验证命令与结果

```
uv run --no-sync pytest services/studio-api/tests/integration/test_turn_request.py
  → 7 passed（unavailable+持久化 / 幂等 / ended-CONFLICT /
    cancel marker durable / ended-cancel-CONFLICT /
    预置 cancel→cancelled / 首轮后 cancel→工具后终止）
uv run --no-sync pytest test_agent_turn.py test_turn_request.py test_agent_tools.py
  → 17 passed（AT-0405 全部回归通过）
uv run --no-sync mypy turn.py schema.py        → clean
pnpm --filter studio-web typecheck             → relay + tsc clean
pnpm --filter studio-web exec playwright test par-08b.spec.ts
  → 2 passed（send→持久化+unavailable；延迟请求→cancel→marker）
```

## 已知限制

- 无本地 model runtime 的环境（含 e2e/CI）只能验证到
  `model_unavailable` 与 cancel 语义；真实模型 turn 的 live 验证仍在
  `tests/engines/test_inference.py`（engine tier，U08/U13 gated）。
- turn 同步执行（≤ `TurnBudget.wall_seconds`=300s）——turn 内消息在
  请求事务提交后一次性进入 outbox/stream；逐步流式 tool 输出不在本
  ticket 范围。
- 取消在 tool-loop 迭代边界生效：单次 `runtime.generate` 内的取消
  需要 runtime 侧中断协议，llama.cpp server 未提供——如实标注为
  per-iteration，不声称即时打断。
