"""Run a real-world learned-node audit over an actual local folder.

Unlike ``complex_learned_demo.py``, this demo does not use baked-in input data
or mock outputs. You must point it at a real directory with ``--target``. The
script samples readable source/docs files from that directory, creates learned
nodes that analyze the sampled content, builds a 14-node workflow, runs it
through the learned-node sandbox, and can open the graph in the editor.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.sandbox import docker_runner


IGNORE_DIRS = {
    ".git",
    ".agents",
    ".claude",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

IGNORE_PATH_PREFIXES = {
    ".local-notes/",
    "editor-server/runs/",
}

TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".css",
    ".csv",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

REAL_REPO_INVENTORY_CODE = """import json


def run(snapshot):
    data = json.loads(snapshot or "{}")
    files = data.get("files", [])
    by_ext = {}
    by_domain = {}
    total_bytes = 0
    largest = []
    key_files = []
    markers = {
        "has_readme": False,
        "has_tests": False,
        "has_docs": False,
        "has_package_manifest": False,
    }
    for item in files:
        path = str(item.get("path", ""))
        suffix = str(item.get("suffix", "")).lower() or "<none>"
        size = int(item.get("size", 0) or 0)
        total_bytes += size
        by_ext[suffix] = by_ext.get(suffix, 0) + 1
        lower = path.lower()
        domain = lower.split("/", 1)[0] if "/" in lower else "<root>"
        by_domain[domain] = by_domain.get(domain, 0) + 1
        if lower.endswith("readme.md") or lower.endswith("readme.txt"):
            markers["has_readme"] = True
        if "test" in lower or "spec" in lower:
            markers["has_tests"] = True
        if lower.startswith("docs/") or "/docs/" in lower:
            markers["has_docs"] = True
        if lower.endswith(("package.json", "pyproject.toml", "cargo.toml", "requirements.txt")):
            markers["has_package_manifest"] = True
        if (
            lower in {"readme.md", "pyproject.toml", "package.json", "cargo.toml"}
            or lower.startswith(("python/blacknode/", "scripts/", "tests/", "docs/"))
        ):
            key_files.append(path)
        largest.append({"path": path, "size": size})
    largest.sort(key=lambda row: row["size"], reverse=True)
    top_domains = sorted(by_domain.items(), key=lambda row: (-row[1], row[0]))[:8]
    return {
        "inventory": {
            "target": data.get("target", ""),
            "sampled_files": len(files),
            "candidate_files": data.get("candidate_files", len(files)),
            "total_sampled_bytes": total_bytes,
            "extensions": by_ext,
            "domains": [{"name": name, "files": count} for name, count in top_domains],
            "largest_files": largest[:8],
            "key_files": key_files[:12],
            "markers": markers,
        }
    }
"""

REAL_REPO_FINDINGS_CODE = """import json
import re


SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|secret|token|password)\\s*[:=]\\s*['\\\"]([^'\\\"]{8,})['\\\"]")
DANGEROUS_PATTERNS = [
    ("high", "Dynamic code execution found; verify the input is trusted.", re.compile(r"\\b(eval|exec)\\s*\\(")),
    ("high", "Shell command execution with shell=True found.", re.compile(r"shell\\s*=\\s*True")),
    ("medium", "Subprocess usage found; verify arguments and error handling.", re.compile(r"\\bsubprocess\\.")),
]
PLACEHOLDER_TOKENS = ("example", "placeholder", "your_", "your-", "changeme", "dummy", "token", "xxxx", "...")


def run(snapshot):
    data = json.loads(snapshot or "{}")
    files = data.get("files", [])
    findings = []
    has_tests = False
    has_readme = False
    seen = set()

    def add(severity, path, line, message, evidence=""):
        key = (severity, path, line, message)
        if key in seen:
            return
        seen.add(key)
        findings.append({
            "severity": severity,
            "path": path,
            "line": line,
            "message": message,
            "evidence": evidence[:220],
        })

    for item in files:
        path = str(item.get("path", ""))
        text = str(item.get("text", ""))
        lower_path = path.lower()
        if "test" in lower_path or "spec" in lower_path:
            has_tests = True
        if lower_path.endswith("readme.md") or lower_path.endswith("readme.txt"):
            has_readme = True
        if int(item.get("line_count", 0) or 0) > 600:
            add("medium", path, 0, "Large sampled file; inspect for split or ownership boundaries.")
        for index, line in enumerate(text.splitlines(), start=1):
            clean = line.strip()
            lower = clean.lower()
            if "todo" in lower or "fixme" in lower or "hack" in lower:
                add("medium", path, index, "Deferred work marker found.", clean)
            secret_match = SECRET_PATTERN.search(clean)
            if secret_match:
                value = secret_match.group(2).lower()
                if not any(token in value for token in PLACEHOLDER_TOKENS):
                    add("high", path, index, "Potential hardcoded secret-like assignment.", clean)
            for severity, message, pattern in DANGEROUS_PATTERNS:
                if pattern.search(clean):
                    add(severity, path, index, message, clean)
    if not has_tests:
        add("medium", ".", 0, "No sampled test/spec files found.")
    if not has_readme:
        add("low", ".", 0, "No README found in sampled files.")
    weight = {"high": 3, "medium": 2, "low": 1}
    findings.sort(key=lambda item: (weight.get(item.get("severity"), 0), item.get("path", "")), reverse=True)
    return {
        "findings": {
            "items": findings[:24],
            "count": len(findings),
            "high": sum(1 for item in findings if item.get("severity") == "high"),
            "medium": sum(1 for item in findings if item.get("severity") == "medium"),
            "low": sum(1 for item in findings if item.get("severity") == "low"),
        }
}
"""

REAL_REPO_ARCHITECTURE_CODE = """import json


LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".md": "Markdown",
    ".json": "JSON",
    ".toml": "TOML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".sh": "Shell",
    ".bat": "Batch",
}


def run(snapshot):
    data = json.loads(snapshot or "{}")
    files = data.get("files", [])
    languages = {}
    domains = {}
    key_files = []
    entrypoints = []
    test_assets = []
    manifest_signals = []
    feature_signals = set()
    package_scripts = []

    for item in files:
        path = str(item.get("path", ""))
        lower = path.lower()
        suffix = str(item.get("suffix", "")).lower()
        text = str(item.get("text", ""))
        language = LANGUAGE_BY_SUFFIX.get(suffix)
        if language:
            languages[language] = languages.get(language, 0) + 1
        domain = lower.split("/", 1)[0] if "/" in lower else "<root>"
        domains[domain] = domains.get(domain, 0) + 1

        if lower in {"readme.md", "pyproject.toml", "package.json", "cargo.toml"}:
            key_files.append(path)
        if lower.startswith(("python/blacknode/", "editor/src/", "editor-server/", "crates/", "scripts/")):
            key_files.append(path)
        if "if __name__ == \\"__main__\\"" in text or "argparse." in text or "uvicorn" in text:
            entrypoints.append(path)
        if lower.startswith("tests/") or "/tests/" in lower or "test_" in lower or lower.endswith((".spec.ts", ".test.ts")):
            test_assets.append(path)
        if lower.endswith("package.json"):
            try:
                package = json.loads(text)
                scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
                if isinstance(scripts, dict):
                    package_scripts.extend(sorted(str(name) for name in scripts)[:8])
            except Exception:
                pass
            manifest_signals.append("Node/JavaScript package manifest")
        if lower.endswith("pyproject.toml"):
            manifest_signals.append("Python project manifest")
        if lower.endswith("cargo.toml"):
            manifest_signals.append("Rust project manifest")

        text_lower = text.lower()
        for needle, label in [
            ("blacknode", "Blacknode workflow runtime"),
            ("mcp", "MCP integration"),
            ("learned node", "learned-node extension point"),
            ("docker", "Docker-backed sandboxing"),
            ("workflow", "visual workflow graph"),
            ("nvidia", "NVIDIA-oriented demos"),
            ("editor", "browser editor surface"),
        ]:
            if needle in text_lower:
                feature_signals.add(label)

    ordered_languages = sorted(languages.items(), key=lambda row: (-row[1], row[0]))
    ordered_domains = sorted(domains.items(), key=lambda row: (-row[1], row[0]))
    test_commands = []
    if test_assets:
        test_commands.append("python -m unittest discover -s tests")
    if "test" in package_scripts:
        test_commands.append("npm test")
    if "build" in package_scripts:
        test_commands.append("npm run build")
    if any(signal == "Rust project manifest" for signal in manifest_signals):
        test_commands.append("cargo test")

    feature_text = ", ".join(sorted(feature_signals)[:5])
    if feature_text:
        summary = f"Repo appears to be a {feature_text} project."
    else:
        summary = "Repo appears to be a multi-file software project with source, docs, and configuration."

    return {
        "architecture": {
            "summary": summary,
            "languages": [{"name": name, "files": count} for name, count in ordered_languages[:8]],
            "domains": [{"name": name, "files": count} for name, count in ordered_domains[:8]],
            "key_files": list(dict.fromkeys(key_files))[:14],
            "entrypoints": list(dict.fromkeys(entrypoints))[:10],
            "test_assets": list(dict.fromkeys(test_assets))[:10],
            "manifest_signals": list(dict.fromkeys(manifest_signals))[:8],
            "feature_signals": sorted(feature_signals)[:10],
            "test_commands": list(dict.fromkeys(test_commands)),
        }
    }
"""

REAL_REPO_BRIEFING_CODE = """def run(inventory, findings, architecture, context, target):
    inventory = inventory if isinstance(inventory, dict) else {}
    findings = findings if isinstance(findings, dict) else {}
    architecture = architecture if isinstance(architecture, dict) else {}
    markers = inventory.get("markers", {}) if isinstance(inventory.get("markers", {}), dict) else {}
    items = findings.get("items", []) if isinstance(findings.get("items", []), list) else []
    target_text = str(target or inventory.get("target", "") or "")
    target_name = target_text.rstrip("\\\\/").replace("\\\\", "/").split("/")[-1] or target_text

    def join_names(rows, limit=6):
        out = []
        for row in rows[:limit] if isinstance(rows, list) else []:
            if isinstance(row, dict):
                out.append(f"{row.get('name')}: {row.get('files')}")
        return ", ".join(out) if out else "none"

    def location(item):
        path = str(item.get("path", "."))
        line = int(item.get("line", 0) or 0)
        return f"{path}:{line}" if line else path

    actions = []
    if findings.get("high", 0):
        actions.append("Review high-severity findings before sharing or demoing this repo.")
    if not markers.get("has_tests"):
        actions.append("Expose test/spec coverage in the audited path or raise --max-files.")
    if not markers.get("has_readme"):
        actions.append("Add or surface README context for the audited path.")
    if architecture.get("test_commands"):
        actions.append("Run verification commands: " + ", ".join(architecture.get("test_commands", [])[:4]))
    if not actions:
        actions.append("No blocking audit marker found in the sampled files; inspect top findings manually.")

    lines = [
        f"# Real repo audit: {target_name}",
        "",
        "## What this repo appears to be",
        f"- {architecture.get('summary', 'No architecture summary produced.')}",
        f"- Languages sampled: {join_names(architecture.get('languages', []))}",
        f"- Main areas sampled: {join_names(architecture.get('domains', []))}",
    ]

    feature_signals = architecture.get("feature_signals", [])
    if feature_signals:
        lines.append("- Product signals: " + ", ".join(str(item) for item in feature_signals[:8]))
    if architecture.get("manifest_signals"):
        lines.append("- Manifests: " + ", ".join(str(item) for item in architecture.get("manifest_signals", [])[:6]))

    lines.extend([
        "",
        "## Audit coverage",
        f"- Prioritized {inventory.get('sampled_files', 0)} files from {inventory.get('candidate_files', inventory.get('sampled_files', 0))} readable candidates.",
        f"- Sampled bytes: {inventory.get('total_sampled_bytes', 0)}",
        f"- Extension mix: {inventory.get('extensions', {})}",
    ])
    key_files = architecture.get("key_files", []) or inventory.get("key_files", [])
    if key_files:
        lines.append("- Key files read: " + ", ".join(str(path) for path in key_files[:10]))
    if architecture.get("entrypoints"):
        lines.append("- Likely entrypoints: " + ", ".join(str(path) for path in architecture.get("entrypoints", [])[:8]))

    lines.extend([
        "",
        "## Findings with evidence",
        f"- Total: {findings.get('count', 0)} | high: {findings.get('high', 0)} | medium: {findings.get('medium', 0)} | low: {findings.get('low', 0)}",
    ])
    if items:
        for index, item in enumerate(items[:8], start=1):
            severity = str(item.get("severity", "info")).upper()
            evidence = str(item.get("evidence", "") or "").strip()
            suffix = f" Evidence: {evidence}" if evidence else ""
            lines.append(f"{index}. [{severity}] {location(item)} - {item.get('message', '')}{suffix}")
    else:
        lines.append("- No findings from the deterministic sampled-file checks.")

    context_text = " ".join(str(context or "").split())
    if context_text:
        lines.extend([
            "",
            "## Retrieved context",
            "- " + context_text[:420],
        ])

    lines.extend([
        "",
        "## Recommended next moves",
    ])
    for action in actions[:6]:
        lines.append(f"- {action}")

    lines.extend([
        "",
        "## Why this demo is not canned",
        "- The learned nodes were created at runtime and executed in the Docker sandbox.",
        "- The report uses the actual sampled file contents from --target, not fixture text.",
        "- The graph combines learned analysis nodes with built-in chunking, keyword indexing, search, and context assembly.",
    ])
    return {"report": "\\n".join(lines)}
"""

LEARNED_NODE_SPECS = [
    {
        "name": "RealRepoInventory",
        "description": "Summarize real local repository file inventory from a sampled snapshot.",
        "category": "Repo",
        "inputs": ["snapshot:Text"],
        "outputs": ["inventory:Dict"],
        "code": REAL_REPO_INVENTORY_CODE,
    },
    {
        "name": "RealRepoFindings",
        "description": "Scan real sampled repository files for TODOs, risk markers, and secret-like text.",
        "category": "Audit",
        "inputs": ["snapshot:Text"],
        "outputs": ["findings:Dict"],
        "code": REAL_REPO_FINDINGS_CODE,
    },
    {
        "name": "RealRepoArchitecture",
        "description": "Infer architecture, language mix, entrypoints, and verification hints from sampled files.",
        "category": "Architecture",
        "inputs": ["snapshot:Text"],
        "outputs": ["architecture:Dict"],
        "code": REAL_REPO_ARCHITECTURE_CODE,
    },
    {
        "name": "RealRepoBriefing",
        "description": "Build a readable real repository audit report from learned-node analysis.",
        "category": "Research",
        "inputs": ["inventory:Dict", "findings:Dict", "architecture:Dict", "context:Text", "target:Text"],
        "outputs": ["report:Text"],
        "code": REAL_REPO_BRIEFING_CODE,
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="real_repo_learned_demo.py")
    parser.add_argument("--target", help="Real local folder or repo to audit.")
    parser.add_argument("--query", default="architecture entrypoint tests docker sandbox mcp TODO FIXME secret")
    parser.add_argument("--max-files", type=int, default=80)
    parser.add_argument("--max-chars-per-file", type=int, default=6000)
    parser.add_argument("--open-editor", action="store_true")
    parser.add_argument("--editor-url", default="http://127.0.0.1:7777")
    parser.add_argument("--keep-learned", action="store_true")
    parser.add_argument("--cleanup-demo-nodes", action="store_true")
    args = parser.parse_args(argv)

    if args.cleanup_demo_nodes:
        _configure_live_env(args.editor_url)
        from blacknode.mcp import tools

        _delete_demo_nodes(tools, notify_editor=True)
        print("[real-repo-demo] deleted persistent real repo demo learned nodes")
        return 0

    if not args.target:
        print("[real-repo-demo] FAIL: --target is required for the real-world demo", file=sys.stderr)
        return 2

    try:
        target = Path(args.target).expanduser().resolve()
        snapshot = build_snapshot(
            target,
            max_files=args.max_files,
            max_chars_per_file=args.max_chars_per_file,
        )
    except Exception as exc:
        print(f"[real-repo-demo] FAIL: {exc}", file=sys.stderr)
        return 1

    live_editor = bool(args.open_editor)
    keep_learned = bool(args.keep_learned or live_editor)
    temp_dir = tempfile.TemporaryDirectory(prefix="blacknode-real-repo-demo-") if not keep_learned else None

    try:
        if temp_dir is not None:
            _configure_demo_env(Path(temp_dir.name))
        else:
            _configure_live_env(args.editor_url)

        _ensure_learned_node_sandbox_available()

        from blacknode.mcp import tools

        if keep_learned:
            _delete_demo_nodes(tools, notify_editor=live_editor)

        created: list[str] = []
        for spec in LEARNED_NODE_SPECS:
            result = tools.create_node_type(**spec, requires_network=False)
            if result.get("status") != "created":
                raise RuntimeError(f"create_node_type failed for {spec['name']}: {result}")
            created.append(spec["name"])

        workflow = build_workflow(
            tools,
            target=str(target),
            snapshot=json.dumps(snapshot, indent=2),
            query=args.query,
        )
        node_count = len(workflow.get("node_meta") or {})
        validation = tools.validate_workflow_tool(workflow)
        if not validation.get("ok"):
            raise RuntimeError(f"workflow validation failed: {validation}")

        if live_editor:
            open_result = tools.open_workflow_in_editor_tab(
                workflow,
                name=f"Real Repo Audit - {target.name}",
                editor_url=args.editor_url,
                organize=True,
            )
            print(f"[real-repo-demo] opened editor tab: {open_result.get('editor_url')}")

        run_result = tools.run_workflow_tool(workflow)
        if run_result.get("ok") is False:
            raise RuntimeError(_format_workflow_run_failure(run_result))
        value = run_result.get("value")
        if not isinstance(value, str) or target.name not in value:
            raise RuntimeError(f"unexpected demo output: {value!r}")

        print(f"[real-repo-demo] target: {target}")
        print(f"[real-repo-demo] sampled files: {len(snapshot['files'])}")
        print(f"[real-repo-demo] learned nodes: {', '.join(created)}")
        categories = sorted({str(spec["category"]) for spec in LEARNED_NODE_SPECS})
        print(f"[real-repo-demo] categories: {', '.join(categories)}")
        print(f"[real-repo-demo] workflow node count: {node_count}")
        print("[real-repo-demo] validation: ok")
        if keep_learned:
            print("[real-repo-demo] learned nodes kept for live demo")
        print("[real-repo-demo] output preview:")
        print(value[:2200])
        return 0
    except Exception as exc:
        print(f"[real-repo-demo] FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            if not keep_learned:
                from blacknode.mcp import tools

                _delete_demo_nodes(tools, notify_editor=False)
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()


def build_snapshot(target: Path, *, max_files: int, max_chars_per_file: int) -> dict[str, Any]:
    if not target.exists():
        raise FileNotFoundError(f"target does not exist: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"target must be a directory: {target}")

    candidates = list(_iter_candidate_files(target))
    files = []
    for path in candidates:
        if len(files) >= max_files:
            break
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:2048]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        rel = path.relative_to(target).as_posix()
        files.append({
            "path": rel,
            "suffix": path.suffix.lower(),
            "size": path.stat().st_size,
            "line_count": text.count("\n") + (1 if text else 0),
            "text": text[:max_chars_per_file],
            "truncated": len(text) > max_chars_per_file,
        })

    if not files:
        raise RuntimeError(f"no readable text/source files found in {target}")

    return {
        "target": str(target),
        "max_files": max_files,
        "max_chars_per_file": max_chars_per_file,
        "candidate_files": len(candidates),
        "files": files,
    }


def _iter_candidate_files(target: Path):
    candidates = []
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(target).as_posix()
        parts = path.relative_to(target).parts[:-1]
        if any(part in IGNORE_DIRS for part in parts):
            continue
        if any(rel.startswith(prefix) for prefix in IGNORE_PATH_PREFIXES):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name.lower() not in {"dockerfile", "makefile"}:
            continue
        candidates.append(path)
    yield from sorted(candidates, key=lambda item: _file_priority(item, target))


def _file_priority(path: Path, target: Path) -> tuple[int, int, int, str]:
    rel = path.relative_to(target).as_posix()
    lower = rel.lower()
    name = path.name.lower()
    if lower in {"readme.md", "pyproject.toml", "package.json", "cargo.toml", "requirements.txt"}:
        bucket = 0
    elif lower.startswith(("python/blacknode/", "src/", "scripts/", "crates/", "editor/src/", "editor-server/")):
        bucket = 1
    elif lower.startswith(("tests/", "test/")) or "/tests/" in lower or "test_" in name:
        bucket = 2
    elif lower.startswith(("docs/", "templates/", "nodes/", "custom-nodes/", "community-nodes/")):
        bucket = 3
    elif lower.startswith((".github/", "docker/")):
        bucket = 4
    elif lower.startswith("."):
        bucket = 8
    else:
        bucket = 5
    if name.endswith(".lock") or name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}:
        bucket += 3
    return (bucket, rel.count("/"), len(rel), rel)


def build_workflow(tools: Any, *, target: str, snapshot: str, query: str) -> dict[str, Any]:
    workflow = tools.create_workflow(
        name="Real Repo Learned Nodes Demo",
        description="Audit a real local folder with learned nodes and RAG context.",
    )
    workflow = _add(tools, workflow, "Text", "target", {"value": target}, (60, 80))
    workflow = _add(tools, workflow, "Text", "snapshot", {"value": snapshot}, (60, 260))
    workflow = _add(tools, workflow, "Text", "query", {"value": query}, (60, 440))
    workflow = _add(tools, workflow, "Text", "headline", {"value": "Blacknode learned-node repo audit\n\n"}, (60, 620))

    workflow = _add(tools, workflow, "RealRepoInventory", "inventory", {}, (380, 120))
    workflow = _add(tools, workflow, "RealRepoFindings", "findings", {}, (380, 340))
    workflow = _add(tools, workflow, "RealRepoArchitecture", "architecture", {}, (380, 560))
    workflow = _add(tools, workflow, "TextChunker", "chunk", {}, (680, 560))
    workflow = _add(tools, workflow, "KeywordIndex", "index", {}, (960, 560))
    workflow = _add(tools, workflow, "KeywordSearch", "search", {}, (1240, 560))
    workflow = _add(tools, workflow, "RAGContext", "context", {}, (1520, 560))
    workflow = _add(tools, workflow, "RealRepoBriefing", "brief", {}, (1800, 260))
    workflow = _add(tools, workflow, "Concat", "concat", {}, (2080, 380))

    for from_node, from_port, to_node, to_port in [
        ("target", "value", "brief", "target"),
        ("snapshot", "value", "inventory", "snapshot"),
        ("snapshot", "value", "findings", "snapshot"),
        ("snapshot", "value", "architecture", "snapshot"),
        ("snapshot", "value", "chunk", "text"),
        ("chunk", "chunks", "index", "documents"),
        ("index", "index", "search", "index"),
        ("query", "value", "search", "query"),
        ("search", "results", "context", "results"),
        ("inventory", "inventory", "brief", "inventory"),
        ("findings", "findings", "brief", "findings"),
        ("architecture", "architecture", "brief", "architecture"),
        ("context", "context", "brief", "context"),
        ("headline", "value", "concat", "a"),
        ("brief", "report", "concat", "b"),
        ("concat", "value", "out", "value"),
    ]:
        workflow = tools.connect_nodes(
            workflow,
            from_node=from_node,
            from_port=from_port,
            to_node=to_node,
            to_port=to_port,
        )["workflow"]
    return workflow


def _add(
    tools: Any,
    workflow: dict[str, Any],
    type_name: str,
    node_id: str,
    params: dict[str, Any],
    pos: tuple[float, float],
) -> dict[str, Any]:
    return tools.add_node(
        workflow,
        type_name,
        params=params,
        node_id=node_id,
        pos=pos,
    )["workflow"]


def _configure_demo_env(root: Path) -> None:
    os.environ["BLACKNODE_LEARNED_DIR"] = str(root / "learned")
    os.environ["BLACKNODE_CONFIG_DIR"] = str(root / "config")
    os.environ["BLACKNODE_LEARNED_NODES_CONSENT"] = "1"
    os.environ.setdefault("BLACKNODE_MCP_QUIET", "1")


def _configure_live_env(editor_url: str) -> None:
    os.environ.pop("BLACKNODE_LEARNED_DIR", None)
    os.environ["BLACKNODE_EDITOR_URL"] = editor_url.rstrip("/")
    os.environ["BLACKNODE_LEARNED_NODES_CONSENT"] = "1"
    os.environ.setdefault("BLACKNODE_MCP_QUIET", "1")


def _ensure_learned_node_sandbox_available() -> None:
    status = docker_runner.learned_node_runtime_status()
    detail = str(status.get("detail") or "").strip()
    if status.get("disabled"):
        message = (
            "Learned-node Docker sandbox is disabled. Unset "
            "BLACKNODE_SANDBOX_DISABLED, then run 'blacknode doctor'."
        )
        if detail:
            message = f"{message} Detail: {detail}"
        raise RuntimeError(message)
    if not status.get("docker_available"):
        message = (
            "Docker is not available for learned-node execution. Start Docker "
            "Desktop or a compatible Docker daemon, then run 'blacknode doctor'."
        )
        if detail:
            message = f"{message} Detail: {detail}"
        raise RuntimeError(message)


def _format_workflow_run_failure(run_result: dict[str, Any]) -> str:
    error = str(run_result.get("error") or "unknown workflow error").strip()
    run_id = run_result.get("run_id")
    suffix = f" (run_id: {run_id})" if run_id else ""
    return f"workflow run failed{suffix}: {error}"


def _delete_demo_nodes(tools: Any, *, notify_editor: bool) -> None:
    for spec in LEARNED_NODE_SPECS:
        tools.delete_learned_node(spec["name"], confirm=True, notify_editor=notify_editor)


if __name__ == "__main__":
    sys.exit(main())
