from __future__ import annotations

import os
import subprocess
import sys
import unittest


RUN_DOCKER_TESTS = os.environ.get("BLACKNODE_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(RUN_DOCKER_TESTS, "set BLACKNODE_INTEGRATION_TESTS=1 to run demo dry-run")
class DemoDryRunTests(unittest.TestCase):
    def test_demo_dry_run_script_completes(self):
        env = os.environ.copy()
        env["BLACKNODE_LEARNED_NODES_CONSENT"] = "1"
        result = subprocess.run(
            [sys.executable, "scripts/demo_dry_run.py"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("workflow ran through Docker-backed learned node", result.stdout)


if __name__ == "__main__":
    unittest.main()
