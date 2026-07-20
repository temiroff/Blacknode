from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


class EditorApiKeyStatusTests(unittest.TestCase):
    def test_status_reports_saved_key_without_exposing_value(self):
        with (
            patch.object(server, "_api_keys", {"NVIDIA NIM": "nvapi-secret"}),
            patch.object(server, "_injected_api_key_envs", set()),
            patch.dict(os.environ, {}, clear=True),
        ):
            response = TestClient(server.app).get("/settings/api-key-status")

        self.assertEqual(response.status_code, 200)
        status = response.json()["NVIDIA NIM"]
        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "saved")
        self.assertEqual(status["env_var"], "NVIDIA_API_KEY")
        self.assertNotIn("nvapi-secret", response.text)

    def test_status_reports_environment_key_when_not_saved(self):
        with (
            patch.object(server, "_api_keys", {}),
            patch.object(server, "_injected_api_key_envs", set()),
            patch.dict(os.environ, {"NVIDIA_API_KEY": "nvapi-environment"}, clear=False),
        ):
            status = server._api_key_status()["NVIDIA NIM"]

        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "environment")

    def test_hugging_face_environment_has_priority_over_saved_key(self):
        with (
            patch.object(server, "_api_keys", {"Hugging Face": "saved-token"}),
            patch.object(server, "_injected_api_key_envs", set()),
            patch.dict(os.environ, {"HF_TOKEN": "terminal-token"}, clear=False),
        ):
            status = server._api_key_status()["Hugging Face"]

        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "environment")
        self.assertEqual(status["env_var"], "HF_TOKEN")


if __name__ == "__main__":
    unittest.main()
