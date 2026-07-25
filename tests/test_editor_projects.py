from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"

if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402
from device_registry import DeviceRegistry  # noqa: E402
from project_store import ProjectStore  # noqa: E402


class EditorProjectApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.workflows = root / "workflows"
        self.workflows.mkdir()
        self._original_workflows_dir = server._WORKFLOWS_DIR
        self._original_project_store = server._project_store
        self._original_device_registry = server._device_registry
        server._WORKFLOWS_DIR = str(self.workflows)
        server._project_store = ProjectStore(root / ".blacknode" / "projects.json")
        server._device_registry = DeviceRegistry(root / ".blacknode" / "devices.json")

    def tearDown(self):
        server._WORKFLOWS_DIR = self._original_workflows_dir
        server._project_store = self._original_project_store
        server._device_registry = self._original_device_registry
        self._tmp.cleanup()

    def _workflow(
        self,
        slug: str,
        name: str,
        *,
        node_types: list[str],
        calibration: bool = False,
    ) -> None:
        metadata = {"required_capabilities": ["joint_group"]}
        if calibration:
            metadata["device_calibration"] = {
                "profile_id": "so_arm101",
                "hardware_id": "USB-SERIAL-42",
            }
        payload = {
            "kind": "blacknode.workflow",
            "schema_version": 1,
            "name": name,
            "saved_at": "2026-07-24T20:00:00",
            "metadata": metadata,
            "node_meta": {
                f"node-{index}": {"id": f"node-{index}", "type": node_type}
                for index, node_type in enumerate(node_types)
            },
            "edges": [],
        }
        (self.workflows / f"{slug}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def _device(self) -> dict:
        return server._device_registry.pair(
            name="Follower — 31741",
            base_url="http://192.168.1.87:8767",
            token="hardware-secret",
            runtime_token="runtime-secret",
            status={"device_id": "arm-31741"},
        )

    def test_project_round_trip_hydrates_linked_resources_without_tokens(self):
        self._workflow(
            "record-and-train",
            "Record and Train",
            node_types=["Robot", "EpisodeRecorder", "ACTTraining"],
            calibration=True,
        )
        device = self._device()

        created = self.client.post("/projects", json={
            "name": "Leader Follower Demo",
            "description": "Two-arm project",
            "workflow_slugs": ["record-and-train"],
            "device_ids": [device["id"]],
        })

        self.assertEqual(created.status_code, 200)
        project = created.json()
        self.assertEqual(project["id"], "leader-follower-demo")
        self.assertEqual(project["active_workflow_slug"], "record-and-train")
        self.assertEqual(project["workflows"][0]["name"], "Record and Train")
        self.assertEqual(project["workflows"][0]["stages"], ["collect", "train"])
        self.assertTrue(project["workflows"][0]["requires_calibration"])
        self.assertEqual(
            project["workflows"][0]["calibration"]["hardware_id"],
            "USB-SERIAL-42",
        )
        self.assertEqual(project["devices"][0]["name"], "Follower — 31741")
        serialized = json.dumps(project)
        self.assertNotIn("hardware-secret", serialized)
        self.assertNotIn("runtime-secret", serialized)

        listed = self.client.get("/projects").json()
        self.assertEqual([item["id"] for item in listed], ["leader-follower-demo"])

    def test_rename_keeps_stable_project_id_and_workflow_rename_updates_link(self):
        self._workflow("first-workflow", "First Workflow", node_types=["Output"])
        project = self.client.post("/projects", json={
            "name": "Original Project",
            "workflow_slugs": ["first-workflow"],
        }).json()

        renamed_project = self.client.patch(
            f"/projects/{project['id']}",
            json={"name": "Renamed Project"},
        )
        self.assertEqual(renamed_project.status_code, 200)
        self.assertEqual(renamed_project.json()["id"], "original-project")
        self.assertEqual(renamed_project.json()["name"], "Renamed Project")

        renamed_workflow = self.client.patch(
            "/workflows/first-workflow",
            json={"name": "Second Workflow"},
        )
        self.assertEqual(renamed_workflow.status_code, 200)
        next_slug = renamed_workflow.json()["slug"]
        fetched = self.client.get("/projects/original-project").json()
        self.assertEqual(fetched["workflow_slugs"], [next_slug])
        self.assertEqual(fetched["active_workflow_slug"], next_slug)

    def test_missing_links_are_visible_and_can_be_removed(self):
        project = self.client.post("/projects", json={
            "name": "Offline Project",
            "workflow_slugs": ["missing-workflow"],
            "device_ids": ["missing-device"],
        }).json()

        self.assertFalse(project["workflows"][0]["exists"])
        self.assertFalse(project["devices"][0]["exists"])

        updated = self.client.patch(
            f"/projects/{project['id']}",
            json={"workflow_slugs": [], "device_ids": []},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["workflows"], [])
        self.assertEqual(updated.json()["devices"], [])
        self.assertIsNone(updated.json()["active_workflow_slug"])

    def test_active_workflow_must_be_linked_and_delete_is_explicit(self):
        invalid = self.client.post("/projects", json={
            "name": "Invalid",
            "workflow_slugs": ["one"],
            "active_workflow_slug": "two",
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("active_workflow_slug", invalid.json()["detail"])

        created = self.client.post("/projects", json={"name": "Disposable"}).json()
        deleted = self.client.delete(f"/projects/{created['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.get(f"/projects/{created['id']}").status_code,
            404,
        )

    def test_duplicate_names_receive_distinct_stable_ids(self):
        first = self.client.post("/projects", json={"name": "Demo"}).json()
        second = self.client.post("/projects", json={"name": "Demo"}).json()
        self.assertEqual(first["id"], "demo")
        self.assertEqual(second["id"], "demo-2")


if __name__ == "__main__":
    unittest.main()
