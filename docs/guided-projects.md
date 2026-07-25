# Guided Projects

Guided Projects provide a click-through starting path for robot learning while
preserving the normal workflow editor. A Project can use the
`robot_learning` starter kit or remain fully custom.

## Robot learning starter

New Projects offer **Robot learning starter — recommended**. The Project's
**Next step** action creates, saves, links, and opens the appropriate workflow
only when that stage is needed:

| Stage | Predefined template |
|---|---|
| Collect | `teleoperation-episode-recording` from `blacknode-dataset` |
| Train | `act-training` from `blacknode-training` |
| Simulate | `isaac-act-policy-deployment` from `blacknode-isaac` |

The generated saved workflow is named for the Project, for example
`Demo Arm · Train ACT policy`. Its metadata records:

```json
{
  "starter_kit": "robot_learning",
  "starter_stage": "train",
  "source_template": "act-training",
  "project_id": "demo-arm"
}
```

Generation is idempotent. Pressing the action again opens the existing linked
starter workflow rather than creating a duplicate. The template is validated
and its package dependencies are checked before a saved workflow is created.
When a required package or template is unavailable, the Project displays the
dependency error and does not create a partial workflow.

Generated workflows are prefilled from Project context:

- collection uses a Project-specific dataset ID, task, and run IDs, selects
  automatic ROS 2 transport, and remains disarmed;
- training selects the newest completed linked dataset and assigns a
  Project-specific training run ID; and
- simulation selects the newest available linked policy and assigns
  Project-specific Isaac run IDs while remaining in status mode.

## Evidence-driven progression

The helper advances from Project evidence:

1. install the device runtime, pair the robot, and link it to the Project;
2. create and open the recording workflow;
3. calibrate the robot required by that workflow;
4. record and save at least one dataset episode;
5. create or open the ACT training workflow;
6. export a policy artifact;
7. create or open the Isaac evaluation workflow; and
8. deploy using the Project's robot-specific deployment workflow.

Every Lifecycle card is also an action:

- Build opens the linked workflows or prepares the first starter workflow.
- Connect opens Devices.
- Configure opens the first robot workflow missing a saved calibration
  selection.
- Collect, Train, and Simulate open a custom workflow or prepare their starter
  workflow.
- Deploy and Operate open Deployments.

Configure turns complete only after every linked robot workflow has a saved
calibration selection. Preparing or opening a workflow alone does not make the
physical calibration complete.

Artifact capture supplies the evidence for recorded episodes, training
progress, exported policies, and completed evaluations. The helper does not
mark a stage complete merely because its template was opened.

## Custom workflows

Users can link any saved workflow at any time. For each lifecycle stage, an
existing custom linked workflow takes priority over a generated starter
workflow. Starter workflows stay ordinary editable saved workflows.

Selecting **Use custom setup** stops predefined template suggestions and keeps
all already linked workflows and artifacts. Selecting
**Use robot learning starter** enables the helper on an existing Project.

Custom Projects do not create starter workflows. This keeps Projects for
deterministic controllers, perception, agents, and other applications outside
the robot-learning sequence.

## API and storage

The Project record stores:

```json
{
  "starter_kit": "robot_learning"
}
```

Existing Projects load with `starter_kit: null`.

The editor server exposes:

```text
POST /projects/{project_id}/starter-workflows/{stage}
```

`stage` is `collect`, `train`, or `simulate`. The response includes the
hydrated Project, the saved workflow reference, and whether it was newly
created.

## Safety

Starter generation only prepares and opens workflows. It does not arm a robot,
start recording, begin training, start simulation, or deploy automatically.
Robot motion remains disarmed by default and continues through the workflow's
normal calibration, stale-data, limit, and shutdown checks.
