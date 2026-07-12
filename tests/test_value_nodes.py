import blacknode  # noqa: F401
from blacknode.node import _NODE_REGISTRY


def test_color_value_node_outputs_color_string():
    fn = _NODE_REGISTRY["Color"]
    assert fn._bn_output_types["value"] == "Color"
    assert fn({"value": "#ef4444"}) == {"value": "#ef4444"}
    assert fn({"value": ""}) == {"value": "#22c55e"}


def test_list_value_node_outputs_list():
    fn = _NODE_REGISTRY["List"]
    assert fn._bn_output_types["value"] == "List"
    assert fn({"value": '["a", 2]'}) == {"value": ["a", 2]}
    assert fn({"value": {"not": "a list"}}) == {"value": []}
