# Blacknode Family Colors

Blacknode uses a stable family color to make workflows, packages, templates,
and documentation faster to scan. The color identifies what a capability does;
runtime health continues to use the separate Ready, Running, Waiting, and Error
status colors.

| Family | Color | Hex |
|---|---|---|
| Core | ![Cyan](images/swatches/swatch-06b6d4.svg) Cyan | `#06b6d4` |
| Agent | ![Purple](images/swatches/swatch-a855f7.svg) Purple | `#a855f7` |
| Robot | ![Teal](images/swatches/swatch-14b8a6.svg) Teal | `#14b8a6` |
| Perception | ![Green](images/swatches/swatch-22c55e.svg) Green | `#22c55e` |
| ROS 2 | ![Blue](images/swatches/swatch-3b82f6.svg) Blue | `#3b82f6` |
| CUDA | ![Lime](images/swatches/swatch-84cc16.svg) Lime | `#84cc16` |
| Controllers | ![Orange](images/swatches/swatch-f97316.svg) Orange | `#f97316` |
| Drivers | ![Gray](images/swatches/swatch-64748b.svg) Gray | `#64748b` |
| Output | ![Pink](images/swatches/swatch-ec4899.svg) Pink | `#ec4899` |
| Values | ![Amber](images/swatches/swatch-f59e0b.svg) Amber | `#f59e0b` |

The refined editor interface applies these colors consistently to:

- node-palette group accents and node icons
- template category headers and category icons; template cards stay neutral
- node headers and family accent lines
- node-search category filters and result icons
- package-browser sections, package icons, and family tags

Use family color for identity and small-area accents. Keep card bodies and
documentation surfaces neutral so text remains readable. Port and wire colors
represent data types rather than node families.

The refined Devices view uses verified runtime, ROS 2, robot, deployment, and
firmware state as a compact health summary. It does not display simulated
hardware telemetry when a device has not reported those measurements.

Package manifests can still declare colors for additional domain families.
When a package belongs to one of the canonical families above, use the
canonical hex value so package-owned templates and documentation remain
consistent with the editor.
