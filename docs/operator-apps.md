# Workflow Apps

Workflow Apps present a focused operator interface backed by an ordinary
Blacknode workflow. The app and node graph share parameters, managed services,
runtime outputs, safety checks, and saved workflow state.

Pressing a shortcut for a workflow with `metadata.operator_view` opens its App
surface. **Edit workflow** reveals the nodes and connections, and the **App**
control in the workflow tab bar returns to the operator surface.

## Operator view contract

An operator view is declared inside workflow metadata:

```json
{
  "operator_view": {
    "schema_version": 1,
    "id": "collect-episodes",
    "title": "Collect episodes",
    "description": "Capture synchronized robot demonstrations.",
    "run_target": {
      "node_id": "recorder",
      "port": "dashboard",
      "mode": "live",
      "label": "Start live"
    },
    "sections": [
      {
        "id": "live",
        "widgets": [
          {
            "type": "image",
            "id": "camera",
            "title": "Camera",
            "source": { "node_id": "camera", "port": "preview" }
          }
        ]
      }
    ]
  }
}
```

Supported widgets are `image`, `status`, `metrics`, `fields`, and `actions`.
Image, status, and metric widgets read live node output ports. Field widgets
update declared node parameters. Actions can update parameters, cook a declared
node output, or call a node's existing direct-control endpoint.

Node IDs, ports, parameters, and controls must exist in the workflow and its
live node schemas. Operator metadata does not create a second runtime contract.

## Keyboard shortcuts and pedals

Open **Shortcuts & pedals** in a Workflow App to bind any declared action to a
keyboard key or game-controller button. USB pedals that identify as keyboards
are assigned with **Assign key**; pedals that identify as game controllers use
**Assign pedal**. An action can keep one binding of each kind, and assignments
are saved in the current browser under the operator view's stable `id`.

Bindings call the same action path as the on-screen button. They do not bypass
confirmations, recorder preconditions, calibration checks, stale-data checks,
joint limits, or motion authorization. Keyboard bindings are ignored while the
operator is editing an input, textarea, or select control.

## Safety

Opening an App surface does not automatically authorize motion. Physical-motion
workflows remain disarmed, and their app metadata must retain confirmations for
arming. Destructive actions such as discarding an incomplete episode also need
explicit confirmation. Stopping live services warns the operator that robot
shutdown can release actuator torque.

The first shipped app is **Collect episodes**, provided by the
`teleoperation-episode-recording` template from `blacknode-dataset`.
