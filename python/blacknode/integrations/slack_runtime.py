"""Run any Blacknode agent workflow as a Slack bot.

Slack is a **driver**, not a set of graph nodes. Blacknode's cook is synchronous
and pull-based; a webhook is push-based and long-lived. So this module owns the
Slack event loop and runs one ``run_workflow`` per incoming message — the same
way the CLI ``run`` and the editor ``/cook`` are drivers around the same engine.

```
blacknode slack templates/slack-nim-agent.json
  └─ Bolt (Socket Mode) owns the event loop
  └─ per-thread ConversationMemory keyed by thread_ts
  └─ each message: inject text into the workflow's input node → run_workflow → reply in thread
```

The graph itself stays a plain ``[Text] → [AgentLoop(nim)] → [ToolBox] → [Output]``
— nothing here changes the execution model. Pure logic (memory, input
injection, message handling) is importable and testable without ``slack_bolt``;
only :func:`serve` needs it, imported lazily with a clear install hint.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from blacknode.workflow import run_workflow

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")


class SlackDependencyError(RuntimeError):
    """Raised when slack_bolt / slack_sdk are not installed."""


class SlackConfigError(RuntimeError):
    """Raised when the workflow has no usable input node."""


class ConversationMemory:
    """Per-thread rolling history, keyed by Slack ``thread_ts``."""

    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max(0, int(max_turns))
        self._threads: dict[str, list[tuple[str, str]]] = {}

    def history(self, thread: str) -> list[tuple[str, str]]:
        return list(self._threads.get(thread, []))

    def add(self, thread: str, user: str, assistant: str) -> None:
        if self.max_turns == 0:
            return
        turns = self._threads.setdefault(thread, [])
        turns.append((user, assistant))
        if len(turns) > self.max_turns:
            del turns[: len(turns) - self.max_turns]

    def build_prompt(self, thread: str, message: str) -> str:
        """Prefix prior turns so the agent has thread context in its single prompt."""
        turns = self.history(thread)
        if not turns:
            return message
        prior = "\n".join(f"User: {user}\nAssistant: {assistant}" for user, assistant in turns)
        return f"{prior}\nUser: {message}"


def detect_input_node(workflow: Mapping[str, Any]) -> str:
    """Find the node whose value should be replaced with the Slack message.

    Prefers the node feeding an agent's ``prompt`` port; falls back to a node
    named ``task``. Raises :class:`SlackConfigError` if neither is found.
    """
    node_meta = workflow.get("node_meta") or {}
    for edge in workflow.get("edges") or []:
        if edge.get("to_port") == "prompt":
            source = edge.get("from")
            if source in node_meta:
                return str(source)
    if "task" in node_meta:
        return "task"
    raise SlackConfigError(
        "Could not find an input node. Pass --input-node with the id of the Text "
        "node that feeds the agent's prompt."
    )


def inject_input(workflow: Mapping[str, Any], input_node: str, text: str) -> dict[str, Any]:
    """Return a copy of ``workflow`` with ``input_node``'s value set to ``text``."""
    node_meta = workflow.get("node_meta") or {}
    if input_node not in node_meta:
        raise SlackConfigError(f"Input node '{input_node}' is not in the workflow.")
    clone = copy.deepcopy(dict(workflow))
    params = dict(clone["node_meta"][input_node].get("params") or {})
    params["value"] = text
    clone["node_meta"][input_node]["params"] = params
    return clone


def _stringify(value: Any) -> str:
    if value is None:
        return "(no output)"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("result", "text", "value", "output", "answer"):
            if isinstance(value.get(key), str):
                return value[key]
    return str(value)


def strip_mention(text: str) -> str:
    """Remove the ``<@U…>`` bot mention(s) an app_mention event carries."""
    return _MENTION_RE.sub("", str(text or "")).strip()


class SlackAgentRuntime:
    """Drives one workflow per Slack message, with per-thread memory."""

    def __init__(
        self,
        workflow: Mapping[str, Any],
        *,
        input_node: str | None = None,
        memory: ConversationMemory | None = None,
    ) -> None:
        self.workflow = dict(workflow)
        self.input_node = input_node or detect_input_node(self.workflow)
        self.memory = memory or ConversationMemory()

    def handle_message(self, text: str, thread_ts: str) -> str:
        message = strip_mention(text)
        prompt = self.memory.build_prompt(thread_ts, message)
        result = run_workflow(inject_input(self.workflow, self.input_node, prompt))
        reply = _stringify(result.get("value"))
        self.memory.add(thread_ts, message, reply)
        return reply


def serve(runtime: SlackAgentRuntime, *, bot_token: str, app_token: str) -> None:
    """Start a Socket Mode Slack app that answers app_mentions via ``runtime``.

    Socket Mode needs no public webhook: a bot token (``xoxb-``) and an
    app-level token (``xapp-``, with ``connections:write``) are enough.
    """
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SlackDependencyError(
            "slack_bolt is not installed. Run: pip install 'blacknode[slack]'"
        ) from exc

    app = App(token=bot_token)

    @app.event("app_mention")
    def _on_mention(event: dict, say: Any) -> None:  # pragma: no cover - needs live Slack
        thread = event.get("thread_ts") or event.get("ts")
        try:
            reply = runtime.handle_message(event.get("text", ""), thread)
        except Exception as exc:  # noqa: BLE001 - never let one message kill the bot
            reply = f"[error] {type(exc).__name__}: {exc}"
        say(text=reply, thread_ts=thread)

    SocketModeHandler(app, app_token).start()
