# NVIDIA GPU Blocks

Blacknode runs **real CUDA work on a local NVIDIA GPU** through
[CuPy](https://cupy.dev/). These are not planning or mock nodes — they compile
and execute on the device and report measured timings. This page documents what
is real today, with numbers you can reproduce, and what is not yet built.

## Requirements

- An NVIDIA GPU and a recent driver
- CUDA 12.x runtime (via CuPy; no separate toolkit needed for the curated ops)
- `cupy-cuda12x` — installed automatically by `start.ps1` / `start.sh` when an
  NVIDIA GPU is detected, or manually with `pip install cupy-cuda12x`

Without a GPU these nodes return a structured "GPU not available" result instead
of failing the graph, so the editor stays usable on any machine.

## The blocks

| Node | What it does |
|---|---|
| **CUDAKernelLab** | Pick a curated GPU op from a dropdown; runs it on the GPU and reports GPU vs CPU timing, speedup, and a correctness check against NumPy. |
| **CUDACustomKernel** | Write your own CUDA C kernel; it is compiled at runtime (NVRTC) and executed on the GPU. Compile errors are reported, not thrown. |
| **GPUCapability** | Reports the GPU name, compute capability, total/free VRAM, and CUDA version. |
| **GPURequirement** | Preflight gate: passes only if the GPU meets a minimum compute capability and VRAM, with a readable reason. |

## Capability matrix

| Capability | Status |
|---|---|
| Run curated CUDA ops on the GPU (CuPy / cuBLAS / cuFFT) | ✅ Real |
| Compile & run custom CUDA C kernels (NVRTC) | ✅ Real |
| Measured GPU-vs-CPU timing + correctness check | ✅ Real |
| GPU capability detection + requirement preflight | ✅ Real |
| float32 and float64 | ✅ Real |
| TensorRT / TensorRT-LLM inference node | ⏳ Planned (Phase 2) |
| Sandboxed custom kernels for untrusted/agent use | ⏳ Planned (Task 1.3) |
| Multi-GPU selection | ⏳ Planned |

## Measured performance

Measured on an **NVIDIA GeForce RTX 4090** (compute 8.9, CUDA 12.x), `float32`,
input size `2^20` (≈1.05M elements), GPU time via CUDA events vs a single-thread
NumPy baseline. **These are illustrative, not formal benchmarks** — speedup
depends heavily on size, dtype, and the CPU baseline. All results are checked for
correctness against NumPy.

| Op | Implementation | Speedup vs NumPy |
|---|---|---|
| mandelbrot | RawKernel (CUDA C) | ~1793× |
| fft | CuPy (cuFFT) | ~212× |
| grayscale | RawKernel (CUDA C) | ~101× |
| sobel_edges | CuPy | ~38× |
| elementwise_mul | RawKernel (CUDA C) | ~32× |
| matmul | CuPy (cuBLAS) | ~29× |
| softmax | CuPy | ~23× |
| saxpy | RawKernel (CUDA C) | ~16× |
| gaussian_blur | CuPy | ~15× |
| monte_carlo_pi | CuPy | ~13× |
| vector_normalize | CuPy | ~5.5× |
| vector_add | RawKernel (CUDA C) | ~5× |
| dot_product | CuPy | ~1× |

`dot_product` is included deliberately: a single small reduction is roughly
CPU-competitive once host↔device overhead is accounted for. The GPU wins big on
compute-heavy and data-parallel work (mandelbrot, FFT, image ops, GEMM), not on
trivial reductions. We show the honest number rather than hide it.

## Writing a custom kernel

`CUDACustomKernel` supports two kernel signatures, selected by the `signature`
dropdown:

- **map** — `(const T* in, T* out, int n)`
- **binary** — `(const T* a, const T* b, T* out, int n)`

The node generates seeded input arrays, launches your kernel, and reports timing.
Example (the default `map` kernel):

```cuda
extern "C" __global__
void user_kernel(const float* in, float* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) out[i] = in[i] * 2.0f + 1.0f;
}
```

A compile error (bad CUDA C) is returned as `report.compiled = false` with the
NVRTC log, so the graph never crashes.

> Custom kernels currently run **directly** on the host process. That is fine for
> your own kernels locally, but arbitrary kernel code is not yet sandboxed — see
> Task 1.3 for the planned Docker + GPU-passthrough isolation that will make this
> safe for agent-authored kernels.

## Capability detection & preflight

`GPUCapability` reports structured device info:

```
available: true
name: NVIDIA GeForce RTX 4090
compute_capability: 8.9
vram_total_gb: 23.99
vram_free_gb: 22.45
cuda_version: 12.x
```

`GPURequirement` turns that into a gate. Inputs `min_compute` and `min_vram_gb`;
outputs `ok` (Bool) and a `reason`:

- `min_compute 8.0, min_vram_gb 16` → `OK: NVIDIA GeForce RTX 4090 (compute 8.9, 23.99 GB)`
- `min_compute 9.0` → `GPU does not meet requirements: compute 8.9 < required 9.0`
- `min_vram_gb 48` → `GPU does not meet requirements: VRAM 23.99 GB < required 48.0 GB`

Wire `GPURequirement` ahead of GPU work to fail fast with a clear message on
machines that cannot run it.

## Try it

- Open the **NVIDIA CUDA Lab** template (`templates/nvidia-cuda-lab.json`), or add
  a **CUDAKernelLab** node, pick an op, and press Cook.
- Run from the CLI: `blacknode run templates/nvidia-cuda-lab.json`.
