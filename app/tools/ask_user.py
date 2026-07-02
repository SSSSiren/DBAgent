"""
ask_user 工具 — 向用户提问，获取更多信息

参考 DBAgent 的 app/tools/agent_tools.py:ask_user_tool
"""


async def ask_user(question: str) -> str:
    """向用户提问，获取更多信息。

    参数:
        question: 清晰明确的问题

    返回:
        用户回答的占位符

    使用场景:
        - 信息不足，需要用户补充
        - 存在歧义，需要用户选择（如多个数据库候选、多个表名相似）
        - 需要用户确认重要操作

    注意:
        这个工具的实际执行需要 Agent 框架支持暂停和恢复。
        当前返回占位符，实际的问答逻辑在 Agent 循环中处理。
    """
    return f"[需要用户回答] 问题：{question}"