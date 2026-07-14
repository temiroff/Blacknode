from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentSkillTests(unittest.TestCase):
    def test_blacknode_skill_is_available_in_canonical_and_agents_paths(self):
        paths = [
            ROOT / "skills" / "blacknode-workflow" / "SKILL.md",
            ROOT / ".agents" / "skills" / "blacknode-workflow" / "SKILL.md",
        ]

        for path in paths:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertIn("name: blacknode-workflow", text)
                self.assertIn("blacknode mcp --transport streamable-http", text)
                self.assertIn("validate_workflow", text)
                self.assertIn("get_editor_runtime_status", text)
                self.assertIn("stop_editor_runtime_services", text)
                self.assertIn("one-shot editor cook", text)

        self.assertEqual(
            paths[0].read_text(encoding="utf-8"),
            paths[1].read_text(encoding="utf-8"),
            "canonical and repository-local Blacknode skills must stay synchronized",
        )


if __name__ == "__main__":
    unittest.main()
