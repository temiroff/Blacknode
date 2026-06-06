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
import os
import re
from typing import Any, Mapping

from blacknode import conversation_state
from blacknode.integrations.registry import DriverSpec, register_driver
from blacknode.providers.keys import secret
from blacknode.workflow import run_workflow


def describe_command(workflow: Mapping[str, Any], text: str) -> str | None:
    """Answer a ``/command`` from the live graph (no LLM). Returns None if not a command."""
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return None
    cmd = stripped[1:].split()[0].split("@")[0].lower() if len(stripped) > 1 else ""
    node_meta = workflow.get("node_meta") or {}
    metas = [m for m in node_meta.values() if isinstance(m, Mapping)]

    if cmd in ("tools", "tool"):
        tools = []
        for m in metas:
            params = m.get("params") or {}
            if m.get("type") == "PythonFn":
                tools.append((str(params.get("name") or params.get("label") or "(unnamed)"),
                              str(params.get("description") or "")))
            elif m.get("type") == "SubnetAsTool":
                tools.append((str(params.get("name") or "subnet_tool"),
                              str(params.get("description") or "")))
        if not tools:
            return "No tools are wired into this graph."
        lines = ["🛠 Tools the agent can use:"]
        lines += [f"• {n}" + (f" — {d}" if d else "") for n, d in tools]
        return "\n".join(lines)

    if cmd in ("model", "models"):
        models = [str((m.get("params") or {}).get("value"))
                  for m in metas if m.get("type") == "Model" and (m.get("params") or {}).get("value")]
        return "🧠 Model: " + ", ".join(models) if models else "No Model node found in this graph."

    if cmd in ("graph", "nodes"):
        counts: dict[str, int] = {}
        for m in metas:
            counts[str(m.get("type"))] = counts.get(str(m.get("type")), 0) + 1
        lines = [f"📊 Graph: {len(metas)} nodes"]
        lines += [f"• {c}× {t}" for t, c in sorted(counts.items())]
        return "\n".join(lines)

    if cmd in ("help", "start"):
        return (
            "I'm a Blacknode agent. Just message me to chat. Commands:\n"
            "/tools — tools I can use\n"
            "/model — the model I'm running\n"
            "/graph — a summary of my node graph"
        )
    return f"Unknown command /{cmd}. Try /help."


def _has_memory_node(workflow: Mapping[str, Any]) -> bool:
    node_meta = workflow.get("node_meta") or {}
    return any(
        isinstance(m, Mapping) and m.get("type") == "ConversationMemory"
        for m in node_meta.values()
    )


def _memory_enabled(workflow: Mapping[str, Any]) -> bool:
    node_meta = workflow.get("node_meta") or {}
    for meta in node_meta.values():
        if isinstance(meta, Mapping) and meta.get("type") == "ConversationMemory":
            params = meta.get("params") or {}
            try:
                return int(params.get("max_turns", 6)) > 0
            except (TypeError, ValueError):
                return True
    return False


def _run_graph(workflow: Mapping[str, Any]) -> str:
    """Cook the workflow and return the reply text.

    When the editor is reachable (``BLACKNODE_SYNC_URL`` set — the editor-server
    sets it for bots it launches), cook through the live-sync path so the editor
    animates the **real** run on the canvas, node by node, for this message.
    Otherwise (e.g. run from a bare terminal) cook headless.
    """
    sync_url = os.environ.get("BLACKNODE_SYNC_URL", "")
    if sync_url:
        try:
            from blacknode.live_sync import run_graph_live
            from blacknode.workflow import graph_from_workflow, infer_entrypoint

            node_id, port = infer_entrypoint(workflow)
            graph = graph_from_workflow(workflow)
            # workflow omitted → animate the already-open graph, no new tab.
            return _stringify(run_graph_live(graph, node_id, port, editor_url=sync_url))
        except Exception:
            pass  # editor unreachable / sync failed → fall back to a headless run
    return _stringify(run_workflow(workflow).get("value"))

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")

# Cosmetic chat-message nodes a driver injects into. Their inbound text lands on
# the ``text`` param (a plain Text node uses ``value``). Shared so every driver
# (Slack, Telegram, …) detects the same family.
_MESSAGE_NODE_TYPES = {"SlackMessage", "TelegramMessage"}


class DriverDependencyError(RuntimeError):
    """Raised when a driver's optional packages are not installed."""


class SlackDependencyError(DriverDependencyError):
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

    Prefers an explicit ``SlackMessage`` node, then the node feeding an agent's
    ``prompt`` port, then a node named ``task``. Raises :class:`SlackConfigError`
    if none is found.
    """
    node_meta = workflow.get("node_meta") or {}
    for node_id, meta in node_meta.items():
        if isinstance(meta, Mapping) and meta.get("type") in _MESSAGE_NODE_TYPES:
            return str(node_id)
    for edge in workflow.get("edges") or []:
        if edge.get("to_port") == "prompt":
            source = edge.get("from")
            if source in node_meta:
                return str(source)
    if "task" in node_meta:
        return "task"
    raise SlackConfigError(
        "Could not find an input node. Pass --input-node with the id of the "
        "SlackMessage (or Text) node that feeds the agent's prompt."
    )


def inject_input(
    workflow: Mapping[str, Any],
    input_node: str,
    text: str,
    *,
    fields: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``workflow`` with the Slack message written into ``input_node``.

    The message text goes to ``text`` on a ``SlackMessage`` node, else ``value``
    on a plain Text node. Optional ``fields`` (``user_id`` / ``channel`` /
    ``thread_ts``) are set only when the node actually declares them, so
    downstream nodes can read the conversation metadata.
    """
    node_meta = workflow.get("node_meta") or {}
    if input_node not in node_meta:
        raise SlackConfigError(f"Input node '{input_node}' is not in the workflow.")
    clone = copy.deepcopy(dict(workflow))
    node = clone["node_meta"][input_node]
    params = dict(node.get("params") or {})
    prompt_field = "text" if node.get("type") in _MESSAGE_NODE_TYPES else "value"
    params[prompt_field] = text
    if fields:
        declared = set(node.get("outputs") or []) | set(node.get("inputs") or [])
        for key, value in fields.items():
            if key != prompt_field and key in declared:
                params[key] = value
    node["params"] = params
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
        # If the graph carries a ConversationMemory node, memory is visible there:
        # the node prepends history, and we record completed turns to the shared
        # store instead of the driver's private memory.
        self.memory_node = _has_memory_node(self.workflow)

    def _live_workflow(self) -> dict[str, Any]:
        """Fetch the editor's *current* graph so edits take effect per-message.

        When launched by the editor (``BLACKNODE_SYNC_URL`` set), each message
        cooks the graph as it is **right now** — change a wire and the next
        message cooks the new shape, no restart. Falls back to the graph the
        driver was started with if the editor isn't reachable.
        """
        url = os.environ.get("BLACKNODE_SYNC_URL", "")
        if url:
            try:
                import json as _json
                import urllib.request as _ur

                with _ur.urlopen(url.rstrip("/") + "/drivers/workflow", timeout=5) as r:
                    wf = _json.loads(r.read().decode("utf-8"))
                if isinstance(wf, dict) and wf.get("node_meta"):
                    return wf
            except Exception:
                pass
        return self.workflow

    def command_reply(self, text: str) -> str | None:
        """If ``text`` is a ``/command``, answer it from the live graph; else None."""
        if not (text or "").strip().startswith("/"):
            return None
        return describe_command(self._live_workflow(), text)

    def handle_message(
        self,
        text: str,
        conv_id: str,
        *,
        user_id: str = "",
        channel: str = "",
        fields: Mapping[str, str] | None = None,
    ) -> str:
        """Run one message through the workflow, keyed by ``conv_id`` for memory.

        ``conv_id`` is the conversation key — Slack ``thread_ts`` or Telegram
        ``chat_id``. ``fields`` lets a transport pass its own metadata ports
        (e.g. Telegram ``chat_id`` / ``message_id``); when omitted, the Slack
        shape (``user_id`` / ``channel`` / ``thread_ts``) is used.
        """
        message = strip_mention(text)
        # Cook the editor's CURRENT graph (so edits take effect without restart);
        # the data connections decide what gets cooked — no special trigger wire.
        workflow = self._live_workflow()
        try:
            input_node = detect_input_node(workflow)
        except SlackConfigError:
            input_node = self.input_node
        has_memory = _has_memory_node(workflow)
        # With a memory node, inject the raw message — the node prepends history.
        # Without one, the driver prepends here, as before.
        prompt = message if has_memory else self.memory.build_prompt(conv_id, message)
        if fields is None:
            fields = {"user_id": user_id, "channel": channel, "thread_ts": conv_id}
        workflow = inject_input(workflow, input_node, prompt, fields=fields)
        reply = _run_graph(workflow)
        if message.strip() and reply.strip():
            if has_memory and _memory_enabled(workflow):
                conversation_state.record(conv_id, message, reply)
            elif not has_memory:
                self.memory.add(conv_id, message, reply)
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

    import json as _json
    import urllib.request as _ur

    from blacknode.integrations.status import DriverStatus

    def _bot_label() -> str:
        try:
            req = _ur.Request(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {bot_token}"}, method="POST",
            )
            with _ur.urlopen(req, timeout=8) as r:
                data = _json.load(r)
                return "@" + str(data.get("user")) if data.get("ok") else ""
        except Exception:
            return ""

    label = _bot_label()
    app = App(token=bot_token)
    status = DriverStatus("slack", str(runtime.workflow.get("name") or ""), label=label).start()

    @app.event("app_mention")
    def _on_mention(event: dict, say: Any) -> None:  # pragma: no cover - needs live Slack
        thread = event.get("thread_ts") or event.get("ts")
        print(f"[slack] <- channel {event.get('channel')}: {str(event.get('text',''))!r}", flush=True)
        # Graph-introspection commands (/tools, /model, /graph) answer directly.
        command = runtime.command_reply(strip_mention(event.get("text", "")))
        if command is not None:
            say(text=command, thread_ts=thread)
            return
        status.mark_processing()
        # The graph drives the send: cooking the reply node posts the answer.
        # The driver only reports errors that prevented a reply.
        try:
            reply = runtime.handle_message(
                event.get("text", ""),
                thread,
                user_id=event.get("user", ""),
                channel=event.get("channel", ""),
            )
            print(f"[slack] -> sent reply: {str(reply)[:80]!r}", flush=True)
        except Exception as exc:  # noqa: BLE001 - never let one message kill the bot
            print(f"[slack] !! error: {type(exc).__name__}: {exc}", flush=True)
            say(text=f"[error] {type(exc).__name__}: {exc}", thread_ts=thread)
        status.mark_listening()

    print(f"[slack] connected as {label or '(unknown)'} — listening for @mentions", flush=True)
    try:
        SocketModeHandler(app, app_token).start()
    finally:
        status.stop()


# A transport-agnostic alias: the runtime knows nothing about Slack, so future
# drivers (Discord, HTTP, …) reuse it directly.
AgentRuntime = SlackAgentRuntime


def _run_slack(runtime: SlackAgentRuntime) -> None:
    serve(
        runtime,
        bot_token=secret("SLACK_BOT_TOKEN"),
        app_token=secret("SLACK_APP_TOKEN"),
    )


register_driver(
    DriverSpec(
        name="slack",
        description="Slack bot (Socket Mode): answers @mentions with the agent workflow.",
        run=_run_slack,
        required_extra="slack",
        required_packages=("slack_bolt", "slack_sdk"),
        required_env=("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"),
    )
)
