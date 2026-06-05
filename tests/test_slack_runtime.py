from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from blacknode.cli import main  # noqa: E402
from blacknode.integrations import slack_runtime as sr  # noqa: E402

TEMPLATE = ROOT / "templates" / "slack-nim-agent.json"


def _template() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


class ConversationMemoryTests(unittest.TestCase):
    def test_build_prompt_without_history_is_just_the_message(self):
        mem = sr.ConversationMemory()
        self.assertEqual(mem.build_prompt("t1", "hello"), "hello")

    def test_build_prompt_includes_prior_turns(self):
        mem = sr.ConversationMemory()
        mem.add("t1", "what is 2+2", "4")
        prompt = mem.build_prompt("t1", "and times 3?")
        self.assertIn("User: what is 2+2", prompt)
        self.assertIn("Assistant: 4", prompt)
        self.assertTrue(prompt.endswith("User: and times 3?"))

    def test_memory_is_per_thread_and_rolls(self):
        mem = sr.ConversationMemory(max_turns=2)
        for i in range(4):
            mem.add("t1", f"q{i}", f"a{i}")
        mem.add("t2", "other", "thread")
        self.assertEqual(mem.history("t1"), [("q2", "a2"), ("q3", "a3")])
        self.assertEqual(mem.history("t2"), [("other", "thread")])


class InputInjectionTests(unittest.TestCase):
    def test_detect_input_node_finds_prompt_source(self):
        self.assertEqual(sr.detect_input_node(_template()), "task")

    def test_detect_input_node_raises_when_absent(self):
        with self.assertRaises(sr.SlackConfigError):
            sr.detect_input_node({"node_meta": {}, "edges": []})

    def test_inject_input_sets_value_without_mutating_original(self):
        wf = _template()
        clone = sr.inject_input(wf, "task", "Capital of France?")
        self.assertEqual(clone["node_meta"]["task"]["params"]["value"], "Capital of France?")
        self.assertEqual(wf["node_meta"]["task"]["params"]["value"], "Hello!")  # original untouched

    def test_strip_mention(self):
        self.assertEqual(sr.strip_mention("<@U12345> hi there"), "hi there")


class RuntimeTests(unittest.TestCase):
    def test_handle_message_injects_runs_and_remembers(self):
        seen = {}

        def fake_run(wf):
            seen["prompt"] = wf["node_meta"]["task"]["params"]["value"]
            return {"value": "Paris."}

        runtime = sr.SlackAgentRuntime(_template())
        self.assertEqual(runtime.input_node, "task")
        with patch.object(sr, "run_workflow", fake_run):
            reply = runtime.handle_message("<@U1> Capital of France?", "thread-1")

        self.assertEqual(reply, "Paris.")
        self.assertEqual(seen["prompt"], "Capital of France?")  # mention stripped, injected
        self.assertEqual(runtime.memory.history("thread-1"), [("Capital of France?", "Paris.")])

    def test_second_message_carries_thread_context(self):
        prompts = []

        def fake_run(wf):
            prompts.append(wf["node_meta"]["task"]["params"]["value"])
            return {"value": f"answer{len(prompts)}"}

        runtime = sr.SlackAgentRuntime(_template())
        with patch.object(sr, "run_workflow", fake_run):
            runtime.handle_message("first question", "t")
            runtime.handle_message("follow up", "t")

        self.assertIn("User: first question", prompts[1])
        self.assertIn("Assistant: answer1", prompts[1])
        self.assertTrue(prompts[1].endswith("User: follow up"))

    def test_stringify_handles_dict_result(self):
        self.assertEqual(sr._stringify({"result": "ok"}), "ok")
        self.assertEqual(sr._stringify(None), "(no output)")


class ServeAndCliTests(unittest.TestCase):
    def test_serve_raises_clear_error_without_slack_bolt(self):
        # slack_bolt is not a test/CI dependency, so serve must fail with guidance.
        runtime = sr.SlackAgentRuntime(_template())
        with self.assertRaises(sr.SlackDependencyError) as ctx:
            sr.serve(runtime, bot_token="xoxb-x", app_token="xapp-x")
        self.assertIn("blacknode[slack]", str(ctx.exception))

    def test_cli_slack_fails_without_setup(self):
        # Without slack_bolt installed (CI) or tokens set, the slack driver can't
        # run: exit 1 with a message about the missing extra or env var.
        err = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stderr(err):
            code = main(["slack", str(TEMPLATE)])
        self.assertEqual(code, 1)
        message = err.getvalue()
        self.assertTrue("blacknode[slack]" in message or "SLACK_BOT_TOKEN" in message, message)


if __name__ == "__main__":
    unittest.main()
