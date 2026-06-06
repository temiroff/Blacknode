"""Task 1.1 — CUDAKernelLab real GPU compute block.

GPU-dependent checks skip cleanly when CuPy / an NVIDIA GPU is absent (e.g. CI).
The no-GPU contract (structured error, never raises) is always exercised.
"""
import pytest

from blacknode.nodes.cuda import (
    CUDA_OPS,
    CUSTOM_KERNEL_TEMPLATE_INFO,
    CUSTOM_KERNEL_TEMPLATES,
    DEFAULT_BINARY_SOURCE,
    DEFAULT_CINEMATIC_SOURCE,
    DEFAULT_CUSTOM_SOURCE,
    DEFAULT_IMAGE_SOURCE,
    DEFAULT_NEON_EDGE_GLOW_2D_SOURCE,
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
    assert getattr(fn, "_bn_input_defaults")["template"] == "image_invert"
    assert getattr(fn, "_bn_input_defaults")["code"] == DEFAULT_IMAGE_SOURCE
    assert getattr(fn, "_bn_input_choices")["template"] == CUSTOM_KERNEL_TEMPLATES


def test_custom_kernel_detects_source_signature():
    assert cuda_nodes._custom_source_signature(DEFAULT_CUSTOM_SOURCE, "user_kernel") == "map"
    assert cuda_nodes._custom_source_signature(DEFAULT_BINARY_SOURCE, "user_kernel") == "binary"
    assert cuda_nodes._custom_source_signature(DEFAULT_IMAGE_SOURCE, "user_kernel") == "image_rgb"
    assert cuda_nodes._custom_source_signature(DEFAULT_CINEMATIC_SOURCE, "user_kernel") == "image_rgb"
    assert cuda_nodes._custom_source_signature(DEFAULT_NEON_EDGE_GLOW_2D_SOURCE, "user_kernel") == "image_rgb"


def test_custom_kernel_template_catalog_is_complete():
    assert set(CUSTOM_KERNEL_TEMPLATE_INFO) == set(CUSTOM_KERNEL_TEMPLATES)
    assert "map_double" not in CUSTOM_KERNEL_TEMPLATES
    assert "binary_multiply" not in CUSTOM_KERNEL_TEMPLATES
    assert CUSTOM_KERNEL_TEMPLATE_INFO["cinematic_teal_orange"]["signature"] == "image_rgb"
    assert "powf" in CUSTOM_KERNEL_TEMPLATE_INFO["cinematic_teal_orange"]["source"]
    assert CUSTOM_KERNEL_TEMPLATE_INFO["neon_edge_glow_2d"]["launch"] == "image_2d"
    assert "threadIdx.y" in CUSTOM_KERNEL_TEMPLATE_INFO["neon_edge_glow_2d"]["source"]


def test_custom_kernel_detects_2d_launch_from_source():
    assert cuda_nodes._custom_launch_mode(DEFAULT_NEON_EDGE_GLOW_2D_SOURCE, "image_rgb") == "image_2d"
    assert cuda_nodes._custom_launch_mode(DEFAULT_CINEMATIC_SOURCE, "image_rgb") == "linear"


def test_custom_image_kernel_without_input_emits_no_image():
    result = cuda_custom_kernel({"template": "cinematic_teal_orange", "input": ""})
    assert result["output"] == ""
    assert result["gpu_ms"] == 0.0
    assert result["report"]["skipped"] is True
    assert result["report"]["reason"] == "no image input"


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
@pytest.mark.parametrize("template", [t for t in CUSTOM_KERNEL_TEMPLATES if t != "custom"])
def test_custom_image_template_runs(template):
    img = image_nodes.encode_image(cuda_nodes.np.full((8, 8, 3), 0.5, dtype=cuda_nodes.np.float32))
    r = cuda_custom_kernel({"input": img, "template": template})
    assert r["report"]["compiled"] is True
    assert r["report"]["template"] == template
    assert r["report"]["signature"] == "image_rgb"
    assert isinstance(r["output"], str)
    assert r["output"].startswith("data:image/")


@gpu_only
def test_custom_2d_image_kernel_runs():
    img = image_nodes.encode_image(cuda_nodes.np.full((8, 8, 3), 0.5, dtype=cuda_nodes.np.float32))
    r = cuda_custom_kernel({"input": img, "template": "neon_edge_glow_2d"})
    assert r["report"]["compiled"] is True
    assert r["report"]["template"] == "neon_edge_glow_2d"
    assert r["report"]["signature"] == "image_rgb"
    assert r["report"]["launch"] == "image_2d"
    assert r["report"]["block"] == [16, 16]
    assert r["report"]["grid"] == [1, 1]
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


# --- CUTLASS GEMM (containerized) -----------------------------------------------

def _cutlass_image_ready() -> bool:
    import subprocess
    try:
        r = subprocess.run(["docker", "image", "inspect", "blacknode-cutlass:latest"],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


cutlass_ready = pytest.mark.skipif(
    not _cutlass_image_ready(),
    reason="blacknode-cutlass:latest image / Docker not available",
)


def test_cutlass_gemm_registered_and_matches_tensor_core_ports():
    fn = _NODE_REGISTRY["CUTLASSGemm"]
    tc = _NODE_REGISTRY["TensorCoreGEMM"]
    # Drop-in comparable: same output ports as the WMMA node.
    assert getattr(fn, "_bn_outputs") == getattr(tc, "_bn_outputs")
    assert getattr(fn, "_bn_category") == "NVIDIA GPU"


def test_cutlass_gemm_never_raises_without_docker(monkeypatch):
    # Force the worker to report Docker missing; the node must still return a
    # structured error dict rather than raising.
    from blacknode.sandbox import cutlass_worker
    monkeypatch.setattr(cutlass_worker, "_WORKER", None)
    monkeypatch.setenv("BLACKNODE_DOCKER", "definitely-not-a-real-docker-binary")
    from blacknode.nodes.cuda import cutlass_gemm
    out = cutlass_gemm({"size": 256})
    assert isinstance(out, dict)
    assert set(out) >= {"result", "gpu_ms", "tflops", "cublas_ms", "device", "report"}
    assert "error" in out["report"]
    assert out["gpu_ms"] == 0.0


@cutlass_ready
def test_cutlass_gemm_runs_in_container():
    from blacknode.nodes.cuda import cutlass_gemm
    from blacknode.sandbox.cutlass_worker import get_worker
    try:
        r = cutlass_gemm({"size": 512, "seed": 0})
        rep = r["report"]
        assert "error" not in rep, rep
        assert rep["correct"] is True, rep
        assert r["tflops"] > 0
        assert rep["cublas_tflops"] > 0
        assert rep["implementation"].startswith("CUTLASS")
        assert r["device"]
    finally:
        get_worker().stop()


# --- generic CUTLASS node (image / matrices / benchmark, one node) --------------

def test_generic_cutlass_node_declares_any_in_and_out():
    fn = _NODE_REGISTRY["CUTLASS"]
    assert getattr(fn, "_bn_input_types")["input"] == "Any"
    assert getattr(fn, "_bn_output_types")["output"] == "Any"
    assert getattr(fn, "_bn_category") == "NVIDIA GPU"


def test_generic_cutlass_auto_routes_by_input():
    assert cuda_nodes._cutlass_route(None) == "benchmark"
    assert cuda_nodes._cutlass_route("   ") == "benchmark"
    assert cuda_nodes._cutlass_route("data:image/png;base64,xxxx") == "conv2d"
    assert cuda_nodes._cutlass_route({"a": [[1, 2]], "b": [[1], [2]]}) == "matmul"


def test_generic_cutlass_never_raises_without_docker(monkeypatch):
    from blacknode.sandbox import cutlass_worker
    monkeypatch.setattr(cutlass_worker, "_WORKER", None)
    monkeypatch.setenv("BLACKNODE_DOCKER", "definitely-not-a-real-docker-binary")
    from blacknode.nodes.cuda import cutlass
    out = cutlass({"op": "benchmark"})
    assert isinstance(out, dict)
    assert set(out) >= {"output", "result", "gpu_ms", "tflops", "device", "report"}
    assert "error" in out["report"]


@cutlass_ready
@pytest.mark.skipif(cuda_nodes.np is None, reason="NumPy unavailable")
def test_generic_cutlass_convolves_an_image():
    img = image_nodes.encode_image(cuda_nodes.np.full((48, 48, 3), 0.5, dtype=cuda_nodes.np.float32))
    from blacknode.nodes.cuda import cutlass
    from blacknode.sandbox.cutlass_worker import get_worker
    try:
        r = cutlass({"input": img, "op": "auto", "filter": "edge"})
        assert r["report"]["op"] == "conv2d"
        assert r["report"]["filter"] == "edge"
        assert isinstance(r["output"], str) and r["output"].startswith("data:image/")
    finally:
        get_worker().stop()


@cutlass_ready
@pytest.mark.skipif(cuda_nodes.np is None, reason="NumPy unavailable")
def test_generic_cutlass_matmul_is_correct():
    np = cuda_nodes.np
    a = np.random.rand(64, 32).astype(np.float32)
    b = np.random.rand(32, 16).astype(np.float32)
    from blacknode.nodes.cuda import cutlass
    from blacknode.sandbox.cutlass_worker import get_worker
    try:
        r = cutlass({"input": {"a": a, "b": b}, "op": "matmul"})
        assert r["report"]["op"] == "matmul"
        assert r["result"]["shape"] == [64, 16]
        assert r["report"]["correct"] is True
    finally:
        get_worker().stop()
