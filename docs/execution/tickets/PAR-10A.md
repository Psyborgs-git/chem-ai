# PAR-10A — bounded Playwright e2e + frontend production build CI jobs

Parity continuation PAR-10 的 CI 脚手架部分（audit
`docs/execution/audit/2026-10-parity/CHEMISTRY_STUDIO_PARITY_AUDIT.md`）。
浏览器旅程/对抗性评估用例属于 PAR-10 后续 lane，本 ticket 只交付两个
CI 任务与确定性产物路径。

## Status

- **状态**: 完成（两个新 CI job 定义 + 本地全量验证通过）
- **Baseline**: `origin/main` @ `117212e`（含 #23 audit 包落库）
- **依赖**: 无 — CI 脚手架独立于 PAR-01..05 业务修复

## 实现内容

### `frontend-build` job（`.github/workflows/ci.yml`）

- `pnpm install --frozen-lockfile` + `pnpm --filter studio-web build`
  —— `build` 脚本本身即 `pnpm relay && tsc -b && vite build`，真实
  生产构建（relay codegen + 类型检查 + rolldown 打包），与 e2e
  webServer 的 preview 前置相同，但独立成 job 可在无浏览器环境下
  快速暴露 build 断裂。
- `timeout-minutes: 15`；沿用 workflow 级 `permissions: contents: read`
  与 `concurrency: cancel-in-progress`（PR ref 组）。

### `e2e` job（`.github/workflows/ci.yml`）

- `uv sync --group dev --frozen` + `pnpm install --frozen-lockfile` +
  `pnpm --filter studio-web exec playwright install --with-deps chromium`
  + `make test-e2e`。
- 不需要 `services:` postgres —— `tests/e2e/serve.sh` 经
  `docker compose` 自带 postgres 容器、创建并 TRUNCATE `studio_e2e`
  隔离库（每次运行全新世界），runner 自带 docker。这是与本地完全相同
  的真实路径，不为 CI 发明第二条路径。
- `timeout-minutes: 30`（28 spec × ≤60s + 2×120s webServer 启动上界，
  含余量）；per-test `timeout: 60_000`、`workers: 1` 维持既有约束。
- 产物：`actions/upload-artifact@v4`，`if: always()`，收集
  `playwright-report/`（HTML）与 `test-results/`（trace/错误上下文），
  `retention-days: 14`，`if-no-files-found: ignore`。
- **非 required gate**：job 名与注释如实标注
  “disposable db, not required yet”。未用 `continue-on-error` ——
  失败即红色真实信号，分支保护是否勾选调 required 由 owner 在仓库
  设置决定，工作流内不虚掩失败。
- 合成 fixture only；无外部服务/凭据/支出。

### 确定性产物根（`tests/e2e/playwright.config.ts`）

- 显式 `reporter: [["list"], ["html", {outputFolder:"../../playwright-report",
  open:"never"}]]` 与 `outputDir: "../../test-results"` —— 相对 config
  目录解析为仓库根，CI artifact 路径固定，本地/CI 行为一致。
- 未改任何测试断言、timeout、worker 数。

### `.gitignore`

- 新增根级 `test-results/`、`playwright-report/`（原有三个路径保留），
  本地 e2e 跑完不再污染工作树。

## Changed files

- `.github/workflows/ci.yml` — 新增 `frontend-build`、`e2e` 两个 job
- `tests/e2e/playwright.config.ts` — reporter/outputDir 固定到仓库根
- `.gitignore` — 根级 playwright 产物忽略
- `docs/execution/tickets/PAR-10A.md` — 本证据文档

## Acceptance tests

- [x] CI 声明有界 Playwright job（disposable db、最小权限、timeout、
      concurrency-cancel、产物收集）
- [x] CI 声明 production frontend build job
- [x] 引用脚本均真实存在且本地在上限时内完成（`pnpm --filter
      studio-web build`、`make test-e2e`）
- [x] 未设 required gate（注释明示）；失败不虚掩为绿色
- [x] 合成 fixture only；无外部 spend/provider
- [ ] 三个浏览器旅程（improve/match/discover）+ PAR-01..05 对抗性
      评估用例 —— 留给 PAR-10 后续 lane（依赖 PAR-01..09 修复落地）

## 验证命令与结果

```text
$ uv run --no-sync python -c "import yaml;yaml.safe_load(open('.github/workflows/ci.yml'))"
(解析通过，无异常)

$ pnpm --filter studio-web build
✓ built in 458ms            （relay + tsc -b + vite build 全绿）

$ make test-e2e
Running 28 tests using 1 worker
  28 passed (51.3s)          （at-0205→cs-1201 全绿；artifact 落在
                              repo-root playwright-report/ 与 test-results/）

$ ls -d playwright-report test-results
playwright-report  test-results
```

CI job 本身需在本 PR 的 workflow run 中首验；e2e job 若因 runner
环境差异（docker/浏览器依赖）出现失败，按真实失败修，不降级。

## 已知限制

- e2e job 在 GitHub runner 的首次执行尚未发生（本 PR CI 见结果）；
  docker compose postgres 与 `--with-deps` 系统包安装依赖 runner
  默认能力，若不可用需改 `services:` postgres + serve.sh 外接 DB
  参数化（当前未做，避免发明第二路径）。
- PAR-10 的浏览器旅程与对抗性评估用例未交付 —— 明确留给后续 lane。
- 分支保护 required-check 变更不在工作流内可控，需 owner 在仓库
  设置中执行；文档与 job 名已如实标注 "not required yet"。
