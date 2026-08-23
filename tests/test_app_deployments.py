from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from blacknode.app_deployments import (
    APP_DEPLOYMENT_KIND,
    AppDeploymentError,
    build_app_deployment,
    load_app_deployment,
    operator_permissions,
    public_app_deployment,
)
from blacknode.app_packages import APP_PACKAGE_KIND, _app_python_requirements, package_app_deployment
from blacknode.cli import main


def _workflow(*, secret: str = "") -> dict:
    return {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Customer Task",
        "entrypoint": {"node_id": "out", "port": "value"},
        "metadata": {
            "required_packages": ["blacknode-example"],
            "required_components": ["blacknode-example/operator"],
            "required_adapters": ["blacknode-example/operator@mock"],
            "operator_view": {
                "schema_version": 1,
                "id": "customer-task",
                "title": "Customer task",
                "icon": "record",
                "settings": {
                    "groups": [{
                        "id": "connection",
                        "title": "Connection",
                        "items": [{
                            "node_id": "text",
                            "param": "value",
                            "label": "Value",
                            "apply_to": [{"node_id": "mirror", "param": "value"}],
                        }],
                    }],
                },
                "run_target": {"node_id": "out", "port": "value"},
                "sections": [{
                    "id": "controls",
                    "widgets": [
                        {
                            "type": "fields",
                            "id": "fields",
                            "items": [{"node_id": "text", "param": "value", "label": "Value"}],
                        },
                        {
                            "type": "actions",
                            "id": "actions",
                            "items": [{
                                "id": "run",
                                "label": "Run",
                                "updates": [{"node_id": "text", "param": "value", "value": "ready"}],
                                "control": {"node_id": "out", "action": "refresh"},
                                "cook_target": {"node_id": "out", "port": "value"},
                            }],
                        },
                    ],
                }],
            },
        },
        "node_meta": {
            "text": {
                "id": "text",
                "type": "Text",
                "params": {"value": "hello", **({"api_key": secret} if secret else {})},
                "pos": [0, 0],
                "inputs": ["value"],
                "outputs": ["value"],
                "input_types": {"value": "Text"},
                "output_types": {"value": "Text"},
                "input_defaults": {"value": ""},
            },
            "out": {
                "id": "out",
                "type": "Output",
                "params": {},
                "pos": [200, 0],
                "inputs": ["value"],
                "outputs": ["value"],
                "input_types": {"value": "Any"},
                "output_types": {"value": "Any"},
                "input_defaults": {},
            },
            "mirror": {
                "id": "mirror",
                "type": "Text",
                "params": {"value": "hello"},
                "pos": [0, 100],
                "inputs": ["value"],
                "outputs": ["value"],
                "input_types": {"value": "Text"},
                "output_types": {"value": "Text"},
                "input_defaults": {"value": ""},
            },
        },
        "edges": [{"from": "text", "from_port": "value", "to": "out", "to_port": "value"}],
    }


class AppDeploymentTests(unittest.TestCase):
    def test_app_requirements_add_provider_clients_only_for_ai_nodes(self):
        plain = {"apps": [{"workflow": {"node_meta": {"text": {"type": "Text"}}}}]}
        ai = {"apps": [{"workflow": {"node_meta": {"agent": {"type": "AgentLoop"}}}}]}

        plain_requirements = _app_python_requirements(plain, {})
        ai_requirements = _app_python_requirements(ai, {})

        self.assertNotIn("anthropic>=0.25", plain_requirements)
        self.assertNotIn("openai>=1.0", plain_requirements)
        self.assertIn("anthropic>=0.25", ai_requirements)
        self.assertIn("openai>=1.0", ai_requirements)

    def test_bundle_exposes_summary_and_operator_permissions(self):
        manifest = build_app_deployment(
            [("customer.json", _workflow())],
            deployment_id="customer-demo",
        )

        self.assertEqual(manifest["kind"], APP_DEPLOYMENT_KIND)
        self.assertEqual(manifest["start_app"], "customer-task")
        self.assertEqual(manifest["required_packages"], ["blacknode-example"])
        self.assertEqual(manifest["required_components"], ["blacknode-example/operator"])
        self.assertEqual(manifest["required_adapters"], ["blacknode-example/operator@mock"])
        public_app = public_app_deployment(manifest)["apps"][0]
        self.assertNotIn("workflow", public_app)
        self.assertEqual(public_app["icon"], "record")
        permissions = operator_permissions(manifest["apps"][0])
        self.assertEqual(permissions["params"], {("text", "value"), ("mirror", "value")})
        self.assertEqual(permissions["updates"], {("text", "value", '"ready"')})
        self.assertEqual(permissions["controls"], {("out", "refresh", "{}")})
        self.assertEqual(permissions["cooks"], {("out", "value", "once")})

    def test_operator_permissions_include_role_swaps_and_toggle_off_controls(self):
        workflow = _workflow()
        view = workflow["metadata"]["operator_view"]
        view["settings"] = {
            "groups": [{
                "id": "robots",
                "title": "Robots",
                "items": [{
                    "node_id": "text",
                    "param": "value",
                    "label": "Physical roles",
                    "input": "swap",
                    "swap_pairs": [{
                        "left": {"node_id": "text", "param": "value"},
                        "right": {"node_id": "mirror", "param": "value"},
                    }],
                }],
            }],
        }
        actions = next(
            widget["items"]
            for section in view["sections"]
            for widget in section["widgets"]
            if widget["type"] == "actions"
        )
        actions[0]["deactivate_control"] = {
            "node_id": "out",
            "action": "stop-refresh",
        }

        permissions = operator_permissions({"id": "customer-task", "workflow": workflow})

        self.assertIn(("text", "value"), permissions["params"])
        self.assertIn(("mirror", "value"), permissions["params"])
        self.assertIn(("out", "stop-refresh", "{}"), permissions["controls"])

    def test_bundle_rejects_persisted_secrets(self):
        with self.assertRaisesRegex(AppDeploymentError, "persisted secret"):
            build_app_deployment(
                [("customer.json", _workflow(secret="do-not-ship"))],
                deployment_id="customer-demo",
            )

    def test_export_app_cli_writes_reloadable_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflow_path = root / "customer.json"
            output_path = root / "customer.blacknode-app.json"
            workflow_path.write_text(json.dumps(_workflow()), encoding="utf-8")

            code = main([
                "export-app",
                str(workflow_path),
                "--id", "customer-demo",
                "--output", str(output_path),
            ])

            self.assertEqual(code, 0)
            manifest = load_app_deployment(output_path)
            self.assertEqual(manifest["id"], "customer-demo")
            self.assertEqual(manifest["apps"][0]["id"], "customer-task")

    def test_package_app_creates_portable_release_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "blacknode"
            package = root / "packages" / "blacknode-example"
            support_package = root / "packages" / "blacknode-support"
            (root / "python" / "blacknode").mkdir(parents=True)
            (root / "editor-server").mkdir()
            (root / "editor" / "dist" / "assets").mkdir(parents=True)
            package.mkdir(parents=True)
            support_package.mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\nname='blacknode'\nversion='1.0.0'\n", encoding="utf-8")
            (root / "README.md").write_text("Blacknode\n", encoding="utf-8")
            (root / "LICENSE").write_text("test\n", encoding="utf-8")
            (root / "python" / "blacknode" / "__init__.py").write_text("", encoding="utf-8")
            (root / "editor-server" / "server.py").write_text("app = None\n", encoding="utf-8")
            (root / "editor-server" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
            (root / "editor" / "dist" / "index.html").write_text("<main>App</main>", encoding="utf-8")
            (root / "editor" / "dist" / "assets" / "app.js").write_text("export {}", encoding="utf-8")
            (package / "blacknode-package.toml").write_text(
                "[package]\nname='blacknode-example'\nversion='1.0.0'\ncomponent-mode=true\n"
                "[dependencies]\npip=['shared-runtime>=1']\n"
                "[components.operator]\ndefault=true\n"
                "[components.operator.dependencies]\npip=['operator-runtime>=2']\n"
                "requires=[{package='blacknode-support',component='base'}]\n"
                "[components.operator.adapters.mock]\ndefault=true\n"
                "[components.operator.adapters.mock.dependencies]\npip=['mock-runtime>=3']\n"
                "[components.auto]\ndefault=false\nnode-types=['Output']\n"
                "[components.auto.dependencies]\npip=['output-runtime>=4']\n"
                "[components.unused]\ndefault=false\n"
                "[components.unused.dependencies]\npip=['unused-runtime>=5']\n",
                encoding="utf-8",
            )
            (package / "requirements.txt").write_text(
                "shared-runtime>=1\noperator-runtime>=2\nmock-runtime>=3\n"
                "output-runtime>=4\nunused-runtime>=5\n",
                encoding="utf-8",
            )
            (support_package / "blacknode-package.toml").write_text(
                "[package]\nname='blacknode-support'\nversion='1.0.0'\ncomponent-mode=true\n"
                "[components.base]\ndefault=false\n"
                "[components.base.dependencies]\npip=['support-runtime>=6']\n",
                encoding="utf-8",
            )
            (support_package / "requirements.txt").write_text(
                "support-runtime>=6\nunrelated-support-runtime>=7\n",
                encoding="utf-8",
            )
            self._commit_repo(root)
            self._commit_repo(package)
            self._commit_repo(support_package)

            deployment = root / "customer.blacknode-app.json"
            deployment.write_text(
                json.dumps(build_app_deployment([("customer.json", _workflow())], deployment_id="customer-demo")),
                encoding="utf-8",
            )
            output = Path(td) / "customer.blacknode-app.zip"

            result = package_app_deployment(deployment, output, source_root=root)

            self.assertEqual(result, output.resolve())
            with zipfile.ZipFile(result) as archive:
                names = set(archive.namelist())
                self.assertIn("deployment.blacknode-app.json", names)
                self.assertIn("editor/index.html", names)
                self.assertIn("core/python/blacknode/__init__.py", names)
                self.assertIn("server/server.py", names)
                self.assertIn("packages/blacknode-example/blacknode-package.toml", names)
                self.assertIn("packages/blacknode-support/blacknode-package.toml", names)
                self.assertIn("install.ps1", names)
                self.assertIn("install.sh", names)
                self.assertIn("start.ps1", names)
                self.assertIn("start.sh", names)
                self.assertIn("requirements.app.txt", names)
                packaged_deployment = json.loads(archive.read("deployment.blacknode-app.json"))
                self.assertEqual(
                    packaged_deployment["required_components"],
                    [
                        "blacknode-example/auto",
                        "blacknode-example/operator",
                        "blacknode-support/base",
                    ],
                )
                metadata = json.loads(archive.read("blacknode-app-package.json"))
                self.assertEqual(metadata["kind"], APP_PACKAGE_KIND)
                self.assertEqual(
                    set(metadata["revisions"]),
                    {"blacknode", "blacknode-example", "blacknode-support"},
                )
                requirements = archive.read("requirements.app.txt").decode("utf-8").splitlines()
                self.assertEqual(metadata["python_requirements"], requirements)
                self.assertIn("fastapi>=0.110", requirements)
                self.assertIn("shared-runtime>=1", requirements)
                self.assertIn("operator-runtime>=2", requirements)
                self.assertIn("mock-runtime>=3", requirements)
                self.assertIn("output-runtime>=4", requirements)
                self.assertIn("support-runtime>=6", requirements)
                self.assertNotIn("unused-runtime>=5", requirements)
                self.assertNotIn("unrelated-support-runtime>=7", requirements)
                self.assertNotIn("anthropic>=0.25", requirements)
                self.assertNotIn("openai>=1.0", requirements)
                component_state = json.loads(archive.read("packages/.blacknode-components.json"))
                self.assertEqual(
                    component_state,
                    {
                        "schema_version": 1,
                        "packages": {
                            "blacknode-example": {
                                "operator": False,
                                "operator@mock": False,
                                "auto": False,
                                "unused": False,
                            },
                            "blacknode-support": {"base": False},
                        },
                    },
                )
                compile(archive.read("bundle_setup.py"), "bundle_setup.py", "exec")
                run_app_source = archive.read("run_app.py").decode("utf-8")
                compile(run_app_source, "run_app.py", "exec")
                run_app_namespace = {
                    "__file__": str(root / "run_app.py"),
                    "__name__": "blacknode_app_package_test",
                }
                exec(run_app_source, run_app_namespace)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
                    occupied.bind(("127.0.0.1", 0))
                    occupied.listen()
                    occupied_port = occupied.getsockname()[1]
                    selected_port = run_app_namespace["choose_available_port"](
                        "127.0.0.1", occupied_port,
                    )
                self.assertGreater(selected_port, occupied_port)
                self.assertIn('payload.get("mode") != "app"', run_app_source)
                self.assertIn("access_log=False", run_app_source)
                self.assertIn("finally:", run_app_source)
                self.assertIn("server_module._stop_runtime_services()", run_app_source)
                self.assertIn("--no-deps", archive.read("install.ps1").decode("utf-8"))
                self.assertIn("requirements.app.txt", archive.read("install.sh").decode("utf-8"))
                self.assertNotIn("server/requirements.txt", archive.read("install.sh").decode("utf-8"))
                self.assertNotIn(".git", "\n".join(names))

    def test_package_app_cli_routes_manifest_and_output(self):
        expected = Path("customer.blacknode-app.zip").resolve()
        with patch("blacknode.cli.package_app_deployment", return_value=expected) as package:
            code = main([
                "package-app",
                "customer.blacknode-app.json",
                "--output", str(expected),
            ])

        self.assertEqual(code, 0)
        package.assert_called_once_with(
            Path("customer.blacknode-app.json"),
            expected,
            editor_dist=None,
            packages_root=None,
        )

    @staticmethod
    def _commit_repo(path: Path) -> None:
        subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
        subprocess.run(
            [
                "git", "-C", str(path), "-c", "user.email=test@example.com",
                "-c", "user.name=Blacknode Test", "commit", "-q", "-m", "test release",
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
