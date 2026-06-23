# DBAgent v2 架构设计文档

## 1. 背景与问题

### 1.1 当前架构的问题

DBAgent v1 采用了**正则驱动的意图解析管道**，存在以下核心问题：

1. **脆弱的意图识别**：`intent.py` 中的关键词匹配极其脆弱，用户换一种说法就会出错
   - 例如："最近有哪些表" 会匹配到 `recent` 而不是 `table_counts`
   - 例如：用户说 "查一下 orders" 而不是 "orders 表"，系统就无法识别

2. **LLM 形同虚设**：`plan_node` 的 6 级优先级链绕过了 LLM，导致 LLM 调用被浪费
   - `understand_node` 的 LLM 分类结果几乎没被使用
   - 真正的路由决策全靠正则匹配

3. **追问能力受限**：follow-up 系统只支持 3 种操作（改 LIMIT、改时间、看 SQL）
   - 无法处理：添加 WHERE 条件、改 GROUP BY、换维度字段等
   - 原因：`_apply_followup_patch()` 只能做结构化 patch，无法理解复杂追问

4. **工具列表不完整**：`PLAN_PROMPT` 只列了 4 个工具，但系统实际有 10+ 个工具
   - LLM 根本不知道有 `nl2sql_query`、`select_database` 等核心工具

### 1.2 设计目标

- ✅ **LLM 驱动所有决策**：用 LLM 替代正则意图解析
- ✅ **灵活的追问能力**：支持任意形式的追问（改条件、改字段、改结构）
- ✅ **简化的架构**：移除复杂的优先级链和状态管理
- ✅ **保留核心能力**：NL2SQL、SQL 验证、SQL 修复、语义规则

---

## 2. 新架构设计

### 2.1 核心思路

从 **"正则路由 + 固定管道"** 切换到 **"LLM Agent + 工具调用"**：

```
旧架构:
  用户输入 → 正则意图解析 → 优先级路由 → 固定管道执行 → 响应

新架构:
  用户输入 → LLM Agent (ReAct) → 自主选择工具 → 执行 → 响应
                    ↑                    |
                    └── 观察结果 ←───────┘
```

### 2.2 技术栈

- **Agent 框架**: LangChain AgentExecutor (ReAct 模式)
- **LLM**: DeepSeek (继续使用)
- **状态管理**: LangGraph (保留，但简化为 Agent 状态包装)
- **API**: FastAPI (保留)

### 2.3 工具集设计

将所有能力封装为 LangChain Tool，让 LLM 自主选择：

| 工具名 | 功能 | 参数 | 说明 |
|--------|------|------|------|
| `list_databases` | 列出可用数据库 | `keyword: str` | 搜索数据库 |
| `select_database` | 选择当前数据库 | `schema_id: int` | 设置上下文 |
| `list_tables` | 列出数据库中的表 | `schema_id: int, keyword: str` | 搜索表 |
| `describe_table` | 查看表结构 | `schema_id: int, table_name: str` | 获取字段信息 |
| `query_database` | **核心 NL2SQL 工具** | `schema_id: int, question: str, table_name: str` | 自然语言转 SQL 并执行 |
| `execute_sql` | 直接执行 SQL | `schema_id: int, sql: str` | 执行原始 SQL |
| `ask_user` | 向用户提问 | `question: str` | 信息不足时询问 |

**关键变化**：
- `query_database` 替代原来的 `nl2sql_query`，接口更简洁
- 移除 `followup_query` — 追问由 Agent 通过 `query_database` 自然处理
- 移除 `confirm_semantic_rules` / `save_custom_semantic_rule` — 语义规则由 Agent 在对话中自然处理

### 2.4 Agent Prompt 设计

```
你是一个数据库分析助手 OneDBA。你可以通过工具帮助用户探索数据库、生成 SQL、执行查询。

## 核心原则
1. 如果用户没有指定数据库，先用 list_databases 查找，再用 select_database 选择
2. 如果用户想用自然语言查询数据，使用 query_database（需要提供 schema_id 和表名）
3. 如果信息不足（比如多个数据库候选、多个表名相似），用 ask_user 让用户选择
4. 如果用户想修改上一轮查询，直接再次调用 query_database 并说明修改点

## 追问处理
当用户说"改成最近 7 天"、"只看前 10 条"等，你应该：
- 理解这是对上一轮查询的修改
- 重新调用 query_database，在 question 中说明完整需求（包含修改点）
- 不要试图修改 SQL 字符串，而是重新生成

## 安全约束
- 只允许 SELECT/SHOW/DESCRIBE
- UPDATE/DELETE/INSERT 需要用户确认
- 禁止 DDL 操作
```

### 2.5 query_database 工具内部流程

```
query_database(schema_id, question, table_name)
    │
    ├── 1. DESCRIBE table → 获取表结构
    │
    ├── 2. 加载语义规则（如果有）
    │
    ├── 3. LLM 生成 SQL
    │      prompt 包含：用户问题 + 表结构 + 语义规则 + 示例值
    │
    ├── 4. 验证 SQL（安全检查、字段检查、LIMIT）
    │
    ├── 5. 执行 SQL
    │      失败 → LLM 修复 → 重新验证 → 重试（最多 3 次）
    │
    └── 6. 返回结果（Markdown 表格 + SQL + 说明）
```

### 2.6 多轮对话支持

**对话记忆**：
- `chat_history`: 最近 20 条消息（user/assistant 交替）
- `summary`: LLM 压缩的摘要（保留数据库选择、关键结果）

**追问机制**：
- 不再用 `last_nl2sql_task` 做结构化 patch
- Agent 通过 `chat_history` 理解追问意图
- 重新调用 `query_database` 并传入完整问题（包含修改点）

**示例对话**：
```
用户: 查一下 orders 表最近 30 天的订单数
Agent: [调用 query_database(schema_id=1, question="orders 表最近 30 天的订单数", table_name="orders")]
Agent: 查询结果...（Markdown 表格）

用户: 改成最近 7 天
Agent: [理解这是对上一轮的修改]
Agent: [调用 query_database(schema_id=1, question="orders 表最近 7 天的订单数", table_name="orders")]
Agent: 已修改为最近 7 天，查询结果...
```

### 2.7 状态设计

简化 `AgentState`：

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

    # Agent 执行状态（由 AgentExecutor 管理）
    intermediate_steps: list[tuple[AgentAction, str]]

    # 最终输出
    response: str

    # 确认状态
    needs_confirmation: bool
    pending_action: dict | None
```

**移除的字段**：
- `execution_plan` — 由 Agent 自主决定
- `parsed_intent` — 不再需要正则意图解析
- `last_nl2sql_task` / `last_generated_sql` 等 — 追问由 Agent 通过对话历史处理
- `pending_nl2sql` / `pending_semantic_confirmation` — 由 Agent 通过 `ask_user` 处理

---

## 3. 实现步骤

### Phase 1: 核心 Agent 搭建

1. **创建新的 Agent 模块**
   - `app/agent/llm_agent.py` — LangChain AgentExecutor 封装
   - 新的 `app/agent/prompts.py` — Agent 系统 prompt
   - 新的 `app/agent/tools.py` — 所有 Tool 定义

2. **实现 query_database 工具**
   - 复用现有的 `generator.py`、`validator.py`、`repair.py`
   - 移除 `intent.py` 的正则解析，改为 LLM 直接理解问题
   - 保留 `resolver.py`（表名/数据库名解析）

3. **简化 graph.py**
   - 移除 understand/plan/act/reflect/summarize 节点
   - 改为 AgentExecutor 驱动的单节点图
   - 保留 confirm 节点（写操作确认）

### Phase 2: 工具迁移

4. **迁移现有工具**
   - `list_databases` / `list_tables` / `describe_table` / `execute_sql` — 直接复用
   - `select_database` — 简化参数（直接传 schema_id）

5. **实现 ask_user 工具**
   - 需要特殊处理：Agent 暂停执行，等待用户输入
   - 可以通过在 graph 中添加 `ask_user` 节点实现

### Phase 3: 多轮对话

6. **对话记忆集成**
   - 将 `chat_history` 和 `summary` 注入 Agent prompt
   - 每轮对话后更新 `summary`

7. **追问支持测试**
   - 测试 Agent 能否正确理解"改成最近 7 天"等追问
   - 验证 Agent 会重新调用 `query_database` 而不是尝试修改 SQL

### Phase 4: 清理与优化

8. **移除旧代码**
   - 删除 `intent.py` 的正则解析函数
   - 删除 `nodes.py` 中的旧节点实现
   - 删除 `state.py` 中不再需要的字段

9. **Prompt 优化**
   - 根据测试结果调优 Agent prompt
   - 添加 few-shot 示例

---

## 4. 关键文件

### 需要修改的文件
- `app/agent/graph.py` — 重构为 AgentExecutor 驱动
- `app/agent/state.py` — 简化状态定义
- `app/agent/prompts.py` — 新的 Agent prompt
- `app/agent/nodes.py` — 删除旧节点，保留工具调用逻辑

### 需要新增的文件
- `app/agent/llm_agent.py` — AgentExecutor 封装
- `app/agent/tools.py` — 统一的 Tool 定义（或拆分到 `app/tools/` 下）

### 需要删除的文件
- `app/nl2sql/intent.py` — 正则意图解析（核心逻辑由 LLM 替代）

### 保留但重构的文件
- `app/nl2sql/generator.py` — SQL 生成（移除对 NL2SQLIntent 的依赖）
- `app/nl2sql/validator.py` — SQL 验证（保留）
- `app/nl2sql/repair.py` — SQL 修复（保留）
- `app/nl2sql/resolver.py` — 名称解析（保留）
- `app/nl2sql/schema.py` — Schema 解析（保留）
- `app/nl2sql/semantics.py` — 语义规则（保留）

---

## 5. 验证方案

### 功能测试
1. **基础查询**: "查一下 orders 表有多少条数据" → 生成 `SELECT COUNT(*) FROM orders`
2. **换一种说法**: "orders 表的数据量是多少" → 同样生成 COUNT 查询
3. **追问**: 上一轮查了最近 30 天，用户说"改成 7 天" → Agent 重新调用 query_database
4. **多库选择**: "查一下 dw 库的 orders 表" → Agent 先 list_databases，再 select_database，再 query_database
5. **信息不足**: "查一下 orders 表"（未指定数据库）→ Agent 用 ask_user 询问

### 回归测试
- 运行现有的 `tests/test_nl2sql.py`，确保核心 NL2SQL 能力不退化
- 运行 `tests/test_agent.py`，验证 Agent 流程正确

### 手动测试
- 启动服务，通过前端 UI 进行多轮对话测试
- 测试各种追问场景

---

## 6. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| LLM 调用成本增加 | Agent 每轮可能调用多次 LLM（决策 + SQL 生成 + 修复）。可以通过缓存表结构、减少不必要的工具调用来控制。 |
| LLM 决策不稳定 | 通过详细的 prompt + few-shot 示例引导；保留 validator 作为安全网。 |
| 追问理解不准确 | 在 prompt 中明确追问处理策略；如果 Agent 理解错误，用户可以重新描述。 |
| 性能下降 | AgentExecutor 的 ReAct 循环可能比固定管道慢。可以通过流式输出改善用户体验。 |

---

## 7. 迁移策略

建议采用 **渐进式迁移**：

1. 先实现新的 Agent 模块，与旧模块并存
2. 通过配置开关切换新旧架构（`USE_LLM_AGENT=true/false`）
3. 充分测试后，再移除旧代码

这样可以随时回退，降低风险。

---

## 8. 当前进度

### 已完成
- ✅ 创建 `last/` 目录，归档旧代码
- ✅ 移动旧架构核心文件到 `last/`
- ✅ 完成架构设计文档

### 进行中
- 🔄 实现新的 Tool 定义（`app/tools/`）
- 🔄 实现 `query_database` 核心工具

### 待开始
- ⏳ 创建 AgentExecutor 封装
- ⏳ 重构 graph.py
- ⏳ 更新 API 路由
- ⏳ 清理旧代码

---

## 9. 参考资源

- LangChain AgentExecutor 文档: https://python.langchain.com/docs/modules/agents/
- LangGraph 文档: https://langchain-ai.github.io/langgraph/
- ReAct 论文: https://arxiv.org/abs/2210.03629
