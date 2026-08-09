from __future__ import annotations

import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

_CLOUD_JOB_PATH = re.compile(r"^/cloud/jobs/[^/]+$")
_CLOUD_JOB_LOGS_PATH = re.compile(r"^/cloud/jobs/[^/]+/logs$")
_CLOUD_JOB_ARTIFACTS_PATH = re.compile(r"^/cloud/jobs/[^/]+/artifacts$")
_CLOUD_ARTIFACT_DOWNLOAD_PATH = re.compile(
    r"^/cloud/jobs/[^/]+/artifacts/[^/]+/download$"
)


@dataclass
class _Workspace(Generic[T]):
    value: T
    touched_at: float


class HostedWorkspaceStore(Generic[T]):
    """Bounded, process-local workspaces for the public Editor preview."""

    def __init__(
        self,
        factory: Callable[[], T],
        *,
        max_workspaces: int = 256,
        ttl_seconds: int = 86_400,
    ) -> None:
        self._factory = factory
        self._max_workspaces = max_workspaces
        self._ttl_seconds = ttl_seconds
        self._items: dict[str, _Workspace[T]] = {}
        self._lock = threading.Lock()

    def get_or_create(self, token: str | None) -> tuple[str, T, bool]:
        now = time.time()
        with self._lock:
            self._reap(now)
            if token and token in self._items:
                item = self._items[token]
                item.touched_at = now
                return token, item.value, False
            while len(self._items) >= self._max_workspaces:
                oldest = min(self._items, key=lambda key: self._items[key].touched_at)
                self._items.pop(oldest, None)
            workspace_token = secrets.token_urlsafe(32)
            value = self._factory()
            self._items[workspace_token] = _Workspace(value=value, touched_at=now)
            return workspace_token, value, True

    def _reap(self, now: float) -> None:
        expired = [
            token
            for token, item in self._items.items()
            if now - item.touched_at > self._ttl_seconds
        ]
        for token in expired:
            self._items.pop(token, None)


def route_allowed(method: str, path: str, *, query: str = "") -> bool:
    method = method.upper()
    if method == "GET" and path in {"/healthz", "/readyz", "/hosted/status"}:
        return True
    if method == "GET" and path in {"/node-types", "/node-defs", "/graph", "/validate"}:
        return True
    if path == "/graph" and method == "POST":
        return True
    if path in {"/graph/requirements", "/graph/refresh-node-schemas"} and method in {
        "PATCH",
        "POST",
    }:
        return True
    if path.startswith("/nodes/"):
        if path.endswith(("/control", "/depth-frame")):
            return False
        return method in {"GET", "PATCH", "DELETE"}
    if path == "/nodes" and method == "POST":
        return True
    if path == "/edges" and method in {"POST", "DELETE"}:
        return True
    if path == "/subnets" and method == "POST":
        return True
    if path == "/cloud/status" and method == "GET":
        return True
    if path == "/cloud/account" and method == "PATCH":
        return True
    if path == "/cloud/newsletter/subscribe" and method == "POST":
        return True
    if path in {
        "/cloud/auth/register",
        "/cloud/auth/login",
        "/cloud/auth/verify-email",
        "/cloud/auth/logout",
    } and method == "POST":
        return True
    if path == "/cloud/credits/history" and method == "GET":
        return True
    if path == "/cloud/jobs" and method == "POST":
        return True
    if _CLOUD_JOB_PATH.fullmatch(path):
        return method in {"GET", "DELETE"}
    if _CLOUD_JOB_LOGS_PATH.fullmatch(path):
        return method == "GET"
    if _CLOUD_JOB_ARTIFACTS_PATH.fullmatch(path):
        return method == "GET"
    if _CLOUD_ARTIFACT_DOWNLOAD_PATH.fullmatch(path):
        return method == "GET"
    if path == "/templates" and method == "GET":
        return True
    if path.startswith("/templates/"):
        return method == "GET" or (method == "POST" and path.endswith("/load"))
    if path == "/packages" and method == "GET":
        return "git=true" not in query.lower()
    if path == "/packages/index" and method == "GET":
        return True
    if path.startswith("/packages/") and method == "GET" and path.endswith("/dependencies"):
        return True
    return path == "/reset" and method == "POST"
