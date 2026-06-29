"""
Agent 执行器 - 基于 LangGraph 的 ReAct Agent

核心职责：
1. 创建 ReAct Agent（推理 + 行动循环）
2. 流式执行 Agent 并产出步骤事件
3. 管理对话记忆（历史 + 摘要）

ReAct 模式：
  LLM 推理 → 选择工具 → 执行工具 → 观察结果 → 继续推理 → ... → 最终回答

依赖关系：
  LangChain 提供：LLM (ChatOpenAI)、消息类型 (HumanMessage/AIMessage/ToolMessage)、工具协议 (@tool)
  LangGraph 提供：Agent 编排引擎 (create_react_agent)，驱动 ReAct 循环
"""

from typing import Any, AsyncIterator
from langgraph.prebuilt import create_react_agent  # LangGraph 预构建的 ReAct Agent
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage  # LangChain 消息类型

from app.agent.llm import get_llm
from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.tools import (
    list_databases_tool,
    select_database_tool,
    list_tables_tool,
    describe_table_tool,
    query_database_tool,
    execute_sql_tool,
    ask_user_tool,
)
from app.memory.summary import update_summary


# ========== 阶段3-1：Agent 创建 ==========

def create_agent_executor():
    """
    创建 Agent 实例

    核心调用：create_react_agent(model, tools, prompt)
    这是 LangGraph 和 LangChain 的桥梁：
    - model: LangChain 的 ChatOpenAI（LLM）
    - tools: LangChain 的 @tool 工具列表
    - prompt: 系统提示词，定义 Agent 的行为规范

    create_react_agent 内部构建的图：
    ┌──────────────────────────────────────────┐
    │                                          │
    │   ┌─────┐  有工具调用  ┌──────┐          │
    │   │ LLM │ ──────────▶ │ 工具  │          │
    │   │推理  │             │ 执行  │          │
    │   └─────┘             └──────┘          │
    │       ▲                     │            │
    │       │    观察结果          │            │
    │       └─────────────────────┘            │
    │       │                                  │
    │       │ 无工具调用（任务完成）              │
    │       ▼                                  │
    │      END                                 │
    └──────────────────────────────────────────┘

    Returns:
        CompiledStateGraph: 编译后的 Agent 执行图
    """
    # 获取 LLM 实例（DeepSeek，通过 ChatOpenAI 封装）
    llm = get_llm()

    # 定义 Agent 可用的工具列表
    # 每个工具都用 @tool 装饰器定义，LangGraph 会自动解析工具的 name/description/parameters
    # LLM 根据工具描述决定调用哪个工具
    tools = [
        list_databases_tool,     # 列出可用数据库
        select_database_tool,    # 选择当前数据库
        list_tables_tool,        # 列出数据库中的表
        describe_table_tool,     # 查看表结构
        query_database_tool,     # 自然语言查询（NL2SQL 核心工具）
        execute_sql_tool,        # 直接执行 SQL
        ask_user_tool,           # 向用户提问
    ]

    # 创建 ReAct Agent
    # create_react_agent 是 LangGraph 的预构建函数，内部已经实现了完整的 ReAct 循环
    # 等价于手动用 StateGraph 构建 agent_node → should_continue → tool_node → agent_node 的图
    agent = create_react_agent(
        model=llm,                          # LLM 模型
        tools=tools,                        # 工具列表
        prompt=AGENT_SYSTEM_PROMPT,         # 系统提示词
    )

    return agent


# ========== 辅助函数 ==========

def extract_tool_calls_from_messages(messages: list) -> list[dict[str, Any]]:
    """
    从消息列表中提取工具调用信息

    用途：
    - 从 Agent 执行后的消息历史中提取所有工具调用记录
    - 用于返回给前端，展示 Agent 执行了哪些工具

    参数：
        messages: LangChain 消息列表，包含 HumanMessage、AIMessage、ToolMessage

    返回：
        工具调用信息列表，格式：
        [
            {
                "tool": "list_databases_tool",
                "args": {},
                "result": "[...]",
                "status": "completed"
            },
            ...
        ]
    """
    tool_calls = []
    for msg in messages:
        # 只处理 ToolMessage，它代表工具执行完成后的返回结果
        if isinstance(msg, ToolMessage):
            # 解析工具名称和结果
            tool_name = msg.name or "unknown"
            tool_calls.append({
                "tool": tool_name,
                "args": {},  # ToolMessage 不包含参数，只有结果
                "result": msg.content,
                "status": "completed",
            })
    return tool_calls


def extract_sql_from_tool_output(output: str) -> str:
    """
    从工具输出中提取 SQL 语句

    用途：
    - query_database_tool 返回的结果中可能包含生成的 SQL
    - 提取 SQL 后发送给前端，让用户看到实际执行的查询

    参数：
        output: 工具输出的字符串，可能包含 ```sql ... ``` 格式的代码块

    返回：
        提取的 SQL 语句，如果没有找到则返回空字符串
    """
    import re
    # 尝试匹配 ```sql ... ``` 格式
    match = re.search(r'```sql\s*(.*?)\s*```', output, re.DOTALL)
    if match:
        sql = match.group(1).strip()
        # 清理字面的 \n 和 \r 字符
        sql = sql.replace('\\n', ' ').replace('\\r', '')
        sql = ' '.join(sql.split())  # 合并多个空白为单个空格
        print(f"[extract_sql] Extracted SQL from ```sql: {sql}")
        return sql
    # 尝试匹配 ``` ... ``` 格式
    match = re.search(r'```\s*(.*?)\s*```', output, re.DOTALL)
    if match:
        sql = match.group(1).strip()
        # 检查是否包含 SQL 关键字，避免误提取非 SQL 代码块
        if any(keyword in sql.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE']):
            # 清理字面的 \n 和 \r 字符
            sql = sql.replace('\\n', ' ').replace('\\r', '')
            sql = ' '.join(sql.split())  # 合并多个空白为单个空格
            print(f"[extract_sql] Extracted SQL from ```: {sql}")
            return sql
    print(f"[extract_sql] No SQL found in output")
    return ""

# ========== 阶段3-2：Agent 流式执行 ==========

async def run_agent_stream(
    user_input: str,
    session_state: dict[str, Any],
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """
    流式运行 Agent，产出详细的步骤事件

    数据流：
    1. 创建 Agent 实例
    2. 构建上下文（数据库信息 + 对话摘要）
    3. 调用 agent.astream_events() 启动 ReAct 循环
    4. 监听事件流，产出 step/sql/final 事件
    5. 更新对话记忆（历史 + 摘要）

    参数：
        user_input: 用户当前输入的消息
        session_state: 会话状态字典，包含 chat_history、summary、selected_database 等

    产出：
        (event_type, data) 元组，event_type 可以是：
        - "step": 中间步骤事件，如工具调用开始/完成
        - "sql": 提取的 SQL 语句
        - "final": 最终响应，包含回复内容和更新后的状态
    """
    # 步骤1：创建 Agent 实例
    # 每次请求都创建新的 Agent，避免状态污染
    agent = create_agent_executor()

    # 步骤2：从会话状态中提取上下文信息
    session_id = session_state.get("session_id", "")
    chat_history = session_state.get("chat_history", [])
    summary = session_state.get("summary", "")
    selected_schema_id = session_state.get("selected_schema_id")
    selected_database = session_state.get("selected_database")

    # 步骤3：构建 Agent 输入消息
    # 策略：截断 + 摘要互补
    # - 摘要覆盖全部历史（压缩文本，放在最前面）
    # - 最近 N 条完整消息（含工具调用，LLM 可精确引用）
    # - 当前用户输入（带数据库上下文）
    MAX_HISTORY_MESSAGES = 20

    messages = []

    # 3a：如果有摘要且历史被截断过，把摘要作为第一条消息注入
    # 摘要让 LLM 了解更早的对话概要，弥补截断造成的信息丢失
    if summary and len(chat_history) >= MAX_HISTORY_MESSAGES:
        messages.append(HumanMessage(content=f"[之前的对话摘要]\n{summary}"))

    # 3b：传入最近的消息历史（已由上一轮截断，这里再保底截断一次）
    recent_history = chat_history[-MAX_HISTORY_MESSAGES:] if len(chat_history) > MAX_HISTORY_MESSAGES else chat_history
    messages.extend(recent_history)

    # 3c：构建当前用户输入（带数据库上下文）
    context_parts = []
    if selected_database:
        context_parts.append(f"当前选择的数据库: {selected_database.get('schemaName')} (schema_id={selected_schema_id})")
    if context_parts:
        context = "\n".join(context_parts)
        full_input = f"{context}\n\n用户问题: {user_input}"
    else:
        full_input = user_input

    messages.append(HumanMessage(content=full_input))

    # 步骤4：收集消息和工具调用信息
    all_messages = []           # 存储所有消息（用于提取最终响应）
    tool_calls_info = []        # 存储工具调用详情（用于返回给前端）
    seen_tool_calls = set()     # 去重：已处理的工具调用
    yielded_steps = set()       # 去重：已 yield 的步骤，避免重复推送

    # 步骤5：启动 ReAct 循环
    # astream_events 是 LangGraph 的核心 API，它返回一个异步事件流
    # 每个事件代表 Agent 执行过程中的一个步骤（LLM 推理、工具调用等）
    # version="v2" 使用新版事件格式
    # recursion_limit: 限制 Agent 的最大推理步数，防止无限循环
    try:
        async for event in agent.astream_events(
            {"messages": messages},  # 输入：摘要 + 历史消息 + 当前用户问题
            version="v2",
            config={"recursion_limit": 40},  # 最多 40 步，防止无限重试
        ):
            event_name = event.get("event", "")  # 事件类型
            run_id = event.get("run_id", "")     # 运行 ID，用于关联同一次工具调用

            # ========== 事件处理：工具调用开始 ==========
            # 当 LLM 决定调用某个工具时，触发此事件
            if event_name == "on_tool_start":
                tool_name = event.get("name", "unknown")           # 工具名称
                tool_input = event.get("data", {}).get("input", {}) # 工具输入参数
                step_key = f"{run_id}:running"
                # 去重：避免重复 yield 同一个步骤
                if step_key not in yielded_steps:
                    yielded_steps.add(step_key)
                    # yield 步骤事件：工具开始执行
                    yield "step", {"step": f"tool:{tool_name}", "status": "running"}
                # 记录工具调用信息（后续会更新结果）
                tool_calls_info.append({
                    "tool": tool_name,
                    "args": tool_input,
                    "run_id": run_id,
                })

            # ========== 事件处理：工具调用完成 ==========
            # 当工具执行完成并返回结果时，触发此事件
            elif event_name == "on_tool_end":
                tool_name = event.get("name", "unknown")            # 工具名称
                tool_output = event.get("data", {}).get("output", "") # 工具输出结果
                step_key = f"{run_id}:completed"
                # 去重：避免重复 yield 同一个步骤
                if step_key not in yielded_steps:
                    yielded_steps.add(step_key)
                    # yield 步骤事件：工具执行完成
                    yield "step", {"step": f"tool:{tool_name}", "status": "completed"}
                # 找到对应的工具调用记录并更新结果
                for tc in tool_calls_info:
                    if tc.get("run_id") == run_id:
                        tc["result"] = str(tool_output)
                        break

                # 特殊处理：如果是 query_database_tool，提取 SQL 并发送给前端
                # 这样用户可以看到实际执行的 SQL 语句
                if tool_name == "query_database_tool":
                    output_str = str(tool_output)
                    sql = extract_sql_from_tool_output(output_str)
                    if sql:
                        yield "sql", {"sql": sql}
                # 如果是 execute_sql_tool，从工具参数中提取 SQL
                elif tool_name == "execute_sql_tool":
                    for tc in tool_calls_info:
                        if tc.get("run_id") == run_id and tc.get("args", {}).get("sql"):
                            sql = tc["args"]["sql"]
                            print(f"[llm_agent] Extracted SQL from execute_sql_tool args: {sql}")
                            yield "sql", {"sql": sql}
                            break

            # ========== 事件处理：LLM 推理完成 ==========
            # 当 LLM 完成一次推理并输出消息时，触发此事件
            elif event_name == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                # 收集所有 LLM 输出的消息（包括中间推理和最终回答）
                if output and hasattr(output, "content"):
                    all_messages.append(output)

    except Exception as e:
        # 捕获递归限制错误或其他异常，返回友好的错误消息
        error_msg = str(e)
        if "recursion_limit" in error_msg.lower() or "GraphRecursionError" in error_msg:
            response = "抱歉，查询过程中步骤过多，已自动停止。"
        else:
            response = f"查询过程中发生错误：{error_msg}"

        # 构建更新后的状态
        chat_history.append(HumanMessage(content=user_input))
        chat_history.append(AIMessage(content=response))
        if len(chat_history) > 20:
            chat_history = chat_history[-20:]

        new_summary = await update_summary(summary, user_input, response)
        updated_state = {
            "session_id": session_id,
            "chat_history": chat_history,
            "summary": new_summary,
            "selected_schema_id": selected_schema_id,
            "selected_database": selected_database,
        }

        yield "final", {
            "response": response,
            "updated_state": updated_state,
            "needs_confirmation": False,
            "pending_action": None,
            "tool_calls": tool_calls_info,
        }
        return

    # 步骤6：提取最终响应
    # 最后一条消息是 LLM 的最终回答（不包含工具调用）
    response = all_messages[-1].content if all_messages else "获取响应失败"

    # 步骤7：检查是否需要确认（当前未实现，预留功能）
    # 如果 Agent 执行了写操作（UPDATE/DELETE/INSERT），需要用户确认
    needs_confirmation = False
    pending_action = None

    # 步骤8：更新对话记忆
    # 将本次对话添加到历史记录
    chat_history.append(HumanMessage(content=user_input))   # 用户输入
    chat_history.append(AIMessage(content=response))        # AI 回答

    # 保持最近 20 条消息，避免上下文过长
    # 这是简单的滑动窗口策略，更早的消息会被丢弃
    if len(chat_history) > 20:
        chat_history = chat_history[-20:]

    # 步骤9：更新对话摘要
    # 调用 LLM 将对话历史压缩为摘要，用于后续请求的上下文
    # 这样即使对话历史被截断，Agent 仍然知道之前讨论过什么
    new_summary = await update_summary(summary, user_input, response)

    # 步骤10：构建更新后的状态
    updated_state = {
        "session_id": session_id,                 # 会话 ID（save_session 保存状态时需要）
        "chat_history": chat_history,             # 更新后的对话历史
        "summary": new_summary,                   # 更新后的摘要
        "selected_schema_id": selected_schema_id, # 保持数据库选择
        "selected_database": selected_database,   # 保持数据库信息
    }

    # 步骤11：yield 最终事件
    # 包含：最终响应、更新后的状态、工具调用记录
    yield "final", {
        "response": response,                   # Agent 的最终回答
        "updated_state": updated_state,         # 更新后的会话状态
        "needs_confirmation": needs_confirmation, # 是否需要确认
        "pending_action": pending_action,       # 待确认的操作
        "tool_calls": tool_calls_info,          # 工具调用记录
    }
