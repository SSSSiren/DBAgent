"""User interaction tool for ReAct agent."""

from langchain.tools import Tool


def ask_user(question: str) -> str:
    """Ask user for clarification or additional information.

    This tool is used when the agent needs more information from the user
    to proceed with the task. The agent should provide a clear, specific
    question that helps resolve ambiguity or gather missing details.

    Args:
        question: The question to ask the user

    Returns:
        A placeholder response. The actual user response will be handled
        by the agent loop which will pause execution and wait for user input.
    """
    # This is a placeholder - the actual response comes from the user
    # The agent loop will handle the interaction
    return f"[Waiting for user response to: {question}]"


# Create the tool instance
ask_user_tool = Tool(
    name="ask_user",
    description="Ask user for clarification or additional information. Use when you need more details to proceed.",
    func=ask_user,
)
