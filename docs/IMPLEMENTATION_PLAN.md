# DBAgent v2 实现计划

## 当前状态

### 已完成
- ✅ 创建 `last/` 目录，归档旧代码
- ✅ 移动旧架构核心文件到 `last/`
- ✅ 完成架构设计文档 (`docs/ARCHITECTURE_V2.md`)

### 当前项目结构

```
DBAgent/
├── app/                          # 新架构代码
│   ├── agent/
│   │   ├── __init__.py
│   │   └── llm.py               # LLM 客户端（保留）
│   ├── api/
│   │   └── __init__.py          # 需要重建 routes.py 和 schemas.py
│   ├── client/
│   │   ├── __init__.py
│   │   └── onedba_client.py     # OneDBA API 客户端（保留）
│   ├── memory/
│   │   └── __init__.py          # 需要重建 summary.py
│   ├── nl2sql/
│   │   ├── __init__.py
│   │   ├── generator.py         # SQL 生成（保留，需重构）
│   │   ├── repair.py            # SQL 修复（保留）
│   │   ├── resolver.py          # 名称解析（保留）
│   │   ├── schema.py            # Schema 解析（保留）
│   │   ├── semantic_parser.py   # 语义规则解析（保留）
│   │   ├── semantics.py         # 语义规则（保留）
│   │   └── validator.py         # SQL 验证（保留）
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── db_explorer.py       # 数据库探索工具（保留）
│   │   ├── formatters.py        # 格式化工具（保留）
│   │   └── sql_executor.py      # SQL 执行器（保留）
│   ├── config.py                # 配置（保留）
│   └── main.py                  # FastAPI 入口（保留）
├── last/                        # 旧架构归档
│   ├── agent/                   # 旧的 Agent 实现
│   ├── nl2sql/intent.py         # 旧的正则意图解析
│   ├── docs/                    # 旧文档
│   ├── tests/                   # 旧测试
│   ├── static/                  # 旧前端
│   └── ...
├── docs/
│   └── ARCHITECTURE_V2.md       # 新架构设计文档
└── requirements.txt
```

---

## 实现计划

### Phase 1: 核心工具实现（优先级：高）

#### 1.1 创建新的 Tool 定义文件

**文件**: `app/tools/agent_tools.py`

**任务**:
- [ ] 实现 `list_databases_tool` — 列出可用数据库
  - 参数: `keyword: str = ""`
  - 返回: 数据库列表（JSON 格式）
  - 复用: `app/tools/db_explorer.py` 中的 `list_databases` 函数

- [ ] 实现 `select_database_tool` — 选择当前数据库
  - 参数: `schema_id: int`
  - 返回: 确认信息
  - 逻辑: 验证 schema_id 是否存在，更新会话上下文

- [ ] 实现 `list_tables_tool` — 列出数据库中的表
  - 参数: `schema_id: int, keyword: str = ""`
  - 返回: 表名列表（Markdown 格式）
  - 复用: `app/tools/db_explorer.py` 中的 `list_tables` 函数

- [ ] 实现 `describe_table_tool` — 查看表结构
  - 参数: `schema_id: int, table_name: str`
  - 返回: 字段信息（Markdown 格式）
  - 复用: `app/tools/db_explorer.py` 中的 `describe_table` 函数

- [ ] 实现 `execute_sql_tool` — 直接执行 SQL
  - 参数: `schema_id: int, sql: str`
  - 返回: 查询结果（Markdown 格式）
  - 复用: `app/tools/sql_executor.py` 中的 `execute_sql` 函数
  - 安全检查: 调用 `needs_confirmation()` 检查写操作

- [ ] 实现 `ask_user_tool` — 向用户提问
  - 参数: `question: str`
  - 返回: 用户回答
  - 特殊处理: 需要暂停 Agent 执行，等待用户输入

**依赖**:
- `app/tools/db_explorer.py`
- `app/tools/sql_executor.py`
- `app/tools/formatters.py`
- `app/client/onedba_client.py`

#### 1.2 实现 query_database 核心工具

**文件**: `app/tools/query_database.py`

**任务**:
- [ ] 实现 `query_database_tool` 函数
  - 参数: `schema_id: int, question: str, table_name: str`
  - 返回: 查询结果（Markdown 格式，包含 SQL + 结果表格 + 说明）

- [ ] 实现内部流程
  1. 调用 `onedba_client.execute_sql()` 执行 `DESCRIBE table_name`
  2. 解析表结构（复用 `app/nl2sql/schema.py` 中的 `parse_describe_result`）
  3. 加载语义规则（复用 `app/nl2sql/semantics.py` 中的 `resolve_semantics`）
  4. 调用 LLM 生成 SQL（重构 `app/nl2sql/generator.py`）
     - 移除对 `NL2SQLIntent` 的依赖
     - 改为接收自然语言问题 + 表结构 + 语义规则
  5. 验证 SQL（复用 `app/nl2sql/validator.py` 中的 `validate_sql`）
  6. 执行 SQL（调用 `onedba_client.execute_sql`）
     - 失败时调用 LLM 修复（复用 `app/nl2sql/repair.py` 中的 `repair_sql`）
     - 最多重试 3 次
  7. 格式化结果（复用 `app/tools/formatters.py` 中的 `format_as_markdown_table`）

- [ ] 实现 SQL 生成 prompt
  - 包含：用户问题、表结构、语义规则、示例值
  - 约束：只读查询、MySQL 8 语法、最小列数、适当 LIMIT

**依赖**:
- `app/nl2sql/generator.py`（需重构）
- `app/nl2sql/validator.py`
- `app/nl2sql/repair.py`
- `app/nl2sql/schema.py`
- `app/nl2sql/semantics.py`
- `app/client/onedba_client.py`

#### 1.3 重构 SQL 生成器

**文件**: `app/nl2sql/generator.py`

**任务**:
- [ ] 移除对 `NL2SQLIntent` 的依赖
- [ ] 修改 `generate_sql` 函数签名
  - 旧: `generate_sql(intent: NL2SQLIntent, table_name: str, columns: list[ColumnSchema], ...)`
  - 新: `generate_sql(question: str, table_name: str, columns: list[ColumnSchema], semantic_rules: list[SemanticRule] = None, ...)`
- [ ] 更新 prompt 模板
  - 移除对 `intent.operation`、`intent.field_hints` 等的引用
  - 改为直接使用用户问题
- [ ] 保留核心逻辑：字段匹配、时间字段推断、SQL 构建

**影响范围**:
- `app/tools/query_database.py`（新文件）需要调用重构后的 `generate_sql`

---

### Phase 2: Agent 核心实现（优先级：高）

#### 2.1 创建 Agent Prompt

**文件**: `app/agent/prompts.py`

**任务**:
- [ ] 设计 Agent 系统 prompt
  - 角色定义：数据库分析助手
  - 核心原则：4 条核心指导原则
  - 追问处理策略：明确如何处理追问
  - 安全约束：只读查询、写操作确认、禁止 DDL

- [ ] 设计 few-shot 示例
  - 示例 1：基础查询（查表数据量）
  - 示例 2：多库选择（先 list_databases，再 select_database，再 query_database）
  - 示例 3：追问处理（"改成最近 7 天"）
  - 示例 4：信息不足（用 ask_user 询问）

**参考**: `docs/ARCHITECTURE_V2.md` 中的 Agent Prompt 设计

#### 2.2 创建 AgentExecutor 封装

**文件**: `app/agent/llm_agent.py`

**任务**:
- [ ] 实现 `create_agent` 函数
  - 初始化 LLM（使用 `app/agent/llm.py` 中的 `get_llm`）
  - 加载工具列表（从 `app/tools/agent_tools.py` 和 `app/tools/query_database.py`）
  - 创建 AgentExecutor（使用 LangChain 的 `create_react_agent`）

- [ ] 实现 `run_agent` 函数
  - 参数: `user_input: str, session_state: dict`
  - 返回: `dict`（包含 response, updated_state）
  - 逻辑:
    1. 从 session_state 恢复上下文（chat_history, summary, selected_schema_id 等）
    2. 构建 Agent 输入（包含用户问题、对话历史、摘要、数据库上下文）
    3. 调用 AgentExecutor.ainvoke()
    4. 提取响应和中间步骤
    5. 更新 session_state（追加 chat_history，更新 summary）
    6. 返回结果

- [ ] 实现对话记忆管理
  - 保留最近 20 条对话历史
  - 每轮对话后调用 LLM 压缩摘要（复用 `last/agent/summary.py` 的逻辑）

- [ ] 实现写操作确认机制
  - 检测 Agent 是否调用了 `execute_sql_tool` 且 SQL 是 UPDATE/DELETE/INSERT
  - 如果是，设置 `needs_confirmation=True`，暂停执行
  - 等待用户确认后继续执行

**依赖**:
- LangChain: `langchain.agents`, `langchain_core.agents`
- `app/agent/llm.py`
- `app/tools/agent_tools.py`
- `app/tools/query_database.py`

#### 2.3 简化 Agent 状态定义

**文件**: `app/agent/state.py`

**任务**:
- [ ] 定义新的 `AgentState` TypedDict
  ```python
  class AgentState(TypedDict, total=False):
      # 基础输入
      user_input: str
      session_id: str

      # 对话记忆
      chat_history: list[dict]
      summary: str

      # 数据库上下文
      selected_schema_id: int | None
      selected_database: dict | None

      # 最终输出
      response: str

      # 确认状态
      needs_confirmation: bool
      pending_action: dict | None
  ```

- [ ] 移除旧字段
  - `execution_plan`
  - `parsed_intent`
  - `last_nl2sql_task` / `last_generated_sql` 等
  - `pending_nl2sql` / `pending_semantic_confirmation`

---

### Phase 3: Graph 重构（优先级：中）

#### 3.1 重构 graph.py

**文件**: `app/agent/graph.py`

**任务**:
- [ ] 移除旧的 6 节点图
  - 删除: `understand_node`, `plan_node`, `act_node`, `reflect_node`, `summarize_node`, `confirm_node`

- [ ] 创建新的 Agent 驱动图
  - 单节点: `agent_node`（调用 `run_agent`）
  - 条件路由:
    - 如果 `needs_confirmation=True` → `confirm_node`
    - 否则 → END

- [ ] 实现 `agent_node`
  - 调用 `run_agent` 函数
  - 返回更新后的状态

- [ ] 实现 `confirm_node`
  - 生成确认提示
  - 等待用户输入"确认执行"

- [ ] 实现条件路由函数
  - `should_continue_after_agent`: 判断是否需要确认

**参考**: `docs/ARCHITECTURE_V2.md` 中的状态设计

---

### Phase 4: API 路由适配（优先级：中）

#### 4.1 重建 API 路由

**文件**: `app/api/routes.py`

**任务**:
- [ ] 实现 `POST /api/chat` — SSE 流式聊天
  - 调用 `agent_graph.astream()`
  - 流式返回 Agent 思考过程和最终响应

- [ ] 实现 `POST /api/chat/sync` — 同步聊天
  - 调用 `agent_graph.ainvoke()`
  - 返回完整响应

- [ ] 实现 `WebSocket /api/ws/{session_id}` — WebSocket 聊天
  - 双向通信
  - 支持流式返回

- [ ] 实现 `GET /api/sessions/{session_id}` — 获取会话状态
  - 返回 session_state

- [ ] 实现会话管理
  - `SESSION_STORE`: 进程内会话存储
  - `build_initial_state()`: 从 SESSION_STORE 恢复状态
  - `save_session()`: 保存状态到 SESSION_STORE

**参考**: `last/agent/routes.py`（旧实现）

#### 4.2 重建 API Schema

**文件**: `app/api/schemas.py`

**任务**:
- [ ] 定义请求模型
  - `ChatRequest`: `user_input: str, session_id: str`

- [ ] 定义响应模型
  - `ChatResponse`: `response: str, session_id: str, needs_confirmation: bool`
  - `SessionState`: 会话状态

**参考**: `last/agent/schemas.py`（旧实现）

---

### Phase 5: 多轮对话支持（优先级：中）

#### 5.1 对话记忆集成

**文件**: `app/memory/summary.py`

**任务**:
- [ ] 实现 `update_summary` 函数
  - 参数: `current_summary: str, user_input: str, assistant_response: str`
  - 返回: `new_summary: str`
  - 逻辑: 调用 LLM 压缩对话为摘要（保留数据库选择、关键结果）
  - 限制: 摘要长度不超过 500 字符

- [ ] 复用旧实现
  - 从 `last/agent/summary.py` 复制逻辑
  - 适配新的 AgentState

#### 5.2 追问支持测试

**任务**:
- [ ] 编写测试用例
  - 测试 1: 基础追问（"改成最近 7 天"）
  - 测试 2: 复杂追问（"添加 WHERE 条件 status = paid"）
  - 测试 3: 结构修改（"按 category 分组"）

- [ ] 验证 Agent 行为
  - Agent 应该重新调用 `query_database`，而不是尝试修改 SQL
  - Agent 应该在 question 中包含完整需求（包含修改点）

---

### Phase 6: 清理与优化（优先级：低）

#### 6.1 移除旧代码

**任务**:
- [ ] 删除 `last/` 目录（确认新架构稳定后）
- [ ] 删除 `app/nl2sql/intent.py`（已移到 `last/nl2sql/intent.py`）
- [ ] 删除 `last/agent/nodes.py` 中的旧节点实现

#### 6.2 Prompt 优化

**任务**:
- [ ] 根据测试结果调优 Agent prompt
- [ ] 添加更多 few-shot 示例
- [ ] 优化追问处理策略

#### 6.3 性能优化

**任务**:
- [ ] 缓存表结构（避免重复 DESCRIBE）
- [ ] 减少不必要的工具调用
- [ ] 优化 LLM 调用次数

---

## 实施顺序

建议按以下顺序实施：

1. **Phase 1.1** → 创建 Tool 定义文件（基础）
2. **Phase 1.3** → 重构 SQL 生成器（解除对 NL2SQLIntent 的依赖）
3. **Phase 1.2** → 实现 query_database 核心工具（核心能力）
4. **Phase 2.1** → 创建 Agent Prompt（指导 Agent 行为）
5. **Phase 2.3** → 简化 Agent 状态定义（数据结构）
6. **Phase 2.2** → 创建 AgentExecutor 封装（Agent 核心）
7. **Phase 3.1** → 重构 graph.py（集成 Agent）
8. **Phase 5.1** → 对话记忆集成（多轮对话）
9. **Phase 4.2** → 重建 API Schema（接口定义）
10. **Phase 4.1** → 重建 API 路由（对外接口）
11. **Phase 5.2** → 追问支持测试（验证能力）
12. **Phase 6** → 清理与优化（收尾）

---

## 依赖关系

```
Phase 1.1 (Tool 定义)
    ↓
Phase 1.3 (重构 SQL 生成器)
    ↓
Phase 1.2 (query_database)
    ↓
Phase 2.1 (Agent Prompt) + Phase 2.3 (AgentState)
    ↓
Phase 2.2 (AgentExecutor)
    ↓
Phase 3.1 (重构 graph.py)
    ↓
Phase 5.1 (对话记忆)
    ↓
Phase 4.2 (API Schema)
    ↓
Phase 4.1 (API 路由)
    ↓
Phase 5.2 (追问测试)
    ↓
Phase 6 (清理优化)
```

---

## 风险与注意事项

1. **LangChain 版本兼容性**
   - 确保使用兼容的 LangChain 版本
   - `create_react_agent` API 可能在不同版本中有变化

2. **LLM 调用成本**
   - Agent 每轮可能调用多次 LLM（决策 + SQL 生成 + 修复）
   - 需要通过缓存和优化工具调用来控制成本

3. **写操作确认**
   - 需要特殊处理 Agent 暂停和恢复
   - 可能需要自定义 AgentExecutor 的行为

4. **追问理解**
   - Agent 可能无法正确理解复杂追问
   - 需要通过 prompt 优化和 few-shot 示例来引导

5. **会话状态管理**
   - `SESSION_STORE` 是进程内的，重启会丢失
   - 生产环境需要持久化存储（Redis、数据库）

---

## 下一步行动

立即开始 **Phase 1.1**: 创建新的 Tool 定义文件 (`app/tools/agent_tools.py`)
