# Docker Compose

Blacknode includes a Docker Compose path for local, cloud VM, and on-prem demos.
It starts three services. Local development can build from source, while
published deployments can use prebuilt GHCR images.

| Service | Port | Purpose |
|---|---:|---|
| `editor` | `3000` | React visual editor. |
| `editor-server` | `7777` | FastAPI backend, workflow store, run store, cook API. |
| `blacknode-mcp` | `9901` | Streamable HTTP MCP server at `/mcp`. |

## Run, Check, See Result

### 1. Start everything

On Windows, use the helper so Docker Desktop/engine problems get a clear
actionable message:

```powershell
.\docker-up.ps1
```

On Linux, macOS, or after confirming `docker info` works:

```bash
docker compose up --build
```

### 2. Open the editor

```text
http://127.0.0.1:3000
```

Load a template, click **Cook** on an Output node, and inspect the **Runs** tab.

### 3. Check the MCP endpoint

```text
http://127.0.0.1:9901/mcp
```

MCP clients connect to that endpoint with `streamable-http`. A browser GET can
show a protocol response instead of a page; use an MCP client to list tools.

### 4. Add NVIDIA credentials

To use hosted NVIDIA NIM, create a local `.env` from the example and set
`NVIDIA_API_KEY`:

```bash
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and start the stack:

```powershell
.\docker-up.ps1
```

Local state mounted from the checkout:

- `workflows/`
- `editor-server/runs/`

This Compose stack is the local and self-hosted evaluation path for the visual
editor, backend, persisted run history, saved workflows, and streamable HTTP MCP
endpoint.

## Run Published Images

After the images are published, use:

```powershell
docker compose -f docker-compose.published.yml up
```

See [Docker Publishing](docker-publish.md) for GHCR publishing and image tags.
