# App deployments

Blacknode App deployments package one or more Workflow Apps into a focused
operator surface. A deployment with one App opens it directly. A deployment
with several Apps opens a compact launcher and lets the operator return with
**All apps**.

The bundle retains the workflow graph as the execution model while granting
the customer surface access only to fields, actions, controls, and cook targets
declared by `metadata.operator_view`. Graph editing, workflow management,
package installation, console commands, file browsing, device administration,
and arbitrary node execution remain outside the operator boundary.

## Create a bundle

Every included workflow must validate and declare a versioned
`metadata.operator_view` with a stable `id`.

```powershell
blacknode export-app `
  packages\blacknode-dataset\templates\teleoperation-episode-recording.json `
  --id customer-recording `
  --name "Robot Data Collection" `
  --output customer-recording.blacknode-app.json
```

Pass multiple workflow paths to create an App launcher. Use `--start-app ID` to
record the preferred App in the manifest for deployment tooling and direct
links.

The command produces a `blacknode.app-deployment` schema-version 1 manifest.
It validates every workflow, records the union of `metadata.required_packages`,
and rejects persisted API keys, tokens, passwords, credentials, and secrets.
Configure credentials in the deployment host environment or its managed secret
store.

## Start the customer surface

Point the editor server at the bundle before starting Blacknode:

```powershell
$env:BLACKNODE_APP_DEPLOYMENT = (Resolve-Path .\customer-recording.blacknode-app.json)
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

The deployment manifest is immutable while the server runs. Field changes
affect the active operator session and the underlying workflow runtime. Update
the workflow defaults and export a new versioned bundle when customer defaults
need to change.

## Operator boundary

The server derives its permission set from the active App:

- `fields` grant updates to their exact node parameter.
- action `updates` grant their exact node parameter changes.
- action `control` entries grant their exact node control action.
- `run_target` and action `cook_target` entries grant their exact node output.
- stopping the active cook and managed runtime remains available as the common
  safety path.

Switching Apps stops active runtime services before loading the next workflow.
Physical-motion Apps remain responsible for disarmed defaults, confirmations,
calibration checks, freshness checks, limits, and shutdown safeguards.
