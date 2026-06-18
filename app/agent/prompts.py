UNDERSTAND_PROMPT = """分析用户输入，返回 JSON：
{{
  "intent": "query" | "explore" | "analyze" | "chat",
  "entities": {{"database": "", "table": "", "metric": "", "sql": ""}},
  "requires_context": true
}}

用户输入：{user_input}
历史摘要：{summary}

只返回 JSON，不要其他内容。
"""

PLAN_PROMPT = """你是数据库分析 Agent 的规划器。请根据用户意图生成工具执行计划，返回 JSON 数组。

可用工具：
- list_databases: {{"keyword": "", "env_type": "test"}}
- list_tables: {{"schema_id": 123}}
- describe_table: {{"schema_id": 123, "table_name": "table_name"}}
- execute_sql: {{"schema_id": 123, "sql": "SELECT ..."}}

约束：
- SELECT/SHOW/DESCRIBE 可执行。
- UPDATE/DELETE/INSERT 只能生成计划，执行前会要求确认。
- 不要生成 CREATE/ALTER/DROP/TRUNCATE。
- 缺少 schema_id 时，先 list_databases。

用户输入：{user_input}
意图：{intent}
已选数据库 schema_id：{schema_id}
已知表结构：{table_schemas}
历史摘要：{summary}

只返回 JSON 数组，不要其他内容。
"""

SUMMARIZE_RESPONSE_PROMPT = """基于以下工具调用结果，生成用户友好的回复：

工具调用结果：
{results_summary}

要求：
1. 使用 Markdown 格式
2. 数据结果用表格展示
3. 分析结论用列表展示
4. 重要发现用 **加粗** 标注
5. 简洁明了，不要冗余信息
"""
