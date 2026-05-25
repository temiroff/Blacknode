from __future__ import annotations

import json
import os
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402
from blacknode.learned import registry  # noqa: E402


def write_learned_node(root: Path, name: str, *, category: str | None = None) -> None:
    node_dir = root / name
    node_dir.mkdir(parents=True)
    (node_dir / "node.py").write_text("def run():\n    return {'ok': True}\n", encoding="utf-8")
    manifest = {
        "name": name,
        "description": "Editor server learned node test.",
        "inputs": [],
        "outputs": ["ok:Bool"],
        "permissions": {"network": False},
        "created_at": "2026-05-24T18:00:00Z",
        "created_by": "unit-test",
        "schema_version": 1,
    }
    if category:
        manifest["category"] = category
    (node_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class EditorLearnedNodesTests(unittest.TestCase):
    def tearDown(self):
        registry.unregister_one("EditorLearned")
        server._NODE_REGISTRY.pop("EditorLearned", None)
        with server._learned_node_event_lock:
            server._learned_node_event_subscribers.clear()

    def test_internal_added_registers_node_and_broadcasts_sse_event(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"BLACKNODE_LEARNED_DIR": tmp}, clear=False):
            write_learned_node(Path(tmp), "EditorLearned")
            events: queue.Queue = queue.Queue()
            with server._learned_node_event_lock:
                server._learned_node_event_subscribers.append(events)

            client = TestClient(server.app)
            response = client.post("/internal/learned-node-added", json={"name": "EditorLearned"})

            self.assertEqual(response.status_code, 200)
            self.assertIn("EditorLearned", server._NODE_REGISTRY)
            self.assertEqual(events.get_nowait()["type"], "learned_node_added")
            node_defs = client.get("/node-defs").json()
            self.assertEqual(node_defs["EditorLearned"]["category"], "Learned")

    def test_learned_nodes_list_source_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"BLACKNODE_LEARNED_DIR": tmp}, clear=False):
            root = Path(tmp)
            write_learned_node(root, "EditorLearned")
            registry.register_one("EditorLearned", learned_dir=root)
            events: queue.Queue = queue.Queue()
            with server._learned_node_event_lock:
                server._learned_node_event_subscribers.append(events)

            client = TestClient(server.app)
            listed = client.get("/learned-nodes").json()
            source = client.get("/learned-nodes/EditorLearned/source").json()
            deleted = client.delete("/learned-nodes/EditorLearned")

            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["nodes"][0]["name"], "EditorLearned")
            self.assertIn("def run", source["source"])
            self.assertEqual(deleted.status_code, 200)
            self.assertFalse((root / "EditorLearned").exists())
            self.assertEqual(events.get_nowait()["type"], "learned_node_deleted")

    def test_promote_learned_node_writes_custom_node_and_broadcasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learned_root = root / "learned"
            with patch.dict(os.environ, {"BLACKNODE_LEARNED_DIR": str(learned_root)}, clear=False), patch.object(server.mcp_tools, "_REPO_ROOT", root):
                write_learned_node(learned_root, "EditorLearned", category="Parsing")
                registry.register_one("EditorLearned", learned_dir=learned_root)
                events: queue.Queue = queue.Queue()
                with server._learned_node_event_lock:
                    server._learned_node_event_subscribers.append(events)

                client = TestClient(server.app)
                promoted = client.post("/learned-nodes/EditorLearned/promote")

                self.assertEqual(promoted.status_code, 200)
                self.assertEqual(promoted.json()["category"], "Parsing")
                self.assertTrue((root / "custom-nodes" / "editor_learned.py").is_file())
                self.assertFalse((learned_root / "EditorLearned").exists())
                self.assertEqual(events.get_nowait()["type"], "learned_node_deleted")
                node_defs = client.get("/node-defs").json()
                self.assertEqual(node_defs["EditorLearned"]["category"], "Parsing")


if __name__ == "__main__":
    unittest.main()

