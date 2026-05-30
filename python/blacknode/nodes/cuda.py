"""Real GPU compute blocks (CuPy / CUDA).

This is the first NVIDIA "block family": a single node, ``CUDAKernelLab``, exposing
a dropdown of curated GPU operations that genuinely run on the local NVIDIA GPU via
CuPy. Each op reports measured GPU time, a NumPy CPU baseline, the speedup, the
device name, and a correctness check against NumPy.

Custom ops (vector_add, saxpy, elementwise_mul, grayscale, mandelbrot) run a CUDA C
kernel compiled at runtime with ``cupy.RawKernel`` (NVRTC). The rest use CuPy's
high-level cuBLAS/cuFFT/reduction paths. No GPU? The node returns a structured
error instead of raising, so the editor stays usable.
"""
from __future__ import annotations

import math
import time
from typing import Any, Callable

try:  # NumPy is only used once CuPy (which depends on it) is confirmed present.
    import numpy as np
except Exception:  # pragma: no cover - keeps the package importable on minimal installs
    np = None

from blacknode.node import Enum, Float, Int, Text, node

# ---------------------------------------------------------------------------
# Op catalogue (drives the dropdown and validation)
# ---------------------------------------------------------------------------

CUDA_OPS: list[str] = [
    "vector_add",
    "saxpy",
    "elementwise_mul",
    "dot_product",
    "matmul",
    "softmax",
    "vector_normalize",
    "fft",
    "grayscale",
    "gaussian_blur",
    "sobel_edges",
    "mandelbrot",
    "monte_carlo_pi",
]

_RAW_OPS = {"vector_add", "saxpy", "elementwise_mul", "grayscale", "mandelbrot"}
_IMAGE_OPS = {"grayscale", "gaussian_blur", "sobel_edges", "mandelbrot"}

_CTYPE = {"float32": "float", "float64": "double"}

# RawKernel sources use {T} as the element type so we can compile a float32 and a
# float64 variant from the same source. Compiled kernels are cached by (op, ctype).
_RAW_SOURCES: dict[str, str] = {
    "vector_add": """
extern "C" __global__ void vector_add(const {T}* a, const {T}* b, {T}* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) out[i] = a[i] + b[i];
}
""",
    "saxpy": """
extern "C" __global__ void saxpy({T} alpha, const {T}* x, const {T}* y, {T}* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) out[i] = alpha * x[i] + y[i];
}
""",
    "elementwise_mul": """
extern "C" __global__ void elementwise_mul(const {T}* a, const {T}* b, {T}* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) out[i] = a[i] * b[i];
}
""",
    "grayscale": """
extern "C" __global__ void grayscale(const {T}* img, {T}* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) out[i] = ({T})(0.299 * img[3*i] + 0.587 * img[3*i+1] + 0.114 * img[3*i+2]);
}
""",
    "mandelbrot": """
extern "C" __global__ void mandelbrot(int* out, int width, int height, int max_iter) {
    int idx = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (idx >= n) return;
    int px = idx % width;
    int py = idx / width;
    double cx = -2.5 + 3.5 * px / width;
    double cy = -1.25 + 2.5 * py / height;
    double zx = 0.0, zy = 0.0;
    int it = 0;
    while (zx*zx + zy*zy <= 4.0 && it < max_iter) {
        double t = zx*zx - zy*zy + cx;
        zy = 2.0*zx*zy + cy;
        zx = t;
        it++;
    }
    out[idx] = it;
}
""",
}

_KERNEL_CACHE: dict[tuple, Any] = {}
_MANDEL_MAX_ITER = 100


def _raw_kernel(op: str, ctype: str):
    key = (op, ctype)
    kern = _KERNEL_CACHE.get(key)
    if kern is None:
        import cupy as cp  # local import: only needed on the GPU path

        kern = cp.RawKernel(_RAW_SOURCES[op].replace("{T}", ctype), op)
        _KERNEL_CACHE[key] = kern
    return kern


# ---------------------------------------------------------------------------
# Input generation (seeded; identical arrays feed both GPU and CPU)
# ---------------------------------------------------------------------------

def _make_inputs(op: str, size: int, dtype: str, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    np_dtype = np.float32 if dtype == "float32" else np.float64

    if op == "matmul":
        n = max(2, int(math.isqrt(size)))
        return {"a": rng.standard_normal((n, n)).astype(np_dtype),
                "b": rng.standard_normal((n, n)).astype(np_dtype), "n": n}
    if op == "mandelbrot":
        side = max(8, int(math.isqrt(size)))
        return {"width": side, "height": side, "max_iter": _MANDEL_MAX_ITER}
    if op == "grayscale":
        side = max(8, int(math.isqrt(size)))
        return {"img": rng.random((side * side, 3)).astype(np_dtype), "pixels": side * side}
    if op in ("gaussian_blur", "sobel_edges"):
        side = max(8, int(math.isqrt(size)))
        return {"img": rng.random((side, side)).astype(np_dtype), "side": side}
    if op == "monte_carlo_pi":
        pts = rng.random((size, 2)).astype(np_dtype)
        return {"pts": pts}
    if op == "saxpy":
        return {"alpha": np_dtype(2.0),
                "x": rng.standard_normal(size).astype(np_dtype),
                "y": rng.standard_normal(size).astype(np_dtype)}
    # vector_add, elementwise_mul, dot_product, softmax, vector_normalize, fft
    return {"a": rng.standard_normal(size).astype(np_dtype),
            "b": rng.standard_normal(size).astype(np_dtype)}


# ---------------------------------------------------------------------------
# High-level ops: one implementation parameterised by the array module (xp),
# so NumPy (CPU) and CuPy (GPU) run identical code.
# ---------------------------------------------------------------------------

def _highlevel(xp, op: str, data: dict[str, Any]):
    if op == "dot_product":
        return xp.dot(data["a"], data["b"])
    if op == "matmul":
        return xp.matmul(data["a"], data["b"])
    if op == "softmax":
        x = data["a"]
        z = x - xp.max(x)
        e = xp.exp(z)
        return e / xp.sum(e)
    if op == "vector_normalize":
        x = data["a"]
        return x / (xp.linalg.norm(x) + 1e-12)
    if op == "fft":
        return xp.abs(xp.fft.fft(data["a"]))
    if op == "monte_carlo_pi":
        p = data["pts"]
        inside = xp.count_nonzero(p[:, 0] * p[:, 0] + p[:, 1] * p[:, 1] <= 1.0)
        return 4.0 * float(inside) / p.shape[0]
    if op == "gaussian_blur":
        return _blur3(xp, data["img"])
    if op == "sobel_edges":
        return _sobel(xp, data["img"])
    raise ValueError(f"not a high-level op: {op}")


def _blur3(xp, img):
    """3x3 Gaussian blur via shifts (identical in NumPy and CuPy)."""
    p = xp.pad(img, 1, mode="edge")
    k = [(1, 2, 1), (2, 4, 2), (1, 2, 1)]
    out = xp.zeros_like(img)
    for di, row in enumerate(k):
        for dj, w in enumerate(row):
            out = out + w * p[di:di + img.shape[0], dj:dj + img.shape[1]]
    return out / 16.0


def _sobel(xp, img):
    p = xp.pad(img, 1, mode="edge")
    def at(di, dj):
        return p[di:di + img.shape[0], dj:dj + img.shape[1]]
    gx = (at(0, 2) + 2 * at(1, 2) + at(2, 2)) - (at(0, 0) + 2 * at(1, 0) + at(2, 0))
    gy = (at(2, 0) + 2 * at(2, 1) + at(2, 2)) - (at(0, 0) + 2 * at(0, 1) + at(0, 2))
    return xp.sqrt(gx * gx + gy * gy)


def _cpu_raw(op: str, data: dict[str, Any]):
    """NumPy reference for the ops that run as RawKernels on the GPU."""
    if op == "vector_add":
        return data["a"] + data["b"]
    if op == "elementwise_mul":
        return data["a"] * data["b"]
    if op == "saxpy":
        return data["alpha"] * data["x"] + data["y"]
    if op == "grayscale":
        img = data["img"]
        return (0.299 * img[:, 0] + 0.587 * img[:, 1] + 0.114 * img[:, 2]).astype(img.dtype)
    if op == "mandelbrot":
        w, h, mi = data["width"], data["height"], data["max_iter"]
        cx = (-2.5 + 3.5 * np.arange(w) / w)[None, :]
        cy = (-1.25 + 2.5 * np.arange(h) / h)[:, None]
        c = cx + 1j * cy
        z = np.zeros_like(c)
        out = np.full(c.shape, mi, dtype=np.int32)   # never-escaped pixels reach max_iter
        alive = np.ones(c.shape, dtype=bool)         # still iterating
        for i in range(mi):
            z[alive] = z[alive] * z[alive] + c[alive]
            escaped = alive & (z.real * z.real + z.imag * z.imag > 4.0)
            out[escaped] = i + 1                      # iterations performed before escape
            alive &= ~escaped
        return out.ravel()
    raise ValueError(f"not a raw op: {op}")


def _gpu_raw(cp, op: str, gdata: dict[str, Any]):
    if op == "vector_add":
        a, b = gdata["a"], gdata["b"]
        out = cp.empty_like(a)
        n = a.size
        _launch(_raw_kernel(op, _ct(a)), n, (a, b, out, np.int32(n)))
        return out
    if op == "elementwise_mul":
        a, b = gdata["a"], gdata["b"]
        out = cp.empty_like(a)
        n = a.size
        _launch(_raw_kernel(op, _ct(a)), n, (a, b, out, np.int32(n)))
        return out
    if op == "saxpy":
        x, y = gdata["x"], gdata["y"]
        out = cp.empty_like(x)
        n = x.size
        alpha = x.dtype.type(gdata["alpha"])
        _launch(_raw_kernel(op, _ct(x)), n, (alpha, x, y, out, np.int32(n)))
        return out
    if op == "grayscale":
        img = gdata["img"]
        n = img.shape[0]
        out = cp.empty(n, dtype=img.dtype)
        _launch(_raw_kernel(op, _ct(img)), n, (img.ravel(), out, np.int32(n)))
        return out
    if op == "mandelbrot":
        w, h, mi = gdata["width"], gdata["height"], gdata["max_iter"]
        n = w * h
        out = cp.empty(n, dtype=cp.int32)
        _launch(_raw_kernel(op, "double"), n, (out, np.int32(w), np.int32(h), np.int32(mi)))
        return out
    raise ValueError(f"not a raw op: {op}")


def _ct(arr) -> str:
    return "float" if arr.dtype == np.float32 else "double"


def _launch(kernel, n: int, args: tuple) -> None:
    block = 256
    grid = (n + block - 1) // block
    kernel((grid,), (block,), args)


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def _time_gpu(cp, fn: Callable, iters: int = 5):
    start = cp.cuda.Event()
    end = cp.cuda.Event()
    r = fn()  # warm-up (includes any JIT compile)
    cp.cuda.Stream.null.synchronize()
    start.record()
    for _ in range(iters):
        r = fn()
    end.record()
    end.synchronize()
    return r, cp.cuda.get_elapsed_time(start, end) / iters


def _time_cpu(fn: Callable, iters: int = 5):
    r = fn()  # warm-up
    t0 = time.perf_counter()
    for _ in range(iters):
        r = fn()
    return r, (time.perf_counter() - t0) * 1000.0 / iters


# ---------------------------------------------------------------------------
# Result summarisation / correctness
# ---------------------------------------------------------------------------

def _summary(val) -> Any:
    if np.isscalar(val) or (hasattr(val, "shape") and val.shape == ()):
        return float(val)
    a = np.asarray(val)
    flat = a.ravel()
    return {
        "shape": list(a.shape),
        "dtype": str(a.dtype),
        "sample": [round(float(x), 6) for x in flat[:4].tolist()],
        "sum": round(float(a.sum()), 6),
    }


def _max_diff(gpu_host, cpu) -> float:
    if np.isscalar(cpu) or (hasattr(cpu, "shape") and getattr(cpu, "shape", None) == ()):
        return float(abs(float(gpu_host) - float(cpu)))
    return float(np.max(np.abs(np.asarray(gpu_host, dtype=np.float64) - np.asarray(cpu, dtype=np.float64))))


# ---------------------------------------------------------------------------
# The node
# ---------------------------------------------------------------------------

@node(
    inputs={
        "op": Enum(CUDA_OPS, default="vector_add"),
        "size": Int(default=1048576),
        "dtype": Enum(["float32", "float64"], default="float32"),
        "seed": Int(default=0),
    },
    outputs=["result:Any", "gpu_ms:Float", "cpu_ms:Float", "speedup:Float", "device:Text", "report:Dict"],
    name="CUDAKernelLab",
    category="NVIDIA GPU",
    description="Run a real CUDA/GPU op on the local NVIDIA GPU and measure it against a NumPy baseline.",
)
def cuda_kernel_lab(ctx: dict) -> dict:
    op = str(ctx.get("op") or "vector_add").strip()
    size = max(2, int(ctx.get("size") or 1048576))
    dtype = str(ctx.get("dtype") or "float32").strip()
    seed = int(ctx.get("seed") or 0)

    if op not in CUDA_OPS:
        return _error(op, f"unknown op '{op}'; choose one of {CUDA_OPS}")
    if dtype not in _CTYPE:
        return _error(op, f"unknown dtype '{dtype}'; use float32 or float64")

    if np is None:
        return _error(op, "NumPy is not installed; install numpy (and cupy-cuda12x) to run GPU blocks.")

    try:
        import cupy as cp
    except Exception as exc:  # noqa: BLE001 - any import/runtime failure is "no GPU here"
        return _error(op, f"CuPy not available ({type(exc).__name__}: {exc}). "
                          f"Install cupy-cuda12x and an NVIDIA GPU to run this block.")

    try:
        props = cp.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else props["name"]
        cc = f"{props['major']}.{props['minor']}"
    except Exception as exc:  # noqa: BLE001
        return _error(op, f"No CUDA device available ({type(exc).__name__}: {exc}).")

    data = _make_inputs(op, size, dtype, seed)

    try:
        if op in _RAW_OPS:
            gdata = _to_gpu(cp, data)
            gpu_val, gpu_ms = _time_gpu(cp, lambda: _gpu_raw(cp, op, gdata))
            cpu_val, cpu_ms = _time_cpu(lambda: _cpu_raw(op, data))
        else:
            gdata = _to_gpu(cp, data)
            gpu_val, gpu_ms = _time_gpu(cp, lambda: _highlevel(cp, op, gdata))
            cpu_val, cpu_ms = _time_cpu(lambda: _highlevel(np, op, data))
        cp.cuda.Stream.null.synchronize()
    except Exception as exc:  # noqa: BLE001
        return _error(op, f"GPU execution failed ({type(exc).__name__}: {exc}).", device=name)

    gpu_host = cp.asnumpy(gpu_val) if hasattr(gpu_val, "get") or hasattr(gpu_val, "device") else gpu_val
    max_diff = _max_diff(gpu_host, cpu_val)
    tol = 1e-2 if dtype == "float32" else 1e-6
    if op in ("fft", "matmul"):
        tol = 1e-1 if dtype == "float32" else 1e-6
    correct = max_diff <= tol if not (op in ("monte_carlo_pi",)) else abs(float(gpu_host) - math.pi) < 0.05

    speedup = round(cpu_ms / gpu_ms, 2) if gpu_ms > 0 else 0.0
    report = {
        "op": op,
        "size": size,
        "dtype": dtype,
        "device": name,
        "compute_capability": cc,
        "implementation": "RawKernel (CUDA C)" if op in _RAW_OPS else "CuPy (cuBLAS/cuFFT/reduction)",
        "gpu_ms": round(gpu_ms, 4),
        "cpu_ms": round(cpu_ms, 4),
        "speedup": speedup,
        "correct": bool(correct),
        "max_abs_diff": round(max_diff, 8),
        "tolerance": tol,
    }
    return {
        "result": _summary(gpu_host),
        "gpu_ms": round(gpu_ms, 4),
        "cpu_ms": round(cpu_ms, 4),
        "speedup": speedup,
        "device": name,
        "report": report,
    }


def _to_gpu(cp, data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in data.items():
        out[k] = cp.asarray(v) if isinstance(v, np.ndarray) else v
    return out


def _error(op: str, message: str, device: str = "") -> dict:
    return {
        "result": {"error": message},
        "gpu_ms": 0.0,
        "cpu_ms": 0.0,
        "speedup": 0.0,
        "device": device,
        "report": {"op": op, "error": message, "device": device},
    }


# ---------------------------------------------------------------------------
# Custom kernel: write your own CUDA C, compiled at runtime (NVRTC) and run on
# the local GPU. The "do anything" tier — predictable blocks' escape hatch.
# ---------------------------------------------------------------------------

CUSTOM_SIGNATURES = ["map", "binary"]   # (in,out,n) | (a,b,out,n)
CUSTOM_INITS = ["arange", "random", "zeros", "ones"]

DEFAULT_CUSTOM_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) out[i] = in[i] * 2.0f + 1.0f;
}'''

DEFAULT_BINARY_SOURCE = '''extern "C" __global__
void user_kernel(const float* a, const float* b, float* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) out[i] = a[i] * b[i];
}'''


def _seed_array(np_mod, init: str, n: int, dtype, seed: int):
    rng = np_mod.random.default_rng(seed)
    if init == "random":
        return rng.random(n).astype(dtype)
    if init == "zeros":
        return np_mod.zeros(n, dtype=dtype)
    if init == "ones":
        return np_mod.ones(n, dtype=dtype)
    return np_mod.arange(n, dtype=dtype)


@node(
    inputs={
        "code": Text(DEFAULT_CUSTOM_SOURCE),
        "kernel": Text("user_kernel"),
        "signature": Enum(CUSTOM_SIGNATURES, default="map"),
        "size": Int(default=1048576),
        "dtype": Enum(["float32", "float64"], default="float32"),
        "init": Enum(CUSTOM_INITS, default="arange"),
        "seed": Int(default=0),
        "block": Int(default=256),
    },
    outputs=["result:Any", "gpu_ms:Float", "device:Text", "report:Dict"],
    name="CUDACustomKernel",
    category="NVIDIA GPU",
    description="Compile and run your own CUDA C kernel on the local NVIDIA GPU (NVRTC). Compile errors are reported.",
)
def cuda_custom_kernel(ctx: dict) -> dict:
    source = str(ctx.get("code") or "").strip()
    kernel = str(ctx.get("kernel") or "user_kernel").strip()
    sig = str(ctx.get("signature") or "map").strip()
    size = max(2, int(ctx.get("size") or 1048576))
    dtype = str(ctx.get("dtype") or "float32").strip()
    init = str(ctx.get("init") or "arange").strip()
    seed = int(ctx.get("seed") or 0)
    block = max(1, min(1024, int(ctx.get("block") or 256)))

    if sig not in CUSTOM_SIGNATURES:
        return _custom_error(f"unknown signature '{sig}'; use 'map' (in,out,n) or 'binary' (a,b,out,n)")
    if not source:
        # No edits committed yet — run the default kernel that the editor shows.
        source = DEFAULT_BINARY_SOURCE if sig == "binary" else DEFAULT_CUSTOM_SOURCE
    if dtype not in _CTYPE:
        return _custom_error(f"unknown dtype '{dtype}'; use float32 or float64")
    if np is None:
        return _custom_error("NumPy is not installed; install numpy and cupy-cuda12x.")

    try:
        import cupy as cp
    except Exception as exc:  # noqa: BLE001
        return _custom_error(f"CuPy not available ({type(exc).__name__}: {exc}). "
                             f"Install cupy-cuda12x and an NVIDIA GPU.")

    try:
        props = cp.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else props["name"]
        cc = f"{props['major']}.{props['minor']}"
    except Exception as exc:  # noqa: BLE001
        return _custom_error(f"No CUDA device available ({type(exc).__name__}: {exc}).")

    np_dtype = np.float32 if dtype == "float32" else np.float64
    n = size
    a = cp.asarray(_seed_array(np, init, n, np_dtype, seed))
    out = cp.empty_like(a)
    if sig == "binary":
        b = cp.asarray(_seed_array(np, init, n, np_dtype, seed + 1))
        args = (a, b, out, np.int32(n))
    else:
        args = (a, out, np.int32(n))
    grid = (n + block - 1) // block

    try:
        kern = cp.RawKernel(source, kernel)
        kern((grid,), (block,), args)            # first launch compiles (NVRTC)
        cp.cuda.Stream.null.synchronize()
        ev0, ev1 = cp.cuda.Event(), cp.cuda.Event()
        ev0.record()
        for _ in range(5):
            kern((grid,), (block,), args)
        ev1.record()
        ev1.synchronize()
        gpu_ms = cp.cuda.get_elapsed_time(ev0, ev1) / 5
    except Exception as exc:  # noqa: BLE001 - NVRTC compile log / launch error
        return _custom_error(f"{type(exc).__name__}: {exc}", device=name)

    host = cp.asnumpy(out)
    report = {
        "kernel": kernel,
        "signature": sig,
        "size": n,
        "dtype": dtype,
        "block": block,
        "grid": grid,
        "device": name,
        "compute_capability": cc,
        "compiled": True,
        "gpu_ms": round(gpu_ms, 4),
    }
    return {
        "result": _summary(host),
        "gpu_ms": round(gpu_ms, 4),
        "device": name,
        "report": report,
    }


def _custom_error(message: str, device: str = "") -> dict:
    return {
        "result": {"error": message},
        "gpu_ms": 0.0,
        "device": device,
        "report": {"error": message, "device": device, "compiled": False},
    }
