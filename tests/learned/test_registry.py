from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blacknode.learned import registry
from blacknode.learned.manifest import ManifestValidationError
from blacknode.node import _NODE_REGISTRY


def write_learned_node(
    root: Path,
    name: str,
    *,
    code: str = "def run(text):\n    return {'result': text.upper()}\n",
    manifest_overrides: dict | None = None,
) -> Path:
    node_dir = root / name
    node_dir.mkdir(parents=True)
    (node_dir / "node.py").write_text(code, encoding="utf-8")
    manifest = {
        "name": name,
        "description": f"{name} learned node for registry tests.",
        "inputs": ["text:Text"],
        "outputs": ["result:Text"],
        "permissions": {"network": False},
        "created_at": "2026-05-24T18:00:00Z",
        "created_by": "unit-test",
        "schema_version": 1,
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    (node_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return node_dir


class LearnedRegistryTests(unittest.TestCase):
    def tearDown(self):
        for name in ("TempLearned", "OtherLearned", "NoHostExec", "SecondLearned"):
            registry.unregister_one(name)

    def test_register_one_registers_docker_delegating_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learned_node(root, "TempLearned")

            manifest = registry.register_one("TempLearned", learned_dir=root)

            fn = _NODE_REGISTRY["TempLearned"]
            self.assertEqual(manifest.name, "TempLearned")
            self.assertEqual(fn._bn_category, "Learned")
            self.assertEqual(fn._bn_source, "learned")
            self.assertEqual(fn._bn_inputs, ["text"])
            self.assertEqual(fn._bn_outputs, ["result"])
            self.assertEqual(fn._bn_permissions, {"network": False})

            with patch.object(registry.docker_runner, "run_in_container", return_value={"result": "HI"}) as run:
                result = fn({"text": "hi", "__node_id__": "n1"})

            self.assertEqual(result, {"result": "HI"})
            call = run.call_args.kwargs
            self.assertIn("def run(text):", call["code"])
            self.assertEqual(call["inputs"], {"text": "hi"})
            self.assertEqual(call["permissions"], {"network": False})

    def test_wrapper_does_not_execute_or_import_user_code_in_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learned_node(
                root,
                "NoHostExec",
                code=(
                    "raise RuntimeError('host imported learned node')\n"
                    "\n"
                    "def run(text):\n"
                    "    return {'result': text}\n"
                ),
            )

            registry.register_one("NoHostExec", learned_dir=root)

            with patch.object(registry.docker_runner, "run_in_container", return_value={"result": "ok"}):
                result = _NODE_REGISTRY["NoHostExec"]({"text": "ok"})

        self.assertEqual(result, {"result": "ok"})

    def test_load_all_loads_valid_and_skips_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learned_node(root, "TempLearned")
            write_learned_node(root, "OtherLearned", manifest_overrides={"name": "Mismatch"})

            report = registry.load_all(root)

        self.assertEqual(report.loaded, ["TempLearned"])
        self.assertIn("OtherLearned", report.skipped)
        self.assertIn("TempLearned", _NODE_REGISTRY)

    def test_two_learned_nodes_keep_distinct_source_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learned_node(
                root,
                "TempLearned",
                code="def run(text):\n    return {'result': 'first:' + text}\n",
            )
            write_learned_node(
                root,
                "SecondLearned",
                code="def run(text):\n    return {'result': 'second:' + text}\n",
            )

            registry.register_one("TempLearned", learned_dir=root)
            registry.register_one("SecondLearned", learned_dir=root)

            seen_code: dict[str, str] = {}

            def fake_run_in_container(*, code, inputs, permissions, node_name=None):
                seen_code[inputs["text"]] = code
                return {"result": inputs["text"]}

            with patch.object(registry.docker_runner, "run_in_container", side_effect=fake_run_in_container):
                self.assertEqual(_NODE_REGISTRY["TempLearned"]({"text": "first"}), {"result": "first"})
                self.assertEqual(_NODE_REGISTRY["SecondLearned"]({"text": "second"}), {"result": "second"})

        self.assertIn("'first:'", seen_code["first"])
        self.assertIn("'second:'", seen_code["second"])
        self.assertNotEqual(seen_code["first"], seen_code["second"])

    def test_register_one_rejects_builtin_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learned_node(root, "Text", manifest_overrides={"description": "Cannot replace built-in Text."})

            with self.assertRaises(ManifestValidationError) as ctx:
                registry.register_one("Text", learned_dir=root)

        self.assertIn("cannot replace built-in", str(ctx.exception))

    def test_unregister_one_removes_learned_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learned_node(root, "TempLearned")
            registry.register_one("TempLearned", learned_dir=root)

        self.assertTrue(registry.unregister_one("TempLearned"))
        self.assertNotIn("TempLearned", _NODE_REGISTRY)
        self.assertFalse(registry.unregister_one("Text"))

    def test_sync_with_disk_unregisters_deleted_learned_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            node_dir = write_learned_node(root, "TempLearned")
            registry.register_one("TempLearned", learned_dir=root)
            for path in node_dir.iterdir():
                path.unlink()
            node_dir.rmdir()

            report = registry.sync_with_disk(root)

        self.assertEqual(report.loaded, [])
        self.assertNotIn("TempLearned", _NODE_REGISTRY)

    def test_sync_with_disk_loads_node_created_by_other_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learned_node(root, "TempLearned")

            report = registry.sync_with_disk(root)

        self.assertEqual(report.loaded, ["TempLearned"])
        self.assertIn("TempLearned", _NODE_REGISTRY)


if __name__ == "__main__":
    unittest.main()
