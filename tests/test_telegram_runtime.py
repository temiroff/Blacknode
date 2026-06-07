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

import blacknode  # noqa: F401,E402  (registers built-in nodes + drivers)
from blacknode.cli import main  # noqa: E402
from blacknode.integrations import slack_runtime as sr  # noqa: E402
from blacknode.integrations.registry import get_driver  # noqa: E402

TEMPLATE = ROOT / "templates" / "telegram-nim-agent.json"


def _template() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


class TelegramNodeTests(unittest.TestCase):
    def test_nodes_registered(self):
        from blacknode.node import _NODE_REGISTRY

        self.assertIn("TelegramMessage", _NODE_REGISTRY)
        self.assertIn("TelegramReply", _NODE_REGISTRY)

    def test_message_node_emits_params(self):
        from blacknode.node import _NODE_REGISTRY

        out = _NODE_REGISTRY["TelegramMessage"]({"text": "hi", "chat_id": "42"})
        self.assertEqual(out["text"], "hi")
        self.assertEqual(out["chat_id"], "42")
        self.assertEqual(out["message_id"], "")

    def test_reply_node_sends_only_with_destination(self):
        from blacknode.nodes import messaging

        posts = []
        orig_post, orig_secret = messaging._post_json, messaging.secret
        messaging._post_json = lambda url, payload, headers=None, timeout=12: posts.append((url, payload)) or True
        messaging.secret = lambda name, explicit=None: "TESTTOKEN"
        try:
            # No chat_id → no network call at all (safe to cook in the editor).
            self.assertFalse(messaging._telegram_send("", "hi"))
            self.assertEqual(posts, [])
            # Real destination + token → it posts via the Telegram API.
            self.assertTrue(messaging._telegram_send("C1", "hi", "5"))
            self.assertEqual(len(posts), 1)
            url, payload = posts[0]
            self.assertIn("sendMessage", url)
            self.assertEqual(payload["chat_id"], "C1")
            self.assertEqual(payload["text"], "hi")
            self.assertEqual(payload["reply_to_message_id"], 5)
        finally:
            messaging._post_json, messaging.secret = orig_post, orig_secret

    def test_template_valid_and_uses_telegram_nodes(self):
        from blacknode.workflow import validate_workflow

        wf = _template()
        self.assertTrue(validate_workflow(wf).ok)
        self.assertEqual(wf["node_meta"]["message"]["type"], "TelegramMessage")
        self.assertEqual(wf["node_meta"]["reply"]["type"], "TelegramReply")
        self.assertEqual(wf["node_meta"]["memory"]["params"]["max_turns"], 0)
        # where (chat_id) + who (user_id) + which message (message_id) all flow
        # message -> reply, so the reply node carries the full context.
        for port in ("chat_id", "user_id", "message_id"):
            self.assertIn(
                {"from": "message", "from_port": port, "to": "reply", "to_port": port},
                wf["edges"],
            )


class TelegramDriverTests(unittest.TestCase):
    def test_driver_registered(self):
        spec = get_driver("telegram")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.required_packages, ("telegram",))
        self.assertEqual(spec.required_env, ("TELEGRAM_BOT_TOKEN",))

    def test_detect_input_node_finds_telegram_message(self):
        self.assertEqual(sr.detect_input_node(_template()), "message")

    def test_handle_message_injects_chat_metadata(self):
        from blacknode import conversation_state
        conversation_state.reset()
        seen = {}

        def fake_run(wf):
            seen.update(wf["node_meta"]["message"]["params"])
            return {"value": "pong"}

        runtime = sr.AgentRuntime(_template())
        with patch.object(sr, "run_workflow", fake_run):
            reply = runtime.handle_message(
                "@bot ping",
                "chat-7",
                fields={"user_id": "U1", "chat_id": "chat-7", "message_id": "55"},
            )

        self.assertEqual(reply, "pong")
        self.assertEqual(seen["text"], "@bot ping")  # Slack-style strip leaves @bot for the driver
        self.assertEqual(seen["chat_id"], "chat-7")
        self.assertEqual(seen["message_id"], "55")
        # Telegram memory is explicitly disabled, so independent prompts stay independent.
        from blacknode import conversation_state
        self.assertEqual(conversation_state.turns("chat-7"), [])


class TextToolCallSalvageTests(unittest.TestCase):
    def _tools(self):
        from blacknode.providers.base import ToolDef
        return [ToolDef(name="calculator", description="", parameters={})]

    def test_recovers_python_dict_tool_call(self):
        from blacknode.providers.openai_provider import _salvage_text_tool_call
        tc = _salvage_text_tool_call("{'name': 'calculator', 'parameters': {'expression': '2+2'}}", self._tools())
        self.assertIsNotNone(tc)
        self.assertEqual(tc.name, "calculator")
        self.assertEqual(tc.arguments, {"expression": "2+2"})

    def test_recovers_json_tool_call_with_prefix(self):
        from blacknode.providers.openai_provider import _salvage_text_tool_call
        tc = _salvage_text_tool_call('Sure! {"name": "calculator", "arguments": {"expression": "42*2"}}', self._tools())
        self.assertEqual(tc.arguments, {"expression": "42*2"})

    def test_ignores_plain_text_and_unknown_tools(self):
        from blacknode.providers.openai_provider import _salvage_text_tool_call
        self.assertIsNone(_salvage_text_tool_call("the result is 84", self._tools()))
        self.assertIsNone(_salvage_text_tool_call("{'name': 'nope', 'parameters': {}}", self._tools()))


class UserFacingAnswerTests(unittest.TestCase):
    def test_blank_agent_prompt_returns_without_model_call(self):
        from blacknode.nodes.ai import _agent_loop_run
        self.assertEqual(_agent_loop_run({"prompt": "", "tools": []}), {"result": "", "steps": []})

    def test_strips_tool_process_preamble(self):
        from blacknode.nodes.ai import _user_facing_answer
        text = (
            'This response shows that the web_search function was called with the query "who is Arnold". '
            "Since the response does not return JSON, I will provide the function result.\n\n"
            "The final answer is: Arnold Arboretum."
        )
        self.assertEqual(_user_facing_answer(text), "Arnold Arboretum.")

    def test_suppresses_process_only_tool_narration(self):
        from blacknode.nodes.ai import _user_facing_answer
        self.assertEqual(
            _user_facing_answer("The final answer is in the output of the web_search tool call."),
            "",
        )
        self.assertEqual(
            _user_facing_answer(
                'This response shows that the web_search function was called with the query "definition".'
            ),
            "",
        )

    def test_preserves_normal_answer(self):
        from blacknode.nodes.ai import _user_facing_answer
        self.assertEqual(_user_facing_answer("Arnold was an actor."), "Arnold was an actor.")

    def test_generic_post_tool_answer_falls_back_to_tool_output(self):
        from blacknode.nodes.ai import _answer_or_tool_output
        self.assertEqual(
            _answer_or_tool_output("This is the final answer to the user's prompt.", "4"),
            "4",
        )
        self.assertEqual(
            _answer_or_tool_output(
                'This is the result of the calculator function call with the expression "2+2".',
                "4",
            ),
            "4",
        )
        self.assertEqual(
            _answer_or_tool_output(
                "The output JSON is too long to be included here.",
                "NVIDIA is a technology company.",
            ),
            "NVIDIA is a technology company.",
        )

    def test_agent_loop_returns_calculator_output_for_generic_final_text(self):
        from blacknode.nodes import ai
        from blacknode.providers.base import CompletionResponse, ToolCall, ToolResult

        responses = [
            CompletionResponse(
                text="",
                tool_calls=[ToolCall(id="calc-1", name="calculator", arguments={"expression": "2+2"})],
                stop_reason="tool_use",
            ),
            CompletionResponse(
                text="This is the final answer to the user's prompt.",
                tool_calls=[],
                stop_reason="end_turn",
            ),
        ]

        def fake_step(*args, **kwargs):
            response = responses.pop(0)
            return None, response, {}

        with (
            patch.object(ai, "_chat_step", side_effect=fake_step),
            patch.object(
                ai,
                "_dispatch_tools",
                return_value=(
                    [ToolResult(tool_call_id="calc-1", name="calculator", output="4")],
                    [{"role": "tool", "name": "calculator", "output": "4"}],
                ),
            ),
            patch.object(ai, "_append_tool_messages", return_value=[]),
        ):
            result = ai._agent_loop_run({"prompt": "2+2", "tools": [lambda: None]})

        self.assertEqual(result["result"], "4")

    def test_agent_loop_stops_repeated_identical_tool_call(self):
        from blacknode.nodes import ai
        from blacknode.providers.base import CompletionResponse, ToolCall, ToolResult

        repeated_call = ToolCall(
            id="search-1",
            name="web_search",
            arguments={"query": "what is nvidia"},
        )
        responses = [
            CompletionResponse(text="", tool_calls=[repeated_call], stop_reason="tool_use"),
            CompletionResponse(text="", tool_calls=[repeated_call], stop_reason="tool_use"),
        ]

        def fake_step(*args, **kwargs):
            return None, responses.pop(0), {}

        with (
            patch.object(ai, "_chat_step", side_effect=fake_step),
            patch.object(
                ai,
                "_dispatch_tools",
                return_value=(
                    [
                        ToolResult(
                            tool_call_id="search-1",
                            name="web_search",
                            output="NVIDIA is a technology company.",
                        )
                    ],
                    [
                        {
                            "role": "tool",
                            "name": "web_search",
                            "output": "NVIDIA is a technology company.",
                        }
                    ],
                ),
            ) as dispatch,
            patch.object(ai, "_append_tool_messages", return_value=[]),
        ):
            result = ai._agent_loop_run(
                {"prompt": "what is nvidia", "tools": [lambda: None]}
            )

        self.assertEqual(result["result"], "NVIDIA is a technology company.")
        dispatch.assert_called_once()


class TelegramImageTests(unittest.TestCase):
    def test_message_node_emits_image(self):
        from blacknode.node import _NODE_REGISTRY
        out = _NODE_REGISTRY["TelegramMessage"]({"text": "hi", "image": "data:image/png;base64,AAAA", "chat_id": "1"})
        self.assertEqual(out["image"], "data:image/png;base64,AAAA")

    def test_decode_data_url(self):
        import base64
        from blacknode.nodes import messaging
        raw = b"hello-bytes"
        url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        dec = messaging._decode_data_url(url)
        self.assertIsNotNone(dec)
        data, mime, ext = dec
        self.assertEqual((data, mime, ext), (raw, "image/png", "png"))
        self.assertIsNone(messaging._decode_data_url("not-an-image"))

    def test_reply_sends_photo_for_image_else_text(self):
        from blacknode.node import _NODE_REGISTRY
        from blacknode.nodes import messaging
        calls = []
        orig_photo, orig_text = messaging._telegram_send_photo, messaging._telegram_send
        messaging._telegram_send_photo = lambda chat_id, data_url, caption="", message_id="": calls.append(("photo", chat_id, caption)) or True
        messaging._telegram_send = lambda chat_id, text, message_id="": calls.append(("text", chat_id, text)) or True
        try:
            _NODE_REGISTRY["TelegramReply"]({"text": "cap", "image": "data:image/png;base64,AAAA", "chat_id": "C1"})
            _NODE_REGISTRY["TelegramReply"]({"text": "hi", "image": "", "chat_id": "C1"})
            _NODE_REGISTRY["TelegramReply"]({"text": "", "image": "", "chat_id": "C1"})
            self.assertEqual(calls, [("photo", "C1", "cap"), ("text", "C1", "hi")])
        finally:
            messaging._telegram_send_photo, messaging._telegram_send = orig_photo, orig_text


class CommandTests(unittest.TestCase):
    def test_tools_command_lists_graph_tools(self):
        out = sr.describe_command(_template(), "/tools")
        self.assertIn("web_search", out)
        self.assertIn("calculator", out)

    def test_model_command_reports_model(self):
        out = sr.describe_command(_template(), "/model")
        self.assertIn("nim:meta/llama-3.1-8b-instruct", out)

    def test_graph_command_summarizes(self):
        out = sr.describe_command(_template(), "/graph")
        self.assertIn("nodes", out)
        self.assertIn("TelegramMessage", out)

    def test_help_and_unknown(self):
        self.assertIn("/tools", sr.describe_command(_template(), "/help"))
        self.assertIn("Unknown", sr.describe_command(_template(), "/nope"))

    def test_non_command_returns_none(self):
        self.assertIsNone(sr.describe_command(_template(), "hello there"))


class TelegramCliTests(unittest.TestCase):
    def test_cli_fails_without_setup(self):
        # Without python-telegram-bot installed (CI) or a token, the driver can't
        # run: exit 1 with a message about the missing extra or env var.
        err = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stderr(err):
            code = main(["telegram", str(TEMPLATE)])
        self.assertEqual(code, 1)
        message = err.getvalue()
        self.assertTrue("blacknode[telegram]" in message or "TELEGRAM_BOT_TOKEN" in message, message)


if __name__ == "__main__":
    unittest.main()
