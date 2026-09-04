from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_device_source_lock.py"
SPEC = importlib.util.spec_from_file_location("update_device_source_lock", SCRIPT)
assert SPEC and SPEC.loader
source_lock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source_lock)


def _payload() -> dict:
    return {
        "schema_version": 1,
        "python_minor": "3.11",
        "runtime": {"repository": "temiroff/blacknode-runtime", "commit": "a" * 40},
        "core": {"repository": "temiroff/Blacknode", "commit": "b" * 40},
        "hardware": {"repository": "temiroff/blacknode-robot", "commit": "c" * 40},
    }


class DeviceSourceLockScriptTests(unittest.TestCase):
    def test_updates_and_writes_full_sha_pins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "lock.json"
            path.write_text(json.dumps(_payload()), encoding="utf-8")

            result = source_lock.main(["--lock", str(path), "--runtime-commit", "d" * 40, "--write"])

            self.assertEqual(result, 0)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["runtime"]["commit"], "d" * 40)

    def test_rejects_short_or_non_hex_pins(self):
        payload = _payload()
        with self.assertRaisesRegex(ValueError, "full lowercase commit SHA"):
            source_lock.update_commits(payload, {"runtime": "deadbeef"})

    def test_verification_requires_each_pin_on_its_default_branch(self):
        responses = iter([
            {"default_branch": "main"}, {"status": "ahead"},
            {"default_branch": "master"}, {"status": "identical"},
            {"default_branch": "main"}, {"status": "diverged"},
        ])
        with patch.object(source_lock, "_github_json", side_effect=lambda _url: next(responses)):
            with self.assertRaisesRegex(ValueError, "hardware commit"):
                source_lock.verify_merged_sources(_payload())


if __name__ == "__main__":
    unittest.main()
