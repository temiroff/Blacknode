from __future__ import annotations

import blacknode  # noqa: F401
from blacknode.node import _NODE_REGISTRY


def test_list_index_returns_item_at_index():
    result = _NODE_REGISTRY["ListIndex"]({"items": ["shoulder_pan", "elbow_flex", "gripper"], "index": 1})
    assert result == {"value": "elbow_flex", "found": True}


def test_list_index_supports_negative_index():
    result = _NODE_REGISTRY["ListIndex"]({"items": ["a", "b", "c"], "index": -1})
    assert result == {"value": "c", "found": True}


def test_list_index_out_of_range_reports_not_found():
    result = _NODE_REGISTRY["ListIndex"]({"items": ["a", "b"], "index": 5})
    assert result == {"value": None, "found": False}


def test_list_index_empty_list_reports_not_found():
    result = _NODE_REGISTRY["ListIndex"]({"items": [], "index": 0})
    assert result == {"value": None, "found": False}
