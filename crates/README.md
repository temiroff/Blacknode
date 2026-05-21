# Rust Workspace

The Rust crates are experimental. The Python runtime is still the canonical Blacknode runtime for the public preview.

Current crates:

- `blacknode-types`: shared value types for the future Rust core.
- `blacknode-core`: graph primitives and node traits.
- `blacknode-runtime`: experimental async execution layer.
- `blacknode-py`: PyO3 bridge scaffold.
- `blacknode-cli`: no-server workflow validator, inspector, and pure-node runner.

## No-Server CLI

Use this when someone wants a quick local check without starting the editor or MCP server:

```powershell
cargo run -p blacknode-cli -- validate templates\text-pipeline.json
cargo run -p blacknode-cli -- inspect templates\nvidia-nim-mcp-demo.json
cargo run -p blacknode-cli -- run-pure templates\text-pipeline.json
```

`run-pure` intentionally supports only deterministic local nodes such as `Text`, `Int`, `Float`, `Bool`, `Dict`, `Literal`, `Model`, `Concat`, math nodes, and `Output`. LLM, Python, file, HTTP, subnet, and agent nodes remain Python-runtime features for now.

This gives the project a useful Rust path without claiming that the full Rust runtime is finished.
