# Project Artifacts v1

Project Artifacts give the Blacknode project lifecycle durable evidence for
data collection, policy training, and simulation. A Project links small typed
references. The extension package that created an artifact remains the owner
of its files and native manifest.

## Goals

- Show what a Project has produced, not only which workflows it can run.
- Turn Collect, Train, and Simulate into evidence-backed lifecycle stages.
- Reuse the manifests already produced by Blacknode extension packages.
- Capture supported node outputs automatically while a linked workflow runs.
- Link existing artifacts by an exact path for work created before Projects.
- Keep model binaries, datasets, logs, credentials, and calibration data out of
  the Project registry.

## Ownership

| Artifact | Authoritative owner | Indexed evidence |
|---|---|---|
| Episode dataset | `blacknode-dataset` | ID, path, task, FPS, episode/frame counts |
| Training run | `blacknode-training` | run ID, output path, phase, progress, losses |
| Checkpoint | `blacknode-training` | checkpoint path, run ID, step |
| Policy | `blacknode-training` | policy path, type, source checkpoint, dimensions |
| Replay evaluation | `blacknode-training` | episode, frames, aggregate errors |
| Simulation run | `blacknode-isaac` | run ID, log path, phase, inference counters |

The artifact index is local editor state at `.blacknode/artifacts.json`.
Projects store only `artifact_ids` in `.blacknode/projects.json`. Unlinking an
artifact from a Project does not remove the index record or its source files.
Deleting a Project does not delete artifacts.

## Reference contract

Each indexed reference has this provider-neutral shape:

```json
{
  "id": "dataset-2bd193725faf064e5d7a",
  "artifact_type": "dataset",
  "kind": "blacknode.episode-dataset",
  "provider": "blacknode-dataset",
  "name": "pick-cube",
  "locator": "/home/alex/.blacknode/datasets/pick-cube",
  "status": "completed",
  "workflow_slugs": ["collect-demonstrations"],
  "metadata": {
    "task": "Pick cube",
    "fps": 30,
    "episode_count": 12
  },
  "created_at": "2026-07-24T20:00:00+00:00",
  "updated_at": "2026-07-24T20:10:00+00:00"
}
```

`artifact_type` is one of `dataset`, `training_run`, `checkpoint`, `policy`,
`evaluation`, or `simulation_run`. `status` is `available`, `running`,
`completed`, or `failed`.

The ID is deterministic from provider, artifact type, and locator. Repeated
status events update one reference instead of adding duplicate cards. Logical
locators under `blacknode://` are used when a managed run has an identity but
has not produced a file path yet.

Metadata is an allowlisted summary. Fields whose names look like credentials,
tokens, secrets, passwords, or authorization data are never indexed. Import is
bounded by depth and item count, and checkpoint/model binaries are never
opened.

## Supported native records

The v1 importer understands:

- `blacknode.episode-dataset`
- `blacknode.training-job`
- `blacknode.training-run`
- `blacknode.action-chunking-checkpoint`
- `blacknode.policy-artifact`
- `blacknode.policy-replay-metrics`
- `blacknode.policy-runtime` from an Isaac node

Exact-path inspection accepts a supported JSON manifest, a directory containing
`dataset.json`, `run.json`, or `manifest.json`, or a checkpoint `.pt` path. It
does not crawl the filesystem or guess from unrelated files.

## Capture flow

When a node in a saved workflow linked to the active Project succeeds:

1. the editor checks the output for a supported native record;
2. it sends only candidate output data to the Project artifact import endpoint;
3. the server sanitizes and normalizes the reference;
4. the artifact index is inserted or updated by deterministic ID; and
5. the Project links the ID and refreshes its lifecycle evidence.

Artifact capture is auxiliary evidence. A capture error cannot change a
successful node cook into a failed cook.

## Lifecycle evidence

| Stage | Complete evidence |
|---|---|
| Collect | A linked dataset reports one or more saved episodes |
| Train | A linked policy artifact exists |
| Simulate | A linked simulation run or evaluation is completed |

A created empty dataset, running training job, checkpoint, or running
simulation is shown as progress, not completion. If no artifact exists yet,
the presence of the corresponding workflow keeps the stage available.

The Project overview chooses a guided action from the first relevant gap:
record the first episode, start or monitor training, evaluate a ready policy,
then deploy and operate.

## HTTP API

- `POST /projects/{project_id}/artifacts/import` captures supported typed
  records from a node output.
- `POST /projects/{project_id}/artifacts/inspect` adds supported records from
  one exact local path.
- `PATCH /projects/{project_id}` with `artifact_ids` links or unlinks
  references.

An import carrying `workflow_slug` is accepted only when that workflow is
linked to the Project. Read responses hydrate `artifacts` in the Project
payload and report whether filesystem-backed sources currently exist.

## Compatibility and next versions

Projects created before artifact support load with an empty `artifact_ids`
list. Existing package manifests and artifact files do not change.

Future versions can add provider registration, remote/object-store locators,
lineage between datasets/checkpoints/policies, evaluation thresholds,
deployment-to-policy links, telemetry evidence, and garbage collection for
unlinked index records. Those additions must keep the provider-owned artifact
and reference-only Project boundary.
