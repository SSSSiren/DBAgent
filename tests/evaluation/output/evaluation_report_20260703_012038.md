# Agent 性能评测报告

**生成时间**: 2026-07-03 01:20:38
**测试数据库**: schemaId=65938636

## 📊 总览

| 指标 | 值 |
|------|----|
| 总用例数 | 30 |
| 通过 | 14 |
| 失败 | 13 |
| 错误 | 3 |
| 通过率 | 46.7% |
| 平均分 | 55.76% |
| 平均延迟 | 64867ms |
| 平均工具调用 | 3.4 |
| 平均 Turns | 7.4 |
| 平均 Token | 22809 |

## 📐 维度平均分

| 维度 | 权重 | 平均分 |
|------|------|--------|
| SQL 语法正确 | 20% | 56.17% |
| 表/列引用正确 | 20% | 56.17% |
| 过滤条件正确 | 20% | 56.17% |
| 结果数据正确 | 30% | 56.17% |
| SQL 规范 | 10% | 52.00% |

## 📋 按难度分布

| 难度 | 用例数 | 通过 | 失败 | 通过率 | 平均分 | 平均延迟 | 平均工具调用 |
|------|--------|------|------|--------|--------|----------|-------------|
| Easy | 10 | 6 | 4 | 60.0% | 64.66% | 49218ms | 3.5 |
| Medium | 15 | 7 | 8 | 46.7% | 58.28% | 65992ms | 3.6 |
| Hard | 5 | 1 | 4 | 20.0% | 30.40% | 92787ms | 2.6 |

## 📝 用例详情

| 用例 | 难度 | 类别 | 通过 | 总分 | SQL | 质量 | 效率 | 延迟 | 工具调用 |
|------|------|------|------|------|-----|------|------|------|---------|
| TC-001 | Easy | 单表过滤 | ❌ | 36.54% | 32.82% | 0.00% | 79.21% | 45875ms | 4 |
| TC-002 | Easy | 单表过滤 | ✅ | 100.00% | 100.00% | 100.00% | 82.60% | 36022ms | 3 |
| TC-003 | Easy | 聚合 | ✅ | 97.00% | 100.00% | 100.00% | 78.81% | 47522ms | 4 |
| TC-004 | Easy | 聚合 | ✅ | 97.00% | 100.00% | 97.50% | 79.11% | 56696ms | 4 |
| TC-005 | Medium | 时间窗口 | ✅ | 97.00% | 100.00% | 100.00% | 80.21% | 47017ms | 4 |
| TC-006 | Medium | 时间窗口 | ✅ | 100.00% | 100.00% | 100.00% | 82.22% | 42852ms | 4 |
| TC-007 | Easy | 单表过滤 | ❌ | 0.00% | 0.00% | 0.00% | 81.65% | 33531ms | 3 |
| TC-008 | Easy | 聚合 | ❌ | 0.00% | 0.00% | 50.00% | 87.54% | 25783ms | 2 |
| TC-009 | Medium | 聚合 | ❌ | 0.00% | 0.00% | 0.00% | 80.50% | 41534ms | 3 |
| TC-010 | Medium | 时间窗口 | ⚠️ | 52.00% | 50.00% | 0.00% | 96.00% | 125019ms | 4 |
| TC-011 | Medium | 多条件过滤 | ❌ | 25.02% | 20.03% | 90.00% | 67.37% | 101456ms | 4 |
| TC-012 | Medium | 聚合 | ✅ | 88.82% | 90.91% | 60.00% | 64.02% | 83887ms | 4 |
| TC-013 | Medium | 聚合 | ✅ | 97.00% | 100.00% | 100.00% | 83.41% | 32170ms | 4 |
| TC-014 | Medium | 时间窗口 | ✅ | 97.00% | 100.00% | 92.50% | 83.72% | 40160ms | 4 |
| TC-015 | Medium | 多条件过滤 | ✅ | 97.00% | 100.00% | 100.00% | 76.63% | 46545ms | 4 |
| TC-016 | Medium | 排名 | ✅ | 100.00% | 100.00% | 100.00% | 78.97% | 49880ms | 4 |
| TC-017 | Easy | 单表过滤 | ✅ | 97.00% | 100.00% | 100.00% | 80.78% | 54650ms | 4 |
| TC-018 | Easy | 聚合 | ✅ | 97.00% | 100.00% | 100.00% | 78.79% | 51715ms | 4 |
| TC-019 | Medium | 聚合 | ❌ | 0.00% | 0.00% | 0.00% | 84.43% | 35995ms | 3 |
| TC-020 | Medium | 时间窗口 | ❌ | 0.00% | 0.00% | 0.00% | 91.96% | 19823ms | 2 |
| TC-021 | Easy | 单表过滤 | ❌ | 25.02% | 20.03% | 100.00% | 78.27% | 46886ms | 3 |
| TC-022 | Easy | 聚合 | ✅ | 97.00% | 100.00% | 62.50% | 65.15% | 93504ms | 4 |
| TC-023 | Medium | JOIN | ⚠️ | 49.00% | 50.00% | 0.00% | 97.00% | 125024ms | 3 |
| TC-024 | Medium | JOIN | ❌ | 0.00% | 0.00% | 0.00% | 78.01% | 89407ms | 3 |
| TC-025 | Medium | 子查询 | ❌ | 71.29% | 71.43% | 0.00% | 68.78% | 109116ms | 4 |
| TC-026 | Hard | 窗口函数 | ❌ | 0.00% | 0.00% | 0.00% | 78.15% | 91959ms | 2 |
| TC-027 | Hard | 派生指标 | ✅ | 97.00% | 100.00% | 100.00% | 74.32% | 103320ms | 4 |
| TC-028 | Hard | 时间窗口 | ❌ | 0.00% | 0.00% | 0.00% | 93.65% | 50309ms | 0 |
| TC-029 | Hard | 复合查询 | ❌ | 55.00% | 50.00% | 0.00% | 77.06% | 93326ms | 4 |
| TC-030 | Hard | 复合查询 | ⚠️ | 0.00% | 0.00% | 0.00% | 97.00% | 125019ms | 3 |

## ❌ 失败/错误用例详情

### TC-001 — 查询所有数据变更类型的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。...

**总分**: 36.54%
**SQL 评分**: 32.82%
**差异**: 行数不一致：生成=20, 参考=354
**生成 SQL**: `SELECT DISTINCT order_type, COUNT(*) AS cnt FROM order_record GROUP BY order_type ORDER BY cnt DESC`
**参考 SQL**: `SELECT id, committer_name, status_desc, create_time
FROM order_record
WHERE order_type = 'dataChange'
ORDER BY create_time DESC;`
**LLM 评判**: 生成SQL查询的是每种工单类型的数量，而参考SQL查询的是所有数据变更类型的工单详情，两者语义完全不同。

### TC-007 — 查询所有严重级别的告警，返回告警ID、实例ID、指标名称和告警时间，按告警时间降序。...

**总分**: 0.00%
**SQL 评分**: 0.00%
**差异**: Agent 未生成 SQL
**参考 SQL**: `SELECT id, db_instance_id, metric_name, alert_time
FROM db_alert_history
WHERE level = 'critical'
ORDER BY alert_time DESC;`

### TC-008 — 统计每种告警级别的数量。...

**总分**: 0.00%
**SQL 评分**: 0.00%
**差异**: Agent 未生成 SQL
**参考 SQL**: `SELECT level, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY level
ORDER BY alert_count DESC;`

### TC-009 — 统计每种告警指标的数量，按数量降序排列前 10 名。...

**总分**: 0.00%
**SQL 评分**: 0.00%
**差异**: Agent 未生成 SQL
**参考 SQL**: `SELECT metric_name, COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY metric_name
ORDER BY alert_count DESC
LIMIT 10;`

### TC-010 — 统计 2024 年 8 月每天的告警数量，按日期升序排列。...

**错误**: 执行超时（120.0秒）

### TC-011 — 查询生产环境的严重告警，返回实例ID、指标名称、当前值和告警时间，按告警时间降序。...

**总分**: 25.02%
**SQL 评分**: 20.03%
**差异**: 行数不一致：生成=1, 参考=2000
**生成 SQL**: `SELECT COUNT(*) AS total FROM db_alert_current WHERE env_type = 'prd' AND level = 'critical'`
**参考 SQL**: `SELECT db_instance_id, metric_name, cur_value, alert_time
FROM db_alert_history
WHERE env_type = 'prd'
  AND level = 'critical'
ORDER BY alert_time DESC;`
**LLM 评判**: 生成SQL查询的是db_alert_current表并返回计数，而参考SQL查询db_alert_history表返回详细记录，两者语义完全不同，无法回答原始问题。

### TC-019 — 统计每种SQL类型的数量，按数量降序排列前 10 名。...

**总分**: 0.00%
**SQL 评分**: 0.00%
**差异**: Agent 未生成 SQL
**参考 SQL**: `SELECT sql_type, COUNT(*) AS sql_count
FROM order_audit_record
GROUP BY sql_type
ORDER BY sql_count DESC
LIMIT 10;`

### TC-020 — 统计 2024 年 12 月每天的审计记录数量，按日期升序排列。...

**总分**: 0.00%
**SQL 评分**: 0.00%
**差异**: Agent 未生成 SQL
**参考 SQL**: `SELECT DATE(create_time) AS audit_date,
       COUNT(*) AS audit_count
FROM order_audit_record
WHERE create_time >= '2024-12-01'
  AND create_time < '2025-01-01'
GROUP BY DATE(create_time)
ORDER BY audit_date ASC;`

### TC-021 — 查询所有角色为 0 的用户，返回用户ID、真实姓名、邮箱和飞书用户名，按用户ID升序。...

**总分**: 25.02%
**SQL 评分**: 20.03%
**差异**: 行数不一致：生成=1, 参考=2000
**生成 SQL**: `SELECT COUNT(*) AS total FROM account WHERE role = 0`
**参考 SQL**: `SELECT id, realname, email, feishu_name
FROM account
WHERE role = 0
ORDER BY id ASC;`
**LLM 评判**: 生成SQL查询的是角色为0的用户总数，而参考SQL查询的是用户详细信息，两者语义完全不同，无法回答原始问题。

### TC-023 — 查询工单及其提交人信息，返回工单ID、工单类型、提交人姓名、提交人邮箱，按工单创建时间降序。...

**错误**: 执行超时（120.0秒）

### TC-024 — 查询工单及其工作流实例信息，返回工单ID、工单类型、工单状态、工作流状态，按工单创建时间降序。...

**总分**: 0.00%
**SQL 评分**: 0.00%
**差异**: Agent 未生成 SQL
**参考 SQL**: `SELECT o.id, o.order_type, o.status_desc, w.status_desc AS workflow_status
FROM order_record o
LEFT JOIN workflow_instance w ON o.id = w.order_id
ORDER BY o.create_time DESC;`

### TC-025 — 查询有严重告警的业务域名称，去重。...

**总分**: 71.29%
**SQL 评分**: 71.43%
**差异**: 行数不一致：生成=15, 参考=35
**生成 SQL**: `SELECT DISTINCT business_subdomain FROM db_alert_current WHERE business_subdomain IS NOT NULL AND business_subdomain != '' LIMIT 20`
**参考 SQL**: `SELECT DISTINCT business_subdomain
FROM db_alert_history
WHERE level = 'critical'
ORDER BY business_subdomain;`
**LLM 评判**: 参考SQL查询db_alert_history中level='critical'的业务域，生成SQL查询db_alert_current且无level条件，语义完全不同，结果集无交集，不等价。

### TC-026 — 查询每个业务域的告警数量，并按告警数量在该业务域内排名。...

**总分**: 0.00%
**SQL 评分**: 0.00%
**差异**: Agent 未生成 SQL
**参考 SQL**: `SELECT business_subdomain,
       metric_name,
       COUNT(*) AS alert_count,
       ROW_NUMBER() OVER (PARTITION BY business_subdomain ORDER BY COUNT(*) DESC) AS rn
FROM db_alert_history
GROUP BY business_subdomain, metric_name
ORDER BY business_subdomain, rn;`

### TC-028 — 对比 2024 年 4 月和 5 月每天的告警数量，返回日期、4月告警数、5月告警数。...

**总分**: 0.00%
**SQL 评分**: 0.00%
**差异**: Agent 未生成 SQL
**参考 SQL**: `SELECT
    DATE(alert_time) AS alert_date,
    SUM(CASE WHEN MONTH(alert_time) = 4 THEN 1 ELSE 0 END) AS april_count,
    SUM(CASE WHEN MONTH(alert_time) = 5 THEN 1 ELSE 0 END) AS may_count
FROM db_alert_history
WHERE alert_time >= '2024-04-01'
  AND alert_time < '2024-06-01'
GROUP BY DATE(alert_time)
ORDER BY alert_date;`

### TC-029 — 统计每位DBA负责的业务域的告警数量，返回DBA标识、业务域、告警数量，按告警数量降序排列前 20 ...

**总分**: 55.00%
**SQL 评分**: 50.00%
**差异**: 行数不一致：生成=0, 参考=20
**生成 SQL**: `SELECT 
    b.dba AS dba_标识,
    b.business_subdomain AS 业务域,
    SUM(a.cnt) AS 告警数量
FROM db_alert_history_day_dba a
JOIN db_dba_businessdomain b ON a.dba_owner = b.dba
GROUP BY b.dba, b.business_subdomain
ORDER BY 告警数量 DESC
LIMIT 20`
**参考 SQL**: `SELECT dba_owner,
       business_subdomain,
       COUNT(*) AS alert_count
FROM db_alert_history
GROUP BY dba_owner, business_subdomain
ORDER BY alert_count DESC
LIMIT 20;`
**LLM 评判**: 生成SQL使用了不同的表（db_alert_history_day_dba和db_dba_businessdomain），且聚合方式为SUM而非COUNT，导致结果为空，与参考SQL语义不等价。

### TC-030 — 统计每种工单类型在各状态下的数量，返回工单类型、状态、数量，按工单类型和数量降序排列。...

**错误**: 执行超时（120.0秒）
