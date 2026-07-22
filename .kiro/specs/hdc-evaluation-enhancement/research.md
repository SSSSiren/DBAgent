# 研究日志

## 发现类型

**轻量发现**（扩展型功能）

## 发现范围

- 评测框架现有代码库分析（`tests/evaluation/`）
- 现有数据模型和接口合约审查
- 集成点和向后兼容约束识别

## 关键发现

### 1. tool_call_details 已完整收集

`_execute_agent_once()` (runner.py:78-79) 已逐工具名收集调用次数到 `tool_call_details: dict[str, int]`。数据通过 `_AgentRunOutput` → `_build_run_detail()` → `RunDetail.tool_call_details` → `_compute_efficiency_from_stats()` → `EfficiencyMetrics.tool_call_details` 完整流转。报告仅使用了 `tool_call_count`（总次数），未展现逐工具细分。

**影响**：无需修改数据收集代码，只需在报告层渲染 `tool_call_details`。

### 2. 现有对比报告模式可直接复用

`_render_hdc_comparison_md()` (reporter.py:432-579) 已实现完整的对比报告渲染管道：全局对比表 → 维度对比表 → 按难度对比 → 逐用例对比 → 结论。每类表格使用一致的 `_add_metric_row()` 辅助函数 (line 582-621) 格式化基线/当前/变化/趋势四列。

**影响**：新增章节遵循相同的表格模式和函数签名，追加在现有章节之后。

### 3. CaseResult 已有 Optional[dict] 扩展模式

`EvaluationReport.baseline_comparison: Optional[dict[str, Any]]` (models.py:146) 是向现有模型追加可选扩展数据的确切模式。`CaseResult` 本身有 `Optional[EfficiencyMetrics]`、`Optional[SQLJudgeResult]`、`Optional[QualityJudgeResult]` 等多个可选字段。

**影响**：`hdc_verification: Optional[HdcVerificationData]` 遵循相同的模式，Pydantic `model_dump` 自动序列化，None 值不出现在 JSON 中。

### 4. CS-* 评测实际使用的工具名

从 `evaluation_report_20260722_104352.json` 提取：`query_database`（27 次）、`find_table`（20 次）、`select_database`（17 次）、`describe_table`（12 次）、`execute_sql`（3 次）。

**影响**：逐工具效率对比表聚焦 `find_table`、`describe_table`、`query_database` 三种核心工具。

### 5. 参考表名提取可行

`sql_judge.py` 已实现从 SQL 文本提取表名的正则匹配逻辑（`TABLE_NAME_RE`）。`TestCase.reference_sql` 总是包含明确的 FROM 子句。HDC 上下文文本中的表名以 `### {table_name}` 格式出现（`format_context()` 输出）。

**影响**：`_verify_hdc_injection()` 可以通过简单的子字符串搜索判断参考表名是否在 HDC 文本中。

## 设计决策

### 决策 1：逐工具对比表包含 3 种核心工具

**选择**：仅渲染 find_table、describe_table、query_database 三种工具的对比，而非列出 tool_call_details 中所有键。

**理由**：这三种工具是 HDC 直接影响的工具（find_table 探索 → describe_table 看结构 → query_database 查询）。select_database 受 schema_id 预设影响，execute_sql 使用率极低（3/20 用例），渲染所有工具会降低表格可读性。

### 决策 2：使用 Pydantic 模型而非裸 dict

**选择**：`HdcVerificationData` 使用 Pydantic BaseModel 而非 `dict[str, Any]`。

**理由**：与现有代码库的 Pydantic 模式一致（TestCase、CaseResult、RunDetail 等全部使用 BaseModel），提供字段级别的类型安全和序列化保证。

### 决策 3：渲染函数签名遵循现有模式

**选择**：`_render_per_tool_breakdown(lines, no_hdc, with_hdc)` 和 `_render_hdc_audit(lines, with_hdc)` 接收 `list[str]` 并 append 内容。

**理由**：与 `_render_hdc_comparison_md()` 内部的所有辅助渲染调用一致。

## 架构决策

### 无新文件

**仅修改 4 个现有文件**，不新增文件。所有新增代码通过函数和类聚合到现有模块中。

**理由**：扩展型功能的每个组件的代码量小（~15-70 行），拆分为新文件会造成不必要的间接引用。评测框架尚未出现文件膨胀问题。

### 构建 vs 采用

**无需外部依赖**。所有新增逻辑使用 Python 标准库（re、str 操作）和已有依赖（Pydantic）。

## 风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| SQL 表名提取不完整（复杂 FROM 子句如 JOIN、子查询） | agent_table_used 为空 | 默认值 ""，不阻塞；后续可改进解析器 |
| HDC 上下文过长导致全文搜索性能下降 | 单次验证耗时增加 | 当前 ~1600 字符，子字符串搜索 < 0.1ms |
| --compare-hdc 报告章节过多导致可读性下降 | 用户阅读负担 | 新增章节追加在最后，不插入现有章节之间 |
