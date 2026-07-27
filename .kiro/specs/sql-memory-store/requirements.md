# Requirements Document

## Introduction
DBAgent 当前每次 NL2SQL 查询都是"冷启动"——不记得自己或他人过去在同一数据库上成功执行过的 SQL。已有的操作偏好记忆（agent-memory-store）仅记录表名使用频次，不存储实际 SQL 文本和执行结果。本模块为 Agent 新增 SQL 历史记忆能力：每次成功执行 SQL 后自动记录（SQL 文本 + 执行结果摘要 + 关联问题），在后续对话中通过语义检索召回相关历史 SQL 作为 few-shot 注入 Agent 上下文，支持 per-user 和 per-database 混合作用域，以及离线模式挖掘。

## Boundary Context
- **In scope**:
  - SQL 语句 + 执行结果摘要的自动持久化
  - 基于用户问题的语义检索（向量相似度排序）
  - 检索结果作为 few-shot 示例注入 Agent 上下文
  - Per-user 和 per-database 混合作用域
  - 基于历史 SQL 的模式挖掘（高频表、高频条件、常见 JOIN）
  - 配置开关控制启用/禁用及各项参数
- **Out of scope**:
  - 执行结果的完整存储（仅存行数、列名、数据预览）
  - 跨服务分布式检索（单进程内完成）
  - 用户可见的查询历史浏览 UI
  - 修改 `agent-memory-store` 的 `query_preferences` 表结构
  - 修改 OpenViking 语义记忆或 HDC Data Vault
- **Adjacent expectations**:
  - SQL 记忆模块与操作偏好记忆（agent-memory-store）共享 post-execution hook 位置，但使用独立数据表
  - 上下文注入复用 `build_context()` 的段落组装机制，不与已有的 7 段冲突
  - 评估框架复用 `--compare-hdc` 的对比评测模式

## Requirements

### Requirement 1: SQL 执行自动记录
**Objective:** As a DBAgent 用户，我希望每次 Agent 成功执行 SQL 后，SQL 语句和执行结果被自动记录，以便后续检索和参考。

#### Acceptance Criteria
1. When Agent 通过 `query_database` 或 `execute_sql` 工具成功执行 SQL 并返回非空结果，the SQL 记忆模块 shall 自动记录一条 SQL 记忆，包含：原始用户问题、执行的 SQL 文本、涉及的表名列表、数据库名称和 schema_id、执行结果的列名列表、结果行数、数据预览（前 3 行）。
2. When SQL 执行失败或返回空结果，the SQL 记忆模块 shall 仍记录 SQL 文本和问题，但标记执行状态为"失败"或"空结果"。
3. When 同一条 SQL 在同一会话中被重复执行，the SQL 记忆模块 shall 跳过重复记录，避免存储冗余。
4. If 记录写入失败，the SQL 记忆模块 shall 静默降级，不阻断 Agent 主流程，并记录 WARN 级别日志。
5. The SQL 记忆模块 shall 对单条 SQL 文本长度超过 2000 字符的记录进行截断存储，保留完整 SQL 的同时额外存储截断版本。

### Requirement 2: 语义检索
**Objective:** As a DBAgent 用户，我希望 Agent 在每次对话开始前，能够基于我的当前问题语义检索相关历史 SQL，作为参考示例。

#### Acceptance Criteria
1. When Agent 开始新一轮对话，the SQL 记忆模块 shall 基于用户当前问题文本生成嵌入向量，并在历史 SQL 记忆库中检索语义最相似的 top-K 条记录（K 可配置，默认 5）。
2. When 检索结果为空（记忆库中无记录或所有相似度低于阈值），the SQL 记忆模块 shall 返回空列表，不注入任何内容。
3. The SQL 记忆模块 shall 按语义相似度从高到低排序返回检索结果。
4. If 嵌入向量生成不可用（如生成服务暂时离线），the SQL 记忆模块 shall 静默降级，返回空列表并记录 WARN 日志。
5. The SQL 记忆模块 shall 在首次检索时对已存储但未生成嵌入向量的历史记录进行异步补嵌入。

### Requirement 3: Few-shot 上下文注入
**Objective:** As a DBAgent 用户，我希望检索到的相关历史 SQL 以清晰的格式注入到 Agent 上下文中，帮助 Agent 生成更准确的 SQL。

#### Acceptance Criteria
1. When SQL 记忆检索返回非空结果，the DBAgent shall 在 Agent 系统 prompt 和用户问题之间插入格式化的 `[SQL 历史记忆 — 相关查询]` 段落。
2. The SQL 记忆模块 shall 将每条历史记录格式化为：用户问题、执行的 SQL、结果摘要（行数 + 列名），并按相似度排序。
3. When 注入的 SQL 记忆段落总长度超过 token 预算上限（默认 1500 字符），the SQL 记忆模块 shall 截断至上限，优先保留相似度最高的记录。
4. When SQL 记忆检索返回空结果，the DBAgent shall 不注入任何 SQL 记忆段落，不改变已有的上下文结构。
5. The SQL 记忆模块 shall 确保注入的历史 SQL 符合 DBAgent 的只读安全约束（不包含 INSERT/UPDATE/DELETE/DDL 语句作为示例）。

### Requirement 4: 混合作用域
**Objective:** As a DBAgent 管理员，我希望 SQL 记忆的作用域可以灵活配置为 per-user 隔离或 per-database 共享模式。

#### Acceptance Criteria
1. When 配置为 per-user 模式（默认），the SQL 记忆模块 shall 仅检索和记录当前用户的 SQL 历史，用户间严格隔离。
2. When 配置为 per-database 共享模式，the SQL 记忆模块 shall 允许同一数据库的所有用户共享 SQL 记忆，检索时返回该数据库下所有用户的记录。
3. When 配置为混合模式，the SQL 记忆模块 shall 对标记为"共享"的数据库使用 per-database 作用域，对未标记的数据库使用 per-user 作用域。
4. Where 作用域为 per-database 共享，the SQL 记忆模块 shall 在每条记录中保留原始 user_id，以便追溯来源。
5. The SQL 记忆模块 shall 支持运行时通过配置变更热切换作用域，新作用域对后续检索和记录立即生效。

### Requirement 5: 模式挖掘
**Objective:** As a DBAgent 管理员，我希望从积累的历史 SQL 中自动挖掘查询模式（高频表、高频条件、常见 JOIN），用于改进 NL2SQL 生成的语义规则。

#### Acceptance Criteria
1. When 某数据库的 SQL 记忆积累到 N 条以上（N 可配置，默认 20），the SQL 记忆模块 shall 支持对该数据库进行模式挖掘。
2. The SQL 记忆模块 shall 在模式挖掘中输出：高频查询表名列表（按查询次数降序）、高频 WHERE 条件模式（按出现次数降序）、常见 JOIN 关系（表对 + 出现次数）。
3. The SQL 记忆模块 shall 将挖掘结果以结构化格式输出，可供下游语义规则系统消费。
4. If 模式挖掘请求触发时记忆记录不足 N 条，the SQL 记忆模块 shall 返回提示信息而非空结果。

### Requirement 6: 配置与控制
**Objective:** As a DBAgent 管理员，我希望通过配置开关控制 SQL 记忆模块的启用/禁用和各项参数。

#### Acceptance Criteria
1. Where 配置 `sql_memory_enabled=True`，the DBAgent shall 启用 SQL 记忆的记录、检索、注入全链路。
2. Where 配置 `sql_memory_enabled=False`（默认），the DBAgent shall 完全跳过 SQL 记忆的记录和检索，不影响现有 Agent 流程。
3. The SQL 记忆模块 shall 支持以下可配置参数：检索 top-K 数量（默认 5）、注入 token 预算上限（默认 1500 字符）、单条 SQL 截断长度（默认 2000 字符）、相似度最低阈值（默认 0.0）、模式挖掘触发阈值（默认 20 条）、记忆记录 TTL（默认 90 天）。
4. When SQL 记忆记录超过 TTL，the SQL 记忆模块 shall 在下次写入或定期清理时自动删除过期记录。
5. The SQL 记忆模块 shall 通过统一配置系统管理所有可配置参数，支持环境变量和配置文件覆盖。

### Requirement 7: 可量化评估
**Objective:** As a DBAgent 管理员，我希望通过对比评测模式量 SQL 记忆模块对 Agent SQL 质量和效率的实际影响。

#### Acceptance Criteria
1. The 评测框架 shall 支持 `--compare-sql-memory` 模式，执行两轮完整评测：一轮无记忆（baseline），一轮有记忆（预填充历史 SQL）。
2. When 对比评测完成，the 评测框架 shall 生成对比报告，包含以下 Memory Impact 指标：SQL 正确率变化、find_table 调用次数变化、总 token 消耗变化、Agent 响应延迟变化。
3. The 评测框架 shall 在对比报告中标注每个用例的 Memory Recall Hit 情况（检索到的历史 SQL 是否与当前问题相关）。
4. When SQL 记忆模块的检索结果被注入但 Agent 生成的 SQL 仍然错误，the 评测框架 shall 记录为 Memory Recall Miss，用于诊断检索质量问题。
