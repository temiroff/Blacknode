# Extension Packages

Blacknode is modular: the base install ships the core node library, and
everything else lives in **extension packages** — separate git repositories
(e.g. `blacknode-cuda`, `blacknode-ros2`) cloned into the `packages/` folder.
Blacknode discovers them at startup and registers their nodes and templates.
Delete a package folder to remove it; the base app keeps working.

## Installing a package

```bash
blacknode packages install https://github.com/you/blacknode-ros2
```

This clones the repo into `packages/`, pip-installs its `requirements.txt`,
and loads it. Or do the same by hand:

```bash
git clone https://github.com/you/blacknode-ros2 packages/blacknode-ros2
pip install -r packages/blacknode-ros2/requirements.txt
```

Restart Blacknode (or press **Reload** in the editor's Packages tab). The
package's nodes appear in the palette under the categories it declares, and
its workflow templates show in the Templates tab.

`blacknode packages list` shows what is installed and whether each package
loaded. The editor's **Packages** tab shows the same, including load errors.

Extra search folders can be added with the `BLACKNODE_PACKAGE_PATH`
environment variable (separated by the platform path separator).

## Package layout

```
blacknode-ros2/
  blacknode-package.toml   # manifest (required)
  nodes/                   # Python modules using @node (required)
    __init__.py
    topics.py
  templates/               # optional workflow JSONs for the Templates tab
  tests/                   # optional pytest suite, run with the core suite
  requirements.txt         # optional pip dependencies
  README.md
```

`nodes/` is loaded as a real Python package, so modules can import each other
relatively and import anything from the `blacknode` core. After loading, the
modules get a stable import alias:

```python
from blacknode.pkg.blacknode_ros2 import topics   # dashes become underscores
```

## The manifest

```toml
[package]
name = "blacknode-ros2"
version = "0.1.0"
description = "ROS 2 topic, service, and action nodes."
requires-blacknode = ">=0.1.0"   # load is skipped (with a clear error) if too old

[categories]
# Palette categories this package introduces, with their header color.
"ROS 2" = "#22314e"

[dependencies]
pip = ["rclpy>=3.0"]   # informational; installed via requirements.txt
```

A failing package (missing deps, bad code, version mismatch) never breaks
startup — it is reported in `blacknode packages list`, the `/packages`
endpoint, and the editor's Packages tab with the error text.

## Writing nodes

Nodes are the same `@node` functions documented in
[custom-nodes.md](custom-nodes.md):

```python
from blacknode.node import Text, node


@node(
    name="ROS2Publish",
    category="ROS 2",
    inputs={"topic": Text, "message": Text},
    outputs={"ok": Text},
)
def ros2_publish(topic: str, message: str) -> str:
    ...
```

Keep heavy imports (GPU libraries, ROS, etc.) inside the function or guarded
in `try/except` at module top, so the package still loads — and its nodes can
return structured errors — on machines without the dependency installed.
`packages/blacknode-cuda` in the main repository is the reference package to
copy from.

## pip-installable packages

A package published to PyPI can skip the folder clone by declaring an entry
point; importing the module must register the nodes:

```toml
[project.entry-points."blacknode.packages"]
blacknode-ros2 = "blacknode_ros2"
```

Category colors come from a module-level `BLACKNODE_CATEGORIES = {"ROS 2":
"#22314e"}` dict, and `__version__` is reported in the package list.

## Tests

Running `pytest` from the Blacknode repo root collects `tests/` **and**
`packages/*/tests/` — every installed package is tested together with the
core. Keep package test filenames unique across packages (prefix them with
the package name, e.g. `test_ros2_topics.py`) so module names don't collide.

Package tests can import the core (`blacknode.node`, test helpers) and the
package's own modules via the stable alias:

```python
from blacknode.pkg.blacknode_ros2 import topics
```

## Folder vs. single-file nodes

| Mechanism | Use for |
|---|---|
| `custom-nodes/` `.py` files | quick local one-file nodes saved from the editor Script tab |
| `packages/<name>/` | multi-file node libraries with deps, templates, their own repo and versioning |
