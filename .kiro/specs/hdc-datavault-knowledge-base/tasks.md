# 实施计划

## 任务格式

- 采用 2 级层次结构：主任务（1, 2, 3...）和子任务（1.1, 1.2, 2.1...）
- `(P)` 标记表示该任务可与同级任务并行执行
- `_Requirements:` 引用需求 ID（仅数字，逗号分隔）
- `_Boundary:` 声明组件边界（`(P)` 任务必填）
- `_Depends:` 声明跨组显式依赖（仅在依赖不明显的场景使用）

---

- [x] 1. 基础设施：扩展客户端、配置与数据模型
- [x] 1.1 扩展 OpenVikingClient 新增 HDC 所需 API
  - 封装 `find()` 方法：POST `/api/v1/search/find`，支持 query/target_uri/level/tags/limit/score_threshold 参数，返回匹配项列表
  - 封装 `search()` 方法：POST `/api/v1/search/search`，支持 session_id 参数用于意图感知检索
  - 封装 `write()` 方法：POST `/api/v1/content/write`，支持 uri/content/mode 参数，返回写入状态
  - 封装 `set_tags()` 方法：POST `/api/v1/fs/attrs/set_tags`，支持 uri/tags/mode 参数
  - 封装 `mkdir()` 方法：POST `/api/v1/fs/mkdir`，支持 uri/description 参数
  - 封装 `rm()` 方法：DELETE `/api/v1/fs`，支持 uri/recursive 参数
  - 所有方法遵循现有 `_post`/`_get_raw` 模式：自动解包 `{"status":"ok","result":...}`，错误时记录日志不抛出
  - 完成后：`OpenVikingClient` 实例可成功调用 `find("测试", target_uri="viking://resources/hdc/")` 并返回结果或空列表
  - _Requirements: 1.3, 1.4, 2.1, 2.2, 3.3, 4.1_
  - _Boundary: OpenVikingClient_

- [x] 1.2 新增 HDC 配置项到 Settings
  - 在 `app/config.py` 的 `Settings` 类中新增 `hdc_enabled: bool = False` 配置项
  - 新增 `hdc_auto_generate: bool = False` 配置项（控制是否在首次使用数据库时自动触发生成）
  - 在 `app/main.py` 的 lifespan 启动日志中新增 HDC 状态行：`[DBAgent] HDC: {'enabled' if settings.hdc_enabled else 'disabled'}`
  - 完成后：设置 `HDC_ENABLED=true` 环境变量后，启动日志显示 `[DBAgent] HDC: enabled`
  - _Requirements: 5.1_
  - _Boundary: Settings_

- [x] 1.3 创建 HDC 数据模型
  - 在 `app/datavault/models.py` 中定义 Pydantic 数据类：`ColumnRaw`、`TableRaw`、`DatabaseRaw`（采集层）
  - 定义 `ColumnSummary`、`TableDescription`、`TableRelationship`、`DatabaseSummary`（生成层）
  - 定义 `TableDescriptionWithColumns`（生成层聚合，关联表描述与列摘要列表）
  - 定义 `HDCContext`、`TableMatch`（检索层输出）
  - `TableDescription.main_entity` 字段必须包含常见同义词（以 `/` 分隔），如 `"售后/退货/退款/换货"`
  - `TableDescription.table_type` 字段限定为 `Literal["fact", "dimension", "bridge"]`
  - 完成后：`from app.datavault.models import TableDescription` 导入成功，类型校验通过
  - _Requirements: 1.2_
  - _Boundary: HDC Models_

- [x] 2. HDC 生成管线
- [x] 2.1 (P) 构建 SchemaCollector — Schema 元数据采集器
  - 在 `app/datavault/collector.py` 中实现 `SchemaCollector` 类
  - 实现 `collect_database(schema_id)` 方法：调用 `OneDBAClient.execute_sql()` 依次执行 `SHOW TABLE STATUS`（获取表列表+注释）→ 逐表 `DESCRIBE`（获取列结构）→ 逐表 `SELECT * LIMIT 3`（获取采样数据）
  - 单表采集失败时记录错误并继续处理其余表，不中断整体采集
  - 返回 `DatabaseRaw` 对象，包含所有成功采集的表元数据
  - 完成后：对测试数据库调用 `collect_database(142)` 返回 `DatabaseRaw`，`tables` 列表非空，每张表包含 `columns` 和 `sample_rows`
  - _Requirements: 1.1_
  - _Boundary: SchemaCollector_

- [x] 2.2 (P) 构建 HDCUploader — OpenViking 上传器
  - 在 `app/datavault/uploader.py` 中实现 `HDCUploader` 类
  - 实现 `upload_database()` 方法：创建 `viking://resources/hdc/{db}/` 目录结构（`mkdir`），写入 `_INDEX.md`（数据库摘要），逐表写入 `_INDEX.md`（表描述）和 `{column}.md`（列详情），写入 `_relationships/{a}__{b}.md`（关系）
  - 实现 `upload_table()` 方法：单表上传（增量更新时使用）
  - 实现 `set_tags()` 调用：表目录级别设置 `hdc_level:table`、`main_entity:{value}`、`table_type:{value}`、`pk:{value}`
  - 实现 `delete_database()` 和 `delete_table()` 方法：`rm` 递归删除
  - 内容格式遵循 Markdown，第一段包含 `main_entity` 同义词确保 VLM 摘要质量
  - 完成后：调用 `upload_database("test_db", ...)` 后，`ov ls viking://resources/hdc/test_db/` 可见完整目录结构，且各表目录下存在 `.abstract.md`（L0）和 `.overview.md`（L1）摘要文件
  - _Requirements: 1.3, 1.4, 3.3_
  - _Boundary: HDCUploader_

- [x] 2.3 构建 HDCGenerator — 列摘要与表描述生成
  - 在 `app/datavault/generator.py` 中实现 `HDCGenerator` 类
  - 实现列摘要生成逻辑：垂直分区策略，每 6 列一组，`asyncio.gather` 并行调用 LLM；prompt 包含表名、列信息（名/类型/键/注释）、采样数据；LLM 输出结构化 JSON（column_name + description）
  - 实现表描述生成逻辑：基于列摘要，每表一次 LLM 调用，prompt 要求输出 `main_entity`（含 `/` 分隔的同义词）、`table_type`（fact/dimension/bridge）、`primary_key`、`key_attributes`（top 5）、`description`
  - 单表 LLM 调用失败时记录错误并跳过，继续处理其余表
  - 完成后：调用 `_generate_column_summaries(table)` 返回正确的列摘要列表；调用 `_generate_table_description(table, summaries)` 返回的 `TableDescription` 中 `main_entity` 包含同义词、`table_type` 为 fact/dimension/bridge 之一
  - _Requirements: 1.2, 1.5, 1.7_
  - _Depends: 2.1, 2.2_
  - _Boundary: HDCGenerator_

- [x] 2.4 构建 HDCGenerator — 表关系与数据库摘要生成
  - 实现表关系两阶段检测：阶段 1 — OpenViking `find` 粗筛候选表（每表 top 5）；阶段 2 — LLM 细筛确认引用关系（join_columns、relationship_type、confidence）
  - 实现数据库摘要生成：基于影响力最大化原则（关系数最多的 Top 5 表 → LLM 推断 `representative_entities`、`domain_hint`、`description`）
  - 实现 `generate()` 主方法：签名 `generate(schema_id, database_name, tables=None, progress_callback=None)`，编排 `collect_database → generate_column_summaries → generate_table_descriptions → upload_tables → generate_relationships → generate_database_summary → upload_cascade` 全流程<br/>
  （表先上传到 OpenViking，使关系检测阶段的 `find()` API 可用，首次生成和增量更新共享同一路径）
  - `progress_callback` 在每个阶段边界调用 `progress_callback(step_name, info_dict)` 用于实时进度上报
  - 返回生成统计字典：`{"status", "tables_total", "tables_succeeded", "columns", "relationships", "duration_seconds", "errors", "mode", "requested_tables"}`；`mode` 为 `"full"` 或 `"partial"`，`requested_tables` 仅在 partial 模式下存在
  - 完成后：调用 `generate(142, "dwd_trade")` 返回统计字典，`status` 为 `"completed"` 或 `"partial"`，OpenViking 中可见完整 HDC 数据
  - _Requirements: 1.2, 1.6, 1.8, 1.10_
  - _Depends: 2.3_
  - _Boundary: HDCGenerator_

- [x] 3. HDC 在线检索
- [x] 3.1 构建 HDCRetriever — 检索与上下文格式化
  - 在 `app/datavault/retriever.py` 中实现 `HDCRetriever` 类
  - 实现 `retrieve(user_input, schema_id, database_name)` 方法：
    - 阶段 1：`find(query=user_input, target_uri=".../hdc/{db}/_tables", tags=["hdc_level:table"], level=[0,1], limit=10)` 检索匹配表
    - 阶段 2：对 top 5 表，`find(query=user_input, target_uri=".../hdc/{db}/_tables/{table}", level=[2], limit=6)` 检索相关列
  - 实现 `format_context(hdc)` 方法：将 `HDCContext` 格式化为 Markdown 段落字符串，数据库摘要 + 匹配表（含 main_entity、description、相关列），每表最多 6 列。5.1 仅在此字符串外层包装 `[数据底座 — 数据库知识]` 标签
  - 实现降级逻辑：OpenViking `find` 调用包裹在 `try/except` 中，异常时记录日志警告并返回 `None`；检索超时（配置阈值）后终止并返回 `None`
  - 完成后：对已有 HDC 的数据库调用 `retrieve("退款金额", "dwd_trade")` 返回 `HDCContext`，`matched_tables` 包含 `after_sale_order`；OpenViking 不可用时返回 `None` 且日志有警告
  - _Requirements: 2.1, 2.2, 2.6, 4.1, 4.2, 4.3, 4.4_
  - _Boundary: HDCRetriever_

- [x] 4. HDC 增量更新
- [x] 4.1 构建 HDCUpdater — Schema 变更检测与增量重算
  - 在 `app/datavault/updater.py` 中实现 `HDCUpdater` 类
  - 实现 `_compute_columns_hash(columns)` 方法：将列名+类型拼接后做 hash，用于快速对比
  - 实现 `check_and_update(schema_id, database_name)` 方法：
    - 采集当前 schema → 计算每表列签名 hash
    - 从 OpenViking 读取已存储的表列表和 hash（通过 `ls` 或 `find`）
    - 对比识别新增表、变更表（hash 不同）、删除表
    - 新增/变更表：调用 `HDCGenerator.generate_table()` 重算
    - 删除表：调用 `HDCUploader.delete_table()` 清理
    - 如有表变更：级联重算表关系和数据库摘要
    - 无变更：直接返回 `{"changed": false}`
  - 完成后：修改测试数据库的某张表（新增一列），调用 `check_and_update()` 返回 `{"changed": true, "new": 0, "changed": 1, "deleted": 0}`，该表的 HDC 已更新
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Depends: 2.4_
  - _Boundary: HDCUpdater_

- [x] 5. 系统集成
- [x] 5.1 集成 HDC 检索到 build_context()
  - 在 `app/agent/context.py` 的 `build_context()` 中新增第 7 段上下文
  - 从 `session_state.get("_hdc_context")` 读取 `HDCContext` 对象
  - 如果非空，组装 `[数据底座 — 数据库知识]` 段落：数据库摘要 + 匹配表列表（表名、核心实体、描述、相关列）
  - 如果为空或 `None`，跳过不添加空段落（与现有 6 段行为一致）
  - HDC 段落与长期记忆段落、操作记忆段落并列，使用 `[数据底座]` 标签明确区分
  - 完成后：session_state 中 `_hdc_context` 有值时，`build_context()` 返回字符串包含 `[数据底座 — 数据库知识]` 段落
  - _Requirements: 2.1, 2.3, 2.4, 2.5_
  - _Boundary: Context Builder_

- [x] 5.2 在 API 路由中接入 HDC 检索
  - 在 `app/api/routes.py` 的聊天端点中，`build_context()` 调用前执行 HDC 检索
  - 仅当 `hdc_enabled=True` 且 `session_state` 中有 `selected_database` 时触发检索
  - 检索结果写入 `session_state["_hdc_context"]`
  - HDC 检索失败（`HDCRetriever.retrieve()` 返回 `None`）时静默降级，不阻塞聊天
  - 完成后：`hdc_enabled=True` 且有选定数据库时，聊天请求的 `session_state["_hdc_context"]` 被填充
  - _Requirements: 2.1, 4.1_
  - _Depends: 5.1_
  - _Boundary: API Routes_

- [x] 5.3 创建 HDC 管理 API 端点
  - 在 `app/api/routes.py` 中新增 HDC 管理路由
  - `POST /api/hdc/generate`：接收 `{"schema_id": int, "database_name": str, "tables": ["t1","t2"] | null}`，校验 `hdc_enabled`，启动异步生成任务，返回 `{"task_id": str, "status": "started"}`；`tables` 为可选字段，不传时全库生成
  - `GET /api/hdc/status/{database_name}`：查询指定数据库的 HDC 状态（是否存在、生成时间、表数量、最近更新时间）
  - `GET /api/hdc/tasks/{task_id}`：查询生成任务进度（phase、tables_done、tables_total、errors）
  - `DELETE /api/hdc/{database_name}`：删除指定数据库的全部 HDC 数据
  - 未启用时（`hdc_enabled=False`）所有端点返回 503
  - 任务状态使用内存 dict 存储（`{task_id: TaskStatus}`）
  - 完成后：`curl -X POST /api/hdc/generate -d '{"schema_id":142,"database_name":"dwd_trade"}'` 返回 `{"task_id": "...", "status": "started"}`
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Depends: 2.4, 4.1, 5.4_
  - _Boundary: API Routes_

- [x] 5.4 创建 datavault 模块入口与工厂函数
  - 在 `app/datavault/__init__.py` 中实现 `get_hdc_generator()` 和 `get_hdc_retriever()` 工厂函数
  - `get_hdc_generator()` 组装 `SchemaCollector(onedba_client) + HDCUploader(ov_client) + HDCGenerator(...)` 依赖链
  - `get_hdc_retriever()` 返回 `HDCRetriever(ov_client)` 实例
  - OpenViking 客户端复用现有按请求创建的模式（从 routes.py 传入）
  - 完成后：`from app.datavault import get_hdc_retriever` 导入成功
  - _Requirements: 1.1, 2.1_
  - _Depends: 2.1, 2.2, 2.4, 3.1_
  - _Boundary: datavault Module_

- [x] 6. 测试与验证
- [x] 6.1 编写 datavault 模块单元测试
  - `test_collector.py`：mock OneDBAClient，验证 `collect_database()` 返回正确的 `DatabaseRaw` 结构；验证单表失败不中断
  - `test_generator.py`：mock LLM 和 OpenVikingClient，验证列摘要分组逻辑（6 列一组）；验证表描述输出解析；验证 `generate()` 返回正确的统计字典
  - `test_retriever.py`：mock OpenVikingClient，验证降级路径返回 `None`；验证 `format_context()` 输出格式
  - `test_updater.py`：验证 `_compute_columns_hash()` 相同列相同 hash、变更列不同 hash；验证变更检测逻辑
  - 完成后：`pytest tests/datavault/ -v` 全部通过
  - _Requirements: 1.1, 1.2, 1.5, 2.2, 3.1, 4.1_
  - _Boundary: Tests_

- [x] 6.2 编写 HDC 集成测试
  - 测试 HDC 检索 → `build_context()` 注入全链路：mock OpenViking `find` 返回匹配结果，验证最终上下文字符串包含 `[数据底座]` 段落
  - 测试降级全链路：mock OpenViking 抛出异常，验证 `build_context()` 不包含 HDC 段落，聊天正常响应
  - 测试管理 API 端点：验证 POST generate 返回 task_id、GET status 返回数据库状态、DELETE 返回成功
  - 测试 `hdc_enabled=False` 时管理 API 返回 503、聊天端点不触发 HDC 检索
  - 完成后：`pytest tests/ -k "hdc" -v` 全部通过
  - _Requirements: 2.1, 2.3, 4.1, 5.1, 5.2_
  - _Depends: 5.2, 5.3_
  - _Boundary: Tests_

- [x] 6.3 编写 HDC 端到端测试
  - 测试完整流程：管理员触发生成 → Agent 对话中 HDC 上下文注入 → 验证 Agent 减少 `describe_table` 调用
  - 测试增量更新流程：修改数据库 schema → 触发增量更新 → 验证仅变更表被重算
  - 测试降级流程：停止 OpenViking → Agent 正常对话（无 HDC 段落）→ 恢复 OpenViking → Agent 对话恢复 HDC 段落
  - 完成后：手动执行 E2E 测试脚本，所有场景通过
  - _Requirements: 1.2, 2.1, 3.2, 4.3_
  - _Depends: 6.2_
  - _Boundary: Tests_

- [x] 7. HDC 生成范围限制 — 部分表模式
- [x] 7.1 (P) SchemaCollector 新增表名过滤
  - 修改 `SchemaCollector.collect_database()` 方法，新增可选参数 `tables: list[str] | None = None`
  - `tables=None`（默认）时保持现有全库采集行为不变
  - `tables=["a","b"]` 时在 `SHOW TABLE STATUS` 结果中仅保留匹配的表名，跳过无关表的 `DESCRIBE` 和 `SELECT * LIMIT 3` 调用
  - 指定的表名在数据库中不存在时，记录 `logger.warning` 并跳过，继续处理其余合法表名
  - 完成后：调用 `collect_database(142, tables=["user_info", "not_exist"])` 仅返回 `user_info` 的 `TableRaw`，日志中有 `not_exist` 的警告
  - _Requirements: 1.7, 1.9_
  - _Depends: 2.1_
  - _Boundary: SchemaCollector_

- [x] 7.2 (P) HDCGenerator.generate() 新增 tables 参数
  - 修改 `HDCGenerator.generate()` 方法，新增可选参数 `tables: list[str] | None = None`
  - `tables=None` 时保持现有全库生成行为不变（向后兼容）
  - `tables=["a","b"]` 时透传到 `collect_database(tables=...)`，仅对指定表执行采集和后续生成
  - 部分表模式下仍执行表关系生成（仅检测指定表之间的关联）和数据库摘要生成（仅基于指定表编写）
  - 返回统计字典新增 `mode: "full" | "partial"` 字段，partial 模式额外附带 `requested_tables` 列表
  - 完成后：调用 `generate(142, "dwd_trade", tables=["user_info"])` 返回 `{"status":"completed","tables_total":1,"mode":"partial","requested_tables":["user_info"],...}`，仅 `user_info` 的 HDC 出现在 OpenViking
  - _Requirements: 1.7, 1.8, 1.10_
  - _Depends: 2.3, 2.4, 7.1_
  - _Boundary: HDCGenerator_

- [x] 7.3 集成测试 — 部分表模式 + 增量更新兼容性
  - 验证部分表模式生成后增量更新正常工作：首先生成 2 张表的 HDC → 增量更新检测到其余表为"待新增" → 自动扩展覆盖范围
  - 验证全库模式增量更新行为不变（`check_and_update()` 无改动，仅验证兼容性）
  - 验证部分表模式生成的 HDC 在 `GET /api/hdc/status/{db}` 中正确反映 `"table_count": 2` 和部分生成状态
  - 完成后：部分表生成的 HDC 经过增量更新后，表数量增加至全库，hash 存储正确
  - _Requirements: 1.11, 1.12_
  - _Depends: 7.2, 4.1_
  - _Boundary: Tests, HDCUpdater_

- [x] 7.4 CLI 支持 — demo_hdc_generate.py 新增 --tables 参数
  - 在 `tests/datavault/demo_hdc_generate.py` 的 argparse 中新增 `--tables` 参数，接受逗号分隔的表名列表
  - 传递到 `generate(schema_id, database_name, tables=[...])`
  - 完成后：`python demo_hdc_generate.py 142 dwd_trade --tables user_info,order_main` 仅对 2 张表生成 HDC
  - _Requirements: 1.7, 1.10_
  - _Depends: 7.2_
  - _Boundary: CLI Script_
