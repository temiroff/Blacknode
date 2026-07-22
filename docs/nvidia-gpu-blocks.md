# NVIDIA GPU Blocks

Blacknode runs **real CUDA work on a local NVIDIA GPU** through
[CuPy](https://cupy.dev/). These are not planning or mock nodes — they compile
and execute on the device and report measured timings. This page documents what
is real today, with numbers you can reproduce, and what is not yet built.

These nodes ship in the
[blacknode-cuda](https://github.com/temiroff/blacknode-cuda)
[extension package](packages.md). Install it with
`blacknode packages install https://github.com/temiroff/blacknode-cuda`
(or clone it into `packages/`). Its nodes appear under the **NVIDIA CUDA**
palette group and its templates load from the Templates tab like any
built-in.

## Requirements

- An NVIDIA GPU and a recent driver
- CUDA 12.x runtime and toolkit headers for CuPy kernels
- `cupy-cuda12x[ctk]` — installed automatically by `start.ps1` / `start.sh`
  when an NVIDIA GPU is detected, or manually with `pip install 'cupy-cuda12x[ctk]'`

Without a GPU these nodes return a structured "GPU not available" result instead
of failing the graph, so the editor stays usable on any machine.

## The blocks

| Node | What it does |
|---|---|
| **CUDAKernelLab** | Pick a curated GPU op from a dropdown; runs it on the GPU and reports GPU vs CPU timing, speedup, and a correctness check against NumPy. |
| **CUDACustomKernel** | Write your own CUDA C kernel; it is compiled at runtime with NVRTC through CuPy `RawKernel` and executed on the local NVIDIA GPU. Compile and launch errors are returned as node results. |
| **CUDAImageFilter** | Apply curated GPU image filters such as grayscale, blur, sharpen, sobel edges, and invert to an `Image` input. |
| **TensorCoreGEMM** | Hand-written WMMA fp16 GEMM (Tensor Cores) compiled with NVRTC, timed against cuBLAS with a TFLOPS report. |
| **CUTLASSGemm** | The NVIDIA-library sibling of TensorCoreGEMM: an fp16 GEMM run through `nvidia-cutlass` in a long-running Docker GPU worker, timed against cuBLAS. Same ports, so the two are drop-in comparable. |
| **CUTLASS** | Generic CUTLASS GEMM block routed by its input: an image runs a convolution (im2col GEMM), two matrices run `A·B`, nothing runs a synthetic benchmark. All compute lives in the Docker worker. |
| **GPUCapability** | Reports the GPU name, compute capability, total/free VRAM, and CUDA version. |
| **GPURequirement** | Preflight gate: passes only if the GPU meets a minimum compute capability and VRAM, with a readable reason. |
| **LoadImage** | Loads a file path or browser-selected image into the graph as an `Image` data URL. `max_size = 0` preserves the original dimensions; set `max_size` only when you want downscaling. |
| **OutputImage** | Displays an `Image` value on the canvas and lets downstream nodes keep receiving the same image data. |

## Capability matrix

| Capability | Status |
|---|---|
| Run curated CUDA ops on the GPU (CuPy / cuBLAS / cuFFT) | ✅ Real |
| Compile & run custom CUDA C kernels (NVRTC) | ✅ Real |
| Hand-written WMMA Tensor Core GEMM vs cuBLAS (TensorCoreGEMM) | ✅ Real |
| CUTLASS-library GEMM in a containerized GPU worker (CUTLASSGemm / CUTLASS) | ✅ Real (needs Docker + NVIDIA Container Toolkit) |
| Measured GPU-vs-CPU timing + correctness check | ✅ Real |
| GPU capability detection + requirement preflight | ✅ Real |
| Browser image loading, drag/drop, node preview, and image copy | ✅ Real |
| Image nodes connected to CUDA image filters and custom kernels | ✅ Real |
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

## Image Workflows

Images move through Blacknode as PNG data URLs, so they are JSON-safe, can be
stored in workflow state, and render directly on nodes and in the Inspector.
The most common visual GPU graph is:

```text
LoadImage.image -> CUDACustomKernel.input -> OutputImage.image
LoadImage.image -> CUDAImageFilter.image  -> OutputImage.image
```

![Blacknode CUDA custom kernel image workflow](images/blacknode-cuda-custom-kernels.jpg)

`LoadImage` accepts an image file path, a data URL, the on-node Browse button,
or an image dropped onto the node. Dropping an image onto an empty canvas creates
a `LoadImage` node with that image loaded. The node reports `width`, `height`,
and `report` metadata including original dimensions and whether resizing
occurred.

By default `max_size` is `0`, which means "preserve the original size". Older
saved graphs that had the old `768` default are migrated to `0` when loaded.
Set `max_size` manually when you want to downscale before CUDA work.

`OutputImage` is a display and pass-through node: it shows the image result on
the canvas and exposes the same `image` value for any downstream connection.

## Real GPU Path For Images

For image custom kernels, the GPU path is:

1. `LoadImage` decodes the source image on the CPU into a float32 `HxWx3` array
   in `[0, 1]`.
2. `CUDACustomKernel` copies that array to the GPU with CuPy.
3. CuPy compiles the CUDA C source at runtime with NVRTC through `RawKernel`.
4. The kernel launches on the local NVIDIA GPU.
5. The result is copied back to CPU memory and encoded as a PNG data URL for
   preview, output, and graph propagation.

There is no silent CPU fallback for `CUDACustomKernel`. If CuPy, the CUDA
device, compilation, or launch fails, the node returns an error in `report`
instead of pretending the work ran on CPU. The CPU parts are image decode,
image encode, and host-device transfer.

Successful runs expose proof in the node result:

```text
report.compiled: true
report.device: NVIDIA GeForce RTX 4090
report.compute_capability: 8.9
report.signature: image_rgb
report.gpu_ms: <CUDA event timing>
```

The first launch may include runtime compilation cost. `gpu_ms` is measured with
CUDA events around repeated kernel launches after the first compile/launch pass.

## Writing a custom kernel

`CUDACustomKernel` accepts `Any` input and returns `Any` output. It can run
synthetic numeric inputs, connected numeric data, dictionaries, or connected
images.

Use the `template` dropdown for quick experiments:

- `image_invert` - default RGB invert image kernel.
- `cinematic_teal_orange` - contrast, teal/orange grade, and vignette.
- `neon_edge_glow_2d` - 2D edge sampling with cyan/orange glow and vignette.
- `comic_ink_2d` - 2D neighbor edges plus posterized ink shading.
- `thermal_vision` - luminance remapped into a hot/cold false-color palette.
- `dream_glow_2d` - 2D neighbor blur mixed into a soft color glow.
- `grayscale` - luminance grayscale.
- `channel_swap` - swaps red and blue channels.
- `vignette` - coordinate-based darkening from center to corners.
- `custom` - use whatever is in the `code` field.

Selecting a built-in template also fills the code editor and adjusts
`signature` / `output_mode` for that template. Editing or pasting into `code`
switches the node back to `custom`, so templates are a starting point rather
than a lock-in.

Set `signature` manually or leave it at `auto`:

- **auto** - detects images, binary dicts, and numeric arrays.
- **map** - `(const T* in, T* out, int n)`
- **binary** - `(const T* a, const T* b, T* out, int n)`
- **image_rgb** - `(const float* in, float* out, int width, int height, int channels)`

The default custom kernel is an image RGB invert kernel, so a fresh
`CUDACustomKernel` can be connected directly to `LoadImage.image`:

```cuda
extern "C" __global__
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
}
```

Image kernels can be written in either 1D or 2D style.

```cuda
// 1D launch: one linear pixel id per thread.
int i = blockDim.x * blockIdx.x + threadIdx.x;
int x = i % width;
int y = i / width;

// 2D launch: x/y come directly from the CUDA grid.
int x = blockDim.x * blockIdx.x + threadIdx.x;
int y = blockDim.y * blockIdx.y + threadIdx.y;
int i = y * width + x;
```

The 1D form launches as `grid=(ceil(width * height / block),)`,
`block=(block,)`. It is compact and works well for per-pixel color transforms.
The 2D form launches as `grid=(ceil(width / block_x), ceil(height / block_y))`,
`block=(block_x, block_y)`. It is easier to read for neighbor sampling,
convolutions, edge detection, and anything that thinks in image coordinates.
`CUDACustomKernel` marks built-in 2D templates explicitly and also auto-detects
custom pasted code that references `threadIdx.y`, `blockIdx.y`, or `blockDim.y`.
The run report includes `launch`, `grid`, and `block`, so you can see which path
was used.

For numeric work, switch the code and signature to `map` or `binary`. Those
numeric signatures are still supported for custom pasted code; the template
dropdown is image-focused so visual tests produce visible output. The node
generates seeded input arrays when nothing is connected, or adapts connected
inputs:

- A list or array-like value becomes a `map` input.
- A dict with `a` and `b` becomes a `binary` input.
- A dict with `data` plus optional `shape` becomes a shaped numeric input.
- An image data URL becomes an `image_rgb` input.

The node validates the CUDA function shape before launch. If the selected
signature does not match the function arguments, it returns a clear signature
mismatch error instead of launching unsafe arguments.

Compile errors and launch errors are returned as `report.compiled = false` with
the NVRTC or CUDA error text, so the graph reports the failure instead of hiding
it.

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

## CUTLASS GEMM (containerized)

`TensorCoreGEMM` and the CUTLASS nodes are siblings: both run an fp16
Tensor-Core GEMM and time it against cuBLAS, but `TensorCoreGEMM` is a
hand-written WMMA kernel compiled on the host with NVRTC, while `CUTLASSGemm`
and `CUTLASS` use NVIDIA's **CUTLASS** library. Wire both with the same ports to
compare a hand-rolled kernel against the vendor library on identical inputs.

CUTLASS's JIT costs ~18 s per process, which is unusable for an interactive
graph. So the CUTLASS nodes do **not** run in the editor server: they talk to a
long-running Docker worker (`blacknode-cutlass`) that holds a warm CUTLASS plan
and streams JSON requests over stdin/stdout. The first call pays a one-time
container start (~9–20 s, dropping after the JIT cache warms on a host volume);
repeat GEMMs then run at GPU speed (~1 ms). The editor-server Python (3.11) needs
no `cupy`/`cutlass` — all GPU work lives in the container, reached through the
`docker` CLI. Every failure surfaces as a structured node error, never a crash.

**Requirements:** Docker, the NVIDIA Container Toolkit, and the worker image.
Build it once from `docker/cutlass/`:

```bash
docker build -t blacknode-cutlass:latest docker/cutlass/
```

The generic **CUTLASS** node has one input port (`op = auto`) and routes by what
you connect:

- an **image** → 3×3 convolution as an im2col GEMM (`filter` picks the kernel;
  `iterations` stacks it deep; `filters > 1` runs a random conv layer for heavy
  compute) → returns the filtered image
- **two matrices** (`{"a": …, "b": …}`, or a lone matrix → `A·Aᵀ`) → returns `A·B`
- **nothing** → a synthetic benchmark at `size` (or a timed burn with `seconds`)

Templates: `packages/blacknode-cuda/templates/cutlass-image-showcase.json` (convolution path) and
`packages/blacknode-cuda/templates/cutlass-gpu-burn.json` (sustained benchmark). The `scripts/_cutlass_*.py`
helpers drive the worker directly for benchmarking and container smoke tests.

## Try it

- Open the **NVIDIA CUDA Lab** template (`packages/blacknode-cuda/templates/nvidia-cuda-lab.json`), or add
  a **CUDAKernelLab** node, pick an op, and press Cook.
- For an image test, add **LoadImage**, **CUDACustomKernel**, and
  **OutputImage**. Load or drop an image onto `LoadImage`, connect
  `LoadImage.image -> CUDACustomKernel.input`, connect
  `CUDACustomKernel.output -> OutputImage.image`, then cook the output image.
- For curated image filters, use **CUDAImageFilter** between **LoadImage** and
  **OutputImage** and choose `grayscale`, `invert`, `gaussian_blur`,
  `sharpen`, or `sobel_edges`.
- Run from the CLI: `blacknode run packages/blacknode-cuda/templates/nvidia-cuda-lab.json`.
