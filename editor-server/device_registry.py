"""Local registry and authenticated client for Blacknode hardware devices."""

from __future__ import annotations

import hashlib
import json
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

    def delete_deployment(self, deployment_id: str) -> dict[str, Any]:
        return self._request("DELETE", self._deployment_endpoint(deployment_id))

    @staticmethod
    def _deployment_endpoint(deployment_id: str) -> str:
        clean_id = str(deployment_id or "").strip()
        if not clean_id:
            raise DeviceRegistryError("Deployment ID is required.")
        return f"/deployments/{urllib.parse.quote(clean_id, safe='')}"


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
                        "runtime_dir",
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
                "paused": False,
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
