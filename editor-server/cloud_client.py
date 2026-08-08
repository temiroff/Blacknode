"""Thin public client for the private Blacknode Cloud HTTP API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CloudConfiguration:
    base_url: str
    api_key: str

    @property
    def configured(self) -> bool:
        return self.base_url.startswith(("http://", "https://")) and len(self.api_key) >= 24


class CloudClientError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def configuration() -> CloudConfiguration:
    return CloudConfiguration(
        base_url=os.environ.get("BLACKNODE_CLOUD_URL", "").strip().rstrip("/"),
        api_key=os.environ.get("BLACKNODE_CLOUD_API_KEY", "").strip(),
    )


def json_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    response = _open(method, path, payload, timeout=timeout)
    with response:
        try:
            value = json.loads(response.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CloudClientError(502, "Blacknode Cloud returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise CloudClientError(502, "Blacknode Cloud returned an invalid response.")
    return value


def download(path: str, *, timeout: float = 30.0) -> tuple[Iterator[bytes], str, str]:
    response = _open("GET", path, timeout=timeout)
    media_type = response.headers.get_content_type() or "application/octet-stream"
    disposition = response.headers.get("Content-Disposition", "")

    def chunks() -> Iterator[bytes]:
        with response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return chunks(), media_type, disposition


def _open(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float,
):
    config = configuration()
    if not config.configured:
        raise CloudClientError(
            503,
            "Configure BLACKNODE_CLOUD_URL and BLACKNODE_CLOUD_API_KEY on the editor server.",
        )
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {config.api_key}",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{config.base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        message = _error_message(exc)
        exc.close()
        raise CloudClientError(exc.code, message) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise CloudClientError(502, "Blacknode Cloud is unreachable.") from exc


def _error_message(response: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "Blacknode Cloud rejected the request."
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail[:500]
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return detail["message"][:500]
    return "Blacknode Cloud rejected the request."
