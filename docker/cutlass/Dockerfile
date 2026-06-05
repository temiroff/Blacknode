# Production image for the CUTLASSGemm node's long-running GEMM worker.
# Same proven recipe as the feasibility gate (docker/Dockerfile.cutlass-test),
# but bakes the worker in so the container is self-contained.
FROM nvidia/cuda:12.6.2-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# cuda-python is pinned <13: nvidia-cutlass 4.2.0 still reads the deprecated
# `cuda.__version__`, which the 13.x package restructuring removed.
RUN pip3 install --no-cache-dir cupy-cuda12x nvidia-cutlass \
    'cuda-python<13' 'cuda-bindings<13'

COPY worker.py /app/worker.py

# /workspace is the CWD so CUTLASS writes its sqlite JIT cache there; mount a
# host dir over it to persist the cache across container restarts.
WORKDIR /workspace
CMD ["python3", "-u", "/app/worker.py"]
