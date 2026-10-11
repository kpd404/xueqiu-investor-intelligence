# Project Roadmap

## 2026-10-11 15:15:18 自然槽位 — 单轮 SUCCESS；持续运行未验证

本条完成上次恢复记录的待验收项，只观察指定槽位，不修改代码、配置、业务
记录或服务安排。香港时间 14:48:54 保存 31 张表内容指纹及源/派生 ID 基线；
15:04 再核对 scheduler 27956/14188 的创建时间、实际命令及等待日志，而非
仅依据历史 PID。资料保存 `.local/natural-slot-20261011`，不覆盖原基线。
等待期间不查询业务库；目标槽位前 10 秒起以 10 秒间隔只读记录运行与锁。

计划 2026-10-11 15:15:18.092621，实际开始 15:15:18.220509（约晚 0.128 秒），
run_id `d6a86b2d-2312-44ee-93af-34ab7b9eac32`，trigger SCHEDULED。
结束 15:17:18.316420，SUCCESS，约 120.096 秒，无失败阶段或错误码。
各阶段均 SUCCESS：

| 阶段 | 秒 |
| --- | ---: |
| COLLECTION | 33.922 |
| ANALYSIS | 72.896 |
| RESOLUTION | 0.529 |
| DOMAIN_STATE | 3.923 |
| CROSS_INVESTOR | 0.341 |
| SIGNALS | 0.905 |
| INTELLIGENCE_EVENTS | 5.918 |
| PRIORITY | 0.221 |
| FEED | 0.187 |
| FEED_LIFECYCLE | 0.230 |
| PRODUCT_VERIFICATION | 0.502 |

Following 实际找到现有页面并完成原 max_batches=1，16 条观察/新增事实；
Profile 沿原 48 小时、2 页、30 秒预算，8 位均成功，73 条观察，29 条新事实。
总观察 89（含 7 条来源重叠），唯一事件 82，新 RawEvent 45、既有事件 37；
CollectionRun +9、Observation +89。此次没有再出现连接/页面为空、认证或
适配器错误；仅证明本轮实际访问成立，不保证以后不再失效。

Analysis +45：37 NO_OPINION、8 PARTIALLY_RESOLVED、0 FAILED，不能把阶段
SUCCESS 说成所有提及均完整解析。Opinion、ThesisChange、Attention 各 +1；
Snapshot +3、Alignment/Consensus 各 +2、Signal +1（候选 13、复用 12），
evidence link +1、state change +1、Investor +1。Event/Priority/Feed 没有新增行，
但原有派生字段有更新；完整增量见 comparison.json，不将零新增说成零写入。
这些是目标自然调度的正常增量，本次验收没有独立业务写入或维护。

实际 DeepSeek 请求 48：Opinion 47（包含 2 次重试）、Thesis 1（0 次重试）；
48 条 HTTP 200 回执，45 条 Analysis 的 provider 元数据保存供核对。
费用账单/扣费回执未取得，不估算费用，不宣称零费用。

12 次 RUNNING 采样均为 PostgreSQL backend 28372 持有原 advisory lock；
客户端端口 50125 实际映射 scheduler 14188。采样中连接可合法 idle；
15:17:28 SUCCESS 采样及产品核验后锁均为空，随后同一 backend 为 idle，
advisory_count=0，连接仍建立，未归还成带锁污染连接。首次采样在运行开始后
约 10 秒，证明为采样证据，不伪称每个瞬间都有连续追踪。没有解锁或终止连接。
运行时状态 API 为 UNKNOWN / latest_status RUNNING，开始时间保留、结束为空；
latest_failure 字段仍是旧 CDP_UNAVAILABLE 的历史失败，不能误读为本轮错误。

结束后健康/状态 API 200，状态回到本轮 SUCCESS；近期 ACTIVE Feed total=3，
返回 3，约 2.342 秒。受影响标的 SZ159981，asset
`36a94306-59a8-4443-beae-40f3ddf45289`，Product 200（约 0.092 秒）；
Feed `dba6d5c5-1efa-4f59-834e-c1d619b08e9b` 的证据入口 200（约 0.092 秒）。
响应为 THESIS_CHANGE_OBSERVED，5 个有效 Thesis Signal/source、1 位投资者；
证据页 5 组一致，6 个去重 RawEvent 引用均能解析、投资者/发布时间匹配、
本地正文可读且 source URL 可用。最大事实时间为 2026-10-10T11:43:51Z
（香港 19:43:51），Feed 与证据一致，没有改为今天的计算时间。
本次不重新打开远端原帖验证全文。Context/投票与公开字段沿现有有效入口。

目标开始前后 Research Candidate 与 Inbox 全表内容指纹一致。自然轮次后的
产品查询前后所有业务表指纹也一致，区别于自然调度本身的业务增量；没有错过
前基线。外部第二轮未发生，本次没有创建候选、用户处理操作、手动刷新或补偿。

同一 scheduler 创建身份仍存活，日志准确记录目标 SUCCESS 后返回原循环；
按完成后 60 分钟 sleep 推算下一次约 16:17:18（不是数据库持久化计划时间）。
原 backend 2436/27848、Vite 20112、CDP 18164 与调度安排均保留，不观察第二轮。
环境在本轮就绪、指定自然轮次完整成功、scheduler 原安排等待分别确认。
长期持续运行、网络断连互斥、稳定性能、远端正文及历史完整性仍未验证；
historical completeness UNKNOWN，不宣称 Operational MVP 全部完成。

## CDP / scheduler 恢复与状态修复部署 — 2026-10-11；自然轮次待验收

保留全部已有修改及 VERIFIED 用户能力。本轮仅恢复现有 runtime，无迁移、
旧 RUNNING 维护、手动 refresh 或情报修改。核查资料位于
`.local/runtime-recover-20261011`，HEAD e7c0d6fdcc4158037201b4549718305956c22beb；
部署前 working diff SHA256
`eedd8948ae1e60c505adfe6293196a8228f3fbe0101e1f28f9977d8295d0e2d4`，
未跟踪实现指纹和部署运行文件 SHA256 已保存，不以 HEAD 单独代表代码身份。

更正上轮受限进程查询的边界：提升权限重新核查确认原 Vite 20112（5173）、
专用 Edge 18164（9222）始终有现存进程，并非本轮重启；原 profile 为
`.local/edge-cdp-profile`。当前 8000 无监听，项目 backend / scheduler 无活进程。
未操作普通 Edge、没有清 profile、复制认证或新建身份。PostgreSQL 为 6480，
5432 可用；无当前 advisory lock。历史 PID 元数据先备存，不作为活进程证明。

最新失败 `4ab9c8e7-dfa6-4757-b4a4-088707a838c0` 的原错误摘要准确为
`connected browser has no existing page for Following Feed observation`：
当时连接浏览器后 pages 为空，由 adapter 报 CDP_UNAVAILABLE；不能归因为
端口不可达、认证失效或浏览器崩溃。为何当时页面为空、scheduler 后续为何消失
缺少退出日志，原因未知。Windows 原登录启动任务为 Ready / enabled，最后
launcher 结果 0；这不证明 scheduler 正常退出。该任务没有被修改或额外触发。

当前真实 CDP 为一个 context / 一个雪球页面
`https://www.xueqiu.com/u/6238316110`，title 因思明见；读取现有 DOM，包含
“已关注”“设置备注”等认证后操作，没有现有登录/风控标记。保留页面、不导航、
不捕获 Following payload、不开采集、不读 Cookie/令牌；可读页面与认证 UI
不替代下一轮 Following 接口和全链路验证。

沿原 uvicorn 命令启动唯一 backend 2436/27848，8000，加载现有工作区与
operations/status.py 的 RUNNING→UNKNOWN 修复；未改 FAILED→SUCCESS。
前端仍为原 Vite，不重启。沿原 scheduler 参数启动唯一 27956/14188，显式
CDP `http://127.0.0.1:9222`（Settings 中默认 endpoint 为 null，原命令也显式传入）。
保持 60 分钟、max_batches=1、既有 Profile bounded 预算，以及 DeepSeek /
deepseek-v4-flash / responses / max_retries=2 和原批准 policy；无预算切换。
原 loop 不保存未来计划；以最后完成时间 20:15:18.092621 的 60 分钟相位跳过
停机期间槽位，`--not-before 2026-10-11T15:15:18.092621+08:00` 恢复下一未来槽。
不声称该时刻是数据库保存的计划，不补跑漏失轮次，不启动第二实例。
原启动方式、PID 记录和失败恢复边界保存：新进程失败时只处理核对归属的新进程，
回到先前 backend/scheduler 未运行状态；不降级数据库或更改原浏览器/前端。

香港时间 14:44 只读就绪验收：health/DB 200，status 200（约 0.033 秒），
OpenAPI 200；状态仍准确为较新 FAILED/COLLECTION/CDP_UNAVAILABLE，freshness
STALE，没有被较早 SUCCESS 或旧 RUNNING 覆盖。API next_expected_refresh_at
仍是按上次 SUCCESS 推算的历史值，不能当作当前 scheduler 实际等待时刻；
实际 15:15:18 由启动参数及 scheduler startup waiting 日志核对。
近期 ACTIVE Feed 返回 2 条，200，约 2.497 秒；现有样本 asset
`6f578ae9-1320-414e-bf30-87f7975a723e` 的 Product 200（约 0.708 秒），
Feed `9686a729-ef1f-4079-b614-a1dbd242b5c5` 的证据入口 200（约 0.856 秒）。
这些是恢复前已有有效样本，不冒充未执行自然轮次的受影响产品。
恢复前后 31 张表指纹一致，包括候选、Inbox、两条旧 RUNNING 和来源；无 LLM。

自然调度验收 PENDING：本次核查尚未到 15:15:18，scheduler 只在 startup waiting。
尚无本轮 run_id、阶段结果、业务增量、LLM/费用回执及运行中锁证据，不能用
就绪探针或昨日 SUCCESS 替代。保留已恢复的循环与原 Windows 登录启动安排；
没有观察脚本/自动化、手动任务或第二轮刷新。环境就绪及状态修复部署通过，
自然轮次、长期持续运行分别未验证。远端正文、性能、网络断连互斥、FAILED
补偿和跨投资者回流不扩展，历史完整性保持 UNKNOWN。

## 历史 RUNNING 与运行状态边界 — 2026-10-11 只读核查及最小修复

保留刷新锁修复、Research Candidate / Inbox VERIFIED 及全部已有修改。
香港时间 14:32:05–14:35:07 对真实 PostgreSQL 只读核查，资料位于
`.local/running-audit-20261011`；HEAD 与工作区/未跟踪内容身份保存于 before/after。
两条未完成记录：

- OperationalRefreshRun `5a706cf9-2c3c-4719-8980-633e8ac18e8e`，SCHEDULED，
  2026-09-22 19:05:15.601392 开始，19:05:15.603367 创建；RUNNING，
  finished_at、failure_stage、failure_code、summary 均为空。
- CollectionRun `5283b24a-de9e-45ef-8788-a1aaca202916`，ENTITY_HISTORY /
  BROWSER_CDP / xueqiu_profile_history_cdp，2026-09-22 19:05:30.950774
  开始/创建；RUNNING，ended_at、stop_reason、summary 为空，coverage UNKNOWN。
  Profile scope 为 `c2d0352b-9783-47fb-bab6-33b4c6f69ffd:9957341637`，
  没有 CollectionObservation。两实体均无 updated_at，不能提供不存在的更新时间。

当前没有可确认的本项目 scheduler/后端/前端进程或刷新 advisory lock，原 PID
元数据仍保留；没有停止、重启或恢复原 runtime。上述历史行不能描述当前活动，
但结束时刻、阶段及具体中断原因证据不足，分类为“执行结果未知”；没有把年龄、
当前无锁或相近开始时间当作明确失败/关联证明。整轮记录没有保存来源 run ID，
不能证明两行属于同一任务；缺失来源记录不能补造。

已确认旧行未覆盖较新结果：最近为 `4ab9c8e7-dfa6-4757-b4a4-088707a838c0`，
2026-10-10 20:15:15→20:15:18 FAILED/COLLECTION/CDP_UNAVAILABLE；较早
`2b0a47c8-c4d0-47b5-8115-c356ebaf93a1` 的 SUCCESS 仅供 freshness 使用。
状态查询按 started_at 选最近运行；canonical 资格由 advisory lock 决定；
增量分析/恢复依据有效 Analysis 和源事件，不依据未结束运行计数。
Collection provenance 保留原始 run_status，仅描述历史归属；无 Observation 的
旧来源行不构造有效事实或恢复目标。本轮没有复现旧 RUNNING 阻塞选择/恢复。

实际复现另一最小错误：最新 RUNNING（包括缺少日志/来源的唯一未完成行）
落到 ACTION_REQUIRED，页面因此显示“刷新失败”。只修改 operations/status.py：
RUNNING 对应 UNKNOWN，保留最新身份、原始时间及 RUNNING 技术值，不推断活跃、
结束、失败或 SUCCESS。UNKNOWN 使用现有前端“刷新状态未知”标签；没有新增
状态、监控、恢复机制或改写历史。最新失败仍优先于旧 SUCCESS，未降低真实告警。

数据库及 HTTP 失败先行 2 failed/3 passed；修复后状态/真实 canonical 入口资格、
失败优先、历史保留、全表零写入、分析恢复及用户能力回归合计 46 passed；
另有真实隔离 PostgreSQL 锁回归 13 passed，限定 Ruff / diff 检查通过。
canonical 入口资格测试执行真实 begin/finish 和竞争边界，不执行采集/provider；
恢复资格由既有恢复回归证明，不表示进行了真实补偿。SQLite 隔离路径不替代
真实 PostgreSQL 锁验证，两组分别报告。

独立临时 8127 后端（27256/11752）只读健康和状态 API 为 200；状态约 0.097 秒，
返回 ACTION_REQUIRED / STALE / 最新 FAILED/CDP_UNAVAILABLE；真实数据库没有
最新 RUNNING，UNKNOWN 分支由隔离真实 HTTP 路径验证。临时进程关闭，端口不再
监听。核查前后 31 张表内容指纹完全一致，没有外部自然调度增量；没有 LLM、
刷新、恢复或运行记录维护。原 runtime 未被启用，本次代码没有部署到原服务。

不需要白名单维护来解除已证明的阻断；当前证据也不足以提出旧行的准确终态和
结束时间，未准备强写计划。网络断连、运行实体缺少 worker/session 关联与更新
时间、长期调度及当前 runtime 未运行的原因仍未验证；没有扩展其他恢复事项。
历史完整性继续 UNKNOWN，不宣称持续运行或 Operational MVP 全部完成。

## PostgreSQL 刷新锁连接生命周期 — 2026-10-10 修复及有界真实验证

保留全部情报修复、Research Candidate 与 Inbox 用户处理 VERIFIED。
本轮仅修改锁连接生命周期、canonical 清理边界及 scheduler 重启时间协调，
没有修改情报、来源有效性、用户工作流或采集/分析预算。

只读证据：原刷新锁键 4831927501 为 session advisory lock；PostgreSQL backend
8120 的客户端端口 57727 映射到原 scheduler 12396。最后实际任务 c012843b…
16:14:27 SUCCESS，17:14/18:14 两轮 SKIPPED_ALREADY_RUNNING，连接 idle；
9 月 22 日旧 RUNNING 行单独保留。不能单凭 idle 认定遗留；本轮真实执行期间
锁连接也可合法 idle。历史 acquire/unlock 的逐次 PID/重入计数没有保存，无法
唯一还原旧生产连接轨迹，不能把某一条静态假设直接当作完整生产根因。

隔离库 snowball_lock_test_5907e9e562bb 用真实两连接池复现：业务 Session
获取锁后 commit 将连接归还池，强制借走原连接后 release 在其他 backend 执行，
原锁仍在；重复获取同一对象使 PostgreSQL 重入计数不归零。原 unlock 返回值
被忽略。失败先行 3 failed/1 passed；修复后 PostgreSQL 13 项通过，包括真实
canonical 全阶段、失败/rollback、取消、最终清理异常、重复获取、竞争拒绝、
连接断开/失效、释放失败与污染连接丢弃。编排/用户工作流 35 项、canonical
范围与 Thesis/跨投资者生命周期 78 项回归通过；限定 Ruff 和 diff 检查通过。

锁改为独立 PostgreSQL Connection 租约，获取、保持和检查释放绑定同一实际
会话；业务 commit/rollback 不归还该锁连接、不提前解锁。同对象重复获取幂等；
竞争失败关闭未持锁租约；释放失败 invalidate 后关闭并抛错，不用 unlock_all。
canonical 最外层 finally 保证最终统计/异常/取消也清理，Session 始终关闭；
释放失败准确记录 FAILED/LOCK_RELEASE，不将其静默保留为成功。
锁键及所有 canonical 入口一致，未增加表或修改数据库连接池配置。

确认原任务结束后暂停后续调度，记录代码指纹、PID、日志与 31 张表基线。
专属控制台核对仅属于原 scheduler/控制器后，用正常 Ctrl+C 退出 16900/12396；
日志记录 stopped，原锁随连接关闭消失，无 Stop-Process/pg_terminate_backend
或强制释放。真实双连接无业务探针 acquire→hold→竞争拒绝→release→再次获取
通过；部署/探针期间全部 31 张表不变。

修复版 scheduler 最终为 4124/6932，原 backend 25620/25984、Vite 20112 未动。
新增可选 `--not-before`（默认不变），只为重启保留原下一轮 19:14:27.924 的时间，
不提前触发任务。第一次启动在地区格式时间解析时退出，未执行任务，错误日志
保留；维护脚本改用带时区 ISO 时间后启动成功。
启动实际加载的工作区身份、原命令、生产文件 SHA256 和部署记录位于
`.local/lock-fix-20261010`，HEAD 仍为 e7c0d6fdcc4158037201b4549718305956c22beb，
不能只用 HEAD 代表当前未提交实现。完整工作区/未跟踪指纹分别保存于部署计划、
live-lock-probe 和 final-audit；最后文档记录在代码部署后写入。

原计划自然调度 `2b0a47c8-c4d0-47b5-8115-c356ebaf93a1`：香港时间
19:14:27.992617→19:15:15.762901，SUCCESS，11 阶段全部通过，无失败阶段。
24 次 RUNNING 采样始终同一 backend 9988，客户端端口 64280 映射 scheduler
6932；结束及后续核查锁为空，scheduler 回到等待。仅观察这一轮，没有手动
refresh、第二轮或监控自动化。代码修复、真实无业务锁验证和本轮自然调度
分别通过；这一样本不能证明长期持续运行。

本轮原配置 DeepSeek Opinion 请求 18 次（含 3 次重试），Thesis 比较 0 次，
18 条 HTTP 200 回执，最终分析 provider token 元数据可查；费用账单未取得，
不估计费用。正常调度新增 RawEvent 15、Analysis 15、Signal 2、Event 1、
Priority/Feed 各 2 等正常增量，完整差异见 final-audit；不能宣称真实库零写入。
Research Candidate、Inbox 用户记录和 Alembic 指纹始终不变，未做历史维护。

剩余边界：每个 active refresh 占额外连接池槽；网络/服务端断连会使 session
锁消失，清理时能检测并报错，但未实现分布式 fencing，不能保证未感知断连
期间的互斥。9 月 22 日历史 RUNNING 行未纠正，长时/高并发/多轮持续运行未验证。
历史完整性 UNKNOWN、跨投资者回流、FAILED 补偿、性能和界面缺口均不扩展。

## Inbox 用户处理真实启用 — 2026-10-10 VERIFIED（有界用户能力）

本条更新下方“隔离通过、真实未启用”的当时状态，保留其历史记录及此前
Research Candidate VERIFIED。没有新增功能或修改情报语义。

真实库 snowball 从 20261010_0025 执行
`.venv\Scripts\python.exe -m alembic upgrade 20261010_0026`；仅新增
inbox_user_states。Feed ID 主键兼唯一约束、RESTRICT 外键、非空 BOOLEAN
阅读/处理状态和创建/更新时间已核对；没有单独状态枚举 CHECK 或额外索引。
迁移后新表为空，没有自动初始化记录；既有业务表不变，仅 Alembic 版本变化。

完整 PostgreSQL 备份位于
`.local/inbox-enable-20261010/backups/snowball-20261010-184803.dump`，
3,503,572 字节，SHA256
`40de889935ece789cf295e01581f4da2b43c8b5002352bb1abc58bd2dd9037a5`。
实际恢复到新隔离库 snowball_restore_verify_inbox_4018840b2496；30 张表内容
指纹一致。结构仅既有 Research Candidate CHECK 的 PostgreSQL 类型转换文本
不同（数组整体转 text 与逐元素转 text），独立只读验证等价；其他结构一致。
未覆盖真实库，恢复验证库保留；未重复候选迁移、未改旧 SQLite 0011。

实际代码 HEAD e7c0d6fdcc4158037201b4549718305956c22beb，启用时工作区差异
SHA256 11efb427746852dee60907c6bee30a2b73556a79df2996636659325128d84ed9，
未跟踪代码逐文件指纹及启动身份保存在 preparation.json。启用及重启期间代码
身份一致；本条文档更新在运行验收后进行。保留全部原修改。
已核实后端沿原 uvicorn/项目目录/8000 替换：25436/4124 → 9684（启用）→
25620/25984（重启持久化）。前端 Vite 20112、5173 未重启，代理为 8000；
仅一套目标后端。健康/数据库、OpenAPI、Inbox 三种筛选及状态 API、Feed、
紫金矿业 Asset Product/证据和既有候选 API 均为 200。

真实浏览器 Inbox → 当前有效紫金矿业证据 → 返回 → 显式已读 → 未读排除
→ 显式已处理 → 待处理排除 → 刷新 → 后端重启 → 状态保持 → 显式恢复通过。
唯一验收 Feed `3b764c33-d00e-4a9a-aa4e-9da61d3ae5c0`，初始无用户记录，
默认 false/false；操作后 true/true；最终 false/false。保留默认状态验收记录。
两次同值 API 提交不改变整行或更新时间；重启前后 ID、状态、创建/更新时间
完全一致。未创建或修改候选，不伪造来源或生命周期反例；相关反例沿用隔离测试。

暂停区间最终指纹审计仅 Alembic 版本、新表及该用户记录变化，29 张既有业务表
完整不变，包括 Research Candidate、原始来源、Signal/Event、历史关联、Priority、
Feed 和生命周期内部数据。没有采集、refresh、恢复历史、LLM 或性能重构。
本轮三种 Inbox 列表约 0.919–0.939 秒（6 条），既有 Feed 单次 1.031 秒，
Product 0.267 秒、证据 0.337 秒；这些样本不替代稳定性能未达标记录。

原 scheduler 16900/12396 在任务结束后暂停、验收后恢复同一进程原循环，
没有中断任务或额外触发。发现其 idle 连接持有刷新锁：最后实际任务
c012843b-f8c0-45a6-8e27-1e75a39c15f0 于 16:14:27 SUCCESS，17:14/18:14
两轮 SKIPPED_ALREADY_RUNNING。依据数据库客户端端口及 PID 确认归属后，
本轮保留锁及 9 月 22 日历史 RUNNING 记录，不强制释放、不顺带修复。
调度“进程恢复”不等于“后续刷新能够成功”，持续运行仍未通过。

资料及截图保存于 `.local/inbox-enable-20261010`。当前 Inbox 仍显示“标的视图”
和“标的情报”导航语义、侧栏入口排版待整理，本轮仅记录。新证据自动恢复未读、
跨投资者回流、通知/批量处理未实现；远端正文超时、历史完整性 UNKNOWN、稳定
性能及持续运行缺口保持，不宣称 Operational MVP 全部完成。

## Inbox 用户处理 — 2026-10-10 实现及隔离验收通过；真实启用未执行

用户可在当前 `/inbox` 明确标记已读/恢复未读、已处理/恢复待处理，按全部、
未读、待处理筛选，并继续查看证据或加入研究候选。筛选数量、分页和排序在
既有有效证据校正之后计算；用户状态不使失效情报重新进入 Inbox。
阅读、预取、加入/归档候选均不自动改变处理进度；新增证据不自动恢复未读。

现有 Feed 是系统投影，Research Candidate 是用户研究意图，均不能承载独立
阅读/处理进度。本轮仅新增 `inbox_user_states`，以真实 Feed ID 为主键及限制删除
外键，保存两个独立布尔值和创建/更新时间；无记录默认未读/待处理。
用户操作不写 Feed.context，不改变 Feed.state、Priority、来源或生命周期基线。
重复显式提交幂等；失败不显示成功；浏览器返回重新读取状态并保留筛选及页码。

失败先行：新数据库 HTTP 测试在实现前因路由不存在失败 2 项；实现后相关后端
114 项通过（含 Thesis/跨投资者有效读取、Thesis 回流和 Research Candidate），
前端 60 项通过，TypeScript/Vite 构建及限定 Ruff 检查通过。
隔离 PostgreSQL `snowball_inbox_test_837e36ede309` 实际执行完整 Alembic
0001→20261010_0026 并重复升级验证；SQLite 实际 0025→0026 增量验证通过。
不将旧 SQLite 0011 完整安装路径声明为已修复。

独立 8113/5176 服务、结构化 fixture、固定来源窗口下真实浏览器完成：
未读筛选→读取有效前后观点→显式已读→加入候选→返回仍待处理→键盘显式已处理
→页面刷新→隔离服务重启→已读/已处理保留→显式恢复。
验收 Feed `139cd013-fff0-4dc3-8b40-a9e2d760bb62`；隔离候选
`1c01cf05-4f24-492d-915b-929653a40c1c`。窄屏布局和证据返回路径已检查。
隔离 31 张表前后指纹仅 inbox_user_states 与 research_candidates 变化，其余
29 张（含来源、Feed、历史关联及内部基线）不变。验收资料位于
`.local/inbox-acceptance-20261010`；验收结束停止本轮隔离服务。

真实业务库未升级 0026，未替换真实 runtime，原后端/前端/scheduler 未操作。
本能力真实启用状态为 NOT ENABLED，不标记整个能力 VERIFIED；此前 Research
Candidate 真实启用 VERIFIED 保持。外部 scheduler 原安排继续，不能将其写入
归因于本轮或宣称整个真实数据库零写入。
Feed 性能未达标、远端正文超时、历史完整性 UNKNOWN、跨投资者回流、候选页面
样式/导航问题继续保留。没有新增自动提醒、批量处理、通知或账户功能。

## Research Candidate 真实启用 — 2026-10-10 VERIFIED（有界用户能力）

在用户明确授权调整既有 runtime 后，确认数据库仍为 0025，不重复迁移。
确认 canonical refresh 锁空闲后暂挂原 scheduler（16900／12396），没有中断任务；
验收结束恢复同一进程与原循环，未通过重启调度器触发新任务。
仅替换归属已核对的后端：19184／19236 → 13280（首次启用）→
25436／4124（真实重启持久化）。沿原 Python/uvicorn 命令、项目目录、8000
地址启动，没有第二套后端；Vite 20112、5173 保持原样，实际页面加载当前实现。
加载代码 HEAD e7c0d6fdcc4158037201b4549718305956c22beb 加工作区及未跟踪实现
指纹，保存于 `.local/research-enable-20261010/preparation.json`；重启前后实现
指纹一致，保留全部已有修改。没有新增功能或改动 Intelligence 语义。

健康/数据库、候选列表与 OpenAPI 路由检查通过；近期 Feed 200、6 条，
本轮单次 1.270 秒；中际旭创 Asset Product 200、0.034 秒；证据 API 200、
0.067 秒，1 组有效关联、2 位方向投票者。单次速度不替代此前未达标记录。

真实浏览器完成 Inbox → 中际旭创证据 → 展开本地原文 → 手动保存功能验收记录
→ 填写用户原因/问题/笔记 → 研究中 → 刷新 → 返回准确来源 → 重复添加复用
→ 后端重启 → 再次打开 → 归档 → 刷新仍归档。唯一候选
`b7daa082-8c44-4b49-8e6d-b9cb12a1f12c`，创建于香港时间
15:48:51.579054，最终 ARCHIVED。两次提交、1 条来源引用，没有重复候选；
身份、创建时间、用户内容和引用在真实重启后完整保持。
实际关联 Alignment de048fb3-f41b-449a-8dc1-1ece09d67f81，来源 RawEvent
297795c1-e3d7-4065-bcba-b26eada12a02／0e60cae2-f944-4754-862b-86cb12d8eb03。
原帖 https://xueqiu.com/7448680761/411737835 与保存地址匹配；本轮核对地址，
没有把远端正文可读标记为通过。本地保存原文可读且区分作者/转发及 AI 提取。

香港时间 15:52:19 的暂停区间终态核对：30 张表仅 research_candidates 变化，
其余 29 张（含 Alembic、运行表及全部既有业务表）指纹不变；未修改来源、
Signal/Event、关联、Priority/Feed 或内部生命周期基线。用户记录只由明确操作
保存/编辑；既有 refresh 没有该用户实体写入路径，本次不触发刷新作额外验证。
调度恢复后自然运行单独归因，不能把这一暂停区间结论扩展为持续零写入。
证据和最终截图保存在 `.local/research-enable-20261010`。

本标记仅代表 Research Candidate 的本次真实入口及完整有界工作流通过。
不代表持续运行或 Operational MVP 整体完成；Feed 性能、远端正文、历史完整性
UNKNOWN、跨投资者回流、样式与导航问题继续保留。本轮停止，不推进其他功能。

## Research Candidate 真实迁移 — 2026-10-10（启用待协调）

真实 PostgreSQL `snowball` 已从 `20260920_0024` 通过实际命令
`.venv/Scripts/python.exe -m alembic upgrade 20261010_0025` 升到
`20261010_0025`。仅新增 research_candidates 表、主键、标的 RESTRICT 外键、
状态 CHECK 和未归档标的部分唯一索引；结构已核对，候选记录为零。
迁移在既有 refresh advisory lock 保护下执行，没有调用 refresh。
迁移紧邻前后，28 张既有业务表内容指纹不变，仅 Alembic 版本更新。

完整备份位于 `.local/research-live-20261010/backups/snowball-20261010-154037.dump`，
3,479,052 字节，SHA256
`d0fd5605184f49f3a658be4525685f914847750dafd51eb4ac73b72d9e33ec77`。
pg_restore 目录可读，并实际恢复到新建隔离库
`snowball_restore_verify_research_984af1bd7e1d`；全部 29 张表指纹与准备基线一致。
代码 HEAD e7c0d6fdcc4158037201b4549718305956c22beb 及工作区、未跟踪实现指纹
保存于 `.local/research-live-20261010/plan.json`，没有只用 HEAD 标识运行代码。

**未启用，真实浏览器工作流未验收，不标记能力 VERIFIED。** 原后端 8000、
前端 5173 和 scheduler 由另一组既有 runtime 管理，本轮保持原样。
旧后端尚未加载候选 API；必须先协调该运行安排，再单独替换后端以加载明确的
当前代码，避免同时出现不同版本业务写入服务。没有创建验收候选、没有执行
真实服务重启持久化检查；此前隔离结果不代替这些验收项。
外部 scheduler 存在，其后续自然运行不能归为本轮；未启动新的 scheduler、
未采集、分析、调用 LLM 或刷新。远端正文、Feed 性能、历史完整性 UNKNOWN、
跨投资者回流及持续运行限制保留；样式和导航问题单独待处理。本轮到此停止。

## 用户能力增量 — 最小 Research Candidate（2026-10-10）

已实现并通过隔离前后端浏览器验收：Inbox／Asset Product／证据页面手动加入
研究候选，保存用户研究原因、待验证问题和笔记，查看列表及详情，切换待研究、
研究中、已归档，明确恢复，并返回具体证据和原帖地址。用户判断独立标识，
没有自动导入 Discovery、LLM 问题生成、评分或买卖建议。

DiscoveryCandidate 是查询投影，现有原始事实与 Intelligence 实体不能承载用户
意图，故新增唯一 `research_candidates` 用户记录表及 0025 Alembic 迁移。
同标的仅一个未归档候选；重复添加复用并合并准确来源引用，不覆盖原笔记和
创建时间；提交身份及内容指纹保证重放幂等，归档记录不会自动打开。
来源校验复用证据读取边界；记录保存具体来源、Opinion／RawEvent 身份，
失效后保留用户记录并区分当前有效、历史引用、未验证与不可用，不借用其他证据。

验收环境为独立 PostgreSQL `snowball_research_test_77cc54fe6b7f`，端口
8102／5175，结构化 fixture 标的 `5706d694-eb5e-43b9-9930-2d77d98b9fa5`。
浏览器完成证据→保存问题→研究中→刷新→重启隔离前后端→再次打开→返回来源，
候选 `f5191e0b-2efe-4d2b-8dc7-590d12733d8e` 的身份、创建时间和内容保持。
测试覆盖关系拒绝、重复引用、归档恢复、来源失效与历史阅读、API 错误、
源表保护及迁移重启持久化；后端及保留回归 109 项、前端 57 项与
TypeScript/Vite build、Ruff 检查通过。重启后的只读验收区间，隔离库全部
30 张表内容指纹无变化。
新 PostgreSQL 实际 0001→0025 升级通过；SQLite 已有 0024 结构到 0025 的实际
Alembic 升级及重复升级通过。全新 SQLite 仍在旧 0011 约束 ALTER 失败，
本次没有修复历史安装缺口。

真实业务库未迁移、未写入测试候选；外部后端、前端和 scheduler 保持原样，
仅停止本次隔离服务。未调用真实 LLM、采集、refresh 或维护。
真实产品启用仍需单独批准业务库迁移及运行验收；本次仅完成隔离用户工作流。
远端原帖正文超时、Feed 后续约 3 秒及首次波动继续未通过；跨投资者回流、
已读状态、通知、持续运行和 Operational MVP 整体均未完成。历史完整性 UNKNOWN。

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

### 有界真实运行验收准备与只读消费检查 — 2026-10-10

**BLOCKED：canonical refresh 尚未执行，不标记整链路 VERIFIED。**
香港时间 01:35:41–01:40:15，HEAD 为
`e7c0d6fdcc4158037201b4549718305956c22beb`，运行前工作区干净，
HEAD diff SHA-256 为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
批准 provider/model 为 deepseek/deepseek-v4-flash，原 policy 未切换。
计划使用现有 canonical CLI：CDP 127.0.0.1:9222、max-batches=1，其余默认；
Profile 8 人/48 小时/2 页/每人 30 秒，未扩大名单或历史窗口。
自动审批拒绝真实刷新，理由为尚未明确授权采集原文传输至外部 DeepSeek。
没有通过其他入口绕过；无新 run_id、无采集、无 LLM 请求、无业务增量。
Collection 至 PRODUCT_VERIFICATION 各阶段均未运行，原 Lifecycle 阻断尚未真实复验。

已保存新只读前后快照至 `.local/acceptance-20261010/`，未覆盖 10-08 基线。
现有备份入口成功，备份 `snowball-20261010-013542.dump`，3303998 bytes，
SHA-256 `e9e517f05af515c01542814e34acf424b1ebf9b188c6b00bb87789322200db59`。
主要业务数量前后一致：1999 RawEvent、2282 Analysis、297 Opinion、299 ThesisChange、
497 Signal、104 Event、76 Priority、76 Feed、67 OperationalRefreshRun。
历史 RUNNING 行始于 09-22，当前无刷新进程/advisory lock，未清理该行。
最近失败 b3510349-e43e-4f24-a9b9-d9412d331dcd 仍为 FEED_LIFECYCLE，
最新记录 386696f6-9c93-4aa7-9549-b6cd68c4fa0c 为 SKIPPED_ALREADY_RUNNING；
当前状态不能重建失败时证据。

仅临时启动当前代码后端与前端进行存量只读检查：health 200/1.146 秒，
近期 ACTIVE Feed 200/89.603 秒、total=6，中性原因与事实时间可读取；
现有紫金矿业 Asset Product 200/13.524 秒，Context 200/21.703 秒，
一个已有 Investor Product 200/1.554 秒。不是本轮受影响产品验收。
Context 当前有效窗口 40 Signal、8 Investor、5 ThesisChange，历史完整性 UNKNOWN。
前端概览可呈现存量证据，最后观察时近期情报区仍在加载；性能不标记通过。

验收前 backend/frontend/scheduler 实际均未运行，PID 文件已过期；状态脚本
可误匹配检查命令为 scheduler。仅停止本次创建并再次确认归属的服务进程树，
恢复原未运行安排；数据库、CDP、用户浏览器保留，未启动 scheduler，未产生后续调度轮。
剩余：取得外部原文传输明确授权后执行唯一有界真实轮，核对阶段和产品字段；
慢 Feed、历史运行状态残留、持续调度、跨投资者回流及历史污染仍未闭环。
未修改功能、语义、迁移或 policy，不宣称持续运行/整个可信变化阶段完成。

### 授权后唯一一轮真实 canonical refresh 验收 — 2026-10-10

**VERIFIED（仅本轮有界 canonical 刷新能力）：SUCCESS。**
用户补充明确授权必要雪球原文/分析字段传输至当前 DeepSeek 后，仅执行一次
`.venv/Scripts/python.exe -m operations.refresh --cdp-endpoint http://127.0.0.1:9222 --max-batches 1`。
本节补充前述被审批阻断的准备记录，不删除原记录。
香港时间 01:46:22–01:51:10，run_id `e2c94621-4977-406f-8002-4e1bff5f8064`。
HEAD `e7c0d6fdcc4158037201b4549718305956c22beb`，工作区差异仅此前路线记录，
SHA-256 `6d69f559b52b0fa26614455f234dd82ecd140eb29f64583521fbb4244fa80928`。
provider/model 和已批准 Opinion/Thesis policy 与运行前快照一致；没有迁移或切换 policy。
沿用本地 01:35:42 成功备份；新的前后快照、原始阶段摘要、HTTP 字段和报告保存于
`.local/acceptance-20261010-authorized/`，10-08 基线不变。

所有真实阶段 SUCCESS，耗时秒数：Collection 42.21、Analysis 59.80、Resolution 0.38、
Domain 2.03、Cross Investor 0.53、Signals 41.02、Events 66.28、Priority 18.84、
Feed 17.60、Lifecycle 19.86、Product Verification 19.91。总约 288.6 秒。
Following Feed 15 条/新增 9，默认预算 Profile 90 条/新增 39，重叠 3，
总观测 102 个已有或新 RawEvent，新增 48。8 个 Profile 的现有汇总均为成功，
其中两个 FIRST_PAGE_UNAVAILABLE，不代表覆盖完整。
Analysis 新增 48：37 NO_OPINION、11 PARTIALLY_RESOLVED、无 FAILED；
实际 Opinion LLM 请求 49（含一次重试）、Thesis 请求 0；费用金额未由 provider 回执证明。
解析 9 个支持标的引用（复用），38 个未解析引用保留。无新 Opinion/Attention/Thesis。
新增 Snapshot/Alignment/Consensus 为 7/6/6；Signal、Event、关联、Priority、Feed 均零新增。
有界刷新仍使用既有全局事实窗口选择，没有扩大名单或另跑历史补偿。

7 个来源依赖标的进入协调范围：18 个 Event 候选，20 个 ACTIVE Event 投影范围，
16 个 Priority/Feed 先刷新再进入同范围 Lifecycle；6 次状态转换，1 个 Thesis 基线更新，
7 Asset 和 15 Investor 通过真实产品验收，零 product failures。
60 个范围外 Feed 明确 deferred；不得称这些历史投影一致。
原错误 Priority `62c6ba81-1da2-4efa-b2e6-3f51c7544f86` 不在本轮范围，
仍为 THESIS_ACCELERATION/count=2，本轮未纠正或重新验收它。

真实 HTTP：health 200/2.50 秒，近期 ACTIVE Feed 200/55.42 秒、total=9；
受影响紫金矿业 Asset Product 200/16.00 秒、Context 200/15.84 秒，
受影响 Investor Product 200/3.93 秒。四并发只读测试；Feed 不能称性能达标，
之前本日同代码存量检查为 89.60 秒，不据此推断稳定性能改善。
Context 与产品内 Context 除请求时钟窗口边界外一致：当前 40 Signal/8 Investor/5 ThesisChange；
Feed 展示 THESIS_CHANGE_OBSERVED/CROSS_INVESTOR_DIRECTION_EVIDENCE、实际投票人数及
来源事实时间（例如紫金矿业仍为 10-09 21:28:04 香港时间，非本輪计算时刻）。
前端概览呈现运行正常及已观察数据；近期情报区长时间加载后最终呈现 9 条，与 HTTP 一致。
方向条目明确为当前状态、未进行前后比较，事实时间与投票者可见；本轮页面读取通过，性能未达标。

**独立读取反例保留**：真实 `/api/intelligence/discovery?asset_id=6f578ae9-1320-414e-bf30-87f7975a723e`
为 422/2.98 秒。服务实际错误
`Priority evidence count does not match Event evidence: efde357d-e18d-4797-99bc-c5c7a216718d`，
该 Priority 为 INVESTOR_VIEW_CHANGE/count=4，历史关联=9；独立入口会全局校验后才筛选标的。
Asset Product 内修复后的 Discovery 通过不能代替此入口通过。只报告，不修改代码。

服务原先实际未运行（PID 文件过期，状态脚本曾误匹配检查命令），无 scheduler 并发。
临时后端/前端只用于此轮验收，结束恢复原未运行安排，数据库/CDP/认证 profile 保留；
scheduler 不启动，不产生第二轮刷新。历史 09-22 RUNNING 行不清理；本轮锁正常释放。
最新真实结果为 MANUAL SUCCESS，状态接口当时 HEALTHY/FRESH 并保留历史失败信息，
这不证明 scheduler 存活、持续运行、重启恢复或所有历史污染已解决。
剩余：独立 Discovery/其他读取入口、Feed/前端响应速度、原失败延期投影、
跨投资者回流、持续调度与用户验收。历史完整性 UNKNOWN；整个可信变化阶段未完成。
到此停止，不再刷新或扩展修复。

### 独立 Discovery 有效关联读取子任务 — 2026-10-10

**局部代码修复完成；隔离验收通过；真实独立入口仍被未刷新历史投影阻断。**
保留本日 MANUAL SUCCESS 真实运行记录与此前路线修改。HEAD 仍为
`e7c0d6fdcc4158037201b4549718305956c22beb`，本次未提交。
09:51:30 香港时间，只读 repeatable-read 核查完整 Priority
`efde357d-e18d-4797-99bc-c5c7a216718d`，Event
`3c0b8823-a5c6-4844-8efd-2c48a819217e`、Asset
`3bd2441a-cdd9-4388-8210-bfd16a707176`，存储数量 4、历史关联 9、当前有效 4。
这只是当前来源状态，不声称重建此前失败时完整事实。
另行确认原 Priority `62c6ba81-1da2-4efa-b2e6-3f51c7544f86`
仍为 THESIS_ACCELERATION/count=2、有效 1，本次不维护。

根因：独立 Discovery UoW 直接使用全部历史 links；生产 Context 前置路径和
Asset Product 先经过有效 Asset read scope。现在独立生产服务与 HTTP 依赖启用
同一 `prepare_context_evidence` 和 `validate_context_projection`：一次批量准备
三类实际关联有效证据，跨投资者在 Event 关联范围选代表、读取真实投票者和事实时间，
不借用未关联来源。保留普通历史仓储和其他类型的既有消费规则。
有效数量、分类、标题、公开 context 或事实时间未刷新时仍报错；全部来源失效排除；
缺失 Priority/Event 不伪装为空结果。原数量检查保留，现比较有效 links。
列表、scope Discovery 同步真实投票人数；窗口、候选规则、标的筛选顺序、limit/total/
has_more 与 fact-time 排序含义不变，没有新增 score/rank/持久化候选或响应字段。

首批真实数据库/HTTP 回归修复前 **4 failed**，修复后通过；最终新增
`test_effective_discovery.py` **30 passed**，包括有效 4/历史 9、三类混合输入、
等价本地代表、未关联证据、迟到前驱、全部失效、15 种真实投影漂移、必要实体缺失、
真实 HTTP dependency、过滤/分页/排序和业务表内容不变。
既有 Attention-only 来源/事实时间测试补充独立 Discovery 对照；独立服务、Context
及 Asset Product scope 对同一有效输入一致。此前 Thesis、跨来源、canonical
SUCCESS/失败保真等回归共 **614 个不同后端用例通过**（583 项相关集合，
另 29 项消费者用例，以及之后新增的 2 项缺失实体测试；重复执行不重复计数）。
实际命令为 pytest 新集成文件、相关 integration 文件集合与 Signal/Event/Priority/
Feed/Lifecycle/read API/architecture 测试，以及 Operational/Discovery/Context/Asset Product
消费者；均 `-q -p no:cacheprovider --tb=short`。
Ruff check/format 与 git diff --check 通过，只有已有 Starlette/httpx 弃用警告。

前端实际标的发现页消费 Asset List API，不伪称本次校正它；已有 Discovery reason
的展示（presentation/AssetProductViewPage）将两种跨投资者技术 key 统一为
“多人观点方向证据”，类型与契约不变。新增标签测试先 **1 failed** 后通过；
全部前端 **47 passed**，`npm test`、`npm run lint`、`npm run build` 通过。

只读批量规模：2 种 Signal、1/6 个 distinct 完整 scope 为 **24/69 SELECT**，
每增加 scope 增加 9 次来源准备；不逐重复 Signal、Feed 或 Event 重建同一 scope，
同一调用不保留跨请求缓存。隔离读取前后完整业务表内容相同。
真实数据库 09:57:53/10:01:49 的 **29 张表内容指纹全部一致**。
未刷新、采集、补偿、LLM、迁移或业务写入，未改真实 Priority/Feed/来源/关联。

真实只读 HTTP：临时后端健康/数据库 200、0.77 秒。
`/api/intelligence/discovery?asset_id=3bd2441a-cdd9-4388-8210-bfd16a707176&limit=1`
仍 **422、32.945 秒**。同 HTTP 生产只读依赖记录完整实际错误：
`Context effective evidence count mismatch: 62c6ba81-1da2-4efa-b2e6-3f51c7544f86`
（10:00:47，额外错误定位只读调用 29.592 秒）。原 efde357d 旧关联误报已解除，
现在触及真实未刷新历史行；入口仍在筛选标的前校验全体 ACTIVE 投影，未改变该边界。
因此真实入口不能标记可用，不能以隔离通过或旧 canonical SUCCESS 替代本次结果。

后端原未运行，仅启动本次所属进程树，验证后恢复未运行状态；scheduler、frontend
不启动，数据库/CDP 与用户进程不操作。没有新增刷新 run，未清理历史 RUNNING 行。
剩余：真实未刷新投影及限定维护策略、列表全体校验的作用范围、响应速度、其他产品
读取入口、跨投资者回流与持续运行。本次只测性能，不优化；历史完整性 UNKNOWN，
历史污染/整个可信变化阶段未完成，到此停止。

### 限定历史 Priority／Feed 协调 — 2026-10-10

**最小协调入口及指定对象真实维护完成；独立 Discovery 仍被其余未刷新投影阻断。**
只读盘点时间香港 10:10:12，范围为独立 Discovery 在过滤、分页前消费的全部
70 条 ACTIVE Feed：39 条可由现有 Priority／Feed 规则纠正，5 条全部证据失效
按有效读取排除，15 条目标类型投影一致，11 条其他类型按原规则没有数量误差。
完整 Priority／Event／Feed／标的身份、旧值、期望值及实际来源依据保存在新的
本地盘点中；没有遇到第一条错误即停止，没有把盘点集合转换为写入集合。
实体／直接来源存在性补充核查未发现缺失；这是当前数据库状态，非旧失败时快照。

新增 `operations.projection_reconcile`，必须显式选择 priority-id 或 asset-id，
默认 dry-run 保存差异计划，单独 `--apply` 重新准备并比较完整前置条件。
复用 Priority／Feed 的现有候选构造和限定 repository 刷新；先在内存使用计划
Priority 给出 Feed 期望值，再在同一事务按 Priority → Feed 写入。仅允许现有
三类 Event 的现有派生行，缺失实体／Feed 身份异常拒绝自动创建或纠正，
没有有效输入／非 ACTIVE Event 跳过，不写零证据投影。
保留 ID、created_at、Feed.state 和内部 Thesis 生命周期基线，不运行 Lifecycle。

计划采用保守的全部上游表内容指纹与生产 policy 身份保护，除选中派生行外
不扩大写入范围；无关上游变化也可能要求重新准备。来源读取按同次 Event
集合缓存，实测 Thesis 单 scope **44 SELECT**；跨投资者同一来源 scope 下
1／2 个目标 Event 均 **77 SELECT**，不会按每个 Feed 重建来源链。
指纹另需按上游表批量读取，时间／内存随当前上游行数增长，尚未性能优化。
apply 使用既有 canonical 协作锁和选中行锁；已有 session advisory lock 的
跨 commit／连接池边界仍未作为本次并发保证验收，不能宣称所有独立写入互斥。

初始隔离测试 **12 failed**，其中九个历史混合场景复现现有 Feed dry-run 无法
消费旧 Priority 分类。最终新增 **21 passed**；相关回归两组 **204／188 passed**，
另加共享 scope 测试，扣除重复用例共 **373** 个通过。覆盖旧 2→有效 1、三类
规则、真实 Discovery HTTP、零网络调用、过期来源／输入／目标计划拒绝、
中途 Feed 失败整事务回滚、限定范围、重复新计划 apply 稳定、STALE／RESOLVED
和内部基线保护、缺失实体拒绝、全失效跳过；Ruff、format、diff 检查通过。
事务故障注入使用隔离 SQLite，未在真实 PostgreSQL 注入故障。

真实维护前香港 10:16:46 保存新的 29 表快照和差异计划，HEAD
`e7c0d6fdcc4158037201b4549718305956c22beb`，另保存工作区 diff 与新增代码内容
指纹。已有备份脚本成功生成 `snowball-20261010-101656.dump`，3,436,094 bytes，
SHA-256 `79658bda62fe87e0d48118e81416326fc72cd4cec2d2e58e89ea71436d9c1faa`。
真实 apply **仅** Priority `62c6ba81-1da2-4efa-b2e6-3f51c7544f86` 和 Feed
`0323fe80-628d-4bb1-8374-e5f42df85598`：数量 2→1、旧加速原因→中性观察，
Feed 标题／原因／公开计数同步。等级 MEDIUM、事实时间
`2026-08-27T07:50:49Z`、身份／created_at／ACTIVE 保持不变。
旧字段已在这两行被替换，原值记录在差异计划中，不声称行内保留旧原因。
29 表对照只发现上述两行的允许字段变化；源表、Event、Signal、关联和范围外
派生记录不变。相同范围再次 dry-run 无纠正；HTTP／最终 dry-run 前后全表一致。

真实 Discovery `/api/intelligence/discovery?limit=1` 香港 10:21:06 返回
**422，85.106 秒**；同一真实依赖核对为
`Context effective evidence count mismatch: 690f2af8-57fa-4daa-8ccf-c4c8a43aca77`
（77.539 秒），该对象已在盘点中：SH:600219，存储 2／有效 1。
没有继续 apply 其余 38 个可纠正对象；5 个全失效对象保留原行并由读取排除。
临时后端验证后已退出，恢复原未运行状态；scheduler 始终未启动，无 refresh、
采集、LLM、迁移、policy 切换或清理。本次维护没有新增 canonical run_id，
不能代替 canonical SUCCESS。Discovery 整体可用性、性能、其他历史投影、
跨投资者回流和持续运行仍未完成；基线与历史 Sprint 原文保持不变。到此停止。

### 显式 38 条历史 Priority／Feed 批量协调 — 2026-10-10

**本白名单子任务完成；本次真实 Discovery 解除投影阻断，性能未通过。**

依据香港时间 2026-10-10 10:10:12.344032+08:00 的 39 条可纠正名单，剔除
`62c6ba81-1da2-4efa-b2e6-3f51c7544f86`，核对剩余 38 个唯一完整 ID。
名单与来源 SHA 保存在 `.local/reconcile-batch-20261010/whitelist.json`、
`whitelist-origin.json`。五条全失效对象不在写入范围。
当前计划：38 READY，0 已一致／全失效／异常；38 Event、38 Feed、28 标的，
Thesis 23、跨投资者发现 14、兼容共识类型 1。

维护入口新增 `--priority-ids-file`，默认 dry-run，显式 `--apply --plan`。
同批复用有效证据准备和来源指纹；代码、policy、来源或目标变化拒绝过期计划。
单批一个事务按 Priority → Feed 执行；不创建缺失实体、不修改语义或 Lifecycle。
新增测试修复前 6 项失败，修复后新增 9 项、单对象兼容合计 30 项通过，相关
九文件回归 214 项通过；覆盖中途失败整批回滚、旧计划拒绝、跳过、范围外保护、
STALE/RESOLVED/内部基线保留、幂等和零网络调用。Ruff、格式和 diff 检查通过。
同批跨投资者分组准备一次、各上游表指纹批量读取一次；来源指纹保守覆盖现有
上游表，仍随上游行数增长，不宣称性能完成。

apply HEAD `e7c0d6fdcc4158037201b4549718305956c22beb`，工作区差异 SHA256
`81fb5fb41d840a5c4bfed2bfb6d0ad6888eb3b97ed4d4df44db7c9500e5fbbad`。
完整未追踪代码身份、最终计划、精确差异和快照保存在上述本地目录。
前快照 10:42:34.593620+08:00，后快照 10:45:25.015226+08:00。
新备份 `snowball-20261010-104244.dump` 成功，3,436,100 bytes，SHA256
`b6b83a2c9b98443eb856bf82fbc2be6b0ae6496388f577aeaf35ef3b68dd1ac7`。
无项目 refresh/scheduler 进程、无 advisory lock；一条 2026-09-22 历史 RUNNING
CollectionRun 保留，不解释为当前运行进程。
一次真实 apply 仅改 38 Priority 和 38 Feed：原因各 38、数量 35、标题 38、公开
context 37、事实时间 17 条；等级、身份、created_at、state、内部区域均保留。
源记录、Event、Signal、历史关联和白名单外行未变；再次 dry-run 38 CONSISTENT，
无待纠正字段；LLM 0。成功批次在 PostgreSQL 提交；故障回滚注入仅隔离库验证。

临时后端 HTTP：health 200/0.130s；Discovery 200/43.459s、40 候选；近期 ACTIVE
Feed 200/47.751s、6 条；SH:600219 Product 200/0.106s、Context 200/0.081s；
HK:00916 Product 200/3.438s、Context 200/3.546s。代表 Thesis 有效 Signal 1、
事实时间 2026-08-28；跨投资者标的有效总消费 10，当前／前窗口 7／3、投资者 3。
独立与嵌套 Context 的数量、投资者和事实时间一致；近期 Feed 人数匹配、不泄漏
内部区域。HTTP 前后 29 业务表完全不变。临时后端已关闭，恢复原未运行状态，
scheduler 未启动。

剩余：43–48 秒耗时不满足日常交互；Product traceability Signal 数量 3／22 与
有效消费 1／10 不同，另一读取边界尚待核查，本次不扩大修复。五条全失效旧行、
历史 Event 时间/metadata/关联保留；跨投资者回流、持续运行和独立并发锁仍未完成。
Historical completeness UNKNOWN。本次不运行 canonical refresh，不证明全体历史
投影永久一致，不标记整个可信变化阶段完成。

### 近期 Feed 保持结果不变的读取优化 — 2026-10-10

**限定读取优化及真实只读复验完成；约 2 秒目标尚未达到。**

固定参数 `state=ACTIVE, since=2026-10-09T02:50:00+00:00, limit=100`。
29 张业务表的指纹与前次维护后完全相同，剖析／HTTP 后也不变。应用首次／后续
剖析分别 47.891／49.864 秒：1,745 SELECT、181,432 返回行，SQL 执行累计
10.754／11.260 秒（不含 fetch/JSON 解码）。跨投资者校验 47.328 秒，95 次
引用 scope 加载 44.455 秒；全库 RawEvent 被每个历史 cutoff 重复加载，JSON
解码约 24 秒是主要瓶颈。实际评估 70 ACTIVE Feed，跨投资者 24、21 个标的，
129 个完整输入 scope／95 个引用 scope；去重和响应 context 耗时小于 1 毫秒。

最小修改仅两处生产文件：`signal_engine/cross_investor_sources.py`、
`signal_engine/repository.py`。Feed 先限定实际关联 Signal 的真实来源依赖链；
所有引用 Snapshot 仍按自己的窗口、as_of、policy 重建完整有效输入。
RawEvent identity map 只加载有效 Attention 的来源（保留全部 first history）；
相同 selector 方法／资产／policy／cutoff 在单次调用内复用。无跨请求缓存、
新表或新算法；不按不可信存储时间、since 或 LIMIT 提前截断。
普通历史读取、资格、前驱、事实时间、关联范围等价去重和分页规则未改。

同数据同参数优化后剖析 2.861／2.827 秒、933 SELECT、8,168 行，SQL 执行
0.679／0.640 秒；97 个完整输入 scope／71 个引用 scope。prepare_inputs 1.547 秒，
引用加载 0.719 秒，引用检查 0.046 秒，等价去重约 0.0005 秒。
最终相关十文件回归 283 项通过；canonical 范围、Thesis 物化／Lifecycle 和批量协调
另 59 项通过。Ruff、格式、diff 检查通过。
优化前后完整响应 JSON 完全一致（6 条、相同身份／证据人数／事实时间／排序／
公开 context／分页）。隔离 1／12／100 个历史窗口，全来源校验 0.028／0.160／
1.385 秒；固定关联读取 0.025／0.015／0.022 秒，均 14 SELECT、结果一致。
既有规模回归增加 20 个无效历史 Signal、5 个同 cutoff 窗口和 5 个无关标的，
同 scope 不再重复查询，但不同 cutoff 仍独立验证。请求后来源 FAILED 下一次读取
立即排除；无永久缓存。旧测试的重复查询次数改为更低的严格数量断言，保留所有
有效性、投影错误、时间、过滤分页及零写入断言。

真实临时后端首次／后续三次 HTTP 200，3.950／4.067／4.333 秒（当时并行回归
测试占用资源）；测试停止后再限定两次顺序请求 200，3.041／3.922 秒。全部响应
与固定旧基线完全一致。Discovery 仅观察一次：200、40 候选、4.372 秒，同样处于
并行测试负载，不宣称其专项性能通过。临时后端已关闭、无项目业务进程，scheduler
未启动；LLM 0，无采集／刷新／维护／迁移。所有 29 业务表在验证前后不变。

剩余瓶颈为 distinct cutoff 的有效 selector SQL 和输入准备（仍 933 查询），
本次不继续扩大为跨窗口基础加载重构。2 秒目标未达，不能标记日常性能合格。
Product traceability 数量差异保留为不同读取口径待核查，不直接判作错误或修复。
历史污染、跨投资者回流、持续运行、Historical completeness UNKNOWN 均保持原边界。

### Feed 不同 cutoff 的单次有限准备优化 — 2026-10-10

**本次有限读取方案完成；2 秒目标未达，HTTP 延迟稳定改善未被本次样本证明。**

分组剖析覆盖 selector／资产／policy／cutoff／窗口（完整数据保存于
`.local/feed-cutoff-20261010/group-before.json`）。933 SQL、8,168 行中，
PortfolioAction 共 388 查询、0 行：97 个资产/cutoff 组每组两次调用，直接输入准备
与 Consistency 各一次。各组政策与 cutoff 明确区分；其余 Opinion／Attention／
Thesis 为 97／97／194 查询，没有把不同 cutoff 误判为相同缓存键。
涉及 21 个跨投资者标的、97 完整输入 scope、71 引用 scope，13 个不同截止时间。
当次不带 cProfile 的分组计时 2.198 秒，prepare_inputs 累计 1.015 秒；这与
上一步带 cProfile 的约 2.8 秒和 HTTP 3.0–3.9 秒分别记录，不混为同一指标。

唯一方案是限定 Feed 关联 Snapshot 的 PortfolioAction 多 cutoff 基础读取。
`PortfolioActionRepository.prepare_cutoffs` 批量读取所需资产的 Action 和对应组合
快照；最大 cutoff 仅限制基础加载范围。每个 cutoff 仍独立过滤快照并重建相邻
关系，绝不把最大截止的有效 Action 直接过滤成旧窗口。普通 by-asset 入口和
批量路径共享 `_select_asset_actions` 纯选择函数，排序与身份不变。
`InvestorActionConsistencyRepository` 可接收此只读 Action reader，配对、policy、
latest-opinion 算法原样复用。共享来源链仅在 Feed `source_keys` 限定路径启用；
新候选/普通历史路径保留原读取。无跨请求缓存、新表、索引或语义扩展。
Opinion、Attention、Thesis selector、前驱、窗口 fingerprint、first history 和
as_of 校验不变；不提前按旧时间或 LIMIT 截断，不新增 Portfolio intelligence。

新测试先因缺少入口失败 2 项，修复后 cutoff／规模 5 项通过，Consistency 与
初始新测试合计 14 项通过；迟到中间快照使旧相邻配对失效，下一请求重新准备
立即体现。非空数据 1资产/1截止、1资产/20截止、5资产/20截止均 2 SQL，
分别加载 3／3／15 基础行，准备 0.005／0.007／0.021 秒；逐截止原 selector
比较约 0.003／0.039／0.204 秒，全部相同。20资产各100截止的空数据仅1 SQL。
前次 1／12／100 历史窗口规模测试和来源失效／前驱／policy／同数身份替换／
未来隔离／关联等价／分页／真实投影报错回归保留。相关十文件 279 项直接通过，
4 项旧 SQL 数量断言更新到更低严格数量后单独通过；Portfolio/Snapshot/canonical/
批量协调另 41 项通过。有效性及零写入断言未削弱。Ruff/格式/diff 检查通过。

固定 `state=ACTIVE,since=2026-10-09T02:50:00+00:00,limit=100`，完整响应一直
与旧基线相同（6 条）。SQL 降至 546，行数仍 8,168，完整输入 scope 仍为 97；
后续带 cProfile 服务样本为 4.179／4.078 秒，不能据 SQL 减少声称耗时改善。
当次分组计时 2.808 秒、输入准备 1.238 秒，同样不作为稳定性能结论。
测试停止后真实 HTTP 首次 200/5.266 秒，后三次 200/3.036、3.303、3.173 秒。
每次完整 JSON 比较通过，没有继续循环压测或另行重构。

本次加载代码 HEAD `e7c0d6fdcc4158037201b4549718305956c22beb`，工作区差异 SHA
`96825640a288cafdfbdebd766116cdae2ca99db2634e19fd029a42027a328803`；完整身份与
未追踪代码指纹在前后快照/result.json。香港时间前快照 12:11:04.689359+08:00，
后快照 12:12:47.770354+08:00；29 业务表与前次数据截面完全相同且零写入。
无 LLM、采集、refresh、维护、迁移。临时后端归属核验后关闭，恢复未运行状态，
scheduler 未启动。历史 RUNNING CollectionRun 保留，未解释为当前进程。

剩余成本包括不同截止的 Opinion/Attention/Thesis 有效读取、引用加载和
fingerprint/输入准备。进一步批量化须单独证明前驱/有效配对/时间边界；本次到此
停止。Discovery 未专项优化，traceability 差异不直接判为错误；不宣称长期性能、
高并发、持续运行或整个可信变化阶段完成，Historical completeness 仍 UNKNOWN。

### Asset Product traceability 历史／有效口径 — 2026-10-10

**本子任务完成；仅核验并呈现证据口径，不完成整个可信变化阶段。性能重构暂停，约 3 秒后续 Feed 与首次波动仍未达到 2 秒目标。**

根因：旧 `signal_count` 是标的全部已存 Signal（含未关联、失效与历史），
`evidence_refs` 是 Review/Evolution 的组合审计引用，既不是全部历史关联，也不是
当前有效集合。`canonical_source_count` 仅排除中间产物，仍含解释 artifact，
不能表述成 RawEvent 或当前有效事实数量。差异本身合法；前端“变化信号”标签错误。
旧字段数值、含义和审计 ID 保留，前端改为“标的全部已存 Signal”“产品审计引用
（含历史）”“非中间产物审计引用”，明确不代表有效证据或变化次数。

兼容添加 `historical_signal_ids`、`historical_associations`（实际旧 Event 关联），
以及可空 `validated_consumption`。后者限定 ACTIVE Feed 实际关联的 Thesis 与
方向证据，不等于近期窗口，不认证其他 Event 类型，不拼接窗口重新推导共识。
未准备来源链时返回 null，区别于已校验后零证据。保留旧响应可反序列化及旧前端
类型兼容。没有替换普通历史读取、创建表或改写历史状态。

Product 专用 scope 开启 provenance；Context/Discovery 不额外加载。
`ProductEvidenceSourceReader` 对已有共享有效关联分组批量追溯 Signal →
ThesisChange/Alignment/Consensus → Snapshot/Opinion → RawEvent，核对标的、
投资者、Analysis/Event 指针和窗口。Opinion 标明当前/前驱/方向投票角色，
Attention 单独追溯并区分 attention-only 投资者。来源时间来自 RawEvent；
链路 observed_at 复用已校正有效输入。每条保留原窗口/as_of，不生成新语义。
没有复制 policy、前驱、输入 fingerprint 或关联范围等价算法，也不借用未关联来源。
新增最多三次批量 SELECT（Thesis、Opinion、Attention），随所需来源行数增长，
不逐 Signal 查询；跨投资者 fixture 中 Product 25 SELECT、独立 Context 23，
添加五个等价窗口后数量仍相同。原 scope 的窗口有效性校验继续保留。

新增真实数据库测试最初三项因缺少区分字段失败，最终 traceability 14 项通过，
覆盖非 material、inactive、失效前驱、FAILED 上游、全部失效、混合历史关联、
等价窗口、全局代表未关联、真实投票者与仅关注者、HTTP 和零写入。
与 Thesis 回流合计 40 项通过；Product/Context/两类 Feed/Discovery/canonical
分组 155 项通过；另九文件 250 项先通过，一项沿用上一轮优化前 SQL 数量失败，
严格预期由 19/21 更新为实际 15/17 后，等价回归整个 18 项通过。
Product 新增两次批量 provenance 的 SQL 断言单独明确，未削弱有效性和零写入。
前端 49 项、TypeScript/Vite 构建、Ruff/格式/diff 检查通过。

香港时间 12:39:22 前快照、12:43:44 后快照：29 张业务表行数与内容指纹完全
一致，零 LLM/采集/refresh/维护/迁移。真实只读 HTTP 核验记录于
`.local/traceability-20261010/http-results.json`；当时 HEAD 为
`e7c0d6fdcc4158037201b4549718305956c22beb`，工作区差异 SHA 为
`bfbb81ef6e6571e164bcfa2acbda34daa585c4d01239b03c69c3e3814831ea97`，
完整未追踪代码指纹一并记录。未覆盖基线。

SH:600219：已存 3、历史关联 2、已校验关联 1，旧审计引用 10/非中间 5；
HK:00916：已存/历史关联 22、已校验 7（Thesis 4、Alignment 2、Consensus 1），
旧审计引用 71/非中间 48；Product Discovery 消费 10，其中另三条沿用其他类型
路径，不能强行改成 7。已校验 Opinion 链分别解析到 2/7 个不同 RawEvent，
跨投资者实际方向投票者三人。旧 trace 字段完整比较一致；Context 对应内容与
Product 一致。HTTP 各请求按自己时钟锚定窗口，窗口边界分别记录，不声称完全
相同 as_of。Product 200/0.104、0.400 秒；Context 200/0.095、0.376 秒。
这是两个标的的样本，不证明全局 Feed 性能达标。

临时后端归属核验后关闭，恢复项目后端/scheduler 未运行安排；历史 RUNNING
记录未改写，未当作当前进程。遗留：历史污染仍保留；其他读取入口的历史/current
state 展示尚未全部校正；跨投资者回流未实现；完整原文阅读、前后观点对比、
统一证据导航及 Research Candidates 工作流仍缺失。Historical completeness
保持 UNKNOWN。本次停止，不扩展证据页面或继续性能优化。

### 2026-10-10：当前入口证据阅读（限定能力已实现，远端阅读验收受限）

用户路径：Inbox「查看证据」→指定 Feed 的实际有效关联；Asset Product
「查看当前有效情报证据」及逐来源入口→观点/前后比较→已保存原文/原帖。
Investor Product 提供覆盖标的的证据导航。新增只读 evidence API 和当前实际
`/assets/:id/evidence` 路由，不改 Intelligence 判定，不创建持久化 Evidence View。

复用共享有效来源链、关联范围去重、投票身份与有效前驱；内容和选择共用一次
repeatable-read、read-only 事务。Opinion/Attention 正文分别批量解析；来源失效
返回 409，不替换为未关联证据。历史引用与有效观点历史单独标识。页面区分
原文事实、AI 提取、已有系统分类；未知字段不推断删除；首次观察不宣称此前
无观点。跨投资者保留各窗口与真实投票者，Attention-only 单列，不拼接新共识。
完整展示已保存文本，不承诺远端全文完整；HTML 不注入执行，转发保持归属边界，
仅保存的安全 http/https URL 可打开。返回页面及重新校验时重新读取来源。

真实浏览器：南山铝业（4b44a018-7114-4913-b18f-422663486f19）Product→证据，
验证 2026-08-24/08-28 的有效前后观点与原文；来源比较
4793f846-2b35-444f-83b4-7a40ff237e86，RawEvent
5cb325ea-74aa-452e-9403-88fd14d5b93b/1f168f58-9205-4644-911b-6f939f56adfd。
龙源电力（afacf10c-d6e5-4f20-80a7-028a55706ba6）Product→证据，看到逐人
方向观点、各自窗口和原帖；实际点击爱投资的小人书原帖 7103876041/408505060。
Inbox 中际旭创 Feed 57a051a4-a5af-4599-a5be-573bbdb282c5→证据，显示
Captain-Nemo船长和戴维斯双击，返回概览成功。雪球原帖新标签获得正确 URL
及对应帖子标题，但远端正文读取工具超时；不得将此记为远端全文阅读通过。
本地原文和观点阅读通过；真实 Attention-only 跨投资者样本未单独验收，隔离测试覆盖。

真实 HTTP Thesis/cross/指定 Inbox evidence 均 200，分别 0.180/0.419/0.128 秒，
返回 1/10/1 组；Feed 固定参数 200/3.349 秒。Feed 约 2 秒目标仍未达到，
本次没有继续性能重构。代码 HEAD e7c0d6fdcc4158037201b4549718305956c22beb，
工作区差异及新增文件各自哈希记录于新的本地验收快照，不能只用 HEAD 表示代码。

数据库指纹对照时间：香港 14:03:12→14:49:18，29 表中 27 表不变，包含来源、
Event、Signal、关联、Priority、Feed；collection_runs 与 operational_refresh_runs
变化。观察到独立 SCHEDULED run 1ac1e43b-f4f0-46e9-8f65-8d05ac1b77b5
于 14:11:44 启动、14:11:46 FAILED。验收未调用采集/refresh/LLM；不能把整段
环境写入归为零。原临时后端/前端 PID 已退出，另组服务与 scheduler 已运行，
归属不同，未停止或改动外部进程；不得宣称服务恢复为原未运行状态。

最终隔离回归：`python -m pytest tests/integration/test_evidence_reading.py
tests/integration/test_product_traceability_boundaries.py tests/test_asset_intelligence_product_view.py
tests/integration/test_effective_asset_context.py tests/integration/test_thesis_stale_reentry.py -q`
94 passed，其中新增证据阅读 15 项。`npm test -- --run` 54 passed（证据页面 4 项）；
`npm run build`、相关 Ruff lint/format、git diff --check 通过。真实只读批量核验
11 个不同 Opinion、24 个引用的标的/投资者/RawEvent/已保存正文/事实时间一致。
隔离查询前后数据库不变；真实环境的运行表变化限制如上，不能全局声称零写入。

限定验收不代表历史污染清除、全部证据完整、跨投资者回流或持续运行成立。
Historical completeness 仍 UNKNOWN，Research Candidate 工作流未实现。
本次结束，不自动推进其他能力。

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
