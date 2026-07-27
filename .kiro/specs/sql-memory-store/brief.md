# Brief: sql-memory-store

## Problem
当前 Agent 的每次 NL2SQL 查询都是"冷启动"——不记得自己或他人过去在同一个数据库上成功执行过的 SQL。已有的 `agent-memory-store`（操作偏好记忆）只记录表名使用频次，不存储实际 SQL 文本和执行结果。Agent 无法利用历史成功经验作为 few-shot 参考，也无法从积累的 SQL 中挖掘查询模式。

## Current State
- `agent-memory-store` 已完整实现：`query_preferences` 表记录 `(user_id, table_name, database_name, query_count, last_query_at)`，已预留 `sql_patterns` JSON 字段但从未使用。
- `SemanticContext.history_sql` 字段已定义但从未传递。
- 没有检索历史 SQL 的工具或机制。
- 评估框架已成熟：`--compare-hdc` 对比模式可直接复用为 `--compare-sql-memory`。

## Desired Outcome
Agent 具备 SQL 历史记忆能力，能：
1. **自动记录**：每次成功执行 SQL 后，自动持久化（SQL 文本 + 执行结果摘要 + 关联的问题描述 + 涉及的表名/数据库）。
2. **语义检索**：Agent 启动前，基于用户当前问题做语义检索，召回 top-K 相关的历史 SQL 作为 few-shot 注入上下文。
3. **混合作用域**：默认 per-user 隔离，支持配置为 per-database 共享模式。
4. **模式挖掘**：积累足够历史后，自动发现高频表、高频查询模式、常见 JOIN 关系。
5. **可量化评估**：通过对比评测（无记忆 vs 有记忆）验证模块的实际收益。

## Approach
扩展 `app/memory/` 层，新增 `SqlMemoryStore`（遵循 `StorageBackend` Protocol 风格），实现 SQL 历史记录的写入、语义检索、作用域过滤。注入流程复用 `build_context()` 的 7 段式结构（新增第 8 段 `[SQL 历史记忆 — 相关查询]`）。评估直接复用 `--compare-hdc` 模式，新增 Memory Impact 维度。

## Scope
- **In**:
  - SQL 记录自动写入（Post-execution hook）
  - 语义检索 + 相似度排序（嵌入向量）
  - Per-user / Per-database 混合作用域
  - 上下文注入（第 8 段 prompt）
  - 4 层测试：Unit → 检索精度 → Context 注入 → E2E 对比评测
- **Out**:
  - SQL 执行结果的完整存储（只存摘要/行数预览）
  - 复杂的权限模型（不超出 OneDBA 已有的权限体系）
  - 跨服务分布式检索（单进程内完成）

## Boundary Candidates
- **SqlMemoryStore** — 存储层（CRUD + 语义检索），独立于 agent-memory-store
- **SqlMemoryRecorder** — 写入钩子（post-execution hook），集成到 routes.py
- **SqlMemoryRetriever** — 检索 + 上下文格式化，注入到 build_context()
- **PatternMiner** — 离线模式挖掘，可选模块

## Out of Boundary
- 不修改 `agent-memory-store` 的 `query_preferences` 表结构
- 不修改 OpenViking 的语义记忆
- 不修改 HDC Data Vault
- 不实现用户 UI 查询历史浏览（纯 Agent 内部使用）

## Upstream / Downstream
- **Upstream**:
  - `app/memory/preferences.py` — 复用记录钩子位置（`routes.py` 的 post-execution）
  - `app/agent/context.py` — 复用 `build_context()` 的段落注入机制
  - `tests/evaluation/` — 复用对比评测框架
  - `app/tools/query_database.py` — SQL 生成的源头
- **Downstream**:
  - 语义规则注入增强（模式挖掘 → `nl2sql/semantics.py`）
  - 用户查询历史浏览功能（未来 UI）

## Existing Spec Touchpoints
- **Extends**: `agent-memory-store` — 共享存储抽象和 hook 位置，但独立数据表
- **Adjacent**: `hdc-datavault-knowledge-base` — 都提供 Agent 上下文增强，但信息来源不同（schema 文档 vs 历史 SQL）

## Constraints
- 存储后端：SQLite（与 sessions/preferences 共享文件，独立表）
- 嵌入模型：复用现有 DeepSeek-V4 或轻量 embedding 模型（通过 OpenAI 兼容 API）
- Token 预算：注入的 SQL 记忆段落需支持截断（默认 max 5 条，每条 SQL 截断至 500 字符）
- 不增加 Agent 首 token 延迟超过 500ms（检索 + 注入）
- 混合作用域通过配置开关控制，默认 per-user
