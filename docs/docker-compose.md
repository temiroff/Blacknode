# Docker Compose

Blacknode includes a Docker Compose path for local, cloud VM, and on-prem demos.
It starts three services. Local development can build from source, while
published deployments can use prebuilt GHCR images.

| Service | Port | Purpose |
|---|---:|---|
| `editor` | `3000` | React visual editor. |
| `editor-server` | `7777` | FastAPI backend, workflow store, run store, cook API. |
| `blacknode-mcp` | `9901` | Streamable HTTP MCP server at `/mcp`. |

The dev stack (`docker-compose.yml`) publishes these ports for local access. The
production stack (`docker-compose.published.yml`) does **not**: `editor-server`
is internal-only, `editor`/`blacknode-mcp` bind to loopback, and public access
goes through the Caddy `proxy` profile. See
[Production deployment](#production-deployment-self-hosted-real-users).

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

## Production deployment (self-hosted, real users)

> **Security boundary — read first.** The `editor-server` executes
> user-authored Python during a cook (`PythonFn` and the Script editor) and has
> **no built-in authentication**. Anyone who can reach it can run arbitrary code
> on the host and read any key typed into the UI. Treat it as a
> trusted-operator tool: **never publish `7777`, `3000`, or `9901` to a public
> interface.** `docker-compose.published.yml` binds the editor and MCP to
> loopback only and exposes the stack to real users solely through an
> authenticating TLS reverse proxy (Caddy, the `proxy` profile).

### 1. Configure environment and secrets

```bash
cp .env.example .env
```

Set, in `.env`:

- Model keys (`NVIDIA_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …).
  Provide keys **here via env**, not through the editor UI key panel — env keys
  are never written to `editor-server/api_keys.json` and are never returned by
  the `/settings/api-keys` endpoint.
- `BLACKNODE_IMAGE_TAG` — pin to a published 12-char commit SHA instead of
  `latest` for reproducible deploys.
- `BLACKNODE_DOMAIN` — the public hostname (a real domain gets an automatic
  Let's Encrypt certificate; `localhost` uses Caddy's internal CA for testing).
- `BLACKNODE_BASICAUTH_USER` and `BLACKNODE_BASICAUTH_HASH`. Generate the hash:

  ```bash
  docker run --rm caddy:2.8-alpine caddy hash-password --plaintext 'your-password'
  ```

### 2. Start behind the auth proxy

```bash
docker compose -f docker-compose.published.yml --profile proxy up -d
```

Caddy terminates TLS, enforces Basic Auth on every request, and reverse-proxies
to the internal editor (`/`) and MCP (`/mcp`) services. Only Caddy binds the
public `80`/`443` ports; the editor (`3000`) and MCP (`9901`) stay on loopback,
and `editor-server` (`7777`) is never published.

Open `https://<your-domain>/`; MCP clients connect to `https://<your-domain>/mcp`.

Without `--profile proxy`, the stack still starts but is reachable only at
`http://127.0.0.1:3000` (and `:9901`) on the host — use that for a single
trusted operator on the box, never for remote users.

### 3. Hardening already applied

- `restart: unless-stopped` and healthchecks on every service.
- `editor-server` runs as a non-root user (`appuser`, uid 10001).
- Per-service CPU/memory limits (`deploy.resources.limits`).
- An isolated `blacknode` bridge network.

### 4. Persistence and backups

State lives in named Docker volumes (survives `down`/`up` and reboots):

| Volume | Holds |
|---|---|
| `blacknode_workflows` | Saved workflow JSON. |
| `blacknode_runs` | Run history / replay records. |
| `caddy_data` | TLS certificates and keys. |

The live editing canvas (`editor-server/blacknode_graph.json`) is scratch state
in the container layer, not a volume — it resets when the container is
recreated (e.g. on an image update). Durable artifacts are the **saved
Workflows** and **Runs** above, so save work to a workflow before redeploying.

Back one up:

```bash
docker run --rm -v blacknode_runs:/data -v "$PWD:/backup" alpine \
  tar czf /backup/runs-backup.tar.gz -C /data .
```

### 5. Still your responsibility

The proxy adds TLS + a shared Basic Auth credential — enough for a small trusted
group. It does **not** add per-user accounts, RBAC, or workspace isolation, and
the cook surface still runs arbitrary code under that one credential. For
untrusted or multi-tenant users, put Blacknode behind SSO/an identity-aware
proxy and run one isolated instance per trust boundary.
