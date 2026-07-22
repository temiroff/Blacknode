"""The frame-stream contract: how one node hands a live video source to another.

Nothing streams between nodes. A stream server subprocess serves MJPEG over
HTTP and the browser connects to it directly; what travels along an edge is a
description of where that video lives. Three spellings of that description grew
up in parallel - a ``frame_stream`` dict, a bare ``source_url``, and a bare
``stream_url`` - so whether two stream nodes could be wired together came down
to which convention each happened to use.

Producers build their handle with :func:`frame_stream`; consumers accept either
a handle or a URL and call :func:`source_url` to get something to read.
"""
from __future__ import annotations

from typing import Any

KIND = "blacknode.frame-stream"
SCHEMA_VERSION = 1


def frame_stream(
    *,
    stream_id: str,
    stream_url: str = "",
    snapshot_url: str = "",
    health_url: str = "",
    media_type: str = "image/jpeg",
    label: str = "",
    topic: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """Build the handle a stream-producing node puts on its ``frame_stream`` port.

    ``stream_url`` is the continuous endpoint and ``snapshot_url`` a single
    frame. Consumers that re-publish or analyse video need the former; a node
    that only wants one picture can use the latter.
    """
    handle: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "stream_id": str(stream_id or ""),
        "stream_url": str(stream_url or ""),
        "snapshot_url": str(snapshot_url or ""),
        "health_url": str(health_url or ""),
        "media_type": media_type,
        "mode": "latest",
        "clock": "unix_ns",
    }
    if label:
        handle["label"] = str(label)
    if topic:
        handle["topic"] = str(topic)
    handle.update(extra)
    return handle


def is_frame_stream(value: Any) -> bool:
    return isinstance(value, dict) and str(value.get("kind") or "") == KIND


def source_url(value: Any, fallback: str = "") -> str:
    """Resolve a readable video URL from a handle, a plain URL, or neither.

    Accepts a ``frame_stream`` handle, a bare URL string, or nothing, so a
    consumer can take either convention on one port. Streams published before
    ``stream_url`` joined the contract only carry the snapshot, whose sibling
    path on the same server is the continuous endpoint.
    """
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        direct = str(value.get("stream_url") or "").strip()
        if direct:
            return direct
        snapshot = str(value.get("snapshot_url") or "").strip()
        if snapshot.endswith("/snapshot.jpg"):
            return snapshot[: -len("/snapshot.jpg")] + "/stream.mjpg"
        if snapshot:
            return snapshot
    return (fallback or "").strip()


def stream_label(value: Any, fallback: str = "camera") -> str:
    if isinstance(value, dict):
        for key in ("label", "topic", "stream_id"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return fallback
