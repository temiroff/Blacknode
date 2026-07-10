"""A package's declared `imports` are verified at load time and surfaced as
non-fatal warnings naming the exact fix — without blocking the load."""
from pathlib import Path

from blacknode.packages import load_package


def _make_package(root: Path, name: str, imports: list[str], node_type: str) -> Path:
    pkg = root / name
    (pkg / "nodes").mkdir(parents=True)
    imports_line = ", ".join(f'"{m}"' for m in imports)
    (pkg / "blacknode-package.toml").write_text(
        "[package]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        "[dependencies]\n"
        f"imports = [{imports_line}]\n",
        encoding="utf-8",
    )
    (pkg / "nodes" / "__init__.py").write_text(
        "from blacknode.node import Text, node\n\n"
        f'@node(name="{node_type}", inputs={{"x": Text}}, outputs={{"y": Text}})\n'
        "def _n(ctx):\n"
        '    return {"y": ctx.get("x", "")}\n',
        encoding="utf-8",
    )
    return pkg


def test_missing_import_is_a_nonfatal_warning(tmp_path):
    pkg = _make_package(tmp_path, "pkg-missing-dep", ["absent_module_xyz123"], "DepCheckNodeA")
    info = load_package(pkg)

    assert info.ok is True  # package still loads
    assert "DepCheckNodeA" in info.node_types
    assert len(info.warnings) == 1
    warning = info.warnings[0]
    assert "absent_module_xyz123" in warning
    assert "pip install" in warning
    assert "blacknode packages setup pkg-missing-dep" in warning


def test_present_import_produces_no_warning(tmp_path):
    pkg = _make_package(tmp_path, "pkg-ok-dep", ["json", "pathlib"], "DepCheckNodeB")
    info = load_package(pkg)

    assert info.ok is True
    assert info.warnings == []
