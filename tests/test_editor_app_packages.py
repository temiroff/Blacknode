from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER = ROOT / "editor-server"
if str(EDITOR_SERVER) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER))

import server  # noqa: E402


def _saved_app(*, app_id: str = "collect-episodes", title: str = "Collect episodes") -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": title,
        "saved_at": "2026-08-22T12:00:00Z",
        "metadata": {
            "operator_view": {
                "schema_version": 1,
                "id": app_id,
                "title": title,
                "description": "Record a dataset episode.",
                "icon": "record",
                "accent": "#00d8ff",
                "sections": [{"id": "controls", "widgets": []}],
            },
        },
    }


class EditorAppPackageTests(unittest.TestCase):
    def test_lists_only_saved_workflows_with_app_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflows = Path(temporary)
            (workflows / "collect.json").write_text(json.dumps(_saved_app()), encoding="utf-8")
            (workflows / "plain.json").write_text(
                json.dumps({"name": "Plain workflow", "metadata": {}}),
                encoding="utf-8",
            )
            (workflows / "broken.json").write_text("{", encoding="utf-8")

            with patch.object(server, "_WORKFLOWS_DIR", str(workflows)):
                response = TestClient(server.app).get("/app-packages/workflows")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{
            "slug": "collect",
            "name": "Collect episodes",
            "saved_at": "2026-08-22T12:00:00Z",
            "app_id": "collect-episodes",
            "title": "Collect episodes",
            "description": "Record a dataset episode.",
            "icon": "record",
            "accent": "#00d8ff",
        }])

    def test_packages_selected_apps_and_returns_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflows = root / "workflows"
            dist = root / "dist"
            workflows.mkdir()
            dist.mkdir()
            (dist / "index.html").write_text("<main>App</main>", encoding="utf-8")
            (workflows / "collect.json").write_text(json.dumps(_saved_app()), encoding="utf-8")

            def fake_export(paths, output, **options):
                self.assertEqual([Path(path).name for path in paths], ["collect.json"])
                self.assertEqual(options["deployment_id"], "customer-suite")
                self.assertEqual(options["start_app"], "collect-episodes")
                Path(output).write_text("{}", encoding="utf-8")
                return Path(output)

            def fake_package(manifest, output, **options):
                self.assertEqual(Path(manifest).name, "deployment.blacknode-app.json")
                self.assertEqual(options["editor_dist"], dist)
                Path(output).write_bytes(b"portable-app-zip")
                return Path(output)

            with (
                patch.object(server, "_WORKFLOWS_DIR", str(workflows)),
                patch.object(server, "export_app_deployment", side_effect=fake_export),
                patch.object(server, "load_app_deployment", return_value={"id": "customer-suite"}),
                patch.object(server, "_build_app_editor_assets", return_value=dist),
                patch.object(server, "package_app_deployment", side_effect=fake_package),
            ):
                response = TestClient(server.app).post("/app-packages", json={
                    "workflow_slugs": ["collect"],
                    "deployment_id": "customer-suite",
                    "name": "Customer suite",
                    "start_app": "collect-episodes",
                })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"portable-app-zip")
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertEqual(
            response.headers["content-disposition"],
            'attachment; filename="customer-suite.blacknode-app.zip"',
        )
        self.assertEqual(response.headers["x-blacknode-app-count"], "1")

    def test_requires_a_saved_workflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(server, "_WORKFLOWS_DIR", temporary):
                response = TestClient(server.app).post("/app-packages", json={
                    "workflow_slugs": ["missing"],
                    "deployment_id": "customer-suite",
                })

        self.assertEqual(response.status_code, 404)
        self.assertIn("Save it before packaging", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
