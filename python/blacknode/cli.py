from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .exporters import export_workflow as export_framework_workflow
from .exporters import list_export_targets
from .learned import registry as learned_registry
from .python_importer import PythonImportError, import_workflow_python
from .sandbox import docker_runner
from .workflow import WorkflowRunError, export_workflow_python, load_workflow, run_workflow, validate_workflow


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate(args.workflow)
    if args.command == "run":
        return _run(args.workflow, args.output)
    if args.command == "export-python":
        return _export_python(args.workflow, args.output, args.style)
    if args.command == "import-python":
        return _import_python(args.script, args.output, args.name)
    if args.command == "export-framework":
        return _export_framework(args.workflow, args.target, args.output)
    if args.command == "export-training":
        return _export_training(args)
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
    export_python.add_argument(
        "--style",
        choices=["flat", "class"],
        default="flat",
        help="Python script style to generate",
    )

    import_python = subcommands.add_parser("import-python", help="import a Blacknode Python export as workflow JSON")
    import_python.add_argument("script", type=Path)
    import_python.add_argument("--output", "-o", type=Path, help="write workflow JSON to this path")
    import_python.add_argument("--name", help="workflow name to store in imported JSON")

    export_framework = subcommands.add_parser(
        "export-framework",
        help="export a workflow JSON file for LangGraph, CrewAI, AutoGen, Swarm, or plain Python",
    )
    export_framework.add_argument("workflow", type=Path)
    export_framework.add_argument(
        "--target",
        "-t",
        choices=[target["id"] for target in list_export_targets()],
        default="langgraph",
        help="framework export target",
    )
    export_framework.add_argument("--output", "-o", type=Path, help="write exported code to this path")

    export_training = subcommands.add_parser(
        "export-training",
        help="export recorded trajectories as a fine-tuning dataset (TRL / Unsloth / OpenPipe)",
    )
    export_training.add_argument("input", type=Path, help="trajectories directory or a single .jsonl file")
    export_training.add_argument(
        "--format",
        "-f",
        default="chat",
        help="dataset schema: chat (default, OpenAI messages) | sharegpt | dpo. 'jsonl' aliases chat.",
    )
    export_training.add_argument("--output", "-o", type=Path, help="write dataset JSONL here (default: stdout)")
    export_training.add_argument("--min-score", type=float, dest="min_score", help="keep trajectories scoring >= this")
    export_training.add_argument("--label", help="keep trajectories with this rating label (e.g. up)")
    export_training.add_argument("--tag", help="keep trajectories carrying this tag")
    export_training.add_argument(
        "--rated-only", action="store_true", dest="rated_only", help="drop trajectories with no rating"
    )

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


def _export_python(path: Path, output: Path | None, style: str = "flat") -> int:
    try:
        script = export_workflow_python(load_workflow(path), style=style)
    except (OSError, json.JSONDecodeError, WorkflowRunError, Exception) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if output is None:
        print(script)
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(script, encoding="utf-8")
    return 0


def _import_python(path: Path, output: Path | None, name: str | None) -> int:
    try:
        source = path.read_text(encoding="utf-8")
        workflow = import_workflow_python(source, name=name or path.stem)
        report = validate_workflow(workflow)
        if not report.ok:
            print(json.dumps(report.to_dict(), indent=2), file=sys.stderr)
            return 1
    except (OSError, SyntaxError, PythonImportError, WorkflowRunError, Exception) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _write_json(workflow, output)
    return 0


def _export_framework(path: Path, target: str, output: Path | None) -> int:
    try:
        result = export_framework_workflow(load_workflow(path), target)
    except (OSError, json.JSONDecodeError, WorkflowRunError, ValueError, Exception) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    code = result["code"]
    if output is None:
        print(code)
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(code, encoding="utf-8")
    return 0


def _export_training(args: argparse.Namespace) -> int:
    from .training.export import KNOWN_FORMATS, export_dataset, write_jsonl

    fmt = (args.format or "chat").lower()
    if fmt not in KNOWN_FORMATS:
        print(f"Unknown --format '{args.format}'. Choose from: chat, sharegpt, dpo.", file=sys.stderr)
        return 2
    try:
        records, stats = export_dataset(
            args.input,
            fmt=fmt,
            min_score=args.min_score,
            label=args.label,
            tag=args.tag,
            rated_only=args.rated_only,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    write_jsonl(records, args.output)
    summary = (
        f"[{stats['format']}] {stats['records_written']} records "
        f"from {stats['trajectories_selected']}/{stats['trajectories_found']} trajectories "
        f"({stats['rated']} rated)"
    )
    if args.output is not None:
        summary += f" -> {args.output}"
    print(summary, file=sys.stderr)
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

    _learned_count, learned_detail = _learned_nodes_doctor_detail()
    add("Learned nodes", True, learned_detail, required=False)

    sandbox_status = docker_runner.learned_node_runtime_status()
    docker_ok = bool(sandbox_status["docker_available"]) and not bool(sandbox_status["disabled"])
    add("Docker", docker_ok, str(sandbox_status["detail"]), required=False)
    image_detail = str(sandbox_status["detail"])
    if sandbox_status["docker_available"]:
        image_detail = f"{sandbox_status['image']} ({'present' if sandbox_status['image_present'] else 'missing'})"
    add("Sandbox image", bool(sandbox_status["image_present"]), image_detail, required=False)
    add(
        "Last sandbox run",
        True,
        _sandbox_duration_detail(sandbox_status.get("last_execution_duration_seconds")),
        required=False,
    )

    print("Blacknode doctor")
    use_color = _terminal_color_enabled()
    for label, ok, detail, required in checks:
        status = _doctor_status(ok, required, color=use_color)
        print(f"{status} {label}: {detail}")

    required_ok = all(ok for _label, ok, _detail, required in checks if required)
    summary = "Required checks passed." if required_ok else "Required checks failed."
    print(_color_text(summary, "green" if required_ok else "red", enabled=use_color))
    return 0 if required_ok else 1


def _mcp(args: argparse.Namespace | None = None) -> int:
    from .mcp import main as run_mcp

    try:
        run_mcp(
            transport=getattr(args, "transport", "stdio"),
            host=getattr(args, "host", None),
            port=getattr(args, "port", None),
            path=getattr(args, "path", None),
            allowed_hosts=getattr(args, "allowed_hosts", None),
        )
    except KeyboardInterrupt:
        return 130
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


def _learned_nodes_doctor_detail() -> tuple[int, str]:
    loaded = sorted(learned_registry.LEARNED_NODE_MANIFESTS)
    base = learned_registry.learned_dir()
    skipped = {}
    report = getattr(sys.modules.get("blacknode"), "_LEARNED_REPORT", None)
    if report is not None and hasattr(report, "skipped"):
        skipped = dict(report.skipped)
    detail = f"{len(loaded)} loaded from {base}"
    if skipped:
        detail += f"; {len(skipped)} skipped"
    return len(loaded), detail


def _sandbox_duration_detail(value: Any) -> str:
    if value is None:
        return "no sandbox runs in this process"
    try:
        return f"{float(value):.3f}s"
    except (TypeError, ValueError):
        return str(value)


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


def _doctor_status(ok: bool, required: bool, *, color: bool | None = None) -> str:
    enabled = _terminal_color_enabled() if color is None else color
    if ok:
        return _color_text("[OK]", "green", enabled=enabled)
    if required:
        return _color_text("[NOT OK]", "red", enabled=enabled)
    return _color_text("[WARN]", "yellow", enabled=enabled)


def _terminal_color_enabled() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    force_color = os.environ.get("FORCE_COLOR")
    if force_color is not None:
        return force_color not in {"", "0", "false", "False"}
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _color_text(text: str, color: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    codes = {
        "green": "32",
        "yellow": "33",
        "red": "31",
    }
    code = codes[color]
    return f"\033[{code}m{text}\033[0m"


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
