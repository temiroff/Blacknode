from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import blacknode.integrations  # noqa: E402, F401  - registers built-in drivers
from blacknode.cli import main  # noqa: E402
from blacknode.integrations import registry as reg  # noqa: E402


def _spec(name="dummy", packages=("os",), env=("DUMMY_TOKEN",)):
    return reg.DriverSpec(
        name=name,
        description="test driver",
        run=lambda runtime: None,
        required_extra=name,
        required_packages=packages,
        required_env=env,
    )


class RegistryTests(unittest.TestCase):
    def test_register_get_and_list(self):
        spec = _spec(name="zzz_dummy")
        reg.register_driver(spec)
        self.assertIs(reg.get_driver("zzz_dummy"), spec)
        self.assertIn("zzz_dummy", [s.name for s in reg.list_drivers()])
        # list is sorted by name
        names = [s.name for s in reg.list_drivers()]
        self.assertEqual(names, sorted(names))

    def test_packages_installed(self):
        self.assertTrue(reg.packages_installed(_spec(packages=("os", "json"))))
        self.assertFalse(reg.packages_installed(_spec(packages=("definitely_not_a_real_pkg_xyz",))))

    def test_missing_env(self):
        spec = _spec(env=("DRV_A", "DRV_B"))
        with patch.dict("os.environ", {"DRV_A": "x"}, clear=True):
            self.assertEqual(reg.missing_env(spec), ["DRV_B"])

    def test_driver_status_transitions(self):
        installed_env = _spec(packages=("os",), env=("DRV_X",))
        with patch.dict("os.environ", {"DRV_X": "1"}, clear=True):
            self.assertEqual(reg.driver_status(installed_env)["status"], "ready")
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(reg.driver_status(installed_env)["status"], "needs env")
        no_pkg = _spec(packages=("definitely_not_a_real_pkg_xyz",), env=())
        self.assertEqual(reg.driver_status(no_pkg)["status"], "needs install")


class SlackRegisteredTests(unittest.TestCase):
    def test_slack_driver_is_registered(self):
        spec = reg.get_driver("slack")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.required_extra, "slack")
        self.assertEqual(spec.required_env, ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"))

    def test_slack_status_keys_present(self):
        st = reg.driver_status(reg.get_driver("slack"))
        self.assertIn(st["status"], {"ready", "needs env", "needs install"})
        self.assertEqual(set(st["env"]), {"SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"})


class DriversCommandTests(unittest.TestCase):
    def test_drivers_human_lists_slack(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["drivers"])
        self.assertEqual(code, 0)
        self.assertIn("slack", out.getvalue())

    def test_drivers_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["drivers", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        names = [d["name"] for d in data["drivers"]]
        self.assertIn("slack", names)
        slack = next(d for d in data["drivers"] if d["name"] == "slack")
        self.assertIn(slack["status"], {"ready", "needs env", "needs install"})
        self.assertEqual(slack["extra"], "blacknode[slack]")


if __name__ == "__main__":
    unittest.main()
