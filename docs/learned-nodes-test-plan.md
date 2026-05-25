# Learned Nodes Test Plan

This guide is the step-by-step validation path for the learned nodes feature.
Run these commands from the repository root on Windows PowerShell unless noted.

The most important end-to-end proof is:

```powershell
$env:BLACKNODE_LEARNED_NODES_CONSENT="1"
python scripts\demo_dry_run.py
```

Do not skip that check for demos. It creates a learned node through MCP, verifies
the editor backend sees it, runs a workflow through the Docker-backed learned
node, and deletes the temporary node.

## 1. Start From Current Master

```powershell
cd F:\PROJECTS\NVDIA\Blacknode
git switch master
git pull --ff-only origin master
git log -1 --oneline
```

Expected latest commit:

```text
1db1a80 Add learned nodes feature
```

This proves you are testing the merged feature, not the old branch state.

## 2. Install Local Dependencies

```powershell
python -m pip install -e .
cd editor
npm install
npm run build
cd ..
```

Expected result:

- Python package installs in editable mode.
- Editor TypeScript/Vite build succeeds.

If `npm run build` fails because Node is too old, install Node `20.19.0` or
newer, then rerun the editor commands.

## 3. Verify Docker Is Available

Start Docker Desktop first, then run:

```powershell
docker info
```

Expected result:

- The command exits successfully.
- Docker reports server details.

Learned nodes require Docker because learned-node Python never runs in the
Blacknode host process. The registered learned node wrapper delegates execution
to `blacknode.sandbox.docker_runner.run_in_container`.

## 4. Build The Sandbox Image

```powershell
docker build -f docker\sandbox\Dockerfile -t blacknode-sandbox:latest .
```

Expected result:

- Docker builds `blacknode-sandbox:latest`.
- The image contains only the approved learned-node runtime libraries.

You can confirm the image exists:

```powershell
docker image inspect blacknode-sandbox:latest
```

The runtime can auto-build the image on first use, but for demos it is better to
build explicitly so startup timing is predictable.

## 5. Run Doctor

```powershell
python -m blacknode.cli doctor
```

Expected learned-node details:

- Docker is reachable.
- `blacknode-sandbox:latest` is present.
- Learned-node directory status is reported.
- No required doctor check fails.

If Docker is not reachable, start Docker Desktop and rerun `docker info`.

## 6. Run The Unit Test Suite

```powershell
python -m unittest discover -s tests
```

Expected result:

```text
OK
```

This runs the normal unit suite. Docker-gated integration tests may be skipped
unless integration mode is enabled.

What this proves:

- Static analysis uses AST parsing.
- Manifest validation rejects invalid learned-node metadata.
- Registry loading handles bad manifests without blocking good learned nodes.
- Two learned nodes can be loaded at once without wrapper late-binding bugs.
- MCP validation returns structured rejection reasons.
- Transactional rollback removes files if registration fails.
- Consent gate behavior is covered.
- Editor learned-node API and SSE units are covered.

## 7. Run Docker Integration Tests

```powershell
$env:BLACKNODE_INTEGRATION_TESTS="1"
$env:BLACKNODE_LEARNED_NODES_CONSENT="1"
python -m unittest discover -s tests
Remove-Item Env:\BLACKNODE_INTEGRATION_TESTS
```

Expected result:

```text
OK
```

This is the proof that the Docker sandbox really works.

The important integration checks include:

- A trivial learned node runs through `docker_runner.run_in_container`.
- Learned node execution returns JSON output from the container.
- A no-network learned node attempts an HTTP request and fails because container
  networking is disabled.

The no-network test is intentionally an actual HTTP attempt, not a package import
or proxy check. It proves the sandbox network mode is doing real isolation.

## 8. Run The Camera Demo Dry Run

```powershell
$env:BLACKNODE_LEARNED_NODES_CONSENT="1"
python scripts\demo_dry_run.py
```

Expected output includes:

```text
[demo] editor backend started
[demo] MCP server connected
[demo] learned node created: ParseRSSDryRun
[demo] editor /learned-nodes sees the new node
[demo] workflow ran through Docker-backed learned node
```

If the editor backend is already running, the first line may be:

```text
[demo] editor backend already running
```

What this proves:

- The MCP server exposes `create_node_type`.
- Consent is accepted through `BLACKNODE_LEARNED_NODES_CONSENT=1`.
- The learned node is written to `nodes/learned/<Name>/`.
- The node is hot-registered.
- The editor backend can list it at `/learned-nodes`.
- Workflow execution reaches the learned node.
- Learned-node code runs in Docker, not in-process.
- Cleanup deletes the temporary learned node.

## 9. Verify MCP Tool Availability

```powershell
python scripts\smoke_test_mcp.py
```

Expected output includes these tools:

```text
create_node_type
list_learned_nodes
delete_learned_node
get_learned_node_source
promote_learned_node
```

This proves an MCP client can see the learned-node control surface.

## 10. Test The Visible Editor Flow

Start the editor:

```powershell
.\start.bat
```

Open:

```text
http://localhost:3000
```

Keep the editor visible, then run:

```powershell
$env:BLACKNODE_LEARNED_NODES_CONSENT="1"
python scripts\demo_dry_run.py --node-name VisualDemoNode
```

Expected editor behavior:

- The node appears in the **Learned** palette category within about 2 seconds.
- The newly added node has a short purple pulse animation.
- The **Learned Nodes** sidebar tab refreshes.

The dry-run script deletes the temporary node at the end, so the sidebar row may
disappear after the script finishes. That is expected. For a persistent visual
test, create a learned node from an MCP client and do not delete it immediately.

## 11. Persistent Manual MCP Test

Use Claude Desktop or another MCP client connected to Blacknode, then ask it:

```text
Create a Blacknode learned node named TitleCaseDemo.
Description: Convert text to title case and return it.
Inputs: text:Text
Outputs: result:Text
Category: Parsing
Code:
def run(text):
    return {"result": text.title()}
requires_network: false
```

Expected result:

- The MCP tool returns `{"status": "created", ...}`.
- `nodes/learned/TitleCaseDemo/node.py` exists.
- `nodes/learned/TitleCaseDemo/manifest.json` exists.
- The editor palette shows `TitleCaseDemo` under **Parsing**.
- The sidebar shows name, description, created date, permissions, **View source**,
  **Promote**, and **Delete**.

Use **View source** to confirm the modal is read-only.

Use **Delete** and confirm deletion when finished. The node should disappear
from the palette/sidebar after the SSE refresh.

## 12. Consent Gate Check

In a fresh shell with no consent env var:

```powershell
Remove-Item Env:\BLACKNODE_LEARNED_NODES_CONSENT -ErrorAction SilentlyContinue
```

Then call `create_node_type` from an MCP client.

Expected rejection:

- The response is rejected.
- The reason explains that agents can create Python code that executes on your
  machine in a Docker sandbox.
- The response tells the user to set:

```powershell
$env:BLACKNODE_LEARNED_NODES_CONSENT="1"
```

After opt-in, consent is persisted at:

```text
~/.blacknode/learned-nodes-consent.json
```

Delete that file to revoke consent.

## 13. Files To Inspect After A Learned Node Is Created

For a learned node named `TitleCaseDemo`, inspect:

```powershell
Get-ChildItem nodes\learned\TitleCaseDemo
Get-Content nodes\learned\TitleCaseDemo\manifest.json
Get-Content nodes\learned\TitleCaseDemo\node.py
```

Expected files:

```text
nodes/learned/TitleCaseDemo/
  manifest.json
  node.py
```

The manifest contains metadata and permissions. The Python file contains the
learned-node source. Blacknode loads the file as text and sends it to Docker at
execution time; it does not import the file into the host process.

## 14. Troubleshooting

Docker is not running:

```powershell
docker info
```

Start Docker Desktop, then retry.

Sandbox image missing:

```powershell
docker build -f docker\sandbox\Dockerfile -t blacknode-sandbox:latest .
```

Editor backend port already in use:

```powershell
Get-NetTCPConnection -LocalPort 7777 -State Listen
```

Editor frontend port already in use:

```powershell
Get-NetTCPConnection -LocalPort 3000 -State Listen
```

Consent keeps passing when you expected a prompt:

```powershell
Remove-Item "$env:USERPROFILE\.blacknode\learned-nodes-consent.json" -ErrorAction SilentlyContinue
Remove-Item Env:\BLACKNODE_LEARNED_NODES_CONSENT -ErrorAction SilentlyContinue
```

Then retry `create_node_type`.

Demo dry run fails after creating a node:

```powershell
Get-ChildItem nodes\learned
```

Delete only the temporary test node directory if it was left behind by an
interrupted run. Do not delete unrelated user-created learned nodes.
