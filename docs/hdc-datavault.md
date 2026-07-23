# HDC 数据底座模块

## 概述

HDC（Hierarchical Data Context，层次化数据上下文）是 DBAgent 的数据库语义知识底座。通过离线 LLM 管线将 OneDBA 数据库 schema 转化为四层业务语义描述（列→表→关系→库），存储于 OpenViking 资源目录，在线检索时注入 Agent 上下文，减少 Agent 面对陌生数据库时的 `find_table → describe_table` 盲搜往返。

**核心能力**：

- **离线生成**：OneDBA 采集 schema → LLM 自底向上生成四层描述
- **在线检索**：OpenViking `find` API 向量检索 + tags 精确过滤，注入 Agent 上下文
- **增量更新**：列签名 hash 对比，仅重算 schema 变更的表
- **范围限制**：支持全库和指定表两种生成/更新模式

## 架构

```
app/datavault/                   # HDC 数据底座模块（3,558 行）
├── __init__.py          (53)    # 模块入口，工厂函数
├── models.py            (141)   # 数据模型（ColumnRaw/TableDescription/HDCContext 等）
├── collector.py         (210)   # Schema 采集器，从 OneDBA 采集元数据
├── generator.py         (1,486) # HDC 生成管线编排（四层 LLM 生成）
├── uploader.py          (441)   # OpenViking 上传器，写文件 + set_tags + 等 embedding
├── retriever.py         (520)   # HDC 检索封装 + 上下文格式化
└── updater.py           (707)   # 增量更新检测与执行
```

### 各模块职责

| 模块 | 职责 | 关键方法 |
|------|------|---------|
| **SchemaCollector** | 从 OneDBA 采集原始 schema（`SHOW TABLE STATUS` → `DESCRIBE` → `SELECT * LIMIT 3`） | `collect_database(schema_id, tables=None)` |
| **HDCGenerator** | 编排四层 LLM 生成管线：列摘要 → 表描述 → 表关系 → 数据库摘要 | `generate(schema_id, db_name, tables=None, progress_callback=None)` |
| **HDCUploader** | 写 HDC 内容到 OpenViking 目录，设置结构化 tags，等待 embedding 就绪 | `upload_tables()`, `upload_cascade()`, `wait_for_embedding()` |
| **HDCRetriever** | 两阶段检索（tags+向量 → 列详情），格式化 `[数据底座]` 上下文段落 | `retrieve(user_input, schema_id, db_name)`, `format_context()` |
| **HDCUpdater** | 列签名 hash 对比，识别新增/变更/删除表，增量重算 | `check_and_update(schema_id, db_name, tables=None)` |

## 数据流

### 生成管线

```
OneDBA → SchemaCollector → TableRaw[]
  → HDCGenerator.generate()
    → 列摘要 (LLM, 6列/组并行)
    → 表描述 (LLM, 逐表流式管线)
    → HDCUploader.upload_tables()  → OpenViking
    → 表关系 (2阶段: find粗筛 → LLM细筛)
    → 数据库摘要 (LLM)
    → HDCUploader.upload_cascade() → OpenViking
```

### 在线检索

```
用户输入 → HDCRetriever.retrieve()
  → Stage 1: find(tags=["hdc_level=table"], level=[0,1]) → 匹配表
  → Stage 2: find(level=[2]) → 相关列（每表 ≤6 列）
  → 读取 _INDEX.md 获取精确元数据
  → 返回 HDCContext → build_context() 注入 Agent
```

## 测试

### 单元测试（32 个用例）

```bash
# 运行全部 HDC 测试
pytest tests/datavault/ -v
```

| 测试文件 | 用例数 | 覆盖范围 |
|---------|--------|---------|
| `test_collector.py` | 11 | SchemaCollector：基本采集、空库、容错、表过滤、不存在表名 |
| `test_retriever_updater.py` | 16 | HDCRetriever（检索/降级/格式化）、HDCUpdater（hash/变更检测）、Models |
| `test_hdc_integration.py` | 5 | build_context 集成：HDC 段落注入/跳过/位置/并列 |

### 端到端验证脚本

| 脚本 | 用途 | 依赖 |
|------|------|------|
| `demo_hdc_generate.py` | 生成 HDC 知识库并验证 | OneDBA + OpenViking + LLM |
| `demo_hdc_update.py` | 验证增量更新的变更检测和重算 | OneDBA + OpenViking + LLM |
| `demo_hdc_compare.py` | 对比实验：有/无 HDC 的 Agent 表现差异 | OneDBA + OpenViking + LLM |
| `demo_hdc_e2e.py` | 完整端到端流程（生成→对比→报告） | OneDBA + OpenViking + LLM |
| `demo_hdc.py` | 纯模拟演示（无需外部服务） | 无 |
| `hdc_debug.py` | 调试 HDC prompt 和检索结果 | OpenViking |

## 使用说明

### 0. 前置条件

- OpenViking Server 运行在 `http://localhost:1933`
- OneDBA 可访问
- LLM 可访问（通过 `Settings.llm_base_url` / `Settings.llm_model` 配置）

### 1. 生成 HDC 知识库

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent

# --- 基本用法 ---

# 全库生成（默认）
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs

# 详细日志
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs -v

# --- 部分表模式（范围限制） ---

# 仅生成指定表
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs --tables user_info,order_main

# 部分表 + 详细日志
python tests/datavault/demo_hdc_generate.py 24223568 dw_onedba_cs --tables user_info,order_main -v
```

**参数说明**：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `schema_id` | 是 | — | OneDBA schema ID |
| `database_name` | 是 | — | 数据库名称 |
| `-v, --verbose` | 否 | `false` | 输出详细的中间日志 |
| `--tables` | 否 | `None` | 逗号分隔的表名列表，不指定则全库生成 |

**输出**：脚本执行三个阶段——生成 → 持久化验证 → 检索验证，全部通过则 HDC 知识库就绪。

### 2. 增量更新

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent

# --- 基本用法 ---

# 检测变更（无变更时不执行任何 LLM 调用）
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs

# 详细日志
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs -v

# --- 过滤模式（仅检测指定表） ---

# 仅检测指定表的变更
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs --tables user_info,order_main

# --- 控制模式 ---

# 仅检测变更，不执行更新
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs --dry-run

# 强制执行更新（即使无变更也重跑关系和摘要）
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs --force-update

# 仅重建关系+数据库摘要（不重跑列摘要/表描述）
python tests/datavault/demo_hdc_update.py 24223568 dw_onedba_cs --rebuild
```

**参数说明**：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `schema_id` | 是 | — | OneDBA schema ID |
| `database_name` | 是 | — | 数据库名称 |
| `-v, --verbose` | 否 | `false` | 输出详细日志 |
| `--tables` | 否 | `None` | 仅检测指定表的变更 |
| `--dry-run` | 否 | `false` | 仅检测变更，不执行更新 |
| `--force-update` | 否 | `false` | 强制执行增量更新 |
| `--rebuild` | 否 | `false` | 强制重建关系+数据库摘要 |

**增量更新流程**：

```
1. 从 OneDBA 采集当前 schema → 计算列签名 hash
2. 从 OpenViking 读取已存储的表列表和 hash
3. 对比识别：新增表 / 变更表（hash 不同）/ 删除表
4. 无变更 → 返回 {"changed": false}（零 LLM 调用）
5. 有变更 → 重算受影响表 → 级联更新关系和摘要
```

### 3. 对比实验

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent

# HDC 对比实验（需先生成 HDC 知识库）
python tests/datavault/demo_hdc_compare.py 24223568 dw_onedba_cs

# 完整端到端（自动生成 + 对比 + 报告）
python tests/datavault/demo_hdc_e2e.py 24223568 dw_onedba_cs
```

### 4. 纯模拟演示（无需外部服务）

```bash
cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
python tests/datavault/demo_hdc.py
```

## 配置项

HDC 相关配置在 `app/config.py` 的 `Settings` 中：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `hdc_enabled` | `bool` | `False` | HDC 功能总开关 |
| `hdc_auto_generate` | `bool` | `False` | 首次使用数据库时是否自动触发生成 |
| `hdc_semantic_timeout` | `float` | `300.0` | write 时的 SemanticProcessor 超时秒数（已降为内联 60s） |

通过环境变量设置：

```bash
export HDC_ENABLED=true
```

## OpenViking 存储结构

```
viking://resources/hdc/{schemaId}/{db}/
├── _INDEX.md                              # 数据库摘要
├── _tables/
│   ├── _INDEX.md                          # 表汇总
│   ├── {table_name}/
│   │   ├── _INDEX.md                      # 表描述（L2）
│   │   ├── {column}.md                    # 列描述（L2）
│   │   ├── .abstract.md                   # L0 摘要（VLM 自动生成）
│   │   └── .overview.md                   # L1 概览（VLM 自动生成）
│   └── ...
└── _relationships/
    ├── {src}__{tgt}.md                    # 表关系
    └── ...
```

**Tags**（表目录级别）：`hdc_level=table`, `main_entity={value}`, `table_type={value}`, `pk={value}`

## 降级策略

- OpenViking 不可用 → 静默降级，日志警告，Agent 回退到 `find_table` + `describe_table`
- HDC 检索无匹配 → 不注入空段落，Agent 正常探索
- LLM 生成失败（单表）→ 记录错误，继续处理其余表
- embedding 未就绪 → retriever 自带 fs/ls 文件系统 fallback

## 注意事项

1. **Embedding 等待**：`upload_table()` 在 `write(wait=True, timeout=60s)` 后还通过 `wait_for_embedding()` 轮询确认 embedding 就绪。如果检索阶段仍返回空，OpenViking 后台 embedding 可能还在处理中，稍等后重试。
2. **VLM 超时**：`write(wait=True, timeout=60s)` 只等 embedding（~2-5s），VLM 生成的 L0/L1 摘要在服务端后台异步完成。服务端日志中的 VLM 超时警告不影响检索功能。
3. **部分表模式**：使用 `--tables` 生成的 HDC 知识库仍然包含关系和摘要（基于已生成表的子集）。后续增量更新会自动将未生成的表识别为"待新增"。
4. **增量更新兼容性**：`check_and_update()` 不假设全库覆盖——未在 OpenViking 中出现的表均被视为"待新增"。
