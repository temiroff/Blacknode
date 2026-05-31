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
import re
import subprocess
import time
from typing import Any, Callable

try:  # NumPy is only used once CuPy (which depends on it) is confirmed present.
    import numpy as np
except Exception:  # pragma: no cover - keeps the package importable on minimal installs
    np = None

from blacknode.node import Any as AnyPort
from blacknode.node import Enum, Float, Image, Int, Text, node

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

CUSTOM_SIGNATURES = ["auto", "map", "binary", "image_rgb"]   # auto | (in,out,n) | (a,b,out,n) | image pixels
CUSTOM_INITS = ["arange", "random", "zeros", "ones"]
CUSTOM_OUTPUT_MODES = ["auto", "same", "summary", "list", "image"]
CUSTOM_KERNEL_TEMPLATES = [
    "custom",
    "image_invert",
    "cinematic_teal_orange",
    "neon_edge_glow_2d",
    "comic_ink_2d",
    "thermal_vision",
    "dream_glow_2d",
    "grayscale",
    "channel_swap",
    "vignette",
]

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

DEFAULT_IMAGE_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int p = i * channels;
    float r = in[p + 0];
    float g = in[p + 1];
    float b = in[p + 2];

    out[p + 0] = 1.0f - r;
    out[p + 1] = 1.0f - g;
    out[p + 2] = 1.0f - b;
}'''

DEFAULT_CINEMATIC_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;

    int pixels = width * height;
    if (i >= pixels) return;

    int p = i * channels;

    float r = in[p + 0];
    float g = in[p + 1];
    float b = in[p + 2];

    // cinematic contrast
    r = powf(r, 0.85f);
    g = powf(g, 0.90f);
    b = powf(b, 1.05f);

    // teal-orange grade
    r *= 1.15f;
    g *= 1.00f;
    b *= 0.90f;

    // vignette
    int x = i % width;
    int y = i / width;

    float nx = (x / (float)width) * 2.0f - 1.0f;
    float ny = (y / (float)height) * 2.0f - 1.0f;

    float dist = sqrtf(nx * nx + ny * ny);
    float vignette = 1.0f - fminf(dist * 0.4f, 0.4f);

    r *= vignette;
    g *= vignette;
    b *= vignette;

    out[p + 0] = fminf(fmaxf(r, 0.0f), 1.0f);
    out[p + 1] = fminf(fmaxf(g, 0.0f), 1.0f);
    out[p + 2] = fminf(fmaxf(b, 0.0f), 1.0f);

    if (channels == 4)
        out[p + 3] = in[p + 3];
}'''

DEFAULT_GRAYSCALE_IMAGE_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int p = i * channels;
    float y = in[p + 0] * 0.2126f + in[p + 1] * 0.7152f + in[p + 2] * 0.0722f;
    out[p + 0] = y;
    out[p + 1] = y;
    out[p + 2] = y;
}'''

DEFAULT_CHANNEL_SWAP_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int p = i * channels;
    out[p + 0] = in[p + 2];
    out[p + 1] = in[p + 1];
    out[p + 2] = in[p + 0];
}'''

DEFAULT_VIGNETTE_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int x = i % width;
    int y = i / width;
    float nx = (x / (float)width) * 2.0f - 1.0f;
    float ny = (y / (float)height) * 2.0f - 1.0f;
    float dist = sqrtf(nx * nx + ny * ny);
    float v = 1.0f - fminf(dist * 0.45f, 0.55f);

    int p = i * channels;
    out[p + 0] = in[p + 0] * v;
    out[p + 1] = in[p + 1] * v;
    out[p + 2] = in[p + 2] * v;
}'''

DEFAULT_NEON_EDGE_GLOW_2D_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels)
{
    int x = blockDim.x * blockIdx.x + threadIdx.x;
    int y = blockDim.y * blockIdx.y + threadIdx.y;

    if (x >= width || y >= height) return;

    int i = y * width + x;
    int p = i * channels;

    float r = in[p + 0];
    float g = in[p + 1];
    float b = in[p + 2];

    float lum = 0.299f * r + 0.587f * g + 0.114f * b;

    int xl = x > 0 ? x - 1 : 0;
    int xr = x + 1 < width ? x + 1 : width - 1;
    int yu = y > 0 ? y - 1 : 0;
    int yd = y + 1 < height ? y + 1 : height - 1;

    int pl = (y * width + xl) * channels;
    int pr = (y * width + xr) * channels;
    int pu = (yu * width + x) * channels;
    int pd = (yd * width + x) * channels;

    float lumL = 0.299f * in[pl] + 0.587f * in[pl + 1] + 0.114f * in[pl + 2];
    float lumR = 0.299f * in[pr] + 0.587f * in[pr + 1] + 0.114f * in[pr + 2];
    float lumU = 0.299f * in[pu] + 0.587f * in[pu + 1] + 0.114f * in[pu + 2];
    float lumD = 0.299f * in[pd] + 0.587f * in[pd + 1] + 0.114f * in[pd + 2];

    float edge = fabsf(lumR - lumL) + fabsf(lumD - lumU);
    edge = fminf(edge * 4.0f, 1.0f);

    float nx = (x / (float)width)  * 2.0f - 1.0f;
    float ny = (y / (float)height) * 2.0f - 1.0f;
    float dist = sqrtf(nx * nx + ny * ny);
    float vignette = 1.0f - fminf(dist * 0.55f, 0.55f);

    r = powf(r, 0.95f) * 1.08f;
    g = powf(g, 1.00f) * 1.02f;
    b = powf(b, 1.08f) * 0.95f;

    r += edge * 0.95f;
    g += edge * 0.35f;
    b += edge * 0.10f;

    r *= vignette;
    g *= vignette;
    b *= vignette;

    out[p + 0] = fminf(fmaxf(r, 0.0f), 1.0f);
    out[p + 1] = fminf(fmaxf(g, 0.0f), 1.0f);
    out[p + 2] = fminf(fmaxf(b, 0.0f), 1.0f);

    if (channels == 4)
        out[p + 3] = in[p + 3];
}'''

DEFAULT_COMIC_INK_2D_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels)
{
    int x = blockDim.x * blockIdx.x + threadIdx.x;
    int y = blockDim.y * blockIdx.y + threadIdx.y;
    if (x >= width || y >= height) return;

    int i = y * width + x;
    int p = i * channels;

    int xl = x > 0 ? x - 1 : 0;
    int xr = x + 1 < width ? x + 1 : width - 1;
    int yu = y > 0 ? y - 1 : 0;
    int yd = y + 1 < height ? y + 1 : height - 1;

    int pl = (y * width + xl) * channels;
    int pr = (y * width + xr) * channels;
    int pu = (yu * width + x) * channels;
    int pd = (yd * width + x) * channels;

    float lumL = 0.299f * in[pl] + 0.587f * in[pl + 1] + 0.114f * in[pl + 2];
    float lumR = 0.299f * in[pr] + 0.587f * in[pr + 1] + 0.114f * in[pr + 2];
    float lumU = 0.299f * in[pu] + 0.587f * in[pu + 1] + 0.114f * in[pu + 2];
    float lumD = 0.299f * in[pd] + 0.587f * in[pd + 1] + 0.114f * in[pd + 2];
    float edge = fminf((fabsf(lumR - lumL) + fabsf(lumD - lumU)) * 5.5f, 1.0f);

    float levels = 5.0f;
    float r = floorf(in[p + 0] * levels) / levels;
    float g = floorf(in[p + 1] * levels) / levels;
    float b = floorf(in[p + 2] * levels) / levels;

    r = powf(fminf(r * 1.22f, 1.0f), 0.82f);
    g = powf(fminf(g * 1.12f, 1.0f), 0.86f);
    b = powf(fminf(b * 1.05f, 1.0f), 0.90f);

    float ink = 1.0f - fminf(edge * 0.9f, 0.9f);
    out[p + 0] = r * ink;
    out[p + 1] = g * ink;
    out[p + 2] = b * ink;

    if (channels == 4)
        out[p + 3] = in[p + 3];
}'''

DEFAULT_THERMAL_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels)
{
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int p = i * channels;
    float lum = 0.299f * in[p + 0] + 0.587f * in[p + 1] + 0.114f * in[p + 2];
    float hotT = fminf(fmaxf((lum - 0.50f) / 0.50f, 0.0f), 1.0f);
    float hot = hotT * hotT * (3.0f - 2.0f * hotT);
    float mid = 1.0f - fabsf(lum - 0.52f) * 2.1f;
    mid = fminf(fmaxf(mid, 0.0f), 1.0f);
    float coldT = fminf(fmaxf((lum - 0.10f) / 0.65f, 0.0f), 1.0f);
    float cold = 1.0f - coldT * coldT * (3.0f - 2.0f * coldT);

    out[p + 0] = fminf(fmaxf(hot * 1.15f + mid * 0.65f, 0.0f), 1.0f);
    out[p + 1] = fminf(fmaxf(mid * 1.05f + cold * 0.15f, 0.0f), 1.0f);
    out[p + 2] = fminf(fmaxf(cold * 0.95f + (1.0f - hot) * 0.20f, 0.0f), 1.0f);

    if (channels == 4)
        out[p + 3] = in[p + 3];
}'''

DEFAULT_DREAM_GLOW_2D_SOURCE = '''extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels)
{
    int x = blockDim.x * blockIdx.x + threadIdx.x;
    int y = blockDim.y * blockIdx.y + threadIdx.y;
    if (x >= width || y >= height) return;

    int i = y * width + x;
    int p = i * channels;

    int xl = x > 0 ? x - 1 : 0;
    int xr = x + 1 < width ? x + 1 : width - 1;
    int yu = y > 0 ? y - 1 : 0;
    int yd = y + 1 < height ? y + 1 : height - 1;

    int pl = (y * width + xl) * channels;
    int pr = (y * width + xr) * channels;
    int pu = (yu * width + x) * channels;
    int pd = (yd * width + x) * channels;

    float blurR = (in[p + 0] * 4.0f + in[pl] + in[pr] + in[pu] + in[pd]) * 0.125f;
    float blurG = (in[p + 1] * 4.0f + in[pl + 1] + in[pr + 1] + in[pu + 1] + in[pd + 1]) * 0.125f;
    float blurB = (in[p + 2] * 4.0f + in[pl + 2] + in[pr + 2] + in[pu + 2] + in[pd + 2]) * 0.125f;

    float r = in[p + 0] * 0.70f + blurR * 0.45f + 0.04f;
    float g = in[p + 1] * 0.70f + blurG * 0.38f + 0.03f;
    float b = in[p + 2] * 0.72f + blurB * 0.50f + 0.08f;

    out[p + 0] = fminf(fmaxf(powf(r, 0.82f), 0.0f), 1.0f);
    out[p + 1] = fminf(fmaxf(powf(g, 0.86f), 0.0f), 1.0f);
    out[p + 2] = fminf(fmaxf(powf(b, 0.78f), 0.0f), 1.0f);

    if (channels == 4)
        out[p + 3] = in[p + 3];
}'''

DEFAULT_CUSTOM_SOURCES = {
    DEFAULT_CUSTOM_SOURCE.strip(),
    DEFAULT_BINARY_SOURCE.strip(),
    DEFAULT_IMAGE_SOURCE.strip(),
}

CUSTOM_KERNEL_TEMPLATE_INFO = {
    "custom": {"source": "", "signature": "auto", "output_mode": "auto"},
    "image_invert": {"source": DEFAULT_IMAGE_SOURCE, "signature": "image_rgb", "output_mode": "image"},
    "cinematic_teal_orange": {"source": DEFAULT_CINEMATIC_SOURCE, "signature": "image_rgb", "output_mode": "image"},
    "neon_edge_glow_2d": {
        "source": DEFAULT_NEON_EDGE_GLOW_2D_SOURCE,
        "signature": "image_rgb",
        "output_mode": "image",
        "launch": "image_2d",
    },
    "comic_ink_2d": {
        "source": DEFAULT_COMIC_INK_2D_SOURCE,
        "signature": "image_rgb",
        "output_mode": "image",
        "launch": "image_2d",
    },
    "thermal_vision": {"source": DEFAULT_THERMAL_SOURCE, "signature": "image_rgb", "output_mode": "image"},
    "dream_glow_2d": {
        "source": DEFAULT_DREAM_GLOW_2D_SOURCE,
        "signature": "image_rgb",
        "output_mode": "image",
        "launch": "image_2d",
    },
    "grayscale": {"source": DEFAULT_GRAYSCALE_IMAGE_SOURCE, "signature": "image_rgb", "output_mode": "image"},
    "channel_swap": {"source": DEFAULT_CHANNEL_SWAP_SOURCE, "signature": "image_rgb", "output_mode": "image"},
    "vignette": {"source": DEFAULT_VIGNETTE_SOURCE, "signature": "image_rgb", "output_mode": "image"},
}


def _seed_array(np_mod, init: str, n: int, dtype, seed: int):
    rng = np_mod.random.default_rng(seed)
    if init == "random":
        return rng.random(n).astype(dtype)
    if init == "zeros":
        return np_mod.zeros(n, dtype=dtype)
    if init == "ones":
        return np_mod.ones(n, dtype=dtype)
    return np_mod.arange(n, dtype=dtype)


def _has_custom_input(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_image_data_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("data:image/")


def _as_numeric_array(value: Any, dtype: Any, label: str):
    try:
        arr = np.asarray(value, dtype=dtype)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{label} is not numeric array data ({type(exc).__name__}: {exc})") from exc
    if arr.size < 1:
        raise ValueError(f"{label} is empty")
    if arr.ndim == 0:
        arr = arr.reshape(1)
    return arr


def _custom_data_from_value(value: Any, dtype: Any) -> dict[str, Any]:
    if _is_image_data_url(value):
        from blacknode.nodes.image import decode_image

        arr = decode_image(value).astype(np.float32, copy=False)
        return {"kind": "image", "a": arr, "shape": arr.shape, "source": "data-url"}

    if isinstance(value, dict):
        if _is_image_data_url(value.get("image")):
            return _custom_data_from_value(value["image"], dtype)
        if "a" in value and "b" in value:
            a = _as_numeric_array(value["a"], dtype, "input.a")
            b = _as_numeric_array(value["b"], dtype, "input.b")
            if a.size != b.size:
                raise ValueError(f"input.a and input.b sizes differ ({a.size} != {b.size})")
            return {"kind": "binary", "a": a, "b": b, "shape": a.shape, "source": "dict"}
        raw = value.get("data", value.get("values", value.get("array")))
        if raw is not None:
            arr = _as_numeric_array(raw, dtype, "input.data")
            shape = value.get("shape")
            if shape:
                try:
                    arr = arr.reshape(tuple(int(x) for x in shape))
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(f"input.shape cannot reshape data ({type(exc).__name__}: {exc})") from exc
            return {"kind": "dict", "a": arr, "shape": arr.shape, "source": "dict"}
        raise ValueError("dict input must contain image, a/b, data, values, or array")

    if isinstance(value, str):
        try:
            return _custom_data_from_value(__import__("json").loads(value), dtype)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                "string input must be an image data URL or JSON numeric array/object"
            ) from exc

    if isinstance(value, (int, float, bool)):
        arr = _as_numeric_array([value], dtype, "input")
        return {"kind": "scalar", "a": arr, "shape": arr.shape, "source": "scalar"}

    arr = _as_numeric_array(value, dtype, "input")
    return {"kind": "array", "a": arr, "shape": arr.shape, "source": type(value).__name__}


def _synthetic_custom_data(signature: str, size: int, dtype: Any, init: str, seed: int) -> dict[str, Any]:
    n = max(2, int(size))
    if signature == "image_rgb":
        side = max(8, int(math.isqrt(n)))
        rng = np.random.default_rng(seed)
        arr = rng.random((side, side, 3), dtype=np.float32)
        return {"kind": "synthetic_image", "a": arr, "shape": arr.shape, "source": "synthetic"}
    a = _seed_array(np, init, n, dtype, seed)
    data = {"kind": "synthetic", "a": a, "shape": a.shape, "source": "synthetic"}
    if signature == "binary":
        data["b"] = _seed_array(np, init, n, dtype, seed + 1)
    return data


def _effective_custom_signature(signature: str, data: dict[str, Any]) -> str:
    if signature != "auto":
        return signature
    if data["kind"] in {"image", "synthetic_image"}:
        return "image_rgb"
    if data["kind"] == "binary" or "b" in data:
        return "binary"
    return "map"


def _default_custom_source_for(signature: str) -> str:
    if signature == "binary":
        return DEFAULT_BINARY_SOURCE
    if signature == "image_rgb":
        return DEFAULT_IMAGE_SOURCE
    return DEFAULT_CUSTOM_SOURCE


def _custom_source_signature(source: str, kernel: str) -> str | None:
    match = re.search(rf"\b{re.escape(kernel)}\s*\(([^)]*)\)", source)
    if not match:
        return None
    params = [p.strip().lower() for p in match.group(1).split(",") if p.strip()]
    joined = " ".join(params)
    if len(params) == 5 and "width" in joined and "height" in joined and "channels" in joined:
        return "image_rgb"
    if len(params) == 4:
        return "binary"
    if len(params) == 3:
        return "map"
    return None


def _custom_output_value(host: Any, data: dict[str, Any], output_mode: str) -> tuple[Any, str]:
    arr = np.asarray(host)
    mode = output_mode if output_mode in CUSTOM_OUTPUT_MODES else "auto"
    if mode in {"auto", "same"}:
        if data["kind"] in {"image", "synthetic_image"}:
            mode = "image"
        elif data["kind"] == "scalar" and arr.size == 1:
            return float(arr.ravel()[0]), "scalar"
        elif data["kind"] in {"array", "dict", "binary"} and arr.size <= 4096:
            mode = "list"
        else:
            mode = "summary"

    if mode == "image":
        from blacknode.nodes.image import encode_image

        return encode_image(arr), "image"
    if mode == "list":
        return arr.tolist(), "list"
    return _summary(arr), "summary"


def _custom_launch_mode(
    source: str,
    signature: str,
    template_info: dict[str, Any] | None = None,
) -> str:
    launch = str((template_info or {}).get("launch") or "").strip()
    if launch in {"linear", "image_2d"}:
        return launch
    if signature == "image_rgb" and re.search(r"\b(?:blockIdx|blockDim|threadIdx)\s*\.\s*y\b", source):
        return "image_2d"
    return "linear"


@node(
    inputs={
        "input": AnyPort,
        "template": Enum(CUSTOM_KERNEL_TEMPLATES, default="image_invert"),
        "code": Text(DEFAULT_IMAGE_SOURCE),
        "kernel": Text("user_kernel"),
        "signature": Enum(CUSTOM_SIGNATURES, default="auto"),
        "size": Int(default=1048576),
        "dtype": Enum(["float32", "float64"], default="float32"),
        "init": Enum(CUSTOM_INITS, default="arange"),
        "seed": Int(default=0),
        "block": Int(default=256),
        "output_mode": Enum(CUSTOM_OUTPUT_MODES, default="auto"),
    },
    outputs=["output:Any", "result:Dict", "gpu_ms:Float", "device:Text", "report:Dict"],
    name="CUDACustomKernel",
    category="NVIDIA GPU",
    description="Compile and run your own CUDA C kernel on optional Any input data. Images round-trip as Image-compatible data URLs.",
)
def cuda_custom_kernel(ctx: dict) -> dict:
    input_value = ctx.get("input")
    template = str(ctx.get("template") or "custom").strip()
    template_info: dict[str, Any] | None = None
    source = str(ctx.get("code") or "").strip()
    kernel = str(ctx.get("kernel") or "user_kernel").strip()
    sig = str(ctx.get("signature") or "auto").strip()
    size = max(2, int(ctx.get("size") or 1048576))
    dtype = str(ctx.get("dtype") or "float32").strip()
    init = str(ctx.get("init") or "arange").strip()
    seed = int(ctx.get("seed") or 0)
    block = max(1, min(1024, int(ctx.get("block") or 256)))
    output_mode = str(ctx.get("output_mode") or "auto").strip()

    if sig not in CUSTOM_SIGNATURES:
        return _custom_error(
            f"unknown signature '{sig}'; use auto, map (in,out,n), "
            "binary (a,b,out,n), or image_rgb (in,out,width,height,channels)"
        )
    if template not in CUSTOM_KERNEL_TEMPLATES:
        return _custom_error(f"unknown template '{template}'; choose one of {CUSTOM_KERNEL_TEMPLATES}")
    if template != "custom":
        template_info = CUSTOM_KERNEL_TEMPLATE_INFO[template]
        source = str(template_info["source"]).strip()
        sig = str(template_info["signature"])
        if output_mode == "auto":
            output_mode = str(template_info["output_mode"])
    if dtype not in _CTYPE:
        return _custom_error(f"unknown dtype '{dtype}'; use float32 or float64")
    if output_mode not in CUSTOM_OUTPUT_MODES:
        return _custom_error(f"unknown output_mode '{output_mode}'; choose one of {CUSTOM_OUTPUT_MODES}")
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

    try:
        np_dtype = np.float32 if dtype == "float32" else np.float64
        if _has_custom_input(input_value):
            data = _custom_data_from_value(input_value, np_dtype)
        else:
            synthetic_sig = (
                "image_rgb"
                if sig == "auto" and source == DEFAULT_IMAGE_SOURCE.strip()
                else "map" if sig == "auto" else sig
            )
            data = _synthetic_custom_data(synthetic_sig, size, np_dtype, init, seed)
        effective_sig = _effective_custom_signature(sig, data)
        if effective_sig == "image_rgb":
            data["a"] = np.asarray(data["a"], dtype=np.float32)
            dtype = "float32"
            np_dtype = np.float32
        if not source or source in DEFAULT_CUSTOM_SOURCES:
            source = _default_custom_source_for(effective_sig)
        source_sig = _custom_source_signature(source, kernel)
        if source_sig and source_sig != effective_sig:
            return _custom_error(
                f"kernel signature mismatch: selected '{effective_sig}' but {kernel} looks like "
                f"'{source_sig}'. Set signature to {source_sig}, use auto, or update the CUDA function arguments.",
                device=name,
            )
    except Exception as exc:  # noqa: BLE001
        return _custom_error(f"could not adapt input ({type(exc).__name__}: {exc})", device=name)

    try:
        launch_mode = _custom_launch_mode(source, effective_sig, template_info)
        block_shape: tuple[int, ...] = (block,)
        grid_shape: tuple[int, ...]
        if effective_sig == "image_rgb":
            arr = np.asarray(data["a"], dtype=np_dtype)
            if arr.ndim == 2:
                arr = arr[:, :, None]
            if arr.ndim != 3:
                return _custom_error("image_rgb signature requires HxW or HxWxC numeric input", device=name)
            h, w, channels = arr.shape
            a = cp.asarray(arr.ravel())
            out = cp.empty_like(a)
            n = h * w
            args = (a, out, np.int32(w), np.int32(h), np.int32(channels))
            if launch_mode == "image_2d":
                side = max(1, min(32, int(math.sqrt(block))))
                block_shape = (side, side)
                grid_shape = ((w + side - 1) // side, (h + side - 1) // side)
            else:
                grid_shape = ((n + block - 1) // block,)
            output_shape = arr.shape
        elif effective_sig == "binary":
            launch_mode = "linear"
            a_host = np.asarray(data["a"], dtype=np_dtype).ravel()
            if "b" in data:
                b_host = np.asarray(data["b"], dtype=np_dtype).ravel()
            else:
                b_host = _seed_array(np, init, a_host.size, np_dtype, seed + 1)
            if a_host.size != b_host.size:
                return _custom_error(f"binary inputs differ in size ({a_host.size} != {b_host.size})", device=name)
            a = cp.asarray(a_host)
            b = cp.asarray(b_host)
            out = cp.empty_like(a)
            n = a_host.size
            args = (a, b, out, np.int32(n))
            grid_shape = ((n + block - 1) // block,)
            output_shape = data.get("shape", a_host.shape)
        else:
            launch_mode = "linear"
            a_host = np.asarray(data["a"], dtype=np_dtype)
            output_shape = data.get("shape", a_host.shape)
            a = cp.asarray(a_host.ravel())
            out = cp.empty_like(a)
            n = a.size
            args = (a, out, np.int32(n))
            grid_shape = ((n + block - 1) // block,)
    except Exception as exc:  # noqa: BLE001
        return _custom_error(f"could not prepare GPU buffers ({type(exc).__name__}: {exc})", device=name)

    try:
        kern = cp.RawKernel(source, kernel)
        kern(grid_shape, block_shape, args)            # first launch compiles (NVRTC)
        cp.cuda.Stream.null.synchronize()
        ev0, ev1 = cp.cuda.Event(), cp.cuda.Event()
        ev0.record()
        for _ in range(5):
            kern(grid_shape, block_shape, args)
        ev1.record()
        ev1.synchronize()
        gpu_ms = cp.cuda.get_elapsed_time(ev0, ev1) / 5
    except Exception as exc:  # noqa: BLE001 - NVRTC compile log / launch error
        return _custom_error(f"{type(exc).__name__}: {exc}", device=name)

    host = cp.asnumpy(out)
    try:
        host = host.reshape(output_shape)
    except Exception:
        pass
    try:
        output, output_kind = _custom_output_value(host, data, output_mode)
    except Exception as exc:  # noqa: BLE001
        return _custom_error(f"could not encode output ({type(exc).__name__}: {exc})", device=name)

    report = {
        "kernel": kernel,
        "template": template,
        "signature": effective_sig,
        "requested_signature": sig,
        "size": n,
        "dtype": dtype,
        "input_kind": data.get("kind", "synthetic"),
        "input_shape": list(data.get("shape", [])),
        "output_kind": output_kind,
        "launch": launch_mode,
        "block": list(block_shape) if len(block_shape) > 1 else block_shape[0],
        "grid": list(grid_shape) if len(grid_shape) > 1 else grid_shape[0],
        "device": name,
        "compute_capability": cc,
        "compiled": True,
        "gpu_ms": round(gpu_ms, 4),
    }
    return {
        "output": output,
        "result": _summary(host),
        "gpu_ms": round(gpu_ms, 4),
        "device": name,
        "report": report,
    }


def _custom_error(message: str, device: str = "") -> dict:
    return {
        "output": {"error": message},
        "result": {"error": message},
        "gpu_ms": 0.0,
        "device": device,
        "report": {"error": message, "device": device, "compiled": False},
    }


# ---------------------------------------------------------------------------
# GPU capability detection + preflight (Task 1.2)
# ---------------------------------------------------------------------------

def _gpu_capability() -> dict:
    """Detect the local NVIDIA GPU. Prefer CuPy (richest data), fall back to
    nvidia-smi, and degrade to "unavailable" instead of raising."""
    try:
        import cupy as cp
        props = cp.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else props["name"]
        free, total = cp.cuda.runtime.memGetInfo()
        ver = cp.cuda.runtime.runtimeGetVersion()  # e.g. 12080 -> "12.8"
        return {
            "available": True,
            "source": "cupy",
            "name": name,
            "compute_capability": f"{props['major']}.{props['minor']}",
            "vram_total_gb": round(total / 1024 ** 3, 2),
            "vram_free_gb": round(free / 1024 ** 3, 2),
            "cuda_version": f"{ver // 1000}.{(ver % 1000) // 10}",
            "cupy_available": True,
        }
    except Exception:
        pass

    smi = _gpu_capability_from_smi()
    if smi is not None:
        return smi

    return {
        "available": False,
        "source": "none",
        "name": "",
        "compute_capability": "",
        "vram_total_gb": 0.0,
        "vram_free_gb": 0.0,
        "cuda_version": "",
        "cupy_available": False,
    }


def _gpu_capability_from_smi() -> dict | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,compute_cap",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4,
        )
    except Exception:
        return None
    if out.returncode != 0 or not (out.stdout or "").strip():
        return None
    parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
    if len(parts) < 4:
        return None
    try:
        total_gb = round(float(parts[1]) / 1024, 2)
        free_gb = round(float(parts[2]) / 1024, 2)
    except ValueError:
        total_gb = free_gb = 0.0
    return {
        "available": True,
        "source": "nvidia-smi",
        "name": parts[0],
        "compute_capability": parts[3],
        "vram_total_gb": total_gb,
        "vram_free_gb": free_gb,
        "cuda_version": "",
        "cupy_available": False,
    }


@node(
    inputs=[],
    outputs=["available:Bool", "name:Text", "compute_capability:Text",
             "vram_total_gb:Float", "vram_free_gb:Float", "cuda_version:Text", "report:Dict"],
    name="GPUCapability",
    category="NVIDIA GPU",
    description="Detect the local NVIDIA GPU's name, compute capability, VRAM, and CUDA version.",
)
def gpu_capability(ctx: dict) -> dict:
    cap = _gpu_capability()
    return {
        "available": cap["available"],
        "name": cap["name"],
        "compute_capability": cap["compute_capability"],
        "vram_total_gb": cap["vram_total_gb"],
        "vram_free_gb": cap["vram_free_gb"],
        "cuda_version": cap["cuda_version"],
        "report": cap,
    }


@node(
    inputs={"min_compute": Float(default=8.0), "min_vram_gb": Float(default=8.0)},
    outputs=["ok:Bool", "reason:Text", "report:Dict"],
    name="GPURequirement",
    category="NVIDIA GPU",
    description="Preflight gate: passes only if the local GPU meets a minimum compute capability and VRAM.",
)
def gpu_requirement(ctx: dict) -> dict:
    min_compute = float(ctx.get("min_compute") or 0.0)
    min_vram = float(ctx.get("min_vram_gb") or 0.0)
    cap = _gpu_capability()
    meta = {**cap, "min_compute": min_compute, "min_vram_gb": min_vram}

    if not cap["available"]:
        return {"ok": False, "reason": "No NVIDIA GPU available.", "report": {**meta, "ok": False}}

    try:
        cc = float(cap["compute_capability"])
    except (ValueError, TypeError):
        cc = 0.0

    failures = []
    if cc < min_compute:
        failures.append(f"compute {cap['compute_capability']} < required {min_compute}")
    if cap["vram_total_gb"] < min_vram:
        failures.append(f"VRAM {cap['vram_total_gb']} GB < required {min_vram} GB")

    ok = not failures
    reason = (
        f"OK: {cap['name']} (compute {cap['compute_capability']}, {cap['vram_total_gb']} GB)"
        if ok else
        f"GPU does not meet requirements: {'; '.join(failures)}"
    )
    return {"ok": ok, "reason": reason, "report": {**meta, "ok": ok, "failures": failures}}


# ---------------------------------------------------------------------------
# GPU image filter — apply a CUDA op to a real image (LoadImage -> here -> OutputImage)
# ---------------------------------------------------------------------------

IMAGE_FILTERS = ["grayscale", "invert", "brighten", "threshold",
                 "gaussian_blur", "sharpen", "sobel_edges"]


def _img_lum(cp, g):
    return 0.299 * g[:, :, 0] + 0.587 * g[:, :, 1] + 0.114 * g[:, :, 2]


def _img_blur(cp, g):
    p = cp.pad(g, ((1, 1), (1, 1), (0, 0)), mode="edge")
    h, w = g.shape[:2]
    out = cp.zeros_like(g)
    for di, row in enumerate(((1, 2, 1), (2, 4, 2), (1, 2, 1))):
        for dj, wt in enumerate(row):
            out = out + wt * p[di:di + h, dj:dj + w, :]
    return out / 16.0


def _apply_image_filter(cp, op: str, g, amount: float):
    if op == "grayscale":
        lum = _img_lum(cp, g)
        return cp.stack([lum, lum, lum], axis=-1)
    if op == "invert":
        return 1.0 - g
    if op == "brighten":
        return cp.clip(g * amount, 0.0, 1.0)
    if op == "threshold":
        cut = amount if 0.0 < amount < 1.0 else 0.5
        m = (_img_lum(cp, g) > cut).astype(g.dtype)
        return cp.stack([m, m, m], axis=-1)
    if op == "gaussian_blur":
        return _img_blur(cp, g)
    if op == "sharpen":
        return cp.clip(g + amount * (g - _img_blur(cp, g)), 0.0, 1.0)
    if op == "sobel_edges":
        lum = _img_lum(cp, g)
        p = cp.pad(lum, 1, mode="edge")
        h, w = lum.shape
        def at(di, dj):
            return p[di:di + h, dj:dj + w]
        gx = (at(0, 2) + 2 * at(1, 2) + at(2, 2)) - (at(0, 0) + 2 * at(1, 0) + at(2, 0))
        gy = (at(2, 0) + 2 * at(2, 1) + at(2, 2)) - (at(0, 0) + 2 * at(0, 1) + at(0, 2))
        e = cp.clip(cp.sqrt(gx * gx + gy * gy), 0.0, 1.0)
        return cp.stack([e, e, e], axis=-1)
    return g


@node(
    inputs={"image": Image, "op": Enum(IMAGE_FILTERS, default="grayscale"), "amount": Float(default=1.0)},
    outputs=["image:Image", "gpu_ms:Float", "device:Text", "report:Dict"],
    name="CUDAImageFilter",
    category="NVIDIA GPU",
    description="Apply a GPU (CUDA) image filter to an image and return the filtered image.",
)
def cuda_image_filter(ctx: dict) -> dict:
    image = ctx.get("image")
    op = str(ctx.get("op") or "grayscale").strip()
    amount = float(ctx.get("amount") or 1.0)

    if not image:
        return _img_error("no image input (connect a LoadImage node)")
    if op not in IMAGE_FILTERS:
        return _img_error(f"unknown filter '{op}'; choose one of {IMAGE_FILTERS}")
    if np is None:
        return _img_error("NumPy is not installed.")

    try:
        import cupy as cp
    except Exception as exc:  # noqa: BLE001
        return _img_error(f"CuPy not available ({type(exc).__name__}: {exc}).")

    try:
        from blacknode.nodes.image import decode_image, encode_image
        arr = decode_image(image)
    except Exception as exc:  # noqa: BLE001
        return _img_error(f"could not read image ({type(exc).__name__}: {exc}).")

    try:
        props = cp.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else props["name"]
    except Exception as exc:  # noqa: BLE001
        return _img_error(f"no CUDA device ({type(exc).__name__}: {exc}).")

    try:
        g = cp.asarray(arr)
        cp.cuda.Stream.null.synchronize()
        ev0, ev1 = cp.cuda.Event(), cp.cuda.Event()
        ev0.record()
        out = _apply_image_filter(cp, op, g, amount)
        ev1.record()
        ev1.synchronize()
        gpu_ms = cp.cuda.get_elapsed_time(ev0, ev1)
        host = cp.asnumpy(out)
    except Exception as exc:  # noqa: BLE001
        return _img_error(f"GPU filter failed ({type(exc).__name__}: {exc}).")

    h, w = arr.shape[:2]
    return {
        "image": encode_image(host),
        "gpu_ms": round(gpu_ms, 4),
        "device": name,
        "report": {"op": op, "amount": amount, "width": w, "height": h,
                   "device": name, "gpu_ms": round(gpu_ms, 4)},
    }


def _img_error(message: str) -> dict:
    return {"image": "", "gpu_ms": 0.0, "device": "", "report": {"error": message}}


# ---------------------------------------------------------------------------
# Tensor Core GEMM (WMMA) — hand-written Tensor Core kernel via NVRTC.
# CUTLASS-style: this is the WMMA primitive CUTLASS itself is built on, and it
# runs through the same NVRTC path as the other kernels (works on Windows).
# ---------------------------------------------------------------------------

_WMMA_GEMM_SRC = r'''
#include <mma.h>
using namespace nvcuda;
// A: MxK, B: KxN, C: MxN, all row-major; M,N,K multiples of 16. One warp per 16x16 C tile.
extern "C" __global__ void wmma_gemm(const half* A, const half* B, float* C, int M, int N, int K) {
    int warp = (blockIdx.x * blockDim.x + threadIdx.x) / 32;
    int tilesN = N / 16;
    int tileRow = warp / tilesN;
    int tileCol = warp % tilesN;
    if (tileRow * 16 >= M || tileCol * 16 >= N) return;

    wmma::fragment<wmma::matrix_a, 16, 16, 16, half, wmma::row_major> af;
    wmma::fragment<wmma::matrix_b, 16, 16, 16, half, wmma::row_major> bf;
    wmma::fragment<wmma::accumulator, 16, 16, 16, float> cf;
    wmma::fill_fragment(cf, 0.0f);

    for (int k = 0; k < K; k += 16) {
        wmma::load_matrix_sync(af, A + (tileRow * 16) * K + k, K);
        wmma::load_matrix_sync(bf, B + k * N + (tileCol * 16), N);
        wmma::mma_sync(cf, af, bf, cf);
    }
    wmma::store_matrix_sync(C + (tileRow * 16) * N + (tileCol * 16), cf, N, wmma::mem_row_major);
}
'''

_WMMA_KERNEL = None


def _wmma_kernel():
    global _WMMA_KERNEL
    if _WMMA_KERNEL is None:
        import cupy as cp
        _WMMA_KERNEL = cp.RawKernel(_WMMA_GEMM_SRC, "wmma_gemm", options=("--std=c++17",))
    return _WMMA_KERNEL


@node(
    inputs={"size": Int(default=1024), "seed": Int(default=0)},
    outputs=["result:Any", "gpu_ms:Float", "tflops:Float", "cublas_ms:Float", "device:Text", "report:Dict"],
    name="TensorCoreGEMM",
    category="NVIDIA GPU",
    description="Hand-written Tensor Core (WMMA, fp16) matrix multiply via NVRTC, with TFLOPS and a cuBLAS comparison.",
)
def tensor_core_gemm(ctx: dict) -> dict:
    size = int(ctx.get("size") or 1024)
    seed = int(ctx.get("seed") or 0)
    n = max(16, (size // 16) * 16)  # WMMA needs multiples of 16

    if np is None:
        return _tc_error("NumPy is not installed.")
    try:
        import cupy as cp
    except Exception as exc:  # noqa: BLE001
        return _tc_error(f"CuPy not available ({type(exc).__name__}: {exc}).")
    try:
        props = cp.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else props["name"]
        cc = f"{props['major']}.{props['minor']}"
    except Exception as exc:  # noqa: BLE001
        return _tc_error(f"no CUDA device ({type(exc).__name__}: {exc}).")

    try:
        cp.random.seed(seed)
        a = cp.random.random((n, n), dtype=cp.float32).astype(cp.float16)
        b = cp.random.random((n, n), dtype=cp.float32).astype(cp.float16)
        c = cp.zeros((n, n), dtype=cp.float32)
        kern = _wmma_kernel()
        warps = (n // 16) * (n // 16)
        block = 256
        grid = (warps * 32 + block - 1) // block
        c16 = cp.empty((n, n), dtype=cp.float16)  # preallocate so cuBLAS timing excludes allocation
        _, wmma_ms = _time_gpu(cp, lambda: kern((grid,), (block,), (a, b, c, n, n, n)), iters=30)
        _, cublas_ms = _time_gpu(cp, lambda: cp.matmul(a, b, out=c16), iters=30)
        ref = a.astype(cp.float32) @ b.astype(cp.float32)
        rel = float(cp.max(cp.abs(c - ref)) / cp.max(cp.abs(ref)))
    except Exception as exc:  # noqa: BLE001
        return _tc_error(f"WMMA GEMM failed ({type(exc).__name__}: {exc}).", device=name)

    flop = 2.0 * n * n * n
    tflops = round(flop / (wmma_ms * 1e9), 2) if wmma_ms > 0 else 0.0
    cublas_tflops = round(flop / (cublas_ms * 1e9), 2) if cublas_ms > 0 else 0.0
    correct = rel < 1e-2
    report = {
        "n": n, "dtype": "float16",
        "wmma_ms": round(wmma_ms, 4), "wmma_tflops": tflops,
        "cublas_ms": round(cublas_ms, 4), "cublas_tflops": cublas_tflops,
        "rel_err": round(rel, 8), "correct": correct,
        "device": name, "compute_capability": cc,
        "implementation": "WMMA Tensor Cores (CUDA C / NVRTC)",
    }
    return {
        "result": {"n": n, "tflops": tflops, "cublas_tflops": cublas_tflops, "correct": correct},
        "gpu_ms": round(wmma_ms, 4),
        "tflops": tflops,
        "cublas_ms": round(cublas_ms, 4),
        "device": name,
        "report": report,
    }


def _tc_error(message: str, device: str = "") -> dict:
    return {"result": {"error": message}, "gpu_ms": 0.0, "tflops": 0.0,
            "cublas_ms": 0.0, "device": device, "report": {"error": message, "device": device}}
