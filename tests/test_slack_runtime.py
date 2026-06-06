from __future__ import annotations

import copy
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

from blacknode import conversation_state  # noqa: E402
from blacknode.cli import main  # noqa: E402
from blacknode.integrations import slack_runtime as sr  # noqa: E402

TEMPLATE = ROOT / "templates" / "slack-nim-agent.json"

# A minimal workflow with NO ConversationMemory node, to exercise the driver's
# own built-in memory path (run_workflow is patched, so only detect/inject matter).
_NO_MEM = {
    "node_meta": {
        "task": {"type": "Text", "inputs": [], "outputs": ["value"], "params": {"value": "Hello!"}},
    },
    "edges": [],
}


def _template() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def _no_mem() -> dict:
    return copy.deepcopy(_NO_MEM)


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
    def test_detect_input_node_prefers_slack_message(self):
        self.assertEqual(sr.detect_input_node(_template()), "message")

    def test_detect_input_node_falls_back_to_prompt_source(self):
        wf = {
            "node_meta": {
                "src": {"type": "Text", "outputs": ["value"]},
                "loop": {"type": "AgentLoop", "inputs": ["prompt"]},
            },
            "edges": [{"from": "src", "from_port": "value", "to": "loop", "to_port": "prompt"}],
        }
        self.assertEqual(sr.detect_input_node(wf), "src")

    def test_detect_input_node_raises_when_absent(self):
        with self.assertRaises(sr.SlackConfigError):
            sr.detect_input_node({"node_meta": {}, "edges": []})

    def test_inject_input_sets_text_without_mutating_original(self):
        wf = _template()
        clone = sr.inject_input(wf, "message", "Capital of France?")
        self.assertEqual(clone["node_meta"]["message"]["params"]["text"], "Capital of France?")
        self.assertEqual(wf["node_meta"]["message"]["params"]["text"], "Hello!")  # original untouched

    def test_inject_input_writes_metadata_into_declared_ports(self):
        wf = _template()
        clone = sr.inject_input(
            wf,
            "message",
            "hi",
            fields={"user_id": "U1", "channel": "C9", "thread_ts": "111.2"},
        )
        params = clone["node_meta"]["message"]["params"]
        self.assertEqual(params["text"], "hi")
        self.assertEqual(params["user_id"], "U1")
        self.assertEqual(params["channel"], "C9")
        self.assertEqual(params["thread_ts"], "111.2")

    def test_inject_input_sets_value_for_plain_text_node(self):
        wf = {"node_meta": {"task": {"type": "Text", "outputs": ["value"], "params": {}}}}
        clone = sr.inject_input(wf, "task", "hello", fields={"channel": "C9"})
        # Plain Text node uses `value`, and does not gain a `channel` it never declared.
        self.assertEqual(clone["node_meta"]["task"]["params"]["value"], "hello")
        self.assertNotIn("channel", clone["node_meta"]["task"]["params"])

    def test_strip_mention(self):
        self.assertEqual(sr.strip_mention("<@U12345> hi there"), "hi there")


class RuntimeTests(unittest.TestCase):
    """The driver's built-in memory path (workflow has no ConversationMemory node)."""

    def test_handle_message_injects_runs_and_remembers(self):
        seen = {}

        def fake_run(wf):
            seen["prompt"] = wf["node_meta"]["task"]["params"]["value"]
            return {"value": "Paris."}

        runtime = sr.SlackAgentRuntime(_no_mem())
        self.assertEqual(runtime.input_node, "task")
        self.assertFalse(runtime.memory_node)
        with patch.object(sr, "run_workflow", fake_run):
            reply = runtime.handle_message(
                "<@U1> Capital of France?", "thread-1", user_id="U1", channel="C9"
            )

        self.assertEqual(reply, "Paris.")
        self.assertEqual(seen["prompt"], "Capital of France?")  # mention stripped, injected
        self.assertEqual(runtime.memory.history("thread-1"), [("Capital of France?", "Paris.")])

    def test_second_message_carries_thread_context(self):
        prompts = []

        def fake_run(wf):
            prompts.append(wf["node_meta"]["task"]["params"]["value"])
            return {"value": f"answer{len(prompts)}"}

        runtime = sr.SlackAgentRuntime(_no_mem())
        with patch.object(sr, "run_workflow", fake_run):
            runtime.handle_message("first question", "t")
            runtime.handle_message("follow up", "t")

        self.assertIn("User: first question", prompts[1])
        self.assertIn("Assistant: answer1", prompts[1])
        self.assertTrue(prompts[1].endswith("User: follow up"))

    def test_handle_message_injects_metadata_into_message_node(self):
        seen = {}

        def fake_run(wf):
            params = wf["node_meta"]["message"]["params"]
            seen.update(params)
            return {"value": "ok"}

        runtime = sr.SlackAgentRuntime(_template())
        self.assertEqual(runtime.input_node, "message")
        with patch.object(sr, "run_workflow", fake_run):
            runtime.handle_message("<@U1> hi", "thread-1", user_id="U1", channel="C9")

        self.assertEqual(seen["text"], "hi")          # mention stripped, raw (memory node prepends)
        self.assertEqual(seen["channel"], "C9")       # event metadata reaches the graph
        self.assertEqual(seen["thread_ts"], "thread-1")

    def test_stringify_handles_dict_result(self):
        self.assertEqual(sr._stringify({"result": "ok"}), "ok")
        self.assertEqual(sr._stringify(None), "(no output)")


class MemoryNodeTests(unittest.TestCase):
    """Memory as a graph node, backed by the shared conversation_state store."""

    def setUp(self):
        conversation_state.reset()

    def test_node_registered_and_prepends_history(self):
        from blacknode.node import _NODE_REGISTRY

        self.assertIn("ConversationMemory", _NODE_REGISTRY)
        first = _NODE_REGISTRY["ConversationMemory"](
            {"message": "hi", "conversation": "c1", "max_turns": 6}
        )
        self.assertEqual(first["prompt"], "hi")  # no history yet

        conversation_state.record("c1", "hi", "hello")
        second = _NODE_REGISTRY["ConversationMemory"](
            {"message": "again", "conversation": "c1", "max_turns": 6}
        )
        self.assertIn("User: hi", second["prompt"])
        self.assertIn("Assistant: hello", second["prompt"])
        self.assertTrue(second["prompt"].endswith("User: again"))

    def test_driver_with_memory_node_records_to_shared_store(self):
        seen = []

        def fake_run(wf):
            seen.append(wf["node_meta"]["message"]["params"]["text"])
            return {"value": f"a{len(seen)}"}

        runtime = sr.SlackAgentRuntime(_template())
        self.assertTrue(runtime.memory_node)
        with patch.object(sr, "run_workflow", fake_run):
            runtime.handle_message("first", "t")
            runtime.handle_message("second", "t")

        # Driver injects RAW messages; the node (mocked out here) would prepend.
        self.assertEqual(seen, ["first", "second"])
        # Turns land in the shared store, not the driver's private memory.
        self.assertEqual(conversation_state.turns("t"), [("first", "a1"), ("second", "a2")])
        self.assertEqual(runtime.memory.history("t"), [])


class MessagingNodeTests(unittest.TestCase):
    def test_nodes_are_registered(self):
        import blacknode  # noqa: F401  (registers built-in nodes on import)
        from blacknode.node import _NODE_REGISTRY

        self.assertIn("SlackMessage", _NODE_REGISTRY)
        self.assertIn("SlackReply", _NODE_REGISTRY)

    def test_slack_message_emits_its_params(self):
        from blacknode.node import _NODE_REGISTRY

        out = _NODE_REGISTRY["SlackMessage"]({"text": "hi", "channel": "C9"})
        self.assertEqual(out["text"], "hi")
        self.assertEqual(out["channel"], "C9")
        self.assertEqual(out["user_id"], "")  # missing params default to empty strings

    def test_slack_reply_passes_text_through(self):
        from blacknode.node import _NODE_REGISTRY

        out = _NODE_REGISTRY["SlackReply"]({"text": "done", "thread_ts": "1.2"})
        self.assertEqual(out["text"], "done")
        self.assertEqual(out["thread_ts"], "1.2")

    def test_template_validates(self):
        from blacknode.workflow import validate_workflow

        report = validate_workflow(_template())
        self.assertTrue(report.ok, report.to_dict())

    def test_message_routing_info_wires_into_reply(self):
        wf = _template()
        self.assertEqual(wf["node_meta"]["message"]["type"], "SlackMessage")
        # who (user_id) + where (channel/thread_ts) all flow message -> reply.
        for port in ("channel", "thread_ts", "user_id"):
            self.assertIn(
                {"from": "message", "from_port": port, "to": "reply", "to_port": port},
                wf["edges"],
            )


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
