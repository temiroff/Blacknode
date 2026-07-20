"""Core index and dependency resolution for Blacknode extension packages."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


_CORE_PACKAGES: dict[str, dict[str, Any]] = {
    "blacknode-skills": {
        "name": "blacknode-skills",
        "layer": "skills",
        "components": {
            "follow-person": {
                "name": "follow-person", "default": False, "node_types": [],
                "adapters": {"ros2": {
                    "name": "ros2", "default": False,
                    "node_types": [
                        "ROS2NativeFollowDetectionJoint", "ROS2FollowDetectionJoint",
                        "ROS2ContinuousFollowDetectionJoint", "ROS2LeaderFollower",
                    ],
                }},
            },
            **{
                name: {"name": name, "default": False, "node_types": []}
                for name in ("pick-place", "delivery", "docking", "inspection")
            },
        },
        "git_url": "https://github.com/temiroff/blacknode-skills.git",
        "description": "Reusable task-level robot skills composed from stable capabilities.",
        "node_types": [
            "ROS2NativeFollowDetectionJoint", "ROS2FollowDetectionJoint",
            "ROS2ContinuousFollowDetectionJoint", "ROS2LeaderFollower",
        ],
    },
    "blacknode-agent": {
        "name": "blacknode-agent",
        "layer": "agent",
        "components": {
            "memory": {
                "name": "memory", "default": True,
                "node_types": [
                    "AdaptationRecommendation", "EpisodeMemoryIngest", "RobotMemoryQuery",
                    "RobotTaskCreate", "TaskEvaluationRecord",
                ],
            },
            **{
                name: {"name": name, "default": False, "node_types": []}
                for name in ("planner", "skill-registry", "mission-review", "confirmation")
            },
        },
        "git_url": "https://github.com/temiroff/blacknode-agent.git",
        "description": "Planning, memory, review, confirmation, and skill orchestration.",
        "node_types": [
            "AdaptationRecommendation", "EpisodeMemoryIngest", "RobotMemoryQuery",
            "RobotTaskCreate", "TaskEvaluationRecord",
        ],
    },
    "blacknode-controllers": {
        "name": "blacknode-controllers",
        "layer": "controllers",
        "components": {
            "mobile-base": {
                "name": "mobile-base", "default": False, "node_types": [],
                "adapters": {"ros2": {
                    "name": "ros2", "default": False,
                    "node_types": ["BaseSafetyGate", "ROS2BaseMove", "ROS2BaseStop", "ROS2LaserScanCheck", "ROS2OdomState"],
                }},
            },
            "policy": {
                "name": "policy", "default": True, "node_types": [],
                "adapters": {"ros2": {
                    "name": "ros2", "default": False,
                    "node_types": ["PolicyRuntime", "PolicySafetyGate"],
                }},
            },
            **{
                name: {"name": name, "default": False, "node_types": []}
                for name in ("nav2", "manipulation", "command-arbitration", "safety-supervisors")
            },
        },
        "git_url": "https://github.com/temiroff/blacknode-controllers.git",
        "description": "Generic motion, manipulation, policy, arbitration, and safety controllers.",
        "node_types": [
            "BaseSafetyGate", "PolicyRuntime", "PolicySafetyGate", "ROS2BaseMove",
            "ROS2BaseStop", "ROS2LaserScanCheck", "ROS2OdomState",
        ],
    },
    "blacknode-drivers": {
        "name": "blacknode-drivers",
        "layer": "drivers",
        "components": {
            "feetech": {
                "name": "feetech",
                "description": "Feetech STS/SMS serial-bus configuration, read-only probing, and safety primitives.",
                "default": True,
                "capabilities": [
                    "driver.feetech",
                    "driver.serial-servo",
                    "robot.joint-driver",
                ],
                "node_types": ["FeetechBusConfig", "FeetechBusProbe"],
                "adapters": {
                    "ros2": {
                        "name": "ros2",
                        "description": "ROS 2 and rosbridge process adapter for the Feetech joint driver.",
                        "default": False,
                        "capabilities": ["adapter.feetech.ros2", "robot.joint-state-transport"],
                        "node_types": ["FeetechROS2Adapter"],
                        "dependencies": {
                            "requires": [
                                {"package": "blacknode-ros2", "component": "core", "version": ">=0.2.0,<1.0.0"},
                            ],
                        },
                    },
                },
            },
        },
        "git_url": "https://github.com/temiroff/blacknode-drivers.git",
        "description": "Physical hardware drivers and firmware adapters, organized as selectively enabled components.",
        "node_types": [
            "FeetechBusConfig",
            "FeetechBusProbe",
            "FeetechROS2Adapter",
        ],
    },
    "blacknode-cuda": {
        "name": "blacknode-cuda",
        "layer": "compute",
        "components": {},
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
        "layer": "ros2",
        "components": {
            "core": {
                "name": "core",
                "default": True,
                "capabilities": ["integration.ros2", "transport.ros2", "transport.rosbridge"],
                "node_types": [
                    "ROS2BridgeEcho", "ROS2BridgePublish", "ROS2Command", "ROS2CompressedImageSnapshot",
                    "ROS2DemoPublisher",
                    "ROS2ImageSnapshot", "ROS2ImageStream", "ROS2InterfaceShow", "ROS2JointState", "ROS2Launch",
                    "ROS2ManualMove", "ROS2MotionDashboard",
                    "ROS2NativeJointState", "ROS2NativeRobotDiscovery", "ROS2NativeSetJoint", "ROS2NativeStatus",
                    "ROS2NodeList", "ROS2PackageExecutables", "ROS2RobotDiscovery", "ROS2RosbridgeServer",
                    "ROS2RosbridgeStatus", "ROS2RotateJoint", "ROS2Run", "ROS2ServiceList", "ROS2SetJoint",
                    "ROS2Status", "ROS2SystemCheck", "ROS2TeachMode", "ROS2TopicEcho", "ROS2TopicList",
                    "ROS2TopicPublish", "ROS2VisualDashboard",
                ],
            },
        },
        "git_url": "https://github.com/temiroff/blacknode-ros2.git",
        "description": "ROS 2 topics, streams, robot interfaces, and safety-gated policy deployment.",
        "node_types": [
            "ROS2BridgeEcho",
            "ROS2BridgePublish",
            "ROS2Command",
            "ROS2CompressedImageSnapshot",
            "ROS2DemoPublisher",
            "ROS2ImageSnapshot",
            "ROS2ImageStream",
            "ROS2InterfaceShow",
            "ROS2JointState",
            "ROS2ManualMove",
            "ROS2Launch",
            "ROS2MotionDashboard",
            "ROS2NativeJointState",
            "ROS2NativeRobotDiscovery",
            "ROS2NativeSetJoint",
            "ROS2NativeStatus",
            "ROS2NodeList",
            "ROS2PackageExecutables",
            "ROS2RosbridgeStatus",
            "ROS2RosbridgeServer",
            "ROS2RobotDiscovery",
            "ROS2RotateJoint",
            "ROS2SetJoint",
            "ROS2Status",
            "ROS2Run",
            "ROS2ServiceList",
            "ROS2SystemCheck",
            "ROS2TeachMode",
            "ROS2TopicEcho",
            "ROS2TopicList",
            "ROS2TopicPublish",
            "ROS2VisualDashboard",
        ],
    },
    "blacknode-robot": {
        "name": "blacknode-robot",
        "layer": "robot",
        "components": {
            "core": {
                "name": "core",
                "default": True,
                "capabilities": ["robot.contracts", "robot.profiles", "robot.calibration", "robot.discovery"],
                "node_types": [
                    "Robot", "RobotCalibrationRecorder", "RobotConnectionDashboard", "RobotDefinition",
                    "RobotDiscovery", "RobotDriverDescriptor", "RobotDriverLauncher", "RobotDriverPreset",
                    "RobotJointDefinition", "RobotJointList", "RobotProfileDuplicate", "RobotProfileList",
                    "RobotProfileLoad", "RobotProfileSave", "RobotUSBDiscovery",
                ],
            },
        },
        "git_url": "https://github.com/temiroff/blacknode-robot.git",
        "description": "Generic robot setup: USB discovery, serial permission diagnostics, driver launch, and standard robot profiles.",
        "node_types": [
            "RobotDiscovery",
            "RobotConnectionDashboard",
            "RobotDriverDescriptor",
            "RobotDriverLauncher",
            "RobotDriverPreset",
            "Robot",
            "RobotJointDefinition",
            "RobotJointList",
            "RobotDefinition",
            "RobotProfileSave",
            "RobotProfileLoad",
            "RobotProfileList",
            "RobotProfileDuplicate",
            "RobotCalibrationRecorder",
            "RobotUSBDiscovery",
        ],
    },
    "blacknode-perception": {
        "name": "blacknode-perception",
        "layer": "perception",
        "components": {
            "camera": {
                "name": "camera", "default": True,
                "node_types": [
                    "Camera", "CameraCalibration", "CameraDiscovery", "CameraSelect", "CameraStream",
                    "CV2CameraDiscovery", "CV2CameraSelect", "CV2CameraStream", "CV2ColorObjectStream",
                    "CV2ColorObjectTracker", "CV2ColorTargetHint", "CV2HSVMask",
                ],
            },
            "vlm": {
                "name": "vlm", "default": True,
                "node_types": [
                    "DetectionPrompt", "FramePrompt", "ReasoningDashboard",
                    "ReasoningStream", "CameraDashboard", "VLM",
                ],
            },
            **{
                name: {"name": name, "default": False, "node_types": []}
                for name in ("depth", "lidar", "imu", "detection", "tracking", "slam", "localization")
            },
        },
        "git_url": "https://github.com/temiroff/blacknode-perception.git",
        "description": "Camera, tracking, VLM, and spatial-perception capabilities organized as selectable components.",
        "node_types": [
            "Camera",
            "CameraCalibration",
            "CameraStream",
            "CameraDiscovery",
            "CameraSelect",
            "CV2CameraStream",
            "CV2CameraDiscovery",
            "CV2CameraSelect",
            "CV2ColorObjectStream",
            "CV2ColorTargetHint",
            "CV2ColorObjectTracker",
            "CV2HSVMask",
            "DetectionPrompt",
            "FramePrompt",
            "ReasoningDashboard",
            "ReasoningStream",
            "CameraDashboard",
            "VLM",
        ],
    },
    "blacknode-dataset": {
        "name": "blacknode-dataset",
        "layer": "learning",
        "components": {},
        "git_url": "https://github.com/temiroff/blacknode-dataset.git",
        "description": "Native episode recording, recovery, validation, LeRobot v3 export, and explicit Hugging Face dataset upload.",
        "node_types": [
            "DatasetCameraStreamList",
            "DatasetBrowser",
            "DatasetCreate",
            "EpisodeDatasetSummary",
            "EpisodeDatasetValidate",
            "EpisodeRecorder",
            "HuggingFaceDatasetUpload",
            "HDF5EpisodeExport",
            "LeRobotV3Export",
            "StreamPublisher",
        ],
    },
    "blacknode-training": {
        "name": "blacknode-training",
        "layer": "learning",
        "components": {},
        "git_url": "https://github.com/temiroff/blacknode-training.git",
        "description": "Robot-policy dataset checks, managed PyTorch training, checkpoints, previews, and deployable policy artifacts.",
        "node_types": [
            "TrainingDatasetCheck",
            "ACTTraining",
            "ACTCheckpointInspect",
            "ACTPolicyPreview",
            "ACTPolicyReplay",
            "ACTPolicyExport",
            "PolicyArtifactLoad",
        ],
    },
    "blacknode-isaac": {
        "name": "blacknode-isaac",
        "layer": "simulation",
        "components": {
            "core": {
                "name": "core", "default": True,
                "node_types": ["IsaacPolicyBridge", "IsaacPolicyRuntime", "IsaacPolicySafetyGate"],
                "dependencies": {
                    "requires": [
                        {"package": "blacknode-controllers", "component": "policy", "version": ">=0.1.0,<1.0.0"},
                    ],
                },
            },
        },
        "git_url": "https://github.com/temiroff/blacknode-isaac.git",
        "description": "Closed-loop policy deployment for Isaac Sim articulations and named RGB sensors.",
        "node_types": [
            "IsaacPolicySafetyGate",
            "IsaacPolicyBridge",
            "IsaacPolicyRuntime",
        ],
    },
}

# Compatibility-mounted core components own every node currently published by
# their repositories. Keeping these lists explicit lets disabled components
# explain exactly which saved workflow nodes they provide.
_CORE_PACKAGES["blacknode-ros2"]["components"]["core"]["node_types"] = list(
    _CORE_PACKAGES["blacknode-ros2"]["node_types"]
)
_CORE_PACKAGES["blacknode-robot"]["components"]["core"]["node_types"] = list(
    _CORE_PACKAGES["blacknode-robot"]["node_types"]
)

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
        "schema_version": 2,
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


def template_component_requirements(workflow: Mapping[str, Any]) -> list[dict[str, str]]:
    """Read direct package components declared by workflow metadata."""
    metadata = workflow.get("metadata")
    if not isinstance(metadata, Mapping):
        return []
    raw_requirements = metadata.get("required_components")
    if not isinstance(raw_requirements, list):
        return []
    requirements: dict[tuple[str, str], dict[str, str]] = {}
    for raw in raw_requirements:
        if isinstance(raw, str):
            package, separator, component = raw.strip().partition("/")
            version = ""
        elif isinstance(raw, Mapping):
            package = str(raw.get("package") or raw.get("name") or "").strip()
            component = str(raw.get("component") or "").strip()
            version = str(raw.get("version") or "").strip()
            separator = "/" if package and component else ""
        else:
            continue
        if not separator or not package or not component:
            continue
        indexed = _CORE_PACKAGES.get(package, {})
        requirements[(package, component)] = {
            "package": package,
            "component": component,
            "version": version,
            "git_url": str(indexed.get("git_url") or ""),
        }
    return list(requirements.values())


def template_adapter_requirements(workflow: Mapping[str, Any]) -> list[dict[str, str]]:
    """Read optional adapters nested under directly required components."""
    metadata = workflow.get("metadata")
    if not isinstance(metadata, Mapping):
        return []
    raw_requirements = metadata.get("required_adapters")
    if not isinstance(raw_requirements, list):
        return []
    requirements: dict[tuple[str, str, str], dict[str, str]] = {}
    for raw in raw_requirements:
        if isinstance(raw, str):
            owner, separator, adapter = raw.strip().partition("@")
            package, component_separator, component = owner.partition("/")
            version = ""
        elif isinstance(raw, Mapping):
            package = str(raw.get("package") or raw.get("name") or "").strip()
            component = str(raw.get("component") or "").strip()
            adapter = str(raw.get("adapter") or "").strip()
            version = str(raw.get("version") or "").strip()
            separator = "@" if adapter else ""
            component_separator = "/" if package and component else ""
        else:
            continue
        if not separator or not component_separator or not package or not component or not adapter:
            continue
        indexed = _CORE_PACKAGES.get(package, {})
        requirements[(package, component, adapter)] = {
            "package": package,
            "component": component,
            "adapter": adapter,
            "version": version,
            "git_url": str(indexed.get("git_url") or ""),
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
    explicit_components = template_component_requirements(workflow)
    explicit_adapters = template_adapter_requirements(workflow)
    missing_packages: dict[str, dict[str, Any]] = {}
    missing_components: list[dict[str, Any]] = []
    missing_adapters: list[dict[str, Any]] = []
    component_plans: list[dict[str, Any]] = []
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

    for requirement in explicit_components:
        package_name = requirement["package"]
        component_name = requirement["component"]
        state = installed.get(package_name)
        if state is None or not bool(state.get("ok", False)):
            add_package({
                "name": package_name,
                "git_url": requirement["git_url"],
                "source": "template_component",
            })
            missing_components.append({**requirement, "reason": "package is not installed"})
            continue
        components = state.get("components", {})
        component = components.get(component_name) if isinstance(components, Mapping) else None
        if not isinstance(component, Mapping):
            missing_components.append({**requirement, "reason": "component is not published by the installed package"})
            continue
        version_ok = True
        if requirement["version"]:
            try:
                from .packages import _version_constraint_satisfied
                version_ok = _version_constraint_satisfied(requirement["version"], str(state.get("version") or ""))
            except Exception:
                version_ok = False
        if not version_ok:
            missing_components.append({**requirement, "reason": f"installed version {state.get('version') or '?'} is incompatible"})
            continue
        if not bool(component.get("enabled", False)):
            missing_components.append({**requirement, "reason": "component is disabled"})
        try:
            from .packages import component_dependency_install_plan
            plan = component_dependency_install_plan(package_name, component_name)
            component_plans.append({**requirement, **plan})
        except Exception:
            pass

    for requirement in explicit_adapters:
        package_name = requirement["package"]
        component_name = requirement["component"]
        adapter_name = requirement["adapter"]
        state = installed.get(package_name)
        if state is None or not bool(state.get("ok", False)):
            add_package({
                "name": package_name,
                "git_url": requirement["git_url"],
                "source": "template_adapter",
            })
            missing_adapters.append({**requirement, "reason": "package is not installed"})
            continue
        if requirement["version"]:
            try:
                from .packages import _version_constraint_satisfied
                version_ok = _version_constraint_satisfied(
                    requirement["version"], str(state.get("version") or "")
                )
            except Exception:
                version_ok = False
            if not version_ok:
                missing_adapters.append({
                    **requirement,
                    "reason": f"installed version {state.get('version') or '?'} is incompatible",
                })
                continue
        components = state.get("components", {})
        component = components.get(component_name) if isinstance(components, Mapping) else None
        adapters = component.get("adapters", {}) if isinstance(component, Mapping) else {}
        adapter = adapters.get(adapter_name) if isinstance(adapters, Mapping) else None
        if not isinstance(adapter, Mapping):
            missing_adapters.append({**requirement, "reason": "adapter is not published by the installed component"})
            continue
        if not bool(component.get("enabled", False)):
            missing_adapters.append({**requirement, "reason": "parent component is disabled"})
        elif not bool(adapter.get("enabled", False)):
            missing_adapters.append({**requirement, "reason": "adapter is disabled"})
        try:
            from .packages import adapter_dependency_install_plan
            plan = adapter_dependency_install_plan(package_name, component_name, adapter_name)
            component_plans.append({**requirement, **plan})
        except Exception:
            pass

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
    if missing_components:
        parts.append("Required components need attention: " + ", ".join(
            f"{item['package']}/{item['component']} ({item['reason']})"
            for item in missing_components
        ))
    if missing_adapters:
        parts.append("Required adapters need attention: " + ", ".join(
            f"{item['package']}/{item['component']}@{item['adapter']} ({item['reason']})"
            for item in missing_adapters
        ))
    return {
        "ok": not packages and not missing_node_types and not missing_components and not missing_adapters,
        "code": (
            "missing_packages" if packages
            else "missing_adapters" if missing_adapters
            else "missing_components" if missing_components
            else "missing_node_types" if missing_node_types
            else "ok"
        ),
        "message": ". ".join(parts) or "Workflow dependencies are available.",
        "missing_node_types": missing_node_types,
        "missing_packages": packages,
        "required_components": explicit_components,
        "required_adapters": explicit_adapters,
        "missing_components": missing_components,
        "missing_adapters": missing_adapters,
        "component_plans": component_plans,
        "unresolved_node_types": unresolved_node_types,
    }


__all__ = [
    "indexed_package",
    "package_index_payload",
    "resolve_workflow_dependencies",
    "template_adapter_requirements",
    "template_component_requirements",
    "template_package_requirements",
    "workflow_node_types",
]
