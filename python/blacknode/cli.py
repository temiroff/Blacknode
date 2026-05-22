from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .workflow import WorkflowRunError, export_workflow_python, load_workflow, run_workflow, validate_workflow


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate(args.workflow)
    if args.command == "run":
        return _run(args.workflow, args.output)
    if args.command == "export-python":
        return _export_python(args.workflow, args.output)
    if args.command == "demo":
        return _demo(args.workflow, args.json)
    if args.command == "doctor":
        return _doctor()
    if args.command == "mcp":
        return _mcp(args)
    parser.print_help()
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blacknode")
    subcommands = parser.add_subparsers(dest="command")

    validate = subcommands.add_parser("validate", help="validate a workflow JSON file")
    validate.add_argument("workflow", type=Path)

    run = subcommands.add_parser("run", help="run a workflow JSON file")
    run.add_argument("workflow", type=Path)
    run.add_argument("--output", "-o", type=Path, help="write run result JSON to this path")

    export_python = subcommands.add_parser("export-python", help="export a workflow JSON file as a Python script")
    export_python.add_argument("workflow", type=Path)
    export_python.add_argument("--output", "-o", type=Path, help="write Python script to this path")

    demo = subcommands.add_parser("demo", help="run the built-in no-key demo workflow")
    demo.add_argument("--workflow", type=Path, help="workflow JSON to run instead of templates/text-pipeline.json")
    demo.add_argument("--json", action="store_true", help="print the full JSON run result")

    subcommands.add_parser("doctor", help="check the local Blacknode development environment")

    mcp = subcommands.add_parser("mcp", help="run the Blacknode MCP server")
    mcp.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport to serve; stdio keeps existing desktop-client behavior",
    )
    mcp.add_argument("--host", default=None, help="HTTP bind host for sse or streamable-http")
    mcp.add_argument("--port", type=int, default=None, help="HTTP bind port for sse or streamable-http")
    mcp.add_argument("--path", default=None, help="HTTP mount path, default /mcp for streamable-http")
    mcp.add_argument(
        "--allowed-host",
        action="append",
        dest="allowed_hosts",
        help="Allowed Host header pattern for HTTP transport; may be repeated",
    )

    return parser


def _validate(path: Path) -> int:
    try:
        report = validate_workflow(load_workflow(path)).to_dict()
    except (OSError, json.JSONDecodeError, WorkflowRunError) as exc:
        _write_json({"ok": False, "errors": [{"message": str(exc)}], "warnings": []}, None)
        return 1

    _write_json(report, None)
    return 0 if report["ok"] else 1


def _run(path: Path, output: Path | None) -> int:
    try:
        result = run_workflow(load_workflow(path))
    except (OSError, json.JSONDecodeError, WorkflowRunError, Exception) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _write_json(result, output)
    return 0


def _export_python(path: Path, output: Path | None) -> int:
    try:
        script = export_workflow_python(load_workflow(path))
    except (OSError, json.JSONDecodeError, WorkflowRunError, Exception) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if output is None:
        print(script)
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(script, encoding="utf-8")
    return 0


def _demo(path: Path | None, as_json: bool) -> int:
    workflow_path = path or _template_path("text-pipeline.json")
    try:
        result = run_workflow(load_workflow(workflow_path))
    except (OSError, json.JSONDecodeError, WorkflowRunError, Exception) as exc:
        print(f"Blacknode demo failed: {exc}", file=sys.stderr)
        return 1

    if as_json:
        _write_json(result, None)
        return 0

    print("Blacknode demo OK")
    print(f"Workflow: {workflow_path}")
    print(f"Result: {result.get('value')}")
    print(f"Run id: {result.get('run_id')}")
    print(f"Events: {len(result.get('events', []))}")
    return 0


def _doctor() -> int:
    checks: list[tuple[str, bool, str, bool]] = []

    def add(label: str, ok: bool, detail: str, *, required: bool = True) -> None:
        checks.append((label, ok, detail, required))

    python_ok = sys.version_info >= (3, 11)
    add("Python", python_ok, f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    try:
        import blacknode  # noqa: F401
        add("Blacknode package", True, "importable")
    except Exception as exc:
        add("Blacknode package", False, str(exc))

    template_path = _template_path("text-pipeline.json")
    add("Demo template", template_path.exists(), str(template_path))

    if template_path.exists():
        try:
            workflow = load_workflow(template_path)
            report = validate_workflow(workflow).to_dict()
            add("Workflow validation", bool(report["ok"]), f"{len(report['errors'])} errors")
            try:
                result = run_workflow(workflow)
                add("Workflow run", result.get("value") == "Hello World", f"value={result.get('value')!r}")
            except Exception as exc:
                add("Workflow run", False, str(exc))
        except Exception as exc:
            add("Workflow validation", False, str(exc))
            add("Workflow run", False, "skipped")

    node_version = _command_version("node", "--version")
    add("Node.js", _node_version_ok(node_version), node_version or "not found", required=False)

    npm_version = _command_version("npm", "--version")
    add("npm", bool(npm_version), npm_version or "not found", required=False)

    node_modules = _repo_root() / "editor" / "node_modules"
    add("Editor dependencies", node_modules.exists(), str(node_modules), required=False)

    mcp_installed = importlib.util.find_spec("mcp") is not None
    add(
        "MCP extra",
        mcp_installed,
        "installed" if mcp_installed else 'missing; run pip install -e ".[mcp]"',
        required=False,
    )

    server_ok = _url_ok("http://127.0.0.1:7777/node-types")
    add("Editor server", server_ok, "http://127.0.0.1:7777" if server_ok else "not running", required=False)

    print("Blacknode doctor")
    for label, ok, detail, required in checks:
        status = "OK" if ok else ("FAIL" if required else "WARN")
        print(f"[{status}] {label}: {detail}")

    required_ok = all(ok for _label, ok, _detail, required in checks if required)
    print("Required checks passed." if required_ok else "Required checks failed.")
    return 0 if required_ok else 1


def _mcp(args: argparse.Namespace | None = None) -> int:
    from .mcp import main as run_mcp

    run_mcp(
        transport=getattr(args, "transport", "stdio"),
        host=getattr(args, "host", None),
        port=getattr(args, "port", None),
        path=getattr(args, "path", None),
        allowed_hosts=getattr(args, "allowed_hosts", None),
    )
    return 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _template_path(name: str) -> Path:
    candidates = [
        Path.cwd() / "templates" / name,
        _repo_root() / "templates" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _command_version(command: str, version_arg: str) -> str:
    executable = shutil.which(command)
    if not executable:
        return ""
    try:
        result = subprocess.run(
            [executable, version_arg],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else ""


def _node_version_ok(version: str) -> bool:
    if not version:
        return False
    raw = version[1:] if version.startswith("v") else version
    try:
        major_text, minor_text, *_rest = raw.split(".")
        major = int(major_text)
        minor = int(minor_text)
    except (ValueError, IndexError):
        return False
    return major > 22 or (major == 22 and minor >= 12) or (major == 20 and minor >= 19)


def _url_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.8) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def _write_json(data: Any, path: Path | None) -> None:
    text = json.dumps(data, indent=2, default=str)
    if path is None:
        print(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{text}\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
