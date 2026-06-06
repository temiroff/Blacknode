# NIM-Powered Telegram Agent

Turn an NVIDIA NIM model into a Telegram bot with tool access. The bot answers
messages, can `web_search` and run a `calculator`, and remembers the
conversation per chat. It is the Telegram twin of the
[Slack agent](slack-nim-demo.md) — same engine, different transport.

## How it works

Like Slack, Telegram is wired as a **driver**, not a trigger node. Blacknode's
graph cook is synchronous and pull-based, so the driver owns the long-poll loop
and runs one workflow execution per message. It reuses the same
transport-neutral runtime; only the transport is Telegram-specific.

```
blacknode telegram templates/telegram-nim-agent.json
  └─ python-telegram-bot long-polls getUpdates (no public URL needed)
  └─ heartbeat → editor (the TelegramMessage node shows a live/offline badge)
  └─ each message: fill TelegramMessage → run_workflow → reply in the chat
```

The conversation's endpoints — and its memory — appear as nodes so the graph
reads top-to-bottom:

```
[TelegramMessage] → [ConversationMemory] → [AgentLoop: nim] → [TelegramReply]
   (auth + IDs)        (per-chat history)        ↑
       │                              [ToolBox] ← web_search (PythonFn)
       │                                        ← calculator (PythonFn)
       └─ chat_id, user_id, message_id ──────────────────────────────┘
```

`ConversationMemory` prepends the chat's recent turns to the prompt; history
persists in a process-global store across the per-message cooks. The only thing
still under the hood is the long-poll loop itself.

`TelegramMessage` is the main node: it holds the bot token (entered in the
editor) and emits the conversation context — `chat_id` (where), `user_id` (who),
`message_id` (which message) — which all wire into `TelegramReply` so the reply
node carries the full context. The driver performs the send using the bot token
stored on the message node.

`TelegramMessage` / `TelegramReply` are **cosmetic**: they do no Telegram I/O.
Before each cook the driver fills `TelegramMessage` with the incoming text plus
`user_id`, `chat_id`, and `message_id`; after the cook it sends whatever reached
`TelegramReply` back to the chat. (Telegram keys a conversation by `chat_id`,
the way Slack keys by `thread_ts`.)

## Prerequisites

- Python 3.11+ and Blacknode installed with the Telegram extra:
  ```bash
  pip install -e ".[telegram]"      # adds python-telegram-bot
  ```
- An **NVIDIA API key** for hosted NIM (`NVIDIA_API_KEY`), from
  [build.nvidia.com](https://build.nvidia.com).
- A **Telegram bot token** from [@BotFather](https://t.me/BotFather)
  (`/newbot` → copy the token). Long polling needs no public URL.

## Run it

```bash
export NVIDIA_API_KEY="nvapi-…"
export TELEGRAM_BOT_TOKEN="123456:ABC-…"

blacknode telegram templates/telegram-nim-agent.json
```

**Tokens** can come from the environment (above) *or* the editor: select the
`TelegramMessage` node and fill **Bot token** in the Inspector's
**Connection · Telegram** panel. The message node is the main node — it holds the
auth, and its `chat_id` wires into `TelegramReply`. It is saved to the local key store
(`editor-server/api_keys.json`), never into the graph; environment variables
override it. Check readiness with `blacknode drivers`.

Then message your bot, or add it to a group and mention it.

## Run it from the editor (one-click)

You don't need the terminal — drive the bot from the canvas:

1. **Install** — select the `TelegramMessage` node. If the package is missing, the
   Inspector shows **⚠ blacknode[telegram] isn't installed** with an **Install**
   button (runs `pip install` in the editor-server's Python).
2. **Token** — fill **Bot token** in the same panel (saved to the key store).
3. **Start** — press **▶ Start bot** on the node. The editor-server launches the
   driver with its own interpreter, so there's no environment to reconcile. The
   button shows **⏳ Starting…**, then the node badge turns green and shows the
   connected bot, e.g. **`● @BlacknodeAgentBot`** (fetched via `getMe`). Press
   **■ Stop bot** to take it down.
4. **Change the token any time** — saving a new token **auto-restarts** a running
   bot so it reconnects as the new bot (a running bot reads its token only at
   startup).

The badge is truthful: **needs install** / **offline** / **listening** /
**processing** reflect the bot's real heartbeat — not an always-on label. Select
the node to see a live **Bot log** tail (connection, each `<- chat …` / `-> sent
reply`, and errors).

## Watch it cook live

While the bot runs, **keep the graph open** and message the bot — you'll watch
the **real run** animate on the canvas: each node lights up as it executes
(top-right status circle + result tooltip), output knobs show their value on
hover, and the reply node sends. These are the actual run events streamed via
live-sync, not a simulation.

Each message cooks the graph **as it is right now** — edit a wire or the `system`
node and the next message uses the new shape, no restart. The data connections
decide what's cooked: cooking the reply pulls everything wired into it
(`TelegramMessage → ConversationMemory → AgentLoop → tools → TelegramReply`).

## Customize

Everything from the Slack demo applies — the graph is identical apart from the
two endpoint nodes. Change the `Model` node for a different NIM model or a local
NIM endpoint; add tools as `PythonFn` nodes wired into `ToolBox`; edit the `Text`
node feeding `system`. `blacknode telegram <your-workflow.json>` drives any graph
whose result is text.

## Notes & limits

- **Memory is a node** (`ConversationMemory`, keyed by `chat_id`) backed by a
  process-global store; restarting the bot clears it.
- **Live status**: while running, the driver heartbeats the editor, so the
  `TelegramMessage` node badge shows **listening** / **processing** / **offline**
  truthfully. Best-effort; never blocks the bot.
- **Long polling** is used for zero-config local runs; for a hosted deployment
  you'd switch to a webhook.
- The bot runs the agent with tool access on external input — only deploy it
  where you trust the inputs, and keep the tools' capabilities in mind.
