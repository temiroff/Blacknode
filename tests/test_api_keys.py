from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.providers import keys


class SharedApiKeyTests(unittest.TestCase):
    def test_loads_editor_saved_api_key_json(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            path.write_text(json.dumps({"NVIDIA NIM": "json-key"}), encoding="utf-8")

            with patch.object(keys, "_SHARED_KEYS_PATH", path), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(keys.api_key_for_provider("NVIDIA NIM", "NVIDIA_API_KEY"), "json-key")

    def test_env_overrides_saved_api_key_json(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            path.write_text(json.dumps({"NVIDIA NIM": "json-key"}), encoding="utf-8")

            with patch.object(keys, "_SHARED_KEYS_PATH", path), patch.dict(os.environ, {"NVIDIA_API_KEY": "env-key"}, clear=True):
                self.assertEqual(keys.api_key_for_provider("NVIDIA NIM", "NVIDIA_API_KEY"), "env-key")

    def test_hugging_face_uses_environment_then_shared_store(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            path.write_text(json.dumps({"Hugging Face": "saved-token"}), encoding="utf-8")

            with patch.object(keys, "_SHARED_KEYS_PATH", path), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(keys.api_key_for_provider("Hugging Face"), "saved-token")
            with (
                patch.object(keys, "_SHARED_KEYS_PATH", path),
                patch.dict(os.environ, {"HF_TOKEN": "terminal-token"}, clear=True),
            ):
                self.assertEqual(keys.api_key_for_provider("Hugging Face"), "terminal-token")


if __name__ == "__main__":
    unittest.main()
