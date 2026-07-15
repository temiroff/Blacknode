"""Core index and dependency resolution for Blacknode extension packages."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


_CORE_PACKAGES: dict[str, dict[str, Any]] = {
    "blacknode-cuda": {
        "name": "blacknode-cuda",
        "git_url": "https://github.com/temiroff/blacknode-cuda.git",
        "description": "Real GPU compute nodes: CUDA kernel lab, custom NVRTC kernels, GPU image filters, Tensor Core GEMM, and CUTLASS.",
        "node_types": [
            "CUDACustomKernel",
            "CUDAImageFilter",
            "CUDAImageFilterStream",
            "CUDAKernelLab",
            "CUTLASS",
            "CUTLASSGemm",
            "GPUCapability",
            "GPURequirement",
            "TensorCoreGEMM",
        ],
    },
    "blacknode-ros2": {
        "name": "blacknode-ros2",
        "git_url": "https://github.com/temiroff/blacknode-ros2.git",
        "description": "ROS 2 topics, services, visual tests, image streams, process launch/run controls, and robot interface nodes.",
        "node_types": [
            "ROS2Command",
            "ROS2CompressedImageSnapshot",
            "ROS2DemoPublisher",
            "ROS2ImageSnapshot",
            "ROS2ImageStream",
            "ROS2InterfaceShow",
            "ROS2FollowDetectionJoint",
            "ROS2JointState",
            "ROS2ManualMove",
            "ROS2Launch",
            "ROS2MotionDashboard",
            "ROS2NativeFollowDetectionJoint",
            "ROS2NativeJointState",
            "ROS2NativeRobotDiscovery",
            "ROS2NativeSetJoint",
            "ROS2NativeStatus",
            "ROS2NodeList",
            "ROS2PackageExecutables",
            "ROS2RosbridgeStatus",
            "ROS2RobotDiscovery",
            "ROS2RotateJoint",
            "ROS2SetJoint",
            "ROS2Status",
            "ROS2Run",
            "ROS2ServiceList",
            "ROS2SystemCheck",
            "ROS2TopicEcho",
            "ROS2TopicList",
            "ROS2TopicPublish",
            "ROS2VisualDashboard",
        ],
    },
    "blacknode-robot": {
        "name": "blacknode-robot",
        "git_url": "https://github.com/temiroff/blacknode-robot.git",
        "description": "Generic robot setup: USB discovery, serial permission diagnostics, driver launch, and standard robot profiles.",
        "node_types": [
            "RobotDiscovery",
            "RobotDriverDescriptor",
            "RobotDriverLauncher",
            "RobotDriverPreset",
            "RobotUSBDiscovery",
        ],
    },
    "blacknode-vision": {
        "name": "blacknode-vision",
        "git_url": "https://github.com/temiroff/blacknode-vision.git",
        "description": "Robot vision workflows: USB cameras, ROS 2 image streams, VLM reasoning dashboards, and OpenCV object tracking.",
        "node_types": [
            "CV2ColorObjectStream",
            "CV2ColorTargetHint",
            "CV2ColorObjectTracker",
            "CV2HSVMask",
            "VisionDetectionPrompt",
            "VisionFramePrompt",
            "VisionReasoningDashboard",
            "VisionReasoningStream",
            "VisionStreamStatus",
            "VisionVLMDescribe",
        ],
    },
}

_NODE_PACKAGE_INDEX: dict[str, dict[str, str]] = {
    node_type: {
        "package": package["name"],
        "git_url": package["git_url"],
    }
    for package in _CORE_PACKAGES.values()
    for node_type in package["node_types"]
}


def package_index_payload() -> dict[str, Any]:
    """Return a JSON-safe copy of the package and node lookup index."""
    return {
        "schema_version": 1,
        "packages": {
            name: {
                **package,
                "node_types": list(package["node_types"]),
            }
            for name, package in _CORE_PACKAGES.items()
        },
        "nodes": {
            node_type: dict(resolution)
            for node_type, resolution in _NODE_PACKAGE_INDEX.items()
        },
    }


def indexed_package(name: str) -> dict[str, Any] | None:
    """Return the official package-index entry for ``name``, if known."""
    package = _CORE_PACKAGES.get(name)
    if package is None:
        return None
    return {
        **package,
        "node_types": list(package["node_types"]),
    }

def workflow_node_types(workflow: Mapping[str, Any]) -> set[str]:
    """Collect node types from the root graph and all nested subgraphs."""
    found: set[str] = set()

    def visit_graph(graph: Mapping[str, Any]) -> None:
        node_meta = graph.get("node_meta")
        if not isinstance(node_meta, Mapping):
            return
        for raw_meta in node_meta.values():
            if not isinstance(raw_meta, Mapping):
                continue
            node_type = raw_meta.get("type")
            if isinstance(node_type, str) and node_type:
                found.add(node_type)
            subgraph = raw_meta.get("subgraph")
            if isinstance(subgraph, Mapping):
                visit_graph(subgraph)

    visit_graph(workflow)
    return found


def template_package_requirements(workflow: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read ``metadata.required_packages`` into normalized descriptors.

    Indexed packages can be named with a string. Third-party templates can
    embed ``name``, ``git_url``, and optional ``node_types`` fields.
    """
    metadata = workflow.get("metadata")
    if not isinstance(metadata, Mapping):
        return []
    raw_requirements = metadata.get("required_packages")
    if not isinstance(raw_requirements, list):
        return []

    requirements: dict[str, dict[str, Any]] = {}
    for raw in raw_requirements:
        if isinstance(raw, str):
            name = raw.strip()
            embedded: Mapping[str, Any] = {}
        elif isinstance(raw, Mapping):
            name = str(raw.get("name", "")).strip()
            embedded = raw
        else:
            continue
        if not name:
            continue

        indexed = _CORE_PACKAGES.get(name, {})
        raw_node_types = embedded.get("node_types", indexed.get("node_types", []))
        node_types = sorted({
            str(node_type).strip()
            for node_type in raw_node_types
            if isinstance(node_type, str) and node_type.strip()
        }) if isinstance(raw_node_types, list) else []
        requirements[name] = {
            "name": name,
            "git_url": str(embedded.get("git_url") or indexed.get("git_url") or "").strip(),
            "node_types": node_types,
            "source": "template",
        }
    return list(requirements.values())


def resolve_workflow_dependencies(
    workflow: Mapping[str, Any],
    *,
    available_node_types: Iterable[str],
    installed_packages: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve missing workflow nodes and explicit package requirements."""
    available = set(available_node_types)
    installed = installed_packages or {}
    missing_node_types = sorted(workflow_node_types(workflow) - available)
    explicit = {
        requirement["name"]: requirement
        for requirement in template_package_requirements(workflow)
    }
    missing_packages: dict[str, dict[str, Any]] = {}
    unresolved_node_types: list[str] = []

    def add_package(requirement: Mapping[str, Any], node_type: str | None = None) -> None:
        name = str(requirement["name"])
        state = installed.get(name, {})
        current = missing_packages.setdefault(name, {
            "name": name,
            "git_url": str(requirement.get("git_url", "")),
            "node_types": [],
            "source": str(requirement.get("source", "core_index")),
            "installed": bool(state),
            "load_error": str(state.get("error", "")) if state else "",
        })
        if node_type and node_type not in current["node_types"]:
            current["node_types"].append(node_type)

    for requirement in explicit.values():
        state = installed.get(requirement["name"])
        if state is None or not bool(state.get("ok", False)):
            add_package(requirement)

    for node_type in missing_node_types:
        requirement = next(
            (item for item in explicit.values() if node_type in item["node_types"]),
            None,
        )
        if requirement is None:
            resolution = _NODE_PACKAGE_INDEX.get(node_type)
            if resolution is not None:
                package_name = resolution["package"]
                requirement = {
                    "name": package_name,
                    "git_url": explicit.get(package_name, {}).get("git_url", resolution["git_url"]),
                    "node_types": [node_type],
                    "source": "core_index",
                }
        if requirement is None:
            unresolved_node_types.append(node_type)
            continue
        add_package(requirement, node_type)

    packages = sorted(missing_packages.values(), key=lambda item: item["name"])
    for package in packages:
        package["node_types"].sort()

    parts: list[str] = []
    if packages:
        parts.append("Missing package" + ("s" if len(packages) != 1 else "") + ": " + ", ".join(
            package["name"] for package in packages
        ))
    if unresolved_node_types:
        parts.append("No package mapping for: " + ", ".join(unresolved_node_types))
    return {
        "ok": not packages and not missing_node_types,
        "code": "missing_packages" if packages else "missing_node_types",
        "message": ". ".join(parts) or "Workflow dependencies are available.",
        "missing_node_types": missing_node_types,
        "missing_packages": packages,
        "unresolved_node_types": unresolved_node_types,
    }


__all__ = [
    "indexed_package",
    "package_index_payload",
    "resolve_workflow_dependencies",
    "template_package_requirements",
    "workflow_node_types",
]
