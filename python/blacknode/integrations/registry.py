"""Registry of integration drivers (Slack, …).

A *driver* turns an outside event source into one-cook-per-message around the
graph engine. They self-register here at import time, the same way nodes use
``_NODE_REGISTRY`` and exporters use their registry, so the CLI can list what is
registered and report whether each one is *activated* — its optional
dependencies installed and its required environment variables present.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any, Callable

from blacknode.providers.keys import secret

# A driver's transport entrypoint: run(runtime) starts the listener and blocks.
RunFn = Callable[[Any], None]

_DRIVER_REGISTRY: dict[str, "DriverSpec"] = {}


@dataclass(frozen=True)
class DriverSpec:
    name: str
    description: str
    run: RunFn
    required_extra: str                      # pip extra, e.g. "slack" -> blacknode[slack]
    required_packages: tuple[str, ...]       # import names that the extra installs
    required_env: tuple[str, ...]            # env vars the driver needs to run


def register_driver(spec: DriverSpec) -> None:
    _DRIVER_REGISTRY[spec.name] = spec


def get_driver(name: str) -> DriverSpec | None:
    return _DRIVER_REGISTRY.get(name)


def list_drivers() -> list[DriverSpec]:
    return [_DRIVER_REGISTRY[name] for name in sorted(_DRIVER_REGISTRY)]


def packages_installed(spec: DriverSpec) -> bool:
    return all(importlib.util.find_spec(pkg) is not None for pkg in spec.required_packages)


def missing_env(spec: DriverSpec) -> list[str]:
    """Required secrets not resolvable from the environment or the key store."""
    return [name for name in spec.required_env if not secret(name)]


def driver_status(spec: DriverSpec) -> dict[str, Any]:
    """Structured readiness for one driver: ``ready`` / ``needs env`` / ``needs install``."""
    installed = packages_installed(spec)
    missing = missing_env(spec)
    if not installed:
        status = "needs install"
    elif missing:
        status = "needs env"
    else:
        status = "ready"
    return {
        "name": spec.name,
        "description": spec.description,
        "status": status,
        "extra": f"blacknode[{spec.required_extra}]",
        "packages_installed": installed,
        "required_packages": list(spec.required_packages),
        "env": {name: bool(secret(name)) for name in spec.required_env},
        "missing_env": missing,
    }
