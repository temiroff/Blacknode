"""Core index and dependency resolution for Blacknode extension packages."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


_CORE_PACKAGES: dict[str, dict[str, Any]] = {
        "blacknode-runtime": {
            "name": "blacknode-runtime",
            "layer": "runtime",
            "components": {
                "deployment": {
                    "name": "deployment",
                    "default": True,
                    "node_types": []
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-runtime.git",
            "description": "Authenticated remote deployment, rollout, rollback, logs, and service supervision.",
            "node_types": []
        },
        "blacknode-skills": {
            "name": "blacknode-skills",
            "layer": "skills",
            "components": {
                "pick-place": {
                    "name": "pick-place",
                    "default": False,
                    "node_types": []
                },
                "follow": {
                    "name": "follow",
                    "aliases": ["follow-person"],
                    "default": False,
                    "node_types": [],
                    "dependencies": {
                        "requires": [
                            {
                                "package": "blacknode-motion",
                                "component": "arm",
                                "version": ">=0.6.0,<1.0.0"
                            },
                            {
                                "package": "blacknode-ros2",
                                "component": "core",
                                "version": ">=0.5.6,<1.0.0"
                            }
                        ]
                    },
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": False,
                            "node_types": [
                                "RobotFollow",
                                "ROS2FollowDetectionJoint",
                                "ROS2LeaderFollower",
                                "ROS2PublishJointState",
                                "ROS2SubscribeJointState",
                                "ROS2JointController",
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
                "ROS2PublishJointState",
                "ROS2SubscribeJointState",
                "ROS2JointController",
                "ROS2NativeFollowDetectionJoint"
            ]
        },
        "blacknode-agent": {
            "name": "blacknode-agent",
            "layer": "agent",
            "components": {
                "executive": {
                    "name": "executive",
                    "aliases": ["planner"],
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
            "description": "Persistent memory and executive mission orchestration.",
            "node_types": [
                "AdaptationRecommendation",
                "EpisodeMemoryIngest",
                "RobotMemoryQuery",
                "RobotTaskCreate",
                "TaskEvaluationRecord"
            ]
        },
        "blacknode-motion": {
            "name": "blacknode-motion",
            "layer": "motion",
            "components": {
                "core": {
                    "name": "core",
                    "default": True,
                    "internal": True,
                    "node_types": []
                },
                "arm": {
                    "name": "arm",
                    "aliases": ["joint-control"],
                    "default": True,
                    "node_types": [
                        "JointMotionProfile"
                    ],
                    "dependencies": {
                        "requires": [
                            {
                                "component": "core",
                                "version": ">=0.6.0,<1.0.0"
                            },
                            {
                                "component": "safety",
                                "version": ">=0.6.0,<1.0.0"
                            }
                        ]
                    },
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
                            ],
                            "dependencies": {
                                "requires": [
                                    {
                                        "package": "blacknode-ros2",
                                        "component": "core",
                                        "version": ">=0.5.6,<1.0.0"
                                    }
                                ]
                            }
                        }
                    }
                },
                "base": {
                    "name": "base",
                    "aliases": ["mobile-base"],
                    "default": False,
                    "node_types": [],
                    "dependencies": {
                        "requires": [
                            {
                                "component": "core",
                                "version": ">=0.6.0,<1.0.0"
                            },
                            {
                                "component": "safety",
                                "version": ">=0.6.0,<1.0.0"
                            }
                        ]
                    },
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
                            ],
                            "dependencies": {
                                "requires": [
                                    {
                                        "package": "blacknode-ros2",
                                        "component": "rosbridge",
                                        "version": ">=0.5.8,<1.0.0"
                                    }
                                ]
                            }
                        }
                    }
                },
                "policy": {
                    "name": "policy",
                    "default": True,
                    "node_types": [],
                    "dependencies": {
                        "requires": [
                            {
                                "component": "core",
                                "version": ">=0.6.0,<1.0.0"
                            },
                            {
                                "component": "safety",
                                "version": ">=0.6.0,<1.0.0"
                            }
                        ]
                    },
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": False,
                            "node_types": [
                                "PolicyRuntime",
                                "PolicySafetyGate"
                            ],
                            "dependencies": {
                                "requires": [
                                    {
                                        "package": "blacknode-ros2",
                                        "component": "rosbridge",
                                        "version": ">=0.5.8,<1.0.0"
                                    }
                                ]
                            }
                        }
                    }
                },
                "safety": {
                    "name": "safety",
                    "default": True,
                    "node_types": [],
                    "dependencies": {
                        "requires": [
                            {
                                "component": "core",
                                "version": ">=0.6.0,<1.0.0"
                            }
                        ]
                    }
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-motion.git",
            "description": "Arm and base planning, trajectory generation, execution, policy, arbitration, and motion safety.",
            "node_types": [
                "BaseSafetyGate",
                "JointMotionProfile",
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
                        "FeetechBusProbe",
                        "FeetechCalibrationProvider",
                        "FeetechRawMonitorProvider"
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
                                        "package": "blacknode-robot",
                                        "component": "contracts",
                                        "version": ">=0.5.0,<1.0.0"
                                    },
                                    {
                                        "package": "blacknode-ros2",
                                        "component": "rosbridge",
                                        "version": ">=0.5.8,<1.0.0"
                                    }
                                ]
                            }
                        }
                    }
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-drivers.git",
            "description": "Physical hardware drivers and firmware adapters, organized as selectively enabled components.",
            "node_types": [
                "FeetechBusConfig",
                "FeetechBusProbe",
                "FeetechCalibrationProvider",
                "FeetechRawMonitorProvider",
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
                "image-processing": {
                    "name": "image-processing",
                    "default": True,
                    "node_types": [
                        "CUDAImageFilter",
                        "CUDAImageFilterStream"
                    ]
                },
                "spatial-processing": {
                    "name": "spatial-processing",
                    "default": True,
                    "node_types": [
                        "Viewer",
                        "SLAM",
                        "WarpParticleLocalization",
                        "WarpDynamicOccupancy",
                        "WarpDepthProjector",
                        "WarpTSDFIntegration",
                        "WarpSurfaceExtraction",
                        "WarpSensorFusion",
                        "WarpTrajectoryEvaluator",
                        "WarpLaserScanFilter",
                        "WarpLiDARViewer",
                        "WarpSLAMDiscoveryViewer"
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
                    "default": False,
                    "node_types": [
                        "CUTLASSGemm"
                    ]
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-cuda.git",
            "description": "GPU capability checks, image processing, tensor operations, and optional benchmarks.",
            "node_types": [
                "CUDAImageFilter",
                "CUDAImageFilterStream",
                "CUTLASS",
                "CUTLASSGemm",
                "GPUCapability",
                "GPURequirement",
                "TensorCoreGEMM",
                "Viewer",
                "SLAM",
                "WarpParticleLocalization",
                "WarpDynamicOccupancy",
                "WarpDepthProjector",
                "WarpTSDFIntegration",
                "WarpSurfaceExtraction",
                "WarpSensorFusion",
                "WarpTrajectoryEvaluator",
                "WarpLaserScanFilter",
                "WarpLiDARViewer",
                "WarpSLAMDiscoveryViewer"
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
                    "default": False,
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
                        "ROS2",
                        "ROS2TopicEcho",
                        "ROS2TopicList",
                        "ROS2TopicPublisher",
                        "ROS2TopicRelay",
                        "ROS2TopicSubscriber"
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
                    "default": False,
                    "node_types": [
                        "ROS2Launch",
                        "ROS2PackageExecutables",
                        "ROS2PythonNode",
                        "ROS2Run",
                        "ROS2WorkspaceBuild"
                    ],
                    "dependencies": {
                        "requires": [{"component": "core"}]
                    }
                },
                "diagnostics": {
                    "name": "diagnostics",
                    "default": True,
                    "node_types": [
                        "ROS2GraphExplorer",
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
                "ROS2",
                "ROS2BridgeEcho",
                "ROS2BridgePublish",
                "ROS2GraphExplorer",
                "ROS2InterfaceShow",
                "ROS2Launch",
                "ROS2NodeList",
                "ROS2PackageExecutables",
                "ROS2PythonNode",
                "ROS2RosbridgeServer",
                "ROS2RosbridgeStatus",
                "ROS2Run",
                "ROS2ServiceList",
                "ROS2Status",
                "ROS2SystemCheck",
                "ROS2TopicEcho",
                "ROS2TopicList",
                "ROS2TopicPublisher",
                "ROS2TopicRelay",
                "ROS2TopicSubscriber",
                "ROS2VisualDashboard",
                "ROS2WorkspaceBuild"
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
                        "RobotCalibrationControl",
                        "RobotCalibrationMockProvider",
                        "RobotCalibrationRecorder"
                    ]
                },
                "capabilities": {
                    "name": "capabilities",
                    "default": True,
                    "node_types": [
                        "ComputeDevice",
                        "DeviceInspect",
                        "RobotAttachment",
                        "RobotAttachmentList",
                        "RobotCapabilityBinding",
                        "RobotCapabilityInspect",
                        "RobotCapabilityList",
                        "RobotCapabilityProfile",
                        "RobotConnectionDashboard",
                        "RobotDiscovery",
                        "RobotMonitor",
                        "RobotRawMonitor",
                        "RobotRawMonitorMockProvider",
                        "RobotROSCapabilityDiscover",
                        "RobotROSInterfaceCheck",
                        "RobotUSBDiscovery"
                    ]
                },
                "devices": {
                    "name": "devices",
                    "default": True,
                    "node_types": [
                        "HardwareCapabilities",
                        "RobotServo"
                    ]
                },
                "telemetry": {
                    "name": "telemetry",
                    "default": True,
                    "node_types": [],
                    "adapters": {
                        "mqtt": {
                            "name": "mqtt",
                            "default": False,
                            "node_types": []
                        }
                    }
                },
                "authorization": {
                    "name": "authorization",
                    "default": False,
                    "node_types": []
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-robot.git",
            "description": "Robot contracts, connected-device lifecycle, normalized telemetry, profiles, and driver launch.",
            "node_types": [
                "ComputeDevice",
                "DeviceInspect",
                "HardwareCapabilities",
                "Robot",
                "RobotAttachment",
                "RobotAttachmentList",
                "RobotCalibrationControl",
                "RobotCalibrationMockProvider",
                "RobotCalibrationRecorder",
                "RobotCapabilityBinding",
                "RobotCapabilityInspect",
                "RobotCapabilityList",
                "RobotCapabilityProfile",
                "RobotConnectionDashboard",
                "RobotDefinition",
                "RobotDiscovery",
                "RobotDriverDescriptor",
                "RobotDriverLauncher",
                "RobotDriverPreset",
                "RobotJointDefinition",
                "RobotJointList",
                "RobotMonitor",
                "RobotProfileDuplicate",
                "RobotProfileList",
                "RobotProfileLoad",
                "RobotProfileSave",
                "RobotRawMonitor",
                "RobotRawMonitorMockProvider",
                "RobotROSCapabilityDiscover",
                "RobotROSInterfaceCheck",
                "RobotServo",
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
                                "CameraROS2Provider",
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
                    "default": True,
                    "node_types": [
                        "DepthCamera",
                        "DepthCameraDeviceSelect",
                        "DepthCameraTestProvider",
                        "DepthObstacleWarning"
                    ],
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": True,
                            "node_types": [
                                "DepthROS2Subscribe"
                            ]
                        }
                    }
                },
                "lidar": {
                    "name": "lidar",
                    "default": True,
                    "node_types": [
                        "LiDAR",
                        "LiDARTestProvider"
                    ],
                    "adapters": {
                        "ros2": {
                            "name": "ros2",
                            "default": True,
                            "node_types": [
                                "LiDARROS2Scan",
                                "LiDARROS2WarpViewer"
                            ],
                            "dependencies": {
                                "requires": [
                                    {
                                        "package": "blacknode-ros2",
                                        "component": "core",
                                        "version": ">=0.4.0,<1.0.0"
                                    },
                                    {
                                        "package": "blacknode-cuda",
                                        "component": "spatial-processing",
                                        "version": ">=0.3.0,<1.0.0"
                                    }
                                ]
                            }
                        }
                    }
                },
                "imu": {
                    "name": "imu",
                    "default": True,
                    "node_types": [
                        "IMU",
                        "IMUTestProvider",
                        "IMUViewer"
                    ]
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
                "CameraROS2Provider",
                "CameraROS2Http",
                "CameraROS2Publish",
                "CameraROS2Subscribe",
                "CameraSelect",
                "CameraStream",
                "DetectionPrompt",
                "DetectionStream",
                "DepthCamera",
                "DepthCameraDeviceSelect",
                "DepthCameraTestProvider",
                "DepthObstacleWarning",
                "DepthROS2Subscribe",
                "FramePrompt",
                "LiDAR",
                "LiDARROS2Scan",
                "LiDARROS2WarpViewer",
                "LiDARTestProvider",
                "IMU",
                "IMUTestProvider",
                "IMUViewer",
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
                    "default": False,
                    "node_types": [
                        "EpisodeEvaluator"
                    ]
                },
                "export": {
                    "name": "export",
                    "default": False,
                    "node_types": [
                        "HDF5EpisodeExport",
                        "LeRobotV3Export"
                    ]
                },
                "publishing": {
                    "name": "publishing",
                    "default": False,
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
                    "default": False,
                    "node_types": [
                        "TrainingDatasetCheck"
                    ]
                },
                "training-jobs": {
                    "name": "training-jobs",
                    "default": False,
                    "node_types": [
                        "ACTTraining"
                    ]
                },
                "checkpoints": {
                    "name": "checkpoints",
                    "default": False,
                    "node_types": [
                        "ACTCheckpointInspect"
                    ]
                },
                "policy-preview": {
                    "name": "policy-preview",
                    "default": False,
                    "node_types": [
                        "ACTPolicyPreview",
                        "ACTPolicyReplay"
                    ]
                },
                "policy-artifacts": {
                    "name": "policy-artifacts",
                    "default": False,
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
                                "package": "blacknode-motion",
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
        },
        "blacknode-newton": {
            "name": "blacknode-newton",
            "layer": "simulation",
            "components": {
                "runtime": {
                    "name": "runtime",
                    "default": True,
                    "node_types": [
                        "NewtonJointCommand",
                        "NewtonSimulation",
                        "NewtonUSDScene",
                        "NewtonViewerConfig"
                    ]
                },
                "viewer-viser": {
                    "name": "viewer-viser",
                    "default": True,
                    "node_types": [],
                    "dependencies": {
                        "requires": [{"component": "runtime"}]
                    }
                },
                "viewer-ovrtx": {
                    "name": "viewer-ovrtx",
                    "default": False,
                    "node_types": [],
                    "dependencies": {
                        "requires": [{"component": "runtime"}]
                    }
                },
                "rosbridge": {
                    "name": "rosbridge",
                    "default": False,
                    "node_types": ["NewtonROSBridge"],
                    "dependencies": {
                        "requires": [
                            {"component": "runtime"},
                            {
                                "package": "blacknode-ros2",
                                "component": "rosbridge",
                                "version": ">=0.5,<1"
                            }
                        ]
                    }
                },
                "replay": {
                    "name": "replay",
                    "default": False,
                    "node_types": ["NewtonReplayBridge"],
                    "dependencies": {
                        "requires": [
                            {"component": "runtime"},
                            {
                                "package": "blacknode-dataset",
                                "component": "publishing",
                                "version": ">=0.2,<1"
                            }
                        ]
                    }
                }
            },
            "git_url": "https://github.com/temiroff/blacknode-newton.git",
            "description": "Interactive Newton physics sessions, browser visualization, and safe articulation teleoperation for Blacknode.",
            "node_types": [
                "NewtonJointCommand",
                "NewtonReplayBridge",
                "NewtonROSBridge",
                "NewtonSimulation",
                "NewtonUSDScene",
                "NewtonViewerConfig"
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


_PACKAGE_ALIASES = {
    # blacknode-controllers was renamed to blacknode-motion. Keep saved
    # workflows deployable while their metadata is migrated naturally.
    "blacknode-controllers": "blacknode-motion",
}

_PACKAGE_COMPONENT_ALIASES = {
    ("blacknode-motion", "joint-control"): "arm",
}


def canonical_package_name(name: str) -> str:
    """Resolve a saved package name to its current official package name."""
    clean_name = str(name or "").strip()
    return _PACKAGE_ALIASES.get(clean_name, clean_name)


def _canonical_requirement_component(package: str, component: str) -> str:
    return _PACKAGE_COMPONENT_ALIASES.get(
        (package, str(component or "").strip()),
        str(component or "").strip(),
    )


def _manifest_node_types(info: Any) -> set[str]:
    """Collect every node type declared by an installed package manifest."""
    declared = {
        str(node_type)
        for node_type in getattr(info, "node_types", [])
        if str(node_type)
    }
    components = getattr(info, "components", {})
    if not isinstance(components, Mapping):
        return declared
    for component in components.values():
        if not isinstance(component, Mapping):
            continue
        declared.update(
            str(node_type)
            for node_type in component.get("node_types", [])
            if str(node_type)
        )
        adapters = component.get("adapters", {})
        if not isinstance(adapters, Mapping):
            continue
        for adapter in adapters.values():
            if not isinstance(adapter, Mapping):
                continue
            declared.update(
                str(node_type)
                for node_type in adapter.get("node_types", [])
                if str(node_type)
            )
    return declared


def _runtime_package_index() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    """Merge installed self-describing manifests over the shipped catalog."""
    packages = {
        name: {
            **package,
            "node_types": list(package["node_types"]),
        }
        for name, package in _CORE_PACKAGES.items()
    }
    nodes = {
        node_type: dict(resolution)
        for node_type, resolution in _NODE_PACKAGE_INDEX.items()
    }
    try:
        from .packages import installed_packages

        installed = installed_packages()
    except Exception:
        installed = []

    for info in installed:
        name = str(getattr(info, "name", "") or "").strip()
        if not name:
            continue
        declared = _manifest_node_types(info)
        package = packages.get(name)
        if package is None:
            git_status = getattr(info, "git_status", {})
            git_url = (
                str(git_status.get("remote") or "")
                if isinstance(git_status, Mapping)
                else ""
            )
            package = {
                "name": name,
                "layer": str(getattr(info, "layer", "") or "extensions"),
                "components": getattr(info, "components", {}),
                "git_url": git_url,
                "description": str(getattr(info, "description", "") or ""),
                "node_types": [],
            }
            packages[name] = package
        package["node_types"] = sorted({
            *package.get("node_types", []),
            *declared,
        })
        git_url = str(package.get("git_url") or "")
        for node_type in declared:
            nodes.setdefault(node_type, {
                "package": name,
                "git_url": git_url,
            })
    return packages, nodes


def package_index_payload() -> dict[str, Any]:
    """Return the shipped catalog enriched by installed package manifests."""
    packages, nodes = _runtime_package_index()
    return {
        "schema_version": 2,
        "packages": packages,
        "nodes": nodes,
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
        name = canonical_package_name(name)

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
        component_name, adapter_separator, adapter = component.partition("@")
        if adapter_separator and component_name and adapter:
            component = component_name
        if not separator or not package or not component:
            continue
        package = canonical_package_name(package)
        component = _canonical_requirement_component(package, component)
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
    raw_requirements: list[Any] = []
    declared_adapters = metadata.get("required_adapters")
    if isinstance(declared_adapters, list):
        raw_requirements.extend(declared_adapters)
    # Older templates sometimes placed compact component@adapter references in
    # required_components. Preserve those saved workflows by resolving both the
    # parent component and the nested adapter.
    declared_components = metadata.get("required_components")
    if isinstance(declared_components, list):
        raw_requirements.extend(
            raw
            for raw in declared_components
            if (
                isinstance(raw, str)
                and "@" in raw.partition("/")[2]
            ) or (
                isinstance(raw, Mapping)
                and "@" in str(raw.get("component") or "")
            )
        )
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
            if not adapter:
                component, separator, adapter = component.partition("@")
            else:
                separator = "@"
            component_separator = "/" if package and component else ""
        else:
            continue
        if not separator or not component_separator or not package or not component or not adapter:
            continue
        package = canonical_package_name(package)
        component = _canonical_requirement_component(package, component)
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
    _, runtime_node_index = _runtime_package_index()

    def installed_component(
        components: Any,
        requested_name: str,
    ) -> tuple[str, Mapping[str, Any] | None]:
        if not isinstance(components, Mapping):
            return requested_name, None
        exact = components.get(requested_name)
        if isinstance(exact, Mapping):
            return requested_name, exact
        for name, candidate in components.items():
            if (
                isinstance(candidate, Mapping)
                and requested_name in candidate.get("aliases", [])
            ):
                return str(name), candidate
        return requested_name, None

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
        _canonical_name, component = installed_component(components, component_name)
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
        _canonical_name, component = installed_component(components, component_name)
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
            resolution = runtime_node_index.get(node_type)
            if resolution is not None:
                package_name = resolution["package"]
                requirement = {
                    "name": package_name,
                    "git_url": explicit.get(package_name, {}).get("git_url", resolution["git_url"]),
                    "node_types": [node_type],
                    "source": (
                        "core_index"
                        if node_type in _NODE_PACKAGE_INDEX
                        else "package_manifest"
                    ),
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
    "canonical_package_name",
    "indexed_package",
    "package_index_payload",
    "resolve_workflow_dependencies",
    "template_adapter_requirements",
    "template_component_requirements",
    "template_package_requirements",
    "workflow_node_types",
]
