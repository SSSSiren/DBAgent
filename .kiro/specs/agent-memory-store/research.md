# Research & Design Decisions

## Summary
- **Feature**: `agent-memory-store`
- **Discovery Scope**: New Feature (Extension)
- **Key Findings**:
  - 现有系统使用 OpenViking 提供语义记忆，但无结构化操作记忆（表名、schema_id、SQL 模式）
  - 现有 `SqliteStore` 已使用 aiosqlite + WAL 模式，`query_preferences` 表可在同一数据库文件中新增，无需额外依赖
  - 现有记忆注入流程（检索 → initial_state → build_context → 注入 prompt）可直接复用，偏好记录钩子可镜像 OpenViking 的 `_record_to_openviking` 模式

## Research Log

### Codebase Architecture Analysis
- **Context**: 理解现有代码结构，确定集成点和扩展模式
- **Sources Consulted**: `app/agent/runner.py`, `app/agent/context.py`, `app/agent/prompts.py`, `app/api/routes.py`, `app/memory/store.py`, `app/knowledge/openviking.py`, `app/config.py`, `app/tools/query_database.py`
- **Findings**:
  - Agent 执行流：`_execute_agent_stream()` 在 Agent 执行前检索 OpenViking 记忆，执行后调用 `_record_to_openviking()` 记录对话
  - `build_context()` 按顺序构建：摘要 → 历史 → 数据库 → 长期记忆 → 返回
  - `SqliteStore` 使用 aiosqlite + WAL 模式，`DEFAULT_SESSION` 模板定义了会话状态字段
  - `query_database` 工具接收 `schema_id`, `question`, `table_name` 参数，返回 Markdown 格式结果
  - 现有 `tool_calls_info` 列表在 Agent 执行后可用，包含每个工具调用的 `tool`, `args`, `result`
- **Implications**: 偏好记录钩子放在 `_execute_agent_stream()` 的 final 事件处理阶段，偏好检索钩子放在 memory 检索阶段

### Storage Pattern Analysis
- **Context**: 确定偏好数据的存储方案
- **Sources Consulted**: `app/memory/store.py` (SqliteStore 实现)
- **Findings**:
  - SqliteStore 使用 aiosqlite + WAL 模式，`data/sessions.db` 已有 `sessions` 表
  - 会话状态以 JSON blob 存储在 `state_json` 列
  - 工厂函数 `get_store()` 支持 "memory" 和 "sqlite" 后端切换
  - 无现有偏好/操作记忆表
- **Implications**: 新增 `query_preferences` 表在同一 SQLite 文件，使用独立连接和 DDL，与会话存储解耦

### OpenViking Integration Analysis
- **Context**: 理解现有记忆系统的工作方式，确保新功能不冲突
- **Sources Consulted**: `app/knowledge/openviking.py`, `app/api/routes.py`
- **Findings**:
  - OpenViking 通过 HTTP API 调用，`kb_enabled` 控制开关
  - 记忆检索每轮对话开始时执行，注入 `initial_state["_memories"]`
  - 记忆记录每轮对话结束后执行，`kb_auto_commit_turns` 控制 commit 频率
  - `retrieve_memories()` 遍历 7 个类别，返回 `list[{"category", "abstract", "name"}]`
  - 记忆检索和记录都有独立的 try/except 静默降级
- **Implications**: 偏好功能使用独立的 `preference_enabled` 开关和独立的 try/except，确保与 OpenViking 互不干扰

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Hook-based (selected) | 在现有 Agent 执行流前后插入钩子 | 最小侵入性，遵循现有模式，无需修改 ReAct 循环 | 钩子逻辑集中在 routes.py，可能增加该文件复杂度 | 与 OpenViking 记忆检索模式一致 |
| Middleware | 作为 FastAPI 中间件拦截请求/响应 | 更低的耦合度 | 无法访问 Agent 内部的 tool_calls_info，记录时机难以确定 | 信息不足，不适合 |
| Tool-level hook | 在 query_database 内部记录偏好 | 记录逻辑与工具紧密耦合 | 工具需要知道 user_id 和 session 上下文，违反单一职责 | 工具层不应知道用户身份 |

## Design Decisions

### Decision: 独立 SQLite 表 + 独立 Store 类
- **Context**: 偏好数据需要持久化，与会话数据不同质
- **Alternatives Considered**:
  1. 在 sessions 表的 state_json 中嵌入偏好数据 — 查询困难，无法高效检索
  2. 使用独立的 SQLite 数据库文件 — 增加运维复杂度
- **Selected Approach**: 在现有 `data/sessions.db` 中新增 `query_preferences` 表，使用独立的 `QueryPreferenceStore` 类管理
- **Rationale**: 复用现有数据库连接基础设施，结构化查询支持 LIKE 搜索和排序，独立类避免污染 SessionStore 的职责
- **Trade-offs**: 需要管理两个独立的数据库连接（preferences 和 sessions），但 aiosqlite 连接开销可接受
- **Follow-up**: 如果未来需要跨表查询，可考虑统一连接管理

### Decision: 存储容量控制 — 每用户上限 + UPSERT
- **Context**: 偏好数据使用 UPSERT 而非日志追加，同一张表无论查询多少次只占 1 行。每行约 120 bytes，即使 1000 用户 × 500 表/人 = 60 MB，仍在 SQLite 舒适范围内。核心风险不是文件大小，而是低频表挤占高频表的检索窗口。
- **Alternatives Considered**:
  1. 无上限 — 极端场景下每用户可能累积数百行，但总量仍可控
  2. 基于 `last_query_at` 的 TTL 过期 — 需要定时任务，增加复杂度
  3. 每用户固定上限 + LRU 淘汰 — 简单有效
- **Selected Approach**: 每用户上限 `max_per_user = 50`（`retrieve_preferences` limit × 10），INSERT 前若已达上限且新记录不命中已有行，则淘汰 `query_count` 最小的记录（LRU 策略）。该上限确保检索窗口（limit=5）始终能覆盖最有用数据。
- **Rationale**: 操作简单、无定时任务、淘汰逻辑在 SQL 层完成；50 条上限对实际用户绰绰有余（一个数据分析师日常涉及的表通常不超过 20-30 张）
- **Trade-offs**: 边缘场景下，一个查询了 50 张不同低频表的用户可能丢失这些记录，但新查询会重新记录
- **Follow-up**: 上限值可通过 `Settings` 配置化，后续可改为基于 `last_query_at` 的阈值清理

### Decision: SQL LIKE 关键词匹配
- **Context**: 需要根据用户输入检索匹配的偏好表
- **Alternatives Considered**:
  1. 全文搜索（FTS5）— 更强大但增加复杂度
  2. 向量嵌入搜索 — 需要外部依赖，过度设计
  3. 精确字符串匹配 — 过于严格
- **Selected Approach**: SQL LIKE 模糊匹配，分词后对 table_name 和 database_name 分别匹配
- **Rationale**: 偏好表数据量小（<1000 行/用户），LIKE 性能足够；无需新增依赖；实现简单
- **Trade-offs**: 中文分词精度有限（使用简单的正则分词），可能漏匹配或误匹配
- **Follow-up**: 如果用户反馈匹配精度不足，可考虑接入 jieba 分词或 FTS5

### Decision: 静默降级策略
- **Context**: 偏好功能不应影响正常对话流程
- **Alternatives Considered**:
  1. 硬失败（抛出异常）— 不符合产品需求（5.2, 5.3）
  2. 带重试的降级 — 增加延迟
- **Selected Approach**: 所有偏好操作包裹在独立的 try/except 中，失败时 print 日志并继续
- **Rationale**: 与 OpenViking 的错误处理模式一致（`_record_to_openviking` 同样静默降级），需求 1.4 明确要求
- **Trade-offs**: 偏好记录失败无感知，用户可能丢失偏好数据
- **Follow-up**: 后续可接入 Langfuse 观测偏好操作的成功率

## Risks & Mitigations
- **关键词匹配精度不足** → 监控匹配率，后续可升级为 jieba 分词或 FTS5
- **SQLite 文件锁竞争**（preferences 和 sessions 共用文件）→ WAL 模式支持并发读，写操作串行化
- **`sql_patterns` 预留字段未实现** → 当前版本仅存储空数组，后续版本实现自动提取，预留字段避免 schema 迁移
- **偏好数据无限增长** → 当前版本不做自动清理，后续可添加 TTL 或 LRU 策略

## References
- [aiosqlite Documentation](https://github.com/omnilib/aiosqlite) — 异步 SQLite 驱动
- [SQLite WAL Mode](https://www.sqlite.org/wal.html) — Write-Ahead Logging 并发模式
- [SQLite UPSERT](https://www.sqlite.org/lang_upsert.html) — ON CONFLICT DO UPDATE 语法