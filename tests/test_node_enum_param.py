"""Task 1.0 — Enum/dropdown param support."""
from blacknode.node import Enum, Int, node, _NODE_REGISTRY


def test_enum_records_choices_and_default():
    @node(
        inputs={"mode": Enum(["a", "b", "c"], default="b"), "n": Int(default=5)},
        outputs=["out:Text"],
        name="_EnumProbe",
    )
    def _probe(ctx):
        return {"out": ctx.get("mode")}

    fn = _NODE_REGISTRY["_EnumProbe"]
    assert fn._bn_input_choices["mode"] == ["a", "b", "c"]
    # non-enum ports carry no choices
    assert "n" not in fn._bn_input_choices
    # default is honored and wire type stays Text
    assert fn._bn_input_defaults["mode"] == "b"
    assert fn._bn_input_types["mode"] == "Text"


def test_enum_defaults_to_first_choice():
    spec = Enum(["x", "y"])
    assert spec.default == "x"
    assert spec.choices == ("x", "y")


def test_cuda_node_exposes_op_dropdown():
    import blacknode  # noqa: F401 - ensure built-in nodes are registered
    fn = _NODE_REGISTRY["CUDAKernelLab"]
    choices = fn._bn_input_choices
    assert "vector_add" in choices["op"]
    assert "mandelbrot" in choices["op"]
    assert choices["dtype"] == ["float32", "float64"]
