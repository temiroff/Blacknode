# Blacknode and NVIDIA AI-Q

Blacknode is complementary to NVIDIA AI-Q. AI-Q handles deep research and
enterprise agent orchestration. Blacknode gives the same agent stack a typed
visual workflow editor, validator, live editor surface, run replay, and Python
export path.

Positioning:

> Agent harnesses can research, code, and reason. Blacknode gives them a typed
> visual workflow editor through MCP.

## Why This Fits AI-Q

NVIDIA AI-Q exposes deep research through agent skills, and NVIDIA NeMo Agent
Toolkit workflows can consume authenticated MCP servers. Blacknode exposes a
workflow construction and debugging surface through MCP, so AI-Q or a coding
harness can use Blacknode as a workflow artifact layer rather than a competing
research engine.

Useful references:

- AI-Q agent skills: https://docs.nvidia.com/aiq-blueprint/latest/integration/agent-skills.html
- NeMo Agent Toolkit MCP client: https://docs.nvidia.com/nemo/agent-toolkit/latest/build-workflows/mcp-client.html
- AI-Q repository: https://github.com/NVIDIA-AI-Blueprints/aiq

## Streamable HTTP MCP

AI-Q and NeMo Agent Toolkit MCP client examples use streamable HTTP. Start
Blacknode's MCP server over HTTP:

```bash
blacknode mcp --transport streamable-http --host 127.0.0.1 --port 9901 --path /mcp
```

Endpoint:

```text
http://127.0.0.1:9901/mcp
```

For Docker Compose:

Windows:

```powershell
.\docker-up.ps1
```

macOS/Linux:

```bash
docker compose up --build
```

The streamable HTTP MCP endpoint is:

```text
http://127.0.0.1:9901/mcp
```

The visual editor is:

```text
http://127.0.0.1:3000
```

## Agent Skill

Blacknode ships a repo-local skill at:

```text
skills/blacknode-workflow/SKILL.md
.agents/skills/blacknode-workflow/SKILL.md
```

Use this skill when an agent needs to create, validate, run, visualize, debug,
or export Blacknode workflows. The skill points agents to the MCP tools and the
NVIDIA templates.

## Demo Script

60-second integration demo:

1. Start Blacknode:

   ```powershell
   .\docker-up.ps1
   ```

2. Start AI-Q or another harness with access to the Blacknode skill and MCP
   endpoint.

3. Prompt:

   ```text
   Use AI-Q to research how NVIDIA NIM, NeMo Retriever, and MCP fit into an
   enterprise agent stack. Then use Blacknode to visualize the recommended
   pipeline as a workflow graph and open it in the editor.
   ```

4. The harness performs research through AI-Q.

5. The harness uses Blacknode MCP tools to open
   `nvidia-video-intelligence-mission-control`, `nvidia-ai-mission-control`, or
   build a custom graph from the research result.

6. Blacknode shows the visual workflow, validation report, and run replay.

7. Export the workflow to Python as the handoff artifact.

## Included Integration Surface

Current Blacknode integration:

- MCP over stdio and streamable HTTP.
- Repo-local `SKILL.md` for agent harnesses.
- NVIDIA-oriented workflow templates and nodes.
- Docker Compose for editor, backend, persisted run history, saved workflows,
  and streamable HTTP MCP services.
