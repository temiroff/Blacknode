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

    def test_managed_device_operations_are_documented_as_ui_first(self):
        agent_instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        agent_guide = (ROOT / "docs" / "agent-guide.md").read_text(encoding="utf-8")
        lifecycle = (ROOT / "docs" / "project-lifecycle.md").read_text(
            encoding="utf-8",
        )

        for text in (agent_instructions, agent_guide, lifecycle):
            with self.subTest(document=text[:40]):
                self.assertIn("**Devices**", text)
                self.assertIn("**Software**", text)
                self.assertIn("**Check updates**", text)
                self.assertIn("**Update all**", text)
                self.assertIn("**Restart**", text)

        self.assertIn("primary operator surface", agent_instructions)
        self.assertIn("fallback path", agent_instructions)


if __name__ == "__main__":
    unittest.main()
