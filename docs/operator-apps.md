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
    "icon": "record",
    "settings": {
      "title": "Collect episodes settings",
      "groups": [
        {
          "id": "connection",
          "title": "Robot connection",
          "items": [
            {
              "label": "ROS bridge host",
              "node_id": "rosbridge",
              "param": "host",
              "input": "text",
              "apply_to": [
                { "node_id": "teleoperation", "param": "host" }
              ]
            }
          ]
        }
      ]
    },
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
      },
      {
        "id": "setup",
        "region": "parameters",
        "widgets": [
          {
            "type": "fields",
            "id": "settings",
            "title": "Dataset",
            "items": [
              {
                "label": "Dataset ID",
                "node_id": "dataset",
                "param": "dataset_id",
                "input": "text"
              }
            ]
          }
        ]
      }
    ]
  }
}
```

Supported widgets are `image`, `viewer`, `status`, `metrics`, `fields`, and
`actions`. Image, viewer, status, and metric widgets read live node output
ports. A `viewer` embeds an HTTP(S) URL produced by a trusted workflow node and
is intended for managed simulation, robot-scene, and other interactive browser
surfaces. Field widgets update declared node parameters. Actions can update
parameters, cook a declared node output, or call a node's existing
direct-control endpoint.

Use `input: "file_path"` for a path that must exist on the App host. It keeps
the path editable and adds a **Browse…** button backed by Blacknode's filesystem
browser. Declare `extensions` to filter selectable files, and optionally set
`picker_title` and `button_label`. This is appropriate for robot descriptions,
scenes, datasets, checkpoints, and other host-side artifacts.

Sections render in the central workspace by default. Set a section's optional
`region` to `parameters` to place its fields and actions in the right-side
parameters rail. The rail becomes part of the normal vertical layout on narrow
screens.

Node IDs, ports, parameters, and controls must exist in the workflow and its
live node schemas. Operator metadata does not create a second runtime contract.

The optional `icon` selects the glyph shown in a deployed App bar. Supported
values are `record`, `camera`, `robot`, `workflow`, and `play`.

Use optional `settings.groups` for connection, robot, camera, storage, and
other setup values that operators need when graph editing is unavailable. Each
setting grants access to its exact `node_id` and `param`. An optional `apply_to`
list mirrors one shared value to additional declared node parameters, which is
useful when several runtime nodes consume the same host or port. Changes apply
to the active App session immediately.

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

Workflow Apps can be delivered through the focused customer surface described
in [App deployments](app-deployments.md).
