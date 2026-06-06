from __future__ import annotations

import json
import subprocess
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


def test_run_snapshot_secret_redaction():
    data = {
        "node_meta": {
            "model": {
                "params": {
                    "api_key": "sk-test",
                    "token": "token-test",
                    "nested": [{"password": "pw-test", "value": "visible"}],
                }
            }
        }
    }

    redacted = server._redact_run_snapshot_secrets(data)

    params = redacted["node_meta"]["model"]["params"]
    assert params["api_key"] == "[redacted]"
    assert params["token"] == "[redacted]"
    assert params["nested"][0]["password"] == "[redacted]"
    assert params["nested"][0]["value"] == "visible"


def test_stop_driver_clears_status_and_terminates_process_tree(monkeypatch):
    class FakeProc:
        pid = 1234

        def __init__(self):
            self.waited = False

        def poll(self):
            return None

        def wait(self, timeout):
            self.waited = True
            return 0

    proc = FakeProc()
    calls = []
    monkeypatch.setattr(server.os, "name", "nt")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )
    server._driver_procs["telegram"] = proc
    server._driver_status["telegram"] = {"state": "listening"}

    server._stop_driver_proc("telegram")

    assert "telegram" not in server._driver_procs
    assert "telegram" not in server._driver_status
    assert calls[0][0] == ["taskkill", "/PID", "1234", "/T", "/F"]
    assert proc.waited is True
