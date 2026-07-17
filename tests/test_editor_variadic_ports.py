from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"
if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402
from blacknode.node import Any as AnyPort  # noqa: E402
from blacknode.node import Bool, Dict, Int, Text, node  # noqa: E402


def test_variadic_ports_follow_numbered_connected_edges():
    meta = {
        "id": "cameras", "type": "DatasetCameraStreamList",
        "inputs": ["trigger", "camera_streams", "camera_stream", "camera_9"],
        "input_types": {"trigger": "Any", "camera_streams": "List", "camera_stream": "Dict", "camera_9": "Dict"},
        "input_defaults": {"camera_streams": [], "camera_stream": {}},
        "variadic_input": {"prefix": "camera", "type": "Dict"},
    }
    edges = [
        {"from": "wrist", "from_port": "frame_stream", "to": "cameras", "to_port": "camera_2"},
        {"from": "front", "from_port": "frame_stream", "to": "cameras", "to_port": "camera_1"},
    ]

    server._sync_variadic_ports(meta, edges)

    assert meta["inputs"][-2:] == ["camera_1", "camera_2"]
    assert meta["input_types"]["camera_1"] == "Dict"
    assert "camera_9" not in meta["inputs"]


def test_primary_ports_are_exposed_as_node_definition_defaults():
    @node(
        name="CompactPortTestNode",
        inputs={"trigger": Text, "advanced": Text},
        outputs={"result": Text, "debug": Text},
        primary_inputs=["trigger"],
        primary_outputs=["result"],
    )
    def compact_port_test(ctx: dict) -> dict:
        return {"result": ctx.get("trigger", ""), "debug": ""}

    payload = server._node_def_payload("CompactPortTestNode", server._NODE_REGISTRY["CompactPortTestNode"])
    assert payload["primary_inputs"] == ["trigger"]
    assert payload["primary_outputs"] == ["result"]


def test_port_visibility_patch_persists_only_declared_ports(monkeypatch):
    previous = server._session.node_meta
    server._session.node_meta = {
        "compact": {
            "id": "compact", "type": "CompactPortTestNode",
            "inputs": ["trigger", "advanced"], "outputs": ["result", "debug"],
        },
    }
    monkeypatch.setattr(server, "_save", lambda: None)
    try:
        result = server.update_port_visibility("compact", server.UpdatePortVisibilityReq(
            promoted_inputs=["advanced", "missing"],
            promoted_outputs=["debug", "missing"],
        ))
    finally:
        server._session.node_meta = previous

    assert result["promoted_inputs"] == ["advanced"]
    assert result["promoted_outputs"] == ["debug"]


def test_large_nodes_get_conservative_automatic_compact_ports():
    @node(
        name="AutomaticCompactPortTestNode",
        inputs={
            "trigger": AnyPort,
            "payload": Dict,
            "host": Text(default="127.0.0.1"),
            "port": Int(default=9000),
            "enabled": Bool(default=True),
        },
        outputs={"found": Bool, "ready": Bool, "data": Dict, "report": Text},
    )
    def automatic_compact_port_test(ctx: dict) -> dict:
        return {"data": ctx.get("payload", {})}

    fn = server._NODE_REGISTRY["AutomaticCompactPortTestNode"]
    assert fn._bn_primary_inputs == ["trigger", "payload"]
    assert fn._bn_primary_outputs == ["data"]


def test_small_nodes_keep_their_complete_port_surface():
    @node(name="SmallPortTestNode", inputs={"value": Text}, outputs={"result": Text})
    def small_port_test(ctx: dict) -> dict:
        return {"result": ctx.get("value", "")}

    fn = server._NODE_REGISTRY["SmallPortTestNode"]
    assert fn._bn_primary_inputs is None
    assert fn._bn_primary_outputs is None
