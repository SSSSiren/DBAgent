# Gap Analysis: hdc-datavault-knowledge-base

## 1. Current State

### 1.1 Requirement-to-Asset Map

| Requirement | Existing Assets | Status |
|-------------|----------------|--------|
| 1. HDC 生成 | — | **Missing** — 无 HDC 生成管线 |
| 1.1 Schema 采集 | `OneDBAClient.execute_sql()` 支持 `SHOW TABLE STATUS` / `DESCRIBE` / `SELECT * LIMIT 3` | **Available** — 可直接复用 |
| 1.2 LLM 生成 | `app/agent/runner.py:_get_llm_client()` 提供 OpenAI 兼容客户端 | **Available** — 需抽取为共用能力 |
| 1.3 OpenViking 上传 | `OpenVikingClient` 仅有 session API（create/add_message/commit） | **Missing** — 需扩展 `write`/`find`/`search`/`set_tags` API |
| 2. HDC 检索 | — | **Missing** — 无 HDC 检索逻辑 |
| 2.1 build_context 注入 | `build_context()` 已有 6 段上下文（摘要/历史/数据库/长期记忆/RAG/偏好） | **Available** — 新增第 7 段 |
| 2.2 向量检索 | OpenViking SDK `find`/`search` API 已存在但未在 DBAgent 中封装 | **Missing** — 需扩展 `OpenVikingClient` |
| 3. 增量更新 | — | **Missing** — 无 schema 变更检测 |
| 4. 静默降级 | `build_context()` 中 `_memories`/`_preferences` 已有 try/except 降级模式 | **Available** — 复用模式 |
| 5. 管理操作 | `app/api/routes.py` 已有 FastAPI 路由 | **Available** — 新增端点 |

### 1.2 Architecture Patterns

| 模式 | 现有实现 | 适用范围 |
|------|---------|---------|
| 配置 | `Settings` (Pydantic) + `@lru_cache` 单例 | 新增 `hdc_enabled` 开关 |
| 工厂 | `get_storage()` / `get_onedba_client()` | 新增 `get_hdc_generator()` |
| 生命周期 | FastAPI `lifespan` async context manager | 可选：HDC 初始化 |
| 降级 | `try/except` + 日志 + 空结果 | 全部 HDC 检索路径 |
| 异步 | 全 async/await | 生成管线：`asyncio.gather` 并行 |
| 单例 | 模块级全局 + 懒初始化 | `OpenVikingClient` 复用（已有） |

### 1.3 Integration Surfaces

```
build_context(session_state) → str
    └── NEW: session_state["_hdc_context"] → HDC 检索结果

run_agent_stream(user_input, session_state) → AsyncIterator
    └── NO CHANGE: 已调用 build_context()

OpenVikingClient (app/knowledge/openviking.py)
    └── EXTEND: find(), search(), write(), set_tags()

OneDBAClient (app/client/onedba.py)
    └── NO CHANGE: 复用 execute_sql()

Settings (app/config.py)
    └── EXTEND: hdc_enabled: bool = False
```

## 2. Gap Analysis

### 2.1 Missing Capabilities

| Capability | Gap | Impact |
|------------|-----|--------|
| `OpenVikingClient` 缺少 `find`/`search`/`write` API | **Medium** — SDK 已有实现，只需封装 HTTP 调用 | 阻塞检索和上传 |
| `app/datavault/` 模块不存在 | **High** — 全新模块，需要 generator + retriever + models | 核心功能 |
| LLM 客户端复用 | **Low** — `runner.py` 中的 `_get_llm_client()` 是模块级私有函数 | 需抽取为共用或直接 import |
| HDC 生成调度 | **Medium** — 生成是异步长任务，需任务状态管理 | 管理 API 需要 |
| Schema 签名 hash | **Low** — 纯函数，无外部依赖 | 增量更新核心 |
| 配置项 | **Low** — 2 个新字段 | 功能开关 |

### 2.2 Constraints

| Constraint | Source | Mitigation |
|------------|--------|------------|
| OpenViking 服务不可用 | 外部依赖 | 静默降级（try/except + 日志） |
| LLM 生成成本 | 150K 列 × 分组 = ~25K 次 LLM 调用 | 首次离线批量生成，增量成本极低 |
| 上下文窗口预算 | HDC 注入 ~1000 tokens | 已有 6 段上下文共 ~6000-8000 tokens，可接受 |
| 目录结构冲突 | `_DERIVED_FILENAMES` 检查 | 文件名不冲突（`_INDEX.md` vs `.abstract.md`） |

### 2.3 Research Needed

- OpenViking `find` API 的实际响应格式和字段（需在实际环境中验证）
- OpenViking `set_tags` API 的 exact signature（SDK 中有 `set_tags` 但参数形式需确认）
- LLM 客户端如何从 `runner.py` 中抽取为共用（从 `_get_llm_client()` 到可被 datavault 模块使用）

## 3. Implementation Approaches

### Option A: Extend Existing Components

**Rationale**: 最小化新文件，最大化复用

**Changes**:
- `app/knowledge/openviking.py` — 扩展 3 个 API（find/search/write）
- `app/agent/context.py` — 新增 HDC 段落（15 行）
- `app/config.py` — 新增 2 个配置项
- `app/api/routes.py` — 新增 3-4 个管理端点
- 新建 `app/datavault/` — generator + retriever + models（~800 行）

**Trade-offs**:
- ✅ 最小化改动面，快速集成
- ✅ 遵循现有模式（标签前缀 `[数据底座]`、`session_state` dict 传递）
- ❌ `OpenVikingClient` 职责膨胀（session + search + write 混合）

**Effort**: M (3-7 days)  **Risk**: Low

### Option B: Separate HDC Service

**Rationale**: 将 HDC 作为独立微服务，通过 HTTP/gRPC 与 DBAgent 通信

**Changes**:
- 新建独立服务 `hdc-service/` — 完整的生成 + 检索 + 更新
- DBAgent 中新增 `HDCClient`（HTTP 封装）
- `build_context()` 调用 `HDCClient` 获取检索结果

**Trade-offs**:
- ✅ 完全解耦，独立部署和扩展
- ✅ 生成任务不占用 DBAgent 进程资源
- ❌ 新增服务运维负担（部署、监控、配置）
- ❌ 增加网络延迟（服务间调用）
- ❌ 过度工程化（当前阶段不需要）

**Effort**: L (1-2 weeks)  **Risk**: Medium

### Option C: Hybrid (Extend + New Module) ★ Recommended

**Rationale**: 新建 `app/datavault/` 模块承载核心逻辑，扩展现有组件做集成

**Changes**:
- 新建 `app/datavault/` — generator.py + retriever.py + models.py + updater.py
- `app/knowledge/openviking.py` — 扩展 3 个 API
- `app/agent/context.py` — 新增 HDC 段落
- `app/config.py` — 新增 2 个配置项
- `app/api/routes.py` — 新增管理端点
- `app/main.py` — 可选：lifespan 中初始化 HDC

**Trade-offs**:
- ✅ 清晰的责任边界（datavault 模块拥有 HDC 逻辑）
- ✅ 遵循现有架构模式（factory + singleton + graceful degradation）
- ✅ 可独立测试（generator/retriever 可 mock OpenViking）
- ❌ 新增 4 个文件 + 扩展 4 个文件

**Effort**: M (3-7 days)  **Risk**: Low

## 4. Recommendations

1. **Preferred approach**: Option C (Hybrid)
2. **Key decisions for design phase**:
   - LLM 客户端抽取：`runner.py` 中的 `_get_llm_client()` 移至 `app/llm.py` 或 `app/datavault/` 直接 import
   - 任务状态管理：使用内存 dict（简单）+ 可选持久化（后续迭代）
   - `find` vs `search` API 选择：优先使用 `find`（简单快速），`search` 作为可选增强
3. **Research items to carry forward**:
   - OpenViking `find` API 响应格式验证
   - `set_tags` API 参数确认
   - LLM 调用成本实测（单表生成耗时 + token 用量）

---

## 5. Design Synthesis Decisions

### Generalization
- 列摘要生成的分组并行策略（垂直分区）是 HDC 的核心泛化：适用于任何数据库、任何表，与具体 schema 无关
- `find` API 的 level 过滤（L0+L1 定位表、L2 检索列）是 OpenViking 检索的通用模式，HDC 检索直接复用

### Build vs. Adopt
- **Adopt**: OpenViking `find` API 用于向量检索 — 已集成、已验证（HotpotQA top20 91% 准确率）
- **Adopt**: OpenViking `set_tags` API 用于结构化元数据索引 — 原生支持、无需自建
- **Adopt**: OpenViking SemanticProcessor 用于 L0/L1 自动生成 — 写时自动处理
- **Build**: HDC 生成管线（`HDCGenerator`）— 核心业务逻辑，无可替代的现成方案
- **Build**: HDC 检索封装（`HDCRetriever`）— 格式化 + 降级逻辑，项目特定

### Simplification
- 不需要独立的向量存储层：OpenViking 已提供，无需在 datavault 模块中再抽象一层
- 不需要 Protocol 抽象 HDC 存储：OpenViking 是唯一后端，无替换场景
- 不需要分布式任务队列：单进程 asyncio 即可满足生成调度需求
- `HDCBackend` Protocol 从设计中移除：只有一个实现（OpenViking），不需要接口抽象

### Design Decisions
- **双路召回策略**：tags 精确过滤（main_entity 同义词）+ 向量语义检索（自然语言描述），互补而非替代
- **目录结构设计**：`viking://resources/hdc/{db}/_tables/{table}/` — 文件名不与 `_DERIVED_FILENAMES` 冲突
- **降级策略**：完全遵循项目现有 try/except 模式，HDC 不可用时 Agent 行为与 HDC 未启用时完全一致
- **配置粒度**：单一 `hdc_enabled` 开关控制全部 HDC 功能（生成 + 检索），避免过度配置