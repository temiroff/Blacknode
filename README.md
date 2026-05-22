# Blacknode

[![CI](https://github.com/temiroff/Blacknode/actions/workflows/ci.yml/badge.svg)](https://github.com/temiroff/Blacknode/actions/workflows/ci.yml)

**The visual workflow builder where AI agents build the workflow.**

Blacknode lets Claude Desktop, Codex, OpenCode, AI-Q, NeMo Agent Toolkit, and
other MCP clients assemble, validate, run, debug, and export typed visual
workflows. Agents get a structured tool surface instead of guessing JSON, and
users get a live graph they can inspect.

<table>
  <tr>
    <td><a href="docs/images/blacknode-light-theme.png"><img src="docs/images/blacknode-light-theme.png" alt="Blacknode visual editor light theme" width="420"></a></td>
    <td><a href="docs/images/blacknode-launcher.png"><img src="docs/images/blacknode-launcher.png" alt="Blacknode launcher terminal" width="420"></a></td>
  </tr>
  <tr>
    <td><a href="docs/images/blacknode-mcp-nim-editor-demo.png"><img src="docs/images/blacknode-mcp-nim-editor-demo.png" alt="MCP NVIDIA NIM workflow in the editor" width="420"></a></td>
    <td><a href="docs/images/blacknode-research-pipeline.png"><img src="docs/images/blacknode-research-pipeline.png" alt="Research pipeline workflow" width="420"></a></td>
  </tr>
</table>

<table>
  <tr>
    <td>
      <video src="https://github.com/user-attachments/assets/9debbc72-68d7-4717-9a44-433ae65fd4d2" controls width="420"></video>
    </td>
    <td>
      <video src="https://github.com/user-attachments/assets/16a0d311-f237-4d6f-9fec-c303fc3e41d0" controls width="420"></video>
    </td>
  </tr>
</table>

## Start Here

**New users should begin with the [Beginner Walkthrough](docs/walkthrough.md).**

It shows the exact commands to run, buttons to press, templates to open, results
to expect, NVIDIA NIM paths, MCP setup, Docker Compose, custom nodes, run
history, and troubleshooting.

## What Blacknode Gives You

- **Visual workflow editor** for building and inspecting typed node graphs.
- **Agent control through MCP** so an AI agent can create, connect, validate,
  run, organize, save, and inspect workflows.
- **NVIDIA workflow surface** for hosted NIM, local NIM launch planning,
  benchmark workflows, AI-Q integration, and streamable HTTP MCP.
- **Typed ports and validation** for Text, Int, Float, Bool, List, Dict,
  Embedding, Fn, Model, Number, and Any.
- **Run history and replay** with event logs, model calls, tool calls, node
  timings, results, and errors.
- **Python export** so a visual graph can become readable Python.
- **Docker Compose deployment** for local, cloud VM, and on-prem demos.

## NVIDIA Agent Stack

Blacknode complements NVIDIA AI-Q and NeMo Agent Toolkit by giving agent
harnesses a visual workflow surface. AI-Q can research and reason over
enterprise data; Blacknode turns agent intent into typed, visible, runnable
workflows through MCP.

**Blacknode is the visual workflow editor for the NVIDIA agent stack.**

See [Blacknode and NVIDIA AI-Q](docs/aiq-integration.md) and
[NVIDIA Mission Control](docs/nvidia-mission-control.md).

## Documentation

### First Run

| Guide | Use it for |
|---|---|
| [Beginner Walkthrough](docs/walkthrough.md) | Step-by-step setup, editor use, CLI checks, NVIDIA workflows, MCP, Docker, and troubleshooting. |
| [MCP Quickstart](docs/quickstart-mcp.md) | Connecting Blacknode to an MCP client. |
| [MCP Test Prompts](docs/mcp-test-prompts.md) | Copy-paste prompts for proving agent workflow control. |

### NVIDIA

| Guide | Use it for |
|---|---|
| [NVIDIA NIM Demo](docs/nvidia-nim-demo.md) | Hosted NVIDIA NIM demo path through MCP and the editor. |
| [NVIDIA Mission Control](docs/nvidia-mission-control.md) | NVIDIA nodes, templates, local readiness, local NIM launch, and benchmark flow. |
| [Blacknode and NVIDIA AI-Q](docs/aiq-integration.md) | Positioning Blacknode beside AI-Q and using streamable HTTP MCP. |
| [Docker Compose](docs/docker-compose.md) | Running the editor, backend, and HTTP MCP server as a self-hosted stack. |
| [Docker Publishing](docs/docker-publish.md) | Publishing prebuilt server/editor images to GHCR and running without local builds. |

### Workflow Reference

| Guide | Use it for |
|---|---|
| [Workflow Schema](docs/workflow-schema.md) | The saved workflow JSON format. |
| [Workflow JSON Schema](docs/workflow.schema.json) | Machine-readable schema for validation and tooling. |
| [Agent Guide](docs/agent-guide.md) | How agents should create and modify Blacknode workflows. |
| [Blacknode Skill](.agents/skills/blacknode-workflow/SKILL.md) | Agent skill instructions for workflow creation, validation, running, and export. |

## Demos

| Demo | What it shows |
|---|---|
| [MCP + NVIDIA NIM preview](https://github.com/user-attachments/assets/9debbc72-68d7-4717-9a44-433ae65fd4d2) | Claude opens, organizes, and cooks an NVIDIA NIM workflow through MCP. |
| [Run workflow live replay](https://github.com/user-attachments/assets/16a0d311-f237-4d6f-9fec-c303fc3e41d0) | The editor runs a visible graph with live node highlights and run replay. |

## Visuals

| Preview | Link |
|---|---|
| MCP + NVIDIA NIM editor demo | [docs/images/blacknode-mcp-nim-editor-demo.png](docs/images/blacknode-mcp-nim-editor-demo.png) |
| Claude Desktop MCP connector | [docs/images/blacknode-mcp-claude-connector.png](docs/images/blacknode-mcp-claude-connector.png) |
| Research pipeline template | [docs/images/blacknode-research-pipeline.png](docs/images/blacknode-research-pipeline.png) |
| Light theme | [docs/images/blacknode-light-theme.png](docs/images/blacknode-light-theme.png) |
| Dark theme | [docs/images/blacknode-dark-theme.png](docs/images/blacknode-dark-theme.png) |

## Project Map

| Path | Purpose |
|---|---|
| `python/blacknode/` | Python workflow runtime, node registry, providers, CLI, and MCP server. |
| `editor-server/` | FastAPI backend for the visual editor, cook API, workflows, and runs. |
| `editor/` | React visual workflow editor. |
| `templates/` | Tracked starter workflows. |
| `workflows/` | Local saved workflows, ignored by git. |
| `docs/` | Walkthroughs, integration guides, workflow schema, and demo assets. |
| `docker-compose.yml` | Self-hosted editor, backend, and streamable HTTP MCP stack. |
| `crates/` | Rust crates and no-server CLI. |

## License

Blacknode is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for
the full license text.
