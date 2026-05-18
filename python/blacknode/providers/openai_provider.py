from __future__ import annotations
import json
import os
from typing import Any
from .base import BaseProvider, CompletionResponse, ToolCall, ToolDef


class OpenAIProvider(BaseProvider):
    """Covers OpenAI, Ollama, LM Studio, llama.cpp — anything with an OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", "sk-local"),
            base_url=base_url,
        )

    def complete(
        self,
        messages: list[dict],
        *,
        model: str,
        system: str = "",
        max_tokens: int = 4096,
        tools: list[ToolDef] | None = None,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> CompletionResponse:
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        call_kwargs: dict[str, Any] = dict(
            model=model,
            messages=all_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if tools:
            call_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            call_kwargs["tool_choice"] = "auto"

        resp = self._client.chat.completions.create(**call_kwargs)
        choice = resp.choices[0]
        msg = choice.message

        text = msg.content or ""
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        finish = choice.finish_reason
        stop_reason = "tool_use" if finish == "tool_calls" else ("length" if finish == "length" else "end_turn")
        return CompletionResponse(text=text, tool_calls=tool_calls, stop_reason=stop_reason)
