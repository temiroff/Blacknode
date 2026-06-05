from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.nodes.trajectory import trajectory_recorder  # noqa: E402
from blacknode.workflow import RunLogger  # noqa: E402


def _read_lines(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


STEPS = [
    {"role": "assistant", "text": "Let me look that up.", "tool_calls": [{"name": "fetch_url", "arguments": {"url": "http://x"}}]},
    {"role": "tool", "name": "fetch_url", "output": "Article text here..."},
    {"role": "assistant", "text": "The article says hello.", "tool_calls": []},
]


class TrajectoryRecorderTests(unittest.TestCase):
    def test_writes_jsonl_and_passes_result_through(self):
        with TemporaryDirectory() as tmp:
            out = trajectory_recorder({
                "result": "The article says hello.",
                "steps": STEPS,
                "prompt": "Summarize this article",
                "model": "claude-sonnet-4-6",
                "dir": tmp,
            })

            self.assertEqual(out["result"], "The article says hello.")
            path = Path(out["path"])
            self.assertEqual(path.name, "run_001.jsonl")
            self.assertTrue(path.is_file())

            lines = _read_lines(out["path"])
            meta, input_line = lines[0], lines[1]
            self.assertEqual(meta["type"], "meta")
            self.assertEqual(meta["schema"], "blacknode.trajectory/1")
            self.assertEqual(meta["model"], "claude-sonnet-4-6")
            self.assertEqual(meta["tool_calls"], 1)
            self.assertEqual(meta["model_outputs"], 2)

            self.assertEqual(input_line, {"type": "input", "role": "user", "content": "Summarize this article"})
            self.assertEqual(lines[3]["type"], "tool_result")
            self.assertEqual(lines[3]["name"], "fetch_url")
            self.assertEqual(lines[-1], {"type": "final", "role": "assistant", "content": "The article says hello."})

    def test_counter_increments_per_run(self):
        with TemporaryDirectory() as tmp:
            first = trajectory_recorder({"result": "a", "steps": [], "prompt": "p", "dir": tmp})
            second = trajectory_recorder({"result": "b", "steps": [], "prompt": "p", "dir": tmp})
            self.assertEqual(Path(first["path"]).name, "run_001.jsonl")
            self.assertEqual(Path(second["path"]).name, "run_002.jsonl")

    def test_meta_uses_run_logger_id_and_counts_events(self):
        logger = RunLogger()
        logger.model_call(node_id="n1", model="m", provider="p")
        logger.tool_call(node_id="n1", name="fetch_url", arguments={"url": "http://x"})
        with TemporaryDirectory() as tmp:
            out = trajectory_recorder({
                "result": "done",
                "steps": STEPS,
                "prompt": "p",
                "dir": tmp,
                "include_events": True,
                "__run_logger__": logger,
            })
            lines = _read_lines(out["path"])
            self.assertEqual(lines[0]["run_id"], logger.run_id)
            self.assertEqual(lines[0]["run_model_calls"], 1)
            self.assertEqual(lines[0]["run_tool_calls"], 1)
            event_lines = [line for line in lines if line["type"] == "event"]
            self.assertEqual(len(event_lines), 2)

    def test_tags_parsed_from_csv(self):
        with TemporaryDirectory() as tmp:
            out = trajectory_recorder({"result": "x", "steps": [], "prompt": "p", "tags": "good, summarize", "dir": tmp})
            meta = _read_lines(out["path"])[0]
            self.assertEqual(meta["tags"], ["good", "summarize"])


if __name__ == "__main__":
    unittest.main()
