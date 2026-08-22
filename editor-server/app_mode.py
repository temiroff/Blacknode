from __future__ import annotations

import re


_ACTIVATE_RE = re.compile(r"^/app-deployment/apps/[a-z][a-z0-9_-]{0,63}/activate$")
_NODE_PARAMS_RE = re.compile(r"^/nodes/[^/]+/params$")
_NODE_CONTROL_RE = re.compile(r"^/nodes/[^/]+/control$")
_NODE_DEPTH_RE = re.compile(r"^/nodes/[^/]+/depth-frame$")


def route_allowed(method: str, path: str) -> bool:
    method = method.upper()
    if method == "GET" and path in {
        "/healthz",
        "/readyz",
        "/hosted/status",
        "/app-deployment",
        "/graph",
        "/runtime/status",
        "/runtime/spatial-viewers",
    }:
        return True
    if method == "GET" and _NODE_DEPTH_RE.fullmatch(path):
        return True
    if method == "POST" and _ACTIVATE_RE.fullmatch(path):
        return True
    if method == "PATCH" and _NODE_PARAMS_RE.fullmatch(path):
        return True
    if method == "POST" and _NODE_CONTROL_RE.fullmatch(path):
        return True
    if method == "POST" and path in {
        "/cook",
        "/cook-stream",
        "/cook/stop",
        "/runtime/stop",
    }:
        return True
    return False
