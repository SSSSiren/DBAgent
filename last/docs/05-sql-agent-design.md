# SQL Agent 设计方案

本文档定义 DBAgent 面向“SQL 语句编写提效”的新 Agent 设计。目标不是让模型一次性猜 SQL，而是通过 schema、业务语义、执行验证和评测闭环，让 Agent 稳定地产出可执行、可解释、可修复的 MySQL SQL。

## 1. 场景特点

SQL 编写提效和通用代码 Agent 不同，核心风险集中在“SQL 看起来对，但结果错”。

| 特点 | 设计含义 |
|---|---|
| 强 schema 依赖 | 生成前必须获得真实表、字段、类型和必要样例值 |
| 枚举值容易幻觉 | 过滤值必须来自字段样例、业务语义层或用户明确输入 |
| 业务口径影响结果 | GMV、有效订单、在售、支付成功等必须配置为语义规则 |
| MySQL 方言约束明确 | 禁止混入 PostgreSQL/BigQuery 语法，复杂窗口函数要按 MySQL 8 生成 |
| 允许执行 SQL | 默认只允许只读查询，并设置超时、行数和安全检查 |
| 写 SQL 提效优先 | 输出 SQL、解释、假设和可修改点，比直接查数更重要 |
| 评测必须闭环 | 需要离线 benchmark 和线上采纳/修改反馈持续优化 |

## 2. 目标边界

### 2.1 V1 目标

1. 基于自然语言生成 MySQL 只读 SQL。
2. 支持单表、多表 Join、聚合、TopN、时间窗口、CTE、窗口函数。
3. 支持 SQL 执行、报错修复和结果解释。
4. 支持 schema 检索、字段样例值检索和业务口径注入。
5. 支持离线 MySQL sandbox benchmark 评测。
6. 输出 SQL 时明确假设、使用表字段和潜在风险。

### 2.2 非目标

| 非目标 | 原因 |
|---|---|
| 自动执行 DDL/DML | 写操作风险高，暂不作为 SQL 编写提效主路径 |
| 一开始覆盖全部真实业务口径 | 当前没有完整数据字典和指标平台，需要逐步沉淀 |
| 完全依赖 LLM 判断正确性 | SQL 正确性优先通过 parser、dry run、执行结果和 benchmark 判断 |
| 追问记忆和复杂意图解析一次性完成 | 已作为后续规划，见 `07`、`08` 文档 |

## 3. Agent 范式

推荐采用组合范式，而不是单一 ReAct。

| 范式 | 用途 |
|---|---|
| Schema-RAG Agent | 检索表结构、字段说明、样例值、历史 SQL 和业务规则 |
| Plan-and-Execute Agent | 先拆解需求，再生成 CTE、Join、聚合和过滤 |
| Tool-using Agent | 调用 schema、sample values、dry run、execute、explain、lint |
| Critic/Repair Agent | 根据 MySQL 报错、空结果、字段不匹配自动修复 |
| Workflow Graph Agent | 用状态机固化“理解、检索、生成、验证、执行、修复、解释” |
| Human-in-the-loop | 歧义字段、多个口径或高成本查询时要求用户确认 |

## 4. 推荐开源底座

| 项目 | 角色 | 采用方式 |
|---|---|---|
| WrenAI | 业务语义层参考 | 借鉴 context layer、business semantics、governance、examples 的组织方式 |
| LangGraph | Agent 编排底座 | 编排状态机、修复循环、人机确认和 trace |
| LlamaIndex | 检索层参考 | 管理 schema 文档、业务规则、历史 SQL 和样例查询的 RAG |

当前仓库已经使用 LangGraph。WrenAI 和 LlamaIndex 第一阶段不要求直接引入依赖，可以先按照它们的设计思想实现轻量语义层和检索接口。

## 5. 目标架构

```text
Frontend / API
    |
LangGraph SQL Agent
    |
    +-- Intent & Task Parser
    +-- Schema Retriever
    +-- Semantic Rule Retriever
    +-- SQL Generator
    +-- SQL Validator
    +-- MySQL Executor
    +-- SQL Repairer
    +-- Result Explainer
    |
Tool Layer
    |
    +-- DatabaseAdapter
    +-- Schema Catalog
    +-- Sample Value Profiler
    +-- Business Semantic Store
    +-- Benchmark/Eval Runner
    |
MySQL / Docs / Benchmark Data
```

## 6. 核心工作流

推荐主流程：

```text
User Question
  ↓
Classify Task
  ↓
Parse Structured SQL Task
  ↓
Retrieve Schema
  ↓
Retrieve Sample Values
  ↓
Retrieve Business Rules
  ↓
Plan SQL Shape
  ↓
Generate Candidate SQL
  ↓
Static Validate
  ↓
Dry Run / Execute Readonly
  ↓
Repair Loop
  ↓
Explain SQL + Result + Assumptions
  ↓
Save Trace for Eval
```

关键约束：

1. 不允许在缺少 schema 的情况下生成最终 SQL。
2. 不允许把中文业务词直接当作枚举值写入 SQL。
3. 不允许执行非只读 SQL。
4. SQL 执行失败必须进入修复循环，而不是直接结束。
5. 每次生成必须保存 trace，便于 benchmark 归因。

## 7. 数据与工具接口

### 7.1 DatabaseAdapter

建议抽象统一数据库接口：

```python
class DatabaseAdapter:
    def list_databases(self) -> list[dict]: ...
    def list_tables(self, database: str) -> list[str]: ...
    def get_table_schema(self, table: str) -> list[dict]: ...
    def get_column_samples(self, table: str, column: str, limit: int = 20) -> list[str]: ...
    def dry_run(self, sql: str) -> dict: ...
    def explain(self, sql: str) -> dict: ...
    def execute_readonly(self, sql: str, limit: int = 100) -> list[dict]: ...
```

V1 面向 MySQL，可以先只实现 MySQL/OneDBA 适配。

### 7.2 Schema Catalog

保存：

- 表名、字段名、类型、注释。
- 主键、索引、可能 Join 键。
- 字段样例值。
- 常用时间字段。
- 废弃字段和禁用字段。

### 7.3 Business Semantic Store

保存业务口径，不硬编码在 prompt 中：

```json
{
  "scope": "ecommerce_sandbox",
  "rules": [
    {
      "name": "有效订单",
      "sql": "order_status IN ('paid', 'completed')",
      "tables": ["orders"]
    },
    {
      "name": "支付成功",
      "sql": "payment_status = 'success'",
      "tables": ["payments"]
    }
  ]
}
```

当前实现采用可级联的语义 provider，而不是强依赖单一外部服务：

| Provider | 作用 | 是否直接注入 SQL prompt |
|---|---|---|
| `http` | 从外部元数据/指标平台读取规则 | 仅 `system/confirmed` 且字段校验通过 |
| `file` | 从部署配置文件读取规则 | 仅 `system/confirmed` 且字段校验通过 |
| `user memory` | 读取用户确认过的规则 | 是，需限定 schema/table |
| `history` | 读取历史 SQL 归纳出的规则 | 默认作为候选，除非标记 confirmed |
| `schema_inference` | 基于字段名和样例值推断候选规则 | 否，只能触发澄清 |

安全边界：

1. 所有规则注入前都必须按当前 `schema_id/tables/columns` 过滤。
2. `candidate` 或 `requires_confirmation=true` 的规则不能直接用于 SQL。
3. 样例值和 schema 推断只能生成候选，例如“有效订单可能是 `paid/completed`”，首次使用必须让用户确认。
4. 用户确认后再沉淀为 `confirmed` 规则，后续查询可自动注入并在回答中说明来源。

确认闭环：

```text
用户：统计 orders 表有效订单 GMV
Agent：识别到候选口径：
       - 有效订单：order_status IN ('paid', 'completed')
       - GMV：SUM(orders.total_amount)
       请确认是否记住并使用这些口径。
用户：确认
Agent：写入 SEMANTIC_USER_RULES_PATH，标记为 status=confirmed/source=user_confirmed，
       然后继续执行原始查询。
```

如果候选口径不正确，用户可以直接给出修正：

```text
用户：有效订单其实是 order_status = 'success'
Agent：校验 `order_status` 是否存在于当前表；
       校验通过后写入 confirmed 语义规则；
       然后继续执行原始查询。
```

目前支持的修正规则格式：

```text
<业务词> 其实是 <SQL 条件或表达式>
<业务词> 就是 <SQL 条件或表达式>
<业务词> = <SQL 条件或表达式>
```

也支持纯自然语言口径说明：

```text
用户：有效订单就是已支付和已完成订单
Agent：调用 LLM 结构化解析层，把自然语言口径解析为候选 SQL 片段；
       例如 `order_status IN ('paid', 'completed')`。
       解析结果仍必须通过字段存在性、安全片段和置信度校验；
       校验通过后才写入 confirmed 语义规则。
```

安全限制：

- 不允许包含 `SELECT/INSERT/UPDATE/DELETE/DDL` 等完整 SQL。
- 不允许多语句。
- 引用字段必须存在于当前表结构。

默认用户确认规则保存到：

```text
data/user_semantic_rules.json
```

写入后的规则仍会在后续查询前按当前 `schema_id/tables/columns` 校验；如果换库后字段不存在，不会注入。

配置示例：

```env
SEMANTIC_PROVIDER=auto
SEMANTIC_SERVICE_URL=http://metadata-service.internal
SEMANTIC_RULES_PATH=/etc/dbagent/semantic_rules.json
SEMANTIC_USER_RULES_PATH=/etc/dbagent/user_semantic_rules.json
SEMANTIC_HISTORY_RULES_PATH=/etc/dbagent/history_semantic_rules.json
SEMANTIC_DEFAULT_DOMAIN=onedba
```

## 8. 通用规则、业务配置和测试特制规则

### 8.1 通用规则

这些规则应进入系统 prompt、SQL generator prompt 或 validator：

1. 只生成单条 `SELECT/WITH`。
2. 不臆造表、字段、枚举值。
3. 枚举值必须来自样例值、业务语义层或用户明确输入。
4. 使用 MySQL 8 语法。
5. 聚合、TopN、列表查询尽量补充确定性 `ORDER BY`。
6. 输出列尽量贴合用户问题，不额外返回无关字段。
7. 复杂窗口函数先聚合到 CTE，再在外层排名。
8. 执行失败后根据 MySQL 错误修复。

### 8.2 业务配置

这些应放入语义层，而不是写死在 Agent 代码里：

| 口径 | 示例 |
|---|---|
| 有效订单 | `order_status IN ('paid', 'completed')` |
| 支付成功 | `payment_status = 'success'` |
| 退款成功 | `refund_status = 'approved'` |
| 在售商品 | `products.status = 'active'` |
| GMV | `SUM(orders.total_amount)` |
| 默认订单时间 | `orders.paid_at` 或 `orders.created_at`，按业务配置 |

### 8.3 Benchmark 特制规则

这些只应留在 benchmark case 或 evaluator 配置里：

1. 强制 alias 与 reference SQL 完全一致。
2. 某个 case 必须使用 `HAVING`。
3. 某个 safety case 固定返回 `id, order_status`。
4. `ORDER BY` 完全匹配 reference。

产品 Agent 不应为了单个测试 case 写死这些规则。

## 9. 评测体系

当前已经落地 MySQL sandbox benchmark，见 `06-mysql-sandbox-benchmark.md`。

核心指标：

| 指标 | 含义 |
|---|---|
| `static_pass_rate` | 静态约束是否通过 |
| `safety_pass_rate` | 是否只读安全 |
| `schema_pass_rate` | 表字段是否命中 |
| `execution_pass_rate` | 是否能在 MySQL 执行 |
| `result_accuracy` | 结果是否与 reference SQL 一致 |

后续需要将失败归因扩展为：

| 归因 | 示例 |
|---|---|
| `enum_value_error` | `status='在售'` 而真实值是 `active` |
| `business_rule_error` | 有效订单漏掉 `paid` |
| `join_semantics_error` | `JOIN` 和 `LEFT JOIN` 语义不一致 |
| `mysql_dialect_error` | 嵌套窗口函数导致 MySQL 报错 |
| `output_shape_mismatch` | 多返回字段或 alias 不一致 |
| `evaluator_strictness` | 语义等价但 hash 不一致 |

## 10. 分阶段落地

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | MySQL sandbox benchmark、reference 自检、prediction 生成 | 已完成 |
| P1 | SQL generator prompt 加入通用规则和 MySQL 方言约束 | 待实现 |
| P1 | 样例值检索，解决枚举值幻觉 | 待实现 |
| P1 | 轻量业务语义层，注入有效订单、GMV、支付成功等规则 | 待实现 |
| P2 | 执行失败自动修复和失败归因报告 | 部分已有，需增强 |
| P2 | evaluator 区分严格失败和语义等价 | 待实现 |
| P3 | 追问记忆和任务版本栈 | 规划中，见 `07` |
| P3 | LLM 结构化意图识别升级 | 规划中，见 `08` |
