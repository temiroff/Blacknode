from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import blacknode as bn
from blacknode.learned import registry
from blacknode.mcp import tools as t


VALID_CODE = "def run(text):\n    return {'result': text.upper()}\n"


class CreateNodeTypeTests(unittest.TestCase):
    def tearDown(self):
        for name in (
            "McpEcho",
            "McpList",
            "McpSource",
            "McpDelete",
            "McpNotify",
            "McpRollback",
            "McpStale",
            "McpCategorized",
            "McpPromote",
        ):
            registry.unregister_one(name)
            bn._NODE_REGISTRY.pop(name, None)

    def learned_env(self, root: Path, *, consent: str | None = "1"):
        values = {
            "BLACKNODE_LEARNED_DIR": str(root),
            "BLACKNODE_CONFIG_DIR": str(root / "config"),
        }
        if consent is not None:
            values["BLACKNODE_LEARNED_NODES_CONSENT"] = consent
        return patch.dict(os.environ, values, clear=False)

    def create_valid(self, name: str = "McpEcho", **overrides):
        payload = {
            "name": name,
            "description": "Uppercase text with a reusable learned node.",
            "inputs": ["text:Text"],
            "outputs": ["result:Text"],
            "code": VALID_CODE,
            "requires_network": False,
        }
        payload.update(overrides)
        return t.create_node_type(**payload)

    def test_consent_gate_rejects_when_unset(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp), consent=None):
            os.environ.pop("BLACKNODE_LEARNED_NODES_CONSENT", None)

            result = self.create_valid()

        self.assertEqual(result["status"], "rejected")
        self.assertIn("BLACKNODE_LEARNED_NODES_CONSENT=1", result["reason"])
        self.assertIn("permanent Python node code", result["reason"])
        self.assertIn("Docker sandbox", result["reason"])
        self.assertIn("delete that file to revoke", result["reason"])

    def test_explicit_consent_is_persisted_and_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.learned_env(root, consent="1"), patch.object(t, "_notify_learned_node_event"):
                first = self.create_valid("McpEcho")
            registry.unregister_one("McpEcho")
            with self.learned_env(root, consent=None), patch.object(t, "_notify_learned_node_event"):
                os.environ.pop("BLACKNODE_LEARNED_NODES_CONSENT", None)
                second = self.create_valid("McpSource")

            self.assertEqual(first["status"], "created")
            self.assertEqual(second["status"], "created")
            self.assertTrue((root / "config" / "learned-nodes-consent.json").is_file())

    def test_rejects_invalid_name(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(name="mcpEcho")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("name must match", result["reason"])

    def test_rejects_name_length(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(name="Ab")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("3-40", result["reason"])

    def test_rejects_existing_learned_directory(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            (Path(tmp) / "McpEcho").mkdir()

            result = self.create_valid()

        self.assertEqual(result["status"], "rejected")
        self.assertIn("already exists on disk", result["reason"])

    def test_rejects_builtin_node_name(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(name="Text")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("already exists", result["reason"])

    def test_rejects_invalid_port_format(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(inputs=["Text:Text"])

        self.assertEqual(result["status"], "rejected")
        self.assertIn("'name:Type'", result["reason"])

    def test_rejects_unsupported_port_type(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(outputs=["result:Path"])

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(
            result["reason"],
            "Port type 'Path' not in allowed set: Text, Int, Float, Bool, List, Dict, Any",
        )

    def test_rejects_static_check_failure(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(code="import os\n\ndef run(text):\n    return {'result': text}\n")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("Forbidden import", result["reason"])

    def test_rejects_missing_run_function(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(code="def helper(text):\n    return {'result': text}\n")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("def run", result["reason"])

    def test_rejects_parameter_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(code="def run(value):\n    return {'result': value}\n")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("parameters must match", result["reason"])

    def test_rejects_description_length(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(description="short")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("description", result["reason"])

    def test_create_node_type_accepts_category(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)), patch.object(t, "_notify_learned_node_event"):
            result = self.create_valid("McpCategorized", category="Parsing")

            manifest = json.loads((Path(tmp) / "McpCategorized" / "manifest.json").read_text(encoding="utf-8"))
            listed = t.list_learned_nodes()

        self.assertEqual(result["status"], "created")
        self.assertEqual(result["category"], "Parsing")
        self.assertEqual(manifest["category"], "Parsing")
        self.assertEqual(bn._NODE_REGISTRY["McpCategorized"]._bn_category, "Parsing")
        self.assertEqual(listed["nodes"][0]["category"], "Parsing")

    def test_create_node_type_rejects_invalid_category(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            result = self.create_valid(category="../bad")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("category", result["reason"])

    def test_create_node_type_writes_files_registers_and_cooks_through_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)), patch.object(t, "_notify_learned_node_event"):
            result = self.create_valid()

            self.assertEqual(result["status"], "created")
            node_dir = Path(result["path"])
            self.assertEqual((node_dir / "node.py").read_text(encoding="utf-8"), VALID_CODE)
            manifest = json.loads((node_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["permissions"], {"network": False})
            self.assertEqual(manifest["category"], "Learned")
            self.assertIn("McpEcho", bn._NODE_REGISTRY)
            self.assertEqual(bn._NODE_REGISTRY["McpEcho"]._bn_category, "Learned")

            graph = bn.Graph()
            node = graph.node("McpEcho", text="hi")
            with patch.object(registry.docker_runner, "run_in_container", return_value={"result": "HI"}) as run:
                self.assertEqual(graph.cook(node, "result"), "HI")

            self.assertEqual(run.call_args.kwargs["inputs"], {"text": "hi"})

    def test_create_rolls_back_files_when_registration_fails(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            root = Path(tmp)
            def fail_after_files(name, *, learned_dir=None):
                node_dir = root / name
                self.assertTrue((node_dir / "node.py").is_file())
                self.assertTrue((node_dir / "manifest.json").is_file())
                raise RuntimeError("boom")

            with patch.object(t.learned_registry, "register_one", side_effect=fail_after_files):
                result = self.create_valid("McpRollback")

            self.assertEqual(result["status"], "rejected")
            self.assertFalse((root / "McpRollback").exists())
            self.assertNotIn("McpRollback", bn._NODE_REGISTRY)

    def test_editor_notification_failure_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)):
            with patch.object(t.urllib_request, "urlopen", side_effect=OSError("editor down")):
                result = self.create_valid("McpNotify")

        self.assertEqual(result["status"], "created")

    def test_list_get_source_and_delete_learned_node(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)), patch.object(t, "_notify_learned_node_event"):
            self.create_valid("McpList")
            self.create_valid("McpSource")

            listed = t.list_learned_nodes()
            names = {entry["name"] for entry in listed["nodes"]}
            source = t.get_learned_node_source("McpSource")
            rejected_delete = t.delete_learned_node("McpSource")
            deleted = t.delete_learned_node("McpSource", confirm=True)

            self.assertEqual(listed["count"], 2)
            self.assertEqual(names, {"McpList", "McpSource"})
            self.assertEqual(source["status"], "ok")
            self.assertEqual(source["source"], VALID_CODE)
            self.assertEqual(rejected_delete["status"], "rejected")
            self.assertEqual(deleted["status"], "deleted")
            self.assertFalse((Path(tmp) / "McpSource").exists())
            self.assertNotIn("McpSource", bn._NODE_REGISTRY)

    def test_create_node_type_recovers_from_stale_learned_registry_entry(self):
        with tempfile.TemporaryDirectory() as tmp, self.learned_env(Path(tmp)), patch.object(t, "_notify_learned_node_event"):
            first = self.create_valid("McpStale")
            self.assertEqual(first["status"], "created")
            shutil.rmtree(Path(tmp) / "McpStale")
            self.assertIn("McpStale", bn._NODE_REGISTRY)

            second = self.create_valid("McpStale")

            self.assertEqual(second["status"], "created")
            self.assertTrue((Path(tmp) / "McpStale" / "node.py").is_file())
            self.assertIn("McpStale", bn._NODE_REGISTRY)

    def test_promote_learned_node_writes_custom_node_and_removes_learned_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learned_root = root / "learned"
            with (
                self.learned_env(learned_root),
                patch.object(t, "_REPO_ROOT", root),
                patch.object(t, "_notify_learned_node_event"),
            ):
                created = self.create_valid("McpPromote", category="Parsing")
                promoted = t.promote_learned_node("McpPromote")

                self.assertEqual(created["status"], "created")
                self.assertEqual(promoted["status"], "promoted")
                self.assertEqual(promoted["category"], "Parsing")
                self.assertEqual(promoted["target"], "custom-nodes")
                self.assertTrue((root / "custom-nodes" / "mcp_promote.py").is_file())
                self.assertFalse((learned_root / "McpPromote").exists())
                self.assertIn("McpPromote", bn._NODE_REGISTRY)
                self.assertNotEqual(getattr(bn._NODE_REGISTRY["McpPromote"], "_bn_source", None), "learned")
                self.assertEqual(bn._NODE_REGISTRY["McpPromote"]._bn_category, "Parsing")

                graph = bn.Graph()
                node = graph.node("McpPromote", text="hi")
                self.assertEqual(graph.cook(node, "result"), "HI")

    def test_promote_learned_node_can_keep_learned_source_as_copy_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learned_root = root / "learned"
            with (
                self.learned_env(learned_root),
                patch.object(t, "_REPO_ROOT", root),
                patch.object(t, "_notify_learned_node_event"),
            ):
                created = self.create_valid("McpPromote")
                promoted = t.promote_learned_node("McpPromote", keep_learned=True)

                self.assertEqual(created["status"], "created")
                self.assertEqual(promoted["status"], "promoted")
                self.assertEqual(promoted["category"], "Custom")
                self.assertFalse(promoted["registered"])
                self.assertTrue((root / "custom-nodes" / "mcp_promote.py").is_file())
                self.assertTrue((learned_root / "McpPromote").exists())
                self.assertEqual(getattr(bn._NODE_REGISTRY["McpPromote"], "_bn_source", None), "learned")


if __name__ == "__main__":
    unittest.main()
