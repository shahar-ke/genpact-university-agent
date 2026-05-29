"""make_llm: builds the chat model from env without initializing a real provider."""

from unittest.mock import patch

from university_agent import llm


def test_make_llm_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    with patch.object(llm, "init_chat_model") as init:
        llm.make_llm()
    init.assert_called_once_with("claude-sonnet-4-6", model_provider="anthropic", temperature=0.2)


def test_make_llm_defaults(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_TEMPERATURE"):
        monkeypatch.delenv(var, raising=False)
    with patch.object(llm, "init_chat_model") as init:
        llm.make_llm()
    init.assert_called_once_with("gemma2:9b", model_provider="ollama", temperature=0.0)
