# 实施计划

## 任务格式说明
- `(P)` — 可与同阶段其他 `(P)` 任务并行执行
- `_Requirements:` — 仅列出需求数字 ID
- `_Boundary:` — 标示组件所属边界（设计文档中的组件名）

---

- [ ] 1. Foundation: 修改核心函数签名以承载新增指标
- [ ] 1.1 (P) 修改 `_execute_tool` 返回元组 `(result, elapsed_ms)`
  - 在 `_execute_tool()` 中记录调用前后的 `time.monotonic()`
  - 将原返回值 `str` 改为 `tuple[str, float]`，float 为执行耗时（毫秒）
  - 所有调用方（`_run_agent` 中的两处 `await _execute_tool(...)`）适配元组解包
  - 验证：工具执行后 `elapsed_ms > 0` 且该值合理（非负数）
  - _Requirements: 1_
  - _Boundary: Agent Runner — _execute_tool_

- [ ] 1.2 (P) 修改 `build_context` 返回元组 `(context_str, ctx_tokens)`
  - 在组装 8 段上下文时为每段估算 Token 数
  - 使用 `tiktoken`（优先）或 `len(text) / 4`（降级）进行估算
  - 返回 `(context_str, ctx_tokens_dict)`，`ctx_tokens_dict` 键名为 8 段上下文名称
  - 降级时在 `ctx_tokens` 中增加 `_method: "char_estimate"` 标记
  - 验证：`ctx_tokens` 包含 8 个键且值均为正整数
  - _Requirements: 6_
  - _Boundary: Context Builder — build_context_

- [ ] 2. Core: Agent Runner 指标增强
- [ ] 2.1 `_run_agent` — 工具耗时与 Token 拆分
  - 将 `total_input_tokens` 和 `total_output_tokens` 独立注入 stats 的 `input_tokens` / `output_tokens` 字段
  - 保留 `tokens` 字段（总和）确保向后兼容
  - 在 `tool_end` 事件中增加 `elapsed_ms` 字段（来自 1.1 的元组返回值）
  - 新增 `tool_timings` 字典累加各工具总耗时和调用次数
  - 验证：final stats 包含 `input_tokens`、`output_tokens`、`tool_timings` 三个新字段
  - _Requirements: 1, 2_
  - _Depends: 1.1_
  - _Boundary: Agent Runner — _run_agent_

- [ ] 2.2 `run_agent_stream` — TTFB 计时与上下文 Token 透传
  - 在 `_run_agent()` 产出首个非 `llm_call` 事件时记录 `t_first`，计算 `ttfb_ms`
  - 适配 1.2 的 `build_context` 返回值变更，接收 `(context_str, ctx_tokens)`
  - 将 `ttfb_ms` 和 `ctx_tokens` 注入 stats
  - 验证：final stats 包含 `ttfb_ms` 和 `ctx_tokens` 字段
  - _Requirements: 3, 6_
  - _Depends: 1.1, 1.2_
  - _Boundary: Agent Runner — run_agent_stream_

- [ ] 2.3 (P) `_execute_agent_stream` — 上下文准备耗时与检索分解
  - 请求到达时记录 `t0`
  - 4 路检索各自由 try/except 包裹并记录各自耗时
  - 上下文准备完成时记录 `t_prep`，计算 `prep_ms = t_prep - t0`
  - 将 `prep_ms` 和 `ctx_timings`（`memories_ms`、`preferences_ms`、`sql_memories_ms`、`hdc_ms`）注入 final SSE 的 stats
  - 禁用检索源对应字段设为 `null`
  - 验证：final SSE stats 包含 `prep_ms` 和 `ctx_timings`，禁用检索源的字段为 `null`
  - _Requirements: 3, 4_
  - _Boundary: API Routes — _execute_agent_stream_

- [ ] 2.4 (P) `query_database` — NL2SQL 引擎分段耗时
  - 新增 `contextvars.ContextVar` 变量 `_nl2sql_timings`
  - 在 DESCRIBE、generate_sql、validate_sql、repair_sql 各阶段前后记录 `time.monotonic()`
  - 将耗时写入 `_nl2sql_timings`，包含 `describe_ms`、`generate_ms`、`validate_ms`、`repair_ms`
  - 失败阶段也记录耗时（`repair_ms` 默认为 0）
  - `_execute_tool` 中读取 `_nl2sql_timings` 并附加到 `tool_end` 的 metadata
  - 验证：`_nl2sql_timings` 在 `query_database` 调用后被正确写入和读取
  - _Requirements: 5_
  - _Boundary: NL2SQL Engine — query_database_

- [ ] 3. Integration: 端到端数据流贯通
- [ ] 3.1 串联 routes → runner → stats 的完整指标链路
  - 确保 `_execute_agent_stream` 中计算的 `prep_ms`、`ctx_timings` 注入到 final SSE 的 stats
  - 确保 `run_agent_stream` 中计算的 `ttfb_ms`、`ctx_tokens` 正确传递
  - 确保 `_run_agent` 的 stats（input_tokens、output_tokens、tool_timings）无遗漏
  - 使用 `stats.setdefault()` 或独立键名确保合并安全
  - 验证：一次完整查询后 final SSE stats 包含所有新增字段且值语义正确
  - _Requirements: 7_
  - _Depends: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: Cross-layer — routes → runner_

- [ ] 4. Validation: 测试与验证
- [ ] 4.1 单元测试：核心函数签名和返回值
  - `_execute_tool()` 返回元组格式验证
  - `build_context()` 返回 `ctx_tokens` 结构和键完整性
  - `query_database` 中 `_nl2sql_timings` 写入和读取
  - 验证：3 个测试通过，覆盖签名变更和 ContextVar 行为
  - _Requirements: 1, 5, 6_
  - _Depends: 1.1, 1.2, 2.4_

- [ ] 4.2 集成测试：SSE 事件结构与向后兼容
  - SSE `tool_end` 包含 `elapsed_ms` 字段且值 > 0
  - final SSE stats 包含所有新增字段且类型正确
  - 禁用某路检索时对应 `ctx_timings` 字段为 `null`
  - `tiktoken` 不可用时降级行为正确
  - 现有评测框架消费 final 事件无异常
  - 验证：5 个测试用例通过
  - _Requirements: 1, 2, 3, 4, 6, 7_
  - _Depends: 3.1_

- [ ] 4.3 E2E 验证：完整查询流时间顺序
  - 发起真实查询，验证 `prep_ms < ttfb_ms < duration_ms` 时间顺序
  - 统计各指标语义正确（`input_tokens + output_tokens == tokens`）
  - NL2SQL 引擎耗时 `describe_ms > 0` 且 `generate_ms > 0`
  - 验证：时间顺序断言通过，Token 等式成立
  - _Requirements: 3, 2, 5_
  - _Depends: 3.1_