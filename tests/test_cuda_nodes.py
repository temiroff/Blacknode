"""Task 1.1 — CUDAKernelLab real GPU compute block.

GPU-dependent checks skip cleanly when CuPy / an NVIDIA GPU is absent (e.g. CI).
The no-GPU contract (structured error, never raises) is always exercised.
"""
import pytest

from blacknode.nodes.cuda import (
    CUDA_OPS,
    DEFAULT_BINARY_SOURCE,
    DEFAULT_CUSTOM_SOURCE,
    cuda_custom_kernel,
    cuda_kernel_lab,
    gpu_capability,
    gpu_requirement,
)


def _has_gpu() -> bool:
    try:
        import cupy as cp
        cp.cuda.runtime.getDeviceProperties(0)
        return True
    except Exception:
        return False


HAS_GPU = _has_gpu()
gpu_only = pytest.mark.skipif(not HAS_GPU, reason="no CuPy / NVIDIA GPU available")


# --- contract that always holds (no GPU needed) ---------------------------------

def test_unknown_op_returns_structured_error():
    r = cuda_kernel_lab({"op": "does_not_exist"})
    assert r["speedup"] == 0.0
    assert "error" in r["report"]
    assert r["gpu_ms"] == 0.0


def test_unknown_dtype_returns_structured_error():
    r = cuda_kernel_lab({"op": "vector_add", "dtype": "float128"})
    assert "error" in r["report"]


def test_node_never_raises_on_bad_input():
    # Whatever the environment, the node returns a dict rather than raising.
    out = cuda_kernel_lab({"op": "vector_add", "size": 4096})
    assert isinstance(out, dict)
    assert set(out) >= {"result", "gpu_ms", "cpu_ms", "speedup", "device", "report"}


# --- real GPU execution ---------------------------------------------------------

@gpu_only
@pytest.mark.parametrize("op", CUDA_OPS)
def test_each_op_runs_correctly_on_gpu(op):
    r = cuda_kernel_lab({"op": op, "size": 1 << 16, "dtype": "float32", "seed": 7})
    rep = r["report"]
    assert "error" not in rep, rep
    assert r["gpu_ms"] > 0.0
    assert rep["correct"] is True, f"{op}: diff={rep.get('max_abs_diff')}"
    assert r["device"]


@gpu_only
def test_float64_path_runs():
    r = cuda_kernel_lab({"op": "saxpy", "size": 1 << 16, "dtype": "float64", "seed": 1})
    assert r["report"]["correct"] is True
    assert r["report"]["dtype"] == "float64"


@gpu_only
def test_report_carries_device_metadata():
    r = cuda_kernel_lab({"op": "matmul", "size": 1 << 16})
    rep = r["report"]
    assert "compute_capability" in rep
    assert rep["implementation"]


# --- custom kernel (the "do anything" tier) -------------------------------------

def test_custom_kernel_empty_source_uses_default():
    # An untouched node (no committed source) runs the default kernel shown in the
    # editor rather than erroring on missing source.
    r = cuda_custom_kernel({"code": "   "})
    assert r["report"].get("error", "") != "no CUDA source provided"


def test_custom_kernel_never_raises():
    out = cuda_custom_kernel({"code": "garbage", "size": 1024})
    assert isinstance(out, dict)
    assert set(out) >= {"result", "gpu_ms", "device", "report"}


@gpu_only
def test_custom_map_kernel_runs():
    # out = in*2 + 1 over arange -> [1, 3, 5, 7, ...]
    r = cuda_custom_kernel({"code": DEFAULT_CUSTOM_SOURCE, "size": 1 << 14, "init": "arange"})
    assert r["report"]["compiled"] is True
    assert r["gpu_ms"] > 0.0
    assert r["result"]["sample"] == [1.0, 3.0, 5.0, 7.0]


@gpu_only
def test_custom_binary_kernel_runs():
    r = cuda_custom_kernel({"code": DEFAULT_BINARY_SOURCE, "signature": "binary",
                            "size": 1 << 14, "init": "random"})
    assert r["report"]["compiled"] is True
    assert r["report"]["signature"] == "binary"


@gpu_only
def test_custom_kernel_compile_error_is_reported():
    r = cuda_custom_kernel({"code": "this is not valid cuda", "kernel": "user_kernel"})
    assert r["report"]["compiled"] is False
    assert "error" in r["result"]
    assert r["gpu_ms"] == 0.0


# --- GPU capability + preflight (Task 1.2) --------------------------------------

def test_gpu_capability_shape():
    r = gpu_capability({})
    assert set(r) >= {"available", "name", "compute_capability",
                      "vram_total_gb", "vram_free_gb", "cuda_version", "report"}
    assert isinstance(r["available"], bool)


def test_gpu_requirement_unmeetable_fails():
    # Compute 99.0 can never be met (and with no GPU it reports unavailable) ->
    # either way the gate fails with a readable reason.
    r = gpu_requirement({"min_compute": 99.0, "min_vram_gb": 8.0})
    assert r["ok"] is False
    assert r["reason"]


@gpu_only
def test_gpu_capability_reports_device():
    r = gpu_capability({})
    assert r["available"] is True
    assert r["name"]
    assert r["compute_capability"]
    assert r["vram_total_gb"] > 0


@gpu_only
def test_gpu_requirement_pass_and_fail():
    assert gpu_requirement({"min_compute": 1.0, "min_vram_gb": 1.0})["ok"] is True
    fail = gpu_requirement({"min_compute": 99.0, "min_vram_gb": 1.0})
    assert fail["ok"] is False
    assert "compute" in fail["reason"]
