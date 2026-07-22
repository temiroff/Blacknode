from blacknode.package_index import (
    package_index_payload,
    resolve_workflow_dependencies,
    template_adapter_requirements,
    template_component_requirements,
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
    assert payload["packages"]["blacknode-perception"]["layer"] == "perception"
    assert payload["packages"]["blacknode-ros2"]["layer"] == "ros2"
    assert payload["packages"]["blacknode-ros2"]["components"]["core"]["default"] is True
    assert payload["packages"]["blacknode-skills"]["layer"] == "skills"
    assert payload["packages"]["blacknode-agent"]["layer"] == "agent"
    assert payload["packages"]["blacknode-controllers"]["layer"] == "controllers"
    assert payload["packages"]["blacknode-dataset"]["layer"] == "learning"
    drivers = payload["packages"]["blacknode-drivers"]
    assert drivers["layer"] == "drivers"
    assert drivers["components"]["feetech"]["default"] is True
    assert drivers["components"]["feetech"]["node_types"] == [
        "FeetechBusConfig",
        "FeetechBusProbe",
    ]
    # Roadmap components are declared ahead of implementation, so assert the
    # one that ships nodes rather than pinning the whole set.
    assert "feetech" in drivers["components"]
    assert all(
        not component["node_types"]
        for name, component in drivers["components"].items()
        if name != "feetech"
    )
    assert drivers["components"]["feetech"]["adapters"]["ros2"]["default"] is False
    assert payload["nodes"]["FeetechROS2Adapter"]["package"] == "blacknode-drivers"
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
    assert payload["nodes"]["ROS2LeaderFollower"]["package"] == "blacknode-skills"
    assert payload["nodes"]["PolicyRuntime"]["package"] == "blacknode-controllers"
    assert payload["nodes"]["BaseSafetyGate"]["package"] == "blacknode-controllers"
    assert payload["nodes"]["Camera"]["package"] == "blacknode-perception"
    assert payload["nodes"]["CameraStream"]["package"] == "blacknode-perception"
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


def test_workflow_declares_nested_adapter_and_reports_disabled_state():
    workflow = _workflow("FeetechROS2Adapter")
    workflow["metadata"]["required_components"] = ["blacknode-drivers/feetech"]
    workflow["metadata"]["required_adapters"] = [{
        "package": "blacknode-drivers",
        "component": "feetech",
        "adapter": "ros2",
        "version": ">=0.1.0,<1.0.0",
    }]
    installed = {
        "blacknode-drivers": {
            "ok": True,
            "version": "0.1.0",
            "components": {
                "feetech": {
                    "enabled": True,
                    "adapters": {"ros2": {"enabled": False}},
                },
            },
        },
    }

    assert template_adapter_requirements(workflow) == [{
        "package": "blacknode-drivers",
        "component": "feetech",
        "adapter": "ros2",
        "version": ">=0.1.0,<1.0.0",
        "git_url": "https://github.com/temiroff/blacknode-drivers.git",
    }]
    result = resolve_workflow_dependencies(
        workflow,
        available_node_types={"FeetechROS2Adapter", "NestedNode"},
        installed_packages=installed,
    )

    assert result["code"] == "missing_adapters"
    assert result["missing_adapters"][0]["reason"] == "adapter is disabled"


def test_workflow_adapter_requirement_adds_missing_official_package():
    workflow = _workflow("FeetechROS2Adapter")
    workflow["metadata"]["required_adapters"] = ["blacknode-drivers/feetech@ros2"]

    result = resolve_workflow_dependencies(
        workflow,
        available_node_types={"NestedNode"},
        installed_packages={},
    )

    assert result["code"] == "missing_packages"
    assert result["missing_packages"][0]["name"] == "blacknode-drivers"
    assert result["missing_adapters"][0]["reason"] == "package is not installed"
