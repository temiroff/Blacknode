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
        # Template has a ConversationMemory node, so turns land in the shared store.
        from blacknode import conversation_state
        self.assertEqual(conversation_state.turns("chat-7"), [("@bot ping", "pong")])


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
