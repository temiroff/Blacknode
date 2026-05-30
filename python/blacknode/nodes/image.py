"""Image I/O nodes.

Images flow through the graph as PNG **data-URL strings** (``data:image/png;base64,...``)
so they are JSON-safe, stream through the cook events, and render directly in the
editor. This lets you wire LoadImage -> a GPU filter/kernel -> OutputImage and see
the result on the canvas. Requires Pillow (``pip install pillow``).
"""
from __future__ import annotations

import base64
import io
from typing import Any

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

from blacknode.node import Image, Int, Text, node


def _pil():
    from PIL import Image as PILImage
    return PILImage


def decode_image(data: Any) -> "np.ndarray":
    """A data URL or a file path -> float32 HxWx3 array in [0, 1]."""
    pil = _pil()
    s = str(data or "")
    if s.startswith("data:"):
        raw = base64.b64decode(s.split(",", 1)[1])
        img = pil.open(io.BytesIO(raw)).convert("RGB")
    else:
        img = pil.open(s).convert("RGB")
    return np.asarray(img, dtype=np.float32) / 255.0


def encode_image(arr: "np.ndarray") -> str:
    """float array (HxW or HxWxC, [0,1]) -> PNG data URL."""
    pil = _pil()
    a = np.clip(np.asarray(arr, dtype=np.float32), 0.0, 1.0)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 1:
        a = np.repeat(a, 3, axis=-1)
    u8 = (a * 255.0 + 0.5).astype(np.uint8)
    img = pil.fromarray(u8)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _resize_max(arr: "np.ndarray", max_size: int) -> "np.ndarray":
    if max_size <= 0:
        return arr
    h, w = arr.shape[:2]
    if max(h, w) <= max_size:
        return arr
    pil = _pil()
    scale = max_size / float(max(h, w))
    new = (max(1, int(w * scale)), max(1, int(h * scale)))
    img = pil.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))
    img = img.resize(new, pil.LANCZOS)
    return np.asarray(img, dtype=np.float32) / 255.0


@node(
    inputs={"path": Text(""), "max_size": Int(default=768)},
    outputs=["image:Image", "width:Int", "height:Int", "report:Dict"],
    name="LoadImage",
    category="Image",
    description="Load an image file from disk into the graph (downscaled to max_size for speed).",
)
def load_image(ctx: dict) -> dict:
    path = str(ctx.get("path") or "").strip()
    max_size = int(ctx.get("max_size") or 0)
    if not path:
        return {"image": "", "width": 0, "height": 0, "report": {"error": "no path provided"}}
    if np is None:
        return {"image": "", "width": 0, "height": 0, "report": {"error": "NumPy not installed"}}
    try:
        arr = decode_image(path)
    except Exception as exc:  # noqa: BLE001
        return {"image": "", "width": 0, "height": 0,
                "report": {"error": f"{type(exc).__name__}: {exc}", "path": path}}
    arr = _resize_max(arr, max_size)
    h, w = arr.shape[:2]
    return {
        "image": encode_image(arr),
        "width": w,
        "height": h,
        "report": {"path": path, "width": w, "height": h},
    }


@node(
    inputs={"image": Image},
    outputs=["image:Image"],
    name="OutputImage",
    category="Image",
    description="Display an image result on the canvas. Cook it to see the picture.",
)
def output_image(ctx: dict) -> dict:
    return {"image": ctx.get("image") or ""}
