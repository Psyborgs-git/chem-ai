# PAR-06 — sign-in/logout + project create/select UI workflows

## Status

- **状态**: 完成。审计项「mounted application 只有 setup/signed-out
  提示语，没有正常 sign-in 面；ProjectsPage 无创建入口」已闭环：
  loopback first-run owner bootstrap、正常 sign-in、sign-out、
  session 过期回到 sign-in、project create/select 全部经 UI，
  不需要 DevTools 或手写 GraphQL。
- **Scope**: `apps/studio-web` 入口门 + auth 传输 + 项目创建表单 +
  e2e 回归。未新增认证机制 —— 复用既有 `/api/auth/*` REST 面与
  `studio_session` httponly cookie（server 管理，前端不读）。
- **未做（按约束）**: 无公开注册、无 cloud identity、无 LAN 部署
  改动（U07 未决）；authorization 仍在服务端；未触碰
  workplan.json。

## 实现内容

### 1. Auth/session 传输（relay/network.ts）

- `fetch`/`/graphql` 只允许在 `relay/network.ts`（§8.2
  check_relay_boundaries），因此 auth REST 调用全部收敛于此：
  `authSetupOwner`（POST /api/auth/setup）、`authSignIn`
  （/api/auth/login）、`authSignOut`（/api/auth/logout）。
  解析服务端 `{"errors":[{code,message,fieldPath,…}]}` 错误体，
  UNAUTHENTICATED/CONFLICT/VALIDATION/NETWORK 分型返回给表单。
- `probeViewer()`：经同一条 GraphQL 通道发 `{ viewer { id
  displayName } }` —— `extensions.code == UNAUTHENTICATED` →
  `signed_out`；拿到 displayName → `signed_in`；传输失败 → `error`
  （绝不把 backend 故障伪装成「未登录」误导已登录用户）。不新增
  API 面。
- 密码只在 POST body 内传递：不进 URL、不进任何浏览器持久化、
  不进日志；cookie 为 httponly，前端从不读它。

### 2. 入口面（features/auth/AuthScreens.tsx）

- `FirstRunScreen`（owner bootstrap）：只在 `/api/auth/setup-needed`
  报告无 owner 时渲染 —— 与服务端 setup gate 语义一致（第二次调用
  服务端返回 CONFLICT）。字段 login / display name / password /
  confirm password（≥10 与一致性先做客户端提示，服务端校验仍是
  权威）。CONFLICT → 诚实提示「owner 已存在，请用 sign-in」。
- `SignInScreen`：既有安装的正常入口；`expired` 变体在会话中途
  失效时显示「session ended — sign in again」。
- 两者都走窄 auth chrome（无导航 —— 未登录用户没有可打开的
  页面），TextField/Button/InlineFinding 与 `cs-*` 既有原子类，
  label 关联 + `role=alert` 错误 + disabled-in-flight，键盘可全程
  操作。无自造设计体系。

### 3. 入口门 + sign-out + 会话失效（routes/AppRoutes.tsx）

- Gate 状态机：`fetchSetupNeeded` → setup → `FirstRunScreen`；
  否则 `probeViewer` → `signed_out` → `SignInScreen`；
  `signed_in` → 挂载 shell（携带 displayName）；`error` →
  「Backend unreachable」如实报错。未登录永不挂 shell/nav。
- `QueryBoundary` 的 auth 分支由静态「Not signed in」文案改为
  渲染 `<SignInScreen expired />` —— 会话中途失效/丢失时原地给
  sign-in 面；URL 不动，登录成功后整页重载正好回到目标页面
  （intended destination 由此保留）。
- `SignOutControl`（shell header，紧邻身份文案与 theme toggle）：
  POST /api/auth/logout → `resetRelayEnvironment()` →
  `window.location.assign("/")` 硬重载。**选型说明**：选择了硬
  重载作为权威失效手段（清掉 Relay store、模块单例、router
  状态、所有在飞的 identity-scoped 缓存），`resetRelayEnvironment`
  覆盖重载落地前的间隙 —— 符合 §8.2 既有约定。
- header 显示「Signed in as {displayName}」，HomePage 旧的
  `ViewerQuery`/`ViewerStatus` 删除（身份展示收敛到 header，
  少一条重复查询）。

### 4. ProjectsPage create/select

- `ProjectCreateForm`（slug + name + description 可选）：提交
  `projectCreate`；服务端 VALIDATION/CONFLICT 经 `errors[]` 显示为
  InlineFinding；成功后直接 `navigate` 进新项目（create → select
  一步完成）。
- 列表改用 `fetchPolicy: "store-and-network"`：每次进页都向服务端
  重取（新建项目立刻可见）同时即时回放缓存 —— 选它而非
  `network-only`，因为后者在 vite dev + React 19 StrictMode 下会
  触发 PAR-01 (#27) 记录的无限重取（实测亲见：~157 次/graphql
  请求/分钟、页面停在 loading）。store-and-network 在有缓存后不再
  suspend，循环不成立。
- 项目「select」为既有链接；无 rename/edit 服务端入口（见限制）。

## Changed files

- `apps/studio-web/src/relay/network.ts` — auth REST 调用 +
  `probeViewer`（§8.2 单传输点内）。
- `apps/studio-web/src/features/auth/AuthScreens.tsx` — 新增：
  FirstRunScreen + SignInScreen + 窄 auth chrome。
- `apps/studio-web/src/routes/AppRoutes.tsx` — 入口门状态机、
  SignOutControl、QueryBoundary auth→SignInScreen、ProjectsPage
  挂 create 表单 + store-and-network、删除旧 ViewerStatus。
- `apps/studio-web/src/features/tasks/operations.ts` —
  `ProjectCreateMutation`。
- `apps/studio-web/src/features/tasks/ProjectCreateForm.tsx` —
  新增项目创建表单。
- `apps/studio-web/src/styles/components.css` —
  `.cs-shell__session` 一个类（header 身份文案）。
- `tests/e2e/par-06.spec.ts` — 新增：本 ticket 的 UI-only 回归。

## Acceptance tests

### PAR-06-A [e2e] 全新安装 → UI bootstrap → UI sign-in → project + 三种 mode 的 task → sign-out → 再 sign-in 数据仍在

`tests/e2e/par-06.spec.ts` 单条旅程（`studio_e2e` 在 beforeAll 里
重新 TRUNCATE —— 与 serve.sh 同模式、infra-only，保证「fresh test
installation」语义；creds 沿用共享 `e2e-owner`/`e2e-password-10`
使后续 spec 的 API helper 仍可登录）：

1. `GET /` → first-run owner 表单是唯一入口（无 nav）；
2. UI 填 login/display name/password×2 → Create owner account →
   落地已登录（header「Signed in as E2E Owner」+ Sign out）；
3. Sign out → Sign in 表单；错误密码 → 「not recognized」诚实
   报错不崩；
4. 正确 sign-in → shell；
5. 会话失效恢复：clearCookies 后 reload `/projects` → 原地
   Sign-in 面（URL 不变）；再 sign-in → 回到 `/projects`；
6. UI 建项目 `par06-proj` / `PAR-06 Project` → 直接进入项目页；
7. TaskCreateForm 各 mode 各建一个 task：improve /
   match_reference / discover → 均落地 `/tasks/<id>`；
8. Sign out → Sign in → Projects 列表点开项目 → 三个 task 链接
   全部在。

**结论**: `make test-e2e` 37/37 全过（par-06.spec 7.4s）——
required regression 全链路 UI 驱动，无 API helper 执行被测动作。

## 验证命令与结果

| 步骤 | 命令 | 结果 |
|---|---|---|
| verify-core | `make verify-core` | PASS（ruff、contracts sync、relay boundaries、unit 379 passed / 2.57s） |
| typecheck | `make typecheck` | PASS（mypy + `pnpm --filter studio-web typecheck`：relay 117 reader/115 normalization/117 operation + tsc -b 无错） |
| 前端 typecheck | `pnpm --filter studio-web typecheck` | PASS |
| 前端单测 | `pnpm --filter studio-web test` | PASS — 9 files / 27 tests |
| 前端构建 | `pnpm --filter studio-web build` | PASS（889kB chunk 警告为 CS-1103 既有） |
| e2e 全套 | `make test-e2e`（= `pnpm --filter studio-web exec playwright test --config ../../tests/e2e/playwright.config.ts`） | **37 passed**（1.5m），含新 spec par-06 |
| dev 手测 | vite dev + Chrome | bootstrap→shell→sign-out→错误密码报错→sign-in→project create 全链路截图验证 |

## 已知限制

- **无 project rename/edit**：schema 只有 `projectCreate`，无
  update/rename mutation —— 「edit」以 create→select 流程覆盖；
  服务端新增入口前不虚构 UI。
- signed-out 的 `probeViewer` 走既有 viewer resolver，服务端日志
  会留一条 `UNAUTHENTICATED: session required` traceback（与今天
  任何未登录 GraphQL 调用相同）；若嫌吵可后续加
  `GET /api/auth/me` 便宜探测，本 ticket 不新增 API 面。
- 密码强度只有服务端 ≥10 校验 + 客户端同样提示；无强度表、无
  rate-limit UI（服务端既有语义未变）。
- first-run 表单只在 `setup-needed=true` 时出现；owner 已存在时
  该入口不存在 —— 这是刻意的（secure bootstrap ≠ public signup）。
- 会话 TTL 由服务端 `session_ttl_seconds` 决定，UI 不显示倒计时；
  到期后下一次查询自然落到 SignInScreen（expired）。
