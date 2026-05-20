from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
EXAMPLES_DIR = ROOT / "examples"

for path in (PYTHON_DIR, EXAMPLES_DIR):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)
