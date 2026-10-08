# Project Roadmap

## 当前执行主线 — 2026-10-08 准备基线

本节取代下文历史记录中的 Current phase、Current sprint、Recommended next
及 Phase 4 exit 后的下一阶段安排。历史 Sprint 全部保留；其 COMPLETE/✅
表示当时实现和演练，不表示本次重新验收。此次仅完成审计和路线准备，没有完成
新产品 Sprint。当前能力和证据见 [基线报告](BASELINE_AUDIT_2026-10-08.md)
与 [带提交、时间、policy 的数据快照](BASELINE_SNAPSHOT_2026-10-08.json)。

项目初心：持续追踪投资者，发现关注、观点、逻辑及真实行为变化，提供可核验
证据，帮助用户形成 Research Candidates。用户能力验收必须贯穿
`Collect → Analyze → Materialize → Product`，不能用类、schema 或单测通过
替代。新增 Intelligence 语义冻结，只修复已证明正确性问题；历史完整性保持
`UNKNOWN`，禁止从缺失推断取消关注、观点消失或仓位退出。

以下按顺序推进，全部为待执行/待验收；每步拆成小任务，不自动启动。

| 顺序 | 用户能力与影响范围 | 验收条件 |
| --- | --- | --- |
| 1. 可信变化修复 | Signal generator、Event/Priority 现有规则、变化文案及对应测试。先 material Thesis gate；再核对累计数量被称 acceleration、跨投资者证据身份/真实状态变化及 observed_at。保留 Snapshot 窗口语义和所有历史事实，不开发新速率算法。 | NEW/UNCHANGED/INSUFFICIENT 不进入变化 Signal；重复观点不冒充变化；累计次数不称加速；同标的有效证据与状态未变时，仅重算/无关全局窗口变化不产生新变化 Signal；真正变化仍可呈现且指向前后证据；observed_at 是来源事实时间，重算不会刷新业务观察时间。离线反例和零 LLM 的隔离全链路通过。 |
| 2. 有效证据与 Feed 生命周期闭环 | 现有 effective selector → Signal → Event evidence → Priority → Feed → Inbox；Feed repository/lifecycle/query。不新建语义投影。历史污染先做只读影响清单，再采用可追溯、非破坏性有效选择；不删除 RawEvent/Analysis。 | 每层明确一个 active policy 身份，无 inactive/superseded/FAILED 来源回退；SUPERSEDED Signal 不支撑最终 Inbox；证据集合、计数、文案一致；STALE 收到真正新有效证据可回流，重复证据不回流；RESOLVED 行为明确且尊重用户处理；幂等重跑，不因 calculation time 回流。以实际 API 回读验证。 |
| 3. 可重复安装与原始事实保护 | Alembic 初始化/升级、安装说明、RawEvent DB 保护、数据库方言测试。只改已复现兼容性/不可变缺口，不因修迁移扩展 Portfolio。 | 全新 SQLite 从 0001 到 head 成功并再次升级无变化；已有 SQLite 副本与隔离 PG 升级通过；schema 与 ORM 一致；ORM、bulk/direct SQL 的 RawEvent UPDATE/DELETE 均被拒绝，INSERT/去重仍可运行；副本升级保留原事实 hash/count；新环境按文档完成启动和离线 source-to-product。 |
| 4. 用户证据阅读闭环 | 现有读 API/schema、Overview 与 Asset/Investor Detail，复用 Opinion/ThesisChange/RawEvent。仅查询与展示。 | 从 Inbox 打开“谁、何时、说了什么、为何标记变化”；展示前后观点正文及差异证据，区分原事实/AI解释/系统规则，包含 confidence、fact time 与 policy；原帖链接可打开，访问失败可读已保存原文；技术 ID 不代替证据；A/H listing 不混淆；真实用户完成一次从条目到原帖的阅读。 |
| 5. 最小研究候选工作流 | 产品操作、必要的用户研究状态持久化与 API/UI；先证明现有实体不能承载再批准最小模型。Discovery 查询投影不当作用户保存记录。 | 用户可从可核验条目保存候选，记录研究问题/备注与证据引用，查看列表、更新处理状态、撤回或归档；重启不丢失，重复保存不重复；旧 evidence/policy 可审计、失效可见；不生成买卖建议、自动决策、价格预测或排名。候选状态命名及最小持久化在执行此步前明确。 |
| 6. 监控覆盖与失败补偿 | 明确的用户监控选择、现有 collection cohort/provenance、scheduler 增量选择、FAILED 分类/受限重试和状态展示。先复用现有元数据，无证据不足不新增编排表。 | 用户知道实际监控谁、每人最近探测/成功/失败/未覆盖窗口；显式名单不会被活跃度选择悄悄替换；失败补偿从业务数据选出，不依赖本次 collection 观察集合；retryable FAILED 有次数/时间界限，认证/风控停止并可见，NO_OPINION 不重复收费；隔离 fake provider 先证明安全重跑，再在单独授权预算内做真实补偿验收。 |
| 7. 持续运行和真实用户验收 | 既有本地 start/stop/status、登录 Task、scheduler、PG 锁、恢复 runbook；聚焦持续进程及用户流程，无云部署。 | 两个独立进程跨 commit/pool reuse 只允许一个 refresh，kill 后锁释放；后台/调度/CDP/数据库失效和恢复可见；验证登录 Task 时间限制与 crash 后实际恢复，隔离备份恢复后按原 identity 安全继续，无重复 artifact/补跑风暴；一次有界真实 Collect→Product、新证据阅读→保存候选→处理的用户验收，留下时间/提交/policy/失败与恢复证据。历史恢复演练不能替代当前结果。 |

暂停：Momentum、升温、行业/主题趋势、新评分、投资者/标的排名、Portfolio
扩展、云部署、全仓重构、高级智能层。真实 Portfolio 当前为零；未来真实行为
必须有事实来源，不能用文字行动宣称代替仓位事实。

### 最小子任务状态 — 2026-10-08

步骤 1 的 **THESIS_CHANGE material-change gate：已修复，隔离数据库回归通过**。
仅在 `signal_engine/generator.py::_thesis_changes` 使用现有 enum 的局部允许集合，
保留 REINFORCED/EXTENDED/CHANGED，排除 NEW/UNCHANGED/INSUFFICIENT；
没有新增 policy、算法或 Pattern 产品依赖。

新增 `tests/integration/test_thesis_change_signals.py` 使用真实
SqlAlchemySignalSourceReader、ThesisChangeRepository effective 查询与现有
SignalGenerator。修复前 4 failed / 17 passed，失败覆盖三种非 material 候选
及混合数据 dry-run 数量。修复后 21 项新增回归全部通过；连同相关既有测试
共 58 passed。验证六种类型、当前 Analysis/comparison identity、失效前驱、
FAILED 排除、PARTIALLY_RESOLVED 保留、asset/event scope、fact-time/source/metadata、
dry-run 零写入及首次仅生成三条、重复生成零新增；Opinion/ThesisChange 内容不变。
代码 lint/format 检查通过。未调用真实 LLM、未执行生产操作、未改业务数据库，
既有审计及基线快照保持原样。

此修复仅阻止新的非 material Thesis 候选；**尚未解决历史已落库污染、
累计数量被解释为 THESIS_ACCELERATION，以及最终 Inbox 有效性**。
步骤 1 整体和产品 Sprint 均未完成；到此停止，不自动执行下一项。

### Priority 中性原因与单次变化消费子任务 — 2026-10-08

**新数据路径局部修复完成，隔离实际服务链与 Feed API 验证通过**。
新增独立 reason `THESIS_CHANGE_OBSERVED`；ACTIVE INVESTOR_VIEW_CHANGE
有至少一条实际 Event–Signal evidence link 即可生成 MEDIUM Priority，
不再以累计 `metadata.signal_count` 推断加速，也不按数量升级等级。
`THESIS_ACCELERATION` 保留原字符串和旧分类身份，与新原因不是别名。

变更限 Priority reason 契约/分类、Feed 标题、前端类型与原因显示，以及测试。
新标题为 `A thesis change was observed`，中文为“观察到投资逻辑变化”；
历史原因展示为“投资逻辑加速（旧分类，未验证加速）”，不伪装成可信新分类。
已核对 Priority/Feed 模型及迁移中的 reason 为 String(64)，无数据库 enum/check
枚举约束；没有新增或执行迁移。前端现有中性中文通用映射可复用。

生命周期算法未修改：新原因不享有历史“加速”的独立激活条件，近期 NEW
条目依照原有 fact-time window 激活；单次/两次的过旧事实保持 NEW，近期 API
不返回。STALE 回流及其他激活规则保持原样。

新增 `tests/integration/test_thesis_change_feed.py` 复用明确标注的结构化
Opinion/ThesisChange fixture，真实贯通 effective Thesis → Signal → Event →
Priority → Feed → Lifecycle → HTTP Feed API，无 LLM、无手工正确 Priority 注入。
唯一手工 Priority 是明确标注的历史兼容 fixture。

修复前新增后端用例 9 failed / 5 passed，确认单次漏选及累计加速误分类；
新增前端展示用例 3 failed / 8 passed。修复后新增链路回归 15 项通过，
连同 Signal gate 与 Event/Priority/Feed/API/Discovery/Narrative/Context/Product
相邻消费者共 **104 passed**；前端全部 **41 passed**，lint 与 build 通过。
Python lint/format 与 git diff --check 通过。

覆盖：三种 material 单次到近期 API，两次仍中性 MEDIUM，三个非 material
无该链路，无 evidence / 非 ACTIVE 排除，以真实 links 而非 metadata 数量
为门槛，过旧事实不激活、observed_at 保留最后来源事实时间，各阶段 dry-run
零写入，重复执行复用 Event/Priority/Feed 身份，历史 reason 可读且不是别名。

兼容性测试明确证明：旧 Priority 被复用时仍保留 THESIS_ACCELERATION，
repository 只更新 evidence_count。本次没有改 repository 历史重分类行为，
**历史 Priority 纠正、历史 Signal 污染和最终 Inbox 有效性仍未解决**；
已有无效历史 evidence 也未被重新验证或排除。新数据链路通过不代表既有
Inbox 已可信。没有业务库写入、生产 refresh/采集/recovery/rebuild/迁移或历史清理，
基线报告与快照保持原样。整个“可信变化”阶段未完成；本子任务到此停止。

### 持久化 Thesis Signal 有效读取与 Event 接入 — 2026-10-08

**只读选择边界局部完成，实际生产 UoW 路径的隔离聚合回归通过**。
新增 `SignalRepository.list_effective_thesis_changes(policy, comparison_version)`：
复用现有 ThesisChange effective selector 的完整当前前驱时间线，批量选择
ACTIVE、source_type/source_id 正确、当前 Opinion/comparison identity 有效、
来源 material 且 Signal 与来源 Asset/Investor 一致的持久化 Thesis Signal。
判断依据真实来源记录，Signal metadata 不能伪造 material 类别；不按局部
event_ids 判定有效性，不保留跨请求的来源缓存。

新增 EventAggregationSignalReader，仅接入
SqlAlchemyIntelligenceEventUnitOfWork.signals；Event aggregator 的 production
dry-run/aggregate 通过该适配器读取。普通 Signal get/list/list_by_asset、
Signal 生成 UoW 和 Feed UoW 的历史读取保持原样；其他 Signal 类型维持原消费
行为，没有顺带校验跨投资者来源、时间或 Attention 来源。

新增 `tests/integration/test_effective_thesis_signals.py` 直接保存旧版可能产生的
错误 Signal，不依靠已修复 generator，也不 mock effective source selector。
首批 25 项修复前 **24 failed / 1 passed**，同时证明无效输入仍被聚合及缺少
专用读取入口；修复后连同新增 UoW 边界验证 **26 项通过**。相关有效源、
此前两个子任务、Event/Priority/Feed、policy 和架构测试合计 **166 passed**。
本次 Python lint/format 和 git diff --check 通过，未修改前端。

覆盖六种旧 Thesis Signal、inactive Analysis/comparison/artifact policy、FAILED、
有效 PARTIALLY_RESOLVED、迟到 Opinion 的全局前驱失效与再次读取、非 ACTIVE、
来源缺失、source type 与 Asset/Investor 不匹配（含 Investor 空值）、伪造 metadata、
有效/无效混合的计数与投资者集合及时间、dry-run 零写入、聚合身份/link 幂等、
历史读取及源内容/Signal.state 保留、其他类型保持原行为。
SQL 观察验证专用入口读取 1 条和 11 条 Signal 均为 **3 次 SELECT**，无逐条来源查询。

**有效读取正确不等于旧 Event 已纠正**。隔离验证明确显示：

- 旧 Event 全部输入失效时，没有新候选/新 link，旧 evidence、metadata、时间范围
  和 ACTIVE 状态原样保留。
- 旧 Event 仍有有效输入时，现有 repository 将 metadata 更新为当前有效候选，
  只追加有效 link；旧无效 link 不删除，first/last 时间通过 min/max 保留原受污染
  范围，ACTIVE 状态不自动改变。因此 metadata 的有效输入数量可能与历史 links
  数量不同。
- 历史 Priority reason/evidence_count、已有 Feed 及最终 Feed query 未纠正；旧来源
  仍可能通过已有 Event/link/时间范围被下游读取。此前新 Priority 中性原因和
  material 候选规则保持不变，不能据此宣称既有 Inbox 已可信。

本次仅改 Signal repository/专用读取适配器、Event UoW、回归测试和本路线状态；
没有删除历史记录、改变 Signal.state、增加表/policy/状态枚举或前驱算法，
没有业务数据库写入、LLM、生产 refresh/采集/recovery/rebuild/迁移/清理。
基线审计与快照校验值不变。历史 Event/Priority/Feed 修复及 STALE 回流留待后续；
整个可信变化阶段未完成，到此停止，不自动执行下一项。

### INVESTOR_VIEW_CHANGE Feed 有效证据只读响应 — 2026-10-08

**本子任务局部完成：真实 HTTP 历史污染场景的只读校正通过**。
Feed 查询新增专用 FeedThesisSignalReader 读取端口，批量复用
SignalRepository.list_effective_thesis_changes；普通 Signal 历史读取、
Event 聚合适配器及 Feed 物化逻辑不变。仅 INVESTOR_VIEW_CHANGE 响应采用
当前有效、实际关联到该 Event、且与 Event/Feed Asset 一致的 Thesis Signal；
无有效关联时排除，不借用同标的未关联 Signal，不依赖存储 ACTIVE/metadata
或 Priority.evidence_count 放行。

有效关联非空时，响应 investors、signal_count/investor_count/source_count/
source_types 全部按该关联集合重建，丢弃旧 context 的其他污染字段。
时间权威是来源 ThesisChange.effective_time；专用适配器仅在读取的 SignalView
副本中覆盖不一致的 Signal.observed_at，再以有效集合的最新来源事实时间
构造响应。不使用旧 Feed/Event 时间、created_at 或 calculated_at 制造新鲜度，
不改写 Signal 或其他 artifact 时间。

since、investor_id、排序、total、limit、has_more 均使用校正后的有效结果，
无效关联的较新时间或投资者不再影响近期窗口/匹配。Asset、state、priority_level、
event_type 过滤保持既有语义；STALE/RESOLVED 不改为 ACTIVE、不自动回流。
有效当前响应使用 THESIS_CHANGE_OBSERVED 和中性标题
`A thesis change was observed`。这是当前只读分类纠正，历史 THESIS_ACCELERATION
仍可反序列化，旧 Priority/Feed 原因和标题仍保留在数据库中。

新增 `tests/integration/test_effective_thesis_feed_query.py` 直接保存已有
Event、旧关联、THESIS_ACCELERATION Priority 与受污染 Feed，真实访问 HTTP Feed API，
不 mock 有效来源查询。修复前 **18 failed / 8 passed**；修复后 **26 passed**。
与前三项修复、Event/Priority/Feed/query、相关 Product 消费者与架构回归合计
**210 passed**；前端现有 **41 passed**，无需更改页面功能。Python lint/format
与 git diff --check 通过。

覆盖：仅非 material/inactive policy/FAILED/失效前驱/非 ACTIVE Signal 的 ACTIVE
Feed 排除；混合证据人数/数量/来源/时间/原因校正；较新无效证据不匹配近期
窗口，无效投资者不匹配查询；来源时间与存储 Signal 时间两方向不一致的处理；
未关联 material Signal 不救活 Event；Event/Feed/Signal Asset 不匹配排除；
正常有效条目、四种 Feed.state、校正后排序/总数/截断/has_more；其他三种
Event 类型保留原响应行为。此前历史 Priority 兼容回归只更新 HTTP 响应预期，
同时强化存储原因/标题保持旧值的断言。

只读验证逐表比较全部业务表查询前后内容，完全一致；SQL 观察中 1 个与
6 个历史混合条目均固定 **11 次 SELECT**，无逐 Feed/Signal 来源查询或 DML。

**仍未完成**：持久化历史 Event/link/Priority/Feed 污染未清理或重写；
下游物化器及其他 Product/read consumers 尚不保证与此有效响应一致，历史
evidence_count、context、时间和原因仍可能不一致；跨投资者/Attention 等其他
Event 的有效性与时间保持原行为，尚未闭环；STALE 回流未修复。
本次结果不代表整个 Inbox 或可信变化阶段完成。

变更限 Feed 查询/专用有效事实时间读取端口及 UoW 接入、上述回归测试和
本路线状态。未调用真实 LLM、未写业务数据库、未执行生产 refresh/采集/
recovery/rebuild/迁移/清理，未新增表/policy/评分/算法；已有修改保留，
基线审计和快照校验值不变。到此停止，不自动继续下一项。

## 历史路线与 Sprint 记录（原文保留）

下文所有“current”“next”“complete”按其记录时点解读，不覆盖顶部当前路线。

## Completed

### Phase 0 — Foundation ✅

Project bootstrap and the initial source-independent persistence/application
boundaries are complete.

### Phase 1 — Data / Intelligence Foundation ✅

RawEvent, real Analysis, deterministic resolution, Opinion, Investor × Asset
state, Attention, Thesis, and the evidence-backed derivation foundations are
complete.

### Phase 2 — Intelligence Product Foundation ✅ / FROZEN

Cross-Investor evidence, Signal, IntelligenceEvent, Priority, Feed, Product
Views, frontend, and Asset ↔ Investor navigation are implemented. Further
semantic expansion is frozen during Phase 3 except for proven correctness
bugs.

### Phase 0

- Sprint 0.5 — Project Bootstrap ✅

### Sprint 1

- 1A — Raw Event Pipeline ✅
- 1B — Opinion Processing ✅
- 1C — Investor Asset State ✅
- 1D — Asset Intelligence Aggregation ✅
- 1E — Core Intelligence Orchestrator ✅
- 1F — Temporal & Processing Hardening ✅

### Sprint 2A

- Xueqiu Collector Foundation ✅

### Sprint 2B

- Real LLM Opinion Extraction ✅
- 2B.1 — Generic OpenAI-Compatible Provider ✅

### Sprint 2C

- 2C.1 — Following Feed Contracts & Architecture ✅
- 2C.2 — Following Feed Browser Runtime ✅
- 2C.3-A — Following Feed Ingestion Wiring ✅
- 2C.3-B — Following Feed Production Wiring ✅
- 2C.4 — Following Feed Historical Pagination Reliability Hardening ✅

### Sprint 2D

- Asset Resolution Contracts & Design ✅
- Deterministic Asset Resolver ✅
- AssetAlias ✅
- Evidence-backed Asset Master ✅
- Unresolved Asset Recovery ✅
- Analysis-scoped Opinion Correctness ✅
- Cross-listing / alias safety hardening ✅

### Sprint 2E.0

- Behavior Evidence Foundation ✅
- AttentionOccurrence ✅
- `OPINION` / `EXPLICIT_MENTION` / `REPOST` evidence attribution ✅
- Effective-analysis semantics ✅
- Current-author attribution hardening ✅

### Sprint 2E.2-A

#### Opinion Attribution & Identity Hardening ✅

- `opinion-extraction-v5` ✅
- Current-author-only Opinion extraction ✅
- Quote/repost attribution isolation ✅
- Cross-listing identity hardening ✅

### Sprint 2E.2-B

#### Production Analysis Policy & Projection Provenance ✅

- Explicit production `AnalysisSpec` ✅
- Provider runtime default != production approval ✅
- Effective State / StateChange / Attention queries ✅
- v4/v5 policy isolation ✅
- v5 production rollout ✅

### Sprint 2E.2

#### Thesis Change V0 ✅

- Effective v5 Opinion timeline ✅
- Independent structured Thesis Comparator ✅
- Versioned ThesisChange artifact ✅
- Fact-time and late-recovery semantics ✅
- `NEW_THESIS` / `THESIS_UNCHANGED` / `THESIS_REINFORCED` / `THESIS_EXTENDED` /
  `THESIS_CHANGED` / `INSUFFICIENT_EVIDENCE` ✅

`NEW_THESIS` means the first thesis observed in the currently available
production-effective Opinion history for an Investor × Asset; it does not claim
to be the investor's first-ever formation of that thesis. Superseded late-history
predecessor pairings remain historical artifacts and are excluded from the
effective Thesis Change timeline.

### Sprint 2E.3-A — Portfolio Fact Foundation Bootstrap ✅

- Independent Portfolio and PositionSnapshot facts ✅
- Derived PortfolioAction contract and persistence ✅
- InvestorActionClaim with RawEvent provenance ✅
- Resolved / unresolved asset identity support ✅
- No Portfolio Collector or production action detection yet ✅

### Sprint 2E.3-B — Portfolio Snapshot Import Foundation ✅

- External snapshot import contract ✅
- Deterministic AssetResolver integration ✅
- Resolved and unresolved PositionSnapshot persistence ✅
- Repeat-import idempotency ✅
- No Portfolio Collector, Action Diff, or Consistency Engine yet ✅

### Sprint 2E.3-C — Portfolio Snapshot Provenance Layer ✅

- PortfolioSnapshotBatch parent fact ✅
- PositionSnapshot batch ownership ✅
- Batch-aware repository and UnitOfWork ✅
- Deterministic batch / position idempotency ✅
- No PortfolioAction diff generation yet ✅

### Sprint 2E.3-D — Portfolio Position Change Detection V0 ✅

- Deterministic two-batch position comparison ✅
- `POSITION_ADDED` / `POSITION_REMOVED` ✅
- `POSITION_INCREASED` / `POSITION_DECREASED` / `POSITION_UNCHANGED` ✅
- Complete batch and position provenance ✅
- Resolved / unresolved identity isolation ✅
- No BUY/SELL intent inference ✅

### Sprint 2E.3-E — Opinion × Action Consistency V0 ✅

- Independent consistency domain ✅
- Active Opinion and PortfolioAction fact-time matching ✅
- Positive / negative alignment and no-direction semantics ✅
- Versioned, provenance-complete consistency artifact ✅
- Idempotent persistence ✅
- No skill, profitability, ranking, or investment recommendation ✅

### Sprint 2E.3-F — Investor Behavior Snapshot Foundation ✅

- Window-scoped InvestorBehaviorSnapshot aggregation ✅
- Active artifact and fact-time filtering ✅
- Attention, Opinion, ThesisChange, PortfolioAction, and Consistency metrics ✅
- Deterministic snapshot identity and idempotent persistence ✅
- No scoring, ranking, prediction, Signal, or Dashboard ✅

### Sprint 2E.3-G — Effective Derived Artifact & Snapshot Provenance Hardening ✅

- Effective adjacent PortfolioAction timeline ✅
- Snapshot completeness and unknown weight semantics ✅
- Effective Opinion × PortfolioAction consistency selection ✅
- Input-fingerprinted immutable BehaviorSnapshot versions ✅
- Late-data and recovery isolation ✅

### Sprint 2E.3-H — Behavior Input Dependency & Policy Closure ✅

- Explicit production Attention policy ✅
- Attention policy isolation in effective queries ✅
- Historical first-attention dependency fingerprint ✅
- FULL / UNKNOWN absence-inference closure ✅
- 2E single-investor foundation correctness closure ✅

### Sprint 2F.0 — Data Reality Check / Intelligence Calibration ✅

- Read-only PostgreSQL coverage audit ✅
- Effective Attention / Opinion / Thesis / Portfolio inventory ✅
- Cross-Investor overlap and sample-bias calibration ✅
- One bounded browser-native Following Feed backfill (no LLM analysis) ✅
- No new business models, tables, scores, or Signals ✅

The current calibration dataset has 42 Investors, 188 RawEvents, and 7.98
days of observed fact time. It has overlap across five Assets (two Investors
each), but no three-Investor overlap and no Portfolio facts. Sprint 2F.0.1
closed active Analysis coverage at 188/188 and added only two evidence-backed
Assets through deterministic recovery. The audit supports 2F design
discussion only; Momentum still requires natural multi-week data.

### Sprint 2F.1 — Cross-Investor Asset Evidence Snapshot Foundation ✅

- Asset-centric fact-time snapshot ✅
- Effective Attention / Opinion / Thesis / Portfolio / Consistency aggregation ✅
- Per-Investor contribution provenance ✅
- Deterministic SHA-256 input identity and immutable versions ✅
- No Consensus score, Divergence, Momentum, Ranking, Signal, or LLM ✅

### Sprint 2F.1.2 — Cross-Investor Contribution Provenance Closure ✅

- Complete window Opinion IDs and counts per Investor contribution ✅
- `cross-investor-asset-snapshot-v2` with v1 preservation ✅
- Aggregate-count reconstruction and repeated-input idempotency validation ✅

### Sprint 2F.2 — Opinion Coverage & Directional Alignment V0 ✅

- Immutable `CrossInvestorAssetAlignment` derived from one source snapshot ✅
- Deterministic `NONE` / `PARTIAL` / `COMPLETE` Opinion Coverage ✅
- Deterministic latest-per-Investor Directional Alignment ✅
- Attention/Opinion Investor-set integrity validation ✅
- SHA-256 source-snapshot + policy identity and append-only idempotency ✅
- No Consensus, Divergence Score, weighting, Momentum, Signal, or LLM ✅

Directional Alignment != Consensus. Alignment `MIXED_DIRECTION` is a broad
multi-side state; Consensus v2 `DIVERGENT` requires direct
bullish/bearish conflict, while a directional side plus Neutral is
`MIXED_WITH_NEUTRAL`. Consensus Change Over Time still waits for repeated
eligible windows and longer time series.

### Sprint 2F.2.5 — Production Analysis Recovery & Intelligence Recalibration ✅

- Active FAILED Analysis recovery with bounded batches/concurrency ✅
- DeepSeek/OpenAI-compatible adapter timeout, retry, exponential backoff, and
  strict structured-output validation hardening ✅
- Existing Opinion, Attention, ThesisChange, CrossInvestorAssetSnapshot, and
  CrossInvestorAssetAlignment rebuild orchestration ✅
- Data Reality Audit v2 coverage/overlap/asset/portfolio reporting ✅
- No production identity, Opinion contract, RawEvent, historical Snapshot, or
  new Intelligence feature changes ✅

### Sprint 2F.2.6 — Full Production Analysis Backfill & Recalibration ✅

- Dynamically selected and processed all missing active Analysis rows ✅
- Preserved valid analyses and real FAILED semantics with bounded resume-safe
  batches ✅
- Rebuilt existing Asset, Opinion, Attention, ThesisChange, Snapshot v2, and
  Alignment v1 artifacts ✅
- Added Data Reality Audit v3 calibration metrics ✅
- No Consensus, Momentum, Warming, Score, Ranking, or Signal implementation ✅

### Sprint 2F.2.7 — Asset Resolution Reality Calibration & Safe Coverage Expansion ✅

- Deterministic unresolved taxonomy and multi-factor prioritization ✅
- 17 evidence-backed Assets and 17 market-scoped symbol Aliases ✅
- Deterministic Opinion/Attention/Thesis/CrossInvestor recovery without Opinion
  LLM reprocessing ✅
- Real 3+ Investor overlap and MIXED_DIRECTION calibration surfaced ✅
- No Consensus, Momentum, Warming, Score, Ranking, or Signal implementation ✅

### Sprint 2F.3 — Cross-Investor Consensus / Divergence Evidence V0 ✅

- Immutable evidence artifact sourced from Snapshot v2 and Alignment v1 ✅
- Three Opinion-Investor eligibility boundary ✅
- Latest Opinion direction per Investor, with no Opinion-count voting ✅
- Provenance, membership, aggregate-count, idempotency, and policy-version
  validation ✅
- Real calibration processed 14 current overlap Snapshots as
  INSUFFICIENT_EVIDENCE; no eligible production Consensus/Divergence case yet ✅
- No score, weighting, ranking, Momentum, Warming, Signal, or Research
  Candidate implementation ✅

### Sprint 2F.3.2 — Consensus Evidence Semantic Hardening ✅

- Added active policy `cross-investor-consensus-evidence-v2` ✅
- Preserved all v1 immutable artifacts and v1 classification semantics ✅
- Reserved `DIVERGENT` for direct bullish/bearish conflict ✅
- Added `MIXED_WITH_NEUTRAL` for bullish/neutral or bearish/neutral mixes ✅
- Kept latest-per-Investor direction and strong-direction mapping unchanged ✅
- Real calibration reclassified 招商轮船 from v1 `DIVERGENT` to v2
  `MIXED_WITH_NEUTRAL` ✅
- No LLM, score, weighting, ranking, Momentum, Signal, or Research Candidate
  implementation ✅

## Current phase — Phase 3 — Operational MVP

Phase 0 Foundation, Phase 1 Data / Intelligence Foundation, and Phase 2
Intelligence Product Foundation are completed or frozen. The UI exists, but
the product is not yet operationally self-running. The critical gap is the
operational loop, not additional Intelligence semantics.

### OMVP-1 — One-Command End-to-End Incremental Refresh

Current sprint. One canonical command must coordinate the existing path from
Following Feed collection through Product View verification, select work from
actual database state, expose stage failures, and be safe to rerun. No new
semantic layer, scheduler, or orchestration table is in scope.

Status: `COMPLETE`. An explicit authenticated Edge CDP smoke returned 16
real Following Feed items. The canonical command created 16 RawEvents,
processed them under the unchanged production Analysis identity, completed
all downstream stages, verified four affected Investor Product Views, and
passed an identical rerun with zero new RawEvents and zero LLM calls.

The verified runtime command is:

```powershell
python -m operations.refresh --cdp-endpoint http://127.0.0.1:9222
```

### OMVP-2 — Scheduled Refresh + Freshness + Failure Visibility

Status: `COMPLETE`.

The lightweight scheduled trigger calls the same canonical refresh service,
persists full-refresh execution metadata, exposes freshness/failure status at
`GET /api/operations/status`, and shows user-facing operational state in
the frontend shell. The verified scheduled runtime uses an authenticated Edge
CDP endpoint and configuration-driven interval/stale thresholds.

No second pipeline, heavy orchestration framework, or Intelligence semantic
was introduced.

### OMVP-3 — Daily Intelligence Inbox

Status: `COMPLETE`.

The Overview product entry now shows Recent Intelligence using the existing
FeedItem, Priority, Event, Signal, and evidence lineage. It uses a rolling
24-hour query-time window, does not create user read state, and preserves the
distinction between successful data refresh and no surfaced Intelligence.
No new semantic layer or persistence artifact was introduced.

## Post-MVP Productionization

Deferred until Operational MVP is complete:

- always-on deployment, CI/CD, restart recovery, metrics, alerts, backups,
  production secrets, and runbooks;
- deeper historical completeness, real portfolio acquisition, and a second
  source;
- RAG and advanced research workflows.

## Deferred / Frozen

The following are explicitly deferred or frozen during Phase 3:

- new semantic layers, ranking, scoring, recommendation, and advanced
  Pattern;
- Context V2, Narrative V2, and advanced Consensus;
- Momentum based on incomplete history;
- Portfolio analytics without real portfolio data;
- RAG and second-source expansion.

Attention Momentum remains `PAUSED / DATA CALIBRATION / WAITING FOR TEMPORAL
COVERAGE`; this is preserved as a data-readiness fact, not a reason to expand
the semantic layer now.

## Product boundary

This project is an Investor Behavior Intelligence System, not a Xueqiu crawler product, stock recommendation
system, auto-trading system, or price prediction system. The roadmap prioritizes discovering who is watching what,
why they are watching it, when their views change, whether they act, and whether multiple investors form consensus
or divergence.

## Phase 4 — Intelligence Yield Recovery

Phase 4 improves intelligence yield by increasing coverage of the already
monitored Xueqiu Investor cohort. It does not add a second source or change
the Intelligence semantic layer.

### IYR-1 — Monitored Investor Direct Collection ✅

The canonical Operational Refresh collection stage now runs:

    Following Feed
          +
    Monitored Investor Direct Recent Profiles
          ↓
    Existing FeedIngestion / Profile DataPipeline
          ↓
    One RawEvent hash boundary
          ↓
    Existing Analysis → Intelligence → Product path

The cohort is bounded at up to eight database-registered Xueqiu Investors,
selected from recent activity and existing effective evidence. The direct
profile path uses a 48-hour overlap, at most two pages, and a 30-second
per-Investor duration bound. It reuses the operator-authenticated CDP
context/page and records existing CollectionRun / CollectionObservation
provenance. Profile failure is isolated per Investor; authentication,
risk-control, and CDP failures stop the direct collection safely.

Real validation produced 52 Profile-only new RawEvents, with ORIGINAL and
REPOST observability, complete downstream processing, and successful Product
verification. No Asset Resolution semantic was changed.

### IYR-2 — Safe Asset Resolution Yield Recovery ✅

Deterministic `CN` symbol normalization now maps only supported explicit
A-share prefixes to SH/SZ. Controlled Asset Master enrichment added
`SZ:300308` and `SZ:300502` with listing-scoped symbol aliases; unsupported
markets, indexes, themes, commodities, unknown prefixes, and ambiguous
cross-listing names remain unresolved.

The existing recovery maintenance runner has a bounded `--resolution-only`
mode that stops after current Asset resolution and missing Opinion
materialization. It cannot enter Analysis or Thesis LLM providers and does not
run downstream Intelligence stages. First-time integration and production
idempotency verification both recorded zero LLM calls; the production rerun
created no duplicate Opinion and changed no downstream count. No migration or
Intelligence semantic was added.

### IYR-3 — Yield Re-validation & Phase 4 Exit Gate ✅

Status: **COMPLETE**.

The real 2026-09-21 canonical refresh validated the full
Collect -> Analyze -> Materialize -> Product path with the bounded default
cohort. It produced 46 new RawEvents, including 30 profile-only events, with
8/8 direct Investor probes successful. The new cohort contained 32.6%
ORIGINAL content and a 34.8% Opinion-bearing Analysis rate, producing 6
Opinions, 7 AttentionOccurrences, 6 ThesisChanges, and 13 Signals.

The rolling 24-hour Inbox contained 11 FeedItems across 7 Assets and 9
Investors. Event identities, Priorities, and FeedItems were correctly reused
where their existing identity/policy required aggregation; 13 new Event
evidence links were added. Effective-policy correctness checks passed, and
remaining unresolved references were primarily UNKNOWN or legitimate
unsupported/index/concept/commodity categories. The safe IYR-2 identities
SZ:300308 and SZ:300502 remained resolvable.

Phase 4 is complete. The next primary mainline is **Always-On Hosting /
Restart Recovery**. The monitored cohort remains bounded at eight Investors;
expansion is deferred and is not part of IYR-3.

## Phase 5 - Always-On Product Runtime

Phase 5 makes the useful-but-bounded local intelligence product durable
across ordinary Windows process and machine restarts. It does not add
Intelligence semantics, cloud deployment, portfolio analytics, ranking, or
cohort expansion.

### P5-1 - Durable Local Runtime & Restart Recovery

Status: **COMPLETE**.

The repository now provides canonical local runtime startup, shutdown, status,
bounded log rotation, explicit CDP ACTION_REQUIRED reporting, and optional
interactive-login Task Scheduler setup. PostgreSQL OperationalRefreshRun
records remain the source of truth, and the existing advisory lock protects
concurrent refreshes.

Backend, scheduler, frontend, scheduler crash recovery, backend recovery,
full stop/start recovery, Product View recovery, Inbox recovery, and
CDP-unavailable failure visibility have been tested.

P5-1 Closure was verified after Windows restart: Edge CDP was restored on
127.0.0.1:9222 with the existing authenticated profile, bounded smoke
succeeded, and the allowed SCHEDULED refresh completed with SUCCESS. The final
Operational Status was HEALTHY / FRESH. This completes durable local runtime
work; cloud Production Ready deployment remains out of scope.

### P5-2 - Backup / Restore & Secrets Safety

Status: **COMPLETE**.

The local runtime now has a bounded PostgreSQL backup/restore path with a
non-secret snapshot manifest, isolated target naming, no-overwrite/no-drop
restore behavior, and post-restore schema, count, integrity, identity,
Product View, Inbox, and Operational Status verification. A real restored
`SCHEDULED` continuation succeeded without duplicate business artifacts or
LLM calls, and the live runtime was returned to HEALTHY / FRESH.

The backup boundary deliberately excludes `.env`, credentials, cookies,
tokens, API keys, and the authenticated Edge profile. Backup retention,
encryption at rest, off-host copies, secret management, and production
backup/restore automation remain future production gaps. This phase does not
claim Production Ready deployment.
