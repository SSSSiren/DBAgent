# BIRD 使用说明

## 1. 概述

BIRD（**BI**g Bench for La**R**ge-scale **D**atabase Grounded Text-to-SQL Evaluation）是一个开创性的跨领域 Text-to-SQL 评测基准，专注于评估模型在**大规模数据库内容**背景下的 SQL 生成能力。

### 核心数据

| 指标 | 数值 |
|------|------|
| 问题-SQL 对 | **12,751** 条 |
| 数据库数量 | **95** 个 |
| 数据库总大小 | **33.4 GB** |
| 覆盖领域 | **37+** 个专业领域 |
| 数据库类型 | SQLite（主）、MySQL、PostgreSQL |
| 论文 | [Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs](https://arxiv.org/abs/2305.03111) (NeurIPS 2023) |

### 核心特点

- **大规模数据库内容**：不同于仅关注 schema 的基准，BIRD 强调模型需要理解和推理实际的数据库值
- **外部知识**：许多问题需要结合 `evidence`（专家标注的外部知识）才能正确生成 SQL
- **脏数据**：数据库包含真实世界格式的数据（缩写、拼写错误、非标准格式等）
- **效率评估**：首个引入 SQL 执行效率评估（VES）的基准
- **多数据库方言**：支持 SQLite、MySQL、PostgreSQL

---

## 2. 下载

### 2.1 完整数据集

| 数据集 | 下载链接 | 说明 |
|--------|----------|------|
| **训练集** | https://bird-bench.oss-cn-beijing.aliyuncs.com/train.zip | 完整训练数据 |
| **验证集** | https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip | 完整验证数据 |

```bash
# 下载训练集
wget https://bird-bench.oss-cn-beijing.aliyuncs.com/train.zip

# 下载验证集
wget https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip

# 解压
unzip train.zip -d bird_train
unzip dev.zip -d bird_dev
```

### 2.2 Mini-Dev（推荐入门）

如果完整数据集太大（33.4 GB），建议先使用 Mini-Dev（500 条示例）：

```bash
# 方式一：从 GitHub 克隆
git clone https://github.com/bird-bench/mini_dev.git
cd mini_dev

# 方式二：从 Hugging Face 加载
# https://huggingface.co/datasets/birdsql/bird_mini_dev
```

### 2.3 代码仓库

```bash
# 官方代码（包含评估脚本和基线模型）
git clone https://github.com/AlibabaResearch/DAMO-ConvAI.git
cd DAMO-ConvAI/bird

# 初始化子模块
git submodule update --init --recursive
```

---

## 3. 数据集结构

解压后的目录结构：

```
bird_dev/
├── dev.json                    # 验证集问题-SQL 对
├── dev_databases/              # 95 个数据库
│   ├── california_schools/
│   │   ├── california_schools.sqlite    # SQLite 数据库文件
│   │   └── database_description/        # Schema 和值描述（CSV）
│   │       ├── tables.csv
│   │       ├── columns.csv
│   │       └── ...
│   ├── ...
│   └── ...
└── dev_tables.json             # 数据库 schema 汇总
```

### 3.1 数据格式

**dev.json** 每条记录格式：

```json
{
    "question_id": 0,
    "db_id": "california_schools",
    "question": "What is the average math score for students in California schools?",
    "evidence": "Math score is stored in the 'scores' table under column 'math_score'.",
    "SQL": "SELECT AVG(math_score) FROM scores",
    "difficulty": "simple"
}
```

关键字段说明：
- `question`：自然语言问题
- `evidence`：专家标注的外部知识提示（模型可利用此信息）
- `SQL`：黄金标准 SQL
- `db_id`：对应的数据库 ID
- `difficulty`：难度等级（simple / moderate / challenging）

### 3.2 数据库结构

每个数据库目录包含：
- **`database_description/`**：CSV 文件，描述表结构、列含义和示例值
- **`*.sqlite`**：实际的 SQLite 数据库文件

---

## 4. Text-to-SQL 使用流程（核心）

### 4.1 喂给模型的输入：从数据文件中取什么

BIRD 的 Text-to-SQL 输入比 Spider 更丰富，核心是 **自然语言问题 + 数据库 Schema + 外部知识 (evidence)**。BIRD 的独特之处在于提供了 `database_description` 目录下的 CSV 文件来描述数据库内容和 schema。

#### 输入来源 1：`dev.json` / `train.json` — 取 `question` 和 `evidence`

```python
import json

with open('bird_dev/dev.json', 'r') as f:
    dev_data = json.load(f)

for item in dev_data:
    question = item['question']   # ← 自然语言问题，喂给模型
    evidence = item['evidence']   # ← 外部知识提示，喂给模型（BIRD 特色）
    db_id    = item['db_id']       # ← 数据库名，用于查找 schema
    gold_sql = item['SQL']         # ← 黄金 SQL，仅用于评估，不喂给模型
    difficulty = item['difficulty'] # ← 难度等级，可选
```

#### 输入来源 2：`database_description/` 目录 — 取 Schema 和值描述

BIRD 每个数据库目录下都有 `database_description/` 文件夹，包含 CSV 文件描述表结构、列含义和示例值：

```python
import csv
import os

def load_database_description(db_path):
    """加载 BIRD 数据库的 schema 描述"""
    desc_dir = os.path.join(db_path, 'database_description')
    schema_info = {}

    for csv_file in os.listdir(desc_dir):
        if csv_file.endswith('.csv'):
            with open(os.path.join(desc_dir, csv_file), 'r') as f:
                reader = csv.DictReader(f)
                schema_info[csv_file.replace('.csv', '')] = list(reader)

    return schema_info

# 使用示例
db_path = 'bird_dev/dev_databases/california_schools'
schema_info = load_database_description(db_path)

# schema_info 包含：
#   'tables.csv'     — 表名和表描述
#   'columns.csv'    — 列名、类型、描述、示例值
#   'foreign_keys.csv' — 外键关系
```

### 4.2 构建 Prompt（完整示例）

BIRD 官方推荐将 `database_description` 中的 CSV 信息 + `evidence` + `question` 拼接成 prompt：

```python
def build_prompt_bird(question, evidence, db_path):
    """将 BIRD 数据构建为 Text-to-SQL 的 prompt"""

    desc_dir = os.path.join(db_path, 'database_description')

    # 1. 读取 tables.csv
    tables_text = ""
    with open(os.path.join(desc_dir, 'tables.csv'), 'r') as f:
        tables_text = f.read()

    # 2. 读取 columns.csv（包含列描述和示例值，这是 BIRD 的关键）
    columns_text = ""
    with open(os.path.join(desc_dir, 'columns.csv'), 'r') as f:
        columns_text = f.read()

    # 3. 构建 schema 文本
    schema_text = f"""Tables:
{tables_text}

Columns:
{columns_text}"""

    # 4. 拼接完整 prompt
    prompt = f"""Given the following database schema:

{schema_text}

External Knowledge:
{evidence if evidence else 'None'}

Question: {question}

Please generate the SQL query.
SQL:"""

    return prompt


# 使用示例
item = dev_data[0]
db_path = f"bird_dev/dev_databases/{item['db_id']}"
prompt = build_prompt_bird(item['question'], item['evidence'], db_path)
print(prompt)
```

**实际生成的 prompt 示例**：

```text
Given the following database schema:

Tables:
Table Name,Description
scores,Student test scores across subjects and grades
schools,California school information

Columns:
Table Name,Column Name,Type,Description,Sample Values
scores,student_id,INTEGER,Unique student identifier,"1001, 1002, 1003"
scores,math_score,INTEGER,Math test score (0-100),"85, 92, 78"
scores,english_score,INTEGER,English test score (0-100),"90, 88, 95"
scores,grade,INTEGER,Grade level (9-12),"9, 10, 11, 12"
schools,school_id,INTEGER,Unique school identifier,"S001, S002"
schools,school_name,TEXT,Full school name,"Lincoln High, Washington High"
schools,district,TEXT,School district name,"LAUSD, SFUSD"

External Knowledge:
Math score is stored in the 'scores' table under column 'math_score'.

Question: What is the average math score for students in California schools?

Please generate the SQL query.
SQL:
```

### 4.3 模型输出

模型只需要输出 **纯 SQL 字符串**：

```text
SELECT AVG(math_score) FROM scores
```

### 4.4 评估：模型输出 vs 黄金 SQL

```python
# 1. 收集模型预测
predictions = []
for item in dev_data:
    db_path = f"bird_dev/dev_databases/{item['db_id']}"
    prompt = build_prompt_bird(item['question'], item['evidence'], db_path)
    
    pred_sql = your_model.generate(prompt)  # 你的模型推理
    predictions.append(f"{pred_sql.strip()}\t----- bird -----\t{item['db_id']}")

# 2. 写入预测文件
# 注意 BIRD 的格式：SQL \t----- bird -----\t db_id
with open('predicted_sql.txt', 'w') as f:
    for pred in predictions:
        f.write(pred + '\n')

# 3. 运行评估
# cd ./llm/
# sh ./run/run_evaluation.sh
```

### 4.5 完整端到端流程图

```
┌──────────────────────────────────────────────────────────────┐
│                    BIRD Text-to-SQL 使用流程                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ① 加载数据                                                   │
│     dev.json                             ──→  question        │
│     dev.json                             ──→  evidence        │
│     dev.json                             ──→  db_id           │
│     database_description/tables.csv      ──→  表名 + 描述      │
│     database_description/columns.csv     ──→  列名 + 类型 +    │
│                                              描述 + 示例值     │
│                                                              │
│  ② 构建 Prompt（BIRD 特色：包含值描述和外部知识）                 │
│     question + tables.csv + columns.csv + evidence            │
│       ──→  prompt 文本                                        │
│                                                              │
│  ③ 喂给模型推理                                               │
│     prompt  ──→  模型  ──→  predicted_SQL                     │
│                                                              │
│  ④ 评估                                                       │
│     predicted_SQL  vs  gold_SQL  ──→  EX / VES / R-VES       │
│     (在 *.sqlite 上执行，同时评估正确性和效率)                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 4.6 关键数据字段对照表

| 文件 | 字段 | 用途 | 是否喂给模型 |
|------|------|------|:---:|
| `dev.json` / `train.json` | `question` | 自然语言问题 | ✅ 喂给模型 |
| `dev.json` / `train.json` | `evidence` | 外部知识提示 | ✅ 喂给模型（BIRD 特色） |
| `dev.json` / `train.json` | `db_id` | 数据库标识 | 用于查找 schema |
| `dev.json` / `train.json` | `SQL` | 黄金 SQL | ❌ 仅用于评估 |
| `dev.json` / `train.json` | `difficulty` | 难度等级 | ✅ 可选 |
| `database_description/tables.csv` | 所有列 | 表名、表描述 | ✅ 喂给模型 |
| `database_description/columns.csv` | 所有列 | 列名、类型、描述、**示例值** | ✅ 喂给模型（BIRD 核心特色） |
| `database_description/foreign_keys.csv` | 所有列 | 外键关系 | ✅ 可选 |
| `*.sqlite` | 实际数据 | 执行预测 SQL | ❌ 仅评估时使用 |

---

## 5. 安装与配置

### 5.1 环境要求

- Python 3.8+
- SQLite3（Python 自带）
- MySQL 8.0+（如需 MySQL 方言）
- PostgreSQL 14+（如需 PostgreSQL 方言）

### 5.2 基础环境配置

```bash
# 创建 Conda 环境
conda create -n bird python=3.11.5
conda activate bird

# 安装依赖
cd DAMO-ConvAI/bird
pip install -r requirements.txt
```

### 5.3 微调环境配置（T5 基线）

```bash
cd ./finetuning/

# 创建微调环境
conda env create -f finetuning.yml
conda activate finetuning

# 安装额外依赖
pip install datasets
pip install torch==1.11.0+cu113 torchvision==0.12.0+cu113 torchaudio==0.11.0 \
    --extra-index-url https://download.pytorch.org/whl/cu113

# 开始训练
sh ./run/run_bird_large.sh
```

### 5.4 LLM In-Context Learning 配置

```bash
cd ./llm/

# 安装 OpenAI SDK
pip install openai

# 运行 GPT 基线
sh ./run/run_gpt.sh
```

### 5.5 MySQL 配置（Mini-Dev 可选）

```bash
# 1. 安装 MySQL
# macOS: brew install mysql
# Linux: sudo apt-get install mysql-server

# 2. 启动 MySQL 服务
# macOS:
sudo /usr/local/mysql/support-files/mysql.server start
# Linux:
sudo systemctl start mysql

# 3. 创建 BIRD 数据库
mysql -u root -p
CREATE DATABASE BIRD;
EXIT;

# 4. 导入数据
mysql -u root -p BIRD < MINIDEV_mysql/BIRD_dev.sql

# 5. 如遇到 sql_mode=only_full_group_by 错误
mysql -u root -p
SELECT @@global.sql_mode;
SET GLOBAL sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';
```

### 5.6 PostgreSQL 配置（Mini-Dev 可选）

```bash
# 1. 安装 PostgreSQL
# macOS: brew install postgresql
# Linux: sudo apt-get install postgresql

# 2. 创建 BIRD 数据库
psql -U USERNAME -c "CREATE DATABASE BIRD;"

# 3. 导入数据
psql -U USERNAME -d BIRD -f MINIDEV_postgresql/BIRD_dev.sql
```

---

## 6. 评估方法

### 6.1 评估指标概览

BIRD 使用三种评估指标：

| 指标 | 全称 | 说明 |
|------|------|------|
| **EX** | Execution Accuracy | 预测 SQL 执行结果与黄金结果是否一致 |
| **VES** | Valid Efficiency Score | 同时评估 SQL 正确性和执行效率 |
| **R-VES** | Reward-based Valid Efficiency Score | VES 的改进版，使用奖励点机制 |

### 6.2 运行评估

```bash
cd ./llm/

# 准备预测文件
# 格式：每行 "SQL\t----- bird -----\tdb_id"
# 示例：
# SELECT AVG(math_score) FROM scores	----- bird -----	california_schools

# 运行评估
sh ./run/run_evaluation.sh
```

评估脚本位置：
- `./llm/src/evaluation.py` — 执行准确率（EX）
- `./llm/src/evaluation_ves.py` — 效率评分（VES）
- `./llm/src/evaluation_f1.py` — Soft F1 评分

### 6.3 Mini-Dev 评估

```bash
cd mini_dev/evaluation/

# 运行全部三项评估
sh run_evaluation.sh
```

### 6.4 效率评估注意事项

- 建议将 `timeout` 增加到 **3 秒/条**
- 建议重复执行 **5 次**，取最高分
- VES 基于预测 SQL 与黄金 SQL 的执行时间比率计算

---

## 7. 使用示例

### 7.1 加载数据并查询

```python
import json
import sqlite3

# 加载验证数据
with open('bird_dev/dev.json', 'r') as f:
    dev_data = json.load(f)

# 连接数据库
db_path = f"bird_dev/dev_databases/{dev_data[0]['db_id']}/{dev_data[0]['db_id']}.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 执行黄金 SQL
cursor.execute(dev_data[0]['SQL'])
result = cursor.fetchall()
print(f"Question: {dev_data[0]['question']}")
print(f"SQL: {dev_data[0]['SQL']}")
print(f"Result: {result}")
```

### 7.2 生成预测文件

```python
# 预测文件格式
predictions = []
for item in dev_data:
    pred_sql = your_model_generate(item['question'], item['evidence'])
    predictions.append(f"{pred_sql}\t----- bird -----\t{item['db_id']}")

with open('predicted_sql.txt', 'w') as f:
    for pred in predictions:
        f.write(pred + '\n')
```

### 7.3 使用 Hugging Face 加载 Mini-Dev

```python
from datasets import load_dataset

# 加载 Mini-Dev 数据集
dataset = load_dataset("birdsql/bird_mini_dev", split="train")

for item in dataset:
    print(f"Q: {item['question']}")
    print(f"SQL: {item['SQL']}")
    print(f"DB: {item['db_id']}")
    print("---")
```

---

## 8. 测试集提交

如需在 BIRD 官方测试集上评估：

1. 准备预测结果文件
2. 发送邮件至 **bird.bench23@gmail.com**
3. 遵循 [Submission Guidelines](https://docs.google.com/document/d/1Rs6d_pcs2vfqW4Ymub7Wb1XtBNlrc-WfH3T7U1ktuBo/edit)
4. 如果主要使用 OpenAI API 且不需要复杂环境，可申请快速评估通道

---

## 9. 注意事项

1. **数据库大小**：完整数据集 33.4 GB，下载和存储需要充足空间。建议入门使用 Mini-Dev
2. **外部知识依赖**：`evidence` 字段是 BIRD 的重要特色，模型应充分利用此信息
3. **效率评估**：VES 是 BIRD 独有的评估维度，不仅要求 SQL 正确，还要求高效
4. **值推理**：模型需要理解数据库中的实际值（如缩写、同义词），而非仅依赖 schema
5. **许可证**：数据集使用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可证
6. **多轮提交**：效率评估建议多次运行取最高分，因为执行时间受系统负载影响

---

## 10. 参考资源

- **论文**：https://arxiv.org/abs/2305.03111
- **官方主页**：https://bird-bench.github.io
- **GitHub 仓库**：https://github.com/AlibabaResearch/DAMO-ConvAI/tree/main/bird
- **Mini-Dev 仓库**：https://github.com/bird-bench/mini_dev
- **Hugging Face**：https://huggingface.co/datasets/birdsql/bird_mini_dev
- **提交指南**：https://docs.google.com/document/d/1Rs6d_pcs2vfqW4Ymub7Wb1XtBNlrc-WfH3T7U1ktuBo/edit
