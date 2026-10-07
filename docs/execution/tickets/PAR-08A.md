# PAR-08A — session/task stream 恢复：重试、终止状态、快照对账

Parity continuation PAR-08 的流恢复部分（audit
`docs/execution/audit/2026-10-parity/CHEMISTRY_STUDIO_PARITY_AUDIT.md`）。
Composer（发送/执行/取消）属 PAR-08 后续 lane，本 ticket 只交付
SessionStream 与 RunsPanel 的真实恢复语义。

## Status

- **状态**: 完成（实现 + vitest 9/9 + e2e 3/3 + AT-0406 回归 3/3 全绿）
- **Baseline**: `origin/main` @ `3c8c2cb`（含 #23 audit 包、#24 CI job）
- **依赖**: 无（前端独立 lane；与 PAR-01..05 后端链无文件冲突）

## 审计指认的缺口（复核属实）

1. `SessionStream` 对 `/api/events/snapshot` 只做一次性 `.catch(() =>
   setLive(false))`：首次快照失败即永久静默 dead——无重试、无状态区分、
   不自愈。
2. EventSource 对非 2xx 关闭（401/403/404）只抛一个不携带状态码的
   `error` 事件，客户端无法区分"网络抖动"与"权限撤销/会话失效"；旧实现
   一律显示 `reconnecting…`，把 revoked/expired 伪装成临时断线。
3. 注释声称"reconnect 时按 maxSeq 对账"，实际 `onOpen` 只翻 badge，
   不重取快照——浏览器丢弃 `Last-Event-ID` 或断线期间产生的事件
   不会被补偿。

## 实现内容

### `apps/studio-web/src/features/research/stream.ts`

- `classifySnapshotError`：把快照响应中的状态码映射为
  `unauthenticated`(401)/`forbidden`(403)/`not_found`(404)/`transient`
  （其余与网络错误）。
- `retryDelayMs`：有界指数退避（500ms·2^attempt，封顶 30s）。
- `streamClosed(source)`：以 `readyState === 2` 判断永久关闭
  （jsdom 无 `EventSource` 常量，禁用 `EventSource.CLOSED`）。
- 原 `openStream`（`?since=` + `Last-Event-ID` + heartbeat 看门狗 +
  `STUDIO_EVENT_MAX_SECONDS` 有界连接）不变——服务端 SSE 本身已正确，
  缺口全部在客户端。

### `apps/studio-web/src/features/research/SessionStream.tsx`

- 生命周期改为**对账循环**：每次（重）连与每次永久关闭都重新
  `fetchEventSnapshot`，按 `maxSeq` 推进 `lastSeq` 后再以 seq 游标
  续订——覆盖浏览器丢 cursor、断线期间间隙两类缺口。
- 快照失败按 `classifySnapshotError` 分流：
  - `transient` → `snapshot unavailable — retrying` + 退避重试；
  - 401 → `sign-in required`、403 → `access revoked`、404 →
    `session not found`：**终止态**，停止重试并清空已渲染消息
    （revocation-aware clearing，不把过期内容当作 live 状态展示）。
- `onOpen` 同时触发一次快照重取（对账）；`onError` 仅在 socket
  永久关闭时触发探测式对账——网络抖动交由 EventSource 自带重连，
  不重复开口。messageId 去重与 seq 续订保持原语义。
- Badge 状态诚实化：connecting/live/reconnecting/unavailable/
  sign-in required/access revoked/not found，不再一律
  "reconnecting…"。

### `apps/studio-web/src/features/runs/RunsPanel.tsx`

- 同样接入快照探测分类：transient → `updates unavailable —
  retrying` + 退避；终止（401/403/404）→ `updates ended`，不再无限
  伪装重连。
- **保留原有 `onOpen` → 去抖 refetch 语义**（权威快照重取防重复/
  复活），仅叠加失败分类与重试治理。

### 测试

- `src/features/research/SessionStream.test.tsx`（vitest，9 例）：
  分类映射、退避上界、closed 判定、快照→live、transient 首败
  500ms 真实退避后自愈、403 终止且消息清空且零重试、快照+流双通道
  同 id 去重、永久关闭→探测→重开口（携带新 `maxSeq`）、关闭后探测
  403→终止。
- `tests/e2e/par-08a.spec.ts`（playwright，3 例，真实 FastAPI + vite
  preview + 隔离 `studio_e2e` 库）：
  1. 路由拦截 snapshot abort → 显示 retrying 而非假 live；解除后
     消息出现并转 live。
  2. snapshot+stream 双双 403 → `access revoked` 终止态，已渲染内容
     清空，不再重试。
  3. 仅 abort stream 端点（查询层不受影响）→ `reconnecting…` 诚实
     显示，解除后自行恢复 live，run 状态不丢不重。

## Acceptance tests（PAR-08 流恢复回归清单）

- [x] 首次快照失败：可恢复（e2e-1）而非一次性死亡
- [x] 断线/重连不重复：messageId 去重 + seq 续订（vitest dedup 例 +
      AT-0406-1 回归通过）
- [x] 取消 in-flight turn：AT-0406-3 回归通过（本 ticket 未改动该路径）
- [x] revoke 源访问：403 → access revoked + 清空渲染 + 零重试
      （vitest + e2e-2）
- [x] expired/forbidden 终止态与 transient 区分（分类器 + 两种 badge）
- [x] 保留 RunsPanel onOpen-refetch（未删改，仅加分类）

## 验证命令与结果

```
pnpm --filter studio-web exec vitest run src/features/research/SessionStream.test.tsx
  → 9 passed (9)
pnpm --filter studio-web test        → 27 passed (9 files)
pnpm --filter studio-web typecheck   → relay + tsc -b clean
pnpm --filter studio-web exec playwright test --config \
    ../../tests/e2e/playwright.config.ts par-08a.spec.ts
  → 3 passed (21.8s)
同命令 at-0406.spec.ts → 3 passed（reconnect/dedup/cancel 无回归）
```

## 已知限制 / 边界

- 查询层（Relay `network-only`）在断线瞬间若有 in-flight refetch，
  会被路由级 error boundary 捕获为 `Failed to fetch`——这是全应用统一
  的失败语义（诚实、非假 live），恢复需 reload；属 PAR-09/全局 UX 范畴，
  不在本 ticket 修改。
- "retention gap"：服务端 outbox 不淘汰（`events/routes.py` 无 prune），
  seq 游标续订天然覆盖；快照对账仍保留作为 browser-drop-cursor 防线。
- Badge 文案为最小诚实集合，未引入新视觉设计。
