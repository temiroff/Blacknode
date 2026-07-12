from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


ALLOWED_PORT_TYPES = frozenset({"Text", "Int", "Float", "Bool", "Color", "List", "Dict", "Any"})
MANIFEST_SCHEMA_VERSION = 1

NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
PORT_RE = re.compile(r"^[a-z_][a-z0-9_]*:[A-Z][a-zA-Z]+$")
CATEGORY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{1,31}$")

REQUIRED_MANIFEST_KEYS = frozenset({
    "name",
    "description",
    "inputs",
    "outputs",
    "permissions",
    "created_at",
    "created_by",
    "schema_version",
})
OPTIONAL_MANIFEST_KEYS = frozenset({"category"})
MANIFEST_KEYS = REQUIRED_MANIFEST_KEYS | OPTIONAL_MANIFEST_KEYS
PERMISSION_KEYS = frozenset({"network"})


class ManifestValidationError(ValueError):
    """Raised when a learned-node manifest does not match the v1 schema."""


@dataclass(frozen=True)
class LearnedNodeManifest:
    name: str
    description: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    permissions: dict[str, bool]
    created_at: str
    created_by: str
    schema_version: int = MANIFEST_SCHEMA_VERSION
    category: str = "Learned"

    @property
    def input_names(self) -> tuple[str, ...]:
        return tuple(_split_port(port)[0] for port in self.inputs)

    @property
    def output_names(self) -> tuple[str, ...]:
        return tuple(_split_port(port)[0] for port in self.outputs)

    @property
    def input_types(self) -> dict[str, str]:
        return dict(_split_port(port) for port in self.inputs)

    @property
    def output_types(self) -> dict[str, str]:
        return dict(_split_port(port) for port in self.outputs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "permissions": dict(self.permissions),
            "created_at": self.created_at,
            "created_by": self.created_by,
            "schema_version": self.schema_version,
        }


def load_manifest(path: str | Path) -> LearnedNodeManifest:
    manifest_path = Path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestValidationError(f"{manifest_path}: invalid JSON: {exc}") from exc
    except OSError as exc:
        raise ManifestValidationError(f"{manifest_path}: could not read manifest: {exc}") from exc
    return validate_manifest(raw, path=manifest_path)


def validate_manifest(data: Mapping[str, Any], *, path: str | Path = "manifest.json") -> LearnedNodeManifest:
    if not isinstance(data, Mapping):
        raise ManifestValidationError(f"{path}: manifest must be a JSON object")

    keys = set(data)
    missing = sorted(REQUIRED_MANIFEST_KEYS - keys)
    extra = sorted(keys - MANIFEST_KEYS)
    if missing:
        raise ManifestValidationError(f"{path}: missing required keys: {missing}")
    if extra:
        raise ManifestValidationError(f"{path}: unknown keys are not allowed: {extra}")

    name = _required_str(data["name"], "name", path)
    if not (3 <= len(name) <= 40 and NAME_RE.match(name)):
        raise ManifestValidationError(f"{path}: name must be a 3-40 character PascalCase identifier")

    description = _required_str(data["description"], "description", path)
    if not (10 <= len(description) <= 200):
        raise ManifestValidationError(f"{path}: description must be 10-200 characters")

    category = validate_category_name(data.get("category", "Learned"), path=path)
    inputs = _validate_ports(data["inputs"], "inputs", path, allow_empty=True)
    outputs = _validate_ports(data["outputs"], "outputs", path, allow_empty=False)
    permissions = _validate_permissions(data["permissions"], path)
    created_at = _required_str(data["created_at"], "created_at", path)
    _validate_created_at(created_at, path)
    created_by = _required_str(data["created_by"], "created_by", path)

    schema_version = data["schema_version"]
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise ManifestValidationError(f"{path}: schema_version must be {MANIFEST_SCHEMA_VERSION}")

    return LearnedNodeManifest(
        name=name,
        description=description,
        inputs=tuple(inputs),
        outputs=tuple(outputs),
        permissions=permissions,
        created_at=created_at,
        created_by=created_by,
        schema_version=schema_version,
        category=category,
    )


def validate_category_name(value: Any, *, path: str | Path = "manifest.json") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{path}: category must be a non-empty string")
    category = value.strip()
    if not CATEGORY_RE.match(category):
        raise ManifestValidationError(
            f"{path}: category must be 2-32 characters and contain only letters, numbers, spaces, '_' or '-'"
        )
    return category


def _validate_ports(value: Any, field: str, path: str | Path, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        raise ManifestValidationError(f"{path}: {field} must be a list")
    if not value and not allow_empty:
        raise ManifestValidationError(f"{path}: {field} must declare at least one port")

    ports: list[str] = []
    names: set[str] = set()
    for index, port in enumerate(value):
        if not isinstance(port, str) or not PORT_RE.match(port):
            raise ManifestValidationError(
                f"{path}: {field}[{index}] must be in 'name:Type' format"
            )
        port_name, port_type = _split_port(port)
        if port_name in names:
            raise ManifestValidationError(f"{path}: duplicate port name '{port_name}' in {field}")
        if port_type not in ALLOWED_PORT_TYPES:
            raise ManifestValidationError(
                f"{path}: unsupported port type '{port_type}' in {field}[{index}]"
            )
        names.add(port_name)
        ports.append(port)
    return ports


def _validate_permissions(value: Any, path: str | Path) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        raise ManifestValidationError(f"{path}: permissions must be an object")
    keys = set(value)
    missing = sorted(PERMISSION_KEYS - keys)
    extra = sorted(keys - PERMISSION_KEYS)
    if missing:
        raise ManifestValidationError(f"{path}: permissions missing required keys: {missing}")
    if extra:
        raise ManifestValidationError(f"{path}: unknown permissions are not allowed: {extra}")
    network = value["network"]
    if not isinstance(network, bool):
        raise ManifestValidationError(f"{path}: permissions.network must be a boolean")
    return {"network": network}


def _validate_created_at(value: str, path: str | Path) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestValidationError(f"{path}: created_at must be an ISO timestamp") from exc


def _required_str(value: Any, field: str, path: str | Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{path}: {field} must be a non-empty string")
    return value


def _split_port(port: str) -> tuple[str, str]:
    name, type_name = port.split(":", 1)
    return name, type_name
