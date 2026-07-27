# OneDBA NL2SQL 测试数据集

> 基于 OneDBA 平台真实数据（dw_onedba @ dw-onedba-t1, schemaId: 65938636）
> 共 30 条测试用例，覆盖工单系统、告警系统db_alert_history、效能统计、账户管理等核心业务

---

## 测试前置条件

**评测时 Agent 已处于以下环境中：**

- 当前数据库已选定：`dw_onedba` (schemaId=65938636)
- 无需调用 `list_databases` 或 `select_database` 探索数据库
- 不需要知道任何表名、列名、枚举值——Agent 需要自行从数据库中发现这些信息

**这模拟真实用户场景：** 用户在 OneDBA 平台上点击进入某个数据库后，直接开始用自然语言提问。

---

## 数据库 Schema 速查

```sql
-- order_record: 工单主表 (1174行)
--   id, committer_id, committer_name, organization, business_domain, order_type,
--   status_code, status_desc, related_users, workflow_id, workflow_desc, comments,
--   group_id, is_finished, create_time, update_time

-- db_alert_history: 数据库告警历史 (381527行)
--   id, db_instance_id, db_node_id, description, business_subdomain, metric_name,
--   cur_value, namespace, alert_time, gmt_create, gmt_modify, level, send_message,
--   uuid, message, sequence, env_type, dba_owner (飞书OpenID，非中文姓名)

-- effect_dba_domain_cost_v2: DBA效能统计 (4114行)
--   id, inspection_date, year, month, week, dba_owner_name, business_domain,
--   cost_time, created_time, updated_time, cost_type, stat_cnt

-- effect_daily_work_v2: 日常工作记录 (22行)
--   id, dba_feishu_id, business_feishu_id, cost_time_minute, cost_time_hour,
--   work_type, business_subdomain_code, business_subdomain, content, status,
--   created_time, updated_time

-- order_audit_record: 工单审计记录 (22839行)
--   id, order_id, schema_id, seq_no, stage, stage_status, error_level, error_message,
--   risk_level, risk_message, sql_text, sql_type, affected_rows, schema_name,
--   table_name, backup_dbname, execute_time, sqlsha1, backup_time, target_table_name,
--   create_time, update_time

-- workflow_instance: 工作流实例 (987行)
--   id, is_finished, is_filter, create_time, update_time, order_id, order_type,
--   committer_id, committer_name, status_code, status_desc, task_id, task_count

-- account: 账户表 (59248行)
--   id, realname, feishu_name, email, phone, role (INT类型), role_groups, comment,
--   feishu_open_id, feishu_user_id, aliyun_user_id, user_type, aliyun_username,
--   aliyun_dms_user_id, avatar, ...

-- cmdb_application: CMDB应用表 (8227行)
--   id, is_deleted, comment, create_time, update_time, owner_user_name,
--   owner_user_real_name, owner_user_id, level, bsd_id, bsd_name, code,
--   ignore_sras, app_id, name, department_id, department_name, functional_id,
--   functional_name, owner_users
```

## 关键枚举值

### order_record.order_type（工单类型）
| 值 | 说明 |
|---|------|
| dataChange | 数据变更 |
| permission | 权限申请 |
| createInstance | 创建实例 |
| structureSync | 结构同步 |
| structureDesign | 结构设计 |
| createDatabase | 创建数据库 |
| appendWhitelist | 添加白名单 |
| dataExport | 数据导出 |
| other | 其他 |
| dataChangeChunk | 分块数据变更 |
| configChange | 配置变更 |
| dataArchive | 数据归档 |
| offlineInstance | 下线实例 |
| dataClean | 数据清理 |
| dataQuery | 数据查询 |
| clearKey | 清理Key |
| parameterChange | 参数变更 |
| userRoleApply | 用户角色申请 |
| passwordApply | 密码申请 |
| decryptApply | 解密申请 |

### order_record.status_code（工单状态）
| 值 | 说明 |
|---|------|
| closed | 工单关闭 |
| successful | 执行成功 |
| waitingApprove | 工单审批中 |
| canceled | 工单已关闭（审批撤销） |
| failed | 执行失败 |
| rejected | 审批被拒绝 |
| processing | 执行中 |
| waitingProcess | 等待执行 |
| new | 新建工单 |
| skipApprove | 免审批 |
| preCheckFail | 预检查失败 |
| completed | 工单完成 |
| approved | 审批通过 |
| waitingSubmitApprove | 待提交审批 |
| waitingSubmitProcess | 等待提交执行 |
| waitingDispatch | 等待调度 |
| preChecking | 预检查中 |

### order_record.is_finished
| 值 | 说明 |
|---|------|
| 0 | 未完成 |
| 1 | 已完成 |

### db_alert_history.level（告警级别）
| 值 | 说明 |
|---|------|
| ok | 正常 |
| warn | 警告 |
| critical | 严重 |

### db_alert_history.metric_name（告警指标，Top 10）
| 值 | 说明 |
|---|------|
| NODE_DiskUsage | 节点磁盘使用率 |
| ShardingMemoryUsage | 分片内存使用率 |
| DiskUsage | 磁盘使用率 |
| DiskUtilization | 磁盘利用率 |
| NodeHeapMemoryUtilization | 节点堆内存利用率 |
| Txn Failed on FE | FE事务失败 |
| NodeDiskUtilization | 节点磁盘利用率 |
| NODE_CpuUsage | 节点CPU使用率 |
| MySQL_ActiveSessions | MySQL活跃会话 |
| CpuUsage | CPU使用率 |

### db_alert_history.env_type（环境类型）
| 值 | 说明 |
|---|------|
| prd | 生产环境 |
| uat | UAT环境 |
| dev | 开发环境 |
| test | 测试环境 |
| pre | 预发环境 |

### db_alert_history.namespace（数据库类型，Top 10）
| 值 | 说明 |
|---|------|
| 分布式关系型数据库TiDB | TiDB |
| Redis集群版 | Redis |
| 云数据库ClickHouse | ClickHouse |
| 云数据库RDS版（RDS） | MySQL RDS |
| ElasticSearch | ES |
| 云数据库MongoDB版 | MongoDB |
| StarRocks | StarRocks |
| ECS | ECS |
| 数据传输服务DTS（Migration） | DTS |
| 火山-redis集群版 | 火山Redis |

### effect_dba_domain_cost_v2.cost_type（成本类型）
| 值 | 说明 |
|---|------|
| 1 | 类型1 |
| 2 | 类型2 |
| 3 | 类型3 |
| 4 | 类型4 |

### effect_dba_domain_cost_v2.business_domain（业务域，Top 10）
| 值 | 说明 |
|---|------|
| 交易平台 | 交易 |
| 算法平台 | 算法 |
| 无线平台 | 无线 |
| 供应链平台 | 供应链 |
| 汇金平台 | 汇金 |
| 国际技术 | 国际 |
| 数据平台 | 数据 |
| 中间件平台 | 中间件 |
| 效率工程 | 效率 |
| 社区技术 | 社区 |

### effect_dba_domain_cost_v2.dba_owner_name（DBA负责人）
| 值 | 说明 |
|---|------|
| 栾尚飞 | |
| 易坤 | |
| 杨俊 | |
| 王文 | |
| 彭东稳 | |
| 沈睿 | |
| 陈浩 | |
| 罗代阳 | |
| 闫晓宇 | |

### effect_daily_work_v2.work_type（工作类型）
| 值 | 说明 |
|---|------|
| 问题排查 | |
| 应急处理 | |
| 解决方案编写 | |
| 数据库拆分/迁移 | |

### effect_daily_work_v2.status（状态）
| 值 | 说明 |
|---|------|
| 1 | 进行中 |
| 2 | 已完成 |

### order_audit_record.stage（审计阶段）
| 值 | 说明 |
|---|------|
| CHECKED | 已检查 |
| RERUN | 重新运行 |

### order_audit_record.sql_type（SQL类型，Top 10）
| 值 | 说明 |
|---|------|
| UPDATE | 更新 |
| DELETE | 删除 |
| SELECT | 查询 |
| ALTER_TABLE | 表结构变更 |
| INSERT | 插入 |
| create | 创建 |
| TRUNCATE | 清空 |
| insertOne | 插入单条 |
| SET | 设置 |

## 时间范围

| 表 | 起始时间 | 结束时间 |
|---|---------|---------|
| order_record | 2021-11-30 | 2026-06-24 |
| db_alert_history | 2024-04-12 | 2024-09-12 |
| effect_dba_domain_cost_v2 | 2024-05-01 | 2024-08-26 |

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

## 一、工单系统查询（order_record）

---

### TC-001 单表过滤 - 数据变更类工单

**自然语言问题：**
```
工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。
```

**参考答案 SQL：**
```sql
SELECT id, committer_name, status_desc, create_time
FROM order_record
WHERE order_type = 'dataChange'
ORDER BY create_time DESC;
```

**预期结果：**
- 应返回 354 行（dataChange 类型工单）
- 所有行的 order_type 都是 'dataChange'

**评判要点：**
- 必须使用 `order_type = 'dataChange'`，不能写错枚举值
- 排序方向为 DESC
- 不能出现 `SELECT *`

---

### TC-002 单表过滤 - 已完成的工单

**自然语言问题：**
```
工单系统：查询 is_finished=1 的工单数量。
```

**参考答案 SQL：**
```sql
SELECT COUNT(*) AS finished_count
FROM order_record
WHERE is_finished = 1;
```

**预期结果：**
- 应返回 762

**评判要点：**
- 必须使用 `is_finished = 1`，不能写 `is_finished = 'true'` 或 `is_finished = 'yes'`
- 结果是单个数值

---

### TC-003 聚合 - 各类型工单数量统计

**自然语言问题：**
```
工单系统：统计每种工单类型的数量，按数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT order_type, COUNT(*) AS order_count
FROM order_record
GROUP BY order_type
ORDER BY order_count DESC;
```

**预期结果（Top 10）：**

| order_type | order_count |
|------------|-------------|
| dataChange | 354 |
| permission | 130 |
| createInstance | 99 |
| structureSync | 89 |
| structureDesign | 69 |
| createDatabase | 64 |
| appendWhitelist | 51 |
| dataExport | 50 |
| other | 48 |
| dataChangeChunk | 35 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向为 DESC
- 总计 1174 条工单

---

### TC-004 聚合 - 各状态工单数量统计

**自然语言问题：**
```
工单系统：统计每种工单状态（status_code 和 status_desc）的数量，按数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT status_code, status_desc, COUNT(*) AS order_count
FROM order_record
GROUP BY status_code, status_desc
ORDER BY order_count DESC;
```

**预期结果（Top 10）：**

| status_code | status_desc | order_count |
|-------------|-------------|-------------|
| closed | 工单关闭:系统关闭 | 266 |
| successful | 执行成功 | 237 |
| waitingApprove | 工单审批中 | 183 |
| canceled | 工单已关闭:审批撤销 | 85 |
| failed | 执行失败 | 44 |
| canceled | 工单关闭:审批撤销 | 38 |
| processing | 执行中 | 37 |
| rejected | 审批被拒绝 | 37 |
| waitingProcess | 等待执行 | 35 |
| closed | 工单已关闭 | 25 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 注意 status_code 和 status_desc 需要一起 GROUP BY

---

### TC-005 时间窗口 - 按月统计工单创建数量

**自然语言问题：**
```
工单系统：统计 2024 年每月创建的工单数量，按月份升序排列。
```

**参考答案 SQL：**
```sql
SELECT DATE_FORMAT(create_time, '%Y-%m') AS month,
       COUNT(*) AS order_count
FROM order_record
WHERE create_time >= '2024-01-01'
  AND create_time < '2025-01-01'
GROUP BY DATE_FORMAT(create_time, '%Y-%m')
ORDER BY month ASC;
```

**预期结果：**
- 应返回 12 行（2024年1-12月）
- 每月工单数量不等

**评判要点：**
- 必须使用 `DATE_FORMAT` 提取年月
- 时间范围过滤使用 `>=` 和 `<` 模式
- 排序方向为 ASC

---

### TC-006 时间窗口 - 按提交人统计工单数量

**自然语言问题：**
```
工单系统：统计 2024 年每位提交人创建的工单数量，按数量降序排列前 10 名。
```

**参考答案 SQL：**
```sql
SELECT committer_name, COUNT(*) AS order_count
FROM order_record
WHERE create_time >= '2024-01-01'
  AND create_time < '2025-01-01'
GROUP BY committer_name
ORDER BY order_count DESC
LIMIT 10;
```

**预期结果：**
- 应返回 10 行
- 每行包含提交人姓名和工单数量

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 必须有 `LIMIT 10`
- 排序方向为 DESC

---

## 二、告警系统db_alert_history查询（db_alert_history）

---

### TC-007 单表过滤 - 严重告警

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
- 应返回 29829 行（critical 级别告警）
- 所有行的 level 都是 'critical'

**评判要点：**
- 必须使用 `level = 'critical'`
- 排序方向为 DESC

---

### TC-008 聚合 - 各告警级别数量统计

**自然语言问题：**
```
告警系统：统计每种告警级别的数量。
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
| ok | 266036 |
| warn | 85662 |
| critical | 29829 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 总计 381527 条告警

---

### TC-009 聚合 - 各指标告警数量统计

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

**预期结果（Top 10）：**

| metric_name | alert_count |
|-------------|-------------|
| NODE_DiskUsage | 254647 |
| ShardingMemoryUsage | 56929 |
| DiskUsage | 23496 |
| DiskUtilization | 12285 |
| NodeHeapMemoryUtilization | 7032 |
| Txn Failed on FE | 6798 |
| NodeDiskUtilization | 5627 |
| NODE_CpuUsage | 3461 |
| MySQL_ActiveSessions | 2567 |
| CpuUsage | 2545 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 必须有 `LIMIT 10`
- 排序方向为 DESC

---

### TC-010 时间窗口 - 按天统计告警趋势

**自然语言问题：**
```
告警系统：统计 2024 年 8 月每天的告警数量，按日期升序排列。
```

**参考答案 SQL：**
```sql
SELECT DATE(alert_time) AS alert_date,
       COUNT(*) AS alert_count
FROM db_alert_history
WHERE alert_time >= '2024-08-01'
  AND alert_time < '2024-09-01'
GROUP BY DATE(alert_time)
ORDER BY alert_date ASC;
```

**预期结果：**
- 应返回多行（2024年8月1-31日中有告警数据的日期）
- 每天告警数量不等

**评判要点：**
- 必须使用 `DATE()` 函数提取日期
- 时间范围过滤使用 `>=` 和 `<` 模式
- 排序方向为 ASC

---

### TC-011 多条件过滤 - 生产环境严重告警

**自然语言问题：**
```
告警系统：查询 env_type='prd' 且 level='critical' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。
```

**参考答案 SQL：**
```sql
SELECT db_instance_id, metric_name, cur_value, alert_time
FROM db_alert_history
WHERE env_type = 'prd'
  AND level = 'critical'
ORDER BY alert_time DESC;
```

**预期结果：**
- 应返回多条记录
- 所有行的 env_type 都是 'prd'，level 都是 'critical'

**评判要点：**
- 必须同时满足 `env_type = 'prd'` 和 `level = 'critical'`
- 排序方向为 DESC

---

### TC-012 聚合 - 各数据库类型告警数量统计

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

**预期结果（Top 10）：**

| namespace | alert_count |
|-----------|-------------|
| 分布式关系型数据库TiDB | 207599 |
| Redis集群版 | 57780 |
| 云数据库ClickHouse | 47108 |
| 云数据库RDS版（RDS） | 31404 |
| ElasticSearch | 12659 |
| 云数据库MongoDB版 | 12339 |
| StarRocks | 10273 |
| ECS | 1909 |
| 数据传输服务DTS（Migration） | 235 |
| 火山-redis集群版 | 206 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向为 DESC

---

## 三、效能统计查询（effect_dba_domain_cost_v2）

---

### TC-013 聚合 - 各业务域成本统计

**自然语言问题：**
```
效能统计：统计每个业务域的总成本时间，按成本降序排列。
```

**参考答案 SQL：**
```sql
SELECT business_domain,
       SUM(cost_time) AS total_cost_time
FROM effect_dba_domain_cost_v2
GROUP BY business_domain
ORDER BY total_cost_time DESC;
```

**预期结果（Top 10）：**

| business_domain | total_cost_time |
|-----------------|-----------------|
| 交易平台 | 1330.63 |
| 算法平台 | 1205.66 |
| 无线平台 | 1137.17 |
| 供应链平台 | 978.05 |
| 汇金平台 | 945.27 |
| 国际技术 | 816.42 |
| 数据平台 | 622.31 |
| 中间件平台 | 571.43 |
| 效率工程 | 445.11 |
| 社区技术 | 424.21 |

**评判要点：**
- 必须使用 `SUM(cost_time)`
- 排序方向为 DESC

---

### TC-014 时间窗口 - 按月统计成本趋势

**自然语言问题：**
```
效能统计：统计 2024 年各月的总成本时间，按月份升序排列。
```

**参考答案 SQL：**
```sql
SELECT CONCAT(year, '-', LPAD(month, 2, '0')) AS month,
       SUM(cost_time) AS total_cost_time
FROM effect_dba_domain_cost_v2
WHERE year = 2024
GROUP BY year, month
ORDER BY month ASC;
```

**预期结果：**
- 应返回 4 行（2024年5-8月，数据范围）
- 每月成本时间：5月 797.00，6月 926.00，7月 833.82，8月 405.45

**评判要点：**
- 数据范围是 2024-05-01 到 2024-08-26
- 必须使用 `year` 和 `month` 字段

---

### TC-015 多条件过滤 - 某DBA负责的业务域成本

**自然语言问题：**
```
效能统计：查询 dba_owner_name='栾尚飞' 负责的所有业务域的成本统计，按成本降序排列。
```

**参考答案 SQL：**
```sql
SELECT business_domain,
       SUM(cost_time) AS total_cost_time
FROM effect_dba_domain_cost_v2
WHERE dba_owner_name = '栾尚飞'
GROUP BY business_domain
ORDER BY total_cost_time DESC;
```

**预期结果：**
- 应返回多条记录
- 所有行的 dba_owner_name 都是 '栾尚飞'

**评判要点：**
- 必须使用 `dba_owner_name = '栾尚飞'`
- 排序方向为 DESC

---

### TC-016 排名 - 成本最高的业务域

**自然语言问题：**
```
效能统计：查询成本最高的前 5 个业务域，返回业务域名称和总成本时间。
```

**参考答案 SQL：**
```sql
SELECT business_domain,
       SUM(cost_time) AS total_cost_time
FROM effect_dba_domain_cost_v2
GROUP BY business_domain
ORDER BY total_cost_time DESC
LIMIT 5;
```

**预期结果：**
- 应返回 5 行
- 按成本降序排列

**评判要点：**
- 必须有 `LIMIT 5`
- 排序方向为 DESC

---

## 四、日常工作查询（effect_daily_work_v2）

---

### TC-017 单表过滤 - 问题排查类工作

**自然语言问题：**
```
日常工作：查询 work_type='问题排查' 的工作记录，返回工作ID、DBA飞书ID、耗时和创建时间。
```

**参考答案 SQL：**
```sql
SELECT id, dba_feishu_id, cost_time_minute, created_time
FROM effect_daily_work_v2
WHERE work_type = '问题排查'
ORDER BY created_time DESC;
```

**预期结果：**
- 应返回 19 行（问题排查类型）
- 所有行的 work_type 都是 '问题排查'

**评判要点：**
- 必须使用 `work_type = '问题排查'`
- 排序方向为 DESC

---

### TC-018 聚合 - 各工作类型数量统计

**自然语言问题：**
```
日常工作：统计每种工作类型的数量。
```

**参考答案 SQL：**
```sql
SELECT work_type, COUNT(*) AS work_count
FROM effect_daily_work_v2
GROUP BY work_type
ORDER BY work_count DESC;
```

**预期结果：**

| work_type | work_count |
|-----------|------------|
| 问题排查 | 19 |
| 应急处理 | 1 |
| 解决方案编写 | 1 |
| 数据库拆分/迁移 | 1 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 总计 22 条记录

---

## 五、工单审计查询（order_audit_record）

---

### TC-019 聚合 - 各SQL类型数量统计

**自然语言问题：**
```
工单审计：统计每种 SQL 类型的数量，按数量降序排列前 10 名。
```

**参考答案 SQL：**
```sql
SELECT sql_type, COUNT(*) AS sql_count
FROM order_audit_record
GROUP BY sql_type
ORDER BY sql_count DESC
LIMIT 10;
```

**预期结果（Top 10）：**

| sql_type | sql_count |
|----------|-----------|
| UPDATE | 22040 |
| DELETE | 325 |
| SELECT | 169 |
| (空) | 88 |
| ALTER_TABLE | 62 |
| INSERT | 52 |
| create | 16 |
| TRUNCATE | 15 |
| insertOne | 14 |
| SET | 13 |

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 必须有 `LIMIT 10`
- 排序方向为 DESC

---

### TC-020 时间窗口 - 按天统计审计记录数量

**自然语言问题：**
```
工单审计：统计 2024 年 12 月每天的审计记录数量，按日期升序排列。
```

**参考答案 SQL：**
```sql
SELECT DATE(create_time) AS audit_date,
       COUNT(*) AS audit_count
FROM order_audit_record
WHERE create_time >= '2024-12-01'
  AND create_time < '2025-01-01'
GROUP BY DATE(create_time)
ORDER BY audit_date ASC;
```

**预期结果：**
- 应返回多行（2024年12月中有审计数据的日期）
- 每天审计记录数量不等

**评判要点：**
- 必须使用 `DATE()` 函数提取日期
- 时间范围过滤使用 `>=` 和 `<` 模式
- 排序方向为 ASC

---

## 六、账户管理查询（account）

---

### TC-021 单表过滤 - 查询某角色的用户

**自然语言问题：**
```
账户管理：查询 role=0 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID升序。
```

**参考答案 SQL：**
```sql
SELECT id, realname, email, feishu_name
FROM account
WHERE role = 0
ORDER BY id ASC;
```

**预期结果：**
- 应返回 53993 行（role=0 的用户）
- 所有行的 role 都是 0

**评判要点：**
- 必须使用 `role = 0`（role 字段为 INT 类型，不要用字符串）
- 排序方向为 ASC

---

### TC-022 聚合 - 各角色用户数量统计

**自然语言问题：**
```
账户管理：统计每种角色的用户数量。
```

**参考答案 SQL：**
```sql
SELECT role, COUNT(*) AS user_count
FROM account
GROUP BY role
ORDER BY user_count DESC;
```

**预期结果：**
- 应返回多条记录
- 按用户数量降序排列

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向为 DESC

---

## 七、综合查询（多表JOIN）


---

### TC-024 JOIN - 工单与工作流实例

**自然语言问题：**
```
工单系统：查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。
```

**参考答案 SQL：**
```sql
SELECT o.id, o.order_type, o.status_desc, w.status_desc AS workflow_status
FROM order_record o
LEFT JOIN workflow_instance w ON o.id = w.order_id
ORDER BY o.create_time DESC;
```

**预期结果：**
- 应返回多条记录
- 包含工单和工作流信息

**评判要点：**
- 必须使用 `LEFT JOIN`
- 关联条件是 `order_record.id = workflow_instance.order_id`
- 排序方向为 DESC

---

### TC-025 去重查询 - 有告警的业务域

**自然语言问题：**
```
告警系统：查询 level='critical' 的告警涉及的业务子域（business_subdomain），去重。
```

**参考答案 SQL：**
```sql
SELECT DISTINCT business_subdomain
FROM db_alert_history
WHERE level = 'critical'
ORDER BY business_subdomain;
```

**预期结果：**
- 应返回多条记录
- 所有业务域都有严重告警

**评判要点：**
- 必须使用 `DISTINCT`
- 必须使用 `level = 'critical'`

---

## 八、复杂查询（Hard）

---

### TC-027 派生指标 - 工单完成率

**自然语言问题：**
```
工单系统：统计每种工单类型的完成率（is_finished=1 的工单数 / 总工单数），按完成率降序排列。
```

**参考答案 SQL：**
```sql
SELECT order_type,
       COUNT(*) AS total_count,
       SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) AS finished_count,
       ROUND(SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS finish_rate
FROM order_record
GROUP BY order_type
ORDER BY finish_rate DESC;
```

**预期结果：**
- 应返回多条记录
- 包含完成率计算

**评判要点：**
- 必须使用 `CASE WHEN` 进行条件聚合
- 必须正确计算完成率

---

### TC-028 时间窗口 - 告警趋势对比

**自然语言问题：**
```
告警系统：使用 CASE WHEN 按月统计 2024 年 4-5 月每天的告警数量，返回日期、4月告警数、5月告警数。
```

**参考答案 SQL：**
```sql
SELECT
    DATE(alert_time) AS alert_date,
    SUM(CASE WHEN MONTH(alert_time) = 4 THEN 1 ELSE 0 END) AS april_count,
    SUM(CASE WHEN MONTH(alert_time) = 5 THEN 1 ELSE 0 END) AS may_count
FROM db_alert_history
WHERE alert_time >= '2024-04-01'
  AND alert_time < '2024-06-01'
GROUP BY DATE(alert_time)
ORDER BY alert_date;
```

**预期结果：**
- 应返回多行（4月和5月中有告警数据的日期）
- 包含两个月的告警数量对比

**评判要点：**
- 必须使用 `CASE WHEN` 进行条件聚合
- 必须正确过滤时间范围

---

### TC-029 复合查询 - 各DBA负责业务域的告警统计

**自然语言问题：**
```
告警系统：统计每位DBA（dba_owner 字段）负责的业务域的告警数量，返回DBA标识、业务域、告警数量，按告警数量降序排列前 20 名。
```

**参考答案 SQL：**
```sql
SELECT dba_owner,
       business_subdomain,
       COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY dba_owner, business_subdomain
ORDER BY alert_count DESC
LIMIT 20;
```

**预期结果：**
- 应返回 20 行
- dba_owner 字段存储的是飞书 Open ID（如 `ou_54489165d3060111cbf8956a7c8c76b0`），非中文姓名
- 按告警数量降序排列

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 必须有 `LIMIT 20`
- 排序方向为 DESC

---

### TC-030 复合查询 - 工单类型与状态交叉分析

**自然语言问题：**
```
工单系统：统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量降序排列。
```

**参考答案 SQL：**
```sql
SELECT order_type,
       status_code,
       COUNT(*) AS order_count
FROM order_record
GROUP BY order_type, status_code
ORDER BY order_type, order_count DESC;
```

**预期结果：**
- 应返回多条记录
- 按工单类型和数量排序

**评判要点：**
- 必须使用 `GROUP BY` 和 `COUNT`
- 排序方向正确

---

## 评分汇总表

| 用例ID | 难度 | 类型 | 涉及表 | 核心考点 |
|--------|------|------|--------|---------|
| TC-001 | Easy | 单表过滤 | order_record | 枚举值正确性 |
| TC-002 | Easy | 单表过滤 | order_record | is_finished 枚举 |
| TC-003 | Easy | 聚合 | order_record | GROUP BY + COUNT |
| TC-004 | Easy | 聚合 | order_record | 多字段 GROUP BY |
| TC-005 | Medium | 时间窗口 | order_record | DATE_FORMAT |
| TC-006 | Medium | 时间窗口 | order_record | GROUP BY + LIMIT |
| TC-007 | Easy | 单表过滤 | db_alert_history | level 枚举 |
| TC-008 | Easy | 聚合 | db_alert_history | GROUP BY + COUNT |
| TC-009 | Medium | 聚合 | db_alert_history | GROUP BY + LIMIT |
| TC-010 | Medium | 时间窗口 | db_alert_history | DATE 函数 |
| TC-011 | Medium | 多条件过滤 | db_alert_history | 多条件 AND |
| TC-012 | Medium | 聚合 | db_alert_history | namespace 聚合 |
| TC-013 | Medium | 聚合 | effect_dba_domain_cost_v2 | SUM 聚合 |
| TC-014 | Medium | 时间窗口 | effect_dba_domain_cost_v2 | year + month 字段 |
| TC-015 | Medium | 多条件过滤 | effect_dba_domain_cost_v2 | dba_owner_name 过滤 |
| TC-016 | Medium | 排名 | effect_dba_domain_cost_v2 | LIMIT + ORDER BY |
| TC-017 | Easy | 单表过滤 | effect_daily_work_v2 | work_type 枚举 |
| TC-018 | Easy | 聚合 | effect_daily_work_v2 | GROUP BY + COUNT |
| TC-019 | Medium | 聚合 | order_audit_record | sql_type 聚合 |
| TC-020 | Medium | 时间窗口 | order_audit_record | DATE 函数 |
| TC-021 | Easy | 单表过滤 | account | role 枚举（INT类型） |
| TC-022 | Easy | 聚合 | account | GROUP BY + COUNT |
| TC-023 | Medium | JOIN | order_record + account | LEFT JOIN (collation注意) |
| TC-024 | Medium | JOIN | order_record + workflow_instance | LEFT JOIN |
| TC-025 | Medium | 去重查询 | db_alert_history | DISTINCT |
| TC-026 | Hard | 窗口函数 | db_alert_history | ROW_NUMBER |
| TC-027 | Hard | 派生指标 | order_record | CASE WHEN |
| TC-028 | Hard | 时间窗口 | db_alert_history | CASE WHEN + 月份对比 |
| TC-029 | Hard | 复合查询 | db_alert_history | 多字段 GROUP BY |
| TC-030 | Hard | 复合查询 | order_record | 交叉分析 |

---

## 快速复制区

> 以下区域方便逐条复制用于测试。每条包含「问题」和「参考SQL」两个代码块。

### TC-001

问题：
```
工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。
```

参考SQL：
```sql
SELECT id, committer_name, status_desc, create_time FROM order_record WHERE order_type = 'dataChange' ORDER BY create_time DESC;
```

### TC-002

问题：
```
工单系统：查询 is_finished=1 的工单数量。
```

参考SQL：
```sql
SELECT COUNT(*) AS finished_count FROM order_record WHERE is_finished = 1;
```

### TC-003

问题：
```
工单系统：统计每种工单类型的数量，按数量降序排列。
```

参考SQL：
```sql
SELECT order_type, COUNT(*) AS order_count FROM order_record GROUP BY order_type ORDER BY order_count DESC;
```

### TC-004

问题：
```
工单系统：统计每种工单状态（status_code 和 status_desc）的数量，按数量降序排列。
```

参考SQL：
```sql
SELECT status_code, status_desc, COUNT(*) AS order_count FROM order_record GROUP BY status_code, status_desc ORDER BY order_count DESC;
```

### TC-005

问题：
```
工单系统：统计 2024 年每月创建的工单数量，按月份升序排列。
```

参考SQL：
```sql
SELECT DATE_FORMAT(create_time, '%Y-%m') AS month, COUNT(*) AS order_count FROM order_record WHERE create_time >= '2024-01-01' AND create_time < '2025-01-01' GROUP BY DATE_FORMAT(create_time, '%Y-%m') ORDER BY month ASC;
```

### TC-006

问题：
```
工单系统：统计 2024 年每位提交人创建的工单数量，按数量降序排列前 10 名。
```

参考SQL：
```sql
SELECT committer_name, COUNT(*) AS order_count FROM order_record WHERE create_time >= '2024-01-01' AND create_time < '2025-01-01' GROUP BY committer_name ORDER BY order_count DESC LIMIT 10;
```

### TC-007

问题：
```
告警系统：查询 level='critical' 的告警，返回告警ID、实例ID、指标名称和告警时间，按告警时间降序。
```

参考SQL：
```sql
SELECT id, db_instance_id, metric_name, alert_time FROM db_alert_history WHERE level = 'critical' ORDER BY alert_time DESC;
```

### TC-008

问题：
```
告警系统：统计每种告警级别的数量。
```

参考SQL：
```sql
SELECT level, COUNT(*) AS alert_count FROM db_alert_history GROUP BY level ORDER BY alert_count DESC;
```

### TC-009

问题：
```
告警系统：统计每种告警指标的数量，按数量降序排列前 10 名。
```

参考SQL：
```sql
SELECT metric_name, COUNT(*) AS alert_count FROM db_alert_history GROUP BY metric_name ORDER BY alert_count DESC LIMIT 10;
```

### TC-010

问题：
```
告警系统：统计 2024 年 8 月每天的告警数量，按日期升序排列。
```

参考SQL：
```sql
SELECT DATE(alert_time) AS alert_date, COUNT(*) AS alert_count FROM db_alert_history WHERE alert_time >= '2024-08-01' AND alert_time < '2024-09-01' GROUP BY DATE(alert_time) ORDER BY alert_date ASC;
```

### TC-011

问题：
```
告警系统：查询 env_type='prd' 且 level='critical' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。
```

参考SQL：
```sql
SELECT db_instance_id, metric_name, cur_value, alert_time FROM db_alert_history WHERE env_type = 'prd' AND level = 'critical' ORDER BY alert_time DESC;
```

### TC-012

问题：
```
告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量降序排列。
```

参考SQL：
```sql
SELECT namespace, COUNT(*) AS alert_count FROM db_alert_history GROUP BY namespace ORDER BY alert_count DESC;
```

### TC-013

问题：
```
效能统计：统计每个业务域的总成本时间，按成本降序排列。
```

参考SQL：
```sql
SELECT business_domain, SUM(cost_time) AS total_cost_time FROM effect_dba_domain_cost_v2 GROUP BY business_domain ORDER BY total_cost_time DESC;
```

### TC-014

问题：
```
效能统计：统计 2024 年各月的总成本时间，按月份升序排列。
```

参考SQL：
```sql
SELECT CONCAT(year, '-', LPAD(month, 2, '0')) AS month, SUM(cost_time) AS total_cost_time FROM effect_dba_domain_cost_v2 WHERE year = 2024 GROUP BY year, month ORDER BY month ASC;
```

### TC-015

问题：
```
效能统计：查询 dba_owner_name='栾尚飞' 负责的所有业务域的成本统计，按成本降序排列。
```

参考SQL：
```sql
SELECT business_domain, SUM(cost_time) AS total_cost_time FROM effect_dba_domain_cost_v2 WHERE dba_owner_name = '栾尚飞' GROUP BY business_domain ORDER BY total_cost_time DESC;
```

### TC-016

问题：
```
效能统计：查询成本最高的前 5 个业务域，返回业务域名称和总成本时间。
```

参考SQL：
```sql
SELECT business_domain, SUM(cost_time) AS total_cost_time FROM effect_dba_domain_cost_v2 GROUP BY business_domain ORDER BY total_cost_time DESC LIMIT 5;
```

### TC-017

问题：
```
日常工作：查询 work_type='问题排查' 的工作记录，返回工作ID、DBA飞书ID、耗时和创建时间。
```

参考SQL：
```sql
SELECT id, dba_feishu_id, cost_time_minute, created_time FROM effect_daily_work_v2 WHERE work_type = '问题排查' ORDER BY created_time DESC;
```

### TC-018

问题：
```
日常工作：统计每种工作类型的数量。
```

参考SQL：
```sql
SELECT work_type, COUNT(*) AS work_count FROM effect_daily_work_v2 GROUP BY work_type ORDER BY work_count DESC;
```

### TC-019

问题：
```
工单审计：统计每种 SQL 类型的数量，按数量降序排列前 10 名。
```

参考SQL：
```sql
SELECT sql_type, COUNT(*) AS sql_count FROM order_audit_record GROUP BY sql_type ORDER BY sql_count DESC LIMIT 10;
```

### TC-020

问题：
```
工单审计：统计 2024 年 12 月每天的审计记录数量，按日期升序排列。
```

参考SQL：
```sql
SELECT DATE(create_time) AS audit_date, COUNT(*) AS audit_count FROM order_audit_record WHERE create_time >= '2024-12-01' AND create_time < '2025-01-01' GROUP BY DATE(create_time) ORDER BY audit_date ASC;
```

### TC-021

问题：
```
账户管理：查询 role=0 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID升序。
```

参考SQL：
```sql
SELECT id, realname, email, feishu_name FROM account WHERE role = 0 ORDER BY id ASC;
```

### TC-022

问题：
```
账户管理：统计每种角色的用户数量。
```

参考SQL：
```sql
SELECT role, COUNT(*) AS user_count FROM account GROUP BY role ORDER BY user_count DESC;
```

### TC-024

问题：
```
工单系统：查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。
```

参考SQL：
```sql
SELECT o.id, o.order_type, o.status_desc, w.status_desc AS workflow_status FROM order_record o LEFT JOIN workflow_instance w ON o.id = w.order_id ORDER BY o.create_time DESC;
```

### TC-025

问题：
```
告警系统：查询 level='critical' 的告警涉及的业务子域（business_subdomain），去重。
```

参考SQL：
```sql
SELECT DISTINCT business_subdomain FROM db_alert_history WHERE level = 'critical' ORDER BY business_subdomain;
```

### TC-027

问题：
```
工单系统：统计每种工单类型的完成率（is_finished=1 的工单数 / 总工单数），按完成率降序排列。
```

参考SQL：
```sql
SELECT order_type, COUNT(*) AS total_count, SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) AS finished_count, ROUND(SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS finish_rate FROM order_record GROUP BY order_type ORDER BY finish_rate DESC;
```

### TC-028

问题：
```
告警系统：使用 CASE WHEN 按月统计 2024 年 4-5 月每天的告警数量，返回日期、4月告警数、5月告警数。
```

参考SQL：
```sql
SELECT DATE(alert_time) AS alert_date, SUM(CASE WHEN MONTH(alert_time) = 4 THEN 1 ELSE 0 END) AS april_count, SUM(CASE WHEN MONTH(alert_time) = 5 THEN 1 ELSE 0 END) AS may_count FROM db_alert_history WHERE alert_time >= '2024-04-01' AND alert_time < '2024-06-01' GROUP BY DATE(alert_time) ORDER BY alert_date;
```

### TC-029

问题：
```
告警系统：统计每位DBA（dba_owner 字段）负责的业务域的告警数量，返回DBA标识、业务域、告警数量，按告警数量降序排列前 20 名。
```

参考SQL：
```sql
SELECT dba_owner, business_subdomain, COUNT(*) AS alert_count FROM db_alert_history GROUP BY dba_owner, business_subdomain ORDER BY alert_count DESC LIMIT 20;
```

### TC-030

问题：
```
工单系统：统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量降序排列。
```

参考SQL：
```sql
SELECT order_type, status_code, COUNT(*) AS order_count FROM order_record GROUP BY order_type, status_code ORDER BY order_type, order_count DESC;
```