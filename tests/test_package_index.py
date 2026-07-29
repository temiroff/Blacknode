from types import SimpleNamespace
from unittest.mock import patch

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
    assert set(payload["packages"]) == {
        "blacknode-agent",
        "blacknode-motion",
        "blacknode-cuda",
        "blacknode-dataset",
        "blacknode-drivers",
        "blacknode-isaac",
        "blacknode-perception",
        "blacknode-robot",
        "blacknode-ros2",
        "blacknode-runtime",
        "blacknode-skills",
        "blacknode-training",
    }
    assert payload["packages"]["blacknode-robot"]["layer"] == "robot"
    robot = payload["packages"]["blacknode-robot"]
    assert {"devices", "telemetry"}.issubset(robot["components"])
    assert robot["components"]["devices"]["node_types"] == ["HardwareCapabilities"]
    assert robot["components"]["telemetry"]["adapters"]["mqtt"]["default"] is False
    assert payload["packages"]["blacknode-perception"]["layer"] == "perception"
    assert payload["packages"]["blacknode-ros2"]["layer"] == "ros2"
    assert payload["packages"]["blacknode-ros2"]["components"]["core"]["default"] is True
    assert payload["packages"]["blacknode-ros2"]["components"]["rosbridge"]["default"] is False
    assert payload["packages"]["blacknode-ros2"]["components"]["processes"]["default"] is False
    assert set(payload["packages"]["blacknode-ros2"]["components"]) == {
        "core",
        "diagnostics",
        "processes",
        "rosbridge",
        "services",
        "topics",
    }
    for component_name in {
        "diagnostics",
        "processes",
        "rosbridge",
        "services",
        "topics",
    }:
        assert payload["packages"]["blacknode-ros2"]["components"][component_name]["dependencies"] == {
            "requires": [{"component": "core"}],
        }
    assert payload["packages"]["blacknode-skills"]["layer"] == "skills"
    agent = payload["packages"]["blacknode-agent"]
    assert agent["layer"] == "agent"
    assert set(agent["components"]) == {"memory", "executive"}
    motion = payload["packages"]["blacknode-motion"]
    assert motion["layer"] == "motion"
    assert set(motion["components"]) == {"core", "arm", "base", "policy", "safety"}
    assert motion["components"]["core"]["default"] is True
    assert motion["components"]["core"]["internal"] is True
    assert motion["components"]["arm"]["node_types"] == ["JointMotionProfile"]
    assert motion["components"]["arm"]["aliases"] == ["joint-control"]
    assert motion["components"]["base"]["aliases"] == ["mobile-base"]
    for component_name in {"arm", "base", "policy"}:
        assert motion["components"][component_name]["dependencies"] == {
            "requires": [
                {
                    "component": "core",
                    "version": ">=0.6.0,<1.0.0",
                },
                {
                    "component": "safety",
                    "version": ">=0.6.0,<1.0.0",
                },
            ],
        }
    assert payload["packages"]["blacknode-agent"]["components"]["executive"]["aliases"] == [
        "planner"
    ]
    assert payload["packages"]["blacknode-skills"]["components"]["follow"]["aliases"] == [
        "follow-person"
    ]
    assert set(payload["packages"]["blacknode-runtime"]["components"]) == {"deployment"}
    assert "JointMotionProfile" not in motion["components"]["arm"]["adapters"]["ros2"]["node_types"]
    assert payload["packages"]["blacknode-dataset"]["layer"] == "learning"
    dataset = payload["packages"]["blacknode-dataset"]["components"]
    assert all(dataset[name]["default"] for name in {"recording", "replay", "validation"})
    assert not any(dataset[name]["default"] for name in {"evaluation", "export", "publishing"})
    cuda = payload["packages"]["blacknode-cuda"]["components"]
    assert set(cuda) == {"capability", "image-processing", "tensor-operations", "benchmarks"}
    assert cuda["benchmarks"]["default"] is False
    drivers = payload["packages"]["blacknode-drivers"]
    assert drivers["layer"] == "drivers"
    assert drivers["components"]["feetech"]["default"] is True
    assert drivers["components"]["feetech"]["node_types"] == [
        "FeetechBusConfig",
        "FeetechBusProbe",
    ]
    assert set(drivers["components"]) == {"feetech"}
    assert drivers["components"]["feetech"]["adapters"]["ros2"]["default"] is False
    assert payload["nodes"]["FeetechROS2Adapter"]["package"] == "blacknode-drivers"
    assert payload["nodes"]["FeetechBusProbe"]["package"] == "blacknode-drivers"
    assert "CUDAKernelLab" not in payload["nodes"]
    assert "CUDACustomKernel" not in payload["nodes"]
    assert payload["nodes"]["ROS2TopicList"]["package"] == "blacknode-ros2"
    assert payload["nodes"]["ROS2TopicPublisher"]["package"] == "blacknode-ros2"
    assert "ROS2DemoPublisher" not in payload["nodes"]
    assert payload["nodes"]["RobotDiscovery"]["package"] == "blacknode-robot"
    assert payload["nodes"]["RobotMonitor"]["package"] == "blacknode-robot"
    assert payload["nodes"]["RobotCapabilityInspect"]["package"] == "blacknode-robot"
    assert payload["nodes"]["HardwareCapabilities"]["package"] == "blacknode-robot"
    assert payload["nodes"]["EpisodeRecorder"] == {
        "package": "blacknode-dataset",
        "git_url": "https://github.com/temiroff/blacknode-dataset.git",
    }
    assert payload["nodes"]["DatasetCameraStreamList"]["package"] == "blacknode-dataset"
    assert payload["nodes"]["DatasetBrowser"]["package"] == "blacknode-dataset"
    assert payload["nodes"]["HDF5EpisodeExport"]["package"] == "blacknode-dataset"
    assert payload["nodes"]["StreamPublisher"]["package"] == "blacknode-dataset"
    assert payload["nodes"]["ROS2LeaderFollower"]["package"] == "blacknode-skills"
    assert payload["nodes"]["ROS2PublishJointState"]["package"] == "blacknode-skills"
    assert payload["nodes"]["ROS2SubscribeJointState"]["package"] == "blacknode-skills"
    assert payload["nodes"]["ROS2JointController"]["package"] == "blacknode-skills"
    for legacy_name in {
        "ROS2JointStatePublish",
        "ROS2JointSubscribe",
        "ROS2JointReplicate",
        "ROS2JointPublish",
        "ROS2LeaderJointSubscriber",
        "ROS2FollowerJointPublisher",
    }:
        assert legacy_name not in payload["nodes"]
    assert payload["nodes"]["PolicyRuntime"]["package"] == "blacknode-motion"
    assert payload["nodes"]["BaseSafetyGate"]["package"] == "blacknode-motion"
    assert payload["nodes"]["Camera"]["package"] == "blacknode-perception"
    assert payload["nodes"]["CameraStream"]["package"] == "blacknode-perception"
    assert payload["nodes"]["ACTTraining"] == {
        "package": "blacknode-training",
        "git_url": "https://github.com/temiroff/blacknode-training.git",
    }
    assert payload["nodes"]["ACTPolicyExport"]["package"] == "blacknode-training"
    assert payload["nodes"]["ACTPolicyReplay"]["package"] == "blacknode-training"
    assert payload["nodes"]["PolicyArtifactLoad"]["package"] == "blacknode-training"
    assert not any(
        component["default"]
        for component in payload["packages"]["blacknode-training"]["components"].values()
    )
    assert payload["nodes"]["IsaacPolicyBridge"] == {
        "package": "blacknode-isaac",
        "git_url": "https://github.com/temiroff/blacknode-isaac.git",
    }
    assert payload["nodes"]["IsaacPolicyRuntime"]["package"] == "blacknode-isaac"


def test_installed_package_manifest_maps_new_node_types_without_core_edit():
    info = SimpleNamespace(
        name="blacknode-skills",
        layer="skills",
        description="skills",
        git_status={},
        node_types=[],
        components={
            "follow": {
                "node_types": [],
                "adapters": {
                    "ros2": {
                        "node_types": ["ROS2FutureJointNode"],
                    },
                },
            },
        },
    )
    with patch("blacknode.packages.installed_packages", return_value=[info]):
        payload = package_index_payload()
        result = resolve_workflow_dependencies(
            _workflow("ROS2FutureJointNode"),
            available_node_types={"NestedNode"},
            installed_packages={
                "blacknode-skills": {
                    "ok": True,
                    "error": "",
                },
            },
        )

    assert payload["nodes"]["ROS2FutureJointNode"] == {
        "package": "blacknode-skills",
        "git_url": "https://github.com/temiroff/blacknode-skills.git",
    }
    assert "ROS2FutureJointNode" in payload["packages"]["blacknode-skills"]["node_types"]
    assert result["unresolved_node_types"] == []
    assert result["missing_packages"] == [{
        "name": "blacknode-skills",
        "git_url": "https://github.com/temiroff/blacknode-skills.git",
        "node_types": ["ROS2FutureJointNode"],
        "source": "package_manifest",
        "installed": True,
        "load_error": "",
    }]


def test_resolver_finds_nested_nodes_and_indexed_package():
    workflow = _workflow("CUDAImageFilter")

    assert workflow_node_types(workflow) == {"CUDAImageFilter", "NestedNode"}
    result = resolve_workflow_dependencies(
        workflow,
        available_node_types={"Output"},
        installed_packages={},
    )

    assert not result["ok"]
    assert result["missing_packages"][0]["name"] == "blacknode-cuda"
    assert result["missing_packages"][0]["node_types"] == ["CUDAImageFilter"]
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
