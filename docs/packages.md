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
| `blacknode-drivers` | Selectively enabled physical hardware drivers and firmware adapters; the first `feetech` component provides inert bus configuration, read-only probing, and torque-safe bus primitives. |
| `blacknode-robot` | Generic USB robot discovery, serial permission help, driver descriptors, driver process launch, and the standard robot profile. |
| `blacknode-controllers` | Joint-control, mobile-base, navigation, manipulation, policy, arbitration, and safety controllers with optional transport adapters. |
| `blacknode-ros2` | ROS 2 graph discovery, topics, services, native/rosbridge transport, managed processes, and diagnostics. |
| `blacknode-perception` | Camera, tracking, VLM, and spatial-perception components, organized as selectable components. |
| `blacknode-dataset` | Blacknode-native episode journals, synchronized robot/camera recording, dataset validation, HDF5 and structured Parquet/MP4 export profiles, and explicit repository publishing. |
| `blacknode-training` | PyTorch action-chunking training from Blacknode HDF5 episodes, managed jobs, resumable checkpoints, recorded-frame previews, and deployable policy artifacts. |
| `blacknode-isaac` | Direct closed-loop policy deployment using Isaac Sim articulation state, named RGB sensors, safety-gated targets, and runtime replay logs. |

Keep the layers separate: `blacknode-robot` owns profiles, calibration, and the
generic robot contract; `blacknode-drivers` owns physical protocol access and
driver-boundary safeguards; and `blacknode-ros2` owns ROS graph and transport
behavior. Optional adapters stay nested under the component they integrate.

A node named `ROS2*` is not automatically a `blacknode-ros2` node. The
integration layer owns only transport-agnostic ROS primitives; a node *about*
a capability belongs to the capability's package as a ROS 2 adapter component
that requires `blacknode-ros2/core`. That is why `CameraROS2Subscribe` lives in
`blacknode-perception` (`camera/ros2`) and `ROS2SetJoint` in
`blacknode-controllers` (`joint-control/ros2`). Dependencies point one way
only — capability adapters depend on the integration layer, never the reverse
— so a second transport can be added as a sibling adapter later without
reorganizing any capability package. Each capability package also ships its
own on-robot colcon sources under `<package>/ros2_ws/src/`.

The `blacknode-skills/follow-person@ros2` CV2 local-reasoning template
(camera and VLM nodes from `blacknode-perception`) routes target selection
through the VLM:

```text
Text target prompt
  -> ReasoningStream
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

Templates declare selectable components and optional adapters separately. The
resolver checks package version and enabled state, then returns the transitive
install/enable plan alongside missing-node results:

```json
{
  "metadata": {
    "required_components": ["blacknode-drivers/feetech"],
    "required_adapters": [
      {
        "package": "blacknode-drivers",
        "component": "feetech",
        "adapter": "ros2",
        "version": ">=0.1.0,<1.0.0"
      }
    ]
  }
}
```

The compact adapter form `"blacknode-drivers/feetech@ros2"` is also accepted.
Component activation remains an explicit package action, so resolving a
template never arms hardware or silently changes the environment.

## Package layout

```
blacknode-ros2/
  blacknode-package.toml   # manifest (required)
  AGENTS.md                # scoped coding-agent instructions (recommended)
  nodes/                   # flat-package Python modules using @node
    __init__.py
    topics.py
  components/              # selective packages keep modules by component
    topics/
      nodes/
        __init__.py
        publish.py
  templates/               # optional workflow JSONs for the Templates tab
  tests/                   # optional pytest suite, run with the core suite
  requirements.txt         # optional pip dependencies
  README.md
```

Flat packages use the root `nodes/` directory. It is loaded as a real Python
package, so modules can import each other relatively and import anything from
the `blacknode` core. After loading, the modules get a stable import alias:

```python
from blacknode.pkg.blacknode_ros2 import topics   # dashes become underscores
```

### Layers and selective components

A package can declare its product layer and describe the components it owns:

```toml
[package]
name = "blacknode-drivers"
version = "0.3.0"
description = "Blacknode physical hardware and firmware adapters."
requires-blacknode = ">=0.3.0"
layer = "drivers"
component-mode = true

[components.feetech]
description = "Feetech serial-bus servo adapter."
default = true
capabilities = ["driver.feetech", "robot.joint-driver"]
nodes = ["components/feetech/nodes"]
templates = ["components/feetech/templates"]
setup-hooks = ["components/feetech/scripts/setup.py"]
node-types = ["FeetechBus", "FeetechServo"]

[components.feetech.dependencies]
pip = ["pyserial>=3.5"]
imports = ["serial"]
requires = [
  { package = "blacknode-robot", version = ">=0.1.0,<1.0.0" }
]

[components.feetech.adapters.ros2]
description = "Optional ROS 2 transport adapter."
default = false
nodes = ["components/feetech/adapters/ros2/nodes"]

[components.feetech.adapters.ros2.dependencies]
requires = [
  { package = "blacknode-ros2", component = "core", version = ">=0.2.0,<1.0.0" }
]

[components.stm32]
description = "STM32 serial bridge."
default = false
nodes = ["components/stm32/nodes"]
```

The Packages UI groups installed and available packages by `layer`. Official
catalog entries provide a layer for older manifests that do not declare one;
third-party packages without a layer appear under `Extensions`.

`component-mode = true` opts the repository into selective loading. Declaring at
least one component `nodes` path also enables this mode, but the explicit flag
is recommended. Only enabled component paths are imported and only their
`pip`, `imports`, and `docker` dependencies are active. Package-level
`[dependencies]` and a root `requirements.txt` are shared by every component,
so component-only dependencies belong in the component table.

Component choices are local machine state. Blacknode writes them to
`packages/.blacknode-components.json`, outside each package Git worktree. A
component uses its manifest `default` until the user creates an override.

Manage components in the editor's Packages tab or from the CLI:

```bash
blacknode packages components blacknode-drivers
blacknode packages dependencies blacknode-drivers feetech
blacknode packages enable blacknode-drivers feetech
blacknode packages dependencies blacknode-drivers feetech --adapter ros2
blacknode packages enable blacknode-drivers feetech --adapter ros2
blacknode packages setup blacknode-drivers
blacknode packages disable blacknode-drivers feetech --adapter ros2
blacknode packages disable blacknode-drivers feetech
blacknode packages reset blacknode-drivers feetech --adapter ros2
blacknode packages reset blacknode-drivers feetech
```

`dependencies` prints the complete installed activation order. A component can
require another component in the same package by omitting `package`, or require
a component in another layer repository:

```toml
[components.feetech.adapters.ros2.dependencies]
requires = [
  { package = "blacknode-ros2", component = "core", version = ">=0.2.0,<1.0.0" }
]
```

Blacknode preflights the complete graph before changing activation state. It
installs missing official packages, safely fast-forwards a clean behind-only
checkout when that can satisfy a version requirement, enables dependencies
before dependents, reuses enabled compatible versions, rejects cycles and
incompatible or dirty checkouts, rolls back newly cloned packages and the whole
activation change if setup or reload fails, and prevents disabling a component
or removing a package that an enabled component requires. The Packages UI shows each component's
direct requirements. `GET /packages/{name}/components/{component}/dependencies`
returns the resolved plan for other clients.

The dependency plan is explicit in `blacknode packages dependencies`; the
enable operation applies it. Third-party dependencies without a catalog source
return an actionable error instead of guessing a repository. Successful
installs, removals, and component changes atomically write
`packages/.blacknode-package-lock.json`, recording versions, Git revisions,
sources, and enabled components.

`setup` installs shared requirements plus pip dependencies of enabled
components and their enabled adapters. It also runs only the enabled units'
declared `.py` or `.sh` `setup-hooks`; paths must remain inside the package.
Enabled component and adapter `templates` paths are added to the Templates tab.
pip reuses already satisfied
dependencies and checks declared version constraints. Component node modules use aliases such as
`blacknode.pkg.blacknode_drivers.feetech.<module>`.
Adapter modules use nested aliases such as
`blacknode.pkg.blacknode_drivers.feetech.adapters.ros2.<module>`.
During a compatibility migration, one component can set `module-root = true`
to retain an existing alias such as `blacknode.pkg.blacknode_ros2.<module>`.

Existing flat manifests remain compatible: their root `nodes/` directory and
package-wide dependencies continue to load as one implicit component. A
manifest can also publish descriptive `[components.*]` entries without opting
into component mode; the UI marks those entries as included.

`disable` creates an explicit local override. `reset` removes that override and
returns the component or adapter to its versioned manifest default. The same
operation is available in the Packages UI and HTTP component endpoints.

Official repositories run a release drift gate in CI:

```bash
blacknode packages validate-catalog /path/to/package
```

This compares the manifest layer, component/adapter names, and declared node
types with Blacknode's authoritative package index, including disabled optional
components.

Lockfile reproduction and version selection across multiple compatible remote
releases remain future resolver stages.

The initial organizational layers are `skills`, `agent`, `robot`,
`perception`, `controllers`, and `drivers`. `ros2` identifies the horizontal
ROS graph and transport layer. `learning`, `compute`, and `simulation`
identify supporting packages such as training, CUDA, and simulator adapters.

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
