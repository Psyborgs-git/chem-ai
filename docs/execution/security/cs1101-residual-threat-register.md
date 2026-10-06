# CS-1101 残余威胁登记表(Residual-Threat Register)

> §21 安全/隐私回归审查的产物。每一条“已验证防护”都对应
> `services/studio-api/tests/security/` 下一条真实攻击它的通过测试;
> 没有测试支撑的声明不写入此表。
>
> 审查基线:CS-1003 WIP 分支(devin/1791291511-cs1003-broker,egress
> broker  infra 侧已落)叠在 main(CS-1103)之上。

## 一、已验证防护(均有攻击型测试)

| 面 | 防护 | 验证 |
|---|---|---|
| 归档装载 | zip/tar 成员路径穿越(abs/相对/`..`/反斜杠)、symlink、成员数/单成员/总解压/压缩比上限 | `test_cs1101_loaders.py::TestArchiveMembers` |
| 类型识别 | 空 zip(仅 EOCD magic)按 quarantine 类型化拒绝,不崩不误判;polyglot(PDF+ZIP)按内容识别 | `TestQuarantineBounds` |
| 活性内容 | docx/xlsx 宏类成员(任意路径段,不限 basename)、xlsx 公式、PDF/JS 等 → `active_content` 隔离标志,不执行 | `TestActiveContent` |
| 解析边界 | 超大输入/成员;解析超时按 poll 窗口真实杀掉子进程;嵌套炸弹 | `TestParserSafety` |
| 嵌入指令 | 文档内 prompt-injection 片段进 quarantine findings,不当指令执行 | `TestEmbeddedInstructions` |
| NUL 字节 | 文本嗅探窗口内 → binary;窗口外 → 持久化前 `pg_clean` 剥除 + `nul_scrubbed` 旗标(修复前是 psycopg DataError 崩溃) | `TestQuarantineBounds`, `imports.py`/`claims.py` |
| 导入路径 | 非 committed 工件拒绝;revoked 工件拒绝重入管线(本次新增);foreign 工件 404 非 oracle | `TestImportPath` |
| 上传面 | declared_size 不符、original_name 含 NUL/空白、checksum 伪造拒绝 | `TestUploadSurface` |
| Loopback 边界 | Host/Origin 非 loopback 拒绝;非安全方法要求 Origin 缺失/`null`/白名单;cookie SameSite=Strict | `test_cs1101_boundaries.py::TestOriginHostSpoofing` |
| 跨作用域 ID | Relay global id、artifact/run/batch id 穿越 → 404/null,与“不存在”不可区分(无 oracle);foreign workspace 任何写操作不可见 | `TestCrossScopeTraversal` |
| 注入 | GraphQL 变量/SQL 文本参数化;恶意字符串原样入库存为数据不可执行;游标跨 kind/scope 拒绝 | `TestInjection` |
| Vault 边界 | storage key 反斜杠归一化 + `..`/空段/`/`开头/NUL 拒绝;键永远 workspace 前缀 | `TestVaultContainment`, `vault.py::_check_key` |
| Worker 边界 | 不实施 `argv_only_no_shell` 契约的后端 → `profile_unavailable` 类型化失败(修复前撞 queued→failed 非法迁移崩溃);stderr 尾部剥控制字符(ANSI/NUL 注入 → ``) | `TestWorkerBoundary`, `execution.py` |
| 审计日志 | 敏感键(password/token/secret…)在任意嵌套深度丢弃(修复前仅顶层);NUL 剥除 | `TestAuditRedaction`, `audit/log.py` |
| 会话边界 | 无 cookie 401;伪造/篡改会话拒绝;会话绑定 workspace | `TestSessionEdges` |
| 出口(egress) | 全仓库静态出站导入扫描扩到 `workers/`+`infra/`;唯一网络客户端是 `workers/inference/runtime.py` 的 loopback urllib | `TestEgressWholeRepo` |
| CS-1003 broker | approval digest 精确相等(非相似);gate 边界复查 digest/recipient/bytes/到期;permit 一次性;denied 时 provider 零字节;revoke_binding 阻断后续 transfer;cancel/reconcile/delete 如实记录暴露量;callback 幂等收敛 | `test_cs1101_revocation.py::TestBrokerRevocation`, `TestEgressGateBoundary` |
| 撤消级联 | chunk 离索引(index_version 变 → 旧 cache key 不可命中 + fetch 层再过滤 status);records rejected+旗标;proposed/accepted claims → superseded;派生工件 BFS 标 `lineage_review:required`;历史曝光记录在 exposedManifestIds/exposedPrincipalIds 不抹除;不存在的 registries 如实报空 + unlearningGuarantee:false | `TestCascadeCompleteness`, `TestStaleCacheDefense` |
| 能力上限 | 伪造 approval grant 给 agent → `load_context` 剥离;伪造 `read_eval_labels` 给 user/agent → 剥离;hidden labels 双闸(capability + kind=service);revoked grant 行惰性;未知 capability 串永不成立 | `test_cs1101_unavailable.py::TestCapabilityCeilings` |
| 准入 | 缺 group/缺观测维度/超容量 → run `blocked` + 逐维原因 + missing 列表 + `export_review_proposal` 提议(非动作);无静默排入、无 reservation;envelope 非负整数/wall 上限 | `TestAdmissionBlockedHonesty` |
| 能力报告 | profile 仅三类诚态 available/unavailable/disabled,均带 detail;未探测不声称 available | `TestCapabilityReportHonesty` |

## 二、本车道发现并修复的缺陷(不入残余,已堵上)

1. **空 zip EOCD 绕过** — `detect_type` 只认 `PK\x03\x04`;空归档(EOCD `PK\x05\x06`)逃逸为 binary → 修复为全 ZIP magic 组。
2. **NUL 字节持久化崩溃** — 文本 NUL 在 4KiB 嗅探窗口外时写库触发 psycopg DataError(DoS);`pg_clean` 边界剥除 + `nul_scrubbed` 旗标。
3. **活性内容仅查 basename** — `xl/macrosheets/foo` 等嵌段逃逸;改为全路径段检查。
4. **Vault/归档反斜杠穿越** — Windows 风格 `..\` 键不规范化;已归一为 `/` 再判段。
5. **审计嵌套泄密** — 敏感键仅丢顶层;递归深层键泄露 token;已递归。
6. **stderr 控制字符注入** — run.error.message 原样带 ANSI/NUL 进审计/展示面;已映射 ``。
7. **`profile_unavailable` 路径非法迁移** — executor 在 attempt 未 start 前 fail → `queued→failed` CONFLICT 裸崩;改为 accept+start 后 typed fail。
8. **撤消后两条复活通道** — `index_batch` 不过滤 `rejected` 记录(撤消的记录可再索引);`import_artifact` 不查 `review_state`(未来 parser 版本可重入);均已加闸。

## 三、仍然暴露/接受的风险(如实记录)

| # | 残余威胁 | 现状与理由 |
|---|---|---|
| R1 | `SubprocessBackend` 如实声明 `network_denied=False` — 本地子进程后端不隔离网络,跑到其上的工作负载可触达 loopback 可达的任何端点 | **能力受限**:需要网络隔离的 profile 必须走容器后端;executor 契约只强制 argv-only。已披露,要求依赖网络隔离的能力标 blocked |
| R2 | `parse_timeout` 按 poll 窗口执行,非 per-member CPU 硬上限 | 超时测试以真实超限验证;窗口粒度内(<500ms)的突刺属接受范围;成员数/字节上限兜底总量 |
| R3 | `Origin: null` 与缺 Origin 在非安全方法上被同等接受 | file:// 与 sandboxed iframe 合法来源;SameSite=Strict+会话绑定兜底;若未来支持非 loopback 部署需收紧 |
| R4 | `secure=False` cookie(loopback http 必要) | 中间件已强制 loopback host;任何反代/非 loopback 部署必须先翻 secure — 部署注意项 |
| R5 | 盘符式 key(`C:\x`)在 POSIX vault 下是合法相对路径(已验证受限);Windows 宿主挂载下会穿越 | 本系统部署面为 POSIX;若迁 Windows 需追加盘符拒绝 — 记录为部署前提 |
| R6 | 撤消按 artifact 生效:相同字节以新 artifact 重新上传不会被旧撤消记录联动 | 新工件 rights 默认 `unknown` 不入索引,需人工再评;内容级 dedup 只绑同 checksum+parser — 接受为既定语义,不声称指纹级撤消 |
| R7 | dataset/model-release registry 尚不存在 → 撤消报告相应字段显式空、`unlearningGuarantee:false` | **能力 blocked**:在 registry 落地前不得声称撤消已传入数据集/模型产物;派生工件靠 `lineage_review` 挂起兜底 |
| R8 | broker 的 `_spent_permits` 为进程内集合 | 单进程部署内一次性保证成立;domain 侧 attempt ledger(CS-1003 后半段)落地前,多副本/重启场景的重放窗口如实披露 |
| R9 | 出站扫描为 AST 静态分析 | `importlib`/computed-string 动态 import 不在覆盖内;与“零依赖网络库”基线合用,残余为蓄意规避场景 |
| R10 | `hidden_targets` 的双闸都在 capability 层;`_evaluation_context` 会自动铸出带 grant 的 service principal | 该 principal 只能由服务端代码路径创建(无 API 面);任何新增能造 kind=service principal 的入口都必须重审此闸 |
| R11 | 审计/outbox 为追加式记录,无密码学防篡改 | 单机本地优先语义下接受;出 DB 的篡改检测不在当前威胁模型内 |
| R12 | 导入时对“文本型恶意内容”的识别是启发式词表 | `prompt_injection`/`active_content` 旗标供人工审;不声称语义级拦截 — fixture-only |

## 四、受陷组件还能看见什么(compromised-component 观测面)

| 受陷方 | 仍能观测/影响 | 边界 |
|---|---|---|
| 解析子进程(隔离 worker) | 本次交付的单 artifact 字节 | env 已剥(PATH/HOME/TMPDIR);argv-only 无 shell;vault key 不落 worker;写库走父进程 |
| API 进程 | 是信任根:DB+vault 均在界内 | 每请求仍过 ctx 能力检查+workspace 行级过滤;审计追加留痕 |
| Provider(CS-1003 double) | 仅见已签发 permit 的字节;回传 artifacts 全记录 | 返回内容在 domain 校验前不可信;无 provider 配置时 PROVIDERS 为空,零真实出口 |
| RetrievalCache 行 | 伪造行指向已撤消 chunk 也无法被服务 | fetch 层按 status 再过滤(已攻击验证) |
| Agent principal | 只见 scope 内可读面 | approval/service-only grant 在 context 加载处剥离,行级伪造无效 |

## 五、发布闸结论

- **发现的关键控制缺陷已全部修复并有回归测试**(见第二节 8 项)。
- **无未堵的关键控制失败**;R7(registry 缺位)与 R1(本地后端无网络隔离)作为“如实披露 + 能力 blocked”在案,不构成放行阻断。
- CS-1003 为 WIP(domain service/persistence 未落):本表对 broker 的断言仅限 infra 层语义;domain 接入后须重跑 `TestBrokerRevocation` 并补持久化 ledger 的重放测试(R8)。
