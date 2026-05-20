from __future__ import annotations

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
EXAMPLES = ROOT / "examples"

for path in (PYTHON_DIR, EXAMPLES):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from blacknode.node import _NODE_REGISTRY  # noqa: E402
from blacknode.providers import registry  # noqa: E402
from blacknode.providers.base import CompletionResponse  # noqa: E402


class FakeNimProvider:
    def __init__(self, calls: list[dict]):
        self.calls = calls

    def complete(self, messages, *, model, system="", max_tokens=1024, tools=None, temperature=1.0, **kwargs):
        self.calls.append({
            "model": model,
            "messages": messages,
            "system": system,
            "max_tokens": max_tokens,
            "tools": tools,
            "temperature": temperature,
        })
        return CompletionResponse(text="Paris")


class ExampleTests(unittest.TestCase):
    def run_example(self, name: str) -> str:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            runpy.run_path(str(EXAMPLES / name), run_name="__main__")
        return stream.getvalue()

    def fake_nim(self):
        calls: list[dict] = []

        def make_nim(api_key=None):
            return FakeNimProvider(calls)

        return calls, patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}), patch.object(registry, "_make_nim", make_nim)

    def test_custom_node_example_runs(self):
        out = self.run_example("custom_node.py")
        self.assertIn("HELLO, BLACKNODE WORLD", out)

    def test_hello_agent_uses_nim_model(self):
        calls, env_patch, nim_patch = self.fake_nim()
        with env_patch, nim_patch:
            out = self.run_example("hello_agent.py")

        self.assertIn("Paris", out)
        self.assertEqual(calls[0]["model"], "meta/llama-3.1-8b-instruct")

    def test_multi_provider_example_uses_nim_model(self):
        calls, env_patch, nim_patch = self.fake_nim()
        with env_patch, nim_patch:
            out = self.run_example("multi_provider.py")

        self.assertIn("=== NVIDIA NIM ===", out)
        self.assertIn("Paris", out)
        self.assertEqual(calls[0]["model"], "meta/llama-3.1-8b-instruct")

    def test_research_pipeline_runs_without_network(self):
        calls, env_patch, nim_patch = self.fake_nim()
        original_http_get = _NODE_REGISTRY["HTTPGet"]

        def fake_http_get(ctx: dict) -> dict:
            return {
                "text": "Houdini is procedural 3D software used for effects, simulations, and pipelines.",
                "status": 200,
            }

        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                _NODE_REGISTRY["HTTPGet"] = fake_http_get
                with env_patch, nim_patch:
                    self.run_example("research_pipeline.py")
            finally:
                _NODE_REGISTRY["HTTPGet"] = original_http_get
                os.chdir(cwd)

            summary = Path(tmp) / "summary.txt"
            self.assertEqual(summary.read_text(encoding="utf-8"), "Paris")

        self.assertEqual(calls[0]["model"], "meta/llama-3.1-8b-instruct")


if __name__ == "__main__":
    unittest.main()
