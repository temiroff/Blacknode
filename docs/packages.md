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

If you cloned a package by hand (or a pull added new prerequisites), install
everything it declares — pip requirements and Docker images — with:

```bash
blacknode packages setup blacknode-ros2
```

`start.ps1` and `start.sh` automatically install missing declared Python
dependencies for installed packages before starting the server. The launchers
stream package names, dependency resolution, downloads, and pip installation
output while this step runs. Set
`BLACKNODE_PACKAGE_AUTO_SETUP=0` to disable that behavior. Automatic startup
setup does not pull Docker images or run package setup scripts; use the command
above when those additional prerequisites are required.

The editor's **Packages** tab can do all of this too: paste a git URL and
press **Install** (clones the repo and installs its prerequisites), or expand
a package and press **Delete** to remove its folder and deregister its nodes —
no restart needed.

Extra search folders can be added with the `BLACKNODE_PACKAGE_PATH`
environment variable (separated by the platform path separator).

## Updating packages

`blacknode packages status` reports package load state, missing official nodes,
and local git state for installed folder packages. Add `--fetch` when you want
to contact remotes and see whether a package is behind upstream:

```bash
blacknode packages status --fetch
```

Update clean package checkouts with:

```bash
blacknode packages update --all
```

The update command is intentionally conservative: it fetches and fast-forwards
only packages with no local edits and no local commits ahead of upstream. Dirty,
ahead, diverged, non-git, and non-folder packages are reported and skipped so a
startup update cannot overwrite package development work. Use `--deps` when a
package update added new Python or Docker prerequisites:

```bash
blacknode packages update --all --deps
```

At launcher startup, Blacknode checks installed package health and attempts safe
fast-forward updates by default. It skips dirty, ahead, diverged, non-git, and
blocked packages rather than overwriting local package work. Disable startup
package updates with `BLACKNODE_PACKAGE_AUTO_UPDATE=0`:

```bash
BLACKNODE_PACKAGE_AUTO_UPDATE=0 ./start.sh
```

On Windows PowerShell:

```powershell
$env:BLACKNODE_PACKAGE_AUTO_UPDATE="0"; .\start.bat
```

Set `BLACKNODE_SKIP_PACKAGE_CHECK=1` to skip the package health check entirely.
If auto-update is disabled but you still want startup to fetch remote state, set
`BLACKNODE_PACKAGE_CHECK_REMOTE=1`.

Official packages are listed in the editor's Packages tab even when they are not
installed. Press **Install** on an available package to clone it from the built-in
Git URL without pasting a repository URL manually.

The editor's **Templates** tab groups starter workflows by Core or their source
package category. Every group starts collapsed, its templates inherit the
category color, and the search field filters across category names, template
names, slugs, and descriptions.

On a Blacknode workspace's first editor session, the editor opens this tab
behind a one-time welcome message. The message directs robotics users to install
the official packages their workflows require and lets core-graph users
continue immediately. After either choice, Blacknode records the acknowledgement
in `.blacknode/onboarding.json` inside the repository and does not show the
message again for that workspace.
## Official robotics and vision packages

The robotics packages are separate repos but can live under `packages/` during
development:

| Package | Role |
|---|---|
| `blacknode-robot` | Generic USB robot discovery, serial permission help, driver descriptors, driver process launch, and the standard robot profile. |
| `blacknode-ros2` | ROS 2 system checks, topic inspection, image snapshots, image streams, process launch/run controls, native `rclpy` robot control, rosbridge robot control, and robot dashboards. |
| `blacknode-vision` | USB camera ROS package, VLM frame reasoning, live reasoning dashboards, OpenCV masks, color tracking streams, and graph-level Python exports. |
| `blacknode-dataset` | Blacknode-native episode journals, synchronized robot/camera recording, dataset validation, HDF5 and structured Parquet/MP4 export profiles, and explicit repository publishing. |
| `blacknode-training` | Optional PyTorch action-chunking training from Blacknode HDF5 episodes, managed jobs, resumable checkpoints, metrics dashboards, and recorded-frame policy previews. |

Keep the layers separate: `blacknode-robot` finds hardware and starts the right
robot driver, robot-specific packages define the driver descriptor, and
`blacknode-ros2` only verifies or controls a ROS-compatible interface exposed by
that driver.

The current `blacknode-vision` CV2 local-reasoning template routes target
selection through the VLM:

```text
Text target prompt
  -> VisionReasoningStream
  -> CV2ColorObjectStream.reasoning_state_url
  -> live overlay / mask / detection JSON
```

The prompt does not connect directly to the CV2 target in that template. The
model answer chooses the target color, and `CV2ColorObjectStream` retargets its
HSV range while running. Tracker properties such as HSV thresholds, minimum
area, morphology, FPS, width, JPEG quality, direct target text, and fallback
color hot-update the running overlay/mask/detection stream from the editor.
Direct text targets such as `track red cube` remain available for non-VLM graphs
through `CV2ColorTargetHint.target` or `CV2ColorObjectStream.target`.

When a tracker is working, use the top-bar **Export** dropdown on the actual
canvas graph. **Plain Python** exports the same nodes and edges you built
visually, including ROS 2, camera, reasoning, and CV2 nodes. A future
robot-deploy exporter should compile supported graph patterns into smaller
standalone scripts, but it should still be an export target, not a node.

## Missing-node resolution

Blacknode ships a small core index that maps official extension node types to
their package name and Git URL. The editor backend exposes it at:

```text
GET /packages/index
```

Template loading scans every root and nested node type before validation. When
a type is unavailable, the loader combines the core index with the template's
optional `metadata.required_packages` declaration. The Templates tab then
shows the missing package, installs it through the existing package installer,
refreshes node definitions, and retries the load.

Indexed packages only need their name:

```json
{
  "metadata": {
    "template": true,
    "required_packages": ["blacknode-cuda"]
  }
}
```

Third-party templates can carry their own resolution:

```json
{
  "metadata": {
    "required_packages": [
      {
        "name": "blacknode-ros-extra",
        "git_url": "https://github.com/example/blacknode-ros-extra.git",
        "node_types": ["ROS2BagPlay"]
      }
    ]
  }
}
```

The install still requires an explicit click. Templates do not clone or execute
package code automatically.

## Package layout

```
blacknode-ros2/
  blacknode-package.toml   # manifest (required)
  AGENTS.md                # scoped coding-agent instructions (recommended)
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

### Agent guidance

Every maintained package should include an `AGENTS.md` because it is an
independent Git repository and may have domain-specific ownership, dependency,
test, lifecycle, and safety rules. Keep that file concise and cover:

- what belongs in the package and what belongs in core or a sibling package
- optional dependency and no-hardware behavior
- managed-service lifecycle and explicit shutdown, when applicable
- exact focused test and template-validation commands
- physical, credential, network, CUDA, camera, or ROS paths that must not be
  claimed as tested without evidence

Use the shared `blacknode-development` skill for package authoring and the
package's `AGENTS.md` for its scoped implementation contract. Do not duplicate
the same general authoring skill in every package. Create a package-specific
skill only when its users need a distinct operational procedure beyond normal
workflow construction.

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
pip = ["pyyaml>=6"]            # informational; installed via requirements.txt
imports = ["yaml", "roslibpy"] # modules verified at load time (see below)
docker = ["ros:jazzy"]         # images pulled by `blacknode packages install` / `setup`
```

### Declaring runtime dependencies so users know what to install

Nodes deliberately guard heavy imports (GPU, ROS, ...) so the package still
loads on a machine without them — which means a missing dependency is invisible
until a node fails at runtime. List the **import names** those guards need under
`[dependencies] imports` (note: the *import* name, e.g. `yaml`, not the pip
name `PyYAML`). At load time Blacknode verifies each one and, for any that are
missing, attaches a non-fatal **warning** with the exact fix command — targeting
*this server's own interpreter*, so there's no ambiguity about which Python or
environment to install into. The warnings show up in:

- `blacknode packages list` (an `ok, deps missing` status plus `!` lines)
- the `GET /packages` endpoint (`warnings` field on each package)
- the editor's **Packages** tab — the status dot turns amber and the expanded
  panel shows the warning and an amber **Install prerequisites** button (hover it
  to see exactly what is missing). When everything declared is satisfied the
  button instead reads **Prerequisites ✓** in green, so you can tell at a glance
  whether you need to press it. Note the check covers the declared Python
  `imports`; Docker images are not verified at load and pull on first use.

The package still loads and its other nodes still work; only the ones needing
the missing module return a structured error until it is installed. Install
everything a package declares (pip requirements and Docker images) at any time
with **Install prerequisites** in the Packages tab, or:

```bash
blacknode packages setup <package-name>
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
