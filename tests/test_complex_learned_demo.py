from __future__ import annotations

import os
import subprocess
import sys
import unittest


class ComplexLearnedDemoTests(unittest.TestCase):
    def test_complex_learned_demo_mock_sandbox(self):
        env = os.environ.copy()
        env["BLACKNODE_LEARNED_NODES_CONSENT"] = "1"
        result = subprocess.run(
            [sys.executable, "scripts/complex_learned_demo.py", "--mock-sandbox"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("workflow node count: 14", result.stdout)
        self.assertIn("categories: Analysis, Parsing, Research", result.stdout)
        self.assertIn("validation: ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
