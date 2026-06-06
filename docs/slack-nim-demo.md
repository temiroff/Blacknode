# NIM-Powered Slack Agent

Turn an NVIDIA NIM model into a Slack bot with tool access in a few minutes. The
bot answers `@mentions` in a thread, can `web_search` and run a `calculator`,
and remembers the conversation per thread.

```
@blacknode what's the population of Tokyo times 2?
  → web_search("population of Tokyo") → calculator("37000000 * 2")
  → "About 74 million."   (posted in-thread)
```

## How it works

Slack is wired as a **driver** around a normal Blacknode agent workflow.
Blacknode's graph cook is synchronous and pull-based; a Slack webhook is
push-based and long-lived, so the driver — not a "trigger node" — owns the event
loop and runs one workflow execution per message, exactly like the CLI `run` and
the editor `/cook` are drivers around the same engine.

```
blacknode slack templates/slack-nim-agent.json
  └─ Slack Bolt (Socket Mode) owns the event loop
  └─ heartbeat → editor (the SlackMessage node shows a live/offline badge)
  └─ each @mention: fill SlackMessage → run_workflow → post SlackReply in thread
```

The conversation's endpoints — and its memory — appear as nodes so the workflow
reads top-to-bottom in the editor:

```
[SlackMessage] → [ConversationMemory] → [AgentLoop: nim] → [SlackReply]
   (auth + IDs)     (per-thread history)      ↑
       │                              [ToolBox] ← web_search (PythonFn)
       │                                        ← calculator (PythonFn)
       └─ channel, thread_ts, user_id ───────────────────────────────┘
```

`ConversationMemory` prepends the thread's recent turns to the prompt; history
persists in a process-global store across the per-message cooks (the driver
records each completed turn). The only thing still "under the hood" is the event
loop itself — which can't be a cook node (it waits for pushes; a cook returns
once).

`SlackMessage` is the main node: it holds the integration's auth (entered in the
editor) and emits the conversation context — `channel`, `thread_ts`, `user_id` —
which all wire into `SlackReply` so the reply node knows where, in which thread,
and to whom it is answering. The driver performs the send using the bot token
stored on the message node.

`SlackMessage` and `SlackReply` are **cosmetic**: they do no Slack I/O
themselves. Before each cook the driver fills the `SlackMessage` node with the
incoming message (prefixed with the thread's recent turns) plus its `user_id`,
`channel`, and `thread_ts`; after the cook it posts whatever reached
`SlackReply` back to the thread. The graph stays a plain pull-based cook that
runs and tests with no Slack connection. Because `channel` / `thread_ts` /
`user_id` are real ports, downstream nodes (e.g. a trajectory recorder) can key
off the live conversation.

## Prerequisites

- Python 3.11+ and Blacknode installed with the Slack extra:
  ```bash
  pip install -e ".[slack]"      # adds slack_bolt + slack_sdk
  ```
- An **NVIDIA API key** for hosted NIM (`NVIDIA_API_KEY`), from
  [build.nvidia.com](https://build.nvidia.com). The template uses
  `nim:meta/llama-3.1-8b-instruct`; point it at a local NIM container by editing
  the workflow's `Model` node and the endpoint if you self-host.
- A **Slack app** with Socket Mode enabled (below). Socket Mode needs no public
  URL, so it works from a laptop behind NAT.

## Slack app setup

1. Create an app at [api.slack.com/apps](https://api.slack.com/apps) → *From scratch*.
2. **Socket Mode** → enable it. Generate an **App-Level Token** with the
   `connections:write` scope → this is your `SLACK_APP_TOKEN` (`xapp-…`).
3. **OAuth & Permissions** → add Bot Token Scopes: `app_mentions:read`,
   `chat:write`. Install the app to your workspace → copy the **Bot User OAuth
   Token** → this is your `SLACK_BOT_TOKEN` (`xoxb-…`).
4. **Event Subscriptions** → subscribe to the bot event `app_mention`.
5. Invite the bot to a channel: `/invite @yourbot`.

## Run it

```bash
export NVIDIA_API_KEY="nvapi-…"
export SLACK_BOT_TOKEN="xoxb-…"
export SLACK_APP_TOKEN="xapp-…"

blacknode slack templates/slack-nim-agent.json
```

**Tokens** can come from the environment (above) *or* the editor: select the
`SlackMessage` node and fill **Bot token** / **App token** in the Inspector's
**Connection · Slack** panel. The message node is the main node — it holds the
auth, and its outputs wire into `SlackReply`. Those are saved to the local key store
(`editor-server/api_keys.json`), never into the graph, so templates stay
shareable. Environment variables override the store. The `NVIDIA_API_KEY` works
the same way (set it, or fill it on the `Model` node). Run `blacknode drivers`
to see whether the Slack driver is `ready`, `needs env`, or `needs install`.

Then in Slack: `@yourbot what is 17 * 23, and what is NVIDIA NIM?`

## Run it from the editor (one-click)

Same as the [Telegram demo](telegram-nim-demo.md#run-it-from-the-editor-one-click):
select the `SlackMessage` node → **Install** the extra if needed → fill the **Bot
token** + **App token** → press **▶ Start bot**. The node badge turns green and
shows the connected bot; changing a token **auto-restarts** the running bot. Keep
the graph open and `@mention` the bot to **watch the real run animate** on the
canvas (per-node status circles, output values on hover), with each message
cooking the current graph — no restart on edits.

**Commands:** `@mention` the bot with `/tools`, `/model`, `/graph`, or `/help` and
it answers **directly from the live graph** (no LLM) — handy to see what's wired
in. Anything else goes to the agent.

Options:

- `--input-node ID` — the node that receives each message. Defaults to
  auto-detecting the `SlackMessage` node (or, in a graph without one, whatever
  Text node feeds the agent's `prompt`).
- `--max-turns N` — how many turns of per-thread history to keep (default 6).

## Customize

- **Model** — edit the `Model` node value (e.g. another NIM model, or a local
  NIM endpoint). Anything the provider stack resolves works: `nim:…`,
  `claude-…`, `gpt-…`, `ollama:…`, `local:…`.
- **Tools** — the two tools are `PythonFn` nodes collected by `ToolBox`. Add
  more by dropping another `PythonFn` and wiring it to a new `ToolBox` port.
- **System prompt** — edit the `Text` node feeding `system`.
- **Any workflow** — `blacknode slack <your-workflow.json>` works for any graph
  whose result is text. The driver auto-detects a `SlackMessage` node, or falls
  back to a plain Text node feeding the agent's `prompt` with an `Output`. The
  bot is generic; the template is just a good default.

## Is it ready? Other drivers

Slack is one **driver** (a runtime around the graph engine). Check whether it's
installed and configured — and what else is registered — with:

```bash
blacknode drivers
```

See [drivers.md](drivers.md) for the registry, the `ready` / `needs env` /
`needs install` states, and how to add a driver (Discord, HTTP, …).

## Notes & limits

- **Memory is a node** (`ConversationMemory`) backed by a process-global store,
  so per-thread history is visible in the graph yet survives across the
  one-cook-per-message runs. Restarting the bot clears it.
- **Live status**: while a driver runs it heartbeats the editor, so the
  `SlackMessage` node's badge shows **listening** (green) when a bot is actually
  connected, **processing** while handling a message, and **offline** (grey)
  when nothing is running. It needs the editor-server up; the heartbeat is
  best-effort and never blocks the bot.
- **Socket Mode** is used for zero-config local runs. For a hosted deployment
  you'd front it with the HTTP events endpoint and Slack request-signature
  verification instead.
- The bot runs the agent with tool access on external input — only install it in
  workspaces you trust, and keep the tools' capabilities in mind.
