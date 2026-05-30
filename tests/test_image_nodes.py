"""Image I/O nodes + GPU image filter.

PIL/GPU-dependent checks skip cleanly when Pillow / an NVIDIA GPU is absent.
The "no image" contract always holds.
"""
import os
import tempfile

import pytest

from blacknode.nodes.cuda import IMAGE_FILTERS, cuda_image_filter
from blacknode.nodes.image import load_image, output_image


def _has_pil() -> bool:
    try:
        import PIL  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def _has_gpu() -> bool:
    try:
        import cupy as cp
        cp.cuda.runtime.getDeviceProperties(0)
        return True
    except Exception:
        return False


HAS_PIL = _has_pil()
HAS_GPU = _has_gpu()
pil_only = pytest.mark.skipif(not HAS_PIL, reason="Pillow/NumPy not installed")
gpu_only = pytest.mark.skipif(not (HAS_PIL and HAS_GPU), reason="no Pillow / NVIDIA GPU")


# --- contracts that always hold -------------------------------------------------

def test_cuda_image_filter_no_image_errors():
    r = cuda_image_filter({"op": "grayscale"})
    assert r["image"] == ""
    assert "error" in r["report"]


def test_output_image_passthrough():
    url = "data:image/png;base64,AAAA"
    assert output_image({"image": url})["image"] == url


def test_load_image_missing_path():
    r = load_image({"path": ""})
    assert r["image"] == ""
    assert "error" in r["report"]


# --- with Pillow ----------------------------------------------------------------

@pil_only
def test_encode_decode_roundtrip():
    import numpy as np
    from blacknode.nodes.image import decode_image, encode_image
    arr = np.zeros((8, 12, 3), dtype=np.float32)
    arr[:, :, 0] = 1.0
    url = encode_image(arr)
    assert url.startswith("data:image/png;base64,")
    back = decode_image(url)
    assert back.shape == (8, 12, 3)
    assert back[0, 0, 0] > 0.9  # red channel preserved


def _make_test_image() -> str:
    import numpy as np
    from PIL import Image as PILImage
    rng = np.random.default_rng(0)
    arr = (rng.random((24, 32, 3)) * 255).astype("uint8")
    path = os.path.join(tempfile.gettempdir(), "_bn_img_test.png")
    PILImage.fromarray(arr).save(path)
    return path


@pil_only
def test_load_image_reads_file():
    path = _make_test_image()
    r = load_image({"path": path, "max_size": 0})
    assert r["width"] == 32 and r["height"] == 24
    assert r["image"].startswith("data:image/png;base64,")


# --- GPU image filter -----------------------------------------------------------

@gpu_only
@pytest.mark.parametrize("op", IMAGE_FILTERS)
def test_each_filter_returns_image(op):
    loaded = load_image({"path": _make_test_image(), "max_size": 0})
    r = cuda_image_filter({"image": loaded["image"], "op": op, "amount": 0.5})
    assert "error" not in r["report"], r["report"]
    assert r["image"].startswith("data:image/png;base64,")
    assert r["device"]
