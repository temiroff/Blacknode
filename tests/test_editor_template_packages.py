from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from blacknode.node import _NODE_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


def _template(node_type: str) -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Missing Package",
        "saved_at": "2026-06-12T00:00:00",
        "entrypoint": {"node_id": "node", "port": "value"},
        "metadata": {
            "template": True,
            "required_packages": ["blacknode-cuda"],
        },
        "node_meta": {
            "node": {
                "id": "node",
                "type": node_type,
                "params": {},
                "pos": [0, 0],
                "inputs": [],
                "outputs": ["value"],
                "input_types": {},
                "output_types": {"value": "Any"},
                "input_defaults": {},
            },
        },
        "edges": [],
    }


def test_template_load_returns_installable_missing_package(tmp_path):
    path = tmp_path / "missing-cuda.json"
    path.write_text(json.dumps(_template("CUDAKernelLab")), encoding="utf-8")
    registered = _NODE_REGISTRY.pop("CUDAKernelLab", None)
    try:
        with (
            patch.object(server, "_TEMPLATES_DIR", str(tmp_path)),
            patch.object(server, "installed_packages", return_value=[]),
        ):
            response = TestClient(server.app).post("/templates/missing-cuda/load")
    finally:
        if registered is not None:
            _NODE_REGISTRY["CUDAKernelLab"] = registered

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "missing_packages"
    assert detail["missing_node_types"] == ["CUDAKernelLab"]
    assert detail["missing_packages"] == [{
        "name": "blacknode-cuda",
        "git_url": "https://github.com/temiroff/blacknode-cuda.git",
        "node_types": ["CUDAKernelLab"],
        "source": "template",
        "installed": False,
        "load_error": "",
    }]
