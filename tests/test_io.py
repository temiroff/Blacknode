from __future__ import annotations

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

from blacknode.nodes.io import file_write, http_get  # noqa: E402


class HttpGetTests(unittest.TestCase):
    def test_http_get_sends_default_user_agent(self):
        captured = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b"ok"

        def fake_urlopen(req, timeout=0):
            captured["req"] = req
            captured["timeout"] = timeout
            return Response()

        with patch("urllib.request.urlopen", fake_urlopen):
            result = http_get({"url": "https://example.com"})

        self.assertEqual(result, {"text": "ok", "status": 200})
        self.assertIn("Blacknode", captured["req"].get_header("User-agent"))
        self.assertIn("Blacknode", captured["req"].get_header("Api-user-agent"))
        self.assertIn("application/json", captured["req"].get_header("Accept"))
        self.assertEqual(captured["timeout"], 20)

    def test_http_get_keeps_custom_headers_and_timeout(self):
        captured = {}

        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b""

        def fake_urlopen(req, timeout=0):
            captured["req"] = req
            captured["timeout"] = timeout
            return Response()

        with patch("urllib.request.urlopen", fake_urlopen):
            http_get({
                "url": "https://example.com",
                "headers": {"User-Agent": "CustomAgent", "X-Test": "yes"},
                "timeout": 3,
            })

        self.assertEqual(captured["req"].get_header("User-agent"), "CustomAgent")
        self.assertEqual(captured["req"].get_header("X-test"), "yes")
        self.assertEqual(captured["timeout"], 3)


class FileWriteTests(unittest.TestCase):
    def test_file_write_returns_absolute_path_for_relative_output(self):
        old_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                result = file_write({
                    "path": "summary.txt",
                    "text": "hello",
                    "encoding": "utf-8",
                })
            finally:
                os.chdir(old_cwd)

            output_path = Path(result["path"])
            self.assertTrue(output_path.is_absolute())
            self.assertEqual(output_path, Path(tmp, "summary.txt").resolve())
            self.assertEqual(output_path.read_text(encoding="utf-8"), "hello")


if __name__ == "__main__":
    unittest.main()
