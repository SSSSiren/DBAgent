# 追问能力与上下文记忆设计

本文档定义 DBAgent 的多轮追问能力。目标是让用户在完成一次查询后，可以继续用“改成最近 7 天”“只看前 5 个”“按实例再分组”“查第一名明细”等自然语言修改或延展上一轮查询，而不是每次都重新描述数据库、表、字段和完整分析目标。

## 1. 背景问题

当前系统已经支持基础上下文：

- `selected_schema_id`：当前会话选中的数据库 schema。
- `selected_database`：当前会话选中的数据库信息。
- `pending_nl2sql`：多库候选时保存未完成的原始查询，用户选择库后继续执行。
- `summary`：LLM 压缩后的自然语言摘要。

这些能力可以解决“选库续接”，但还不足以解决复杂追问：

| 场景 | 当前风险 | 期望 |
|---|---|---|
| 用户说“改成最近 7 天” | Agent 不知道上一轮是哪张表、哪个时间字段、哪个分组 | 复用上一轮结构，仅修改时间范围 |
| 用户说“只看 critical” | Agent 可能重新解析成新问题，丢失原分组和排序 | 在上一轮 SQL 上追加过滤条件 |
| 用户说“查第一名明细” | Agent 不知道第一名是哪一行 | 复用上一轮结果中的第一行维度值 |
| 用户说“把 SQL 给我” | Agent 可能重新生成 SQL | 直接返回上一轮已执行 SQL |
| 用户说“按 namespace 再分组” | Agent 可能覆盖原有 group by | 在上一轮 group by 基础上追加维度 |

核心结论：

```text
追问不应该依赖摘要记忆猜测，而应该依赖结构化的 last_nl2sql_task。
```

## 2. 设计目标

### 2.1 V1 目标

1. 保存上一轮 NL2SQL 查询的结构化任务。
2. 识别用户输入是否为追问。
3. 将追问解析为结构化 patch，而不是重新完整理解。
4. 基于上一轮任务应用 patch，重新生成或改写 SQL。
5. 展示本次追问继承了哪些上下文、修改了哪些条件。
6. 对模糊追问返回澄清问题，而不是错误执行。

### 2.2 非目标

V1 暂不支持：

| 暂不支持 | 原因 |
|---|---|
| 长距离跨主题追问 | 需要主题栈和多任务记忆，先保证最近一次查询 |
| 自动理解所有业务别名 | 需要业务词典或元数据，先依赖字段相似匹配 |
| 任意 SQL 字符串语义重写 | 风险高，优先 patch 结构化任务再生成 SQL |
| 多表 Join 追问自动扩展 | 依赖 Join 关系推断，后续在 NL2SQL Join 能力中实现 |

## 3. 总体架构

推荐链路：

```text
User Input
  ↓
Classify Follow-up
  ├── not_follow_up ──> 正常 NL2SQL 工作流
  ├── show_sql ───────> 返回 last_validated_sql
  ├── continue_pending -> 继续 pending_nl2sql
  └── patch_query
        ↓
     Apply Patch To last_nl2sql_task
        ↓
     Resolve Missing Fields
        ↓
     Generate SQL From Task
        ↓
     Validate SQL
        ↓
     Execute SQL
        ↓
     Save New last_nl2sql_task
        ↓
     Summarize
```

关键原则：

```text
追问优先 patch 结构化任务，而不是直接字符串替换 SQL。
```

原因：

- SQL 字符串替换容易破坏语法，例如替换 `LIMIT`、`WHERE`、`GROUP BY` 的位置。
- 结构化任务能保留语义，例如“分组字段”“指标字段”“时间范围”“过滤条件”。
- Validator 仍能在最终执行前兜底。

## 4. 状态设计

### 4.1 AgentState 扩展

建议扩展 `AgentState`：

```python
class AgentState(TypedDict, total=False):
    # 已有字段省略

    last_nl2sql_task: Optional[dict]
    last_generated_sql: Optional[str]
    last_validated_sql: Optional[str]
    last_result_preview: list[dict]
    last_result_summary: Optional[dict]
    last_query_topic: Optional[str]
    followup_patch: Optional[dict]
```

### 4.2 last_nl2sql_task

`last_nl2sql_task` 是追问的核心记忆，建议结构如下：

```json
{
  "task_id": "uuid",
  "created_at": "2026-06-18T17:00:00+08:00",
  "updated_at": "2026-06-18T17:02:00+08:00",
  "user_question": "帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行",
  "database": {
    "schema_id": 65938636,
    "schema_name": "dw_onedba",
    "instance_name": "dw-onedba-t1",
    "env": "test"
  },
  "table": {
    "name": "db_alert_history",
    "hint": "alert history"
  },
  "operation": "group_count_rank",
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
  "sql": "SELECT metric_name, COUNT(*) AS cnt FROM db_alert_history WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 30 DAY) GROUP BY metric_name ORDER BY cnt DESC LIMIT 20",
  "assumptions": [
    "使用 alert_time 作为最近 30 天的时间字段"
  ]
}
```

### 4.3 last_result_summary

用于支持“查第一名明细”“刚才最高的是哪个”等结果追问：

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

- 只保存前 N 行预览，建议 N=20。
- 不保存大结果集全文。
- 不保存未脱敏的敏感字段值，除非业务确认允许。

## 5. 追问分类

### 5.1 分类结果

`classify_followup(user_input, state)` 返回：

```json
{
  "is_followup": true,
  "type": "change_time_range",
  "confidence": 0.92,
  "patch": {
    "time_range": {"type": "relative_days", "value": 7}
  },
  "needs_clarification": false,
  "clarification_question": ""
}
```

### 5.2 支持的追问类型

| 类型 | 示例 | 处理方式 |
|---|---|---|
| `continue_pending` | “在 onedba-t1 实例上找” | 使用 `pending_nl2sql` 原始问题和新库继续执行 |
| `change_time_range` | “改成最近 7 天” | 替换上一轮时间范围 |
| `add_filter` | “只看 level=critical” | 追加过滤条件 |
| `replace_filter` | “level 改成 warning” | 修改同字段过滤条件 |
| `change_limit` | “只看前 5 个” | 修改 `LIMIT` |
| `change_order` | “按次数升序” | 修改排序方向 |
| `add_group_by` | “再按 namespace 细分” | 在原 `group_by` 后追加字段 |
| `change_group_by` | “改成按 namespace 分组” | 替换原 `group_by` |
| `show_sql` | “把 SQL 给我” | 返回上一轮 SQL，不重新执行 |
| `explain_result` | “解释一下结果” | 基于上一轮结果摘要解释 |
| `drill_down` | “查第一名明细” | 用上一轮 top row 维度追加过滤，查询明细 |
| `change_table` | “换成 db_alert_current 表” | 保留可迁移意图，重新解析新表 schema |

### 5.3 不是追问的情况

以下情况应进入正常 NL2SQL，而不是追问：

- 用户明确指定了新数据库和新表，并提出完整新问题。
- 用户问题与上一轮查询主题无关。
- 上一轮没有 `last_nl2sql_task`。
- 追问类型需要上一轮结果，但 `last_result_summary` 为空。

## 6. Patch 规则

### 6.1 时间范围

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

生成 SQL：

```sql
WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
```

规则：

- 如果上一轮有 `time_field`，直接复用。
- 如果上一轮无时间字段，但当前表 schema 有唯一高置信时间字段，可自动使用并说明假设。
- 如果有多个候选时间字段，必须澄清。

### 6.2 过滤条件

用户：

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

规则：

- `field_hint` 必须解析到真实字段。
- 若字段不存在，可按字段相似匹配规则选择高置信字段，并在回答中说明。
- 若值需要加引号，由 SQL builder 根据字段类型处理。

### 6.3 分组字段

用户：

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

结果：

```sql
GROUP BY metric_name, namespace
```

用户：

```text
改成按 namespace 分组
```

Patch：

```json
{
  "op": "replace_group_by",
  "field_hints": ["namespace"]
}
```

结果：

```sql
GROUP BY namespace
```

### 6.4 Limit

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

规则：

- 聚合排行类查询默认允许修改 `LIMIT`。
- 明细查询仍需要 `LIMIT`，无用户指定时默认 100。

### 6.5 Drill Down

用户：

```text
查第一名明细
```

前置条件：

- 上一轮是聚合查询。
- `last_result_summary.top_rows[0]` 存在。
- 第一行中至少有一个维度字段。

Patch：

```json
{
  "op": "drill_down",
  "source_row_index": 0
}
```

上一轮：

```sql
SELECT metric_name, COUNT(*) AS cnt
FROM db_alert_history
WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY metric_name
ORDER BY cnt DESC
LIMIT 20
```

追问生成：

```sql
SELECT *
FROM db_alert_history
WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
  AND metric_name = 'cpu_usage'
LIMIT 100
```

回答必须说明：

```text
我按上一轮结果第一名 metric_name=cpu_usage 查询明细。
```

## 7. SQL 生成策略

### 7.1 推荐实现

新增模块：

```text
app/nl2sql/
├── task.py        # NL2SQLTask 结构、序列化、结果摘要
├── followup.py    # 追问识别和 patch 解析
└── patcher.py     # 对 NL2SQLTask 应用 patch 并生成新任务
```

### 7.2 生成方式

V1 采用混合策略：

1. 可确定的 patch 使用规则生成 SQL。
2. 复杂表达式仍可调用 LLM，但必须输入 `last_nl2sql_task` 和真实 `table_schema`。
3. 最终 SQL 必须经过 `validator.py`。

```text
followup_patch -> task patcher -> sql builder -> validator -> executor
```

不要在追问里直接让 LLM 自由生成工具调用。

## 8. 记忆策略

### 8.1 结构化记忆与摘要记忆分工

| 记忆类型 | 用途 | 是否可作为执行依据 |
|---|---|---|
| `last_nl2sql_task` | 追问 patch、SQL 再生成 | 是 |
| `selected_database` | 省略数据库时复用 | 是 |
| `table_schemas` | schema 缓存 | 是 |
| `pending_nl2sql` | 澄清续接 | 是 |
| `summary` | 对话压缩、辅助理解 | 否，只能辅助 |
| `chat_history` | 展示和短期上下文 | 否，只能辅助 |

### 8.2 Session TTL

表结构缓存和 `last_nl2sql_task` 按 session TTL 保存。建议：

- 本地内存版：跟随进程生命周期。
- 后续接 Redis：TTL 默认 24 小时。
- 用户显式切换数据库时，清空与旧库强绑定的 `last_nl2sql_task`，保留摘要。

### 8.3 多任务历史

V1 只保存最近一次 NL2SQL 任务。

V2 可升级为任务栈：

```json
{
  "nl2sql_tasks": [
    {"task_id": "t1", "topic": "alert metric rank"},
    {"task_id": "t2", "topic": "approval node count"}
  ],
  "active_task_id": "t2"
}
```

当用户说“回到刚才那个告警排行”时，才需要任务栈。

## 9. API 与前端展示

### 9.1 Tool Call 元数据

`nl2sql_followup` 工具建议返回：

```json
{
  "content": "查询结果 Markdown",
  "nl2sql": {
    "type": "followup",
    "followup_type": "change_time_range",
    "inherited_context": {
      "database": "dw-onedba-t1",
      "table": "db_alert_history",
      "group_by": ["metric_name"]
    },
    "changes": [
      "时间范围：最近 30 天 -> 最近 7 天"
    ],
    "sql": "SELECT ...",
    "assumptions": []
  },
  "last_nl2sql_task": {}
}
```

### 9.2 前端展示

前端应展示：

- 当前继承的数据库和表。
- 本次追问修改点。
- 生成 SQL。
- 查询结果。
- 假设说明。

示例：

```text
继承上下文：dw-onedba-t1 / db_alert_history
本次修改：时间范围由最近 30 天改为最近 7 天
```

## 10. 澄清策略

以下情况必须澄清：

| 情况 | 示例回复 |
|---|---|
| 无上一轮任务 | “我没有可复用的上一轮查询，请提供数据库、表和分析目标。” |
| 多个字段候选 | “表中有 create_time 和 update_time，你想按哪个时间字段统计？” |
| 追问目标不明确 | “你说的‘按它分组’中的‘它’指哪个字段？” |
| drill down 无结果 | “上一轮结果为空，无法查询第一名明细。” |
| 切库导致上下文不兼容 | “你已切换数据库，需要重新确认表名或查询目标。” |

## 11. 测试计划

### 11.1 单元测试

| 模块 | 测试点 |
|---|---|
| `followup.py` | 识别时间范围、limit、过滤、分组、show_sql、drill_down |
| `patcher.py` | patch 后任务结构正确 |
| `task.py` | 保存/恢复任务，生成结果摘要 |
| `validator.py` | 追问生成 SQL 仍满足只读、单表、字段存在、LIMIT 规则 |

### 11.2 集成测试

使用 mock OneDBA 覆盖：

1. 初始查询：最近 30 天 metric_name 排行。
2. 追问：改成最近 7 天。
3. 追问：只看前 5 个。
4. 追问：只看 level=critical。
5. 追问：再按 namespace 细分。
6. 追问：把 SQL 给我。
7. 追问：查第一名明细。
8. 无上一轮任务时追问，返回澄清。
9. 切换数据库后追问，要求重新确认。

### 11.3 真实 Smoke Test

建议真实联调顺序：

```text
使用 dw-onedba-t1
帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行
改成最近 7 天
只看前 5 个
把 SQL 给我
查第一名明细
```

每一步检查：

- 是否复用同一数据库。
- 是否复用同一表。
- SQL 是否只改变用户指定的部分。
- 回答是否说明继承上下文和修改点。

## 12. 分阶段实现

### Phase F1：最近一次任务记忆

- 新增 `last_nl2sql_task` 状态。
- NL2SQL 查询成功后保存结构化任务。
- session load/save 支持该字段。
- 前端可展示当前上下文。

成功标准：

```text
用户执行一次查询后，系统能返回“上一轮 SQL”和“上一轮查询表”。
```

### Phase F2：确定性追问 patch

- 实现 `show_sql`。
- 实现 `change_time_range`。
- 实现 `change_limit`。
- 实现 `add_filter`。
- 实现 `add_group_by` / `change_group_by`。

成功标准：

```text
“改成最近 7 天”“只看前 5 个”“按 namespace 再分组”不会丢失上一轮查询上下文。
```

### Phase F3：结果驱动追问

- 保存 `last_result_summary`。
- 实现 `drill_down`。
- 支持“第一名”“第二名”“上一条结果”等指代。

成功标准：

```text
用户说“查第一名明细”时，系统能基于上一轮结果第一行生成明细查询。
```

### Phase F4：多任务上下文

- 保存最近 N 个 NL2SQL 任务。
- 支持用户显式切换 active task。
- 支持“回到刚才那个告警排行”。

成功标准：

```text
用户在多个分析主题之间切换时，追问能绑定到正确任务。
```

## 13. 待确认问题

以下问题需要产品/使用方确认后再固化实现：

1. `last_result_summary` 是否允许保存真实查询结果的前 20 行？
   - 建议：允许保存当前会话内前 20 行，进程内存保存，不持久化到磁盘。

2. 用户显式切换数据库后，是否立即清空 `last_nl2sql_task`？
   - 建议：清空，避免跨库误用表和字段。

3. 追问中出现新表名时，是视为新查询还是“换表继续分析”？
   - 建议：如果用户说“换成/改用 xxx 表”，视为换表追问；如果完整提出新问题，视为新查询。

4. Drill down 明细默认返回多少行？
   - 建议：默认 `LIMIT 100`，并在回答中说明。

5. 多轮追问是否需要展示每次继承和修改的上下文？
   - 建议：展示简短说明，便于开发人员校验 SQL。

6. 是否需要支持“撤回上一步修改”？
   - 建议：V1 不支持；V2 通过任务版本栈实现。

## 14. 当前结论

增强追问能力的关键不是增加更多自然语言规则，而是把每次 NL2SQL 查询保存成可 patch 的结构化任务。

V1 应优先完成三件事：

1. 保存 `last_nl2sql_task`。
2. 把追问解析为明确 patch。
3. patch 后重新生成并校验 SQL。

这样可以解决当前“选库后遗忘原需求”和“追问丢失上一轮表/字段/分组”的问题，并为后续复杂分析、多任务切换和结果 drill down 打基础。
