======================================================================
  VK-DBAgent RAG 验证 — 知识库增强效果对比
======================================================================
  用户: vkdb-rag-verify
  知识库: viking://resources/dba-sql-reference
  目标库: dw_onedba (schema_id=65938636)


======================================================================
  Phase 1: 上传知识库到 OpenViking
======================================================================
[OK] 资源已存在: viking://resources/dba-sql-reference

======================================================================
  Phase 2: 基线 (无 RAG)
======================================================================

  [User →] 帮我统计一下生产环境中各个业务子域的RDS实例有多少告警，按告警数量从多到少排列...
  [KB] 总上下文: 0 条长期记忆 + 0 条 RAG 参考 = 0 条
  [Tool] find_table
  [Think] 我看到搜索结果主要是 test 环境，但用户需要的是**生产环境**。让我进一步搜索生产环境中的相关表。

...
  [Tool] find_table
  [Tool] list_databases
  [Think] 生产环境没有直接返回 onedba 数据库，让我扩大搜索范围，看看生产环境有哪些数据库和表。

...
  [Tool] list_databases
  [Tool] find_table
  [Think] 虽然 `list_databases` 在生产环境中没有返回结果，但 `dw_onedba`（schemaId: 65938636）中包含了所有相关表，且该库通常存储的是生产环境的汇总数据。让我先选择这个数据库，然后进行查询。

...
  [Tool] select_database
  [Think] 已选择 `dw_onedba` 数据库。现在让我用自然语言查询来统计各业务子域的 RDS 实例告警数量。

...
  [Tool] query_database
  [Think] 让我先查看关键表的结构，以便准确回答这些问题。

...
  [Tool] describe_table
  [Tool] describe_table
  [Tool] describe_table
  [Tool] describe_table
  [Think] 表结构已经很清晰了。`db_alert_history_day_domain` 表已经按业务子域聚合了告警数量。让我先确认一下 `db_rds_instance` 中 `env_type` 的值，然后执行查询。

...
  [Tool] query_database
[query_database] Generated SQL: SELECT DISTINCT env_type FROM db_rds_instance
[query_database] Result rows: 6
  [SQL] SELECT DISTINCT env_type FROM db_rds_instance...
  [Think] 生产环境的 `env_type` 是 `prd`。现在让我查看告警记录表的结构，以便关联 RDS 实例和告警。

...
  [Tool] describe_table
  [Tool] describe_table
  [Think] 表结构已经很清晰了。`db_alert_record_v2` 表包含 `env_type`、`business_subdomain` 和 `resource_type` 字段，可以直接按生产环境 + RDS 实例过滤。让我执行查询。

...
  [Tool] query_database
[query_database] Generated SQL: SELECT a.business_subdomain, COUNT(*) AS alert_count FROM db_alert_record_v2 a INNER JOIN db_rds_instance r ON a.db_instance_id = r.db_instance_id WHERE a.env_type = 'prd' GROUP BY a.business_subdomain ORDER BY alert_count DESC, a.business_subdomain
[query_database] Result rows: 0
  [SQL] SELECT a.business_subdomain, COUNT(*) AS alert_count FROM db_alert_record_v2 a INNER JOIN db_rds_instance r ON a.db_instance_id = r.db_instance_id WHE...
  [Think] 结果为空，让我排查一下原因。先分别检查两张表中生产环境的数据情况。

...
  [Tool] query_database
[query_database] Generated SQL: SELECT 'alert_count' AS metric, CAST(COUNT(*) AS CHAR) AS value FROM db_alert_record_v2 WHERE env_type = 'prd' UNION ALL SELECT 'instance_count', CAST(COUNT(*) AS CHAR) FROM db_rds_instance WHERE env_type = 'prd' UNION ALL SELECT 'distinct_resource_types', GROUP_CONCAT(DISTINCT resource_type ORDER BY resource_type SEPARATOR ',') FROM db_alert_record_v2 WHERE env_type = 'prd'
[query_database] Result rows: 3
  [SQL] SELECT 'alert_count' AS metric, CAST(COUNT(*) AS CHAR) AS value FROM db_alert_record_v2 WHERE env_type = 'prd' UNION ALL SELECT 'instance_count', CAST...
  [Think] `db_alert_record_v2` 中 `env_type='prd'` 的告警数为 0。让我检查告警表中实际有哪些环境的数据。



...
  [Tool] query_database
[query_database] Generated SQL: SELECT env_type, COUNT(*) AS record_count FROM db_alert_record_v2 GROUP BY env_type ORDER BY record_count DESC, env_type ASC
[query_database] Result rows: 1
  [SQL] SELECT env_type, COUNT(*) AS record_count FROM db_alert_record_v2 GROUP BY env_type ORDER BY record_count DESC, env_type ASC...
  [Tool] query_database
[query_database] Generated SQL: SELECT env_type, COUNT(*) AS cnt FROM db_alert_history GROUP BY env_type ORDER BY cnt DESC, env_type
[query_database] Result rows: 6
  [SQL] SELECT env_type, COUNT(*) AS cnt FROM db_alert_history GROUP BY env_type ORDER BY cnt DESC, env_type...
  [Think] `db_alert_record_v2` 几乎没有数据，但 `db_alert_history` 有大量生产环境数据（373,584 条）。让我用 `db_alert_history` 来查询。



...
  [Tool] query_database
[Langfuse] Trace URL: http://localhost:3000/project/cmr3l096r0006lj075180lfcx/traces/decdcaa14c7434191c95aef05d29cd68

--- 基线结果摘要 ---
  响应长度: 0 chars
  工具调用: ['find_table', 'find_table', 'list_databases', 'list_databases', 'find_table', 'select_database', 'query_database', 'describe_table', 'describe_table', 'describe_table', 'describe_table', 'query_database', 'describe_table', 'describe_table', 'query_database', 'query_database', 'query_database', 'query_database', 'query_database']
  工具调用次数: 19
  SQL 数量: 5
  耗时: 300249ms
  记忆数: 0
  ❌ 错误: 执行超时 (300s)

======================================================================
  Phase 3: RAG 检索
======================================================================
[OK] 检索到 5 条相关资源
  [1] score=0.6220 viking://resources/dba-sql-reference/dba-sql-reference.md
      完整内容: 3951 chars
  [2] score=0.5578 viking://resources/dba-sql-reference/.overview.md
      完整内容: 3889 chars
  [3] score=0.4466 viking://resources/db-troubleshooting-guide/db-troubleshooting-guide.md
      完整内容: 2079 chars

======================================================================
  Phase 4: 有 RAG
======================================================================

  [User →] 帮我统计一下生产环境中各个业务子域的RDS实例有多少告警，按告警数量从多到少排列...
  [RAG] 注入 3 条知识库上下文
  [KB] 总上下文: 0 条长期记忆 + 3 条 RAG 参考 = 3 条
[KB] build_context: 注入 3 条 RAG SQL 参考
  [Tool] find_table
  [Think] 找到了关键表：`db_alert_history`（告警历史）和 `db_rds_instance`（RDS实例）。让我先选择数据库，然后查询。

...
  [Tool] select_database
  [Think] 现在让我用自然语言查询来统计生产环境中各业务子域的 RDS 实例告警数量。

...
  [Tool] query_database
[query_database] Generated SQL: SELECT ri.business_subdomain, COUNT(ah.id) AS alert_count FROM db_rds_instance ri JOIN db_alert_history ah ON ri.db_instance_id = ah.db_instance_id WHERE ri.env_type = 'prd' GROUP BY ri.business_subdomain ORDER BY alert_count DESC
[query_database] Result rows: 44
  [SQL] SELECT ri.business_subdomain, COUNT(ah.id) AS alert_count FROM db_rds_instance ri JOIN db_alert_history ah ON ri.db_instance_id = ah.db_instance_id WH...
[Langfuse] Trace URL: http://localhost:3000/project/cmr3l096r0006lj075180lfcx/traces/13aa916e43f8c16b689da1addf424e37

--- 有 RAG 结果摘要 ---
  响应长度: 1112 chars
  工具调用: ['find_table', 'select_database', 'query_database']
  工具调用次数: 3
  SQL 数量: 1
  耗时: 60696ms
  记忆数: 3

======================================================================
  Phase 5: 验证报告
======================================================================

[指标 1] 工具调用次数对比
  场景                       工具调用 详情
  ------------------------------------------------------------
  无 RAG (基线)                 19 ['find_table', 'find_table', 'list_databases', 'list_databases', 'find_table', '
  有 RAG                       3 ['find_table', 'select_database', 'query_database']

  ✅ RAG 减少 16 次工具调用，跳过: {'describe_table', 'list_databases'}

[指标 2] 耗时对比
  场景                         耗时(ms) 相对基线
  ---------------------------------------------
  无 RAG (基线)                300,249
  有 RAG                      60,696       -80%

  ✅ RAG 节省 239,553ms (239.6s)

[指标 3] Token 消耗对比
  ⚠️ 基线超时，token 数据不可用

[指标 4] RAG 检索到的参考资料原文

  ── 参考资料 #1 ── viking://resources/dba-sql-reference/dba-sql-reference.md
  # OneDBA DBA 常用 SQL 参考

> 数据库: `dw_onedba` (schema_id=65938636, 实例 dw-onedba-t1)
> 最后更新: 2026-07-15

---

## 0. 关键字段取值速查

### db_rds_instance.env_type
| 值 | 含义 |
|----|------|
| prd | 生产环境 |
| pre | 预发环境 |
| test | 测试环境 |
| dev | 开发环境 |
| uat | 压测环境 |

### db_rds_instance.business_subdomain（生产环境 Top 10）
数据平台-离线数仓、数据平台-数据研发、风控-风控技术、社区技术-社区后端、交易平台-订单、算法平台-搜索工程、汇金平台-财务结算、汇金平台-财务、商家、算法平台-算法工程

### db_rds_instance.level
P0 / P1 / P2 / P3 / P4（数字越小等级越高）

### db_rds_instance.engine
MySQL(1469) / PostgreSQL(20) / SQLServer(1) / POLARDB(1)

### db_rds_instance.region_id
cn-hangzhou(1380) / ap-southeast-1(77) / cn-east-3(21) / cn-shanghai(6) / cn-hongkong(3)

### db_rds_instance.db_instance_status
Running(1443) / Transing(44) / ReadInstanceTransing(3) / Released(1)

### db_instance_v2.res_type（所有实例类型）
acs_rds(1569) / acs_kvstore(485) / acs_dts(132) / acs_hbase(93) / acs_mongodb(56) / acs_starrocks(45) / acs_clickhouse(44) / acs_tidb(25) / acs_pika(20)

### db_schemas.env_type
prd(91665) / test(16143) / pre(3820) / dev(3298) / uat(2830)

### db_schemas.instance_type
acs_rds(11557) / db_starrocks(386) / db_tidb(262) / acs_hbase(187) / acs_clickhouse(84) / db_oceanbase(3)

### db_alert_history.level
ok / warn / critical

### db_alert_history.metric_name（Top 告警指标）
NODE_DiskUsage / ShardingMemoryUsage / DiskUsage / DiskUtilization / NodeHeapMemoryUtilization / CpuUsage / NODE_CpuUsage / MySQL_ActiveSessions

---

## 1. RDS 实例统计

### 1.1 按业务子域统计生产环境 RDS 实例
```sql
SELECT business_subdomain, C
  ... (共 2000 chars，已截断)

  ── 参考资料 #2 ── viking://resources/dba-sql-reference/.overview.md
  # dba-sql-reference

This document is a DBA SQL reference guide for the OneDBA platform, providing quick lookup values and analytical queries for database administration. It covers four main sections: key field value references for environment types, business subdomains, instance levels, engines, regions, and statuses; RDS instance statistics grouped by business subdomain, environment, engine, level, region, and status; a global instance view across all resource types; and schema database counts by environment and type. The final section details alert history analysis by severity and metric, including a query for a specific instance's recent alerts. Intended for database administrators managing the dw_onedba database, this reference enables efficient inventory, configuration, and monitoring analysis using predefined SQL queries. Keywords: OneDBA, DBA, SQL reference, RDS instance, schema, alert history, database administration.

## Quick Navigation

**What do you want to learn or do?**

- **Look up reference values for environment types, subdomains, engines, regions, or statuses** → dba-sql-reference.md dba-sql-reference.md (Key Field Value References section)
- **Analyze RDS instance statistics grouped by business subdomain, environment, engine, level, region, or status** → dba-sql-reference.md dba-sql-reference.md (RDS Instance Statistics section)
- **View all instances globally across all resource types** → dba-sql-reference.md dba-sql-reference.md (Global Instance View sec
  ... (共 2000 chars，已截断)

  ── 参考资料 #3 ── viking://resources/db-troubleshooting-guide/db-troubleshooting-guide.md
  # 数据库常见问题处理手册

## 1. MySQL 连接数过高导致服务不可用

### 现象
- 应用日志出现 `Too many connections` 错误
- `SHOW PROCESSLIST` 显示大量 Sleep 连接
- 新连接无法建立

### 排查步骤
1. 查看当前连接数: `SHOW STATUS LIKE 'Threads_connected';`
2. 查看最大连接数: `SHOW VARIABLES LIKE 'max_connections';`
3. 按用户统计连接: `SELECT user, COUNT(*) FROM information_schema.processlist GROUP BY user;`
4. 按状态统计: `SELECT state, COUNT(*) FROM information_schema.processlist GROUP BY state;`

### 解决方案
**临时方案 (紧急恢复):**
```sql
-- 杀掉空闲超过 300 秒的连接
SELECT CONCAT('KILL ', id, ';') FROM information_schema.processlist
WHERE command = 'Sleep' AND time > 300;

-- 临时调大最大连接数 (需 SUPER 权限)
SET GLOBAL max_connections = 500;
```

**永久方案:**
1. 检查应用连接池配置: 确保 `maxPoolSize` 不超过数据库 max_connections 的 70%
2. 设置连接超时: `wait_timeout = 300` (5分钟), `interactive_timeout = 300`
3. 启用连接池验证: `validationQuery=SELECT 1`, `testOnBorrow=true`
4. 添加监控告警: 当连接数 > 80% 阈值时触发告警

---

## 2. 慢查询导致 CPU 飙升

### 现象
- CPU 使用率持续 > 90%
- 业务响应变慢
- `SHOW PROCESSLIST` 显示大量 `Sending data` 状态

### 排查步骤
1. 开启慢查询日志: `SET GLOBAL slow_query_log = ON;`
2. 设置阈值: `SET GLOBAL long_query_time = 1;`
3. 使用 pt-query-digest 分析慢查询日志
4. 查看当前正在执行的慢查询:
```sql
SELECT * FROM information_schema.processlist
WHERE command != 'Sleep' AND time > 5
ORDER BY time DESC;
```

### 解决方案
1. **添加索引**: 对 WHERE/JOIN/ORDER BY 列创建合适索引
   ```sql
   CREATE INDEX idx_created_at ON orders(created_at);
   CREATE INDEX idx_user_status ON users(user_id, status);
   ```
2. **优化查询**: 避免 SELECT *, 使用 LIMIT, 拆分大表 JOIN
3. **读写分离**: 读请求走只读副本, 写请求走主库
4. **查
  ... (共 2000 chars，已截断)

[指标 5] Agent 最终答案对比

  ── 基线 (无 RAG) 答案 (0 chars) ──
  

  ── 有 RAG 答案 (1112 chars) ──
  查询完成！以下是生产环境（prd）中各业务子域的 RDS 实例告警统计，按告警数量从多到少排列：

**执行的 SQL：**
```sql
SELECT ri.business_subdomain, COUNT(ah.id) AS alert_count 
FROM db_rds_instance ri 
JOIN db_alert_history ah ON ri.db_instance_id = ah.db_instance_id 
WHERE ri.env_type = 'prd' 
GROUP BY ri.business_subdomain 
ORDER BY alert_count DESC
```

### 📊 生产环境 RDS 告警统计（按业务子域）

| 排名 | 业务子域 | 告警数量 |
|------|----------|----------|
| 1 | 风控-风控技术 | 3,755 |
| 2 | 客服 | 3,026 |
| 3 | 国际技术-交易&资金 | 2,947 |
| 4 | 交易平台-用户 | 2,346 |
| 5 | 算法平台-算法工程 | 2,323 |
| 6 | 供应链平台-履约域 | 1,866 |
| 7 | 技术保障-运维开发 | 1,782 |
| 8 | 汇金平台-支付 | 1,754 |
| 9 | 国际技术-国际商品 | 1,722 |
| 10 | 数据平台-离线数仓 | 1,641 |
| 11 | 社区技术-社区后端 | 1,583 |
| 12 | 交易平台-订单 | 890 |
| 13 | 算法平台-推荐 | 668 |
| 14 | 商家 | 662 |
| 15 | 稳定生产-监控平台 | 633 |
| 16 | 供应链平台-仓储域 | 278 |
| 17 | 供应链平台-计费域 | 218 |
| 18 | 前端平台 | 171 |
| 19 | 数据平台-数据研发 | 145 |
| 20 | 算法平台-搜索工程 | 115 |
| ... | （共 44 个业务子域） | ... |

### 🔑 关键发现

- **告警最多的 TOP 3**：**风控-风控技术**（3,755）、**客服**（3,026）、**国际技术-交易&资金**（2,947），这三个子域合计占告警总量的比例较高
- 告警数量呈现明显的**长尾分布**，前 11 个业务子域告警均超过 1,500，而排名靠后的子域告警数量较少
- 共涉及 **44 个业务子域**，覆盖了交易、供应链、算法、数据、国际技术等多个业务方向

======================================================================
  综合判断
======================================================================
  ❌ FAIL  基线执行成功
  ✅ PASS  有 RAG 执行成功
  ✅ PASS  工具调用减少
  ✅ PASS  耗时减少
  ✅ PASS  Token 减少
  ✅ PASS  RAG 知识库已注入上下文

  通过: 5/6
  ⚠️ 大部分通过

[附录] 原始对比数据
{
  "baseline": {
    "tool_call_names": [
      "find_table",
      "find_table",
      "list_databases",
      "list_databases",
      "find_table",
      "select_database",
      "query_database",
      "describe_table",
      "describe_table",
      "describe_table",
      "describe_table",
      "query_database",
      "describe_table",
      "describe_table",
      "query_database",
      "query_database",
      "query_database",
      "query_database",
      "query_database"
    ],
    "tool_call_counts": {
      "find_table": 3,
      "list_databases": 2,
      "select_database": 1,
      "query_database": 7,
      "describe_table": 6
    },
    "sqls_count": 5,
    "duration_ms": 300249,
    "tokens": 0,
    "memory_count": 0,
    "error": "执行超时 (300s)",
    "response_preview": ""
  },
  "with_rag": {
    "tool_call_names": [
      "find_table",
      "select_database",
      "query_database"
    ],
    "tool_call_counts": {
      "find_table": 1,
      "select_database": 1,
      "query_database": 1
    },
    "sqls_count": 1,
    "duration_ms": 60696,
    "tokens": 27587,
    "memory_count": 3,
    "error": null,
    "response_preview": "查询完成！以下是生产环境（prd）中各业务子域的 RDS 实例告警统计，按告警数量从多到少排列：\n\n**执行的 SQL：**\n```sql\nSELECT ri.business_subdomain, COUNT(ah.id) AS alert_count \nFROM db_rds_instance ri \nJOIN db_alert_history ah ON ri.db_instance_id = ah.db_instance_id \nWHERE ri.env_type = 'prd' \nGROUP BY ri.business_subdomain \nORDER BY alert_count"
  }
}
