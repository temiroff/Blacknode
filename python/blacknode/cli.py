from __future__ import annotations

import argparse
import json
import sys
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


def _write_json(data: Any, path: Path | None) -> None:
    text = json.dumps(data, indent=2, default=str)
    if path is None:
        print(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{text}\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
