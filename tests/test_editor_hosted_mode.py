from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER = ROOT / "editor-server"
if str(EDITOR_SERVER) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER))

from hosted_mode import HostedWorkspaceStore, route_allowed


class EditorHostedModeTests(unittest.TestCase):
    def test_hosted_workspaces_are_isolated_and_reused(self) -> None:
        store = HostedWorkspaceStore(dict, max_workspaces=2)

        first_token, first, first_created = store.get_or_create(None)
        first["nodes"] = ["a"]
        repeated_token, repeated, repeated_created = store.get_or_create(first_token)
        second_token, second, second_created = store.get_or_create(None)

        self.assertTrue(first_created)
        self.assertFalse(repeated_created)
        self.assertTrue(second_created)
        self.assertEqual(repeated_token, first_token)
        self.assertEqual(repeated, {"nodes": ["a"]})
        self.assertNotEqual(second_token, first_token)
        self.assertEqual(second, {})

    def test_hosted_route_allowlist_keeps_graph_and_cloud_surfaces(self) -> None:
        self.assertTrue(route_allowed("GET", "/node-defs"))
        self.assertTrue(route_allowed("POST", "/nodes"))
        self.assertTrue(route_allowed("PATCH", "/nodes/node_1/params"))
        self.assertTrue(route_allowed("POST", "/edges"))
        self.assertTrue(route_allowed("POST", "/templates/hello/load"))
        self.assertTrue(route_allowed("POST", "/cloud/auth/login"))
        self.assertTrue(route_allowed("PATCH", "/cloud/account"))
        self.assertTrue(route_allowed("POST", "/cloud/newsletter/subscribe"))
        self.assertTrue(route_allowed("POST", "/cloud/jobs"))
        self.assertTrue(route_allowed("GET", "/cloud/jobs/job_123/artifacts"))
        self.assertTrue(
            route_allowed(
                "GET",
                "/cloud/jobs/job_123/artifacts/artifact_456/download",
            )
        )

    def test_hosted_route_allowlist_blocks_machine_and_execution_surfaces(self) -> None:
        blocked = [
            ("POST", "/cook"),
            ("POST", "/cook-stream"),
            ("POST", "/console/exec"),
            ("POST", "/filesystem/browse"),
            ("POST", "/device-hosts/inspect"),
            ("POST", "/devices"),
            ("POST", "/packages/install"),
            ("DELETE", "/packages/blacknode-cuda"),
            ("POST", "/custom-nodes"),
            ("POST", "/exec-node"),
            ("POST", "/api/workflows/current/run"),
            ("POST", "/nodes/node_1/control"),
            ("GET", "/nodes/node_1/depth-frame"),
        ]
        for method, path in blocked:
            self.assertFalse(route_allowed(method, path), (method, path))

        self.assertFalse(route_allowed("GET", "/packages", query="git=true"))
        self.assertFalse(route_allowed("POST", "/cloud/admin/statistics"))
        self.assertFalse(route_allowed("PATCH", "/cloud/jobs/job_123"))
