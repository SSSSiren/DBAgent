# DBAgent 架构设计文档

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Web Layer                             │
│  POST /api/chat (SSE)  │  WebSocket /ws  │  GET /api/sessions       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                     LangGraph Agent Core                             │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    State Graph                                 │   │
│  │                                                                │   │
│  │   ┌─────────┐    ┌──────────┐    ┌─────────┐    ┌─────────┐  │   │
│  │   │  理解    │───▶│  规划     │───▶│  执行    │───▶│  总结    │  │   │
│  │   │UNDERSTAND│   │   PLAN    │   │   ACT    │   │ SUMMARY  │  │   │
│  │   └─────────┘    └──────────┘    └────┬────┘    └─────────┘  │   │
│  │        ▲                               │                       │   │
│  │        │                               ▼                       │   │
│  │        │                         ┌──────────┐                  │   │
│  │        └─────────────────────────│  反思     │                  │   │
│  │                                  │ REFLECT  │                  │   │
│  │                                  └──────────┘                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Summary Memory                              │   │
│  │  - 对话历史 → LLM 摘要 → 压缩上下文                            │   │
│  │  - 保留关键信息：已选数据库、表结构、查询结果摘要                │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼───────┐  ┌────────▼────────┐  ┌───────▼───────┐
│  SQL Executor  │  │  DB Explorer    │  │ Data Analyzer │
│                │  │                 │  │               │
│ - 执行 SQL     │  │ - 列出数据库     │  │ - 统计分析     │
│ - 安全检查     │  │ - 列出表         │  │ - 趋势分析     │
│ - 写操作确认   │  │ - 查看表结构     │  │ - 异常检测     │
│ - 结果格式化   │  │ - 搜索关键词     │  │ - 生成报告     │
└───────┬───────┘  └────────┬────────┘  └───────┬───────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │     OneDBA API Client        │
              │  - 查询数据库列表             │
              │  - 执行 SQL                  │
              │  - 响应格式转换              │
              └─────────────────────────────┘
```

## 2. 核心模块设计

### 2.1 LangGraph Agent Core

#### 状态定义

```python
# app/agent/state.py

from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, Literal, Optional
from dataclasses import dataclass

@dataclass
class ToolCall:
    """工具调用记录"""
    tool: str
    args: dict
    result: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed

class AgentState(TypedDict):
    """Agent 状态"""
    # 输入
    user_input: str
    session_id: str
    
    # 对话记忆
    chat_history: list[dict]
    summary: str  # 摘要记忆
    
    # 上下文
    selected_schema_id: Optional[int]
    selected_database: Optional[dict]
    table_schemas: dict[str, list]  # 表名 -> 字段列表
    
    # 执行过程
    current_step: str
    parsed_intent: Optional[dict]
    execution_plan: list[dict]
    tool_calls: list[ToolCall]
    
    # 输出
    response: str
    needs_confirmation: bool
    pending_action: Optional[dict]
```

#### 状态图定义

```python
# app/agent/graph.py

from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.nodes import (
    understand_node,
    plan_node,
    act_node,
    reflect_node,
    summarize_node,
    confirm_node,
)

def should_continue(state: AgentState) -> str:
    """判断下一步"""
    if state.get("needs_confirmation"):
        return "confirm"
    
    if state.get("current_step") == "finish":
        return "finish"
    
    if state.get("execution_plan"):
        return "continue"
    
    return "finish"

# 构建状态图
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("understand", understand_node)
workflow.add_node("plan", plan_node)
workflow.add_node("act", act_node)
workflow.add_node("reflect", reflect_node)
workflow.add_node("summarize", summarize_node)
workflow.add_node("confirm", confirm_node)

# 定义边
workflow.set_entry_point("understand")
workflow.add_edge("understand", "plan")
workflow.add_edge("plan", "act")

workflow.add_conditional_edges(
    "act",
    should_continue,
    {
        "continue": "reflect",
        "confirm": "confirm",
        "finish": "summarize",
    }
)

workflow.add_edge("reflect", "plan")  # 反思后重新规划
workflow.add_edge("confirm", "act")   # 确认后继续执行
workflow.add_edge("summarize", END)

# 编译
agent_graph = workflow.compile()
```

### 2.2 节点实现

```python
# app/agent/nodes.py

from app.agent.state import AgentState
from langchain_openai import ChatOpenAI
from app.config import settings

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
    temperature=0.1,
)

async def understand_node(state: AgentState) -> dict:
    """理解用户意图"""
    prompt = f"""分析用户输入，返回 JSON：
{{
    "intent": "query" | "explore" | "analyze" | "chat",
    "entities": {{"database": "...", "table": "...", "metric": "..."}},
    "requires_context": true/false
}}

用户输入：{state['user_input']}
历史摘要：{state.get('summary', '')}

只返回 JSON，不要其他内容。
"""
    
    response = await llm.ainvoke(prompt)
    import json
    parsed = json.loads(response.content)
    
    return {
        "current_step": "understand",
        "parsed_intent": parsed,
    }


async def plan_node(state: AgentState) -> dict:
    """规划执行步骤"""
    intent = state.get("parsed_intent", {})
    summary = state.get("summary", "")
    
    # 根据意图生成执行计划
    if intent.get("intent") == "explore":
        # 探索：先查数据库，再查表
        keyword = intent.get("entities", {}).get("database", "")
        plan = [
            {"tool": "list_databases", "args": {"keyword": keyword}},
        ]
    elif intent.get("intent") == "analyze":
        # 分析：需要多步查询
        plan = [
            {"tool": "list_databases", "args": {"keyword": ""}},
            {"tool": "list_tables", "args": {}},
            {"tool": "describe_table", "args": {}},
            {"tool": "execute_sql", "args": {"sql": ""}},
        ]
    else:
        # 直接查询
        plan = [{"tool": "execute_sql", "args": {"sql": ""}}]
    
    return {
        "current_step": "plan",
        "execution_plan": plan,
    }


async def act_node(state: AgentState) -> dict:
    """执行当前步骤"""
    plan = state.get("execution_plan", [])
    if not plan:
        return {"current_step": "finish"}
    
    current = plan[0]
    tool_name = current["tool"]
    tool_args = current["args"]
    
    # 执行工具
    from app.tools import execute_sql, list_databases, list_tables, describe_table
    
    result = None
    if tool_name == "execute_sql":
        # 检查是否需要确认
        sql = tool_args.get("sql", "")
        if needs_confirmation(sql):
            return {
                "current_step": "confirm",
                "needs_confirmation": True,
                "pending_action": current,
            }
        
        result = await execute_sql(**tool_args)
    elif tool_name == "list_databases":
        result = await list_databases(**tool_args)
    elif tool_name == "list_tables":
        schema_id = state.get("selected_schema_id")
        result = await list_tables(schema_id=schema_id)
    elif tool_name == "describe_table":
        schema_id = state.get("selected_schema_id")
        table_name = tool_args.get("table_name", "")
        result = await describe_table(schema_id=schema_id, table_name=table_name)
    
    # 更新状态
    from app.agent.state import ToolCall
    tool_call = ToolCall(
        tool=tool_name,
        args=tool_args,
        result=result,
        status="completed",
    )
    
    return {
        "current_step": "act",
        "tool_calls": state.get("tool_calls", []) + [tool_call],
        "execution_plan": plan[1:],
    }


async def reflect_node(state: AgentState) -> dict:
    """反思执行结果"""
    tool_calls = state.get("tool_calls", [])
    plan = state.get("execution_plan", [])
    
    if not tool_calls:
        return {"current_step": "finish"}
    
    last_call = tool_calls[-1]
    
    # 检查是否执行失败
    if last_call.status == "failed":
        # 尝试调整计划
        return {"current_step": "retry"}
    
    # 更新上下文
    if last_call.tool == "list_databases" and last_call.result:
        # 解析数据库列表，自动选择第一个
        import json
        databases = json.loads(last_call.result)
        if len(databases) == 1:
            return {
                "selected_schema_id": databases[0]["schemaId"],
                "selected_database": databases[0],
            }
    
    if plan:
        return {"current_step": "continue"}
    
    return {"current_step": "finish"}


async def summarize_node(state: AgentState) -> dict:
    """生成最终回复"""
    tool_calls = state.get("tool_calls", [])
    
    # 构建工具调用摘要
    results_summary = []
    for call in tool_calls:
        results_summary.append({
            "tool": call.tool,
            "args": call.args,
            "result": call.result[:500] if call.result else None,
        })
    
    prompt = f"""基于以下工具调用结果，生成用户友好的回复：

工具调用结果：
{json.dumps(results_summary, ensure_ascii=False, indent=2)}

要求：
1. 使用 Markdown 格式
2. 数据结果用表格展示
3. 分析结论用列表展示
4. 重要发现用 **加粗** 标注
5. 简洁明了，不要冗余信息
"""
    
    response = await llm.ainvoke(prompt)
    
    # 更新摘要记忆
    from app.memory.summary import update_summary
    new_summary = await update_summary(
        state.get("summary", ""),
        state["user_input"],
        response.content,
    )
    
    return {
        "current_step": "finish",
        "response": response.content,
        "summary": new_summary,
    }


async def confirm_node(state: AgentState) -> dict:
    """等待用户确认"""
    pending = state.get("pending_action", {})
    
    response = f"""⚠️ 即将执行写操作，请确认：

操作类型：{pending.get('tool')}
参数：{json.dumps(pending.get('args', {}), ensure_ascii=False)}

输入 "确认执行" 继续，其他任意内容取消。
"""
    
    return {
        "response": response,
        "needs_confirmation": False,
    }


def needs_confirmation(sql: str) -> bool:
    """判断 SQL 是否需要用户确认"""
    sql_upper = sql.strip().upper()
    return sql_upper.startswith(("UPDATE", "DELETE", "INSERT"))
```

### 2.3 摘要记忆

```python
# app/memory/summary.py

from langchain_openai import ChatOpenAI
from app.config import settings

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
    temperature=0.1,
)

async def update_summary(
    old_summary: str,
    user_input: str,
    assistant_response: str,
) -> str:
    """更新对话摘要"""
    prompt = f"""将以下对话内容压缩为简洁的摘要，保留关键信息：

已有摘要：
{old_summary or '（无）'}

新对话：
用户：{user_input}
助手：{assistant_response[:500]}...

要求：
1. 保留：已选数据库、表名、关键查询结果
2. 移除：具体 SQL、详细数据
3. 控制在 200 字以内

返回更新后的摘要：
"""
    
    response = await llm.ainvoke(prompt)
    return response.content
```

### 2.4 工具定义

```python
# app/tools/sql_executor.py

from langchain.tools import tool
from app.client.onedba_client import onedba_client
from app.tools.formatters import format_as_markdown_table

@tool
async def execute_sql(sql: str, schema_id: int) -> str:
    """执行 SQL 查询并返回结果。
    
    Args:
        sql: SQL 语句（SELECT/SHOW/DESCRIBE）
        schema_id: 数据库 Schema ID
    
    Returns:
        查询结果（Markdown 表格格式）
    """
    # 安全检查
    check = security_check(sql)
    if not check.passed:
        return f"❌ {check.message}"
    
    try:
        # 执行 SQL
        result = await onedba_client.execute_sql(schema_id, sql)
        
        # 格式化为 Markdown 表格
        return format_as_markdown_table(result)
    except Exception as e:
        return f"❌ 执行失败：{str(e)}"


def security_check(sql: str):
    """安全检查"""
    sql_upper = sql.strip().upper()
    
    # DDL 拦截
    if sql_upper.startswith(("CREATE", "ALTER", "DROP", "TRUNCATE")):
        return SecurityCheckResult(False, "DDL 操作请走 OneDBA 工单")
    
    return SecurityCheckResult(True)


class SecurityCheckResult:
    def __init__(self, passed: bool, message: str = ""):
        self.passed = passed
        self.message = message


# app/tools/db_explorer.py

@tool
async def list_databases(keyword: str = "", env_type: str = "test") -> str:
    """列出用户有权限的数据库。
    
    Args:
        keyword: 搜索关键词（库名、实例名）
        env_type: 环境类型（test/prd/uat/dev/pre）
    
    Returns:
        数据库列表（JSON 格式）
    """
    try:
        databases = await onedba_client.list_databases(
            keyword=keyword,
            env_type=env_type,
        )
        
        import json
        return json.dumps(databases, ensure_ascii=False)
    except Exception as e:
        return f"❌ 查询失败：{str(e)}"


@tool
async def list_tables(schema_id: int) -> str:
    """列出数据库中的所有表。
    
    Args:
        schema_id: 数据库 Schema ID
    
    Returns:
        表名列表
    """
    try:
        result = await onedba_client.execute_sql(
            schema_id,
            "SHOW TABLES"
        )
        return format_as_markdown_table(result)
    except Exception as e:
        return f"❌ 查询失败：{str(e)}"


@tool
async def describe_table(schema_id: int, table_name: str) -> str:
    """查看表结构。
    
    Args:
        schema_id: 数据库 Schema ID
        table_name: 表名
    
    Returns:
        表结构信息
    """
    try:
        result = await onedba_client.execute_sql(
            schema_id,
            f"DESCRIBE {table_name}"
        )
        return format_as_markdown_table(result)
    except Exception as e:
        return f"❌ 查询失败：{str(e)}"


# app/tools/formatters.py

def format_as_markdown_table(result: dict) -> str:
    """将 OneDBA 结果格式化为 Markdown 表格"""
    columns = result.get("columnNames", [])
    rows = result.get("columnDatas", [])
    
    if not columns or not rows:
        return "查询成功，结果为空"
    
    # 提取列名
    col_names = [col.get("title", col.get("field")) for col in columns]
    
    # 构建表格
    lines = []
    lines.append("| " + " | ".join(col_names) + " |")
    lines.append("| " + " | ".join(["---"] * len(col_names)) + " |")
    
    for row in rows:
        values = [str(row.get(col.get("key"), "")) for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    
    lines.append(f"\n共 {len(rows)} 行")
    return "\n".join(lines)
```

### 2.5 OneDBA Client

```python
# app/client/onedba_client.py

import httpx
from typing import List, Dict, Any, Optional
from app.config import settings

class OneDBAClient:
    def __init__(self):
        self.base_url = "https://onedba.shizhuang-inc.com"
        self.access_token = settings.ONEDBA_ACCESS_TOKEN
        self.timeout = 30
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            "accessToken": self.access_token,
            "Content-Type": "application/json",
        }
    
    async def list_databases(
        self,
        keyword: str = "",
        env_type: str = "test",
        instance_type: str = "acs_rds",
        main_body: str = "shizhuang",
    ) -> List[Dict[str, Any]]:
        """查询用户有权限的数据库列表"""
        url = f"{self.base_url}/api/external/v1/agent/instance/schema/user/list"
        
        params = {
            "queryType": "select",
            "page": 1,
            "size": 30,
            "envType": env_type,
            "instanceType": instance_type,
            "mainBody": main_body,
        }
        
        if keyword:
            params["keyword"] = keyword
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 0:
                raise Exception(f"API 错误：{result.get('message')}")
            
            return result.get("data", {}).get("items", [])
    
    async def execute_sql(
        self,
        schema_id: int,
        sql: str,
        query_timeout: int = 30,
    ) -> Dict[str, Any]:
        """执行 SQL 查询"""
        url = f"{self.base_url}/api/external/v1/agent/query"
        
        payload = {
            "schemaId": schema_id,
            "sqlText": sql,
            "queryTimeout": query_timeout,
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 0:
                raise Exception(f"API 错误：{result.get('message')}")
            
            return result.get("data", {})

# 全局实例
onedba_client = OneDBAClient()
```

### 2.6 API Layer

```python
# app/api/routes.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from app.agent.graph import agent_graph
import json

router = APIRouter()

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tool_calls: list

@router.post("/chat")
async def chat(request: ChatRequest):
    """SSE 流式输出"""
    from fastapi.responses import StreamingResponse
    
    async def event_stream():
        initial_state = {
            "user_input": request.message,
            "session_id": request.session_id,
            "chat_history": [],
            "summary": "",
            "selected_schema_id": None,
            "selected_database": None,
            "table_schemas": {},
            "current_step": "",
            "parsed_intent": None,
            "execution_plan": [],
            "tool_calls": [],
            "response": "",
            "needs_confirmation": False,
            "pending_action": None,
        }
        
        async for event in agent_graph.astream_events(initial_state):
            event_type = event["event"]
            
            if event_type == "on_llm_stream":
                yield {
                    "type": "text",
                    "content": event["data"]["chunk"],
                }
            
            elif event_type == "on_tool_start":
                yield {
                    "type": "tool_call",
                    "tool": event["name"],
                    "args": event["data"]["input"],
                    "status": "running",
                }
            
            elif event_type == "on_tool_end":
                yield {
                    "type": "tool_result",
                    "tool": event["name"],
                    "result": event["data"]["output"],
                    "status": "completed",
                }
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """WebSocket 双向通信"""
    await websocket.accept()
    
    try:
        while True:
            message = await websocket.receive_text()
            
            initial_state = {
                "user_input": message,
                "session_id": session_id,
                "chat_history": [],
                "summary": "",
                "selected_schema_id": None,
                "selected_database": None,
                "table_schemas": {},
                "current_step": "",
                "parsed_intent": None,
                "execution_plan": [],
                "tool_calls": [],
                "response": "",
                "needs_confirmation": False,
                "pending_action": None,
            }
            
            async for event in agent_graph.astream_events(initial_state):
                await websocket.send_json(event)
    
    except WebSocketDisconnect:
        pass


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    # TODO: 实现会话存储
    return {
        "session_id": session_id,
        "status": "active",
    }
```

## 3. 项目结构

```
DBAgent/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 配置管理
│   │
│   ├── agent/                     # LangGraph Agent
│   │   ├── __init__.py
│   │   ├── graph.py               # 状态图定义
│   │   ├── nodes.py               # 节点实现
│   │   ├── state.py               # 状态定义
│   │   └── prompts.py             # 系统提示
│   │
│   ├── memory/                    # 记忆管理
│   │   ├── __init__.py
│   │   └── summary.py             # 摘要记忆
│   │
│   ├── tools/                     # Agent 工具
│   │   ├── __init__.py
│   │   ├── sql_executor.py        # SQL 执行
│   │   ├── db_explorer.py         # 数据库探索
│   │   └── formatters.py          # 结果格式化
│   │
│   ├── client/                    # 外部 API
│   │   ├── __init__.py
│   │   └── onedba_client.py       # OneDBA API
│   │
│   └── api/                       # HTTP API
│       ├── __init__.py
│       ├── routes.py              # 路由
│       └── schemas.py             # 数据模型
│
├── tests/
│   ├── __init__.py
│   ├── test_agent.py
│   ├── test_tools.py
│   └── test_onedba_client.py
│
├── requirements.txt
├── .env.example
└── README.md
```

## 4. 依赖清单

```txt
# requirements.txt

# Web 框架
fastapi>=0.109.0
uvicorn>=0.27.0
websockets>=12.0

# LangChain
langchain>=0.1.0
langchain-openai>=0.0.5
langgraph>=0.0.30

# HTTP 客户端
httpx>=0.26.0

# 配置
pydantic>=2.5.0
pydantic-settings>=2.1.0

# 工具
python-dotenv>=1.0.0
```

## 5. 配置示例

```bash
# .env.example

# DeepSeek API
DEEPSEEK_API_KEY=your_deepseek_api_key

# OneDBA
ONEDBA_ACCESS_TOKEN=your_onedba_access_token

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

## 6. 开发计划

| 阶段 | 任务 | 预计时间 |
|---|---|---|
| **Phase 1** | 基础框架搭建 | 1 天 |
| | - FastAPI 项目初始化 | |
| | - LangGraph 状态图定义 | |
| | - OneDBA Client 实现 | |
| **Phase 2** | 核心工具实现 | 1 天 |
| | - SQL Executor Tool | |
| | - DB Explorer Tool | |
| | - 结果格式化 | |
| **Phase 3** | Agent 节点实现 | 1 天 |
| | - Understand / Plan / Act / Reflect / Summarize | |
| | - 摘要记忆 | |
| **Phase 4** | API 层实现 | 0.5 天 |
| | - SSE 流式输出 | |
| | - WebSocket 支持 | |
| **Phase 5** | 测试与优化 | 0.5 天 |

## 7. 关键设计决策

### 7.1 为什么选择 LangGraph 而不是 AgentExecutor？

- **复杂工作流支持**：LangGraph 支持有向图，可以实现多步骤、有分支的工作流
- **状态管理**：内置状态管理，方便追踪执行过程
- **人机交互**：原生支持中断和确认机制
- **可观测性**：更好的调试和监控支持

### 7.2 为什么使用摘要记忆？

- **平衡上下文和 token**：完整对话历史会消耗大量 token，摘要记忆可以压缩上下文
- **保留关键信息**：通过 LLM 提取关键信息（已选数据库、表结构等）
- **支持长对话**：适合多轮交互场景

### 7.3 为什么读操作自动，写操作确认？

- **安全性**：UPDATE/DELETE/INSERT 可能修改数据，需要用户确认
- **效率**：SELECT/SHOW/DESCRIBE 是只读操作，可以自动执行
- **用户体验**：减少不必要的确认步骤

## 8. 后续扩展

### 8.1 数据分析工具

可以添加更多分析工具：

- `analyze_trend`：趋势分析
- `detect_anomaly`：异常检测
- `generate_report`：生成分析报告

### 8.2 可视化支持

- 集成 matplotlib/plotly 生成图表
- 支持导出为图片

### 8.3 集成到 OneDBA

- 添加认证中间件
- 支持多租户
- 集成到 OneDBA 前端
