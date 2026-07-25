# Projects

Projects are the durable workspace above individual Blacknode workflows. A
project groups the workflows and devices used to move a robotics application
from building and calibration through deployment and operation.

Workflow tabs remain the place where graphs are edited. Opening a project
restores its saved workflows as tabs and adds project context around them.

## Projects v1

Projects v1 provides:

- local project creation, naming, description, renaming, and removal;
- links to any number of saved workflows;
- links to any number of paired devices;
- restoration of linked workflows as editor tabs;
- a project/workflow breadcrumb while a linked workflow is active;
- lifecycle guidance based on evidence in linked workflows and devices; and
- typed links to provider-owned dataset, training, policy, and simulation
  artifacts; and
- an optional robot-learning starter that prepares the next predefined
  workflow; and
- a view of deployments reported by linked devices.

Project data is local editor state. It is stored in
`.blacknode/projects.json`, is excluded from Git, and must not contain pairing
tokens, calibration data, workflow graph copies, run logs, or artifact
contents. Typed references are indexed separately in
`.blacknode/artifacts.json`; see [Project Artifacts v1](project-artifacts.md).

## Ownership

A project stores references, not copies:

| Resource | Owner | Project reference |
|---|---|---|
| Workflow graph | `workflows/<slug>.json` | workflow slug |
| Paired device and credentials | device registry | device ID |
| Robot profile and calibration selection | workflow metadata | discovered from the linked workflow |
| Calibration record | hardware service | never copied into the project |
| Deployment revision and process state | target runtime | project ID and workflow slug |
| Dataset, training, policy, and simulation artifacts | their extension package | typed artifact ID |

This keeps credentials and physical-hardware calibration bound to their
existing secure and hardware-aware owners.

## Stored record

The local project registry uses schema version 1:

```json
{
  "schema_version": 1,
  "projects": [
    {
      "id": "leader-follower-demo",
      "name": "Leader Follower Demo",
      "description": "SO-ARM leader and follower bring-up",
      "workflow_slugs": [
        "so-arm101-leader-deploy",
        "so-arm102-follower-deploy"
      ],
      "device_ids": [
        "alex-desktop-usb-...31481...",
        "alex-desktop-usb-...31741..."
      ],
      "artifact_ids": [
        "dataset-2bd193725faf064e5d7a"
      ],
      "starter_kit": "robot_learning",
      "active_workflow_slug": "so-arm101-leader-deploy",
      "created_at": "2026-07-24T20:00:00+00:00",
      "updated_at": "2026-07-24T20:00:00+00:00"
    }
  ]
}
```

Project IDs are stable. Renaming a project does not change its ID. Workflow
renames update project references. Missing or deleted resources remain visible
as missing references until the user removes or replaces them, avoiding silent
changes to project intent.

`active_workflow_slug` is the workflow selected after opening the project. It
must be one of `workflow_slugs`; when it is absent the first linked workflow is
used.

## HTTP API

The editor server exposes:

- `GET /projects`
- `POST /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `POST /projects/{project_id}/artifacts/import`
- `POST /projects/{project_id}/artifacts/inspect`
- `POST /projects/{project_id}/starter-workflows/{stage}`

Create and update requests use the persisted fields above. Read responses also
hydrate workflow and device references with their current names, availability,
node types, and non-secret device information.

The API tolerates resources that are temporarily unavailable. A missing
workflow or device is returned with `exists: false` instead of preventing the
rest of the project from opening.

## Deployment ownership

New remote deployment revisions may declare both:

```json
{
  "project_id": "leader-follower-demo",
  "workflow_slug": "so-arm101-leader-deploy"
}
```

The editor server accepts the pair only when the project exists, the workflow
is linked to it, and the target device is linked to it. The target runtime
persists both fields on the deployment record and revision manifest. A revision
with no ownership fields preserves the deployment's existing ownership.

An existing owned deployment cannot be reassigned to another project or
workflow by staging an update. Stage a new deployment for the new owner.
Previously created deployment records remain compatible and are returned with
empty ownership fields; the editor describes them as unassigned and keeps them
available in Deployments.

The Projects overview includes only deployments whose `project_id` exactly
matches the open project. This makes lifecycle status and deployment counts
project-specific rather than inferred from every process on a linked device.

## Lifecycle evidence

The project overview uses evidence, not a manually advanced wizard:

| Stage | Evidence shown in v1 |
|---|---|
| Connect | One or more paired devices are linked |
| Build | One or more saved workflows are linked |
| Configure | A linked workflow selects a robot calibration when required |
| Collect | A linked dataset contains at least one saved episode |
| Train | A linked policy artifact exists |
| Simulate | A linked simulation run or evaluation completed |
| Deploy | The target runtime reports a staged or active deployment owned by the project |
| Operate | The target runtime reports a running deployment owned by the project |

Collect, Train, and Simulate are optional paths. Their absence does not block a
project that deploys an already available policy or a deterministic controller.
A corresponding workflow makes the stage available; an empty dataset, running
job, checkpoint, or running simulation shows progress; only the artifact
evidence above marks it complete.

The next action is selected from the first actionable gap:

1. install the device runtime, pair the robot, and link it;
2. choose or link a saved workflow;
3. select calibration when a robot workflow requires it;
4. record the first episode when collection is configured;
5. train or monitor a policy when recorded data is ready;
6. evaluate a ready policy when simulation is configured;
7. deploy or monitor a running deployment.

When `starter_kit` is `robot_learning`, Next can create, link, and open the
predefined collection, ACT training, or Isaac evaluation workflow needed for
the current gap. A custom linked workflow for that stage takes priority. See
[Guided Projects](guided-projects.md).

## Editor behavior

- **Projects** is a top-level editor panel beside Workflows and Devices.
- **Workflows** continues to manage individual saved graphs.
- Opening a project opens every available linked workflow as a tab and selects
  `active_workflow_slug`.
- Existing unrelated or dirty tabs are preserved.
- The breadcrumb reads `Project / Workflow` only when the active workflow
  belongs to the active project.
- A project can link the current tab only after that workflow has been saved.
- Device and workflow selectors show existing names as well as stable IDs or
  slugs so similarly named robots remain distinguishable.

## Future extensions

Later versions can add artifact lineage, evaluation gates, deployment-to-policy
links, dashboards, telemetry views, project members, and cloud
synchronization. The deployment ownership fields provide the stable join for
exact deployment history when a history index is added.

Those additions should preserve the core boundary: applications and workflows
depend on capabilities and stable resource identities, while providers retain
ownership of credentials, physical hardware, and generated artifacts.
