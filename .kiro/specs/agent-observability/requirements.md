# 需求文档

## 简介
本项目旨在为 DBAgent 补充细粒度可观测性能力，使运维人员和开发者能够诊断查询性能瓶颈。当前系统仅提供端到端的总耗时、总 Token 和总工具调用次数三个粗粒度指标，无法回答"哪个环节慢"的问题。本需求聚焦于补齐 6 项关键缺口，覆盖工具级、阶段级和上下文级的可观测性。

## 边界上下文
- **范围内**：工具执行耗时采集与传播、输入/输出 Token 拆分、TTFB 与上下文准备耗时、上下文检索耗时分解、NL2SQL 引擎分段耗时、上下文 Token 占比估算
- **范围外**：新的外部监控集成（Prometheus/Grafana）、美元成本估算、告警/通知系统、分布式追踪变更、新的持久化存储需求
- **相邻预期**：Langfuse trace 已有 span 结构，新增指标应兼容现有 span 生命周期；现有 SSE 事件结构保持不变，新增字段为向后兼容的追加；评测框架（tests/evaluation/）应能消费新增 stats 字段无需改动

## 需求

### 需求 1：工具执行耗时可见性
**目标：** 作为运维人员或开发者，我希望看到每次工具调用的实际耗时，以便诊断哪些工具调用是性能瓶颈。

#### 验收标准
1. When Agent 执行工具调用，the DBAgent shall 记录该次工具调用的执行耗时（毫秒）
2. When 工具调用完成，the SSE `tool_end` 事件 shall 包含 `elapsed_ms` 字段
3. When Agent 查询完成，the final stats shall 包含 `tool_timings` 字段，列出各工具名称及其累计耗时和调用次数
4. If 工具调用失败，the DBAgent shall 仍记录其耗时

### 需求 2：输入/输出 Token 拆分
**目标：** 作为开发者，我希望区分输入 Token 和输出 Token 的消耗，以便诊断是 prompt 膨胀还是模型过度推理导致的 Token 增长。

#### 验收标准
1. When Agent 完成查询，the final stats shall 包含 `input_tokens` 和 `output_tokens` 两个独立字段
2. When Agent 完成查询，the final stats shall 保留 `tokens` 字段（总和），确保向后兼容
3. While Agent 在 ReAct 循环中多次调用 LLM，the DBAgent shall 逐轮累加 `prompt_tokens` 和 `completion_tokens`

### 需求 3：TTFB 与上下文准备耗时
**目标：** 作为运维人员，我希望知道从请求到达到首个有意义输出的时间（TTFB），以及上下文准备阶段的耗时，以便区分"准备慢"和"推理慢"。

#### 验收标准
1. When 聊天请求到达，the DBAgent shall 记录请求到达时间戳
2. When 上下文准备完成（4路并行检索结束），the DBAgent shall 记录准备阶段耗时 `prep_ms`
3. When Agent 产出首个输出（文本或工具调用），the DBAgent shall 记录 TTFB `ttfb_ms`
4. When Agent 查询完成，the final stats shall 包含 `prep_ms` 和 `ttfb_ms` 字段

### 需求 4：上下文检索耗时分解
**目标：** 作为开发者，我希望知道 4 路并行检索各自耗时，以便定位哪个检索源是性能瓶颈。

#### 验收标准
1. When DBAgent 执行 4 路并行检索，the DBAgent shall 分别记录各检索源的耗时
2. When Agent 查询完成，the final stats shall 包含 `ctx_timings` 字段，包含 `memories_ms`（OpenViking 长期记忆）、`preferences_ms`（查询偏好）、`sql_memories_ms`（SQL 历史记忆）、`hdc_ms`（HDC 数据底座）
3. If 某路检索被配置禁用（如 `kb_enabled=false`），the 对应字段 shall 标记为 `null` 或不存在

### 需求 5：NL2SQL 引擎内部分段耗时
**目标：** 作为开发者，我希望看到 NL2SQL 引擎内部各阶段的耗时分布，以便诊断 SQL 生成、校验或修复阶段的性能问题。

#### 验收标准
1. When `query_database` 工具执行 NL2SQL 流水线，the DBAgent shall 记录各阶段耗时：`describe_ms`（DESCRIBE 表）、`generate_ms`（SQL 生成）、`validate_ms`（SQL 校验）
2. If SQL 校验失败触发自动修复，the DBAgent shall 额外记录 `repair_ms`（SQL 修复）耗时
3. When 工具调用完成，the NL2SQL 分段耗时 shall 通过 SSE 事件或工具结果元数据对外暴露
4. If NL2SQL 流水线中某阶段失败，the DBAgent shall 仍记录该阶段耗时

### 需求 6：上下文 Token 占比估算
**目标：** 作为开发者，我希望知道 8 段上下文中各段的 Token 占比，以便在 context window 紧张时针对性裁剪。

#### 验收标准
1. When `build_context()` 组装上下文，the DBAgent shall 估算各段上下文的 Token 数
2. When Agent 查询完成，the final stats shall 包含 `ctx_tokens` 字段，按上下文段名称列出估算 Token 数
3. The Token 估算 shall 使用与 LLM 兼容的 tokenizer 进行，允许 ±10% 的偏差
4. If tokenizer 不可用，the DBAgent shall 降级为字符数估算并标记估算方法

### 需求 7：向后兼容性
**目标：** 作为运维人员，新增的可观测性字段不应破坏现有的 SSE 消费者（前端、评测框架）。

#### 验收标准
1. The 新增 stats 字段 shall 仅追加到现有结构，不删除或重命名已有字段
2. The 现有 SSE 事件类型（`step`、`sql`、`final`、`llm_call`）shall 保持其现有字段不变
3. When 评测框架消费 SSE 事件，the 新增字段 shall 不影响现有效率评判逻辑