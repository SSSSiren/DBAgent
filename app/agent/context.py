"""
上下文构建 — 组装 Agent 输入所需的上下文信息

参考 DBAgent 的 app/agent/llm_agent.py 中的上下文构建逻辑
"""

from __future__ import annotations

from typing import Any


def build_context(session_state: dict[str, Any]) -> str:
    """
    根据会话状态构建上下文文本。

    策略：
    - 如果有对话摘要，作为第一条消息注入
    - 如果有对话历史，注入最近几轮对话
    - 如果存在已选数据库，添加数据库上下文

    Args:
        session_state: 会话状态，包含 chat_history、summary、selected_database 等

    Returns:
        上下文字符串（可直接注入到 prompt 中）
    """
    context_parts: list[str] = []

    # 1. 对话摘要（压缩后的早期对话）
    summary = session_state.get("summary", "")
    if summary:
        context_parts.append(f"[之前的对话摘要]\n{summary}")

    # 2. 最近对话历史（让 LLM 知道上一轮做了什么）
    chat_history = session_state.get("chat_history", [])
    if chat_history:
        # 取最近 4 条消息（2 轮对话），避免 prompt 过长
        recent = chat_history[-4:]
        history_lines = []
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                history_lines.append(f"用户: {content}")
            elif role == "assistant":
                # 截断过长的 assistant 回复（前 500 字符足够提供上下文）
                truncated = content[:500] + ("..." if len(content) > 500 else "")
                history_lines.append(f"助手: {truncated}")
        if history_lines:
            context_parts.append("[对话历史]\n" + "\n".join(history_lines))

    # 3. 已选数据库上下文
    selected_database = session_state.get("selected_database")
    selected_schema_id = session_state.get("selected_schema_id")
    if selected_database:
        schema_name = selected_database.get("schemaName", "未知")
        context_parts.append(
            f"当前选择的数据库: {schema_name} (schema_id={selected_schema_id})"
        )

    # 4. 长期记忆（来自 OpenViking）
    memories = session_state.get("_memories", [])
    if memories:
        memory_lines = ["[长期记忆 — 来自之前的对话]"]
        for m in memories[:10]:  # 最多注入 10 条记忆，避免 prompt 过长
            memory_lines.append(f"- {m['abstract']}")
        context_parts.append("\n".join(memory_lines))
        print(f"[KB] build_context: 注入 {len(memories[:10])} 条长期记忆到提示词")

    return "\n\n".join(context_parts) if context_parts else ""


def update_session_state(
    session_state: dict[str, Any],
    user_input: str,
    response: str,
    selected_database: dict[str, Any] | None = None,
    selected_schema_id: int | None = None,
) -> dict[str, Any]:
    """
    更新会话状态（在 Agent 返回结果后调用）。

    Args:
        session_state: 当前会话状态
        user_input: 用户输入
        response: Agent 最终响应
        selected_database: 更新后的数据库信息
        selected_schema_id: 更新后的 schema ID

    Returns:
        更新后的会话状态
    """
    # 更新对话历史
    chat_history = session_state.get("chat_history", [])
    chat_history.append({"role": "user", "content": user_input})
    chat_history.append({"role": "assistant", "content": response})

    # 保持最近 20 条消息
    if len(chat_history) > 20:
        chat_history = chat_history[-20:]

    # 更新数据库上下文
    current_schema_id = selected_schema_id or session_state.get("selected_schema_id")
    current_database = selected_database or session_state.get("selected_database")

    return {
        **session_state,
        "chat_history": chat_history,
        "selected_schema_id": current_schema_id,
        "selected_database": current_database,
    }


def extract_sql_from_text(text: str) -> str:
    """
    从文本中提取 SQL 语句。

    支持格式：
    - ```sql ... ```
    - ``` ... ```（包含 SQL 关键字时）
    """
    import re

    # 尝试匹配 ```sql ... ``` 格式
    match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        sql = match.group(1).strip()
        sql = sql.replace("\\n", " ").replace("\\r", "")
        sql = " ".join(sql.split())
        return sql

    # 尝试匹配 ``` ... ``` 格式（检查是否包含 SQL 关键字）
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        sql = match.group(1).strip()
        if any(
            keyword in sql.upper()
            for keyword in ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE"]
        ):
            sql = sql.replace("\\n", " ").replace("\\r", "")
            sql = " ".join(sql.split())
            return sql

    return ""