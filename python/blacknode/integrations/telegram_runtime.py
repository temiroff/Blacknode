"""Run any Blacknode agent workflow as a Telegram bot.

Like Slack, Telegram is a **driver**, not graph nodes: the cook is synchronous
and pull-based, so this module owns the long-poll loop and runs one
``run_workflow`` per incoming message. It reuses the transport-neutral
:class:`~blacknode.integrations.slack_runtime.AgentRuntime` (memory + input
injection); only the transport here is Telegram-specific.

```
blacknode telegram templates/telegram-nim-agent.json
  └─ python-telegram-bot long-polls getUpdates (no public URL needed)
  └─ injects text, photos, and Telegram IDs into TelegramMessage
  └─ cooks the current graph; TelegramReply sends text or a photo
  └─ optional per-chat ConversationMemory keyed by chat_id
```
"""
from __future__ import annotations

from blacknode.integrations.registry import DriverSpec, register_driver
from blacknode.integrations.slack_runtime import AgentRuntime, DriverDependencyError
from blacknode.providers.keys import secret


class TelegramDependencyError(DriverDependencyError):
    """Raised when python-telegram-bot is not installed."""


def serve(runtime: AgentRuntime, *, bot_token: str) -> None:
    """Long-poll Telegram and process text or photo messages via ``runtime``.

    Long polling needs no public webhook — only a bot token from @BotFather.
    """
    try:
        import asyncio

        from telegram import Update
        from telegram.ext import Application, MessageHandler, filters
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise TelegramDependencyError(
            "python-telegram-bot is not installed. Run: pip install 'blacknode[telegram]'"
        ) from exc

    import json as _json
    import urllib.request as _ur

    from blacknode.integrations.status import DriverStatus

    def _bot_username() -> str:
        try:
            with _ur.urlopen(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=8) as r:
                return "@" + _json.load(r)["result"]["username"]
        except Exception:
            return ""

    label = _bot_username()
    app = Application.builder().token(bot_token).build()
    status = DriverStatus("telegram", str(runtime.workflow.get("name") or ""), label=label).start()

    async def _on_message(update: "Update", context) -> None:  # pragma: no cover - needs live Telegram
        message = update.effective_message
        if message is None:
            return
        photo = message.photo[-1] if message.photo else None
        text = (message.text or message.caption or "")
        if not text.strip() and photo is None:
            return
        username = context.bot.username
        if username and text:
            text = text.replace(f"@{username}", "").strip()
        chat_id = str(message.chat_id)
        user = update.effective_user

        image_url = ""
        if photo is not None:
            try:
                import base64
                tg_file = await context.bot.get_file(photo.file_id)
                raw = await tg_file.download_as_bytearray()
                image_url = "data:image/jpeg;base64," + base64.b64encode(bytes(raw)).decode("ascii")
            except Exception as exc:  # noqa: BLE001
                print(f"[telegram] !! image download failed: {exc}", flush=True)

        fields = {
            "user_id": str(user.id) if user else "",
            "chat_id": chat_id,
            "message_id": str(message.message_id),
            "image": image_url,
        }
        print(f"[telegram] <- chat {chat_id}: {text!r}{' +photo' if photo else ''}", flush=True)
        # Graph-introspection commands (/tools, /model, /graph, /help) answer
        # directly from the live graph — no agent run.
        command = runtime.command_reply(text)
        if command is not None:
            await message.reply_text(command)
            print(f"[telegram] -> command reply ({text!r})", flush=True)
            return
        status.mark_processing()
        # The graph drives the send: cooking the reply node posts the answer.
        # The driver only reports errors that prevented a reply.
        try:
            reply = await asyncio.to_thread(runtime.handle_message, text, chat_id, fields=fields)
            print(f"[telegram] -> sent reply: {str(reply)[:80]!r}", flush=True)
        except Exception as exc:  # noqa: BLE001 - never let one message kill the bot
            print(f"[telegram] !! error: {type(exc).__name__}: {exc}", flush=True)
            try:
                await message.reply_text(f"[error] {type(exc).__name__}: {exc}")
            except Exception:
                pass
        status.mark_listening()

    # Text (incl. commands) + photos so /tools etc. and image messages reach us.
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, _on_message))
    print(f"[telegram] connected as {label or '(unknown)'} — long-polling (DM the bot; groups need @mention)", flush=True)
    try:
        app.run_polling()
    finally:
        status.stop()


def _run_telegram(runtime: AgentRuntime) -> None:
    serve(runtime, bot_token=secret("TELEGRAM_BOT_TOKEN"))


register_driver(
    DriverSpec(
        name="telegram",
        description="Telegram bot (long polling): answers messages with the agent workflow.",
        run=_run_telegram,
        required_extra="telegram",
        required_packages=("telegram",),
        required_env=("TELEGRAM_BOT_TOKEN",),
    )
)
