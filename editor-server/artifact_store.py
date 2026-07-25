"""Typed references to artifacts owned by Blacknode extension packages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_SECRET_RE = re.compile(
    r"(api[_-]?key|token|secret|password|credential|authorization)",
    re.IGNORECASE,
)
_MAX_IMPORT_DEPTH = 8
_MAX_IMPORT_ITEMS = 500


class ArtifactStoreError(RuntimeError):
    """An artifact reference could not be inspected or persisted."""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any, *, maximum: int = 500) -> str:
    clean = str(value or "").strip()
    if any(ord(char) < 32 for char in clean):
        clean = "".join(char for char in clean if ord(char) >= 32)
    return clean[:maximum]


def _safe_metadata(values: dict[str, Any], allowed: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in allowed:
        if _SECRET_RE.search(key) or key not in values:
            continue
        value = values[key]
        if value is None or isinstance(value, (str, int, float, bool)):
            result[key] = _clean_text(value) if isinstance(value, str) else value
        elif isinstance(value, list):
            result[key] = [
                _clean_text(item, maximum=120)
                for item in value[:100]
                if isinstance(item, (str, int, float, bool))
            ]
        elif isinstance(value, dict):
            nested: dict[str, Any] = {}
            for nested_key, nested_value in list(value.items())[:100]:
                if _SECRET_RE.search(str(nested_key)):
                    continue
                if nested_value is None or isinstance(
                    nested_value, (str, int, float, bool)
                ):
                    nested[str(nested_key)[:120]] = (
                        _clean_text(nested_value, maximum=120)
                        if isinstance(nested_value, str)
                        else nested_value
                    )
            result[key] = nested
    return result


def _path_locator(value: Any) -> str:
    clean = _clean_text(value, maximum=2000)
    if not clean:
        return ""
    return str(Path(clean).expanduser().resolve())


def _record_id(provider: str, artifact_type: str, locator: str) -> str:
    digest = hashlib.sha256(
        f"{provider}\0{artifact_type}\0{locator}".encode("utf-8")
    ).hexdigest()[:20]
    return f"{artifact_type}-{digest}"


def _status_for_job(payload: dict[str, Any]) -> str:
    phase = _clean_text(payload.get("phase"), maximum=80).lower()
    if payload.get("running"):
        return "running"
    if phase in {"complete", "completed", "succeeded", "success", "stopped"}:
        return "completed"
    if phase in {"failed", "error"} or payload.get("error"):
        return "failed"
    return "available"


def _artifact_candidate(
    payload: dict[str, Any],
    *,
    node_type: str = "",
) -> dict[str, Any] | None:
    kind = _clean_text(payload.get("kind"), maximum=160)
    now = _iso_now()
    artifact_type = ""
    provider = ""
    locator = ""
    name = ""
    status = "available"
    metadata: dict[str, Any] = {}

    if kind == "blacknode.episode-dataset":
        artifact_type = "dataset"
        provider = "blacknode-dataset"
        locator = _path_locator(payload.get("path"))
        dataset_id = _clean_text(payload.get("dataset_id"), maximum=160)
        name = dataset_id or (Path(locator).name if locator else "Dataset")
        episodes = int(payload.get("episode_count") or 0)
        status = "completed" if episodes > 0 else "available"
        metadata = _safe_metadata(
            payload,
            (
                "dataset_id",
                "task",
                "fps",
                "episode_count",
                "total_frames",
                "duration_seconds",
                "robot_type",
                "joint_names",
                "cameras",
            ),
        )
    elif kind in {"blacknode.training-job", "blacknode.training-run"}:
        artifact_type = "training_run"
        provider = "blacknode-training"
        run_id = _clean_text(payload.get("run_id"), maximum=160)
        locator = _path_locator(payload.get("output_dir"))
        if not locator:
            locator = f"blacknode://training/runs/{run_id or 'unknown'}"
        name = run_id or (Path(locator).name if locator else "Training run")
        status = (
            _status_for_job(payload)
            if kind == "blacknode.training-job"
            else "available"
        )
        metadata = _safe_metadata(
            payload,
            (
                "run_id",
                "phase",
                "running",
                "step",
                "steps",
                "progress",
                "train_loss",
                "validation_loss",
                "best_validation_loss",
                "device",
                "started_at",
                "ended_at",
                "error",
            ),
        )
    elif kind == "blacknode.action-chunking-checkpoint":
        artifact_type = "checkpoint"
        provider = "blacknode-training"
        locator = _path_locator(payload.get("path"))
        name = Path(locator).name if locator else "Training checkpoint"
        status = "completed"
        metadata = _safe_metadata(payload, ("run_id", "step", "created_at"))
    elif kind == "blacknode.policy-artifact":
        artifact_type = "policy"
        provider = "blacknode-training"
        locator = _path_locator(payload.get("path"))
        name = (
            _clean_text(payload.get("name"), maximum=160)
            or (Path(locator).name if locator else "Policy")
        )
        status = "completed"
        metadata = _safe_metadata(
            payload,
            (
                "policy_type",
                "backend",
                "created_at",
                "source_checkpoint",
                "step",
                "action_mode",
                "units",
                "joint_names",
                "camera_names",
                "fps",
                "state_dim",
                "action_dim",
                "metrics",
            ),
        )
    elif kind == "blacknode.policy-replay-metrics":
        artifact_type = "evaluation"
        provider = "blacknode-training"
        policy = _path_locator(payload.get("policy_artifact"))
        episode = int(payload.get("episode_index") or 0)
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:20]
        locator = f"blacknode://policy-replay/{fingerprint}"
        name = f"Policy replay · episode {episode}"
        status = "completed"
        metadata = _safe_metadata(
            payload,
            (
                "episode_index",
                "frames",
                "mean_absolute_error",
                "root_mean_square_error",
                "max_absolute_error",
                "motion_commanded",
            ),
        )
        if policy:
            metadata["policy_artifact"] = policy
    elif kind == "blacknode.policy-runtime" and "isaac" in node_type.lower():
        artifact_type = "simulation_run"
        provider = "blacknode-isaac"
        run_id = _clean_text(payload.get("run_id"), maximum=160)
        locator = _path_locator(payload.get("log_path"))
        if not locator:
            locator = f"blacknode://isaac/runs/{run_id or 'unknown'}"
        name = run_id or "Isaac policy run"
        status = _status_for_job(payload)
        metadata = _safe_metadata(
            payload,
            (
                "run_id",
                "phase",
                "running",
                "inference_count",
                "command_count",
                "blocked_count",
                "mean_inference_ms",
                "last_error",
                "armed",
                "emergency_stop",
                "human_takeover",
            ),
        )
    else:
        return None

    if not locator:
        return None
    created_at = _clean_text(payload.get("created_at"), maximum=100) or now
    artifact_id = _record_id(provider, artifact_type, locator)
    return {
        "id": artifact_id,
        "artifact_type": artifact_type,
        "kind": kind,
        "provider": provider,
        "name": name[:160],
        "locator": locator,
        "status": status,
        "metadata": metadata,
        "created_at": created_at,
        "updated_at": now,
    }


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    stack: list[tuple[Any, int]] = [(value, 0)]
    seen = 0
    while stack and seen < _MAX_IMPORT_ITEMS:
        current, depth = stack.pop()
        seen += 1
        if depth > _MAX_IMPORT_DEPTH:
            continue
        if isinstance(current, dict):
            yield current
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, (list, tuple)):
            stack.extend((item, depth + 1) for item in current)


class ArtifactStore:
    """Persist small, provider-neutral references without copying artifacts."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def list(self, artifact_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
        with self._lock:
            records = self._load()
            selected = (
                [records[item] for item in artifact_ids or [] if item in records]
                if artifact_ids is not None
                else list(records.values())
            )
            return [self._hydrate(record) for record in selected]

    def import_value(
        self,
        value: Any,
        *,
        node_type: str = "",
        workflow_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}
        for payload in _walk_dicts(value):
            candidate = _artifact_candidate(payload, node_type=node_type)
            if candidate is None:
                continue
            if workflow_slug:
                candidate["workflow_slugs"] = [
                    _clean_text(workflow_slug, maximum=60)
                ]
            candidates[candidate["id"]] = candidate

            if payload.get("kind") == "blacknode.training-job":
                checkpoint = _path_locator(payload.get("checkpoint"))
                if checkpoint:
                    checkpoint_payload = {
                        "kind": "blacknode.action-chunking-checkpoint",
                        "path": checkpoint,
                        "run_id": payload.get("run_id"),
                        "step": payload.get("step"),
                    }
                    derived = _artifact_candidate(checkpoint_payload)
                    if derived is not None:
                        if workflow_slug:
                            derived["workflow_slugs"] = [
                                _clean_text(workflow_slug, maximum=60)
                            ]
                        candidates[derived["id"]] = derived
        if not candidates:
            return []
        with self._lock:
            records = self._load()
            for artifact_id, candidate in candidates.items():
                prior = records.get(artifact_id)
                if prior:
                    candidate["created_at"] = prior.get(
                        "created_at", candidate["created_at"]
                    )
                    candidate["workflow_slugs"] = list(
                        dict.fromkeys([
                            *list(prior.get("workflow_slugs") or []),
                            *list(candidate.get("workflow_slugs") or []),
                        ])
                    )
                records[artifact_id] = candidate
            self._save(records)
            return [self._hydrate(records[item]) for item in candidates]

    def inspect_path(
        self,
        raw_path: str,
        *,
        workflow_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        clean = _clean_text(raw_path, maximum=2000)
        if not clean:
            raise ArtifactStoreError("Artifact path is required.")
        path = Path(clean).expanduser().resolve()
        if not path.exists():
            raise ArtifactStoreError(f"Artifact path does not exist: {path}")

        candidates: list[Path] = []
        if path.is_dir():
            candidates = [
                item
                for item in (
                    path / "dataset.json",
                    path / "run.json",
                    path / "manifest.json",
                )
                if item.is_file()
            ]
        elif path.suffix.lower() == ".pt":
            return self.import_value(
                {
                    "kind": "blacknode.action-chunking-checkpoint",
                    "path": str(path),
                },
                workflow_slug=workflow_slug,
            )
        elif path.suffix.lower() == ".json":
            candidates = [path]

        imported: list[dict[str, Any]] = []
        for candidate in candidates:
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ArtifactStoreError(
                    f"Could not read artifact manifest {candidate}: {exc}"
                ) from exc
            if isinstance(payload, dict):
                if payload.get("kind") == "blacknode.episode-dataset":
                    episodes = payload.get("episodes")
                    if isinstance(episodes, list):
                        payload.setdefault("episode_count", len(episodes))
                        payload.setdefault(
                            "total_frames",
                            sum(
                                int(item.get("frames") or 0)
                                for item in episodes
                                if isinstance(item, dict)
                            ),
                        )
                if payload.get("kind") == "blacknode.training-run":
                    config = payload.get("config")
                    if isinstance(config, dict):
                        payload.setdefault("run_id", config.get("run_id"))
                if payload.get("kind") in {
                    "blacknode.episode-dataset",
                    "blacknode.policy-artifact",
                }:
                    payload["path"] = str(candidate.parent)
                elif not payload.get("path"):
                    payload["path"] = str(candidate.parent)
                if payload.get("kind") == "blacknode.training-run":
                    payload["output_dir"] = str(candidate.parent)
                imported.extend(
                    self.import_value(payload, workflow_slug=workflow_slug)
                )
        if path.is_dir():
            imported.extend(
                self.import_value(
                    [
                        {
                            "kind": "blacknode.action-chunking-checkpoint",
                            "path": str(item),
                        }
                        for item in sorted(path.glob("checkpoint-*.pt"))
                    ],
                    workflow_slug=workflow_slug,
                )
            )
        unique = {item["id"]: item for item in imported}
        if not unique:
            raise ArtifactStoreError(
                "No supported Blacknode artifact manifest was found at that path."
            )
        return list(unique.values())

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactStoreError(
                f"Could not read local artifact index at {self.path}: {exc}"
            ) from exc
        artifacts = payload.get("artifacts", []) if isinstance(payload, dict) else []
        if not isinstance(artifacts, list):
            raise ArtifactStoreError("Local artifact index has an invalid format.")
        records: dict[str, dict[str, Any]] = {}
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            artifact_id = _clean_text(item.get("id"), maximum=100)
            if artifact_id:
                records[artifact_id] = dict(item)
        return records

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        payload = {
            "schema_version": 1,
            "artifacts": list(records.values()),
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
    def _hydrate(record: dict[str, Any]) -> dict[str, Any]:
        locator = str(record.get("locator") or "")
        exists = True
        if locator and not locator.startswith("blacknode://"):
            exists = Path(locator).exists()
        return {**record, "exists": exists}
