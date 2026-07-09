# 调研与设计决策

## 摘要
- **功能**：nl2sql-query-assistant
- **调研范围**：Extension（对现有 DBAgent 系统的扩展）
- **关键发现**：
  - 现有 `app/memory/store.py` 使用进程内 dict + threading.Lock，会话 ID 由前端生成（非加密安全）
  - 现有 API 层已接受 `user_id` 参数但存储层未使用，导致多用户数据混合
  - aiosqlite 是最适合当前规模的持久化方案，零基础设施开销
  - uuid6（UUID7）提供加密安全且时间可排序的会话 ID 生成

## 调研日志

### 现有代码库扩展点分析
- **上下文**：确定哪些文件需要修改以支持多用户隔离和持久化存储
- **来源**：直接代码库探索（Explore subagent）
- **发现**：
  - 核心变更在 `app/memory/store.py`，需要从 dict 改为抽象存储后端
  - `get_session()` 需要增加 `user_id` 参数，否则多用户会话会碰撞
  - OpenViking 集成已经正确处理了 `user_id` 隔离，无需修改
  - Agent 层的 `context.py` 无需修改（对 user_id 透明）
  - 前端需要增加 user_id 输入和会话管理 UI
- **影响**：10 个文件需要修改，其中 `store.py` 和前端文件改动最大

### 持久化存储方案选型
- **上下文**：选择适合单 Docker 容器、10-50 用户场景的会话持久化方案
- **来源**：WebSearch（aiosqlite、redis-py、FastAPI 会话存储最佳实践）
- **发现**：
  - aiosqlite：零基础设施，适配现有 `./data` 卷，WAL 模式支持并发读写，性能远超需求
  - Redis：功能强大但过度设计，需要额外容器，增加运维复杂度
  - 文件 JSON 存储：无成熟库，需自行实现并发控制，不推荐
  - FastAPI 生态对单进程部署普遍推荐 SQLite
- **影响**：采用 aiosqlite，新增依赖 `aiosqlite` 和 `uuid6`

### 会话 ID 生成策略
- **上下文**：当前前端 `Math.random()` + `Date.now()` 不安全，需改为服务端生成
- **来源**：WebSearch（UUID7 vs UUID4 vs nanoid）
- **发现**：
  - UUID7 是 RFC 9562 推荐标准，时间可排序 + 加密安全
  - UUID4 不支持排序，不利于数据库索引
  - nanoid 最后发布于 2018 年，生态停滞
- **影响**：采用 uuid6 库生成 UUID7，服务端在 `create_session()` 中生成

## 架构模式评估

| 方案 | 描述 | 优势 | 风险/限制 | 备注 |
|------|------|------|----------|------|
| 策略模式 | StorageBackend 协议 + 多实现 | 接口稳定，后端可替换 | 协议需要足够通用 | 采用 |
| 直接 SQLite | 无抽象层，直接使用 aiosqlite | 代码更少 | 后续切换后端需大改 | 不采用 |
| ORM 方案 | SQLAlchemy/SQLModel | 功能丰富 | 过度设计，增加依赖 | 不采用 |

## 设计决策

### 决策：采用 aiosqlite 作为默认持久化存储
- **上下文**：需要会话数据在服务重启后保留，当前 dict 存储在重启后丢失
- **备选方案**：
  1. Redis — 需要额外容器，过度设计
  2. 文件 JSON — 无成熟库，并发控制复杂
  3. aiosqlite — 零基础设施，适配现有部署
- **选定方案**：aiosqlite，默认保持 `STORAGE_BACKEND=memory` 向后兼容
- **理由**：适配现有 `./data:/app/data` 卷挂载，WAL 模式支持并发，ACID 保证数据安全
- **权衡**：单写者锁在极高并发下可能成为瓶颈，但 10-50 用户场景不受影响
- **后续**：如需扩展至多 worker，可切换到 Redis 而接口不变

### 决策：采用 StorageBackend 协议抽象存储层
- **上下文**：需要支持多种存储后端（memory/sqlite/redis），且保持 API 层代码不变
- **备选方案**：
  1. 策略模式（Protocol）— 无运行时开销，接口清晰
  2. 直接实现 SqliteStore 替代 dict — 简单但不可扩展
- **选定方案**：Python Protocol 定义 `StorageBackend`，三种实现
- **理由**：Protocol 不需要显式继承，符合 Python 惯用法；切换后端只需修改配置
- **权衡**：Protocol 不强制类型检查，需单元测试确保实现正确性

### 决策：采用 UUID7 作为会话 ID
- **上下文**：需要服务端生成不可预测且数据库索引友好的会话 ID
- **备选方案**：
  1. UUID4 — 随机，不可排序
  2. UUID7 — 时间可排序 + 随机组件
  3. nanoid — 更短但生态停滞
- **选定方案**：uuid6 库生成 UUID7
- **理由**：RFC 9562 推荐标准，B-tree 友好索引，加密安全
- **权衡**：比 UUID4 多一个依赖

## 风险与缓解
- **SQLite 单写者瓶颈** — 10-50 用户、WAL 模式足够；通过监控 `last_active_at` 观察写入频率
- **数据库文件损坏** — SQLite 有 WAL 恢复机制；建议定期备份 `./data` 目录
- **前端 localStorage 被篡改** — 符合简单身份标识的范围定义；服务端不信任前端，每次校验 user_id
- **向后兼容** — 默认 `STORAGE_BACKEND=memory`，现有部署不受影响

## 参考
- [aiosqlite 文档](https://github.com/omnilib/aiosqlite) — 异步 SQLite 驱动
- [uuid6 文档](https://github.com/oittaa/uuid6-python) — UUID7 实现
- [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562) — UUID 标准（推荐 v7）