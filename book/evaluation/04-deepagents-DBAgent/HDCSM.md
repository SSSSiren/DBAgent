# Agent 性能评测报告

**生成时间**: 2026-08-17 14:26:35
**LLM 模型**: deepseek-v4-pro-260425
**LLM Base URL**: https://dwai-data.dewu-inc.com/openai/v1
**评测总耗时**: 23.4 分钟 (1,402,198ms)

## ⚙️ 运行配置

| 参数 | 值 |
|------|----|
| 数据库 | `dw_onedba` (schemaId=65938636) |
| 重复次数 | 8 |
| 并发数 | 12 |
| HDC 数据底座 | 启用 |
| HDC 命名空间 | `recall_extra` |
| LLM 评判 | 启用 |
| 回答质量评判 | 启用 |
| CLI 命令 | `python -m tests.evaluation.cli run --repeat 8 --concurrency 12 --timeout 400 --with-hdc --hdc-namespace recall_extra -v --verbose-hdc` |

## 📊 总览

### 评分

| 指标 | 值 |
|------|----|
| 总用例数 | 28 |
| 通过 | 28 |
| 失败 | 0 |
| 错误 | 0 |
| 通过率 | 100.0% |
| 平均分 | 97.49% |

### 延迟

| 指标 | 值 | 说明 |
|------|----|------|
| 端到端延迟 | 29103ms | 完整 ReAct 循环墙钟时间 |
| 准备耗时 (prep) | 5ms | 4路检索 + context 组装 |
| TTFB | 6621ms | 首个 LLM 响应或工具调用到达时间 |

### 工具调用

| 指标 | 值 |
|------|----|
| 平均工具调用 | 1.0 |
| 平均 Turns | 2.0 |

### Token 消耗

| 指标 | 值 | 说明 |
|------|----|------|
| 总 Token | 18363 | input + output |
| 输入 Token | 17632 | prompt（系统提示词 + 上下文 + 对话历史） |
| 输出 Token | 730 | completion（推理 + 工具调用决策） |

### 波动 (σ)

| 指标 | 标准差 |
|------|--------|
| 工具调用 | ±0.0 |
| 总 Token | ±204 |
| 输入 Token | ±145 |
| 输出 Token | ±78 |
| 延迟 | ±3198ms |
| Turns | ±0.0 |

## 📐 维度平均分

| 维度 | 权重 | 平均分 |
|------|------|--------|
| SQL 语法正确 | 10% | 100.00% |
| 表/列引用正确 | 10% | 99.11% |
| 过滤条件正确 | 10% | 99.55% |
| 结果数据正确 | 60% | 100.00% |
| SQL 规范 | 10% | 75.36% |

## 📋 按难度分布

| 难度 | 用例数 | 通过 | 失败 | 通过率 | 平均分 | 平均延迟 | 平均工具调用 |
|------|--------|------|------|--------|--------|----------|-------------|
| Easy | 10 | 10 | 0 | 100.0% | 97.07% | 25910ms | 1.0 |
| Medium | 14 | 14 | 0 | 100.0% | 97.62% | 27862ms | 1.1 |
| Hard | 4 | 4 | 0 | 100.0% | 98.09% | 41434ms | 1.0 |

## 📝 用例详情

| 用例 | 难度 | 类别 | 通过 | 总分 | SQL | 工具调用 | Token(总) | 输入Token | 输出Token | 延迟 |
|------|------|------|------|------|-----|----------|----------|----------|---------|------|
| TC-001 | Easy | 单表过滤 | ✅ | 96.54% | 100.00% | 1±0 | 29383±162 | 28587±19 | 795±153 | 28824±3240ms |
| TC-002 | Easy | 单表过滤 | ✅ | 97.60% | 100.00% | 1±0 | 14408±28 | 14150±10 | 258±27 | 15105±840ms |
| TC-003 | Easy | 聚合 | ✅ | 97.60% | 100.00% | 1±0 | 14991±38 | 14423±9 | 568±36 | 22649±2245ms |
| TC-004 | Easy | 聚合 | ✅ | 95.94% | 100.00% | 1±0 | 16279±184 | 15352±16 | 927±180 | 30150±2155ms |
| TC-005 | Medium | 时间窗口 | ✅ | 94.60% | 100.00% | 1±0 | 14976±33 | 14451±17 | 524±36 | 26358±4940ms |
| TC-006 | Medium | 时间窗口 | ✅ | 100.00% | 100.00% | 1±0 | 14866±54 | 14276±30 | 589±34 | 27626±3297ms |
| TC-007 | Easy | 单表过滤 | ✅ | 95.91% | 100.00% | 1±0 | 34624±139 | 33666±21 | 957±134 | 33413±3059ms |
| TC-008 | Easy | 聚合 | ✅ | 97.60% | 100.00% | 1±0 | 14682±44 | 14267±22 | 414±47 | 21918±3146ms |
| TC-009 | Medium | 聚合 | ✅ | 100.00% | 100.00% | 1±0 | 15001±41 | 14439±13 | 562±48 | 22996±1374ms |
| TC-010 | Medium | 时间窗口 | ✅ | 97.54% | 100.00% | 1±0 | 14975±86 | 14489±29 | 485±95 | 22801±2269ms |
| TC-011 | Medium | 多条件过滤 | ✅ | 96.29% | 100.00% | 1±0 | 34746±217 | 33675±27 | 1070±203 | 35667±5449ms |
| TC-012 | Medium | 聚合 | ✅ | 97.60% | 100.00% | 1±0 | 15027±44 | 14499±19 | 528±29 | 22783±2748ms |
| TC-013 | Medium | 聚合 | ✅ | 95.47% | 100.00% | 1±0 | 15266±52 | 14624±25 | 642±40 | 26069±1304ms |
| TC-014 | Medium | 时间窗口 | ✅ | 97.41% | 100.00% | 1±0 | 14691±59 | 14156±38 | 535±30 | 27903±5042ms |
| TC-015 | Medium | 多条件过滤 | ✅ | 96.98% | 100.00% | 1±0 | 15744±99 | 14989±25 | 754±84 | 29367±2155ms |
| TC-016 | Medium | 排名 | ✅ | 100.00% | 100.00% | 1±0 | 14980±33 | 14501±26 | 478±19 | 25241±4147ms |
| TC-017 | Easy | 单表过滤 | ✅ | 97.01% | 100.00% | 1±0 | 15832±42 | 14816±11 | 1016±44 | 34404±1968ms |
| TC-018 | Easy | 聚合 | ✅ | 97.48% | 100.00% | 1±0 | 14435±62 | 14002±20 | 432±49 | 22563±3426ms |
| TC-019 | Medium | 聚合 | ✅ | 100.00% | 100.00% | 1±0 | 14770±46 | 14271±32 | 499±42 | 21825±2205ms |
| TC-020 | Medium | 时间窗口 | ✅ | 97.10% | 100.00% | 1±0 | 14783±50 | 14313±12 | 470±46 | 22856±896ms |
| TC-021 | Easy | 单表过滤 | ✅ | 97.38% | 100.00% | 1±0 | 30495±165 | 29769±14 | 726±159 | 26432±3541ms |
| TC-022 | Easy | 聚合 | ✅ | 97.60% | 100.00% | 1±0 | 14409±56 | 13919±18 | 489±58 | 23637±3685ms |
| TC-024 | Medium | JOIN | ✅ | 96.16% | 100.00% | 2±0 | 34259±3435 | 32936±3414 | 1322±172 | 50881±5560ms |
| TC-025 | Medium | 子查询 | ✅ | 97.60% | 100.00% | 1±0 | 15529±76 | 14769±14 | 760±76 | 27690±2351ms |
| TC-027 | Hard | 派生指标 | ✅ | 97.60% | 100.00% | 1±0 | 15482±147 | 14593±67 | 888±85 | 35881±4329ms |
| TC-028 | Hard | 时间窗口 | ✅ | 97.54% | 100.00% | 1±0 | 15539±102 | 14751±51 | 787±72 | 34272±2552ms |
| TC-029 | Hard | 复合查询 | ✅ | 100.00% | 100.00% | 1±0 | 16539±72 | 15185±30 | 1353±51 | 44014±5022ms |
| TC-030 | Hard | 复合查询 | ✅ | 97.23% | 100.00% | 1±0 | 17458±151 | 15840±30 | 1618±133 | 51570±6611ms |

## 🤖 Agent 中间过程

### TC-001 ✅ — 工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。
- 本轮回复: ## 查询结果

**数据库**: `dw_onedba`  
**表**: `order_record`

**执行的 SQL**:
```sql
SELECT id, committer_name, status_desc, create_time 
FROM order_record 
WHERE order_type = 'dataChange' 
ORDER BY create_time
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。",
  "table_name": "order_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。

**表**: order_record
... (共 452 行)
     ```

</details>

### TC-002 ✅ — 工单系统：查询 is_finished=1 的工单数量。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：查询 is_finished=1 的工单数量。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：查询 is_finished=1 的工单数量。
- 本轮回复: 查询结果：**is_finished=1（已完成）的工单数量为 778 条**。

执行的 SQL：

```sql
SELECT COUNT(*) AS finished_count FROM order_record WHERE is_finished = 1
```
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "统计 is_finished=1 的工单数量",
  "schema_id": 65938636,
  "table_name": "order_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计 is_finished=1 的工单数量

**表**: order_record
... (共 20 行)
     ```

</details>

### TC-003 ✅ — 工单系统：统计每种工单类型的数量，按数量降序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计每种工单类型的数量，按数量降序排列。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计每种工单类型的数量，按数量降序排列。
- 本轮回复: ## 工单系统：每种工单类型数量统计（降序）

**执行 SQL：**
```sql
SELECT order_type, COUNT(*) AS order_count 
FROM order_record 
GROUP BY order_type 
ORDER BY order_count DESC, order_type ASC
```

**结果（共 20 种工单类型）：**

| 序号 
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "统计每种工单类型的数量，按数量降序排列",
  "schema_id": 65938636,
  "table_name": "order_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计每种工单类型的数量，按数量降序排列

**表**: order_record
... (共 39 行)
     ```

</details>

### TC-004 ✅ — 工单系统：统计每种工单状态（status_code 和 status_desc）的数量，按数量降序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计每种工单状态（status_code 和 status_desc）的数量，按数量降序排列。
- 本轮回复: 根据 HDC 数据底座，`order_record` 表正是当前数据库 `dw_onedba` 中的工单表，包含 `status_code` 和 `status_desc` 字段。直接查询。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计每种工单状态（status_code 和 status_desc）的数量，按数量降序排列。
- 上一轮回复: 根据 HDC 数据底座，`order_record` 表正是当前数据库 `dw_onedba` 中的工单表，包含 `status_code` 和 `status_desc` 字段。直接查询。


- 本轮回复: ## 工单状态统计（按数量降序）

**执行的 SQL**：
```sql
SELECT status_code, status_desc, COUNT(*) AS order_count 
FROM order_record 
GROUP BY status_code, status_desc 
ORDER BY order_count DESC
```

| 序号 | status_code 
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "统计每种工单状态（status_code 和 status_desc）的数量，按数量降序排列",
  "table_name": "order_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计每种工单状态（status_code 和 status_desc）的数量，按数量降序排列

**表**: order_record
... (共 84 行)
     ```

</details>

### TC-005 ✅ — 工单系统：统计 2024 年每月创建的工单数量，按月份升序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计 2024 年每月创建的工单数量，按月份升序排列。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计 2024 年每月创建的工单数量，按月份升序排列。
- 本轮回复: ## 2024 年每月工单数量统计

**执行 SQL：**
```sql
SELECT MONTH(create_time) AS month, COUNT(*) AS order_count 
FROM order_record 
WHERE create_time >= '2024-01-01' AND create_time < '2025-01-01' 
GROUP BY MONTH(c
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "工单系统：统计 2024 年每月创建的工单数量，按月份升序排列。",
  "table_name": "order_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 工单系统：统计 2024 年每月创建的工单数量，按月份升序排列。

**表**: order_record
... (共 37 行)
     ```

</details>

### TC-006 ✅ — 工单系统：统计 2024 年每位提交人创建的工单数量，按数量降序排列前 10 名。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计 2024 年每位提交人创建的工单数量，按数量降序排列前 10 名。
- 本轮回复: 用户的需求很明确：统计 2024 年每位提交人的工单数量，按数量降序排列取前 10 名。这和历史查询中的第 1 条类似，只是排序方向从升序改为降序。直接使用 `query_database` 查询。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计 2024 年每位提交人创建的工单数量，按数量降序排列前 10 名。
- 上一轮回复: 用户的需求很明确：统计 2024 年每位提交人的工单数量，按数量降序排列取前 10 名。这和历史查询中的第 1 条类似，只是排序方向从升序改为降序。直接使用 `query_database` 查询。


- 本轮回复: ## 2024 年工单提交统计（按数量降序，Top 10）

查询基于 `order_record` 表，统计 2024 年每位提交人创建的工单数量，按数量降序排列。

**执行的 SQL**：
```sql
SELECT committer_name, COUNT(*) AS order_count 
FROM order_record 
WHERE create_time >= '2024-0
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "table_name": "order_record",
  "question": "工单系统：统计 2024 年每位提交人创建的工单数量，按数量降序排列前 10 名。"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 工单系统：统计 2024 年每位提交人创建的工单数量，按数量降序排列前 10 名。

**表**: order_record
... (共 32 行)
     ```

</details>

### TC-007 ✅ — 告警系统：查询 level='critical' 的告警，返回告警ID、实例ID、指标名称和告警时间，按告警时间降序。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：查询 level='critical' 的告警，返回告警ID、实例ID、指标名称和告警时间，按告警时间降序。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：查询 level='critical' 的告警，返回告警ID、实例ID、指标名称和告警时间，按告警时间降序。
- 本轮回复: ## 查询结果

**数据库**: `dw_onedba` (schema_id=65938636)  
**表**: `db_alert_history`  
**执行的 SQL**:

```sql
SELECT id, db_instance_id, metric_name, alert_time 
FROM db_alert_history 
WHERE level = 'critical
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "查询 db_alert_history 表中 level='critical' 的告警，返回告警ID(id)、实例ID(db_instance_id)、指标名称(metric_name)和告警时间(alert_time)，按告警时间降序排列",
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 查询 db_alert_history 表中 level='critical' 的告警，返回告警ID(id)、实例ID(db_instance_id)、指标名称(metric_name)和告警时间(alert_time)，按告警时间降序排列

**表**: db_alert_history
... (共 523 行)
     ```

</details>

### TC-008 ✅ — 告警系统：统计每种告警级别的数量。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计每种告警级别的数量。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计每种告警级别的数量。
- 本轮回复: 根据 `db_alert_history` 表的查询结果，告警系统中共有 3 种告警级别，按数量升序排列如下：

| 告警级别 | 数量 |
| --- | --- |
| **critical**（严重） | 29,829 |
| **warn**（警告） | 85,662 |
| **ok**（正常） | 266,036 |

**执行的 SQL**：
```sql
SELECT level,
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "统计每种告警级别的数量，按数量升序排列",
  "schema_id": 65938636,
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计每种告警级别的数量，按数量升序排列

**表**: db_alert_history
... (共 26 行)
     ```

</details>

### TC-009 ✅ — 告警系统：统计每种告警指标的数量，按数量降序排列前 10 名。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计每种告警指标的数量，按数量降序排列前 10 名。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计每种告警指标的数量，按数量降序排列前 10 名。
- 本轮回复: 根据 `db_alert_history` 表的查询结果，以下是告警指标按数量降序排列的 Top 10：

| 排名 | 告警指标 (metric_name) | 告警数量 |
| --- | --- | --- |
| 1 | NODE_DiskUsage | 254,647 |
| 2 | ShardingMemoryUsage | 56,929 |
| 3 | DiskUsage | 23,
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "告警系统：统计每种告警指标（metric_name）的数量，按数量降序排列前 10 名。",
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 告警系统：统计每种告警指标（metric_name）的数量，按数量降序排列前 10 名。

**表**: db_alert_history
... (共 29 行)
     ```

</details>

### TC-010 ✅ — 告警系统：统计 2024 年 8 月每天的告警数量，按日期升序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计 2024 年 8 月每天的告警数量，按日期升序排列。
- 本轮回复: 根据历史查询记录和数据库知识，这与之前 7 月的告警统计模式完全一致，直接使用 `db_alert_history` 表查询
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计 2024 年 8 月每天的告警数量，按日期升序排列。
- 上一轮回复: 根据历史查询记录和数据库知识，这与之前 7 月的告警统计模式完全一致，直接使用 `db_alert_history` 表查询
- 本轮回复: 查询执行完成，结果如下：

**执行的 SQL：**
```sql
SELECT DATE(alert_time) AS alert_date, COUNT(*) AS alert_count 
FROM db_alert_history 
WHERE alert_time >= '2024-08-01' AND alert_time < '2024-09-01' 
GROUP BY DATE(a
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "告警系统：统计 2024 年 8 月每天的告警数量，按日期升序排列。",
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 告警系统：统计 2024 年 8 月每天的告警数量，按日期升序排列。

**表**: db_alert_history
... (共 29 行)
     ```

</details>

### TC-011 ✅ — 告警系统：查询 env_type='prd' 且 level='critical' 的告警，返回实例ID、指标名称、当前

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：查询 env_type='prd' 且 level='critical' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。
- 本轮回复: 根据 HDC 数据底座和之前的查询记录，`db_alert_history` 表最适合这个需求。让我直接查询。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：查询 env_type='prd' 且 level='critical' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。
- 上一轮回复: 根据 HDC 数据底座和之前的查询记录，`db_alert_history` 表最适合这个需求。让我直接查询。


- 本轮回复: ## 查询结果：生产环境 Critical 级别告警

**表**: `db_alert_history`（dw_onedba 库）  
**SQL**:
```sql
SELECT db_instance_id, metric_name, cur_value, alert_time 
FROM db_alert_history 
WHERE env_type = 'prd' AND level 
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "告警系统：查询 env_type='prd' 且 level='critical' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。",
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 告警系统：查询 env_type='prd' 且 level='critical' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。

**表**: db_alert_history
... (共 523 行)
     ```

</details>

### TC-012 ✅ — 告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量降序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量降序排列。
- 本轮回复: 根据历史查询记录，直接使用 `db_alert_history` 表来统计。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量降序排列。
- 上一轮回复: 根据历史查询记录，直接使用 `db_alert_history` 表来统计。


- 本轮回复: ## 告警系统：每种 namespace（数据库产品类型）的告警数量（降序）

**执行的 SQL：**
```sql
SELECT namespace, COUNT(*) AS alert_count 
FROM db_alert_history 
GROUP BY namespace 
ORDER BY alert_count DESC
```

| 序号 | namespace | 告警数量
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量降序排列。",
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量降序排列。

**表**: db_alert_history
... (共 30 行)
     ```

</details>

### TC-013 ✅ — 效能统计：统计每个业务域的总成本时间，按成本降序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 效能统计：统计每个业务域的总成本时间，按成本降序排列。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 效能统计：统计每个业务域的总成本时间，按成本降序排列。
- 本轮回复: ## 效能统计：各业务域总成本时间

基于 `effect_dba_domain_cost_v2` 表，统计全部历史数据中各业务域的总成本时间，按降序排列：

| 排名 | 业务域 | 总成本时间（秒） |
| ---: | --- | ---: |
| 1 | 算法平台 | 489.73 |
| 2 | 交易平台 | 454.24 |
| 3 | 汇金平台 | 254.86 |
| 4 | 数据
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "统计每个业务域的总成本时间，按总成本降序排列",
  "schema_id": 65938636,
  "table_name": "effect_dba_domain_cost_v2"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计每个业务域的总成本时间，按总成本降序排列

**表**: effect_dba_domain_cost_v2
... (共 44 行)
     ```

</details>

### TC-014 ✅ — 效能统计：统计 2024 年各月的总成本时间，按月份升序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 效能统计：统计 2024 年各月的总成本时间，按月份升序排列。
- 本轮回复: 根据数据底座信息，`effect_dba_domain_cost_v2` 表包含 `year`、`month`、`cost_time` 字段，可以直接满足需求。与之前"按周统计"的查询类似，这次改为按月。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 效能统计：统计 2024 年各月的总成本时间，按月份升序排列。
- 上一轮回复: 根据数据底座信息，`effect_dba_domain_cost_v2` 表包含 `year`、`month`、`cost_time` 字段，可以直接满足需求。与之前"按周统计"的查询类似，这次改为按月。


- 本轮回复: 查询成功，以下是 2024 年各月的总成本时间统计：

**执行的 SQL：**
```sql
SELECT CONCAT(year, '-', LPAD(month, 2, '0')) AS month_label, 
       SUM(cost_time) AS total_cost_time 
FROM effect_dba_domain_cost_v2 
WHERE year = 20
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "效能统计：统计 2024 年各月的总成本时间，按月份升序排列。",
  "schema_id": 65938636,
  "table_name": "effect_dba_domain_cost_v2"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 效能统计：统计 2024 年各月的总成本时间，按月份升序排列。

**表**: effect_dba_domain_cost_v2
... (共 29 行)
     ```

</details>

### TC-015 ✅ — 效能统计：查询 dba_owner_name='栾尚飞' 负责的所有业务域的成本统计，按成本降序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 效能统计：查询 dba_owner_name='栾尚飞' 负责的所有业务域的成本统计，按成本降序排列。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 效能统计：查询 dba_owner_name='栾尚飞' 负责的所有业务域的成本统计，按成本降序排列。
- 本轮回复: ## 栾尚飞 — 所有业务域成本统计（按成本降序）

**执行 SQL：**

```sql
SELECT business_domain, SUM(cost_time) AS total_cost_time 
FROM effect_dba_domain_cost_v2 
WHERE dba_owner_name = '栾尚飞' 
GROUP BY business_domain 
ORDER 
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "查询 dba_owner_name='栾尚飞' 负责的所有业务域的成本统计，按成本降序排列。成本为 cost_time 字段的总和，按 business_domain 分组。",
  "table_name": "effect_dba_domain_cost_v2"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 查询 dba_owner_name='栾尚飞' 负责的所有业务域的成本统计，按成本降序排列。成本为 cost_time 字段的总和，按 business_domain 分组。

**表**: effect_dba_domain_cost_v2
... (共 43 行)
     ```

</details>

### TC-016 ✅ — 效能统计：查询成本最高的前 5 个业务域，返回业务域名称和总成本时间。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 效能统计：查询成本最高的前 5 个业务域，返回业务域名称和总成本时间。
- 本轮回复: 根据 HDC 数据底座匹配，表 `effect_dba_domain_cost_v2` 正是用于效能统计的业务域成本表。直接查询
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 效能统计：查询成本最高的前 5 个业务域，返回业务域名称和总成本时间。
- 上一轮回复: 根据 HDC 数据底座匹配，表 `effect_dba_domain_cost_v2` 正是用于效能统计的业务域成本表。直接查询
- 本轮回复: 查询完成，以下是成本最高的前 5 个业务域：

**执行 SQL：**
```sql
SELECT business_domain, SUM(cost_time) AS total_cost_time 
FROM effect_dba_domain_cost_v2 
GROUP BY business_domain 
ORDER BY total_cost_time DESC, business_
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "查询成本最高的前 5 个业务域，返回业务域名称和总成本时间，按总成本降序排列",
  "schema_id": 65938636,
  "table_name": "effect_dba_domain_cost_v2"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 查询成本最高的前 5 个业务域，返回业务域名称和总成本时间，按总成本降序排列

**表**: effect_dba_domain_cost_v2
... (共 28 行)
     ```

</details>

### TC-017 ✅ — 日常工作：查询 work_type='问题排查' 的工作记录，返回工作ID、DBA飞书ID、耗时和创建时间。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 日常工作：查询 work_type='问题排查' 的工作记录，返回工作ID、DBA飞书ID、耗时和创建时间。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 日常工作：查询 work_type='问题排查' 的工作记录，返回工作ID、DBA飞书ID、耗时和创建时间。
- 本轮回复: 查询成功，以下是 `work_type='问题排查'` 的工作记录：

**执行的 SQL**：
```sql
SELECT id, dba_feishu_id, cost_time_minute, created_time 
FROM effect_daily_work_v2 
WHERE work_type = '问题排查' 
ORDER BY created_time ASC
```

**
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "查询 work_type='问题排查' 的工作记录，返回工作ID、DBA飞书ID、耗时和创建时间，按创建时间升序排列",
  "table_name": "effect_daily_work_v2"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 查询 work_type='问题排查' 的工作记录，返回工作ID、DBA飞书ID、耗时和创建时间，按创建时间升序排列

**表**: effect_daily_work_v2
... (共 42 行)
     ```

</details>

### TC-018 ✅ — 日常工作：统计每种工作类型的数量。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 日常工作：统计每种工作类型的数量。
- 本轮回复: 根据数据底座，`effect_daily_work_v2` 表记录了 DBA 日常工作信息，直接用它来查询
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 日常工作：统计每种工作类型的数量。
- 上一轮回复: 根据数据底座，`effect_daily_work_v2` 表记录了 DBA 日常工作信息，直接用它来查询
- 本轮回复: 查询完成，以下是 `effect_daily_work_v2` 表中每种工作类型的数量统计：

**执行的 SQL：**
```sql
SELECT work_type, COUNT(*) AS work_count 
FROM effect_daily_work_v2 
GROUP BY work_type 
ORDER BY work_count ASC
```

**查询结果：**

| 序
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "统计每种工作类型的数量，按数量升序排列",
  "schema_id": 65938636,
  "table_name": "effect_daily_work_v2"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计每种工作类型的数量，按数量升序排列

**表**: effect_daily_work_v2
... (共 27 行)
     ```

</details>

### TC-019 ✅ — 工单审计：统计每种 SQL 类型的数量，按数量降序排列前 10 名。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单审计：统计每种 SQL 类型的数量，按数量降序排列前 10 名。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单审计：统计每种 SQL 类型的数量，按数量降序排列前 10 名。
- 本轮回复: 根据 `order_audit_record` 表统计，以下是 SQL 类型数量降序排列的前 10 名：

**执行的 SQL**：
```sql
SELECT sql_type, COUNT(*) AS sql_count 
FROM order_audit_record 
GROUP BY sql_type 
ORDER BY sql_count DESC, sql_type ASC 
LIM
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "统计每种 SQL 类型的数量，按数量降序排列前 10 名",
  "schema_id": 65938636,
  "table_name": "order_audit_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计每种 SQL 类型的数量，按数量降序排列前 10 名

**表**: order_audit_record
... (共 29 行)
     ```

</details>

### TC-020 ✅ — 工单审计：统计 2024 年 12 月每天的审计记录数量，按日期升序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单审计：统计 2024 年 12 月每天的审计记录数量，按日期升序排列。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单审计：统计 2024 年 12 月每天的审计记录数量，按日期升序排列。
- 本轮回复: 查询结果如下：

**SQL 语句**：
```sql
SELECT DATE(create_time) AS audit_date, COUNT(*) AS audit_count 
FROM order_audit_record 
WHERE create_time >= '2024-12-01' AND create_time < '2025-01-01' 
GROUP BY DATE(cr
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "统计 2024 年 12 月每天的审计记录数量，按日期升序排列",
  "schema_id": 65938636,
  "table_name": "order_audit_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计 2024 年 12 月每天的审计记录数量，按日期升序排列

**表**: order_audit_record
... (共 24 行)
     ```

</details>

### TC-021 ✅ — 账户管理：查询 role=0 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID升序。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 账户管理：查询 role=0 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID升序。
- 本轮回复: 根据 HDC 数据底座，`account` 表就在当前数据库 `dw_onedba` 中，我直接查询。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 账户管理：查询 role=0 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID升序。
- 上一轮回复: 根据 HDC 数据底座，`account` 表就在当前数据库 `dw_onedba` 中，我直接查询。


- 本轮回复: ## 查询结果：role=0 的用户

**数据库**: `dw_onedba`  
**执行 SQL**:
```sql
SELECT id, realname, email, feishu_name FROM account WHERE role = 0 ORDER BY id ASC
```

共返回 **500 条**记录（role=0 为默认普通用户），以下是完整结果：

| 序号 | 
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "查询 role=0 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID升序排列。",
  "table_name": "account"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 查询 role=0 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID升序排列。

**表**: account
... (共 519 行)
     ```

</details>

### TC-022 ✅ — 账户管理：统计每种角色的用户数量。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 账户管理：统计每种角色的用户数量。
- 本轮回复: 用户的问题与历史查询记忆中的第1条高度匹配，我直接基于 `account` 表进行查询。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 账户管理：统计每种角色的用户数量。
- 上一轮回复: 用户的问题与历史查询记忆中的第1条高度匹配，我直接基于 `account` 表进行查询。


- 本轮回复: 根据 `account` 表统计，每种角色的用户数量如下：

| 序号 | role（角色） | 用户数量 |
| --- | --- | --- |
| 1 | 999 | 1 |
| 2 | 6 | 7 |
| 3 | 99 | 15 |
| 4 | 1 | 5,234 |
| 5 | 0 | 53,993 |

**执行的 SQL：**

```sql
SELECT role, COUNT(
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "账户管理：统计每种角色的用户数量，按数量升序排列",
  "table_name": "account"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 账户管理：统计每种角色的用户数量，按数量升序排列

**表**: account
... (共 30 行)
     ```

</details>

### TC-024 ✅ — 工单系统：查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。

<details>
<summary>🧠 LLM 调用记录 (3 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。
- 请求工具: find_table
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。
- 本轮回复: 找到了 `workflow_instance`（审批流实例）和 `order_record`（工单记录），两张表都在当前数据库 `dw_onedba` 中。直接查询：


- 请求工具: query_database
- 最终响应: 否

**第 3 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。
- 上一轮回复: 找到了 `workflow_instance`（审批流实例）和 `order_record`（工单记录），两张表都在当前数据库 `dw_onedba` 中。直接查询：


- 本轮回复: ## 查询结果

查询已成功执行，返回 **500 条**记录，以下是结果概览：

**执行 SQL：**
```sql
SELECT o.id, o.order_type, o.status_desc AS order_status, w.status_desc AS workflow_status 
FROM order_record o 
LEFT JOIN workflow_instanc
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (2 次)</summary>

**1. find_table**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "keyword": "workflow,flow,instance,process",
  "max_results": 50
}
     ```
  📤 输出:
     ```
| schemaId | 数据库名 | 环境 | 表名 | 表注释 |
| --- | --- | --- | --- | --- |
| 25800743 | dw_onedba | test | db_rds_instance_bak |  |
| 25800743 | dw_onedba | test | db_tidb_instance |  |
| 65938636 | dw_onedba | test | workflow_feishu_record | 飞书发送记录 |
... (共 58 行)
     ```

**2. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "工单系统：查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。关联 order_record 和 workflow_instance 表。",
  "table_name": "order_record, workflow_instance"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 工单系统：查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。关联 order_record 和 workflow_instance 表。

**表**: order_record, workflow_instance
... (共 529 行)
     ```

</details>

### TC-025 ✅ — 告警系统：查询 level='critical' 的告警涉及的业务子域（business_subdomain），去重。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：查询 level='critical' 的告警涉及的业务子域（business_subdomain），去重。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：查询 level='critical' 的告警涉及的业务子域（business_subdomain），去重。
- 本轮回复: 查询成功，以下是 `level='critical'` 的告警涉及的业务子域（去重）：

**执行的 SQL：**
```sql
SELECT DISTINCT business_subdomain FROM db_alert_history WHERE level = 'critical' ORDER BY business_subdomain
```

**结果：共 35 个业务子域**

|
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "告警系统：查询 level='critical' 的告警涉及的业务子域（business_subdomain），去重。",
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 告警系统：查询 level='critical' 的告警涉及的业务子域（business_subdomain），去重。

**表**: db_alert_history
... (共 58 行)
     ```

</details>

### TC-027 ✅ — 工单系统：统计每种工单类型的完成率（is_finished=1 的工单数 / 总工单数），按完成率降序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计每种工单类型的完成率（is_finished=1 的工单数 / 总工单数），按完成率降序排列。
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计每种工单类型的完成率（is_finished=1 的工单数 / 总工单数），按完成率降序排列。
- 本轮回复: ## 工单系统：各工单类型完成率

按完成率降序排列，共 20 种工单类型：

| 序号 | 工单类型 | 总工单数 | 已完成数 | 完成率 |
| --- | --- | --- | --- | --- |
| 1 | structureSync | 92 | 86 | **93.48%** |
| 2 | dataExport | 50 | 44 | **88.00%** |
| 3 | d
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "question": "工单系统：统计每种工单类型的完成率（is_finished=1 的工单数 / 总工单数），按完成率降序排列。",
  "schema_id": 65938636,
  "table_name": "order_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 工单系统：统计每种工单类型的完成率（is_finished=1 的工单数 / 总工单数），按完成率降序排列。

**表**: order_record
... (共 43 行)
     ```

</details>

### TC-028 ✅ — 告警系统：使用 CASE WHEN 按月统计 2024 年 4-5 月每天的告警数量，返回日期、4月告警数、5月告警数。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：使用 CASE WHEN 按月统计 2024 年 4-5 月每天的告警数量，返回日期、4月告警数、5月告警数。
- 本轮回复: 根据历史查询记录，`db_alert_history` 表适合这个需求。直接使用 `query_database` 生成并执行查询
- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：使用 CASE WHEN 按月统计 2024 年 4-5 月每天的告警数量，返回日期、4月告警数、5月告警数。
- 上一轮回复: 根据历史查询记录，`db_alert_history` 表适合这个需求。直接使用 `query_database` 生成并执行查询
- 本轮回复: ## 查询结果

执行 SQL：

```sql
SELECT DATE(alert_time) AS alert_date,
       SUM(CASE WHEN MONTH(alert_time) = 4 THEN 1 ELSE 0 END) AS april_count,
       SUM(CASE WHEN MONTH(alert_time) = 5 THEN 1 ELSE 0 E
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "告警系统：使用 CASE WHEN 按月统计 2024 年 4-5 月每天的告警数量，返回日期、4月告警数、5月告警数。按日期升序排列。",
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 告警系统：使用 CASE WHEN 按月统计 2024 年 4-5 月每天的告警数量，返回日期、4月告警数、5月告警数。按日期升序排列。

**表**: db_alert_history
... (共 29 行)
     ```

</details>

### TC-029 ✅ — 告警系统：统计每位DBA（dba_owner 字段）负责的业务域的告警数量，返回DBA标识、业务域、告警数量，按告警数量

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计每位DBA（dba_owner 字段）负责的业务域的告警数量，返回DBA标识、业务域、告警数量，按告警数量降序排列前 20 名。
- 本轮回复: 根据数据底座，`db_alert_history` 表正是用于告警统计的核心表，且你的查询与历史查询类似，直接使用当前数据库 `dw_onedba`。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 告警系统：统计每位DBA（dba_owner 字段）负责的业务域的告警数量，返回DBA标识、业务域、告警数量，按告警数量降序排列前 20 名。
- 上一轮回复: 根据数据底座，`db_alert_history` 表正是用于告警统计的核心表，且你的查询与历史查询类似，直接使用当前数据库 `dw_onedba`。


- 本轮回复: 查询已执行，结果如下：

**SQL 语句**：
```sql
SELECT dba_owner, business_subdomain, COUNT(*) AS alert_count 
FROM db_alert_history 
GROUP BY dba_owner, business_subdomain 
ORDER BY alert_count DESC, dba_owner, busi
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "统计每位DBA（dba_owner 字段）负责的业务域（business_subdomain 字段）的告警数量，返回DBA标识、业务域、告警数量，按告警数量降序排列前 20 名。",
  "table_name": "db_alert_history"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计每位DBA（dba_owner 字段）负责的业务域（business_subdomain 字段）的告警数量，返回DBA标识、业务域、告警数量，按告警数量降序排列前 20 名。

**表**: db_alert_history
... (共 43 行)
     ```

</details>

### TC-030 ✅ — 工单系统：统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量降序排列。

<details>
<summary>🧠 LLM 调用记录 (2 轮)</summary>

**第 1 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量降序排列。
- 本轮回复: 根据历史查询记录，这个需求与之前查询过的"工单类型在各状态下的数量"一致，只是排序方向改为降序。我直接查询。


- 请求工具: query_database
- 最终响应: 否

**第 2 轮** [deepseek-v4-pro-260425]
- 用户问题: 工单系统：统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量降序排列。
- 上一轮回复: 根据历史查询记录，这个需求与之前查询过的"工单类型在各状态下的数量"一致，只是排序方向改为降序。我直接查询。


- 本轮回复: 查询完成。以下是按工单类型和数量降序排列的统计结果：

**实际执行的 SQL：**
```sql
SELECT order_type, status_code AS status, COUNT(*) AS order_count 
FROM order_record 
GROUP BY order_type, status_code 
ORDER BY order_type, order_cou
- 最终响应: 是

</details>

<details>
<summary>🔧 工具调用详情 (1 次)</summary>

**1. query_database**
  ⏱ 耗时: **0ms**
  📥 输入:
     ```json
{
  "schema_id": 65938636,
  "question": "统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量降序排列",
  "table_name": "order_record"
}
     ```
  📤 输出:
     ```
## 查询结果

**问题**: 统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量降序排列

**表**: order_record
... (共 152 行)
     ```

</details>

## 🔬 稳定性分析

标准差越小表示 Agent 对该用例的回答越稳定。

| 用例 | 工具调用 (σ) | Token (σ) | 输入Token (σ) | 输出Token (σ) | 延迟 (σ) | Turns (σ) | 各次工具调用 |
|------|-------------|-----------|--------------|--------------|----------|-----------|-------------|
| TC-001 | ±0.0 | ±162 | ±19 | ±153 | ±3240ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-002 | ±0.0 | ±28 | ±10 | ±27 | ±840ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-003 | ±0.0 | ±38 | ±9 | ±36 | ±2245ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-004 | ±0.0 | ±184 | ±16 | ±180 | ±2155ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-005 | ±0.0 | ±33 | ±17 | ±36 | ±4940ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-006 | ±0.0 | ±54 | ±30 | ±34 | ±3297ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-007 | ±0.0 | ±139 | ±21 | ±134 | ±3059ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-008 | ±0.0 | ±44 | ±22 | ±47 | ±3146ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-009 | ±0.0 | ±41 | ±13 | ±48 | ±1374ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-010 | ±0.0 | ±86 | ±29 | ±95 | ±2269ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-011 | ±0.0 | ±217 | ±27 | ±203 | ±5449ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-012 | ±0.0 | ±44 | ±19 | ±29 | ±2748ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-013 | ±0.0 | ±52 | ±25 | ±40 | ±1304ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-014 | ±0.0 | ±59 | ±38 | ±30 | ±5042ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-015 | ±0.0 | ±99 | ±25 | ±84 | ±2155ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-016 | ±0.0 | ±33 | ±26 | ±19 | ±4147ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-017 | ±0.0 | ±42 | ±11 | ±44 | ±1968ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-018 | ±0.0 | ±62 | ±20 | ±49 | ±3426ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-019 | ±0.0 | ±46 | ±32 | ±42 | ±2205ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-020 | ±0.0 | ±50 | ±12 | ±46 | ±896ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-021 | ±0.0 | ±165 | ±14 | ±159 | ±3541ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-022 | ±0.0 | ±56 | ±18 | ±58 | ±3685ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-024 | ±0.0 | ±3435 | ±3414 | ±172 | ±5560ms | ±0.3 | 2 → 2 → 2 → 2 → 2 → 2 → 2 → 2 |
| TC-025 | ±0.0 | ±76 | ±14 | ±76 | ±2351ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-027 | ±0.0 | ±147 | ±67 | ±85 | ±4329ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-028 | ±0.0 | ±102 | ±51 | ±72 | ±2552ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-029 | ±0.0 | ±72 | ±30 | ±51 | ±5022ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |
| TC-030 | ±0.0 | ±151 | ±30 | ±133 | ±6611ms | ±0.0 | 1 → 1 → 1 → 1 → 1 → 1 → 1 → 1 |

**最不稳定用例**: TC-001 (工具调用 σ=±0.0)
> 工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。
