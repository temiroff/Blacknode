# Blacknode v0.1.0 Preview Release Notes

Draft release notes for the first public preview.

## Title

Blacknode v0.1.0 Preview - visual AI workflows with MCP control

## Summary

Blacknode is a visual workflow builder for AI agents. This preview includes a React node editor, Python runtime, portable workflow JSON, CLI execution, Python export, reusable templates, run history, and an MCP server so agents can create and operate workflows through typed tools.

## Highlights

- Visual node editor with typed, color-coded ports.
- Python graph runtime with per-run evaluation.
- Workflow CLI: validate, run, export Python, and launch MCP.
- MCP server for AI-agent workflow building and editor control.
- Templates for LLM chat, NVIDIA NIM, research flows, Python tools, tool agents, and subnets.
- Run history with event timelines, model/tool call visibility, result previews, and error inspection.
- Local provider-key handling for Anthropic, OpenAI, NVIDIA NIM, and local/Ollama-style models.
- CI covering Python tests, editor build, and Rust workspace check.

## Try It

No API key required:

```powershell
pip install -e .
python -m blacknode.cli validate templates\text-pipeline.json
python -m blacknode.cli run templates\text-pipeline.json
python -m blacknode.cli export-python templates\subnet-tool-call.json --output subnet_tool_call.py
python subnet_tool_call.py
```

Start the editor on Windows:

```bat
start.bat
```

Start the MCP server:

```powershell
pip install -e ".[mcp]"
blacknode mcp
```

Then use the prompts in `docs/quickstart-mcp.md` or `docs/mcp-test-prompts.md`.

## Validation

Current local validation:

```text
python -m pytest
npm run build
cargo check
python scripts\smoke_test_mcp.py
```

Expected status:

- Python tests pass.
- Editor production build passes.
- Rust workspace check passes.
- MCP smoke test reports a healthy server.

## Known Limitations

- Public preview: graph APIs and workflow internals may change.
- Windows has the smoothest launch path through `start.bat`; macOS/Linux users can use `start.sh` or the manual two-terminal start.
- Arbitrary Python tool execution is a developer feature and should not be treated as a hardened sandbox.
- NVIDIA NIM, OpenAI, and Anthropic demos require provider credentials.
- Rust crates are present as a future runtime direction, but the packaged Python runtime is currently canonical.
- No hosted cloud workspace or team collaboration yet.

## Suggested Git Tag

```powershell
git tag v0.1.0-preview
git push origin v0.1.0-preview
```

Create the GitHub release as a prerelease and paste these notes into the release body.
