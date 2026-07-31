# DBAgent 项目汇报图稿

基于最新 `.kiro` 更新整理。视觉版见 [dbagent-ppt-diagrams.html](./dbagent-ppt-diagrams.html)。

## 已感知的 `.kiro` 变化

- HDC 数据底座从“四层：列 -> 表 -> 关系 -> 库”调整为“三层：列 -> 表 -> 库”。
- 当前前端主流式通道是 SSE；WebSocket 端点已实现，但前端未接入。
- NL2SQL 模块描述移除了 `semantics.py`，核心仍是 `generator.py`、`validator.py`、`repair.py`、`schema.py`。
- 新增 Agent 可观测性侧信道：收集 NL2SQL 阶段耗时、上下文 token、工具耗时，并进入评测报告。
- HDC demo 脚本已从 `tests/datavault/` 迁移到 `tools/hdc/`，测试目录保留纯测试。

## 1. 模块关系图

```mermaid
flowchart LR
    User["用户\n自然语言问题"] --> UI["Web UI\nSSE 实时展示"]
    UI --> API["API / 会话层\napp/api"]
    API --> Context["上下文增强\napp/agent/context.py"]
    API --> Runner["ReAct 编排\napp/agent/runner.py"]

    Context <-.检索.-> Memory["多层记忆\n会话 / 偏好 / SQL Memory"]
    Context <-.召回.-> HDC["HDC 三层语义底座\n列 -> 表 -> 库"]
    Context <-.读取.-> KB["OpenViking\n长期记忆 / HDC 资源目录"]

    Runner --> LLM["OpenAI 兼容 LLM\nDeepSeek-V4"]
    Runner --> Tools["工具注册表\napp/tools"]
    Tools --> Discovery["数据库发现\nlist/find/describe"]
    Tools --> Query["query_database"]
    Query --> NL2SQL["NL2SQL 闭环\n生成 -> 验证 -> 修复"]
    NL2SQL --> Guard["安全分级\n只读放行 / 写与 DDL 拦截"]
    Guard --> OneDBA["OneDBA API\n执行 SQL / 返回数据"]

    Runner -.trace / timings.-> Obs["可观测性\nSSE step/sql/final + Langfuse"]
    OneDBA --> API
    API --> UI

    classDef main fill:#eaf4ff,stroke:#1b6fd8,color:#0b2b4c
    classDef agent fill:#fff5e6,stroke:#e58a00,color:#4a2a00
    classDef enhance fill:#f4f0ff,stroke:#7c4dff,color:#2e1767
    classDef data fill:#ecfdf3,stroke:#0f9d58,color:#063b1e
    classDef guard fill:#fff0f0,stroke:#d64545,color:#4a1212
    class User,UI,API main
    class Context,Runner,LLM,Tools agent
    class Memory,HDC,KB,Obs enhance
    class Discovery,Query,NL2SQL,OneDBA data
    class Guard guard
```

## 2. 业务流程图

```mermaid
flowchart TB
    A["1 用户提问"] --> B["2 恢复会话"]
    B --> C["3 并行检索上下文"]
    C --> C1["长期记忆"]
    C --> C2["查询偏好"]
    C --> C3["SQL 历史"]
    C --> C4["HDC 表/列语义"]
    C1 --> D["4 ReAct Agent 决策"]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E{"需要找表?"}
    E -- 是 --> F["数据库发现工具\nlist/find/describe"]
    F --> D
    E -- 否 --> G["query_database"]
    G --> H["NL2SQL\n生成 -> 验证 -> 修复"]
    H --> I{"SQL 类型"}
    I -- 只读 --> J["OneDBA 执行\nLIMIT 保护"]
    I -- 写/DDL --> K["拦截\n不执行"]
    J --> L["SSE 输出\nstep / sql / final"]
    K --> L
    L --> M["沉淀资产\n会话、偏好、SQL Memory、trace"]
    M -. 下一轮复用 .-> C
```

## 汇报讲解主线

- **一眼看主链路**：用户问题 -> 上下文增强 -> ReAct 决策 -> NL2SQL 闭环 -> 安全执行 -> SSE 结果。
- **一眼看创新点**：HDC 三层语义底座、多层记忆、ContextVar 富化、观测侧信道、安全分级。
- **一眼看业务价值**：少找表、少写 SQL、少误操作、过程透明、结果可复用。
