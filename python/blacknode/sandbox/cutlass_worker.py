"""Host-side manager for the long-running CUTLASS GEMM worker container.

The CUTLASS JIT costs ~18s per process, so a `docker run` per call is unusable
in an interactive graph (~20s/call). Instead we start ONE container, keep it
alive, and stream JSON requests to it over stdin/stdout — repeat GEMMs then run
at GPU speed (~1ms). The JIT cache is persisted on a host volume so even the
worker's one-time startup drops from ~20s to ~9s after the first launch.

This module talks to the `docker` CLI via subprocess only: the editor server
(Python 3.11) needs no cupy/cutlass/docker-SDK — all GPU work lives in the
container. Every failure surfaces as CutlassWorkerError; nodes turn that into a
structured error so the editor never crashes.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_IMAGE = "blacknode-cutlass:latest"
STARTUP_TIMEOUT_SECONDS = 90      # cold start pays the CUTLASS JIT (~18s) + container start
REQUEST_TIMEOUT_SECONDS = 60
_CACHE_ENV = "BLACKNODE_CUTLASS_CACHE"


class CutlassWorkerError(RuntimeError):
    """Any failure starting or talking to the CUTLASS worker container."""


def _image() -> str:
    return os.environ.get("BLACKNODE_CUTLASS_IMAGE", DEFAULT_IMAGE)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cache_dir() -> Path:
    raw = os.environ.get(_CACHE_ENV)
    path = Path(raw) if raw else _repo_root() / ".cutlass-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _docker_cli() -> str:
    return os.environ.get("BLACKNODE_DOCKER", "docker")


class CutlassWorker:
    """One persistent worker container, reused across requests."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self.info: dict[str, Any] = {}
        self.startup_ms: float = 0.0

    # -- lifecycle ----------------------------------------------------------
    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _ensure_image(self) -> None:
        cli = _docker_cli()
        try:
            inspect = subprocess.run(
                [cli, "image", "inspect", _image()],
                capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError as exc:
            raise CutlassWorkerError(
                "the 'docker' CLI was not found; install Docker Desktop to use the CUTLASS node"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise CutlassWorkerError(f"could not query Docker ({type(exc).__name__}: {exc})") from exc
        if inspect.returncode == 0:
            return
        raise CutlassWorkerError(
            f"CUTLASS image '{_image()}' is not built. Build it with: "
            f"docker build -f docker/cutlass/Dockerfile -t {_image()} docker/cutlass"
        )

    def _start(self) -> None:
        self._ensure_image()
        cache = _cache_dir()
        cmd = [
            _docker_cli(), "run", "--rm", "-i", "--gpus", "all",
            "-v", f"{cache}:/workspace", "-w", "/workspace",
            _image(),
        ]
        t0 = time.perf_counter()
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1,
            )
        except FileNotFoundError as exc:
            raise CutlassWorkerError(
                "the 'docker' CLI was not found; install Docker Desktop to use the CUTLASS node"
            ) from exc

        ready = self._read_json(proc, STARTUP_TIMEOUT_SECONDS, phase="startup")
        if not ready.get("ready") or not ready.get("ok"):
            self._terminate(proc)
            raise CutlassWorkerError(f"worker failed to start: {ready.get('error', ready)}")
        self._proc = proc
        self.info = ready
        self.startup_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    @staticmethod
    def _read_json(proc: subprocess.Popen[str], timeout: float, *, phase: str) -> dict[str, Any]:
        """Read the next JSON response line, enforcing a timeout via a reader thread.

        The nvidia/cuda base image prints a CUDA license banner to stdout at
        startup, so lines that aren't a JSON object (don't start with '{') are
        skipped until the worker's real JSON arrives.
        """
        box: list[Any] = [None]

        def _reader() -> None:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.strip()
                if line.startswith("{"):
                    box[0] = line
                    return
            box[0] = ""  # stream closed without a JSON line

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            raise CutlassWorkerError(f"timed out after {timeout}s waiting for worker ({phase})")
        line = box[0]
        if not line:
            stderr = _drain(proc.stderr)
            raise CutlassWorkerError(f"worker produced no output ({phase}); stderr: {stderr[:500]}")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise CutlassWorkerError(f"worker sent invalid JSON ({phase}): {line[:200]}") from exc

    @staticmethod
    def _terminate(proc: subprocess.Popen[str] | None) -> None:
        if proc is None:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        with self._lock:
            if self._proc is not None:
                try:
                    if self._proc.stdin and not self._proc.stdin.closed:
                        self._proc.stdin.write(json.dumps({"op": "quit"}) + "\n")
                        self._proc.stdin.flush()
                except Exception:  # noqa: BLE001
                    pass
                self._terminate(self._proc)
                self._proc = None

    # -- requests -----------------------------------------------------------
    def request(self, payload: dict[str, Any], timeout: float = REQUEST_TIMEOUT_SECONDS) -> dict[str, Any]:
        with self._lock:
            if not self._alive():
                self._start()
            proc = self._proc
            assert proc is not None and proc.stdin is not None
            try:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
            except Exception as exc:  # noqa: BLE001 - broken pipe => worker died
                self._terminate(proc)
                self._proc = None
                raise CutlassWorkerError(f"worker pipe broke: {type(exc).__name__}: {exc}") from exc
            return self._read_json(proc, timeout, phase=str(payload.get("op", "request")))


def _drain(stream: Any) -> str:
    if stream is None:
        return ""
    try:
        return stream.read() or ""
    except Exception:  # noqa: BLE001
        return ""


_WORKER: CutlassWorker | None = None
_WORKER_LOCK = threading.Lock()


def get_worker() -> CutlassWorker:
    """Return the process-wide singleton worker (lazily created)."""
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None:
            _WORKER = CutlassWorker()
        return _WORKER


def _run(payload: dict[str, Any], timeout: float = REQUEST_TIMEOUT_SECONDS) -> dict[str, Any]:
    worker = get_worker()
    result = worker.request(payload, timeout)
    if not result.get("ok"):
        raise CutlassWorkerError(str(result.get("error") or "worker reported failure"))
    result.setdefault("startup_ms", worker.startup_ms)
    return result


def gemm(n: int, seed: int) -> dict[str, Any]:
    """Synthetic benchmark GEMM (compare vs cuBLAS). Raises CutlassWorkerError."""
    return _run({"op": "gemm", "n": int(n), "seed": int(seed)})


def benchmark(n: int, seed: int = 0, seconds: float = 0.0, iterations: int = 30) -> dict[str, Any]:
    """Benchmark GEMM. With seconds>0 it burns the GPU for ~that long at a
    sustained N x N GEMM and reports sustained TFLOPS; otherwise it times one
    GEMM and compares to cuBLAS."""
    payload: dict[str, Any] = {"op": "benchmark", "n": int(n), "seed": int(seed),
                               "iterations": int(iterations)}
    if seconds and seconds > 0:
        payload["seconds"] = float(seconds)
    return _run(payload, timeout=max(REQUEST_TIMEOUT_SECONDS, float(seconds) + 30.0))


def _encode_array(arr: Any) -> dict[str, Any]:
    import base64
    import numpy as np

    arr = np.ascontiguousarray(arr)
    return {"b64": base64.b64encode(arr.tobytes()).decode("ascii"),
            "shape": list(arr.shape), "dtype": str(arr.dtype)}


def _decode_array(payload: dict[str, Any]) -> Any:
    import base64
    import numpy as np

    raw = base64.b64decode(payload["b64"])
    return np.frombuffer(raw, dtype=np.dtype(payload["dtype"])).reshape(payload["shape"])


def matmul(a: Any, b: Any) -> dict[str, Any]:
    """A.B as a CUTLASS GEMM. a, b are numpy 2-D arrays. Result array is in ['out']."""
    r = _run({"op": "matmul", "a": _encode_array(a), "b": _encode_array(b)})
    r["out"] = _decode_array(r["out"])
    return r


def conv2d(image_hwc: Any, kernel: Any, norm: float = 1.0,
           iterations: int = 1, filters: int = 1, seed: int = 0,
           timeout: float = REQUEST_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Convolve an HxWxC image via im2col + CUTLASS GEMM.

    image_hwc is a numpy float array (values ~0..1); kernel is a k x k list/array.
    iterations stacks the conv block (deep), filters>1 runs a random conv LAYER
    (a CNN forward pass) instead of the single named filter. The result image is
    in ['out']. A longer timeout is allowed because heavy stacks are the point.
    """
    import numpy as np

    r = _run({"op": "conv2d", "image": _encode_array(np.asarray(image_hwc, dtype=np.float32)),
              "kernel": np.asarray(kernel, dtype=np.float32).tolist(), "norm": float(norm),
              "iterations": int(iterations), "filters": int(filters), "seed": int(seed)},
             timeout=timeout)
    r["out"] = _decode_array(r["out"])
    return r
