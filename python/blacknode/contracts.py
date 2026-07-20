"""Phase 0 contract catalog: the frozen set of ``kind`` strings used across
Blacknode packages, and constructors for the contracts that don't have a
producer yet.

See ``.local-notes/phase-0-contract-catalog.md`` for the full rationale and
field-level specification of every contract listed here. In short: every
extension package already independently converged on describing typed
payloads as ``{"kind": "blacknode.<name>", "schema_version": 1, ...}``. This
module is the single place that set of names is enumerated, so a new
contract can be checked against what already exists instead of silently
duplicating it under a different name.

This module intentionally has no dependencies beyond the standard library —
core stays hardware/ROS/vision-neutral (see the roadmap's Architecture Rule
1). Constructors for contracts that already ship in an extension package
(frame-stream, episode, policy-artifact, ...) are NOT duplicated here; that
package's source is the contract's source of truth. Only contracts with no
existing producer get a constructor here, since there's nowhere else for
one to live yet.
"""
from __future__ import annotations

import time
from typing import Any

# --- Part 1: already shipping elsewhere -------------------------------------
# Enumerated here only as a lookup table (kind -> owning package) so new code
# can check before inventing a competing shape. Field-level shapes live in
# the owning package; see the catalog doc for the one-line purpose of each.

SHIPPING_KINDS: dict[str, str] = {
    # Physical / spatial state
    "blacknode.camera-device": "blacknode-perception",
    "blacknode.camera-discovery": "blacknode-perception",
    "blacknode.camera-calibration": "blacknode-perception",
    # Streams
    "blacknode.frame-stream": "blacknode-perception",
    "blacknode.stream-frame": "blacknode-dataset",
    "blacknode.replay-stream": "blacknode-dataset",
    "blacknode.sample-stream": "blacknode-ros2",
    "blacknode.latest-value-stream": "blacknode-perception",
    # Episodes / datasets
    "blacknode.episode": "blacknode-dataset",
    "blacknode.episode-journal": "blacknode-dataset",
    "blacknode.episode-frame": "blacknode-dataset",
    "blacknode.episode-dataset": "blacknode-dataset",
    "blacknode.episode-replay": "blacknode-dataset",
    "blacknode.dataset-catalog": "blacknode-dataset",
    # Export / publishing
    "blacknode.hdf5-export": "blacknode-dataset",
    "blacknode.hub-dataset": "blacknode-dataset",
    "blacknode.lerobot-export": "blacknode-dataset",
    "blacknode.huggingface-export": "blacknode-dataset",
    # Training / policy
    "blacknode.training-dataset": "blacknode-training",
    "blacknode.training-job": "blacknode-training",
    "blacknode.training-run": "blacknode-training",
    "blacknode.action-chunking-checkpoint": "blacknode-training",
    "blacknode.act-policy-model": "blacknode-training",
    "blacknode.policy-artifact": "blacknode-training",
    "blacknode.policy-prediction": "blacknode-training",
    "blacknode.policy-preview": "blacknode-training",
    "blacknode.policy-replay": "blacknode-training",
    "blacknode.policy-replay-frame": "blacknode-training",
    "blacknode.policy-replay-metrics": "blacknode-training",
    "blacknode.policy-runtime": "blacknode-controllers",
    "blacknode.policy-safety-gate": "blacknode-controllers",
    # Simulation
    "blacknode.isaac-command": "blacknode-isaac",
    "blacknode.isaac-observation": "blacknode-isaac",
    "blacknode.isaac-policy-bridge": "blacknode-isaac",
    # Teleoperation
    "blacknode.teleoperation-sample": "blacknode-skills",
}

# --- Part 2: new for Phase 0 --------------------------------------------------
# No producer exists yet anywhere in the codebase. Constructors below are the
# reference shape; adopt them as-is when Phase 1+ builds the first producer
# instead of inventing a parallel shape.

NEW_KINDS: dict[str, str] = {
    # Physical system
    "blacknode.robot-profile": "assembly identity, capabilities, driver and calibration references",
    "blacknode.mobile-base": "drive model, limits, command/state endpoints, and footprint",
    "blacknode.robot-model": "links, joints, frame names, geometry artifact, and controller mappings",
    "blacknode.sensor": "physical identity, frame, calibration, transport, health, and stream handle",
    # Streams
    "blacknode.odometry-stream": "pose and velocity estimate with source/receive time and sequence",
    "blacknode.imu-stream": "orientation, angular velocity, linear acceleration",
    "blacknode.laser-scan-stream": "2-D range scan with angle/range bounds",
    "blacknode.depth-stream": "depth frame handle with encoding and scale",
    "blacknode.point-cloud-stream": "point cloud handle",
    "blacknode.transform-stream": "frame-to-frame transform, static or dynamic",
    "blacknode.detection-stream": "a batch of detection2d/detection3d results",
    "blacknode.robot-state-stream": "joint positions/velocities and armed state",
    # Planning / execution
    "blacknode.pose": "frame-qualified position and orientation",
    "blacknode.map": "map artifact, resolution, origin, frame, and provenance",
    "blacknode.navigation-goal": "target pose or named location with tolerance",
    "blacknode.navigation-status": "navigation state machine, progress, and stop reason",
    "blacknode.detection2d": "labeled 2-D detection with pixel center/bbox",
    "blacknode.detection3d": "labeled 3-D detection with pose and extent",
    "blacknode.joint-trajectory": "joint-space waypoints over time",
    "blacknode.cartesian-trajectory": "tool-space pose waypoints over time",
    "blacknode.grasp-candidate": "scored gripper approach pose",
    "blacknode.manipulation-status": "manipulation state machine and stop reason",
    "blacknode.safety-policy": "velocity/step/staleness limits, generalized from policy-safety-gate",
    "blacknode.motion-authorization": "explicit, time-bound authorization to move",
    "blacknode.estop-state": "latched emergency-stop state",
}

ALL_KINDS: dict[str, str] = {**SHIPPING_KINDS, **NEW_KINDS}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stream_fields(frame: str, sequence: int) -> dict[str, Any]:
    now_ns = time.time_ns()
    return {
        "source_time_ns": now_ns,
        "receive_time_ns": now_ns,
        "sequence": sequence,
        "frame": frame,
        "valid": True,
    }


def robot_profile(
    profile_id: str, *, capabilities: list[str] | None = None,
    driver: dict[str, Any] | None = None, units: str = "radians",
) -> dict[str, Any]:
    return {
        "kind": "blacknode.robot-profile", "schema_version": 1,
        "profile_id": profile_id, "capabilities": list(capabilities or []),
        "driver": dict(driver or {}), "units": units,
    }


def mobile_base(
    drive_model: str, *, max_linear_velocity: float, max_angular_velocity: float,
    footprint_m: tuple[float, float], odom_frame: str = "odom", base_frame: str = "base_link",
    command_topic: str = "", state_topic: str = "",
) -> dict[str, Any]:
    if drive_model not in {"differential", "mecanum", "ackermann"}:
        raise ValueError(f"unsupported drive_model: {drive_model!r}")
    return {
        "kind": "blacknode.mobile-base", "schema_version": 1,
        "drive_model": drive_model,
        "max_linear_velocity": max_linear_velocity, "max_angular_velocity": max_angular_velocity,
        "footprint_m": list(footprint_m), "odom_frame": odom_frame, "base_frame": base_frame,
        "command_topic": command_topic, "state_topic": state_topic,
    }


def robot_model(
    model_id: str, *, joint_names: list[str], frame_names: list[str],
    geometry_artifact_path: str = "", controller_mappings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": "blacknode.robot-model", "schema_version": 1,
        "model_id": model_id, "joint_names": list(joint_names), "frame_names": list(frame_names),
        "geometry_artifact_path": geometry_artifact_path,
        "controller_mappings": dict(controller_mappings or {}),
    }


def sensor(
    sensor_id: str, sensor_type: str, *, frame: str, transport: str,
    calibration_path: str = "", stream_handle: dict[str, Any] | None = None, healthy: bool = False,
) -> dict[str, Any]:
    return {
        "kind": "blacknode.sensor", "schema_version": 1,
        "sensor_id": sensor_id, "sensor_type": sensor_type, "frame": frame, "transport": transport,
        "calibration_path": calibration_path, "stream_handle": dict(stream_handle or {}), "healthy": healthy,
    }


def pose(
    frame: str, *, position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    orientation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0), confidence: float | None = None,
) -> dict[str, Any]:
    x, y, z = position
    qx, qy, qz, qw = orientation
    result: dict[str, Any] = {
        "kind": "blacknode.pose", "schema_version": 1, "frame": frame,
        "position": {"x": x, "y": y, "z": z},
        "orientation": {"x": qx, "y": qy, "z": qz, "w": qw},
    }
    if confidence is not None:
        result["confidence"] = confidence
    return result


def odometry_stream(
    frame: str = "odom", child_frame: str = "base_link", *, sequence: int = 0,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    orientation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
    linear_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    angular_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, Any]:
    x, y, z = position
    qx, qy, qz, qw = orientation
    lx, ly, lz = linear_velocity
    ax, ay, az = angular_velocity
    return {
        "kind": "blacknode.odometry-stream", "schema_version": 1,
        **_stream_fields(frame, sequence), "child_frame": child_frame,
        "position": {"x": x, "y": y, "z": z},
        "orientation": {"x": qx, "y": qy, "z": qz, "w": qw},
        "linear_velocity": {"x": lx, "y": ly, "z": lz},
        "angular_velocity": {"x": ax, "y": ay, "z": az},
    }


def imu_stream(
    frame: str, *, sequence: int = 0,
    orientation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
    angular_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    linear_acceleration: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, Any]:
    qx, qy, qz, qw = orientation
    ax, ay, az = angular_velocity
    lx, ly, lz = linear_acceleration
    return {
        "kind": "blacknode.imu-stream", "schema_version": 1,
        **_stream_fields(frame, sequence),
        "orientation": {"x": qx, "y": qy, "z": qz, "w": qw},
        "angular_velocity": {"x": ax, "y": ay, "z": az},
        "linear_acceleration": {"x": lx, "y": ly, "z": lz},
    }


def laser_scan_stream(
    frame: str, *, sequence: int = 0, angle_min: float, angle_max: float, angle_increment: float,
    range_min: float, range_max: float, ranges: list[float],
) -> dict[str, Any]:
    return {
        "kind": "blacknode.laser-scan-stream", "schema_version": 1,
        **_stream_fields(frame, sequence),
        "angle_min": angle_min, "angle_max": angle_max, "angle_increment": angle_increment,
        "range_min": range_min, "range_max": range_max, "ranges": list(ranges),
    }


def depth_stream(
    frame: str, *, sequence: int = 0, snapshot_url: str = "", encoding: str = "16UC1", depth_scale: float = 0.001,
) -> dict[str, Any]:
    return {
        "kind": "blacknode.depth-stream", "schema_version": 1,
        **_stream_fields(frame, sequence),
        "snapshot_url": snapshot_url, "encoding": encoding, "depth_scale": depth_scale,
    }


def point_cloud_stream(frame: str, *, sequence: int = 0, point_count: int = 0, source_url: str = "") -> dict[str, Any]:
    return {
        "kind": "blacknode.point-cloud-stream", "schema_version": 1,
        **_stream_fields(frame, sequence),
        "point_count": point_count, "source_url": source_url,
    }


def transform_stream(
    frame: str, child_frame: str, *,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0), static: bool = False,
) -> dict[str, Any]:
    tx, ty, tz = translation
    rx, ry, rz, rw = rotation
    now_ns = time.time_ns()
    return {
        "kind": "blacknode.transform-stream", "schema_version": 1,
        "source_time_ns": now_ns, "receive_time_ns": now_ns,
        "frame": frame, "child_frame": child_frame,
        "translation": {"x": tx, "y": ty, "z": tz},
        "rotation": {"x": rx, "y": ry, "z": rz, "w": rw},
        "static": static,
    }


def detection_stream(frame: str, *, sequence: int = 0, detections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "kind": "blacknode.detection-stream", "schema_version": 1,
        **_stream_fields(frame, sequence),
        "detections": list(detections or []),
    }


def robot_state_stream(
    *, sequence: int = 0, joint_positions: dict[str, float] | None = None,
    joint_velocities: dict[str, float] | None = None, units: str = "radians", armed: bool = False,
) -> dict[str, Any]:
    return {
        "kind": "blacknode.robot-state-stream", "schema_version": 1,
        **_stream_fields("base_link", sequence),
        "joint_positions": dict(joint_positions or {}), "joint_velocities": dict(joint_velocities or {}),
        "units": units, "armed": armed,
    }


def map_artifact(
    map_id: str, *, frame: str = "map", resolution: float, origin: dict[str, Any] | None = None,
    artifact_path: str = "", created_by: str = "",
) -> dict[str, Any]:
    return {
        "kind": "blacknode.map", "schema_version": 1,
        "map_id": map_id, "frame": frame, "resolution": resolution,
        "origin": origin or pose(frame),
        "artifact_path": artifact_path,
        "provenance": {"created_at": _now_iso(), "created_by": created_by, "source": "slam"},
    }


def navigation_goal(*, target: dict[str, Any] | None = None, named_location: str = "", tolerance_m: float = 0.1) -> dict[str, Any]:
    if not target and not named_location:
        raise ValueError("navigation_goal requires target or named_location")
    return {
        "kind": "blacknode.navigation-goal", "schema_version": 1,
        "target": target or {}, "named_location": named_location, "tolerance_m": tolerance_m,
    }


def navigation_status(
    state: str = "idle", *, current_pose: dict[str, Any] | None = None,
    distance_remaining_m: float = 0.0, eta_seconds: float = 0.0, recovery_count: int = 0, stop_reason: str = "",
) -> dict[str, Any]:
    valid_states = {"idle", "planning", "moving", "recovering", "succeeded", "failed", "cancelled"}
    if state not in valid_states:
        raise ValueError(f"unsupported navigation state: {state!r}")
    return {
        "kind": "blacknode.navigation-status", "schema_version": 1,
        "state": state, "current_pose": current_pose or {},
        "distance_remaining_m": distance_remaining_m, "eta_seconds": eta_seconds,
        "recovery_count": recovery_count, "stop_reason": stop_reason,
    }


def detection2d(label: str, *, confidence: float, center: tuple[float, float], bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    cx, cy = center
    bx, by, bw, bh = bbox
    return {
        "kind": "blacknode.detection2d", "schema_version": 1,
        "label": label, "confidence": confidence,
        "center": {"x": cx, "y": cy}, "bbox": {"x": bx, "y": by, "width": bw, "height": bh},
    }


def detection3d(label: str, *, confidence: float, frame: str, pose_: dict[str, Any], extent: tuple[float, float, float]) -> dict[str, Any]:
    ex, ey, ez = extent
    return {
        "kind": "blacknode.detection3d", "schema_version": 1,
        "label": label, "confidence": confidence, "frame": frame, "pose": pose_,
        "extent": {"x": ex, "y": ey, "z": ez},
    }


def joint_trajectory(joint_names: list[str], waypoints: list[dict[str, Any]], *, units: str = "radians") -> dict[str, Any]:
    return {
        "kind": "blacknode.joint-trajectory", "schema_version": 1,
        "joint_names": list(joint_names), "waypoints": list(waypoints), "units": units,
    }


def cartesian_trajectory(frame: str, waypoints: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "blacknode.cartesian-trajectory", "schema_version": 1,
        "frame": frame, "waypoints": list(waypoints),
    }


def grasp_candidate(frame: str, pose_: dict[str, Any], *, score: float, width_m: float) -> dict[str, Any]:
    return {
        "kind": "blacknode.grasp-candidate", "schema_version": 1,
        "frame": frame, "pose": pose_, "score": score, "width_m": width_m,
    }


def manipulation_status(state: str = "idle", *, target: dict[str, Any] | None = None, stop_reason: str = "") -> dict[str, Any]:
    valid_states = {"idle", "planning", "previewing", "executing", "succeeded", "failed", "cancelled"}
    if state not in valid_states:
        raise ValueError(f"unsupported manipulation state: {state!r}")
    return {
        "kind": "blacknode.manipulation-status", "schema_version": 1,
        "state": state, "target": target or {}, "stop_reason": stop_reason,
    }


def safety_policy(
    *, max_linear_velocity: float = 0.0, max_angular_velocity: float = 0.0,
    max_joint_velocity_deg_s: float = 0.0, staleness_limit_s: float = 0.5, require_calibration: bool = True,
) -> dict[str, Any]:
    return {
        "kind": "blacknode.safety-policy", "schema_version": 1,
        "max_linear_velocity": max_linear_velocity, "max_angular_velocity": max_angular_velocity,
        "max_joint_velocity_deg_s": max_joint_velocity_deg_s,
        "staleness_limit_s": staleness_limit_s, "require_calibration": require_calibration,
    }


def motion_authorization(*, authorized: bool, max_age_s: float, scope: str) -> dict[str, Any]:
    return {
        "kind": "blacknode.motion-authorization", "schema_version": 1,
        "authorized": authorized, "issued_at": _now_iso(), "max_age_s": max_age_s, "scope": scope,
    }


def estop_state(*, latched: bool = False, reason: str = "", cleared_by: str = "") -> dict[str, Any]:
    return {
        "kind": "blacknode.estop-state", "schema_version": 1,
        "latched": latched, "triggered_at": _now_iso() if latched else "",
        "reason": reason, "cleared_by": cleared_by,
    }
