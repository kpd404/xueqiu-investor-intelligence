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

### Thesis Priority → Feed 物化一致性 — 2026-10-08

**本子任务局部完成，隔离历史投影重跑与 HTTP 字段对照通过**。
起始 HEAD 为 `686a0b091fa6985508c2a5e3ff8bd5559c1bc97a`，工作区干净。
前四项来源有效性、material gate、中性原因及只读查询校正继续保留。

Priority/Feed 物化批量复用现有 FeedThesisSignalReader（effective selector +
ThesisChange.effective_time），新增纯关联分组 helper 供 Priority、Feed 及查询
共同使用。它仅将当前有效 Signal 与真实 Event links 按 Asset 对应分组，
不复制前驱算法/material 分类，不使用未关联的同标的 Signal 或异标的证据。

ACTIVE INVESTOR_VIEW_CHANGE 有有效关联时，Priority 为 MEDIUM /
THESIS_CHANGE_OBSERVED，evidence_count 仅计有效关联。新增 repository 的
`add_or_refresh_thesis_change` 限定检查真实 ACTIVE INVESTOR_VIEW_CHANGE，
仅此路径可刷新旧 reason、priority_level、evidence_count；通用 add_if_absent
及其他 Event 类型的复用规则保持原样。Priority id/event_id/created_at 不变。
隔离实例的实际字段更新为 **HIGH / THESIS_ACCELERATION / 2 →
MEDIUM / THESIS_CHANGE_OBSERVED / 1**；旧字段确实被替换，不宣称行内仍保存
被替换的旧值，也没有引入通用审计表。

Feed 使用同一有效关联重建 title/reason/context 与最新来源事实时间，保持
id/priority_id/created_at/state。既有 STALE、RESOLVED 不自动激活。全部输入
失效或 Event 不满足 ACTIVE 条件时，不创建/刷新该 Thesis Priority 或 Feed；
旧行可原样保留，不写 evidence_count=0、不删除、不新增失效状态。

正常执行顺序：**Event 聚合 → Priority.materialize → Feed.materialize → Feed API**。
Priority.dry_run 只提供候选，不替代实际刷新。旧 Priority 的分类/等级或有效
计数未刷新时，Feed.dry_run 和 Feed.materialize 均明确 ValueError；保留数量
一致性检查，比较有效关联数量，不比较全部历史 links。全部有效证据为空时
直接跳过旧 Priority，不因旧原因/计数重新支撑 Feed。

新增 `tests/integration/test_thesis_materialization_consistency.py`，使用真实
数据库服务及旧 Event/links/Priority/Feed fixture。首批修复前 **13 failed /
5 passed**；修复后连同未关联/异标的补充场景 **20 项通过**，相关后端回归
合计 **223 passed**。Python lint/format 与 git diff --check 通过。

覆盖混合历史关联、旧分类限定纠正、全部非 material 无新建/刷新（有/无旧行）、
晚到 Opinion 的前驱失效与再次物化、错误较新的 Signal/Event 时间不制造近期
情报、未关联/异标的排除、Event 状态门槛、STALE/RESOLVED 保留、dry-run 零
写入、首次纠正后身份/字段幂等、其他三种 Event 保持原行为及 repository scope
拒绝其他类型。历史兼容测试更新为“旧值可读取、授权 Thesis 刷新后派生值替换”，
保留 id/created_at 与历史枚举兼容性断言。

完整隔离链路中，旧 Event 已保有前一子任务的合法聚合 metadata 和受污染时间
范围，因此 Event 聚合只复用身份/关联，不改变该 Event；Priority/Feed 更新后
逐字段与当前 HTTP 响应对照，而非仅检查 200。Query 仍逐表零写入；保护性快照
确认除 Priority/Feed 外所有业务表（含 RawEvent、Analysis、Opinion、ThesisChange、
Signal、Event 及旧 evidence links）内容不变。1 个与 6 个历史混合条目下，
Priority dry-run + Feed dry-run + HTTP 查询合计均为 **27 次 SELECT**，没有逐条
来源查询。

本次代码仅修改上述服务/UoW、限定 repository 刷新、共享关联 helper、相应测试
和本路线；未修改 Event repository/聚合的既有持久化行为，未改业务数据库、
未调用 LLM、未执行生产 refresh/采集/recovery/rebuild/迁移/历史维护。
基线审计及快照保持原样。**仍未完成**：历史 Event 时间/metadata/关联纠正，
全部失效但保留的旧派生行治理、其他 Product/read consumers 的有效证据口径、
跨投资者有效性和时间、STALE 回流及完整生命周期闭环。整个 Inbox 与可信变化
阶段未完成；到此停止，不自动执行下一项。

### Thesis Feed Lifecycle 有效证据一致性 — 2026-10-08

**本子任务局部完成，完整隔离链路及前五项相关回归通过**。
Lifecycle._plan 对 INVESTOR_VIEW_CHANGE 复用 FeedThesisSignalReader 和
group_effective_thesis_evidence，按实际关联、当前有效且 Asset 一致的 Thesis
证据检查数量和状态输入，不使用未关联的同标的证据或历史全量 link 数量。
未复制 policy/material/前驱算法，其他 Event 类型保留普通历史读取和原校验。

有效证据非空时，一致性检查仍严格保留：Priority.evidence_count 必须等于
有效关联数量，分类必须是 MEDIUM / THESIS_CHANGE_OBSERVED；Feed 的
Asset/event_type/reason/title/context/observed_at 必须与已刷新的投影一致。
未按 Priority → Feed 顺序刷新时，dry-run/apply 明确报错，不替上游校正任何字段。
用于 NEW → ACTIVE / ACTIVE → STALE 的时间来自有效 ThesisChange.effective_time
读取副本，沿用原有窗口，错误较新的 Signal/Event/无效关联时间不制造新鲜度。

全部关联失效时，在投影分类/历史数量校验前跳过该 Thesis 条目，保留历史行、
关联和原状态，不激活也不阻断正常条目。FeedLifecyclePlan.skipped 记录
Feed/Event ID 与 `NO_EFFECTIVE_THESIS_EVIDENCE`；既有 operational lifecycle
helper 的摘要增加 skipped_count 和明细。该诊断不新增持久化表、policy 或状态
枚举，不表示旧 ACTIVE 行或持久化污染已清除。

状态 policy 文件和合法转换集合没有修改；**没有新增 STALE → ACTIVE**。
有效旧证据仍允许正常 ACTIVE → STALE；STALE/RESOLVED 不自动转换。
Lifecycle apply 仍只写合法 Feed.state，不修改来源、Event、关联、Priority 或
Feed 的标题/context/时间等字段。

新增 `tests/integration/test_thesis_lifecycle_consistency.py` 使用真实隔离数据库，
先 Event 聚合 → Priority/Feed 物化，再 Lifecycle 与 HTTP API，保留混合历史
旧 links 和受污染 Signal/Event 时间。修复前 **20 failed / 3 passed**；修复后
**23 passed**，前五项及相关 API/物化/架构/运行诊断回归合计 **264 passed**。
Python lint/format 和 git diff --check 通过。

覆盖近期 NEW 激活、旧 NEW 不激活、旧 ACTIVE 过期、STALE/RESOLVED 无回流；
历史 non-material 或迟到 Opinion 导致全部来源失效时记录跳过并让正常条目
继续；未关联/异标的证据不能救活条目；Priority 数量/原因/等级及 Feed 原因/
标题/context/时间未刷新均报错；dry-run 逐表零写入，重跑及重复应用计划幂等，
保护性快照确认 Lifecycle 除 Feed.state 外所有业务字段不变；其他三种 Event
维持原行为。1 个与 6 个混合条目下，Lifecycle dry-run + HTTP 查询均为
**20 次 SELECT**，没有逐条来源查询。

本次仅改 Lifecycle service/诊断结果导出、operational helper 的跳过摘要、
上述回归和本路线状态。未调用真实 LLM，未写业务数据库、未执行生产 refresh/
采集/recovery/rebuild/迁移/维护；诊断 helper 仅在注入隔离数据库的测试中调用。
前五项改动保留，基线审计和快照不变。**仍未解决**：STALE 回流、跨投资者
有效性与时间、历史 Event/来源/关联污染及跳过后保留的旧派生行、其他产品
读取入口口径和完整生命周期闭环。整个可信变化阶段未完成；停止，不自动继续。

### Thesis STALE 回流与原始事实基线 — 2026-10-08

**本子任务局部完成：仅 INVESTOR_VIEW_CHANGE 可按有效新事实 STALE → ACTIVE**。
保留前六项有效来源、物化、查询和 Lifecycle 一致性要求；RESOLVED 不自动打开，
其他 Event 类型没有新增回流，默认通用转换校验也不允许它们 STALE → ACTIVE。

#### 基线及判断边界

复用现有 `IntelligenceFeedItem.context["_thesis_lifecycle"]` JSON 内部区域，
没有新增字段、表、迁移或 Analysis policy。基线格式 version=1，绑定 Event/Asset，
保存：精确 known_raw_event_ids、已消费来源 consumed_facts（RawEvent ID →
published_time）、不倒退的事实 high_watermark、reentry_after 过期/初始化截止，
以及最近合法转换的原因、评估时间和支持它的来源事实。

仅保存 material 解释身份不够：旧 RawEvent 可能在后来重新解释或解析后才变成
material。因此检查点还批量读取一次当前数据库已知 RawEvent UUID 集合，作为
“已存在事实”的精确排除集合；它不推进该标的的事实水位。UUID 不用于时间排序，
也不使用 collected_time/calculated_at/created_at 证明新事实。此精确内部集合
随数据量增长，暂不引入新的持久化索引或编排表。

回流须同时满足：当前 STALE、实际关联的当前有效 material 来源、Priority/Feed
已刷新、来源 RawEvent 未被基线记录、published_time 严格晚于事实水位及
过期/初始化截止、位于原有激活窗口且不晚于评估时间。RawEvent 时间与有效
投影时间须一致；存在未来或不一致时间时保守不回流。同时间戳不同事件不能
证明顺序，因此不回流。截止时间只限制过期后发生的事实，不作为新事实证明。

NEW → ACTIVE、ACTIVE → STALE、STALE → ACTIVE 时记录必要检查点；STALE
观察时单调扩充已知事实/消费记录，必要时只更新内部基线而不转换状态，避免
未来时间日后变为过去、旧帖新解释或 policy/前驱重配制造回流。集合只追加，
水位只取 max；来源减少或恢复有效不能忘记已消费事实或使进度倒退。
全部证据失效仍按前一步跳过，不写状态或基线。

历史 STALE 缺基线或缺可信过期截止时，先建立当前事实检查点并记录
LEGACY_STALE_BASELINE_INITIALIZED，不立即激活，也不从已被物化覆盖的时间
猜测旧基线。之后的真实新事实才可能回流；初始化之前的潜在有效新事实或
同时间戳事实可能继续遗漏。这是保守兼容，不声称恢复全部历史遗漏。已有
损坏/不支持版本的基线明确报错，不静默清空进度。

#### 存储、计划与写入

Feed repository 物化覆盖展示 context 时保留专用内部区域；公开查询剥离该区域，
标题/context/时间一致性校验只比较展示字段。Lifecycle 专用 repository 方法
检查并锁定相关 Feed 行，在同一 UPDATE/事务中保存必要基线与合法状态，保持
Feed/Priority/Event ID 与现有 created_at；Event 模型本身没有 created_at 列。
最近回流记录 NEW_EFFECTIVE_THESIS_FACT 及支持 RawEvent ID/发布时间，
不新增重复条目或通用通知框架。

dry-run 只产生转换和检查点计划，不写任何字段。apply 使用外部计划时，按注入
执行时钟重新核对相关证据、投影、窗口和基线前置条件；条件失效、计划不再
匹配或缺少 Thesis 事实检查点则 ValueError，不能只凭 from_state 执行。已提交
的同一检查点/转换可幂等复用。baseline_updated_count 与状态 updated_count
分开记录；operational helper 仅追加诊断明细，不执行额外业务步骤。

#### 验证结果及限制

新增 `tests/integration/test_thesis_stale_reentry.py`，固定时钟真实贯通有效来源
→ Signal → Event → Priority → Feed → Lifecycle → HTTP Inbox。首批修复前
**7 failed / 9 passed**；修复后连同 policy/前驱/时间反例 **26 passed**。
保留前六项相关后端回归合计 **290 passed**；前端 lint 与 **41 passed**。
Python lint/format 和 git diff --check 通过。

覆盖真正新事实回流/近期 Inbox、相同证据重跑、再次过期后不得重复回流、
仍在近期窗口但早于过期截止的旧事实补录、非 material/未关联/同时间戳事实、
仅新解释 ID/计算时间、前驱重配、policy 切换及恢复、未来时间及仅时钟推进、
派生时间与原始时间不一致、全失效跳过、历史保守初始化及随后新事实、基线
不被物化覆盖、不泄漏 API、旧计划失效/伪造计划拒绝、损坏基线不重置、
RESOLVED/其他 Event 不回流。首次纠正后重跑稳定，身份和创建时间不变。

成功回流逐表确认除 Feed 外所有业务表不变；失败注入在状态/基线 flush 后触发，
两者都回滚。前六项保护断言仅额外允许明确内部区域变化，公开字段与来源保护
未放宽；模拟过去的外部计划测试采用固定执行时钟。Lifecycle dry-run + HTTP
查询在 1 个与 6 个条目下均 **21 次 SELECT**（新增一次原始 UUID 库存批量读取），
不存在逐 Feed/Signal 来源查询。

本次未调用真实 LLM、未执行生产 refresh/采集/recovery/rebuild/迁移/维护，
未写业务数据库或修改/删除来源事实与历史关联；所有写入验证在隔离数据库。
基线审计及快照未改写。**仍存在**：保守初始化/相同时间/截止前补录的潜在
遗漏、跨投资者有效性与回流、历史 Event/关联污染、其他产品读取入口口径及
总体运行验收。整个 Inbox 与可信变化阶段未完成；停止，不自动继续下一项。

### 跨投资者 Signal 已引用来源链校验 — 2026-10-08

**本子任务局部完成：只读 policy/引用边界接入候选与持久化聚合读取**。
保留此前七项 Thesis 修复、普通 Signal 历史读取，以及 NEW_ATTENTION 原行为。
新增 `CrossInvestorReferencedEvidenceReader.list_with_valid_references` 作为共享
来源入口；`SignalRepository.list_cross_investor_signals_with_valid_references`
复用它并要求 ACTIVE、准确 Signal type/source_type/source_id、Asset 一致、
无伪造单投资者身份，再由 EventAggregationSignalReader 接入 production UoW。
本次命名及边界为“已引用来源有效”，不是 Snapshot freshness/supersession。

Alignment → Snapshot 及 Consensus → Alignment → Snapshot 必须存在、同标的、
Snapshot 引用一致，input identity 与既有 fingerprint 函数一致。显式检查 active
Snapshot/Alignment/Consensus policy 以及 Snapshot 的批准 Opinion、Attention、
Thesis comparison、Consistency identity，不回退到历史 policy。来源结构或引用
不合法的产物排除，不相信 Signal.metadata。既有纯 Alignment/Consensus 构造/
完整性路径用于核对已有产物，不复制分类算法，不执行 calculate 或持久化。

上游按 Asset + window_end 分组，复用 existing effective selectors；沿用 Snapshot
服务的 window_end 读取截止（as_of 更晚也不引入窗口后事实）。引用 Opinion、
Attention、ThesisChange 必须仍有效，Investor/Asset/RawEvent/Analysis 关联准确，
贡献的方向/时间/类型等标签与已引用真实来源一致；Thesis 前驱也必须在该截止
的有效时间线中，时间对应 current Opinion 事实。first-Attention 引用及其身份/
时间可核验，窗口内 latest Opinion 仅从已引用 Opinion 集合确认，不把未来或
后来未引用的新 Opinion 填进旧窗口。Portfolio/Consistency 只有存在引用时才按
既有效规则读取校验，不假定生产数据存在，也不扩展 intelligence。

**边界**：已引用证据仍有效，不代表 Snapshot 包含目前窗口全部有效证据。
晚到事实扩大输入集合不会仅凭这一点判定旧 Snapshot 失效；也不重新断言存储
first-Attention anchor 已是现在最早的完整历史锚点。窗口版本、late-data 输入
完整性与 supersession 另行处理，历史完整性继续 UNKNOWN。

新增 `tests/integration/test_cross_signal_source_chains.py`，真实上游数据库数据，
直接保存历史错误 Signal，不用修复后的 generator 替代旧数据场景，也不 mock
effective selector。合法 artifact calculate 只用于隔离 fixture 准备，随后专门
禁止 calculate 的读取测试通过。首批修复前 **50 failed / 3 passed**；补充后
新增 **61 passed**，跨来源及此前七项/相关消费者回归合计 **401 passed**。
Python lint/format 与 git diff --check 通过。

覆盖每层及上游 policy、来源缺失/现存错配、Asset/引用/input identity 错误、
inactive/FAILED Opinion、Attention 实际身份与 policy、Thesis 前驱失效、标签/
metadata 伪造、窗口后事实、窗口内新增但未引用事实、旧非 ACTIVE Signal、
混合聚合只新增合法 evidence links、普通历史读取保留、dry-run 逐表零写入、
重复生成/聚合幂等及缺失 Portfolio 引用排除。旧回归中“跨来源永远放行”的
断言按本次授权更新为 NEW_ATTENTION 不变，未削弱 Thesis 来源/幂等验证。

批量观测：2 条与 12 条旧跨投资者 Signal 的专用读取均 **10 次 SELECT**；
六个同 Asset/window_end 的窗口版本共用一次完整上游读取。生成 dry-run 的
11 → 21 次 SELECT 增量仅为新增候选各自的 Signal 身份查找，非逐 Signal 重读
来源链。所有校验零写入，未删除历史 Signal、改状态或改来源记录。

**时间及含义未修复**：候选 observed_at 仍取原 calculated_at，Signal 身份仍为
type + source_id，窗口 fingerprint 不变；CONSENSUS_CHANGE 保留现有枚举及候选
状态条件，没有把当前共识状态证明为共识变化。不同合法窗口/版本、相同事实
的重复 Signal、旧 Event metadata/状态/证据关联、Priority/Feed 物化与查询的
跨投资者有效性仍未解决，最终 Feed 不能据此宣称可信。

本次限 Signal 候选/专用读取、共享只读校验、对应测试和本路线状态；未改
Priority、Feed query、跨投资者回流、calculated_at/observed_at、窗口/去重规则，
未调用真实 LLM、未执行生产 refresh/采集/recovery/rebuild/迁移/维护、未写
业务数据库、未新增表/policy/评分/算法。已有修改和基线快照保留。跨投资者
情报及整个可信变化阶段均未完成；停止，不自动继续下一项。

### 跨投资者 Signal 方向证据事实时间 — 2026-10-09

**本子任务局部完成：两类新候选与专用读取停止用 calculated_at 充当 observed_at**。
保留此前八项修复及共享只读来源链校验，不修改 Consensus 分类、窗口输入身份、
Signal type/source/唯一键/去重、policy、来源时间或历史 Signal 字段。

时间依据：CROSS_INVESTOR_ALIGNMENT 的方向状态使用 Snapshot 各投票投资者的
latest_window_opinion；现有 CONSENSUS_CHANGE 使用经校验的 Consensus.latest_opinions，
与同源 Snapshot 的投票成员/Opinion 一致。两类 observed_at 都取这组实际方向
投票 Opinion 对应 **RawEvent.published_time 的最大值**，表示最晚一票的事实时间，
不是共识形成/变化时间。Neutral 也是既有方向投票的一部分，不添加新侧别规则。
Attention-only 贡献、非投票 Opinion、Thesis/Portfolio/Consistency 的较新时间不能
刷新它；不是 Snapshot 中所有 artifact 时间的最大值。

共享入口新增 `list_with_fact_times`，沿用已加载的 Asset/window_end 有效 Opinion
→ RawEvent 事实读取，核对实际 Opinion 身份、方向和贡献时间；只从各自 Snapshot
已引用的 latest votes 取值，不从当前窗口全集或窗口后最新 Opinion 替换。旧
`list_with_valid_references` 保留接口并复用同一校验。无法证明投票或贡献时间与
真实来源不一致时排除，不使用 calculated_at/generated_time/collected_time、窗口
结束或当前时间兜底。不复制分类算法，不创建新情报层。

Generator 使用统一事实时间映射，created_at 仍为实际生成时刻。已落库 Signal 的
专用读取只对返回的 SignalView 副本校正 observed_at，普通 get/list 保留原值。
Event 聚合适配器传递校正副本，不能只筛 ID 后又返回原始带污染时间的对象。
复用旧 Signal 的物理记录不被重写；相同身份重跑无新增行。

新增 `tests/integration/test_cross_signal_fact_time.py`，真实隔离 Snapshot/Alignment/
Consensus（旧事实、新计算）与直接保存的旧 ACTIVE Signal。首批修复前
**11 failed**；补充新行、非投票真实 Thesis 引用与混合聚合后 **15 passed**。
此前 Thesis/来源链及相关 API/物化/生命周期/架构回归合计 **416 passed**，
Python lint/format 与 git diff --check 通过。上一子任务刻意冻结计算时间的断言
只更新为事实时间预期，历史原值、身份及有效来源断言继续保留。

覆盖两类候选与旧读取校正、历史值完整保留、重算时间变化不影响 observed_at、
窗口后事实不泄漏、贡献时间字符串伪造排除、较新的非投票 Attention 与实际
Thesis 引用不刷新方向时间、迟到旧投票使用原发布时间、新 Signal 的创建时间
与事实时间分离、dry-run 逐表零写入、重复生成身份复用、混合窗口 Event 候选
时间范围按校正输入。沿用来源链的分组读取和查询预算：2/12 条持久化 Signal
仍 **10 次 SELECT**，没有新增逐 Signal 事实查询，输入集合扩大等边界未改。

旧 Event 隔离验证明确区分：新的聚合候选 first/last 都按事实；既有 repository
仍用 min/max 保留历史范围，例中 first 可扩展到事实时间，但受污染 last 仍是
旧 calculated_at。旧 links 与历史 Signal 原时间保留，不进行 Event/Priority/Feed
维护，也不校正最终 Feed 响应。**仍未解决**：窗口输入完整性/supersession、
重复窗口/相同事实的重复 Signal、CONSENSUS_CHANGE 的真实前后比较与表述、
历史 Event/关联及最终跨投资者 Feed 时间/有效性、跨投资者回流。

本次只改共享只读事实时间解析、候选/专用读取及 Event 输入接入、相关回归和
本路线状态；未调用真实 LLM、未执行生产 refresh/采集/recovery/rebuild/迁移/
维护、未写业务数据库、未改来源或删除关联、未新增表/policy/评分/算法。
已有修改及基线快照不变。跨投资者情报和整个可信变化阶段均未完成；停止，
不自动继续下一项。

### Snapshot 当前窗口输入完整性校验 — 2026-10-09

**本子任务局部完成：当前数据库与批准 policy 下的窗口输入 identity 校验**。
保留此前九项修复，特别是方向投票 RawEvent 事实时间；不选择全标的“最新
Snapshot”，不跨窗口比较，不改变窗口、policy、fingerprint 或分类规则。

`CrossInvestorAssetSnapshotService.prepare_inputs` 是共享只读入口，提取原
calculate 中的 effective selectors、窗口过滤、排序、贡献构造、first Attention
history 依赖及 fingerprint。calculate 使用相同准备结果再持久化；读取路径
使用同一 Session 的只读 repository ports，不调用 calculate、不写 Snapshot。
没有持久化 UoW 的准备实例明确拒绝 calculate。

共享来源链入口逐 Snapshot 按 asset/window_start/window_end/as_of 及全部批准
policy 身份重建应有 input_identity，与存储身份比较后再做原引用链校验。
截止仍为 window_end，as_of 更晚不能引入未来事实；相同数量下的身份替换、
有效前驱重配、窗口前首次 Attention identity 变化均能使旧输入身份不匹配。
其他标的、窗口后事实、FAILED/inactive 解释不改变该 scope 的有效输入。
所有现有来源链接口（含事实时间接口）、新 Alignment/Consensus 候选及旧
ACTIVE Signal 的 Event 专用读取共用这一规则，普通历史读取仍保留原记录。
正常隔离刷新产生匹配输入的新 Snapshot 后可入选，旧 Snapshot/Signal/state
均保留；本次不是历史修复或 Signal 删除。

修复前先运行新增真实数据库测试，两类 Signal 在已有引用仍有效但遗漏迟到
窗口 Opinion 时均失败：**2 failed**。修复后新增窗口完整性用例 **12 passed**，
覆盖迟到 Opinion/Attention（包括仅补 Attention）、同数量身份替换、前驱、
first history、无关/无效输入、不同 window_start/as_of、旧行保留、新来源链
通过、dry-run 逐表零写入与重复生成/聚合幂等。来源链及事实时间旧测试中
允许遗漏输入/继续消费过时 Snapshot 的预期按本次正确性边界更新，保留事实
时间、有效来源、历史读取和幂等断言，不扩展共识变化含义。

实际回归命令使用 `.venv/Scripts/python.exe -m pytest ... -q
-p no:cacheprovider --tb=short`：Snapshot/Alignment/Consensus、来源链/事实
时间、此前七项 Thesis/Feed/Lifecycle 及 Signal/Event/Priority/Feed 回归共
**317 passed**；另运行 architecture、intelligence_read_api、thesis_change_contracts
和 integration/thesis_change 共 **90 passed**，合计 **407 passed**。
Python ruff check/format 与 git diff --check 通过。仅存在已有 httpx/Starlette
弃用警告，未调用 LLM 或外部服务。

按完整 scope 在一次调用内缓存准备身份，不存在跨请求永久缓存。实测无
Portfolio 引用 fixture：1 个 scope/2 条旧 Signal 的专用读取 **19 SELECT**；
6 个不同完整 scope/12 条旧 Signal **64 SELECT**（每新增 scope 9 次输入准备，
共同 asset/window_end 的原引用读取继续复用）。生成 dry-run **20 → 75 SELECT**，
另外每新增两类来源有 2 次既有 Signal 身份查找。来源读取随 distinct scope
增长，不逐 Signal/Alignment/Consensus 重读整个上游；不同窗口不共用错误截止。
Portfolio 有效输入也由原准备逻辑读取以发现新增输入，没有扩展 Portfolio。

所有写入验证仅在隔离 SQLite；未执行生产 refresh/采集/recovery/迁移/维护，
业务数据库、来源事实、历史关联及基线审计/快照未改写。历史完整性仍
**UNKNOWN**：本次仅证明当前数据库/policy 的窗口输入一致，不能证明外部
历史完整。**仍未解决**跨窗口相同事实重复 Signal、CONSENSUS_CHANGE 的真实
前后比较及表述、旧 Event 时间/关联、跨投资者 Priority/Feed 最终有效性及回流、
其他产品读取入口。整个跨投资者情报与可信变化阶段未完成；到此停止。

### 跨窗口等价跨投资者 Signal 消费 — 2026-10-09

**本子任务局部完成：新生成与 Event 专用读取抑制等价窗口重复输入**。
保留此前十项修复、Snapshot/Alignment/Consensus 的合法窗口身份与持久化
内容、Signal 的 type + source_id 数据库唯一键及真实来源引用。未新增表、
policy、共识变化算法、内部签名字段或通用去重框架。

先以真实隔离数据库复现：同输入两个合法窗口的新候选为 4 条而非 2 条，
旧重复 Signal 的专用读取也返回 4 条。另调用真实 OperationalRefreshService
的 `_derive_cross_investor`、`_generate_signals` 派生阶段（不调用 run、采集或
分析），补入其他标的较晚 RawEvent 后，全局 window_end 扩大，本标的贡献
不变、生成新合法 Snapshot，却新增 2 条跨投资者 Signal。首批 **3 failed**，
不是仅凭 source_id 静态风险作结论。

共享 `list_with_equivalence` 使用同次 prepare_inputs 和既有来源链、完整性、
事实时间校验。等价要求 Signal 类型、Asset、当前批准解释 identity/资格、
规范化完整有效输入、分类结果都一致。沿用原 fingerprint 构造，仅把
window_start/window_end/as_of 替换为相同的指纹占位边界，不用占位时间做查询
或观察时间兜底；计算时间与版本来源 ID 不参与等价。保留全部有效 artifact
IDs、各层 policy、投资者贡献、first Attention dependency 与事实时间，以及
最新 Opinion 身份/方向/事实时间；不是只比较人数、方向或 observed_at。
分类 key 来自已校验的真实 Alignment/Consensus 结果，不复制分类算法，不
信任 Signal.metadata 中的签名。本次不会将当前共识状态证明为“共识变化”。

新候选在同批每组选择一个代表；优先复用真实有效 ACTIVE Signal，旧重复
记录按持久化 created_at、Signal UUID 选稳定代表，无可复用记录时按来源 UUID
选代表。顺序不依赖数据库返回次序或本次评估时间；代表保持实际 source_type/
source_id，候选 observed_at 仍为方向投票 RawEvent 事实时间。无效/非 ACTIVE
Signal 占用的旧 type/source 身份不自动激活，也不阻断其他可用来源。实际
generate 与 dry-run 使用同一候选路径，不仅在预览中去重。

`select_effective_cross_signals` 同时用于新候选的已有代表选择与 repository
专用读取，Event 聚合只消费每组一个经校验、校正事实时间的代表。普通历史
读取保留所有旧行/state/原时间，失效代表不会屏蔽仍有效的来源。原 Event
repository 在正常聚合重跑时仍可能更新其 metadata，但本次未改其规则或执行
历史重建；隔离旧 Event 的四条 evidence links 与受污染 last time 全部保留，
新候选 signal_count 为 1、零新增重复关联。Priority/Feed 未修改。

新增 `test_cross_signal_equivalence.py` **18 passed**，覆盖同窗口与不同窗口/
as_of/计算时间重跑、同批稳定选择、已有代表优先、旧重复消费、policy/状态/
身份失效后的有效替代、不同 Opinion 历史及不同 Attention 投资者即使人数/
方向/事实时间相同也不误合并、类型/标的隔离、真实有效输入变化、伪造
metadata、实际刷新全局窗口反例、源表保护、dry-run 零写入及生成/聚合幂等。
此前完整性测试仍确认三个合法来源窗口都通过自己的校验、历史六条 Signal
保留，仅专用消费结果改为每类型一个代表。未削弱来源有效性、时间或身份断言。

使用 `.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider --tb=short`，
Signal/Event、Snapshot/Alignment/Consensus、此前 Thesis/Feed/生命周期/读取
链路合计 **335 passed**；architecture、intelligence_read_api、Thesis 契约及
integration/thesis_change 另 **90 passed**，合计 **425 passed**。最终新增测试
单独重跑 18 passed，ruff check/format 和 git diff --check 通过。唯一测试警告
是既有 httpx/Starlette 弃用警告；没有外部服务或 LLM 调用。

按来源/完整 scope 复用同次准备，不用永久缓存。实测 1 个 scope：历史 Signal
从 2 条增至 22 条（新增伪造来源记录），专用读取均 **19 SELECT**，生成 dry-run
均 **21 SELECT**。6 个 distinct scope/12 条旧等价 Signal：专用读取 **64**、
生成 dry-run **66 SELECT**。后者只保留两条候选的身份查找，另有一次历史
Signal 批量读取；来源查询随 distinct scope 增长，不逐重复 Signal 重建来源链。

**并发边界仍有限**：等价查找与 add_if_absent 在同一生成 UoW，但数据库只
约束同一 type/source，未约束不同来源的等价输入。独立并发调用可能看到不同
可见窗口/未提交 Signal，仍可能分别写入等价来源，不能凭串行幂等测试宣称
数据库级跨来源唯一性。SQLite canonical refresh 锁实测仅同进程协作互斥；
PostgreSQL 使用 session advisory lock，只有锁持续属于同一 backend 且所有
调用遵守锁协议时才可协调刷新。当前实现跨 commit 未显式固定连接，持续
持锁/连接池复用及跨进程行为尚未验证，不在本次扩建或修复锁框架。

所有写入验证仅隔离 SQLite，未执行生产刷新/采集/恢复/迁移/维护，未修改
业务数据库、来源事实、历史关联或 Signal.state；既有工作区修改和基线文件
保留。**仍未解决**：共识变化的真实前后比较与文案、旧 Event 关联/时间及
Priority/Feed 的历史污染和最终跨投资者有效性、跨投资者回流、其他产品读取
入口、独立并发的跨来源唯一性和 PG 锁持续性。历史完整性仍 UNKNOWN。
路线只记录本子任务完成，不宣称跨投资者情报或整个可信变化阶段完成；停止。

### 跨投资者当前方向状态的准确分类与展示 — 2026-10-09

**本子任务局部完成：新数据链路表达当前方向观察，不宣称共识前后变化**。
保留此前十一项修复。新增独立 Priority reason
`CROSS_INVESTOR_DIRECTION_EVIDENCE`，表示既有规则下观察到多人观点方向证据，
涵盖符合资格的方向一致或直接看好/谨慎分歧。Alignment 对应 Priority 仍 LOW，
Consensus 对应仍 HIGH；方向分类、资格、阈值、排序及 Signal/Event 身份不变。
未增加 Consensus Change Over Time、演化算法、表、policy 或变化加分。

保留 `SignalType.CONSENSUS_CHANGE`、`EventType.CONSENSUS_STATE_CHANGE` 及
其他既有技术身份，契约注明它们是兼容值，不能证明形成、增强、减弱、反转
或变化。旧 Priority reason `CONSENSUS_STATE_CHANGE`、`CROSS_INVESTOR_DISCOVERY`
保持独立原字符串，可反序列化，不删除、不与新原因设别名。已核对模型和
既有迁移中 reason 为 String(64)，没有枚举/check 约束；未新增或执行迁移。

新 Feed 标题为 `Cross-investor direction evidence was observed`，中文原因
为“观察到多人观点方向证据”。前端明确区分当前方向状态、来源观察时间与
是否有前后比较：新卡片标注来源观察时间、未进行前后状态比较、方向一致
不代表投资逻辑一致。当前方向一致/直接分歧标签不描述逻辑共识或反转；
Asset 页的兼容事件原因、通用复核说明及 Narrative 文本不再用技术类型宣称
真实变化，证据 Signal 计数也不统一称“变化信号”。没有改变这些产品读取
入口的有效性或分类算法。

历史处理限定为准确展示：旧原因标题/中文标签明确“旧分类、未验证变化或
来源有效性”。Feed query 对旧原因返回警示标题的只读副本，reason、context、
时间和数据库原行不被重分类或校正；未把旧记录包装成新可信观察。真实
隔离测试明确：Priority repository 重用旧行仍仅更新 evidence_count，旧 reason、
id、created_at 保留；本次未添加跨投资者历史重分类或批量维护。Thesis 的
限定刷新行为继续保留，未全局改变 repository 重用规则。

先通过真实有效来源 → Snapshot/Alignment/Consensus → Signal → Event →
Priority → Feed → Lifecycle → HTTP API 添加失败测试：首次看好方向一致及
直接看好/谨慎分歧均因旧原因失败，**2 failed**。新增前端新原因/旧原因/
当前状态翻译测试在修复前 **5 failed / 11 passed**。
修复后新增隔离链路 **6 passed**：除两类首次观察外，还验证重复生成与物化
复用原身份/创建时间、中性标题/新原因/事实时间/HTTP 一致、旧原因独立可读、
旧 Priority 数量刷新但原因保留、旧 Feed 只读警示及来源失效后仍可能返回。
查询逐表零写入，普通历史字段和来源保护断言保留，没有手工正确新 Priority
代替上游生成；仅历史兼容 fixture 直接保存明确标注的旧 Priority。

使用 `.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider --tb=short`，
跨窗口等价/来源校验/事实时间/完整性及 Thesis/物化/Lifecycle/Feed 回归
**341 passed**；架构、实际读 API、Thesis 上游、Discovery/Narrative/Context/
Attention Classification/Asset Product 消费者另 **126 passed**，共 **467 passed**。
前端 `npm test` **46 passed**，`npm run lint` 与 `npm run build` 通过；Python
ruff check/format 和 git diff --check 通过。测试保留既有 HTTP 库弃用警告。
旧分类规则测试只更新新原因预期与显式枚举集合，不改变等级/有效性/幂等断言。

**Lifecycle 不修改**：HIGH_PRIORITY、兼容 CONSENSUS_EVENT 与 CROSS_INVESTOR_EVENT
特殊激活分支继续存在。隔离固定时钟验证，60 天前的 NEW 条目仍可能仅因
这些分支 ACTIVE，即使不在激活时间窗口；有正确事实时间时近期 since 查询
排除它们。技术值与激活分支都不证明旧事实有资格进入近期 Inbox。受污染
旧 Event/Feed 时间及失效证据可能绕过时间筛选，必须由后续跨投资者有效
证据物化/查询/Lifecycle 口径修复；本次未实现跨投资者回流。

所有写入仅隔离数据库，未调用真实 LLM，未执行生产刷新/采集/恢复/迁移/
维护，未修改业务数据库或基线审计/快照，既有工作区修改保留。**仍未解决**
历史跨投资者 Priority 原因、Event/证据关联和时间污染、最终 Feed 有效性及
特殊激活口径、跨投资者回流与其他产品入口有效性；真实共识变化能力没有
实现，历史完整性仍 UNKNOWN。只记录本子任务状态；停止，不自动继续。

### 跨投资者 Feed 查询的有效关联、投票者与事实时间 — 2026-10-09

**本子任务局部完成，仅修复两类 Feed 查询响应**：
CROSS_INVESTOR_ALIGNMENT → CROSS_INVESTOR_DISCOVERY、CONSENSUS_CHANGE →
CONSENSUS_STATE_CHANGE。技术身份仍兼容旧值，不证明真实前后变化。此前十二项
修复保留，特别是 Thesis 查询、内部生命周期基线、全局 Signal 去重与事实时间。

共享 `list_with_votes` 在原 policy/来源链/窗口输入完整性/事实时间/等价校验的
同次加载中，提供实际参与方向投票的有效 Opinion 投资者；原三字段事实时间
与四字段等价入口保持兼容。新增 `FeedCrossInvestorSignalReader.group_by_events`
注入现有 Feed 查询 UoW，复用传入的历史 Signal 批量读取，不新增持久化投影。
ACTIVE、来源身份和 Asset 合法的 Signal 先保留未去重的有效读取副本，再按
每个 Event 的真实 evidence links、对应 Signal type 和 Asset 过滤，最后复用
原稳定代表规则在该关联集合内去重。没有先全局代表相交，也没有补造关联或
借用同标的未关联 Signal；全局代表未关联、另一合法等价来源已关联时仍可读。

仅在 Event/Feed Asset 和技术类型一致且有效关联非空时返回当前方向证据。
响应重新构造 signal_count/source_count/source_types、实际投票者及其人数，
observed_at 取已校验方向投票 RawEvent 事实时间的最大值。忽略旧 Event/Feed
时间、Priority.evidence_count、旧 context 以及 Signal 的错误观察时间。
Signal.investor_id 为空也不再导致零人数；Attention-only 投资者不是投票者。
不同真实输入的合法历史窗口仍分别作为证据保留，投资者集合仅用于展示/
人数/过滤，不把跨窗口投票重新组合成一个当前共识，不新增方向分类。

当前有效响应 reason 为 CROSS_INVESTOR_DIRECTION_EVIDENCE，标题为
`Cross-investor direction evidence was observed`。旧 Priority/Feed 的 reason
只在响应副本校正，存储原值不变，LOW/HIGH 不重分类。since、investor_id、
排序、total、limit、has_more 在有效筛选/去重/事实时间校正后计算；调用方
Feed.state 过滤保持，STALE/RESOLVED/NEW 不写状态、不自动激活或重开。
旧 context 与 Thesis 内部生命周期区域不泄漏，其他 Event 类型不扩展校验。

修复前先构造已有 Event/旧 Priority/旧 Feed、错误历史时间及真实旧关联，
首批真实 HTTP 测试 **6 failed**：两类 inactive 来源仍返回、重复窗口仍展示
999 旧计数、未正确展示实际投票者。修复后新增
`test_effective_cross_feed_query.py` **43 passed**，覆盖政策/FAILED/前驱失效、
窗口遗漏迟到输入、非 ACTIVE/缺失来源、类型/Asset/投资者身份错配、有效与
更晚失效证据混合、等价窗口关联、未关联全局代表/未关联有效来源不可补足、
Attention-only、事实旧计算新、不同状态的多个历史窗口不合成共识、投票者
过滤、当前中性分类、分页/排序/各状态、等级保留、全部业务表零写入及查询规模。

使用 `.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider --tb=short`：
本次 HTTP 场景与此前十二项来源/Signal/Event/Thesis/物化/Lifecycle/Feed 回归
**384 passed**；架构、读 API、Thesis 上游、Discovery/Narrative/Context/Attention
Classification/Asset Product 消费者另 **126 passed**，共 **510 passed**。
ruff check/format、git diff --check 通过；只有既有 HTTP 库弃用警告。此前“旧
跨投资者原因仍在 HTTP 返回”“非方向证据可支撑跨 Event”的预期按新边界
更新，底层旧 Priority/Feed 内容不变、Thesis 与其他类型的断言没有放宽。
未改前端或响应字段形状，投票者沿用现有 investors 契约。

SQL 实测所有查询仅 SELECT，查询前后逐表比较内容完全相同：
1 个 distinct scope、1/2 个 Event 均 **25 SELECT**；历史 Signal 从 2 条增至
22 条（新增已关联伪造来源）仍 25。单标的 6 个完整 scope、32 条 Signal、
2 个 Event 为 **70 SELECT**；6 个标的、11 个完整 scope、42 条 Signal、12 个
Event 为 **145 SELECT**。本无 Portfolio 引用 fixture 的查询量为基础 10 +
9×完整 scope + 6×asset/window_end 引用读取 scope；Signal/Event 增长只增加
批量数据及内存关联处理，不逐 Feed/Signal 重建完整来源链。同次准备复用，
不同窗口各自读取正确截止，不使用跨请求永久缓存。Thesis-only 查询仍保留
此前 11 次批量读取预算。

写入验证仅隔离数据库 fixture；查询零写入，没有生产刷新/采集/恢复/迁移/
维护、真实 LLM、业务数据库修改或历史清理，基线文件和既有修改保留。
**仍未解决**跨投资者 Priority/Feed 物化的有效数量/投票者/时间一致性、旧
Event/关联/Priority/Feed 的持久化污染、Lifecycle 特殊激活口径与回流、其他
产品读取入口有效性、独立并发/PG 锁边界及真实共识变化能力。当前查询校正
不代表安全物化重跑或生命周期已闭环；历史完整性仍 UNKNOWN。路线只记录
本子任务完成，停止，不自动继续，不宣称整个 Inbox 或可信变化阶段完成。

### 跨投资者 Priority → Feed 物化一致性 — 2026-10-09

**本子任务局部完成，仅修复两类目标物化，不包含 Lifecycle 或回流**。
保留此前十三项修复、原 Signal/Event 身份和普通历史读取。Priority、Feed 与
查询复用 `FeedCrossInvestorSignalReader.group_by_events`：真实关联、ACTIVE
Signal、有效 policy/来源链/窗口完整性、Event 范围等价去重、方向投票者和
RawEvent 事实时间都由同一入口解析，没有复制来源/前驱/等价算法。
共享端口移至 evidence 模块，共用公开 context 构造，不改变查询响应口径。

Priority 仅处理 ACTIVE Event 和非空有效证据，evidence_count 为去重后数量，
reason 为 CROSS_INVESTOR_DIRECTION_EVIDENCE，按既有规则分别 LOW/HIGH。
新增限定 writer `add_or_refresh_cross_direction`，只允许两类 ACTIVE Event，
纠正 reason、priority_level、evidence_count，保留 id/event_id/created_at。
**旧字段值被替换，不再保存在该行**：隔离旧 CROSS_INVESTOR_DISCOVERY /
CONSENSUS_STATE_CHANGE 原因变为中性原因，故意错置的 HIGH/LOW 恢复 LOW/HIGH，
999/历史关联数量改为有效数量。未新增审计框架，通用 add_if_absent 与 Thesis
限定刷新原行为不变；其他类型不会因本次 writer 被重新分类。

执行顺序明确为 **Event 聚合 → Priority 物化 → Feed 物化**。Priority dry-run
只提供候选，不刷新旧行；未实际刷新或 reason/等级/有效数量不一致时，Feed
dry-run 与 materialize 均明确 ValueError，数量校验未删除。资格及来源按各自
完整 scope 判断，不用 event_ids 局部集合替代有效性；未关联全局代表不能
误排合法关联，也不能借同标的未关联证据。

Feed 使用同一有效组的中性标题/原因/公开 context 和事实 observed_at，不用
Event.last_observed_at。投票人数来自有效 Opinion，Attention-only 不算投票者；
不同真实输入的窗口证据保持独立，只合并展示参与者集合，不合成共识。
复用 Feed id/priority_id/created_at/state，既有内部区域按原契约保留、HTTP
不泄漏。STALE/RESOLVED 不激活或重开。全部证据失效或 Event 非 ACTIVE 时
跳过，不写零数量、不生成/刷新投影，旧行保留；失效来源继续由当前查询排除。

先构造已有 Event/旧 Priority/旧 Feed、重复及非 ACTIVE 历史关联和污染时间，
运行真实 Priority dry-run 复现两类都把 1 组有效证据计为 3 条：**2 failed**。
修复后新增 `test_cross_materialization_consistency.py` **30 passed**，覆盖混合
历史纠正及真实聚合→物化→HTTP 字段一致、ACTIVE/STALE/RESOLVED、旧原因/
等级替换、身份/创建时间/内部区域保留、dry-run 零写入、重复字段稳定、
失效 policy/迟到输入与非 ACTIVE Event 跳过、无 Priority 的全失效 Event
不新建、未刷新与单字段不一致报错、局部合法代表、不借未关联证据、
Attention-only、不同真实输入不合并、其他类型重用及 scoped writer 拒绝越界。
每次写入逐表确认除 Priority/Feed 外全部记录保持原样，源事实、Signal、Event
及旧 links 完整保留；查询前后全部表相同，公开持久化字段与 HTTP 响应一致。

使用 `.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider --tb=short`，
本次物化与此前十三项/相关 Signal/Event/Thesis/Feed 回归 **414 passed**；
架构、实际读取 API、上游及 Discovery/Narrative/Context/Attention Classification/
Asset Product 消费者另 **126 passed**，共 **540 passed**。ruff check/format、
git diff --check 通过。此前刻意保留“目标类型旧原因不刷新”“Thesis 关联可
支撑跨 Event 物化”的预期更新为本次正确边界；其他类型、有效性与幂等保护
未削弱。唯一测试警告仍为既有 HTTP 库弃用警告。

批量实测无 Portfolio 引用 fixture：一个完整 scope、两类 Event 的 Priority /
Feed dry-run 为 **22 / 23 SELECT**；六个完整 scope、12 条等价 Signal 为
**67 / 68 SELECT**，每增加 scope 增量 9 次，两类来源共用同次准备/校验。
没有逐 Signal/Feed 重建来源链；实际写入额外使用既有按投影身份查找/刷新，
没有新增跨请求缓存或并发框架。来源集合改变后必须再次按规定顺序刷新，
不能用旧计划或 dry-run 当作已完成的 Priority 更新。

**Lifecycle 仍未闭环，已保留真实反例**：新 Priority 有效数量为 1，旧 links
仍为 3，完成 Feed 物化后 Lifecycle dry-run/apply 均报
`Priority evidence count does not match Event evidence`，没有状态或其他写入。
单来源场景中 HIGH_PRIORITY/CONSENSUS_EVENT/CROSS_INVESTOR_EVENT 仍可激活旧
事实（此前固定时钟反例继续通过）。未修改这些分支、数量口径或跨投资者
回流；本次全链路证明止于物化和 HTTP，不声称 Lifecycle 已修复。

所有写入仅隔离 SQLite fixture；未调用真实 LLM，未执行生产刷新/采集/恢复/
迁移/维护，未修改业务数据库、历史 Event/来源/Signal/关联、锁或其他读取
入口，基线文件与既有修改保留。**仍未解决** Lifecycle 有效证据/时间口径、
特殊激活及回流、保留的历史 Event 时间/关联与全失效旧投影、其他产品入口
有效性、独立并发/PG 锁、真实共识演化及产品验收。历史完整性仍 UNKNOWN。
路线只记录本子任务状态；停止，不自动继续，不宣称整个 Inbox 或可信变化阶段完成。

### 跨投资者 Lifecycle 有效口径与限定时间激活 — 2026-10-09

**本子任务局部完成，不实现跨投资者 STALE → ACTIVE**。保留此前十四项修复，
Lifecycle 的两类目标 Event 批量复用查询/物化的有效关联入口，包含来源链、
完整窗口输入、Event 范围等价去重、实际投票者和 RawEvent 事实时间。不复制
来源算法、不借未关联证据，不用全部旧 links、旧 Event 时间或计算时间判断。

有效证据存在时严格检查 Priority 原因/LOW-HIGH 规则/有效数量及 Feed 标的、
技术类型、原因、中性标题、公开 context、事实 observed_at。内部区域沿用
feed_display_context 契约，不因私有内容存在而误报公开字段不同；未刷新字段
直接 ValueError，Lifecycle 不修正上游、标题、context 或时间。来源全失效时
保留行、关联和原状态，记录 `NO_EFFECTIVE_CROSS_DIRECTION_EVIDENCE`，不激活
且不阻断其他正常条目；跳过不表示历史污染清除。

仅两类目标的 NEW 激活改为：ACTIVE Event + 有效证据 + 投影一致 + 来源事实
在现有激活窗口内且不晚于评估时间。HIGH_PRIORITY、CONSENSUS_EVENT、
CROSS_INVESTOR_EVENT、旧原因不再单独绕过时间窗口；其他 Event 原规则保留。
ACTIVE 过期按有效事实时间及原 stale_window，重复/失效较新关联、旧 Event
时间不能阻止过期；STALE/RESOLVED 不新增自动转换，Thesis 回流与基线算法
不变。目标转换只写合法 Feed.state，无跨投资者内部基线写入。

外部跨投资者自动转换计划执行前按执行时钟重新批量核对来源及投影；识别
实际 Priority→Event 关系，不能通过篡改 Feed.type 绕过目标检查。来源失效、
窗口过期或投影错配后不能只凭 from_state 执行旧计划。沿用原合法状态集合
及错误风格，不增加并发框架，不扩大成跨投资者回流；现有手工处理状态的
合法转换保留。Thesis 外部计划/checkpoint 校验继续执行既有逻辑。

先实际生成历史 3 links/1 有效组，完成 Priority/Feed 物化再调用 Lifecycle，
以及两类旧/未来事实的正确单来源投影：修复前新增 **6 failed**，分别复现
旧数量错误与不受时间约束的激活。修复后新增
`test_cross_lifecycle_consistency.py` **45 passed**：真实聚合→Priority→Feed→
Lifecycle→HTTP 字段/状态/近期窗口验证、等价关联、LOW/HIGH 旧事实不激活、
未来事实不激活、近期 NEW 激活、旧 ACTIVE 过期、失效的真实近期事实不能
阻止过期、全失效跳过/不阻断、Priority/Feed 九项字段错配报错、非 ACTIVE
Event、STALE/RESOLVED 无回流、外部计划来源/时钟/类型失效拒绝、dry-run 零
写入、重复执行幂等及按字段确认只写目标 state。源记录/关联/所有上游表
保持不变，API 仍按真实投票者和事实时间返回，不仅检查 HTTP 200。

真实 Thesis 基线保护场景保留原库存吸收行为：新增 RawEvent 后既有 Thesis
维护仍可扩展 known_raw_event_ids；完成这项既有维护后，跨投资者激活不改
Thesis 状态或基线。此前 Thesis 回流、假回流/外部计划及原子性回归保留。
旧“按全部 links 报错”“兼容类型能激活旧事实”“Thesis Signal 能支撑跨
Event 激活”的目标类型预期按本次修复更新，其他 Event 与 Thesis 原断言未放宽。

实际 `.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider --tb=short`：
本次及此前十四项/相关 Signal/Event/Thesis/Feed/Lifecycle 回归 **459 passed**，
架构、实际读 API、上游及相邻产品消费者 **126 passed**，合计 **585 passed**。
最终本次+既有 Lifecycle 单测重跑 50 passed，ruff check/format、git diff --check
通过；仅保留既有 HTTP 库弃用警告。SQL 实测一个完整 scope、两类 Event 的
Lifecycle dry-run **23 SELECT**；六个 scope、12 条等价 Signal **68 SELECT**。
同次来源准备复用，所有 dry-run SELECT 且逐表零写入，不逐 Feed/Signal 重建。

**真实 Thesis 启动失败独立保留，未解决**：用户报告启动在 FEED_LIFECYCLE 因
Thesis Priority 与有效证据数量不一致失败。本次隔离保留同类别反例，未刷新
Thesis Priority 时仍报 `Priority evidence count does not match effective Thesis
evidence`，没有写入。这不证明真实故障根因，不把它归因于跨投资者旧关联；
后续必须单独核查 canonical refresh 的选择范围/阶段顺序/有效输入一致性。
本次未运行生产刷新、读取/修改业务数据库或操纵现有服务，不宣称真实启动
恢复成功，也没有扩大修改编排。

未调用真实 LLM，未执行生产采集/恢复/迁移/维护，未停止或重启服务；历史
Event/Signal/来源/关联与基线文件保留。**仍未解决**跨投资者回流、上述真实
Thesis 编排失败及其根因、持久化历史污染、其他产品入口有效性、独立并发/
PG 锁、真实共识演化和真实用户验收。历史完整性仍 UNKNOWN。路线只记录
本子任务状态，停止，不自动继续，不宣称整个 Inbox 或可信变化阶段完成。

### canonical refresh 物化与 Lifecycle 范围协调 — 2026-10-09

**本子任务局部完成：修复编排范围，不宣称生产运行恢复或整轮验收完成**。
保留此前十五项 Intelligence 修复，不改变有效来源、分类、事实时间、等级、
状态规则，不实现跨投资者回流。只协调已有服务和明确评估范围。

生产只读核查：香港时间 **2026-10-09 22:22:27.921706 +08:00**，连接 localhost
PostgreSQL snowball，REPEATABLE READ / READ ONLY，SHOW transaction_read_only=on，
结束 rollback。当前 HEAD 为 e3db4bd353eaf2c68904d4c2d7bacd84ed66b6e3，含本会话
既有未提交修改；失败摘要未记录执行代码提交，不能将当前工作区当作失败时
完整版本。未调用 LLM、运行 refresh 或修改业务表。

读取真实 run f3a11789-ef66-41b3-9894-e3a97b06dac3：开始 21:40:38.194555、结束
21:43:11.703326（香港时间），FAILED / FEED_LIFECYCLE / STAGE_FAILED。摘要记录
60 个 observed RawEvent、25 个新事件、25 次新 Analysis，domain 11 个 Opinion、
9 个 affected Assets，聚合 25 个 Event，物化 23 个 Priority/Feed；该运行的
历史 LLM 请求是已存摘要，本次没有发出这些请求。

报错 Priority 62c6ba81-1da2-4efa-b2e6-3f51c7544f86 不在摘要 23 个已物化 ID 中；
当前父 Event ab976a9a-ced4-4671-8b96-e0cb554c42f1 不在 25 个聚合 ID 中；Asset
5d7bb2ad-e432-411e-8662-f02f35086a2f 不在 9 个 affected Assets 中。当前该 Priority
仍 MEDIUM/THESIS_ACCELERATION/evidence_count=2，Feed 0323fe80-628d-4bb1-8374-
e5f42df85598 为 ACTIVE、旧原因与计数 2。两条 ACTIVE Thesis Signal 中，第一条
来源 NEW_THESIS（比较仍有效但不是 material），第二条 THESIS_EXTENDED 有效，
当前有效变化数量为 **1**；两条来源 RawEvent 均未在本轮 observed 集合中。
当前 Opinion policy 为 opinion-analysis-v3:794dc66ba5096337c3e2c0f85554887352f476e5f52ad55363b6b9420d5502a9，
comparison 为 thesis-comparison-policy-v1:b11fa32abad7ca1b339170a41e1f38b18ef72e51e61f26961bd37db2e3982dc4，
两条来源 identity 匹配当前配置、Analysis 均 SUCCESS。

**可确认与限制**：失败摘要明确报错行未被本轮物化；当前代码只按聚合候选
ID 刷新投影，却全量评估 Feed，当前数据库仍有同类 2/1 不一致。来源类别/
有效数量是核查时状态，不是失败时快照，不能证明当时恰为 1，也不能据此
宣称阶段间来源变化已被还原。读取摘要和当前记录不等于复原全部失败事实。

真实隔离 canonical 反例：两个标的，一个为本轮已有成功 Analysis 的输入，
另一个为历史旧 Thesis 投影；只有外部 comparator 使用结构化 fixture，全部
内部 scope 选择、resolution/domain/cross/Signal/Event/Priority/Feed/Lifecycle/
Product 服务及 operational run/锁仍真实执行。修复前 **1 failed**，canonical
返回 FEED_LIFECYCLE 的 effective Thesis count 错误，不是 NoOpRefresh 或仅手动
串联服务。实际外部采集在无数据场景使用明确空结果 fixture，不访问网络。

最小修复：domain 的 affected Assets 额外来自观察 RawEvent 与已有 Opinion、
Attention、Thesis 当前/前驱事件的持久化关系（含旧 policy/FAILED 依赖）；
只是保守依赖覆盖，不由编排器判断有效性。聚合候选 ID 继续记录，但后续
projection_event_ids 取 affected Assets 全部已有 ACTIVE Event，避免“有新
候选”代替“有受影响旧投影”；Priority 后的 projection_priority_ids 从范围内
持久化行读取，包含全失效保留行。Feed 与 Lifecycle 传递相同 Event 范围。
Lifecycle dry_run/apply 新增可选 event_ids，默认仍全量原行为，显式空集合
评估零条；外部 plan 不与 scope 混用。只筛评估条目/关联，不改变全局有效
来源选择、Thesis 基线或状态算法。

边界明确：其他未受本轮观察依赖/派生输出影响的标的，以及非 ACTIVE 父
Event，暂不评估，未宣称其投影已一致。摘要输出 source_dependency_asset_ids、
projection_event_ids、projection_priority_ids、Lifecycle scope_event_ids /
evaluated_items 与 deferred_feed_count，便于识别延期范围。无新采集不触发
全仓历史修复或重复分析；合法 skip-collection CLI 仍要求显式 RawEvent ID，
空数据验收走真实 collection 阶段的外部空结果 fixture。

新增 `test_canonical_refresh_scope.py` **7 passed**：原类 scope 错误修复、本轮
新变化至 HTTP ACTIVE 结果、当前标的与无关旧投影边界、迟到前驱使有效数量
减少、无新 material 候选但旧 Event 全失效、FAILED 来源依赖覆盖、干净重复
运行零新增业务产物/零 LLM 请求、空采集安全执行、阶段间真实来源变化及
单写入故障仍分别 FAILED 于 FEED_LIFECYCLE/FEED。没有删除检查、强改数量、
清理关联或 fallback inactive policy。旧无关投影逐行不变，已有失效行按原
规则跳过，真实来源变化会重新验证/暴露失败，不用捕获异常制造 SUCCESS。

**发现但未扩大修复的独立阻断**：有效数量从 2 降到 1 的 canonical 场景，
Priority、Feed、Lifecycle 和 HTTP 已正确协调，但 Asset Product 的 Context
仍要求所有旧 evidence links 数量与有效 Priority 数量一致，报
`Event evidence count mismatch`，PRODUCT_VERIFICATION 为 PARTIAL，最终
PARTIAL_FAILURE。这是其他产品读取入口口径问题，按范围限制保留，不弱化
验证或改为 SUCCESS。已有 FAILED Analysis 场景也保持 PARTIAL_FAILURE。
干净新变化/重跑/空数据及全失效场景可 SUCCESS，不以这些场景宣称生产所有
历史条目或整个产品链路已经恢复。

实际命令 `.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider --tb=short`：
新 canonical/既有编排单测和此前十五项回归 **475 passed**，架构/实际读取/
相邻产品另 **126 passed**，合计 **601 passed**；最终范围测试+编排单测 16
passed，ruff check/format、git diff --check 通过。仅既有 HTTP 库弃用警告。
canonical 集成与 NoOp 单测结果分开：正确性证明使用七项真实服务集成场景。

尚需单独授权的真实运行验收：观察新 summary scope 是否覆盖实际依赖、识别
延期旧投影、核对阶段间来源变化和其他产品检查结果。未执行生产验证，
报错旧 Priority 本身未在业务库被纠正，不能宣称真实服务已恢复。另保留
全局 policy 切换/未观察依赖的有界协调、其他读入口口径、历史污染、独立
并发/PG 锁、跨投资者回流、真实共识演化及用户验收缺口。历史完整性仍
UNKNOWN，基线快照/历史 Sprint 不改写；路线只记录本子任务，停止，不自动继续。

### Asset Product Context 有效关联读取一致性 — 2026-10-09

**本子任务局部完成，解除已复现的 Context 产品验收阻断，不启动生产验证**。
保留此前十六项修复，未改 Context 窗口边界、判定算法、状态规则、表、policy
或持久化投影，没有新增 Momentum/共识演化/加速。历史完整性保持 UNKNOWN。

实际路径根因不只一处：独立 Context 先调用 standalone Discovery，该入口按
旧 evidence links 检查 Priority；Asset Product 则先加载 Asset read scope，
scoped Discovery/Attention 的检查及 Context 自身仍消费旧 links。仅替换
Context 内一个数量比较不能解除这些前置阻断。修复前通过真实 Priority/Feed
物化及 Lifecycle 后调用独立 Context/Asset Product，首批 **3 failed**，确认
旧关联与当前有效数量不一致；前一步 canonical 数量减少案例仍 PARTIAL。

最小读取修复在现有内存 scope 完成：Asset UoW 注入既有有效 Thesis Signal /
跨投资者关联读取端口；一次准备 ACTIVE Feed 所关联三类 Event 的有效组，
Thesis 复用事实时间读取和真实链接分组，跨投资者复用来源/完整性/事实时间/
投票者及关联范围等价去重。严格校验必要 Priority/Feed 已按该组刷新（身份、
分类、等级、数量、标题、公开 context、事实时间），非空有效证据下不一致
直接报错，不删检查、不读侧替上游修正。全失效 ACTIVE 行从消费集合排除，
不制造有效零投影；数据库状态/旧关联/来源内容不变。

scope 携带 context_evidence 与已验证关联的跨来源引用，内存 evidence links
只保留该 Event 实际关联的有效代表，Signal 时间为只读副本。原历史 Signal
repository 与所有持久化记录保留；没有虚拟 source 或补造关联。Asset Product
现有 scope 消费者共用这套输入以通过前置检查，未重写其算法；独立 Discovery/
Evolution 等其他入口不做全仓修复。Context 独立 asset/candidate/batch 生产
入口改用同一 scope loader，避免先通过旧 standalone Discovery 检查。batch
按 listing scope 复用结果，不让每个 Context 子区块重新查询完整来源链。

Context 的 activity/investor/timeline 使用校正后的实际关联集合与来源事实，
跨方向 Signal.investor_id 为空时仍使用验证过的 Opinion 投票者，Attention-only
不算方向投资者。保留既有 Feed/Event 观察窗口成员分配与 current/previous
边界，不新增逐观点窗口算法；有效观察时间替代污染的旧时间。Thesis 变化
计数只消费关联 material 来源，未关联/非 material 的比较产物不冒充变化；
Context cross_state 在原窗口截止规则内只使用有效关联所支持的来源引用，不
用失效较新产物或计算时间填补状态。新/返回投资者仍只是观察集合的差/交，
两个窗口差异不证明完整行为变化、共识形成或消失，限制文字保持 UNKNOWN。

新增 `test_effective_asset_context.py` **29 passed**，覆盖 Thesis 数量减少、
跨投资者失效/等价关联、合法非全局代表、三类投影五字段未刷新保真、
全失效排除、实际投票者/Attention-only、事实时间/历史窗口、asset/candidate/
batch Context 一致、Asset Product context 字段一致、真实 HTTP 200 具体字段
及不一致时 422、逐表零写入、保留基线/历史关联、共享读取规模。原 scope
计数单测补充已验证端口及准确投影 fixture，未 mock 掉新增集成有效 selectors。

此前真实 canonical 数量减少场景现在 **PRODUCT_VERIFICATION SUCCESS**、整轮
SUCCESS：经过实际 raw 范围选择/既有 Analysis 与派生/Event/Priority/Feed/
Lifecycle/Asset Product/Context，接着验证 Feed 与 Asset/Context HTTP 具体
数量和投资者，并核对查询零写入。只使用外部采集/comparator/时钟 fixture，
没有绕过 scope 或产品验证。另对必要产品读取单点注入真实 ValueError，
canonical 仍 PARTIAL_FAILURE 且 PRODUCT_VERIFICATION PARTIAL；前一步 FEED /
FEED_LIFECYCLE 失败阶段及来源变化保真测试继续通过，没有捕获后标 SUCCESS。

实际 `.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider --tb=short`：
本次及 canonical/此前十六项回归 **504 passed**；架构/实际 API/上游/相邻
产品消费者 **126 passed**，共 **630 passed**。最终本次+canonical 重跑 36
passed，ruff check/format、git diff --check 通过，只有既有 HTTP 库弃用警告。
字段形状、窗口含义与其他 Event 语义保持，未改前端或降低接口错误约束。

SQL 实测（无 Portfolio 引用 fixture）独立 Context 和整次 Asset Product
在 1 个完整 scope、2 个 Event 下均 **30 SELECT**；6 个等价完整 scope、12 条
旧 Signal 下均 **75 SELECT**（每新增 scope 9 次，共用 asset/window_end 引用
读取）。跨 Context 子区块/产品组合不再重复重建来源链；同次来源准备复用，
只读且逐表内容完全不变。批量 Context 以每个 Asset scope 读取一次，不宣称
全仓查询常数成本，也没有优化全部 Feed 查询。

未调用真实 LLM、未执行生产刷新/恢复/迁移/维护、未修改业务数据库或操作
现有服务，基线审计与快照不改写。**尚需真实运行验收** canonical 当前 scope、
延期历史投影、真实来源阶段变化与产品验证结果；隔离成功不证明生产失败
行已经纠正或服务已恢复。仍保留其他 standalone 产品读取入口有效性、
历史污染、未观察依赖/全局 policy 协调、独立并发/PG 锁、跨投资者回流、
真实共识演化及用户验收缺口。路线只记录本子任务，停止，不自动执行生产
验证，不宣称整个 Inbox 或可信变化阶段完成。

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
