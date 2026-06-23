# DBAgent 产品需求文档

## 1. 产品定位

**数据分析 Agent** —— 基于 LangGraph + FastAPI 的智能数据库分析助手，能够完成多步骤数据探索、自然语言转 SQL、查询结果可视化等任务，最终集成到 OneDBA 平台提供 Web 服务。

## 2. 需求确认记录

| 维度 | 选择 | 说明 |
|---|---|---|
| 核心功能 | 数据分析 Agent | 多步骤数据探索、自动发现数据库和表、生成分析洞察 |
| 交互方式 | 纯文本对话 + 结构化输出 + 多轮对话 + 工作流确认 | 支持 Markdown 表格、列表等富文本 |
| 技术栈 | Python (FastAPI + LangChain/LangGraph) | |
| LLM | DeepSeek V4 Flash | 通过 OpenAI 兼容接口调用 |
| 部署方式 | 先本地服务，最终集成到 OneDBA 平台 | |
| 与旧系统关系 | 完全替代 `@DBR/backend` | 废弃旧代码，重新开发 |

## 3. 技术选型确认

| 组件 | 选择 | 理由 |
|---|---|---|
| Agent 框架 | **LangGraph** | 支持复杂工作流、状态管理、人机交互，适合多步骤数据分析场景 |
| 记忆策略 | **摘要记忆** | 使用 LLM 对历史对话生成摘要，平衡上下文和 token 消耗 |
| 输出方式 | **流式输出（SSE + WebSocket）** | 实时展示 Agent 思考过程，用户体验好 |
| 工具确认 | **读操作自动，写操作确认** | SELECT/SHOW/DESCRIBE 自动执行，UPDATE/DELETE/INSERT 需用户确认 |

## 4. 优先级功能

| 优先级 | 功能 | 说明 |
|---|---|---|
| P0 | 自然语言转 SQL | 用户用自然语言描述查询需求，Agent 转换为 SQL 并执行 |
| P0 | 多步骤数据分析 | 自动发现数据源 → 构建查询 → 执行 → 分析 → 生成洞察 |
| P0 | 数据库探索 | 列出数据库、列出表、查看表结构 |
| P1 | 查询结果可视化 | 表格、Markdown 格式展示 |

## 5. 用户场景示例

### 场景 1：数据库探索

```
用户：帮我看看 onedba 相关的数据库
Agent：[调用 list_databases(keyword="onedba")]
      找到以下数据库：
      | 库名 | 实例 | 环境 | 主体 |
      |---|---|---|---|
      | dw_onedba | dw-onedba-t1 | 测试 | 识装 |
      | dw_onedba_cs | dw-test-t0-03 | 测试 | 识装 |

用户：看看 dw_onedba 里有哪些表
Agent：[调用 list_tables(schema_id=65938636)]
      该库共有 532 张表，部分如下：
      | 表名 | 说明 |
      |---|---|
      | order_record | 工单记录 |
      | db_instance | 数据库实例 |
      ...
```

### 场景 2：数据分析

```
用户：帮我分析一下最近的工单情况
Agent：[多步骤执行]
      1. 发现 dw_onedba.order_record 表
      2. 查看表结构
      3. 执行分组统计 SQL
      4. 生成分析报告

      ## 工单分析报告
      共 1,171 条工单，20 种类型。

      ### 工单总量排行
      | 排名 | 类型 | 总数 | 占比 |
      |---|---|---|---|
      | 1 | 数据变更 | 354 | 30.2% |
      | 2 | 权限申请 | 128 | 10.9% |
      ...

      ### 关键发现
      - **结构同步系统关闭率 91%**，建议排查
      - **追加白名单执行失败率 43%**，建议排查
```

### 场景 3：自然语言查询

```
用户：查一下 order_record 表里最近的 10 条工单
Agent：[调用 execute_sql]
      ```sql
      SELECT id, committer_name, order_type, status_desc, create_time
      FROM order_record
      ORDER BY create_time DESC
      LIMIT 10
      ```
      | id | 提交人 | 类型 | 状态 | 创建时间 |
      |---|---|---|---|---|
      | 20857 | 东青 | structureSync | 审批中 | 2026-06-09 |
      ...
```
