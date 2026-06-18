from app.agent.llm import get_llm, is_llm_configured


async def update_summary(old_summary: str, user_input: str, assistant_response: str) -> str:
    """Compress conversation history into a short durable summary."""

    prompt = f"""将以下对话内容压缩为简洁的摘要，保留关键信息：

已有摘要：
{old_summary or "（无）"}

新对话：
用户：{user_input}
助手：{assistant_response[:500]}

要求：
1. 保留：已选数据库、表名、关键查询结果
2. 移除：具体 SQL、详细数据
3. 控制在 200 字以内

返回更新后的摘要：
"""
    try:
        if not is_llm_configured():
            raise RuntimeError("DeepSeek API key is not configured")
        response = await get_llm().ainvoke(prompt)
        return response.content[:500]
    except Exception:
        merged = f"{old_summary} 用户问：{user_input}；助手答：{assistant_response[:120]}"
        return merged.strip()[:200]
