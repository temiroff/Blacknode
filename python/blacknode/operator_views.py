from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any
from urllib.parse import urlsplit


_WIDGET_TYPES = frozenset({"image", "viewer", "status", "metrics", "fields", "actions"})
_INPUT_TYPES = frozenset({"text", "number", "textarea", "file_path", "calibration_file", "swap"})
_TONES = frozenset({"neutral", "primary", "success", "warning", "danger"})
_EXTENSION_RE = re.compile(r"\.[a-z0-9][a-z0-9._+-]{0,31}", re.I)


class OperatorViewValidationError(ValueError):
    """Raised when a workflow's operator surface does not match schema version 1."""


def _record(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OperatorViewValidationError(f"{path} must be an object.")
    return value


def _list(value: object, path: str, *, nonempty: bool = False) -> Sequence[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = " contain at least one item" if nonempty else " be an array"
        raise OperatorViewValidationError(f"{path} must{suffix}.")
    return value


def _text(record: Mapping[str, Any], key: str, path: str, *, optional: bool = False) -> str:
    value = record.get(key)
    if optional and value is None:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise OperatorViewValidationError(f"{path}.{key} must be a non-empty string.")
    return value


def _optional_text(record: Mapping[str, Any], key: str, path: str) -> None:
    if key in record and record[key] is not None and not isinstance(record[key], str):
        raise OperatorViewValidationError(f"{path}.{key} must be a string.")


def _enum(record: Mapping[str, Any], key: str, choices: frozenset[str], path: str) -> None:
    value = record.get(key)
    if value is not None and value not in choices:
        raise OperatorViewValidationError(f"{path}.{key} must be one of: {', '.join(sorted(choices))}.")


def _source(value: object, path: str) -> None:
    source = _record(value, path)
    _text(source, "node_id", path)
    _text(source, "port", path)


def _target(value: object, path: str) -> None:
    target = _record(value, path)
    _text(target, "node_id", path)
    _text(target, "port", path)
    _enum(target, "mode", frozenset({"once", "live"}), path)
    _optional_text(target, "label", path)
    _optional_text(target, "confirm", path)
    if target.get("live_source") is not None:
        _source(target["live_source"], f"{path}.live_source")


def _field(value: object, path: str) -> None:
    field = _record(value, path)
    _text(field, "node_id", path)
    _text(field, "param", path)
    _text(field, "label", path)
    _enum(field, "input", _INPUT_TYPES, path)
    for key in ("placeholder", "button_label", "picker_title", "confirm"):
        _optional_text(field, key, path)
    for key in ("min", "max", "step"):
        if key in field and field[key] is not None and not isinstance(field[key], (int, float)):
            raise OperatorViewValidationError(f"{path}.{key} must be a number.")
    if field.get("extensions") is not None:
        extensions = _list(field["extensions"], f"{path}.extensions", nonempty=True)
        for extension in extensions:
            clean = str(extension or "").strip()
            normalized = clean if clean.startswith(".") else f".{clean}"
            if not isinstance(extension, str) or not _EXTENSION_RE.fullmatch(normalized):
                raise OperatorViewValidationError(f"{path}.extensions contains an invalid file extension.")
    if field.get("input") == "file_path" and not field.get("extensions"):
        raise OperatorViewValidationError(f"{path}.extensions is required for a file_path field.")
    if field.get("apply_to") is not None:
        for index, raw_target in enumerate(_list(field["apply_to"], f"{path}.apply_to")):
            target = _record(raw_target, f"{path}.apply_to[{index}]")
            _text(target, "node_id", f"{path}.apply_to[{index}]")
            _text(target, "param", f"{path}.apply_to[{index}]")
    if field.get("swap_pairs") is not None:
        for index, raw_pair in enumerate(_list(field["swap_pairs"], f"{path}.swap_pairs", nonempty=True)):
            pair_path = f"{path}.swap_pairs[{index}]"
            pair = _record(raw_pair, pair_path)
            for side in ("left", "right"):
                target = _record(pair.get(side), f"{pair_path}.{side}")
                _text(target, "node_id", f"{pair_path}.{side}")
                _text(target, "param", f"{pair_path}.{side}")
    if field.get("disabled_when") is not None:
        _source(field["disabled_when"], f"{path}.disabled_when")


def _control(value: object, path: str) -> None:
    control = _record(value, path)
    _text(control, "node_id", path)
    _text(control, "action", path)
    if control.get("payload") is not None:
        _record(control["payload"], f"{path}.payload")


def _action(value: object, path: str) -> None:
    action = _record(value, path)
    _text(action, "id", path)
    _text(action, "label", path)
    _enum(action, "tone", _TONES, path)
    _enum(action, "active_tone", _TONES, path)
    for key in ("confirm", "active_label", "active_confirm"):
        _optional_text(action, key, path)
    if action.get("updates") is not None:
        for index, raw_update in enumerate(_list(action["updates"], f"{path}.updates", nonempty=True)):
            update_path = f"{path}.updates[{index}]"
            update = _record(raw_update, update_path)
            _text(update, "node_id", update_path)
            _text(update, "param", update_path)
            if "value" not in update:
                raise OperatorViewValidationError(f"{update_path}.value is required.")
    for key in ("control", "deactivate_control"):
        if action.get(key) is not None:
            _control(action[key], f"{path}.{key}")
    if action.get("cook_target") is not None:
        _target(action["cook_target"], f"{path}.cook_target")
    if action.get("state") is not None:
        _source(action["state"], f"{path}.state")
    if not any(action.get(key) is not None for key in ("updates", "control", "cook_target")):
        raise OperatorViewValidationError(f"{path} must declare updates, control, or cook_target.")


def _widget(value: object, path: str) -> None:
    widget = _record(value, path)
    widget_type = _text(widget, "type", path)
    if widget_type not in _WIDGET_TYPES:
        raise OperatorViewValidationError(f"{path}.type must be one of: {', '.join(sorted(_WIDGET_TYPES))}.")
    _text(widget, "id", path)
    _optional_text(widget, "title", path)
    if widget_type in {"image", "viewer"}:
        _text(widget, "title", path)
        _source(widget.get("source"), f"{path}.source")
        _optional_text(widget, "empty", path)
        if widget_type == "image":
            _enum(widget, "aspect", frozenset({"video", "dashboard"}), path)
        elif widget.get("trusted_origins") is not None:
            origins = _list(widget["trusted_origins"], f"{path}.trusted_origins")
            for origin in origins:
                parsed = urlsplit(str(origin or ""))
                if (
                    not isinstance(origin, str)
                    or parsed.scheme not in {"http", "https"}
                    or not parsed.netloc
                    or parsed.username
                    or parsed.password
                    or parsed.path not in {"", "/"}
                    or parsed.query
                    or parsed.fragment
                ):
                    raise OperatorViewValidationError(
                        f"{path}.trusted_origins must contain exact HTTP(S) origins."
                    )
        return
    items = _list(widget.get("items"), f"{path}.items", nonempty=True)
    for index, item in enumerate(items):
        item_path = f"{path}.items[{index}]"
        if widget_type == "fields":
            _field(item, item_path)
        elif widget_type == "actions":
            _action(item, item_path)
        else:
            record = _record(item, item_path)
            _source(record, item_path)
            _text(record, "label", item_path)
            if widget_type == "status":
                _enum(record, "tone", frozenset({"neutral", "success", "warning", "danger"}), item_path)
                _optional_text(record, "true_label", item_path)
                _optional_text(record, "false_label", item_path)
            else:
                _optional_text(record, "suffix", item_path)
                _enum(record, "format", frozenset({"number", "duration", "text"}), item_path)


def validate_operator_view(value: object) -> Mapping[str, Any]:
    """Validate and return an operator-view mapping using the complete v1 contract."""
    view = _record(value, "operator_view")
    if view.get("schema_version") != 1:
        raise OperatorViewValidationError("operator_view.schema_version must be 1.")
    _text(view, "title", "operator_view")
    for key in ("id", "description", "accent"):
        _optional_text(view, key, "operator_view")
    _enum(view, "icon", frozenset({"record", "camera", "robot", "workflow", "play"}), "operator_view")
    if view.get("run_target") is not None:
        _target(view["run_target"], "operator_view.run_target")
    section_ids: set[str] = set()
    widget_ids: set[str] = set()
    for index, raw_section in enumerate(_list(view.get("sections"), "operator_view.sections", nonempty=True)):
        path = f"operator_view.sections[{index}]"
        section = _record(raw_section, path)
        section_id = _text(section, "id", path)
        if section_id in section_ids:
            raise OperatorViewValidationError(f"{path}.id duplicates section id '{section_id}'.")
        section_ids.add(section_id)
        _optional_text(section, "title", path)
        _optional_text(section, "description", path)
        _enum(section, "region", frozenset({"main", "parameters"}), path)
        _enum(section, "layout", frozenset({"grid", "stack"}), path)
        for widget_index, widget in enumerate(_list(section.get("widgets"), f"{path}.widgets", nonempty=True)):
            widget_path = f"{path}.widgets[{widget_index}]"
            _widget(widget, widget_path)
            widget_id = str(widget["id"])
            if widget_id in widget_ids:
                raise OperatorViewValidationError(f"{widget_path}.id duplicates widget id '{widget_id}'.")
            widget_ids.add(widget_id)
    settings = view.get("settings")
    if settings is not None:
        settings = _record(settings, "operator_view.settings")
        _optional_text(settings, "title", "operator_view.settings")
        _optional_text(settings, "description", "operator_view.settings")
        group_ids: set[str] = set()
        for index, raw_group in enumerate(_list(settings.get("groups"), "operator_view.settings.groups", nonempty=True)):
            path = f"operator_view.settings.groups[{index}]"
            group = _record(raw_group, path)
            group_id = _text(group, "id", path)
            if group_id in group_ids:
                raise OperatorViewValidationError(f"{path}.id duplicates settings group id '{group_id}'.")
            group_ids.add(group_id)
            _text(group, "title", path)
            _optional_text(group, "description", path)
            for item_index, item in enumerate(_list(group.get("items"), f"{path}.items", nonempty=True)):
                _field(item, f"{path}.items[{item_index}]")
    return view
