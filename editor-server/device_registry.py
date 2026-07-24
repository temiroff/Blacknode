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


class HardwareDeviceClient:
    """Talk to one hardware service while keeping its bearer token server-side."""

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

    def rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/rpc", payload=payload)

    def validate_pairing(self) -> dict[str, Any]:
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
                    "Pairing token was rejected. Run ./pair.sh --show on the device "
                    "and paste the current token."
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
            records = self._load()
            return [
                self._public(record)
                for record in sorted(
                    records.values(),
                    key=lambda item: (str(item.get("name", "")).lower(), item["id"]),
                )
            ]

    def get_public(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._load().get(device_id)
            return self._public(record) if record is not None else None

    def client(self, device_id: str) -> HardwareDeviceClient:
        with self._lock:
            record = self._load().get(device_id)
            if record is None:
                raise KeyError(device_id)
            return HardwareDeviceClient(record["base_url"], record["token"])

    def runtime_client(self, device_id: str) -> RuntimeDeviceClient:
        with self._lock:
            record = self._load().get(device_id)
            if record is None:
                raise KeyError(device_id)
            runtime_url = record.get("runtime_url") or default_runtime_url(record["base_url"])
            return RuntimeDeviceClient(runtime_url, record["token"])

    def pair(
        self,
        *,
        name: str,
        base_url: str,
        token: str,
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
            records = self._load()
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
            record = {
                "id": device_id,
                "name": clean_name or remote_device_id,
                "base_url": clean_url,
                "runtime_url": (
                    existing.get("runtime_url")
                    if existing and existing.get("runtime_url")
                    else default_runtime_url(clean_url)
                ),
                "token": clean_token,
                "token_fingerprint": token_fingerprint(clean_token),
                "remote_device_id": remote_device_id,
                "created_at": created_at,
                "updated_at": now,
            }
            records[device_id] = record
            self._save(records)
            return self._public(record)

    def delete(self, device_id: str) -> bool:
        with self._lock:
            records = self._load()
            if device_id not in records:
                return False
            del records[device_id]
            self._save(records)
            return True

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeviceRegistryError(
                f"Could not read local device registry at {self.path}: {exc}"
            ) from exc
        devices = payload.get("devices", {}) if isinstance(payload, dict) else {}
        if not isinstance(devices, dict):
            raise DeviceRegistryError("Local device registry has an invalid format.")
        return {
            str(device_id): dict(record)
            for device_id, record in devices.items()
            if isinstance(record, dict)
        }

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        payload = {"schema_version": 1, "devices": records}
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

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        public = {
            key: value
            for key, value in record.items()
            if key != "token"
        }
        public.setdefault("runtime_url", default_runtime_url(str(record["base_url"])))
        return public
