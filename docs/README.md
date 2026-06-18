# DBAgent 设计文档索引

本目录包含 DBAgent 项目的完整设计文档。

## 📚 文档列表

| 文档 | 说明 | 状态 |
|---|---|---|
| [01-requirements.md](./01-requirements.md) | 产品需求文档 | ✅ 完成 |
| [02-architecture.md](./02-architecture.md) | 架构设计文档 | ✅ 完成 |
| [03-testing.md](./03-testing.md) | 测试说明文档 | ✅ 完成 |
| [04-nl2sql-workflow.md](./04-nl2sql-workflow.md) | NL2SQL 工作流设计问答 | ✅ 完成 |
| [05-follow-up-memory.md](./05-follow-up-memory.md) | 追问能力与上下文记忆设计 | ✅ 初版完成 |

## 📋 文档概要

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

### 05-follow-up-memory.md - 追问能力与上下文记忆设计

包含内容：
- 当前追问能力的边界和问题
- `last_nl2sql_task` 结构化记忆设计
- 追问分类、patch 规则和 SQL 再生成策略
- 结果驱动追问、澄清策略和测试计划
- 分阶段实现方案和待确认问题

## 🚀 下一步

1. 确认 `05-follow-up-memory.md` 中的待确认问题
2. 实现 `last_nl2sql_task` 结构化记忆
3. 实现确定性追问 patch
4. 增加追问能力单元测试和真实 smoke test

## 📞 联系方式

如有问题或建议，请联系项目团队。
