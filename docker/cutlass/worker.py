"""Long-running CUTLASS worker (runs inside the blacknode-cutlass container).

One generic GEMM engine, several ops. The CUTLASS plan + JIT kernel compile
once on the first GEMM and are reused, so repeat requests run at GPU speed
(~1ms) instead of paying the ~18s JIT every call. See
.local-notes/cutlass-container-feasibility-plan.md for the measurements.

Protocol: one JSON request per line on stdin, one JSON response per line on
stdout. Array payloads travel as {"b64","shape","dtype"} (base64 of raw bytes),
so the host owns image/codec concerns and the worker only does GPU math.

Requests:
    {"op": "ping"}                                  -> {"ok": true, "pong": true}
    {"op": "gemm",   "n": 512, "seed": 0}           -> synthetic benchmark + timings
    {"op": "matmul", "a": <arr>, "b": <arr>}        -> A.B as a CUTLASS GEMM
    {"op": "conv2d", "image": <arr HxWxC>,          -> filter applied as im2col + GEMM
                     "kernel": [[...]], "norm": 1.0}
    {"op": "quit"}                                  -> exits

Every failure is reported as {"ok": false, "error": "..."} instead of crashing.
"""
import base64
import json
import sys
import warnings

warnings.filterwarnings("ignore")


def _emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    try:
        import numpy as np
        import cupy as cp
        import cutlass_cppgen as cutlass
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "ready": False, "error": f"import failed: {type(exc).__name__}: {exc}"})
        return

    try:
        props = cp.cuda.runtime.getDeviceProperties(0)
        device = props["name"].decode() if isinstance(props["name"], bytes) else props["name"]
        cc = f"{props['major']}.{props['minor']}"
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "ready": False, "error": f"no CUDA device: {type(exc).__name__}: {exc}"})
        return

    # fp16 in/out, fp32 ACCUMULATE (Tensor Cores' native accumulator). fp16
    # accumulation drifts badly at large K; fp32 keeps rel_err ~1e-4 and matches
    # the WMMA node. One plan, reused for every request (kernel cached on disk).
    plan = cutlass.op.Gemm(
        element=cp.float16,
        element_accumulator=cp.float32,
        layout=cutlass.LayoutType.RowMajor,
    )

    def _decode(arr):
        raw = base64.b64decode(arr["b64"])
        return np.frombuffer(raw, dtype=np.dtype(arr["dtype"])).reshape(arr["shape"])

    def _encode(host):
        host = np.ascontiguousarray(host)
        return {"b64": base64.b64encode(host.tobytes()).decode("ascii"),
                "shape": list(host.shape), "dtype": str(host.dtype)}

    def _gemm_fp16(A, B):
        """Run D = A.B on the GPU through the cached CUTLASS plan. A,B are cupy
        fp16, row-major. CUTLASS tensor-core fp16 needs the contiguous dims (K,
        N) aligned to a multiple of 8, so K and N are zero-padded up and the
        result sliced back. Returns (D fp16 of shape (M,N), ms for one run)."""
        M, K = A.shape
        N = B.shape[1]
        Kp = ((K + 7) // 8) * 8
        Np = ((N + 7) // 8) * 8
        if Kp != K or Np != N:
            Ap = cp.zeros((M, Kp), dtype=cp.float16); Ap[:, :K] = A
            Bp = cp.zeros((Kp, Np), dtype=cp.float16); Bp[:K, :N] = B
        else:
            Ap, Bp = A, B
        C = cp.zeros((M, Np), dtype=cp.float16)
        D = cp.zeros((M, Np), dtype=cp.float16)
        ev0, ev1 = cp.cuda.Event(), cp.cuda.Event()
        plan.run(Ap, Bp, C, D)  # warm-up / JIT on first shape
        cp.cuda.Stream.null.synchronize()
        ev0.record()
        plan.run(Ap, Bp, C, D)
        ev1.record()
        ev1.synchronize()
        return D[:, :N], cp.cuda.get_elapsed_time(ev0, ev1)

    # -- ops ---------------------------------------------------------------
    def _benchmark(req):
        import time as _time_mod
        n = max(16, (int(req.get("n", 512)) // 16) * 16)
        cp.random.seed(int(req.get("seed", 0)))
        A = cp.random.random((n, n), dtype=cp.float32).astype(cp.float16)
        B = cp.random.random((n, n), dtype=cp.float32).astype(cp.float16)
        C = cp.zeros((n, n), dtype=cp.float16); D = cp.zeros((n, n), dtype=cp.float16)
        cublas_out = cp.empty((n, n), dtype=cp.float16)

        def _time(fn, iters):
            ev0, ev1 = cp.cuda.Event(), cp.cuda.Event()
            fn(); cp.cuda.Stream.null.synchronize()
            ev0.record()
            for _ in range(iters):
                fn()
            ev1.record(); ev1.synchronize()
            return cp.cuda.get_elapsed_time(ev0, ev1) / iters

        flop = 2.0 * n * n * n

        # If a duration is requested, keep firing CUTLASS GEMMs back-to-back
        # until ~seconds have elapsed -- a real GPU burn at sustained TFLOPS.
        seconds = float(req.get("seconds", 0) or 0)
        if seconds > 0:
            plan.run(A, B, C, D); cp.cuda.Stream.null.synchronize()  # warm/JIT
            passes = 0
            ev0, ev1 = cp.cuda.Event(), cp.cuda.Event()
            ev0.record()
            wall0 = _time_mod.perf_counter()
            while _time_mod.perf_counter() - wall0 < seconds:
                for _ in range(20):
                    plan.run(A, B, C, D)
                passes += 20
                cp.cuda.Stream.null.synchronize()
            ev1.record(); ev1.synchronize()
            gpu_ms = cp.cuda.get_elapsed_time(ev0, ev1)
            sustained = (flop * passes) / (gpu_ms * 1e9)  # gpu_ms is ms -> TFLOPS
            return {"ok": True, "op": "benchmark", "mode": "burn", "n": n, "dtype": "float16",
                    "passes": passes, "total_flop_T": round(flop * passes / 1e12, 1),
                    "gpu_ms": round(gpu_ms, 1), "cutlass_tflops": round(sustained, 1),
                    "cutlass_ms": round(gpu_ms / passes, 4), "cublas_tflops": 0.0, "cublas_ms": 0.0,
                    "rel_err": 0.0, "correct": True,
                    "device": device, "compute_capability": cc}

        iters = max(1, int(req.get("iterations", 30)))
        cutlass_ms = _time(lambda: plan.run(A, B, C, D), iters)
        cublas_ms = _time(lambda: cp.matmul(A, B, out=cublas_out), iters)
        ref = A.astype(cp.float32) @ B.astype(cp.float32)
        rel = float(cp.max(cp.abs(D.astype(cp.float32) - ref)) / cp.max(cp.abs(ref)))
        return {"ok": True, "op": "benchmark", "mode": "compare", "n": n, "dtype": "float16",
                "cutlass_ms": round(cutlass_ms, 4),
                "cutlass_tflops": round(flop / (cutlass_ms * 1e9), 2) if cutlass_ms > 0 else 0.0,
                "cublas_ms": round(cublas_ms, 4),
                "cublas_tflops": round(flop / (cublas_ms * 1e9), 2) if cublas_ms > 0 else 0.0,
                "rel_err": round(rel, 8), "correct": rel < 1e-2,
                "device": device, "compute_capability": cc}

    def _matmul(req):
        a = cp.asarray(_decode(req["a"]).astype(np.float16))
        b = cp.asarray(_decode(req["b"]).astype(np.float16))
        if a.ndim != 2 or b.ndim != 2 or a.shape[1] != b.shape[0]:
            return {"ok": False, "error": f"matmul shape mismatch: {a.shape} . {b.shape}"}
        D, ms = _gemm_fp16(a, b)
        ref = a.astype(cp.float32) @ b.astype(cp.float32)
        rel = float(cp.max(cp.abs(D.astype(cp.float32) - ref)) / (cp.max(cp.abs(ref)) + 1e-12))
        M, K = a.shape; N = b.shape[1]
        flop = 2.0 * M * K * N
        return {"ok": True, "op": "matmul", "out": _encode(cp.asnumpy(D)),
                "M": M, "K": K, "N": N, "gpu_ms": round(ms, 4),
                "tflops": round(flop / (ms * 1e9), 2) if ms > 0 else 0.0,
                "rel_err": round(rel, 8), "correct": rel < 1e-2,
                "device": device, "compute_capability": cc}

    def _im2col_depthwise(g, H, W, C, k):
        """(C*H*W, k*k): one row per (channel, pixel) k x k neighbourhood."""
        pad = k // 2
        gp = cp.pad(g, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
        patches = cp.empty((C * H * W, k * k), dtype=cp.float16)
        col = 0
        for di in range(k):
            for dj in range(k):
                window = gp[di:di + H, dj:dj + W, :]
                patches[:, col] = window.transpose(2, 0, 1).reshape(-1).astype(cp.float16)
                col += 1
        return patches

    def _im2col_full(g, H, W, C, k):
        """(H*W, k*k*C): one row per pixel, columns = full k x k x C neighbourhood
        (a real conv-layer unfold across input channels)."""
        pad = k // 2
        gp = cp.pad(g, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
        cols = []
        for di in range(k):
            for dj in range(k):
                cols.append(gp[di:di + H, dj:dj + W, :].reshape(H * W, C))
        return cp.concatenate(cols, axis=1).astype(cp.float16)  # (H*W, k*k*C)

    def _conv2d(req):
        """Convolution as CUTLASS GEMM (im2col), with two scaling knobs so it
        spans from a single instant filter to a minute of real conv-net compute:

          filters == 1 : depthwise named filter (edge/emboss/...), one
                         (C*H*W, k*k).(k*k, 1) GEMM. The cheap, recognisable path.
          filters  > 1 : a real conv LAYER -- unfold k*k*C neighbourhoods and
                         GEMM against a random bank of F filters (H*W, k*k*C).(.,F),
                         ReLU, then project F->3 with a second GEMM. This is a CNN
                         forward pass with random weights: heavy and visual.

        `iterations` repeats the block, feeding the output back in (a deep stack),
        so total work = iterations x (one or two GEMMs). Everything is timed and
        the aggregate TFLOPS reported."""
        img = _decode(req["image"]).astype(np.float32)
        if img.ndim == 2:
            img = img[:, :, None]
        H, W, C = img.shape
        kernel = np.asarray(req["kernel"], dtype=np.float32)
        k = kernel.shape[0]
        norm = float(req.get("norm", 1.0)) or 1.0
        iterations = max(1, min(2000, int(req.get("iterations", 1))))
        filters = max(1, min(512, int(req.get("filters", 1))))
        seed = int(req.get("seed", 0))

        g = cp.asarray(img)
        total_ms = 0.0
        total_flop = 0.0
        gemms = 0

        if filters == 1:
            kvec = cp.asarray((kernel.reshape(k * k, 1) / norm).astype(np.float16))
            for _ in range(iterations):
                patches = _im2col_depthwise(g, H, W, C, k)         # (C*H*W, k*k)
                D, ms = _gemm_fp16(patches, kvec)                  # (C*H*W, 1)
                g = cp.clip(D.astype(cp.float32).reshape(C, H, W).transpose(1, 2, 0), 0.0, 1.0)
                total_ms += ms; total_flop += 2.0 * (C * H * W) * (k * k); gemms += 1
            gemm_dims = [C * H * W, k * k, 1]
        else:
            rng = cp.random.RandomState(seed)
            Kf = k * k * C
            Wbank = (rng.standard_normal((Kf, filters)) / np.sqrt(Kf)).astype(cp.float16)
            Wproj = (rng.standard_normal((filters, 3)) / np.sqrt(filters)).astype(cp.float16)
            for _ in range(iterations):
                patches = _im2col_full(g, H, W, C if C == 3 else C, k)  # (H*W, k*k*C)
                feats, ms1 = _gemm_fp16(patches, Wbank)            # (H*W, F)
                feats = cp.maximum(feats, cp.float16(0))           # ReLU
                rgb, ms2 = _gemm_fp16(feats, Wproj)               # (H*W, 3)
                x = rgb.astype(cp.float32)
                g = (1.0 / (1.0 + cp.exp(-x))).reshape(H, W, 3)   # sigmoid -> [0,1]
                C = 3
                total_ms += ms1 + ms2
                total_flop += 2.0 * (H * W) * Kf * filters + 2.0 * (H * W) * filters * 3
                gemms += 2
            gemm_dims = [H * W, k * k * 3, filters]

        out = np.clip(cp.asnumpy(g).astype(np.float32), 0.0, 1.0)
        return {"ok": True, "op": "conv2d", "out": _encode(out),
                "width": W, "height": H, "channels": int(out.shape[-1]), "ksize": k,
                "iterations": iterations, "filters": filters, "gemms": gemms,
                "M": gemm_dims[0], "K": gemm_dims[1], "N": gemm_dims[2],
                "gpu_ms": round(total_ms, 2),
                "tflops": round(total_flop / (total_ms * 1e9), 2) if total_ms > 0 else 0.0,
                "device": device, "compute_capability": cc}

    _emit({"ok": True, "ready": True, "device": device, "compute_capability": cc,
           "cutlass": cutlass.__version__})

    ops = {"gemm": _benchmark, "benchmark": _benchmark, "matmul": _matmul, "conv2d": _conv2d}

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            _emit({"ok": False, "error": f"bad request json: {exc}"})
            continue
        op = str(req.get("op") or "").strip()
        if op == "quit":
            _emit({"ok": True, "bye": True}); return
        if op == "ping":
            _emit({"ok": True, "pong": True}); continue
        handler = ops.get(op)
        if handler is None:
            _emit({"ok": False, "error": f"unknown op '{op}'"}); continue
        try:
            _emit(handler(req))
        except Exception as exc:  # noqa: BLE001
            _emit({"ok": False, "error": f"{op} failed: {type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()
