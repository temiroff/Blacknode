"""Where custom vision models live, and how a model name resolves to a file.

Mirrors the robot's convention (a models/ folder referenced by name): drop a
trained YOLO weight into .blacknode/models and pick it by filename, while
built-in names like 'yolov8n.pt' pass through for ultralytics to auto-download.
"""
from __future__ import annotations

import os
from pathlib import Path

# Built-in ultralytics weights that auto-download; offered alongside custom files.
BUILTIN_MODELS = [
    "yolov8n.pt", "yolov8s.pt", "yolov8m.pt",
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt",
]
_MODEL_SUFFIXES = {".pt", ".onnx", ".engine"}


def _repo_root() -> Path:
    # python/blacknode/vision_models.py -> parents[2] is the checkout root.
    return Path(os.environ.get("BLACKNODE_HOME") or Path(__file__).resolve().parents[2])


def models_dir() -> Path:
    path = _repo_root() / ".blacknode" / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def custom_models() -> list[str]:
    """Filenames of user-supplied model weights, newest first."""
    directory = models_dir()
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _MODEL_SUFFIXES]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files]


def resolve_model(name: str) -> str:
    """A model name -> a path YOLO can load.

    An existing path (absolute or relative) is used as-is; a bare filename found
    in the models dir resolves to it; anything else passes through unchanged so
    ultralytics can treat it as a downloadable built-in.
    """
    name = (name or "").strip()
    if not name:
        return "yolov8n.pt"
    if Path(name).exists():
        return str(Path(name).resolve())
    candidate = models_dir() / name
    if candidate.exists():
        return str(candidate)
    return name
