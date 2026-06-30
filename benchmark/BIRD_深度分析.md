# BIRD 深度分析：Agent SQL 能力测试适用性

## 1. 为什么 BIRD 值得单独分析

在三个 benchmark 中，BIRD 是唯一一个**从设计之初就考虑到了真实世界数据库交互复杂性**的基准。Spider 1.0 测的是"给定 schema 能不能写对 SQL"，Spider 2.0 测的是"企业级数据库环境下能不能写对 SQL"，而 BIRD 测的是"面对一个真实的大型数据库，你能不能理解它的内容，然后写出正确且高效的 SQL"。

这个"理解数据库内容"的过程，天然就是 Agent 的工作方式。

---

## 2. BIRD 为 Agent 测试提供的独特能力维度

### 2.1 值推理（Value Reasoning）—— Agent 的"数据探索"能力

BIRD 要求模型理解数据库中的**实际值**，而非仅依赖 schema。这是它与 Spider 最本质的区别。

**Spider 模式**：
```
已知：scores 表有 student_id, math_score, english_score 列
问题：平均数学成绩是多少？
模型：SELECT AVG(math_score) FROM scores  ← 只需理解 schema
```

**BIRD 模式**：
```
已知：scores 表有 student_id, score, subject 列
问题：平均数学成绩是多少？
模型需要先知道：subject 列中数学对应的值是什么？是 "Math"、"math"、"Mathematics" 还是 "MTH"？
```

对于 Agent 来说，这意味着：
- Agent 需要执行 `SELECT DISTINCT subject FROM scores` 来探索取值
- Agent 发现 `subject = 'MTH'` 后，才能正确写 `WHERE subject = 'MTH'`
- 如果第一次写错（`WHERE subject = 'Math'`），执行返回空结果，Agent 需要**回溯修正**

这是 BIRD 对 Agent 最核心的价值：**它迫使 Agent 先探索数据，再写 SQL**。

### 2.2 脏数据（Dirty Data）—— Agent 的"错误恢复"能力

BIRD 的数据库包含真实世界的数据格式问题：
- 缩写：`"CA"` vs `"California"` vs `"Calif."`
- 拼写错误：`"recieved"` vs `"received"`
- 非标准格式：日期可能是 `"2023-01-01"`、`"01/01/2023"`、`"Jan 1, 2023"`
- 空值/NULL 处理：不同数据库的 NULL 处理方式不同

对 Agent 的考验：
```
Agent: SELECT * FROM orders WHERE order_date = '2023-01-01'
数据库: 返回空（因为实际存的是 '01/01/2023'）
Agent: 需要分析为什么返回空 → 执行 SELECT DISTINCT order_date LIMIT 5 → 发现格式差异 → 修正 SQL
```

这是典型的 Agent 错误恢复循环，Spider 1.0 和 2.0 都不具备这种场景。

### 2.3 效率评估（VES/R-VES）—— Agent 的"优化迭代"能力

BIRD 是**唯一**引入效率评估的 benchmark。VES（Valid Efficiency Score）的计算逻辑：

```
VES = Execution Accuracy × Efficiency Score

Efficiency Score：
- 如果预测 SQL 执行时间 ≤ 黄金 SQL 执行时间 → 1.0
- 如果预测 SQL 执行时间 > 黄金 SQL 执行时间 → 按比例扣分
```

这直接对应 Agent 的优化循环：
```
Agent 第1轮：生成 SQL → 执行耗时 5.2s → VES 低
Agent 第2轮：分析执行计划 → 发现缺少索引利用 → 重写 SQL → 执行耗时 0.3s → VES 高
```

**这是其他任何 benchmark 都无法提供的 Agent 能力测试维度**。

### 2.4 evidence 字段 —— Agent 的"知识整合"能力

BIRD 的 `evidence` 字段是专家标注的外部知识，例如：
```
问题：Which students manage to generate the highest income?
evidence：Income is stored in the income table. The highest income should be calculated
          after joining member and income tables, not from the raw income table alone.
```

对 Agent 的两种测试模式：
- **LLM 模式**：把 evidence 直接喂给模型
- **Agent 模式**：不提供 evidence，Agent 自己通过探索数据来推理出这些知识

---

## 3. 现有代码库的适配分析

### 3.1 已有的基础设施

当前项目已有完整的 Spider 1.0 benchmark 集成：

```
app/benchmark/
├── __init__.py
├── spider_loader.py    # 数据加载：SpiderSchema, SpiderExample, load_tables()
├── spider_prompt.py    # Prompt 构建：build_prompt()
├── spider_runner.py    # 核心运行器：并发调用 LLM，提取 SQL
├── spider_evaluator.py # 评估模块

scripts/
└── run_spider_benchmark.py  # CLI 入口
```

`app/tools/` 下的 Agent 工具：
- `list_databases_tool` / `select_database_tool` / `list_tables_tool` / `describe_table_tool`：Schema 探索工具
- `query_database_tool`：NL2SQL 工具
- `execute_sql_tool`：直接执行 SQL

### 3.2 BIRD 与 Spider 的数据格式差异

| 维度 | Spider 1.0 | BIRD | 适配难度 |
|------|-----------|------|:---:|
| 问题文件 | `dev.json` | `dev.json` | 低 |
| 问题字段 | `question` | `question` + `evidence` | 低 |
| Schema 来源 | `tables.json`（集中式） | `database_description/*.csv`（分散式） | 中 |
| 数据库文件 | `database/{db_id}/{db_id}.sqlite` | `dev_databases/{db_id}/{db_id}.sqlite` | 低 |
| 黄金 SQL 字段 | `query` | `SQL` | 低 |
| 评估指标 | EM + EX | EX + VES + R-VES | 高 |
| 预测文件格式 | 每行一条 SQL | `SQL\t----- bird -----\tdb_id` | 低 |

### 3.3 关键适配点

**① Schema 加载方式完全不同**

Spider 的 schema 来自 `tables.json`（一个 JSON 文件包含所有 schema）：
```python
# Spider 模式
tables = json.load(open('tables.json'))
schema = tables['academic']  # 直接索引
```

BIRD 的 schema 来自每个数据库目录下的 CSV 文件：
```python
# BIRD 模式
# 需要读取 database_description/tables.csv 和 columns.csv
# 这些 CSV 包含表名、列名、类型、描述、示例值
```

**② evidence 字段是 BIRD 独有**

Spider 没有外部知识字段，BIRD 的 `evidence` 可以：
- 直接喂给 LLM（LLM 模式）
- 不提供，让 Agent 自己探索（Agent 模式）

**③ 评估指标不同**

Spider 只有 EM 和 EX。BIRD 额外有 VES（效率评估），需要：
- 测量每个预测 SQL 的执行时间
- 与黄金 SQL 的执行时间比较
- 计算效率得分

---

## 4. BIRD 的 Agent 测试场景设计

### 4.1 场景一：Schema 探索（基础 Agent 能力）

**输入**：只给 Agent 数据库连接（SQLite 路径），不给 schema 描述
**Agent 行为**：
1. 连接数据库
2. 执行 `SELECT name FROM sqlite_master WHERE type='table'` 获取表名
3. 执行 `PRAGMA table_info({table})` 获取列信息
4. 执行 `SELECT * FROM {table} LIMIT 3` 查看示例数据
5. 基于探索结果生成 SQL

**评估**：最终 SQL 的 EX 分数

### 4.2 场景二：值探索（BIRD 核心场景）

**输入**：Agent 有 schema 但不知道具体取值
**Agent 行为**：
1. 读问题："Find the average math score"
2. 查看 schema：`scores` 表有 `subject` 列（类型 TEXT）
3. 执行 `SELECT DISTINCT subject FROM scores` → 发现值是 `"MTH"` 不是 `"Math"`
4. 生成正确 SQL：`SELECT AVG(score) FROM scores WHERE subject = 'MTH'`

**评估**：正确率 — 如果 Agent 不做值探索，直接写 `WHERE subject = 'Math'`，必然错误

### 4.3 场景三：效率优化（BIRD 独有）

**输入**：Agent 生成 SQL 后可以执行并查看耗时
**Agent 行为**：
1. 生成 SQL：`SELECT * FROM large_table WHERE condition`
2. 执行 → 耗时 5.2s（慢）
3. 分析：表太大，需要加索引利用或优化 JOIN 顺序
4. 重写 SQL：`SELECT needed_cols FROM large_table USE INDEX (idx) WHERE condition`
5. 执行 → 耗时 0.3s（快）
6. 提交优化后的 SQL

**评估**：VES 分数 — 直接反映 Agent 的优化能力

### 4.4 场景四：错误恢复（脏数据场景）

**输入**：Agent 生成的 SQL 执行报错或返回意外结果
**Agent 行为**：
1. 生成 SQL → 执行报错：`no such column: order_date`
2. 执行 `PRAGMA table_info(orders)` → 发现列名是 `order_dt`
3. 修正 SQL → 执行成功但返回空
4. 执行 `SELECT order_dt FROM orders LIMIT 5` → 发现日期格式是 `MM/DD/YYYY`
5. 修正 WHERE 条件 → 返回正确结果

**评估**：Agent 能否在有限步数内完成修正

---

## 5. 接入方案（不改动现有代码）

### 5.1 设计原则

1. **零侵入**：不动 `app/` 下的任何现有代码
2. **独立模块**：在 `app/benchmark/` 下新增 BIRD 专用文件
3. **复用接口**：复用现有的 `SpiderExample`/`SpiderSchema` 数据类，或定义等价的 BIRD 数据类
4. **独立入口**：在 `scripts/` 下新增 `run_bird_benchmark.py`

### 5.2 新增文件清单

```
app/benchmark/
├── bird_loader.py      # 新增：BIRD 数据加载器
├── bird_prompt.py      # 新增：BIRD Prompt 构建（含 evidence 支持）
├── bird_runner.py      # 新增：BIRD 运行器（LLM 模式）
├── bird_agent_runner.py # 新增：BIRD Agent 运行器（Agent 模式）
└── bird_evaluator.py   # 新增：BIRD 评估器（EX + VES）

scripts/
└── run_bird_benchmark.py  # 新增：CLI 入口
```

### 5.3 数据流设计

```
LLM 模式（不改动现有 Agent 逻辑）：
  bird_loader.py  →  question + evidence + CSV schema
  bird_prompt.py  →  prompt 文本
  bird_runner.py  →  LLM 推理 → SQL
  bird_evaluator.py → EX / VES 分数

Agent 模式（复用现有 Agent 工具）：
  bird_loader.py  →  question + db_path（不给 schema）
  bird_agent_runner.py → 调用现有 Agent（仅给 db_path + question）
  Agent 自行探索 → SQL
  bird_evaluator.py → EX / VES 分数
```

### 5.4 与现有代码的关系

| 现有文件 | 是否改动 | 说明 |
|----------|:---:|------|
| `app/agent/llm_agent.py` | ❌ 不改 | Agent 定义不变 |
| `app/tools/agent_tools.py` | ❌ 不改 | 工具定义不变 |
| `app/tools/sql_executor.py` | ❌ 不改 | SQL 执行不变 |
| `app/benchmark/spider_loader.py` | ❌ 不改 | Spider 加载器保持独立 |
| `app/benchmark/spider_runner.py` | ❌ 不改 | Spider 运行器保持独立 |
| `app/benchmark/__init__.py` | ❌ 不改 | 不需要注册新模块 |
| `scripts/run_spider_benchmark.py` | ❌ 不改 | Spider CLI 保持独立 |

### 5.5 BIRD 数据放置

```bash
data/
├── spider/          # 已有：Spider 1.0 数据
├── bird/            # 新增：BIRD 数据
│   ├── dev.json
│   ├── train.json
│   └── dev_databases/
│       ├── california_schools/
│       │   ├── california_schools.sqlite
│       │   └── database_description/
│       └── ...
└── bird_mini_dev/   # 新增：BIRD Mini-Dev（推荐入门）
```

---

## 6. BIRD 的局限性

### 6.1 对 Agent 测试的不足

| 不足 | 说明 |
|------|------|
| **无多轮对话设计** | BIRD 是单轮 question → SQL，不涉及多轮交互 |
| **无子任务分解** | 问题都是单步 SQL，不涉及"先查 A 再根据 A 的结果查 B" |
| **evidence 是预标注的** | 外部知识由专家预先写好，Agent 不需要从外部知识库检索 |
| **无工具选择** | Agent 不需要决策"用哪个工具"，只需要决策"探索哪些数据" |
| **评估是单次的** | 评估只看最终 SQL，不评估 Agent 的探索过程质量 |

### 6.2 数据规模的实际挑战

完整 BIRD 数据集 33.4 GB，95 个数据库。对 Agent 测试意味着：
- 如果 Agent 每次探索都 `SELECT *`，token 消耗巨大
- 需要 Agent 具备智能采样能力（`LIMIT 5`、`DISTINCT`、`COUNT`）
- Mini-Dev（500 条）更适合快速验证

### 6.3 与真实 Agent 场景的差距

BIRD 仍然是一个**有标准答案的 benchmark**。真实 Agent 场景中：
- 用户的问题可能模糊，需要 Agent 主动澄清
- 数据库可能持续变化，Agent 需要适应
- 可能存在多个等价正确的 SQL，评估标准是"用户满意度"而非"与黄金 SQL 一致"

---

## 7. 总结

### 7.1 BIRD 对 Agent 测试的核心价值排名

| 排名 | 能力维度 | BIRD 独特性 | 对 Agent 的价值 |
|:---:|------|:---:|------|
| 1 | **效率优化** | 唯一有 VES 的 benchmark | 支撑完整的"执行→分析→优化" Agent 循环 |
| 2 | **值推理** | 强调数据库内容而非仅 schema | 迫使 Agent 先探索数据再写 SQL |
| 3 | **脏数据** | 真实世界数据格式 | 迫使 Agent 处理错误、修正推理 |
| 4 | **外部知识** | evidence 字段 | 可对比 Agent 自行推理 vs 给定知识的差异 |

### 7.2 一句话结论

**BIRD 是三个 benchmark 中最适合测试 Agent SQL 能力的，但需要改造：去除预提供的 schema 和 evidence，只给 Agent 数据库连接，让它自行探索、推理、优化。其中 VES 效率评估是 BIRD 独一无二的优势，能直接量化 Agent 的"执行→分析→优化"反馈循环能力。**

### 7.3 接入建议

现有代码库已有完整的 Spider 1.0 benchmark 集成（`app/benchmark/spider_*.py`），BIRD 可以完全独立地复制这个模式，**零改动现有代码**：
- 新增 `app/benchmark/bird_*.py`（loader / prompt / runner / agent_runner / evaluator）
- 新增 `scripts/run_bird_benchmark.py`
- 数据放 `data/bird/` 或 `data/bird_mini_dev/`