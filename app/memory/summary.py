"""
对话记忆管理 - 摘要压缩

职责：
1. 维护对话摘要（summary），用于跨请求的上下文保持
2. 调用 LLM 将对话历史压缩为简洁摘要（不超过 500 字）
3. 在上下文过长时提供降级策略（简单截断）

记忆策略：
  完整历史（最近 20 条） + 压缩摘要（更早的对话）
  ↓
  下次请求时注入到 Agent 的输入中：
  "对话摘要: ...\n\n用户问题: ..."
"""

from typing import Any
from app.agent.llm import get_llm
from langchain_core.prompts import ChatPromptTemplate


# 摘要生成提示词
# 使用 ChatPromptTemplate 定义模板，{chat_history} 和 {current_summary} 是占位符
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

    职责：
    1. 将本轮对话（用户输入 + AI 回答）追加到摘要中
    2. 如果是首次对话（无历史摘要），直接返回对话内容
    3. 如果有历史摘要，调用 LLM 将新对话压缩进旧摘要
    4. 限制摘要长度不超过 500 字

    调用时机：
    在 llm_agent.py 的 run_agent_stream() 中，Agent 执行完成后调用

    参数：
        current_summary: 当前已有的摘要（可能为空）
        user_input: 用户本轮输入
        assistant_response: AI 本轮回答

    返回：
        更新后的摘要字符串（不超过 500 字）

    降级策略：
    如果 LLM 调用失败，使用简单拼接 + 截断的方式生成摘要
    """
    # 构建本轮对话历史文本
    chat_history = f"用户：{user_input}\n助手：{assistant_response}"

    # 首次对话：没有历史摘要，直接用本轮对话作为摘要
    if not current_summary:
        return chat_history

    # 有历史摘要：调用 LLM 将新对话压缩进旧摘要
    try:
        llm = get_llm()
        # 填充提示词模板
        prompt = SUMMARY_PROMPT.format(
            chat_history=chat_history,
            current_summary=current_summary,
        )
        # 调用 LLM 生成新摘要
        response = await llm.ainvoke(prompt)
        new_summary = response.content.strip()

        # 安全限制：确保摘要不超过 500 字
        if len(new_summary) > 500:
            new_summary = new_summary[:500]

        return new_summary
    except Exception as e:
        # 降级策略：LLM 调用失败时，简单拼接旧摘要 + 新对话
        # 取最后 500 字，避免无限增长
        combined = f"{current_summary}\n\n{chat_history}"
        if len(combined) > 500:
            combined = combined[-500:]
        return combined
