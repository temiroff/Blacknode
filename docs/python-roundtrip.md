# Python Round-Trip

Blacknode can export a visual workflow to readable Python or LangGraph, import
that generated file back into the editor, and stream external Python execution
state into run replay.

## Export

Editor:

1. Start Blacknode.
2. Open or build a workflow with an `Output` node.
3. Use the top-bar `Export` menu.
4. Choose `Plain Python` or `Python Class`.

CLI:

```powershell
blacknode export-python templates\text-pipeline.json --output workflow.py
blacknode export-python templates\text-pipeline.json --style class --output workflow.class.py
```

Framework exporter:

```powershell
blacknode export-framework templates\text-pipeline.json --target python --output workflow.python.py
blacknode export-framework templates\text-pipeline.json --target python-class --output workflow.class.py
```

The exported script keeps stable node IDs, clear variable names, step comments,
typed node params, visual edges, and the workflow entrypoint.

## Run

```powershell
python workflow.py
```

Expected result for the starter workflow:

```text
Hello World
```

## Import Back Into Blacknode

Editor:

1. Click `Import` in the top bar.
2. Pick a Blacknode Python or LangGraph export.
3. The editor opens it as a new workflow tab.

CLI:

```powershell
blacknode import-python workflow.py --output imported.workflow.json
blacknode import-python workflow.langgraph.py --output imported-langgraph.workflow.json
blacknode validate imported.workflow.json
```

HTTP:

```powershell
$code = Get-Content .\workflow.py -Raw
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:7777/import/python `
  -ContentType application/json `
  -Body (@{ code = $code; name = "Imported Workflow" } | ConvertTo-Json)
```

## Live Sync

Live sync lets a Python script push run events back into the editor.

1. Start Blacknode with `start.bat`.
2. Export a workflow to Python.
3. Run the script with `BLACKNODE_SYNC_URL` pointing at the editor backend.

PowerShell:

```powershell
$env:BLACKNODE_SYNC_URL="http://127.0.0.1:7777"
python workflow.py
```

When live sync is enabled, the editor opens the workflow tab and shows node
execution through run replay. If `BLACKNODE_SYNC_URL` is not set, the exported
script runs normally without contacting the editor.

Live-sync endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /sync/runs` | Start an external Python run. |
| `POST /sync/events` | Append run replay events. |
| `POST /sync/runs/{run_id}/finish` | Mark the run success or error. |
| `GET /sync/runs/{run_id}` | Read a running or finished run snapshot. |
