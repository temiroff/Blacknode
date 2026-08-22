# App deployments

Blacknode App deployments package one or more Workflow Apps into a focused
operator surface. The customer shell retains a compact Blacknode top bar with
the deployed App icons and a Settings control. It opens the configured start
App directly and switches between bundled Apps from the icon bar.

The bundle retains the workflow graph as the execution model while granting
the customer surface access only to fields, actions, controls, and cook targets
declared by `metadata.operator_view`. Graph editing, workflow management,
package installation, console commands, file browsing, device administration,
and arbitrary node execution remain outside the operator boundary.

## Create a bundle

Every included workflow must validate and declare a versioned
`metadata.operator_view` with a stable `id`.

```powershell
New-Item -ItemType Directory -Force .\.local-notes\deployments | Out-Null

blacknode export-app `
  packages\blacknode-dataset\templates\teleoperation-episode-recording.json `
  --id customer-recording `
  --name "Robot Data Collection" `
  --output .local-notes\deployments\customer-recording.blacknode-app.json
```

Pass multiple workflow paths to create a multi-App deployment. Use
`--start-app ID` to choose the App that opens first. Each workflow can declare
an `operator_view.icon`; the top bar keeps every bundled App visible and uses
its name as the icon tooltip.

The command produces a `blacknode.app-deployment` schema-version 1 manifest.
It validates every workflow, records the union of `metadata.required_packages`,
and rejects persisted API keys, tokens, passwords, credentials, and secrets.
Configure credentials in the deployment host environment or its managed secret
store.

The exported manifest is the deployable artifact. Keep each released manifest
under a versioned artifact name or release record so the previous known-good
bundle remains available for rollback.

## Prepare the deployment host

Install the released Blacknode core and every package listed in the manifest's
`required_packages`. For **Collect episodes**, open **Devices**, select the
robot, press **Software**, then press **Check updates** and **Update all**. This
updates the robot Runtime and its installed extension packages through the
operator surface.

Place the exported `.blacknode-app.json` bundle on the computer serving the App.
That computer needs network access to the robot transports and services used by
the workflow. Store provider credentials in the host environment or managed
secret store; the bundle itself stays credential-free.

## Start the customer surface

Point the editor server at the bundle before starting Blacknode:

```powershell
$env:BLACKNODE_APP_DEPLOYMENT = (
  Resolve-Path .\.local-notes\deployments\customer-recording.blacknode-app.json
).Path
.\start.bat
```

```bash
export BLACKNODE_APP_DEPLOYMENT="$(realpath ./customer-recording.blacknode-app.json)"
./start.sh
```

For a customer domain, also set `BLACKNODE_APP_PUBLIC_ORIGINS` to the exact
comma-separated HTTPS origins allowed to send operator commands. Local startup
accepts `http://localhost:3000` and `http://127.0.0.1:3000` by default.

Opening Blacknode now enters the customer App shell automatically. A direct App
link uses `/app/<app-id>`, such as `/app/collect-episodes`.

Open the top-bar **Settings** control to configure the robot connection and
other inputs declared by the active workflow's `operator_view.settings`.
Settings update only their declared node parameters. Graph editing remains an
authoring capability outside the customer shell.

## Verify the deployment

Open `http://localhost:3000/app/collect-episodes`. A single-App deployment shows
one App icon. A multi-App deployment opens `start_app` and shows every bundled
App icon for direct switching.

Check the server mode and public manifest from a second terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:7777/healthz
Invoke-RestMethod http://127.0.0.1:7777/app-deployment
```

The health response reports `mode: app`. The public deployment response lists
the expected App IDs and reports `access.graph_editing` as `false`. Exercise the
declared fields and recording controls with physical motion disarmed before
authorizing a robot session.

For a customer hostname, terminate TLS at the deployment proxy, forward the App
and API traffic to Blacknode, and set `BLACKNODE_APP_PUBLIC_ORIGINS` to the exact
HTTPS origin. Run one deployment manifest per server process.

## Update or roll back an App

The deployment manifest is immutable while the server runs. Export a new
versioned bundle, stop the App host, point `BLACKNODE_APP_DEPLOYMENT` at the new
bundle, and restart Blacknode. To roll back, repeat the same process with the
previous known-good bundle.

Field changes affect the active operator session and underlying workflow
runtime. Update the workflow defaults and export a new bundle when customer
defaults need to change.

## Operator boundary

The server derives its permission set from the active App:

- `fields` grant updates to their exact node parameter.
- `settings` grant updates to their exact node parameter and any exact
  `apply_to` targets.
- action `updates` grant their exact node parameter changes.
- action `control` entries grant their exact node control action.
- `run_target` and action `cook_target` entries grant their exact node output.
- stopping the active cook and managed runtime remains available as the common
  safety path.

Switching Apps stops active runtime services before loading the next workflow.
Physical-motion Apps remain responsible for disarmed defaults, confirmations,
calibration checks, freshness checks, limits, and shutdown safeguards.
