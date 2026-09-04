from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


_SHA_RE = re.compile(r"[0-9a-f]{40}")
_SOURCE_KEYS = ("runtime", "core", "hardware")


def load_and_validate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("source lock schema_version must be 1")
    for key in _SOURCE_KEYS:
        source = payload.get(key)
        if not isinstance(source, dict) or not str(source.get("repository") or "").strip():
            raise ValueError(f"source lock is missing {key}.repository")
        sha = str(source.get("commit") or "").lower()
        if not _SHA_RE.fullmatch(sha):
            raise ValueError(f"source lock {key}.commit must be a full lowercase commit SHA")
        source["commit"] = sha
    return payload


def update_commits(payload: dict[str, Any], commits: dict[str, str | None]) -> None:
    for key, raw_sha in commits.items():
        if raw_sha is None:
            continue
        sha = raw_sha.strip().lower()
        if not _SHA_RE.fullmatch(sha):
            raise ValueError(f"{key} commit must be a full lowercase commit SHA")
        payload[key]["commit"] = sha


def _github_json(url: str) -> dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "blacknode-release-lock"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"GitHub rejected source verification ({exc.code}) for {url}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach GitHub for source verification: {exc.reason}") from exc


def verify_merged_sources(payload: dict[str, Any]) -> None:
    for key in _SOURCE_KEYS:
        repository = payload[key]["repository"]
        sha = payload[key]["commit"]
        repo = _github_json(f"https://api.github.com/repos/{repository}")
        default_branch = str(repo.get("default_branch") or "").strip()
        if not default_branch:
            raise ValueError(f"GitHub did not report a default branch for {repository}")
        encoded_branch = urllib.parse.quote(default_branch, safe="")
        comparison = _github_json(
            f"https://api.github.com/repos/{repository}/compare/{sha}...{encoded_branch}"
        )
        if comparison.get("status") not in {"ahead", "identical"}:
            raise ValueError(
                f"{key} commit {sha} is not merged into {repository}:{default_branch}"
            )


def write_lock(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or update managed-device source pins.")
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "editor-server" / "device-runtime-sources.lock.json",
    )
    parser.add_argument("--runtime-commit")
    parser.add_argument("--core-commit")
    parser.add_argument("--hardware-commit")
    parser.add_argument("--verify-merged", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = load_and_validate(args.lock)
        update_commits(payload, {
            "runtime": args.runtime_commit,
            "core": args.core_commit,
            "hardware": args.hardware_commit,
        })
        if args.verify_merged:
            verify_merged_sources(payload)
        if args.write:
            write_lock(args.lock, payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"source-lock error: {exc}", file=sys.stderr)
        return 1
    print("Managed-device source lock is valid and uses merged full-SHA pins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
