"""Find heavy CUTLASS conv configs and save the evolving image."""
import base64, time, numpy as np
from pathlib import Path
from blacknode.nodes.cuda import cutlass
from blacknode.nodes.image import encode_image
from blacknode.sandbox.cutlass_worker import get_worker

DEMO = Path(r"F:\PROJECTS\NVDIA\Blacknode\.local-notes\cutlass-demo")


def save(data_url, path):
    Path(path).write_bytes(base64.b64decode(data_url.split(",", 1)[1]))


# high-res structured image so each GEMM is big
H = W = 512
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
r = np.sqrt((xx - W / 2) ** 2 + (yy - H / 2) ** 2)
img = np.clip(np.stack([0.5 + 0.5 * np.sin(r / 9.0),
                        0.5 + 0.5 * np.sin((xx + yy) / 11.0),
                        xx / W], -1).astype(np.float32), 0, 1)
enc = encode_image(img)

configs = [
    ("depthwise iters",   {"op": "conv2d", "filter": "emboss", "iterations": 200, "filters": 1}),
    ("conv layer bank",   {"op": "conv2d", "filter": "edge",   "iterations": 40,  "filters": 64}),
    ("HEAVY conv stack",  {"op": "conv2d", "filter": "edge",   "iterations": 120, "filters": 96}),
]
try:
    for name, params in configs:
        t0 = time.perf_counter()
        rr = cutlass({"input": enc, **params})
        wall = time.perf_counter() - t0
        rep = rr["report"]
        tag = name.replace(" ", "_")
        save(rr["output"], DEMO / f"heavy_{tag}.png")
        print("%-18s wall=%5.1fs  gpu_ms=%8.0f  gemms=%4d  %6.1f TFLOPS  GEMM(M=%d,K=%d,N=%d)" % (
            name, wall, rr["gpu_ms"], rep["gemms"], rep["tflops"],
            rep["gemm_M"], rep["gemm_K"], rep["gemm_N"]))
finally:
    get_worker().stop()
print("saved to", DEMO)
