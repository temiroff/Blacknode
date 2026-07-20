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
    if args.command == "drivers":
        return _drivers(args)
    if args.command == "slack":
        return _run_driver("slack", args)
    if args.command == "telegram":
        return _run_driver("telegram", args)
    if args.command == "demo":
        return _demo(args.workflow, args.json)
    if args.command == "doctor":
        return _doctor()
    if args.command == "packages":
        return _packages(args)
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

    drivers = subcommands.add_parser(
        "drivers",
        help="list integration drivers and whether each is registered and activated",
    )
    drivers.add_argument("--json", action="store_true", help="print machine-readable JSON")

    slack = subcommands.add_parser(
        "slack",
        help="run a workflow as a Slack bot (e.g. a NIM agent with tools)",
    )
    slack.add_argument("workflow", type=Path, help="agent workflow JSON to drive")
    slack.add_argument(
        "--input-node",
        dest="input_node",
        help="node id that receives each Slack message (default: auto-detect the agent prompt source)",
    )
    slack.add_argument(
        "--max-turns", type=int, default=6, dest="max_turns", help="conversation turns kept per thread"
    )

    telegram = subcommands.add_parser(
        "telegram",
        help="run a workflow as a Telegram bot (e.g. a NIM agent with tools)",
    )
    telegram.add_argument("workflow", type=Path, help="agent workflow JSON to drive")
    telegram.add_argument(
        "--input-node",
        dest="input_node",
        help="node id that receives each Telegram message (default: auto-detect the agent prompt source)",
    )
    telegram.add_argument(
        "--max-turns", type=int, default=6, dest="max_turns", help="conversation turns kept per chat"
    )

    demo = subcommands.add_parser("demo", help="run the built-in no-key demo workflow")
    demo.add_argument("--workflow", type=Path, help="workflow JSON to run instead of templates/text-pipeline.json")
    demo.add_argument("--json", action="store_true", help="print the full JSON run result")

    subcommands.add_parser("doctor", help="check the local Blacknode development environment")

    packages = subcommands.add_parser("packages", help="list or install Blacknode extension packages")
    packages_sub = packages.add_subparsers(dest="packages_command")
    packages_sub.add_parser("list", help="show installed extension packages")
    packages_status = packages_sub.add_parser("status", help="show package load, node, and git status")
    packages_status.add_argument("--fetch", action="store_true", help="fetch remotes before reporting git ahead/behind state")
    packages_update = packages_sub.add_parser("update", help="fetch and fast-forward clean installed package repos")
    packages_update.add_argument("names", nargs="*", help="package names to update; defaults to every installed folder package")
    packages_update.add_argument("--all", action="store_true", help="update every installed folder package")
    packages_update.add_argument("--deps", action="store_true", help="reinstall package prerequisites after updating")
    packages_install = packages_sub.add_parser(
        "install", help="git clone a package repo into packages/ and install its pip deps"
    )
    packages_install.add_argument("url", help="git URL of the package repository")
    packages_install.add_argument("--directory", type=Path, help="override the packages/ root folder")
    packages_install.add_argument("--no-deps", action="store_true", help="skip installing pip deps and Docker images")
    packages_setup = packages_sub.add_parser(
        "setup", help="install the prerequisites (pip deps, Docker images) of an already-cloned package"
    )
    packages_setup.add_argument("name", nargs="?", help="package folder name under packages/")
    packages_setup.add_argument("--directory", type=Path, help="override the packages/ root folder")
    packages_setup.add_argument(
        "--missing", action="store_true",
        help="install Python dependencies only for installed packages whose declared imports are missing",
    )
    packages_components = packages_sub.add_parser(
        "components", help="show selectively managed components and their activation state"
    )
    packages_components.add_argument("name", nargs="?", help="limit output to one installed package")
    packages_enable = packages_sub.add_parser("enable", help="enable one package component")
    packages_enable.add_argument("name", help="installed package name")
    packages_enable.add_argument("component", help="component name")
    packages_disable = packages_sub.add_parser("disable", help="disable one package component")
    packages_disable.add_argument("name", help="installed package name")
    packages_disable.add_argument("component", help="component name")

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


def _packages(args: Any) -> int:
    if args.packages_command == "list":
        return _packages_list()
    if args.packages_command == "status":
        return _packages_status(args.fetch)
    if args.packages_command == "update":
        return _packages_update(args.names, args.all, args.deps)
    if args.packages_command == "install":
        return _packages_install(args.url, args.directory, args.no_deps)
    if args.packages_command == "setup":
        return _packages_setup(args.name, args.directory, args.missing)
    if args.packages_command == "components":
        return _packages_components(args.name)
    if args.packages_command == "enable":
        return _packages_set_component(args.name, args.component, True)
    if args.packages_command == "disable":
        return _packages_set_component(args.name, args.component, False)
    print("usage: blacknode packages {list,status,update,install,setup,components,enable,disable}", file=sys.stderr)
    return 2


def _packages_list() -> int:
    import blacknode  # noqa: F401  triggers package discovery

    from .packages import installed_packages

    packages = installed_packages()
    if not packages:
        print("No extension packages installed.")
        print("Clone one into packages/ or run: blacknode packages install <git-url>")
        return 0
    for info in packages:
        status = _package_status_label(info)
        print(f"{info.name} {info.version or '?'} [{status}] {len(info.node_types)} nodes  {info.path}")
        if info.missing_node_types:
            print("  missing nodes: " + ", ".join(info.missing_node_types))
        if not info.ok:
            last_line = info.error.strip().splitlines()[-1] if info.error.strip() else "unknown error"
            print(f"  {last_line}")
        _print_package_warnings(info)
    return 0


def _package_status_label(info: Any) -> str:
    if not info.ok:
        return "FAILED"
    warnings = getattr(info, "warnings", []) or []
    missing_nodes = getattr(info, "missing_node_types", []) or []
    if missing_nodes:
        return "ok, nodes missing"
    if warnings:
        return "ok, deps missing"
    return "ok"


def _print_package_warnings(info: Any) -> None:
    for warning in getattr(info, "warnings", []) or []:
        for line in warning.splitlines():
            print(f"  ! {line}")


def _packages_status(fetch: bool = False) -> int:
    import blacknode  # noqa: F401  triggers package discovery

    from .packages import package_statuses

    statuses = package_statuses(fetch=fetch)
    if not statuses:
        print("No extension packages installed.")
        print("Clone one into packages/ or run: blacknode packages install <git-url>")
        return 0
    for info in statuses:
        status = "FAILED" if not info.get("ok", False) else "ok"
        if info.get("ok", False) and info.get("missing_node_types"):
            status = "ok, nodes missing"
        elif info.get("ok", False) and info.get("warnings"):
            status = "ok, warnings"
        git = info.get("git_status") or {}
        git_parts: list[str] = []
        if git.get("is_git_repo"):
            branch = git.get("branch") or "detached"
            git_parts.append(str(branch))
            if git.get("dirty"):
                git_parts.append("dirty")
            ahead = git.get("ahead")
            behind = git.get("behind")
            if ahead:
                git_parts.append(f"ahead {ahead}")
            if behind:
                git_parts.append(f"behind {behind}")
            if git.get("fetch_error"):
                git_parts.append("fetch failed")
        print(f"{info['name']} {info.get('version') or '?'} [{status}] {len(info.get('node_types') or [])} nodes  {info.get('path') or ''}")
        if git_parts:
            print("  git: " + ", ".join(git_parts))
        if info.get("missing_node_types"):
            print("  missing nodes: " + ", ".join(info["missing_node_types"]))
        if not info.get("ok", False):
            error = str(info.get("error") or "").strip()
            print(f"  {error.splitlines()[-1] if error else 'unknown error'}")
        for warning in info.get("warnings") or []:
            for line in str(warning).splitlines():
                print(f"  ! {line}")
        if git.get("fetch_error"):
            print(f"  ! fetch: {git['fetch_error']}")
    return 0


def _packages_update(names: list[str], all_packages: bool, deps: bool) -> int:
    import blacknode  # noqa: F401  triggers package discovery

    from .packages import update_packages

    if all_packages:
        names = []
    result = update_packages(names or None, install_deps=deps)
    for item in result["updated"]:
        package = item.get("package") or {}
        print(f"updated {item['name']}: {len(package.get('node_types') or [])} nodes")
    for item in result["skipped"]:
        print(f"skipped {item['name']}: {item['reason']}")
    for item in result["failed"]:
        print(f"failed {item['name']}: {item['error']}", file=sys.stderr)
    if result["updated"]:
        print("Restart Blacknode (or press Reload in the editor Packages tab) to use updated nodes.")
    return 0 if result["ok"] else 1

def _packages_install(url: str, directory: Path | None, no_deps: bool) -> int:
    from .packages import install_from_git

    result = install_from_git(url, root=directory, install_deps=not no_deps)
    if result["ok"]:
        print("Restart Blacknode (or press Reload in the editor Packages tab) to use the new nodes.")
        return 0
    print(f"error: {result['error']}", file=sys.stderr)
    return 1


def _packages_setup(name: str | None, directory: Path | None, missing: bool = False) -> int:
    """(Re)install the prerequisites of an already-cloned package."""
    if missing:
        if name or directory:
            print("error: --missing cannot be combined with a package name or --directory", file=sys.stderr)
            return 2
        import blacknode  # noqa: F401 - triggers package discovery

        from .packages import install_missing_python_dependencies

        result = install_missing_python_dependencies()
        if not result["installed"] and not result["failed"]:
            print("All installed package Python dependencies are already available.")
        for item in result["installed"]:
            print(f"installed {item['name']} Python dependencies")
        for item in result["failed"]:
            print(f"failed {item['name']}: {item['error']}", file=sys.stderr)
        return 0 if result["ok"] else 1
    if not name:
        print("error: package name is required unless --missing is used", file=sys.stderr)
        return 2

    from .packages import MANIFEST_NAME, install_prerequisites, load_package, packages_root

    root = (directory or packages_root()).expanduser().resolve()
    dest = root / name
    if not (dest / MANIFEST_NAME).exists():
        print(f"error: {dest} is not a Blacknode package (no {MANIFEST_NAME})", file=sys.stderr)
        return 1
    install_prerequisites(dest)
    info = load_package(dest)
    if info.ok:
        print(f"{info.name} {info.version or ''} loads OK: {len(info.node_types)} nodes")
        return 0
    print(f"Package still fails to load:\n{info.error}", file=sys.stderr)
    return 1


def _packages_components(name: str | None) -> int:
    import blacknode  # noqa: F401 - triggers package discovery

    from .packages import installed_packages

    packages = [info for info in installed_packages() if not name or info.name == name]
    if name and not packages:
        print(f"error: no package named '{name}' is installed", file=sys.stderr)
        return 1
    shown = False
    for info in packages:
        if not info.components:
            continue
        shown = True
        mode = "selective" if info.component_mode else "catalog only"
        print(f"{info.name} [{mode}]")
        for component in info.components.values():
            state = "enabled" if component.get("enabled") else "disabled"
            default = " (default)" if component.get("default") else ""
            print(f"  {component['name']}: {state}{default}")
    if not shown:
        target = f"Package '{name}' has" if name else "Installed packages have"
        print(f"{target} no declared components.")
    return 0


def _packages_set_component(name: str, component: str, enabled: bool) -> int:
    import blacknode  # noqa: F401 - triggers package discovery

    from .packages import set_component_enabled

    try:
        info = set_component_enabled(name, component, enabled)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    action = "enabled" if enabled else "disabled"
    print(f"{action} {name}/{component}: {len(info.node_types)} package nodes active")
    _print_package_warnings(info)
    return 0


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


def _drivers(args: argparse.Namespace) -> int:
    import blacknode.integrations  # noqa: F401 - import side effect registers drivers
    from .integrations.registry import driver_status, list_drivers

    statuses = [driver_status(spec) for spec in list_drivers()]
    if getattr(args, "json", False):
        _write_json({"drivers": statuses}, None)
        return 0
    if not statuses:
        print("No integration drivers registered.")
        return 0

    use_color = _terminal_color_enabled()
    print("Blacknode drivers")
    for st in statuses:
        color = "green" if st["status"] == "ready" else "yellow"
        tag = _color_text(f"[{st['status']}]", color, enabled=use_color)
        print(f"{tag} {st['name']} - {st['description']}")
        pkg_state = "installed" if st["packages_installed"] else "missing"
        print(f"    extra: {st['extra']} ({pkg_state})")
        if st["env"]:
            env_state = ", ".join(f"{name} ({'set' if present else 'missing'})" for name, present in st["env"].items())
            print(f"    env:   {env_state}")
    return 0


def _run_driver(name: str, args: argparse.Namespace) -> int:
    import blacknode.integrations  # noqa: F401 - import side effect registers drivers
    from .integrations.registry import get_driver, missing_env, packages_installed
    from .integrations.slack_runtime import (
        AgentRuntime,
        ConversationMemory,
        DriverDependencyError,
        SlackConfigError,
    )

    spec = get_driver(name)
    if spec is None:
        print(f"Unknown driver '{name}'. Run 'blacknode drivers' to list them.", file=sys.stderr)
        return 2
    if not packages_installed(spec):
        print(f"The {name} driver needs its extra. Run: pip install 'blacknode[{spec.required_extra}]'", file=sys.stderr)
        return 1
    missing = missing_env(spec)
    if missing:
        print(f"Set {', '.join(missing)} to run the {name} driver.", file=sys.stderr)
        return 1

    try:
        workflow = load_workflow(args.workflow)
        runtime = AgentRuntime(
            workflow,
            input_node=args.input_node,
            memory=ConversationMemory(max_turns=args.max_turns),
        )
    except (OSError, json.JSONDecodeError, WorkflowRunError, SlackConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Blacknode {name} driver running ({args.workflow}); input node: {runtime.input_node}. Ctrl-C to stop.")
    try:
        spec.run(runtime)
    except DriverDependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
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
