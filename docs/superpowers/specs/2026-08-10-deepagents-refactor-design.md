# Deepagents 重构设计（2026-08-10）

## 1. 背景与目标

本项目（SDK-DBAgent）当前是手写 ReAct Agent 的 NL2SQL 数据库助手：`app/agent/runner.py` 直接基于 `openai` SDK 实现 ReAct 循环，自建 `ToolRegistry`（6 个工具 + 中间件链），单 Agent 无协作，8 段上下文经 `build_context()` 每轮全量拼进用户 prompt。

本次目标：**分两阶段把项目从手写 ReAct 重构为 deepagents（LangGraph `create_agent`）架构**，全程保持生产可用，每阶段结束可独立部署。

### 已确认的关键决策

| 维度 | 决策 |
|---|---|
| 重构深度 | 全面重写为 LangGraph 架构 |
| 推进方式 | 方案 C：渐进两阶段（阶段 1 换引擎保兼容，阶段 2 拆子代理重设事件流） |
| 对外接口 | 允许重设事件/API，前端适配（阶段 1 保持零改动，阶段 2 增量适配） |
| LLM 接入 | LangChain `ChatOpenAI` 接入 DeepSeek-V4（OpenAI 兼容代理） |
| 记忆层 | 本次不动，后续单独做（聚焦 Agent 引擎） |
| 多 Agent | 多角色子代理架构 |
| 安全模型 | SQL 校验保留在工具层（permissions 不适用自定义工具）；deepagents permissions 仅作未来文件系统备用 |
| 部署与观测 | 保持 Docker，LangGraph 持久化 |

## 2. 阶段边界

- **阶段 1（引擎替换）**：`runner.py` 手写 ReAct → `create_deep_agent` 单代理；SSE 事件流、HTTP API、前端完全兼容、零改动。验收：现有测试全绿 + 冒烟通过 + SSE 逐字段一致。
- **阶段 2（多角色子代理）**：拆 4 角色子代理；SSE 事件流重设（新增 `subagent_start/subagent_step`），前端增量适配。验收：行为等价 + 新事件流可观测。

## 3. 总体架构（阶段 2 目标态）

```
FastAPI (app/api/routes.py)                    ← HTTP/SSE 不变（阶段2起事件模型演进）
   └─ agent/runner.py → create_deep_agent      ← 替换自建 ReAct 循环
        │  model: ChatOpenAI(DeepSeek-V4, 走 OpenAI 兼容代理)
        ├─ Orchestrator ────────────────── 主代理（意图理解/最终回答/委派/当前库）
        │    ├─ 委派 task(schema-explorer, ...)
        │    ├─ 委派 task(sql-generator, ...)
        │    └─ 委派 task(sql-reviewer, ...)
        ├─ subagent: schema-explorer        ← 表发现 + schema 探查
        │    tools: find_table / list_databases / describe_table
        ├─ subagent: sql-generator          ← NL2SQL 生成
        │    tools: query_database（内部调 nl2sql/generator.py）
        └─ subagent: sql-reviewer           ← SQL 校验/修复
             tools: execute_sql（内部调 nl2sql/validator.py + repair.py）
   └─ 保留不动：memory/*, nl2sql/*, datavault/*, knowledge/*, observation/*, client/onedba.py, API 路由, 静态前端
```

## 4. 核心保留层（两阶段都不动）

- `nl2sql/`（生成→校验→修复流水线）
- `memory/`（Protocol 存储：SqlMemoryBackend / PreferenceBackend / StorageBackend / AdminStoreBackend）
- `datavault/`（HDC）、`knowledge/`（OpenViking）、`observation/`（Langfuse）
- `client/onedba.py`、API 路由、静态前端

## 5. 上下文与状态管理

### 5.1 输入上下文三类处理

| 处理方式 | 段落 | 说明 |
|---|---|---|
| 移除（交 deepagents 内建） | ① 对话摘要 ② 最近历史 | 由 Summarization/offloading + checkpoint 自动承载 |
| 改为 on-demand 读取 | ③ 当前数据库 ④ OpenViking 记忆 ⑥ 偏好 ⑦ HDC ⑧ SQL 记忆 | 通过 `@dynamic_prompt` middleware 或工具内读取，仅相关时注入 |
| 工具内检索 | ⑤ SQL 参考（碎片化条目） | 保留 RAG，由 sql-generator 子代理按需加载 |

### 5.2 状态与上下文接口（阶段 1 关键改动）

- **`DeepAgentState` 自定义字段**（`deepagents>=0.6.6`）：`current_schema_id`（原先塞在 session_state）、`session_id` / `user_id`
- **`context_schema`（RuntimeContext）**：HDC、偏好、SQL 记忆等每轮动态检索结果走 runtime context，子代理自动继承；顺带解决当前 ContextVar 侧信道痛点
- **SSE 事件适配层（阶段 1）**：`stream_events(version="v3")` 的 `messages`/`tool_calls` projection → 现有 `step/sql/final` 事件，前端零改动
- **取消机制**：`CancelEventRegistry` 保留为驱动层，驱动 `agent.ainvoke(..., interrupt_before=...)` 中断；阶段 1 保现有 cancel API 语义，阶段 2 可选演进 `interrupt_on=["tools"]`

### 5.3 三层记忆的迁移映射（基于代码实证）

| 段 | 归属 | 迁移方式 |
|---|---|---|
| ⑤ SQL 参考知识库 | 团队规则，碎片化条目 | 保留 RAG 检索，改由 sql-generator 子代理按需加载（写 SQL 前取） |
| ⑧ SQL 历史记忆 | 用户历史，语义检索（余弦相似度） | 保留 `search_similar`，在 sql-generator 内部检索，注入时机从"每轮全量"改"写 SQL 前" |
| ⑥ 查询偏好 | 表级使用偏好（query_count 排序） | 保留 `retrieve_preferences`，在 schema-explorer 找表前调用 |

三者的**存储实现（Protocol + SQLite）全部保留**，只改变**注入时机和位置**。

### 5.4 不变量

- HDC、偏好、SQL 记忆、SQL 参考四类检索结果**永不进 system prompt 常量部分**，只进 runtime context / 工具内检索
- `nl2sql/`、`memory/`、`datavault/`、`knowledge/` 业务模块零改动

## 6. 子代理职责与工具归属

### 6.1 4 角色划分

| 子代理 | 职责 | 挂载工具 | 需要的上下文段 | 明确不挂 |
|---|---|---|---|---|
| Orchestrator（主代理） | 意图理解、任务规划、委派、最终回答、跨子代理调度 | `task` 委派工具、`select_database` | 摘要、当前 DB、用户意图 | 不直接碰数据工具 |
| schema-explorer | 表发现 + schema 探查 | `find_table`、`list_databases`、`describe_table` | 偏好（⑥） | 不挂 `execute_sql`/`query_database` |
| sql-generator | NL2SQL 生成 | `query_database`（内部调 generator.py） | HDC（⑦）、SQL 参考（⑤）、SQL 记忆（⑧） | 不挂 `execute_sql` |
| sql-reviewer | SQL 校验/修复 | `execute_sql`（内部调 validator.py + repair.py） | 校验规则（静态） | 不挂 `find_table`/`describe_table` |

### 6.2 安全边界

**工具级隔离即安全边界**：sql-generator 只能生成，sql-reviewer 才能执行，schema-explorer 只读 schema，主代理是唯一能委派者。权限最小化天然成立。

**写操作/DDL 拦截**：保留在工具层（`execute_sql`/`query_database` 内部调 `validator.py`，只读 SELECT/SHOW/DESCRIBE + LIMIT 500，写/DDL 拦截）。deepagents permissions 不适用自定义工具（官方明确仅作用于内置 filesystem 工具），仅作未来文件系统备用。

### 6.3 子代理通信与结果回传

- `task` 工具委派，父代理拿最终报告（`ToolMessage` content），中间工具调用完全隔离
- sql-generator / sql-reviewer 用 `response_format`（Pydantic）序列化结构化 JSON 回传（如 `{sql, explanation, assumptions}` / `{valid, reason, repair}`）
- **NL2SQL 三阶段闭环留在 `query_database` 工具内部**（不拆子代理往返）

### 6.4 已确认决策

1. 生成→校验→修复闭环**留在 `query_database` 工具内部**
2. `select_database` **保留在主代理**（Orchestrator 记住当前库）

## 7. SSE 事件流与取消机制

### 7.1 阶段 1（引擎替换）：事件流完全兼容

保留现有 `step/sql/llm_call/final` 4 类事件，前端零改动。只替换事件生产源：

| deepagents projection | 映射为 SSE 事件 |
|---|---|
| `messages` 流（content-block-delta） | `step`（thinking） |
| `tool_calls` 流 | `step`（tool:xxx running/completed）+ `sql` |
| 流结束 | `final` |
| 原有 `llm_call` 事件 | 从 stream_events 的 LLM 事件**经保兼容垫片重建**（评测框架零改动） |

**llm_call 取舍：选 A（保兼容垫片）**，评测框架零改动；到阶段 2 重设事件流时统一升级。

### 7.2 阶段 2（子代理）：事件流演进，前端增量适配

| 新 SSE 事件 | 内容 | 来源 |
|---|---|---|
| `step`（thinking） | 主代理思考文本 | messages 流（coordinator namespace） |
| `subagent_start` | 子代理启动（`{type, task}`） | `stream.subagents` |
| `subagent_step` | 子代理内部工具进度 | subagent handle 的 tool_calls |
| `sql` | 生成的 SQL（含所属子代理） | 各层提取 |
| `final` | 最终响应 + 完整子代理轨迹 | 流结束 |

关键实现：`stream.interleave("messages", "subagents")` 并行消费，用 namespace/`subagent` handle 的 `name` 区分来源。前端增量适配：新增 `subagent_start/subagent_step` 折叠式轨迹渲染，其余 `step/sql/final` 语义不变。

### 7.3 取消机制

现状：`CancelEventRegistry`（asyncio.Event + 5min TTL）。deepagents 取消模型为 checkpoint 中断（interrupt）：
- 阶段 1：`ainvoke(..., interrupt_before=...)`，`CancelEventRegistry` 保留为驱动层。对外 cancel API 语义不变
- 阶段 2：可选演进 `interrupt_on=["tools"]`（工具级可恢复中断）

## 8. 测试与验证策略

### 8.1 测试分层

| 层 | 内容 | 关键点 |
|---|---|---|
| 单元测试 | 工具、NL2SQL、memory、datavault 各模块 | 不动，现有测试原样通过 |
| 集成测试 | `create_deep_agent` 组装、事件流翻译层 | 新增：`stream_events` → SSE 事件映射正确 |
| 回归测试 | 现有 `tests/` 全量 + `scripts/acceptance.sh` | 阶段 1 验收红线 |
| 评测框架 | `tests/evaluation/`（TC-001...） | 阶段 1 保留 llm_call 垫片 → 零改动 |

### 8.2 阶段验收标准

**阶段 1（引擎替换）验收**：
- [ ] 现有 pytest 全量通过（含评测框架）
- [ ] `scripts/acceptance.sh` 冒烟通过
- [ ] SSE 4 类事件与重构前逐字段一致（step/sql/llm_call/final）
- [ ] cancel API 语义不变
- [ ] DeepSeek 通过 `ChatOpenAI` 接入正常，function calling 行为等价

**阶段 2（子代理）验收**：
- [ ] 4 角色子代理组装完成，端到端行为等价
- [ ] 新事件流 `subagent_start/subagent_step` 前端渲染可用
- [ ] 上下文隔离生效：子代理中间工具输出不再进主上下文
- [ ] 写操作/DDL 拦截回归验证（validator 规则不受影响）
- [ ] 评测集跑分不低于重构前基线（用 `tools/comparison_experiment.sh` 对比）

### 8.3 风险与缓解

| 风险 | 缓解 |
|---|---|
| deepagents/LangChain 与 DeepSeek 兼容性未知（function calling 边界行为差异） | 阶段 1 先做最小 POC（create_deep_agent + 单个 query_database）验证等价 |
| `stream_events` 事件格式与现有 SSE 事件映射偏差 | 阶段 1 用逐字段 diff 验收，先写事件适配层单测 |
| 子代理引入额外 LLM 调用 → 成本↑ | 阶段 2 拆分粒度可调（只拆 sql-generator 起步）；每个子代理强制 concise 报告 |
| 取消语义在 LangGraph 中断模型下变复杂 | 阶段 1 保留 CancelEventRegistry 作驱动层，中断语义随后验证 |

## 9. 明确不做（本次范围外）

- 记忆层重写（会话/偏好/SQL 记忆/HDC 架构），后续单独做
- 部署形态变更（保持 Docker + gunicorn + LangGraph SQLite checkpoint）
- 前端整体重写（仅阶段 2 增量适配事件流渲染）
- deepagents permissions 机制接入（当前无文件系统需求）

## 10. 参考文献

- Deep Agents 官方文档：docs.langchain.com/oss/python/deepagents/{overview, quickstart, tools, context-engineering, event-streaming, subagents, permissions, backends, going-to-production}
- API 参考：reference.langchain.com/python/deepagents/
- 当前代码实证：`app/agent/runner.py`、`app/tools/__init__.py`、`app/memory/sql_memory.py`、`app/memory/preferences.py`
