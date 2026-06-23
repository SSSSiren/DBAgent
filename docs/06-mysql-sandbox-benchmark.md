# MySQL Sandbox Benchmark

本文档说明面向 SQL 编写提效 Agent 的 MySQL sandbox benchmark。它用于离线评测 Agent 生成 SQL 的基础能力：MySQL 语法、表字段选择、只读安全、执行成功率和结果正确率。

## 1. 内容

| 路径 | 说明 |
|---|---|
| `benchmarks/mysql_sandbox/schema.sql` | 电商测试库表结构 |
| `benchmarks/mysql_sandbox/seed.sql` | 固定种子数据 |
| `benchmarks/mysql_sandbox/cases.jsonl` | 评测样本，每行一个 case |
| `app/benchmark/mysql_sandbox.py` | 加载、静态评分、MySQL 执行和结果比对逻辑 |
| `scripts/generate_predictions.py` | 调用 DBAgent 生成 `predictions.jsonl` |
| `scripts/run_mysql_sandbox_benchmark.py` | 命令行 runner |

## 2. 初始化 MySQL 测试库

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS dbagent_sandbox DEFAULT CHARACTER SET utf8mb4"
mysql -u root -p dbagent_sandbox < benchmarks/mysql_sandbox/schema.sql
mysql -u root -p dbagent_sandbox < benchmarks/mysql_sandbox/seed.sql
```

执行模式依赖 PyMySQL：

```bash
pip install PyMySQL
```

## 3. 自检评测集

用 `reference_sql` 作为预测结果，验证 schema、seed 和 runner 是否正常：

```bash
python scripts/run_mysql_sandbox_benchmark.py \
  --use-reference \
  --mysql-url "mysql://root:@127.0.0.1:3306/dbagent_sandbox"
```

如果暂时没有 MySQL，也可以只做静态检查：

```bash
python scripts/run_mysql_sandbox_benchmark.py --use-reference
```

## 4. 评测 Agent 输出

如果 DBAgent 服务已经启动，可以自动生成预测文件：

```bash
python -m app.main
```

另开一个终端：

```bash
python scripts/generate_predictions.py \
  --base-url http://127.0.0.1:8000 \
  --output predictions.jsonl
```

脚本会先调用 `/api/chat/sync`。如果当前 Agent 路由没有返回 SQL，会默认回退到项目配置的 LLM 直接生成 SQL；该回退需要 `.env` 中配置 `DEEPSEEK_API_KEY`。如需禁用回退：

```bash
python scripts/generate_predictions.py \
  --base-url http://127.0.0.1:8000 \
  --output predictions.jsonl \
  --no-fallback-direct-llm
```

调试时可以先只跑一条：

```bash
python scripts/generate_predictions.py \
  --base-url http://127.0.0.1:8000 \
  --case-id ecom_agg_001 \
  --output predictions.jsonl
```

Agent 生成结果保存为 JSONL：

```json
{"id":"ecom_agg_001","sql":"SELECT order_status, COUNT(id) AS order_count FROM orders GROUP BY order_status ORDER BY order_status;","source":"reply","error":""}
```

运行：

```bash
python scripts/run_mysql_sandbox_benchmark.py \
  --predictions predictions.jsonl \
  --mysql-url "mysql://root:@127.0.0.1:3306/dbagent_sandbox" \
  --output benchmark_report.json
```

## 5. 当前指标

| 指标 | 含义 |
|---|---|
| `static_pass_rate` | 必需 token、禁止 token、schema 命中是否通过 |
| `safety_pass_rate` | 是否为单条只读 `SELECT/WITH` |
| `schema_pass_rate` | 是否包含期望表和字段 |
| `execution_pass_rate` | 是否能在 MySQL 执行 |
| `result_accuracy` | candidate SQL 和 reference SQL 的结果 hash 是否一致 |

## 6. 扩展建议

第一版样本聚焦电商域。后续可以按真实业务逐步增加：

1. 把真实表结构抽样脱敏后加入新 domain。
2. 把用户修改过的 SQL 加入 regression set。
3. 增加 ambiguous case，评测 Agent 是否会澄清而不是硬写 SQL。
4. 增加慢查询检查，例如强制 `EXPLAIN` 并限制全表扫描。
