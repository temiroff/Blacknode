from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderConfigError(RuntimeError):
    """Raised when a provider cannot run because required local settings are missing."""


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    output: str


@dataclass
class CompletionResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    # normalised: "end_turn" | "tool_use" | "length" | "stop"
    stop_reason: str = "end_turn"


class BaseProvider(ABC):
    """Uniform interface over any LLM backend."""

    @abstractmethod
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
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"

    def tool_result_messages(
        self,
        assistant_text: str,
        tool_calls: list[ToolCall],
        tool_results: list[ToolResult],
    ) -> list[dict]:
        results = "\n".join(f"[{r.name} result]: {r.output}" for r in tool_results)
        return [
            {"role": "assistant", "content": assistant_text or "[tool use]"},
            {"role": "user", "content": results},
        ]
