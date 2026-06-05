from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.cli import main  # noqa: E402
from blacknode.nodes.trajectory import build_trajectory, write_trajectory  # noqa: E402
from blacknode.training import export as exp  # noqa: E402

STEPS = [
    {"role": "assistant", "text": "Let me look that up.", "tool_calls": [{"name": "fetch_url", "arguments": {"url": "http://x"}}]},
    {"role": "tool", "name": "fetch_url", "output": "Article text here..."},
    {"role": "assistant", "text": "The article says hello.", "tool_calls": []},
]


def _write_run(directory: str, *, prompt: str, result: str, steps=STEPS, score=None, label=None, tags=None) -> str:
    rating = None
    extra_lines = None
    if score is not None:
        rating = {"score": score, "label": label or str(score), "reason": "ok", "rater": "model"}
        extra_lines = [{"type": "rating", **rating}]
    meta, messages, _ = build_trajectory(
        prompt=prompt, steps=steps, result=result, tags=tags,
        extra_meta={"label": rating} if rating else None,
    )
    return str(write_trajectory(directory, meta, messages, extra_lines=extra_lines))


class LoadAndFilterTests(unittest.TestCase):
    def test_load_parses_meta_steps_and_rating(self):
        with TemporaryDirectory() as tmp:
            _write_run(tmp, prompt="Summarize", result="The article says hello.", score=4, label="4")
            trajs = exp.load_trajectories(tmp)
            self.assertEqual(len(trajs), 1)
            t = trajs[0]
            self.assertEqual(t.prompt, "Summarize")
            self.assertEqual(t.final, "The article says hello.")
            self.assertEqual(t.score, 4.0)
            self.assertEqual(len(t.steps), 3)  # two model_output + one tool_result

    def test_filters(self):
        with TemporaryDirectory() as tmp:
            _write_run(tmp, prompt="a", result="ra", score=5, label="5", tags=["keep"])
            _write_run(tmp, prompt="b", result="rb", score=2, label="2")
            _write_run(tmp, prompt="c", result="rc")  # unrated
            self.assertEqual(len(exp.filter_trajectories(exp.load_trajectories(tmp), min_score=4)), 1)
            self.assertEqual(len(exp.filter_trajectories(exp.load_trajectories(tmp), rated_only=True)), 2)
            self.assertEqual(len(exp.filter_trajectories(exp.load_trajectories(tmp), tag="keep")), 1)
            self.assertEqual(len(exp.filter_trajectories(exp.load_trajectories(tmp), label="5")), 1)


class FormatTests(unittest.TestCase):
    def test_chat_record_roundtrips_tool_calls(self):
        with TemporaryDirectory() as tmp:
            _write_run(tmp, prompt="Summarize", result="The article says hello.")
            record = exp.to_chat_record(exp.load_trajectories(tmp)[0])
            roles = [m["role"] for m in record["messages"]]
            self.assertEqual(roles, ["user", "assistant", "tool", "assistant"])
            assistant_with_call = record["messages"][1]
            self.assertEqual(assistant_with_call["tool_calls"][0]["function"]["name"], "fetch_url")
            tool_msg = record["messages"][2]
            self.assertEqual(tool_msg["tool_call_id"], assistant_with_call["tool_calls"][0]["id"])
            self.assertEqual(record["messages"][-1]["content"], "The article says hello.")

    def test_chat_does_not_duplicate_final_when_equal_to_last_assistant(self):
        steps = [{"role": "assistant", "text": "Final only.", "tool_calls": []}]
        with TemporaryDirectory() as tmp:
            _write_run(tmp, prompt="p", result="Final only.", steps=steps)
            record = exp.to_chat_record(exp.load_trajectories(tmp)[0])
            self.assertEqual([m["role"] for m in record["messages"]], ["user", "assistant"])

    def test_sharegpt_role_mapping(self):
        with TemporaryDirectory() as tmp:
            _write_run(tmp, prompt="Summarize", result="The article says hello.")
            record = exp.to_sharegpt_record(exp.load_trajectories(tmp)[0])
            froms = [c["from"] for c in record["conversations"]]
            self.assertEqual(froms, ["human", "gpt", "tool", "gpt"])

    def test_dpo_pairs_best_vs_worse_for_same_prompt(self):
        with TemporaryDirectory() as tmp:
            _write_run(tmp, prompt="Same task", result="great answer", steps=[], score=5)
            _write_run(tmp, prompt="Same task", result="ok answer", steps=[], score=3)
            _write_run(tmp, prompt="Same task", result="bad answer", steps=[], score=1)
            pairs = exp.build_dpo_pairs(exp.load_trajectories(tmp))
            self.assertEqual(len(pairs), 2)  # best vs each worse
            for pair in pairs:
                self.assertEqual(pair["chosen"], "great answer")
                self.assertEqual(pair["prompt"], "Same task")
                self.assertGreater(pair["metadata"]["chosen_score"], pair["metadata"]["rejected_score"])


class CliTests(unittest.TestCase):
    def test_cli_writes_dataset_and_prints_summary(self):
        with TemporaryDirectory() as tmp:
            _write_run(tmp, prompt="Summarize", result="hello", score=5, label="5")
            out_path = Path(tmp) / "dataset.jsonl"
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["export-training", tmp, "--format", "jsonl", "--output", str(out_path)])
            self.assertEqual(code, 0)
            self.assertIn("[chat]", err.getvalue())
            lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(lines), 1)
            self.assertIn("messages", lines[0])
            self.assertEqual(lines[0]["metadata"]["score"], 5.0)

    def test_cli_min_score_filter(self):
        with TemporaryDirectory() as tmp:
            _write_run(tmp, prompt="a", result="ra", score=5, label="5")
            _write_run(tmp, prompt="b", result="rb", score=2, label="2")
            out_path = Path(tmp) / "ds.jsonl"
            with redirect_stderr(io.StringIO()):
                code = main(["export-training", tmp, "--min-score", "4", "-o", str(out_path)])
            self.assertEqual(code, 0)
            lines = [l for l in out_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)

    def test_cli_unknown_format_errors(self):
        with TemporaryDirectory() as tmp:
            with redirect_stderr(io.StringIO()):
                code = main(["export-training", tmp, "--format", "bogus"])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
