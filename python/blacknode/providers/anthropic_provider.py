from __future__ import annotations
import os
from typing import Any
from .base import BaseProvider, CompletionResponse, ToolCall, ToolDef


class AnthropicProvider(BaseProvider):
    def __init__(self, api_key: str | None = None):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

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
        call_kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            temperature=temperature,
        )
        if system:
            call_kwargs["system"] = system
        if tools:
            call_kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        resp = self._client.messages.create(**call_kwargs)

        text = ""
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

        stop_map = {"end_turn": "end_turn", "tool_use": "tool_use", "max_tokens": "length"}
        stop_reason = stop_map.get(resp.stop_reason, "end_turn")
        return CompletionResponse(text=text, tool_calls=tool_calls, stop_reason=stop_reason)

    # raw content block list for AgentLoop multi-turn continuations
    def _raw_content(self, messages, **kw):
        return self._client.messages.create(messages=messages, **kw).content
