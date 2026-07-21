# OneDBA NL2SQL 测试数据集 — dw_onedba_cs

> 基于 OneDBA 平台真实数据（dw_onedba_cs @ dw-onedba-t1, schemaId: 24223568）
> 共 20 条测试用例，覆盖告警系统db_alert_history、待办记录等核心业务

---

## 测试前置条件

**评测时 Agent 已处于以下环境中：**

- 当前数据库已选定：`dw_onedba_cs` (schemaId=24223568)
- 无需调用 `list_databases` 或 `select_database` 探索数据库
- 不需要知道任何表名、列名、枚举值——Agent 需要自行从数据库中发现这些信息

**这模拟真实用户场景：** 用户在 OneDBA 平台上点击进入某个数据库后，直接开始用自然语言提问。

---

## 数据库 Schema 速查

```sql
-- db_alert_history: 数据库告警历史 (155648行)
--   id (PK), db_instance_id, db_node_id, description, business_subdomain, metric_name,
--   cur_value, namespace, alert_time, gmt_create, gmt_modify, level, send_message,
--   uuid, message, a1, a2, a3, a4, a5, csong, csong1, lee, cc, aa2

-- todo_record_detail: 待办记录详情 (59行)
--   id (PK), record_type, todo_id, user_id, username, status_code, status_desc,
--   comment, is_finished (INT: 0/1), create_time, update_time

-- dp_permission: 权限表 (0行，空表)
--   id (PK), create_time, modify_time, parent_id, permission_name, permission_url,
--   menu_code, enable, menu_memo, is_show, is_menu, router, rank
```

## 关键枚举值

### db_alert_history.level（告警级别）
| 值 | 说明 |
|---|------|
| ok | 正常 |
| info | 信息 |
| warn | 警告 |
| critical | 严重 |

### db_alert_history.metric_name（告警指标）
| 值 | 说明 |
|---|------|
| DiskUsage | 磁盘使用率 |
| IOPSUsage | IOPS使用率 |
| NodeCPUUtilization | 节点CPU利用率 |
| CpuUsage | CPU使用率 |
| ShardingMemoryUsage | 分片内存使用率 |
| rds001_cpu_util | RDS CPU利用率 |

### db_alert_history.namespace（数据库类型）
| 值 | 说明 |
|---|------|
| 云数据库RDS版（RDS） | MySQL RDS |
| ElasticSearch | ES |
| Redis集群版 | Redis |

### db_alert_history.business_subdomain（业务子域）
| 值 | 说明 |
|---|------|
| 社区后端 | 社区后端 |
| 财务结算 | 财务结算 |
| 大数据 | 大数据 |
| 商品 | 商品 |
| 效率后端 | 效率后端 |
| 仓储域 | 仓储域 |
| 基础架构 | 基础架构 |

### todo_record_detail.record_type（记录类型）
| 值 | 说明 |
|---|------|
| handler | 处理记录 |
| comment | 评论记录 |

### todo_record_detail.status_code（状态码）
| 值 | 说明 |
|---|------|
| accepted | 已确认 |
| completed | 已完成 |
| waitingProcess | 待处理 |
| processing | 处理中 |

### todo_record_detail.is_finished
| 值 | 说明 |
|---|------|
| 0 | 未完成 |
| 1 | 已完成 |

## 时间范围

| 表 | 起始时间 | 结束时间 |
|---|---------|---------|
| db_alert_history | 2022-07-12 | 2022-07-12 |
| todo_record_detail | 2025-04-09 | 2025-04-09 |

---

## 评分标准说明

每条用例包含以下评判维度：

| 维度 | 分值 | 说明 |
|------|------|------|
| SQL 语法正确 | 20% | SQL 可执行、无语法错误 |
| 表/列引用正确 | 20% | 使用了正确的表和列名，无幻觉字段 |
| 过滤条件正确 | 20% | WHERE 条件与预期语义一致（含枚举值正确） |
| 结果数据正确 | 30% | 返回数据行和数值与参考答案一致 |
| SQL 规范 | 10% | 无 SELECT *、有合理 ORDER BY、LIMIT 适当 |

**通过标准**：总分 >= 80% 视为通过；结果数据正确为必须项（不通过则直接不及格）。

---

## 一、告警系统db_alert_history查询（db_alert_history）

---

### CS-001 单表过滤 - 严重告警

**自然语言问题：**
```
告警系统：查询 level='critical' 的告警，返回告警ID、实例ID、指标名称和告警时间，按告警时间降序。
```

**参考答案 SQL：**
```sql
SELECT id, db_instance_id, metric_name, alert_time
FROM db_alert_history
WHERE level = 'critical'
ORDER BY alert_time DESC;
```

**预期结果：**
- 应返回 24576 行（critical 级别告警）
- 所有行的 level 都是 'critical'

**评判要点：**
- 必须使用 `level = 'critical'`
- 排序方向为 DESC
- 不能出现 `SELECT *`

---

### CS-002 单表过滤 - 已发送消息的告警

**自然语言问题：**
```
告警系统：查询 send_message=1 的告警数量。
```

**参考答案 SQL：**
```sql
SELECT COUNT(*) AS sent_count
FROM db_alert_history
WHERE send_message = 1;
```

**预期结果：**
- 应返回单个数值：8192

**评判要点：**
- 必须使用 `send_message = 1`（INT 类型，不要用字符串）
- 结果为 8192

---

### CS-003 聚合 - 各告警级别数量统计

**自然语言问题：**
```
告警系统：统计每种告警级别的数量，按数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT level, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY level
ORDER BY alert_count DESC;
```

**预期结果：**

| level | alert_count |
|-------|-------------|
| ok | 65536 |
| info | 57344 |
| critical | 24576 |
| warn | 8192 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向为 DESC
- 总计 155648 条告警

---

### CS-004 聚合 - 各告警指标数量统计

**自然语言问题：**
```
告警系统：统计每种告警指标的数量，按数量降序排列前 10 名。
```

**参考答案 SQL：**
```sql
SELECT metric_name, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY metric_name
ORDER BY alert_count DESC
LIMIT 10;
```

**预期结果（Top 6）：**

| metric_name | alert_count |
|-------------|-------------|
| DiskUsage | 65536 |
| IOPSUsage | 49152 |
| NodeCPUUtilization | 16384 |
| CpuUsage | 8192 |
| ShardingMemoryUsage | 8192 |
| rds001_cpu_util | 8192 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 必须有 `LIMIT 10`
- 排序方向为 DESC

---

### CS-005 聚合 - 各数据库类型告警数量统计

**自然语言问题：**
```
告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT namespace, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY namespace
ORDER BY alert_count DESC;
```

**预期结果：**

| namespace | alert_count |
|-----------|-------------|
| 云数据库RDS版（RDS） | 131072 |
| ElasticSearch | 16384 |
| Redis集群版 | 8192 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向为 DESC

---

### CS-006 聚合 - 各业务域告警数量统计

**自然语言问题：**
```
告警系统：统计每个业务子域（business_subdomain）的告警数量，按数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT business_subdomain, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY business_subdomain
ORDER BY alert_count DESC;
```

**预期结果：**

| business_subdomain | alert_count |
|--------------------|-------------|
| 社区后端 | 57344 |
| 财务结算 | 32768 |
| 大数据 | 24576 |
| 商品 | 16384 |
| 效率后端 | 8192 |
| 仓储域 | 8192 |
| 基础架构 | 8192 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向为 DESC
- 总计 7 个业务域

---

### CS-007 多条件过滤 - RDS严重告警

**自然语言问题：**
```
告警系统：查询 namespace='云数据库RDS版（RDS）' 且 level='critical' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。
```

**参考答案 SQL：**
```sql
SELECT db_instance_id, metric_name, cur_value, alert_time
FROM db_alert_history
WHERE namespace = '云数据库RDS版（RDS）'
  AND level = 'critical'
ORDER BY alert_time DESC;
```

**预期结果：**
- 应返回多条记录
- 所有行的 namespace 都是 '云数据库RDS版（RDS）'，level 都是 'critical'

**评判要点：**
- 必须同时满足两个 WHERE 条件
- 排序方向为 DESC

---

### CS-008 时间窗口 - 按小时统计告警趋势

**自然语言问题：**
```
告警系统：统计 2022-07-12 当天每小时的告警数量，按小时升序排列。
```

**参考答案 SQL：**
```sql
SELECT DATE_FORMAT(alert_time, '%Y-%m-%d %H:00') AS hour,
       COUNT(*) AS alert_count
FROM db_alert_history
WHERE alert_time >= '2022-07-12'
  AND alert_time < '2022-07-13'
GROUP BY DATE_FORMAT(alert_time, '%Y-%m-%d %H:00')
ORDER BY hour ASC;
```

**预期结果：**
- 应返回 1 行（所有告警数据集中在 2022-07-12 23:00 这个小时，alert_time 范围 23:33:47 ~ 23:38:57）
- 该行计数为 155648

**评判要点：**
- 必须使用 `DATE_FORMAT` 提取小时
- 时间范围过滤使用 `>=` 和 `<` 模式
- 排序方向为 ASC

---

### CS-009 去重查询 - 有告警的实例

**自然语言问题：**
```
告警系统：查询 level='critical' 的告警涉及的所有 db_instance_id，去重，按实例ID升序排列。
```

**参考答案 SQL：**
```sql
SELECT DISTINCT db_instance_id
FROM db_alert_history
WHERE level = 'critical'
ORDER BY db_instance_id ASC;
```

**预期结果：**
- 应返回 1 条记录：`db_instance_id = 'rr-bp15y9mb09arb224v'`
- 所有 critical 级别告警集中在同一个实例上

**评判要点：**
- 必须使用 `DISTINCT`
- 必须使用 `level = 'critical'`
- 排序方向为 ASC

---

### CS-010 排名 - 各业务域内告警指标排名（MySQL 5.7 兼容）

**自然语言问题：**
```
告警系统：查询每个业务域内各告警指标的告警数量，按业务域分组并按告警数量降序排名，返回业务域、指标名、告警数量、排名。
```

**参考答案 SQL（MySQL 5.7 用户变量方式）：**
```sql
SELECT business_subdomain,
       metric_name,
       alert_count,
       rn
FROM (
  SELECT business_subdomain,
         metric_name,
         alert_count,
         @rn := IF(@prev_domain = business_subdomain, @rn + 1, 1) AS rn,
         @prev_domain := business_subdomain
  FROM (
    SELECT business_subdomain, metric_name, COUNT(*) AS alert_count
    FROM db_alert_history
    GROUP BY business_subdomain, metric_name
    ORDER BY business_subdomain, alert_count DESC
  ) AS t,
  (SELECT @rn := 0, @prev_domain := '') AS init
) AS ranked
ORDER BY business_subdomain, rn;
```

**预期结果：**
- 应返回多条记录，每个业务域内的指标按告警数量降序排名
- 排名从 1 开始，同一业务域内排名连续且不重复

**评判要点：**
- 排名结果正确（同一业务域内 alert_count 最大 → rn=1，其次 rn=2，依此类推）
- 不可使用 ROW_NUMBER() OVER() — 当前 MySQL 5.7 不支持

> **平台限制说明**：当前 OneDBA 实例 (schemaId=24223568) 连接的是 **MySQL 5.7.38**，不支持 `ROW_NUMBER() OVER(PARTITION BY ...)` 窗口函数。如需测试窗口函数能力，请在 MySQL 8.0+ 或 TiDB 实例上进行。

---

### CS-011 派生指标 - 告警级别占比

**自然语言问题：**
```
告警系统：统计每种告警级别的数量及占比（该级别告警数 / 总告警数），返回告警级别、数量和百分比，按数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT level,
       COUNT(*) AS alert_count,
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM db_alert_history), 2) AS percentage
FROM db_alert_history
GROUP BY level
ORDER BY alert_count DESC;
```

**预期结果：**
- 应返回 4 行
- 包含百分比计算

**评判要点：**
- 必须使用子查询计算总行数进行占比运算
- 必须正确计算百分比

---

### CS-012 复合查询 - 各业务域各指标告警数量

**自然语言问题：**
```
告警系统：统计每个业务子域下每种告警指标的数量，按业务域和告警数量降序排列，返回业务域、指标名、告警数量。
```

**参考答案 SQL：**
```sql
SELECT business_subdomain,
       metric_name,
       COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY business_subdomain, metric_name
ORDER BY business_subdomain, alert_count DESC;
```

**预期结果：**
- 应返回多条记录
- 按业务域和数量排序

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向正确

---

## 二、待办记录查询（todo_record_detail）

---

### CS-013 单表过滤 - 已完成的待办记录

**自然语言问题：**
```
待办系统：查询 is_finished=1 的待办记录，返回记录ID、待办ID、用户名、状态描述和创建时间，按创建时间降序。
```

**参考答案 SQL：**
```sql
SELECT id, todo_id, username, status_desc, create_time
FROM todo_record_detail
WHERE is_finished = 1
ORDER BY create_time DESC;
```

**预期结果：**
- 应返回多条记录
- 所有行的 is_finished 都是 1

**评判要点：**
- 必须使用 `is_finished = 1`（INT 类型）
- 排序方向为 DESC
- 不能出现 `SELECT *`

---

### CS-014 单表过滤 - 处理记录

**自然语言问题：**
```
待办系统：查询 record_type='handler' 的待办记录数量。
```

**参考答案 SQL：**
```sql
SELECT COUNT(*) AS handler_count
FROM todo_record_detail
WHERE record_type = 'handler';
```

**预期结果：**
- 应返回 58

**评判要点：**
- 必须使用 `record_type = 'handler'`
- 结果是单个数值

---

### CS-015 聚合 - 各状态待办数量统计

**自然语言问题：**
```
待办系统：统计每种状态（status_code 和 status_desc）的待办记录数量，按数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT status_code, status_desc, COUNT(*) AS record_count
FROM todo_record_detail
GROUP BY status_code, status_desc
ORDER BY record_count DESC;
```

**预期结果：**

| status_code | status_desc | record_count |
|-------------|-------------|--------------|
| accepted | 已确认 | 29 |
| completed | 已完成 | 24 |
| waitingProcess | 待处理 | 4 |
| processing | 处理中 | 1 |
| completed | 添加评论 | 1 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 注意 status_code 和 status_desc 需要一起 GROUP BY

---

### CS-016 聚合 - 各用户待办数量统计

**自然语言问题：**
```
待办系统：统计每位用户的待办记录数量，按数量降序排列前 5 名。
```

**参考答案 SQL：**
```sql
SELECT username, COUNT(*) AS record_count
FROM todo_record_detail
GROUP BY username
ORDER BY record_count DESC
LIMIT 5;
```

**预期结果：**
- 应返回 5 行
- 每行包含用户名和记录数量

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 必须有 `LIMIT 5`
- 排序方向为 DESC

---

### CS-017 多条件过滤 - 某用户的已完成记录

**自然语言问题：**
```
待办系统：查询 username='岱影(Win)｜王文' 且 is_finished=1 的待办记录，返回记录ID、待办ID、状态描述和创建时间，按创建时间降序。
```

**参考答案 SQL：**
```sql
SELECT id, todo_id, status_desc, create_time
FROM todo_record_detail
WHERE username = '岱影(Win)｜王文'
  AND is_finished = 1
ORDER BY create_time DESC;
```

**预期结果：**
- 应返回多条记录
- 所有行的 username 都是 '岱影(Win)｜王文'

**评判要点：**
- 必须同时满足两个 WHERE 条件
- 排序方向为 DESC

---

### CS-018 派生指标 - 用户完成率

**自然语言问题：**
```
待办系统：统计每位用户的待办完成率（is_finished=1 的记录数 / 总记录数），返回用户名、总记录数、完成数和完成率，按完成率降序排列。
```

**参考答案 SQL：**
```sql
SELECT username,
       COUNT(*) AS total_count,
       SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) AS finished_count,
       ROUND(SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS finish_rate
FROM todo_record_detail
GROUP BY username
ORDER BY finish_rate DESC;
```

**预期结果：**
- 应返回多条记录
- 包含完成率计算

**评判要点：**
- 必须使用 `CASE WHEN` 进行条件聚合
- 必须正确计算完成率

---

## 三、综合查询

---

### CS-019 时间窗口 - 待办记录按小时分布

**自然语言问题：**
```
待办系统：统计 2025-04-09 当天每小时的待办记录创建数量，按小时升序排列。
```

**参考答案 SQL：**
```sql
SELECT DATE_FORMAT(create_time, '%Y-%m-%d %H:00') AS hour,
       COUNT(*) AS record_count
FROM todo_record_detail
WHERE create_time >= '2025-04-09'
  AND create_time < '2025-04-10'
GROUP BY DATE_FORMAT(create_time, '%Y-%m-%d %H:00')
ORDER BY hour ASC;
```

**预期结果：**
- 应返回多行（2025-04-09 当天有数据的小时）
- 每小时记录数量不等

**评判要点：**
- 必须使用 `DATE_FORMAT` 提取小时
- 时间范围过滤使用 `>=` 和 `<` 模式
- 排序方向为 ASC

---

### CS-020 复合查询 - 各业务域告警严重程度分布

**自然语言问题：**
```
告警系统：统计每个业务子域下各告警级别的数量，返回业务域、告警级别、数量，按业务域和数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT business_subdomain,
       level,
       COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY business_subdomain, level
ORDER BY business_subdomain, alert_count DESC;
```

**预期结果：**
- 应返回多条记录
- 按业务域和数量排序

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向正确

---

## 评分汇总表

| 用例ID | 难度 | 类型 | 涉及表 | 核心考点 |
|--------|------|------|--------|---------|
| CS-001 | Easy | 单表过滤 | db_alert_history | level 枚举值正确性 |
| CS-002 | Easy | 单表过滤 | db_alert_history | send_message INT 类型过滤 |
| CS-003 | Easy | 聚合 | db_alert_history | GROUP BY + COUNT |
| CS-004 | Easy | 聚合 | db_alert_history | GROUP BY + LIMIT |
| CS-005 | Easy | 聚合 | db_alert_history | namespace 聚合 |
| CS-006 | Easy | 聚合 | db_alert_history | business_subdomain 聚合 |
| CS-007 | Medium | 多条件过滤 | db_alert_history | 多条件 AND |
| CS-008 | Medium | 时间窗口 | db_alert_history | DATE_FORMAT 小时聚合 |
| CS-009 | Medium | 去重查询 | db_alert_history | DISTINCT |
| CS-010 | Hard | 排名 | db_alert_history | 用户变量模拟 ROW_NUMBER（MySQL 5.7 兼容） |
| CS-011 | Hard | 派生指标 | db_alert_history | 子查询占比计算 |
| CS-012 | Medium | 复合查询 | db_alert_history | 多字段 GROUP BY |
| CS-013 | Easy | 单表过滤 | todo_record_detail | is_finished 枚举 |
| CS-014 | Easy | 单表过滤 | todo_record_detail | record_type 枚举 |
| CS-015 | Easy | 聚合 | todo_record_detail | 多字段 GROUP BY |
| CS-016 | Medium | 聚合 | todo_record_detail | GROUP BY + LIMIT |
| CS-017 | Medium | 多条件过滤 | todo_record_detail | 多条件 AND |
| CS-018 | Hard | 派生指标 | todo_record_detail | CASE WHEN 完成率 |
| CS-019 | Medium | 时间窗口 | todo_record_detail | DATE_FORMAT 小时聚合 |
| CS-020 | Medium | 复合查询 | db_alert_history | 交叉分析 |

---

## 快速复制区

> 以下区域方便逐条复制用于测试。每条包含「问题」和「参考SQL」两个代码块。

### CS-001

问题：
```
告警系统：查询 level='critical' 的告警，返回告警ID、实例ID、指标名称和告警时间，按告警时间降序。
```

参考SQL：
```sql
SELECT id, db_instance_id, metric_name, alert_time FROM db_alert_history WHERE level = 'critical' ORDER BY alert_time DESC;
```

### CS-002

问题：
```
告警系统：查询 send_message=1 的告警数量。
```

参考SQL：
```sql
SELECT COUNT(*) AS sent_count FROM db_alert_history WHERE send_message = 1;
```

### CS-003

问题：
```
告警系统：统计每种告警级别的数量，按数量降序排列。
```

参考SQL：
```sql
SELECT level, COUNT(*) AS alert_count FROM db_alert_history GROUP BY level ORDER BY alert_count DESC;
```

### CS-004

问题：
```
告警系统：统计每种告警指标的数量，按数量降序排列前 10 名。
```

参考SQL：
```sql
SELECT metric_name, COUNT(*) AS alert_count FROM db_alert_history GROUP BY metric_name ORDER BY alert_count DESC LIMIT 10;
```

### CS-005

问题：
```
告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量降序排列。
```

参考SQL：
```sql
SELECT namespace, COUNT(*) AS alert_count FROM db_alert_history GROUP BY namespace ORDER BY alert_count DESC;
```

### CS-006

问题：
```
告警系统：统计每个业务子域（business_subdomain）的告警数量，按数量降序排列。
```

参考SQL：
```sql
SELECT business_subdomain, COUNT(*) AS alert_count FROM db_alert_history GROUP BY business_subdomain ORDER BY alert_count DESC;
```

### CS-007

问题：
```
告警系统：查询 namespace='云数据库RDS版（RDS）' 且 level='critical' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。
```

参考SQL：
```sql
SELECT db_instance_id, metric_name, cur_value, alert_time FROM db_alert_history WHERE namespace = '云数据库RDS版（RDS）' AND level = 'critical' ORDER BY alert_time DESC;
```

### CS-008

问题：
```
告警系统：统计 2022-07-12 当天每小时的告警数量，按小时升序排列。
```

参考SQL：
```sql
SELECT DATE_FORMAT(alert_time, '%Y-%m-%d %H:00') AS hour, COUNT(*) AS alert_count FROM db_alert_history WHERE alert_time >= '2022-07-12' AND alert_time < '2022-07-13' GROUP BY DATE_FORMAT(alert_time, '%Y-%m-%d %H:00') ORDER BY hour ASC;
```

### CS-009

问题：
```
告警系统：查询 level='critical' 的告警涉及的所有 db_instance_id，去重，按实例ID升序排列。
```

参考SQL：
```sql
SELECT DISTINCT db_instance_id FROM db_alert_history WHERE level = 'critical' ORDER BY db_instance_id ASC;
```

### CS-010

问题：
```
告警系统：查询每个业务域内各告警指标的告警数量，按业务域分组并按告警数量降序排名，返回业务域、指标名、告警数量、排名。
```

参考SQL：
```sql
SELECT business_subdomain, metric_name, alert_count, rn FROM (SELECT business_subdomain, metric_name, alert_count, @rn := IF(@prev_domain = business_subdomain, @rn + 1, 1) AS rn, @prev_domain := business_subdomain FROM (SELECT business_subdomain, metric_name, COUNT(*) AS alert_count FROM db_alert_history GROUP BY business_subdomain, metric_name ORDER BY business_subdomain, alert_count DESC) AS t, (SELECT @rn := 0, @prev_domain := '') AS init) AS ranked ORDER BY business_subdomain, rn;
```

### CS-011

问题：
```
告警系统：统计每种告警级别的数量及占比（该级别告警数 / 总告警数），返回告警级别、数量和百分比，按数量降序排列。
```

参考SQL：
```sql
SELECT level, COUNT(*) AS alert_count, ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM db_alert_history), 2) AS percentage FROM db_alert_history GROUP BY level ORDER BY alert_count DESC;
```

### CS-012

问题：
```
告警系统：统计每个业务子域下每种告警指标的数量，按业务域和告警数量降序排列，返回业务域、指标名、告警数量。
```

参考SQL：
```sql
SELECT business_subdomain, metric_name, COUNT(*) AS alert_count FROM db_alert_history GROUP BY business_subdomain, metric_name ORDER BY business_subdomain, alert_count DESC;
```

### CS-013

问题：
```
待办系统：查询 is_finished=1 的待办记录，返回记录ID、待办ID、用户名、状态描述和创建时间，按创建时间降序。
```

参考SQL：
```sql
SELECT id, todo_id, username, status_desc, create_time FROM todo_record_detail WHERE is_finished = 1 ORDER BY create_time DESC;
```

### CS-014

问题：
```
待办系统：查询 record_type='handler' 的待办记录数量。
```

参考SQL：
```sql
SELECT COUNT(*) AS handler_count FROM todo_record_detail WHERE record_type = 'handler';
```

### CS-015

问题：
```
待办系统：统计每种状态（status_code 和 status_desc）的待办记录数量，按数量降序排列。
```

参考SQL：
```sql
SELECT status_code, status_desc, COUNT(*) AS record_count FROM todo_record_detail GROUP BY status_code, status_desc ORDER BY record_count DESC;
```

### CS-016

问题：
```
待办系统：统计每位用户的待办记录数量，按数量降序排列前 5 名。
```

参考SQL：
```sql
SELECT username, COUNT(*) AS record_count FROM todo_record_detail GROUP BY username ORDER BY record_count DESC LIMIT 5;
```

### CS-017

问题：
```
待办系统：查询 username='岱影(Win)｜王文' 且 is_finished=1 的待办记录，返回记录ID、待办ID、状态描述和创建时间，按创建时间降序。
```

参考SQL：
```sql
SELECT id, todo_id, status_desc, create_time FROM todo_record_detail WHERE username = '岱影(Win)｜王文' AND is_finished = 1 ORDER BY create_time DESC;
```

### CS-018

问题：
```
待办系统：统计每位用户的待办完成率（is_finished=1 的记录数 / 总记录数），返回用户名、总记录数、完成数和完成率，按完成率降序排列。
```

参考SQL：
```sql
SELECT username, COUNT(*) AS total_count, SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) AS finished_count, ROUND(SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS finish_rate FROM todo_record_detail GROUP BY username ORDER BY finish_rate DESC;
```

### CS-019

问题：
```
待办系统：统计 2025-04-09 当天每小时的待办记录创建数量，按小时升序排列。
```

参考SQL：
```sql
SELECT DATE_FORMAT(create_time, '%Y-%m-%d %H:00') AS hour, COUNT(*) AS record_count FROM todo_record_detail WHERE create_time >= '2025-04-09' AND create_time < '2025-04-10' GROUP BY DATE_FORMAT(create_time, '%Y-%m-%d %H:00') ORDER BY hour ASC;
```

### CS-020

问题：
```
告警系统：统计每个业务子域下各告警级别的数量，返回业务域、告警级别、数量，按业务域和数量降序排列。
```

参考SQL：
```sql
SELECT business_subdomain, level, COUNT(*) AS alert_count FROM db_alert_history GROUP BY business_subdomain, level ORDER BY business_subdomain, alert_count DESC;
```