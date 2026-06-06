# Local Telegram Agent

Blacknode can expose a locally running workflow as a Telegram bot. Telegram is
the remote chat interface; the driver, workflow, tools, GPU nodes, and graph
execution run on the machine running Blacknode. Model inference runs wherever
the selected model runs: the included NIM model is hosted, while a local model
endpoint can keep inference local.

This is useful when you want to message your local agent from a phone or another
Telegram client without deploying the Blacknode editor to the public internet.
The included template uses NVIDIA NIM, but the workflow can use any provider
supported by Blacknode, including a local model endpoint.

Telegram is not the agent. A Telegram message reaches your bot, the local
Blacknode driver invokes your workflow, and `TelegramReply` returns the result.

## What "Local Agent" Means

- Blacknode and the driver run on your workstation or server.
- Long polling creates an outbound connection, so Blacknode needs no public
  inbound port.
- Workflow tools execute where Blacknode executes unless a tool explicitly
  calls an external service.
- Telegram's servers transport incoming and outgoing messages and photos.
- A hosted model provider receives the prompt and relevant tool context.
- A local model endpoint keeps model inference on infrastructure you control.

## What You Control

The visual graph defines the agent:

- The `Model` node selects the model or endpoint.
- The system `Text` node defines its behavior.
- `PythonFn` nodes define available tools.
- `ToolBox` controls which tools the agent can call.
- `ConversationMemory` controls whether earlier turns are included.
- Image or CUDA nodes control any photo-processing path.
- `TelegramReply` controls what is sent back to Telegram.

Telegram does not gain general access to your computer. The agent can only use
the capabilities you expose through its workflow and tools. A broad Python,
filesystem, shell, network, or database tool is therefore a broad permission.

## Architecture

Telegram support is implemented as a **driver** around a normal pull-based
Blacknode workflow:

```text
Telegram user
    |
    | Telegram Bot API (long polling)
    v
Blacknode Telegram driver
    |
    | fills the live TelegramMessage node
    v
TelegramMessage -> ConversationMemory -> AgentLoop -> TelegramReply
                                         ^
                                         |
                                      ToolBox
```

For every incoming message, the driver:

1. Receives text, a photo, or a photo caption from Telegram.
2. Downloads the photo when present and converts it to an image data URL.
3. Fills `TelegramMessage.text`, `image`, `chat_id`, `user_id`, and
   `message_id`.
4. Cooks the current graph by pulling from `TelegramReply`.
5. Lets `TelegramReply` call Telegram's `sendMessage` or `sendPhoto` API.

`TelegramMessage` represents inbound data and does no network I/O itself.
`TelegramReply` is an active output node: cooking it sends the resulting text or
image when a real `chat_id` and bot token are available.

The bot token is associated with the Telegram connection in the Inspector, but
it is stored in the local key store, not in workflow JSON.

## Long Polling And Webhooks

Blacknode currently uses **long polling**:

- The local driver repeatedly asks Telegram for new updates.
- No public URL, TLS certificate, router configuration, or inbound firewall rule
  is required.
- It works well for local development, workstation agents, and private demos.
- The Blacknode process must remain running to receive messages.

A **webhook** reverses the connection: Telegram sends each update to a public
HTTPS endpoint. That is generally preferable for an always-on hosted service,
but webhook transport is **not currently implemented as a Blacknode setting**.
A hosted webhook deployment would require a public HTTPS endpoint, Telegram
webhook registration, request routing, and production authentication and
operations work.

## Included Workflow

Open `templates/telegram-nim-agent.json`. It includes:

- `nim:meta/llama-3.1-8b-instruct`
- A direct-answer system prompt
- `web_search`
- `calculator`
- Telegram message and reply nodes
- A `ConversationMemory` node with `max_turns = 0`

Memory is intentionally disabled by default. Independent requests such as
`2+2` and `what is NVIDIA?` do not inherit previous answers. To enable per-chat
memory, set `ConversationMemory.max_turns` to a positive number. History is
keyed by `chat_id`, kept in process memory, and cleared when the bot process
restarts.

## Prerequisites

- Python 3.11+
- Telegram support:

  ```bash
  pip install -e ".[telegram]"
  ```

- A Telegram bot token from [@BotFather](https://t.me/BotFather):
  run `/newbot` and copy the token.
- Credentials required by the chosen model. The included hosted NIM model uses
  `NVIDIA_API_KEY`.

Check readiness:

```bash
blacknode drivers
```

The Telegram driver reports `ready`, `needs env`, or `needs install`.

Environment variables take precedence over values saved in the editor key
store. Templates and exported workflows do not contain the saved token.

## Start From The Editor

1. Open the Telegram NIM Agent template.
2. Select `TelegramMessage`.
3. Install `blacknode[telegram]` if the Inspector reports it missing.
4. Enter the Bot token under **Connection - Telegram**.
5. Configure the model credential, such as `NVIDIA_API_KEY`.
6. Press **Start bot** on `TelegramMessage`.
7. Message the bot in Telegram.

The node displays `starting`, `listening`, `processing`, or offline state from
the driver's heartbeat. Press **Stop bot** to terminate the full driver process
tree. Stop requests are bounded, so the editor does not remain stuck on
`Stopping...` if the backend is unavailable.

Changing a saved bot token restarts a running driver so the new token takes
effect. Workflow edits do not require a restart: each incoming message cooks
the graph currently open in the editor.

## Start From The CLI

PowerShell:

```powershell
$env:NVIDIA_API_KEY="nvapi-..."
$env:TELEGRAM_BOT_TOKEN="123456:ABC-..."
blacknode telegram templates\telegram-nim-agent.json
```

Bash:

```bash
export NVIDIA_API_KEY="nvapi-..."
export TELEGRAM_BOT_TOKEN="123456:ABC-..."
blacknode telegram templates/telegram-nim-agent.json
```

Long polling runs in the foreground until the process is stopped.

## Direct Messages And Groups

- In a direct message, send text or a photo directly to the bot.
- In a group, Telegram's bot privacy setting controls which messages the bot
  receives. With privacy enabled, mention the bot or use a bot command.
- The driver removes its own `@username` mention before sending text to the
  agent.
- Every received group message can run the connected tools, so only add the bot
  to groups whose members should have that access.

## Message Behavior

| Incoming message | Graph behavior | Telegram reply |
|---|---|---|
| Text only | Text enters the agent path. | Sends final text when non-empty. |
| `2+2` | The calculator can run and return `4`. | Sends `4`, not tool narration. |
| Photo only, image path wired | Image nodes run; blank text does not invoke the text agent. | Sends the resulting image if non-empty. |
| Photo only, no image path | There is no text prompt or image result. | Sends nothing. |
| Photo plus caption | The photo enters `image`; caption enters `text`. | Can send an image with the text as its caption. |
| Empty text and empty image | No useful work is available. | Sends nothing and records no memory turn. |

Intermediate model narration such as descriptions of function calls is not a
user answer. Blacknode removes known tool-process wrappers and falls back to the
actual tool output when a weak model returns generic text after a tool call.
Raw steps remain available in run replay for debugging.

## Image Workflows

`TelegramMessage.image` is an image data URL when a photo was received, and an
empty string otherwise. `TelegramReply.image` is wire-only: it does not display
a file Browse control.

Example:

```text
TelegramMessage.image -> CUDACustomKernel.input
CUDACustomKernel.output -> TelegramReply.image
```

Image-mode CUDA kernels skip execution and return an empty image when the input
is empty. This prevents a synthetic benchmark image from being sent in response
to a text-only message.

For captioned image replies:

```text
AgentLoop.result -----------------> TelegramReply.text
ImageProcessor.output ------------> TelegramReply.image
```

When both are present, `TelegramReply` sends the image through `sendPhoto` and
uses the text as its caption.

## Commands

These commands are answered directly from the live graph without an LLM call:

| Command | Result |
|---|---|
| `/tools` | Lists tools currently connected to the agent. |
| `/model` | Shows the configured model. |
| `/graph` | Summarizes the current graph. |
| `/help` | Lists available commands. |

## Live Runs And Replay

When the editor starts the driver, each Telegram message cooks the current live
graph. The canvas shows node execution, and the Runs panel records:

- Node start, finish, and errors
- Model calls
- Tool calls and arguments
- Tool outputs in agent steps
- Final result
- Timing and cached-node information

Replay is the correct place to diagnose whether incomplete text came from the
search tool, the model, or Telegram. Telegram itself does not shorten the text
stored in a Blacknode run record.

## Security

- Treat the bot token and model API keys as secrets.
- Tokens saved in the editor go to the local key store and are excluded from
  workflow JSON.
- Anyone allowed to message the bot can cause the graph to run.
- Restrict group access and Telegram bot privacy settings appropriately.
- Review every connected tool before exposing the bot to untrusted users.
- Avoid unrestricted shell, filesystem, database, or network tools unless that
  access is intentional and isolated.
- Long polling avoids opening an inbound port, but outbound calls still go to
  Telegram, the model provider, and any network-enabled tools.
- Do not claim that hosted NIM inference is local. Use a local model endpoint
  when prompt data must remain on infrastructure you control.

## Troubleshooting

**The bot does not start**

Run `blacknode drivers`. Install `blacknode[telegram]`, verify the token, and
verify credentials for the selected model.

**The node remains on `Starting...`**

Inspect the Bot log in the Inspector. Confirm the editor backend is running and
can reach `api.telegram.org`.

**The node remains on `Stopping...`**

Refresh the editor if it is showing stale UI state. Current builds bound the
stop request and terminate the complete driver process tree.

**A later answer includes earlier questions**

Set `ConversationMemory.max_turns` to `0`. The included Telegram template
already uses this setting.

**A photo is returned for a text-only message**

Confirm the image processor receives `TelegramMessage.image`, not a synthetic
default. Current image-mode CUDA kernels emit no output when that input is
empty.

**The bot explains a tool call instead of answering**

Restart the bot after updating Blacknode so it loads the latest agent-loop
cleanup. Run replay should show the real tool output.

## Current Limits

- Transport is long polling only; webhook mode is not implemented.
- Conversation memory is process-local, not persistent storage.
- Telegram receives text and photos; other attachment types are not currently
  handled by this driver.
- Search quality is limited by the connected search tool. A truncated search
  snippet remains truncated even if Telegram delivery is correct.
- The driver is a local runtime, not a multi-tenant hosted bot platform.

See [Integration Drivers](drivers.md) for the shared driver architecture and
[NVIDIA GPU Blocks](nvidia-gpu-blocks.md) for image and CUDA processing.
