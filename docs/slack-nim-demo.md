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

Slack is wired as a **driver** around a normal Blacknode agent workflow, not as
graph nodes. Blacknode's graph cook is synchronous and pull-based; a Slack
webhook is push-based and long-lived, so the driver owns the event loop and runs
one workflow execution per message — exactly like the CLI `run` and the editor
`/cook` are drivers around the same engine.

```
blacknode slack templates/slack-nim-agent.json
  └─ Slack Bolt (Socket Mode) owns the event loop
  └─ ConversationMemory keyed by thread_ts   (per-thread history)
  └─ each @mention: inject text → run_workflow → post reply in thread
```

The workflow is a plain visual graph you can open and edit in the Blacknode
editor:

```
[Text: message] → [AgentLoop: nim:meta/llama-3.1-8b-instruct] → [Output]
                         ↑
                  [ToolBox] ← web_search (PythonFn)
                            ← calculator (PythonFn)
```

The driver overwrites the `Text` input node with each incoming message (prefixed
with the thread's recent turns) and posts the agent's result back to the thread.

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

Then in Slack: `@yourbot what is 17 * 23, and what is NVIDIA NIM?`

Options:

- `--input-node ID` — the node that receives each message. Defaults to
  auto-detecting the node that feeds the agent's `prompt` (here, `task`).
- `--max-turns N` — how many turns of per-thread history to keep (default 6).

## Customize

- **Model** — edit the `Model` node value (e.g. another NIM model, or a local
  NIM endpoint). Anything the provider stack resolves works: `nim:…`,
  `claude-…`, `gpt-…`, `ollama:…`, `local:…`.
- **Tools** — the two tools are `PythonFn` nodes collected by `ToolBox`. Add
  more by dropping another `PythonFn` and wiring it to a new `ToolBox` port.
- **System prompt** — edit the `Text` node feeding `system`.
- **Any workflow** — `blacknode slack <your-workflow.json>` works for any graph
  that has a text input feeding an agent and an `Output`. The bot is generic;
  the template is just a good default.

## Is it ready? Other drivers

Slack is one **driver** (a runtime around the graph engine). Check whether it's
installed and configured — and what else is registered — with:

```bash
blacknode drivers
```

See [drivers.md](drivers.md) for the registry, the `ready` / `needs env` /
`needs install` states, and how to add a driver (Discord, HTTP, …).

## Notes & limits

- **Memory lives in the driver**, not in the graph — a single process holds the
  per-thread history. Restarting the bot clears it. (This is by design: the cook
  is stateless per run.)
- **Socket Mode** is used for zero-config local runs. For a hosted deployment
  you'd front it with the HTTP events endpoint and Slack request-signature
  verification instead.
- The bot runs the agent with tool access on external input — only install it in
  workspaces you trust, and keep the tools' capabilities in mind.
