# Docker Publishing

Blacknode publishes two images:

| Image | Purpose |
|---|---|
| `ghcr.io/temiroff/blacknode-server` | Python runtime, editor backend, CLI, and MCP server. |
| `ghcr.io/temiroff/blacknode-editor` | Production static editor served by nginx. |

The MCP service reuses the server image with a different command.

## Publish From GitHub Actions

The `Docker Publish` workflow runs on pushes to `main` or `master`, version tags
like `v0.1.0`, and manual dispatch.

It pushes:

- `latest` for branch builds.
- The short commit SHA for every build.
- `vX.Y.Z` and `X.Y.Z` for version tag builds.

GitHub Container Registry packages may start private. If the repository is
public, open the package settings in GitHub and make the two packages public.

## Publish Manually

```powershell
docker login ghcr.io
docker build -f docker/Dockerfile.server -t ghcr.io/temiroff/blacknode-server:latest .
docker build -f docker/Dockerfile.editor -t ghcr.io/temiroff/blacknode-editor:latest .
docker push ghcr.io/temiroff/blacknode-server:latest
docker push ghcr.io/temiroff/blacknode-editor:latest
```

## Run Published Images

Download `docker-compose.published.yml` and the `docker/Caddyfile`, copy
`.env.example` to `.env`, then choose a mode.

**Local / single trusted operator** (editor on loopback only):

```powershell
docker compose -f docker-compose.published.yml up -d
```

Open `http://127.0.0.1:3000`.

**Remote users** (LAN IP or VM): the editor-server runs arbitrary code and has
no auth, so it is never exposed directly. Set `BLACKNODE_DOMAIN` and the
`BLACKNODE_BASICAUTH_*` values in `.env`, then start the Caddy TLS + Basic Auth
front door:

```powershell
docker compose -f docker-compose.published.yml --profile proxy up -d
```

Open `https://<your-domain>/`. See
[Docker Compose § Production deployment](docker-compose.md#production-deployment-self-hosted-real-users)
for the full security boundary, secrets, persistence, and backup guidance.
