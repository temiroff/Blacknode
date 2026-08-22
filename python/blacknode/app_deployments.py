from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .workflow import load_workflow, validate_workflow


APP_DEPLOYMENT_KIND = "blacknode.app-deployment"
APP_DEPLOYMENT_SCHEMA_VERSION = 1
_ID_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_SECRET_KEY_RE = re.compile(r"(?:api[_-]?key|token|secret|password|credential)$", re.I)


class AppDeploymentError(ValueError):
    pass


def _clean_id(value: object, *, label: str) -> str:
    clean = str(value or "").strip().lower().replace(" ", "-")
    if not _ID_RE.fullmatch(clean):
        raise AppDeploymentError(
            f"{label} must start with a letter and contain only lowercase letters, numbers, '_' or '-'."
        )
    return clean


def _operator_view(workflow: Mapping[str, Any], *, source: str) -> Mapping[str, Any]:
    metadata = workflow.get("metadata")
    view = metadata.get("operator_view") if isinstance(metadata, Mapping) else None
    if not isinstance(view, Mapping):
        raise AppDeploymentError(f"{source} does not declare metadata.operator_view.")
    if view.get("schema_version") != 1:
        raise AppDeploymentError(f"{source} operator_view.schema_version must be 1.")
    if not str(view.get("title") or "").strip():
        raise AppDeploymentError(f"{source} operator_view.title is required.")
    if not isinstance(view.get("sections"), list) or not view["sections"]:
        raise AppDeploymentError(f"{source} operator_view.sections must contain at least one section.")
    return view


def _secret_paths(value: object, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if _SECRET_KEY_RE.search(str(key)) and item not in (None, "", [], {}):
                found.append(item_path)
            found.extend(_secret_paths(item, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_secret_paths(item, f"{path}[{index}]"))
    return found


def _required_packages(workflow: Mapping[str, Any]) -> list[str]:
    metadata = workflow.get("metadata")
    values = metadata.get("required_packages") if isinstance(metadata, Mapping) else None
    if not isinstance(values, list):
        return []
    return sorted({str(value).strip() for value in values if str(value).strip()})


def build_app_deployment(
    workflows: Iterable[tuple[str, Mapping[str, Any]]],
    *,
    deployment_id: str,
    name: str | None = None,
    start_app: str | None = None,
) -> dict[str, Any]:
    clean_deployment_id = _clean_id(deployment_id, label="Deployment id")
    apps: list[dict[str, Any]] = []
    seen: set[str] = set()
    package_names: set[str] = set()

    for source, raw_workflow in workflows:
        workflow = copy.deepcopy(dict(raw_workflow))
        report = validate_workflow(workflow)
        if not report.ok:
            messages = "; ".join(issue.message for issue in report.errors)
            raise AppDeploymentError(f"{source} is not a valid workflow: {messages}")
        view = _operator_view(workflow, source=source)
        app_id = _clean_id(view.get("id") or Path(source).stem, label=f"App id for {source}")
        if app_id in seen:
            raise AppDeploymentError(f"Duplicate app id '{app_id}'.")
        secret_paths = _secret_paths(workflow)
        if secret_paths:
            raise AppDeploymentError(
                f"{source} contains persisted secret values at {', '.join(secret_paths[:5])}. "
                "Configure credentials on the deployment host instead."
            )
        seen.add(app_id)
        required_packages = _required_packages(workflow)
        package_names.update(required_packages)
        apps.append({
            "id": app_id,
            "name": str(view["title"]).strip(),
            "description": str(view.get("description") or "").strip(),
            "accent": str(view.get("accent") or "").strip(),
            "required_packages": required_packages,
            "workflow": workflow,
        })

    if not apps:
        raise AppDeploymentError("An App deployment needs at least one workflow.")
    selected_start = _clean_id(start_app or apps[0]["id"], label="Start app")
    if selected_start not in seen:
        raise AppDeploymentError(f"Start app '{selected_start}' is not included in this deployment.")

    return {
        "kind": APP_DEPLOYMENT_KIND,
        "schema_version": APP_DEPLOYMENT_SCHEMA_VERSION,
        "id": clean_deployment_id,
        "name": str(name or apps[0]["name"]).strip() or apps[0]["name"],
        "start_app": selected_start,
        "access": {"role": "operator", "graph_editing": False},
        "required_packages": sorted(package_names),
        "apps": apps,
    }


def validate_app_deployment(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AppDeploymentError("App deployment manifest must contain a JSON object.")
    if value.get("kind") != APP_DEPLOYMENT_KIND:
        raise AppDeploymentError(f"App deployment kind must be '{APP_DEPLOYMENT_KIND}'.")
    if value.get("schema_version") != APP_DEPLOYMENT_SCHEMA_VERSION:
        raise AppDeploymentError("App deployment schema_version must be 1.")
    deployment_id = _clean_id(value.get("id"), label="Deployment id")
    raw_apps = value.get("apps")
    if not isinstance(raw_apps, list):
        raise AppDeploymentError("App deployment apps must be an array.")
    rebuilt = build_app_deployment(
        (
            (f"apps[{index}]", app.get("workflow"))
            for index, app in enumerate(raw_apps)
            if isinstance(app, Mapping) and isinstance(app.get("workflow"), Mapping)
        ),
        deployment_id=deployment_id,
        name=str(value.get("name") or "").strip() or None,
        start_app=str(value.get("start_app") or "").strip() or None,
    )
    if len(rebuilt["apps"]) != len(raw_apps):
        raise AppDeploymentError("Every app entry must contain a workflow object.")
    return rebuilt


def load_app_deployment(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AppDeploymentError(f"Could not read App deployment {manifest_path}: {exc}") from exc
    return validate_app_deployment(value)


def export_app_deployment(
    workflow_paths: Iterable[str | Path],
    output: str | Path,
    *,
    deployment_id: str,
    name: str | None = None,
    start_app: str | None = None,
) -> Path:
    sources: list[tuple[str, Mapping[str, Any]]] = []
    for value in workflow_paths:
        path = Path(value)
        try:
            workflow = load_workflow(path)
        except (OSError, json.JSONDecodeError) as exc:
            raise AppDeploymentError(f"Could not read workflow {path}: {exc}") from exc
        sources.append((str(path), workflow))
    manifest = build_app_deployment(
        sources,
        deployment_id=deployment_id,
        name=name,
        start_app=start_app,
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output_path


def public_app_deployment(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(manifest[key])
        for key in ("kind", "schema_version", "id", "name", "start_app", "access", "required_packages")
        if key in manifest
    } | {
        "apps": [
            {
                key: copy.deepcopy(app[key])
                for key in ("id", "name", "description", "accent", "required_packages")
                if key in app
            }
            for app in manifest.get("apps", [])
            if isinstance(app, Mapping)
        ]
    }


def app_by_id(manifest: Mapping[str, Any], app_id: str) -> Mapping[str, Any] | None:
    return next(
        (
            app for app in manifest.get("apps", [])
            if isinstance(app, Mapping) and app.get("id") == app_id
        ),
        None,
    )


def permission_value(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def operator_permissions(app: Mapping[str, Any]) -> dict[str, set[tuple[str, ...]]]:
    workflow = app.get("workflow") if isinstance(app.get("workflow"), Mapping) else {}
    view = _operator_view(workflow, source=str(app.get("id") or "app"))
    params: set[tuple[str, str]] = set()
    updates: set[tuple[str, str, str]] = set()
    controls: set[tuple[str, str, str]] = set()
    cooks: set[tuple[str, str, str]] = set()

    run_target = view.get("run_target")
    if isinstance(run_target, Mapping):
        cooks.add((
            str(run_target.get("node_id") or ""),
            str(run_target.get("port") or ""),
            str(run_target.get("mode") or "once"),
        ))
    for section in view.get("sections", []):
        if not isinstance(section, Mapping):
            continue
        for widget in section.get("widgets", []):
            if not isinstance(widget, Mapping):
                continue
            widget_type = widget.get("type")
            for item in widget.get("items", []):
                if not isinstance(item, Mapping):
                    continue
                if widget_type == "fields":
                    params.add((str(item.get("node_id") or ""), str(item.get("param") or "")))
                if widget_type != "actions":
                    continue
                for update in item.get("updates", []):
                    if isinstance(update, Mapping):
                        updates.add((
                            str(update.get("node_id") or ""),
                            str(update.get("param") or ""),
                            permission_value(update.get("value")),
                        ))
                control = item.get("control")
                if isinstance(control, Mapping):
                    controls.add((
                        str(control.get("node_id") or ""),
                        str(control.get("action") or ""),
                        permission_value(control.get("payload") if isinstance(control.get("payload"), Mapping) else {}),
                    ))
                target = item.get("cook_target")
                if isinstance(target, Mapping):
                    cooks.add((
                        str(target.get("node_id") or ""),
                        str(target.get("port") or ""),
                        str(target.get("mode") or "once"),
                    ))
    return {
        "params": {item for item in params if all(item)},
        "updates": {item for item in updates if all(item)},
        "controls": {item for item in controls if all(item)},
        "cooks": {item for item in cooks if all(item)},
    }
