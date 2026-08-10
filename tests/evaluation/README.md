# 评测框架使用说明

## 命令概览

```bash
python -m tests.evaluation.cli [子命令] [参数]
```

| 子命令 | 用途 |
|--------|------|
| `list` | 列出所有测试用例 |
| `run` | 运行评测，生成 JSON + Markdown 报告 |

---

## 基础命令

### 列出用例

```bash
# 列出默认测试集的全部用例
python -m tests.evaluation.cli list

# 按难度筛选
python -m tests.evaluation.cli list --difficulty Hard

# 列出 CS 测试集
python -m tests.evaluation.cli list --test-file tests/docs/test_cases_onedba_cs_evaluation.md
```

### 运行评测

```bash
# 运行全部用例
python -m tests.evaluation.cli run

# 指定用例
python -m tests.evaluation.cli run --ids TC-001 TC-005

# 重复执行取平均（消除 LLM 随机性）
python -m tests.evaluation.cli run --ids TC-001 --repeat 5

# 并发执行（加速评测）
python -m tests.evaluation.cli run --concurrency 4

# 指定数据库
python -m tests.evaluation.cli run --schema-id 24223568 --db-name dw_onedba_cs
```

---

## 对比评测模式

### HDC 数据底座对比

```bash
# 自动跑两轮：无 HDC（基线）+ 有 HDC，生成对比报告
python -m tests.evaluation.cli run --compare-hdc --ids TC-001 TC-007

# 指定 HDC 命名空间变体
python -m tests.evaluation.cli run --compare-hdc --hdc-namespace recall_complete

# 限定表白名单
python -m tests.evaluation.cli run --with-hdc --hdc-tables "order_record,account"
```

### SQL 记忆对比

```bash
# 三步对比：基线 + 填充孪生测例 + 有记忆评测
python -m tests.evaluation.cli run --compare-sql-memory --repeat 3

# 跳过填充步骤，使用已有记忆
python -m tests.evaluation.cli run --compare-sql-memory --skip-seed

# 跳过基线（从已有 JSON 加载）
python -m tests.evaluation.cli run --compare-sql-memory --skip-baseline --baseline output/baseline.json
```

### 与历史基线对比

```bash
python -m tests.evaluation.cli run --baseline output/evaluation_report_20260101_120000.json
```

---

## 模型切换

```bash
# 使用不同 LLM 模型（覆盖 .env 中的 llm_model）
python -m tests.evaluation.cli run --llm-model deepseek-v4-pro --ids TC-001
```

---

## 详细日志

```bash
# 输出 Agent 中间过程（工具调用、SQL 生成、思考过程）
python -m tests.evaluation.cli run --ids TC-001 --verbose

# 输出 HDC 注入详情
python -m tests.evaluation.cli run --with-hdc --verbose-hdc --ids TC-001
```

---

## 评判控制

```bash
# 跳过 LLM 评判（仅用结构匹配 + 结果对比）
python -m tests.evaluation.cli run --no-llm-judge

# 跳过回答质量评判
python -m tests.evaluation.cli run --no-quality-judge

# 保留 Langfuse trace（默认评测时禁用，避免污染生产 trace）
python -m tests.evaluation.cli run --keep-langfuse --ids TC-001
```

---

## 报告输出

评测完成后自动在 `tests/evaluation/output/` 下生成 JSON 和 Markdown 两份报告：

- `evaluation_report_{timestamp}.json` — 完整结构化数据
- `evaluation_report_{timestamp}.md` — 可读报告

HDC 对比报告：
- `hdc_comparison_{timestamp}.json`
- `hdc_comparison_{timestamp}.md`

SQL 记忆对比报告：
- `sql_memory_comparison_{timestamp}.json`
- `sql_memory_comparison_{timestamp}.md`

---

## 报告内容解读

### 标准报告

| 章节 | 内容 |
|------|------|
| 总览 | 通过率、平均分、平均延迟、平均工具调用、平均 Token、**平均输入/输出 Token** |
| 维度平均分 | SQL 语法、表/列引用、过滤条件、结果数据、SQL 规范 |
| 按难度分布 | Easy/Medium/Hard 分别统计 |
| 逐用例详情 | 每条用例的 SQL/质量/效率分、延迟、工具调用、**输入/输出 Token** |
| Agent 中间过程 | 每轮 LLM 调用详情 + 每次工具调用输入/输出（折叠区块） |
| 稳定性分析 | 重复执行时的标准差（工具调用、Token、**输入/输出 Token**、延迟、Turns） |
| 基线对比 | 与历史基线的各维度差异 |

### HDC 对比报告

| 章节 | 内容 |
|------|------|
| 全局对比 | 通过率、平均分、延迟、工具调用、Turns、**总/输入/输出 Token** 的差异 |
| 维度评分对比 | 5 个 SQL 维度的变化 |
| 按难度对比 | Easy/Medium/Hard 分类统计 |
| 逐用例对比 | 逐条展示分数变化、**工具调用变化、总/输入/输出 Token 变化**、首轮正确性 |
| 工具调用效率对比 | find_table/describe_table/query_database 各自的调用次数对比 |
| HDC 正确性审计 | 正确表在上下文中 / Agent 用对表 / 幻觉表名 |

### SQL 记忆对比报告

| 章节 | 内容 |
|------|------|
| 全局对比 | 基线 vs 有记忆的：SQL 分数、工具调用、**总/输入/输出 Token**、延迟 |
| Memory Impact 汇总 | 改进/退化/不变用例数量 |
| 逐用例对比 | 用例级别的分数变化和方向 |

---

## 新增可观测性指标（v1.1）

### 报告中新增列/行

| 指标 | 出现位置 | 含义 |
|------|---------|------|
| 平均输入 Token | 概览表 | prompt 消耗量 |
| 平均输出 Token | 概览表 | completion 消耗量 |
| 输入/输出 Token | 逐用例详情 | 格式 `12000/3000`，repeat>1 时含标准差 |
| 输入 Token (σ) | 稳定性分析 | 跨 repeat 的输入 Token 波动 |
| 输出 Token (σ) | 稳定性分析 | 跨 repeat 的输出 Token 波动 |
| 输入 Token 变化 | HDC/SQL 记忆对比 | 对比两轮的输入 Token 差额 |
| 输出 Token 变化 | HDC/SQL 记忆对比 | 对比两轮的输出 Token 差额 |

### 判断改进/退化的维度

| 指标方向 | 含义 | 说明 |
|---------|------|------|
| `input_token_delta < 0` | ✅ 改进 | prompt/上下文更精简 |
| `output_token_delta < 0` | ✅ 改进 | LLM 推理更高效 |
| `total_token_delta < 0` | ✅ 改进 | 总成本降低 |
| `input_token_delta > 0` | ⚠️ 退化 | 上下文膨胀，检查 HDC/记忆注入量 |
| `output_token_delta < 0 且 input_token_delta > 0` | ⚠️ tradeoff | 上下文更多但推理更少，可能 HDC 在起作用 |

### JSON 编程式消费

生成的 JSON 报告中新增字段：

```json
// CaseResult > EfficiencyMetrics
{
  "total_tokens": 15000,
  "input_tokens": 12000,       // 新增
  "output_tokens": 3000         // 新增
}

// CaseResult > RunDetail
{
  "total_tokens": 15000,
  "input_tokens": 12000,       // 新增
  "output_tokens": 3000         // 新增
}

// EvaluationReport 顶层
{
  "average_tokens": 15000.0,
  "average_input_tokens": 12000.0,    // 新增
  "average_output_tokens": 3000.0,    // 新增
  "std_input_tokens": 400.0,          // 新增
  "std_output_tokens": 100.0          // 新增
}
```

**向后兼容**：所有新增字段都有 `default=0`，旧 JSON 报告反序列化时自动填充为 0，不影响历史数据分析。

---

## 常见批量评测示例

```bash
rep=10
conc=4

# 基础评测
python -m tests.evaluation.cli run --repeat $rep --concurrency $conc

# HDC 对比（指定命名空间）
python -m tests.evaluation.cli run --compare-hdc --repeat $rep --concurrency $conc

# SQL 记忆对比
python -m tests.evaluation.cli run --compare-sql-memory --repeat $rep --concurrency $conc
```
