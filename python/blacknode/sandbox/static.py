from __future__ import annotations

import ast
from dataclasses import dataclass


FORBIDDEN_IMPORTS = frozenset({
    "os",
    "subprocess",
    "shutil",
    "ctypes",
    "socket",
    "multiprocessing",
    "threading",
    "asyncio.subprocess",
    "pty",
    "fcntl",
    "resource",
    "signal",
})

FORBIDDEN_NAMES = frozenset({
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
    "vars",
    "open",
})

FORBIDDEN_DUNDER_ACCESS = frozenset({
    "__builtins__",
    "__class__",
    "__globals__",
    "__import__",
})


@dataclass(frozen=True)
class StaticCheckResult:
    safe: bool
    reason: str = ""


def check_safe(code: str) -> StaticCheckResult:
    """Return a fast AST-only safety smell check for learned-node source."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return StaticCheckResult(False, f"Syntax error: {exc.msg} at line {exc.lineno}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_import(alias.name):
                    return StaticCheckResult(False, f"Forbidden import: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_forbidden_import(module):
                return StaticCheckResult(False, f"Forbidden import: {module}")
            for alias in node.names:
                imported_name = f"{module}.{alias.name}" if module else alias.name
                if _is_forbidden_import(imported_name):
                    return StaticCheckResult(False, f"Forbidden import: {imported_name}")

        elif isinstance(node, ast.Name):
            if node.id == "open":
                return StaticCheckResult(
                    False,
                    "Use of `open` not allowed in learned nodes "
                    "(I/O is mediated by the runner)",
                )
            if node.id in FORBIDDEN_NAMES:
                return StaticCheckResult(False, f"Forbidden name: {node.id}")
            if node.id in FORBIDDEN_DUNDER_ACCESS:
                return StaticCheckResult(False, f"Forbidden dunder access: {node.id}")

        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_DUNDER_ACCESS:
                return StaticCheckResult(False, f"Forbidden dunder access: {node.attr}")

    return StaticCheckResult(True)


def _is_forbidden_import(module_name: str) -> bool:
    if not module_name:
        return False
    return any(
        module_name == forbidden or module_name.startswith(f"{forbidden}.")
        for forbidden in FORBIDDEN_IMPORTS
    )

