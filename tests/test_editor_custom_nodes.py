from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import sys


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"
if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


class EditorCustomNodeSourceTests(unittest.TestCase):
    def test_reads_only_a_named_python_file_from_custom_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp) / "custom-nodes"
            custom_dir.mkdir()
            source = "from blacknode.node import node\n"
            (custom_dir / "tutorial.py").write_text(source, encoding="utf-8")

            with patch.object(server, "_CUSTOM_NODES_DIR", str(custom_dir)):
                response = TestClient(server.app).get(
                    "/custom-nodes/source",
                    params={"filename": "tutorial.py"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["filename"], "tutorial.py")
            self.assertEqual(response.json()["code"], source)

    def test_source_endpoint_does_not_escape_custom_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom_dir = root / "custom-nodes"
            custom_dir.mkdir()
            (root / "secret.py").write_text("SECRET", encoding="utf-8")

            with patch.object(server, "_CUSTOM_NODES_DIR", str(custom_dir)):
                response = TestClient(server.app).get(
                    "/custom-nodes/source",
                    params={"filename": "../secret.py"},
                )

            self.assertEqual(response.status_code, 404)
            self.assertNotIn("SECRET", response.text)

    def test_refresh_canvas_reloads_schema_and_removes_only_invalid_edges(self):
        type_name = "RefreshSchemaTutorialNode"
        previous_fn = server._NODE_REGISTRY.get(type_name)
        original_session = server._session
        try:
            with tempfile.TemporaryDirectory() as tmp:
                custom_dir = Path(tmp) / "custom-nodes"
                custom_dir.mkdir()
                source_path = custom_dir / "tutorial.py"
                source_path.write_text(
                    "from blacknode.node import Text, node\n"
                    "@node(name='RefreshSchemaTutorialNode', inputs={'text': Text}, outputs={'result': Text})\n"
                    "def tutorial(text):\n"
                    "    return text\n",
                    encoding="utf-8",
                )
                self.assertTrue(server.load_node_file(source_path)["ok"])

                session = server.Session()
                session.node_meta["tutorial-1"] = {
                    "id": "tutorial-1",
                    "type": type_name,
                    "params": {"text": "hello", "label": "My first node"},
                    "pos": [0, 0],
                    "inputs": ["text"],
                    "outputs": ["result"],
                    "input_types": {"text": "Text"},
                    "output_types": {"result": "Text"},
                    "input_defaults": {},
                    "promoted_inputs": None,
                    "promoted_outputs": None,
                }
                session.graph._nodes["tutorial-1"] = {
                    "type": type_name,
                    "params": {"text": "hello", "label": "My first node"},
                }
                session.graph._edges = [{
                    "from": "tutorial-1",
                    "from_port": "result",
                    "to": "tutorial-1",
                    "to_port": "text",
                }]

                source_path.write_text(
                    "from blacknode.node import Int, List, node\n"
                    "@node(name='RefreshSchemaTutorialNode', inputs={'messages': List}, outputs={'count': Int})\n"
                    "def tutorial(messages):\n"
                    "    return len(messages or [])\n",
                    encoding="utf-8",
                )

                with (
                    patch.object(server, "_CUSTOM_NODES_DIR", str(custom_dir)),
                    patch.object(server, "_session", session),
                    patch.object(server, "_save"),
                ):
                    response = TestClient(server.app).post("/graph/refresh-node-schemas")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["updated_nodes"][0]["added_inputs"], ["messages"])
                self.assertEqual(payload["updated_nodes"][0]["removed_inputs"], ["text"])
                self.assertEqual(payload["removed_edges"], [{
                    "from": "tutorial-1",
                    "from_port": "result",
                    "to": "tutorial-1",
                    "to_port": "text",
                }])
                self.assertEqual(session.node_meta["tutorial-1"]["inputs"], ["messages"])
                self.assertEqual(session.node_meta["tutorial-1"]["outputs"], ["count"])
                self.assertNotIn("text", session.node_meta["tutorial-1"]["params"])
                self.assertEqual(session.node_meta["tutorial-1"]["params"]["label"], "My first node")
                self.assertEqual(session.graph._edges, [])
        finally:
            server._session = original_session
            if previous_fn is None:
                server._NODE_REGISTRY.pop(type_name, None)
            else:
                server._NODE_REGISTRY[type_name] = previous_fn


def test_editor_routes_saved_custom_nodes_into_script_editor():
    inspector = (ROOT / "editor" / "src" / "components" / "Inspector.tsx").read_text(encoding="utf-8")
    palette = (ROOT / "editor" / "src" / "components" / "NodePalette.tsx").read_text(encoding="utf-8")
    script = (ROOT / "editor" / "src" / "components" / "ScriptEditor.tsx").read_text(encoding="utf-8")

    assert "Edit source" in inspector
    assert "customNodeFile" in inspector
    assert "initialFilename" in palette
    assert "getCustomNodeSource(initialFilename)" in script


def test_editor_exposes_canvas_schema_refresh_control():
    app = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    api = (ROOT / "editor" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "Refresh canvas" in app
    assert "api.refreshCanvasSchemas()" in app
    assert "'/graph/refresh-node-schemas'" in api


if __name__ == "__main__":
    unittest.main()
