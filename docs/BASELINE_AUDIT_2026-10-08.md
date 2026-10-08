# Operational MVP 准备基线审计 — 2026-10-08

本次是准备工作，不完成新的产品 Sprint。当前主线以 ROADMAP.md 顶部的七步路线为准；历史 COMPLETE 记录表示当时的实现及演练，不替代当前正确性、安装或用户验收。

## 基线与方法

- 仓库：`D:\Document\snowBall`；HEAD：`a2ea769aaf8a67d9a26b4d14e5d6ba748e083a84`，与待核对审计基线一致。初始 `git status --porcelain` 为空。
- 已检查 AGENTS.md、README.md、ARCHITECTURE.md、DATA_MODEL.md、PROJECT_STATUS.md、ROADMAP.md，及对应实现、迁移、测试和恢复入口。
- 当前数据来自 PostgreSQL `snowball`，不是历史文档数字。最终快照时间：2026-10-08 19:31:22 +08:00；数据库事务时间：19:31:22.398307 +08:00。
- 使用 `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`，查询后 rollback；没有执行 refresh、采集、LLM、业务迁移、seed、rebuild、恢复或进程启停。读取配置没有调用 provider。
- 复现使用测试替身、内存 SQLite，以及全新 `.local/preparation_empty_sqlite.db`。该测试文件不属于业务数据库。初始迁移失败后的隔离文件保留供检查。
- 当前后台可能自行运行；审计不会暂停它。快照是一个一致性事务截面，不是对未来数据不变的承诺。
- 原始机器结果见 [数据快照](BASELINE_SNAPSHOT_2026-10-08.json) 和 [隔离复现](BASELINE_REPRODUCTION_2026-10-08.json)。所有历史完整性仍为 `UNKNOWN`。

## 当前数据截面

| 指标 | 当前值 | 口径 |
| --- | ---: | --- |
| Investor / Asset | 54 / 55 | 全表 |
| RawEvent / EventAnalysis | 1,868 / 2,151 | 全表，Analysis 含历史 identity |
| 当前 policy Analysis | 1,787 | SUCCESS 149、PARTIALLY_RESOLVED 506、NO_OPINION 1,131、FAILED 1 |
| 缺失当前 policy Analysis | 81 | 对每个 RawEvent 检查 exact analysis_version |
| Opinion / 有效 Opinion | 284 / 252 | 有效仅当前 identity + SUCCESS/PARTIALLY_RESOLVED |
| Attention / 有效 Attention | 329 / 329 | 现有 effective selector + attention-occurrence-v1 |
| ThesisChange / 有效 ThesisChange | 286 / 252 | 现有当前 predecessor + Opinion/comparison policy selector |
| Snapshot / Alignment / Consensus | 209 / 127 / 130 | 全表历史数量，不宣称全部当前有效 |
| Signal / Event / Evidence | 463 / 99 / 437 | 全表数量，不宣称全部有效 |
| Priority / Feed | 70 / 70 | 全表；Feed ACTIVE 68、STALE 2 |
| CollectionRun / Observation / RefreshRun | 136 / 1,267 / 43 | 全表 |
| Portfolio 相关事实、Action、Consistency | 0 | 不支持真实行为确认或扩展 |

RawEvent 已观察事实范围为 2026-08-11 08:37:39 至 2026-09-22 18:57:20 +08:00；跨度不等于完整覆盖。

完整 Opinion/comparison identity（含 provider/model/prompt/schema/digest）在 JSON 中。当前配置身份为：

- Opinion：`opinion-analysis-v3:794dc66ba5096337c3e2c0f85554887352f476e5f52ad55363b6b9420d5502a9`，provider `deepseek`，model `deepseek-v4-flash`，prompt `opinion-extraction-v5`，schema `opinion-extraction-result-v2`。
- Comparison：`thesis-comparison-policy-v1:b11fa32abad7ca1b339170a41e1f38b18ef72e51e61f26961bd37db2e3982dc4`，同 provider/model，prompt `thesis-comparison-v1`，schema `thesis-comparison-result-v1`。
- Attention `attention-occurrence-v1`；Snapshot `cross-investor-asset-snapshot-v2`；Alignment `cross-investor-directional-alignment-v1`；Consensus `cross-investor-consensus-evidence-v2`。

读取身份通过配置校验；这不表示审计批准了新 policy。没有修改任何 policy。

## 九项发现核对

“已复现”表示只读生产数据或隔离调用确认；“静态风险”表示代码链路可见但未完成对应端到端反例；“未验证”不能当作通过。“已修复”只指指定局部边界。

| 审计项 | 当前判定 | 证据与限制 |
| --- | --- | --- |
| 1. 非变化进入 Signal、累计数量解释为 acceleration | **已复现** | `signal_engine/generator.py::_thesis_changes` 无 change_type gate。只读候选有 NEW_THESIS 82、UNCHANGED 5、INSUFFICIENT 11；落库 THESIS_CHANGE Signal 对应 NEW 89、UNCHANGED 5、INSUFFICIENT 11。`intelligence/events/aggregator.py::_candidates` 按标的累计；`priority/service.py::_classify` 仅 signal_count>=2 即 MEDIUM/THESIS_ACCELERATION，隔离调用确认，无速率/比较窗口依据。 |
| 2. 无关 RawEvent 改变全局窗口重复跨投资者 Signal | **静态风险，身份子问题已复现** | `operations/refresh.py::_derive_cross_investor` 使用全局 `_raw_event_time_bounds`；Snapshot identity 包含 window/as_of；Alignment identity 派生自 Snapshot；Signal identity 是 type+source_id。隔离验证同 opinion_ids 仅变窗口即变 Snapshot identity。尚未执行“无关 RawEvent→affected asset selection→新 Signal”的完整反例；不能断言每个无关事件都会新增。Snapshot 按窗口版本化本身是合法设计，修复应位于 Signal 有效性/变化边界，不能直接删除窗口身份。 |
| 3. 跨投资者 Signal 以 calculated_at 为 observed_at | **已复现** | `_alignments` / `_consensus` 明确赋 calculation time；只读 join 确认 89 个 Alignment Signal、7 个 Consensus Signal 与来源 calculated_at 相等。重算时间因此可能被呈现为新观察；未写入验证。 |
| 4. STALE 新证据无法回 Inbox | **已复现（生命周期隔离边界）** | Feed repository 重用 priority_id 时更新时间/context，保留 state；lifecycle policy 只有 NEW→ACTIVE、ACTIVE→STALE/RESOLVED。给 STALE 条目新 observed_at 后 transition_count=0；真实 Inbox 全链路复演未执行。 |
| 5. active policy/effective source 未贯穿 Inbox | **已复现部分，policy 全链路为静态风险** | Thesis/Attention 上游确有 active selectors；跨投资者 generator 只选自身 policy，未核对来源 Snapshot 的全部 policy/有效性。最终 `feed/query.py::list_feed` 未追溯 effective source，也未筛 Signal.state。隔离将关联 Signal 标为 SUPERSEDED 后 ACTIVE Feed 仍返回 1 条。未进行生产 policy 切换或逐条 Inbox 污染归因。 |
| 6. 主页面正文、前后对比、原帖链缺失 | **静态确认的产品缺口；浏览器用户验收未验证** | `OverviewPage.tsx::RecentIntelligenceCard` 展示标签、数量、资产/投资者链接；Feed response 无 Opinion 正文/前后内容/RawEvent URL。当前 Product 页面主要展示摘要、类型、引用 ID，底层有 RawEvent.url 和 Opinion.thesis，不等于主入口已有阅读闭环。 |
| 7. 候选工作流与明确监控名单缺失 | **静态确认的产品缺口** | DiscoveryCandidate 是查询投影，不是用户保存/研究记录。App 路由无候选保存、备注、状态流；schema 无对应用户工作流。已有 Following Feed、CLI 作者过滤和按数据库活动选择最多八人的 `_select_monitored_profile_cohort`；这不是用户明确选择并持久维护的监控名单。Reality Study registry 是研究脚本名单，不能当作运行时名单。 |
| 8. scheduled refresh FAILED 补偿不足 | **已复现（分析阶段隔离边界）** | `_analyze` 只运行 status=None，FAILED 仅计 existing_failed/partial；隔离输入 FAILED 得 processed=0、llm_requests=0。run 的 scope 来自 collection.observed_event_ids，也没有全库失败补偿选择。底层/维护恢复能力存在，不代表 scheduler 会用它。当前库确有 1 条 active FAILED 和 81 条 missing，未调用付费补偿。 |
| 9a. SQLite 初始迁移 | **已复现失败** | 新空 SQLite 实际 `alembic upgrade head`，0001–0010 执行后在 `20260904_0011` 遇到 `NotImplementedError: No support for ALTER of constraints in SQLite dialect`。内存测试使用 metadata.create_all，不能覆盖此安装入口。 |
| 9b. RawEvent DB 级不可变 | **SQLite 已复现缺口；PostgreSQL 静态风险** | ORM before_update/before_delete 有保护；内存 SQLite 直接 SQL UPDATE、DELETE 都成功。生产 pg_trigger 查询无自定义 RawEvent trigger；未在生产尝试写入，权限层是否另有禁止尚未核实，不能声称 PG 写入已复现。 |
| 9c. PostgreSQL 锁 | **静态风险，真实并发未验证** | `operations/locking.py` 在 Session 上取得 session-level advisory lock 后 commit；SQLAlchemy Session 可能归还连接，未显式固定物理连接至 release。SQLite fallback 仅进程内互斥。历史声称通过不替代多进程、pool reuse、kill 后释放测试；本步骤没有锁写操作。 |
| 9d. 持续进程恢复 | **历史演练存在，当前持续恢复未验证** | start/stop/status 与登录 Task 存在；scheduler 是节拍 loop，未监督 OS 进程；登录 Task 有一天 ExecutionTimeLimit。当前只读状态见下，未 crash/reboot/restore 演练。不能据此宣称持续进程已恢复。 |

已修复的局部边界：`intelligence/patterns/rules.py::MATERIAL_THESIS_TRANSITION_TYPES` 只纳入 REINFORCED/EXTENDED/CHANGED，Attention Classification 的 active eligibility 使用 Feed/Discovery，不单凭 Event ACTIVE。相应离线测试通过。它们没有修复 Signal→Priority→Inbox 链，因此九项中没有可整体标记“已修复”的项。

## 启动、迁移、恢复、测试入口

| 用途 | 现有入口 | 本次结果/限制 |
| --- | --- | --- |
| 本地安装 | README: venv → pip install -e ".[dev]" → .env → alembic upgrade head → uvicorn | 默认 SQLite 的迁移失败已复现；没有修改业务库 |
| Python API | `uvicorn backend.app.main:app --reload`；GET /health | 当前 GET 返回 app/database ok |
| 前端 | frontend/package.json: npm run dev / lint / test / build | 本次静态检查入口，未重跑前端套件/构建 |
| 手动/定时 | `python -m operations.refresh --cdp-endpoint ...`；`python -m operations.scheduler --cdp-endpoint ... [--once]` | 会采集、写库、可能付费，本次均不执行 |
| 本地进程 | scripts/start-runtime.ps1、stop-runtime.ps1、runtime-status.ps1、install-runtime-task.ps1 | status 脚本被本机 PowerShell execution policy 阻止；用只读端口和 GET 补齐状态，没有绕过政策 |
| 迁移 | alembic.ini、database/migrations/env.py、versions/0001–0024 | 业务 PG 记录 head=20260920_0024；未跑业务 upgrade 或 alembic check。既有文档记录 psycopg compatibility shim，当前兼容性未重验 |
| 分析恢复 | scripts/recover_production_analysis.py、run_production_analysis_catchup.py；pipeline/analysis_recovery.py | 会写入，部分路径可能调用真实 LLM；没有执行 |
| 本地备份/恢复 | RECOVERY_RUNBOOK；backup-database.ps1、restore-database.ps1、verify_database_restore.py | 历史 isolated restore 演练保留；本次不做 dump/restore/continuation |
| 离线验证 | `.venv/Scripts/python.exe -m pytest ...` | 本次两批共 **80 passed**，并完成 JSON 中的隔离反例；不是全套或真实用户验收 |

80 项为 Signal evidence、Feed lifecycle/query/projection、operational refresh/status、RawEvent contracts、runtime/database recovery scripts、Event、Priority、Attention Classification、Asset Product View、effective-analysis-downstream。非失败警告为 FastAPI test-client deprecated；首批还有 pytest cache 写权限警告。没有用已有“625 passed / frontend 38 passed”作为本次结果。

2026-10-08 19:32:04 +08:00 只读运行探测：5432/8000/5173 有监听，9222 无监听；/health=ok；/api/operations/status=`ACTION_REQUIRED / STALE`，latest=`FAILED / SCHEDULED / COLLECTION / CDP_UNAVAILABLE`。最后成功时间为 2026-09-22 05:15:52.395968 +08:00。端口可访问不表示浏览器 UI 已通过验收，数据库里的 ACTIVE 也不等于近期或有效。

## 下一步最小任务（本次不执行）

只修复 **THESIS_CHANGE Signal 的 material-change gate**：复用现有 REINFORCED/EXTENDED/CHANGED 分类，排除 NEW_THESIS、THESIS_UNCHANGED、INSUFFICIENT_EVIDENCE；先加实际 SqlAlchemySignalSourceReader 的参数化回归，再改 generator。影响限 Signal 候选选择及测试，不改变 ThesisChange/Opinion、不新增语义、表或 policy，不调用 LLM。

验收：六种类型逐一验证，只有三种 material 类型产生候选；fact-time 不变；同输入 dry-run/重复生成保持幂等；保留 inactive-policy 排除；无业务数据变更。这个小任务不应声称修复累计 acceleration、历史已落库污染或 Inbox。后续必须另行处理 Priority 表述/依据、Signal 有效性和旧 artifact 的非破坏性排除，再进入真实端到端验收。
