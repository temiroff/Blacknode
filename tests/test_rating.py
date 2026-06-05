from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.nodes import rating  # noqa: E402
from blacknode.nodes.rating import _parse_judgement, _parse_scale, rate_output  # noqa: E402
from blacknode.providers.base import CompletionResponse  # noqa: E402

STEPS = [
    {"role": "assistant", "text": "thinking", "tool_calls": [{"name": "f", "arguments": {}}]},
    {"role": "tool", "name": "f", "output": "res"},
    {"role": "assistant", "text": "final answer", "tool_calls": []},
]


class FakeProvider:
    def __init__(self, text: str):
        self.text = text
        self.calls: list[dict] = []

    def complete(self, messages, *, model, system="", max_tokens=1024, tools=None, temperature=1.0, **kw):
        self.calls.append({"messages": messages, "model": model, "temperature": temperature})
        return CompletionResponse(text=self.text, tool_calls=[], stop_reason="end_turn")


def _fake_resolve(reply: str, clean: str = "the-model"):
    provider = FakeProvider(reply)
    return lambda *a, **k: (provider, clean), provider


def _read_lines(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class ParseHelperTests(unittest.TestCase):
    def test_parse_scale_variants(self):
        self.assertEqual(_parse_scale("1-5"), ("numeric", 1.0, 5.0))
        self.assertEqual(_parse_scale("1-10"), ("numeric", 1.0, 10.0))
        self.assertEqual(_parse_scale("updown"), ("binary", 0.0, 1.0))
        self.assertEqual(_parse_scale("thumbs"), ("binary", 0.0, 1.0))
        self.assertEqual(_parse_scale("garbage"), ("numeric", 1.0, 5.0))

    def test_parse_numeric_json(self):
        score, label, reason = _parse_judgement('{"score": 4, "reason": "good"}', "numeric", 1.0, 5.0)
        self.assertEqual((score, label, reason), (4.0, "4", "good"))

    def test_parse_numeric_clamps_and_falls_back_to_number_scan(self):
        score, _label, _r = _parse_judgement("I'd rate this a 9 out of 5 honestly", "numeric", 1.0, 5.0)
        self.assertEqual(score, 5.0)

    def test_parse_binary_verdict(self):
        score, label, _r = _parse_judgement('{"verdict": "down", "reason": "wrong"}', "binary", 0.0, 1.0)
        self.assertEqual((score, label), (0.0, "down"))

    def test_unreadable_returns_none(self):
        score, label, _r = _parse_judgement("no signal here at all", "binary", 0.0, 1.0)
        self.assertIsNone(score)
        self.assertEqual(label, "")


class RateOutputTests(unittest.TestCase):
    def test_model_judge_scores_and_labels_trajectory(self):
        fake_resolve, provider = _fake_resolve('{"score": 4, "reason": "Accurate but verbose"}')
        with TemporaryDirectory() as tmp, patch.object(rating, "resolve", fake_resolve):
            out = rate_output({
                "result": "final answer",
                "steps": STEPS,
                "prompt": "Summarize this",
                "judge_model": "nim:meta/llama-3.1-70b-instruct",
                "rubric": "Rate 1-5 for accuracy and helpfulness",
                "dir": tmp,
            })

            self.assertEqual(out["result"], "final answer")  # passthrough
            self.assertEqual(out["score"], 4.0)
            self.assertEqual(out["label"], "4")
            self.assertEqual(out["reason"], "Accurate but verbose")
            self.assertEqual(out["rating"]["rater"], "model")
            self.assertEqual(out["rating"]["judge_model"], "the-model")
            self.assertEqual(provider.calls[0]["temperature"], 0.0)  # deterministic judging

            lines = _read_lines(out["path"])
            self.assertEqual(lines[0]["label"]["score"], 4.0)          # meta carries the label
            self.assertEqual(lines[1]["content"], "Summarize this")    # input preserved
            self.assertEqual(lines[-1]["type"], "rating")              # rating appended last
            self.assertEqual(lines[-1]["score"], 4.0)

    def test_thumbs_scale(self):
        fake_resolve, _ = _fake_resolve('{"verdict": "up", "reason": "great"}')
        with TemporaryDirectory() as tmp, patch.object(rating, "resolve", fake_resolve):
            out = rate_output({"result": "x", "prompt": "p", "scale": "updown", "dir": tmp})
        self.assertEqual(out["label"], "up")
        self.assertEqual(out["score"], 1.0)

    def test_review_band_flags_low_scores(self):
        fake_resolve, _ = _fake_resolve('{"score": 2, "reason": "weak"}')
        with TemporaryDirectory() as tmp, patch.object(rating, "resolve", fake_resolve):
            out = rate_output({"result": "x", "prompt": "p", "scale": "1-5", "review_band": "2-3", "dir": tmp})
        self.assertTrue(out["rating"]["needs_human_review"])

    def test_save_false_skips_file(self):
        fake_resolve, _ = _fake_resolve('{"score": 5, "reason": "ok"}')
        with TemporaryDirectory() as tmp, patch.object(rating, "resolve", fake_resolve):
            out = rate_output({"result": "x", "prompt": "p", "dir": tmp, "save": False})
        self.assertEqual(out["path"], "")
        self.assertEqual(list(Path(tmp).glob("*.jsonl")), [])


if __name__ == "__main__":
    unittest.main()
