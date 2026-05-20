from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.providers.keys import api_key_for_provider, shared_api_keys_path

NIM_MODEL = "nim:meta/llama-3.1-8b-instruct"


def require_nim_api_key() -> None:
    if not api_key_for_provider("NVIDIA NIM", "NVIDIA_API_KEY"):
        raise SystemExit(
            "Set NVIDIA_API_KEY or save a NVIDIA NIM key in the editor "
            f"({shared_api_keys_path()})."
        )
