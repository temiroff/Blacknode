from blacknode.package_index import (
    package_index_payload,
    resolve_workflow_dependencies,
    template_package_requirements,
    workflow_node_types,
)


def _workflow(node_type: str, required_packages=None):
    metadata = {"template": True}
    if required_packages is not None:
        metadata["required_packages"] = required_packages
    return {
        "metadata": metadata,
        "node_meta": {
            "node": {
                "id": "node",
                "type": node_type,
                "subgraph": {
                    "node_meta": {
                        "nested": {
                            "id": "nested",
                            "type": "NestedNode",
                        },
                    },
                    "edges": [],
                },
            },
        },
        "edges": [],
    }


def test_core_index_maps_official_node_types_to_git_packages():
    payload = package_index_payload()

    assert payload["schema_version"] == 2
    assert payload["packages"]["blacknode-robot"]["layer"] == "robot"
    assert payload["packages"]["blacknode-vision"]["layer"] == "perception"
    assert payload["packages"]["blacknode-ros2"]["layer"] == "integration"
    assert payload["packages"]["blacknode-dataset"]["layer"] == "learning"
    drivers = payload["packages"]["blacknode-drivers"]
    assert drivers["layer"] == "drivers"
    assert drivers["components"]["feetech"]["default"] is True
    assert drivers["components"]["feetech"]["node_types"] == [
        "FeetechBusConfig",
        "FeetechBusProbe",
    ]
    assert payload["nodes"]["FeetechBusProbe"]["package"] == "blacknode-drivers"
    assert payload["nodes"]["CUDAKernelLab"] == {
        "package": "blacknode-cuda",
        "git_url": "https://github.com/temiroff/blacknode-cuda.git",
    }
    assert payload["nodes"]["ROS2TopicList"]["package"] == "blacknode-ros2"
    assert payload["nodes"]["RobotDiscovery"]["package"] == "blacknode-robot"
    assert payload["nodes"]["EpisodeRecorder"] == {
        "package": "blacknode-dataset",
        "git_url": "https://github.com/temiroff/blacknode-dataset.git",
    }
    assert payload["nodes"]["DatasetCameraStreamList"]["package"] == "blacknode-dataset"
    assert payload["nodes"]["DatasetBrowser"]["package"] == "blacknode-dataset"
    assert payload["nodes"]["HDF5EpisodeExport"]["package"] == "blacknode-dataset"
    assert payload["nodes"]["StreamPublisher"]["package"] == "blacknode-dataset"
    assert payload["nodes"]["ROS2LeaderFollower"]["package"] == "blacknode-ros2"
    assert payload["nodes"]["PolicyRuntime"]["package"] == "blacknode-ros2"
    assert payload["nodes"]["Camera"]["package"] == "blacknode-vision"
    assert payload["nodes"]["CameraStream"]["package"] == "blacknode-vision"
    assert payload["nodes"]["CV2CameraStream"]["package"] == "blacknode-vision"
    assert payload["nodes"]["ACTTraining"] == {
        "package": "blacknode-training",
        "git_url": "https://github.com/temiroff/blacknode-training.git",
    }
    assert payload["nodes"]["ACTPolicyExport"]["package"] == "blacknode-training"
    assert payload["nodes"]["ACTPolicyReplay"]["package"] == "blacknode-training"
    assert payload["nodes"]["PolicyArtifactLoad"]["package"] == "blacknode-training"
    assert payload["nodes"]["IsaacPolicyBridge"] == {
        "package": "blacknode-isaac",
        "git_url": "https://github.com/temiroff/blacknode-isaac.git",
    }
    assert payload["nodes"]["IsaacPolicyRuntime"]["package"] == "blacknode-isaac"


def test_resolver_finds_nested_nodes_and_indexed_package():
    workflow = _workflow("CUDAKernelLab")

    assert workflow_node_types(workflow) == {"CUDAKernelLab", "NestedNode"}
    result = resolve_workflow_dependencies(
        workflow,
        available_node_types={"Output"},
        installed_packages={},
    )

    assert not result["ok"]
    assert result["missing_packages"][0]["name"] == "blacknode-cuda"
    assert result["missing_packages"][0]["node_types"] == ["CUDAKernelLab"]
    assert result["unresolved_node_types"] == ["NestedNode"]


def test_template_can_embed_third_party_package_resolution():
    workflow = _workflow("AcmeNode", [{
        "name": "blacknode-acme",
        "git_url": "https://example.com/blacknode-acme.git",
        "node_types": ["AcmeNode"],
    }])

    assert template_package_requirements(workflow) == [{
        "name": "blacknode-acme",
        "git_url": "https://example.com/blacknode-acme.git",
        "node_types": ["AcmeNode"],
        "source": "template",
    }]
    result = resolve_workflow_dependencies(
        workflow,
        available_node_types={"NestedNode"},
        installed_packages={},
    )

    assert result["code"] == "missing_packages"
    assert result["missing_packages"][0]["name"] == "blacknode-acme"
    assert result["missing_packages"][0]["node_types"] == ["AcmeNode"]
    assert result["unresolved_node_types"] == []


def test_installed_explicit_package_does_not_block_available_workflow():
    workflow = _workflow("CUDAKernelLab", ["blacknode-cuda"])
    result = resolve_workflow_dependencies(
        workflow,
        available_node_types={"CUDAKernelLab", "NestedNode"},
        installed_packages={"blacknode-cuda": {"ok": True, "error": ""}},
    )

    assert result["ok"]
    assert result["missing_packages"] == []
