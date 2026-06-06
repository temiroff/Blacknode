"""Chat I/O nodes — the visible endpoints of a conversation-driven graph.

The graph itself does the work: ``[SlackMessage] -> [ConversationMemory] ->
[AgentLoop] -> [SlackReply]``. A chat *driver* only owns the event loop — it
fills the message node with the inbound event and cooks the **reply** node.
Cooking the reply pulls the whole graph behind it (memory → agent → tools), and
the **reply node sends the answer itself** (Slack/Telegram HTTP API). The driver
no longer posts; it just listens and kicks the reply.

Sending is gated on a real destination (``channel`` / ``chat_id``) plus an
available token, so cooking in the editor without a live conversation does
nothing — the graph stays safe to run and test.
"""
from __future__ import annotations

import json
import urllib.request

from blacknode import conversation_state
from blacknode.node import node
from blacknode.providers.keys import secret


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 12) -> bool:
    data = json.dumps(payload).encode("utf-8")
    head = {"Content-Type": "application/json"}
    head.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=head, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except Exception:
        return False


def _telegram_send(chat_id: str, text: str, message_id: str = "") -> bool:
    token = secret("TELEGRAM_BOT_TOKEN")
    if not (token and chat_id and text):
        return False
    payload: dict = {"chat_id": chat_id, "text": text}
    if message_id.isdigit():
        payload["reply_to_message_id"] = int(message_id)
    return _post_json(f"https://api.telegram.org/bot{token}/sendMessage", payload)


def _slack_send(channel: str, text: str, thread_ts: str = "") -> bool:
    token = secret("SLACK_BOT_TOKEN")
    if not (token and channel and text):
        return False
    payload: dict = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return _post_json(
        "https://slack.com/api/chat.postMessage", payload,
        headers={"Authorization": f"Bearer {token}"},
    )


@node(
    inputs=["message:Text", "conversation:Text", "max_turns:Int=6"],
    outputs=["prompt:Text", "conversation:Text"],
    name="ConversationMemory",
    category="Integrations",
)
def conversation_memory(ctx: dict) -> dict:
    """Per-conversation chat memory, made visible in the graph.

    Wire the incoming ``message`` and a ``conversation`` key (Slack ``thread_ts``
    / Telegram ``chat_id``) in; the node prepends the last ``max_turns`` turns
    and outputs the combined ``prompt`` for the agent. History persists in a
    process-global store (see :mod:`blacknode.conversation_state`); the driver
    records each completed turn after the agent answers.
    """
    conversation = str(ctx.get("conversation", ""))
    message = str(ctx.get("message", ""))
    max_turns = int(ctx.get("max_turns", 6) or 0)
    prompt = conversation_state.build_prompt(conversation, message, max_turns)
    return {"prompt": prompt, "conversation": conversation}


@node(
    inputs=[],
    outputs=["text:Text", "user_id:Text", "channel:Text", "thread_ts:Text"],
    name="SlackMessage",
    category="Integrations",
)
def slack_message(ctx: dict) -> dict:
    """Inbound Slack message.

    The driver fills these from the live event before each cook; the same params
    double as sample values for a manual editor run.
    """
    return {
        "text": str(ctx.get("text", "")),
        "user_id": str(ctx.get("user_id", "")),
        "channel": str(ctx.get("channel", "")),
        "thread_ts": str(ctx.get("thread_ts", "")),
    }


@node(
    inputs=["text:Text", "channel:Text", "thread_ts:Text", "user_id:Text"],
    outputs=["text:Text", "channel:Text", "thread_ts:Text", "user_id:Text"],
    name="SlackReply",
    category="Integrations",
)
def slack_reply(ctx: dict) -> dict:
    """Outbound Slack reply — **sends** the message when cooked.

    Cooking this node posts ``text`` to ``channel`` (in ``thread_ts``) via the
    Slack API, using the bot token from the key store. ``channel`` / ``thread_ts``
    / ``user_id`` come wired from the ``SlackMessage`` node. Sending is gated on a
    real ``channel`` + token, so cooking in the editor without a live thread does
    nothing.
    """
    text = str(ctx.get("text", ""))
    channel = str(ctx.get("channel", ""))
    thread_ts = str(ctx.get("thread_ts", ""))
    _slack_send(channel, text, thread_ts)
    return {
        "text": text,
        "channel": channel,
        "thread_ts": thread_ts,
        "user_id": str(ctx.get("user_id", "")),
    }


@node(
    inputs=[],
    outputs=["text:Text", "user_id:Text", "chat_id:Text", "message_id:Text"],
    name="TelegramMessage",
    category="Integrations",
)
def telegram_message(ctx: dict) -> dict:
    """Inbound Telegram message.

    The driver fills these from the live update before each cook; the same params
    double as sample values for a manual editor run. (Telegram keys a
    conversation by ``chat_id``, the way Slack keys by ``thread_ts``.)
    """
    return {
        "text": str(ctx.get("text", "")),
        "user_id": str(ctx.get("user_id", "")),
        "chat_id": str(ctx.get("chat_id", "")),
        "message_id": str(ctx.get("message_id", "")),
    }


@node(
    inputs=["text:Text", "chat_id:Text", "user_id:Text", "message_id:Text"],
    outputs=["text:Text", "chat_id:Text", "user_id:Text", "message_id:Text"],
    name="TelegramReply",
    category="Integrations",
)
def telegram_reply(ctx: dict) -> dict:
    """Outbound Telegram reply — **sends** the message when cooked.

    Cooking this node posts ``text`` to ``chat_id`` (as a reply to ``message_id``)
    via the Telegram API, using the bot token from the key store. ``chat_id`` /
    ``user_id`` / ``message_id`` come wired from the ``TelegramMessage`` node.
    Sending is gated on a real ``chat_id`` + token, so cooking in the editor
    without a live chat does nothing.
    """
    text = str(ctx.get("text", ""))
    chat_id = str(ctx.get("chat_id", ""))
    message_id = str(ctx.get("message_id", ""))
    _telegram_send(chat_id, text, message_id)
    return {
        "text": text,
        "chat_id": chat_id,
        "user_id": str(ctx.get("user_id", "")),
        "message_id": message_id,
    }
