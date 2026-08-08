from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"
if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402
import cloud_client  # noqa: E402
import cloud_sessions  # noqa: E402


class EditorCloudTests(unittest.TestCase):
    def setUp(self):
        self.session_store = cloud_sessions.CloudSessionStore()
        self.session_patch = patch.object(server, "_cloud_sessions", self.session_store)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()

    def authenticated_client(self) -> TestClient:
        session_id, _ = self.session_store.create(
            "registered-user-cloud-token-0123456789",
            (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            {
                "id": "user_123",
                "organization_id": "org_123",
                "email": "robot@example.com",
                "display_name": "Robot Builder",
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        client = TestClient(server.app)
        client.cookies.set(server._CLOUD_SESSION_COOKIE, session_id)
        return client

    def test_cloud_status_reports_configuration_without_exposing_key(self):
        with patch.dict(
            os.environ,
            {
                "BLACKNODE_CLOUD_URL": "https://cloud.blacknode.example",
                "BLACKNODE_CLOUD_API_KEY": "private-cloud-key-with-24-characters",
            },
            clear=False,
        ):
            response = TestClient(server.app).get("/cloud/status")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
        self.assertEqual(response.json()["gpu"], "NVIDIA L40S")
        self.assertFalse(response.json()["authenticated"])
        self.assertNotIn("private-cloud-key", response.text)

    def test_cloud_validation_errors_name_the_invalid_fields(self):
        response = SimpleNamespace(
            read=lambda: json.dumps(
                {
                    "detail": [
                        {
                            "loc": ["body", "password"],
                            "msg": "String should have at least 10 characters",
                            "type": "string_too_short",
                        },
                        {
                            "loc": ["body", "email"],
                            "msg": "Value error, enter a valid email address",
                            "type": "value_error",
                        },
                    ]
                }
            ).encode("utf-8")
        )

        message = cloud_client._error_message(response)

        self.assertEqual(
            message,
            "password: String should have at least 10 characters; "
            "email: Value error, enter a valid email address",
        )

    def test_authenticated_cloud_status_refreshes_verification_state(self):
        client = self.authenticated_client()

        def cloud_call(method, path, payload=None, **kwargs):
            self.assertEqual(kwargs["authorization"], "registered-user-cloud-token-0123456789")
            if path == "/v1/account":
                return {
                    "id": "user_123",
                    "organization_id": "org_123",
                    "email": "robot@example.com",
                    "display_name": "Robot Builder",
                    "created_at": datetime.now(UTC).isoformat(),
                    "email_verified_at": datetime.now(UTC).isoformat(),
                }
            if path == "/v1/credits":
                return {"unit": "gpu-second", "balance": 7200, "reserved": 0, "available": 7200}
            raise AssertionError(path)

        with patch.object(server, "_cloud_call", side_effect=cloud_call):
            response = client.get("/cloud/status")

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["account"]["email_verified_at"])

    def test_login_keeps_cloud_token_in_http_only_server_session(self):
        auth = {
            "token": "registered-user-cloud-token-0123456789",
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            "account": {
                "id": "user_123",
                "organization_id": "org_123",
                "email": "robot@example.com",
                "display_name": "Robot Builder",
                "created_at": datetime.now(UTC).isoformat(),
            },
        }

        def cloud_call(method, path, payload=None, **kwargs):
            if path == "/v1/auth/login":
                self.assertFalse(kwargs["allow_admin"])
                return auth
            if path == "/v1/credits":
                self.assertEqual(kwargs["authorization"], auth["token"])
                return {"unit": "gpu-second", "balance": 7200, "reserved": 0, "available": 7200}
            raise AssertionError(path)

        with (
            patch.dict(os.environ, {"BLACKNODE_CLOUD_URL": "https://cloud.blacknode.example"}),
            patch.object(server, "_cloud_call", side_effect=cloud_call),
        ):
            response = TestClient(server.app).post(
                "/cloud/auth/login",
                json={"email": "robot@example.com", "password": "correct-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])
        self.assertNotIn("token", response.text)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)

    def test_create_cloud_job_sends_portable_workflow_to_private_api(self):
        session = server.Session()
        session.node_meta = {"out": {"type": "Output"}}
        calls: list[tuple[str, str, dict]] = []
        workflow = {
            "kind": "blacknode.workflow",
            "schema_version": 1,
            "name": "Cloud graph",
            "entrypoint": {"node_id": "out", "port": "value"},
            "node_meta": {"out": {"type": "Output"}},
            "edges": [],
            "metadata": {},
        }

        def cloud_call(request, method, path, payload=None):
            self.assertIsNotNone(request.cookies.get(server._CLOUD_SESSION_COOKIE))
            calls.append((method, path, payload))
            return {"id": "job_" + "a" * 32, "status": "QUEUED"}

        with (
            patch.object(server, "_session", session),
            patch.object(server, "_workflow_payload", return_value=workflow),
            patch.object(
                server,
                "validate_bn_workflow",
                return_value=SimpleNamespace(ok=True, to_dict=lambda: {"ok": True}),
            ),
            patch.object(server, "_cloud_user_call", side_effect=cloud_call),
        ):
            response = self.authenticated_client().post(
                "/cloud/jobs",
                json={
                    "entrypoint": {"node_id": "out", "port": "value"},
                    "workflow_name": "Cloud graph",
                    "project_ref": "robot-project",
                },
            )

        self.assertEqual(response.status_code, 200)
        method, path, payload = calls[0]
        self.assertEqual((method, path), ("POST", "/v1/jobs"))
        self.assertEqual(payload["compute"]["gpu_class"], "l40s")
        self.assertEqual(payload["compute"]["gpu_count"], 1)
        self.assertEqual(payload["workflow"]["entrypoint"]["node_id"], "out")
        self.assertNotIn("image", payload["runtime"])

    def test_invalid_job_id_never_reaches_cloud(self):
        with patch.object(server, "_cloud_user_call") as cloud_call:
            response = self.authenticated_client().get("/cloud/jobs/../../secrets")

        self.assertIn(response.status_code, {400, 404})
        cloud_call.assert_not_called()

    def test_credit_history_and_logout_use_registered_session(self):
        client = self.authenticated_client()

        def cloud_call(method, path, payload=None, **kwargs):
            self.assertEqual(kwargs["authorization"], "registered-user-cloud-token-0123456789")
            if path == "/v1/auth/logout":
                return {"ok": True}
            raise AssertionError(path)

        with (
            patch.object(
                server,
                "_cloud_user_call",
                return_value={
                    "unit": "gpu-second",
                    "entries": [{"id": "credit_1", "delta_seconds": 7200}],
                },
            ) as user_call,
            patch.object(server, "_cloud_call", side_effect=cloud_call),
        ):
            history = client.get("/cloud/credits/history")
            logged_out = client.post("/cloud/auth/logout")

        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["entries"][0]["delta_seconds"], 7200)
        self.assertEqual(user_call.call_args.args[2], "/v1/credits/history?limit=100")
        self.assertTrue(logged_out.json()["revoked"])
        self.assertIn("Max-Age=0", logged_out.headers["set-cookie"])

    def test_email_verification_proxy_never_uses_admin_or_user_credentials(self):
        token = "email_verify_" + "a" * 48

        def cloud_call(method, path, payload=None, **kwargs):
            self.assertEqual((method, path), ("POST", "/v1/auth/verify-email"))
            self.assertEqual(payload, {"token": token})
            self.assertFalse(kwargs["allow_admin"])
            self.assertNotIn("authorization", kwargs)
            return {"verified": True, "account": {"email": "robot@example.com"}}

        with patch.object(server, "_cloud_call", side_effect=cloud_call):
            response = TestClient(server.app).post(
                "/cloud/auth/verify-email",
                json={"token": token},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["verified"])


if __name__ == "__main__":
    unittest.main()
