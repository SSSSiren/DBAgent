# 研究日志

## 发现范围

本特性是对现有评测框架的增强，属于扩展类型，发现重点聚焦于代码库集成点和现有模式。

## 关键发现

### 1. 静默降级风险点

`runner.py` 中的 `_inject_hdc_context()` (line 168-191) 有三层静默降级：

1. `settings.hdc_enabled` 为 False → 直接 return False，无日志
2. OpenViking 连接失败 → Exception 被捕获，return False
3. `HDCRetriever.retrieve()` 返回空 → return False

在 `--compare-hdc` 模式下，用户如果不设 `HDC_ENABLED=true`，第二轮（有 HDC）会完全等同于第一轮（无 HDC），但报告不会提示任何异常。

**解决**：在 `_run_compare_hdc()` 入口处显式检查。

### 2. repeat 非对称性

`_run_single_case()` (line 376-582) 中：

- Agent 执行：repeat N 次 ✓
- 效率指标：N 次取平均 ✓
- SQL 正确性：仅最后一次 ✗
- 回答质量：仅最后一次 ✗
- HDC 验证：仅最后一次 ✗

这使得 `--repeat 4` 只能给出效率的稳定性，正确率仍然是单次点估计。

**解决**：在 judge 阶段加入循环，对所有 run 执行 judge 后取平均。

### 3. HDC 审计数据已存在但未聚合

前一批增强（`hdc-evaluation-enhancement`）已在 `CaseResult.hdc_verification` 和 `RunDetail.first_table_used` 中收集了幻觉检测和首表追踪的原始数据，但 `_render_hdc_audit()` 只做了逐用例展示和简单计数，未在报告顶层汇总"幻觉率"和"首表命中率"。

**解决**：在 `_render_hdc_audit()` 末尾增加聚合统计。

### 4. 技术决策

- **不做 judge 并发**：Judge 调用已有 LLM API 内部的并发限流，额外加 Semaphore 会引入不必要的复杂性。
- **保守幻觉策略**：repeat>1 时任一 run 出现幻觉即标记为幻觉，宁可高估不可低估。
- **首表命中严格策略**：repeat>1 时所有 run 都命中才算命中，确保统计保守。

### 5. 风险

- **Judge 调用量增加**：`--repeat 4` 时 judge 调用量变为原来的 4×，对 LLM API 有额外压力。
- **向后兼容**：`repeat=1` 时 judge 逻辑路径不变，`Optional` 新字段默认为 None。

## 来源

- `tests/evaluation/runner.py` line 168-191 (silent degradation)
- `tests/evaluation/runner.py` line 376-582 (repeat asymmetry)
- `tests/evaluation/reporter.py` line 765-816 (HDC audit renders)
- `tests/evaluation/models.py` line 99-112 (RunDetail fields)
- 用户测试需求：schema 24223568 有/无 HDC 对比，schema 65938636 覆盖梯度，repeat 4 次
