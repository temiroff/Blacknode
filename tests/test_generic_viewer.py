import blacknode  # noqa: F401  registers built-in nodes
from blacknode.node import _NODE_REGISTRY


def test_generic_viewer_normalizes_point_cloud_without_map_features():
    viewer = _NODE_REGISTRY["GenericViewer"]
    result = viewer({
        "source": {
            "kind": "blacknode.point-cloud-frame",
            "points_xyz": [[1.0, 2.0, 3.0]],
            "colors_rgb": [[0.2, 0.6, 1.0]],
        },
        "title": "Front sensor",
        "frame": "front_lidar",
        "show_axes": True,
    })

    assert result["status"]["state"] == "ready"
    assert result["scene"]["viewer_role"] == "generic"
    assert result["scene"]["points"] == [[1.0, 2.0, 3.0]]
    assert result["scene"]["frame"] == "front_lidar"
    assert "floor_points" not in result["scene"]
    assert "occupancy" not in result["scene"]
    assert "robot" not in result["scene"]


def test_generic_viewer_reports_unsupported_source():
    viewer = _NODE_REGISTRY["GenericViewer"]
    result = viewer({"source": {"kind": "blacknode.frame-stream"}})

    assert result["scene"] == {}
    assert result["status"]["state"] == "unavailable"
