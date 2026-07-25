"""Regression checks for readable editor typography."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SOURCE = ROOT / "editor" / "src"
CSS_SIZE = re.compile(r"font-size:\s*([0-9]+(?:\.[0-9]+)?)px")
TSX_SIZE = re.compile(r"fontSize:\s*([0-9]+(?:\.[0-9]+)?)")


class EditorTypographyTests(unittest.TestCase):
    def test_explicit_editor_text_is_at_least_eleven_pixels(self):
        violations: list[str] = []
        for path in sorted(EDITOR_SOURCE.rglob("*")):
            if path.suffix not in {".css", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            pattern = CSS_SIZE if path.suffix == ".css" else TSX_SIZE
            for match in pattern.finditer(text):
                if float(match.group(1)) >= 11:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                violations.append(
                    f"{path.relative_to(ROOT)}:{line} uses {match.group(1)}px"
                )

        self.assertEqual([], violations, "\n".join(violations))

    def test_editor_body_uses_standard_readable_base_size(self):
        stylesheet = (EDITOR_SOURCE / "index.css").read_text(encoding="utf-8")
        body = re.search(r"body\s*\{(?P<rules>.*?)\}", stylesheet, re.DOTALL)
        self.assertIsNotNone(body)
        size = CSS_SIZE.search(body.group("rules"))
        self.assertIsNotNone(size)
        self.assertGreaterEqual(float(size.group(1)), 16)


if __name__ == "__main__":
    unittest.main()
