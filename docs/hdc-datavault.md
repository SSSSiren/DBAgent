# HDC 数据底座模块

## 概述

HDC（Hierarchical Data Context，层次化数据上下文）是 DBAgent 的数据库语义知识底座。通过离线 LLM 管线将 OneDBA 数据库 schema 转化为四层业务语义描述（列→表→关系→库），存储于 OpenViking 资源目录，在线检索时注入 Agent 上下文，减少 Agent 面对陌生数据库时的 `find_table → describe_table` 盲搜往返。

**核心能力**：

- **离线生成**：OneDBA 采集 schema → LLM 自底向上生成四层描述
- **在线检索**：OpenViking `find` API 向量检索 + tags 精确过滤，注入 Agent 上下文
- **增量更新**：列签名 hash 对比，仅重算 schema 变更的表
- **范围限制**：支持全库和指定表两种生成/更新模式

## 架构

```
app/datavault/                   # HDC 数据底座模块（3,558 行）
├── __init__.py          (53)    # 模块入口，工厂函数
├── models.py            (141)   # 数据模型（ColumnRaw/TableDescription/HDCContext 等）
├── collector.py         (210)   # Schema 采集器，从 OneDBA 采集元数据
├── generator.py         (1,486) # HDC 生成管线编排（四层 LLM 生成）
├── uploader.py          (441)   # OpenViking 上传器，写文件 + set_tags + 等 embedding
├── retriever.py         (520)   # HDC 检索封装 + 上下文格式化
└── updater.py           (707)   # 增量更新检测与执行
```

### 各模块职责

| 模块 | 职责 | 关键方法 |
|------|------|---------|
| **SchemaCollector** | 从 OneDBA 采集原始 schema（`SHOW TABLE STATUS` → `DESCRIBE` → `SELECT * LIMIT 3`） | `collect_database(schema_id, tables=None)` |
| **HDCGenerator** | 编排四层 LLM 生成管线：列摘要 → 表描述 → 表关系 → 数据库摘要 | `generate(schema_id, db_name, tables=None, progress_callback=None)` |
| **HDCUploader** | 写 HDC 内容到 OpenViking 目录，设置结构化 tags，等待 embedding 就绪 | `upload_tables()`, `upload_cascade()`, `wait_for_embedding()` |
| **HDCRetriever** | 两阶段检索（tags+向量 → 列详情），格式化 `[数据底座]` 上下文段落 | `retrieve(user_input, schema_id, db_name)`, `format_context()` |
| **HDCUpdater** | 列签名 hash 对比，识别新增/变更/删除表，增量重算 | `check_and_update(schema_id, db_name, tables=None)` |

## 数据流

### 生成管线

```
OneDBA → SchemaCollector → TableRaw[]
  → HDCGenerator.generate()
    → 列摘要 (LLM, 6列/组并行)
    → 表描述 (LLM, 逐表流式管线)
    → HDCUploader.upload_tables()  → OpenViking
    → 表关系 (2阶段: find粗筛 → LLM细筛)
    → 数据库摘要 (LLM)
    → HDCUploader.upload_cascade() → OpenViking
```

### 在线检索

```
用户输入 → HDCRetriever.retrieve()
  → Stage 1: find(tags=["hdc_level=table"], level=[0,1]) → 匹配表
  → Stage 2: find(level=[2]) → 相关列（每表 ≤6 列）
  → 读取 _INDEX.md 获取精确元数据
  → 返回 HDCContext → build_context() 注入 Agent
```

## 测试体系

HDC 模块拥有两层测试：**单元/集成测试**（`tests/datavault/`）和 **评估框架**（`tests/evaluation/`）。

### 1. 单元测试与集成测试（tests/datavault/）

纯 Python 测试，使用 mock 对象，无需外部服务即可运行。

#### 1.1 运行全部测试

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent

# 运行全部 HDC 相关测试（32 个用例，无外部依赖）
pytest tests/datavault/ -v
```

#### 1.2 测试文件总览

| 文件 | 类型 | 用例数 | 覆盖范围 | 外部依赖 |
|------|------|--------|---------|---------|
| `test_collector.py` | 单元测试 | 11 | SchemaCollector：基本采集、空库、容错、表过滤、不存在表名 | 无 |
| `test_retriever_updater.py` | 单元测试 | 16 | HDCRetriever（检索/降级/格式化）、HDCUpdater（hash/变更检测）、数据模型 | 无 |
| `test_hdc_integration.py` | 集成测试 | 5 | `build_context()` 中 `[数据底座]` 段落注入/跳过/位置/并列 | 无 |
| `demo_hdc.py` | 模拟演示 | — | 纯模拟 e-commerce 场景，展示 HDC 减少 tool-call 轮次的原理 | 无 |

#### 1.3 test_collector.py（11 个用例）

测试 `SchemaCollector` 的 OneDBA schema 采集逻辑，使用 `MockOneDBAClient` 模拟数据库响应。

| 用例 | 验证点 |
|------|--------|
| `test_collect_basic` | 单表 2 列的完整采集（name, comment, engine, row_count, columns, sample rows） |
| `test_collect_empty_database` | `SHOW TABLE STATUS` 返回空 → 0 张表 |
| `test_collect_no_column_datas` | 响应缺失 `columnDatas` 键 → 优雅处理 |
| `test_single_table_failure_does_not_abort` | 单表 DESCRIBE 失败 → 该表 columns 为空，其余表正常 |
| `test_duplicate_table_names_skipped` | `SHOW TABLE STATUS` 出现重名表 → 仅保留首次出现 |
| `test_unparseable_row_count_defaults_zero` | 非数字 `row_count`（如 "N/A"）→ 默认 0 |
| `test_describe_empty_fields` | DESCRIBE 行缺失 Field 键 → 跳过 |
| `test_tables_filter_only_collects_specified` | `tables=["users"]` → 仅采集 "users"，忽略其余表 |
| `test_tables_none_collects_all` | `tables=None` → 采集全部表 |
| `test_nonexistent_table_name_warns_and_skips` | 过滤列表中的不存在表名 → 日志警告，继续执行 |
| `test_all_nonexistent_tables_returns_empty` | 全部指定表不存在 → 返回空 `DatabaseRaw` |

#### 1.4 test_retriever_updater.py（16 个用例）

测试 `HDCRetriever`、`HDCUpdater` 和 Pydantic 数据模型，使用 `MockOVClient` 模拟 OpenViking。

**HDCRetriever（6 个用例）**：

| 用例 | 验证点 |
|------|--------|
| `test_retrieve_with_matches` | 完整检索管线：`find()` 返回表+列 → `TableMatch` 对象正确填充 |
| `test_retrieve_empty_returns_none` | 无匹配表 → 返回 `None`（优雅降级） |
| `test_format_context_with_data` | `format_context()` 生成有效 `[数据底座]` markdown 段落 |
| `test_format_context_none` | `format_context(None)` → 返回空字符串 |
| `test_format_context_empty_tables` | 空 `matched_tables` → 仍输出 header 和数据库摘要 |
| `test_openviking_unavailable_returns_none` | `find()` 返回空 → 返回 `None` |

**HDCUpdater（6 个用例）**：

| 用例 | 验证点 |
|------|--------|
| `test_same_columns_same_hash` | 相同列结构 → 相同 SHA256 hash |
| `test_reordered_columns_same_hash` | 列顺序不影响 hash（先排序再 hash） |
| `test_different_type_different_hash` | 修改列 data_type → hash 不同 |
| `test_added_column_different_hash` | 新增列 → hash 不同 |
| `test_removed_column_different_hash` | 删除列 → hash 不同 |
| `test_empty_columns_hash` | 空列列表 → 仍生成有效 hash 字符串 |

**数据模型（4 个用例）**：

| 用例 | 验证点 |
|------|--------|
| `test_table_description_defaults` | `table_type="fact"`, `main_entity=""`, `key_attributes=[]` |
| `test_table_description_with_synonyms` | `main_entity` 支持 `/` 分隔同义词 |
| `test_hdc_context_empty` | `database_summary=""`, `matched_tables=[]` |
| `test_table_match_default` | `relevant_columns=[]` |

#### 1.5 test_hdc_integration.py（5 个用例）

测试 `build_context()` 中 HDC 上下文的注入行为。

| 用例 | 验证点 |
|------|--------|
| `test_hdc_context_injected` | `session_state["_hdc_context"]` 被注入到 `build_context()` 输出 |
| `test_hdc_context_empty_skipped` | 空字符串 → 不追加空段落 |
| `test_hdc_context_missing_skipped` | 缺失 key → 静默忽略 |
| `test_hdc_context_alongside_other_sections` | HDC 段落与 memory/preferences 段落共存 |
| `test_hdc_context_position` | HDC 段落出现在 preferences 之后（context 末尾） |

#### 1.6 demo_hdc.py（模拟演示，无需外部服务）

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
python tests/datavault/demo_hdc.py
```

纯模拟 e-commerce 数据库（`dwd_trade`）场景，包含 4 张表（order_info, after_sale_order, payment_info, user_info），使用 `MockRetriever` 模拟关键词匹配，演示 HDC 将 Agent 的 tool-call 轮次从 3-4 轮减少到 1 轮的效果。3 个测试问题覆盖退款、GMV、用户查询。

---

### 2. 评估框架（tests/evaluation/）

结构化的 Agent 质量评估框架，通过 50 条测试用例 + 多维度评分，量化 HDC 对 Agent 表现的提升效果。

#### 2.1 框架架构

```
tests/evaluation/                   # 评估框架（~3,600 行）
├── cli.py                   (375)  # CLI 入口（argparse），run / list 子命令；hdc_enabled 前置校验
├── runner.py                (870)  # 核心执行引擎，编排 Agent 运行 + 各类 judge；repeat judge 循环
├── models.py                (168)  # 全部 Pydantic v2 数据模型
├── loader.py                (247)  # Markdown 测试用例解析器
├── scorer.py                (129)  # 5 维度评分聚合 + 加权总分
├── reporter.py              (920)  # JSON + Markdown 报告生成（含 baseline / HDC 对比 + 审计聚合）
├── debug_hdc_prompt.py      (207)  # 独立 HDC prompt 诊断工具
├── judges/
│   ├── sql_judge.py         (397)  # 3 阶 SQL 正确性判定（结构→结果→LLM）
│   ├── quality_judge.py     (102)  # LLM 回答质量评估（4 子维度）
│   └── efficiency_judge.py  (114)  # 算法效率评分（无 LLM）
├── hdc_eval/                       # 历史评估报告存档
├── output/                         # 当前评估输出目录
└── tool_calls_enhance/             # 工具调用能力对比报告
```

**核心数据流**：

```
CLI (cli.py)
  → 前置校验: hdc_enabled 开关（--compare-hdc 模式下强制检查）
  → Loader (loader.py)    解析 Markdown → list[TestCase]
  → Runner (runner.py)    逐用例执行（repeat>1 时每个 run 都 judge 后取平均）：
      1. _execute_agent_once()  → Agent 原始输出
      2. judge_sql_correctness() → 3 阶 SQL 判定（结构→执行→LLM）× N 次
      3. judge_answer_quality()  → LLM 回答质量评分 × N 次
      4. compute_efficiency()    → 算法效率评分
      5. _verify_hdc_injection() → HDC 注入审计 + 多次运行聚合
      6. score_case()           → 5 维度 + 总评分
  → Scorer (scorer.py)   维度评分 + 加权总分
  → Reporter (reporter.py) → JSON + Markdown 报告（含评测总耗时）
```

#### 2.2 使用方式

**基本运行**：

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent

# 列出所有测试用例
python tests/evaluation/cli.py list
python tests/evaluation/cli.py list --difficulty Hard
python tests/evaluation/cli.py list --category aggregation

# 运行评估（30 条 TC 用例）
python tests/evaluation/cli.py run
python tests/evaluation/cli.py run --ids TC-001,TC-005,TC-010
python tests/evaluation/cli.py run --difficulty Medium --timeout 180

# 运行 CS 用例集
python tests/evaluation/cli.py run --test-file tests/docs/test_cases_onedba_cs_evaluation.md
```

**HDC 对比实验**：

```bash
# 前置：必须设置环境变量（--compare-hdc 启动时会主动校验）
export HDC_ENABLED=true

# HDC 对比模式（两轮：无 HDC baseline → 有 HDC experiment，启动时打印预估耗时）
python -m tests.evaluation.cli run --compare-hdc -v
python -m tests.evaluation.cli run --compare-hdc --verbose-hdc --verbose
python -m tests.evaluation.cli run --compare-hdc --ids TC-001,TC-005 --repeat 3

# 带 token 成本区分的对比（传入 HDC 离线生成的 token 数，报告中区分运行时/离线成本）
python -m tests.evaluation.cli run --compare-hdc --repeat 4 --verbose-hdc --hdc-gen-tokens 1200000

# 使用命名空间测试特定知识库变体（需先用 demo_hdc_generate.py --namespace 生成）
python -m tests.evaluation.cli run --with-hdc --hdc-namespace incomplete --ids TC-001,TC-002
python -m tests.evaluation.cli run --with-hdc --hdc-namespace complete --ids TC-001,TC-002
python -m tests.evaluation.cli run --with-hdc --hdc-namespace overcomplete --ids TC-001,TC-002

# 命名空间 + 对比模式（无 HDC baseline vs 指定命名空间的 HDC）
python -m tests.evaluation.cli run --compare-hdc --hdc-namespace incomplete --ids TC-001

# 与历史 baseline 对比
python -m tests.evaluation.cli run --baseline tests/evaluation/hdc_eval/hdc-65938636.json
```

**Prompt 调试**：

```bash
# 诊断 HDC context 注入到 prompt 的实际内容
python tests/evaluation/debug_hdc_prompt.py
python tests/evaluation/debug_hdc_prompt.py --ids TC-001,TC-002
python tests/evaluation/debug_hdc_prompt.py --difficulty Hard
```

#### 2.3 CLI 参数详解

**`run` 子命令参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--ids` | list[str] | None | 按用例 ID 过滤（如 TC-001,TC-005） |
| `--difficulty` | choice | None | 按难度过滤：Easy / Medium / Hard |
| `--category` | str | None | 按类别过滤（如 aggregation, JOIN） |
| `--test-file` | str | tests/docs/test_cases_onedba_evaluation.md | 测试用例 Markdown 文件路径 |
| `--schema-id` | int | 65938636 | OneDBA schema ID |
| `--db-name` | str | dw_onedba | 数据库名称 |
| `--timeout` | float | 120.0 | 单用例超时秒数 |
| `--concurrency` | int | 1 | 并发执行用例数 |
| `--repeat` | int | 1 | 每用例重复次数（正确率+效率均取平均；排除外部服务异常值） |
| `--no-llm-judge` | flag | False | 跳过 Tier 3 LLM SQL 判定 |
| `--no-quality-judge` | flag | False | 跳过回答质量评判 |
| `--keep-langfuse` | flag | False | 保留 Langfuse trace |
| `--llm-model` | str | None | 覆盖 LLM 模型 |
| `--baseline` | str | None | 与历史 JSON baseline 对比 |
| `--compare-hdc` | flag | False | HDC 两轮对比模式（无 HDC → 有 HDC），启动时自动校验 `HDC_ENABLED` 并打印预估耗时 |
| `--hdc-gen-tokens` | int | None | HDC 离线生成消耗的 token 数（传入后在报告中区分运行时/离线成本，不传则不展示） |
| `--hdc-tables` | str | None | HDC 检索表白名单（逗号分隔，仅保留匹配的表上下文，用于测试知识库缺失场景） |
| `--hdc-namespace` | str | None | HDC 命名空间，用于检索特定变体的知识库（如 incomplete/complete/overcomplete） |
| `--verbose / -v` | flag | False | 打印 Agent 中间步骤 |
| `--verbose-hdc` | flag | False | 打印 HDC 注入状态（每用例每次运行；repeat>1 时输出 `#run_index` 区分） |
| `--output-dir` | str | tests/evaluation/output | 报告输出目录 |

**`list` 子命令参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--difficulty` | choice | None | 按难度过滤 |
| `--category` | str | None | 按类别过滤 |
| `--test-file` | str | None | 指定测试用例文件 |

#### 2.4 测试用例集

用例定义在 Markdown 文件中，按 `### TC-XXX` / `### CS-XXX` 格式组织：

| 用例集 | 文件 | 数量 | 内容 |
|--------|------|------|------|
| TC（基础） | `tests/docs/test_cases_onedba_evaluation.md` | 30 条 | 覆盖：单表过滤、聚合、JOIN、窗口函数、子查询、多表关联 |
| CS（增强） | `tests/docs/test_cases_onedba_cs_evaluation.md` | 20 条 | 覆盖：更复杂场景、边界条件 |

每条用例包含：问题描述、参考 SQL、预期行数、判定标准。`loader.py` 中的硬编码映射表记录每条用例的难度（Easy/Medium/Hard）、类别和涉及的表名。

#### 2.5 评分体系

**5 维度评分**（`scorer.py`），`--repeat N` 时每个维度基于 N 次 judge 均值计算：

| 维度 | 权重 | 来源 | 说明 |
|------|------|------|------|
| `sql_syntax` | 10% | SQL Judge Tier 1 | SQL 语法是否有效 |
| `table_column` | 10% | SQL Judge 表/列重叠 | 使用的表和列是否与参考一致 |
| `filter_condition` | 10% | SQL Judge 扣分项 | 过滤条件是否等价 |
| `result_data` | 60% | SQL Judge 综合分（N 次均值） | 结果数据是否与参考一致（核心维度） |
| `sql_standard` | 10% | 算法检查 | 编码规范（禁止 `SELECT *`、需 `ORDER BY`/`LIMIT`） |

**硬约束**：`result_data < 0.5` 时总分上限 0.70。通过阈值：总分 ≥ 0.80。

**异常值排除**：`--repeat N` 时若某次 judge 因外部服务不可用（OneDBA 超时、LLM API 错误）而失败，该次得分标记为异常值（`RunDetail.sql_score = None`），不纳入均值计算；因 Agent 本身未生成 SQL 导致的 0 分则正常纳入。

**3 阶 SQL 判定**（`judges/sql_judge.py`）：

| 阶 | 方法 | 触发条件 |
|----|------|---------|
| Tier 1 - 结构匹配 | SQL 字符串归一化对比 | 默认 |
| Tier 2 - 结果对比 | 在真实数据库执行两条 SQL，比对行数+列名+数据值 | Tier 1 不匹配 |
| Tier 3 - LLM 语义判定 | `deepseek-chat` 评估语义等价性 | Tier 2 失败或 SQL 执行报错 |

**回答质量评估**（`judges/quality_judge.py`）：LLM 评估 4 个子维度——completeness（完整性）、accuracy（准确性）、clarity（清晰度）、sql_transparency（SQL 透明性），总分为 4 项均值。

**效率评分**（`judges/efficiency_judge.py`）：纯算法计算，阈值可配置（`max_tool_calls=25`, `max_turns=20`, `max_tokens=500k`, `max_latency_ms=240s`），各项线性映射到 0.0-1.0，取均值。

#### 2.6 报告输出

每次运行在 `tests/evaluation/output/` 下生成：

| 文件 | 说明 |
|------|------|
| `evaluation_report_{timestamp}.json` | 完整结构化报告（含所有 CaseResult 和 `total_duration_ms`） |
| `evaluation_report_{timestamp}.md` | 可读 Markdown 报告（总耗时/概览/维度/难度/逐用例/失败分析） |
| `hdc_comparison_{timestamp}.json` | HDC 对比专用报告（含 baseline vs experiment 全量 diff、首表命中率、幻觉率） |
| `hdc_comparison_{timestamp}.md` | HDC 对比 Markdown（总耗时对比/全局对比/维度对比/难度对比/逐用例对比/工具效率/HDC 审计/token 成本说明） |

**HDC 对比报告特有内容**：
- 全局指标 delta（pass rate, avg score, latency, tool calls, turns, tokens, **评测总耗时**, **HDC 离线生成 token**（可选））
- 5 维度分维度对比（带趋势箭头）
- 按难度分组对比
- 逐用例首表正确率追踪（agent 首次使用的表是否与参考 SQL 一致）
- 工具调用效率分析（find_table / describe_table / query_database 使用频次对比）
- HDC 注入审计（context 是否包含正确表、agent 是否使用正确表、幻觉检测、**首表命中率**、**幻觉率**）
- Token 成本说明（HDC 离线生成 token 为一次性成本，随查询次数增加摊薄）

#### 2.7 HDC 注入验证

`runner.py` 中的 `_verify_hdc_injection()` 对每个用例的 HDC context 进行审计；`--repeat N` 时对所有运行分别审计后按策略聚合：

1. 从参考 SQL 提取正确表名
2. 检查 HDC context 是否包含该表（`correct_table_in_context`）
3. 检查 Agent 使用的第一张表是否正确（`agent_used_correct_table`）
4. 检测 Agent 是否使用了不在 HDC context 中的表名（幻觉检测，`is_hallucination`）

多次运行聚合策略：`injected` 取 OR（任一注入成功即算）、`correct_table_in_context` 取 OR、`agent_used_correct_table` 取多数、`is_hallucination` 取 OR（保守策略）。

审计结果写入 `CaseResult.hdc_verification`（`HdcVerificationData` 模型），并在 HDC 对比报告中以首表命中率和幻觉率汇总展示。

---

### 3. 集成验证脚本（tests/datavault/，需外部服务）

以下脚本需要 OneDBA + OpenViking + LLM 全部可用。

#### 3.1 生成 HDC 知识库

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent

# --- 基本用法 ---

# 全库生成（默认）
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs

# 详细日志
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs -v

# --- 部分表模式（范围限制） ---

# 仅生成指定表
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs --tables user_info,order_main

# 部分表 + 详细日志
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs --tables user_info,order_main -v

# --- 命名空间模式（知识库变体隔离） ---

# 为同一数据库生成多套独立的知识库，用于评测不同场景（残缺/完整/过剩）

# 完整知识库：仅包含用例涉及的表
python tests/datavault/demo_hdc_generate.py 65938636 dw_onedba \
    --tables order_record,user_task,account --namespace complete

# 残缺知识库：缺少部分用例需要的表
python tests/datavault/demo_hdc_generate.py 65938636 dw_onedba \
    --tables order_record,user_task --namespace incomplete

# 过剩知识库：全库所有表（包含大量用例不需要的表，测试噪音影响）
python tests/datavault/demo_hdc_generate.py 65938636 dw_onedba \
    --namespace overcomplete
```

**参数说明**：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `schema_id` | 是 | 25800743 | OneDBA schema ID |
| `database_name` | 是 | dw_onedba | 数据库名称 |
| `-v, --verbose` | 否 | false | 输出详细的中间日志（每表/每关系的 LLM 耗时） |
| `--tables` | 否 | None | 逗号分隔的表名列表，不指定则全库生成 |
| `--namespace` | 否 | None | HDC 命名空间，用于隔离同一数据库的不同知识库变体（如 incomplete/complete/overcomplete） |

**输出**：脚本执行**三个验证阶段**：

1. **Phase 1 - 生成**：调用 `HDCGenerator.generate()` 完成 4 层 LLM 生成
2. **Phase 2 - 持久化验证**：通过 OpenViking HTTP API 检查目录结构（`_tables/`、`_INDEX.md`、列 `.md` 文件、`_relationships/` 等）
3. **Phase 3 - 检索验证**：创建 `HDCRetriever`，用 "告警"、"权限"、"表结构" 三个关键词验证检索命中

全部通过则 HDC 知识库就绪。

#### 3.2 增量更新

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent

# --- 基本用法 ---

# 检测变更（无变更时不执行任何 LLM 调用）
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs

# 详细日志
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs -v

# --- 过滤模式（仅检测指定表） ---

# 仅检测指定表的变更
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs --tables user_info,order_main

# --- 控制模式 ---

# 仅检测变更，不执行更新
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs --dry-run

# 强制执行更新（即使无变更也重跑关系和摘要）
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs --force-update

# 仅重建关系+数据库摘要（不重跑列摘要/表描述）
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs --rebuild
```

**参数说明**：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `schema_id` | 是 | — | OneDBA schema ID |
| `database_name` | 是 | — | 数据库名称 |
| `-v, --verbose` | 否 | false | 输出详细日志 |
| `--tables` | 否 | None | 仅检测指定表的变更 |
| `--dry-run` | 否 | false | 仅检测变更，不执行更新 |
| `--force-update` | 否 | false | 强制执行增量更新 |
| `--rebuild` | 否 | false | 强制重建关系+数据库摘要 |

**增量更新流程**：

```
1. 确保 HDC 知识库已存在（否则提示先运行 demo_hdc_generate.py）
2. 先跑一次无变更检测 → 验证 {"changed": false}（零 LLM 调用）
3. 列签名 hash 对比：读取 OpenViking 中存储的 columns_hash tags
   → 识别新增表 / 变更表（hash 不同）/ 删除表 / 无 hash 表
4. 有变更 → 重算受影响表的列摘要+表描述 → 级联更新关系和摘要
5. --rebuild 模式：跳过列/表重算，仅重建关系+数据库摘要
```

#### 3.3 对比实验

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent

# HDC 对比实验（需先生成 HDC 知识库）
python tests/datavault/demo_hdc_compare.py 24223568 dw_onedba_cs

# 完整端到端（自动生成 + 对比 + 报告）
python tests/datavault/demo_hdc_e2e.py 24223568 dw_onedba_cs
```

`demo_hdc_compare.py` 对 3 个预设问题各跑两轮（无 HDC baseline → 有 HDC experiment），对比 tool-call 轮次、耗时和 token 消耗。`demo_hdc_e2e.py` 将生成+对比合并为一条命令。

#### 3.4 OpenViking 连通性调试

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
python tests/datavault/hdc_debug.py
```

无参数脚本，创建 `viking://resources/hdc/debug_test/` 测试目录，写入 test.md 并设置 tag，验证 OpenViking 基本 CRUD 功能正常。

### 4. 典型工作流

```
# 第 1 步：连通性检查（无外部依赖）
pytest tests/datavault/ -v                        # 32 个单元+集成测试全部通过
python tests/datavault/demo_hdc.py                 # 理解 HDC 概念（纯模拟）

# 第 2 步：基础设施检查（需外部服务）
python tests/datavault/hdc_debug.py                # 验证 OpenViking 连通性

# 第 3 步：生成 HDC 知识库
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs   # 验证增量更新

# 第 4 步：对比实验
python tests/datavault/demo_hdc_e2e.py 24223568 dw_onedba_cs     # 全自动
# 或分步执行
python tests/datavault/demo_hdc_compare.py 24223568 dw_onedba_cs

# 第 5 步：正式评估（50 条用例，多维度量化，repeat 4 次取平均）
export HDC_ENABLED=true
python -m tests.evaluation.cli run --compare-hdc --repeat 4 --verbose-hdc --hdc-gen-tokens 1200000

# 第 6 步（可选）：多知识库变体评测（残缺/完整/过剩）
# 先生成三套独立知识库
python tests/datavault/demo_hdc_generate.py 65938636 dw_onedba \
    --tables order_record,user_task,account --namespace complete
python tests/datavault/demo_hdc_generate.py 65938636 dw_onedba \
    --tables order_record,user_task --namespace incomplete
python tests/datavault/demo_hdc_generate.py 65938636 dw_onedba \
    --namespace overcomplete
# 分别评测
python -m tests.evaluation.cli run --with-hdc --hdc-namespace incomplete --ids TC-001,TC-002
python -m tests.evaluation.cli run --with-hdc --hdc-namespace complete --ids TC-001,TC-002
python -m tests.evaluation.cli run --with-hdc --hdc-namespace overcomplete --ids TC-001,TC-002
```

## 配置项

HDC 相关配置在 `app/config.py` 的 `Settings` 中：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `hdc_enabled` | `bool` | `False` | HDC 功能总开关 |
| `hdc_auto_generate` | `bool` | `False` | 首次使用数据库时是否自动触发生成 |
| `hdc_semantic_timeout` | `float` | `300.0` | write 时的 SemanticProcessor 超时秒数（已降为内联 60s） |

通过环境变量设置：

```bash
export HDC_ENABLED=true
```

## OpenViking 存储结构

```
viking://resources/hdc/{schemaId}/{db}/[/{namespace}/]
├── _INDEX.md                              # 数据库摘要
├── _tables/
│   ├── _INDEX.md                          # 表汇总
│   ├── {table_name}/
│   │   ├── _INDEX.md                      # 表描述（L2）
│   │   ├── {column}.md                    # 列描述（L2）
│   │   ├── .abstract.md                   # L0 摘要（VLM 自动生成）
│   │   └── .overview.md                   # L1 概览（VLM 自动生成）
│   └── ...
└── _relationships/
    ├── {src}__{tgt}.md                    # 表关系
    └── ...
```

**命名空间（namespace）**：可选路径后缀，用于同一 `(schemaId, db)` 下隔离不同的 HDC 知识库变体。不传时路径为 `{schemaId}/{db}/`；传入时路径为 `{schemaId}/{db}/{namespace}/`。典型用途：生成 incomplete / complete / overcomplete 三套知识库，分别评测 Agent 在不同知识覆盖度下的表现。

**Tags**（表目录级别）：`hdc_level=table`, `main_entity={value}`, `table_type={value}`, `pk={value}`, `columns_hash={sha256}`

## 降级策略

- OpenViking 不可用 → 静默降级，日志警告，Agent 回退到 `find_table` + `describe_table`
- HDC 检索无匹配 → 不注入空段落，Agent 正常探索
- LLM 生成失败（单表）→ 记录错误，继续处理其余表
- embedding 未就绪 → retriever 自带 fs/ls 文件系统 fallback

## 注意事项

1. **Embedding 等待**：`upload_table()` 在 `write(wait=True, timeout=60s)` 后还通过 `wait_for_embedding()` 轮询确认 embedding 就绪。如果检索阶段仍返回空，OpenViking 后台 embedding 可能还在处理中，稍等后重试。
2. **VLM 超时**：`write(wait=True, timeout=60s)` 只等 embedding（~2-5s），VLM 生成的 L0/L1 摘要在服务端后台异步完成。服务端日志中的 VLM 超时警告不影响检索功能。
3. **部分表模式**：使用 `--tables` 生成的 HDC 知识库仍然包含关系和摘要（基于已生成表的子集）。后续增量更新会自动将未生成的表识别为"待新增"。`demo_hdc_update.py` 的 Phase 3 变更预览在 `--tables` 模式下只对比指定表的 hash，OpenViking 中其余表不会误判为删除。
4. **增量更新兼容性**：`check_and_update()` 不假设全库覆盖——未在 OpenViking 中出现的表均被视为"待新增"。
5. **评估环境要求**：`cli.py` 强制要求 conda 环境为 `/Users/admin/miniconda3/envs/DBR/bin/python`，否则退出。
