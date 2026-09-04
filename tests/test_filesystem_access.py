from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER = ROOT / "editor-server"
if str(EDITOR_SERVER) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER))

from filesystem_access import browse_listing, normalize_extensions  # noqa: E402


class FilesystemAccessTests(unittest.TestCase):
    def test_normalizes_and_validates_extensions(self):
        self.assertEqual(normalize_extensions(["USD", ".usda"]), frozenset({".usd", ".usda"}))
        with self.assertRaisesRegex(ValueError, "Invalid file extension"):
            normalize_extensions(["../secret"])

    def test_restricted_listing_stays_inside_root(self):
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(root_dir).resolve()
            (root / "scene.usd").write_text("scene", encoding="utf-8")
            (root / "notes.txt").write_text("notes", encoding="utf-8")

            listing = browse_listing(str(root), ["usd"], roots=(root,))

            self.assertEqual([item["name"] for item in listing["entries"]], ["scene.usd"])
            self.assertEqual(listing["parent"], "")
            with self.assertRaises(PermissionError):
                browse_listing(outside_dir, ["usd"], roots=(root,))


if __name__ == "__main__":
    unittest.main()
