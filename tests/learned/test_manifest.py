from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from blacknode.learned.manifest import ManifestValidationError, load_manifest, validate_manifest


def valid_manifest(**overrides):
    data = {
        "name": "ParseRSS",
        "description": "Parse an RSS feed URL into entries.",
        "inputs": ["url:Text"],
        "outputs": ["entries:List"],
        "permissions": {"network": True},
        "created_at": "2026-05-24T18:00:00Z",
        "created_by": "unit-test",
        "schema_version": 1,
    }
    data.update(overrides)
    return data


class LearnedManifestTests(unittest.TestCase):
    def test_valid_manifest_normalizes_to_dataclass(self):
        manifest = validate_manifest(valid_manifest())

        self.assertEqual(manifest.name, "ParseRSS")
        self.assertEqual(manifest.input_names, ("url",))
        self.assertEqual(manifest.output_names, ("entries",))
        self.assertEqual(manifest.permissions, {"network": True})

    def test_load_manifest_reads_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(valid_manifest()), encoding="utf-8")

            manifest = load_manifest(path)

        self.assertEqual(manifest.name, "ParseRSS")

    def test_rejects_missing_required_keys(self):
        data = valid_manifest()
        data.pop("outputs")

        with self.assertRaises(ManifestValidationError) as ctx:
            validate_manifest(data)

        self.assertIn("missing required keys", str(ctx.exception))

    def test_rejects_unknown_top_level_keys(self):
        with self.assertRaises(ManifestValidationError) as ctx:
            validate_manifest(valid_manifest(extra=True))

        self.assertIn("unknown keys", str(ctx.exception))

    def test_rejects_invalid_name(self):
        with self.assertRaises(ManifestValidationError):
            validate_manifest(valid_manifest(name="parse_rss"))

    def test_rejects_short_description(self):
        with self.assertRaises(ManifestValidationError):
            validate_manifest(valid_manifest(description="too short"))

    def test_rejects_invalid_port_declaration(self):
        with self.assertRaises(ManifestValidationError) as ctx:
            validate_manifest(valid_manifest(inputs=["URL:Text"]))

        self.assertIn("'name:Type'", str(ctx.exception))

    def test_rejects_unsupported_port_type(self):
        with self.assertRaises(ManifestValidationError) as ctx:
            validate_manifest(valid_manifest(outputs=["entries:Path"]))

        self.assertIn("unsupported port type", str(ctx.exception))

    def test_rejects_duplicate_port_names(self):
        with self.assertRaises(ManifestValidationError) as ctx:
            validate_manifest(valid_manifest(inputs=["text:Text", "text:Text"]))

        self.assertIn("duplicate port name", str(ctx.exception))

    def test_outputs_must_not_be_empty(self):
        with self.assertRaises(ManifestValidationError):
            validate_manifest(valid_manifest(outputs=[]))

    def test_rejects_extra_permission_categories(self):
        with self.assertRaises(ManifestValidationError) as ctx:
            validate_manifest(valid_manifest(permissions={"network": False, "filesystem": True}))

        self.assertIn("unknown permissions", str(ctx.exception))

    def test_rejects_non_boolean_network_permission(self):
        with self.assertRaises(ManifestValidationError):
            validate_manifest(valid_manifest(permissions={"network": "no"}))

    def test_rejects_wrong_schema_version(self):
        with self.assertRaises(ManifestValidationError):
            validate_manifest(valid_manifest(schema_version=2))

    def test_rejects_invalid_created_at(self):
        with self.assertRaises(ManifestValidationError):
            validate_manifest(valid_manifest(created_at="not-a-date"))


if __name__ == "__main__":
    unittest.main()

