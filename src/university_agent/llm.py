"""Provider-agnostic chat-model factory.

Defaults to a local open-source model via Ollama. Switch to a commercial provider by
setting LLM_PROVIDER / LLM_MODEL (and installing that provider's package, e.g.
`uv pip install langchain-anthropic`). See the README.
"""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

DEFAULT_PROVIDER = "ollama"
# Balanced local default: strong at SQL + the NL understand/synthesize steps, ~5.4GB on a
# 16GB Mac. Alternatives: codegemma:7b (SQL-heavy), llama3.1:8b (generalist).
DEFAULT_MODEL = "gemma2:9b"


def make_llm() -> BaseChatModel:
    """Build the chat model from LLM_PROVIDER / LLM_MODEL / LLM_TEMPERATURE env vars."""
    provider = os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER)
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0"))
    return init_chat_model(model, model_provider=provider, temperature=temperature)
