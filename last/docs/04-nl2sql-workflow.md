# NL2SQL 工作流设计

本文档定义 DBAgent 从“LLM 直接生成工具计划”升级到“基于真实库表结构生成 SQL”的 NL2SQL 工作流。目标是让 Agent 面对不同开发人员、不同表、不同字段、不同自然语言查询时，不再依赖代码里硬编码字段规则。

## 1. 背景问题

当前实现中，`plan_node` 主要让 LLM 直接生成工具调用计划，例如：

```json
[
  {"tool": "list_databases", "args": {"keyword": "dw-onedba-t1"}},
  {"tool": "execute_sql", "args": {"schema_id": 65938636, "sql": "SELECT ..."}}
]
```

这个方式有几个问题：

| 问题 | 表现 | 影响 |
|---|---|---|
| LLM 工具参数不稳定 | 同一句话可能一次缺 `sql`，一次缺 `table_name` | 用户得到不同错误 |
| 缺少 schema 约束 | LLM 在不知道真实字段时猜 SQL | 字段名错误、表名错误 |
| 局部规则不可扩展 | 为 `id/nodeid` 写硬编码 | 新字段又要改代码 |
| 失败修复弱 | SQL 报错后直接返回用户 | 用户需要自己定位问题 |

NL2SQL 工作流的核心原则是：

```text
只要是查询数据的问题，必须先定位 schema_id 和真实 table_schema，再允许生成 SQL。
```

## 2. 目标

### 2.1 V1 目标

V1 先支持单库、单表、只读查询：

1. 从自然语言中解析数据库/实例关键词。
2. 通过 OneDBA 定位唯一 `schema_id`。
3. 从自然语言中解析候选表名。
4. 获取真实表结构：`DESCRIBE table`。
5. 基于真实字段列表生成只读 SQL。
6. 校验 SQL 安全性和字段/表引用。
7. 执行 SQL。
8. 如果 SQL 失败，基于错误信息和表结构自动修复一次。
9. 返回 SQL、结果和简洁分析。

### 2.2 非目标

V1 暂不处理：

| 暂不支持 | 说明 |
|---|---|
| 多表 Join 自动发现 | 需要关系推断、外键/业务语义，不在第一阶段 |
| 跨库查询 | OneDBA schema 权限和 SQL 方言差异需要单独设计 |
| 写操作自动生成 | INSERT/UPDATE/DELETE 仍需确认，且不作为 NL2SQL 主路径 |
| 可视化图表 | 先返回 Markdown 表格和文字分析 |
| 长链路复杂报表 | 先保证单查询稳定，复杂分析后续拆多步 |

## 3. 工作流总览

V1 推荐工作流：

```text
Understand
  ↓
Resolve Database
  ↓
Resolve Table
  ↓
Load Table Schema
  ↓
Generate SQL
  ↓
Validate SQL
  ↓
Execute SQL
  ↓
Repair SQL? 失败时最多一次
  ↓
Summarize
```

和当前通用 Agent 图的关系：

- 仍然可以保留 LangGraph。
- 但 NL2SQL 查询不要再让 LLM 直接任意生成工具计划。
- `plan_node` 应识别到 `intent=query/analyze` 后进入专用 NL2SQL 子流程。
- 探索类问题仍可使用原工具计划，例如“有哪些库”“有哪些表”“表结构是什么”。

## 4. 状态扩展

建议扩展 `AgentState`：

```python
class AgentState(TypedDict, total=False):
    # 已有字段省略

    nl2sql: Optional[dict]
    candidate_databases: list[dict]
    candidate_tables: list[str]
    resolved_table: Optional[str]
    table_schema: list[dict]
    generated_sql: Optional[str]
    validated_sql: Optional[str]
    sql_validation_errors: list[str]
    sql_execution_error: Optional[str]
    sql_repair_attempts: int
```

`nl2sql` 可保存结构化任务：

```json
{
  "is_query": true,
  "database_keyword": "dw-onedba-t1",
  "table_hint": "approval template node",
  "metric_or_field_hint": "nodeid",
  "operation": "most_frequent",
  "time_range": null,
  "limit": 100,
  "needs_clarification": false,
  "clarification_question": ""
}
```

## 5. 节点设计

### 5.1 Understand

职责：

- 判断是否进入 NL2SQL。
- 提取查询意图，而不是直接生成 SQL。
- 提取数据库关键词、表名提示、字段/指标提示、过滤条件、排序/聚合要求。

输出示例：

```json
{
  "intent": "query",
  "database_keyword": "dw-onedba-t1",
  "table_hint": "approval template node",
  "field_hints": ["nodeid"],
  "operation": "most_frequent",
  "filters": [],
  "time_range": null,
  "limit": 100
}
```

要求：

- 不在该节点生成 SQL。
- 不调用 OneDBA。
- 解析失败时进入澄清，不要猜危险 SQL。

### 5.2 Resolve Database

职责：

- 使用 `list_databases(keyword=database_keyword)` 查询候选库。
- 如果唯一命中，设置 `selected_schema_id` 和 `selected_database`。
- 如果多个命中，按明确规则选择或向用户澄清。

建议匹配优先级：

1. `instanceName` 完全等于用户关键词。
2. `schemaName` 完全等于用户关键词。
3. `searchName` 包含用户关键词。
4. 其他模糊包含。

如果多个候选同分：

- 返回候选列表，让用户选择。
- 不要默认选第一个，除非用户上下文中已有选中库。

已确认决策：

```text
命中多个 test 实例时，必须让用户选择，默认选择有误查风险。
```

### 5.3 Resolve Table

职责：

- 将用户表名提示规范化，例如 `approval template node` -> `approval_template_node`。
- 必要时执行 `SHOW TABLES` 获取表列表。
- 在表列表中做精确/模糊匹配。

匹配策略：

| 用户输入 | 规范化 | 匹配 |
|---|---|---|
| `approval template node` | `approval_template_node` | 精确匹配 |
| `approval-template-node` | `approval_template_node` | 精确匹配 |
| `approvalTemplateNode` | `approval_template_node` | 可选，后续支持 |

如果找不到表：

- 返回最接近的候选表。
- 要求用户确认，不生成 SQL。

### 5.4 Load Table Schema

职责：

- 执行 `DESCRIBE resolved_table`。
- 解析字段列表并保存到 `table_schema`。
- 缓存到 `table_schemas[table_name]`。

字段结构建议：

```json
[
  {
    "name": "nodeid",
    "type": "bigint(20)",
    "nullable": true,
    "key": "",
    "default": null,
    "extra": ""
  }
]
```

强约束：

```text
Generate SQL 前必须有 table_schema。
```

### 5.5 Generate SQL

职责：

- 基于用户问题、真实表结构、数据库方言生成 SQL。
- 只生成 SELECT/SHOW/DESCRIBE。
- 默认给查询加 `LIMIT`，聚合查询除外或按需要加。

Prompt 契约：

```text
你是 SQL 生成器。
只基于给定 table_schema 生成 SQL。
不得使用 table_schema 中不存在的字段。
不得发明表名。
只返回 JSON。

输入：
- 用户问题
- schema_id
- table_name
- table_schema
- 历史摘要

输出：
{
  "sql": "...",
  "explanation": "...",
  "used_columns": ["..."],
  "assumptions": ["..."],
  "needs_clarification": false,
  "clarification_question": ""
}
```

示例：

用户：

```text
帮我查查 dw-onedba-t1 数据库中 approval template node 表中出现最多的 nodeid 是什么
```

表结构包含 `nodeid` 时：

```sql
SELECT nodeid, COUNT(*) AS cnt
FROM approval_template_node
GROUP BY nodeid
ORDER BY cnt DESC
LIMIT 1
```

如果表结构不包含 `nodeid`：

```json
{
  "needs_clarification": true,
  "clarification_question": "approval_template_node 表中没有 nodeid 字段。你是否想查询 id 或 node_id？"
}
```

### 5.6 Validate SQL

职责：

- 在执行前校验 SQL。

校验规则：

| 规则 | 处理 |
|---|---|
| 只允许单条 SQL | 多语句拒绝 |
| 只允许 SELECT/SHOW/DESCRIBE | 写操作走确认，DDL 拒绝 |
| 表名必须等于 resolved_table 或允许白名单 | 不匹配则拒绝 |
| 字段必须存在于 table_schema | 不存在则澄清或修复 |
| 非聚合 SELECT 必须有 LIMIT | 自动追加或要求重写 |
| 禁止注释拼接和危险关键字 | 拒绝 |

建议实现位置：

```text
app/nl2sql/validator.py
```

LIMIT 决策：

- 普通只读查询默认追加 `LIMIT 100`，并在回答中说明。
- 聚合查询默认追加 `LIMIT 20`，并在回答中说明。
- 用户问“最多的一个”“第一名”“最高的一条”等单个结果时，使用 `LIMIT 1`，并在回答中说明。

### 5.7 Execute SQL

职责：

- 调用现有 `execute_sql` 工具。
- 保存原始结果和 Markdown 结果。

注意：

- 当前 OneDBA 返回会包含 `_idx_` 序号列。展示层可选择保留或过滤。
- 结果为空不是错误，应明确告诉用户“查询成功但无数据”。

### 5.8 Repair SQL

职责：

- SQL 执行失败时，最多自动修复 4 次。

输入：

- 用户问题
- 原 SQL
- OneDBA 错误信息
- table_schema

输出：

```json
{
  "sql": "...",
  "reason": "...",
  "can_retry": true
}
```

限制：

- V1 最多修复 4 次，避免无限循环。
- 修复后仍必须经过 `Validate SQL`。
- 不能把只读 SQL 修成写 SQL。
- 如果错误是权限不足，不重试，直接说明权限问题。

### 5.9 Summarize

职责：

- 返回用户真正关心的结果。
- 展示 SQL。
- 展示结果表格。
- 对空结果、权限不足、字段不存在做明确解释。

输出结构建议：

```text
### 查询结论
...

### 执行 SQL
```sql
...
```

### 查询结果
| ... |

### 说明
- ...
```

## 6. 模块划分

建议新增目录：

```text
app/nl2sql/
├── __init__.py
├── intent.py          # NL2SQL 意图结构和解析
├── resolver.py        # 数据库和表解析
├── schema.py          # DESCRIBE 结果解析和缓存
├── generator.py       # 基于 schema 生成 SQL
├── validator.py       # SQL 校验
├── repair.py          # SQL 修复
└── prompts.py         # NL2SQL prompts
```

当前 `app/agent/nodes.py` 应逐步瘦身，只负责节点编排，不承载大量规则。

## 7. 测试计划

### 7.1 单元测试

| 模块 | 测试点 |
|---|---|
| `intent.py` | 提取 database/table/field/operation |
| `resolver.py` | 表名规范化、候选表匹配、候选库选择 |
| `schema.py` | DESCRIBE Markdown/OneDBA raw 结果解析 |
| `generator.py` | mock LLM 输出解析、缺字段澄清 |
| `validator.py` | DDL 拦截、多语句拦截、字段校验、LIMIT 校验 |
| `repair.py` | Unknown column 修复、权限错误不重试 |

### 7.2 集成测试

使用 mock OneDBA + mock LLM 覆盖：

1. 单库单表聚合查询成功。
2. 字段不存在，返回澄清问题。
3. 表不存在，返回候选表。
4. LLM 生成 SQL 使用不存在字段，被 validator 拦截。
5. SQL 第一次执行失败，repair 后成功。
6. 权限不足，不重试，直接说明。

### 7.3 真实 Smoke Test

真实环境手动验证：

```text
帮我查查 dw-onedba-t1 数据库中 approval template node 表中出现最多的 nodeid 是什么
```

预期链路：

```text
list_databases -> list_tables/resolve_table -> describe_table -> generate_sql -> validate_sql -> execute_sql -> summarize
```

## 8. 分阶段实现

### Phase A：基础 NL2SQL 路径

- 新增 `app/nl2sql/` 模块。
- 实现 database/table/schema 解析。
- 实现基于 schema 的 SQL 生成。
- 实现 SQL validator。
- 接入 Agent 节点。

成功标准：

```text
同一句自然语言连续请求多次，工具链稳定，不出现缺 sql/table_name 的工具调用。
```

### Phase B：SQL 修复

- 捕获 OneDBA SQL 错误。
- 实现 `repair_sql`。
- 最多自动重试一次。

成功标准：

```text
Unknown column / 表名格式错误等可修复问题能自动修正一次。
```

### Phase C：多轮上下文

- 用户第一次选择数据库后，后续查询复用 `selected_schema_id`。
- 表结构缓存到 `table_schemas`。
- 摘要记忆保存已选库、常用表和关键字段。

成功标准：

```text
用户无需每次重复数据库名，也能继续查询同一库。
```

## 9. 已确认决策与待确认项

以下决策来自产品/使用方确认，后续实现应按此执行。

1. 多个数据库候选时，是否允许 Agent 默认选择最匹配的实例？
   - 已确认：命中多个 test 实例时，必须让用户选择，默认选择有误查风险。

2. 只读查询是否必须自动追加 `LIMIT`？
   - 已确认：普通只读查询默认 `LIMIT 100`，并向用户说明。

3. 聚合查询是否需要 `LIMIT`？
   - 已确认：聚合查询默认 `LIMIT 20`；用户问“最多的一个”时加 `LIMIT 1`，并向用户说明。

4. 用户提到字段但表结构中不存在时，是否允许 LLM 选择相似字段？
   - 已确认：可以自动选择高置信相似字段，但必须在回答中说明假设。

5. 是否允许跨表 Join？
   - 已确认：无明确 Join 条件时：
     - 有外键/元数据：可自动 Join。
     - 有唯一高置信命名匹配且样本验证通过：可自动 Join，但回答中说明假设。
     - 多个候选或低置信：必须向用户澄清。
   - V1 仍以单表查询为主，Join 作为后续增强。

6. SQL 方言按什么处理？
   - 已确认：暂时只支持 MySQL/RDS。

7. 是否需要记录和展示生成 SQL 的解释？
   - 已确认：展示 SQL 和简短解释，便于开发人员校验。

8. 权限字段如何解释？
   - 待确认：真实联调中出现 `ownerPriv=true` 但 `selectPriv=false` 仍能执行 SELECT。实现时不得基于这些字段推断“无查询权限”，避免误导用户。

9. 表结构缓存多久？
   - 已确认：按 session TTL 保存。

10. 失败重试次数是否固定为 1？
    - 已确认：V1 固定最多 4 次，避免无限循环。

## 10. 当前结论

NL2SQL 应作为 DBAgent 的核心查询路径，而不是在通用 plan/act 中继续堆字段规则。

第一阶段实现时应坚持三条硬约束：

1. 查询数据前必须解析到 `schema_id`。
2. 生成 SQL 前必须获取真实 `table_schema`。
3. 执行 SQL 前必须通过 validator。

这三条约束解决的是稳定性问题：同一句话不应该两次生成不同的缺参工具调用，也不应该因为新字段出现就修改代码。

## 11. 当前实现状态

已完成 V1 基础路径：

- 新增 `app/nl2sql/` 模块。
- 支持 NL2SQL 意图解析：数据库关键词、表名提示、字段提示、操作类型、默认 LIMIT。
- 支持 Top-N 数量解析：例如“最多的两个”生成 `LIMIT 2`，“最多的一个”生成 `LIMIT 1`。
- 支持表名前缀多表计数：例如“approval 各个表分别有多少条数据”会匹配 `approval*` 表并生成 `UNION ALL` 统计 SQL。
- 支持上下文数据库复用：用户未显式提供数据库时，优先使用当前会话已选库或摘要中的实例名。
- 支持最近 N 天次数排行：例如“最近 30 天不同 metric_name 的告警次数排行”会按时间字段过滤并分组统计。
- 支持待澄清查询续接：多库候选时保存原始 NL2SQL 查询，用户下一句指定实例后继续原查询。
- 支持字段数量查询：例如“alert history 表中有多少个字段”会解析表结构并返回字段数量。
- 支持数据库候选解析：唯一高置信命中自动选择，多候选返回澄清。
- 支持表名规范化和候选表匹配。
- 支持 OneDBA `DESCRIBE` 原始结果解析为 `table_schema`。
- 支持基于真实表结构调用 LLM 生成 SQL。
- 支持 SQL validator：只读 SQL、单表约束、字段存在性、默认 LIMIT、别名识别。
- 支持 SQL repair 框架，最多 4 次。
- Agent 查询类请求已接入 `nl2sql_query` 合成工具，避免 LLM 直接生成缺参工具调用。
- `nl2sql_query` 会返回结构化元数据：内部子步骤、生成 SQL、假设与限制、选中的数据库。
- session 会保存 NL2SQL 解析出的 `selected_schema_id` 和脱敏后的 `selected_database`，后续问题可复用数据库上下文。
- 支持显式选库命令：例如 `使用 dw-onedba-t1` 或 `选择 dw-onedba-t1 数据库`。
- 前端已展示 NL2SQL 子步骤、SQL 和假设说明。

已通过真实 smoke test：

```text
帮我查查dw-onedba-t1数据库中approval template node表中出现最多的nodeid是什么
```

实际链路：

```text
list_databases -> SHOW TABLES -> DESCRIBE approval_template_node -> generate_sql -> validate_sql -> execute_sql -> summarize
```

实际 SQL：

```sql
SELECT node_id, COUNT(*) AS cnt
FROM approval_template_node
GROUP BY node_id
ORDER BY cnt DESC
LIMIT 1
```

当前结果：

```text
node_id = 1001
cnt = 12
```

已通过 Top-N smoke test：

```text
帮我查查dw-onedba-t1数据库中approval template node表中出现最多的两个nodeid是什么
```

实际 SQL：

```sql
SELECT node_id, COUNT(*) AS freq
FROM approval_template_node
GROUP BY node_id
ORDER BY freq DESC
LIMIT 2
```

当前结果：

```text
node_id = 1001, freq = 12
node_id = 1002, freq = 11
```

已通过表名前缀多表计数 smoke test：

```text
帮我查查dw-onedba-t1数据库中approval 各个表中分别有多少条数据
```

实际 SQL：

```sql
SELECT 'approval_node' AS table_name, COUNT(*) AS total FROM `approval_node`
UNION ALL
SELECT 'approval_template' AS table_name, COUNT(*) AS total FROM `approval_template`
UNION ALL
SELECT 'approval_template_node' AS table_name, COUNT(*) AS total FROM `approval_template_node`
ORDER BY total DESC
```

当前结果：

```text
approval_template_node = 57
approval_template = 23
approval_node = 15
```

已通过最近 N 天指标排行 smoke test：

```text
帮我分析 dw-onedba-t1 数据库中 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行
```

实际 SQL：

```sql
SELECT metric_name, COUNT(*) AS cnt
FROM db_alert_history
WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY metric_name
ORDER BY cnt DESC
LIMIT 20
```

当前结果：

```text
共 0 行
```

同一会话下省略数据库名时，也可从摘要中复用 `dw-onedba-t1`。

已通过澄清续接 smoke test：

```text
用户：dw onedba t1数据库 找找alert history表中有多少个字段
Agent：找到多个匹配数据库，请选择一个
用户：在onedba-t1实例上找
Agent：继续原始查询，返回 db_alert_history 表字段数量
```

当前结果：

```text
db_alert_history 字段数 = 18
```

下一步建议：

1. 将 `nl2sql_query` 内部子步骤暴露为前端可见事件，而不是只显示一个合成工具。
2. 增加 session TTL 表结构缓存。
3. 补充字段相似匹配的显式置信度和说明。
4. 增加 mock LLM 的端到端测试，覆盖 SQL 修复路径。
