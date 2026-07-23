"""Core index and dependency resolution for Blacknode extension packages."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


_CORE_PACKAGES: dict[str, dict[str, Any]] = {
        "blacknode-skills": {
            "name": "blacknode-skills",
            "layer": "skills",
            "components": {
                "pick-place": {
                    "name": "pick-place",
                    "default": False,
                    "node_types": []
                },
                "follow-person": {
                    "name": "follow-person",
                    "default": False,
                    "node_types": [],
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": False,
                            "node_types": [
                                "RobotFollow",
                                "ROS2FollowDetectionJoint",
                                "ROS2LeaderFollower",
                                "ROS2NativeFollowDetectionJoint"
                            ]
                        }
                    }
                },
                "delivery": {
                    "name": "delivery",
                    "default": False,
                    "node_types": []
                },
                "docking": {
                    "name": "docking",
                    "default": False,
                    "node_types": []
                },
                "inspection": {
                    "name": "inspection",
                    "default": False,
                    "node_types": []
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-skills.git",
            "description": "Reusable task-level robot skills composed from stable capabilities.",
            "node_types": [
                "RobotFollow",
                "ROS2FollowDetectionJoint",
                "ROS2LeaderFollower",
                "ROS2NativeFollowDetectionJoint"
            ]
        },
        "blacknode-agent": {
            "name": "blacknode-agent",
            "layer": "agent",
            "components": {
                "planner": {
                    "name": "planner",
                    "default": False,
                    "node_types": []
                },
                "skill-registry": {
                    "name": "skill-registry",
                    "default": False,
                    "node_types": []
                },
                "mission-review": {
                    "name": "mission-review",
                    "default": False,
                    "node_types": []
                },
                "confirmation": {
                    "name": "confirmation",
                    "default": False,
                    "node_types": []
                },
                "memory": {
                    "name": "memory",
                    "default": True,
                    "node_types": [
                        "AdaptationRecommendation",
                        "EpisodeMemoryIngest",
                        "RobotMemoryQuery",
                        "RobotTaskCreate",
                        "TaskEvaluationRecord"
                    ]
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-agent.git",
            "description": "Planning, memory, review, confirmation, and skill orchestration.",
            "node_types": [
                "AdaptationRecommendation",
                "EpisodeMemoryIngest",
                "RobotMemoryQuery",
                "RobotTaskCreate",
                "TaskEvaluationRecord"
            ]
        },
        "blacknode-controllers": {
            "name": "blacknode-controllers",
            "layer": "controllers",
            "components": {
                "joint-control": {
                    "name": "joint-control",
                    "default": True,
                    "node_types": [],
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": True,
                            "node_types": [
                                "ROS2JointSliders",
                                "ROS2JointState",
                                "ROS2ManualMove",
                                "ROS2MotionDashboard",
                                "ROS2SetJoint"
                            ]
                        }
                    }
                },
                "mobile-base": {
                    "name": "mobile-base",
                    "default": False,
                    "node_types": [],
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": False,
                            "node_types": [
                                "BaseSafetyGate",
                                "ROS2BaseMove",
                                "ROS2BaseStop",
                                "ROS2LaserScanCheck",
                                "ROS2OdomState"
                            ]
                        }
                    }
                },
                "nav2": {
                    "name": "nav2",
                    "default": False,
                    "node_types": []
                },
                "manipulation": {
                    "name": "manipulation",
                    "default": False,
                    "node_types": []
                },
                "policy": {
                    "name": "policy",
                    "default": True,
                    "node_types": [],
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": False,
                            "node_types": [
                                "PolicyRuntime",
                                "PolicySafetyGate"
                            ]
                        }
                    }
                },
                "command-arbitration": {
                    "name": "command-arbitration",
                    "default": False,
                    "node_types": []
                },
                "safety-supervisors": {
                    "name": "safety-supervisors",
                    "default": False,
                    "node_types": []
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-controllers.git",
            "description": "Generic motion, manipulation, policy, arbitration, and safety controllers.",
            "node_types": [
                "BaseSafetyGate",
                "PolicyRuntime",
                "PolicySafetyGate",
                "ROS2BaseMove",
                "ROS2BaseStop",
                "ROS2JointSliders",
                "ROS2JointState",
                "ROS2LaserScanCheck",
                "ROS2ManualMove",
                "ROS2MotionDashboard",
                "ROS2OdomState",
                "ROS2SetJoint"
            ]
        },
        "blacknode-drivers": {
            "name": "blacknode-drivers",
            "layer": "drivers",
            "components": {
                "feetech": {
                    "name": "feetech",
                    "default": True,
                    "node_types": [
                        "FeetechBusConfig",
                        "FeetechBusProbe"
                    ],
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": False,
                            "node_types": [
                                "FeetechROS2Adapter"
                            ],
                            "dependencies": {
                                "requires": [
                                    {
                                        "package": "blacknode-ros2",
                                        "component": "core",
                                        "version": ">=0.2.0,<1.0.0"
                                    }
                                ]
                            }
                        }
                    }
                },
                "stm32": {
                    "name": "stm32",
                    "default": False,
                    "node_types": []
                },
                "serial": {
                    "name": "serial",
                    "default": False,
                    "node_types": []
                },
                "can": {
                    "name": "can",
                    "default": False,
                    "node_types": []
                },
                "usb": {
                    "name": "usb",
                    "default": False,
                    "node_types": []
                },
                "motor-controllers": {
                    "name": "motor-controllers",
                    "default": False,
                    "node_types": []
                },
                "sensor-drivers": {
                    "name": "sensor-drivers",
                    "default": False,
                    "node_types": []
                },
                "vendor-adapters": {
                    "name": "vendor-adapters",
                    "default": False,
                    "node_types": []
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-drivers.git",
            "description": "Physical hardware drivers and firmware adapters, organized as selectively enabled components.",
            "node_types": [
                "FeetechBusConfig",
                "FeetechBusProbe",
                "FeetechROS2Adapter"
            ]
        },
        "blacknode-cuda": {
            "name": "blacknode-cuda",
            "layer": "compute",
            "components": {
                "capability": {
                    "name": "capability",
                    "default": True,
                    "node_types": [
                        "GPUCapability",
                        "GPURequirement"
                    ]
                },
                "kernels": {
                    "name": "kernels",
                    "default": True,
                    "node_types": [
                        "CUDACustomKernel",
                        "CUDAKernelLab"
                    ]
                },
                "image-processing": {
                    "name": "image-processing",
                    "default": True,
                    "node_types": [
                        "CUDAImageFilter",
                        "CUDAImageFilterStream"
                    ]
                },
                "tensor-operations": {
                    "name": "tensor-operations",
                    "default": True,
                    "node_types": [
                        "CUTLASS",
                        "TensorCoreGEMM"
                    ]
                },
                "benchmarks": {
                    "name": "benchmarks",
                    "default": True,
                    "node_types": [
                        "CUTLASSGemm"
                    ]
                }
            },
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
                "TensorCoreGEMM"
            ]
        },
        "blacknode-ros2": {
            "name": "blacknode-ros2",
            "layer": "ros2",
            "components": {
                "core": {
                    "name": "core",
                    "default": True,
                    "node_types": []
                },
                "rosbridge": {
                    "name": "rosbridge",
                    "default": True,
                    "node_types": [
                        "ROS2BridgeEcho",
                        "ROS2BridgePublish",
                        "ROS2RosbridgeServer",
                        "ROS2RosbridgeStatus"
                    ],
                    "dependencies": {
                        "requires": [{"component": "core"}]
                    }
                },
                "topics": {
                    "name": "topics",
                    "default": True,
                    "node_types": [
                        "ROS2TopicEcho",
                        "ROS2TopicList",
                        "ROS2TopicPublish",
                        "ROS2TopicPublisher"
                    ],
                    "dependencies": {
                        "requires": [{"component": "core"}]
                    }
                },
                "services": {
                    "name": "services",
                    "default": True,
                    "node_types": [
                        "ROS2ServiceList"
                    ],
                    "dependencies": {
                        "requires": [{"component": "core"}]
                    }
                },
                "processes": {
                    "name": "processes",
                    "default": True,
                    "node_types": [
                        "ROS2Launch",
                        "ROS2PackageExecutables",
                        "ROS2Run"
                    ],
                    "dependencies": {
                        "requires": [{"component": "core"}]
                    }
                },
                "diagnostics": {
                    "name": "diagnostics",
                    "default": True,
                    "node_types": [
                        "ROS2InterfaceShow",
                        "ROS2NodeList",
                        "ROS2Status",
                        "ROS2SystemCheck",
                        "ROS2VisualDashboard"
                    ],
                    "dependencies": {
                        "requires": [{"component": "core"}]
                    }
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-ros2.git",
            "description": "ROS 2 integration primitives: graph discovery, topics, services, processes, and native/rosbridge transports.",
            "node_types": [
                "ROS2BridgeEcho",
                "ROS2BridgePublish",
                "ROS2InterfaceShow",
                "ROS2Launch",
                "ROS2NodeList",
                "ROS2PackageExecutables",
                "ROS2RosbridgeServer",
                "ROS2RosbridgeStatus",
                "ROS2Run",
                "ROS2ServiceList",
                "ROS2Status",
                "ROS2SystemCheck",
                "ROS2TopicEcho",
                "ROS2TopicList",
                "ROS2TopicPublish",
                "ROS2TopicPublisher",
                "ROS2VisualDashboard"
            ]
        },
        "blacknode-robot": {
            "name": "blacknode-robot",
            "layer": "robot",
            "components": {
                "core": {
                    "name": "core",
                    "default": True,
                    "node_types": []
                },
                "contracts": {
                    "name": "contracts",
                    "default": True,
                    "node_types": [
                        "RobotDefinition",
                        "RobotJointDefinition",
                        "RobotJointList"
                    ]
                },
                "profiles": {
                    "name": "profiles",
                    "default": True,
                    "node_types": [
                        "RobotProfileDuplicate",
                        "RobotProfileList",
                        "RobotProfileLoad",
                        "RobotProfileSave"
                    ]
                },
                "models": {
                    "name": "models",
                    "default": True,
                    "node_types": [
                        "Robot",
                        "RobotDriverDescriptor",
                        "RobotDriverLauncher",
                        "RobotDriverPreset"
                    ]
                },
                "calibration": {
                    "name": "calibration",
                    "default": True,
                    "node_types": [
                        "RobotCalibrationRecorder"
                    ]
                },
                "capabilities": {
                    "name": "capabilities",
                    "default": True,
                    "node_types": [
                        "RobotConnectionDashboard",
                        "RobotDiscovery",
                        "RobotUSBDiscovery"
                    ]
                },
                "authorization": {
                    "name": "authorization",
                    "default": False,
                    "node_types": []
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-robot.git",
            "description": "Generic robot setup: USB discovery, serial permission diagnostics, driver launch, and standard robot profiles.",
            "node_types": [
                "Robot",
                "RobotCalibrationRecorder",
                "RobotConnectionDashboard",
                "RobotDefinition",
                "RobotDiscovery",
                "RobotDriverDescriptor",
                "RobotDriverLauncher",
                "RobotDriverPreset",
                "RobotJointDefinition",
                "RobotJointList",
                "RobotProfileDuplicate",
                "RobotProfileList",
                "RobotProfileLoad",
                "RobotProfileSave",
                "RobotUSBDiscovery"
            ]
        },
        "blacknode-perception": {
            "name": "blacknode-perception",
            "layer": "perception",
            "components": {
                "camera": {
                    "name": "camera",
                    "default": True,
                    "node_types": [
                        "Camera",
                        "CameraCalibration",
                        "CameraDiscovery",
                        "CameraSelect",
                        "CameraStream"
                    ],
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": True,
                            "node_types": [
                                "CameraROS2Subscribe",
                                "CameraROS2Publish",
                                "CameraROS2Http"
                            ]
                        }
                    }
                },
                "vlm": {
                    "name": "vlm",
                    "default": True,
                    "node_types": [
                        "CameraDashboard",
                        "DetectionPrompt",
                        "FramePrompt",
                        "ReasoningDashboard",
                        "ReasoningStream",
                        "VLM"
                    ]
                },
                "depth": {
                    "name": "depth",
                    "default": False,
                    "node_types": []
                },
                "lidar": {
                    "name": "lidar",
                    "default": False,
                    "node_types": []
                },
                "imu": {
                    "name": "imu",
                    "default": False,
                    "node_types": []
                },
                "detection": {
                    "name": "detection",
                    "default": True,
                    "node_types": [
                        "DetectionStream",
                        "DetectionYolo"
                    ],
                    "dependencies": {
                        "requires": [
                            {
                                "package": "blacknode-perception",
                                "component": "camera",
                                "version": ">=0.2.0,<1.0.0"
                            }
                        ]
                    }
                },
                "tracking": {
                    "name": "tracking",
                    "default": True,
                    "node_types": [
                        "TrackingObject",
                        "TrackingColorHint",
                        "TrackingColorMask"
                    ]
                },
                "slam": {
                    "name": "slam",
                    "default": False,
                    "node_types": []
                },
                "localization": {
                    "name": "localization",
                    "default": False,
                    "node_types": []
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-perception.git",
            "description": "Camera, tracking, VLM, and spatial-perception capabilities organized as selectable components.",
            "node_types": [
                "TrackingObject",
                "TrackingColorHint",
                "TrackingColorMask",
                "Camera",
                "CameraCalibration",
                "CameraDashboard",
                "CameraDiscovery",
                "CameraROS2Http",
                "CameraROS2Publish",
                "CameraROS2Subscribe",
                "CameraSelect",
                "CameraStream",
                "DetectionPrompt",
                "DetectionStream",
                "FramePrompt",
                "ReasoningDashboard",
                "ReasoningStream",
                "VLM",
                "DetectionYolo"
            ]
        },
        "blacknode-dataset": {
            "name": "blacknode-dataset",
            "layer": "learning",
            "components": {
                "recording": {
                    "name": "recording",
                    "default": True,
                    "node_types": [
                        "DatasetBrowser",
                        "DatasetCameraStreamList",
                        "DatasetCreate",
                        "EpisodeRecorder"
                    ]
                },
                "replay": {
                    "name": "replay",
                    "default": True,
                    "node_types": [
                        "EpisodeReplay",
                        "TrajectorySmoother"
                    ]
                },
                "validation": {
                    "name": "validation",
                    "default": True,
                    "node_types": [
                        "EpisodeDatasetSummary",
                        "EpisodeDatasetValidate",
                        "EpisodeStats"
                    ]
                },
                "evaluation": {
                    "name": "evaluation",
                    "default": True,
                    "node_types": [
                        "EpisodeEvaluator"
                    ]
                },
                "export": {
                    "name": "export",
                    "default": True,
                    "node_types": [
                        "HDF5EpisodeExport",
                        "LeRobotV3Export"
                    ]
                },
                "publishing": {
                    "name": "publishing",
                    "default": True,
                    "node_types": [
                        "BlacknodeHubExport",
                        "HuggingFaceDatasetUpload",
                        "StreamPublisher"
                    ]
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-dataset.git",
            "description": "Native episode recording, recovery, validation, LeRobot v3 export, and explicit Hugging Face dataset upload.",
            "node_types": [
                "BlacknodeHubExport",
                "DatasetBrowser",
                "DatasetCameraStreamList",
                "DatasetCreate",
                "EpisodeDatasetSummary",
                "EpisodeDatasetValidate",
                "EpisodeEvaluator",
                "EpisodeRecorder",
                "EpisodeReplay",
                "EpisodeStats",
                "HDF5EpisodeExport",
                "HuggingFaceDatasetUpload",
                "LeRobotV3Export",
                "StreamPublisher",
                "TrajectorySmoother"
            ]
        },
        "blacknode-training": {
            "name": "blacknode-training",
            "layer": "learning",
            "components": {
                "dataset-check": {
                    "name": "dataset-check",
                    "default": True,
                    "node_types": [
                        "TrainingDatasetCheck"
                    ]
                },
                "training-jobs": {
                    "name": "training-jobs",
                    "default": True,
                    "node_types": [
                        "ACTTraining"
                    ]
                },
                "checkpoints": {
                    "name": "checkpoints",
                    "default": True,
                    "node_types": [
                        "ACTCheckpointInspect"
                    ]
                },
                "policy-preview": {
                    "name": "policy-preview",
                    "default": True,
                    "node_types": [
                        "ACTPolicyPreview",
                        "ACTPolicyReplay"
                    ]
                },
                "policy-artifacts": {
                    "name": "policy-artifacts",
                    "default": True,
                    "node_types": [
                        "ACTPolicyExport",
                        "PolicyArtifactLoad"
                    ]
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-training.git",
            "description": "Robot-policy dataset checks, managed PyTorch training, checkpoints, previews, and deployable policy artifacts.",
            "node_types": [
                "ACTCheckpointInspect",
                "ACTPolicyExport",
                "ACTPolicyPreview",
                "ACTPolicyReplay",
                "ACTTraining",
                "PolicyArtifactLoad",
                "TrainingDatasetCheck"
            ]
        },
        "blacknode-isaac": {
            "name": "blacknode-isaac",
            "layer": "simulation",
            "components": {
                "core": {
                    "name": "core",
                    "default": True,
                    "node_types": [],
                    "dependencies": {
                        "requires": [
                            {
                                "package": "blacknode-controllers",
                                "component": "policy",
                                "version": ">=0.1.0,<1.0.0"
                            }
                        ]
                    }
                },
                "bridge": {
                    "name": "bridge",
                    "default": True,
                    "node_types": [
                        "IsaacPolicyBridge"
                    ]
                },
                "robot-models": {
                    "name": "robot-models",
                    "default": False,
                    "node_types": []
                },
                "virtual-sensors": {
                    "name": "virtual-sensors",
                    "default": False,
                    "node_types": []
                },
                "articulations": {
                    "name": "articulations",
                    "default": False,
                    "node_types": []
                },
                "policy-runtime": {
                    "name": "policy-runtime",
                    "default": True,
                    "node_types": [
                        "IsaacPolicyRuntime",
                        "IsaacPolicySafetyGate"
                    ]
                },
                "scenario-assets": {
                    "name": "scenario-assets",
                    "default": False,
                    "node_types": []
                },
                "qualification": {
                    "name": "qualification",
                    "default": False,
                    "node_types": []
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-isaac.git",
            "description": "Closed-loop policy deployment for Isaac Sim articulations and named RGB sensors.",
            "node_types": [
                "IsaacPolicyBridge",
                "IsaacPolicyRuntime",
                "IsaacPolicySafetyGate"
            ]
        }
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
