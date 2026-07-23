# 需求文档

## 项目描述

DBAgent 的 NL2SQL 查询助手在面对陌生数据库时，需要反复调用 `find_table` → `describe_table` 工具来理解 schema 含义，每轮对话额外消耗 1-2 次 LLM 往返（2-5 秒延迟）。用户用自然语言描述查询需求（如"退货率"、"GMV"），但表名和列名是机器命名（如 `after_sale_order`、`total_amount`），存在语义鸿沟。

本项目采用 TiInsight 论文的 HDC（层次化数据上下文）方法论，结合 OpenViking 作为存储和检索基础设施，为 OneDBA 上的数据库构建结构化业务语义知识库。HDC 在对话开始时注入 Agent 上下文，使 LLM 能直接理解表结构和字段含义，减少盲搜轮次，提升 Agent 回答速度。

**核心能力**：
- 离线 HDC 生成管线：从 OneDBA 采集 schema → LLM 自底向上生成四层描述（列→表→关系→库）
- 在线 HDC 检索：OpenViking `find` API 向量检索 + tags 精确过滤，`build_context()` 注入
- 增量更新：列签名 hash 对比，仅重算 schema 变更的表

## 边界上下文

- **范围内**：HDC 知识库的生成（离线管线，支持全库和部分表两种模式）、检索（在线路径）、增量更新（后台任务）、静默降级、管理操作
- **范围外**：不替换 OpenViking 语义记忆、不替换现有 `find_table`/`describe_table` 工具、不实现自定义 embedding 或向量存储
- **相邻预期**：OpenViking 提供向量检索和存储能力；OneDBA 平台提供 schema 采集能力；现有 `build_context()` 已注入 OpenViking 语义记忆和操作记忆，HDC 上下文段落与之并列

## 需求

### 需求 1：HDC 知识库生成

**目标**：作为 DBA 管理员，我希望触发一次 HDC 生成操作，系统自动从 OneDBA 采集指定数据库的 schema 元数据，通过 LLM 生成四层业务语义描述，并上传至 OpenViking 资源目录，以便后续对话中检索使用。

#### 验收标准

1. When 管理员触发 HDC 生成并指定数据库（schema_id + database_name），the DBAgent HDC 子系统 shall 从 OneDBA 采集该数据库的全部表名、列结构（DESCRIBE）和采样数据（每表 LIMIT 3），不依赖人工提供元数据
2. When schema 采集完成后，the DBAgent HDC 子系统 shall 按自底向上顺序生成四层描述：列摘要（分组并行，每组 5-8 列一次 LLM 调用）→ 表描述（含 main_entity 同义词、table_type、key_attributes）→ 表关系（两阶段检测：向量粗筛 → LLM 细筛）→ 数据库摘要（基于影响力最大化原则）
3. When 表描述生成完成后，the DBAgent HDC 子系统 shall 将结构化元数据（main_entity、table_type、primary_key）作为 tags 写入 OpenViking 对应目录，确保 tags 内容与 `_INDEX.md` 文件内容一致
4. When 所有内容上传到 OpenViking 后，the DBAgent HDC 子系统 shall 触发 SemanticProcessor 处理，使 OpenViking 自动生成 L0（.abstract）和 L1（.overview）摘要
5. When 生成过程中某张表的 LLM 调用失败，the DBAgent HDC 子系统 shall 记录该表错误并继续处理其余表，不中断整个数据库的生成流程
6. When 生成完成后，the DBAgent HDC 子系统 shall 返回生成统计（成功表数、失败表数、列数、关系数、耗时）
7. Where 管理员在触发生成时指定了目标表名列表，the DBAgent HDC 子系统 shall 仅对指定表执行 schema 采集、列摘要生成、表描述生成和上传操作，跳过未指定表
8. Where 管理员指定了目标表名列表（即部分表生成模式），the DBAgent HDC 子系统 shall 基于已生成的表完成表关系生成和数据库摘要生成步骤（关系仅检测指定表之间的关联，数据库摘要仅基于指定表的核心实体和业务域编写），返回的生成统计中注明"部分生成"状态及涉及的表名列表
9. If 管理员指定的表名在目标数据库中不存在，the DBAgent HDC 子系统 shall 记录警告并跳过该表名，继续处理其余合法表名，不中断整体流程
10. Where 管理员未指定目标表名列表（默认行为），the DBAgent HDC 子系统 shall 采集全部表并生成完整四层 HDC 知识库，保持现有行为不变
11. Where 管理员使用部分表模式生成 HDC 后，the DBAgent HDC 子系统 shall 确保后续增量更新操作可正常执行——增量更新应能检测到未生成表的新增/变更，并自动扩展知识库覆盖范围
12. When 增量更新在部分表模式下生成的 HDC 知识库上执行，the DBAgent HDC 子系统 shall 仅对比已生成表的列签名 hash，未生成的表视为"待新增"并纳入更新范围

### 需求 2：HDC 在线检索与上下文注入

**目标**：作为 Agent，我希望在对话开始时，系统能根据用户输入和当前选定的数据库，从 HDC 知识库中检索匹配的表描述和列信息，并注入到 Agent 上下文中，以便直接理解表结构语义，减少 `describe_table` 工具调用。

#### 验收标准

1. When 用户发起对话且已选定数据库，the DBAgent HDC 子系统 shall 在 `build_context()` 中注入该数据库的 HDC 数据库摘要（含核心实体、业务域、表数量）
2. When 用户输入包含与 HDC 表描述或列描述语义相关的关键词，the DBAgent HDC 子系统 shall 通过 OpenViking `find` API 检索匹配的表（使用 tags 精确过滤 + 向量语义检索，双路召回），并将匹配结果注入 Agent 上下文
3. When 用户输入无法匹配任何 HDC 表描述，the DBAgent HDC 子系统 shall 返回空结果，不在上下文中添加空段落，Agent 照常使用 `find_table` 工具探索
4. When 用户未选定数据库，the DBAgent HDC 子系统 shall 跳过 HDC 检索，不阻塞正常对话流程
5. The DBAgent HDC 子系统 shall 将 HDC 上下文段落与 OpenViking 语义记忆段落、操作记忆段落并列展示，使用 `[数据底座]` 标签明确区分
6. When HDC 检索到的表描述包含列信息，the DBAgent HDC 子系统 shall 仅注入与用户问题相关的列（最多每表 6 列），而非全部列，避免上下文膨胀

### 需求 3：HDC 增量更新

**目标**：作为 DBA 管理员，我希望当数据库 schema 发生变更时，系统能自动检测变更范围，仅重算受影响的部分，而非重建整个知识库，以控制 LLM 调用成本和更新时间。

#### 验收标准

1. When HDC 增量更新触发（定时任务或手动），the DBAgent HDC 子系统 shall 对比当前 schema 的列签名 hash（列名+类型）与 OpenViking 中存储的 hash，识别新增、变更和删除的表
2. When 检测到表新增或表结构变更，the DBAgent HDC 子系统 shall 仅对该表重新执行"列摘要 → 表描述"生成流程，并更新 OpenViking 中的对应文件和 tags
3. When 检测到表删除，the DBAgent HDC 子系统 shall 从 OpenViking 中移除该表的 HDC 目录
4. When 表的增删改影响表关系或数据库摘要，the DBAgent HDC 子系统 shall 在变更表处理完成后，重新计算受影响的关系和数据库摘要
5. When 未检测到任何 schema 变更，the DBAgent HDC 子系统 shall 不执行任何 LLM 调用，直接返回"无变更"

### 需求 4：静默降级

**目标**：作为系统运维者，我希望当 OpenViking 服务不可用时，HDC 功能静默降级，不阻塞 Agent 的正常对话流程，用户感知不到异常。

#### 验收标准

1. When OpenViking 服务不可达或 `find` API 返回错误，the DBAgent HDC 子系统 shall 在日志中记录警告，不向 Agent 上下文注入任何 HDC 内容，Agent 回退到现有 `find_table` + `describe_table` 工具调用流程
2. When HDC 检索超时（超过配置的阈值），the DBAgent HDC 子系统 shall 终止检索并降级，不阻塞对话启动
3. When OpenViking 服务在降级后恢复，the DBAgent HDC 子系统 shall 在下一次对话中自动恢复 HDC 检索，无需人工干预
4. The DBAgent HDC 子系统 shall 在降级期间不向用户展示任何错误信息或异常提示，确保用户无感知

### 需求 5：管理操作

**目标**：作为 DBA 管理员，我希望通过 API 或 CLI 管理 HDC 知识库的生命周期，包括触发生成、查看状态和删除指定数据库的 HDC 数据。

#### 验收标准

1. When 管理员调用 HDC 生成 API 并指定 schema_id 和 database_name，the DBAgent HDC 子系统 shall 启动异步生成任务并返回任务标识，不阻塞 API 响应
2. When 管理员查询 HDC 生成任务状态，the DBAgent HDC 子系统 shall 返回当前进度（采集/生成列/生成表/生成关系/上传中/已完成/失败）和已处理的表数量
3. When 管理员调用 HDC 删除 API 并指定 database_name，the DBAgent HDC 子系统 shall 从 OpenViking 中移除该数据库的全部 HDC 目录和文件
4. When 管理员查询指定数据库的 HDC 状态，the DBAgent HDC 子系统 shall 返回该数据库的 HDC 是否存在、生成时间、覆盖的表数量、最近一次更新的时间