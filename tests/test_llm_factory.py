# tests/test_llm_factory.py
import pytest
from app.agent.llm_factory import get_chat_model


def test_get_chat_model_returns_chatopenai(monkeypatch):
    from langchain_openai import ChatOpenAI
    monkeypatch.setenv("LLM_BASE_URL", "http://fake:8000/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-flash-260425")
    # 重置单例
    from app.agent import llm_factory
    llm_factory._chat_model = None
    model = get_chat_model()
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-v4-flash-260425"
