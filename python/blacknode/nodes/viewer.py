"""Dependency-light presentation nodes for portable sensor data."""
from __future__ import annotations

import copy

from blacknode.node import Bool, Dict, Text, node


def _generic_scene(source: dict, title: str, frame: str, show_axes: bool) -> dict:
    kind = str(source.get("kind") or "")
    if kind == "blacknode.viewer-scene":
        scene = copy.deepcopy(source)
    else:
        points = source.get("points_xyz", source.get("points", []))
        colors = source.get("colors_rgb", source.get("colors", []))
        scene = {
            "kind": "blacknode.viewer-scene",
            "schema_version": 1,
            "primitive": "point-cloud",
            "points": copy.deepcopy(points) if isinstance(points, list) else [],
            "colors": copy.deepcopy(colors) if isinstance(colors, list) else [],
            "point_count": len(points) if isinstance(points, list) else 0,
        }
    scene.setdefault("kind", "blacknode.viewer-scene")
    scene.setdefault("schema_version", 1)
    scene.setdefault("primitive", "point-cloud")
    scene["viewer_role"] = "generic"
    scene["show_axes"] = bool(show_axes)
    if title:
        scene["title"] = title
    if frame:
        scene["frame"] = frame
    return scene


@node(
    name="GenericViewer",
    category="Core",
    description=(
        "Present a portable viewer scene or point-cloud frame with neutral axes. "
        "Map floors, occupancy, and robot geometry are reserved for map viewers."
    ),
    inputs={
        "source": Dict,
        "title": Text(default="Sensor data"),
        "frame": Text(default=""),
        "show_axes": Bool(default=True),
    },
    outputs={"scene": Dict, "status": Dict, "report": Text},
    primary_inputs=["source"],
    primary_outputs=["scene", "status"],
)
def generic_viewer(ctx: dict) -> dict:
    source = ctx.get("source") if isinstance(ctx.get("source"), dict) else {}
    supported = str(source.get("kind") or "") in {
        "blacknode.viewer-scene",
        "blacknode.point-cloud-frame",
        "blacknode.point-cloud",
    } or isinstance(source.get("points_xyz", source.get("points")), list)
    if not source or not supported:
        status = {
            "kind": "blacknode.viewer-status",
            "schema_version": 1,
            "state": "waiting" if not source else "unavailable",
            "source_fresh": False,
            "error": "" if not source else "source must be a viewer scene or point-cloud frame",
        }
        return {"scene": {}, "status": status, "report": status["error"] or "Generic viewer waiting for data"}
    scene = _generic_scene(
        source,
        str(ctx.get("title") or "").strip(),
        str(ctx.get("frame") or "").strip(),
        bool(ctx.get("show_axes", True)),
    )
    status = {
        "kind": "blacknode.viewer-status",
        "schema_version": 1,
        "state": "ready",
        "source_fresh": True,
        "error": "",
    }
    return {"scene": scene, "status": status, "report": "Generic viewer ready"}
