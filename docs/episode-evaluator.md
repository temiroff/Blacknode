# Episode Evaluator — design & first slice

The robot-episode counterpart to the LLM `RateOutput` judge in
[Training Data Loop](training-data-loop.md). It closes the physical-robot
learning loop — `record → evaluate → keep good → train → deploy → record` — the
architecture Blacknode already proved for text agents, lifted to
`blacknode-dataset` episodes.

**Implemented (first slice):** `EpisodeEvaluator` + `EpisodeStats` nodes and a
self-calibrating analysis core (`packages/blacknode-dataset/nodes/analysis.py`),
covered by `tests/test_episode_evaluator.py` (no robot/cameras/ffmpeg needed).

## Design rule: nothing task-specific is hard-coded

The node ships *mechanisms*. Every task-specific number or label is either
**inferred from the episode's own statistics** or **supplied by the caller** —
never baked into the code.

| Thing that could be hard-coded | How it's actually determined |
|---|---|
| Which joint is the gripper | Most bimodal observation column (Otsu between-class variance), with a confidence that drops when the pick is ambiguous — never "last joint" |
| Open/closed bands | The gripper column's own two clusters, per-episode |
| A slip / lost grip | The **commanded** gripper action disagreeing with the **achieved** gripper for a sustained run — no guess about which aperture means "closed" |
| "Moving" cutoff, stall noise floor | Percentiles of this episode's velocity / tracking-error distributions |
| Subtask phases | Segments *discovered* from change-points, tagged with neutral evidence (`grip-change` / `move` / `settle`) — no assumed grasp→lift→transport ladder, no assumed order or count |
| **What "success" means** | The node refuses to invent it. It always computes signals; the *verdict* needs a caller-supplied criterion |

If no success criterion is supplied, the node returns `success=None,
confidence=0` and a report telling you to supply one. Measurement is universal
and data-driven; the *definition of success* is the user's, not the code's.

## Data it consumes (real schema)

A saved episode's `data.parquet` (via `storage.episode_replay → data_path`):
`timestamp`, and vector-over-`joint_names` columns `observation.state`,
`action`, `leader.state`, plus `task`. **No force/tactile/object-pose channel
exists** — so "lost grip" is the commanded-vs-achieved gripper divergence above,
not a sensor read.

## `EpisodeEvaluator`

```
inputs:  trigger, episode|dataset|dataset_id+root+episode_index,
         success_rule:Text, reference:Dict, save_label:Bool
outputs: success:Bool, score:Float, failed_stage:Text, confidence:Float,
         subtasks:List, signals:Dict, verdict:Dict, episode:Dict, report:Text
```

`confidence` is the **min** of the success-criterion confidence and the
gripper-discovery confidence, so an ambiguous gripper pick can't produce a
falsely confident verdict. The `verdict` is written back into the episode's
`episode.json` under `"evaluation"` (guarded by `save_label`) — that is the
"robot remembers how it fails" memory, stored where the episode lives.

### Supplying a success criterion (pick one)

- **`success_rule`** — a boolean expression over the signals, e.g.
  `"not grip_slip and 'move' in tags"`. Evaluated in a restricted namespace
  (`grip_slip`, `slip_frames`, `stall_frames`, `tags`, `n_segments`,
  `max_tracking_error`, …). The definition lives in the caller's string.
- **`reference`** — `analysis.build_reference([...])` over the signal
  fingerprints of known-good demos; the episode is failed when it's a
  z-score outlier. The definition comes from *data*.
- **vision model** — phase 2 (§below).

## `EpisodeStats`

Pure aggregation over the verdicts already written to a dataset's episodes:
`success_rate`, `attempts`, `evaluated`, `by_stage`, `common_failures`. This is
the pitch's "72% success / common failures" panel, from data the evaluator
already produced — no new sensing, no model.

## Wiring the loop (real node names)

```
DatasetBrowser ──episode──▶ EpisodeEvaluator ──success──▶ (gate) ──▶ ACTTraining(start)
                                    │
                                    └── verdict ▶ episode.json  (labeled memory)  ▶ EpisodeStats
```

Next build step is a small `DatasetFilterByVerdict` node that runs the evaluator
across a dataset and emits the `success`-only subset whose path feeds
`ACTTraining.dataset_path`. That single edge closes the loop end-to-end on one task.

## Phase 2 (after the loop closes)

- **Vision pass inside `EpisodeEvaluator`** — sample frames from the episode's
  camera mp4, judge against the episode's own `task` string via the
  `blacknode-vision` provider stack, confidence-blend with the rule/reference
  verdict, and route disagreement to review. (Deliberately not in the first
  slice: keeps the core deterministic and hardware-free.)
- **`EpisodeReasoner`** — maps `signals` → `likely_causes`, where every cause
  must cite a signal (`grip_slip → "commanded hold, gripper opened at frame N"`),
  so it can't fabricate a cause that isn't in the data.
- **`EpisodeSuggester`** — maps failure evidence to a *typed, wireable* action
  (`{action: "collect_demos", n: 10}`, `{action: "adjust_training", param: …}`),
  a graph edge rather than prose.
- **Interactive episode viewer** — editor surface over `subtasks` + `signals` +
  existing replay.

## Open questions for the owner

- **Gripper-discovery confidence floor.** Below what confidence should the node
  decline to name a gripper and downgrade to "arm-only" analysis? Per-robot
  hints in `dataset.json` features would remove the ambiguity entirely.
- **Slip run-length.** Sustained-mismatch threshold is 3 frames to reject
  1–2 frame command/achieve latency; should it be fps-relative?
- **Reference fingerprint.** Current features are `grip_slip / n_stall /
  n_segments / max_tracking_error / n_move`. Which task-agnostic features
  belong here is worth iterating once real good/bad demos exist.
```
