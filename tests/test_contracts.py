"""Phase 0 contract catalog: registry integrity and constructor contracts."""
from __future__ import annotations

import json

import pytest

from blacknode import contracts as c


def test_shipping_and_new_kinds_do_not_overlap():
    assert not (set(c.SHIPPING_KINDS) & set(c.NEW_KINDS))
    assert set(c.ALL_KINDS) == set(c.SHIPPING_KINDS) | set(c.NEW_KINDS)


def test_every_kind_is_namespaced():
    for kind in c.ALL_KINDS:
        assert kind.startswith("blacknode."), kind


@pytest.mark.parametrize("kind", sorted(c.SHIPPING_KINDS))
def test_shipping_kind_has_a_known_owner(kind):
    assert c.SHIPPING_KINDS[kind].startswith("blacknode-")


def _constructors():
    p = c.pose("map", position=(1.0, 2.0, 0.0))
    return {
        "blacknode.robot-profile": c.robot_profile("r1", capabilities=["mobile-base"], driver={"hardware_id": "x"}),
        "blacknode.mobile-base": c.mobile_base(
            "differential", max_linear_velocity=1.0, max_angular_velocity=1.5, footprint_m=(0.4, 0.3),
        ),
        "blacknode.robot-model": c.robot_model("m1", joint_names=["shoulder"], frame_names=["base_link"]),
        "blacknode.sensor": c.sensor("s1", "lidar-2d", frame="lidar_link", transport="ros2"),
        "blacknode.pose": p,
        "blacknode.odometry-stream": c.odometry_stream(),
        "blacknode.imu-stream": c.imu_stream("imu_link"),
        "blacknode.laser-scan-stream": c.laser_scan_stream(
            "lidar_link", angle_min=-1.5, angle_max=1.5, angle_increment=0.01,
            range_min=0.1, range_max=8.0, ranges=[1.0, 2.0],
        ),
        "blacknode.depth-stream": c.depth_stream("camera_depth_frame"),
        "blacknode.point-cloud-stream": c.point_cloud_stream("camera_depth_frame"),
        "blacknode.transform-stream": c.transform_stream("base_link", "lidar_link"),
        "blacknode.detection-stream": c.detection_stream("camera_rgb_frame", detections=[]),
        "blacknode.robot-state-stream": c.robot_state_stream(joint_positions={"shoulder": 0.1}),
        "blacknode.map": c.map_artifact("map1", resolution=0.05),
        "blacknode.navigation-goal": c.navigation_goal(target=p),
        "blacknode.navigation-status": c.navigation_status(),
        "blacknode.detection2d": c.detection2d("cube", confidence=0.9, center=(320.0, 240.0), bbox=(300.0, 220.0, 40.0, 40.0)),
        "blacknode.detection3d": c.detection3d("cube", confidence=0.9, frame="map", pose_=p, extent=(0.05, 0.05, 0.05)),
        "blacknode.joint-trajectory": c.joint_trajectory(["shoulder"], [{"positions": [0.1], "time_from_start_s": 1.0}]),
        "blacknode.cartesian-trajectory": c.cartesian_trajectory("map", [{"pose": p, "time_from_start_s": 1.0}]),
        "blacknode.grasp-candidate": c.grasp_candidate("map", p, score=0.8, width_m=0.05),
        "blacknode.manipulation-status": c.manipulation_status(),
        "blacknode.safety-policy": c.safety_policy(max_linear_velocity=1.0),
        "blacknode.motion-authorization": c.motion_authorization(authorized=True, max_age_s=30.0, scope="base_motion"),
        "blacknode.estop-state": c.estop_state(),
    }


def test_every_new_kind_has_a_working_constructor():
    produced = _constructors()
    assert set(produced) == set(c.NEW_KINDS)


@pytest.mark.parametrize("kind,value", sorted(_constructors().items()))
def test_constructor_output_matches_its_kind_and_is_json_serializable(kind, value):
    assert value["kind"] == kind
    assert value["schema_version"] == 1
    json.dumps(value)  # must round-trip cleanly for storage/transport


def test_mobile_base_rejects_unknown_drive_model():
    with pytest.raises(ValueError):
        c.mobile_base("bogus", max_linear_velocity=1.0, max_angular_velocity=1.0, footprint_m=(1.0, 1.0))


def test_navigation_goal_requires_target_or_named_location():
    with pytest.raises(ValueError):
        c.navigation_goal()


def test_navigation_status_rejects_unknown_state():
    with pytest.raises(ValueError):
        c.navigation_status("bogus")


def test_manipulation_status_rejects_unknown_state():
    with pytest.raises(ValueError):
        c.manipulation_status("bogus")


def test_estop_state_only_timestamps_when_latched():
    assert c.estop_state(latched=False)["triggered_at"] == ""
    assert c.estop_state(latched=True)["triggered_at"] != ""
