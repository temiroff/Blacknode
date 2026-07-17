import blacknode  # noqa: F401
from blacknode import Graph
from blacknode.node import _NODE_REGISTRY


def test_list_node_declares_variadic_any_inputs_and_collects_in_order():
    fn = _NODE_REGISTRY["List"]
    assert fn._bn_variadic_input == {"prefix": "item", "type": "Any"}

    graph = Graph()
    first = graph.node("Text", value="front")
    second = graph.node("Text", value="wrist")
    items = graph.node("List")
    first.out("value") >> items.inp("item_1")
    second.out("value") >> items.inp("item_2")

    assert items.cook("value") == ["front", "wrist"]


def test_list_literal_value_remains_backward_compatible():
    graph = Graph()
    items = graph.node("List", value=[1, 2, 3])
    assert items.cook("value") == [1, 2, 3]
