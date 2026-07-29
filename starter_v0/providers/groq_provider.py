from __future__ import annotations

import os

from providers.openai_provider import OpenAIProvider


class GroqProvider(OpenAIProvider):
    """Groq exposes an OpenAI-compatible Chat Completions surface."""

    def __init__(self) -> None:
        super().__init__(
            api_key_env="GROQ_API_KEY",
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            # llama-3.3-70b-versatile intermittently emits `<function=name,{...}>`
            # pseudo-syntax that Groq rejects with 400 tool_use_failed; gpt-oss-120b
            # uses native tool calling and does not.
            default_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        )
