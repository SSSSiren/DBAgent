# 需求文档

## 项目描述（输入）
**问题方**：DBAgent 的后端开发者及最终用户（100+ 并行访问场景）。

**当前状况**：Agent 运行时的会话、记忆、偏好等数据直接依赖 SQLite 作为存储层。SQLite 是串行写入模型，无法支撑上线后多用户（100+）并行读写的并发需求，且 Agent 核心逻辑中散落着对 SQLite 的直接调用，耦合紧密。

**改变目标**：在 Agent 与具体存储实现之间引入一层抽象接口（Repository/Storage Adapter），使 Agent 模块仅依赖抽象契约而不感知底层存储类型。这既能保持当前 SQLite 快速原型验证的能力，又为后续切换至 PostgreSQL/MySQL 等支持并发的数据库铺平道路，最大程度降低迁移时的改动范围和风险。

## 边界上下文
- **范围内**：会话存储接口统一抽象、偏好存储接口抽象化（使其与会话存储共享抽象模式）、存储后端通过配置切换、存储生命周期统一管理（会话 + 偏好合并为单一入口）、现有数据文件格式向后兼容
- **范围外**：具体的关系数据库实现（PostgreSQL/MySQL/其他）、跨后端数据迁移工具、连接池与并发策略实现、ORM 框架引入、OpenViking 长期记忆和 Langfuse 观测等外部 HTTP 集成变更
- **相邻期望**：Agent 核心逻辑（runner.py、context.py）的会话读写行为不变；现有 API 路由的请求-响应语义不变；存储后端切换时已有会话与偏好数据不丢失；OpenViking 和 Langfuse 的集成方式不因本次变更而改变

## 需求

### Requirement 1: 统一会话存储接口
**Objective:** As a 后端开发者, I want 所有会话数据操作通过统一契约接口进行, so that Agent 核心逻辑和 API 路由不感知底层存储实现细节。

#### Acceptance Criteria
1. When Agent 核心逻辑或 API 路由执行会话创建、读取、更新、删除、列表操作, the 存储抽象层 shall 仅暴露契约接口而非具体存储实现的内部细节
2. When 调用方导入存储能力, the 存储抽象层 shall 提供单一访问入口,调用方无需区分会话存储与偏好存储的导入来源
3. While 存储后端切换为不同实现, the 存储抽象层 shall 保持所有会话操作的返回数据结构和行为语义完全一致

### Requirement 2: 偏好存储抽象化
**Objective:** As a 后端开发者, I want 查询偏好存储与会话存储共享相同的抽象模式, so that 偏好数据也能在不同存储后端之间无感知切换。

#### Acceptance Criteria
1. When 偏好存储被访问（记录查询、写入、列表、淘汰）, the 存储抽象层 shall 提供与会话存储一致的契约接口模式
2. When 存储后端从文件持久化切换为内存实现, the 存储抽象层 shall 保持偏好记录的增删查及 LRU 淘汰行为语义不变
3. If 偏好功能在配置中被禁用, then the 存储抽象层 shall 优雅降级而不影响会话存储或其他模块的正常运行

### Requirement 3: 存储后端可配置切换
**Objective:** As a 运维人员, I want 通过应用配置切换存储后端类型, so that 无需修改代码即可在开发环境（内存/文件持久化）和未来生产环境（高并发数据库）之间切换。

#### Acceptance Criteria
1. When 应用启动且配置指定了存储后端类型, the 存储抽象层 shall 自动初始化对应的后端实现
2. When 配置变更且应用重启, the 存储抽象层 shall 使用新指定的后端类型
3. If 配置指定的存储后端类型不被支持, then the 存储抽象层 shall 在启动阶段报告明确的错误信息并阻止应用继续启动

### Requirement 4: 存储生命周期统一管理
**Objective:** As a 运维人员, I want 所有存储组件（会话 + 偏好）通过统一的初始化与关闭流程管理, so that 资源生命周期一致可靠且不会出现连接泄漏。

#### Acceptance Criteria
1. When 应用启动, the 存储抽象层 shall 按正确的依赖顺序初始化所有已注册的存储后端
2. When 应用关闭, the 存储抽象层 shall 按逆序关闭所有已初始化的存储后端并释放连接资源
3. If 任一存储后端初始化失败, then the 存储抽象层 shall 报告具体错误原因并阻止应用启动

### Requirement 5: 向后兼容与回归安全
**Objective:** As a 后端开发者, I want 引入存储抽象层后现有功能不受影响, so that 已有的开发工作流和测试套件不产生回归。

#### Acceptance Criteria
1. When 使用基于文件的持久化后端, the 存储抽象层 shall 读写现有数据文件且数据格式完全兼容
2. When 使用内存后端, the 存储抽象层 shall 保持与现有内存存储实现相同的会话增删查行为
3. The 存储抽象层 shall 支持以注入内存实例的方式进行隔离测试,与现有测试套件的测试模式兼容