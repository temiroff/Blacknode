from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path


_EXTENSION_RE = re.compile(r"\.[a-z0-9][a-z0-9._+-]{0,31}", re.I)


def normalize_extensions(values: Iterable[object]) -> frozenset[str]:
    extensions: set[str] = set()
    for value in values:
        clean = str(value or "").strip().lower()
        if not clean:
            continue
        normalized = clean if clean.startswith(".") else f".{clean}"
        if not _EXTENSION_RE.fullmatch(normalized):
            raise ValueError(f"Invalid file extension '{clean}'.")
        extensions.add(normalized)
    return frozenset(extensions)


def configured_app_roots(raw_value: str | None) -> tuple[Path, ...]:
    values = [item.strip() for item in (raw_value or "").split(os.pathsep) if item.strip()]
    roots = tuple(Path(item).expanduser().resolve() for item in values) or (Path.home().resolve(),)
    missing = [str(root) for root in roots if not root.is_dir()]
    if missing:
        raise ValueError(f"App file roots must be existing directories: {', '.join(missing)}")
    return roots


def path_within_roots(path: Path, roots: Iterable[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def _system_roots() -> tuple[Path, ...]:
    if os.name == "nt":
        return tuple(
            Path(f"{letter}:\\").resolve()
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            if Path(f"{letter}:\\").is_dir()
        )
    return (Path("/").resolve(),)


def browse_listing(
    raw_path: str,
    extensions: Iterable[object],
    *,
    roots: tuple[Path, ...] | None = None,
) -> dict[str, object]:
    """Return a directory listing, optionally constrained to explicit roots."""
    restricted = roots is not None
    browse_roots = roots if roots is not None else _system_roots()
    fallback = browse_roots[0] if restricted else Path.home().resolve()
    clean_path = str(raw_path or "").strip()
    requested = Path(clean_path).expanduser() if clean_path and not clean_path.startswith("package://") else fallback
    try:
        requested = requested.resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Could not resolve {requested}: {exc}") from exc
    if restricted and not path_within_roots(requested, browse_roots):
        raise PermissionError("The requested path is outside the App's configured file roots.")

    selected = ""
    if requested.is_file():
        selected = str(requested)
        requested = requested.parent
    if not requested.is_dir():
        if restricted:
            raise ValueError(f"Directory does not exist: {requested}")
        requested = fallback

    allowed = normalize_extensions(extensions)
    try:
        entries: list[dict[str, object]] = []
        for child in requested.iterdir():
            try:
                resolved = child.resolve()
                if restricted and not path_within_roots(resolved, browse_roots):
                    continue
                is_directory = child.is_dir()
                if not is_directory and allowed and child.suffix.lower() not in allowed:
                    continue
                entries.append({
                    "name": child.name,
                    "path": str(resolved),
                    "is_directory": is_directory,
                    "size": None if is_directory else child.stat().st_size,
                })
            except (OSError, RuntimeError):
                continue
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Could not browse {requested}: {exc}") from exc

    entries.sort(key=lambda item: (not bool(item["is_directory"]), str(item["name"]).casefold()))
    parent = requested.parent
    parent_path = str(parent) if parent != requested and (not restricted or path_within_roots(parent, browse_roots)) else ""
    return {
        "path": str(requested),
        "parent": parent_path,
        "roots": [str(root) for root in browse_roots],
        "selected": selected,
        "entries": entries[:5000],
    }
