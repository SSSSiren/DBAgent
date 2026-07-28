"""
上下文构建 — 组装 Agent 输入所需的上下文信息

参考 DBAgent 的 app/agent/llm_agent.py 中的上下文构建逻辑
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Token estimation helper
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> tuple[int, str]:
    """Estimate the number of tokens in *text*.

    Uses ``tiktoken`` (cl100k_base) when available; falls back to a
    character-based heuristic ``len(text) / 4``, which is accurate to
    roughly ±10% for English text.

    Returns:
        (count, method) where method is ``"tiktoken"`` or ``"char_estimate"``.
    """
    # ── try tiktoken (sync, <1ms) ──
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), "tiktoken"
    except Exception:
        pass

    # ── fallback: character estimate ──
    return max(1, len(text) // 4), "char_estimate"


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def build_context(session_state: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """
    根据会话状态构建上下文文本。

    策略：
    - 如果有对话摘要，作为第一条消息注入
    - 如果有对话历史，注入最近几轮对话
    - 如果存在已选数据库，添加数据库上下文

    Args:
        session_state: 会话状态，包含 chat_history、summary、selected_database 等

    Returns:
        (context_str, ctx_tokens_dict) 的元组。
        ctx_tokens_dict 包含 8 段上下文的 Token 估算值，
        键名为各段名称（如 "summary", "chat_history" 等）。
        降级估算时额外包含 ``_method: "char_estimate"`` 标记。
    """
    context_parts: list[str] = []
    ctx_tokens: dict[str, int] = {}

    # 1. 对话摘要（压缩后的早期对话）
    summary = session_state.get("summary", "")
    _summary_text = ""
    if summary:
        _summary_text = f"[之前的对话摘要]\n{summary}"
        context_parts.append(_summary_text)
    count, method = _estimate_tokens(_summary_text)
    ctx_tokens["summary"] = count

    # 2. 最近对话历史（让 LLM 知道上一轮做了什么）
    chat_history = session_state.get("chat_history", [])
    _history_text = ""
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
            _history_text = "[对话历史]\n" + "\n".join(history_lines)
            context_parts.append(_history_text)
    ctx_tokens["chat_history"] = _estimate_tokens(_history_text)[0]

    # 3. 已选数据库上下文
    selected_database = session_state.get("selected_database")
    selected_schema_id = session_state.get("selected_schema_id")
    _db_text = ""
    if selected_database:
        schema_name = selected_database.get("schemaName", "未知")
        _db_text = f"当前选择的数据库: {schema_name} (schema_id={selected_schema_id})"
        context_parts.append(_db_text)
    ctx_tokens["selected_database"] = _estimate_tokens(_db_text)[0]

    # 4. 长期记忆（来自 OpenViking）
    memories = session_state.get("_memories", [])
    _memories_text = ""
    if memories:
        memory_lines = ["[长期记忆 — 来自之前的对话]"]
        for m in memories[:10]:  # 最多注入 10 条记忆，避免 prompt 过长
            memory_lines.append(f"- {m['abstract']}")
        _memories_text = "\n".join(memory_lines)
        context_parts.append(_memories_text)
        print(f"[KB] build_context: 注入 {len(memories[:10])} 条长期记忆到提示词")
    ctx_tokens["memories"] = _estimate_tokens(_memories_text)[0]

    # 5. SQL 参考知识库（RAG 检索结果，可信任的精确技术参考）
    rag_reference = session_state.get("_rag_reference", [])
    _rag_text = ""
    if rag_reference:
        rag_lines = ["[SQL 参考知识库 — 以下是你熟悉的数据库中已验证的 SQL 知识，包含真实的表名、字段名和常见取值，可以直接使用]"]
        for r in rag_reference[:5]:
            abstract = r.get("abstract", "")
            # 截断过长的参考内容
            if len(abstract) > 2000:
                abstract = abstract[:2000] + "..."
            rag_lines.append(f"- {abstract}")
        _rag_text = "\n".join(rag_lines)
        context_parts.append(_rag_text)
        print(f"[KB] build_context: 注入 {len(rag_reference[:5])} 条 RAG SQL 参考")
    ctx_tokens["rag_reference"] = _estimate_tokens(_rag_text)[0]

    # 6. 操作记忆（查询偏好）
    preferences = session_state.get("_preferences", [])
    _pref_text = ""
    if preferences:
        pref_lines = ["[操作记忆 — 查询偏好]"]
        for p in preferences:
            pref_lines.append(
                f"- {p['database_name']}.{p['table_name']}（查询 {p['query_count']} 次）"
            )
        _pref_text = "\n".join(pref_lines)
        context_parts.append(_pref_text)
    ctx_tokens["preferences"] = _estimate_tokens(_pref_text)[0]

    # 7. 数据底座（HDC）— 来自 app/datavault/retriever
    hdc_context = session_state.get("_hdc_context", "")
    _hdc_text = ""
    if hdc_context:
        _hdc_text = str(hdc_context)
        context_parts.append(_hdc_text)
    ctx_tokens["hdc_context"] = _estimate_tokens(_hdc_text)[0]

    # 8. SQL 历史记忆 — 相关历史查询
    sql_memories = session_state.get("_sql_memories", [])
    _sqlmem_text = ""
    if sql_memories:
        from app.config import get_settings
        settings = get_settings()
        budget = getattr(settings, "sql_memory_token_budget", 1500)

        mem_lines = [
            "[SQL 历史记忆 — 相关查询]",
            "以下是你或同事在此数据库上成功执行过的类似查询，可作为参考：",
            "",
        ]
        total_len = len("\n".join(mem_lines))
        entries = []

        for m in sql_memories:
            sql_text = m.get("sql_truncated", "") or m.get("sql_text", "")
            if len(sql_text) > 500:
                sql_text = sql_text[:500] + "..."

            # 安全过滤：排除写操作
            sql_upper = sql_text.upper()
            dangerous = any(
                kw in sql_upper
                for kw in ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "TRUNCATE ", "ALTER ", "CREATE "]
            )
            if dangerous:
                continue

            row_info = ""
            row_count = m.get("row_count")
            if row_count is not None:
                column_names = m.get("column_names", [])
                cols_str = ", ".join(column_names[:5]) if column_names else "?"
                row_info = f"**结果**: {row_count} 行，列: [{cols_str}]"

            entry = f"{len(entries) + 1}. **问题**: {m.get('question', '')}\n   **SQL**: {sql_text}"
            if row_info:
                entry += f"\n   {row_info}"

            if total_len + len(entry) + 2 > budget:
                break

            entries.append(entry)
            total_len += len(entry) + 1

        if entries:
            _sqlmem_text = "\n".join(mem_lines + entries)
            context_parts.append(_sqlmem_text)
            print(f"[SQLMem] build_context: 注入 {len(entries)} 条 SQL 记忆到提示词（共 {total_len} 字符，预算 {budget}）")
    ctx_tokens["sql_memories"] = _estimate_tokens(_sqlmem_text)[0]

    # Set _method marker based on actual estimation method used
    # (proxy: any non-empty text that came back with "char_estimate" means fallback)
    if method == "char_estimate":
        ctx_tokens["_method"] = "char_estimate"  # type: ignore[assignment]

    context_str = "\n\n".join(context_parts) if context_parts else ""
    return context_str, ctx_tokens


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