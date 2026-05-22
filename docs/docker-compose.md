# Docker Compose

Blacknode includes a Docker Compose path for local, cloud VM, and on-prem demos.
It starts three services:

| Service | Port | Purpose |
|---|---:|---|
| `editor` | `3000` | React visual editor. |
| `editor-server` | `7777` | FastAPI backend, workflow store, run store, cook API. |
| `blacknode-mcp` | `9901` | Streamable HTTP MCP server at `/mcp`. |

Start everything:

```bash
docker compose up --build
```

Open:

```text
http://127.0.0.1:3000
```

MCP endpoint:

```text
http://127.0.0.1:9901/mcp
```

To use hosted NVIDIA NIM, create a local `.env` from the example and set
`NVIDIA_API_KEY`:

```bash
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and start the stack:

```bash
docker compose up --build
```

Local state mounted from the checkout:

- `workflows/`
- `editor-server/runs/`

This is a deployment baseline for demos and self-hosted evaluation. It is not
yet an enterprise-hardened production package with auth, RBAC, secret-store
integration, or execution sandboxing.
