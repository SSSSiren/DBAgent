# Brief: hdc-datavault-knowledge-base

## Problem
DBAgent 的 NL2SQL 查询助手在面对陌生数据库时，需要反复调用 `find_table` → `describe_table` 工具来理解 schema 含义，每轮对话额外消耗 1-2 次 LLM 往返（2-5 秒延迟）。用户用自然语言描述查询需求（如"退货率"、"GMV"），但表名和列名是机器命名（如 `after_sale_order`、`total_amount`），存在语义鸿沟。现有 OpenViking 语义记忆提供用户画像和偏好，但无法提供数据库 schema 的业务语义理解。

## Current State
- DBAgent 已有 NL2SQL 流水线、数据库发现工具（`find_table`/`describe_table`）、OpenViking 长期记忆集成
- `build_context()` 已注入 OpenViking 语义记忆和操作记忆（`agent-memory-store` spec）
- OpenViking 提供 `find`/`search` API（向量检索 + 目录递归 + IntentAnalyzer）和 `write`/`add_resource` API（内容写入 + SemanticProcessor 自动 L0/L1）
- 缺少：对数据库 schema 的结构化业务语义描述，Agent 每次都需要从零开始理解表结构

## Desired Outcome
1. DBAgent 在对话开始时，`build_context()` 能注入当前数据库的 HDC 摘要（数据库画像 + 匹配的表描述 + 相关列信息）
2. Agent 在上下文中已有表语义的情况下，直接生成 SQL，减少 1-2 轮 tool calling 往返
3. HDC 知识库支持增量更新：schema 变更时仅重算受影响的表，不重建整个知识库
4. OpenViking 不可用时，HDC 检索静默降级，Agent 回退到现有 `find_table` + `describe_table` 流程

## Approach
**方案 A：全自动生成 + OpenViking 原生检索**

采用 TiInsight 论文的 HDC（层次化数据上下文）方法论，四层自底向上生成：
- **列摘要**：LLM 分组并行生成每列的业务描述（垂直分区策略，每 6 列一组）
- **表描述**：LLM 推断 main_entity（含同义词）、table_type（fact/dimension/bridge）、key_attributes
- **表关系**：两阶段检测（向量粗筛 → LLM 细筛），O(n²)→O(n)
- **数据库摘要**：影响力最大化（关系数最多的 Top N 表 → LLM 推断实体）

存储于 OpenViking `viking://resources/hdc/` 资源目录：
- 库=目录、表=子目录、列=`.md` 文件
- 结构化元数据（main_entity、table_type、pk）打入 tags 做精确检索
- OpenViking SemanticProcessor 自动生成 L0/L1 摘要

检索使用 OpenViking `find` API：tags 精确过滤 + 向量语义检索，双路召回。`build_context()` 中注入 HDC 上下文段落。

增量更新：列签名 hash 对比 → 仅重算变更的表。

## Scope
- **In**:
  - `app/datavault/` 模块：HDC 生成管线（generator）+ 检索封装（retriever）+ 数据模型（models）
  - `OpenVikingClient` 扩展：`find`/`search`/`write` API 封装
  - `build_context()` 新增 HDC 上下文段落
  - 增量更新：列签名 hash 对比 + 变更检测
  - HDC 生成 CLI 或 API 端点（管理员触发）
  - 静默降级：OpenViking 不可用时不阻塞 Agent
- **Out**:
  - 不替换 OpenViking 语义记忆（`retrieve_memories`）
  - 不替换现有 `find_table`/`describe_table` 工具（HDC 是补充，不是替代）
  - 不实现自定义 embedding 模型（复用 OpenViking 配置）
  - 不实现自定义向量存储（复用 OpenViking 向量后端）
  - 不做 HDC 数据的跨用户共享（每个数据库的 HDC 是全局的，但检索在用户上下文中）

## Boundary Candidates
- **HDC 生成**：schema 采集 + LLM 生成 + OpenViking 上传（离线管线）
- **HDC 检索**：OpenViking find API 调用 + 上下文格式化 + build_context 注入（在线路径）
- **HDC 更新**：schema 变更检测 + 增量重算（后台任务）

## Out of Boundary
- 不做 SQL 生成质量的自动评估（属于 NL2SQL 流水线的范围）
- 不做 HDC 内容的可视化展示（属于前端范围）
- 不做多用户 HDC 编辑和协作
- 不做历史版本的 HDC 回滚（利用 OpenViking 的 git snapshot 能力即可，不需要额外开发）

## Upstream / Downstream
- **Upstream**:
  - OpenViking 服务（`find`/`search`/`write`/`add_resource` API）
  - OneDBA 平台（schema 采集：`SHOW TABLE STATUS` + `DESCRIBE` + `SELECT * LIMIT 3`）
  - LLM 服务（HDC 生成时的描述生成，复用项目已有 LLM 配置）
- **Downstream**:
  - NL2SQL 流水线可利用 HDC 表关系自动推导 JOIN 路径
  - `find_table` 工具可利用 HDC 表描述做语义匹配（升级关键词搜索为语义搜索）
  - 未来可能的"数据目录"产品功能

## Existing Spec Touchpoints
- **Extends**: `agent-memory-store` — HDC 上下文段落与操作记忆段落并列注入 `build_context()`
- **Adjacent**: `nl2sql-query-assistant` — HDC 提升 schema linking 准确率，但不修改 NL2SQL 流水线本身
- **Adjacent**: `storage-abstraction-layer` — 不修改 `StorageBackend` 协议，HDC 使用独立的 OpenViking 存储路径

## Constraints
- OpenViking 服务必须可用（不可用时静默降级）
- HDC 生成的 LLM 成本可控（首次批量生成 ~100 库 × 50 表 = ~$15-30，增量更新成本极低）
- 目录结构 `viking://resources/hdc/{db}/_tables/{table}/{column}.md` 不与 OpenViking 自动生成的 `.abstract.md`/`.overview.md` 冲突
- HDC 生成不阻塞 Agent 正常服务（后台异步执行）
- 遵循项目现有架构模式：Protocol 驱动的可插拔设计、工厂 + 进程级单例、try/except 静默降级