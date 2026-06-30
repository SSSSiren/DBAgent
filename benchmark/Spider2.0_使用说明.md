# Spider 2.0 使用说明

## 1. 概述

Spider 2.0 是由香港大学（HKU）xlang-ai 团队推出的新一代 Text-to-SQL 评测基准，专注于**真实企业级 Text-to-SQL 工作流**的评估。该基准被 **ICLR 2025 Oral** 接收。

### 核心数据

| 指标 | 数值 |
|------|------|
| 任务数量 | **615** 个（547 个 Text-to-SQL + 68 个 DBT 代码代理任务） |
| 数据库系统 | Snowflake、BigQuery、SQLite、DuckDB/DBT |
| 论文 | [Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows](https://arxiv.org/abs/2411.07763) (ICLR 2025 Oral) |

### 与 Spider 1.0 的主要区别

| 维度 | Spider 1.0 | Spider 2.0 |
|------|-----------|-----------|
| 数据库规模 | 小型 SQLite（KB~MB 级） | 企业级数据库（GB~TB 级） |
| 数据库类型 | 仅 SQLite | Snowflake、BigQuery、SQLite、DuckDB |
| 任务复杂度 | 单表/多表 SQL 查询 | 多步工作流、仓库级任务 |
| 真实度 | 学术场景 | 真实企业场景 |
| 环境 | 本地即可运行 | 需要云数据库账号 |

---

## 2. 任务设置

Spider 2.0 提供三种任务设置：

| 设置 | 类型 | 示例数 | 数据库 | 费用 |
|------|------|--------|--------|------|
| **Spider 2.0-Snow** | Text-to-SQL | 547 | Snowflake | 免费 |
| **Spider 2.0-Lite** | Text-to-SQL | 547 | BigQuery (214) + Snowflake (198) + SQLite (135) | 部分收费 |
| **Spider 2.0-DBT** | 代码代理任务 | 68 | DuckDB/DBT | 免费 |

---

## 3. 下载

### 3.1 代码仓库

```bash
git clone https://github.com/xlang-ai/Spider2.git
cd Spider2
```

### 3.2 数据集文件

数据集文件已包含在仓库中：

- `spider2-lite/` — Spider 2.0-Lite 问题文件 (`spider2-lite.jsonl`)
- `spider2-snow/` — Spider 2.0-Snow 问题文件 (`spider2-snow.jsonl`)
- `evaluation_suite/gold/sql/` — 部分黄金 SQL 参考

### 3.3 论文

- **arXiv**：https://arxiv.org/abs/2411.07763
- **OpenReview (ICLR 2025)**：https://openreview.net/forum?id=Spider2

---

## 4. 安装与配置

### 4.1 环境要求

- Python 3.10+
- Docker（Lite 和 Snow 的 Docker 方式需要）
- Snowflake 账号（Spider 2.0-Snow）
- Google Cloud 账号 + BigQuery 凭证（Spider 2.0-Lite 的 BigQuery 部分）

### 4.2 基础安装

```bash
# 克隆仓库
git clone https://github.com/xlang-ai/Spider2.git
cd Spider2

# 安装依赖
pip install -r requirements.txt
```

### 4.3 Spider 2.0-Snow 配置（推荐方式：Tool-Call）

Spider 2.0-Snow 提供 **Docker-free** 的快速评估方式 `spider-agent-tc`：

```bash
# 1. 填写 Snowflake 访问表单
# 访问：https://forms.gle/xxxxx（见仓库 README 中的 Snowflake Guideline）
# 团队会发送账号注册邮件

# 2. 配置 Snowflake 凭证
# 将收到的账号信息配置到环境变量或配置文件中

# 3. 运行 spider-agent-tc
cd methods/spider-agent-tc
# 按照该目录下的 README 进行配置和运行
```

### 4.4 Spider 2.0-Lite 配置（Docker 方式）

```bash
# 1. BigQuery 配置
# 按照仓库中的 "Bigquery Guideline" 注册 Google Cloud 账号
# 获取 BigQuery 访问凭证（服务账号 JSON 密钥文件）

# 2. Snowflake 配置
# 同 4.3 节，填写 Snowflake 访问表单

# 3. 运行 Docker 评估框架
cd methods/spider-agent-lite
# 按照该目录下的 README 配置 Docker 环境
docker-compose up
```

### 4.5 Spider 2.0-DBT 配置

```bash
# DBT 任务使用 DuckDB，无需 Docker，无费用
cd methods/spider-agent-dbt
# 按照该目录下的 README 进行配置
```

---

## 5. 数据格式

### 5.1 问题文件格式（JSONL）

`spider2-snow.jsonl` / `spider2-lite.jsonl` 每行格式：

```json
{
    "id": "snow_001",
    "db_id": "sales_db",
    "question": "What was the total revenue for each product category in Q4 2023?",
    "instruction": "Write a SQL query to calculate...",
    "database_type": "snowflake",
    "tables": ["orders", "products", "categories"],
    "evidence": "Revenue is calculated as quantity * unit_price..."
}
```

### 5.2 黄金 SQL 格式

位于 `evaluation_suite/gold/sql/` 目录下，按任务 ID 组织。

---

## 6. Text-to-SQL 使用流程（核心）

### 6.1 喂给模型的输入：从数据文件中取什么

Spider 2.0 的 Text-to-SQL 输入是 **自然语言问题 + 数据库 Schema + 可选的外部知识**。

#### 输入来源：`spider2-snow.jsonl` / `spider2-lite.jsonl`

```python
import json

questions = []
with open('spider2-snow/spider2-snow.jsonl', 'r') as f:
    for line in f:
        questions.append(json.loads(line))

for q in questions:
    # 以下字段喂给模型：
    question   = q['question']      # ← 自然语言问题
    db_id      = q['db_id']          # ← 数据库名，用于获取 schema
    tables     = q.get('tables', []) # ← 涉及的表名列表
    evidence   = q.get('evidence', '') # ← 外部知识（可选）
    db_type    = q.get('database_type', '') # ← 数据库类型（snowflake/bigquery/sqlite）

    # 以下字段不喂给模型：
    gold_sql   = q.get('SQL')        # ← 黄金 SQL，仅用于评估
```

### 6.2 构建 Prompt（完整示例）

```python
def build_prompt_spider2(question, db_schema_text, evidence=None):
    """将 Spider 2.0 数据构建为 Text-to-SQL 的 prompt"""

    prompt_parts = [f"Database Schema:\n{db_schema_text}\n"]

    if evidence:
        prompt_parts.append(f"Additional Context:\n{evidence}\n")

    prompt_parts.append(f"Question: {question}\n")
    prompt_parts.append("Write a SQL query to answer the question.\nSQL:")

    return '\n'.join(prompt_parts)


# 使用示例
q = questions[0]
prompt = build_prompt_spider2(
    question=q['question'],
    db_schema_text=get_schema_for_db(q['db_id']),  # 从 Snowflake/BigQuery 获取 schema
    evidence=q.get('evidence')
)
print(prompt)
```

**实际生成的 prompt 示例**：

```text
Database Schema:

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    order_date DATE,
    total_amount DECIMAL(10,2)
)
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR(100),
    region VARCHAR(50)
)
FOREIGN KEY (orders.customer_id) REFERENCES customers(customer_id)

Additional Context:
Revenue is calculated as total_amount before any discounts.

Question: What was the total revenue for each customer in the West region during 2023?

Write a SQL query to answer the question.
SQL:
```

### 6.3 模型输出

模型只需要输出 **纯 SQL 字符串**：

```text
SELECT c.name, SUM(o.total_amount) AS total_revenue
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE c.region = 'West' AND o.order_date BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY c.name
```

### 6.4 评估：模型输出 vs 黄金 SQL

```python
# 1. 收集模型预测
predictions = []
for q in questions:
    schema = get_schema_for_db(q['db_id'])
    prompt = build_prompt_spider2(q['question'], schema, q.get('evidence'))
    pred_sql = your_model.generate(prompt)
    predictions.append({
        "id": q['id'],
        "db_id": q['db_id'],
        "predicted_sql": pred_sql
    })

# 2. 写入预测文件（JSONL 格式）
with open('predictions.jsonl', 'w') as f:
    for pred in predictions:
        f.write(json.dumps(pred) + '\n')

# 3. 运行评估
# cd evaluation_suite/
# python evaluate.py --pred_file ../predictions.jsonl --gold_dir ./gold/sql/ --setting snow
```

### 6.5 完整端到端流程图

```
┌──────────────────────────────────────────────────────────────┐
│                  Spider 2.0 Text-to-SQL 使用流程               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ① 加载数据                                                   │
│     spider2-snow.jsonl / spider2-lite.jsonl                   │
│       ──→  question  (文本)                                    │
│       ──→  db_id + tables (用于查 schema)                      │
│       ──→  evidence  (外部知识，可选)                            │
│                                                              │
│  ② 获取 Schema（关键差异 vs Spider 1.0）                        │
│     Snowflake/BigQuery/SQLite  ──→  真实企业 schema            │
│     (通过云连接或本地 Docker 获取)                               │
│                                                              │
│  ③ 构建 Prompt                                                │
│     question + schema + evidence  ──→  prompt 文本             │
│                                                              │
│  ④ 喂给模型推理                                               │
│     prompt  ──→  模型  ──→  predicted_SQL                     │
│                                                              │
│  ⑤ 评估                                                       │
│     predicted_SQL  vs  gold_SQL  ──→  EX / EM 分数            │
│     (在真实云数据库上执行比较结果)                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 6.6 关键数据字段对照表

| 文件 | 字段 | 用途 | 是否喂给模型 |
|------|------|------|:---:|
| `spider2-snow.jsonl` / `spider2-lite.jsonl` | `question` | 自然语言问题 | ✅ 喂给模型 |
| `spider2-snow.jsonl` / `spider2-lite.jsonl` | `db_id` | 数据库标识 | 用于查找 schema |
| `spider2-snow.jsonl` / `spider2-lite.jsonl` | `tables` | 涉及的表名 | ✅ 可选，帮助缩小范围 |
| `spider2-snow.jsonl` / `spider2-lite.jsonl` | `evidence` | 外部知识提示 | ✅ 喂给模型 |
| `spider2-snow.jsonl` / `spider2-lite.jsonl` | `database_type` | 数据库类型 | ✅ 可选，帮助生成方言 |
| 云数据库（Snowflake/BQ） | 实际 schema | 表结构 | ✅ 喂给模型（需通过连接获取） |
| `evaluation_suite/gold/sql/` | 黄金 SQL | 标准答案 | ❌ 仅用于评估 |

---

## 7. 评估方法详解

### 7.1 自评估

所有示例和黄金答案已发布，可自行评估：

```bash
# 使用评估套件
cd evaluation_suite/

# 运行评估（具体命令参见 evaluation_suite/README.md）
python evaluate.py \
    --pred_file ../predictions.jsonl \
    --gold_dir ./gold/sql/ \
    --setting snow  # 或 lite
```

### 7.2 官方排行榜提交

如需将结果提交到官方排行榜：

1. 按照仓库中的 **Submission Guidance** 文档准备提交文件
2. 确保方法可复现
3. 通过指定渠道提交（详见仓库 README）

### 7.3 评估指标

| 指标 | 说明 |
|------|------|
| **Execution Accuracy (EX)** | 预测 SQL 执行结果与黄金结果是否一致 |
| **Exact Set Match (EM)** | SQL 各子句的集合匹配准确率 |

---

## 8. 使用示例

### 8.1 加载问题数据

```python
import json

# 加载 Spider 2.0-Snow 问题
questions = []
with open('spider2-snow/spider2-snow.jsonl', 'r') as f:
    for line in f:
        questions.append(json.loads(line))

print(f"Loaded {len(questions)} questions")
print(questions[0]['question'])
```

### 8.2 生成预测文件

```python
# 预测文件格式（JSONL）
predictions = []
for q in questions:
    predictions.append({
        "id": q["id"],
        "db_id": q["db_id"],
        "predicted_sql": "SELECT ... FROM ... WHERE ..."
    })

with open('predictions.jsonl', 'w') as f:
    for pred in predictions:
        f.write(json.dumps(pred) + '\n')
```

---

## 9. 注意事项

1. **Snowflake 访问需要申请**：Spider 2.0-Snow 需要填写访问表单，团队会发送账号注册邮件
2. **BigQuery 可能产生费用**：Spider 2.0-Lite 中的 BigQuery 查询可能产生 Google Cloud 费用
3. **Snowflake 查询排队**：Spider 2.0-Snow 免费使用，但查询会排队执行
4. **黄金 SQL 仅部分公开**：只公开少量黄金 SQL 用于方法设计和 prompt 调试，不建议用于微调
5. **Oracle Tables 标注**：如使用 ground-truth 表信息，需在提交时注明
6. **DBT 任务独立**：Spider 2.0-DBT 是代码代理任务而非纯 SQL 生成，评估方式不同

---

## 10. 参考资源

- **论文**：https://arxiv.org/abs/2411.07763
- **GitHub 仓库**：https://github.com/xlang-ai/Spider2
- **官方主页**：https://spider2-lily.github.io
- **Spider 1.0**：https://github.com/taoyds/spider
- **xlang-ai 团队**：https://github.com/xlang-ai
