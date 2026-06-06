"""Process-global conversation memory.

The ``ConversationMemory`` node and the chat drivers share this store so
per-conversation history is *visible in the graph* (the node prepends it to the
prompt) yet still persists across the one-cook-per-message runs a driver makes —
a cook is otherwise stateless. Keyed by an opaque conversation id (Slack
``thread_ts`` / Telegram ``chat_id``).
"""
from __future__ import annotations

import threading

_LOCK = threading.Lock()
_TURNS: dict[str, list[tuple[str, str]]] = {}
# Hard cap per conversation so a long-lived process can't grow without bound;
# the node chooses how many of these to actually show via its ``max_turns``.
_HARD_CAP = 100


def turns(conversation: str) -> list[tuple[str, str]]:
    with _LOCK:
        return list(_TURNS.get(conversation, []))


def build_prompt(conversation: str, message: str, max_turns: int = 6) -> str:
    """Prefix the last ``max_turns`` turns of ``conversation`` before ``message``."""
    history = turns(conversation)
    if max_turns <= 0:
        history = []
    else:
        history = history[-max_turns:]
    if not history:
        return message
    prior = "\n".join(f"User: {u}\nAssistant: {a}" for u, a in history)
    return f"{prior}\nUser: {message}"


def record(conversation: str, user: str, assistant: str) -> None:
    """Append a completed (user, assistant) turn to ``conversation``."""
    if not conversation:
        return
    with _LOCK:
        history = _TURNS.setdefault(conversation, [])
        history.append((user, assistant))
        if len(history) > _HARD_CAP:
            del history[: len(history) - _HARD_CAP]


def reset() -> None:
    """Clear all history (used by tests)."""
    with _LOCK:
        _TURNS.clear()
