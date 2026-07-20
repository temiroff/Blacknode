# Extension Packages

Each subfolder here is a Blacknode extension package — usually a separate git
repository cloned in place:

```bash
git clone https://github.com/you/blacknode-ros2 packages/blacknode-ros2
pip install -r packages/blacknode-ros2/requirements.txt   # if it has deps
```

or simply:

```bash
blacknode packages install https://github.com/you/blacknode-ros2
```

Blacknode discovers every folder containing a `blacknode-package.toml` at
startup and registers its nodes and templates. Delete a folder to remove the
package. See [docs/packages.md](../docs/packages.md) for the manifest format
and how to write your own package.

Every package folder here is gitignored — each is its own repository. Official
robotics packages are split by responsibility: `blacknode-robot` owns robot
profiles and calibration, `blacknode-drivers` owns physical hardware protocols,
`blacknode-ros2` owns ROS 2 graph/transport behavior, and `blacknode-perception`
provides camera/CV2/VLM perception. `blacknode-cuda` remains the smallest flat
package reference; `blacknode-drivers` is the selective-component reference.

Maintained packages should include a scoped `AGENTS.md` with ownership,
dependency, safety, and verification rules. Agents use the core
`blacknode-development` skill for the shared authoring workflow, then follow the
target package's `AGENTS.md`; packages do not need duplicated general skills.
