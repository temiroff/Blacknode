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
from artifact_store import ArtifactStore  # noqa: E402
from device_registry import DeviceRegistry  # noqa: E402
from project_store import ProjectStore  # noqa: E402


class EditorProjectApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.root = root
        self.workflows = root / "workflows"
        self.workflows.mkdir()
        self.templates = root / "templates"
        self.templates.mkdir()
        self._original_workflows_dir = server._WORKFLOWS_DIR
        self._original_templates_dir = server._TEMPLATES_DIR
        self._original_starter_kits = server._PROJECT_STARTER_KITS
        self._original_project_store = server._project_store
        self._original_artifact_store = server._artifact_store
        self._original_device_registry = server._device_registry
        server._WORKFLOWS_DIR = str(self.workflows)
        server._TEMPLATES_DIR = str(self.templates)
        server._PROJECT_STARTER_KITS = {
            "robot_learning": {
                "collect": {
                    "template_slug": "starter-collect",
                    "name": "Collect demonstrations",
                },
            },
        }
        server._project_store = ProjectStore(root / ".blacknode" / "projects.json")
        server._artifact_store = ArtifactStore(root / ".blacknode" / "artifacts.json")
        server._device_registry = DeviceRegistry(root / ".blacknode" / "devices.json")

    def tearDown(self):
        server._WORKFLOWS_DIR = self._original_workflows_dir
        server._TEMPLATES_DIR = self._original_templates_dir
        server._PROJECT_STARTER_KITS = self._original_starter_kits
        server._project_store = self._original_project_store
        server._artifact_store = self._original_artifact_store
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

    def test_project_created_before_artifacts_loads_with_empty_references(self):
        server._project_store.path.parent.mkdir(parents=True)
        server._project_store.path.write_text(json.dumps({
            "schema_version": 1,
            "projects": [{
                "id": "legacy",
                "name": "Legacy",
                "description": "",
                "workflow_slugs": [],
                "device_ids": [],
                "active_workflow_slug": None,
                "created_at": "2026-07-24T20:00:00+00:00",
                "updated_at": "2026-07-24T20:00:00+00:00",
            }],
        }), encoding="utf-8")

        project = self.client.get("/projects/legacy")

        self.assertEqual(project.status_code, 200)
        self.assertEqual(project.json()["artifact_ids"], [])
        self.assertEqual(project.json()["artifacts"], [])
        self.assertIsNone(project.json()["starter_kit"])

    def test_guided_starter_materializes_links_and_reuses_saved_workflow(self):
        (self.templates / "starter-collect.json").write_text(json.dumps({
            "kind": "blacknode.workflow",
            "schema_version": 1,
            "name": "Starter collection",
            "entrypoint": {"node_id": "out", "port": "value"},
            "metadata": {
                "template": True,
                "description": "Safe starter fixture",
            },
            "node_meta": {
                "out": {
                    "id": "out",
                    "type": "Output",
                    "pos": [0, 0],
                    "params": {"label": "Result"},
                    "inputs": ["value"],
                    "outputs": [],
                    "input_types": {"value": "Any"},
                    "output_types": {},
                    "input_defaults": {},
                },
            },
            "edges": [],
        }), encoding="utf-8")
        project = self.client.post("/projects", json={
            "name": "Guided Arm",
            "starter_kit": "robot_learning",
        }).json()

        created = self.client.post(
            f"/projects/{project['id']}/starter-workflows/collect",
        )
        reused = self.client.post(
            f"/projects/{project['id']}/starter-workflows/collect",
        )

        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["created"])
        result = created.json()
        workflow = result["workflow"]
        self.assertEqual(workflow["starter_kit"], "robot_learning")
        self.assertEqual(workflow["starter_stage"], "collect")
        self.assertEqual(workflow["source_template"], "starter-collect")
        self.assertEqual(result["project"]["workflow_slugs"], [workflow["slug"]])
        self.assertEqual(
            result["project"]["active_workflow_slug"],
            workflow["slug"],
        )
        saved = json.loads(
            (self.workflows / f"{workflow['slug']}.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertNotIn("template", saved["metadata"])
        self.assertEqual(saved["metadata"]["project_id"], project["id"])
        self.assertEqual(reused.status_code, 200)
        self.assertFalse(reused.json()["created"])
        self.assertEqual(
            reused.json()["workflow"]["slug"],
            workflow["slug"],
        )

    def test_custom_project_does_not_materialize_starter_workflows(self):
        project = self.client.post("/projects", json={
            "name": "Custom",
        }).json()
        response = self.client.post(
            f"/projects/{project['id']}/starter-workflows/collect",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("Enable", response.json()["detail"])

    def test_starter_prefills_dataset_policy_and_safe_runtime_defaults(self):
        project = server._project_store.create(
            name="Prefilled",
            starter_kit="robot_learning",
        )
        dataset_path = self.root / "datasets" / "demo"
        dataset_path.mkdir(parents=True)
        policy_path = self.root / "policies" / "demo"
        policy_path.mkdir(parents=True)
        artifacts = server._artifact_store.import_value([
            {
                "kind": "blacknode.episode-dataset",
                "dataset_id": "demo",
                "path": str(dataset_path),
                "fps": 30,
                "task": "Pick",
                "episode_count": 4,
            },
            {
                "kind": "blacknode.policy-artifact",
                "path": str(policy_path),
                "policy_type": "act",
            },
        ])
        project = server._project_store.link_artifact_ids(
            project["id"],
            [artifact["id"] for artifact in artifacts],
        )
        training = {
            "node_meta": {
                "dataset_browser": {
                    "params": {"dataset": {}, "root": "", "dataset_id": ""},
                    "input_defaults": {
                        "dataset": {},
                        "root": "",
                        "dataset_id": "",
                    },
                },
                "training": {
                    "params": {"action": "start", "run_id": "act-training"},
                    "input_defaults": {
                        "action": "start",
                        "run_id": "act-training",
                    },
                },
            },
        }
        simulation = {
            "node_meta": {
                "artifact_path": {
                    "params": {"value": "placeholder"},
                    "input_defaults": {},
                },
                "runtime": {
                    "params": {"action": "start", "run_id": "isaac-policy"},
                    "input_defaults": {
                        "action": "start",
                        "run_id": "isaac-policy",
                    },
                },
            },
        }

        server._configure_project_starter_workflow(training, "train", project)
        server._configure_project_starter_workflow(
            simulation,
            "simulate",
            project,
        )

        browser = training["node_meta"]["dataset_browser"]["params"]
        self.assertEqual(browser["dataset"]["path"], str(dataset_path.resolve()))
        self.assertEqual(browser["dataset_id"], "demo")
        self.assertEqual(
            training["node_meta"]["training"]["params"]["run_id"],
            "prefilled-act",
        )
        self.assertEqual(
            simulation["node_meta"]["artifact_path"]["params"]["value"],
            str(policy_path.resolve()),
        )
        self.assertEqual(
            simulation["node_meta"]["runtime"]["params"]["action"],
            "status",
        )

    def test_artifact_capture_links_dataset_evidence_and_deduplicates(self):
        self._workflow(
            "record",
            "Record",
            node_types=["EpisodeRecorder"],
        )
        project = self.client.post("/projects", json={
            "name": "Dataset Project",
            "workflow_slugs": ["record"],
        }).json()
        dataset_path = Path(self._tmp.name) / "datasets" / "pick-cube"
        dataset_path.mkdir(parents=True)
        payload = {
            "kind": "blacknode.episode-dataset",
            "schema_version": 1,
            "dataset_id": "pick-cube",
            "path": str(dataset_path),
            "task": "Pick cube",
            "fps": 30,
            "episode_count": 2,
            "pairing_token": "must-not-be-indexed",
        }

        first = self.client.post(
            f"/projects/{project['id']}/artifacts/import",
            json={
                "workflow_slug": "record",
                "node_type": "EpisodeRecorder",
                "value": payload,
            },
        )
        second = self.client.post(
            f"/projects/{project['id']}/artifacts/import",
            json={
                "workflow_slug": "record",
                "node_type": "EpisodeRecorder",
                "value": {**payload, "episode_count": 3},
            },
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        result = second.json()["project"]
        self.assertEqual(len(result["artifact_ids"]), 1)
        self.assertEqual(len(result["artifacts"]), 1)
        artifact = result["artifacts"][0]
        self.assertEqual(artifact["artifact_type"], "dataset")
        self.assertEqual(artifact["status"], "completed")
        self.assertEqual(artifact["metadata"]["episode_count"], 3)
        self.assertNotIn("must-not-be-indexed", json.dumps(result))

    def test_newton_run_artifact_is_indexed_as_simulation_evidence(self):
        artifact_path = Path(self._tmp.name) / "newton-runs" / "newton-run-a.json"
        artifact_path.parent.mkdir(parents=True)
        artifact_path.write_text("{}", encoding="utf-8")
        artifacts = server._artifact_store.import_value({
            "kind": "blacknode.newton-run-artifact",
            "schema_version": 1,
            "artifact_id": "newton-run-0123456789abcdefabcd",
            "name": "SO-101 tracking",
            "path": str(artifact_path),
            "run_id": "newton-scene",
            "source": "rosbridge:arm",
            "joint_names": ["shoulder"],
            "summary": {"sample_count": 120, "max_abs_error": 0.04},
        })
        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0]
        self.assertEqual(artifact["artifact_type"], "simulation_run")
        self.assertEqual(artifact["provider"], "blacknode-newton")
        self.assertEqual(artifact["status"], "completed")
        self.assertEqual(artifact["metadata"]["summary"]["sample_count"], 120)

    def test_existing_manifest_can_be_added_and_unlinked_without_deletion(self):
        project = self.client.post("/projects", json={
            "name": "Existing Policy",
        }).json()
        policy_path = Path(self._tmp.name) / "policies" / "act-v1"
        policy_path.mkdir(parents=True)
        manifest = policy_path / "manifest.json"
        manifest.write_text(json.dumps({
            "kind": "blacknode.policy-artifact",
            "schema_version": 1,
            "path": str(policy_path),
            "policy_type": "act",
            "step": 1200,
        }), encoding="utf-8")

        added = self.client.post(
            f"/projects/{project['id']}/artifacts/inspect",
            json={"path": str(policy_path)},
        )

        self.assertEqual(added.status_code, 200)
        linked = added.json()["project"]
        self.assertEqual(linked["artifacts"][0]["artifact_type"], "policy")
        artifact_id = linked["artifacts"][0]["id"]
        unlinked = self.client.patch(
            f"/projects/{project['id']}",
            json={"artifact_ids": []},
        )
        self.assertEqual(unlinked.status_code, 200)
        self.assertEqual(unlinked.json()["artifacts"], [])
        self.assertTrue(manifest.exists())
        self.assertTrue(
            server._artifact_store.list([artifact_id]),
            "Unlinking must not delete the provider-owned artifact reference",
        )

    def test_native_dataset_manifest_and_run_outputs_map_to_typed_evidence(self):
        self._workflow(
            "learning",
            "Learning",
            node_types=["EpisodeRecorder", "ACTTraining", "IsaacPolicyRuntime"],
        )
        project = self.client.post("/projects", json={
            "name": "Learning Project",
            "workflow_slugs": ["learning"],
        }).json()

        dataset_path = self.root / "datasets" / "pick-cube"
        dataset_path.mkdir(parents=True)
        (dataset_path / "dataset.json").write_text(json.dumps({
            "kind": "blacknode.episode-dataset",
            "schema_version": 1,
            "dataset_id": "pick-cube",
            "fps": 30,
            "task": "Pick cube",
            "episodes": [{"frames": 50}, {"frames": 60}],
        }), encoding="utf-8")
        inspected = self.client.post(
            f"/projects/{project['id']}/artifacts/inspect",
            json={"path": str(dataset_path), "workflow_slug": "learning"},
        )
        self.assertEqual(inspected.status_code, 200)
        dataset = inspected.json()["artifacts"][0]
        self.assertEqual(dataset["metadata"]["episode_count"], 2)
        self.assertEqual(dataset["metadata"]["total_frames"], 110)

        output_dir = self.root / "training" / "act-run"
        output_dir.mkdir(parents=True)
        checkpoint = output_dir / "checkpoint-000100.pt"
        checkpoint.touch()
        policy_path = self.root / "policies" / "act-run"
        policy_path.mkdir(parents=True)
        simulation_log = self.root / "runs" / "isaac.jsonl"
        simulation_log.parent.mkdir(parents=True)
        simulation_log.touch()
        captured = self.client.post(
            f"/projects/{project['id']}/artifacts/import",
            json={
                "workflow_slug": "learning",
                "node_type": "IsaacPolicyRuntime",
                "value": [
                    {
                        "kind": "blacknode.training-job",
                        "run_id": "act-run",
                        "output_dir": str(output_dir),
                        "checkpoint": str(checkpoint),
                        "phase": "training",
                        "running": True,
                        "step": 100,
                        "steps": 1000,
                    },
                    {
                        "kind": "blacknode.policy-artifact",
                        "path": str(policy_path),
                        "policy_type": "act",
                    },
                    {
                        "kind": "blacknode.policy-runtime",
                        "run_id": "isaac-eval",
                        "log_path": str(simulation_log),
                        "phase": "stopped",
                        "running": False,
                    },
                ],
            },
        )
        self.assertEqual(captured.status_code, 200)
        artifacts = captured.json()["project"]["artifacts"]
        self.assertEqual(
            {item["artifact_type"] for item in artifacts},
            {"dataset", "training_run", "checkpoint", "policy", "simulation_run"},
        )
        training = next(
            item for item in artifacts if item["artifact_type"] == "training_run"
        )
        simulation = next(
            item for item in artifacts if item["artifact_type"] == "simulation_run"
        )
        self.assertEqual(training["status"], "running")
        self.assertEqual(simulation["status"], "completed")

    def test_artifact_workflow_must_belong_to_project(self):
        project = self.client.post("/projects", json={"name": "Scoped"}).json()
        response = self.client.post(
            f"/projects/{project['id']}/artifacts/import",
            json={
                "workflow_slug": "other-workflow",
                "value": {
                    "kind": "blacknode.training-job",
                    "run_id": "run-1",
                },
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("linked", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
