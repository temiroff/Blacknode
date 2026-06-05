import sys
import traceback

try:
    import cupy as cp
    import cutlass_cppgen as cutlass

    print("cutlass", cutlass.__version__, "| cc", cutlass.device_cc(), "| nvcc", cutlass.nvcc_version())

    M = N = K = 512
    A = cp.random.random((M, K), dtype=cp.float32).astype(cp.float16)
    B = cp.random.random((K, N), dtype=cp.float32).astype(cp.float16)
    C = cp.zeros((M, N), dtype=cp.float16)
    D = cp.zeros((M, N), dtype=cp.float16)

    plan = cutlass.op.Gemm(element=cp.float16, layout=cutlass.LayoutType.RowMajor)
    plan.run(A, B, C, D)
    cp.cuda.Stream.null.synchronize()

    ref = A.astype(cp.float32) @ B.astype(cp.float32)
    diff = cp.abs(D.astype(cp.float32) - ref)
    abs_err = float(cp.max(diff))
    # fp16 output at K=512 has output magnitudes ~150, where the fp16 ULP is
    # ~0.07; absolute error is dominated by output rounding, so correctness is
    # judged by relative error (must track fp16's ~0.1% precision), not abs.
    rel_err = float(cp.max(diff / cp.abs(ref)))
    print(f"CUTLASS GEMM OK -> max abs diff {abs_err:.4f} | max rel diff {rel_err:.5f}")
    print("RESULT: SUCCESS" if rel_err < 0.01 else "RESULT: WRONG")
except Exception as e:
    print("RESULT: FAILED", type(e).__name__, str(e)[:300])
    traceback.print_exc()
    sys.exit(1)
