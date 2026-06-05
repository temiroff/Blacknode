"""Cook templates/cutlass-image-showcase.json end-to-end with a real image."""
import base64
import json
import numpy as np
from pathlib import Path

from blacknode.nodes.image import encode_image
from blacknode.workflow import run_workflow  # type: ignore
from blacknode.sandbox.cutlass_worker import get_worker

DEMO = Path(r"F:\PROJECTS\NVDIA\Blacknode\.local-notes\cutlass-demo")
DEMO.mkdir(parents=True, exist_ok=True)


def save(data_url, path):
    Path(path).write_bytes(base64.b64decode(data_url.split(",", 1)[1]))


# A structured, colourful scene that embosses/edges nicely: gradient sky,
# a "sun" disc, and rolling bands.
H, W = 360, 480
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
sky = np.stack([0.3 + 0.5 * (yy / H), 0.5 + 0.3 * (yy / H), 0.9 - 0.4 * (yy / H)], -1)
sun = np.exp(-(((xx - 360) ** 2 + (yy - 90) ** 2) / 2200.0))[..., None] * np.array([1.0, 0.9, 0.4])
hills = (0.35 + 0.15 * np.sin(xx / 40.0))[..., None] * (yy / H > 0.72)[..., None] * np.array([0.2, 0.7, 0.3])
scene = np.clip(sky + sun + hills, 0, 1).astype(np.float32)
img_path = DEMO / "scene_input.png"
save(encode_image(scene), img_path)

template = json.loads(Path(r"F:\PROJECTS\NVDIA\Blacknode\templates\cutlass-image-showcase.json").read_text())
template["node_meta"]["load"]["params"]["source"] = str(img_path)

try:
    for filt in ("emboss", "edge", "sharpen"):
        template["node_meta"]["cutlass"]["params"]["filter"] = filt
        result = run_workflow(template)
        value = result["value"]
        save(value, DEMO / f"scene_{filt}.png")
        print(f"cooked filter={filt:8} -> scene_{filt}.png  (output is image: {str(value).startswith('data:image')})")
finally:
    get_worker().stop()
print("done")
