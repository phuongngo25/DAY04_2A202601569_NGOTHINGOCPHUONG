from __future__ import annotations

import json
import os
import time
from typing import Any

from providers.base import ModelResponse, ToolCall


# Some OpenAI-compatible backends reject a response when the model emits its own
# pseudo-syntax instead of a real tool call (Groq: 400 tool_use_failed). That is a
# serialization failure in the provider, not a routing decision by the agent, so it
# must be retried — otherwise run_eval scores the case as provider_error and it drops
# out of measured_cases entirely.
_RETRYABLE_MARKERS = ("tool_use_failed", "429", "rate_limit", "overloaded", "503", "502")
_MAX_RETRIES = int(os.getenv("OPENAI_COMPAT_MAX_RETRIES", "3"))


def _is_retryable(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


class OpenAIProvider:
    """OpenAI Chat Completions provider with normalized tool_calls output."""

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        default_model: str = "gpt-4o-mini",
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url = base_url
        self.default_model = default_model

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live provider dependency first: pip install openai") from exc

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        client = OpenAI(api_key=api_key, base_url=self.base_url)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                if attempt >= _MAX_RETRIES or not _is_retryable(exc):
                    raise
                # A bit-identical retry can re-sample the same broken generation, so
                # nudge temperature off zero from the second attempt onward.
                if attempt >= 1:
                    kwargs["temperature"] = max(temperature, 0.1) + 0.1 * attempt
                time.sleep(2 * (attempt + 1))

        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for call in msg.tool_calls or []:
            args = json.loads(call.function.arguments or "{}")
            calls.append(ToolCall(name=call.function.name, args=args))
        return ModelResponse(text=msg.content, tool_calls=calls, raw=resp)
