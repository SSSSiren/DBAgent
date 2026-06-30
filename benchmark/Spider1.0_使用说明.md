# Spider 1.0 使用说明

## 1. 概述

Spider 1.0 是由耶鲁大学 11 名学生创建的大规模语义解析和 Text-to-SQL 数据集。它是 Text-to-SQL 领域最经典的跨领域评测基准之一。

### 核心数据

| 指标 | 数值 |
|------|------|
| 问题数量 | **10,181** 条 |
| 唯一 SQL 查询 | **5,693** 条 |
| 数据库数量 | **200** 个 |
| 覆盖领域 | **138** 个 |
| 数据库类型 | SQLite |
| 论文 | [Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task](https://arxiv.org/abs/1809.08887) (EMNLP 2018) |

### 核心特点

- **跨领域泛化**：训练集和测试集的数据库 schema 不重叠，要求模型具备泛化到新数据库的能力
- **复杂 SQL**：包含 JOIN、NESTED、GROUP BY、ORDER BY、HAVING、子查询等复杂 SQL 结构
- **难度分级**：分为 Easy、Medium、Hard、Extra Hard 四个难度等级

---

## 2. 下载

### 2.1 数据集下载

- **Google Drive（官方）**：https://drive.google.com/file/d/1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J/view?usp=sharing
- **GitHub 仓库**：https://github.com/taoyds/spider
- **Hugging Face 镜像**：https://huggingface.co/datasets/spider

```bash
# 方式一：从 Google Drive 下载
# 访问上述 Google Drive 链接，手动下载 spider.zip

# 方式二：从 GitHub 克隆（包含基线模型和评估脚本）
git clone https://github.com/taoyds/spider.git
cd spider
```

### 2.2 评估脚本下载

```bash
# Test Suite Accuracy 评估（官方推荐指标）
git clone https://github.com/taoyds/test-suite-sql-eval.git
```

---

## 3. 数据集结构

下载解压后的目录结构：

```
spider/
├── train_spider.json      # 训练集（约 7,000 条）
├── train_others.json      # 额外训练数据
├── dev.json               # 验证集（约 1,034 条）
├── test.json              # 测试集（约 2,147 条，已公开发布）
├── tables.json            # 数据库 schema 定义
├── database/              # 200 个 SQLite 数据库文件
│   ├── academic/
│   │   └── academic.sqlite
│   ├── ...
│   └── ...
└── evaluation.py          # 基础评估脚本
```

### 3.1 数据格式

**train_spider.json / dev.json** 每条记录格式：

```json
{
    "db_id": "academic",
    "question": "How many heads of the departments are older than 56?",
    "query": "SELECT count(*) FROM head WHERE age > 56",
    "question_toks": ["How", "many", "heads", "of", "the", "departments", "are", "older", "than", "56", "?"],
    "query_toks": ["SELECT", "count", "(", "*", ")", "FROM", "head", "WHERE", "age", ">", "56"],
    "sql": {
        "select": [false, [[[3, [0, [0, 0, false], null]], false]]],
        "from": {"table_units": [["table_unit", 0]], "conds": []},
        "where": [[false, 2, [0, [0, 1, false], null]]],
        ...
    }
}
```

**tables.json** 每条记录格式：

```json
{
    "db_id": "academic",
    "table_names_original": ["department", "head", "course"],
    "table_names": ["department", "head", "course"],
    "column_names_original": [[-1, "*"], [0, "department_id"], [0, "name"], ...],
    "column_names": [[-1, "*"], [0, "department id"], [0, "name"], ...],
    "column_types": ["text", "number", "text", ...],
    "foreign_keys": [[1, 0], ...],
    "primary_keys": [0, 1, ...]
}
```

---

## 4. Text-to-SQL 使用流程（核心）

这是本文档最关键的章节：解释**你给模型喂什么数据、模型输出什么、怎么评估**。

### 4.1 喂给模型的输入：从数据文件中取什么

Text-to-SQL 任务的核心输入是 **自然语言问题 + 数据库 Schema**。你需要从 Spider 的数据文件中提取以下内容拼成 prompt：

#### 输入来源 1：`train_spider.json` / `dev.json` — 取 `question` 字段

```python
import json

with open('spider/dev.json', 'r') as f:
    dev_data = json.load(f)

for item in dev_data:
    question = item['question']      # ← 自然语言问题，喂给模型
    db_id    = item['db_id']          # ← 对应的数据库名，用于查找 schema
    gold_sql = item['query']          # ← 黄金 SQL，仅用于评估，不喂给模型
```

#### 输入来源 2：`tables.json` — 取对应数据库的 Schema

```python
with open('spider/tables.json', 'r') as f:
    tables = json.load(f)

# 按 db_id 查找 schema
db_schema = next(t for t in tables if t['db_id'] == db_id)

# Schema 中包含：
#   table_names_original  — 表名列表
#   column_names_original — 列名列表 [table_index, column_name]
#   column_types          — 列类型 (text/number/time/boolean)
#   foreign_keys          — 外键关系 [[col_a, col_b], ...]
#   primary_keys          — 主键列索引
```

### 4.2 构建 Prompt（完整示例）

将 question 和 schema 拼接成给模型的输入：

```python
def build_prompt(question, db_schema):
    """将 Spider 数据构建为 Text-to-SQL 的 prompt"""
    
    # 1. 构建 schema 文本
    schema_lines = []
    for i, table_name in enumerate(db_schema['table_names_original']):
        # 找到属于该表的列
        columns = [
            (col_name, col_type)
            for (table_idx, col_name), col_type in zip(
                db_schema['column_names_original'][1:],  # 跳过 [-1, "*"]
                db_schema['column_types'][1:]
            )
            if table_idx == i
        ]
        col_str = ', '.join(f"{name} ({dtype})" for name, dtype in columns)
        # 标记主键
        pk_cols = [
            db_schema['column_names_original'][pk][1]
            for pk in db_schema['primary_keys']
            if db_schema['column_names_original'][pk][0] == i
        ]
        pk_str = f"  PRIMARY KEY: {', '.join(pk_cols)}" if pk_cols else ""
        schema_lines.append(f"CREATE TABLE {table_name} ({col_str}){pk_str}")
    
    # 2. 添加外键
    fk_lines = []
    for fk in db_schema['foreign_keys']:
        from_col = db_schema['column_names_original'][fk[0]]
        to_col = db_schema['column_names_original'][fk[1]]
        from_table = db_schema['table_names_original'][from_col[0]]
        to_table = db_schema['table_names_original'][to_col[0]]
        fk_lines.append(
            f"FOREIGN KEY ({from_table}.{from_col[1]}) REFERENCES {to_table}({to_col[1]})"
        )
    
    schema_text = '\n'.join(schema_lines + fk_lines)
    
    # 3. 拼接最终 prompt
    prompt = f"""Given the following database schema:

{schema_text}

Write a SQL query for the following question:

Question: {question}

SQL:"""
    
    return prompt


# 使用示例
item = dev_data[0]
schema = next(t for t in tables if t['db_id'] == item['db_id'])
prompt = build_prompt(item['question'], schema)
print(prompt)
```

**实际生成的 prompt 示例**：

```text
Given the following database schema:

CREATE TABLE department (Department_ID (number), Name (text), Creation (text), Ranking (number), Budget_in_Billions (number), Num_Employees (number))
  PRIMARY KEY: Department_ID
CREATE TABLE head (head_ID (number), name (text), born_state (text), age (number))
  PRIMARY KEY: head_ID
CREATE TABLE management (department_ID (number), head_ID (number), temporary_acting (text))
FOREIGN KEY (management.department_ID) REFERENCES department(Department_ID)
FOREIGN KEY (management.head_ID) REFERENCES head(head_ID)

Write a SQL query for the following question:

Question: How many heads of the departments are older than 56?

SQL:
```

### 4.3 模型输出

模型只需要输出 **纯 SQL 字符串**，不需要额外包装：

```text
SELECT count(*) FROM head WHERE age > 56
```

### 4.4 评估：模型输出 vs 黄金 SQL

```python
# 1. 收集模型预测
predictions = []
gold_lines = []

for item in dev_data:
    schema = next(t for t in tables if t['db_id'] == item['db_id'])
    prompt = build_prompt(item['question'], schema)
    
    pred_sql = your_model.generate(prompt)  # 你的模型推理
    predictions.append(pred_sql)
    gold_lines.append(f"{item['query']}\t{item['db_id']}")

# 2. 写入预测文件
with open('predicted_sql.txt', 'w') as f:
    for pred in predictions:
        f.write(pred.strip() + '\n')

# 3. 写入 gold 文件
with open('dev_gold.sql', 'w') as f:
    for line in gold_lines:
        f.write(line + '\n')

# 4. 运行评估
# python evaluation.py --gold dev_gold.sql --pred predicted_sql.txt --etype all --db database/ --table tables.json
```

### 4.5 完整端到端流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    Text-to-SQL 使用流程                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ① 加载数据                                                  │
│     train_spider.json / dev.json  ──→  question (文本)       │
│     tables.json                  ──→  schema   (结构)        │
│     database/*.sqlite            ──→  实际数据  (执行用)       │
│                                                             │
│  ② 构建 Prompt                                               │
│     question + schema  ──→  prompt 文本                      │
│                                                             │
│  ③ 喂给模型推理                                              │
│     prompt  ──→  模型  ──→  predicted_SQL                    │
│                                                             │
│  ④ 评估                                                      │
│     predicted_SQL  vs  gold_SQL  ──→  EM / EX 分数           │
│     (在 database/*.sqlite 上执行比较结果)                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.6 关键数据字段对照表

| 文件 | 字段 | 用途 | 是否喂给模型 |
|------|------|------|:---:|
| `train_spider.json` / `dev.json` | `question` | 自然语言问题 | ✅ 喂给模型 |
| `train_spider.json` / `dev.json` | `db_id` | 数据库标识 | 用于查找 schema |
| `train_spider.json` / `dev.json` | `query` | 黄金 SQL | ❌ 仅用于评估 |
| `tables.json` | `table_names_original` | 表名 | ✅ 喂给模型 |
| `tables.json` | `column_names_original` | 列名 | ✅ 喂给模型 |
| `tables.json` | `column_types` | 列类型 | ✅ 喂给模型 |
| `tables.json` | `foreign_keys` | 外键关系 | ✅ 喂给模型 |
| `tables.json` | `primary_keys` | 主键 | ✅ 可选 |
| `database/*.sqlite` | 实际数据 | 执行预测 SQL | ❌ 仅评估时使用 |

---

## 5. 安装与配置

### 5.1 环境要求

- Python 3.6+
- SQLite3

### 5.2 安装步骤

```bash
# 1. 解压数据集
unzip spider.zip -d spider
cd spider

# 2. 安装 Python 依赖
pip install sqlite3  # Python 自带，通常无需额外安装
```

---

## 6. 评估方法详解

### 6.1 基础评估（Component Matching）

使用仓库自带的 `evaluation.py`：

```bash
python evaluation.py \
    --gold dev_gold.sql \
    --pred predicted_sql.txt \
    --etype all \
    --db database/ \
    --table tables.json
```

参数说明：
- `--gold`：黄金 SQL 文件，格式为每行 `SQL \t db_id`
- `--pred`：预测 SQL 文件，每行一条 SQL
- `--etype`：评估类型，可选 `match`（精确集合匹配）、`exec`（执行准确率）、`all`（两者都计算）
- `--db`：SQLite 数据库目录
- `--table`：`tables.json` 文件路径

### 6.2 Test Suite Accuracy（官方推荐）

自 2020 年 11 月起，官方推荐使用 **Test Suite Accuracy** 作为主要评估指标：

```bash
git clone https://github.com/taoyds/test-suite-sql-eval.git
cd test-suite-sql-eval

# 生成测试套件
python generate_test_suite.py \
    --gold_sql_path ../spider/dev_gold.sql \
    --database_dir ../spider/database/ \
    --table_path ../spider/tables.json

# 执行评估
python evaluation.py \
    --gold ../spider/dev_gold.sql \
    --pred predicted_sql.txt \
    --db ../spider/database/ \
    --table ../spider/tables.json \
    --etype all
```

### 6.3 评估指标说明

| 指标 | 说明 |
|------|------|
| **Exact Set Match (EM)** | 将 SQL 分解为多个子句（SELECT、FROM、WHERE 等），对每个子句进行集合匹配 |
| **Execution Accuracy (EX)** | 在 SQLite 数据库上执行预测 SQL 和黄金 SQL，比较结果集是否一致 |
| **Test Suite Accuracy** | 通过生成多个等价 SQL 变体来减少假阴性，更准确地衡量语义正确性 |

---

## 7. 注意事项

1. **Leaderboard 已冻结**：Spider 1.0 的排行榜已于 2024 年 2 月停止接收新提交，如需参与排行榜请使用 Spider 2.0
2. **测试集已公开**：与许多基准不同，Spider 1.0 的测试集已公开发布，可自行评估
3. **数据库 schema 不重叠**：训练/验证/测试集的数据库完全不同，确保评估的是跨领域泛化能力
4. **许可证**：数据集使用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可证

---

## 8. 参考资源

- **论文**：https://arxiv.org/abs/1809.08887
- **官方主页**：https://yale-lily.github.io/spider
- **GitHub 仓库**：https://github.com/taoyds/spider
- **评估脚本**：https://github.com/taoyds/test-suite-sql-eval
- **CodaLab 提交教程**：https://worksheets.codalab.org/worksheets/0x82150f426cb94c17b861ef4162817399/
