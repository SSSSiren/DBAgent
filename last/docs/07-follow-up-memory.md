# 追问能力与上下文记忆设计（V1 最小闭环已实现）

本文档定义 DBAgent 的多轮追问能力。目标是让用户在完成一次 NL2SQL 查询后，可以继续用“把 SQL 给我”“只看前 5 个”“改成最近 7 天”等自然语言修改或延展上一轮查询，而不是每次都重新描述数据库、表、字段和完整分析目标。

当前实现已经完成 V1 最小闭环：

- 保存上一轮 NL2SQL 查询的结构化任务 `last_nl2sql_task`。
- 保存上一轮最终 SQL：`last_generated_sql` / `last_validated_sql`。
- 保存上一轮结果摘要：`last_result_preview` / `last_result_summary`。
- 识别并执行三类追问：`show_sql`、`change_limit`、`change_time_range`。
- 追问 SQL 基于结构化 task 重新生成，再经过 validator 校验并执行。
- API 和 UI 暴露最新 SQL，前端左侧“最新 SQL”文本框可复制。

## 1. 背景问题

系统原有基础上下文包括：

- `selected_schema_id`：当前会话选中的数据库 schema。
- `selected_database`：当前会话选中的数据库信息。
- `pending_nl2sql`：多库候选时保存未完成的原始查询，用户选择库后继续执行。
- `summary`：LLM 压缩后的自然语言摘要。

这些能力可以解决“选库续接”，但不能可靠解决复杂追问：

| 场景 | 原风险 | 当前状态 |
|---|---|---|
| 用户说“把 SQL 给我” | Agent 可能重新生成 SQL | 已实现，直接返回上一轮最终 SQL |
| 用户说“只看前 5 个” | 可能丢失原分组、排序、时间范围 | 已实现，patch `last_nl2sql_task.limit` 后重跑 |
| 用户说“改成最近 7 天” | 不知道上一轮时间字段 | 已实现，复用 `time_field`；缺失时澄清 |
| 用户说“只看 critical” | 需要字段和值解析 | 未实现，后续扩展 |
| 用户说“按 namespace 再分组” | 需要字段解析和 group by patch | 未实现，后续扩展 |
| 用户说“查第一名明细” | 需要复用上一轮结果第一行维度值 | 未实现，已有 `last_result_summary` 基础 |

核心原则：

```text
追问不依赖摘要记忆猜测，而依赖结构化的 last_nl2sql_task。
短期执行状态和长期领域记忆分层管理，避免偏好记忆静默覆盖本轮查询意图。
```

## 2. 当前实现范围

### 2.1 已实现

| 能力 | 入口/字段 | 说明 |
|---|---|---|
| 结构化任务保存 | `last_nl2sql_task` | 成功 NL2SQL 后保存库、表、字段、where、group、order、limit、schema、sql |
| 最终 SQL 保存 | `last_generated_sql` / `last_validated_sql` | `last_validated_sql` 优先作为最新 SQL |
| 结果摘要保存 | `last_result_summary` | 从 OneDBA `columnNames` / `columnDatas` 提取 `row_count`、`columns`、`top_rows`、`empty` |
| 追问分类 | `classify_followup` | 识别 `show_sql`、`change_limit`、`change_time_range` |
| 追问执行 | `run_followup_query` | 应用 patch、生成 SQL、校验、执行、刷新记忆 |
| 会话持久化 | `SESSION_STORE` | 保存和恢复追问记忆字段 |
| 最新 SQL API | `latest_sql` | `/api/chat` final 事件和 `/api/sessions/{session_id}` 均返回 |
| 最新 SQL UI | `app/static/*` | 左侧“最新 SQL”文本框展示，可复制 |

### 2.2 暂未实现

| 能力 | 原因 |
|---|---|
| `add_filter` / `replace_filter` | 需要字段 hint、值类型、枚举值来源和冲突规则 |
| `add_group_by` / `change_group_by` | 需要字段解析和 SQL builder 扩展 |
| `drill_down` | 需要从 `last_result_summary.top_rows` 选择维度值并生成明细查询 |
| `undo_last_patch` | 需要任务版本栈 |
| 长期领域记忆 | 需要存储、作用域、查看/删除和优先级策略 |
| 多任务上下文 | 需要 active task 和任务栈 |

## 3. 当前工作流

```text
User Input
  ↓
build_initial_state 从 SESSION_STORE 恢复上下文
  ↓
plan_node
  ├── pending_nl2sql + 选库追问 -> nl2sql_query
  ├── select_database -> select_database
  ├── classify_followup 命中 -> followup_query
  └── 普通查询 -> nl2sql_query / 原通用工具计划
```

`followup_query` 当前链路：

```text
followup patch
  ↓
_apply_followup_patch(last_nl2sql_task)
  ↓
_build_sql_from_task
  ↓
validate_sql
  ↓
onedba_client.execute_sql
  ↓
保存新的 last_nl2sql_task / last_validated_sql / last_result_summary
```

关键约束：

- `show_sql` 不重新执行查询。
- `change_limit` 和 `change_time_range` 必须基于 `last_nl2sql_task` 生成 SQL。
- 不直接字符串替换原 SQL。
- 最终 SQL 必须经过 `validate_sql`。
- `change_time_range` 没有 `time_field` 时返回澄清，不盲猜字段。

## 4. 状态设计

### 4.1 AgentState 字段

当前 `AgentState` 已扩展：

```python
class AgentState(TypedDict, total=False):
    # 已有字段省略

    pending_nl2sql: Optional[dict[str, Any]]
    pending_semantic_confirmation: Optional[dict[str, Any]]
    last_nl2sql_task: Optional[dict[str, Any]]
    nl2sql_task_stack: Optional[dict[str, Any]]
    last_generated_sql: Optional[str]
    last_validated_sql: Optional[str]
    last_result_preview: list[dict[str, Any]]
    last_result_summary: Optional[dict[str, Any]]
    last_query_topic: Optional[str]
    followup_patch: Optional[dict[str, Any]]
    long_term_memory_hints: list[dict[str, Any]]
```

其中 V1 最小闭环实际使用：

- `last_nl2sql_task`
- `last_generated_sql`
- `last_validated_sql`
- `last_result_preview`
- `last_result_summary`
- `followup_patch`

`nl2sql_task_stack`、`last_query_topic`、`long_term_memory_hints` 已预留，尚未接入完整行为。

### 4.2 last_nl2sql_task

当前 task 示例：

```json
{
  "task_id": "uuid",
  "created_at": "2026-06-23T10:00:00+00:00",
  "updated_at": "2026-06-23T10:01:00+00:00",
  "user_question": "帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行",
  "database": {
    "schema_id": 65938636,
    "schema_name": "dw_onedba",
    "instance_name": "dw-onedba-t1",
    "env": "test"
  },
  "table": {
    "name": "db_alert_history",
    "hint": "db_alert_history"
  },
  "operation": "ranking_count",
  "select_fields": [
    {"name": "metric_name", "role": "dimension"},
    {"name": "cnt", "role": "metric", "expression": "COUNT(*)"}
  ],
  "where": [
    {
      "field": "alert_time",
      "operator": ">=",
      "value_type": "relative_days",
      "value": 30
    }
  ],
  "filters": [],
  "group_by": ["metric_name"],
  "order_by": [
    {"field": "cnt", "direction": "DESC"}
  ],
  "limit": 20,
  "time_field": "alert_time",
  "table_schema": [
    {"name": "metric_name", "type": "varchar(128)"},
    {"name": "alert_time", "type": "datetime"}
  ],
  "sql": "SELECT metric_name, COUNT(*) AS cnt FROM `db_alert_history` WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 30 DAY) GROUP BY metric_name ORDER BY cnt DESC LIMIT 20",
  "assumptions": [
    "最近 30 天使用字段 alert_time 过滤。"
  ]
}
```

### 4.3 last_result_summary

当前结果摘要结构：

```json
{
  "row_count": 20,
  "columns": ["metric_name", "cnt"],
  "top_rows": [
    {"metric_name": "cpu_usage", "cnt": 128},
    {"metric_name": "disk_usage", "cnt": 95}
  ],
  "empty": false
}
```

保存规则：

- 只保存前 20 行预览。
- 不保存大结果集全文。
- 当前只保存在进程内 session 中。
- 后续接入持久化时需要重新确认敏感字段策略。

## 5. 追问分类

### 5.1 当前分类结果

`classify_followup(user_input, state)` 返回：

```json
{
  "is_followup": true,
  "type": "change_time_range",
  "confidence": 0.88,
  "patch": {
    "op": "replace_time_range",
    "time_range": {"type": "relative_days", "value": 7}
  },
  "needs_clarification": false,
  "clarification_question": ""
}
```

### 5.2 已支持追问

| 类型 | 示例 | Patch | 行为 |
|---|---|---|---|
| `show_sql` | “把 SQL 给我” | `{"op": "show_sql"}` | 返回 `last_validated_sql` 或 `last_generated_sql` |
| `change_limit` | “只看前 5 个” | `{"op": "replace_limit", "limit": 5}` | 修改 task `limit`，重建 SQL 并执行 |
| `change_time_range` | “改成最近 7 天” | `{"op": "replace_time_range", "time_range": {"type": "relative_days", "value": 7}}` | 修改相对时间 where，重建 SQL 并执行 |
| `continue_pending` | “在 onedba-t1 实例上找” | 内置选库续接 | 使用 `pending_nl2sql` 原始问题和新库继续执行 |

### 5.3 当前不作为追问处理

以下情况仍进入正常 NL2SQL 或返回澄清：

- 没有上一轮 SQL 或 `last_nl2sql_task` 时说“把 SQL 给我”。
- 用户明确指定新数据库、新表并提出完整新问题。
- “只看 critical”“按 namespace 再分组”“查第一名明细”等未实现类型。
- `change_time_range` 但上一轮任务没有 `time_field`。

## 6. Patch 规则

### 6.1 show_sql

用户：

```text
把 SQL 给我
```

Patch：

```json
{"op": "show_sql"}
```

行为：

- 直接返回上一轮 `last_validated_sql`。
- 如果没有 validated SQL，则返回 `last_generated_sql`。
- 不重新执行 SQL。
- API final payload 的 `latest_sql` 保持为该 SQL。

### 6.2 change_limit

用户：

```text
只看前 5 个
```

Patch：

```json
{
  "op": "replace_limit",
  "limit": 5
}
```

行为：

- 深拷贝 `last_nl2sql_task`。
- 修改 `task.limit`。
- 通过 `_build_sql_from_task` 重建 SQL。
- 通过 `validate_sql` 校验。
- 执行 SQL。
- 更新 `last_nl2sql_task`、`last_validated_sql`、`last_result_summary`。

### 6.3 change_time_range

用户：

```text
改成最近 7 天
```

Patch：

```json
{
  "op": "replace_time_range",
  "time_range": {"type": "relative_days", "value": 7}
}
```

行为：

- 要求上一轮 task 存在 `time_field`。
- 移除同一 `time_field` 上已有的 `relative_days` 条件。
- 追加新的相对时间条件。
- 重建 SQL、校验、执行并刷新 task。

生成 SQL 示例：

```sql
SELECT metric_name, COUNT(*) AS cnt
FROM `db_alert_history`
WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY metric_name
ORDER BY cnt DESC
LIMIT 5
```

## 7. SQL 生成策略

当前 V1 最小闭环使用规则生成：

```text
last_nl2sql_task -> _apply_followup_patch -> _build_sql_from_task -> validate_sql -> execute_sql
```

已支持 SQL 结构：

- `SELECT` 字段来自 `select_fields`。
- metric 表达式支持 `expression AS name`，例如 `COUNT(*) AS cnt`。
- `WHERE` 支持 `relative_days` 和简单值条件的渲染。
- `GROUP BY` 来自 `group_by`。
- `ORDER BY` 来自 `order_by`。
- `LIMIT` 来自 `limit`。

当前限制：

- 不支持 join。
- 不支持 HAVING。
- 不支持复杂表达式 patch。
- 不支持自动字段相似匹配 patch。
- 不支持任意 SQL AST 反解析。

后续如果扩展复杂追问，应优先把结构扩展到 task，而不是直接编辑 SQL 字符串。

## 8. API 与前端展示

### 8.1 API

`/api/chat` SSE final 事件当前返回：

```json
{
  "type": "final",
  "session_id": "session-id",
  "reply": "Markdown 回复",
  "tool_calls": [],
  "needs_confirmation": false,
  "latest_sql": "SELECT ..."
}
```

`latest_sql` 来自：

```text
last_validated_sql > last_generated_sql > ""
```

`/api/sessions/{session_id}` 当前也返回 `latest_sql`，用于页面刷新或切换 session 后恢复 UI 中的 SQL 文本框。

### 8.2 Tool Call 元数据

只要工具结果包含 `sql` 字段，`_tool_call_to_dict` 会暴露：

```json
{
  "tool": "followup_query",
  "status": "completed",
  "nl2sql": {
    "steps": [],
    "sql": "SELECT ...",
    "table_name": "db_alert_history",
    "assumptions": [],
    "selected_schema_id": 65938636,
    "selected_database": {}
  }
}
```

这同时覆盖 `nl2sql_query` 和 `followup_query`。

### 8.3 前端

当前 UI 行为：

- 左侧栏新增“最新 SQL”只读文本框。
- final 事件优先读取 `finalPayload.latest_sql`。
- 如果没有 `latest_sql`，再回退读取 `tool_calls[].nl2sql.sql`。
- 如果还没有，则尝试从回复 Markdown 的 SQL 代码块中提取。
- `/api/sessions/{session_id}` 返回 `latest_sql` 时会回填文本框。
- “复制 SQL”按钮在有 SQL 时启用。

## 9. 澄清策略

当前已实现澄清：

| 情况 | 回复 |
|---|---|
| 时间追问但上一轮没有 `time_field` | “上一轮查询没有明确时间字段，请先说明要用哪个时间字段。” |
| 追问需要 task 但没有 `last_nl2sql_task` | “上一轮没有可追问的 NL2SQL 任务。” |
| 追问 task 信息不完整 | “上一轮任务信息不完整，无法应用追问。” |
| 追问 task 缺少 `schema_id` | “上一轮任务缺少 schema_id，无法执行追问。” |

后续需要补充：

- 多个字段候选时澄清。
- 结果为空时 drill down 澄清。
- 切库导致上下文不兼容时澄清。
- 过滤值缺少可靠来源时澄清。

## 10. 测试计划与当前覆盖

### 10.1 自动化测试

当前已有测试覆盖：

| 测试 | 覆盖点 |
|---|---|
| `test_followup_memory_fields_round_trip_through_session_store` | 追问记忆字段 session 保存和恢复 |
| `test_result_summary_uses_structured_onedba_result` | OneDBA 原始结果转 `last_result_summary` |
| `test_build_last_nl2sql_task_captures_patchable_query_shape` | 构造可 patch 的 task |
| `test_classify_followup_*` | `show_sql`、`change_limit`、`change_time_range` 分类 |
| `test_plan_node_routes_show_sql_followup` | 追问路由到 `followup_query` |
| `test_run_followup_query_show_sql_returns_last_sql` | 返回上一轮 SQL |
| `test_run_followup_query_change_limit_executes_patched_task` | 修改 LIMIT 并执行 |
| `test_run_followup_query_change_time_range_executes_patched_task` | 修改时间范围并执行 |
| `test_act_node_stores_nl2sql_followup_memory` | act_node 回写追问记忆 |
| `test_tool_call_to_dict_exposes_sql_for_followup_query` | followup SQL 暴露给前端 |
| `test_latest_sql_from_state_prefers_validated_sql` | API `latest_sql` 优先级 |
| `test_frontend_latest_sql_logic_exists` | UI 最新 SQL 文本框和复制逻辑 |

推荐命令：

```bash
/Users/admin/miniconda3/envs/DBR/bin/python -m pytest tests/test_agent.py tests/test_frontend.py
/Users/admin/miniconda3/envs/DBR/bin/python -m pytest
```

当前全量测试状态：

```text
95 passed
```

### 10.2 手动对话测试

使用同一个 `session_id` 连续输入：

```text
帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行
把 SQL 给我
只看前 5 个
改成最近 7 天
把 SQL 给我
```

检查点：

- 首轮查询成功后，左侧“最新 SQL”文本框出现 SQL。
- “把 SQL 给我”不重新执行查询，只返回上一轮 SQL。
- “只看前 5 个”后 SQL 保留原表、原分组、原排序、原时间条件，只修改 `LIMIT 5`。
- “改成最近 7 天”后 SQL 包含 `INTERVAL 7 DAY`，并保留当前 LIMIT。
- 再次“把 SQL 给我”返回最近 7 天版本的 SQL。
- 点击“复制 SQL”可以复制文本框内容。

无上下文测试：

```text
把 SQL 给我
```

期望：

- 新 session 下不应伪造 SQL。
- UI 最新 SQL 仍为空。

缺时间字段测试：

1. 先执行一个没有 `time_field` 的查询。
2. 再输入：

```text
改成最近 7 天
```

期望：

- 返回澄清，不盲猜时间字段。

## 11. 分阶段实现状态

### Phase F1：最近一次任务记忆

状态：已实现。

- 新增 `last_nl2sql_task` 状态。
- NL2SQL 查询成功后保存结构化任务。
- session load/save 支持追问字段。
- API 和 UI 可展示最新 SQL。

### Phase F2：确定性追问 patch

状态：部分实现。

已实现：

- `show_sql`
- `change_time_range`
- `change_limit`

未实现：

- `add_filter`
- `replace_filter`
- `add_group_by`
- `change_group_by`
- `change_order`

### Phase F3：结果驱动追问

状态：基础已具备，行为未实现。

已实现：

- 保存 `last_result_summary`。

未实现：

- `drill_down`
- “第一名”“第二名”“上一条结果”等指代解析。

### Phase F4：任务版本栈与撤回

状态：未实现。

目标：

- 将 `last_nl2sql_task` 升级为 `nl2sql_task_stack`。
- 每次成功执行后追加完整版本快照。
- 支持“撤回上一步”。
- 支持“撤回刚才那个条件”。

### Phase F5：长期领域记忆

状态：未实现。

目标：

- 支持用户显式写入 `field_alias`。
- 支持用户显式写入 `default_time_field`。
- 查询时将长期记忆作为字段解析候选。
- 支持查看和删除当前作用域记忆。

### Phase F6：多任务上下文

状态：未实现。

目标：

- 保存最近 N 个 NL2SQL 任务。
- 支持用户显式切换 active task。
- 支持“回到刚才那个告警排行”。

## 12. 后续设计建议

### 12.1 add_filter

目标示例：

```text
只看 level=critical
```

Patch：

```json
{
  "op": "add_filter",
  "filter": {
    "field_hint": "level",
    "operator": "=",
    "value": "critical"
  }
}
```

落地前提：

- 将 `field_hint` 解析到真实字段。
- 值来源必须可靠：用户明确输入、字段样例值或业务语义层。
- 同字段已有过滤时，应识别为 replace 还是 add。
- SQL 生成后仍走 validator。

### 12.2 add_group_by

目标示例：

```text
再按 namespace 细分
```

Patch：

```json
{
  "op": "add_group_by",
  "field_hint": "namespace"
}
```

落地前提：

- 字段必须存在于 `table_schema`。
- select_fields 要补充新维度字段。
- group_by 追加字段，order_by 保持稳定。

### 12.3 drill_down

目标示例：

```text
查第一名明细
```

前置条件：

- 上一轮是聚合查询。
- `last_result_summary.top_rows[0]` 存在。
- 第一行中至少有一个维度字段。

生成示例：

```sql
SELECT *
FROM db_alert_history
WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
  AND metric_name = 'cpu_usage'
LIMIT 100
```

### 12.4 任务版本栈

目标结构：

```json
{
  "active_task_id": "t1",
  "tasks": {
    "t1": {
      "topic": "alert metric rank",
      "current_version": 3,
      "versions": [
        {
          "version": 1,
          "user_input": "最近 30 天不同 metric_name 告警次数排行",
          "task": {},
          "sql": "SELECT ...",
          "patch": null,
          "created_at": "2026-06-23T10:00:00+08:00"
        }
      ]
    }
  }
}
```

撤回原则：

- 不物理删除旧版本。
- 撤回也生成新版本。
- 用户显式新条件优先于历史版本。

### 12.5 长期领域记忆

建议先落地两类：

| 类型 | 示例 |
|---|---|
| `field_alias` | “告警级别” -> `level` |
| `default_time_field` | `db_alert_history.default_time_field = alert_time` |

写入规则：

- 只有用户明确说“记住”“以后默认”“这个字段就是”时，才写入 `user_confirmed` 记忆。
- LLM 单次推断不得直接持久化。
- 长期记忆不能覆盖本轮用户显式输入。
- 记忆命中后最终 SQL 仍必须通过 validator。

## 13. 待确认问题

1. `last_result_summary` 是否允许保存真实查询结果的前 20 行？
   - 当前实现：允许在 session 内保存前 20 行，不落盘。

2. 用户显式切换数据库后，是否立即清空 `last_nl2sql_task`？
   - 当前实现：尚未清空。建议后续清空，避免跨库误用表和字段。

3. Drill down 明细默认返回多少行？
   - 建议默认 `LIMIT 100`，并在回答中说明。

4. 多轮追问是否需要展示每次继承和修改的上下文？
   - 建议展示简短说明，例如继承表、分组、排序，修改了时间或 limit。

5. 是否需要支持“撤回上一步修改”？
   - 建议需要。通过任务版本栈实现，撤回生成新版本。

6. 长期字段别名和默认时间字段是否需要 UI 管理能力？
   - 建议至少提供查看和删除能力，避免记忆过期后用户无法排查。

## 14. 当前结论

追问能力的关键不是增加更多自然语言规则，而是把每次 NL2SQL 查询保存成可 patch 的结构化任务。

当前 V1 最小闭环已经证明这条路径可行：

1. 成功查询后保存 `last_nl2sql_task`。
2. 追问先分类为明确 patch。
3. patch 后由结构化 task 重建 SQL。
4. SQL 经过 validator 后执行。
5. 执行成功后刷新 task、SQL 和结果摘要。

下一步优先建议实现：

1. `add_filter`：解决“只看 critical”。
2. `add_group_by`：解决“再按 namespace 细分”。
3. `drill_down`：基于已有 `last_result_summary` 支持“查第一名明细”。
4. 切库时清理旧 `last_nl2sql_task`，降低跨库误用风险。
