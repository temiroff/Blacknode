# Integration Drivers

A **driver** connects an outside event source (Slack, and future ones like
Discord or an HTTP webhook) to a Blacknode agent workflow. Drivers are runtimes
*around* the graph engine, not graph nodes: the cook stays synchronous and
pull-based, and the driver runs one cook per incoming message. See
[slack-nim-demo.md](slack-nim-demo.md) for the Slack walkthrough.

## See what's registered and activated

Drivers self-register at import (like nodes and exporters do). List them and
their readiness:

```bash
blacknode drivers
```

```
Blacknode drivers
[needs install] slack - Slack bot (Socket Mode): answers @mentions with the agent workflow.
    extra: blacknode[slack] (missing)
    env:   SLACK_BOT_TOKEN (missing), SLACK_APP_TOKEN (missing)
```

Status is one of:

| Status | Meaning |
|---|---|
| `ready` | the optional extra is installed **and** all required env vars are set |
| `needs install` | the optional extra (`pip install 'blacknode[<extra>]'`) is missing |
| `needs env` | deps are present but a required env var (e.g. a token) is unset |

`blacknode drivers --json` prints the same data machine-readably (name, status,
extra, `packages_installed`, per-var `env` map, `missing_env`) for scripting.

## The seam every driver shares

Only the transport differs between drivers. The runtime engine is reusable:

- `ConversationMemory` — per-conversation history, keyed by a thread/channel id
- `detect_input_node` / `inject_input` — write the incoming text into the graph
- `AgentRuntime.handle_message(text, thread_id) -> reply` — the universal call

`AgentRuntime` (aliased from `SlackAgentRuntime`) knows nothing about Slack; a
new driver only provides a transport that calls `handle_message`.

## Add a driver

Three steps, mirroring Slack:

**1. A transport module** `python/blacknode/integrations/<name>_runtime.py` that
reuses `AgentRuntime` and registers itself:

```python
import os
from blacknode.integrations.registry import DriverSpec, register_driver
from blacknode.integrations.slack_runtime import AgentRuntime  # the reusable seam

def serve(runtime, *, token):
    try:
        import discord
    except ImportError as exc:
        raise RuntimeError("pip install 'blacknode[discord]'") from exc
    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_message(msg):
        if msg.author != client.user:
            await msg.channel.send(runtime.handle_message(msg.content, str(msg.channel.id)))

    client.run(token)

def _run(runtime):
    serve(runtime, token=os.environ.get("DISCORD_TOKEN", ""))

register_driver(DriverSpec(
    name="discord",
    description="Discord bot: answers messages with the agent workflow.",
    run=_run,
    required_extra="discord",
    required_packages=("discord",),
    required_env=("DISCORD_TOKEN",),
))
```

**2. Import it for registration** — add it to
`python/blacknode/integrations/__init__.py` so `import blacknode.integrations`
registers it (the same place the Slack driver is imported).

**3. Wire the CLI** — add a `discord` subparser in `cli.py` (copy the `slack`
one) and dispatch it through the shared runner: `_run_driver("discord", args)`.
That runner reads the registry, checks the extra and env vars, builds the
`AgentRuntime`, and starts the transport — so the new driver gets the same
readiness checks and error messages for free.

**4. Declare the extra** in `pyproject.toml`:

```toml
discord = ["discord.py>=2.0"]
```

Once registered, the new driver shows up in `blacknode drivers` with its own
readiness, and `blacknode <name> <workflow.json>` runs it.
