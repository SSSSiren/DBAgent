# Research & Design Decisions

## Summary
- **Feature**: storage-abstraction-layer
- **Discovery Scope**: Extension（扩展现有系统）
- **Key Findings**:
  - 会话存储已有 `StorageBackend` Protocol + 工厂模式，偏好存储缺失对等抽象
  - 仅需对称补齐 Protocol 模式，无需引入新技术或新依赖
  - 两套独立的生命周期（`get_store()` + `get_preference_store()`）可通过 `StorageManager` 薄封装层统一

## Research Log

### 代码库耦合分析
- **Context**: 需要理解当前存储层与 Agent 核心逻辑的耦合程度
- **Sources Consulted**: `app/memory/store.py`, `app/memory/preferences.py`, `app/main.py`, `app/api/routes.py`, `app/config.py`
- **Findings**:
  - 仅 2 个生产文件直接 import `aiosqlite`（`store.py`, `preferences.py`）
  - 会话存储通过 `StorageBackend` Protocol 解耦，偏好存储无协议
  - `main.py` 和 `routes.py` 从两个独立模块导入存储功能
  - 测试通过 monkeypatch 工厂函数注入 `:memory:` 实例
- **Implications**: 改动范围小——仅需修改 `app/memory/` 包内文件 + 两个调用方

### 包命名决策
- **Context**: `structure.md` 描述为 `app/storage/`，实际代码在 `app/memory/`
- **Sources Consulted**: `.kiro/steering/structure.md`, `app/memory/`
- **Findings**: 包重命名涉及大量导入路径变更，与 R5（向后兼容）冲突
- **Implications**: 本迭代保持 `app/memory/` 包名，重命名留待后续独立迭代

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A: 扩展现有组件 | 在 `app/memory/` 内对称补齐 PreferenceBackend + StorageManager | 最小改动，现有 Protocol 模式可直接复用 | 包名与 structure.md 不一致 | **选中** |
| B: 新建包 + 重构 | 新建 `app/storage/`，迁移所有存储逻辑 | 与 structure.md 一致，语义清晰 | 改动范围大，所有导入路径需更新 | 后续迭代考虑 |
| C: 混合方案 | 分阶段：先补抽象，后重命名 | 风险最低 | 两个迭代周期，总时间更长 | 过度设计 |

## Design Decisions

### Decision: PreferenceBackend 接口范围
- **Context**: `QueryPreferenceStore` 有多个方法，需决定哪些纳入 Protocol
- **Alternatives Considered**:
  1. 完整复制所有方法签名（包括 `_count_user_records`、`_evict_lru`）
  2. 仅抽象调用方实际使用的方法（`record_query`、`retrieve_preferences`、`retrieve_top_preferences`、`initialize`、`close`）
- **Selected Approach**: Option 2 — 仅抽象调用方使用的方法
- **Rationale**: 内部辅助方法是实现细节，不应出现在 Protocol 中；`routes.py` 仅调用 3 个业务方法 + 生命周期方法
- **Trade-offs**: 未来若有新调用方需要其他方法，需扩展 Protocol
- **Follow-up**: 实现时确认 `routes.py` 中所有偏好调用点均已覆盖

### Decision: 偏好后端跟随会话后端选择
- **Context**: 是否需要为偏好存储设置独立的 `preference_backend` 配置项
- **Alternatives Considered**:
  1. 独立配置：`preference_backend` 字段，可与会话后端不同
  2. 跟随配置：偏好后端始终与会话后端一致
- **Selected Approach**: Option 2 — 跟随会话后端
- **Rationale**: 同一文件存储场景下，会话和偏好使用不同后端类型无实际意义；避免配置复杂度
- **Trade-offs**: 未来若需要独立选择（如会话用 Redis、偏好用 SQLite），需重构
- **Follow-up**: 无需

### Decision: 保留旧 API 作为兼容包装
- **Context**: 如何迁移现有 `get_store()` 和 `get_preference_store()` 调用方
- **Alternatives Considered**:
  1. 一次性替换所有调用方
  2. 保留旧 API 为 deprecated wrapper，内部分发到 StorageManager
- **Selected Approach**: Option 2 — 渐进式迁移
- **Rationale**: 降低测试和调用方改动风险；旧 API 标记为 deprecated 提供迁移窗口
- **Trade-offs**: 短期存在两套 API，代码略有冗余
- **Follow-up**: 确认所有测试通过后，可在后续迭代中移除旧 API

## Risks & Mitigations
- 测试 monkeypatch 路径变更导致回归 → 更新所有测试文件中的导入路径；保留旧 API wrapper 作为过渡
- `QueryPreferenceStore` 重命名破坏外部引用 → 在 `__init__.py` 中保留旧名称作为别名导出
- 双连接未合并导致资源浪费 → 记录为已知限制，后续迭代考虑共享连接

## References
- 无外部参考资料（所有决策基于代码库内部探索）