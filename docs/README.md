# DBAgent 设计文档索引

本目录包含 DBAgent 项目的完整设计文档。

## 📚 文档列表

| 文档 | 说明 | 状态 |
|---|---|---|
| [01-requirements.md](./01-requirements.md) | 产品需求文档 | ✅ 完成 |
| [02-architecture.md](./02-architecture.md) | 架构设计文档 | ✅ 完成 |
| [03-testing.md](./03-testing.md) | 测试说明文档 | ✅ 完成 |

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

## 🚀 下一步

1. 确认设计文档是否符合预期
2. 开始实现代码（按照 Phase 1-5 的开发计划）
3. 创建项目基础结构
4. 实现核心模块

## 📞 联系方式

如有问题或建议，请联系项目团队。
