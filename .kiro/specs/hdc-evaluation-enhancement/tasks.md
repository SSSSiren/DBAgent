# 实施计划

## 任务

- [x] 1. 数据模型：新增 HdcVerificationData 和扩展 RunDetail/CaseResult
  - 在 `tests/evaluation/models.py` 中新增 `HdcVerificationData` Pydantic 模型，包含 `injected`、`context_chars`、`reference_table`、`correct_table_in_context`、`agent_table_used`、`agent_used_correct_table`、`is_hallucination` 字段
  - 在 `RunDetail` 模型中追加 `first_tool`、`first_table_used`、`called_find_table_before_query` 三个字段（均为可选默认值）
  - 在 `CaseResult` 模型中追加 `hdc_verification: Optional[HdcVerificationData]` 字段
  - 完成标志：`HdcVerificationData` 可被 Pydantic 序列化/反序列化，`CaseResult` 的 `model_dump(mode="json")` 输出包含新字段
  - _Requirements: 2.1, 2.2, 2.4, 3.1, 3.2, 5.3_

- [ ] 2. 运行器：新增 HDC 验证和首轮追踪函数
  - 在 `tests/evaluation/runner.py` 中新增 `_verify_hdc_injection(hdc_context, test_case, agent_output) -> HdcVerificationData` 函数：接收 `hdc_context` 字符串（而非 session_state dict），搜索参考表名，从 Agent SQL 提取实际表名，判断是否幻觉
  - 新增 `_extract_first_tool_info(agent_output) -> tuple[str, str, bool]` 函数：从 `tool_calls` 列表提取 first_tool、first_table_used（首个 query_database 或 execute_sql 调用的 table_name）、called_find_table_before_query
  - 修改 `_AgentRunOutput` dataclass：新增 `hdc_context: str = ""` 字段
  - 修改 `_run_one()` 内部函数：在 `_inject_hdc_context()` 成功后，将 `session_state.get("_hdc_context", "")` 存入 `_AgentRunOutput.hdc_context`
  - 修改 `_build_run_detail()`：调用 `_extract_first_tool_info(run)` 填充 RunDetail 新字段
  - 在 `_run_single_case()` 中，HDC 轮次时取 `last_run.hdc_context` 调用 `_verify_hdc_injection()`，将结果赋给 `CaseResult.hdc_verification`
  - 完成标志：`_run_single_case()` 在 `enable_hdc=True` 时产生 `CaseResult.hdc_verification` 非 None，每个 `RunDetail` 含首轮追踪数据
  - _Requirements: 2.1, 2.2, 2.4, 3.1, 3.2_
  - _Boundary: runner.py_
  - _Depends: 1_

- [ ] 3. (P) 报告器：新增逐工具效率对比和 HDC 审计渲染
  - 在 `tests/evaluation/reporter.py` 中新增 `_render_per_tool_breakdown(lines, no_hdc, with_hdc)` 函数：读取 `no_hdc` 和 `with_hdc` 报告中的 `case_results[].efficiency.tool_call_details`，渲染 find_table、describe_table、query_database 三种工具的基线 vs HDC 对比表，含趋势标注、汇总行、首轮 find_table 调用率
  - 新增 `_render_hdc_audit(lines, with_hdc)` 函数：读取 `with_hdc.case_results[].hdc_verification`，渲染逐用例审计表（HDC 含正确表、Agent 用正确表、幻觉），末尾输出聚合统计
  - 修改 `_render_hdc_comparison_md()` 中的逐用例对比表：在现有列后新增"首轮正确"列，从 `run_details[].first_table_used` 与 `test_case.reference_sql` 提取的表名对比判断
  - 在 `_render_hdc_comparison_md()` 末尾（结论章节之前）追加调用 `_render_per_tool_breakdown()` 和 `_render_hdc_audit()`
  - 完成标志：`--compare-hdc` 生成的 Markdown 报告包含"工具调用效率对比"和"HDC 正确性审计"两个新章节，逐用例对比表含"首轮正确"列
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.3, 2.5, 3.3, 3.4, 5.2, 5.4_
  - _Boundary: reporter.py_
  - _Depends: 1_

- [ ] 4. (P) CLI：新增 --verbose-hdc 参数和实时输出
  - 在 `tests/evaluation/cli.py` 的 `run` 子命令中新增 `--verbose-hdc` 参数
  - 新增 `verbose_hdc` 参数到 `run_evaluation()` 函数签名，透传至 `_run_single_case()`，在 `_run_one()` 中 `_inject_hdc_context()` 返回后打印注入状态行
  - 注入状态行格式：`[HDC] {case_id}: 已注入({chars}字符) | 正确表在上下文中={yes/no}`（正确表名通过子字符串搜索判断，仅需输出 yes/no）
  - 注入失败时打印 `[HDC] {case_id}: 注入失败，跳过` 但不中断评测
  - 在 `_run_compare_hdc()` 的有 HDC 轮次结束后，遍历 `with_hdc_report.case_results` 汇总并打印聚合摘要：注入成功数、正确表在上下文中数、Agent 采纳正确表数、Agent 幻觉数
  - 未使用 `--verbose-hdc` 时保持现有输出格式不变
  - 完成标志：`--compare-hdc --verbose-hdc` 运行时终端输出每条用例的 HDC 注入状态和最终聚合摘要
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - _Boundary: cli.py, runner.py_
  - _Depends: 1, 2_

- [ ] 5. 集成验证：E2E 测试确保完整流程
  - 编写集成测试：用 2 条 CS 用例运行 `--compare-hdc`，验证 JSON 报告含 `hdc_verification` 字段和 `RunDetail` 新字段
  - 验证 Markdown 报告含"工具调用效率对比"和"HDC 正确性审计"章节，逐用例对比表含"首轮正确"列
  - 验证 `--verbose-hdc` 终端输出格式正确
  - 验证 `--with-hdc` 单轮模式（非 `--compare-hdc`）报告无新章节、无新增字段
  - 完成标志：集成测试通过，证明新旧模式均向后兼容
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Depends: 1, 2, 3, 4_