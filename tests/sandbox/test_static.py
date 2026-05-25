from __future__ import annotations

import unittest

from blacknode.sandbox.static import FORBIDDEN_IMPORTS, FORBIDDEN_NAMES, check_safe


class StaticCheckTests(unittest.TestCase):
    def test_rejects_every_forbidden_import(self):
        for module_name in sorted(FORBIDDEN_IMPORTS):
            with self.subTest(module_name=module_name):
                result = check_safe(f"import {module_name}\n")
                self.assertFalse(result.safe)
                self.assertEqual(result.reason, f"Forbidden import: {module_name}")

    def test_rejects_forbidden_import_submodules(self):
        result = check_safe("import os.path\n")

        self.assertFalse(result.safe)
        self.assertEqual(result.reason, "Forbidden import: os.path")

    def test_rejects_forbidden_from_import_modules(self):
        result = check_safe("from subprocess import run\n")

        self.assertFalse(result.safe)
        self.assertEqual(result.reason, "Forbidden import: subprocess")

    def test_rejects_dotted_from_import_aliases(self):
        result = check_safe("from asyncio import subprocess\n")

        self.assertFalse(result.safe)
        self.assertEqual(result.reason, "Forbidden import: asyncio.subprocess")

    def test_rejects_every_forbidden_name(self):
        for name in sorted(FORBIDDEN_NAMES):
            with self.subTest(name=name):
                result = check_safe(
                    "def run(value):\n"
                    f"    return {name}(value)\n"
                )
                self.assertFalse(result.safe)
                self.assertIn(name, result.reason)

    def test_open_gets_specific_io_message(self):
        result = check_safe(
            "def run(path):\n"
            "    return open(path).read()\n"
        )

        self.assertFalse(result.safe)
        self.assertEqual(
            result.reason,
            "Use of `open` not allowed in learned nodes (I/O is mediated by the runner)",
        )

    def test_rejects_dunder_bypass_attributes(self):
        for attr in ("__builtins__", "__class__", "__globals__", "__import__"):
            with self.subTest(attr=attr):
                result = check_safe(
                    "def run(value):\n"
                    f"    return value.{attr}\n"
                )
                self.assertFalse(result.safe)
                self.assertEqual(result.reason, f"Forbidden dunder access: {attr}")

    def test_rejects_standalone_dunder_builtins(self):
        result = check_safe(
            "def run(value):\n"
            "    return __builtins__\n"
        )

        self.assertFalse(result.safe)
        self.assertEqual(result.reason, "Forbidden dunder access: __builtins__")

    def test_reports_syntax_errors(self):
        result = check_safe("def run(:\n")

        self.assertFalse(result.safe)
        self.assertEqual(result.reason, "Syntax error: invalid syntax at line 1")

    def test_allows_plain_transform_code(self):
        result = check_safe(
            "import json\n"
            "\n"
            "def run(text, limit=5):\n"
            "    words = json.loads(text)\n"
            "    return {'items': words[:limit]}\n"
        )

        self.assertTrue(result.safe, result.reason)

    def test_does_not_execute_top_level_code(self):
        result = check_safe(
            "raise RuntimeError('host execution would fail')\n"
            "\n"
            "def run(value):\n"
            "    return {'value': value}\n"
        )

        self.assertTrue(result.safe, result.reason)


if __name__ == "__main__":
    unittest.main()

