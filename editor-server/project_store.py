"""Local project registry for grouping workflows and paired devices."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ID_RE = re.compile(r"[^a-z0-9]+")
_WORKFLOW_SLUG_RE = re.compile(r"[a-zA-Z0-9_-]{1,60}")


class ProjectStoreError(RuntimeError):
    """A project record could not be read, validated, or persisted."""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    return _ID_RE.sub("-", value.strip().lower()).strip("-")[:60] or "project"


def _unique_strings(values: list[str] | None, *, field: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        clean = str(value or "").strip()
        if not clean:
            continue
        if len(clean) > 240 or any(ord(char) < 32 for char in clean):
            raise ProjectStoreError(f"{field} contains an invalid value.")
        if field == "workflow_slugs" and not _WORKFLOW_SLUG_RE.fullmatch(clean):
            raise ProjectStoreError(f"Invalid workflow slug '{clean}'.")
        if clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result


class ProjectStore:
    """Persist stable project records without copying linked resources."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(record)
                for record in sorted(
                    self._load().values(),
                    key=lambda item: (
                        str(item.get("updated_at", "")),
                        str(item.get("name", "")).lower(),
                    ),
                    reverse=True,
                )
            ]

    def get(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._load().get(project_id)
            return dict(record) if record is not None else None

    def create(
        self,
        *,
        name: str,
        description: str = "",
        workflow_slugs: list[str] | None = None,
        device_ids: list[str] | None = None,
        active_workflow_slug: str | None = None,
    ) -> dict[str, Any]:
        clean_name = self._clean_name(name)
        clean_description = self._clean_description(description)
        clean_workflows = _unique_strings(workflow_slugs, field="workflow_slugs")
        clean_devices = _unique_strings(device_ids, field="device_ids")
        clean_active = str(active_workflow_slug or "").strip() or None
        if clean_active and clean_active not in clean_workflows:
            raise ProjectStoreError(
                "active_workflow_slug must be one of workflow_slugs."
            )
        with self._lock:
            records = self._load()
            base_id = _slug(clean_name)
            project_id = base_id
            suffix = 2
            while project_id in records:
                project_id = f"{base_id[: 60 - len(str(suffix)) - 1]}-{suffix}"
                suffix += 1
            now = _iso_now()
            record = {
                "id": project_id,
                "name": clean_name,
                "description": clean_description,
                "workflow_slugs": clean_workflows,
                "device_ids": clean_devices,
                "active_workflow_slug": (
                    clean_active
                    or (clean_workflows[0] if clean_workflows else None)
                ),
                "created_at": now,
                "updated_at": now,
            }
            records[project_id] = record
            self._save(records)
            return dict(record)

    def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        workflow_slugs: list[str] | None = None,
        device_ids: list[str] | None = None,
        active_workflow_slug: str | None = None,
        update_active_workflow: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            records = self._load()
            record = records.get(project_id)
            if record is None:
                raise KeyError(project_id)
            if name is not None:
                record["name"] = self._clean_name(name)
            if description is not None:
                record["description"] = self._clean_description(description)
            if workflow_slugs is not None:
                record["workflow_slugs"] = _unique_strings(
                    workflow_slugs,
                    field="workflow_slugs",
                )
            if device_ids is not None:
                record["device_ids"] = _unique_strings(
                    device_ids,
                    field="device_ids",
                )
            workflows = list(record.get("workflow_slugs") or [])
            if update_active_workflow:
                clean_active = str(active_workflow_slug or "").strip() or None
                if clean_active and clean_active not in workflows:
                    raise ProjectStoreError(
                        "active_workflow_slug must be one of workflow_slugs."
                    )
                record["active_workflow_slug"] = clean_active
            if record.get("active_workflow_slug") not in workflows:
                record["active_workflow_slug"] = workflows[0] if workflows else None
            record["updated_at"] = _iso_now()
            records[project_id] = record
            self._save(records)
            return dict(record)

    def delete(self, project_id: str) -> bool:
        with self._lock:
            records = self._load()
            if project_id not in records:
                return False
            del records[project_id]
            self._save(records)
            return True

    def replace_workflow_slug(self, previous_slug: str, next_slug: str) -> None:
        """Keep project links intact when a saved workflow is renamed."""
        if previous_slug == next_slug:
            return
        with self._lock:
            records = self._load()
            changed = False
            now = _iso_now()
            for record in records.values():
                workflows = list(record.get("workflow_slugs") or [])
                if previous_slug not in workflows:
                    continue
                replaced = [
                    next_slug if slug == previous_slug else slug
                    for slug in workflows
                ]
                record["workflow_slugs"] = _unique_strings(
                    replaced,
                    field="workflow_slugs",
                )
                if record.get("active_workflow_slug") == previous_slug:
                    record["active_workflow_slug"] = next_slug
                record["updated_at"] = now
                changed = True
            if changed:
                self._save(records)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectStoreError(
                f"Could not read local project registry at {self.path}: {exc}"
            ) from exc
        projects = payload.get("projects", []) if isinstance(payload, dict) else []
        if not isinstance(projects, list):
            raise ProjectStoreError("Local project registry has an invalid format.")
        records: dict[str, dict[str, Any]] = {}
        for item in projects:
            if not isinstance(item, dict):
                continue
            project_id = str(item.get("id") or "").strip()
            if project_id:
                records[project_id] = dict(item)
        return records

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        payload = {
            "schema_version": 1,
            "projects": list(records.values()),
        }
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _clean_name(value: str) -> str:
        clean = str(value or "").strip()
        if not clean:
            raise ProjectStoreError("Project name is required.")
        if len(clean) > 120 or any(ord(char) < 32 for char in clean):
            raise ProjectStoreError("Project name is invalid.")
        return clean

    @staticmethod
    def _clean_description(value: str) -> str:
        clean = str(value or "").strip()
        if len(clean) > 2000:
            raise ProjectStoreError(
                "Project description must be 2,000 characters or fewer."
            )
        return clean
