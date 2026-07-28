# 研究日志

## 发现范围
轻量级发现（扩展类功能），聚焦于现有代码库中的集成点和模式。

## 关键发现

### 1. 现有计时模式
- `_run_agent()` 使用 `time.monotonic()` 在函数入口（runner.py:97）和退出点（runner.py:249,263）计时
- `ToolCallContext` 在 `tools/__init__.py:157-178` 已有 `elapsed_ms` 属性，但仅用于 timeout middleware 判断超时，未传播到 Runner 层
- 评测框架 `_execute_agent_once()` 有独立的 `start_time`/`duration_ms`（runner.py:67,123），与 Agent stats 中的 `duration_ms` 是相互独立的计时

### 2. Stats 结构现状
- stats 字典仅有 3 个键：`duration_ms`、`num_turns`、`tokens`
- `tokens` 是 `input_tokens + output_tokens` 的总和，内部已分开累积（runner.py:98-99,154-156），但输出时合并
- 评测框架 `_build_run_detail()` 仅消费 `stats["num_turns"]` 和 `stats["tokens"]`，有 `isinstance(dict)` 防御性检查，新增字段安全

### 3. 4 路检索为顺序执行
- `_execute_agent_stream()` 中的 4 路检索（OpenViking、偏好、SQL 记忆、HDC）是顺序执行的，各自有独立的 try/except
- 每个块写入 `initial_state` 的不同键：`_memories`、`_preferences`、`_sql_memories`、`_hdc_context`

### 4. NL2SQL 引擎接口约束
- `query_database()` 返回 `str`，无法直接携带结构化元数据
- 所有 6 个工具遵循统一的 `async def tool(**kwargs) -> str` 签名
- 使用 `contextvars.ContextVar` 作为侧通道是最小侵入方案

### 5. Token 估算依赖
- 项目当前无 `tiktoken` 依赖
- DeepSeek-V4 的 tokenizer 可能不兼容 `tiktoken` 的 `cl100k_base` 编码
- 降级方案：`len(text) / 4` 字符估算（中文约 1.5-2 字符/token，英文约 4 字符/token）

## 设计决策

### ContextVar 侧通道（NL2SQL 耗时）
- **决策**：使用 `contextvars.ContextVar` 传递 NL2SQL 引擎耗时
- **理由**：避免修改 6 个工具的统一 `str` 返回接口，不破坏工具注册表中间件链
- **替代方案**：修改 `_execute_tool()` 返回 `(str, metadata)` 元组 → 影响所有工具和中间件，改动范围大

### Token 拆分（不拆分输入/输出独立字段）
- **决策**：stats 中增加 `input_tokens` 和 `output_tokens`，保留 `tokens` 总和
- **理由**：向后兼容，评测框架仍可用 `stats.get("tokens")` 消费

### 字符估算降级（Token 估算）
- **决策**：`tiktoken` 不可用时使用 `len(text) / 4` 估算
- **理由**：不引入硬依赖，允许 ±10% 偏差，满足需求 6 的验收标准

## 风险
- `contextvars` 在 asyncio 中的行为已验证（Python 3.12 原生支持）
- 新增字段不会导致 Langfuse trace 结构变化（仅在 metadata 中追加）
- 评测框架的 `isinstance(dict)` 防御性检查确保新增字段不破坏现有逻辑