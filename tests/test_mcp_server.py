from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from blacknode.mcp import server


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class NonTtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return False


class McpServerTests(unittest.TestCase):
    def test_stdio_terminal_hint_is_written_to_stderr_for_humans(self):
        stderr = TtyStringIO()
        with (
            patch.object(server.sys, "stdin", TtyStringIO()),
            patch.object(server.sys, "stderr", stderr),
            patch.object(server.mcp, "run"),
        ):
            server.main(transport="stdio")

        text = stderr.getvalue()
        self.assertIn("Blacknode MCP stdio server is running.", text)
        self.assertIn("waiting for an MCP client", text)
        self.assertIn("Press Ctrl+C to stop.", text)

    def test_stdio_terminal_hint_is_silent_for_mcp_clients(self):
        stderr = TtyStringIO()
        with (
            patch.object(server.sys, "stdin", NonTtyStringIO()),
            patch.object(server.sys, "stderr", stderr),
            patch.object(server.mcp, "run"),
        ):
            server.main(transport="stdio")

        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
