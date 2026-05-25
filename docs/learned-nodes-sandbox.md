# Learned Nodes Sandbox

Learned-node Python runs in Docker, not in the Blacknode host process.

## Image

Build the sandbox image:

```powershell
docker build -f docker\sandbox\Dockerfile -t blacknode-sandbox:latest .
```

The image is based on `python:3.12-slim` and installs only:

- `requests`
- `beautifulsoup4`
- `feedparser`
- `lxml`
- `python-dateutil`
- `pyyaml`
- `pillow`

## Runtime Limits

Each cook starts a fresh container with:

| Setting | Value |
|---|---|
| image | `blacknode-sandbox:latest` |
| command | `python /workspace/runner.py` |
| network | `none` by default, `bridge` when `requires_network=True` |
| memory | `512m` |
| CPU | 1 CPU quota |
| pids | 100 |
| capabilities | drop all |
| root filesystem | read-only |
| tmpfs | `/tmp`, 64 MB |
| workspace mount | one temporary directory mounted at `/workspace` |

The host writes `node.py`, `input.json`, and `runner.py` into the temporary
workspace. The container writes `output.json`. The workspace is removed after
the run.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `BLACKNODE_LEARNED_DIR` | `./nodes/learned` | Learned-node storage |
| `BLACKNODE_SANDBOX_IMAGE` | `blacknode-sandbox:latest` | Docker image tag |
| `BLACKNODE_SANDBOX_TIMEOUT` | `30` | Per-execution timeout in seconds |
| `BLACKNODE_SANDBOX_MEMORY` | `512m` | Container memory limit |
| `BLACKNODE_SANDBOX_DISABLED` | `false` | Refuse learned-node execution |

## Troubleshooting

Run:

```powershell
blacknode doctor
```

Common failures:

- Docker is not running: start Docker Desktop and rerun `blacknode doctor`.
- Image is missing: run the build command above, or let the first learned-node
  cook attempt the one-shot automatic build.
- Timeout: raise `BLACKNODE_SANDBOX_TIMEOUT` for debugging, then reduce it
  before demos.
- Memory failure: inspect the node source and reduce allocations; the default
  limit is intentionally small.
