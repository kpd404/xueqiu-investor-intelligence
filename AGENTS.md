# Xueqiu Investor Intelligence System

## AI Agent Engineering Guidelines

Version: 1.0

---

# 1. Project Mission

本项目是一个 AI 驱动的投资情报分析系统。

核心目标：通过持续追踪投资者行为，分析：

- 投资者关注变化
- 投资观点变化
- 投资逻辑变化
- 组合行为变化
- 多投资者共识形成

最终输出 Research Candidates，帮助用户发现“哪些投资标的值得进一步研究”。

---

# 2. Product Boundary

## 本项目不是

- 股票买卖推荐系统
- 自动交易系统
- 价格预测系统
- 高频交易系统

## 本项目是

Investment Intelligence System。

核心价值：

- Information Discovery
- Behavior Analysis
- Research Prioritization

所有功能设计必须围绕“发现变化”，而不是“预测价格”。

---

# 3. Core Design Philosophy

## Principle 1: Raw Data First

所有 AI 分析必须建立在原始数据之上。

禁止直接保存 AI 结论作为事实。

正确流程：

```text
Raw Event
    ↓
AI Analysis
    ↓
Derived Intelligence
```

## Principle 2: Evidence Based

任何 AI 生成观点必须能够追溯来源。

所有 Opinion、Signal、Summary 必须关联原始事件 ID。

禁止没有来源的 AI 推断。

## Principle 3: Change Matters

系统关注变化。

例如：

- 重要：Neutral → Bullish
- 不重要：一直 Bullish

所有核心算法优先关注：

- 新关注
- 观点变化
- 仓位变化
- 共识形成

## Principle 4: Separate Fact and Interpretation

系统必须区分以下三类信息：

### Fact

原始事实。

示例：“大 V 组合腾讯仓位从 10% 增加到 18%”。

### AI Interpretation

AI 分析。

示例：“该行为可能代表其长期信心增强”。

### AI Signal

系统计算。

示例：“腾讯 Signal Score 87”。

三者不可混淆。

---

# 4. System Architecture

系统采用分层架构：

```text
Data Source Layer
        ↓
Raw Event Layer
        ↓
Investment Understanding Layer
        ↓
Investor Asset State Layer
        ↓
Intelligence Aggregation Layer
        ↓
Signal Engine
        ↓
Product Layer
```

每层职责必须明确。禁止跨层耦合。

---

# 5. Layer Responsibilities

## Layer 1: Data Source

职责：提供原始数据。

必须使用 Adapter Pattern。

禁止业务逻辑依赖具体数据源。

正确：

```text
SourceAdapter
 ├── XueqiuAdapter
 └── ManualImportAdapter
```

错误：

```python
if xueqiu:
    do_everything()
```

## Layer 2: Raw Event

职责：保存世界发生了什么。

Raw Event 必须：

- 不修改
- 不覆盖
- 永久保存

任何分析结果必须生成新的数据。

## Layer 3: Investment Understanding

职责：文本理解。

输出结构化投资观点，包括：

- Asset
- Direction
- Conviction
- Thesis
- Catalyst
- Risk
- Time Horizon

AI 输出必须 JSON 化。禁止只保存自然语言总结。

## Layer 4: Investor Asset State

职责：维护 Investor × Asset 状态。

例如：

```text
Investor A
Tencent
Neutral
   ↓
Bullish
```

状态变化必须记录。

## Layer 5: Intelligence Aggregation

职责：从多个投资者状态中生成：

- Attention Momentum
- Consensus
- Divergence
- Position Confirmation
- Industry Trend

## Layer 6: Signal Engine

职责：生成研究信号。

输出不是 Buy/Sell，而是 Research Priority。

---

# 6. Core Data Entities

系统核心实体：

## Investor

代表投资者。

## Asset

代表投资标的。

## RawEvent

原始事件。

## Opinion

AI 结构化观点。

## InvestorAssetState

投资者—资产状态。

## Signal

研究信号。

新增实体必须说明为什么现有实体无法承载。禁止随意增加表。

---

# 7. AI Usage Rules

## AI 负责

- 文本理解
- 信息抽取
- 投资逻辑总结
- 报告生成

## AI 不负责

- 状态计算
- 分数计算
- 确定性逻辑

例如，观点变化不应由 LLM 决定，而应通过数据库状态比较确定。

---

# 8. Prompt Management

所有 Prompt 必须集中管理。

禁止在业务代码中硬编码 Prompt。

推荐结构：

```text
/prompts
├── investor_analysis.md
├── thesis_extraction.md
└── report_generation.md
```

---

# 9. Model Output Requirements

所有 LLM 输出必须结构化。

示例：

```json
{
  "asset": "Tencent",
  "direction": "BULLISH",
  "strength": 80
}
```

禁止直接解析自然语言。

---

# 10. Data Quality Rules

所有数据必须包含：

- source
- timestamp
- confidence

AI 结果必须包含 confidence。

低置信度数据不得进入高优先级 Signal。

---

# 11. Signal Engine Rules

Signal Score 必须可解释。禁止黑盒评分。

任何 Signal 必须输出：

- Why
- Evidence
- Risk

---

# 12. Development Rules

## Before Coding

Agent 必须先：

1. 理解已有架构
2. 检查已有代码
3. 说明影响范围

禁止直接重构。

## Small Changes First

优先小 PR、小模块。避免一次修改大量文件。

## Maintainability

代码优先考虑：

- 可读性
- 可测试性
- 可扩展性

而不是最短代码。

---

# 13. Testing Requirements

新增功能必须至少包含一种测试：

- Unit Test
- Integration Test

核心测试必须覆盖：

- Event Processing
- Opinion Extraction
- State Update
- Signal Calculation

---

# 14. Future Expansion Rules

未来扩展包括：

- 更多数据源
- ETF
- 基金
- 港股
- 美股
- 宏观主题

设计时不得绑定雪球。

---

# 15. MVP Priority

当前阶段优先级：

## P0

- 数据模型
- Raw Event
- Opinion Extraction
- State Update
- Signal

## P1

- Dashboard
- Report

## P2

- Advanced Agent
- Backtesting
- Learning System

---

# 16. Agent Behavior

作为项目 AI 工程助手，你应该：

- 主动发现架构问题
- 优先保持系统长期可维护
- 不为了快速 Demo 牺牲设计
- 不生成未经验证的复杂方案

当需求不明确时，优先提出设计问题，不要自行假设。

---

# Final Principle

这个项目的核心不是“抓取雪球内容”，而是建立一个 Investor Behavior Intelligence Graph，理解：

- 谁在关注什么
- 为什么关注
- 什么时候改变观点
- 是否真的行动
- 这些变化是否正在形成市场趋势

所有工程决策必须服务于这个目标。
