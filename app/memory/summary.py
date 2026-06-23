"""
对话记忆管理 - 摘要压缩
"""

from typing import Any
from app.agent.llm import get_llm
from langchain_core.prompts import ChatPromptTemplate


SUMMARY_PROMPT = ChatPromptTemplate.from_template("""
请将以下对话历史压缩成简洁的摘要，保留关键信息：
- 用户选择的数据库和表
- 执行过的查询及其结果概要
- 重要的上下文信息

对话历史：
{chat_history}

当前摘要：
{current_summary}

请生成更新后的摘要（不超过 500 字）：
""")


async def update_summary(
    current_summary: str,
    user_input: str,
    assistant_response: str,
) -> str:
    """
    更新对话摘要

    Args:
        current_summary: 当前摘要
        user_input: 用户输入
        assistant_response: 助手响应

    Returns:
        更新后的摘要
    """
    # 构建对话历史
    chat_history = f"用户：{user_input}\n助手：{assistant_response}"

    # 如果当前摘要为空，直接返回对话历史
    if not current_summary:
        return chat_history

    # 调用 LLM 压缩摘要
    try:
        llm = get_llm()
        prompt = SUMMARY_PROMPT.format(
            chat_history=chat_history,
            current_summary=current_summary,
        )
        response = await llm.ainvoke(prompt)
        new_summary = response.content.strip()

        # 限制长度
        if len(new_summary) > 500:
            new_summary = new_summary[:500]

        return new_summary
    except Exception as e:
        # 如果 LLM 调用失败，简单拼接
        combined = f"{current_summary}\n\n{chat_history}"
        if len(combined) > 500:
            combined = combined[-500:]
        return combined
