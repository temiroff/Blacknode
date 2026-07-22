# Graph deployment — design and roadmap

**Status:** phase 1 implemented. Phases 2-4 are design intent, not built.

Deploying a graph means running it as a long-lived background process that
outlives the editor, so it can act as live infrastructure other graphs build
on. Deploy a camera publisher once, then keep editing a separate graph that
subscribes to it.

## What already existed

Most of the execution half of deployment was already in the tree before this
feature. It is worth naming, because the deployment layer is deliberately thin
on top of it rather than a parallel implementation.

`export_workflow_python()` in `python/blacknode/workflow.py` emits a
standalone script that bootstraps the Blacknode runtime (via `BLACKNODE_HOME`,
the repo, or a venv), rebuilds the graph, runs it live, and then calls
`_hold_live_runtime_if_needed()` — which blocks while live nodes run and tears
the runtime down on exit. That script *is* the deployment artifact.

`run_graph_live()` in `python/blacknode/live_sync.py` already posts to
`/sync/runs`, `/sync/events`, and `/sync/runs/{id}/finish` on
`BLACKNODE_EDITOR_URL`, so a detached process reports its lifecycle back into
the editor with no new transport.

Every package implements `runtime_status()` / `stop_runtime_services()`,
aggregated at `/runtime/status` and `/runtime/stop`.

`ros2_runtime._managed_detached` and `robot._managed_drivers` are the existing
supervised-subprocess pattern; `editor-server/run_store.py` is the existing
JSON-file-per-record store pattern. Deployment copies both rather than
inventing new ones.

The gaps were therefore narrow: **detachment** (live runtime ran inside the
editor-server process, so quitting the editor killed the streams),
**persistence** (nothing survived a restart, so orphans could not be
reclaimed), and **addressability** (nothing declared where a deployed graph's
outputs could be reached).

## Why local processes before Docker

The obvious instinct is "deploy = build a container." For this codebase that
is the wrong first step, for reasons the repo already documents:

- Docker Desktop gives a container no `/dev/video*`. That is exactly why
  `ROS2USBCamera` captures on the host and bridges MJPEG into the ROS graph.
  Containerising a camera-publisher graph breaks the flagship example.
- DDS discovery does not cross the Docker Desktop NAT on Windows and macOS
  (noted in `packages/blacknode-ros2/README.md`). A containerised deployment
  could not be subscribed to from a graph running in the editor, which is the
  entire point of the feature.

So `target` is an abstraction with three implementations, delivered in order:
`local-process` (phase 1, no constraints), `docker` (phase 3, for graphs that
touch no host hardware — CI, headless processing), and `remote` (phase 4, the
robot story). Same snapshot, same registry, different runner.

## The deployable unit is a snapshot

A deployment freezes the workflow JSON at deploy time, together with the
resolved package lock, and hashes the pair. That hash is the version.

Deploying a *snapshot* rather than a live reference to an editor tab is what
makes versioning fall out for free: the tab keeps changing, the deployment
does not. "Push a new version" is then the same operation locally and on a
robot — produce a new snapshot, swap which one is active, keep the old one for
rollback.

Two kinds of deployment fall out of whether the graph contains live nodes
(`_bn_live_capable` in the node registry):

| Kind | Contains live nodes | Expected end state |
|---|---|---|
| `service` | yes | stays `running` until stopped |
| `job` | no | runs once, ends `exited` with code 0 |

This distinction matters in the UI: `exited` is success for a job and failure
for a service.

## Exports: how graphs compose (phase 2)

This is the part that makes cross-graph composition real, and it is where the
ROS 2 adapter architecture pays off.

A deployment should declare **what it provides** as addressable endpoints with
a scheme — `ros2topic:/camera/image_raw` plus message type, `http:` for an
MJPEG URL, later `mqtt:` for a topic pattern. The deployed process can derive
these from its own graph at startup and report them through the sync channel
it already uses.

Once the registry holds exports, the editor can offer them where they are
actually needed: dropping a subscribe node shows a picker of live exports from
running deployments, labelled by deployment instead of by raw topic string.

Deployment stays transport-agnostic. Adding MQTT later means a new
integration-layer package with capability adapters (exactly like
`blacknode-ros2` — see `docs/packages.md`), surfacing as a new export scheme
with no change to the deployment machinery.

## Known hazards

**Resource conflicts.** A deployed camera publisher holds camera index 0; an
editor graph with a `Camera` node on the same index then fails with a generic
"already in use" message. The registry knows what is deployed, so deploy
should refuse or warn when a new deployment claims a device or port an
existing one holds, and the editor should attribute the failure to the
specific deployment. *Not yet implemented — phase 2.*

**Double-running.** Deploying the graph currently running live in the editor
produces two copies competing for the same hardware and topics. Intended
semantics: deploy stops the editor's live runtime for that graph and hands
ownership to the deployment. *Not yet implemented — phase 2.*

**Secrets.** Deployed processes inherit the editor server's environment so
provider keys (`VISION_API_KEY`, `NVIDIA_API_KEY`, …) keep working. Keys are
never copied into the snapshot on disk.

## Robot deployment (phase 4)

Deliberately scoped out, but the seam matters so the wrong thing is not built
twice.

Carries over: snapshot-as-version, the registry and record shape, exports, and
the stop/start/redeploy verbs. A robot is largely a `remote` target.

Does not carry over, and is where the real work is: provisioning a fresh
machine, atomic activation with rollback (a bad policy on a robot is a
physical hazard, not a failed request), operating while disconnected, and
staged rollout across a fleet.

Safety rule: a deployed graph containing `PolicyRuntime`, `ROS2SetJoint`, or
any other motion node must land **disarmed**. Arming stays a separate explicit
act. Deploy must never imply arm.

Dependency: robot deployment needs the **`ros2_ws` workspace aggregator** — a
command collecting every installed package's `ros2_ws/src/*` into one
workspace for a single `colcon build`. It is agreed but unbuilt, and robot
deploy is what makes it mandatory, since the robot must have the colcon
packages built before a deployed graph can talk to them. Build it as part of
phase 4, not before.

## Phases

**Phase 1 — local process deployments (done).** Snapshot + hash, on-disk
registry under `.blacknode/deployments/`, detached local-process runner,
lifecycle (deploy / stop / start / delete), per-deployment logs, pid
reconciliation on read, HTTP API, and a Deployments panel with a Deploy
button.

**Phase 2 — composition.** Exports declaration and reporting, the subscribe
node picker, resource-conflict detection, and editor/deployment ownership
handoff.

**Phase 3 — container target.** `docker` runner for graphs that touch no host
hardware, reusing the same snapshot and registry.

**Phase 4 — remote and robot.** Provisioning, atomic activation with
rollback, offline operation, fleet rollout, disarmed-on-arrival safety, and
the `ros2_ws` aggregator.

## Phase 1 reference

Registry lives at `.blacknode/deployments/<id>/` with `deployment.json`
(record), `snapshot.json` (frozen workflow), `graph.py` (generated script),
and `deployment.log` (captured output).

| Endpoint | Purpose |
|---|---|
| `GET /deployments` | List records, pid-reconciled |
| `POST /deployments` | Snapshot the current graph (or a supplied workflow) and start it |
| `GET /deployments/{id}` | One record |
| `POST /deployments/{id}/stop` | Terminate the process, keep the snapshot |
| `POST /deployments/{id}/start` | Re-run the existing snapshot |
| `DELETE /deployments/{id}` | Stop and remove the record and its directory |
| `GET /deployments/{id}/logs` | Tail captured output |

Core module: `python/blacknode/deployments.py`. It has no editor-server or
FastAPI imports, so the same store backs the CLI and, later, remote targets.
