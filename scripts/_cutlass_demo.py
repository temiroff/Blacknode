import base64
import numpy as np
from blacknode.pkg.blacknode_cuda.cuda import cutlass
from blacknode.nodes.image import encode_image
from blacknode.sandbox.cutlass_worker import get_worker

OUT = r"F:\PROJECTS\NVDIA\Blacknode\.local-notes\cutlass-demo"


def save(data_url, path):
    open(path, "wb").write(base64.b64decode(data_url.split(",", 1)[1]))


# A recognizable test image: concentric rings + diagonal bars + gradient.
H = W = 320
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
r = np.sqrt((xx - W / 2) ** 2 + (yy - H / 2) ** 2)
img = np.clip(np.stack([
    0.5 + 0.5 * np.sin(r / 7.0),
    0.5 + 0.5 * np.sin((xx + yy) / 9.0),
    xx / W,
], axis=-1).astype(np.float32), 0, 1)
enc_in = encode_image(img)
save(enc_in, OUT + r"\input.png")

try:
    for filt in ("sharpen", "edge", "emboss", "gaussian"):
        r = cutlass({"input": enc_in, "op": "auto", "filter": filt})
        rep = r["report"]
        is_img = str(r["output"]).startswith("data:image")
        save(r["output"], OUT + "\\out_" + filt + ".png")
        print("conv[%-8s] route=%-6s GEMM(M=%d,K=%d,N=%d) %s TFLOPS out=%s" % (
            filt, rep["op"], rep["gemm_M"], rep["gemm_K"], rep["gemm_N"],
            rep["tflops"], "image" if is_img else "?"))

    a = np.random.rand(256, 128).astype(np.float32)
    b = np.random.rand(128, 64).astype(np.float32)
    rm = cutlass({"input": {"a": a, "b": b}, "op": "auto"})
    print("matmul          route=%-6s shape=%s correct=%s rel_err=%s %.2f TFLOPS" % (
        rm["report"]["op"], rm["result"]["shape"], rm["report"]["correct"],
        rm["report"]["rel_err"], rm["tflops"]))

    rb = cutlass({"op": "auto"})
    print("benchmark       route=%-6s n=%s %s TFLOPS (cublas %s)" % (
        rb["report"]["op"], rb["result"]["n"], rb["tflops"], rb["result"]["cublas_tflops"]))
finally:
    get_worker().stop()
print("saved PNGs to", OUT)
