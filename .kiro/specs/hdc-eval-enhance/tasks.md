# 实施计划

> **前置条件**：本规格依赖前一批增强 `hdc-evaluation-enhancement`（位于 `.kiro/specs/hdc-evaluation-enhancement/`）的已实现交付物，包括：
> - `CaseResult.hdc_verification: Optional[HdcVerificationData]` 字段
> - `RunDetail.first_table_used`, `RunDetail.called_find_table_before_query` 字段
> - `_verify_hdc_injection()` 函数 (runner.py)
> - `_extract_first_tool_info()` 函数 (runner.py)
> - `_render_hdc_audit()` 函数 (reporter.py)
> - `_render_per_tool_breakdown()` 函数 (reporter.py)
> - `_render_hdc_comparison_md()` 函数 (reporter.py)
> - `_compute_hdc_diff()` 函数 (reporter.py)
> - `_add_metric_row()` 辅助函数 (reporter.py)
> - `--verbose-hdc` CLI 参数
>
> 若上述任何交付物缺失或 schema 不同，本规格的任务将在实现时受阻。

## 任务

- [ ] 1. Foundation：数据模型扩展
  - [ ] 1.1 在 `RunDetail` 模型中新增 `sql_score` 和 `quality_score` 两个可选浮点字段（默认 None），用于存储单次 Agent 运行的 judge 得分
  - [ ] 1.2 在 `EvaluationReport` 模型中新增 `hdc_generation_tokens` 可选整数字段（默认 None），用于存储用户通过 CLI 传入的 HDC 离线生成 token 数
  - Pydantic 模型序列化输出中包含新增字段（值为 None 时 JSON 中为 null），现有字段类型和语义不受影响
  - _Requirements: 2.4, 4.1_

- [ ] 2. Core：评测逻辑和报告增强
  - [ ] 2.1 (P) `--compare-hdc` 启动时前置校验 `hdc_enabled` 开关（若未启用则打印明确错误信息和 `export HDC_ENABLED=true` 修复指引后 exit code 非零退出）；同时根据用例数、repeat 次数和预设平均耗时（90s）估算并打印总耗时
    - 未设 `HDC_ENABLED=true` 时运行 `--compare-hdc` 立即报错退出
    - 正常运行 `--compare-hdc` 时终端首行打印预估耗时
    - `--with-hdc` 单轮模式不受此校验影响（由 `_inject_hdc_context()` 内部静默降级）
    - _Requirements: 1.1, 1.2, 1.3, 5.1_
    - _Boundary: CLI (cli.py)_

  - [ ] 2.2 (P) 新增 `--hdc-gen-tokens` CLI 参数（`run` 子命令，类型 int，默认 None），并透传至 `run_evaluation()` → `EvaluationReport.hdc_generation_tokens`
    - `--hdc-gen-tokens 500000` 传入后 JSON 报告的 `hdc_generation_tokens` 字段为 500000
    - 未传入时该字段为 null（向后兼容）
    - _Requirements: 4.1_
    - _Boundary: CLI (cli.py)_
    - _Depends: 1.2_

  - [ ] 2.3 (P) `repeat > 1` 时对每条用例的每一次 Agent 运行都执行 SQL 正确性评判和回答质量评判，各次得分排除外部服务异常值后取算术平均值覆盖 `sql_judge.score` 和 `quality_judge.score`；同时 HDC 验证对所有运行聚合（injected 取 OR、correct_table_in_context 取 OR、agent_used_correct_table 取多数、is_hallucination 取 OR）；`--verbose-hdc` 在 repeat>1 时为每次运行输出 HDC 注入状态（移除 `run_index == 0` 限制）
    - repeat=3 时每条用例的 SQL judge 调用 3 次，最终 `sql_judge.score` 为正常 runs 的均值（排除因 OneDBA/LLM API 异常失败的 judge）
    - judge 因外部服务不可用失败时 `RunDetail.sql_score = None`（标记为异常值，不纳入均值）；因 Agent 未生成 SQL 导致 score 为 0.0 时正常纳入
    - repeat=1 时行为完全不变（仅调用 judge 一次）
    - 每次运行的原始 judge 得分记录在 `RunDetail.sql_score` 和 `RunDetail.quality_score` 中
    - JSON 报告中的 `run_details` 数组每个元素包含 `sql_score` 和 `quality_score` 字段
    - `--verbose-hdc` 在 repeat>1 时终端输出格式为 `[HDC] {case_id}#{run_index}: ...`，repeat=1 时保持原格式
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
    - _Boundary: Runner (runner.py)_
    - _Depends: 1.1_

  - [ ] 2.4 (P) HDC 对比报告中新增三项增强：1) `_render_hdc_audit()` 末尾从 `diff` 字典读取首表命中率和幻觉率（由 `_compute_hdc_diff()` 计算，确保 JSON 和 Markdown 一致）并追加汇总行；2) `_render_hdc_comparison_md()` 全局对比表在"平均 Token"后增加"HDC 离线生成 Token"行（仅 `hdc_generation_tokens` 非 None 时显示）并补充结论摊销说明；3) `_compute_hdc_diff()` 返回结构中追加 `first_table_hit_rate: float | None` 和 `hallucination_rate: float | None` 字段（参照 design.md 中 `_compute_hdc_diff()` 增加 JSON 聚合字段 节）
    - 首表命中率和幻觉率由 `_compute_hdc_diff()` 计算一次，`_render_hdc_audit()` 从 `diff` 字典读取（不重复计算），JSON 和 Markdown 中数值严格一致
    - `_render_hdc_audit()` 签名增加 `diff: dict` 参数
    - repeat>1 时首表命中要求所有运行都命中才算命中
    - 幻觉率 = 被标记为幻觉的用例数（含 OR 聚合） / 有 HDC 验证数据的用例数
    - JSON 对比报告 `diff` 中 `first_table_hit_rate` 和 `hallucination_rate` 为 None 时表示无数据，Markdown 中显示 "N/A"
    - `--hdc-gen-tokens` 未传入时 Markdown 报告中不出现对应行
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.2, 4.3_
    - _Boundary: Reporter (reporter.py)_
    - _Depends: 2.2_

- [ ] 3. 集成验证
  - [ ] 3.1 端到端验证：使用 2 条测例运行 `--compare-hdc --repeat 3 --hdc-gen-tokens 500000`，验证 JSON 和 Markdown 报告包含所有新字段和新章节
    - `--compare-hdc` 在 `HDC_ENABLED=false` 时正确报错退出
    - `--compare-hdc` 正常运行时终端首行显示预估耗时
    - JSON 报告的 `case_results[].sql_judge.score` 为 3 次均值
    - JSON 报告的 `run_details[]` 每个元素含 `sql_score` 和 `quality_score`
    - JSON 报告的 `hdc_generation_tokens` 字段为 500000
    - JSON 对比的 `diff` 含 `first_table_hit_rate` 和 `hallucination_rate`
    - Markdown 报告含"首表命中率"和"幻觉率"汇总行
    - Markdown 报告含"HDC 离线生成 Token"行和摊销说明
    - _Requirements: 1.1, 2.1, 2.4, 3.1, 3.3, 4.1, 5.1_
    - _Depends: 2.1, 2.2, 2.3, 2.4_
