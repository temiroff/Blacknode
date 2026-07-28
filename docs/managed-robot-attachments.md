# Managed robot attachments

Blacknode attachments describe cameras, depth cameras, LiDARs, IMUs, and other
devices mounted on a robot. An attachment keeps stable physical identity,
capability, ROS 2 interfaces, frames, calibration, and mounting extrinsics.
Workflows consume the stable capability and attachment ID; provider-specific
topics and launch commands stay in the device configuration.

## Lifecycle model

An enabled attachment has an explicit managed-service lifecycle:

1. **Configured** — the attachment record and expected interfaces are valid.
2. **Starting** — the Runtime starts or reuses the selected provider.
3. **Ready** — every required ROS 2 interface has a live publisher of the
   expected type and fresh data has been observed.
4. **Degraded** — the provider process is alive but a required interface is
   missing, has the wrong type, or is stale.
5. **Stopped** — Blacknode has stopped the provider and its complete process
   group.
6. **Unavailable** — the provider package, executable, device, permission, or
   ROS 2 environment is unavailable.

Start and stop actions must be idempotent. Checking an attachment is read-only
and never starts a provider implicitly. Starting a provider is always an
explicit user action.

Attachment providers are managed independently from workflow deployments.
Replacing a workflow must not restart a healthy camera, LiDAR, or IMU service.
One robot control workflow owns motion authority; read-only perception,
recording, diagnostics, and UI clients may consume attachment streams
concurrently.

## Ownership

| Layer | Responsibility |
|---|---|
| `blacknode-runtime` | Authenticated process supervision, logs, status, and complete stop paths |
| `blacknode-ros2` | ROS 2 process/topic primitives, native and bridge transports, type and endpoint inspection |
| `blacknode-perception` | RGB, depth, point-cloud, camera-info, preview, and camera-provider contracts |
| `blacknode-drivers` | Vendor SDKs, device probes, firmware, and provider-specific hardware setup |
| Blacknode editor | Attachment setup, explicit Start/Stop, preview, diagnostics, and workflow creation |
| Workflow nodes | Detection, tracking, SLAM, recording, policies, and robot reactions |

Base robot and attachment records remain loadable when ROS 2, camera SDKs, or
provider packages are absent. Missing providers return a structured unavailable
state and do not prevent unrelated capabilities from loading.

## RGB and depth interface groups

A camera provider reports an interface group instead of one hard-coded topic:

| Interface | ROS 2 type | Required |
|---|---|---|
| RGB image | `sensor_msgs/msg/Image` or `sensor_msgs/msg/CompressedImage` | yes for RGB |
| RGB camera info | `sensor_msgs/msg/CameraInfo` | recommended |
| Depth image | `sensor_msgs/msg/Image` | yes for depth |
| Depth camera info | `sensor_msgs/msg/CameraInfo` | recommended |
| Point cloud | `sensor_msgs/msg/PointCloud2` | optional |

The provider records the actual image encoding reported in each message.
Common depth encodings include `16UC1` with a millimetre scale and `32FC1` with
a metre scale. A depth preview is a visualization; workflows that need metric
depth consume the depth-stream contract and original topic.

## Initial provider profiles

### Existing ROS 2 topics

Blacknode does not start a driver. It validates and consumes topics already
published by another managed stack.

### Generic USB camera

The provider starts Blacknode's bundled `perception_camera usb_camera` process
and verifies its RGB image and camera-info topics. Device selection and
parameters remain in the provider configuration.

### Blacknode RGB-D

The bundled `perception_camera rgbd_camera.launch.py` provider accepts explicit
RGB and metric-depth video inputs and publishes a normalized interface:

```text
/camera/rgb/image_raw
/camera/rgb/camera_info
/camera/depth/image_raw
/camera/depth/camera_info
```

Blacknode accepts metric depth encoded as `16UC1` or `32FC1`. Calibrated
downstream components may derive a point cloud when intrinsics and extrinsics
are available. Native ROS 2 topics remain the sensor-data source of truth.

## Editor workflow

The target operator flow is:

```text
Manage robot
  → Attachments
  → Add camera
  → Detect/select provider
  → Configure expected RGB/depth interfaces
  → Start provider
  → Verify publishers and freshness
  → Preview RGB/depth
  → Save frames and mounting extrinsics
  → Create a detection, recording, SLAM, or policy workflow
```

Advanced provider and ROS fields stay collapsed. The robot summary shows only
attachment count and health.

## Streaming and remote clients

ROS 2 remains inside the robot/device data plane. The Runtime exposes stable,
authenticated attachment stream handles:

- HTTPS for snapshots, configuration, and actions.
- WebSocket for status, logs, detections, maps, and structured telemetry.
- MJPEG as the first LAN-compatible RGB/depth preview.
- WebRTC as the mobile and remote low-latency video transport.

Mobile clients do not connect directly to DDS or an unauthenticated rosbridge.
Zenoh may bridge ROS 2 graphs between routed sites. MQTT may carry fleet events
and notifications; neither is required for the initial local camera path.

## Safety and verification

- Camera and depth providers never arm or command robot motion.
- Attachment readiness requires source freshness, not only a live process.
- Motion-producing workflows consume detections, maps, or policies through the
  robot motion-authority and safety contracts.
- Every provider requires a mock or replay implementation.
- Provider swaps must pass the same RGB/depth contract tests.
- Hardware validation must report which physical camera, depth, ROS, and
  network paths were exercised.
