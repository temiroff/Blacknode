"""Task 1.1 — CUDAKernelLab real GPU compute block.

GPU-dependent checks skip cleanly when CuPy / an NVIDIA GPU is absent (e.g. CI).
The no-GPU contract (structured error, never raises) is always exercised.
"""
import pytest

from blacknode.nodes.cuda import (
    CUDA_OPS,
    DEFAULT_BINARY_SOURCE,
    DEFAULT_CUSTOM_SOURCE,
    DEFAULT_IMAGE_SOURCE,
    cuda_custom_kernel,
    cuda_kernel_lab,
    gpu_capability,
    gpu_requirement,
)
from blacknode.node import _NODE_REGISTRY
from blacknode.nodes import cuda as cuda_nodes
from blacknode.nodes import image as image_nodes


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


def test_custom_kernel_declares_any_data_in_and_out():
    fn = _NODE_REGISTRY["CUDACustomKernel"]
    assert getattr(fn, "_bn_input_types")["input"] == "Any"
    assert getattr(fn, "_bn_output_types")["output"] == "Any"
    assert getattr(fn, "_bn_output_types")["result"] == "Dict"
    assert "output" in getattr(fn, "_bn_outputs")
    assert "result" in getattr(fn, "_bn_outputs")


def test_custom_kernel_default_code_is_image_kernel():
    fn = _NODE_REGISTRY["CUDACustomKernel"]
    assert getattr(fn, "_bn_input_defaults")["code"] == DEFAULT_IMAGE_SOURCE


def test_custom_kernel_detects_source_signature():
    assert cuda_nodes._custom_source_signature(DEFAULT_CUSTOM_SOURCE, "user_kernel") == "map"
    assert cuda_nodes._custom_source_signature(DEFAULT_BINARY_SOURCE, "user_kernel") == "binary"
    assert cuda_nodes._custom_source_signature(DEFAULT_IMAGE_SOURCE, "user_kernel") == "image_rgb"


@pytest.mark.skipif(cuda_nodes.np is None, reason="NumPy unavailable")
def test_custom_kernel_auto_detects_numeric_array_input():
    data = cuda_nodes._custom_data_from_value([1, 2, 3], cuda_nodes.np.float32)
    assert data["kind"] == "array"
    assert cuda_nodes._effective_custom_signature("auto", data) == "map"

    output, kind = cuda_nodes._custom_output_value(
        cuda_nodes.np.asarray([2, 4, 6], dtype=cuda_nodes.np.float32),
        data,
        "auto",
    )
    assert kind == "list"
    assert output == [2.0, 4.0, 6.0]


@pytest.mark.skipif(cuda_nodes.np is None, reason="NumPy unavailable")
def test_custom_kernel_auto_detects_image_data_url(monkeypatch):
    monkeypatch.setattr(
        image_nodes,
        "decode_image",
        lambda _data: cuda_nodes.np.zeros((2, 3, 3), dtype=cuda_nodes.np.float32),
    )
    data = cuda_nodes._custom_data_from_value("data:image/png;base64,placeholder", cuda_nodes.np.float32)
    assert data["kind"] == "image"
    assert data["shape"] == (2, 3, 3)
    assert cuda_nodes._effective_custom_signature("auto", data) == "image_rgb"


def test_custom_kernel_never_raises():
    out = cuda_custom_kernel({"code": "garbage", "size": 1024})
    assert isinstance(out, dict)
    assert set(out) >= {"output", "result", "gpu_ms", "device", "report"}


@gpu_only
def test_custom_map_kernel_runs():
    # out = in*2 + 1 over arange -> [1, 3, 5, 7, ...]
    r = cuda_custom_kernel({"code": DEFAULT_CUSTOM_SOURCE, "size": 1 << 14, "init": "arange"})
    assert r["report"]["compiled"] is True
    assert r["gpu_ms"] > 0.0
    assert "output" in r
    assert r["result"]["sample"] == [1.0, 3.0, 5.0, 7.0]


@gpu_only
def test_custom_binary_kernel_runs():
    r = cuda_custom_kernel({"code": DEFAULT_BINARY_SOURCE, "signature": "binary",
                            "size": 1 << 14, "init": "random"})
    assert r["report"]["compiled"] is True
    assert r["report"]["signature"] == "binary"


@gpu_only
def test_custom_image_kernel_missing_signature_defaults_auto():
    img = image_nodes.encode_image(cuda_nodes.np.zeros((8, 8, 3), dtype=cuda_nodes.np.float32))
    r = cuda_custom_kernel({"input": img, "code": DEFAULT_IMAGE_SOURCE})
    assert r["report"]["compiled"] is True
    assert r["report"]["signature"] == "image_rgb"
    assert isinstance(r["output"], str)
    assert r["output"].startswith("data:image/")


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


# --- Tensor Core (WMMA) GEMM ----------------------------------------------------

def test_tensor_core_gemm_never_raises():
    from blacknode.nodes.cuda import tensor_core_gemm
    out = tensor_core_gemm({"size": 256})
    assert isinstance(out, dict)
    assert set(out) >= {"result", "gpu_ms", "tflops", "cublas_ms", "device", "report"}


@gpu_only
def test_tensor_core_gemm_runs_correctly():
    from blacknode.nodes.cuda import tensor_core_gemm
    r = tensor_core_gemm({"size": 512, "seed": 0})
    rep = r["report"]
    assert "error" not in rep, rep
    assert rep["correct"] is True, rep
    assert r["tflops"] > 0
    assert rep["cublas_tflops"] > 0
    assert rep["implementation"].startswith("WMMA")


@gpu_only
def test_tensor_core_gemm_rounds_to_multiple_of_16():
    from blacknode.nodes.cuda import tensor_core_gemm
    r = tensor_core_gemm({"size": 100})
    assert r["report"]["n"] == 96  # 100 -> floor to multiple of 16
