from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SERVER_DIR = ROOT / "editor-server"
if str(EDITOR_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_SERVER_DIR))

import server  # noqa: E402


def test_joint_list_dynamic_ports_follow_connected_edges():
    meta = {
        "id": "joints",
        "type": "RobotJointList",
        "inputs": ["joint_1", "joint_2", "joint_16"],
        "input_types": {"joint_1": "Dict", "joint_2": "Dict", "joint_16": "Dict"},
        "outputs": ["joints", "count", "report"],
        "output_types": {"joints": "List", "count": "Int", "report": "Text"},
        "input_defaults": {},
    }
    edges = [
        {"from": "b", "from_port": "joint", "to": "joints", "to_port": "joint_25"},
        {"from": "a", "from_port": "joint", "to": "joints", "to_port": "joint_2"},
    ]

    server._sync_joint_list_ports(meta, edges)

    assert meta["inputs"] == ["joint_2", "joint_25"]
    assert meta["input_types"] == {"joint_2": "Dict", "joint_25": "Dict"}
    assert meta["input_defaults"] == {}
