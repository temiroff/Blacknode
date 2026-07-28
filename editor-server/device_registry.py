"""Local registry and authenticated client for Blacknode hardware devices."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_MAX_RESPONSE_BYTES = 1024 * 1024
_ID_RE = re.compile(r"[^a-z0-9]+")
_ATTACHMENT_ID_RE = re.compile(r"[^a-z0-9]+")
_ROS_MESSAGE_TYPE_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*/(?:msg|srv|action)/[A-Za-z][A-Za-z0-9_]*$"
)
_ATTACHMENT_TYPES = {
    "camera",
    "depth_camera",
    "lidar",
    "imu",
    "gps",
    "microphone",
    "custom",
}


class DeviceRegistryError(RuntimeError):
    """A local registry or remote device request could not be completed."""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_base_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise DeviceRegistryError("Device URL is required.")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        raise DeviceRegistryError("Device URL must start with http:// or https://.")
    if not parsed.hostname:
        raise DeviceRegistryError("Device URL must include a hostname or IP address.")
    if parsed.username or parsed.password:
        raise DeviceRegistryError("Device URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise DeviceRegistryError("Device URL must not contain a query or fragment.")
    if parsed.path not in {"", "/"}:
        raise DeviceRegistryError("Enter the service base URL without an endpoint path.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise DeviceRegistryError("Device URL contains an invalid port.") from exc
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    authority = f"{host}:{port}" if port is not None else host
    return urllib.parse.urlunsplit((parsed.scheme, authority, "", "", ""))


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def default_runtime_url(hardware_url: str) -> str:
    parsed = urllib.parse.urlsplit(normalize_base_url(hardware_url))
    host = f"[{parsed.hostname}]" if ":" in str(parsed.hostname) else parsed.hostname
    return urllib.parse.urlunsplit((parsed.scheme, f"{host}:8766", "", "", ""))


def _slug(value: str) -> str:
    return _ID_RE.sub("-", value.strip().lower()).strip("-")[:48] or "device"


def _attachment_identifier(value: Any, fallback: str = "attachment") -> str:
    text = _ATTACHMENT_ID_RE.sub(
        "_",
        str(value or "").strip().lower(),
    ).strip("_")
    if not text:
        text = fallback
    if not text[0].isalpha():
        text = f"attachment_{text}"
    return text[:64]


def _finite_attachment_number(value: Any, field: str) -> float:
    try:
        result = float(value or 0.0)
    except (TypeError, ValueError) as exc:
        raise DeviceRegistryError(f"{field} must be a number.") from exc
    if not math.isfinite(result):
        raise DeviceRegistryError(f"{field} must be finite.")
    return result


def _normalize_attachment(
    values: dict[str, Any],
    *,
    existing_id: str = "",
) -> dict[str, Any]:
    requested_id = _attachment_identifier(
        values.get("attachment_id")
        or values.get("id")
        or values.get("display_name"),
    )
    if existing_id and requested_id != existing_id:
        raise DeviceRegistryError(
            "Attachment IDs are stable. Duplicate the attachment to use a new ID."
        )
    attachment_id = existing_id or requested_id
    display_name = str(
        values.get("display_name")
        or attachment_id.replace("_", " ").title()
    ).strip()
    if not display_name:
        raise DeviceRegistryError("Attachment name is required.")
    attachment_type = str(
        values.get("attachment_type") or "custom"
    ).strip().lower()
    if attachment_type not in _ATTACHMENT_TYPES:
        raise DeviceRegistryError(
            "Attachment type must be camera, depth camera, LiDAR, IMU, GPS, "
            "microphone, or custom."
        )
    capability = _attachment_identifier(
        values.get("capability") or attachment_type,
        attachment_type,
    )
    provider = values.get("provider") if isinstance(values.get("provider"), dict) else {}
    provider_package = str(
        values.get("provider_package") or provider.get("package") or ""
    ).strip()
    provider_component = str(
        values.get("provider_component") or provider.get("component") or ""
    ).strip()
    provider_adapter = str(
        values.get("provider_adapter") or provider.get("adapter") or "ros2"
    ).strip()
    if not provider_package or not provider_component:
        raise DeviceRegistryError(
            "Attachment provider package and component are required."
        )
    provider_profile = str(
        values.get("provider_profile")
        or provider.get("profile")
        or "existing_topics"
    ).strip().lower()
    if provider_profile not in {
        "existing_topics",
        "usb_cam",
        "rosorin_depth",
        "custom_launch",
    }:
        raise DeviceRegistryError(
            "Attachment provider profile must be existing topics, USB camera, "
            "ROSOrin depth camera, or custom ROS 2 launch."
        )
    topic = str(values.get("topic") or "").strip()
    if not topic.startswith("/") or any(character.isspace() for character in topic):
        raise DeviceRegistryError(
            "ROS 2 topic must start with / and cannot contain spaces."
        )
    message_type = str(values.get("message_type") or "").strip()
    if not _ROS_MESSAGE_TYPE_RE.fullmatch(message_type):
        raise DeviceRegistryError(
            "ROS 2 message type must look like sensor_msgs/msg/Image."
        )
    camera_info_topic = str(values.get("camera_info_topic") or "").strip()
    depth_topic = str(values.get("depth_topic") or "").strip()
    point_cloud_topic = str(values.get("point_cloud_topic") or "").strip()
    for label, optional_topic in (
        ("Camera info", camera_info_topic),
        ("Depth", depth_topic),
        ("Point cloud", point_cloud_topic),
    ):
        if optional_topic and (
            not optional_topic.startswith("/")
            or any(character.isspace() for character in optional_topic)
        ):
            raise DeviceRegistryError(
                f"{label} ROS 2 topic must start with / and cannot contain spaces."
            )
    launch_package = str(values.get("launch_package") or "").strip()
    launch_target = str(values.get("launch_target") or "").strip()
    raw_launch_arguments = values.get("launch_arguments") or []
    if isinstance(raw_launch_arguments, str):
        launch_arguments = [
            value
            for value in raw_launch_arguments.splitlines()
            if value.strip()
        ]
    elif isinstance(raw_launch_arguments, list):
        launch_arguments = [str(value) for value in raw_launch_arguments]
    else:
        raise DeviceRegistryError("ROS 2 launch arguments must be a list or lines.")
    if provider_profile == "custom_launch" and (
        not launch_package or not launch_target
    ):
        raise DeviceRegistryError(
            "Custom ROS 2 launch requires a package and launch file."
        )
    parent_frame = str(values.get("parent_frame") or "base_link").strip()
    frame_id = str(values.get("frame_id") or f"{attachment_id}_link").strip()
    if not parent_frame or not frame_id:
        raise DeviceRegistryError("Parent frame and attachment frame are required.")
    if any(character.isspace() for character in parent_frame + frame_id):
        raise DeviceRegistryError("ROS 2 frame names cannot contain spaces.")
    mount = values.get("mount") if isinstance(values.get("mount"), dict) else {}
    translation = (
        mount.get("translation_m")
        if isinstance(mount.get("translation_m"), list)
        else []
    )
    rotation = (
        mount.get("rotation_rpy_rad")
        if isinstance(mount.get("rotation_rpy_rad"), list)
        else []
    )
    x_m = values.get("x_m", translation[0] if len(translation) > 0 else 0.0)
    y_m = values.get("y_m", translation[1] if len(translation) > 1 else 0.0)
    z_m = values.get("z_m", translation[2] if len(translation) > 2 else 0.0)
    roll_rad = values.get(
        "roll_rad",
        rotation[0] if len(rotation) > 0 else 0.0,
    )
    pitch_rad = values.get(
        "pitch_rad",
        rotation[1] if len(rotation) > 1 else 0.0,
    )
    yaw_rad = values.get(
        "yaw_rad",
        rotation[2] if len(rotation) > 2 else 0.0,
    )
    hardware_identity = (
        values.get("hardware_identity")
        if isinstance(values.get("hardware_identity"), dict)
        else {}
    )
    hardware_id = str(
        values.get("hardware_id") or hardware_identity.get("id") or ""
    ).strip()
    required = bool(values.get("required", True))
    enabled = bool(values.get("enabled", True))
    provider_record = {
        "package": provider_package,
        "component": provider_component,
        "adapter": provider_adapter,
        "profile": provider_profile,
    }
    interface = {
        "kind": "topic",
        "direction": "output",
        "topic": topic,
        "candidates": [topic],
        "message_type": message_type,
        "frame_id": frame_id,
    }
    interfaces = [interface]
    if camera_info_topic:
        interfaces.append({
            "kind": "topic",
            "role": "camera_info",
            "direction": "output",
            "topic": camera_info_topic,
            "candidates": [camera_info_topic],
            "message_type": "sensor_msgs/msg/CameraInfo",
            "frame_id": frame_id,
            "required": False,
        })
    if depth_topic:
        interfaces.append({
            "kind": "topic",
            "role": "depth",
            "direction": "output",
            "topic": depth_topic,
            "candidates": [depth_topic],
            "message_type": "sensor_msgs/msg/Image",
            "frame_id": frame_id,
            "required": attachment_type == "depth_camera",
        })
    if point_cloud_topic:
        interfaces.append({
            "kind": "topic",
            "role": "points",
            "direction": "output",
            "topic": point_cloud_topic,
            "candidates": [point_cloud_topic],
            "message_type": "sensor_msgs/msg/PointCloud2",
            "frame_id": frame_id,
            "required": False,
        })
    mount_record = {
        "translation_m": [
            _finite_attachment_number(x_m, "Mount X"),
            _finite_attachment_number(y_m, "Mount Y"),
            _finite_attachment_number(z_m, "Mount Z"),
        ],
        "rotation_rpy_rad": [
            _finite_attachment_number(roll_rad, "Mount roll"),
            _finite_attachment_number(pitch_rad, "Mount pitch"),
            _finite_attachment_number(yaw_rad, "Mount yaw"),
        ],
    }
    identity_record = {
        "id": hardware_id,
        "serial": str(hardware_identity.get("serial") or "").strip(),
        "vendor_id": str(hardware_identity.get("vendor_id") or "").strip(),
        "product_id": str(hardware_identity.get("product_id") or "").strip(),
        "path": str(hardware_identity.get("path") or "").strip(),
    }
    configuration = {
        "attachment_id": attachment_id,
        "attachment_type": attachment_type,
        "parent_frame": parent_frame,
        "frame_id": frame_id,
        "mount": mount_record,
        "ros2_interfaces": interfaces,
        "managed_service": {
            "id": attachment_id.replace("_", "-"),
            "profile": provider_profile,
            "launch_package": launch_package,
            "launch_target": launch_target,
            "launch_arguments": launch_arguments,
        },
    }
    binding = {
        "kind": "blacknode.robot-capability-binding",
        "schema_version": 1,
        "capability": capability,
        "provider": provider_record,
        "configuration": configuration,
        "hardware_identity": identity_record,
        "required": required,
    }
    attachment = {
        "kind": "blacknode.robot-attachment",
        "schema_version": 1,
        "id": attachment_id,
        "display_name": display_name,
        "attachment_type": attachment_type,
        "capability": capability,
        "provider": provider_record,
        "hardware_identity": identity_record,
        "parent_frame": parent_frame,
        "frame_id": frame_id,
        "mount": mount_record,
        "interfaces": interfaces,
        "service": {
            "id": attachment_id.replace("_", "-"),
            "profile": provider_profile,
            "launch_package": launch_package,
            "launch_target": launch_target,
            "launch_arguments": launch_arguments,
        },
        "required": required,
        "enabled": enabled,
        "binding": binding,
    }
    previous_check = values.get("last_check")
    if isinstance(previous_check, dict):
        attachment["last_check"] = dict(previous_check)
    return attachment


def _host_id(runtime_url: str) -> str:
    parsed = urllib.parse.urlsplit(normalize_base_url(runtime_url))
    label = _slug(str(parsed.hostname or "computer"))
    digest = hashlib.sha256(runtime_url.encode("utf-8")).hexdigest()[:8]
    return f"{label}-{digest}"


class HardwareDeviceClient:
    """Talk to one hardware service while keeping its bearer token server-side."""

    pairing_command = "./pair.sh --show"

    def __init__(self, base_url: str, token: str, *, timeout: float = 5.0) -> None:
        self.base_url = normalize_base_url(base_url)
        self.token = str(token or "").strip()
        self.timeout = timeout
        if not self.token:
            raise DeviceRegistryError("Pairing token is required.")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", authenticated=False)

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/status")

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/capabilities")

    def calibration(self) -> dict[str, Any]:
        return self._request("GET", "/calibration")

    def activate_calibration(
        self,
        profile: dict[str, Any],
        calibration: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/calibration",
            payload={"profile": profile, "calibration": calibration},
        )

    def deactivate_calibration(self) -> dict[str, Any]:
        return self._request("DELETE", "/calibration")

    def rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/rpc", payload=payload)

    def validate_pairing(self) -> dict[str, Any]:
        if urllib.parse.urlsplit(self.base_url).port == 8766:
            raise DeviceRegistryError(
                "Port 8766 is the shared Blacknode runtime, not a robot hardware "
                "service. Use the hardware URL printed by './pair.sh --all --show', "
                "such as port 8765 or 8767."
            )
        health = self.health()
        if health.get("service") != "blacknode-hardware":
            raise DeviceRegistryError(
                "The URL responded, but it is not a Blacknode Hardware service."
            )
        if not health.get("auth_required"):
            raise DeviceRegistryError(
                "Pairing authentication is not enabled on this device. "
                "Run ./pair.sh on the device and restart its service."
            )
        status = self.status()
        if not isinstance(status, dict) or not status.get("device_id"):
            raise DeviceRegistryError("The device returned an invalid status response.")
        return status

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        authenticated: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout if timeout is None else timeout,
            ) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise DeviceRegistryError(
                    f"Pairing token was rejected. Run {self.pairing_command} on the "
                    "device and paste the current token."
                ) from exc
            if exc.code == 404 and endpoint == "/calibration":
                raise DeviceRegistryError(
                    "This device service does not support calibration activation yet. "
                    "Update blacknode-hardware on the device, run "
                    "'./service.sh restart', then refresh the device in Blacknode."
                ) from exc
            detail = ""
            try:
                error_payload = json.loads(exc.read(_MAX_RESPONSE_BYTES).decode("utf-8"))
                if isinstance(error_payload, dict):
                    detail = str(
                        error_payload.get("error")
                        or error_payload.get("detail")
                        or ""
                    ).strip()
            except (OSError, AttributeError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise DeviceRegistryError(
                (
                    f"Device request to {endpoint} failed with HTTP {exc.code}: {detail}"
                    if detail
                    else f"Device request to {endpoint} failed with HTTP {exc.code}."
                )
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise DeviceRegistryError(
                f"Could not reach {self.base_url}: {reason}. "
                "Check the address, service, network, and firewall."
            ) from exc
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise DeviceRegistryError("Device response exceeded the 1 MB safety limit.")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeviceRegistryError(
                f"Device returned invalid JSON from {endpoint}."
            ) from exc
        if not isinstance(result, dict):
            raise DeviceRegistryError(
                f"Device returned an invalid response from {endpoint}."
            )
        return result


class RuntimeDeviceClient(HardwareDeviceClient):
    """Authenticated client for the deployment runtime on a paired device."""

    pairing_command = "./service.sh pairing"

    def manifest(self) -> dict[str, Any]:
        return self._request("GET", "/manifest")

    def list_deployments(self) -> dict[str, Any]:
        return self._request("GET", "/deployments")

    def stage_deployment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/deployments", payload=payload)

    def sync_packages(self, packages: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/packages/sync",
            payload={"packages": packages},
            timeout=600.0,
        )

    def get_deployment(self, deployment_id: str) -> dict[str, Any]:
        return self._request("GET", self._deployment_endpoint(deployment_id))

    def start_deployment(self, deployment_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._deployment_endpoint(deployment_id)}/start",
            payload={},
        )

    def stop_deployment(self, deployment_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._deployment_endpoint(deployment_id)}/stop",
            payload={},
        )

    def rollback_deployment(
        self,
        deployment_id: str,
        *,
        start: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._deployment_endpoint(deployment_id)}/rollback",
            payload={"start": start},
        )

    def deployment_logs(self, deployment_id: str, *, limit: int = 20000) -> dict[str, Any]:
        safe_limit = max(512, min(int(limit), 200000))
        return self._request(
            "GET",
            f"{self._deployment_endpoint(deployment_id)}/logs?limit={safe_limit}",
        )

    def deployment_telemetry(
        self,
        deployment_id: str,
        *,
        stream: str = "robot-state",
    ) -> dict[str, Any]:
        endpoint = self._deployment_endpoint(deployment_id)
        query = urllib.parse.urlencode({"stream": stream})
        return self._request("GET", f"{endpoint}/telemetry?{query}")

    def deployment_workflow(
        self,
        deployment_id: str,
        *,
        revision: str = "",
    ) -> dict[str, Any]:
        endpoint = f"{self._deployment_endpoint(deployment_id)}/workflow"
        if revision:
            endpoint += "?" + urllib.parse.urlencode({"revision": revision})
        return self._request("GET", endpoint)

    def set_deployment_motion_armed(
        self,
        deployment_id: str,
        *,
        armed: bool,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._deployment_endpoint(deployment_id)}/control",
            payload={"command": "arm" if armed else "disarm"},
            timeout=15.0,
        )

    def ros2_diagnostics(self) -> dict[str, Any]:
        return self._request("GET", "/diagnostics/ros2", timeout=90.0)

    def get_service(self, service_id: str) -> dict[str, Any]:
        return self._request("GET", self._service_endpoint(service_id), timeout=30.0)

    def start_service(
        self,
        service_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._service_endpoint(service_id)}/start",
            payload=payload,
            timeout=30.0,
        )

    def stop_service(self, service_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._service_endpoint(service_id)}/stop",
            payload={},
            timeout=30.0,
        )

    def delete_deployment(self, deployment_id: str) -> dict[str, Any]:
        return self._request("DELETE", self._deployment_endpoint(deployment_id))

    @staticmethod
    def _deployment_endpoint(deployment_id: str) -> str:
        clean_id = str(deployment_id or "").strip()
        if not clean_id:
            raise DeviceRegistryError("Deployment ID is required.")
        return f"/deployments/{urllib.parse.quote(clean_id, safe='')}"

    @staticmethod
    def _service_endpoint(service_id: str) -> str:
        clean_id = str(service_id or "").strip()
        if not clean_id:
            raise DeviceRegistryError("Managed service ID is required.")
        return f"/services/{urllib.parse.quote(clean_id, safe='')}"


class DeviceRegistry:
    """Persist paired devices locally and never expose their stored tokens."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            _hosts, records = self._load_payload()
            return [
                self._public(record)
                for record in sorted(
                    records.values(),
                    key=lambda item: (str(item.get("name", "")).lower(), item["id"]),
                )
            ]

    def get_public(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            _hosts, records = self._load_payload()
            record = records.get(device_id)
            return self._public(record) if record is not None else None

    def client(self, device_id: str) -> HardwareDeviceClient:
        with self._lock:
            _hosts, records = self._load_payload()
            record = records.get(device_id)
            if record is None:
                raise KeyError(device_id)
            return HardwareDeviceClient(record["base_url"], record["token"])

    def runtime_client(self, device_id: str) -> RuntimeDeviceClient:
        with self._lock:
            hosts, records = self._load_payload()
            record = records.get(device_id)
            if record is None:
                raise KeyError(device_id)
            host = hosts.get(str(record.get("host_id") or ""))
            runtime_url = (
                (host or {}).get("runtime_url")
                or record.get("runtime_url")
                or default_runtime_url(record["base_url"])
            )
            runtime_token = (
                (host or {}).get("runtime_token")
                or record.get("runtime_token")
                or record["token"]
            )
            return RuntimeDeviceClient(runtime_url, runtime_token)

    def list_hosts(self) -> list[dict[str, Any]]:
        with self._lock:
            hosts, records = self._load_payload()
            hosts, changed = self._materialize_hosts(hosts, records)
            if changed:
                self._save_payload(hosts, records)
            robots_by_host: dict[str, list[dict[str, Any]]] = {}
            for record in records.values():
                host_id = str(
                    record.get("host_id")
                    or _host_id(
                        str(
                            record.get("runtime_url")
                            or default_runtime_url(record["base_url"])
                        )
                    )
                )
                robots_by_host.setdefault(host_id, []).append(self._public(record))
            result = []
            for host in sorted(
                hosts.values(),
                key=lambda item: (str(item.get("name", "")).lower(), item["id"]),
            ):
                public = self._public_host(host)
                public["robots"] = sorted(
                    robots_by_host.get(host["id"], []),
                    key=lambda item: (str(item.get("name", "")).lower(), item["id"]),
                )
                result.append(public)
            return result

    def get_host_public(self, host_id: str) -> dict[str, Any] | None:
        with self._lock:
            hosts, records = self._load_payload()
            hosts, changed = self._materialize_hosts(hosts, records)
            if changed:
                self._save_payload(hosts, records)
            host = hosts.get(host_id)
            if host is None:
                return None
            public = self._public_host(host)
            public["robots"] = [
                self._public(record)
                for record in records.values()
                if str(record.get("host_id") or "") == host_id
            ]
            return public

    def host_client(self, host_id: str) -> RuntimeDeviceClient:
        with self._lock:
            hosts, records = self._load_payload()
            hosts, changed = self._materialize_hosts(hosts, records)
            if changed:
                self._save_payload(hosts, records)
            host = hosts.get(host_id)
            if host is None:
                raise KeyError(host_id)
            return RuntimeDeviceClient(host["runtime_url"], host["runtime_token"])

    def pair_host(
        self,
        *,
        name: str,
        runtime_url: str,
        runtime_token: str,
        manifest: dict[str, Any],
        managed_runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_url = normalize_base_url(runtime_url)
        clean_token = str(runtime_token or "").strip()
        if not clean_token:
            raise DeviceRegistryError("Runtime pairing token is required.")
        if (
            manifest.get("service") != "blacknode-runtime"
            or manifest.get("protocol_version") != 1
        ):
            raise DeviceRegistryError(
                "The URL responded, but it is not a compatible Blacknode runtime."
            )
        remote_id = str(manifest.get("device_id") or "").strip()
        with self._lock:
            hosts, records = self._load_payload()
            hosts, _changed = self._materialize_hosts(hosts, records)
            existing = next(
                (item for item in hosts.values() if item.get("runtime_url") == clean_url),
                None,
            )
            now = _iso_now()
            host_id = existing["id"] if existing else _host_id(clean_url)
            created_at = existing.get("created_at") if existing else now
            management = (
                {
                    key: value
                    for key, value in managed_runtime.items()
                    if key in {
                        "ssh_host",
                        "ssh_port",
                        "ssh_username",
                        "host_fingerprint",
                        "instance_id",
                        "runtime_port",
                        "service_name",
                        "install_root",
                        "runtime_dir",
                        "packages_dir",
                        "stack_mode",
                        "hardware_dir",
                        "hardware_port",
                        "hardware_service_name",
                        "hardware_state",
                        "hardware_configured",
                        "hardware_pid_file",
                        "hardware_token_file",
                        "hardware_log_path",
                        "hardware_owned_install",
                        "management_mode",
                        "config_path",
                        "pid_file",
                        "log_path",
                        "owned_install",
                    }
                }
                if managed_runtime
                else dict((existing or {}).get("managed_runtime") or {})
            )
            host = {
                "id": host_id,
                "name": str(name or "").strip() or remote_id or str(
                    urllib.parse.urlsplit(clean_url).hostname or "Computer"
                ),
                "runtime_url": clean_url,
                "runtime_token": clean_token,
                "runtime_token_fingerprint": token_fingerprint(clean_token),
                "remote_device_id": remote_id,
                "paused": False,
                "created_at": created_at or now,
                "updated_at": now,
            }
            if management:
                host["managed_runtime"] = management
            hosts[host_id] = host
            for record in records.values():
                record_runtime_url = str(
                    record.get("runtime_url")
                    or default_runtime_url(record["base_url"])
                )
                if record_runtime_url == clean_url:
                    record["host_id"] = host_id
                    record["runtime_url"] = clean_url
                    record["runtime_token"] = clean_token
                    record["runtime_token_fingerprint"] = token_fingerprint(clean_token)
                    record["runtime_token_explicit"] = True
                    record["updated_at"] = now
            self._save_payload(hosts, records)
            public = self._public_host(host)
            public["robots"] = [
                self._public(record)
                for record in records.values()
                if record.get("host_id") == host_id
            ]
            return public

    def set_host_paused(self, host_id: str, paused: bool) -> dict[str, Any]:
        with self._lock:
            hosts, records = self._load_payload()
            hosts, _changed = self._materialize_hosts(hosts, records)
            host = hosts.get(host_id)
            if host is None:
                raise KeyError(host_id)
            host["paused"] = bool(paused)
            host["updated_at"] = _iso_now()
            self._save_payload(hosts, records)
            public = self._public_host(host)
            public["robots"] = [
                self._public(record)
                for record in records.values()
                if str(record.get("host_id") or "") == host_id
            ]
            return public

    def set_host_remote_device_id(
        self,
        host_id: str,
        remote_device_id: str,
    ) -> dict[str, Any]:
        clean_remote_id = str(remote_device_id or "").strip()
        if not clean_remote_id:
            raise DeviceRegistryError("The runtime manifest has no stable device identity.")
        with self._lock:
            hosts, records = self._load_payload()
            hosts, _changed = self._materialize_hosts(hosts, records)
            host = hosts.get(host_id)
            if host is None:
                raise KeyError(host_id)
            current_remote_id = str(host.get("remote_device_id") or "").strip()
            if current_remote_id and current_remote_id != clean_remote_id:
                raise DeviceRegistryError(
                    "The paired runtime identity changed. Pair the runtime again "
                    "before enabling SSH management."
                )
            host["remote_device_id"] = clean_remote_id
            host["updated_at"] = _iso_now()
            self._save_payload(hosts, records)
            public = self._public_host(host)
            public["robots"] = [
                self._public(record)
                for record in records.values()
                if str(record.get("host_id") or "") == host_id
            ]
            return public

    def set_host_management(
        self,
        host_id: str,
        managed_runtime: dict[str, Any],
    ) -> dict[str, Any]:
        allowed_keys = {
            "ssh_host",
            "ssh_port",
            "ssh_username",
            "host_fingerprint",
            "instance_id",
            "runtime_port",
            "service_name",
            "install_root",
            "runtime_dir",
            "packages_dir",
            "stack_mode",
            "hardware_dir",
            "hardware_port",
            "hardware_service_name",
            "hardware_state",
            "hardware_configured",
            "hardware_pid_file",
            "hardware_token_file",
            "hardware_log_path",
            "hardware_owned_install",
            "management_mode",
            "config_path",
            "pid_file",
            "log_path",
            "owned_install",
        }
        management = {
            key: value
            for key, value in managed_runtime.items()
            if key in allowed_keys
        }
        required_keys = allowed_keys - {
            "stack_mode",
            "install_root",
            "packages_dir",
            "hardware_dir",
            "hardware_port",
            "hardware_service_name",
            "hardware_state",
            "hardware_configured",
            "hardware_pid_file",
            "hardware_token_file",
            "hardware_log_path",
            "hardware_owned_install",
            "management_mode",
            "config_path",
            "pid_file",
            "log_path",
            "owned_install",
        }
        if not required_keys.issubset(management):
            raise DeviceRegistryError(
                "The verified SSH runtime identity is incomplete."
            )
        with self._lock:
            hosts, records = self._load_payload()
            hosts, _changed = self._materialize_hosts(hosts, records)
            host = hosts.get(host_id)
            if host is None:
                raise KeyError(host_id)
            host["managed_runtime"] = management
            host["updated_at"] = _iso_now()
            self._save_payload(hosts, records)
            public = self._public_host(host)
            public["robots"] = [
                self._public(record)
                for record in records.values()
                if str(record.get("host_id") or "") == host_id
            ]
            return public

    def rename_host(self, host_id: str, name: str) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Device name is required.")
        with self._lock:
            hosts, records = self._load_payload()
            hosts, _changed = self._materialize_hosts(hosts, records)
            host = hosts.get(host_id)
            if host is None:
                raise KeyError(host_id)
            host["name"] = clean_name
            host["updated_at"] = _iso_now()
            self._save_payload(hosts, records)
            return self._public_host(host)

    def delete_host(self, host_id: str, *, cascade: bool = False) -> bool:
        with self._lock:
            hosts, records = self._load_payload()
            hosts, _changed = self._materialize_hosts(hosts, records)
            if host_id not in hosts:
                return False
            attached = [
                record
                for record in records.values()
                if str(record.get("host_id") or "") == host_id
            ]
            if attached and not cascade:
                raise DeviceRegistryError(
                    "Remove this device's robots before removing the device."
                )
            if cascade:
                attached_ids = {
                    str(record.get("id") or "")
                    for record in attached
                }
                records = {
                    record_id: record
                    for record_id, record in records.items()
                    if record_id not in attached_ids
                }
            del hosts[host_id]
            self._save_payload(hosts, records)
            return True

    def pair(
        self,
        *,
        name: str,
        base_url: str,
        token: str,
        runtime_token: str | None = None,
        runtime_url: str | None = None,
        host_id: str | None = None,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        clean_url = normalize_base_url(base_url)
        clean_token = str(token or "").strip()
        if not clean_token:
            raise DeviceRegistryError("Pairing token is required.")
        remote_device_id = str(status.get("device_id") or "").strip()
        if not remote_device_id:
            raise DeviceRegistryError("The device status has no device_id.")
        with self._lock:
            hosts, records = self._load_payload()
            hosts, _changed = self._materialize_hosts(hosts, records)
            selected_host = hosts.get(str(host_id or ""))
            if host_id and selected_host is None:
                raise DeviceRegistryError("Compute device was not found.")
            existing = next(
                (item for item in records.values() if item.get("base_url") == clean_url),
                None,
            )
            now = _iso_now()
            if existing is not None:
                device_id = existing["id"]
                created_at = existing.get("created_at") or now
            else:
                base_id = _slug(remote_device_id or clean_name)
                device_id = base_id
                suffix = 2
                while device_id in records:
                    device_id = f"{base_id}-{suffix}"
                    suffix += 1
                created_at = now
            clean_runtime_url = normalize_base_url(
                str(
                    (selected_host or {}).get("runtime_url")
                    or runtime_url
                    or (
                        existing.get("runtime_url")
                        if existing and existing.get("runtime_url")
                        else default_runtime_url(clean_url)
                    )
                )
            )
            resolved_host_id = str(
                (selected_host or {}).get("id")
                or host_id
                or (
                    existing.get("host_id")
                    if existing and existing.get("host_id")
                    else _host_id(clean_runtime_url)
                )
            )
            if resolved_host_id not in hosts:
                now_for_host = _iso_now()
                hosts[resolved_host_id] = {
                    "id": resolved_host_id,
                    "name": str(
                        urllib.parse.urlsplit(clean_runtime_url).hostname or "Computer"
                    ),
                    "runtime_url": clean_runtime_url,
                    "runtime_token": "",
                    "runtime_token_fingerprint": "",
                    "remote_device_id": "",
                    "created_at": now_for_host,
                    "updated_at": now_for_host,
                }
            clean_runtime_token = str(
                (selected_host or {}).get("runtime_token")
                or runtime_token
                or ""
            ).strip()
            runtime_token_explicit = bool(
                (selected_host or {}).get("runtime_token")
                or clean_runtime_token
            )
            if not clean_runtime_token and existing and existing.get("runtime_token_explicit"):
                clean_runtime_token = (
                    str(existing.get("runtime_token") or "").strip()
                )
                runtime_token_explicit = True
            if not clean_runtime_token:
                runtime_peer = next(
                    (
                        item
                        for item in records.values()
                        if (
                            item.get("runtime_url")
                            or default_runtime_url(item["base_url"])
                        ) == clean_runtime_url
                        and item.get("runtime_token_explicit")
                        and str(item.get("runtime_token") or "").strip()
                    ),
                    None,
                )
                if runtime_peer is not None:
                    clean_runtime_token = str(runtime_peer["runtime_token"]).strip()
                    runtime_token_explicit = True
            clean_runtime_token = clean_runtime_token or clean_token
            host = hosts[resolved_host_id]
            if not str(host.get("runtime_token") or "").strip() or runtime_token_explicit:
                host["runtime_token"] = clean_runtime_token
                host["runtime_token_fingerprint"] = token_fingerprint(clean_runtime_token)
                host["updated_at"] = now
            record = {
                "id": device_id,
                "name": clean_name or remote_device_id,
                "base_url": clean_url,
                "host_id": resolved_host_id,
                "runtime_url": clean_runtime_url,
                "token": clean_token,
                "token_fingerprint": token_fingerprint(clean_token),
                "runtime_token": clean_runtime_token,
                "runtime_token_fingerprint": token_fingerprint(clean_runtime_token),
                "runtime_token_explicit": runtime_token_explicit,
                "remote_device_id": remote_device_id,
                "software_version": (
                    str(status.get("software_version") or "").strip()
                    or str((existing or {}).get("software_version") or "").strip()
                ),
                "paused": False,
                "attachments": [
                    dict(item)
                    for item in ((existing or {}).get("attachments") or [])
                    if isinstance(item, dict)
                ],
                "created_at": created_at,
                "updated_at": now,
            }
            records[device_id] = record
            if runtime_token_explicit:
                for other_id, other in records.items():
                    if (
                        other_id != device_id
                        and (
                            other.get("runtime_url")
                            or default_runtime_url(other["base_url"])
                        ) == record["runtime_url"]
                    ):
                        other["host_id"] = resolved_host_id
                        other["runtime_token"] = clean_runtime_token
                        other["runtime_token_fingerprint"] = token_fingerprint(
                            clean_runtime_token
                        )
                        other["runtime_token_explicit"] = True
                        other["updated_at"] = now
            self._save_payload(hosts, records)
            return self._public(record)

    def remember_device_software_version(
        self,
        device_id: str,
        software_version: str,
    ) -> None:
        clean_version = str(software_version or "").strip()
        if not clean_version or clean_version.casefold() == "unknown":
            return
        with self._lock:
            hosts, records = self._load_payload()
            record = records.get(device_id)
            if record is None:
                raise KeyError(device_id)
            if str(record.get("software_version") or "") == clean_version:
                return
            record["software_version"] = clean_version
            record["updated_at"] = _iso_now()
            self._save_payload(hosts, records)

    def delete(self, device_id: str) -> bool:
        with self._lock:
            hosts, records = self._load_payload()
            if device_id not in records:
                return False
            del records[device_id]
            self._save_payload(hosts, records)
            return True

    def rename(self, device_id: str, name: str) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Device name is required.")
        with self._lock:
            hosts, records = self._load_payload()
            record = records.get(device_id)
            if record is None:
                raise KeyError(device_id)
            record["name"] = clean_name
            record["updated_at"] = _iso_now()
            records[device_id] = record
            self._save_payload(hosts, records)
            return self._public(record)

    def set_device_paused(self, device_id: str, paused: bool) -> dict[str, Any]:
        with self._lock:
            hosts, records = self._load_payload()
            record = records.get(device_id)
            if record is None:
                raise KeyError(device_id)
            record["paused"] = bool(paused)
            record["updated_at"] = _iso_now()
            self._save_payload(hosts, records)
            return self._public(record)

    def save_attachment(
        self,
        device_id: str,
        values: dict[str, Any],
        *,
        attachment_id: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._lock:
            hosts, records = self._load_payload()
            record = records.get(device_id)
            if record is None:
                raise KeyError(device_id)
            clean_existing_id = (
                _attachment_identifier(attachment_id)
                if attachment_id
                else ""
            )
            attachment = _normalize_attachment(
                values,
                existing_id=clean_existing_id,
            )
            attachments = [
                dict(item)
                for item in (record.get("attachments") or [])
                if isinstance(item, dict) and str(item.get("id") or "")
            ]
            index = next(
                (
                    index
                    for index, item in enumerate(attachments)
                    if str(item.get("id") or "") == attachment["id"]
                ),
                None,
            )
            if clean_existing_id:
                if index is None:
                    raise KeyError(clean_existing_id)
                attachments[index] = attachment
            elif index is not None:
                raise DeviceRegistryError(
                    f"Attachment '{attachment['id']}' already exists."
                )
            else:
                attachments.append(attachment)
            attachments.sort(
                key=lambda item: (
                    str(item.get("display_name") or "").casefold(),
                    str(item.get("id") or ""),
                )
            )
            record["attachments"] = attachments
            record["updated_at"] = _iso_now()
            records[device_id] = record
            self._save_payload(hosts, records)
            return self._public(record), attachment

    def delete_attachment(
        self,
        device_id: str,
        attachment_id: str,
    ) -> dict[str, Any]:
        clean_id = _attachment_identifier(attachment_id)
        with self._lock:
            hosts, records = self._load_payload()
            record = records.get(device_id)
            if record is None:
                raise KeyError(device_id)
            attachments = [
                dict(item)
                for item in (record.get("attachments") or [])
                if isinstance(item, dict) and str(item.get("id") or "")
            ]
            filtered = [
                item
                for item in attachments
                if str(item.get("id") or "") != clean_id
            ]
            if len(filtered) == len(attachments):
                raise KeyError(clean_id)
            record["attachments"] = filtered
            record["updated_at"] = _iso_now()
            records[device_id] = record
            self._save_payload(hosts, records)
            return self._public(record)

    def remember_attachment_check(
        self,
        device_id: str,
        attachment_id: str,
        check: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        clean_id = _attachment_identifier(attachment_id)
        with self._lock:
            hosts, records = self._load_payload()
            record = records.get(device_id)
            if record is None:
                raise KeyError(device_id)
            attachments = [
                dict(item)
                for item in (record.get("attachments") or [])
                if isinstance(item, dict) and str(item.get("id") or "")
            ]
            attachment = next(
                (
                    item
                    for item in attachments
                    if str(item.get("id") or "") == clean_id
                ),
                None,
            )
            if attachment is None:
                raise KeyError(clean_id)
            attachment["last_check"] = dict(check)
            record["attachments"] = attachments
            record["updated_at"] = _iso_now()
            records[device_id] = record
            self._save_payload(hosts, records)
            return self._public(record), attachment

    def _load_payload(
        self,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}, {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeviceRegistryError(
                f"Could not read local device registry at {self.path}: {exc}"
            ) from exc
        devices = payload.get("devices", {}) if isinstance(payload, dict) else {}
        hosts = payload.get("hosts", {}) if isinstance(payload, dict) else {}
        if not isinstance(devices, dict) or not isinstance(hosts, dict):
            raise DeviceRegistryError("Local device registry has an invalid format.")
        return ({
            str(host_id): dict(record)
            for host_id, record in hosts.items()
            if isinstance(record, dict)
        }, {
            str(device_id): dict(record)
            for device_id, record in devices.items()
            if isinstance(record, dict)
        })

    def _load(self) -> dict[str, dict[str, Any]]:
        _hosts, devices = self._load_payload()
        return devices

    def _save_payload(
        self,
        hosts: dict[str, dict[str, Any]],
        records: dict[str, dict[str, Any]],
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        payload = {"schema_version": 2, "hosts": hosts, "devices": records}
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            if temporary.exists():
                temporary.unlink()

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        hosts, _existing = self._load_payload()
        self._save_payload(hosts, records)

    @staticmethod
    def _materialize_hosts(
        hosts: dict[str, dict[str, Any]],
        records: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], bool]:
        changed = False
        for record in records.values():
            runtime_url = normalize_base_url(
                str(
                    record.get("runtime_url")
                    or default_runtime_url(record["base_url"])
                )
            )
            host_id = str(record.get("host_id") or _host_id(runtime_url))
            host = hosts.get(host_id)
            if host is None:
                now = str(record.get("created_at") or _iso_now())
                hosts[host_id] = {
                    "id": host_id,
                    "name": str(
                        urllib.parse.urlsplit(runtime_url).hostname or "Computer"
                    ),
                    "runtime_url": runtime_url,
                    "runtime_token": str(
                        record.get("runtime_token") or record.get("token") or ""
                    ),
                    "runtime_token_fingerprint": str(
                        record.get("runtime_token_fingerprint")
                        or record.get("token_fingerprint")
                        or ""
                    ),
                    "remote_device_id": "",
                    "created_at": now,
                    "updated_at": str(record.get("updated_at") or now),
                }
                changed = True
            if record.get("host_id") != host_id:
                record["host_id"] = host_id
                changed = True
            if record.get("runtime_url") != runtime_url:
                record["runtime_url"] = runtime_url
                changed = True
        return hosts, changed

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        public = {
            key: value
            for key, value in record.items()
            if key not in {"token", "runtime_token", "runtime_token_explicit"}
        }
        public.setdefault("runtime_url", default_runtime_url(str(record["base_url"])))
        public.setdefault(
            "runtime_token_fingerprint",
            str(record.get("token_fingerprint") or ""),
        )
        public["runtime_token_configured"] = bool(
            record.get("runtime_token_explicit")
        )
        return public

    @staticmethod
    def _public_host(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in record.items()
            if key != "runtime_token"
        }
