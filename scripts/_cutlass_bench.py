import json
import time
import warnings

warnings.filterwarnings("ignore")

t0 = time.perf_counter()
import cupy as cp
import cutlass_cppgen as cutlass

t_import = time.perf_counter()

M = N = K = 512
cp.random.seed(0)
A = cp.random.random((M, K)).astype(cp.float16)
B = cp.random.random((K, N)).astype(cp.float16)
C = cp.zeros((M, N), dtype=cp.float16)
D = cp.zeros((M, N), dtype=cp.float16)

plan = cutlass.op.Gemm(element=cp.float16, layout=cutlass.LayoutType.RowMajor)

# First run pays the CUTLASS JIT emit+compile.
plan.run(A, B, C, D)
cp.cuda.Stream.null.synchronize()
t_jit = time.perf_counter()

# Warm runs: plan + kernel already compiled and cached in-process.
warm = []
for _ in range(30):
    s = time.perf_counter()
    plan.run(A, B, C, D)
    cp.cuda.Stream.null.synchronize()
    warm.append((time.perf_counter() - s) * 1000.0)

warm.sort()
result = {
    "import_s": round(t_import - t0, 3),
    "jit_first_s": round(t_jit - t_import, 3),
    "warm_median_ms": round(warm[len(warm) // 2], 3),
    "warm_min_ms": round(warm[0], 3),
    "in_container_total_s": round(time.perf_counter() - t0, 3),
}
print("BENCH " + json.dumps(result))
