"""Scene assembly nodes: SceneRoot, MeshLoad, Transform, Merge, MaterialAssign."""
from __future__ import annotations
from typing import Any
from blacknode.node import node


# Scene objects are plain dicts — swappable with a real scene graph later.

@node(inputs=[], outputs=["scene"], name="SceneRoot")
def scene_root(ctx: dict) -> dict:
    return {"scene": {"type": "scene", "children": [], "meta": {}}}


@node(inputs=["path", "format"], outputs=["mesh"], name="MeshLoad")
def mesh_load(ctx: dict) -> dict:
    path   = ctx.get("path", "")
    fmt    = ctx.get("format", "obj")
    return {"mesh": {"type": "mesh", "path": path, "format": fmt, "children": []}}


@node(inputs=["object", "translate", "rotate", "scale"], outputs=["object"], name="Transform")
def transform_node(ctx: dict) -> dict:
    obj  = dict(ctx.get("object") or {})
    obj["transform"] = {
        "translate": ctx.get("translate", [0, 0, 0]),
        "rotate":    ctx.get("rotate",    [0, 0, 0]),
        "scale":     ctx.get("scale",     [1, 1, 1]),
    }
    return {"object": obj}


@node(inputs=["parent", "child"], outputs=["scene"], name="MergeScene")
def merge_scene(ctx: dict) -> dict:
    parent = dict(ctx.get("parent") or {"type": "scene", "children": []})
    child  = ctx.get("child")
    parent.setdefault("children", []).append(child)
    return {"scene": parent}


@node(inputs=["object", "material"], outputs=["object"], name="MaterialAssign")
def material_assign(ctx: dict) -> dict:
    obj  = dict(ctx.get("object") or {})
    obj["material"] = ctx.get("material", {})
    return {"object": obj}
