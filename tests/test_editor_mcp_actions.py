from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from blacknode.mcp import tools


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


def test_saved_workflow_editor_action_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_WORKFLOWS_DIR", str(tmp_path))
    with server._editor_action_lock:
        server._editor_action_queue.clear()

    workflow = tools.create_workflow("Saved Demo")
    (tmp_path / "Saved_Demo.json").write_text(json.dumps(workflow), encoding="utf-8")

    client = TestClient(server.app)
    listed = client.get("/workflows")
    assert listed.status_code == 200
    assert listed.json() == [{"slug": "Saved_Demo", "name": "Saved Demo", "saved_at": ""}]

    queued = client.post("/editor/actions/load-saved-workflow-tab", json={"slug": "Saved_Demo"})
    assert queued.status_code == 200
    assert queued.json()["action"]["type"] == "load_saved_workflow_tab"

    actions = client.get("/editor/actions").json()["actions"]
    assert len(actions) == 1
    assert actions[0]["payload"]["slug"] == "Saved_Demo"
    assert actions[0]["payload"]["organize"] is True

    assert client.get("/editor/actions").json()["actions"] == []


def test_editor_management_actions_queue():
    with server._editor_action_lock:
        server._editor_action_queue.clear()

    client = TestClient(server.app)
    assert client.post("/editor/actions/organize-graph").status_code == 200
    assert client.post("/editor/actions/rename-tab", json={"name": "Renamed"}).status_code == 200
    assert client.post("/editor/actions/close-tab").status_code == 200

    actions = client.get("/editor/actions").json()["actions"]
    assert [action["type"] for action in actions] == [
        "organize_graph",
        "rename_tab",
        "close_tab",
    ]
    assert actions[1]["payload"] == {"name": "Renamed"}

