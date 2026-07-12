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
robotics packages are split by responsibility: `blacknode-robot` is generic
USB/driver setup, `blacknode-ros2` is ROS 2 transport/control, and
`blacknode-vision` is camera/CV2/VLM perception. `blacknode-cuda` remains the
smallest reference package to copy when writing your own.
