from __future__ import annotations
import json
import os
import re
from typing import Any
from .base import BaseProvider, CompletionResponse, ToolCall, ToolDef, ToolResult


_CONTEXT_LENGTH_RE = re.compile(
    r"maximum context length is\s+(\d+)\s+tokens.*?"
    r"requested\s+(\d+)\s+tokens\s+\((\d+)\s+in the messages,\s+(\d+)\s+in the completion\)",
    re.IGNORECASE | re.DOTALL,
)


def _context_safe_max_tokens(exc: Exception, requested_max_tokens: int) -> int | None:
    match = _CONTEXT_LENGTH_RE.search(str(exc))
    if not match:
        return None

    context_limit = int(match.group(1))
    message_tokens = int(match.group(3))
    room = context_limit - message_tokens - 16
    if room <= 0:
        raise ValueError(
            f"Prompt uses {message_tokens} tokens, but this model only has a "
            f"{context_limit} token context window."
        ) from exc

    safe_max_tokens = min(requested_max_tokens, room)
    return safe_max_tokens if safe_max_tokens < requested_max_tokens else None


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
        max_tokens: int = 1024,
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

        try:
            resp = self._client.chat.completions.create(**call_kwargs)
        except Exception as exc:
            safe_max_tokens = _context_safe_max_tokens(exc, max_tokens)
            if safe_max_tokens is None:
                raise
            call_kwargs["max_tokens"] = safe_max_tokens
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

    def tool_result_messages(
        self,
        assistant_text: str,
        tool_calls: list[ToolCall],
        tool_results: list[ToolResult],
    ) -> list[dict]:
        return [
            {
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in tool_calls
                ],
            },
            *[
                {
                    "role": "tool",
                    "tool_call_id": r.tool_call_id,
                    "name": r.name,
                    "content": r.output,
                }
                for r in tool_results
            ],
        ]
