from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


def test_onboarding_is_workspace_local_and_persistent(tmp_path: Path):
    state_path = tmp_path / ".blacknode" / "onboarding.json"
    state = {"package_welcome_seen": False}

    with (
        patch.object(server, "_ONBOARDING_PATH", state_path),
        patch.object(server, "_onboarding_state", state),
    ):
        client = TestClient(server.app)
        first = client.get("/settings/onboarding")
        saved = client.post("/settings/onboarding", json={"package_welcome_seen": True})

        assert first.status_code == 200
        assert first.json() == {"package_welcome_seen": False}
        assert saved.status_code == 200
        assert saved.json() == {"ok": True, "package_welcome_seen": True}
        assert json.loads(state_path.read_text(encoding="utf-8")) == {
            "package_welcome_seen": True,
        }


def test_missing_workspace_state_shows_welcome(tmp_path: Path):
    with patch.object(server, "_ONBOARDING_PATH", tmp_path / "missing.json"):
        server._load_onboarding_state()
        assert server._onboarding_state == {"package_welcome_seen": False}
