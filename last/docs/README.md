# DBAgent 设计文档索引

本目录包含 DBAgent 项目的完整设计文档。

## 文档列表

| 文档 | 说明 | 状态 |
|---|---|---|
| [01-requirements.md](./01-requirements.md) | 产品需求文档 | 已完成 |
| [02-architecture.md](./02-architecture.md) | 架构设计文档 | 已完成 |
| [03-testing.md](./03-testing.md) | 测试说明文档 | 已完成 |
| [04-nl2sql-workflow.md](./04-nl2sql-workflow.md) | 当前 NL2SQL 工作流设计 | 已部分实现 |
| [05-sql-agent-design.md](./05-sql-agent-design.md) | 面向 SQL 编写提效的新 Agent 设计 | 新增设计 |
| [06-mysql-sandbox-benchmark.md](./06-mysql-sandbox-benchmark.md) | MySQL sandbox benchmark 使用说明 | 已实现 |
| [07-follow-up-memory.md](./07-follow-up-memory.md) | 追问能力与上下文记忆设计 | V1 最小闭环已实现 |
| [08-intent-recognition-improvement.md](./08-intent-recognition-improvement.md) | NL2SQL 意图识别改进方案 | 规划中，未实现 |

## 文档概要

### 01-requirements.md - 产品需求文档

包含内容：
- 产品定位：数据分析 Agent
- 需求确认记录：技术选型、交互方式、部署方式等
- 优先级功能列表
- 用户场景示例

关键决策：
- **核心功能**：多步骤数据分析、自然语言转 SQL、数据库探索
- **技术栈**：Python (FastAPI + LangGraph)
- **LLM**：DeepSeek V4 Flash
- **记忆策略**：摘要记忆
- **输出方式**：流式输出（SSE + WebSocket）
- **工具确认**：读操作自动，写操作确认

### 02-architecture.md - 架构设计文档

包含内容：
- 整体架构图
- 核心模块设计（LangGraph Agent、工具、客户端等）
- 状态机设计（Understand → Plan → Act → Reflect → Summarize）
- 项目结构
- 依赖清单
- 开发计划（预计 4 天）

核心组件：
- **LangGraph Agent**：状态图驱动的多步骤工作流
- **Tools**：SQL Executor、DB Explorer、Data Analyzer
- **Memory**：摘要记忆，平衡上下文和 token
- **API**：SSE 流式输出 + WebSocket 双向通信

### 03-testing.md - 测试说明文档

包含内容：
- 测试环境和运行命令
- 当前单元测试覆盖范围
- 如何通过反向验证确认测试有效
- 当前测试边界和后续集成测试建议
- 本地服务 smoke test 命令

### 04-nl2sql-workflow.md - NL2SQL 工作流设计问答

包含内容：
- 为什么要从直接工具规划升级为 NL2SQL 专用流程
- 数据库、表、字段解析策略
- 生成 SQL 前必须获取真实表结构的约束
- SQL 校验、修复、澄清和输出策略
- 第一阶段实现范围和成功标准

### 05-sql-agent-design.md - SQL Agent 设计方案

包含内容：
- SQL 编写提效场景特点
- Agent 范式和推荐开源底座
- 目标架构、核心工作流和工具接口
- 通用规则、业务配置和 benchmark 特制规则的边界
- 基于当前 benchmark 结果的分阶段落地计划

### 06-mysql-sandbox-benchmark.md - MySQL Sandbox Benchmark

包含内容：
- MySQL sandbox schema、seed、case 文件说明
- `generate_predictions.py` 生成预测文件
- `run_mysql_sandbox_benchmark.py` 静态和执行评测
- 当前指标定义和扩展建议

### 07-follow-up-memory.md - 追问能力与上下文记忆设计

状态：V1 最小闭环已实现。

包含内容：
- 当前已实现的 `show_sql`、`change_limit`、`change_time_range` 追问闭环
- `last_nl2sql_task`、`last_validated_sql`、`last_result_summary` 等结构化记忆
- 追问分类、结构化 patch、SQL 再生成和 validator 约束
- API/UI 最新 SQL 展示与复制能力
- 后续 `add_filter`、`add_group_by`、`drill_down`、任务版本栈和长期记忆规划

### 08-intent-recognition-improvement.md - NL2SQL 意图识别改进方案

状态：规划中，未实现。

包含内容：
- 当前规则解析的边界和升级目标
- 规则解析、LLM 结构化解析、schema 校验的三层架构
- Intent Schema、query pattern 和字段置信度设计
- 模块拆分、合并策略和回归样本集方案
- 分阶段实现计划和待确认问题

## 下一步

1. 基于 `05-sql-agent-design.md` 增强 SQL generator prompt 和 MySQL 方言约束。
2. 增加字段样例值检索，优先解决枚举值幻觉。
3. 建立轻量业务语义层，配置有效订单、GMV、支付成功、退款成功等规则。
4. 增强 benchmark 失败归因，区分真实错误和 evaluator 过严。
5. 后续再实现 `07-follow-up-memory.md` 和 `08-intent-recognition-improvement.md`。

## 联系方式

如有问题或建议，请联系项目团队。
