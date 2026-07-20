from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
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


def test_component_dependency_plan_endpoint():
    plan = {
        "target": {"package": "blacknode-adapter", "component": "camera"},
        "plan": [
            {"package": "blacknode-camera", "component": "core", "version": "0.1.0", "enabled": True},
            {"package": "blacknode-adapter", "component": "camera", "version": "0.1.0", "enabled": False},
        ],
        "changes": [
            {"package": "blacknode-adapter", "component": "camera", "version": "0.1.0", "enabled": False},
        ],
    }
    with patch.object(server, "bn_component_dependency_plan", return_value=plan) as resolver:
        response = TestClient(server.app).get(
            "/packages/blacknode-adapter/components/camera/dependencies"
        )

    assert response.status_code == 200
    assert response.json() == plan
    resolver.assert_called_once_with("blacknode-adapter", "camera")


def test_template_list_groups_core_and_package_templates(tmp_path: Path):
    core_dir = tmp_path / "core"
    robot_dir = tmp_path / "robot" / "templates"
    core_dir.mkdir()
    robot_dir.mkdir(parents=True)
    (core_dir / "text-pipeline.json").write_text(
        json.dumps(_template("TextInput")), encoding="utf-8",
    )
    (robot_dir / "motion-test.json").write_text(
        json.dumps(_template("Robot")), encoding="utf-8",
    )
    robot_package = SimpleNamespace(
        name="blacknode-robot",
        ok=True,
        templates_dir=str(robot_dir),
        categories={"Robot": "#14b8a6"},
    )

    with (
        patch.object(server, "_TEMPLATES_DIR", str(core_dir)),
        patch.object(server, "installed_packages", return_value=[robot_package]),
    ):
        response = TestClient(server.app).get("/templates")

    assert response.status_code == 200
    templates = {template["slug"]: template for template in response.json()}
    assert templates["text-pipeline"]["group"] == "Core"
    assert templates["text-pipeline"]["group_color"] == "#6366f1"
    assert templates["motion-test"]["group"] == "Robot"
    assert templates["motion-test"]["group_color"] == "#14b8a6"
