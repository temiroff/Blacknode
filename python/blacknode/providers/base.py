from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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
        max_tokens: int = 4096,
        tools: list[ToolDef] | None = None,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> CompletionResponse:
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
