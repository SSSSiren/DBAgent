# NL2SQL 意图识别改进方案（规划中，未实现）

本文档定义 DBAgent 在当前“规则提取 NL2SQL 关键槽位”基础上的升级方案。目标是提升自然语言泛化能力，避免每遇到一种新问法、新字段、新表达方式都修改正则规则。

## 0. 当前实现基线

截至当前代码状态，项目已经具备推进本方案的基础，但意图识别仍处在“规则优先、结构较薄”的阶段。

| 模块 | 当前状态 | 与本方案关系 |
|---|---|---|
| `app/nl2sql/intent.py` | 定义 `NL2SQLIntent`，并包含数据库、表、字段、操作、limit、时间范围等规则解析 | 需要拆分为数据结构与规则解析两层 |
| `app/agent/nodes.py` | `plan_node` 会识别 NL2SQL 查询并进入 `run_nl2sql_query` | 需要把入口从 `parse_nl2sql_intent` 逐步切到 `intent_parser.parse_intent` |
| `run_nl2sql_query` | 已实现库表解析、加载表结构、SQL 生成、校验、执行、修复 | 可复用为后续 intent 结果的执行链路 |
| `app/nl2sql/resolver.py` | 已支持数据库和表名候选解析 | 需要扩展字段候选、置信度和澄清结果 |
| `app/nl2sql/generator.py` | 已要求只基于真实 schema 生成 SQL | 需要优先消费 `query_pattern`、`dimensions`、`filters` 等结构 |
| `app/nl2sql/validator.py` | 已做只读、安全、表名、字段和 LIMIT 校验 | 继续作为最终 SQL 安全边界 |
| `tests/test_nl2sql.py` | 已覆盖现有规则、resolver、validator、语义层 prompt | 需要新增 intent fixture 和 LLM/merger mock 测试 |

当前可推进结论：

```text
可以推进，但第一阶段应保持行为兼容，先做 Intent Schema 扩展与规则模块化。
LLM 结构化解析应在回归样本集和 merger 测试补齐后再接入主链路。
```

## 1. 背景问题

当前 NL2SQL 意图识别主要由 `app/nl2sql/intent.py` 中的规则实现，能够处理一批明确表达：

- `dw-onedba-t1 数据库`
- `approval template node 表`
- `出现最多的两个 nodeid`
- `最近 30 天`
- `approval 各个表有多少条数据`

这种方式稳定、可控，但存在边界：

| 问题 | 表现 | 影响 |
|---|---|---|
| 规则覆盖不完整 | “最近一周”“近 7 日”“上个月”等表达可能识别不到 | 查询失败或缺少时间条件 |
| 语言泛化弱 | “按指标看看告警次数”不一定能映射到 `metric_name` | 需要用户使用字段原名 |
| 查询结构表达不足 | 只靠 `operation` 难以表达多维分组、过滤、趋势 | SQL 生成扩展困难 |
| 正则不断膨胀 | 每个失败 case 都加规则 | 维护成本高，容易互相影响 |
| 缺少置信度 | 字段相似匹配无法明确高低置信 | 不知道该自动执行还是澄清 |

核心结论：

```text
不要继续无限堆正则。规则应作为确定性兜底，复杂语言理解交给 LLM，最终由真实 schema 和 validator 约束。
```

## 2. 设计目标

1. 保留现有规则解析能力，保证简单查询稳定。
2. 引入 LLM 结构化解析，提高自然语言泛化能力。
3. 定义统一的 Intent Schema，避免 LLM 返回自由文本。
4. 通过真实库表 schema 校验表名、字段名和时间字段。
5. 引入候选与置信度，明确自动执行和澄清边界。
6. 建立意图解析回归样本集，避免修一个 case 破坏旧能力。

### 2.1 非目标

| 非目标 | 说明 |
|---|---|
| 自动跨表 Join 推断 | 仍按 `04-nl2sql-workflow.md` 的单库、单表 V1 边界推进 |
| LLM 直接生成 SQL | LLM parser 只返回结构化 intent，SQL 仍由 generator 基于 schema 生成 |
| 绕过 SQL validator | 所有最终 SQL 仍必须经过 `validate_sql` |
| 复杂业务口径自动注入 | 业务口径继续走语义层确认机制，未确认候选不能直接用于 SQL |
| 前端完整展示 parser JSON | 前端只展示用户可理解的识别摘要，不暴露内部完整结构 |

## 3. 总体方案

推荐三层解析架构：

```text
User Input
  ↓
Rule Parser
  ↓
LLM Parser
  ↓
Intent Merger
  ↓
Schema Resolver
  ↓
Intent Validator
  ↓
SQL Generator
```

职责分工：

| 层 | 职责 |
|---|---|
| Rule Parser | 提取确定性信息，作为兜底和修正依据 |
| LLM Parser | 解析复杂自然语言，返回结构化 JSON |
| Intent Merger | 合并规则和 LLM 结果，解决冲突 |
| Schema Resolver | 基于真实表结构解析表名、字段名、时间字段 |
| Intent Validator | 判断是否可执行，或是否需要澄清 |
| SQL Generator | 基于最终结构化 intent 生成 SQL |

设计原则：

```text
规则负责确定性，LLM 负责语言泛化，schema 负责真实性，validator 负责安全性。
```

### 3.1 推荐执行顺序

实际落地时不要一次性切换主链路。建议按以下顺序推进：

```text
Phase I1 Intent Schema 兼容扩展
  ↓
Phase I2 Rule Parser 模块化，行为保持不变
  ↓
Phase I2.5 回归样本集先落地
  ↓
Phase I3 LLM Parser，默认可关闭
  ↓
Phase I4 Intent Merger，灰度接入主链路
  ↓
Phase I5 Schema Resolver 字段候选与置信度
  ↓
Phase I6 主链路切换与清理
  ↓
Phase I7 观测与灰度
```

原因：

- I1/I2 是结构性重整，风险低，可以快速建立清晰边界。
- I2.5 应提前做，作为后续 LLM 和 merger 的回归护栏。
- I3/I4 引入非确定性，需要 mock 测试、失败降级和开关控制。
- I5 会影响自动执行或澄清边界，应在 intent 结构稳定后进行。

## 4. Intent Schema 设计

建议将当前 `NL2SQLIntent` 扩展为更完整的结构化 schema。

### 4.1 基础结构

```json
{
  "is_query": true,
  "query_pattern": "group_count_rank",
  "database_keyword": "dw-onedba-t1",
  "table_hint": "db_alert_history",
  "table_prefix": "",
  "field_hints": [
    {"text": "metric_name", "role": "dimension"}
  ],
  "dimensions": [
    {"field_hint": "metric_name"}
  ],
  "measure": {
    "type": "count",
    "expression": "COUNT(*)",
    "alias": "cnt"
  },
  "filters": [],
  "time_range": {
    "type": "relative",
    "value": 30,
    "unit": "day",
    "field_hint": ""
  },
  "order_by": [
    {"field_hint": "cnt", "direction": "desc"}
  ],
  "limit": 20,
  "needs_clarification": false,
  "clarification_question": ""
}
```

### 4.2 Python 数据结构建议

V1 仍可使用 `dataclass`，避免一次性引入 Pydantic 迁移成本。后续如果 API 层也需要复用该结构，再考虑升级为 Pydantic model。

```python
@dataclass
class FieldHint:
    text: str
    role: str = ""  # dimension, measure, filter, time


@dataclass
class DimensionSpec:
    field_hint: str
    resolved_field: str = ""


@dataclass
class MeasureSpec:
    type: str = "count"  # count, sum, avg, min, max
    field_hint: str = ""
    expression: str = ""
    alias: str = "cnt"


@dataclass
class FilterSpec:
    field_hint: str
    operator: str
    value: str | int | float | bool
    resolved_field: str = ""


@dataclass
class TimeRangeSpec:
    type: str = ""  # relative, absolute, named_period
    value: int | str | None = None
    unit: str = ""  # day, week, month
    field_hint: str = ""
    resolved_field: str = ""


@dataclass
class OrderBySpec:
    field_hint: str
    direction: str = "desc"
    resolved_field: str = ""


@dataclass
class NL2SQLIntent:
    is_query: bool
    user_input: str = ""

    # New structured fields
    query_pattern: str = ""
    database_keyword: str = ""
    table_hint: str = ""
    table_prefix: str = ""
    field_hints: list[FieldHint] = field(default_factory=list)
    dimensions: list[DimensionSpec] = field(default_factory=list)
    measure: MeasureSpec | None = None
    filters: list[FilterSpec] = field(default_factory=list)
    time_range: TimeRangeSpec | None = None
    order_by: list[OrderBySpec] = field(default_factory=list)
    limit: int | None = None

    # Compatibility fields for current code path
    operation: str = "select"
    legacy_field_hints: list[str] = field(default_factory=list)
    time_days: int | None = None

    needs_clarification: bool = False
    clarification_question: str = ""
```

兼容要求：

- 第一阶段可以暂时保留当前 `field_hints: list[str]`，但最终应迁移到结构化 `FieldHint`。
- 为减少改动面，也可以先新增 `structured_field_hints`，待 generator 和 follow-up 迁移后再统一命名。
- `operation`、`time_days` 在 I1/I2 阶段必须继续可用，避免破坏 `run_nl2sql_query`、`_fallback_generated_sql`、追问记忆等现有链路。

### 4.3 query_pattern

只靠 `operation` 不足以表达 SQL 结构，建议引入 `query_pattern`：

| query_pattern | 说明 | 示例 |
|---|---|---|
| `detail_query` | 明细查询 | “查最近 100 条告警” |
| `single_table_count` | 单表总数 | “这个表有多少条数据” |
| `table_count_batch` | 多表计数 | “approval 各个表分别有多少条数据” |
| `top_n_frequency` | 单字段出现频率 Top-N | “出现最多的两个 nodeid” |
| `group_count_rank` | 按维度统计次数排行 | “不同 metric_name 的告警次数排行” |
| `time_series_trend` | 按时间粒度趋势 | “最近 30 天每天告警趋势” |
| `field_count` | 字段数量 | “这个表有多少个字段” |
| `schema_explore` | 表结构探索 | “看一下这个表结构” |

`operation` 可以保留作为兼容字段，但 SQL 生成应优先基于 `query_pattern`。

### 4.4 operation 兼容映射

当前代码大量使用 `operation`。迁移期间必须提供双向兼容映射：

| 旧 `operation` | 新 `query_pattern` | 说明 |
|---|---|---|
| `select` | `detail_query` | 普通明细查询 |
| `recent` | `detail_query` | 带时间倾向的明细查询 |
| `count` | `single_table_count` | 单表记录数 |
| `table_counts` | `table_count_batch` | 多表计数 |
| `most_frequent` | `top_n_frequency` | 单字段 Top-N |
| `ranking_count` | `group_count_rank` | 按维度计数排行 |
| `field_count` | `field_count` | 字段数量 |

迁移规则：

```text
生成阶段优先读取 query_pattern。
如果 query_pattern 为空，则从 operation 推导。
如果 operation 为空，则从 query_pattern 反推一个兼容 operation。
```

## 5. 模块拆分

建议将 `app/nl2sql/intent.py` 拆分为以下模块：

```text
app/nl2sql/
├── intent.py          # Intent 数据结构、枚举、归一化
├── rule_parser.py     # 当前正则规则迁移到这里
├── llm_parser.py      # LLM 结构化解析
├── intent_parser.py   # 规则 + LLM 合并入口
├── intent_validator.py # Intent 可执行性校验
├── resolver.py        # 数据库、表、字段候选解析
├── validator.py       # SQL 安全与字段校验
└── generator.py       # SQL 生成
```

### 5.0 迁移约束

1. 先新增模块，再迁移调用点，不在同一个提交中删除旧入口。
2. `parse_nl2sql_intent(user_input)` 在 I1/I2 后仍然存在，作为兼容 wrapper。
3. 新入口命名为 `parse_intent(user_input, summary="", enable_llm=True)`。
4. LLM 不可用、超时、JSON 解析失败时，必须返回规则解析结果。
5. 任何 parser 都不能执行 OneDBA 查询，schema 相关判断放在 resolver 阶段。

### 5.1 rule_parser.py

职责：

- 保留现有规则能力。
- 提取确定性强的信息。
- 作为 LLM 不可用时的兜底。

适合规则提取的内容：

| 信息 | 示例 |
|---|---|
| 数据库关键词 | `dw-onedba-t1 数据库` |
| 表名提示 | `approval template node 表` |
| 数字 limit | `前 5 个`、`两个` |
| 时间范围 | `最近 30 天` |
| 多表前缀 | `approval 各个表` |
| 显式 SQL | 用户直接输入 `SELECT ...` |

### 5.2 llm_parser.py

职责：

- 调用 DeepSeek 解析复杂自然语言。
- 只返回固定 JSON。
- 不生成 SQL。
- 不发明已解析 schema 之外的真实字段，只能返回用户表达的 `field_hint`。

Prompt 要求：

```text
你是 NL2SQL 意图解析器，不生成 SQL。
你只把用户问题解析为 JSON。
字段名不确定时返回 field_hint，不要假设真实字段存在。
如果问题缺少数据库或表，不要编造，设置 needs_clarification。
```

### 5.3 intent_parser.py

职责：

- 统一入口：`parse_intent(user_input, summary)`。
- 串行调用规则和 LLM。
- 合并结果。
- 输出标准 Intent。

伪代码：

```python
async def parse_intent(user_input: str, summary: str = "", enable_llm: bool = True) -> NL2SQLIntent:
    rule_intent = parse_by_rules(user_input)
    if not enable_llm:
        return normalize_intent(rule_intent)

    llm_intent = await parse_by_llm(user_input, summary)
    merged = merge_intents(rule_intent, llm_intent)
    return normalize_intent(merged)
```

### 5.4 intent_validator.py

Intent 层 validator 与 SQL validator 区分，负责在进入 schema resolver 或 SQL generator 前判断结构是否足够。

| 校验项 | 处理 |
|---|---|
| `is_query=false` | 不进入 NL2SQL |
| 没有 `table_hint` 且没有 `table_prefix` | 返回“需要先明确要查询的表名” |
| `limit <= 0` 或过大 | 重置到默认值并记录 assumption，或要求澄清 |
| filter operator 不在白名单 | 丢弃该 filter 并要求澄清 |
| `query_pattern` 不在枚举中 | 降级为 `detail_query` 或规则结果 |

operator 白名单：

```text
=, !=, >, >=, <, <=, LIKE, IN, NOT IN, BETWEEN, IS NULL, IS NOT NULL
```

## 6. 规则与 LLM 合并策略

合并时不能简单“LLM 覆盖规则”，需要按字段设定优先级。

| 字段 | 优先级 | 原因 |
|---|---|---|
| `database_keyword` | 规则优先 | 用户显式写出的实例名最可靠 |
| `table_hint` | 规则优先，其次 LLM | 显式 `xx 表` 边界较清楚 |
| `table_prefix` | 规则优先 | “各个表”模式确定性强 |
| `limit` | 规则优先 | 数字解析应确定 |
| `time_range` | 规则优先，其次 LLM | 明确数字优先；“上周”等交给 LLM |
| `query_pattern` | LLM 优先，规则兜底 | 复杂查询模式需要语言理解 |
| `dimensions` | LLM 优先，schema 后校验 | 维度表达多样 |
| `filters` | LLM 优先，schema 后校验 | 过滤条件表达复杂 |
| `order_by` | LLM 优先，规则兜底 | “升序/倒序/最高/最低”等语义化 |

冲突处理：

```text
若规则识别到显式值，LLM 返回不同值：
  - 对数据库、表、limit、时间数字，规则优先。
  - 对 query_pattern、维度、过滤条件，合并后交给 schema resolver 校验。
```

### 6.1 合并输出应保留来源

为了排查和调试，建议每个关键字段保留来源元信息：

```json
{
  "query_pattern": "group_count_rank",
  "sources": {
    "query_pattern": "llm",
    "database_keyword": "rule",
    "table_hint": "rule",
    "limit": "rule",
    "time_range": "rule",
    "dimensions": "llm"
  }
}
```

这些来源信息不一定需要暴露给前端，但应在测试或 debug 日志中可见。

### 6.2 LLM 输出降级规则

| 异常情况 | 降级策略 |
|---|---|
| LLM 未配置 | 只使用规则结果 |
| LLM 超时 | 只使用规则结果，并记录 debug 信息 |
| LLM 返回非 JSON | 只使用规则结果 |
| LLM 返回 JSON 但字段类型错误 | 对错误字段丢弃，保留其他合法字段 |
| LLM 将 `needs_clarification=true` 但规则已高置信识别 | 规则优先，继续后续 resolver |
| LLM 返回 SQL 字符串 | 忽略 SQL 字段，并记录 parser violation |

## 7. Schema 后置校验

意图解析阶段只回答“用户想要什么”，不直接决定真实字段。

示例：

```text
查 alert history 表中最近 30 天不同指标的告警次数
```

LLM 可返回：

```json
{
  "table_hint": "alert history",
  "field_hints": [{"text": "指标", "role": "dimension"}],
  "query_pattern": "group_count_rank",
  "time_range": {"type": "relative", "value": 30, "unit": "day"}
}
```

后续通过真实表结构解析：

```text
alert history -> db_alert_history
指标 -> metric_name
最近 30 天 -> alert_time
```

如果 schema 中没有对应字段，不能执行 SQL，应进入澄清或相似字段确认。

### 7.1 Resolver 输出契约

建议把 resolver 输出从单个值扩展为候选结构：

```json
{
  "hint": "指标",
  "resolved": "metric_name",
  "confidence": 0.91,
  "candidates": [
    {
      "name": "metric_name",
      "confidence": 0.91,
      "match_type": "business_alias",
      "reason": "内置业务词典：指标 -> metric_name"
    }
  ],
  "needs_clarification": false,
  "question": ""
}
```

字段解析只允许在以下来源中做判断：

| 来源 | 示例 | 可信度 |
|---|---|---|
| 精确字段名 | `metric_name` -> `metric_name` | 高 |
| 规范化字段名 | `metric name` -> `metric_name` | 高 |
| 表结构相似度 | `node id` -> `nodeid` | 中高 |
| 内置小词典 | `指标` -> `metric_name` | 取决于字段是否存在 |
| 业务语义层 | `GMV` -> `SUM(total_amount)` | 必须已确认 |
| LLM 猜测 | `指标` -> `metric_name` | 不能单独作为真实字段依据 |

### 7.2 时间字段解析

时间范围需要单独解析时间字段，不能只靠“最近 N 天”就盲目使用某个字段。

推荐优先级：

1. 用户显式指定字段，例如“按 create_time 最近 7 天”。
2. intent 的 `time_range.field_hint` 经 schema resolver 高置信匹配。
3. 表中唯一高置信时间字段，例如 `alert_time`、`create_time`、`created_at`。
4. 多个时间字段时进入澄清。
5. 没有时间字段时，不添加时间过滤，并返回明确说明或澄清。

对当前 `time_days` 的兼容：

```text
如果 time_range 为空但 time_days 有值，则构造 relative day time_range。
如果 time_range 已有值，则以 time_range 为准，并同步 time_days 供旧逻辑使用。
```

## 8. 字段候选与置信度

建议字段解析输出候选结构：

```json
{
  "hint": "指标",
  "resolved_field": "metric_name",
  "candidates": [
    {"field": "metric_name", "confidence": 0.91, "reason": "业务常用指标字段"},
    {"field": "metric_key", "confidence": 0.72, "reason": "名称相似"}
  ],
  "needs_clarification": false
}
```

处理规则：

| 情况 | 处理 |
|---|---|
| 唯一高置信字段 | 自动使用，并在回答中说明假设 |
| 多个高置信候选 | 让用户选择 |
| 只有低置信候选 | 让用户澄清 |
| 无候选字段 | 明确提示字段不存在 |
| LLM 返回字段但 schema 不存在 | 禁止执行，进入修正或澄清 |

建议阈值：

```text
confidence >= 0.85：可自动使用
0.60 <= confidence < 0.85：需要澄清
confidence < 0.60：视为未匹配
```

### 8.1 置信度计算建议

置信度不要求一开始非常精细，但必须可解释。V1 可采用加权启发式：

| 匹配方式 | 建议分数 |
|---|---:|
| 字段名完全匹配 | 1.00 |
| normalize 后完全匹配 | 0.95 |
| 唯一后缀匹配 | 0.90 |
| 内置业务词典命中且字段存在 | 0.88 |
| 相似度 >= 0.92 | 0.86 |
| 相似度 0.80 到 0.92 | 0.60 到 0.85 |
| 仅 LLM 建议但无 schema 支撑 | 最高 0.59 |

如果两个候选分数差距小于 `0.05`，即使最高分超过 `0.85`，也建议澄清，避免静默选错字段。

## 9. LLM 结构化解析输出契约

LLM 必须只返回 JSON，不能返回解释文本：

```json
{
  "is_query": true,
  "query_pattern": "group_count_rank",
  "database_keyword": "",
  "table_hint": "db_alert_history",
  "table_prefix": "",
  "dimensions": [
    {"field_hint": "metric_name"}
  ],
  "measure": {
    "type": "count",
    "alias": "cnt"
  },
  "filters": [
    {
      "field_hint": "level",
      "operator": "=",
      "value": "critical"
    }
  ],
  "time_range": {
    "type": "relative",
    "value": 30,
    "unit": "day",
    "field_hint": ""
  },
  "order_by": [
    {"field_hint": "cnt", "direction": "desc"}
  ],
  "limit": 20,
  "needs_clarification": false,
  "clarification_question": ""
}
```

禁止行为：

- 不生成 SQL。
- 不调用工具。
- 不编造数据库 ID。
- 不编造真实字段是否存在。
- 不因为字段不确定就随意选择一个字段。

### 9.1 Prompt 输入边界

LLM parser 的输入只包含：

- 用户原始问题。
- 当前 session summary。
- 已选择数据库的简要信息，如果存在。
- 上一轮任务摘要，如果是追问候选。
- 支持的 `query_pattern` 枚举和 JSON schema。

LLM parser 不接收完整表结构，避免它在解析阶段把 field hint 误当成真实字段确认。真实 schema 只在 resolver/generator 阶段使用。

### 9.2 LLM 调用开关

建议增加配置：

```text
NL2SQL_ENABLE_LLM_INTENT_PARSER=true
NL2SQL_INTENT_LLM_TIMEOUT_SECONDS=5
```

默认策略：

- 本地测试环境可以关闭 LLM parser。
- 生产或集成环境开启时必须有超时和降级。
- 单元测试用 monkeypatch/mock LLM，不依赖真实 DeepSeek。

## 10. 回归样本集

每发现一个失败 case，不应只修改规则，还应加入回归样本集。

建议新增：

```text
tests/fixtures/nl2sql_intents.json
```

样本格式：

```json
[
  {
    "id": "intent-001",
    "case_type": "legacy_rule",
    "input": "帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行",
    "expected": {
      "table_hint": "db_alert_history",
      "query_pattern": "group_count_rank",
      "time_range": {"value": 30, "unit": "day"},
      "dimensions": [{"field_hint": "metric_name"}],
      "limit": 20
    }
  },
  {
    "id": "intent-002",
    "case_type": "legacy_rule",
    "input": "查 approval template node 表里出现最多的两个 nodeid",
    "expected": {
      "table_hint": "approval_template_node",
      "query_pattern": "top_n_frequency",
      "dimensions": [{"field_hint": "nodeid"}],
      "limit": 2
    }
  }
]
```

测试目标：

- 新增问法不破坏已有问法。
- LLM 不可用时规则兜底仍可处理简单查询。
- 合并策略稳定。
- schema 校验能拦截不存在字段。

### 10.1 建议样本分类

| case_type | 说明 |
|---|---|
| `legacy_rule` | 当前规则已经支持，必须保持不变 |
| `time_expression` | 最近一周、近 7 日、上个月、本月等 |
| `query_pattern` | Top-N、分组排行、趋势、明细、字段数量 |
| `field_alias` | 指标、告警时间、创建时间等自然语言字段 hint |
| `filter_expression` | critical、状态为成功、包含 xx 等过滤 |
| `clarification` | 缺少表、多个字段候选、不存在字段等 |

### 10.2 测试分层

| 测试 | 覆盖 |
|---|---|
| `test_rule_parser.py` | 规则迁移后行为不变 |
| `test_llm_parser.py` | prompt 约束、JSON 解析、非法输出降级 |
| `test_intent_merger.py` | 字段级优先级和冲突处理 |
| `test_intent_fixtures.py` | fixture 批量回归 |
| `test_resolver.py` | 字段候选、置信度、澄清 |
| `test_agent.py` | plan_node 和 run_nl2sql_query 兼容旧入口 |

## 11. 分阶段实现

### Phase I1：Intent Schema 扩展

- 扩展 `NL2SQLIntent`。
- 新增 `query_pattern`、`dimensions`、`measure`、`filters`、`time_range`、`order_by`。
- 保持对当前字段的兼容。
- 增加 `normalize_intent()`，统一补齐 `query_pattern` 与 `operation`。
- 增加兼容属性或转换函数，减少调用点一次性修改。

成功标准：

```text
现有测试不破坏，当前 NL2SQL 查询仍能执行。
```

### Phase I2：规则解析模块化

- 新增 `app/nl2sql/rule_parser.py`。
- 将当前 `intent.py` 中的正则解析迁移到 `rule_parser.py`。
- `intent.py` 只保留数据结构、枚举、归一化函数和兼容 wrapper。
- 增加规则解析单元测试。

成功标准：

```text
现有规则能力完整迁移，行为不变。
```

验收命令：

```bash
/Users/admin/miniconda3/envs/DBR/bin/python -m pytest tests/test_nl2sql.py tests/test_agent.py -q
```

### Phase I2.5：回归样本集先行

- 新增 `tests/fixtures/nl2sql_intents.json`。
- 先放入当前已经支持的 legacy case。
- 增加 fixture runner，先只走规则 parser。
- 后续每个新能力先加 fixture，再改 parser。

成功标准：

```text
fixture 中 legacy case 全部通过，且和现有单元测试互相补充。
```

### Phase I3：LLM 结构化解析

- 新增 `llm_parser.py`。
- 使用 DeepSeek 返回固定 JSON。
- LLM 不可用或 JSON 解析失败时不影响规则兜底。
- 增加配置开关和超时。
- 单元测试只使用 mock LLM。

成功标准：

```text
复杂自然语言能补全 query_pattern、filters、dimensions。
```

### Phase I4：Intent Merger

- 新增 `intent_parser.py`。
- 实现规则和 LLM 的字段级合并策略。
- 明确冲突优先级。
- 默认先在测试中启用，主链路可通过配置灰度。

成功标准：

```text
数据库、表、limit、时间数字等确定性信息优先采用规则结果。
```

### Phase I5：Schema Resolver 增强

- 增加字段候选和置信度。
- 对中文业务词、下划线、驼峰、相似字段做统一匹配。
- 高置信自动使用，低置信澄清。
- 增加时间字段解析策略。
- 多候选分数接近时必须澄清。

成功标准：

```text
“指标”可高置信映射到 metric_name；多个候选时不误执行。
```

### Phase I6：主链路切换与清理

- 将 `plan_node` 和 `run_nl2sql_query` 入口切到 `intent_parser.parse_intent`。
- 删除或降级旧 fallback 中容易绕过 schema 的 SQL 推断路径。
- generator 优先消费 `query_pattern`，再兼容 `operation`。
- 文档和测试同步更新。

成功标准：

```text
意图解析升级后，旧查询能力不回退。
```

完整验收命令：

```bash
/Users/admin/miniconda3/envs/DBR/bin/python -m pytest -q
```

### Phase I7：观测与灰度

- 在 debug 日志中记录 rule intent、llm intent、merged intent、resolver candidates。
- 统计 intent parser 降级次数、澄清次数、SQL validation failure 类型。
- 如果 LLM parser 引入明显误判，可以通过配置立即关闭，仅保留规则路径。

成功标准：

```text
线上或本地 smoke 中可解释每一次“为什么执行/为什么澄清/为什么降级”。
```

## 12. 待确认问题

1. 是否允许 LLM 在没有数据库名时，从当前 session summary 推断数据库？
   - 允许作为辅助，但最终以 `selected_schema_id` 或用户确认过的库为准。

2. 中文业务词映射是否需要维护词典？
   - 内置可沉淀的小词典，例如“指标 -> metric_name”“告警时间 -> alert_time”；后续接业务元数据。

3. 字段高置信自动匹配阈值是否采用 `0.85`？
   - V1 使用 `0.85`，低于该值必须澄清。

4. LLM 解析结果是否需要在前端展示？
   - 不展示完整 JSON，只展示“识别到的表、字段、过滤条件、时间范围”，便于用户校验。

5. 新增查询模式时是否必须先补样本？
   - 必须补样本，否则容易引入回归。

6. 是否允许 parser 使用上一轮 `last_nl2sql_task`？
   - 可以用于识别追问意图，但普通新查询不能被上一轮任务静默污染。

7. 字段候选是否自动展示给用户？
   - 只有需要澄清时展示候选；高置信自动使用时在“假设与限制”中说明。

8. 是否将 intent 结果持久化到 session？
   - V1 可只保存在 `last_nl2sql_task` 中。若后续需要调试，可保存 merged intent 的摘要，不保存完整大对象。

## 13. 风险与控制

| 风险 | 说明 | 控制措施 |
|---|---|---|
| LLM 输出不稳定 | 同一问题返回不同 pattern 或字段 hint | 规则优先、fixture 回归、mock 测试、配置开关 |
| LLM 编造字段 | 把自然语言词直接当真实字段 | schema resolver 二次确认，validator 拦截 |
| 兼容字段混乱 | `operation` 与 `query_pattern` 不一致 | `normalize_intent()` 统一映射并测试 |
| 自动执行误查 | 低置信字段被自动使用 | 阈值控制，多候选接近必须澄清 |
| 正则和 LLM 冲突 | 显式表名/limit 被覆盖 | 字段级合并优先级固定 |
| 测试假通过 | 只测新 parser，不测主链路 | fixture + agent + generator + validator 分层测试 |

## 14. 实施准入与完成标准

每个阶段进入下一阶段前，应满足：

1. 当前阶段新增测试通过。
2. 全量 `pytest -q` 通过。
3. 旧入口 `parse_nl2sql_intent` 行为不破坏，直到主链路正式切换。
4. LLM parser 失败时可降级到规则 parser。
5. 新增查询模式必须至少有 1 条 fixture。

本方案完成标准：

```text
1. 规则 parser 和 LLM parser 可独立测试。
2. intent merger 有明确字段级优先级。
3. schema resolver 能输出字段候选与置信度。
4. generator 能优先消费 query_pattern。
5. 低置信字段、多个候选字段、不存在字段均不会自动执行 SQL。
6. 现有 NL2SQL、追问记忆、语义确认和 validator 测试不回退。
```

## 15. 当前结论

NL2SQL 意图识别应从“正则主导”升级为“规则 + LLM + schema 约束”的组合架构。

落地时应坚持三条原则：

1. LLM 只解析意图，不直接生成 SQL。
2. 真实字段和表名必须由 schema resolver 确认。
3. 所有最终 SQL 仍必须经过 validator。

这样可以在保持安全性和稳定性的前提下，显著提升对不同开发人员自然语言表达的覆盖能力。第一步建议从 `Intent Schema 兼容扩展` 和 `规则解析模块化` 开始，确认旧能力不回退后再引入 LLM parser。
