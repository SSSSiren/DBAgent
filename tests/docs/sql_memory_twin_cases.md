# SQL Memory 孪生测例数据集

> 基于 tests/docs/test_cases_onedba_evaluation.md 的 28 个原始 TC 生成
> 每个 TWIN-XXX 对应一个 TC-XXX，语义相似但问题不同
> 用于 SQL 记忆模块的对比评测：孪生测例填充记忆 → 原始 TC 验证检索泛化

## 变换规则

| 变换类型 | 适用场景 |
|----------|---------|
| 值替换 | 单表过滤、多条件过滤 |
| 条件反转 | 布尔条件 |
| 聚合函数替换 | 聚合 |
| 时间窗口平移 | 时间窗口 |
| 排序方向反转 | 排名、单表过滤 |
| 同义词替换 | 所有问题描述 |

---

### TWIN-001 单表过滤 - 数据导出类工单 (对应 TC-001)

**自然语言问题：**
工单系统：查询 order_type='dataExport' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间升序。

**参考答案 SQL：**
SELECT id, committer_name, status_desc, create_time
FROM order_record
WHERE order_type = 'dataExport'
ORDER BY create_time ASC;

**预期结果：**
- 应返回 50 行（dataExport 类型工单）
- 所有行的 order_type 都是 'dataExport'

**对应原始 TC：** TC-001

---

### TWIN-002 单表过滤 - 未完成的工单 (对应 TC-002)

**自然语言问题：**
工单系统：统计未完成的工单（is_finished=0）有多少条。

**参考答案 SQL：**
SELECT COUNT(*) AS unfinished_count
FROM order_record
WHERE is_finished = 0;

**预期结果：**
- 应返回 412 条（未完成工单数 = 1174 - 762）

**对应原始 TC：** TC-002

---

### TWIN-003 聚合 - 各类型工单平均创建时间 (对应 TC-003)

**自然语言问题：**
工单系统：统计每种工单类型的数量，按数量升序排列。

**参考答案 SQL：**
SELECT order_type, COUNT(*) AS order_count
FROM order_record
GROUP BY order_type
ORDER BY order_count ASC;

**预期结果：**
- 与 TC-003 结果相同但排序方向相反

**对应原始 TC：** TC-003

---

### TWIN-004 聚合 - 各状态工单数量统计（升序）(对应 TC-004)

**自然语言问题：**
工单系统：统计每种工单状态（status_code 和 status_desc）的数量，按数量升序排列。

**参考答案 SQL：**
SELECT status_code, status_desc, COUNT(*) AS order_count
FROM order_record
GROUP BY status_code, status_desc
ORDER BY order_count ASC;

**预期结果：**
- 与 TC-004 结果相同但排序方向相反

**对应原始 TC：** TC-004

---

### TWIN-005 时间窗口 - 按季度统计工单创建数量 (对应 TC-005)

**自然语言问题：**
工单系统：统计 2024 年每季度创建的工单数量，按季度升序排列。

**参考答案 SQL：**
SELECT QUARTER(create_time) AS quarter,
       COUNT(*) AS order_count
FROM order_record
WHERE create_time >= '2024-01-01'
  AND create_time < '2025-01-01'
GROUP BY QUARTER(create_time)
ORDER BY quarter ASC;

**预期结果：**
- 应返回 4 行（Q1-Q4）

**对应原始 TC：** TC-005

---

### TWIN-006 时间窗口 - 按提交人统计工单数量（升序）(对应 TC-006)

**自然语言问题：**
工单系统：统计 2024 年每位提交人创建的工单数量，按数量升序排列前 10 名。

**参考答案 SQL：**
SELECT committer_name, COUNT(*) AS order_count
FROM order_record
WHERE create_time >= '2024-01-01'
  AND create_time < '2025-01-01'
GROUP BY committer_name
ORDER BY order_count ASC
LIMIT 10;

**预期结果：**
- 应返回 10 行，数量最少的提交人排前面

**对应原始 TC：** TC-006

---

### TWIN-007 单表过滤 - 警告级别告警 (对应 TC-007)

**自然语言问题：**
告警系统：查询 level='warn' 的告警，返回告警ID、实例ID、指标名称和告警时间，按告警时间升序。

**参考答案 SQL：**
SELECT id, db_instance_id, metric_name, alert_time
FROM db_alert_history
WHERE level = 'warn'
ORDER BY alert_time ASC;

**预期结果：**
- 应返回 85662 行（warn 级别告警）
- 所有行的 level 都是 'warn'

**对应原始 TC：** TC-007

---

### TWIN-008 聚合 - 各告警级别平均告警数量 (对应 TC-008)

**自然语言问题：**
告警系统：统计每种告警级别的数量，按数量升序排列。

**参考答案 SQL：**
SELECT level, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY level
ORDER BY alert_count ASC;

**预期结果：**
- 与 TC-008 结果相同但排序方向相反

**对应原始 TC：** TC-008

---

### TWIN-009 聚合 - 各指标告警数量统计（升序）(对应 TC-009)

**自然语言问题：**
告警系统：统计每种告警指标的数量，按数量升序排列前 10 名。

**参考答案 SQL：**
SELECT metric_name, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY metric_name
ORDER BY alert_count ASC
LIMIT 10;

**预期结果：**
- 应返回 10 行，数量最少的指标排前面

**对应原始 TC：** TC-009

---

### TWIN-010 时间窗口 - 按天统计告警趋势（2024年7月）(对应 TC-010)

**自然语言问题：**
告警系统：统计 2024 年 7 月每天的告警数量，按日期升序排列。

**参考答案 SQL：**
SELECT DATE(alert_time) AS alert_date,
       COUNT(*) AS alert_count
FROM db_alert_history
WHERE alert_time >= '2024-07-01'
  AND alert_time < '2024-08-01'
GROUP BY DATE(alert_time)
ORDER BY alert_date ASC;

**预期结果：**
- 应返回多行（2024年7月1-31日中有告警数据的日期）

**对应原始 TC：** TC-010

---

### TWIN-011 多条件过滤 - 测试环境警告告警 (对应 TC-011)

**自然语言问题：**
告警系统：查询 env_type='test' 且 level='warn' 的告警，返回实例ID、指标名称、当前值和告警时间，按告警时间升序。

**参考答案 SQL：**
SELECT db_instance_id, metric_name, cur_value, alert_time
FROM db_alert_history
WHERE env_type = 'test'
  AND level = 'warn'
ORDER BY alert_time ASC;

**预期结果：**
- 所有行的 env_type 都是 'test'，level 都是 'warn'

**对应原始 TC：** TC-011

---

### TWIN-012 聚合 - 各数据库类型告警数量统计（升序）(对应 TC-012)

**自然语言问题：**
告警系统：统计每种 namespace（数据库产品类型）的告警数量，按数量升序排列。

**参考答案 SQL：**
SELECT namespace, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY namespace
ORDER BY alert_count ASC;

**预期结果：**
- 与 TC-012 结果相同但排序方向相反

**对应原始 TC：** TC-012

---

### TWIN-013 聚合 - 各业务域平均成本时间 (对应 TC-013)

**自然语言问题：**
效能统计：统计每个业务域的平均成本时间，按平均成本降序排列。

**参考答案 SQL：**
SELECT business_domain,
       AVG(cost_time) AS avg_cost_time
FROM effect_dba_domain_cost_v2
GROUP BY business_domain
ORDER BY avg_cost_time DESC;

**预期结果：**
- 使用 AVG 而非 SUM

**对应原始 TC：** TC-013

---

### TWIN-014 时间窗口 - 按周统计成本趋势 (对应 TC-014)

**自然语言问题：**
效能统计：统计 2024 年各周的总成本时间，按周升序排列。

**参考答案 SQL：**
SELECT CONCAT(year, '-W', LPAD(week, 2, '0')) AS week_label,
       SUM(cost_time) AS total_cost_time
FROM effect_dba_domain_cost_v2
WHERE year = 2024
GROUP BY year, week
ORDER BY week_label ASC;

**预期结果：**
- 应返回多行，按周统计

**对应原始 TC：** TC-014

---

### TWIN-015 多条件过滤 - 某DBA负责的业务域成本（按时间）(对应 TC-015)

**自然语言问题：**
效能统计：查询 dba_owner_name='栾尚飞' 负责的 2024 年所有业务域的成本统计，按成本升序排列。

**参考答案 SQL：**
SELECT business_domain,
       SUM(cost_time) AS total_cost_time
FROM effect_dba_domain_cost_v2
WHERE dba_owner_name = '栾尚飞'
  AND year = 2024
GROUP BY business_domain
ORDER BY total_cost_time ASC;

**预期结果：**
- 所有行的 dba_owner_name 都是 '栾尚飞'，year 都是 2024

**对应原始 TC：** TC-015

---

### TWIN-016 排名 - 成本最低的业务域 (对应 TC-016)

**自然语言问题：**
效能统计：查询成本最低的前 5 个业务域，返回业务域名称和总成本时间。

**参考答案 SQL：**
SELECT business_domain,
       SUM(cost_time) AS total_cost_time
FROM effect_dba_domain_cost_v2
GROUP BY business_domain
ORDER BY total_cost_time ASC
LIMIT 5;

**预期结果：**
- 应返回 5 行，按成本升序排列

**对应原始 TC：** TC-016

---

### TWIN-017 单表过滤 - 应急处理类工作 (对应 TC-017)

**自然语言问题：**
日常工作：查询 work_type='应急处理' 的工作记录，返回工作ID、DBA飞书ID、耗时和创建时间，按创建时间升序。

**参考答案 SQL：**
SELECT id, dba_feishu_id, cost_time_minute, created_time
FROM effect_daily_work_v2
WHERE work_type = '应急处理'
ORDER BY created_time ASC;

**预期结果：**
- 应返回 1 行（应急处理类型）
- work_type 为 '应急处理'

**对应原始 TC：** TC-017

---

### TWIN-018 聚合 - 各工作类型数量统计（升序）(对应 TC-018)

**自然语言问题：**
日常工作：统计每种工作类型的数量，按数量升序排列。

**参考答案 SQL：**
SELECT work_type, COUNT(*) AS work_count
FROM effect_daily_work_v2
GROUP BY work_type
ORDER BY work_count ASC;

**预期结果：**
- 与 TC-018 结果相同但排序方向相反

**对应原始 TC：** TC-018

---

### TWIN-019 聚合 - 各SQL类型数量统计（升序）(对应 TC-019)

**自然语言问题：**
工单审计：统计每种 SQL 类型的数量，按数量升序排列前 10 名。

**参考答案 SQL：**
SELECT sql_type, COUNT(*) AS sql_count
FROM order_audit_record
GROUP BY sql_type
ORDER BY sql_count ASC
LIMIT 10;

**预期结果：**
- 应返回 10 行，数量最少的 SQL 类型排前面

**对应原始 TC：** TC-019

---

### TWIN-020 时间窗口 - 按天统计审计记录数量（2024年11月）(对应 TC-020)

**自然语言问题：**
工单审计：统计 2024 年 11 月每天的审计记录数量，按日期升序排列。

**参考答案 SQL：**
SELECT DATE(create_time) AS audit_date,
       COUNT(*) AS audit_count
FROM order_audit_record
WHERE create_time >= '2024-11-01'
  AND create_time < '2024-12-01'
GROUP BY DATE(create_time)
ORDER BY audit_date ASC;

**预期结果：**
- 应返回多行（2024年11月1-30日中有审计数据的日期）

**对应原始 TC：** TC-020

---

### TWIN-021 单表过滤 - 查询某角色的用户（role=1）(对应 TC-021)

**自然语言问题：**
账户管理：查询 role=1 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID降序。

**参考答案 SQL：**
SELECT id, realname, email, feishu_name
FROM account
WHERE role = 1
ORDER BY id DESC;

**预期结果：**
- 应返回 role=1 的用户（非 role=0）
- 所有行的 role 都是 1
- 排序方向为 DESC

**对应原始 TC：** TC-021

---

### TWIN-022 聚合 - 各角色用户数量统计（升序）(对应 TC-022)

**自然语言问题：**
账户管理：统计每种角色的用户数量，按数量升序排列。

**参考答案 SQL：**
SELECT role, COUNT(*) AS user_count
FROM account
GROUP BY role
ORDER BY user_count ASC;

**预期结果：**
- 与 TC-022 结果相同但排序方向相反

**对应原始 TC：** TC-022

---

### TWIN-024 JOIN - 工单与审计记录 (对应 TC-024)

**自然语言问题：**
工单系统：查询工单及其审计记录，返回工单ID、工单类型、SQL类型、风险等级，按工单创建时间升序。

**参考答案 SQL：**
SELECT o.id, o.order_type, a.sql_type, a.risk_level
FROM order_record o
LEFT JOIN order_audit_record a ON o.id = a.order_id
ORDER BY o.create_time ASC;

**预期结果：**
- 应返回多条记录
- 包含工单和审计信息
- 排序方向为 ASC

**对应原始 TC：** TC-024

---

### TWIN-025 去重查询 - 有告警的环境类型 (对应 TC-025)

**自然语言问题：**
告警系统：查询 level='warn' 的告警涉及的环境类型（env_type），去重。

**参考答案 SQL：**
SELECT DISTINCT env_type
FROM db_alert_history
WHERE level = 'warn'
ORDER BY env_type;

**预期结果：**
- 应返回多条记录
- 使用 DISTINCT 去重

**对应原始 TC：** TC-025

---

### TWIN-027 派生指标 - 工单未完成率 (对应 TC-027)

**自然语言问题：**
工单系统：统计每种工单类型的未完成率（is_finished=0 的工单数 / 总工单数），按未完成率升序排列。

**参考答案 SQL：**
SELECT order_type,
       COUNT(*) AS total_count,
       SUM(CASE WHEN is_finished = 0 THEN 1 ELSE 0 END) AS unfinished_count,
       ROUND(SUM(CASE WHEN is_finished = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS unfinished_rate
FROM order_record
GROUP BY order_type
ORDER BY unfinished_rate ASC;

**预期结果：**
- 应返回多条记录
- 使用 CASE WHEN 计算未完成率

**对应原始 TC：** TC-027

---

### TWIN-028 时间窗口 - 告警趋势对比（6-7月）(对应 TC-028)

**自然语言问题：**
告警系统：使用 CASE WHEN 按月统计 2024 年 6-7 月每天的告警数量，返回日期、6月告警数、7月告警数。

**参考答案 SQL：**
SELECT
    DATE(alert_time) AS alert_date,
    SUM(CASE WHEN MONTH(alert_time) = 6 THEN 1 ELSE 0 END) AS june_count,
    SUM(CASE WHEN MONTH(alert_time) = 7 THEN 1 ELSE 0 END) AS july_count
FROM db_alert_history
WHERE alert_time >= '2024-06-01'
  AND alert_time < '2024-08-01'
GROUP BY DATE(alert_time)
ORDER BY alert_date;

**预期结果：**
- 应返回多行（6月和7月中有告警数据的日期）
- 包含两个月的告警数量对比

**对应原始 TC：** TC-028

---

### TWIN-029 复合查询 - 各DBA负责业务域的告警统计（升序）(对应 TC-029)

**自然语言问题：**
告警系统：统计每位DBA（dba_owner 字段）负责的业务域的告警数量，返回DBA标识、业务域、告警数量，按告警数量升序排列前 20 名。

**参考答案 SQL：**
SELECT dba_owner,
       business_subdomain,
       COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY dba_owner, business_subdomain
ORDER BY alert_count ASC
LIMIT 20;

**预期结果：**
- 应返回 20 行，按告警数量升序排列

**对应原始 TC：** TC-029

---

### TWIN-030 复合查询 - 工单类型与状态交叉分析（升序）(对应 TC-030)

**自然语言问题：**
工单系统：统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量升序排列。

**参考答案 SQL：**
SELECT order_type,
       status_code,
       COUNT(*) AS order_count
FROM order_record
GROUP BY order_type, status_code
ORDER BY order_type, order_count ASC;

**预期结果：**
- 应返回多条记录
- 按工单类型和数量升序排列

**对应原始 TC：** TC-030