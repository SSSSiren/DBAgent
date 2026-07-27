# Requirements Document

## Introduction

本特性对 `tests/evaluation/` 评估框架进行四项改进，提升 HDC 对比评测的可靠性、可诊断性和可观测性。改进聚焦于：启动时前置校验防止静默降级、repeat 模式下的正确率统计准确性、幻觉率和首表命中率的顶层聚合、以及运行时/离线 token 的区分展示。

## Boundary Context (Optional)

- **In scope**: CLI 启动校验、runner 中 repeat 模式下的 judge 逻辑、reporter 中的聚合指标输出、models 中的字段扩展
- **Out of scope**: generator.py / uploader.py / retriever.py 等 datavault 模块本身的修改、scorer 评分权重的调整、judge 判定逻辑的修改、新 judge 类型的引入
- **Adjacent expectations**: HDC 离线生成 token 数由用户通过 CLI 参数传入（框架不自动统计生成阶段的 token）；`HDC_ENABLED` 环境变量仍需用户手动设置，框架仅做校验不自动设置

## Requirements

### Requirement 1: `--compare-hdc` 模式启动时强制校验 HDC 开关

**Objective:** 作为评测工程师，我希望 `--compare-hdc` 模式在启动时主动检查 `hdc_enabled` 配置，如果未启用则立即报错退出，避免静默降级导致浪费数小时的无效对比评测。

#### Acceptance Criteria

1. When `--compare-hdc` 标志被传入且 `settings.hdc_enabled` 为 `False`，评测框架 shall 在开始执行前打印明确错误信息并退出（exit code 非零）。
2. The 错误信息 shall 包含具体的修复指引（如 `export HDC_ENABLED=true`）。
3. When `--compare-hdc` 标志被传入且 `settings.hdc_enabled` 为 `True`，评测框架 shall 正常进入两轮对比流程，行为不变。
4. The `--compare-hdc` 校验 shall 不影响 `--with-hdc` 单轮模式的行为——`--with-hdc` 模式下仍保持静默降级逻辑（由 `_inject_hdc_context()` 内部处理），不在 CLI 层校验。

### Requirement 2: `--repeat N` 模式下正确率对所有运行取平均

**Objective:** 作为评测工程师，我希望 `--repeat 4` 时每条用例的正确率反映 4 次运行的统计均值，而非仅取最后一次运行的结果，从而获得更可靠的正确率估算。

#### Acceptance Criteria

1. When `repeat > 1`，评测框架 shall 对每条用例的每一次 Agent 运行都执行 SQL 正确性评判（Tier 1/2/3），并将各次得分的算术平均值写入 `sql_judge.score`。
2. When `repeat > 1`，评测框架 shall 对每条用例的每一次 Agent 运行都执行回答质量评判（LLM judge），并将各次得分的算术平均值写入 `quality_judge.score`。
3. When `repeat = 1`，评测框架 shall 保持原有行为不变（仅评判单次运行）。
4. The 每次运行的原始 judge 得分 shall 记录在 `RunDetail` 新增的字段中（`sql_score`、`quality_score`），便于后续审计。

### Requirement 3: 报告中新增幻觉率和首表命中率汇总指标

**Objective:** 作为评测工程师，我希望在 HDC 对比报告的顶层汇总中直接看到幻觉率和首表命中率，快速判断 HDC 是否正确定位了目标表，以及 Agent 是否使用了 HDC 上下文之外的表名。

#### Acceptance Criteria

1. The HDC 对比 Markdown 报告 shall 在"HDC 正确性审计"章节的聚合统计中包含"首表命中率"指标——统计所有运行中 Agent 第一个查询工具使用的表名与参考表名一致的比例。
2. The HDC 对比 Markdown 报告 shall 在"HDC 正确性审计"章节的聚合统计中包含"幻觉率"指标——统计 Agent 实际使用的表名既不在 HDC 上下文中也不在参考 SQL 中的比例。
3. The "首表命中率" and "幻觉率" shall 作为顶层指标出现在 HDC 对比报告的 JSON 文件中（在 `diff` 结构中增加对应字段）。
4. When 多次运行（repeat > 1），首表命中率 shall 基于所有运行汇总计算（取各次运行严格一致才算命中）。

### Requirement 4: 报告中区分运行时 token 和离线生成 token

**Objective:** 作为评测工程师，我希望在报告中清晰看到 Agent 运行时消耗的 token 与 HDC 离线生成消耗的 token 区分展示，从而评估 HDC 的总拥有成本。

#### Acceptance Criteria

1. When 用户通过 `--hdc-gen-tokens` CLI 参数传入 HDC 离线生成 token 数，评测框架 shall 在 HDC 对比报告中额外展示"HDC 生成 Token（一次性）"行，置于"平均 Token（运行时）"行之后。
2. When `--hdc-gen-tokens` 未传入，评测框架 shall 不在报告中显示 HDC 生成 token 行（向后兼容）。
3. The HDC 对比报告结论部分 shall 补充说明：HDC 生成 token 是一次性成本，随着查询次数增加摊薄效果越好。

### Requirement 5: `--compare-hdc` 模式启动时展示预估耗时

**Objective:** 作为评测工程师，我希望在 `--compare-hdc` 启动时看到基于当前参数的预估总耗时，便于决定是否调整并发度或用例范围。

#### Acceptance Criteria

1. When `--compare-hdc` 启动，评测框架 shall 在开始执行前打印预估总耗时（公式：`用例数 × repeat × 平均执行耗时 × 2 轮`）。
2. The 预估信息 shall 包含当前参数摘要（用例数、repeat 次数、并发度、超时时间），方便用户确认。
