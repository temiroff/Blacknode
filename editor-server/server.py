"""Blacknode editor backend — FastAPI server the React editor talks to."""
from __future__ import annotations
import asyncio, uuid, os, sys, json, threading, re, queue, io, contextlib, time, subprocess, importlib, signal, shlex, hashlib, math, copy, base64, tempfile
from array import array
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import blacknode as bn
import blacknode.integrations  # noqa: F401  registers chat drivers (slack/telegram)
# The server executes nodes itself rather than going through Graph, so the
# frame-stream contract has to be filled here too.
from blacknode import console as command_console
from blacknode.node import fill_frame_stream as bn_fill_frame_stream
from blacknode.deployments import DeploymentError, DeploymentStore, resolve_entrypoint
from blacknode.discovery import discover_node_modules, load_node_file
from blacknode.integrations import registry as driver_registry
from blacknode.exporters import export_workflow as export_framework_workflow
from blacknode.exporters import list_export_targets
from blacknode.learned import registry as learned_registry
from blacknode.mcp import tools as mcp_tools
from blacknode.node import _NODE_REGISTRY
from blacknode.nodes import ai as ai_nodes
import blacknode.package_index as bn_package_index
from blacknode.packages import MANIFEST_NAME as BN_MANIFEST_NAME
from blacknode.packages import component_dependency_plan as bn_component_dependency_plan
from blacknode.packages import adapter_dependency_plan as bn_adapter_dependency_plan
from blacknode.packages import discover_packages as discover_bn_packages
from blacknode.packages import install_from_git as bn_install_from_git
from blacknode.packages import install_prerequisites as bn_install_prerequisites
from blacknode.packages import installed_packages, package_category_colors, package_statuses, package_template_dirs
from blacknode.packages import load_package as bn_load_package
from blacknode.packages import packages_root as bn_packages_root
from blacknode.packages import remove_package as bn_remove_package
from blacknode.packages import ensure_component_enabled as bn_ensure_component_enabled
from blacknode.packages import ensure_adapter_enabled as bn_ensure_adapter_enabled
from blacknode.packages import set_component_enabled as bn_set_component_enabled
from blacknode.packages import set_adapter_enabled as bn_set_adapter_enabled
from blacknode.packages import reset_component as bn_reset_component
from blacknode.python_importer import import_workflow_python
from blacknode.workflow import WorkflowRunError, export_workflow_python
from blacknode.workflow import validate_graph as validate_bn_graph
from blacknode.workflow import validate_workflow as validate_bn_workflow
from device_installer import (
    adopt_legacy_hardware_services,
    configure_hardware_services,
    control_runtime,
    DeviceInstallError,
    discover_hardware_pairings,
    inspect_managed_service_updates,
    inspect_runtime,
    install_hardware_environment,
    install_runtime,
    probe_device,
    restart_hardware_service,
    uninstall_runtime,
    update_managed_services,
)
from device_registry import (
    DeviceRegistry,
    DeviceRegistryError,
    HardwareDeviceClient,
    RuntimeDeviceClient,
)
from local_runtime import (
    LocalRuntimeError,
    default_local_runtime_dir,
    ensure_local_runtime,
    inspect_local_hardware,
    inspect_local_package_updates,
    inspect_local_runtime,
    install_local_runtime,
    manage_local_package,
    stop_local_runtime,
    uninstall_local_runtime,
)
from artifact_store import ArtifactStore, ArtifactStoreError
from project_store import ProjectStore, ProjectStoreError
from run_store import RunStore
import cloud_client
import cloud_sessions
from hosted_mode import HostedWorkspaceStore, route_allowed as hosted_route_allowed


def package_index_payload(*args, **kwargs):
    return bn_package_index.package_index_payload(*args, **kwargs)


def resolve_workflow_dependencies(*args, **kwargs):
    return bn_package_index.resolve_workflow_dependencies(*args, **kwargs)


def canonical_package_name(*args, **kwargs):
    return bn_package_index.canonical_package_name(*args, **kwargs)


def template_adapter_requirements(*args, **kwargs):
    return bn_package_index.template_adapter_requirements(*args, **kwargs)


def template_component_requirements(*args, **kwargs):
    return bn_package_index.template_component_requirements(*args, **kwargs)


def workflow_node_types(*args, **kwargs):
    return bn_package_index.workflow_node_types(*args, **kwargs)


_HOSTED_MODE = os.environ.get("BLACKNODE_HOSTED_MODE", "").strip().lower() in {
    "1",
    "true",
    "yes",
}
_HOSTED_PUBLIC_ORIGIN = os.environ.get(
    "BLACKNODE_HOSTED_PUBLIC_ORIGIN",
    "https://app.blacknoderobotics.com",
).strip().rstrip("/")
_HOSTED_ACCOUNT_ORIGINS = frozenset(
    origin.strip().rstrip("/")
    for origin in os.environ.get("BLACKNODE_HOSTED_ACCOUNT_ORIGINS", "").split(",")
    if origin.strip().startswith(("http://", "https://"))
)
_HOSTED_ACCOUNT_CORS_METHODS = {
    "/cloud/status": frozenset({"GET"}),
    "/cloud/account": frozenset({"PATCH"}),
    "/cloud/auth/register": frozenset({"POST"}),
    "/cloud/auth/login": frozenset({"POST"}),
    "/cloud/auth/logout": frozenset({"POST"}),
    "/cloud/newsletter/subscribe": frozenset({"POST"}),
}

app = FastAPI(title="Blacknode Editor Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[] if _HOSTED_MODE else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CLOUD_SESSION_COOKIE = "blacknode_cloud_session"
_cloud_sessions = cloud_sessions.CloudSessionStore()


def _reap_orphaned_stream_servers() -> None:
    """Kill stream-server helpers left behind by a previous run before serving.

    Stream servers are spawned detached so a cook can end without killing them.
    When the editor exits uncleanly - a crash, a hard reload, a Windows restart
    that skips atexit - they keep holding the camera, and the next capture reads
    nothing ("camera frame read failed"). Clearing them at startup means a
    restart always begins with the hardware free.
    """
    marker = "stream_server.py"
    my_pid = os.getpid()
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"],
                capture_output=True, text=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            for line in out.splitlines():
                if marker not in line:
                    continue
                pid = line.strip().rsplit(None, 1)[-1]
                if pid.isdigit() and int(pid) != my_pid:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", pid],
                                   capture_output=True, timeout=10,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            subprocess.run(["pkill", "-f", marker], capture_output=True, timeout=10)
    except Exception:
        # Best effort: a failure here must never stop the server booting.
        pass



# Log every subprocess any node starts, so the Console shows the whole picture
# rather than only the calls that remembered to instrument themselves.
command_console.install_spawn_hook()

# ── Persistence ───────────────────────────────────────────────────────────────

_SAVE_PATH      = os.path.join(os.path.dirname(__file__), "blacknode_graph.json")
_WORKFLOWS_DIR  = os.path.join(os.path.dirname(__file__), "..", "workflows")
_TEMPLATES_DIR  = os.path.join(os.path.dirname(__file__), "..", "templates")
_CUSTOM_NODES_DIR = os.path.join(os.path.dirname(__file__), "..", "custom-nodes")
_RUNS_DIR       = os.path.join(os.path.dirname(__file__), "runs")
_run_store      = RunStore(_RUNS_DIR)
# Deployments live beside the repo, not under editor-server/, because a
# deployment outlives this server process and is not tied to it.
_DEPLOYMENTS_DIR = Path(__file__).resolve().parents[1] / ".blacknode" / "deployments"
_deployment_store = DeploymentStore(_DEPLOYMENTS_DIR)
_DEVICES_PATH = Path(__file__).resolve().parents[1] / ".blacknode" / "devices.json"
_device_registry = DeviceRegistry(_DEVICES_PATH)
_PROJECTS_PATH = Path(__file__).resolve().parents[1] / ".blacknode" / "projects.json"
_project_store = ProjectStore(_PROJECTS_PATH)
_ARTIFACTS_PATH = Path(__file__).resolve().parents[1] / ".blacknode" / "artifacts.json"
_artifact_store = ArtifactStore(_ARTIFACTS_PATH)
_save_timer: threading.Timer | None = None
_SUBGRAPH_NODE_TYPES = {"Subnet", "SubnetAsTool", "VisualAgentLoop"}
_TOOLBOX_NODE_TYPES = {"ToolBox"}
_JOINT_LIST_NODE_TYPES = {"RobotJointList"}
_NUMBERED_INPUT_NODE_TYPES = {*_TOOLBOX_NODE_TYPES, *_JOINT_LIST_NODE_TYPES}
_DYNAMIC_PORT_TYPES = {*_SUBGRAPH_NODE_TYPES, "SubnetInput", "SubnetOutput", *_NUMBERED_INPUT_NODE_TYPES}
_WORKFLOW_KIND = "blacknode.workflow"
_WORKFLOW_SCHEMA_VERSION = 1
_SECRET_FIELD_RE = re.compile(r"(api[_-]?key|token|secret|password|credential)", re.I)


def _migrate_legacy_node_meta(meta: dict) -> bool:
    changed = False
    if meta.get("type") == "LoadImage":
        params = meta.setdefault("params", {})
        defaults = meta.setdefault("input_defaults", {})
        if params.get("max_size") == 768 and defaults.get("max_size") == 768:
            params["max_size"] = 0
            changed = True
        if defaults.get("max_size") == 768:
            defaults["max_size"] = 0
            changed = True

    subgraph = meta.get("subgraph")
    if isinstance(subgraph, dict):
        inner_meta = subgraph.get("node_meta")
        if isinstance(inner_meta, dict):
            for child in inner_meta.values():
                if isinstance(child, dict):
                    changed = _migrate_legacy_node_meta(child) or changed
    return changed


def _save_now() -> None:
    try:
        with open(_SAVE_PATH, "w") as f:
            json.dump({"node_meta": _session.node_meta,
                       "edges":     _session.graph._edges,
                       "metadata":  _session.metadata,
                       "entrypoint": _session.entrypoint}, f, indent=2)
    except Exception as e:
        print(f"[blacknode] save error: {e}")


def _save(debounce: float = 0.0) -> None:
    """Write graph to disk. Pass debounce > 0 to coalesce rapid calls (e.g. node drag)."""
    if _HOSTED_MODE:
        return
    global _save_timer
    if _save_timer:
        _save_timer.cancel()
    if debounce > 0:
        _save_timer = threading.Timer(debounce, _save_now)
        _save_timer.daemon = True
        _save_timer.start()
    else:
        _save_now()


def _load() -> None:
    if not os.path.exists(_SAVE_PATH):
        return
    try:
        with open(_SAVE_PATH) as f:
            data = json.load(f)
        meta_map: dict = data.get("node_meta", {})
        edges:    list = data.get("edges",     [])
        metadata = data.get("metadata")
        _session.metadata = dict(metadata) if isinstance(metadata, dict) else {}
        entrypoint = data.get("entrypoint")
        _session.entrypoint = dict(entrypoint) if isinstance(entrypoint, dict) else None
        # only restore nodes whose type is still registered
        migrated = False
        for node_id, meta in meta_map.items():
            if meta["type"] not in _NODE_REGISTRY and meta["type"] not in _SUBGRAPH_NODE_TYPES:
                continue
            migrated = _migrate_legacy_node_meta(meta) or migrated
            if meta["type"] in _SUBGRAPH_NODE_TYPES:
                _sync_subgraph_node_ports(meta)
            elif meta["type"] in _TOOLBOX_NODE_TYPES:
                _sync_toolbox_ports(meta, edges)
            _session.node_meta[node_id] = meta
            node_entry = {
                "type":   meta["type"],
                "params": dict(meta.get("params", {})),
            }
            if meta["type"] in _SUBGRAPH_NODE_TYPES:
                node_entry["subgraph"] = meta.get("subgraph", {"node_meta": {}, "edges": []})
            _session.graph._nodes[node_id] = node_entry
            _session.graph._dirty.add(node_id)
        _session.graph._edges = [
            e for e in edges
            if e["from"] in _session.graph._nodes and e["to"] in _session.graph._nodes
        ]
        print(f"[blacknode] Loaded {len(_session.node_meta)} nodes, "
              f"{len(_session.graph._edges)} edges from {_SAVE_PATH}")
        if migrated:
            _save()
    except Exception as e:
        print(f"[blacknode] Could not load saved graph: {e}")


# ── In-memory state ───────────────────────────────────────────────────────────

class Session:
    def __init__(self):
        self.graph = bn.Graph()
        self.node_meta: dict[str, dict] = {}
        self.metadata: dict[str, Any] = {}
        self.entrypoint: dict[str, str] | None = None


_local_session = Session()
_hosted_session_context: ContextVar[Session | None] = ContextVar(
    "blacknode_hosted_session",
    default=None,
)
_hosted_workspaces = HostedWorkspaceStore(Session)


class _SessionProxy:
    def _target(self) -> Session:
        return _hosted_session_context.get() or _local_session

    def __getattr__(self, name: str):
        return getattr(self._target(), name)

    def __setattr__(self, name: str, value) -> None:
        setattr(self._target(), name, value)


_session = _SessionProxy()


def _hosted_error(code: str, message: str) -> Response:
    response = Response(
        content=json.dumps({"detail": {"code": code, "message": message}}),
        status_code=403,
        media_type="application/json",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _hosted_account_cors_allowed(origin: str, method: str, path: str) -> bool:
    return (
        origin in _HOSTED_ACCOUNT_ORIGINS
        and method.upper() in _HOSTED_ACCOUNT_CORS_METHODS.get(path, frozenset())
    )


def _set_hosted_account_cors(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    vary = response.headers.get("Vary", "")
    if "origin" not in {item.strip().lower() for item in vary.split(",") if item.strip()}:
        response.headers["Vary"] = f"{vary}, Origin".strip(", ")


@app.middleware("http")
async def hosted_preview_boundary(request: Request, call_next):
    if not _HOSTED_MODE:
        return await call_next(request)
    path = request.url.path
    method = request.method.upper()
    origin = request.headers.get("origin", "").rstrip("/")
    requested_method = request.headers.get("access-control-request-method", "").upper()
    if method == "OPTIONS":
        if not _hosted_account_cors_allowed(origin, requested_method, path):
            return _hosted_error("INVALID_ORIGIN", "The request origin is not allowed.")
        response = Response(status_code=204)
        _set_hosted_account_cors(response, origin)
        response.headers["Access-Control-Allow-Methods"] = requested_method
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Max-Age"] = "600"
        return response
    cross_origin_account_request = bool(origin and origin != _HOSTED_PUBLIC_ORIGIN)
    if cross_origin_account_request and not _hosted_account_cors_allowed(origin, method, path):
        return _hosted_error("INVALID_ORIGIN", "The request origin is not allowed.")
    if not hosted_route_allowed(method, path, query=request.url.query):
        return _hosted_error(
            "HOSTED_CAPABILITY_UNAVAILABLE",
            "This capability is available in the installed Blacknode Editor.",
        )
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        if origin != _HOSTED_PUBLIC_ORIGIN and not cross_origin_account_request:
            return _hosted_error("INVALID_ORIGIN", "The request origin is not allowed.")
    workspace_token = None
    context_token = None
    created = False
    if path not in {"/healthz", "/readyz", "/hosted/status"}:
        workspace_token, workspace, created = _hosted_workspaces.get_or_create(
            request.cookies.get("__Host-blacknode_workspace")
        )
        context_token = _hosted_session_context.set(workspace)
    try:
        response = await call_next(request)
    finally:
        if context_token is not None:
            _hosted_session_context.reset(context_token)
    if created and workspace_token:
        response.set_cookie(
            "__Host-blacknode_workspace",
            workspace_token,
            max_age=86_400,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if cross_origin_account_request:
        _set_hosted_account_cors(response, origin)
    return response


# ── Schema models ─────────────────────────────────────────────────────────────

class AddNodeReq(BaseModel):
    type_name: str
    params: dict[str, Any] = {}
    pos: tuple[float, float] = (0.0, 0.0)

class ConnectReq(BaseModel):
    from_id: str
    from_port: str
    to_id: str
    to_port: str

class UpdateParamReq(BaseModel):
    key: str
    value: Any

class NodeControlReq(BaseModel):
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)

class PickDirectoryReq(BaseModel):
    initial_path: str = ""
    title: str = ""

class PickFileReq(BaseModel):
    initial_path: str = ""
    title: str = ""
    extensions: list[str] = Field(default_factory=list)

class BrowseFilesReq(BaseModel):
    path: str = ""
    extensions: list[str] = Field(default_factory=list)

class DatasetTrimReq(BaseModel):
    token: str
    frame_index: int
    side: str

class DatasetReplayEventReq(BaseModel):
    token: str
    frame_index: int
    event: str

class UpdatePortsReq(BaseModel):
    inputs: list[str] | None = None
    outputs: list[str] | None = None
    input_types: dict[str, str] | None = None
    output_types: dict[str, str] | None = None
    input_defaults: dict[str, Any] | None = None
    multi_input_ports: list[str] | None = None

class UpdatePortVisibilityReq(BaseModel):
    promoted_inputs: list[str] | None = None
    promoted_outputs: list[str] | None = None

class CookReq(BaseModel):
    node_id: str
    port: str = "output"
    run_mode: str = "once"

class CookTargetReq(BaseModel):
    node_id: str
    port: str = "output"

class CookGraphReq(BaseModel):
    targets: list[CookTargetReq]
    run_mode: str = "once"

class CloudJobReq(BaseModel):
    entrypoint: dict[str, str]
    workflow_name: str = "Current Graph"
    project_ref: str | None = None
    max_runtime_seconds: int = Field(default=3600, ge=60, le=86_400)


class CloudVLATrainReq(BaseModel):
    dataset_uri: str = Field(min_length=1, max_length=1000)
    dataset_revision: str = Field(default="", max_length=200)
    steps: int = Field(default=5000, ge=1, le=10_000_000)
    batch_size: int = Field(default=8, ge=1, le=1024)
    action_horizon: int = Field(default=10, ge=1, le=256)
    max_runtime_seconds: int = Field(default=14_400, ge=60, le=86_400)
    project_ref: str | None = None


class CloudLoginReq(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class CloudRegisterReq(CloudLoginReq):
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(default="", max_length=100)


class CloudUpdateAccountReq(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    compute_provider_preference: str | None = Field(
        default=None,
        pattern=r"^(auto|nvcf|nebius)$",
    )


class CloudNewsletterReq(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    consent: bool
    source: str = Field(
        default="website",
        min_length=1,
        max_length=50,
        pattern=r"^[a-z0-9_-]+$",
    )


class CloudEmailVerificationReq(BaseModel):
    token: str = Field(min_length=32, max_length=500)


class SetGraphReq(BaseModel):
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    entrypoint: dict[str, str] | None = None

class UpdateWorkflowRequirementsReq(BaseModel):
    required_capabilities: list[str] = []
    device_calibration: dict[str, str] | None = None

class ExecNodeReq(BaseModel):
    code: str

class SaveCustomNodeReq(BaseModel):
    filename: str = "custom_node.py"
    code: str

class SetApiKeyReq(BaseModel):
    provider: str
    key: str

class SetOnboardingReq(BaseModel):
    package_welcome_seen: bool = True

class SaveWorkflowReq(BaseModel):
    name: str
    previous_slug: str | None = None

class RenameWorkflowReq(BaseModel):
    name: str

class CreateProjectReq(BaseModel):
    name: str
    description: str = ""
    workflow_slugs: list[str] = []
    device_ids: list[str] = []
    artifact_ids: list[str] = []
    starter_kit: str | None = None
    active_workflow_slug: str | None = None

class UpdateProjectReq(BaseModel):
    name: str | None = None
    description: str | None = None
    workflow_slugs: list[str] | None = None
    device_ids: list[str] | None = None
    artifact_ids: list[str] | None = None
    starter_kit: str | None = None
    active_workflow_slug: str | None = None

class ImportProjectArtifactsReq(BaseModel):
    workflow_slug: str | None = None
    node_type: str = ""
    value: Any = None

class InspectProjectArtifactReq(BaseModel):
    path: str
    workflow_slug: str | None = None

class NewWorkflowTabReq(BaseModel):
    name: str = "Untitled"

class OpenWorkflowTabReq(BaseModel):
    name: str | None = None
    workflow: dict[str, Any]
    organize: bool = True

class CookEditorNodeReq(BaseModel):
    node_id: str
    port: str = "value"

class LoadSavedWorkflowTabReq(BaseModel):
    slug: str
    name: str | None = None
    organize: bool = True

class RenameEditorTabReq(BaseModel):
    name: str

class LearnedNodeEventReq(BaseModel):
    name: str

class UpdateSubgraphReq(BaseModel):
    node_meta: dict[str, Any] = {}
    edges: list[dict[str, Any]] = []

class CollapseSubnetReq(BaseModel):
    node_ids: list[str]
    label: str = "Subnet"

class FrameworkExportReq(BaseModel):
    target: str
    workflow: dict[str, Any] | None = None

class ExportWorkflowReq(BaseModel):
    workflow: dict[str, Any] | None = None

class ImportPythonReq(BaseModel):
    code: str
    name: str = "Imported Python Workflow"

class DeployReq(BaseModel):
    name: str = ""
    # Omit to deploy whatever is currently in the editor graph.
    workflow: dict[str, Any] | None = None
    target: str = "local-process"
    autostart: bool = True

class PairDeviceReq(BaseModel):
    name: str = ""
    base_url: str
    token: str
    runtime_token: str | None = None

class PairDeviceHostReq(BaseModel):
    name: str = ""
    runtime_url: str
    runtime_token: str

class PairHostRobotReq(BaseModel):
    name: str = ""
    base_url: str
    token: str

class SshProbeReq(BaseModel):
    host: str
    port: int = 22

class SshDeviceReq(SshProbeReq):
    username: str
    password: str

class InspectDeviceHostReq(SshDeviceReq):
    host_fingerprint: str
    name: str = ""
    save_inspection: bool = False

class InstallDeviceHostReq(InspectDeviceHostReq):
    name: str = ""
    action: str = "runtime_only"
    instance_id: str = ""

class InstallLocalDeviceHostReq(BaseModel):
    name: str = "Local computer"
    install_dir: str

class ConfigureDeviceHostManagementReq(InspectDeviceHostReq):
    pass

class UninstallDeviceHostReq(BaseModel):
    password: str

class DiscoverHostRobotsReq(BaseModel):
    password: str

class RuntimeLifecycleReq(BaseModel):
    action: str
    password: str

class UpdateManagedDeviceReq(BaseModel):
    password: str
    scope: str = "all"
    operation: str = "auto"


class LocalPackageActionReq(BaseModel):
    action: str

class RemoteHardwarePackageActionReq(BaseModel):
    action: str
    password: str

class RobotLifecycleReq(BaseModel):
    action: str
    password: str = ""

class RenameDeviceReq(BaseModel):
    name: str


class RobotAttachmentReq(BaseModel):
    attachment_id: str
    display_name: str
    attachment_type: str
    capability: str
    provider_package: str
    provider_component: str
    provider_adapter: str = "ros2"
    provider_profile: str = "existing_topics"
    topic: str
    message_type: str
    camera_info_topic: str = ""
    depth_topic: str = ""
    point_cloud_topic: str = ""
    launch_package: str = ""
    launch_target: str = ""
    launch_arguments: list[str] = Field(default_factory=list)
    parent_frame: str = "base_link"
    frame_id: str
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0
    roll_rad: float = 0.0
    pitch_rad: float = 0.0
    yaw_rad: float = 0.0
    hardware_id: str = ""
    required: bool = True
    enabled: bool = True


class DeploymentPreflightReq(BaseModel):
    # Omit to validate the graph currently open in the editor.
    workflow: dict[str, Any] | None = None

class RemoteDeployReq(BaseModel):
    name: str = ""
    workflow_hash: str
    start: bool = False
    deployment_id: str | None = None
    project_id: str | None = None
    workflow_slug: str | None = None

class RemoteRollbackReq(BaseModel):
    start: bool = False

class RemoteMotionControlReq(BaseModel):
    armed: bool

class DeviceRpcReq(BaseModel):
    jsonrpc: str = "2.0"
    id: Any = None
    method: str
    params: dict[str, Any] = {}

class SyncRunReq(BaseModel):
    node_id: str
    port: str = "output"
    node_type: str = "ExternalPython"
    workflow: dict[str, Any] | None = None

class SyncEventReq(BaseModel):
    run_id: str
    event: dict[str, Any]

class SyncFinishReq(BaseModel):
    status: str = "success"
    value: Any = None
    error: str | None = None

_PROVIDER_ENV: dict[str, str] = {
    "Anthropic":     "ANTHROPIC_API_KEY",
    "OpenAI":        "OPENAI_API_KEY",
    "NVIDIA NIM":    "NVIDIA_API_KEY",
    "Hugging Face":  "HF_TOKEN",
    "Ollama (local)": "",
}

_KEYS_PATH = os.path.join(os.path.dirname(__file__), "api_keys.json")
_api_keys: dict[str, str] = {}
_injected_api_key_envs: set[str] = set()
_editor_action_queue: list[dict[str, Any]] = []
_editor_action_lock = threading.Lock()
_learned_node_event_subscribers: list[queue.Queue] = []
_learned_node_event_lock = threading.Lock()
_active_cook_lock = threading.Lock()
_active_cook_stop: threading.Event | None = None


class _CookStopped(Exception):
    pass


def _prepare_cook() -> threading.Event:
    global _active_cook_stop
    with _active_cook_lock:
        if _active_cook_stop is not None:
            _active_cook_stop.set()
        _active_cook_stop = threading.Event()
        return _active_cook_stop


def _stop_active_cook() -> None:
    with _active_cook_lock:
        if _active_cook_stop is not None:
            _active_cook_stop.set()


_RUNTIME_MODULES = {
    "ros2": "blacknode.pkg.blacknode_ros2.ros2_runtime",
    "ros2_live": "blacknode.pkg.blacknode_skills.follow.leader_follower_runtime",
    "joint_control": "blacknode.pkg.blacknode_motion.arm.adapters.ros2.joint_motion",
    "robot_servo_motion": "blacknode.pkg.blacknode_motion.arm.servo_control",
    "robot_calibration_control": "blacknode.pkg.blacknode_robot.calibration_control",
    "vision": "blacknode.pkg.blacknode_perception.cv2_runtime",
    "cuda": "blacknode.pkg.blacknode_cuda.cuda_stream_runtime",
    "viewer": "blacknode.pkg.blacknode_cuda.viewer_runtime",
    "imu_viewer": "blacknode.pkg.blacknode_perception.imu_runtime",
    "slam": "blacknode.pkg.blacknode_cuda.slam_runtime",
    "robot": "blacknode.pkg.blacknode_robot.robot",
    "dataset": "blacknode.pkg.blacknode_dataset.runtime",
    "training": "blacknode.pkg.blacknode_training.runtime",
    "isaac": "blacknode.pkg.blacknode_isaac.runtime",
    "newton": "blacknode.pkg.blacknode_newton.runtime",
}

# Package reloads replace node functions before sys.modules is always updated.
# Resolve stateful robot runtime helpers through the registered launcher—the
# exact module globals that own the live subprocess table—so status and Stop
# All cannot silently look at an empty duplicate module.
_RUNTIME_REGISTRY_ANCHORS = {
    "robot": "RobotDriverLauncher",
    "isaac": "IsaacPolicyBridge",
    "newton": "NewtonSimulation",
    "joint_control": "ROS2ManualMove",
    "robot_calibration_control": "RobotCalibrationControl",
    "viewer": "Viewer",
    "imu_viewer": "IMUViewer",
    "slam": "SLAM",
}

_RUNTIME_CALLABLE_ALIASES = {
    ("ros2_live", "runtime_status"): "leader_follower_runtime_status",
    ("ros2_live", "stop_runtime_services"): "stop_leader_follower_services",
}

_remote_ros2_lock = threading.RLock()
_remote_ros2_runs: dict[str, dict[str, Any]] = {}
_remote_ros2_image_lock = threading.RLock()
_remote_ros2_image_runs: dict[str, dict[str, Any]] = {}


def _remote_ros2_service_id(node_id: str) -> str:
    clean = re.sub(r"[^a-z0-9-]+", "-", str(node_id or "").lower()).strip("-")
    return f"editor-{clean}"[:64] or "editor-ros2"


def _remote_ros2_image_service_id(node_id: str) -> str:
    clean = re.sub(r"[^a-z0-9-]+", "-", str(node_id or "").lower()).strip("-")
    return f"editor-image-{clean}"[:64] or "editor-image"


def _remote_ros2_error_outputs(
    request: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    device_id = str(request.get("device_id") or "")
    topic = str(request.get("topic") or "")
    stream_id = f"device:{device_id}:topic-subscriber:{topic}"
    return {
        "running": False,
        "message": {},
        "messages": [],
        "stream": {
            "kind": "blacknode.message-stream",
            "schema_version": 1,
            "stream_id": stream_id,
            "protocol": "ros2",
            "state": "unavailable",
            "managed": True,
            "topic": topic,
            "message_type": str(request.get("message_type") or ""),
            "backend": f"remote:{device_id}",
            "device_id": device_id,
        },
        "status": {
            "kind": "blacknode.stream-status",
            "schema_version": 1,
            "stream_id": stream_id,
            "state": "unavailable",
            "available": False,
            "worker_alive": False,
            "source_fresh": False,
            "received": 0,
            "last_message_time_ns": 0,
            "age_seconds": None,
            "stale_after_seconds": float(request.get("stale_after_seconds") or 2.0),
            "device_id": device_id,
            "error": error,
        },
        "received": 0,
        "backend": f"remote:{device_id}",
        "report": f"ROS2 unavailable on {device_id}: {error}",
    }


def _remote_ros2_outputs(
    request: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    raw = response.get("outputs") if isinstance(response.get("outputs"), dict) else {}
    outputs = copy.deepcopy(raw)
    device_id = str(request.get("device_id") or "")
    backend = f"remote:{device_id}"
    outputs["backend"] = backend
    stream = outputs.get("stream") if isinstance(outputs.get("stream"), dict) else {}
    remote_stream_id = (
        f"device:{device_id}:topic-subscriber:{str(request.get('topic') or '')}"
    )
    stream.update(
        kind="blacknode.message-stream",
        schema_version=1,
        protocol="ros2",
        backend=backend,
        device_id=device_id,
        node_id=str(request.get("node_id") or ""),
        stream_id=remote_stream_id,
    )
    outputs["stream"] = stream
    status = outputs.get("status") if isinstance(outputs.get("status"), dict) else {}
    status.update(device_id=device_id, stream_id=remote_stream_id)
    outputs["status"] = status
    report = str(outputs.get("report") or "").strip()
    outputs["report"] = f"{report} · device {device_id}" if report else f"ROS2 device {device_id}"
    return outputs


def _ensure_remote_ros2_ready(client: RuntimeDeviceClient) -> None:
    manifest = client.manifest()
    features = {str(item) for item in (manifest.get("features") or [])}
    if "remote_ros2_topic_stream_v1" not in features:
        raise DeviceRegistryError(
            "Update Blacknode Runtime to 0.4.1 or newer from Devices → Software."
        )
    remote_packages = {
        str(item.get("name") or ""): str(item.get("version") or "")
        for item in (manifest.get("packages") or [])
        if isinstance(item, dict)
    }
    workflow = {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "metadata": {
            "required_packages": ["blacknode-ros2"],
            "required_components": [
                "blacknode-ros2/core",
                "blacknode-ros2/topics",
            ],
        },
        "node_meta": {"ros2": {"type": "ROS2"}},
        "edges": [],
    }
    specs = _workflow_target_package_specs(workflow)
    ros2_spec = next(
        (item for item in specs if item.get("name") == "blacknode-ros2"),
        None,
    )
    if not ros2_spec or not ros2_spec.get("git_url"):
        raise DeviceRegistryError(
            "The editor cannot resolve the trusted blacknode-ros2 package source."
        )
    required_version = str(ros2_spec.get("version") or "")
    registered_nodes = {str(item) for item in (manifest.get("node_types") or [])}
    needs_sync = (
        "blacknode-ros2" not in remote_packages
        or (required_version and remote_packages.get("blacknode-ros2") != required_version)
        or "ROS2" not in registered_nodes
    )
    if needs_sync:
        result = client.sync_packages([ros2_spec])
        if not result.get("ok", True):
            raise DeviceRegistryError(
                str(result.get("error") or "Could not install blacknode-ros2 on the device.")
            )


def _remote_ros2_action(request: dict[str, Any]) -> dict[str, Any]:
    node_id = str(request.get("node_id") or "").strip()
    device_id = str(request.get("device_id") or "").strip()
    action = str(request.get("action") or "status").strip().lower()
    if not node_id or not device_id:
        raise RuntimeError("ROS2 remote execution requires a node and paired device")
    service_id = _remote_ros2_service_id(node_id)
    payload = {
        key: request.get(key)
        for key in (
            "topic",
            "message_type",
            "node_name",
            "history",
            "timeout",
            "stale_after_seconds",
            "qos",
        )
    }
    client = _device_registry.runtime_client(device_id)
    try:
        if action == "start":
            _ensure_remote_ros2_ready(client)
            response = client.start_ros2_topic(service_id, payload)
            with _remote_ros2_lock:
                _remote_ros2_runs[node_id] = dict(request)
        elif action == "once":
            _ensure_remote_ros2_ready(client)
            response = client.read_ros2_topic_once(service_id, payload)
        elif action == "stop":
            response = client.stop_ros2_topic(service_id)
            with _remote_ros2_lock:
                _remote_ros2_runs.pop(node_id, None)
        elif action == "status":
            response = client.ros2_topic_status(service_id)
        else:
            raise RuntimeError(f"unknown ROS2 action {action!r}")
    except DeviceRegistryError as exc:
        detail = str(exc)
        if "HTTP 404" in detail or "not found" in detail.casefold():
            detail = (
                "This device Runtime does not support remote ROS2 topic streams. "
                "Update Blacknode Runtime to 0.4.1 or newer."
            )
        return {"id": service_id, "outputs": _remote_ros2_error_outputs(request, detail)}
    return {"id": service_id, "outputs": _remote_ros2_outputs(request, response)}


def _message_stream_reader(source: dict[str, Any]) -> dict[str, Any]:
    """Read the latest value behind a managed message-stream descriptor."""
    if str(source.get("kind") or "") != "blacknode.message-stream":
        return {
            "status": {
                "state": "unavailable",
                "source_fresh": False,
                "error": "source is not a blacknode.message-stream",
            }
        }
    protocol = str(source.get("protocol") or "").strip().lower()
    if protocol != "ros2":
        return {
            "status": {
                "state": "unavailable",
                "source_fresh": False,
                "error": f"message-stream protocol {protocol or 'unknown'!r} is not supported",
            }
        }
    topic = str(source.get("topic") or "").strip()
    device_id = str(source.get("device_id") or "").strip()
    if device_id:
        source_node_id = str(source.get("node_id") or "").strip()
        with _remote_ros2_lock:
            exact = _remote_ros2_runs.get(source_node_id) if source_node_id else None
            request = dict(exact) if exact is not None else next(
                (
                    dict(item)
                    for item in _remote_ros2_runs.values()
                    if str(item.get("device_id") or "") == device_id
                    and str(item.get("topic") or "") == topic
                ),
                None,
            )
        if request is None:
            return _remote_ros2_error_outputs(
                {"device_id": device_id, "topic": topic},
                "the paired-device ROS2 stream is not running",
            )
        result = _remote_ros2_action({**request, "action": "status"})
        return dict(result.get("outputs") or {})

    status_fn = _runtime_callable(
        "ros2",
        _RUNTIME_MODULES["ros2"],
        "topic_subscriber_status",
    )
    outputs_fn = _runtime_callable(
        "ros2",
        _RUNTIME_MODULES["ros2"],
        "ros2_topic_outputs",
    )
    if status_fn is None or outputs_fn is None:
        return {
            "status": {
                "state": "unavailable",
                "source_fresh": False,
                "error": "blacknode-ros2 Runtime is not loaded",
            }
        }
    return dict(outputs_fn(status_fn(topic)))


def _remote_ros2_runtime_status() -> dict[str, Any]:
    with _remote_ros2_lock:
        runs = [(node_id, dict(item)) for node_id, item in _remote_ros2_runs.items()]
    node_outputs = []
    for node_id, request in runs:
        status_request = {**request, "node_id": node_id, "action": "status"}
        result = _remote_ros2_action(status_request)
        node_outputs.append({
            "node_type": "ROS2",
            "node_id": node_id,
            "run_id": str(result.get("id") or _remote_ros2_service_id(node_id)),
            "outputs": dict(result.get("outputs") or {}),
        })
    return {
        "ok": all(
            str(item.get("outputs", {}).get("status", {}).get("state") or "") != "error"
            for item in node_outputs
        ),
        "active": bool(runs),
        "streams": [],
        "managed_runs": [],
        "node_outputs": node_outputs,
        "detached_count": 0,
    }


def _stop_remote_ros2_services() -> dict[str, Any]:
    with _remote_ros2_lock:
        runs = [(node_id, dict(item)) for node_id, item in _remote_ros2_runs.items()]
        _remote_ros2_runs.clear()

    def stop_one(item: tuple[str, dict[str, Any]]) -> str:
        node_id, request = item
        try:
            _remote_ros2_action({**request, "node_id": node_id, "action": "stop"})
            return ""
        except Exception as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=max(1, min(8, len(runs)))) as executor:
        errors = [error for error in executor.map(stop_one, runs) if error] if runs else []
    return {
        "ok": not errors,
        "stopped": {"streams": len(runs)},
        "errors": errors,
        "report": f"stopped {len(runs)} remote ROS2 stream(s)",
    }


def _ensure_remote_ros2_image_ready(client: RuntimeDeviceClient) -> None:
    _ensure_remote_ros2_ready(client)
    features = {str(item) for item in (client.manifest().get("features") or [])}
    if "remote_ros2_image_stream_v1" not in features:
        raise DeviceRegistryError(
            "Update Blacknode Runtime to 0.4.10 or newer from Devices → Software."
        )


def _paired_stream_url(client: RuntimeDeviceClient, value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    stream = urllib.parse.urlsplit(raw)
    paired = urllib.parse.urlsplit(client.base_url)
    if not stream.hostname or not paired.hostname:
        return raw
    host = paired.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{stream.port}" if stream.port is not None else ""
    return urllib.parse.urlunsplit((paired.scheme or stream.scheme, host + port, stream.path, stream.query, stream.fragment))


def _normalize_remote_ros2_image_response(
    client: RuntimeDeviceClient,
    request: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(
        response.get("stream") if isinstance(response.get("stream"), dict) else {}
    )
    for key in ("stream_url", "snapshot_url", "health_url", "frame_url"):
        result[key] = _paired_stream_url(client, result.get(key))
    result["device_id"] = str(request.get("device_id") or "")
    result["backend"] = f"remote:{result['device_id']}"
    return {"id": str(response.get("id") or ""), "stream": result}


def _remote_ros2_image_action(request: dict[str, Any]) -> dict[str, Any]:
    node_id = str(request.get("node_id") or "").strip()
    device_id = str(request.get("device_id") or "").strip()
    action = str(request.get("action") or "status").strip().lower()
    if not node_id or not device_id:
        raise RuntimeError("ROS2 image execution requires a node and paired device")
    stream_id = _remote_ros2_image_service_id(node_id)
    payload = {
        key: request.get(key)
        for key in (
            "topic",
            "message_type",
            "port",
            "max_fps",
            "max_width",
            "jpeg_quality",
            "timeout",
        )
    }
    client = _device_registry.runtime_client(device_id)
    try:
        if action == "start":
            _ensure_remote_ros2_image_ready(client)
            response = client.start_ros2_image(stream_id, payload)
            with _remote_ros2_image_lock:
                _remote_ros2_image_runs[node_id] = dict(request)
        elif action == "once":
            _ensure_remote_ros2_image_ready(client)
            response = client.read_ros2_image_once(stream_id, payload)
        elif action == "stop":
            response = client.stop_ros2_image(stream_id)
            with _remote_ros2_image_lock:
                _remote_ros2_image_runs.pop(node_id, None)
        elif action == "status":
            response = client.ros2_image_status(stream_id)
        else:
            raise RuntimeError(f"unknown ROS2 image action {action!r}")
        return _normalize_remote_ros2_image_response(client, request, response)
    except DeviceRegistryError as exc:
        return {
            "id": stream_id,
            "stream": {
                "ok": False,
                "running": False,
                "stream_id": stream_id,
                "device_id": device_id,
                "backend": f"remote:{device_id}",
                "error": str(exc),
            },
        }


def _remote_ros2_image_runtime_status() -> dict[str, Any]:
    with _remote_ros2_image_lock:
        runs = [(node_id, dict(item)) for node_id, item in _remote_ros2_image_runs.items()]
    node_outputs = []
    for node_id, request in runs:
        result = _remote_ros2_image_action({**request, "node_id": node_id, "action": "status"})
        node_outputs.append({
            "node_type": str(request.get("node_type") or "ROS2Image"),
            "node_id": node_id,
            "run_id": str(result.get("id") or _remote_ros2_image_service_id(node_id)),
            "outputs": dict(result.get("stream") or {}),
        })
    return {
        "ok": all(bool(item.get("outputs", {}).get("ok", True)) for item in node_outputs),
        "active": bool(runs),
        "streams": [],
        "managed_runs": [],
        "node_outputs": node_outputs,
        "detached_count": 0,
    }


def _stop_remote_ros2_image_services() -> dict[str, Any]:
    with _remote_ros2_image_lock:
        runs = [(node_id, dict(item)) for node_id, item in _remote_ros2_image_runs.items()]
        _remote_ros2_image_runs.clear()

    def stop_one(item: tuple[str, dict[str, Any]]) -> str:
        node_id, request = item
        try:
            result = _remote_ros2_image_action({**request, "node_id": node_id, "action": "stop"})
            return str(result.get("stream", {}).get("error") or "")
        except Exception as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=max(1, min(8, len(runs)))) as executor:
        errors = [error for error in executor.map(stop_one, runs) if error] if runs else []
    return {
        "ok": not errors,
        "stopped": {"streams": len(runs)},
        "errors": errors,
        "report": f"stopped {len(runs)} remote ROS2 image stream(s)",
    }


def _runtime_module(module_name: str):
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _runtime_callable(label: str, module_name: str, name: str):
    callable_name = _RUNTIME_CALLABLE_ALIASES.get((label, name), name)
    anchor_name = _RUNTIME_REGISTRY_ANCHORS.get(label)
    anchor = _NODE_REGISTRY.get(anchor_name) if anchor_name else None
    candidate = (
        getattr(anchor, "__globals__", {}).get(callable_name)
        if anchor is not None
        else None
    )
    if callable(candidate):
        return candidate
    runtime = _runtime_module(module_name)
    candidate = (
        getattr(runtime, callable_name, None)
        if runtime is not None
        else None
    )
    return candidate if callable(candidate) else None


def _runtime_module_status(label: str, module_name: str) -> dict[str, Any]:
    status_fn = _runtime_callable(label, module_name, "runtime_status")
    if status_fn is None:
        return {
            "ok": True,
            "active": False,
            "streams": [],
            "managed_runs": [],
            "detached_count": 0,
            "report": f"{label} runtime is not loaded",
        }
    try:
        status = status_fn()
        if isinstance(status, list):
            return {
                "ok": True,
                "active": bool(status),
                "streams": [],
                "managed_runs": [
                    item for item in status if isinstance(item, dict)
                ],
                "detached_count": 0,
            }
        return dict(status)
    except Exception as exc:
        return {"ok": False, "active": False, "error": f"{type(exc).__name__}: {exc}"}


def _runtime_status() -> dict[str, Any]:
    modules = {
        label: _runtime_module_status(label, module_name)
        for label, module_name in _RUNTIME_MODULES.items()
    }
    modules["remote_ros2"] = _remote_ros2_runtime_status()
    modules["remote_ros2_images"] = _remote_ros2_image_runtime_status()
    streams: list[dict[str, Any]] = []
    cv2_streams: list[dict[str, Any]] = []
    reasoning_streams: list[dict[str, Any]] = []
    managed_runs: list[dict[str, Any]] = []
    detached_count = 0
    for label, status in modules.items():
        streams.extend({**item, "runtime": label} for item in status.get("streams", []) if isinstance(item, dict))
        cv2_streams.extend({**item, "runtime": label} for item in status.get("cv2_streams", []) if isinstance(item, dict))
        reasoning_streams.extend({**item, "runtime": label} for item in status.get("reasoning_streams", []) if isinstance(item, dict))
        managed_runs.extend({**item, "runtime": label} for item in status.get("managed_runs", []) if isinstance(item, dict))
        detached_count += int(status.get("detached_count") or 0)
    ok = all(bool(status.get("ok", True)) for status in modules.values())
    active = any(bool(status.get("active")) for status in modules.values())
    reports = [
        str(status.get("report") or status.get("error") or "").strip()
        for status in modules.values()
        if status.get("report") or status.get("error")
    ]
    return {
        "ok": ok,
        "active": active,
        "modules": modules,
        "streams": streams,
        "cv2_streams": cv2_streams,
        "reasoning_streams": reasoning_streams,
        "managed_runs": managed_runs,
        "detached_count": detached_count,
        "report": "; ".join(reports),
    }


def _spatial_viewer_runtime_status() -> dict[str, Any]:
    """Return focused spatial-viewer outputs without probing remote services."""
    labels = ("viewer", "slam", "imu_viewer")
    modules = {
        label: _runtime_module_status(label, _RUNTIME_MODULES[label])
        for label in labels
    }
    return _pack_spatial_viewer_scenes({
        "ok": all(bool(status.get("ok", True)) for status in modules.values()),
        "active": any(bool(status.get("active")) for status in modules.values()),
        "modules": modules,
        "report": "; ".join(
            str(status.get("report") or status.get("error") or "").strip()
            for status in modules.values()
            if status.get("report") or status.get("error")
        ),
    })


_SPATIAL_POINT_FIELDS = {
    "points", "current_points", "floor_points", "occupied_points",
    "particles", "dynamic_points", "dynamic_velocities",
}
_SPATIAL_COLOR_FIELDS = {
    "colors", "current_colors", "floor_colors", "occupied_colors",
}


def _pack_numeric_rows(value: Any, *, color: bool = False) -> Any:
    if not isinstance(value, list) or len(value) < 64:
        return value
    rows = [row for row in value if isinstance(row, (list, tuple)) and len(row) >= 2]
    if len(rows) != len(value):
        return value
    try:
        if color:
            values = array("B")
            for row in rows:
                components = [float(row[index] if index < len(row) else 0.0) for index in range(3)]
                if not all(math.isfinite(component) for component in components):
                    return value
                values.extend(max(0, min(255, round(component * 255.0))) for component in components)
            encoding = "uint8-normalized-base64"
        else:
            values = array("f")
            for row in rows:
                components = [float(row[index] if index < len(row) else 0.0) for index in range(3)]
                if not all(math.isfinite(component) for component in components):
                    return value
                values.extend(components)
            if sys.byteorder != "little":
                values.byteswap()
            encoding = "float32-le-base64"
    except (OverflowError, TypeError, ValueError):
        return value
    return {
        "kind": "blacknode.numeric-rows",
        "schema_version": 1,
        "encoding": encoding,
        "components": 3,
        "count": len(rows),
        "data": base64.b64encode(values.tobytes()).decode("ascii"),
    }


def _pack_spatial_viewer_scenes(status: dict[str, Any]) -> dict[str, Any]:
    packed = dict(status)
    packed_modules: dict[str, Any] = {}
    for label, module_status in dict(status.get("modules") or {}).items():
        module_copy = dict(module_status)
        packed_outputs = []
        for item in module_status.get("node_outputs", []):
            if not isinstance(item, dict):
                continue
            item_copy = dict(item)
            outputs = dict(item.get("outputs") or {})
            scene = dict(outputs.get("scene") or {})
            for field in _SPATIAL_POINT_FIELDS | _SPATIAL_COLOR_FIELDS:
                if field in scene:
                    scene[field] = _pack_numeric_rows(
                        scene[field],
                        color=field in _SPATIAL_COLOR_FIELDS,
                    )
            outputs["scene"] = scene
            item_copy["outputs"] = outputs
            packed_outputs.append(item_copy)
        module_copy["node_outputs"] = packed_outputs
        packed_modules[label] = module_copy
    packed["modules"] = packed_modules
    return packed


def _stop_runtime_module(label: str, module_name: str) -> dict[str, Any]:
    stop_fn = _runtime_callable(label, module_name, "stop_runtime_services")
    if stop_fn is None:
        return {
            "ok": True,
            "stopped": {"streams": 0, "managed_runs": 0, "detached": 0, "cv2_streams": 0, "reasoning_streams": 0},
            "report": f"{label} runtime is not loaded",
        }
    try:
        result = dict(stop_fn())
        stopped = result.get("stopped")
        if isinstance(stopped, (int, float)):
            result["stopped"] = {"managed_runs": int(stopped)}
        return result
    except Exception as exc:
        return {
            "ok": False,
            "stopped": {"streams": 0, "managed_runs": 0, "detached": 0, "cv2_streams": 0, "reasoning_streams": 0},
            "error": f"{type(exc).__name__}: {exc}",
        }


_RUNTIME_STOP_TIMEOUT_SECONDS = 12.0


def _stop_runtime_services() -> dict[str, Any]:
    stop_tasks: dict[str, Callable[[], dict[str, Any]]] = {
        label: (lambda label=label, module_name=module_name: _stop_runtime_module(label, module_name))
        for label, module_name in _RUNTIME_MODULES.items()
    }
    stop_tasks["remote_ros2"] = _stop_remote_ros2_services
    stop_tasks["remote_ros2_images"] = _stop_remote_ros2_image_services

    # Package and remote services are independent managed runtimes. Stop them
    # concurrently and bound the HTTP response so one faulty package cannot
    # strand the editor in "Stopping live" forever. A timed-out handler keeps
    # finishing in its worker while the editor receives an actionable result.
    executor = ThreadPoolExecutor(max_workers=max(1, min(16, len(stop_tasks))))
    future_labels = {
        executor.submit(stop_task): label
        for label, stop_task in stop_tasks.items()
    }
    completed, pending = wait(
        future_labels,
        timeout=_RUNTIME_STOP_TIMEOUT_SECONDS,
    )
    completed_results: dict[str, dict[str, Any]] = {}
    for future in completed:
        label = future_labels[future]
        try:
            completed_results[label] = dict(future.result())
        except Exception as exc:
            completed_results[label] = {
                "ok": False,
                "stopped": {},
                "error": f"{type(exc).__name__}: {exc}",
            }
    for future in pending:
        label = future_labels[future]
        future.cancel()
        completed_results[label] = {
            "ok": False,
            "stopped": {},
            "error": (
                f"{label} stop is still completing in the background after "
                f"{_RUNTIME_STOP_TIMEOUT_SECONDS:g} seconds"
            ),
        }
    executor.shutdown(wait=False, cancel_futures=True)
    modules = {
        label: completed_results[label]
        for label in stop_tasks
    }
    stopped = {"streams": 0, "managed_runs": 0, "detached": 0, "cv2_streams": 0, "reasoning_streams": 0}
    for result in modules.values():
        raw_stopped = result.get("stopped") if isinstance(result.get("stopped"), dict) else {}
        for key in stopped:
            value = raw_stopped.get(key) or 0
            # Package runtimes should return numeric counters, but older or
            # independently updated packages may return a structured stop
            # result here. Preserve Stop All and extract its nested count.
            if isinstance(value, dict):
                value = value.get("stopped") or 0
            try:
                stopped[key] += int(value)
            except (TypeError, ValueError):
                continue
    ok = all(bool(result.get("ok", True)) for result in modules.values())
    reports = [
        str(result.get("report") or result.get("error") or "").strip()
        for result in modules.values()
        if result.get("report") or result.get("error")
    ]
    return {
        "ok": ok,
        "stopped": stopped,
        "modules": modules,
        "report": "; ".join(reports) or (
            f"stopped {stopped['streams']} stream(s), "
            f"{stopped['cv2_streams']} CV2 stream(s), "
            f"{stopped['reasoning_streams']} reasoning stream(s), "
            f"{stopped['managed_runs']} run process(es), "
            f"{stopped['detached']} detached process(es)"
        ),
    }


_CV2_STREAM_LIVE_CONFIG_KEYS = {
    "source_url",
    "object_color",
    "use_reasoning_color",
    "target",
    "reasoning_state_url",
    "target_update_seconds",
    "label",
    "min_area",
    "max_detections",
    "blur",
    "morphology_iters",
    "show_follow_guides",
    "follow_target_x",
    "follow_deadband",
    "max_fps",
    "max_width",
    "jpeg_quality",
}


def _push_live_node_param_update(meta: dict[str, Any], key: str, value: Any, old_params: dict[str, Any]) -> None:
    if meta.get("type") == "ROS2JointSliders" and key in {"targets", "armed"}:
        run_id = str(old_params.get("run_id") or meta.get("params", {}).get("run_id") or "joint_sliders").strip() or "joint_sliders"
        fn_name = "set_joint_slider_targets" if key == "targets" else "set_joint_slider_armed"
        update_fn = _runtime_callable("joint_control", _RUNTIME_MODULES["joint_control"], fn_name)
        if update_fn is None:
            return
        try:
            result = update_fn(run_id, value)
        except Exception as exc:  # noqa: BLE001
            print(f"[blacknode] live joint-slider update failed for {run_id}.{key}: {type(exc).__name__}: {exc}")
            return
        if not result.get("ok", True) and "not running" not in str(result.get("report") or ""):
            print(f"[blacknode] live joint-slider update for {run_id}.{key}: {result.get('report')}")
        return
    if meta.get("type") in {
        "ROS2LeaderFollower",
        "ROS2JointController",
    }:
        update_fn = _runtime_callable("ros2_live", _RUNTIME_MODULES["ros2_live"], "update_leader_follower_config")
        if update_fn is None:
            return
        run_id = str(old_params.get("run_id") or meta.get("params", {}).get("run_id") or "leader_follower").strip() or "leader_follower"
        try:
            result = update_fn(run_id, {key: value})
        except Exception as exc:  # noqa: BLE001
            print(f"[blacknode] live leader-follower update failed for {run_id}.{key}: {type(exc).__name__}: {exc}")
            return
        if not result.get("ok", True) and "not running" not in str(result.get("report") or ""):
            print(f"[blacknode] live leader-follower update failed for {run_id}.{key}: {result.get('error') or result.get('report')}")
        return
    if meta.get("type") == "DepthCloudViewer" and key == "color_mode":
        update_fn = _runtime_callable("viewer", _RUNTIME_MODULES["viewer"], "set_viewer_color_mode")
        if update_fn is None:
            return
        viewer_id = str(
            old_params.get("viewer_id")
            or meta.get("params", {}).get("viewer_id")
            or "depth_cloud_viewer"
        ).strip() or "depth_cloud_viewer"
        try:
            update_fn(viewer_id, value)
        except Exception as exc:  # noqa: BLE001
            print(f"[blacknode] live depth-cloud color update failed for {viewer_id}: {type(exc).__name__}: {exc}")
        return
    if meta.get("type") != "TrackingObject" or key not in _CV2_STREAM_LIVE_CONFIG_KEYS:
        return
    runtime = _runtime_module(_RUNTIME_MODULES["vision"])
    if runtime is None or not hasattr(runtime, "update_color_stream_config"):
        return
    stream_id = str(old_params.get("stream_id") or meta.get("params", {}).get("stream_id") or "cube_tracker").strip() or "cube_tracker"
    update_key = "target_text" if key == "target" else key
    try:
        result = runtime.update_color_stream_config(stream_id, {update_key: value})
    except Exception as exc:  # noqa: BLE001
        print(f"[blacknode] live CV2 param update failed for {stream_id}.{key}: {type(exc).__name__}: {exc}")
        return
    if not result.get("ok", True):
        print(f"[blacknode] live CV2 param update failed for {stream_id}.{key}: {result.get('error') or result.get('report')}")


def _raise_if_stopped(stop_event: threading.Event | None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise _CookStopped("stopped")


def _load_api_keys() -> None:
    global _api_keys
    if not os.path.exists(_KEYS_PATH):
        return
    try:
        with open(_KEYS_PATH) as f:
            _api_keys = json.load(f)
        for provider, key in _api_keys.items():
            env_var = _PROVIDER_ENV.get(provider)
            # Preserve credentials already configured in the launching terminal.
            # Saved editor keys are only copied into otherwise-empty variables.
            if env_var and key and not os.environ.get(env_var):
                os.environ[env_var] = key
                _injected_api_key_envs.add(env_var)
        loaded = [p for p, k in _api_keys.items() if k]
        if loaded:
            print(f"[blacknode] Loaded API keys for: {', '.join(loaded)}")
    except Exception as e:
        print(f"[blacknode] Could not load api_keys.json: {e}")


def _save_api_keys() -> None:
    try:
        with open(_KEYS_PATH, "w") as f:
            json.dump(_api_keys, f, indent=2)
    except Exception as e:
        print(f"[blacknode] Could not save api_keys.json: {e}")


def _api_key_status() -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for provider, env_var in _PROVIDER_ENV.items():
        saved = bool(_api_keys.get(provider))
        environment = bool(env_var and os.environ.get(env_var))
        external_environment = environment and env_var not in _injected_api_key_envs
        source = "environment" if external_environment else "saved" if saved else "missing"
        status[provider] = {
            "configured": saved or environment or not env_var,
            "source": source if env_var else "local",
            "env_var": env_var,
        }
    return status


_load_api_keys()

# ── Custom model persistence ──────────────────────────────────────────────────

_CUSTOM_MODELS_PATH = os.path.join(os.path.dirname(__file__), "custom_models.json")
_custom_models: list[str] = []


def _load_custom_models() -> None:
    global _custom_models
    if not os.path.exists(_CUSTOM_MODELS_PATH):
        return
    try:
        with open(_CUSTOM_MODELS_PATH) as f:
            _custom_models = json.load(f)
    except Exception as e:
        print(f"[blacknode] Could not load custom_models.json: {e}")


def _save_custom_models() -> None:
    try:
        with open(_CUSTOM_MODELS_PATH, "w") as f:
            json.dump(_custom_models, f, indent=2)
    except Exception as e:
        print(f"[blacknode] Could not save custom_models.json: {e}")


class AddCustomModelReq(BaseModel):
    value: str


_load_custom_models()

# ── Workspace onboarding persistence ─────────────────────────────────────────

_ONBOARDING_PATH = Path(__file__).resolve().parents[1] / ".blacknode" / "onboarding.json"
_onboarding_state: dict[str, bool] = {"package_welcome_seen": False}


def _load_onboarding_state() -> None:
    global _onboarding_state
    if not _ONBOARDING_PATH.exists():
        _onboarding_state = {"package_welcome_seen": False}
        return
    try:
        payload = json.loads(_ONBOARDING_PATH.read_text(encoding="utf-8"))
        _onboarding_state = {
            "package_welcome_seen": bool(payload.get("package_welcome_seen", False)),
        }
    except Exception as e:
        _onboarding_state = {"package_welcome_seen": False}
        print(f"[blacknode] Could not load onboarding state: {e}")


def _save_onboarding_state() -> None:
    try:
        _ONBOARDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = _ONBOARDING_PATH.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(_onboarding_state, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(_ONBOARDING_PATH)
    except Exception as e:
        print(f"[blacknode] Could not save onboarding state: {e}")


_load_onboarding_state()


def _toolbox_port_sort_key(port: str) -> tuple[int, str]:
    match = re.fullmatch(r"tool_(\d+)", str(port))
    return (int(match.group(1)), str(port)) if match else (999_999, str(port))


def _sync_toolbox_ports(toolbox_meta: dict, edges: list[dict] | None = None) -> None:
    """Keep ToolBox metadata dynamic and remove disconnected tool slots."""
    fn = _NODE_REGISTRY.get("ToolBox")
    inputs = [
        str(port)
        for port in list(toolbox_meta.get("inputs") or [])
        if str(port).startswith("tool_")
    ]
    if edges is not None:
        connected = sorted({
            str(e.get("to_port"))
            for e in edges
            if e.get("to") == toolbox_meta.get("id") and str(e.get("to_port", "")).startswith("tool_")
        }, key=_toolbox_port_sort_key)
        inputs = connected

    input_types = dict(toolbox_meta.get("input_types", {}))
    toolbox_meta["inputs"] = inputs
    toolbox_meta["input_types"] = {port: input_types.get(port, "Fn") for port in inputs}
    toolbox_meta["outputs"] = getattr(fn, "_bn_outputs", ["tools"])
    toolbox_meta["output_types"] = getattr(fn, "_bn_output_types", {"tools": "List"})
    toolbox_meta["input_defaults"] = {}


def _joint_port_sort_key(port: str) -> tuple[int, str]:
    match = re.fullmatch(r"joint_(\d+)", str(port))
    return (int(match.group(1)), str(port)) if match else (999_999, str(port))


def _sync_joint_list_ports(meta: dict, edges: list[dict] | None = None) -> None:
    """Keep RobotJointList metadata aligned with connected numbered sockets."""
    fn = _NODE_REGISTRY.get("RobotJointList")
    inputs = [str(port) for port in list(meta.get("inputs") or []) if str(port).startswith("joint_")]
    if edges is not None:
        inputs = sorted({
            str(edge.get("to_port"))
            for edge in edges
            if edge.get("to") == meta.get("id") and str(edge.get("to_port", "")).startswith("joint_")
        }, key=_joint_port_sort_key)
    input_types = dict(meta.get("input_types", {}))
    meta["inputs"] = inputs
    meta["input_types"] = {port: input_types.get(port, "Dict") for port in inputs}
    meta["outputs"] = getattr(fn, "_bn_outputs", ["joints", "count", "report"])
    meta["output_types"] = getattr(fn, "_bn_output_types", {"joints": "List", "count": "Int", "report": "Text"})
    meta["input_defaults"] = {}


def _sync_variadic_ports(meta: dict, edges: list[dict] | None = None) -> None:
    spec = meta.get("variadic_input") if isinstance(meta.get("variadic_input"), dict) else {}
    prefix = str(spec.get("prefix") or "item").rstrip("_")
    port_type = str(spec.get("type") or "Any")
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    fn = _NODE_REGISTRY.get(str(meta.get("type") or ""))
    base_inputs = list(getattr(fn, "_bn_inputs", []))
    dynamic = [str(port) for port in meta.get("inputs", []) if pattern.fullmatch(str(port))]
    if edges is not None:
        dynamic = sorted({
            str(edge.get("to_port")) for edge in edges
            if edge.get("to") == meta.get("id") and pattern.fullmatch(str(edge.get("to_port") or ""))
        }, key=lambda port: int(pattern.fullmatch(port).group(1)))
    meta["inputs"] = [*base_inputs, *dynamic]
    base_types = dict(getattr(fn, "_bn_input_types", {}))
    meta["input_types"] = {**base_types, **{port: port_type for port in dynamic}}
    meta["input_defaults"] = dict(getattr(fn, "_bn_input_defaults", {}))


def _default_visual_agent_loop_subgraph() -> dict:
    node_meta = {
        "loop_in": {
            "id": "loop_in", "type": "SubnetInput", "params": {},
            "pos": [40, 220],
            "inputs": [],
            "outputs": ["prompt", "system", "model", "tools", "max_tokens", "max_iter"],
            "input_types": {},
            "output_types": {
                "prompt": "Text",
                "system": "Text",
                "model": "Model",
                "tools": "List",
                "max_tokens": "Int",
                "max_iter": "Int",
            },
            "input_defaults": {},
        },
        "messages": {
            "id": "messages", "type": "AgentMessages", "params": {},
            "pos": [300, 120],
            "inputs": ["prompt"],
            "outputs": ["messages"],
            "input_types": {"prompt": "Text"},
            "output_types": {"messages": "List"},
            "input_defaults": {},
        },
        "chat": {
            "id": "chat", "type": "AgentChatStep", "params": {},
            "pos": [560, 100],
            "inputs": ["messages", "system", "model", "tools", "max_tokens"],
            "outputs": ["assistant_text", "tool_calls", "stop_reason", "step"],
            "input_types": {
                "messages": "List",
                "system": "Text",
                "model": "Model",
                "tools": "List",
                "max_tokens": "Int",
            },
            "output_types": {
                "assistant_text": "Text",
                "tool_calls": "List",
                "stop_reason": "Text",
                "step": "Dict",
            },
            "input_defaults": {"model": "claude-sonnet-4-6", "max_tokens": 1024},
        },
        "iteration": {
            "id": "iteration", "type": "AgentIteration", "params": {"start": 1},
            "pos": [560, 360],
            "inputs": ["start"],
            "outputs": ["iteration"],
            "input_types": {"start": "Int"},
            "output_types": {"iteration": "Int"},
            "input_defaults": {"start": 1},
        },
        "dispatch": {
            "id": "dispatch", "type": "ToolDispatch", "params": {},
            "pos": [840, 80],
            "inputs": ["tool_calls", "tools"],
            "outputs": ["tool_results", "steps"],
            "input_types": {"tool_calls": "List", "tools": "List"},
            "output_types": {"tool_results": "List", "steps": "List"},
            "input_defaults": {},
        },
        "stop": {
            "id": "stop", "type": "AgentStopCheck", "params": {},
            "pos": [840, 330],
            "inputs": ["stop_reason", "tool_calls", "iteration", "max_iter"],
            "outputs": ["continue", "done", "reason"],
            "input_types": {
                "stop_reason": "Text",
                "tool_calls": "List",
                "iteration": "Int",
                "max_iter": "Int",
            },
            "output_types": {"continue": "Bool", "done": "Bool", "reason": "Text"},
            "input_defaults": {"iteration": 1, "max_iter": 5},
        },
        "append": {
            "id": "append", "type": "AgentAppendMessages", "params": {},
            "pos": [1120, 120],
            "inputs": ["messages", "model", "assistant_text", "tool_calls", "tool_results"],
            "outputs": ["messages"],
            "input_types": {
                "messages": "List",
                "model": "Model",
                "assistant_text": "Text",
                "tool_calls": "List",
                "tool_results": "List",
            },
            "output_types": {"messages": "List"},
            "input_defaults": {"model": "claude-sonnet-4-6"},
        },
        "final": {
            "id": "final", "type": "AgentFinalAnswer", "params": {},
            "pos": [1400, 150],
            "inputs": ["messages", "system", "model", "max_tokens", "assistant_text", "stop_reason", "reason", "tool_calls"],
            "outputs": ["result", "step"],
            "input_types": {
                "messages": "List",
                "system": "Text",
                "model": "Model",
                "max_tokens": "Int",
                "assistant_text": "Text",
                "stop_reason": "Text",
                "reason": "Text",
                "tool_calls": "List",
            },
            "output_types": {"result": "Text", "step": "Dict"},
            "input_defaults": {"model": "claude-sonnet-4-6", "max_tokens": 1024},
        },
        "loop_out": {
            "id": "loop_out", "type": "SubnetOutput", "params": {},
            "pos": [1680, 180],
            "inputs": ["result", "steps"],
            "outputs": [],
            "input_types": {"result": "Text", "steps": "List"},
            "output_types": {},
            "input_defaults": {},
        },
    }
    edges = [
        {"from": "loop_in", "from_port": "prompt", "to": "messages", "to_port": "prompt"},
        {"from": "messages", "from_port": "messages", "to": "chat", "to_port": "messages"},
        {"from": "loop_in", "from_port": "system", "to": "chat", "to_port": "system"},
        {"from": "loop_in", "from_port": "model", "to": "chat", "to_port": "model"},
        {"from": "loop_in", "from_port": "tools", "to": "chat", "to_port": "tools"},
        {"from": "loop_in", "from_port": "max_tokens", "to": "chat", "to_port": "max_tokens"},
        {"from": "chat", "from_port": "tool_calls", "to": "dispatch", "to_port": "tool_calls"},
        {"from": "loop_in", "from_port": "tools", "to": "dispatch", "to_port": "tools"},
        {"from": "messages", "from_port": "messages", "to": "append", "to_port": "messages"},
        {"from": "loop_in", "from_port": "model", "to": "append", "to_port": "model"},
        {"from": "chat", "from_port": "assistant_text", "to": "append", "to_port": "assistant_text"},
        {"from": "chat", "from_port": "tool_calls", "to": "append", "to_port": "tool_calls"},
        {"from": "dispatch", "from_port": "tool_results", "to": "append", "to_port": "tool_results"},
        {"from": "chat", "from_port": "stop_reason", "to": "stop", "to_port": "stop_reason"},
        {"from": "chat", "from_port": "tool_calls", "to": "stop", "to_port": "tool_calls"},
        {"from": "iteration", "from_port": "iteration", "to": "stop", "to_port": "iteration"},
        {"from": "loop_in", "from_port": "max_iter", "to": "stop", "to_port": "max_iter"},
        {"from": "append", "from_port": "messages", "to": "final", "to_port": "messages"},
        {"from": "loop_in", "from_port": "system", "to": "final", "to_port": "system"},
        {"from": "loop_in", "from_port": "model", "to": "final", "to_port": "model"},
        {"from": "loop_in", "from_port": "max_tokens", "to": "final", "to_port": "max_tokens"},
        {"from": "chat", "from_port": "assistant_text", "to": "final", "to_port": "assistant_text"},
        {"from": "chat", "from_port": "stop_reason", "to": "final", "to_port": "stop_reason"},
        {"from": "chat", "from_port": "tool_calls", "to": "final", "to_port": "tool_calls"},
        {"from": "stop", "from_port": "reason", "to": "final", "to_port": "reason"},
        {"from": "final", "from_port": "result", "to": "loop_out", "to_port": "result"},
        {"from": "dispatch", "from_port": "steps", "to": "loop_out", "to_port": "steps"},
    ]
    return {"node_meta": node_meta, "edges": edges}


def _ensure_edge(edges: list[dict], from_id: str, from_port: str, to_id: str, to_port: str) -> None:
    if not any(
        e.get("from") == from_id
        and e.get("from_port") == from_port
        and e.get("to") == to_id
        and e.get("to_port") == to_port
        for e in edges
    ):
        edges.append({"from": from_id, "from_port": from_port, "to": to_id, "to_port": to_port})


def _migrate_visual_agent_loop_subgraph(subnet_meta: dict) -> None:
    subgraph = subnet_meta.setdefault("subgraph", {"node_meta": {}, "edges": []})
    inner_meta = subgraph.setdefault("node_meta", {})
    edges = subgraph.setdefault("edges", [])

    if "iter_one" in inner_meta and "iteration" not in inner_meta:
        old = inner_meta.pop("iter_one")
        inner_meta["iteration"] = {
            **old,
            "id": "iteration",
            "type": "AgentIteration",
            "params": {"start": old.get("params", {}).get("value", 1)},
            "inputs": ["start"],
            "outputs": ["iteration"],
            "input_types": {"start": "Int"},
            "output_types": {"iteration": "Int"},
            "input_defaults": {"start": 1},
        }
        for edge in edges:
            if edge.get("from") == "iter_one":
                edge["from"] = "iteration"
            if edge.get("from") == "iteration" and edge.get("from_port") == "value":
                edge["from_port"] = "iteration"

    final = inner_meta.get("final")
    if final:
        final["inputs"] = ["messages", "system", "model", "max_tokens", "assistant_text", "stop_reason", "reason", "tool_calls"]
        final["input_types"] = {
            **final.get("input_types", {}),
            "messages": "List",
            "system": "Text",
            "model": "Model",
            "max_tokens": "Int",
            "assistant_text": "Text",
            "stop_reason": "Text",
            "reason": "Text",
            "tool_calls": "List",
        }
        final["input_defaults"] = {**final.get("input_defaults", {}), "model": "claude-sonnet-4-6", "max_tokens": 1024}

    _ensure_edge(edges, "chat", "assistant_text", "append", "assistant_text")
    _ensure_edge(edges, "iteration", "iteration", "stop", "iteration")
    _ensure_edge(edges, "chat", "assistant_text", "final", "assistant_text")
    _ensure_edge(edges, "chat", "stop_reason", "final", "stop_reason")
    _ensure_edge(edges, "chat", "tool_calls", "final", "tool_calls")
    _ensure_edge(edges, "stop", "reason", "final", "reason")


def _sync_subgraph_node_ports(subnet_meta: dict) -> None:
    """Rebuild a Subnet node's inputs/outputs from its single boundary nodes.

    SubnetInput outputs  → outer Subnet inputs
    SubnetOutput inputs  → outer Subnet outputs
    """
    subnet_meta.setdefault("subgraph", {"node_meta": {}, "edges": []})
    if subnet_meta.get("type") == "SubnetAsTool":
        params = subnet_meta.setdefault("params", {})
        params["name"] = params.get("name") or params.get("subnet_label") or params.get("label") or "tool"
        params.setdefault("description", "")
        fn = _NODE_REGISTRY.get("SubnetAsTool")
        subnet_meta["inputs"]         = getattr(fn, "_bn_inputs", ["name", "description"])
        subnet_meta["outputs"]        = getattr(fn, "_bn_outputs", ["fn"])
        subnet_meta["input_types"]    = getattr(fn, "_bn_input_types", {"name": "Text", "description": "Text"})
        subnet_meta["output_types"]   = getattr(fn, "_bn_output_types", {"fn": "Fn"})
        subnet_meta["input_defaults"] = getattr(fn, "_bn_input_defaults", {"name": "tool"})
        return

    if subnet_meta.get("type") == "VisualAgentLoop":
        if not subnet_meta.get("subgraph", {}).get("node_meta"):
            subnet_meta["subgraph"] = _default_visual_agent_loop_subgraph()
        else:
            _migrate_visual_agent_loop_subgraph(subnet_meta)
        fn = _NODE_REGISTRY.get("VisualAgentLoop")
        subnet_meta["inputs"]         = getattr(fn, "_bn_inputs", [])
        subnet_meta["outputs"]        = getattr(fn, "_bn_outputs", ["result", "steps"])
        subnet_meta["input_types"]    = getattr(fn, "_bn_input_types", {})
        subnet_meta["output_types"]   = getattr(fn, "_bn_output_types", {})
        subnet_meta["input_defaults"] = getattr(fn, "_bn_input_defaults", {})
        return

    subgraph = subnet_meta.get("subgraph", {})
    inner_meta = subgraph.get("node_meta", {})
    inputs, outputs = [], []
    in_types: dict[str, str] = {}
    out_types: dict[str, str] = {}
    for m in inner_meta.values():
        if m["type"] == "SubnetInput":
            for port in m.get("outputs", []):
                if port not in inputs:
                    inputs.append(port)
                    in_types[port] = m.get("output_types", {}).get(port, "Any")
        elif m["type"] == "SubnetOutput":
            for port in m.get("inputs", []):
                if port not in outputs:
                    outputs.append(port)
                    out_types[port] = m.get("input_types", {}).get(port, "Any")
    subnet_meta["inputs"]         = inputs
    subnet_meta["outputs"]        = outputs
    subnet_meta["input_types"]    = in_types
    subnet_meta["output_types"]   = out_types
    subnet_meta["input_defaults"] = {}


def _meta_fingerprint(meta: dict) -> str:
    fields = {
        "params": meta.get("params", {}),
        "inputs": meta.get("inputs", []),
        "outputs": meta.get("outputs", []),
        "input_types": meta.get("input_types", {}),
        "output_types": meta.get("output_types", {}),
        "input_defaults": meta.get("input_defaults", {}),
        "subgraph": meta.get("subgraph", None),
    }
    return json.dumps(fields, sort_keys=True, default=str)


def _sync_dynamic_node_meta(meta: dict, edges: list[dict] | None = None) -> bool:
    """Refresh dynamic node metadata and mirror it into the runtime graph entry."""
    before = _meta_fingerprint(meta)
    fn = _NODE_REGISTRY.get(str(meta.get("type") or ""))
    declared_variadic = getattr(fn, "_bn_variadic_input", None)
    if declared_variadic:
        meta["variadic_input"] = dict(declared_variadic)
    if meta.get("type") in _SUBGRAPH_NODE_TYPES:
        _sync_subgraph_node_ports(meta)
    elif meta.get("type") in _TOOLBOX_NODE_TYPES:
        _sync_toolbox_ports(meta, edges)
    elif meta.get("type") in _JOINT_LIST_NODE_TYPES:
        _sync_joint_list_ports(meta, edges)
    elif isinstance(meta.get("variadic_input"), dict):
        _sync_variadic_ports(meta, edges)
    changed = before != _meta_fingerprint(meta)

    node_id = meta.get("id")
    if node_id in _session.graph._nodes:
        entry = _session.graph._nodes[node_id]
        entry["type"] = meta.get("type")
        entry["params"] = dict(meta.get("params", {}))
        if meta.get("type") in _SUBGRAPH_NODE_TYPES:
            entry["subgraph"] = meta.get("subgraph", {"node_meta": {}, "edges": []})
    return changed


def _enqueue_editor_action(action_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    action = {
        "id": str(uuid.uuid4()),
        "type": action_type,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "payload": payload or {},
    }
    with _editor_action_lock:
        _editor_action_queue.append(action)
        del _editor_action_queue[:-100]
    return action


def _broadcast_learned_node_event(event_type: str, name: str) -> dict[str, Any]:
    event = {
        "type": event_type,
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _learned_node_event_lock:
        subscribers = list(_learned_node_event_subscribers)
    for subscriber in subscribers:
        subscriber.put(event)
    return event


if not _HOSTED_MODE:
    _load()   # restore the trusted local session on startup


@app.get("/healthz")
def editor_health():
    return {"status": "ok", "mode": "hosted" if _HOSTED_MODE else "local"}


@app.get("/readyz")
def editor_readiness():
    return {"status": "ready", "mode": "hosted" if _HOSTED_MODE else "local"}


@app.get("/hosted/status")
def hosted_status():
    return {
        "hosted": _HOSTED_MODE,
        "workspace_persistence": "session" if _HOSTED_MODE else "local",
        "execution": "cloud-only" if _HOSTED_MODE else "local-and-cloud",
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/node-types")
def list_node_types():
    return sorted(_NODE_REGISTRY.keys())


def _category_for_node(fn: Any) -> str:
    module = getattr(fn, "__module__", "")
    module_categories = {
        "blacknode.nodes.values": "Values",
        "blacknode.nodes.ai": "AI",
        "blacknode.nodes.api": "API",
        "blacknode.nodes.core": "Core",
        "blacknode.nodes.database": "Database",
        "blacknode.nodes.flow": "Flow",
        "blacknode.nodes.io": "IO",
        "blacknode.nodes.math": "Math",
        "blacknode.nodes.nvidia": "NVIDIA",
        "blacknode.nodes.rag": "RAG",
        "blacknode.nodes.routing": "Routing",
        "blacknode.nodes.search": "Search",
        "blacknode.nodes.subnet": "Subnet",
    }
    return getattr(fn, "_bn_category", None) or module_categories.get(module, "Custom")


def _node_def_payload(name: str, fn: Any) -> dict[str, Any]:
    doc = (getattr(fn, "_bn_description", None) or fn.__doc__ or "").strip()
    category = _category_for_node(fn)
    return {
        "type": name,
        "category": category,
        "color": package_category_colors().get(category, ""),
        "package": getattr(fn, "_bn_package", ""),
        "component": getattr(fn, "_bn_component", "") or "",
        "adapter": getattr(fn, "_bn_adapter", "") or "",
        "hidden": bool(getattr(fn, "_bn_hidden", False)),
        "live_capable": bool(getattr(fn, "_bn_live_capable", False)),
        "inputs": getattr(fn, "_bn_inputs", []),
        "outputs": getattr(fn, "_bn_outputs", ["output"]),
        "input_types": getattr(fn, "_bn_input_types", {}),
        "output_types": getattr(fn, "_bn_output_types", {}),
        "input_defaults": getattr(fn, "_bn_input_defaults", {}),
        "input_choices": getattr(fn, "_bn_input_choices", {}),
        "variadic_input": getattr(fn, "_bn_variadic_input", None),
        "primary_inputs": getattr(fn, "_bn_primary_inputs", None),
        "primary_outputs": getattr(fn, "_bn_primary_outputs", None),
        "doc": doc.split("\n", 1)[0] if doc else "",
        "source": getattr(fn, "_bn_source_path", ""),
    }


@app.get("/node-defs")
def list_node_defs():
    definitions = {
        name: _node_def_payload(name, fn)
        for name, fn in sorted(_NODE_REGISTRY.items())
    }
    # Enum metadata is captured when a package module loads, but robot profiles
    # can be created while the editor is running. Refresh Robot's choices from
    # disk for every schema request so Properties and other schema consumers do
    # not require a server restart to discover a newly saved profile.
    robot_definition = definitions.get("Robot")
    if isinstance(robot_definition, dict):
        try:
            profile_ids = [
                str(profile.get("id") or "").strip()
                for profile in _available_robot_profiles({
                    "node_meta": _session.node_meta,
                })
                if str(profile.get("id") or "").strip() not in {"", "auto"}
            ]
        except (OSError, ValueError):
            profile_ids = []
        if profile_ids:
            input_choices = {
                key: list(values)
                for key, values in (robot_definition.get("input_choices") or {}).items()
            }
            input_choices["profile_id"] = profile_ids
            robot_definition["input_choices"] = input_choices
    return definitions

@app.get("/graph")
def get_graph():
    """Return nodes with types always read fresh from registry."""
    nodes = []
    for meta in _session.node_meta.values():
        fn = _NODE_REGISTRY.get(meta["type"])
        _sync_dynamic_node_meta(meta, _session.graph._edges)
        if fn is not None:
            if "promoted_inputs" not in meta and getattr(fn, "_bn_primary_inputs", None) is not None:
                meta["promoted_inputs"] = list(fn._bn_primary_inputs)
            if "promoted_outputs" not in meta and getattr(fn, "_bn_primary_outputs", None) is not None:
                meta["promoted_outputs"] = list(fn._bn_primary_outputs)
        if meta["type"] in _DYNAMIC_PORT_TYPES or isinstance(meta.get("variadic_input"), dict) or fn is None:
            nodes.append({**meta})
        else:
            nodes.append({
                **meta,
                "inputs":         getattr(fn, "_bn_inputs",         meta.get("inputs",         [])),
                "outputs":        getattr(fn, "_bn_outputs",        meta.get("outputs",        [])),
                "input_types":    getattr(fn, "_bn_input_types",    meta.get("input_types",    {})),
                "output_types":   getattr(fn, "_bn_output_types",   meta.get("output_types",   {})),
                "input_defaults": getattr(fn, "_bn_input_defaults", meta.get("input_defaults", {})),
                "live_capable":   bool(getattr(fn, "_bn_live_capable", False)),
            })
    return {
        "nodes": nodes,
        "edges": _session.graph._edges,
        "metadata": dict(_session.metadata),
        "entrypoint": dict(_session.entrypoint) if _session.entrypoint else None,
    }


def _port_schema_snapshot(meta: dict) -> dict[str, Any]:
    return {
        "inputs": list(meta.get("inputs", [])),
        "outputs": list(meta.get("outputs", [])),
        "input_types": dict(meta.get("input_types", {})),
        "output_types": dict(meta.get("output_types", {})),
        "input_defaults": dict(meta.get("input_defaults", {})),
        "variadic_input": copy.deepcopy(meta.get("variadic_input")),
        "live_capable": bool(meta.get("live_capable", False)),
    }


def _schema_change_payload(node_id: str, type_name: str, before: dict, after: dict) -> dict:
    old_inputs = set(before["inputs"])
    new_inputs = set(after["inputs"])
    old_outputs = set(before["outputs"])
    new_outputs = set(after["outputs"])
    return {
        "id": node_id,
        "type": type_name,
        "added_inputs": sorted(new_inputs - old_inputs),
        "removed_inputs": sorted(old_inputs - new_inputs),
        "added_outputs": sorted(new_outputs - old_outputs),
        "removed_outputs": sorted(old_outputs - new_outputs),
        "types_changed": (
            before["input_types"] != after["input_types"]
            or before["output_types"] != after["output_types"]
        ),
        "defaults_changed": before["input_defaults"] != after["input_defaults"],
    }


def _refresh_canvas_node_schemas() -> dict[str, Any]:
    """Persist current registry schemas into every node on the active canvas."""
    updated_nodes: list[dict[str, Any]] = []

    for node_id, meta in _session.node_meta.items():
        type_name = str(meta.get("type") or "")
        fn = _NODE_REGISTRY.get(type_name)
        if fn is None or type_name in _SUBGRAPH_NODE_TYPES:
            continue

        before = _port_schema_snapshot(meta)
        old_inputs = set(before["inputs"])
        inputs = list(getattr(fn, "_bn_inputs", before["inputs"]))
        outputs = list(getattr(fn, "_bn_outputs", before["outputs"]))
        meta["inputs"] = inputs
        meta["outputs"] = outputs
        meta["input_types"] = dict(getattr(fn, "_bn_input_types", before["input_types"]))
        meta["output_types"] = dict(getattr(fn, "_bn_output_types", before["output_types"]))
        meta["input_defaults"] = dict(getattr(fn, "_bn_input_defaults", before["input_defaults"]))
        meta["live_capable"] = bool(getattr(fn, "_bn_live_capable", False))

        declared_variadic = getattr(fn, "_bn_variadic_input", None)
        if declared_variadic is None:
            meta.pop("variadic_input", None)
        else:
            meta["variadic_input"] = dict(declared_variadic)

        # Remove values that belonged to ports deleted from the node definition,
        # while preserving labels and any other editor-only parameters.
        params = dict(meta.get("params", {}))
        for port in old_inputs - set(inputs):
            params.pop(port, None)
        meta["params"] = params

        for key, allowed in (("promoted_inputs", inputs), ("promoted_outputs", outputs)):
            promoted = meta.get(key)
            if isinstance(promoted, list):
                meta[key] = [port for port in promoted if port in allowed]

        _sync_dynamic_node_meta(meta, _session.graph._edges)
        after = _port_schema_snapshot(meta)
        if before != after:
            updated_nodes.append(_schema_change_payload(node_id, type_name, before, after))
            _session.graph._dirty.add(node_id)

    valid_edges: list[dict] = []
    removed_edges: list[dict] = []
    for edge in _session.graph._edges:
        source = _session.node_meta.get(edge.get("from"))
        target = _session.node_meta.get(edge.get("to"))
        source_valid = source is not None and edge.get("from_port") in source.get("outputs", [])
        target_valid = target is not None and edge.get("to_port") in target.get("inputs", [])
        if source_valid and target_valid:
            valid_edges.append(edge)
        else:
            removed_edges.append(dict(edge))
    _session.graph._edges = valid_edges

    # Dynamic nodes can expose an extra connection slot based on the final edge set.
    for meta in _session.node_meta.values():
        _sync_dynamic_node_meta(meta, valid_edges)

    _save()
    return {
        "updated_nodes": updated_nodes,
        "removed_edges": removed_edges,
    }


@app.post("/graph/refresh-node-schemas")
def refresh_canvas_node_schemas():
    report = discover_node_modules([Path(_CUSTOM_NODES_DIR)])
    if report.get("failed"):
        return {
            "ok": False,
            **report,
            "updated_nodes": [],
            "removed_edges": [],
        }
    changes = _refresh_canvas_node_schemas()
    return {
        "ok": True,
        **report,
        **changes,
        "graph": get_graph(),
    }


@app.post("/graph")
def set_graph(req: SetGraphReq):
    _restore_session_from_nodes(
        req.nodes,
        req.edges,
        metadata=req.metadata,
        entrypoint=req.entrypoint,
    )
    _save()
    return get_graph()


def _normalized_required_capabilities(values: list[Any]) -> list[str]:
    capabilities: set[str] = set()
    for value in values:
        name = str(value or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", name):
            raise HTTPException(400, f"Invalid capability name: {name or '(empty)'}")
        capabilities.add(name)
    if len(capabilities) > 32:
        raise HTTPException(400, "A workflow may declare at most 32 capabilities.")
    return sorted(capabilities)


def _normalized_calibration_selection(value: dict[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return None
    profile_id = str(value.get("profile_id") or "").strip()
    hardware_id = str(value.get("hardware_id") or "").strip()
    if not profile_id or not hardware_id:
        raise HTTPException(400, "Calibration selection requires profile_id and hardware_id.")
    if len(profile_id) > 128 or len(hardware_id) > 256:
        raise HTTPException(400, "Calibration selection is too long.")
    return {"profile_id": profile_id, "hardware_id": hardware_id}


@app.patch("/graph/requirements")
def update_workflow_requirements(req: UpdateWorkflowRequirementsReq):
    metadata = dict(_session.metadata)
    metadata["required_capabilities"] = _normalized_required_capabilities(
        req.required_capabilities
    )
    calibration = _normalized_calibration_selection(req.device_calibration)
    if calibration is None:
        metadata.pop("device_calibration", None)
    else:
        metadata["device_calibration"] = calibration
    _session.metadata = metadata
    _save()
    return {"metadata": dict(metadata)}


@app.post("/nodes")
def add_node(req: AddNodeReq):
    if req.type_name in _SUBGRAPH_NODE_TYPES:
        node_id = str(__import__('uuid').uuid4())
        if req.type_name == "Subnet":
            params = {"label": req.params.get("label", "Subnet")}
        elif req.type_name == "SubnetAsTool":
            params = {
                "name": req.params.get("name") or req.params.get("subnet_label") or "tool",
                "description": req.params.get("description", ""),
            }
        else:
            params = dict(req.params)
        meta: dict[str, Any] = {
            "id":           node_id,
            "type":         req.type_name,
            "params":       params,
            "pos":          list(req.pos),
            "inputs":       [],
            "outputs":      [],
            "input_types":  {},
            "output_types": {},
            "input_defaults": {},
            "subgraph":     {"node_meta": {}, "edges": []},
        }
        _sync_subgraph_node_ports(meta)
        _session.node_meta[node_id] = meta
        _session.graph._nodes[node_id] = {
            "type": req.type_name,
            "params": meta["params"],
            "subgraph": meta["subgraph"],
        }
        _session.graph._dirty.add(node_id)
        _save()
        return meta
    if req.type_name not in _NODE_REGISTRY:
        raise HTTPException(400, f"Unknown node type '{req.type_name}'")
    proxy = _session.graph.node(req.type_name, **req.params)
    fn = _NODE_REGISTRY[req.type_name]
    meta = {
        "id":           proxy._id,
        "type":         req.type_name,
        "params":       req.params,
        "pos":          list(req.pos),
        "inputs":         getattr(fn, "_bn_inputs",         []),
        "outputs":        getattr(fn, "_bn_outputs",        ["output"]),
        "input_types":    getattr(fn, "_bn_input_types",    {}),
        "output_types":   getattr(fn, "_bn_output_types",   {}),
        "input_defaults": getattr(fn, "_bn_input_defaults", {}),
        "variadic_input": getattr(fn, "_bn_variadic_input", None),
        "promoted_inputs": list(getattr(fn, "_bn_primary_inputs", None) or []) if getattr(fn, "_bn_primary_inputs", None) is not None else None,
        "promoted_outputs": list(getattr(fn, "_bn_primary_outputs", None) or []) if getattr(fn, "_bn_primary_outputs", None) is not None else None,
    }
    if getattr(fn, "_bn_variadic_input", None):
        meta["variadic_input"] = dict(fn._bn_variadic_input)
        _sync_variadic_ports(meta)
    if req.type_name in _TOOLBOX_NODE_TYPES:
        _sync_toolbox_ports(meta)
    _session.node_meta[proxy._id] = meta
    _save()
    return meta


@app.delete("/nodes/{node_id}")
def remove_node(node_id: str):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    if _session.node_meta[node_id].get("type") == "RobotServo":
        disarm = _runtime_callable(
            "robot_servo_motion",
            _RUNTIME_MODULES["robot_servo_motion"],
            "disarm_servo_motion",
        )
        if disarm is not None:
            disarm(f"robot-servo:{node_id}")
    del _session.node_meta[node_id]
    _session.graph._edges = [
        e for e in _session.graph._edges
        if e["from"] != node_id and e["to"] != node_id
    ]
    _session.graph._nodes.pop(node_id, None)
    _session.graph._dirty.discard(node_id)
    _save()
    return {"ok": True}


@app.patch("/nodes/{node_id}/params")
def update_param(node_id: str, req: UpdateParamReq):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    meta = _session.node_meta[node_id]
    old_params = dict(meta.get("params", {}))
    if (
        meta.get("type") == "RobotServo"
        and req.key in {"robot_id", "profile_id", "servo_id", "joint_name", "units"}
        and old_params.get(req.key) != req.value
    ):
        disarm = _runtime_callable(
            "robot_servo_motion",
            _RUNTIME_MODULES["robot_servo_motion"],
            "disarm_servo_motion",
        )
        if disarm is not None:
            disarm(f"robot-servo:{node_id}")
    meta["params"][req.key] = req.value
    _session.graph._nodes[node_id]["params"][req.key] = req.value
    _session.graph._mark_dirty(node_id)
    # A changed input invalidates every visible result derived from it. The
    # graph cache was already dirtied above; clear persisted node status too so
    # the editor never continues presenting an old dashboard as current.
    invalidated = {node_id}
    pending = [node_id]
    while pending:
        current = pending.pop()
        for edge in _session.graph._edges:
            target = str(edge.get("to") or "")
            if edge.get("from") == current and target and target not in invalidated:
                invalidated.add(target)
                pending.append(target)
    live_armed_targets = {
        str(edge.get("to") or "")
        for edge in _session.graph._edges
        if (
            meta.get("type") == "Bool"
            and req.key == "value"
            and isinstance(req.value, bool)
            and edge.get("from") == node_id
            and edge.get("from_port") == "value"
            and edge.get("to_port") == "armed"
            and str((_session.node_meta.get(str(edge.get("to") or "")) or {}).get("type") or "")
            in {"ROS2LeaderFollower", "ROS2JointController"}
        )
    }
    for invalidated_id in invalidated:
        invalidated_meta = _session.node_meta.get(invalidated_id)
        if invalidated_meta is not None:
            _clear_runtime_status(invalidated_meta)
            if invalidated_meta.get("type") in {
                "ROS2LeaderFollower",
                "ROS2JointController",
            } and invalidated_id != node_id:
                disarm_fn = _runtime_callable("ros2_live", _RUNTIME_MODULES["ros2_live"], "update_leader_follower_config")
                if disarm_fn is not None:
                    run_id = str(invalidated_meta.get("params", {}).get("run_id") or "leader_follower").strip() or "leader_follower"
                    armed = req.value if invalidated_id in live_armed_targets else False
                    try:
                        disarm_fn(run_id, {"armed": armed})
                    except Exception as exc:  # noqa: BLE001
                        action = "update" if invalidated_id in live_armed_targets else "disarm"
                        print(f"[blacknode] could not {action} invalidated leader-follower '{run_id}': {type(exc).__name__}: {exc}")
    _push_live_node_param_update(meta, req.key, req.value, old_params)
    _save()
    return meta


@app.get("/nodes/{node_id}/depth-frame")
def depth_frame(node_id: str):
    meta = _session.node_meta.get(node_id)
    if meta is None or meta.get("type") != "DepthViewer":
        raise HTTPException(404, "DepthViewer node not found")
    status = _session.graph._cache.get((node_id, "status"))
    if not isinstance(status, dict):
        raise HTTPException(409, "Run the DepthViewer once before opening its raw frame")
    frame_url = str(status.get("frame_url") or "").strip()
    parsed = urllib.parse.urlparse(frame_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path != "/frame.bin":
        raise HTTPException(409, "DepthViewer has no supported raw HTTP frame")
    try:
        request = urllib.request.Request(
            frame_url,
            headers={"Accept": "application/vnd.blacknode.metric-depth-frame"},
        )
        with urllib.request.urlopen(request, timeout=2.0) as upstream:
            payload = upstream.read(256 * 1024 * 1024 + 1)
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise HTTPException(502, f"Raw depth frame unavailable: {type(exc).__name__}: {exc}") from exc
    if len(payload) > 256 * 1024 * 1024:
        raise HTTPException(413, "Raw depth frame exceeds 256 MiB")
    if not payload.startswith(b"BNDEPTH1"):
        raise HTTPException(502, "Raw depth source returned an invalid frame")
    return Response(
        content=payload,
        media_type="application/vnd.blacknode.metric-depth-frame",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/nodes/{node_id}/control")
def control_node(node_id: str, req: NodeControlReq):
    meta = _session.node_meta.get(node_id)
    if meta is None:
        raise HTTPException(404, "Node not found")
    if meta.get("type") == "RobotServo":
        action = str(req.action or "").strip().lower()
        if action not in {"arm", "disarm", "joint-command", "status"}:
            raise HTTPException(
                400,
                "RobotServo supports arm, disarm, joint-command, or status",
            )
        run_id = f"robot-servo:{node_id}"
        function_name = {
            "arm": "arm_servo_motion",
            "disarm": "disarm_servo_motion",
            "joint-command": "command_servo_motion",
            "status": "servo_motion_status",
        }[action]
        control_fn = _runtime_callable(
            "robot_servo_motion",
            _RUNTIME_MODULES["robot_servo_motion"],
            function_name,
        )
        if control_fn is None:
            raise HTTPException(503, "blacknode-motion Servo control is not loaded")

        def reject_servo_command(detail: str) -> None:
            disarm_fn = _runtime_callable(
                "robot_servo_motion",
                _RUNTIME_MODULES["robot_servo_motion"],
                "disarm_servo_motion",
            )
            if disarm_fn is not None:
                try:
                    disarm_fn(run_id)
                except Exception:
                    pass
            raise HTTPException(409, detail)

        try:
            if action == "arm":
                robot_id = str(req.payload.get("robot_id") or "").strip()
                profile_id = _monitor_profile_selection(
                    req.payload.get("profile_id")
                    or meta.get("params", {}).get("profile_id")
                )
                if not robot_id.startswith("local-usb-"):
                    raise HTTPException(
                        409,
                        "Standalone Servo motion currently requires a Local USB robot target",
                    )
                target = _local_robot_monitor_target(robot_id, profile_id)
                if target is None or not target.get("available"):
                    raise HTTPException(409, "The selected Local USB robot is unavailable")
                if target.get("raw_mode"):
                    raise HTTPException(409, "Select a calibrated robot profile before motion")
                profile = dict(target.get("profile") or {})
                calibration = dict(target.get("calibration") or {})
                result = dict(control_fn(run_id, {
                    "robot_id": robot_id,
                    "profile": profile,
                    "hardware": dict(target.get("hardware") or {}),
                    "hardware_id": str(target.get("hardware_id") or ""),
                    "calibration": calibration,
                }))
            elif action == "joint-command":
                command = (
                    dict(req.payload.get("command") or {})
                    if isinstance(req.payload.get("command"), dict)
                    else {}
                )
                try:
                    servo_id = int(meta.get("params", {}).get("servo_id") or 1)
                    command_servo_id = int(command.get("servo_id") or 0)
                except (TypeError, ValueError):
                    reject_servo_command("Servo command has an invalid ID")
                joint_name = str(meta.get("params", {}).get("joint_name") or "").strip()
                if command_servo_id != servo_id:
                    reject_servo_command("Servo command ID does not match this node")
                if not joint_name or str(command.get("joint_name") or "") != joint_name:
                    reject_servo_command(
                        "Servo command joint does not match live telemetry"
                    )
                result = dict(control_fn(run_id, command))
            else:
                result = dict(control_fn(run_id))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(409, str(exc)) from exc
        if not result.get("ok", False):
            raise HTTPException(409, str(result.get("report") or "Servo motion was blocked"))
        outputs = {
            key: value
            for key, value in result.items()
            if key != "ok"
        }
        return {"ok": True, "node_id": node_id, "outputs": outputs}
    if meta.get("type") == "ROS2JointSliders":
        if req.action != "joint-command":
            raise HTTPException(400, "ROS2JointSliders supports the joint-command control")
        source_id = str(req.payload.get("source_node_id") or "").strip()
        source_meta = _session.node_meta.get(source_id)
        if source_meta is None or source_meta.get("type") != "RobotServo":
            raise HTTPException(409, "Connect a RobotServo command output before moving")
        connected = any(
            edge.get("from") == source_id
            and edge.get("from_port") == "command"
            and edge.get("to") == node_id
            and edge.get("to_port") == "command"
            for edge in _session.graph._edges
        )
        if not connected:
            raise HTTPException(
                409,
                "Connect RobotServo.command to ROS2JointSliders.command before moving",
            )
        command = (
            dict(req.payload.get("command") or {})
            if isinstance(req.payload.get("command"), dict)
            else {}
        )
        source_params = dict(source_meta.get("params") or {})
        try:
            source_servo_id = int(source_params.get("servo_id") or 1)
            command_servo_id = int(command.get("servo_id") or 0)
        except (TypeError, ValueError) as exc:
            raise HTTPException(409, "The Servo command has an invalid servo ID") from exc
        if command_servo_id != source_servo_id:
            raise HTTPException(409, "The Servo command does not match the connected Servo ID")
        source_joint = str(source_params.get("joint_name") or "").strip()
        command_joint = str(command.get("joint_name") or "").strip()
        if not source_joint or command_joint != source_joint:
            raise HTTPException(
                409,
                "The Servo joint identity is not synchronized with its live telemetry",
            )
        control_fn = _runtime_callable(
            "joint_control",
            _RUNTIME_MODULES["joint_control"],
            "set_joint_slider_command",
        )
        if control_fn is None:
            raise HTTPException(503, "blacknode-motion live joint control is not loaded")
        run_id = str(meta.get("params", {}).get("run_id") or "joint_sliders").strip() or "joint_sliders"
        result = dict(control_fn(run_id, command))
        if not result.get("ok", False):
            raise HTTPException(409, str(result.get("report") or "Joint command was blocked"))
        outputs = {
            "commanded": bool(result.get("commanded")),
            "report": str(result.get("report") or "Joint command accepted"),
        }
        for port, value in outputs.items():
            _session.graph._cache[(node_id, port)] = value
        return {"ok": True, "node_id": node_id, "outputs": outputs}
    if meta.get("type") == "TrajectorySmoother":
        if req.action != "apply":
            raise HTTPException(400, "TrajectorySmoother supports the apply control")
        control_fn = _runtime_callable("dataset", _RUNTIME_MODULES["dataset"], "apply_configured_smoother")
        if control_fn is None:
            raise HTTPException(503, "blacknode-dataset smoother runtime is not loaded")
        params = dict(meta.get("params") or {})
        try:
            outputs = dict(control_fn(
                node_id,
                str(params.get("method") or "spline"),
                float(params.get("strength") if params.get("strength") is not None else 1.0),
                preview_source=str(params.get("preview_source") or "action"),
                preview_joint=str(params.get("preview_joint") or ""),
            ))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        for port, value in outputs.items():
            _session.graph._cache[(node_id, port)] = value
        _session.graph._dirty.discard(node_id)
        return {"ok": True, "node_id": node_id, "outputs": outputs}
    if meta.get("type") == "ACTTraining":
        if req.action not in {"status", "stop"}:
            raise HTTPException(400, "ACTTraining direct controls support status or stop; use Run to start")
        control_fn = _runtime_callable("training", _RUNTIME_MODULES["training"], "control_training_job")
        if control_fn is None:
            raise HTTPException(503, "blacknode-training runtime is not loaded")
        run_id = str(meta.get("params", {}).get("run_id") or "act-training").strip() or "act-training"
        try:
            outputs = dict(control_fn(run_id, req.action))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        for port, value in outputs.items():
            _session.graph._cache[(node_id, port)] = value
        _session.graph._dirty.discard(node_id)
        return {"ok": True, "node_id": node_id, "outputs": outputs}
    if meta.get("type") == "PPOTraining":
        if req.action not in {"status", "stop", "close-viewer"}:
            raise HTTPException(
                400,
                "PPOTraining direct controls support status, stop, or close-viewer; "
                "use Run to start training or replay",
            )
        control_fn = _runtime_callable("training", _RUNTIME_MODULES["training"], "control_ppo_training_job")
        if control_fn is None:
            raise HTTPException(503, "blacknode-training PPO runtime is not loaded")
        run_id = str(meta.get("params", {}).get("run_id") or "so101-reach-ppo").strip() or "so101-reach-ppo"
        try:
            outputs = dict(control_fn(run_id, req.action))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        for port, value in outputs.items():
            _session.graph._cache[(node_id, port)] = value
        _session.graph._dirty.discard(node_id)
        return {"ok": True, "node_id": node_id, "outputs": outputs}
    if meta.get("type") in {
        "Viewer", "LiDARViewer", "DepthCloudViewer", "ReconstructionViewer",
        "FusionViewer", "MapViewer", "SLAM", "IMUViewer",
    }:
        action = str(req.action or "").strip().lower()
        base_actions = (
            {"status", "stop"}
            if meta.get("type") == "IMUViewer"
            else {"status", "clear", "pause", "resume", "stop"}
        )
        if action not in base_actions and not (
            meta.get("type") == "SLAM" and action == "set-goal"
        ):
            raise HTTPException(
                400,
                "Viewer controls support status, clear, pause, resume, or stop; "
                "IMUViewer supports status or stop; "
                "SLAM additionally supports set-goal",
            )
        params = dict(meta.get("params") or {})
        if meta.get("type") == "IMUViewer":
            runtime_id = str(params.get("viewer_id") or "imu_viewer").strip() or "imu_viewer"
            function_name = {
                "status": "imu_viewer_status",
                "stop": "stop_imu_viewer",
            }[action]
            control_fn = _runtime_callable(
                "imu_viewer", _RUNTIME_MODULES["imu_viewer"], function_name,
            )
            if control_fn is None:
                raise HTTPException(503, "blacknode-perception IMU Viewer runtime is not loaded")
            outputs = dict(control_fn(runtime_id))
        elif meta.get("type") in {
            "Viewer", "LiDARViewer", "DepthCloudViewer", "ReconstructionViewer",
            "FusionViewer", "MapViewer",
        }:
            default_runtime_id = {
                "Viewer": "viewer",
                "LiDARViewer": "lidar_viewer",
                "DepthCloudViewer": "depth_cloud_viewer",
                "ReconstructionViewer": "reconstruction_viewer",
                "FusionViewer": "fusion_viewer",
                "MapViewer": "map_viewer",
            }[str(meta.get("type"))]
            runtime_id = str(params.get("viewer_id") or default_runtime_id).strip() or default_runtime_id
            function_name = {
                "status": "viewer_status",
                "clear": "clear_viewer",
                "pause": "pause_viewer",
                "resume": "resume_viewer",
                "stop": "stop_viewer",
            }[action]
            control_fn = _runtime_callable("viewer", _RUNTIME_MODULES["viewer"], function_name)
            if control_fn is None:
                raise HTTPException(503, "blacknode-cuda Viewer runtime is not loaded")
            outputs = dict(control_fn(runtime_id))
        else:
            runtime_id = str(params.get("slam_id") or "slam").strip() or "slam"
            function_name = {
                "status": "slam_status",
                "clear": "clear_slam",
                "pause": "set_mapping",
                "resume": "set_mapping",
                "stop": "stop_slam",
                "set-goal": "set_trajectory_goal",
            }[action]
            control_fn = _runtime_callable("slam", _RUNTIME_MODULES["slam"], function_name)
            if control_fn is None:
                raise HTTPException(503, "blacknode-cuda SLAM runtime is not loaded")
            if action == "set-goal":
                try:
                    goal_x_m = float(req.payload.get("goal_x_m"))
                    goal_y_m = float(req.payload.get("goal_y_m"))
                except (TypeError, ValueError) as exc:
                    raise HTTPException(400, "SLAM goal coordinates must be finite numbers") from exc
                if not math.isfinite(goal_x_m) or not math.isfinite(goal_y_m):
                    raise HTTPException(400, "SLAM goal coordinates must be finite numbers")
                outputs = dict(control_fn(runtime_id, goal_x_m, goal_y_m))
            else:
                outputs = dict(
                    control_fn(runtime_id)
                    if action in {"status", "clear", "stop"}
                    else control_fn(runtime_id, action == "resume")
                )
        for port, value in outputs.items():
            _session.graph._cache[(node_id, port)] = value
        _session.graph._dirty.discard(node_id)
        return {"ok": True, "node_id": node_id, "outputs": outputs}
    if meta.get("type") == "Robot":
        if req.action != "ping":
            raise HTTPException(400, "Robot supports the ping control")
        control_fn = _runtime_callable("robot", _RUNTIME_MODULES["robot"], "identify_robot")
        if control_fn is None:
            raise HTTPException(503, "blacknode-robot runtime is not loaded")
        outputs = dict(control_fn(dict(meta.get("params") or {})))
        return {"ok": True, "node_id": node_id, "outputs": outputs}
    if meta.get("type") != "EpisodeRecorder":
        raise HTTPException(400, "This node does not expose direct controls")
    control_fn = _runtime_callable("dataset", _RUNTIME_MODULES["dataset"], "control_configured_recorder")
    if control_fn is None:
        raise HTTPException(503, "blacknode-dataset recorder runtime is not loaded")
    run_id = str(meta.get("params", {}).get("run_id") or "episode_recorder").strip() or "episode_recorder"
    try:
        outputs = dict(control_fn(run_id, req.action))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "node_id": node_id, "outputs": outputs}


def _pick_directory(initial_path: str = "", title: str = "") -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - depends on the local Python GUI build
        raise RuntimeError(f"native folder picker is unavailable: {exc}") from exc
    initial = Path(str(initial_path or "")).expanduser()
    if not initial.is_dir():
        initial = Path.home()
    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        return str(filedialog.askdirectory(
            parent=root,
            title=str(title or "Choose a folder that will contain Blacknode datasets"),
            initialdir=str(initial),
            mustexist=True,
        ) or "")
    finally:
        root.destroy()


def _pick_file(
    initial_path: str = "",
    title: str = "",
    extensions: list[str] | None = None,
) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - depends on the local Python GUI build
        raise RuntimeError(f"native file picker is unavailable: {exc}") from exc
    initial = Path(str(initial_path or "")).expanduser()
    initial_dir = initial.parent if initial.is_file() else initial
    if not initial_dir.is_dir():
        initial_dir = Path.home()
    clean_extensions = []
    for raw in list(extensions or []):
        extension = str(raw or "").strip().lower()
        if extension and not extension.startswith("."):
            extension = f".{extension}"
        if extension and extension.replace(".", "").isalnum():
            clean_extensions.append(extension)
    filetypes = []
    if clean_extensions:
        label = ", ".join(extension.upper().lstrip(".") for extension in clean_extensions)
        filetypes.append((f"{label} files", " ".join(f"*{extension}" for extension in clean_extensions)))
    filetypes.append(("All files", "*.*"))
    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        return str(filedialog.askopenfilename(
            parent=root,
            title=str(title or "Choose a file"),
            initialdir=str(initial_dir),
            initialfile=initial.name if initial.is_file() else "",
            filetypes=filetypes,
        ) or "")
    finally:
        root.destroy()


@app.post("/filesystem/pick-directory")
def pick_directory(req: PickDirectoryReq):
    try:
        selected = _pick_directory(req.initial_path, req.title)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"selected": selected, "cancelled": not bool(selected)}


@app.post("/filesystem/pick-file")
def pick_file(req: PickFileReq):
    try:
        selected = _pick_file(req.initial_path, req.title, req.extensions)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if selected and req.extensions:
        allowed = {
            (extension if str(extension).startswith(".") else f".{extension}").lower()
            for extension in req.extensions
            if str(extension or "").strip()
        }
        if allowed and Path(selected).suffix.lower() not in allowed:
            raise HTTPException(400, f"Selected file must use one of: {', '.join(sorted(allowed))}")
    return {"selected": selected, "cancelled": not bool(selected)}


def _filesystem_roots() -> list[str]:
    if os.name == "nt":
        return [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").is_dir()]
    return ["/"]


@app.post("/filesystem/browse")
def browse_files(req: BrowseFilesReq):
    raw_path = str(req.path or "").strip()
    requested = Path(raw_path).expanduser() if raw_path and not raw_path.startswith("package://") else Path.home()
    selected = ""
    if requested.is_file():
        selected = str(requested.resolve())
        requested = requested.parent
    if not requested.is_dir():
        requested = Path.home()
    try:
        current = requested.resolve()
        allowed = {
            (extension if str(extension).startswith(".") else f".{extension}").lower()
            for extension in req.extensions
            if str(extension or "").strip()
        }
        entries = []
        for child in current.iterdir():
            try:
                is_directory = child.is_dir()
                if not is_directory and allowed and child.suffix.lower() not in allowed:
                    continue
                entries.append({
                    "name": child.name,
                    "path": str(child.resolve()),
                    "is_directory": is_directory,
                    "size": None if is_directory else child.stat().st_size,
                })
            except (OSError, RuntimeError):
                continue
    except (OSError, RuntimeError) as exc:
        raise HTTPException(400, f"Could not browse {current}: {exc}") from exc
    entries.sort(key=lambda item: (not item["is_directory"], item["name"].casefold()))
    parent = current.parent
    return {
        "path": str(current),
        "parent": str(parent) if parent != current else "",
        "roots": _filesystem_roots(),
        "selected": selected,
        "entries": entries[:5000],
    }


@app.patch("/nodes/{node_id}/ports")
def update_ports(node_id: str, req: UpdatePortsReq):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    meta = _session.node_meta[node_id]
    if meta["type"] not in _NUMBERED_INPUT_NODE_TYPES and not isinstance(meta.get("variadic_input"), dict):
        raise HTTPException(400, "This node does not support editable root ports")

    if req.inputs is not None:
        meta["inputs"] = req.inputs
    if req.outputs is not None:
        meta["outputs"] = req.outputs
    if req.input_types is not None:
        meta["input_types"] = req.input_types
    if req.output_types is not None:
        meta["output_types"] = req.output_types
    if req.input_defaults is not None:
        meta["input_defaults"] = req.input_defaults
    if req.multi_input_ports is not None:
        meta["multi_input_ports"] = req.multi_input_ports

    if meta["type"] in _TOOLBOX_NODE_TYPES:
        _sync_toolbox_ports(meta)
    elif meta["type"] in _JOINT_LIST_NODE_TYPES:
        _sync_joint_list_ports(meta)
    else:
        _sync_variadic_ports(meta)
    _session.graph._mark_dirty(node_id)
    _save()
    return meta


@app.patch("/nodes/{node_id}/presentation")
def update_port_visibility(node_id: str, req: UpdatePortVisibilityReq):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    meta = _session.node_meta[node_id]
    if req.promoted_inputs is not None:
        allowed = set(meta.get("inputs", []))
        meta["promoted_inputs"] = [port for port in req.promoted_inputs if port in allowed]
    if req.promoted_outputs is not None:
        allowed = set(meta.get("outputs", []))
        meta["promoted_outputs"] = [port for port in req.promoted_outputs if port in allowed]
    _save()
    return meta


@app.patch("/nodes/{node_id}/pos")
def update_pos(node_id: str, pos: list[float]):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    _session.node_meta[node_id]["pos"] = pos
    _save(debounce=0.8)   # coalesce rapid drag updates
    return {"ok": True}


@app.post("/edges")
def connect(req: ConnectReq):
    try:
        _session.graph._add_edge(req.from_id, req.from_port, req.to_id, req.to_port)
    except Exception as e:
        raise HTTPException(400, str(e))
    meta = _session.node_meta.get(req.to_id)
    if meta and meta.get("type") in _TOOLBOX_NODE_TYPES and req.to_port.startswith("tool_"):
        inputs = list(meta.get("inputs", []))
        if req.to_port not in inputs:
            meta["inputs"] = [*inputs, req.to_port]
            meta["input_types"] = {**meta.get("input_types", {}), req.to_port: "Fn"}
        _sync_toolbox_ports(meta)
    elif meta and meta.get("type") in _JOINT_LIST_NODE_TYPES and req.to_port.startswith("joint_"):
        inputs = list(meta.get("inputs", []))
        if req.to_port not in inputs:
            meta["inputs"] = [*inputs, req.to_port]
            meta["input_types"] = {**meta.get("input_types", {}), req.to_port: "Dict"}
        _sync_joint_list_ports(meta)
    elif meta and isinstance(meta.get("variadic_input"), dict):
        _sync_variadic_ports(meta, _session.graph._edges)
    _save()
    return {"ok": True}


@app.delete("/edges")
def disconnect(from_id: str, from_port: str, to_id: str, to_port: str):
    _session.graph._edges = [
        e for e in _session.graph._edges
        if not (e["from"] == from_id and e["from_port"] == from_port
                and e["to"] == to_id and e["to_port"] == to_port)
    ]
    meta = _session.node_meta.get(to_id)
    if meta and meta.get("type") in _TOOLBOX_NODE_TYPES:
        _sync_toolbox_ports(meta, _session.graph._edges)
    elif meta and meta.get("type") in _JOINT_LIST_NODE_TYPES:
        _sync_joint_list_ports(meta, _session.graph._edges)
    elif meta and isinstance(meta.get("variadic_input"), dict):
        _sync_variadic_ports(meta, _session.graph._edges)
    _save()
    return {"ok": True}


@app.patch("/nodes/{node_id}/subgraph")
def update_subgraph(node_id: str, req: UpdateSubgraphReq):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    if _session.node_meta[node_id]["type"] not in _SUBGRAPH_NODE_TYPES:
        raise HTTPException(400, "Node does not own a subgraph")
    subgraph = {"node_meta": req.node_meta, "edges": req.edges}
    _session.node_meta[node_id]["subgraph"] = subgraph
    _session.graph._nodes[node_id]["subgraph"] = subgraph
    _sync_subgraph_node_ports(_session.node_meta[node_id])
    _session.graph._mark_dirty(node_id)
    _save()
    return _session.node_meta[node_id]


@app.get("/nodes/{node_id}/subgraph")
def get_subgraph(node_id: str):
    if node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    if _sync_dynamic_node_meta(_session.node_meta[node_id], _session.graph._edges):
        _save()
    return _session.node_meta[node_id].get("subgraph", {"node_meta": {}, "edges": []})


@app.post("/subnets")
def collapse_to_subnet(req: CollapseSubnetReq):
    """Collapse selected nodes into a Subnet node."""
    import uuid as _uuid
    node_ids = set(req.node_ids)
    for nid in node_ids:
        if nid not in _session.node_meta:
            raise HTTPException(404, f"Node {nid} not found")

    # Compute bounding box centre for subnet position
    positions = [_session.node_meta[nid]["pos"] for nid in node_ids]
    cx = sum(p[0] for p in positions) / len(positions)
    cy = sum(p[1] for p in positions) / len(positions)

    # Classify edges as internal or crossing
    all_edges = _session.graph._edges
    internal_edges = [e for e in all_edges if e["from"] in node_ids and e["to"] in node_ids]
    entering_edges  = [e for e in all_edges if e["from"] not in node_ids and e["to"] in node_ids]
    exiting_edges   = [e for e in all_edges if e["from"] in node_ids and e["to"] not in node_ids]

    # Build inner node_meta for collapsed nodes
    inner_meta: dict[str, dict] = {}
    for nid in node_ids:
        inner_meta[nid] = dict(_session.node_meta[nid])

    new_inner_nodes: dict[str, dict] = {}
    new_inner_edges: list[dict] = []

    min_x = min(inner_meta[nid]["pos"][0] for nid in node_ids)
    max_x = max(inner_meta[nid]["pos"][0] for nid in node_ids)
    avg_y = sum(inner_meta[nid]["pos"][1] for nid in node_ids) / len(node_ids)

    # ONE SubnetInput node with one output per unique entering target port
    entry_ports: list[str] = []
    seen_entry_ports: set[str] = set()
    subnet_inputs: list[dict] = []

    for e in entering_edges:
        p = e["to_port"]
        if p in seen_entry_ports:
            p = f"{e['to'][:6]}_{e['to_port']}"
        seen_entry_ports.add(p)
        entry_ports.append(p)
        subnet_inputs.append({"port_name": p, "from_id": e["from"], "from_port": e["from_port"]})

    if entry_ports:
        inp_id = str(_uuid.uuid4())
        new_inner_nodes[inp_id] = {
            "id": inp_id, "type": "SubnetInput", "params": {},
            "pos": [min_x - 220, avg_y],
            "inputs": [], "outputs": entry_ports,
            "input_types": {}, "output_types": {p: "Any" for p in entry_ports},
            "input_defaults": {},
        }
        for i, e in enumerate(entering_edges):
            new_inner_edges.append({
                "from": inp_id, "from_port": entry_ports[i],
                "to": e["to"], "to_port": e["to_port"],
            })

    # ONE SubnetOutput node with one input per unique exiting source port
    exit_ports: list[str] = []
    seen_exit_ports: set[str] = set()
    subnet_outputs: list[dict] = []

    for e in exiting_edges:
        p = e["from_port"]
        if p in seen_exit_ports:
            p = f"{e['from'][:6]}_{e['from_port']}"
        seen_exit_ports.add(p)
        exit_ports.append(p)
        subnet_outputs.append({"port_name": p, "to_id": e["to"], "to_port": e["to_port"]})

    if exit_ports:
        out_id = str(_uuid.uuid4())
        new_inner_nodes[out_id] = {
            "id": out_id, "type": "SubnetOutput", "params": {},
            "pos": [max_x + 220, avg_y],
            "inputs": exit_ports, "outputs": [],
            "input_types": {p: "Any" for p in exit_ports}, "output_types": {},
            "input_defaults": {},
        }
        for i, e in enumerate(exiting_edges):
            new_inner_edges.append({
                "from": e["from"], "from_port": e["from_port"],
                "to": out_id, "to_port": exit_ports[i],
            })

    # Build complete inner meta
    all_inner_meta = {**inner_meta, **new_inner_nodes}
    all_inner_edges = internal_edges + new_inner_edges

    # Create the Subnet node
    subnet_id = str(_uuid.uuid4())
    subnet_meta: dict[str, Any] = {
        "id":       subnet_id,
        "type":     "Subnet",
        "params":   {"label": req.label},
        "pos":      [cx, cy],
        "inputs":   [],
        "outputs":  [],
        "input_types": {},
        "output_types": {},
        "input_defaults": {},
        "subgraph": {"node_meta": all_inner_meta, "edges": all_inner_edges},
    }
    _sync_subgraph_node_ports(subnet_meta)

    # Remove collapsed nodes from session
    for nid in node_ids:
        del _session.node_meta[nid]
        _session.graph._nodes.pop(nid, None)
        _session.graph._dirty.discard(nid)

    # Remove all edges involving collapsed nodes
    _session.graph._edges = [
        e for e in _session.graph._edges
        if e["from"] not in node_ids and e["to"] not in node_ids
    ]

    # Add subnet node to session
    _session.node_meta[subnet_id] = subnet_meta
    _session.graph._nodes[subnet_id] = {
        "type": "Subnet",
        "params": subnet_meta["params"],
        "subgraph": subnet_meta["subgraph"],
    }
    _session.graph._dirty.add(subnet_id)

    # Rewire external edges through the subnet
    for inp_info in subnet_inputs:
        _session.graph._edges.append({
            "from": inp_info["from_id"],
            "from_port": inp_info["from_port"],
            "to": subnet_id,
            "to_port": inp_info["port_name"],
        })
    for out_info in subnet_outputs:
        _session.graph._edges.append({
            "from": subnet_id,
            "from_port": out_info["port_name"],
            "to": out_info["to_id"],
            "to_port": out_info["to_port"],
        })

    _save()
    return {"subnet": subnet_meta, "removed_node_ids": list(node_ids)}


@app.post("/cook")
def cook(req: CookReq):
    import traceback
    if req.node_id not in _session.node_meta:
        raise HTTPException(404, "Node not found")
    if req.node_id not in _session.graph._nodes:
        raise HTTPException(500, f"Node {req.node_id} missing from graph (try resetting)")
    node_type = _session.node_meta[req.node_id]["type"]
    workflow = _run_workflow_snapshot(req.node_id, req.port)
    run_id = _run_store.begin(node_id=req.node_id, port=req.port, node_type=node_type, workflow=workflow)
    try:
        _refresh_live_compute_device_params()
        _begin_fresh_cook()
        _run_store.record_event(run_id, {"type": "start", "node_id": req.node_id, "port": req.port})
        proxy  = bn.NodeProxy(_session.graph, req.node_id, node_type, {})
        result = _session.graph.cook(proxy, req.port)
        _run_store.record_event(run_id, _event_for_storage({
            "type": "success", "node_id": req.node_id, "port": req.port, "value": result,
        }))
        _run_store.record_event(run_id, _event_for_storage({"type": "done", "port": req.port, "value": result}))
        _run_store.finalize_success(run_id, value=_event_value(result))
        return {"value": result, "port": req.port, "run_id": run_id}
    except Exception as exc:
        trace = traceback.format_exc()
        _run_store.record_event(run_id, {
            "type": "error", "node_id": req.node_id, "port": req.port, "error": trace,
        })
        _run_store.finalize_error(run_id, error=str(exc))
        raise HTTPException(500, trace)


def _json_line(payload: dict) -> str:
    return json.dumps(payload, default=str) + "\n"


_RUNTIME_STATUS_KEYS = ("cookResult", "cookError", "cooking", "cookPort")


def _status_value(value: Any) -> Any:
    # Runtime scenes contain hundreds of thousands of ordinary numeric
    # scalars. Sending each one through json.dumps/json.loads made a 15k-point
    # cloud spend close to a second in status normalization alone.
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _status_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_status_value(item) for item in value]
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return str(value)


def _is_image_data_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("data:image/")


def _event_value(value: Any) -> Any:
    if _is_image_data_url(value):
        return f"[image data URL, {len(value)} chars]"
    if isinstance(value, list):
        return [_event_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _event_value(item) for key, item in value.items()}
    return value


def _event_outputs(outputs: Any) -> Any:
    if isinstance(outputs, dict):
        return {key: _event_value(value) for key, value in outputs.items()}
    return _event_value(outputs)


def _live_outputs(outputs: Any) -> Any:
    """Per-port values for the live success event, keeping full image data URLs.

    Unlike ``_event_outputs`` (which placeholders images to keep run-log files
    small), this preserves images so the editor can preview a node's image
    output inline even when a different port is the one being cooked — e.g. a
    dashboard wired to a downstream node by its ``summary`` port still shows its
    rendered image on the node. Storage re-strips images via
    ``_event_for_storage``, so run logs stay small.
    """
    return _status_value(outputs)


def _event_for_storage(event: dict[str, Any]) -> dict[str, Any]:
    stored = dict(event)
    if "value" in stored:
        stored["value"] = _event_value(stored["value"])
    if "outputs" in stored:
        stored["outputs"] = _event_outputs(stored["outputs"])
    return stored


def _clear_runtime_status(meta: dict) -> None:
    for key in _RUNTIME_STATUS_KEYS:
        meta.pop(key, None)


def _record_node_success(meta_map: dict[str, dict], node_id: str, port: str, value: Any) -> None:
    meta = meta_map.get(node_id)
    if not meta:
        return
    _clear_runtime_status(meta)
    meta["cookResult"] = _status_value(value)
    meta["cookPort"] = port
    meta["cooking"] = False


def _record_node_error(meta_map: dict[str, dict], node_id: str, port: str, error: str) -> None:
    meta = meta_map.get(node_id)
    if not meta:
        return
    _clear_runtime_status(meta)
    meta["cookError"] = str(error)
    meta["cookPort"] = port
    meta["cooking"] = False


def _node_cached_outputs(cache: dict[tuple, Any], node_id: str, fallback_port: str, fallback_value: Any) -> Any:
    outputs = {
        str(port): _status_value(value)
        for (nid, port), value in cache.items()
        if nid == node_id
    }
    return outputs if len(outputs) > 1 else fallback_value


def _clear_runtime_status_tree(meta_map: dict[str, dict]) -> None:
    for meta in meta_map.values():
        _clear_runtime_status(meta)
        subgraph = meta.get("subgraph")
        if isinstance(subgraph, dict):
            inner_meta = subgraph.get("node_meta")
            if isinstance(inner_meta, dict):
                _clear_runtime_status_tree(inner_meta)


def _begin_fresh_cook(clear_status: bool = True) -> None:
    """Make every user-triggered cook execute from scratch.

    The graph still uses its cache inside a single cook so one upstream node
    can feed multiple downstream ports without running twice.
    """
    _session.graph._cache.clear()
    _session.graph._dirty = set(_session.graph._nodes)
    if clear_status:
        _clear_runtime_status_tree(_session.node_meta)


def _subgraph_output_node_id(subgraph: dict) -> str:
    for nid, meta in subgraph.get("node_meta", {}).items():
        if meta.get("type") == "SubnetOutput":
            return nid
    raise KeyError("Subgraph has no SubnetOutput node")


def _subgraph_output_has_status(subnet_id: str, port: str) -> bool:
    subgraph = _session.node_meta[subnet_id].get("subgraph", {})
    try:
        output_id = _subgraph_output_node_id(subgraph)
    except KeyError:
        return False
    meta = subgraph.get("node_meta", {}).get(output_id, {})
    return meta.get("cookPort") == port and ("cookResult" in meta or "cookError" in meta)


def _cook_subgraph_streamed_value(subnet_id: str, port: str):
    output_id = _subgraph_output_node_id(_session.node_meta[subnet_id].get("subgraph", {}))
    final_value: Any = None
    final_error: str | None = None
    saw_done = False

    for line in _subgraph_cook_trace(subnet_id, output_id, port):
        yield line
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get("type") == "done":
            saw_done = True
            final_value = event.get("value")
            final_error = event.get("error")

    if final_error:
        raise RuntimeError(final_error)
    if not saw_done:
        raise RuntimeError("Subgraph cook did not complete")
    return final_value


def _visual_node_id(inner_meta: dict[str, dict], preferred: str, type_name: str) -> str | None:
    if preferred in inner_meta:
        return preferred
    for node_id, meta in inner_meta.items():
        if meta.get("type") == type_name:
            return node_id
    return None


def _visual_emit_success(inner_meta: dict[str, dict], node_id: str | None, port: str, value: Any, outputs: dict | None = None):
    if not node_id:
        return
    status_value = outputs if outputs is not None else value
    _record_node_success(inner_meta, node_id, port, status_value)
    yield _json_line({
        "type": "success",
        "node_id": node_id,
        "port": port,
        "value": status_value,
        "outputs": outputs if outputs is not None else {port: value},
    })


def _visual_emit_start(node_id: str | None, port: str, inner_meta: dict[str, dict] | None = None):
    if not node_id:
        return
    payload: dict[str, Any] = {"type": "start", "node_id": node_id, "port": port}
    if inner_meta and node_id in inner_meta:
        payload["node_type"] = str(inner_meta[node_id].get("type", ""))
    yield _json_line(payload)


def _visual_emit_error(inner_meta: dict[str, dict], node_id: str | None, port: str, error: str):
    if not node_id:
        return
    _record_node_error(inner_meta, node_id, port, error)
    payload: dict[str, Any] = {"type": "error", "node_id": node_id, "port": port, "error": error}
    if node_id in inner_meta:
        payload["node_type"] = str(inner_meta[node_id].get("type", ""))
    yield _json_line(payload)


def _cook_visual_agent_loop_streamed_value(subnet_id: str, port: str, outer_ctx: dict):
    import traceback

    subgraph = _session.node_meta[subnet_id].get("subgraph", {})
    inner_meta = subgraph.get("node_meta", {})
    _migrate_visual_agent_loop_subgraph(_session.node_meta[subnet_id])

    loop_in_id = _visual_node_id(inner_meta, "loop_in", "SubnetInput")
    messages_id = _visual_node_id(inner_meta, "messages", "AgentMessages")
    chat_id = _visual_node_id(inner_meta, "chat", "AgentChatStep")
    iteration_id = _visual_node_id(inner_meta, "iteration", "AgentIteration") or _visual_node_id(inner_meta, "iter_one", "Int")
    stop_id = _visual_node_id(inner_meta, "stop", "AgentStopCheck")
    dispatch_id = _visual_node_id(inner_meta, "dispatch", "ToolDispatch")
    append_id = _visual_node_id(inner_meta, "append", "AgentAppendMessages")
    final_id = _visual_node_id(inner_meta, "final", "AgentFinalAnswer")
    loop_out_id = _visual_node_id(inner_meta, "loop_out", "SubnetOutput")

    model = outer_ctx.get("model", "claude-sonnet-4-6")
    system = outer_ctx.get("system", "You are a helpful agent. Use the available tools.")
    prompt = outer_ctx.get("prompt", "")
    tools = outer_ctx.get("tools") or []
    max_tokens = ai_nodes._max_tokens_for_model(model, outer_ctx.get("max_tokens"))
    max_iter = max(1, ai_nodes._int_value(outer_ctx.get("max_iter"), 5))

    injected = {
        "prompt": prompt,
        "system": system,
        "model": model,
        "tools": tools,
        "max_tokens": max_tokens,
        "max_iter": max_iter,
    }
    yield from _visual_emit_success(inner_meta, loop_in_id, "inputs", injected, injected)

    messages: list[dict] = [{"role": "user", "content": prompt}]
    yield from _visual_emit_success(inner_meta, messages_id, "messages", messages, {"messages": messages})

    steps: list[dict] = []
    final_result = ""
    final_step: dict = {"role": "assistant", "text": "", "tool_calls": []}

    for iteration in range(1, max_iter + 1):
        yield from _visual_emit_success(
            inner_meta,
            iteration_id,
            "iteration",
            iteration,
            {"iteration": iteration},
        )

        try:
            yield from _visual_emit_start(chat_id, "step")
            _, resp, chat_step = ai_nodes._chat_step(
                messages,
                model=model,
                system=system,
                tools=tools,
                max_tokens=max_tokens,
                provider_name=outer_ctx.get("provider"),
                base_url=outer_ctx.get("base_url"),
                api_key=outer_ctx.get("api_key"),
            )
        except Exception as exc:
            error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
            yield from _visual_emit_error(inner_meta, chat_id, "step", error)
            raise

        chat_outputs = {
            "assistant_text": resp.text,
            "tool_calls": chat_step["tool_calls"],
            "stop_reason": resp.stop_reason,
            "step": chat_step,
        }
        yield from _visual_emit_success(inner_meta, chat_id, "step", chat_step, chat_outputs)
        steps.append({
            "role": "assistant",
            "text": resp.text,
            "tool_calls": [{"name": tc.name, "arguments": tc.arguments} for tc in resp.tool_calls],
        })

        stop_outputs = ai_nodes.agent_stop_check({
            "stop_reason": resp.stop_reason,
            "tool_calls": chat_step["tool_calls"],
            "iteration": iteration,
            "max_iter": max_iter,
        })
        yield from _visual_emit_success(inner_meta, stop_id, "reason", stop_outputs["reason"], stop_outputs)

        if stop_outputs["reason"] == "final":
            final_result = resp.text
            final_step = {"role": "assistant", "text": final_result, "tool_calls": [], "reason": "final"}
            yield from _visual_emit_success(inner_meta, final_id, "result", final_result, {"result": final_result, "step": final_step})
            break

        tool_call_dicts = [ai_nodes._tool_call_dict(tc) for tc in resp.tool_calls]
        yield from _visual_emit_start(dispatch_id, "steps")
        tool_results, tool_steps = ai_nodes._dispatch_tools(tool_call_dicts, tools)
        dispatch_outputs = {
            "tool_results": [ai_nodes._tool_result_dict(r) for r in tool_results],
            "steps": tool_steps,
        }
        yield from _visual_emit_success(inner_meta, dispatch_id, "steps", tool_steps, dispatch_outputs)
        steps.extend(tool_steps)

        messages = ai_nodes._append_tool_messages(
            messages,
            model=model,
            assistant_text=resp.text,
            tool_calls=tool_call_dicts,
            tool_results=[ai_nodes._tool_result_dict(r) for r in tool_results],
            provider_name=outer_ctx.get("provider"),
            base_url=outer_ctx.get("base_url"),
            api_key=outer_ctx.get("api_key"),
        )
        yield from _visual_emit_success(inner_meta, append_id, "messages", messages, {"messages": messages})

        if stop_outputs["reason"] == "max_iter":
            try:
                yield from _visual_emit_start(final_id, "result")
                final_outputs = ai_nodes.agent_final_answer({
                    "messages": messages,
                    "system": system,
                    "model": model,
                    "max_tokens": max_tokens,
                    "assistant_text": resp.text,
                    "stop_reason": resp.stop_reason,
                    "reason": "max_iter",
                    "tool_calls": chat_step["tool_calls"],
                    "provider": outer_ctx.get("provider"),
                    "base_url": outer_ctx.get("base_url"),
                    "api_key": outer_ctx.get("api_key"),
                })
            except Exception as exc:
                error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
                yield from _visual_emit_error(inner_meta, final_id, "result", error)
                raise
            final_result = final_outputs.get("result", "")
            final_step = final_outputs.get("step", {})
            steps.append(final_step)
            yield from _visual_emit_success(inner_meta, final_id, "result", final_result, final_outputs)
            break

    loop_outputs = {"result": final_result, "steps": steps}
    yield from _visual_emit_success(inner_meta, loop_out_id, port, loop_outputs.get(port), loop_outputs)
    return loop_outputs.get(port)


def _refresh_subgraph_status_if_needed(subnet_id: str, port: str):
    if _subgraph_output_has_status(subnet_id, port):
        return
    if _session.node_meta[subnet_id].get("type") == "VisualAgentLoop":
        outer_ctx = dict(_session.graph._nodes.get(subnet_id, {}).get("params", {}))
        for edge in _session.graph._edges:
            if edge["to"] == subnet_id and (edge["from"], edge["from_port"]) in _session.graph._cache:
                outer_ctx[edge["to_port"]] = _session.graph._cache[(edge["from"], edge["from_port"])]
        value = yield from _cook_visual_agent_loop_streamed_value(subnet_id, port, outer_ctx)
    else:
        value = yield from _cook_subgraph_streamed_value(subnet_id, port)
    _session.graph._cache[(subnet_id, port)] = value
    _session.graph._dirty.discard(subnet_id)


def _lookup_node_type(node_id: str | None) -> str:
    if not isinstance(node_id, str):
        return ""
    meta = _session.node_meta.get(node_id)
    if isinstance(meta, dict):
        return str(meta.get("type", ""))
    return ""


def _node_event(payload: dict[str, Any]) -> str:
    """Build an ndjson event line, auto-filling node_type when a node_id is set."""
    if "node_id" in payload and "node_type" not in payload:
        node_type = _lookup_node_type(payload["node_id"])
        if node_type:
            payload = {**payload, "node_type": node_type}
    return _json_line(payload)


def _cook_target_batch_trace(cook_one, targets: list[tuple[str, str]]):
    """Cook every requested terminal while sharing the current graph cache."""
    import traceback

    if len(targets) == 1:
        node_id, port = targets[0]
        try:
            final_value = yield from cook_one(node_id, port)
            yield _json_line({"type": "done", "port": port, "value": _event_value(final_value)})
        except _CookStopped:
            yield _json_line({"type": "done", "port": port, "error": "stopped"})
        except Exception:
            yield _json_line({"type": "done", "port": port, "error": traceback.format_exc()})
        return

    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    target_status: list[dict[str, str]] = []
    try:
        for node_id, port in targets:
            key = f"{node_id}.{port}"
            try:
                values[key] = yield from cook_one(node_id, port)
                target_status.append({"node_id": node_id, "port": port, "status": "success"})
            except _CookStopped:
                raise
            except Exception:
                errors[key] = traceback.format_exc()
                target_status.append({"node_id": node_id, "port": port, "status": "error"})

        done: dict[str, Any] = {
            "type": "done",
            "port": "leaves",
            "value": _event_value(values),
            "targets": target_status,
        }
        if errors:
            done["error"] = "\n\n".join(
                f"{key}:\n{error}" for key, error in errors.items()
            )
        yield _json_line(done)
    except _CookStopped:
        yield _json_line({
            "type": "done",
            "port": "leaves",
            "value": _event_value(values),
            "targets": target_status,
            "error": "stopped",
        })


class _CookStreamLogger:
    """RunLogger-shaped adapter that forwards model/tool events into the cook stream.

    The AI nodes call ``ctx['__run_logger__'].model_call(...)`` and
    ``.tool_call(...)``. The CLI runtime gives them a real RunLogger; the editor
    cook path used to drop those events on the floor. This adapter queues them
    so ``_cook_trace`` can yield them as ndjson lines, which means both the live
    frontend and the persistent RunStore see them.
    """

    def __init__(self):
        self._pending: list[dict[str, Any]] = []

    def drain(self) -> list[dict[str, Any]]:
        pending, self._pending = self._pending, []
        return pending

    def model_call(self, *, node_id, model, provider=None, action="complete", tool_count=None):
        event: dict[str, Any] = {
            "type": "model_call",
            "node_id": node_id,
            "node_type": _lookup_node_type(node_id),
            "model": model,
            "action": action,
        }
        if provider:
            event["provider"] = provider
        if tool_count is not None:
            event["tool_count"] = tool_count
        self._pending.append(event)

    def tool_call(self, *, node_id, name, arguments=None):
        self._pending.append({
            "type": "tool_call",
            "node_id": node_id,
            "node_type": _lookup_node_type(node_id),
            "name": name,
            "arguments": dict(arguments or {}),
        })


def _cook_trace(
    node_id: str,
    port: str,
    stop_event: threading.Event | None = None,
    targets: list[tuple[str, str]] | None = None,
    run_mode: str = "once",
):
    import traceback
    emitted_cached: set[tuple[str, str]] = set()
    logger = _CookStreamLogger()

    def drain_logger():
        for event in logger.drain():
            yield _json_line(event)

    def emit_cached_success(current_id: str, current_port: str):
        cache_key = (current_id, current_port)
        if cache_key in emitted_cached or cache_key not in _session.graph._cache:
            return
        emitted_cached.add(cache_key)
        yield _node_event({
            "type": "success",
            "node_id": current_id,
            "port": current_port,
            "value": _session.graph._cache[cache_key],
            "cached": True,
        })

    def emit_cached_upstream(current_id: str, visiting: set[str] | None = None):
        if visiting is None:
            visiting = set()
        if current_id in visiting:
            return
        visiting.add(current_id)
        for edge in _session.graph._edges:
            if edge["to"] == current_id:
                yield from emit_cached_upstream(edge["from"], visiting)
                source_def = _session.graph._nodes.get(edge["from"])
                if source_def and source_def.get("type") in {"Subnet", "VisualAgentLoop"}:
                    yield from _refresh_subgraph_status_if_needed(edge["from"], edge["from_port"])
                yield from emit_cached_success(edge["from"], edge["from_port"])
        visiting.remove(current_id)

    def cook_one(current_id: str, current_port: str):
        _raise_if_stopped(stop_event)
        if current_id not in _session.node_meta:
            raise KeyError(f"Node {current_id} not found")
        if current_id not in _session.graph._nodes:
            raise KeyError(f"Node {current_id} missing from graph")

        node_def = _session.graph._nodes[current_id]
        cache_key = (current_id, current_port)
        if (
            node_def["type"] not in {"Subnet", "VisualAgentLoop"}
            and current_id not in _session.graph._dirty
            and cache_key in _session.graph._cache
        ):
            value = _session.graph._cache[cache_key]
            yield from emit_cached_upstream(current_id)
            yield from emit_cached_success(current_id, current_port)
            return value

        ctx = dict(node_def["params"])

        for edge in _session.graph._edges:
            if edge["to"] == current_id:
                val = yield from cook_one(edge["from"], edge["from_port"])
                _raise_if_stopped(stop_event)
                ctx[edge["to_port"]] = val

        try:
            if node_def["type"] in {"Subnet", "VisualAgentLoop"}:
                _raise_if_stopped(stop_event)
                yield _node_event({"type": "start", "node_id": current_id, "port": current_port})
                try:
                    if node_def["type"] == "VisualAgentLoop":
                        value = yield from _cook_visual_agent_loop_streamed_value(current_id, current_port, ctx)
                    else:
                        value = yield from _cook_subgraph_streamed_value(current_id, current_port)
                    _raise_if_stopped(stop_event)
                    result = {current_port: value}
                    _session.graph._cache[(current_id, current_port)] = value
                    _session.graph._dirty.discard(current_id)
                    yield _node_event({
                        "type": "success",
                        "node_id": current_id,
                        "port": current_port,
                        "value": value,
                        "outputs": _event_outputs(result),
                    })
                    return value
                except Exception as exc:
                    yield _node_event({"type": "error", "node_id": current_id, "port": current_port, "error": str(exc)})
                    raise

            yield _node_event({
                "type": "start",
                "node_id": current_id,
                "port": current_port,
            })

            fn = _NODE_REGISTRY[node_def["type"]]
            ctx.update(getattr(_session.graph, "_runtime_context", {}))
            ctx["__graph__"] = _session.graph
            ctx["__node_id__"] = current_id
            ctx["__run_logger__"] = logger
            ctx["__run_mode__"] = "live" if run_mode == "live" else "once"
            _out_buf, _err_buf = io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(_out_buf), contextlib.redirect_stderr(_err_buf):
                    result = fn(ctx)
                    if isinstance(result, dict):
                        result = bn_fill_frame_stream(result, list(getattr(fn, "_bn_outputs", []) or []))
            finally:
                yield from drain_logger()
                for _stream, _buf in (("stdout", _out_buf), ("stderr", _err_buf)):
                    _text = _buf.getvalue()
                    if _text.strip():
                        yield _node_event({
                            "type": "log",
                            "node_id": current_id,
                            "stream": _stream,
                            "text": _text,
                        })
            _raise_if_stopped(stop_event)
            if not isinstance(result, dict):
                result = {"output": result}

            for key, value in result.items():
                _session.graph._cache[(current_id, key)] = value
            _session.graph._dirty.discard(current_id)

            if cache_key not in _session.graph._cache:
                raise KeyError(
                    f"Node '{node_def['type']}' did not produce port '{current_port}'. "
                    f"Available: {[key for (nid, key) in _session.graph._cache if nid == current_id]}"
                )

            value = _session.graph._cache[cache_key]
            yield _node_event({
                "type": "success",
                "node_id": current_id,
                "port": current_port,
                "value": value,
                "outputs": _live_outputs(result),
            })
            return value
        except Exception as exc:
            yield from drain_logger()
            error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
            yield _node_event({
                "type": "error",
                "node_id": current_id,
                "port": current_port,
                "error": error,
            })
            raise

    yield from _cook_target_batch_trace(cook_one, targets or [(node_id, port)])


def _captured_cook_trace(
    node_id: str,
    port: str,
    run_id: str,
    stop_event: threading.Event | None = None,
    targets: list[tuple[str, str]] | None = None,
    run_mode: str = "once",
):
    """Wrap _cook_trace so every emitted event is also persisted to the run store."""
    final_value: Any = None
    final_error: str | None = None
    try:
        for line in _cook_trace(node_id, port, stop_event, targets=targets, run_mode=run_mode):
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                event = None
            if isinstance(event, dict):
                stored_event = _event_for_storage(event)
                _run_store.record_event(run_id, stored_event)
                if stored_event.get("type") == "done":
                    if stored_event.get("error"):
                        final_error = stored_event.get("error")
                    elif "value" in event:
                        final_value = stored_event.get("value")
                elif stored_event.get("type") == "error" and final_error is None:
                    final_error = stored_event.get("error")
            yield line
    finally:
        if final_error is not None:
            _run_store.finalize_error(run_id, error=final_error)
        else:
            _run_store.finalize_success(run_id, value=final_value)


def _stream_in_worker(lines_factory, stop_event: threading.Event, port: str):
    import traceback

    out_q: queue.Queue[str | None] = queue.Queue()

    def run_worker() -> None:
        try:
            for line in lines_factory():
                if stop_event.is_set():
                    break
                out_q.put(line)
        except _CookStopped:
            out_q.put(_json_line({"type": "done", "port": port, "error": "stopped"}))
        except Exception:
            out_q.put(_json_line({"type": "done", "port": port, "error": traceback.format_exc()}))
        finally:
            out_q.put(None)

    worker = threading.Thread(target=run_worker, name=f"blacknode-cook-{port}", daemon=True)
    worker.start()

    while True:
        if stop_event.is_set():
            yield _json_line({"type": "done", "port": port, "error": "stopped"})
            break
        try:
            line = out_q.get(timeout=0.25)
        except queue.Empty:
            continue
        if line is None:
            break
        yield line


@app.post("/cook-stream")
def cook_stream(req: CookReq):
    node_type = _session.node_meta.get(req.node_id, {}).get("type", "")
    workflow = _run_workflow_snapshot(req.node_id, req.port)
    run_id = _run_store.begin(node_id=req.node_id, port=req.port, node_type=node_type, workflow=workflow)
    _refresh_live_compute_device_params()
    stop_event = _prepare_cook()
    _begin_fresh_cook()
    headers = {"X-Blacknode-Run-Id": run_id}
    lines_factory = lambda: _captured_cook_trace(req.node_id, req.port, run_id, stop_event, run_mode=req.run_mode)
    return StreamingResponse(
        _stream_in_worker(lines_factory, stop_event, req.port),
        media_type="application/x-ndjson",
        headers=headers,
    )


def _graph_cook_targets(req: CookGraphReq) -> list[tuple[str, str]]:
    if not req.targets:
        raise HTTPException(400, "Graph run requires at least one terminal target")
    if len(req.targets) > 256:
        raise HTTPException(400, "Graph run supports at most 256 terminal targets")

    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for target in req.targets:
        item = (target.node_id.strip(), target.port.strip())
        if not item[0] or not item[1]:
            raise HTTPException(400, "Each graph run target needs a node_id and port")
        if item not in seen:
            seen.add(item)
            targets.append(item)
    return targets


@app.post("/cook-graph-stream")
def cook_graph_stream(req: CookGraphReq):
    targets = _graph_cook_targets(req)
    workflow = _run_graph_workflow_snapshot(targets)
    run_id = _run_store.begin(
        node_id="__graph__",
        port="leaves",
        node_type="Graph",
        workflow=workflow,
    )
    _refresh_live_compute_device_params()
    stop_event = _prepare_cook()
    _begin_fresh_cook()
    headers = {"X-Blacknode-Run-Id": run_id}
    first_node, first_port = targets[0]
    lines_factory = lambda: _captured_cook_trace(
        first_node, first_port, run_id, stop_event, targets=targets, run_mode=req.run_mode,
    )
    return StreamingResponse(
        _stream_in_worker(lines_factory, stop_event, "leaves"),
        media_type="application/x-ndjson",
        headers=headers,
    )


def _cloud_call(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    authorization: str | None = None,
    allow_admin: bool = True,
) -> dict[str, Any]:
    try:
        return cloud_client.json_request(
            method,
            path,
            payload,
            authorization=authorization,
            allow_admin=allow_admin,
        )
    except cloud_client.CloudClientError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


def _cloud_session(request: Request) -> cloud_sessions.CloudSession:
    session = _cloud_sessions.get(request.cookies.get(_CLOUD_SESSION_COOKIE))
    if session is None:
        raise HTTPException(401, "Sign in to Blacknode Cloud to continue.")
    return session


def _cloud_user_call(
    request: Request,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _cloud_call(
        method,
        path,
        payload,
        authorization=_cloud_session(request).token,
        allow_admin=False,
    )


def _cloud_cookie_secure(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    return request.url.scheme == "https" or forwarded == "https"


def _set_cloud_cookie(
    request: Request,
    response: Response,
    session_id: str,
    session: cloud_sessions.CloudSession,
) -> None:
    max_age = max(0, int(session.expires_at.timestamp() - time.time()))
    response.set_cookie(
        _CLOUD_SESSION_COOKIE,
        session_id,
        max_age=max_age,
        httponly=True,
        secure=_cloud_cookie_secure(request),
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _clear_cloud_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(
        _CLOUD_SESSION_COOKIE,
        httponly=True,
        secure=_cloud_cookie_secure(request),
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _cloud_status_payload(request: Request, response: Response) -> dict[str, Any]:
    config = cloud_client.configuration()
    status_payload: dict[str, Any] = {
        "configured": config.available,
        "gpu": "NVIDIA L40S",
        "url": config.base_url if config.available else "",
        "authenticated": False,
        "account": None,
        "credits": None,
        "compute_providers": None,
    }
    session_id = request.cookies.get(_CLOUD_SESSION_COOKIE)
    session = _cloud_sessions.get(session_id)
    if session is None:
        if session_id:
            _clear_cloud_cookie(request, response)
        return status_payload
    try:
        account = _cloud_call(
            "GET",
            "/v1/account",
            authorization=session.token,
            allow_admin=False,
        )
        credits = _cloud_call(
            "GET",
            "/v1/credits",
            authorization=session.token,
            allow_admin=False,
        )
        compute_providers = _cloud_call(
            "GET",
            "/v1/compute/providers",
            authorization=session.token,
            allow_admin=False,
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            _cloud_sessions.pop(session_id)
            _clear_cloud_cookie(request, response)
            return status_payload
        raise
    status_payload.update(
        authenticated=True,
        account=account,
        credits=credits,
        compute_providers=compute_providers,
    )
    response.headers["Cache-Control"] = "no-store"
    return status_payload


def _cloud_job_id(value: str) -> str:
    if not re.fullmatch(r"job_[0-9a-f]{32}", value):
        raise HTTPException(400, "Invalid Blacknode Cloud job ID.")
    return value


@app.get("/cloud/status")
def cloud_status(request: Request, response: Response):
    return _cloud_status_payload(request, response)


@app.patch("/cloud/account")
def update_cloud_account(
    req: CloudUpdateAccountReq,
    request: Request,
    response: Response,
):
    payload = {
        key: value
        for key, value in {
            "display_name": req.display_name,
            "compute_provider_preference": req.compute_provider_preference,
        }.items()
        if value is not None
    }
    if not payload:
        raise HTTPException(422, "Provide at least one Cloud account setting.")
    account = _cloud_user_call(
        request,
        "PATCH",
        "/v1/account",
        payload,
    )
    credits = _cloud_user_call(request, "GET", "/v1/credits")
    compute_providers = _cloud_user_call(request, "GET", "/v1/compute/providers")
    config = cloud_client.configuration()
    response.headers["Cache-Control"] = "no-store"
    return {
        "configured": config.available,
        "gpu": "NVIDIA L40S",
        "url": config.base_url if config.available else "",
        "authenticated": True,
        "account": account,
        "credits": credits,
        "compute_providers": compute_providers,
    }


def _cloud_authenticate(
    request: Request,
    response: Response,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    auth = _cloud_call("POST", path, payload, allow_admin=False)
    token = str(auth.get("token") or "")
    expires_at = str(auth.get("expires_at") or "")
    account = auth.get("account")
    if len(token) < 24 or not expires_at or not isinstance(account, dict):
        raise HTTPException(502, "Blacknode Cloud returned an invalid login session.")
    session_id, session = _cloud_sessions.create(token, expires_at, account)
    _set_cloud_cookie(request, response, session_id, session)
    config = cloud_client.configuration()
    credits = _cloud_call(
        "GET",
        "/v1/credits",
        authorization=session.token,
        allow_admin=False,
    )
    compute_providers = _cloud_call(
        "GET",
        "/v1/compute/providers",
        authorization=session.token,
        allow_admin=False,
    )
    return {
        "configured": config.available,
        "gpu": "NVIDIA L40S",
        "url": config.base_url if config.available else "",
        "authenticated": True,
        "account": session.account,
        "credits": credits,
        "compute_providers": compute_providers,
    }


@app.post("/cloud/auth/register")
def register_cloud_account(
    req: CloudRegisterReq,
    request: Request,
    response: Response,
):
    return _cloud_authenticate(
        request,
        response,
        "/v1/auth/register",
        {
            "email": req.email,
            "password": req.password,
            "display_name": req.display_name,
        },
    )


@app.post("/cloud/auth/login")
def login_cloud_account(req: CloudLoginReq, request: Request, response: Response):
    return _cloud_authenticate(
        request,
        response,
        "/v1/auth/login",
        {"email": req.email, "password": req.password},
    )


@app.post("/cloud/newsletter/subscribe")
def subscribe_cloud_newsletter(req: CloudNewsletterReq):
    return _cloud_call(
        "POST",
        "/v1/newsletter/subscriptions",
        {"email": req.email, "consent": req.consent, "source": req.source},
        allow_admin=False,
    )


@app.post("/cloud/auth/verify-email")
def verify_cloud_email(req: CloudEmailVerificationReq):
    return _cloud_call(
        "POST",
        "/v1/auth/verify-email",
        {"token": req.token},
        allow_admin=False,
    )


@app.post("/cloud/auth/logout")
def logout_cloud_account(request: Request, response: Response):
    session_id = request.cookies.get(_CLOUD_SESSION_COOKIE)
    session = _cloud_sessions.pop(session_id)
    revoked = session is None
    if session is not None:
        try:
            _cloud_call(
                "POST",
                "/v1/auth/logout",
                authorization=session.token,
                allow_admin=False,
            )
            revoked = True
        except HTTPException:
            revoked = False
    _clear_cloud_cookie(request, response)
    return {"ok": True, "revoked": revoked}


@app.get("/cloud/credits/history")
def get_cloud_credit_history(request: Request, limit: int = Query(default=100, ge=1, le=200)):
    return _cloud_user_call(request, "GET", f"/v1/credits/history?limit={limit}")


@app.post("/cloud/jobs")
def create_cloud_job(req: CloudJobReq, request: Request):
    node_id = str(req.entrypoint.get("node_id") or "").strip()
    port = str(req.entrypoint.get("port") or "").strip()
    if node_id not in _session.node_meta or not port:
        raise HTTPException(400, "Choose a valid workflow output before running on Cloud.")
    workflow = _workflow_payload(
        req.workflow_name.strip()[:200] or "Current Graph",
        entrypoint={"node_id": node_id, "port": port},
        metadata={"source": "blacknode-editor"},
    )
    workflow = _redact_run_snapshot_secrets(workflow)
    validation = validate_bn_workflow(workflow)
    if not validation.ok:
        raise HTTPException(
            400,
            {
                "message": "The workflow is not ready for Cloud execution.",
                "validation": validation.to_dict(),
            },
        )
    return _cloud_user_call(
        request,
        "POST",
        "/v1/jobs",
        {
            "contract_version": "blacknode.cloud.jobs/v1",
            "project_ref": req.project_ref,
            "workflow": workflow,
            "compute": {
                "gpu_class": "l40s",
                "gpu_count": 1,
                "max_runtime_seconds": req.max_runtime_seconds,
            },
            "runtime": {"release": "gpu-development"},
        },
    )


@app.get("/cloud/datasets")
def list_cloud_datasets(request: Request):
    return _cloud_user_call(request, "GET", "/v1/datasets")


@app.put("/cloud/datasets")
async def upload_cloud_dataset(request: Request):
    name = Path(request.headers.get("X-Dataset-Name", "")).name
    if not name.endswith((".tar.gz", ".tgz")):
        raise HTTPException(400, "Choose a .tar.gz LeRobot dataset archive.")
    descriptor, temporary_name = tempfile.mkstemp(prefix="blacknode-dataset-", suffix=".tar.gz")
    os.close(descriptor)
    temporary = Path(temporary_name).resolve()
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > 50 * 1024 * 1024 * 1024:
                    raise HTTPException(413, "Dataset archive exceeds the 50 GiB V0 limit.")
                digest.update(chunk)
                handle.write(chunk)
        if not size:
            raise HTTPException(400, "Dataset archive is empty.")
        sha256 = digest.hexdigest()
        asset_id = f"dataset_{sha256[:32]}"
        try:
            with temporary.open("rb") as stream:
                return cloud_client.upload(
                    f"/v1/datasets/{asset_id}",
                    stream,
                    size=size,
                    headers={
                        "X-Dataset-Name": name,
                        "X-Dataset-SHA256": sha256,
                        "X-Dataset-Size": str(size),
                    },
                    authorization=_cloud_session(request).token,
                )
        except cloud_client.CloudClientError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)


@app.post("/cloud/vla/jobs")
def create_cloud_vla_job(req: CloudVLATrainReq, request: Request):
    uri = req.dataset_uri.strip()
    revision = req.dataset_revision.strip()
    if uri.startswith("hf://") and not revision:
        raise HTTPException(400, "Pin the Hugging Face dataset to an immutable revision.")
    if not uri.startswith(("hf://", "blacknode-cloud://datasets/")):
        raise HTTPException(400, "Choose a pinned Hugging Face or uploaded Cloud dataset.")
    workflow = {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "OpenPI π0.5 Fine-Tune",
        "entrypoint": {"node_id": "train", "port": "model"},
        "metadata": {
            "source": "blacknode-editor-vla",
            "required_packages": ["blacknode-dataset", "blacknode-training"],
            "required_components": [
                "blacknode-dataset/adapters",
                "blacknode-training/vla-openpi",
            ],
            "cloud": {"workload": "vla_train", "gpu_class": "l40s"},
            "safety": {"physical_motion_authorized": False},
        },
        "node_meta": {
            "dataset": {
                "id": "dataset",
                "type": "LeRobotDataset",
                "params": {"uri": uri, "revision": revision, "source_uri": ""},
                "inputs": ["trigger", "uri", "revision", "source_uri"],
                "outputs": ["dataset", "uri", "revision", "report"],
            },
            "train": {
                "id": "train",
                "type": "OpenPIFineTune",
                "params": {
                    "action": "run",
                    "dataset": {},
                    "run_id": f"pi05-{uuid.uuid4().hex[:12]}",
                    "output_dir": "",
                    "steps": req.steps,
                    "batch_size": req.batch_size,
                    "action_horizon": req.action_horizon,
                    "action_mode": "absolute_joint",
                    "learning_rate": 0.00005,
                    "save_interval": min(1000, req.steps),
                    "seed": 42,
                    "resume": True,
                    "overwrite": False,
                },
                "inputs": [
                    "trigger", "action", "dataset", "run_id", "output_dir", "steps",
                    "batch_size", "action_horizon", "action_mode", "learning_rate",
                    "save_interval", "seed", "resume", "overwrite",
                ],
                "outputs": [
                    "ok", "running", "phase", "step", "progress", "status", "metrics",
                    "model", "model_path", "report",
                ],
            },
        },
        "edges": [
            {"from": "dataset", "from_port": "dataset", "to": "train", "to_port": "dataset"}
        ],
    }
    return _cloud_user_call(
        request,
        "POST",
        "/v1/jobs",
        {
            "contract_version": "blacknode.cloud.jobs/v1",
            "project_ref": req.project_ref,
            "workflow": workflow,
            "compute": {
                "gpu_class": "l40s",
                "gpu_count": 1,
                "max_runtime_seconds": req.max_runtime_seconds,
            },
            "runtime": {"release": "gpu-development"},
        },
    )
@app.get("/cloud/jobs/{job_id}")
def get_cloud_job(job_id: str, request: Request):
    return _cloud_user_call(request, "GET", f"/v1/jobs/{_cloud_job_id(job_id)}")


@app.delete("/cloud/jobs/{job_id}")
def cancel_cloud_job(job_id: str, request: Request):
    return _cloud_user_call(request, "DELETE", f"/v1/jobs/{_cloud_job_id(job_id)}")


@app.get("/cloud/jobs/{job_id}/logs")
def get_cloud_job_logs(
    job_id: str,
    request: Request,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
):
    path = f"/v1/jobs/{_cloud_job_id(job_id)}/logs?after_seq={after_seq}&limit={limit}"
    return _cloud_user_call(request, "GET", path)


@app.get("/cloud/jobs/{job_id}/artifacts")
def get_cloud_job_artifacts(job_id: str, request: Request):
    return _cloud_user_call(
        request,
        "GET",
        f"/v1/jobs/{_cloud_job_id(job_id)}/artifacts",
    )


@app.get("/cloud/jobs/{job_id}/artifacts/{artifact_id}/download")
def download_cloud_job_artifact(job_id: str, artifact_id: str, request: Request):
    clean_job_id = _cloud_job_id(job_id)
    if not re.fullmatch(r"artifact_[0-9a-f]{28}", artifact_id):
        raise HTTPException(400, "Invalid Blacknode Cloud artifact ID.")
    try:
        chunks, media_type, disposition = cloud_client.download(
            f"/v1/jobs/{clean_job_id}/artifacts/{artifact_id}/download",
            authorization=_cloud_session(request).token,
        )
    except cloud_client.CloudClientError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    headers = {"Content-Disposition": disposition} if disposition else None
    return StreamingResponse(chunks, media_type=media_type, headers=headers)


@app.post("/cook/stop")
def stop_cook():
    _stop_active_cook()
    _begin_fresh_cook()
    return {"ok": True, "runtime": _stop_runtime_services()}


@app.get("/ollama/models")
def ollama_models(endpoint_url: str = "http://127.0.0.1:11434"):
    base = endpoint_url.strip().rstrip("/") or "http://127.0.0.1:11434"
    req = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "Blacknode/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}
    models = sorted(str(m.get("name", "")) for m in payload.get("models", []) if isinstance(m, dict) and m.get("name"))
    return {"ok": True, "models": models}


# Tools the Console may run. The editor is reachable from any browser tab (CORS
# is open on a fixed port), so a free-form shell here would be arbitrary code
# execution triggerable by any page. Commands are split with shlex and passed as
# argv - never through a shell - so pipes, redirects and substitution cannot run.
# "blacknode" maps to this checkout's CLI rather than whatever is on PATH.
_CONSOLE_TOOLS: dict[str, list[str]] = {
    "blacknode": [sys.executable, "-m", "blacknode.cli"],
    "ros2": ["ros2"],
    "colcon": ["colcon"],
    "docker": ["docker"],
    "git": ["git"],
    "python": [sys.executable, "-m"],
    "ping": ["ping"],
}
_SHELL_METACHARACTERS = set(";|&><`$") | {"\n", "\r"}

# One-click diagnostics: ordinary commands, run through the same executor as
# anything typed, so nothing here can do what typing cannot.
_DIAGNOSTICS: list[dict[str, Any]] = [
    {"id": "bn-doctor", "label": "Blacknode doctor", "command": "blacknode doctor", "timeout": 60},
    {"id": "bn-packages", "label": "Installed packages", "command": "blacknode packages list", "timeout": 45},
    {"id": "bn-drivers", "label": "Integration drivers", "command": "blacknode drivers", "timeout": 30},
    {"id": "docker-ps", "label": "Running containers", "command": "docker ps", "timeout": 25},
    {"id": "git-status", "label": "Repo status", "command": "git status --short --branch", "timeout": 20},
    {"id": "ros2-topics", "label": "ROS 2 topics", "command": "ros2 topic list", "timeout": 20},
    {"id": "ros2-nodes", "label": "ROS 2 nodes", "command": "ros2 node list", "timeout": 20},
]


class ConsoleExecReq(BaseModel):
    command: str
    timeout: float = 20.0


def _console_execute(raw: str, timeout: float) -> dict[str, Any]:
    """Run one allow-listed command and record it in the shared console log."""
    raw = (raw or "").strip()
    if not raw:
        raise HTTPException(400, "Empty command")
    if set(raw) & _SHELL_METACHARACTERS:
        raise HTTPException(400, "Shell operators are not supported; run one command at a time")
    try:
        argv = shlex.split(raw)
    except ValueError as exc:
        raise HTTPException(400, f"Could not parse command: {exc}") from exc
    if not argv:
        raise HTTPException(400, "Empty command")

    tool, rest = argv[0], argv[1:]
    prefix = _CONSOLE_TOOLS.get(tool)
    if prefix is None:
        raise HTTPException(
            400,
            f"'{tool}' is not an allowed tool. Allowed: " + ", ".join(sorted(_CONSOLE_TOOLS)),
        )
    timeout = max(1.0, min(float(timeout or 20.0), 180.0))

    # ros2 goes through the runtime so it honours the docker/native backend and
    # is recorded there; everything else runs on the host.
    if tool == "ros2":
        runner = _runtime_callable("ros2", _RUNTIME_MODULES["ros2"], "run_ros2")
        if runner is None:
            raise HTTPException(503, "blacknode-ros2 runtime is not loaded")
        return dict(runner(rest, timeout=timeout))

    env = dict(os.environ)
    if tool in ("blacknode", "python"):
        env["PYTHONPATH"] = os.pathsep.join(
            [str(Path(__file__).resolve().parent.parent / "python"), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)

    logged = command_console.record(raw, backend="host", source="console")
    try:
        # Recorded above with output and exit code, so keep the audit hook from
        # logging the same spawn a second time.
        with command_console.suppress():
            proc = subprocess.run(
                [*prefix, *rest], capture_output=True, text=True, timeout=timeout, env=env,
            )
    except FileNotFoundError:
        message = f"'{tool}' is not installed or not on PATH"
        logged.finish(False, error=message)
        raise HTTPException(404, message)
    except subprocess.TimeoutExpired:
        message = f"`{raw}` timed out after {timeout:g}s"
        logged.finish(False, error=message)
        return {"ok": False, "stdout": "", "stderr": "", "error": message, "timed_out": True}

    logged.finish(
        proc.returncode == 0,
        stdout=proc.stdout,
        stderr=proc.stderr,
        error="" if proc.returncode == 0 else f"exited with code {proc.returncode}",
        exit_code=proc.returncode,
    )
    return {
        "ok": proc.returncode == 0,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "exit_code": proc.returncode,
    }


@app.get("/console")
def console_log(limit: int = 100, after_id: int = 0):
    """Commands Blacknode has shelled out to, newest last."""
    return {
        "entries": command_console.entries(limit=limit, after_id=after_id),
        "active": command_console.active_count(),
        "diagnostics": [{"id": d["id"], "label": d["label"]} for d in _DIAGNOSTICS],
        "tools": sorted(_CONSOLE_TOOLS),
    }


@app.post("/console/clear")
def console_clear():
    command_console.clear()
    return {"ok": True}


@app.post("/console/run/{diagnostic_id}")
def console_run(diagnostic_id: str):
    spec = next((d for d in _DIAGNOSTICS if d["id"] == diagnostic_id), None)
    if spec is None:
        raise HTTPException(404, f"Unknown diagnostic '{diagnostic_id}'")
    return _console_execute(str(spec["command"]), float(spec.get("timeout", 20)))


@app.post("/console/exec")
def console_exec(req: ConsoleExecReq):
    return _console_execute(req.command, req.timeout)


@app.get("/runtime/status")
def runtime_status():
    return _status_value(_runtime_status())


@app.get("/runtime/spatial-viewers")
def spatial_viewer_runtime_status():
    return _status_value(_spatial_viewer_runtime_status())


@app.get("/api/dataset/media/{token}")
@app.get("/dataset/media/{token}")
def dataset_media(token: str):
    resolve_fn = _runtime_callable("dataset", _RUNTIME_MODULES["dataset"], "replay_media_path")
    path = resolve_fn(token) if resolve_fn is not None else None
    if path is None:
        raise HTTPException(404, "Replay media not found")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/dataset/frame/{token}")
@app.get("/dataset/frame/{token}")
def dataset_frame(token: str, index: int = 0):
    frame_fn = _runtime_callable("dataset", _RUNTIME_MODULES["dataset"], "replay_frame")
    try:
        frame = frame_fn(token, index) if frame_fn is not None else None
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    if frame is None:
        raise HTTPException(404, "Replay frame not found")
    return frame


@app.post("/api/dataset/trim")
@app.post("/dataset/trim")
def dataset_trim(req: DatasetTrimReq):
    trim_fn = _runtime_callable("dataset", _RUNTIME_MODULES["dataset"], "trim_replay_episode")
    if trim_fn is None:
        raise HTTPException(503, "blacknode-dataset trim runtime is not loaded")
    try:
        return dict(trim_fn(req.token, req.frame_index, req.side))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/dataset/replay-event")
@app.post("/dataset/replay-event")
def dataset_replay_event(req: DatasetReplayEventReq):
    publish_fn = _runtime_callable("dataset", _RUNTIME_MODULES["dataset"], "publish_replay_event")
    if publish_fn is None:
        raise HTTPException(503, "blacknode-dataset replay stream runtime is not loaded")
    try:
        return dict(publish_fn(req.token, req.frame_index, req.event))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/runtime/stop")
def stop_runtime():
    _stop_active_cook()
    _begin_fresh_cook()
    return _stop_runtime_services()


class NewtonWorkspaceActionReq(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


def _control_newton_workspace(action: str, payload: dict[str, Any] | None = None):
    control_fn = _runtime_callable(
        "newton", _RUNTIME_MODULES["newton"], "control_workspace"
    )
    if control_fn is None:
        raise HTTPException(
            503,
            "The Newton workspace is unavailable. Install and enable the blacknode-newton runtime and a viewer component.",
        )
    try:
        result = dict(control_fn(action, dict(payload or {})))
        saved_artifact = result.get("saved_artifact")
        if isinstance(saved_artifact, dict):
            result["artifact_references"] = _artifact_store.import_value(saved_artifact)
        return result
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/newton/workspace")
def newton_workspace_status():
    return _control_newton_workspace("status")


@app.post("/newton/workspace/{action}")
def newton_workspace_action(action: str, req: NewtonWorkspaceActionReq):
    return _control_newton_workspace(action, req.payload)


# ── Paired hardware devices ──────────────────────────────────────────────────

def _paired_device_client(device_id: str) -> HardwareDeviceClient:
    try:
        return _device_registry.client(device_id)
    except KeyError as exc:
        raise HTTPException(404, "Device not found") from exc
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc


def _device_host_runtime_status(host_id: str) -> dict[str, Any]:
    try:
        host = _device_registry.get_host_public(host_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if host is None:
        raise HTTPException(404, "Device not found")
    if host.get("paused"):
        return {
            "ok": False,
            "paused": True,
            "state": "stopped",
            "runtime_url": host["runtime_url"],
            "error": "Runtime is paused.",
        }
    managed = host.get("managed_runtime")
    if (
        isinstance(managed, dict)
        and str(managed.get("management_mode") or "") == "local"
    ):
        managed_hardware: dict[str, Any] | None = None
        if managed.get("hardware_dir"):
            try:
                managed_hardware = inspect_local_hardware(managed)
            except LocalRuntimeError as exc:
                managed_hardware = {
                    "ok": False,
                    "kind": "hardware",
                    "state": "unavailable",
                    "installed": False,
                    "installed_version": "unknown",
                    "service_url": (
                        f"http://127.0.0.1:{int(managed.get('hardware_port') or 0)}"
                    ),
                    "service_name": str(
                        managed.get("hardware_service_name")
                        or "blacknode-hardware-local-awaiting-device"
                    ),
                    "error": str(exc),
                }
        try:
            runtime_report = inspect_local_runtime(managed)
        except LocalRuntimeError as exc:
            runtime_report = {
                "ok": False,
                "kind": "runtime",
                "state": "unavailable",
                "installed": False,
                "installed_version": "unknown",
                "error": str(exc),
            }
        result = {
            "ok": bool(runtime_report.get("ok")),
            "runtime_url": host["runtime_url"],
            "state": str(runtime_report.get("state") or "unavailable"),
            "installed": bool(runtime_report.get("installed")),
            "installed_version": str(
                runtime_report.get("installed_version") or "unknown"
            ),
        }
        manifest = runtime_report.get("manifest")
        if isinstance(manifest, dict):
            result["manifest"] = manifest
        if runtime_report.get("error"):
            result["error"] = str(runtime_report["error"])
        if managed_hardware is not None:
            result["hardware"] = managed_hardware
        return result
    try:
        manifest = _device_registry.host_client(host_id).manifest()
        if (
            manifest.get("service") != "blacknode-runtime"
            or manifest.get("protocol_version") != 1
        ):
            raise DeviceRegistryError(
                "Runtime service identity or protocol is incompatible."
            )
    except (DeviceRegistryError, KeyError) as exc:
        return {
            "ok": False,
            "state": "unreachable",
            "runtime_url": host["runtime_url"],
            "error": str(exc),
        }
    result = {
        "ok": True,
        "state": "running",
        "runtime_url": host["runtime_url"],
        "manifest": manifest,
    }
    return result


@app.get("/device-hosts")
def list_device_hosts():
    try:
        return {"devices": _device_registry.list_hosts()}
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/device-hosts")
def pair_device_host(req: PairDeviceHostReq):
    try:
        client = RuntimeDeviceClient(req.runtime_url, req.runtime_token)
        manifest = client.manifest()
        host = _device_registry.pair_host(
            name=req.name,
            runtime_url=client.base_url,
            runtime_token=req.runtime_token,
            manifest=manifest,
        )
    except DeviceRegistryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "device": host,
        "runtime": _device_host_runtime_status(host["id"]),
    }


@app.get("/device-hosts/local-install-defaults")
def local_device_host_install_defaults():
    return {"install_dir": str(default_local_runtime_dir())}


def _install_local_device_host_payload(
    req: InstallLocalDeviceHostReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    installed = install_local_runtime(
        install_dir=req.install_dir,
        core_root=Path(__file__).resolve().parents[1],
        progress=progress,
    )
    if progress is not None:
        progress({"progress": 98, "message": "Pairing the local Runtime"})
    runtime_url = str(installed["runtime_url"])
    runtime_token = str(installed["runtime_token"])
    manifest = dict(installed["manifest"])
    host = _device_registry.pair_host(
        name=req.name,
        runtime_url=runtime_url,
        runtime_token=runtime_token,
        manifest=manifest,
        managed_runtime={
            key: installed[key]
            for key in (
                "management_mode",
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
                "config_path",
                "pid_file",
                "log_path",
                "owned_install",
            )
            if key in installed
        },
    )
    if progress is not None:
        progress({"progress": 100, "message": "Local computer is ready"})
    return {
        "device": host,
        "runtime": {
            "ok": True,
            "runtime_url": runtime_url,
            "manifest": manifest,
        },
        "install": {
            key: value
            for key, value in installed.items()
            if key not in {"runtime_token", "manifest"}
        },
    }


@app.post("/device-hosts/local-install-stream")
def install_local_device_host_stream(req: InstallLocalDeviceHostReq):
    def event_stream():
        events: queue.Queue[dict[str, Any]] = queue.Queue()

        def worker() -> None:
            try:
                result = _install_local_device_host_payload(req, progress=events.put)
                events.put({"type": "done", "result": result})
            except (LocalRuntimeError, DeviceRegistryError) as exc:
                events.put({"type": "error", "error": str(exc)})
            except Exception as exc:
                events.put({
                    "type": "error",
                    "error": f"Local Runtime installation failed: {exc}",
                })

        threading.Thread(
            target=worker,
            name="blacknode-local-runtime-install",
            daemon=True,
        ).start()
        while True:
            event = events.get()
            if "type" not in event:
                event = {"type": "progress", **event}
            yield json.dumps(event, separators=(",", ":")) + "\n"
            if event.get("type") in {"done", "error"}:
                break

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.post("/device-hosts/ssh-probe")
def probe_device_host_ssh(req: SshProbeReq):
    try:
        return probe_device(
            host=req.host,
            port=req.port,
        )
    except DeviceInstallError as exc:
        raise HTTPException(400, str(exc)) from exc


def _classify_inspected_ros2_graph(
    inspection: dict[str, Any],
) -> dict[str, Any]:
    graph = (
        dict(inspection.get("ros2_graph") or {})
        if isinstance(inspection.get("ros2_graph"), dict)
        else {}
    )
    topics = list(graph.get("topics") or [])
    nodes = list(graph.get("nodes") or [])
    services = list(graph.get("services") or [])
    graph.setdefault("available", False)
    graph.setdefault("state", "unavailable")
    graph.setdefault("read_only", True)
    graph.setdefault("daemon_used", False)
    graph.setdefault("errors", [])
    graph.update({
        "found": False,
        "capabilities": [],
        "unclassified": [],
        "inventory": {
            "topics": topics,
            "nodes": nodes,
            "services": services,
        },
        "report": "",
    })
    if not graph["available"]:
        errors = [
            str(value or "").strip()
            for value in graph.get("errors", [])
            if str(value or "").strip()
        ]
        graph["report"] = (
            errors[0]
            if errors
            else "The remote ROS 2 graph is unavailable."
        )
        inspection["ros2_graph"] = graph
        return inspection

    discover = _NODE_REGISTRY.get("RobotROSCapabilityDiscover")
    if not callable(discover):
        graph["report"] = (
            "The ROS 2 graph was read successfully. Enable the "
            "blacknode-robot capabilities component to classify it."
        )
        inspection["ros2_graph"] = graph
        return inspection
    try:
        classified = discover({
            "topics": topics,
            "nodes": nodes,
            "services": services,
        })
    except Exception as exc:
        graph["errors"] = [
            *list(graph.get("errors") or []),
            f"Capability classification failed: {exc}",
        ]
        graph["report"] = (
            "The ROS 2 graph was read, but capability classification failed."
        )
        inspection["ros2_graph"] = graph
        return inspection
    if isinstance(classified, dict):
        graph.update({
            key: classified.get(key)
            for key in (
                "found",
                "capabilities",
                "unclassified",
                "inventory",
                "report",
            )
        })
    inspection["ros2_graph"] = graph
    return inspection


def _device_host_live_inspection(host_id: str) -> dict[str, Any]:
    """Read current Runtime and ROS state through the paired device API."""
    try:
        host = _device_registry.get_host_public(host_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if host is None:
        raise HTTPException(404, "Compute device not found")
    if host.get("paused"):
        raise HTTPException(409, "The compute device Runtime is stopped.")
    try:
        client = _device_registry.host_client(host_id)
        manifest = client.manifest()
        diagnostics = client.ros2_diagnostics()
    except (DeviceRegistryError, KeyError) as exc:
        raise HTTPException(
            409,
            "A paired, running Blacknode Runtime is required for live device "
            "data. Install or pair the Runtime from Devices; an SSH password "
            "is not required after pairing.",
        ) from exc
    if (
        manifest.get("service") != "blacknode-runtime"
        or manifest.get("protocol_version") != 1
    ):
        raise HTTPException(409, "The paired Runtime identity is incompatible.")

    topics = [
        str(value or "").strip()
        for value in diagnostics.get("topics", [])
        if str(value or "").strip()
    ]
    nodes = [
        str(value or "").strip()
        for value in diagnostics.get("nodes", [])
        if str(value or "").strip()
    ]
    services = [
        str(value or "").strip()
        for value in diagnostics.get("services", [])
        if str(value or "").strip()
    ]
    errors = [
        str(value or "").strip()
        for value in diagnostics.get("warnings", [])
        if str(value or "").strip()
    ]
    diagnostics_ok = bool(diagnostics.get("ok"))
    try:
        deployment_payload = client.list_deployments()
    except (DeviceRegistryError, AttributeError, TypeError):
        deployment_payload = {}
    robot_targets = [
        {
            "id": str(robot.get("id") or ""),
            "name": str(robot.get("name") or robot.get("id") or "Robot"),
            "remote_device_id": str(robot.get("remote_device_id") or ""),
            "paused": bool(robot.get("paused")),
        }
        for robot in (host.get("robots") or [])
        if isinstance(robot, dict) and str(robot.get("id") or "")
    ]
    robot_ids = {robot["id"] for robot in robot_targets}
    deployments = []
    for value in deployment_payload.get("deployments", []):
        if not isinstance(value, dict):
            continue
        target_id = str(value.get("target_device_id") or "")
        if target_id and target_id not in robot_ids:
            continue
        deployment = _robot_deployment_summary(value)
        deployment.update({
            "target_device_id": target_id,
            "project_id": str(value.get("project_id") or ""),
            "workflow_slug": str(value.get("workflow_slug") or ""),
            "updated_at": str(value.get("updated_at") or ""),
        })
        deployments.append(deployment)
    inspection = {
        "ok": diagnostics_ok,
        "live": diagnostics_ok,
        "read_only": True,
        "checked_at": str(
            diagnostics.get("checked_at")
            or datetime.now().astimezone().isoformat(timespec="seconds")
        ),
        "source": "paired_runtime",
        "environment": {
            "policy": "preserve",
            "os": {"name": "", "version": "", "architecture": ""},
            "python": {"version": "", "executable": ""},
            "nvidia": {
                "available": False,
                "gpus": [],
                "driver_version": "",
                "driver_cuda_version": "",
                "cuda_toolkit_version": "",
                "nvidia_smi": False,
                "nvcc": False,
                "preserved": True,
            },
            "ros2": {
                "available": bool(diagnostics.get("available")),
                "distributions": [],
                "selected_distribution": "",
                "ros2_on_path": bool(diagnostics.get("available")),
                "preserved": True,
            },
            "docker": {
                "available": False,
                "client_version": "",
                "server_version": "",
                "daemon_running": False,
                "service_enabled": False,
                "preserved": True,
            },
            "runtime_setup_packages": [],
            "runtime": {
                "device_id": str(manifest.get("device_id") or ""),
                "version": str(manifest.get("runtime_version") or ""),
                "protocol_version": manifest.get("protocol_version"),
            }
        },
        "host_fingerprint": "",
        "instances": [],
        "suggested_port": 0,
        "suggested_instance_id": "",
        "robots": robot_targets,
        "deployments": deployments,
        "ros2_graph": {
            "available": bool(diagnostics.get("available")),
            "state": "available" if diagnostics_ok else "unavailable",
            "distribution": "",
            "domain_id": "",
            "read_only": True,
            "daemon_used": False,
            "topics": topics,
            "nodes": nodes,
            "services": services,
            "errors": errors,
            "diagnostics_summary": str(diagnostics.get("summary") or ""),
        },
    }
    inspection = _classify_inspected_ros2_graph(inspection)
    streams: list[dict[str, Any]] = []
    seen_streams: set[tuple[str, str, str]] = set()
    graph = inspection.get("ros2_graph")
    capabilities = (
        graph.get("capabilities")
        if isinstance(graph, dict)
        and isinstance(graph.get("capabilities"), list)
        else []
    )
    for candidate in capabilities:
        if not isinstance(candidate, dict):
            continue
        capability = str(candidate.get("capability") or "").strip()
        for evidence in candidate.get("evidence") or []:
            if not isinstance(evidence, dict) or evidence.get("kind") != "topic":
                continue
            topic = str(evidence.get("name") or "").strip()
            message_type = str(evidence.get("message_type") or "").strip()
            key = (capability, topic, message_type)
            if not capability or not topic or key in seen_streams:
                continue
            seen_streams.add(key)
            streams.append({
                "kind": "blacknode.deployed-stream",
                "schema_version": 1,
                "source": "ros2_graph",
                "capability": capability,
                "device_id": host_id,
                "robot_id": "",
                "deployment_id": "",
                "state": "available",
                "available": True,
                "topic": topic,
                "message_type": message_type,
            })
    for deployment in deployments:
        if int(deployment.get("mapping_control_count") or 0) != 1:
            continue
        topic = str(deployment.get("mapping_topic") or "/map")
        key = ("map", topic, "nav_msgs/msg/OccupancyGrid")
        if key in seen_streams:
            continue
        seen_streams.add(key)
        streams.append({
            "kind": "blacknode.deployed-stream",
            "schema_version": 1,
            "source": "deployment",
            "capability": "map",
            "device_id": host_id,
            "robot_id": str(deployment.get("target_device_id") or ""),
            "deployment_id": str(deployment.get("id") or ""),
            "state": str(deployment.get("state") or "stopped"),
            "available": str(deployment.get("state") or "") == "running",
            "topic": topic,
            "message_type": "nav_msgs/msg/OccupancyGrid",
        })
    inspection["streams"] = streams
    return inspection


def _refresh_live_compute_device_params() -> None:
    """Inject ephemeral live state immediately before an editor cook."""
    _session.graph.set_runtime_context(
        __remote_ros2_action__=_remote_ros2_action,
        __remote_ros2_image_action__=_remote_ros2_image_action,
        __message_stream_reader__=_message_stream_reader,
    )
    for node in _session.graph._nodes.values():
        if str(node.get("type") or "") != "ComputeDevice":
            continue
        params = node.get("params")
        if not isinstance(params, dict):
            continue
        device_id = str(params.get("device_id") or "").strip()
        if not device_id:
            params["inspection"] = {}
            continue
        try:
            params["inspection"] = _device_host_live_inspection(device_id)
        except HTTPException as exc:
            params["inspection"] = {
                "ok": False,
                "live": False,
                "read_only": True,
                "checked_at": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "source": "paired_runtime",
                "environment": {},
                "ros2_graph": {
                    "available": False,
                    "state": "unavailable",
                    "read_only": True,
                    "daemon_used": False,
                    "topics": [],
                    "nodes": [],
                    "services": [],
                    "errors": [str(exc.detail)],
                    "found": False,
                    "capabilities": [],
                    "unclassified": [],
                    "inventory": {"topics": [], "nodes": [], "services": []},
                    "report": str(exc.detail),
                },
                "error": str(exc.detail),
            }


@app.get("/device-hosts/{host_id}/live-inspection")
def get_device_host_live_inspection(host_id: str):
    return _device_host_live_inspection(host_id)


@app.post("/device-hosts/inspect")
def inspect_device_host(req: InspectDeviceHostReq):
    try:
        inspection = inspect_runtime(
            host=req.host,
            port=req.port,
            username=req.username,
            password=req.password,
            host_fingerprint=req.host_fingerprint,
        )
        inspection = _classify_inspected_ros2_graph(inspection)
        if req.save_inspection:
            runtime_host = f"[{req.host}]" if ":" in req.host else req.host
            inspection["device"] = _device_registry.register_inspection_host(
                name=req.name,
                runtime_url=f"http://{runtime_host}:8766",
                ssh_host=req.host,
                ssh_port=req.port,
                ssh_username=req.username,
                host_fingerprint=str(
                    inspection.get("host_fingerprint")
                    or req.host_fingerprint
                ),
                inspection=inspection,
            )
        return inspection
    except (DeviceInstallError, DeviceRegistryError) as exc:
        raise HTTPException(400, str(exc)) from exc


def _install_device_host_payload(
    req: InstallDeviceHostReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    installed = install_runtime(
        host=req.host,
        port=req.port,
        username=req.username,
        password=req.password,
        host_fingerprint=req.host_fingerprint,
        action=req.action,
        instance_id=req.instance_id,
        progress=progress,
    )
    host_name = str(req.host or "").strip()
    runtime_host = f"[{host_name}]" if ":" in host_name else host_name
    runtime_port = int(installed["runtime_port"])
    runtime_url = f"http://{runtime_host}:{runtime_port}"
    runtime_token = str(installed["runtime_token"])
    if progress is not None:
        progress({"progress": 98, "message": "Pairing the installed runtime"})
    client = RuntimeDeviceClient(runtime_url, runtime_token)
    manifest = client.manifest()
    host = _device_registry.pair_host(
        name=req.name,
        runtime_url=runtime_url,
        runtime_token=runtime_token,
        manifest=manifest,
        managed_runtime={
            "ssh_host": host_name,
            "ssh_port": req.port,
            "ssh_username": req.username,
            "host_fingerprint": installed["host_fingerprint"],
            "instance_id": installed["instance_id"],
            "runtime_port": runtime_port,
            "service_name": installed["service_name"],
            "install_root": installed.get("install_root", ""),
            "runtime_dir": installed["runtime_dir"],
            "packages_dir": installed.get("packages_dir", ""),
            "firewall_source": installed.get("firewall_source", ""),
            "delivery_mode": installed.get("delivery_mode", "device_online"),
            "core_dir": installed.get("core_dir", ""),
            "python_dir": installed.get("python_dir", ""),
            "python_version": installed.get("python_version", ""),
            "stack_mode": installed.get("stack_mode", "runtime_only"),
            "hardware_dir": installed.get("hardware_dir", ""),
        },
    )
    if progress is not None:
        progress({"progress": 100, "message": "Device is ready"})
    return {
        "device": host,
        "runtime": {
            "ok": True,
            "runtime_url": runtime_url,
            "manifest": manifest,
        },
        "install": {
            key: value
            for key, value in installed.items()
            if key != "runtime_token"
        },
    }


@app.post("/device-hosts/install")
def install_device_host(req: InstallDeviceHostReq):
    try:
        return _install_device_host_payload(req)
    except (DeviceInstallError, DeviceRegistryError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/device-hosts/install-stream")
def install_device_host_stream(req: InstallDeviceHostReq):
    def event_stream():
        events: queue.Queue[dict[str, Any]] = queue.Queue()

        def worker() -> None:
            try:
                result = _install_device_host_payload(req, progress=events.put)
                events.put({"type": "done", "result": result})
            except (DeviceInstallError, DeviceRegistryError) as exc:
                events.put({"type": "error", "error": str(exc)})
            except Exception as exc:
                events.put({
                    "type": "error",
                    "error": f"Device installation failed: {exc}",
                })

        threading.Thread(
            target=worker,
            name="blacknode-device-install",
            daemon=True,
        ).start()
        while True:
            event = events.get()
            if "type" not in event:
                event = {"type": "progress", **event}
            yield json.dumps(event, separators=(",", ":")) + "\n"
            if event.get("type") in {"done", "error"}:
                break

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.get("/device-hosts/{host_id}/runtime-status")
def get_device_host_runtime_status(host_id: str):
    return _device_host_runtime_status(host_id)


@app.post("/device-hosts/{host_id}/management")
def configure_device_host_management(
    host_id: str,
    req: ConfigureDeviceHostManagementReq,
):
    try:
        host = _device_registry.get_host_public(host_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if host is None:
        raise HTTPException(404, "Device not found")
    if isinstance(host.get("managed_runtime"), dict):
        raise HTTPException(409, "SSH management is already configured for this device.")

    try:
        runtime_port = urllib.parse.urlsplit(
            str(host.get("runtime_url") or "")
        ).port
    except ValueError as exc:
        raise HTTPException(409, "The paired runtime URL has an invalid port.") from exc
    if not runtime_port:
        raise HTTPException(
            409,
            "The paired runtime URL must include its service port before SSH "
            "management can be enabled.",
        )

    try:
        inspection = inspect_runtime(
            host=req.host,
            port=req.port,
            username=req.username,
            password=req.password,
            host_fingerprint=req.host_fingerprint,
        )
    except DeviceInstallError as exc:
        raise HTTPException(400, str(exc)) from exc

    expected_device_id = str(host.get("remote_device_id") or "").strip()
    if not expected_device_id:
        try:
            manifest = _device_registry.host_client(host_id).manifest()
            if (
                manifest.get("service") != "blacknode-runtime"
                or manifest.get("protocol_version") != 1
            ):
                raise DeviceRegistryError(
                    "Runtime service identity or protocol is incompatible."
                )
            expected_device_id = str(manifest.get("device_id") or "").strip()
            _device_registry.set_host_remote_device_id(
                host_id,
                expected_device_id,
            )
        except KeyError as exc:
            raise HTTPException(404, "Device not found") from exc
        except DeviceRegistryError as exc:
            raise HTTPException(
                409,
                "Blacknode could not recover a stable identity from this paired "
                f"runtime. Pair the runtime again first. {exc}",
            ) from exc
    matches = [
        instance
        for instance in inspection.get("instances", [])
        if (
            isinstance(instance, dict)
            and int(instance.get("port") or 0) == runtime_port
            and bool(instance.get("service_installed"))
            and str(instance.get("device_id") or "") == expected_device_id
        )
    ]
    if not matches:
        raise HTTPException(
            409,
            f"SSH connected, but no installed Blacknode runtime service on port "
            f"{runtime_port} matches this paired device ({expected_device_id or 'unknown ID'}).",
        )
    if len(matches) != 1:
        raise HTTPException(
            409,
            f"Multiple installed runtime services match port {runtime_port}; "
            "resolve the duplicate services before enabling SSH management.",
        )
    instance = matches[0]
    management = {
        "ssh_host": str(req.host or "").strip(),
        "ssh_port": int(req.port),
        "ssh_username": str(req.username or "").strip(),
        "host_fingerprint": str(inspection.get("host_fingerprint") or ""),
        "instance_id": str(instance.get("instance_id") or ""),
        "runtime_port": runtime_port,
        "service_name": str(instance.get("service_name") or ""),
        "install_root": str(instance.get("install_root") or ""),
        "runtime_dir": str(instance.get("runtime_dir") or ""),
        "packages_dir": str(instance.get("packages_dir") or ""),
    }
    if not all(
        management.get(key)
        for key in (
            "ssh_host",
            "ssh_username",
            "host_fingerprint",
            "instance_id",
            "service_name",
            "runtime_dir",
        )
    ):
        raise HTTPException(
            409,
            "The matching runtime service does not expose a complete management identity.",
        )
    try:
        device = _device_registry.set_host_management(host_id, management)
    except KeyError as exc:
        raise HTTPException(404, "Device not found") from exc
    except DeviceRegistryError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "ok": True,
        "device": device,
        "instance": {
            key: value
            for key, value in instance.items()
            if not str(key).startswith("_")
        },
        "summary": (
            f"SSH management enabled for {management['service_name']} on "
            f"runtime port {runtime_port}."
        ),
    }


def _raise_rpc_error(result: dict[str, Any], *, action: str) -> None:
    error = result.get("error") if isinstance(result, dict) else None
    if not error:
        return
    message = (
        str(error.get("message") or error)
        if isinstance(error, dict)
        else str(error)
    )
    raise DeviceRegistryError(f"Could not {action} robot: {message}")


@app.post("/device-hosts/{host_id}/lifecycle")
def control_device_host_lifecycle(host_id: str, req: RuntimeLifecycleReq):
    try:
        return _control_device_host_lifecycle_payload(host_id, req)
    except DeviceInstallError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (DeviceRegistryError, KeyError) as exc:
        raise HTTPException(502, str(exc)) from exc


def _control_device_host_lifecycle_payload(
    host_id: str,
    req: RuntimeLifecycleReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    action = str(req.action or "").strip().lower()
    if action not in {"pause", "resume"}:
        raise HTTPException(400, "Device action must be pause or resume.")
    report(5, "Checking the managed device")
    try:
        host = _device_registry.get_host_public(host_id)
    except DeviceRegistryError as exc:
        raise DeviceRegistryError(str(exc)) from exc
    if host is None:
        raise HTTPException(404, "Device not found")
    managed = host.get("managed_runtime")
    if not isinstance(managed, dict):
        raise HTTPException(
            409,
            "This runtime was paired manually. Pause or resume its service on the "
            "device with ./service.sh stop or ./service.sh start.",
        )

    stopped_deployments: list[str] = []
    controlled_robots: list[str] = []
    warnings: list[str] = []
    if action == "pause":
        report(15, f"Stopping deployments through {host['runtime_url']}")
        try:
            deployments = _device_registry.host_client(host_id).list_deployments()
            for deployment in deployments.get("deployments") or []:
                if (
                    isinstance(deployment, dict)
                    and str(deployment.get("state") or "") == "running"
                ):
                    deployment_id = str(deployment.get("id") or "")
                    if deployment_id:
                        _device_registry.host_client(host_id).stop_deployment(
                            deployment_id
                        )
                        stopped_deployments.append(deployment_id)
        except (DeviceRegistryError, KeyError) as exc:
            warnings.append(
                f"Deployment runtime {host['runtime_url']} could not be reached: {exc}"
            )
        robots = list(host.get("robots") or [])
        for index, robot in enumerate(robots):
            robot_id = str(robot.get("id") or "")
            if not robot_id:
                continue
            report(
                30 + int(30 * (index + 1) / max(1, len(robots))),
                f"Stopping and disarming {robot.get('name') or robot_id}",
            )
            try:
                result = _paired_device_client(robot_id).rpc({
                    "jsonrpc": "2.0",
                    "id": f"device-pause-{robot_id}",
                    "method": "stop",
                    "params": {},
                })
                _raise_rpc_error(result, action="pause")
                _device_registry.set_device_paused(robot_id, True)
                controlled_robots.append(robot_id)
            except (DeviceRegistryError, HTTPException, KeyError) as exc:
                detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                warnings.append(
                    f"Robot {robot.get('name') or robot_id} could not be stopped: {detail}"
                )

    report(70, f"{'Stopping' if action == 'pause' else 'Starting'} the runtime service")
    if str(managed.get("management_mode") or "") == "local":
        runtime = (
            stop_local_runtime(managed)
            if action == "pause"
            else ensure_local_runtime(managed)
        )
    else:
        runtime = control_runtime(
            host=str(managed.get("ssh_host") or ""),
            port=int(managed.get("ssh_port") or 22),
            username=str(managed.get("ssh_username") or ""),
            password=req.password,
            host_fingerprint=str(managed.get("host_fingerprint") or ""),
            instance_id=str(managed.get("instance_id") or "default"),
            action=action,
        )

    if action == "resume":
        robots = list(host.get("robots") or [])
        for index, robot in enumerate(robots):
            robot_id = str(robot.get("id") or "")
            if not robot_id:
                continue
            report(
                78 + int(17 * (index + 1) / max(1, len(robots))),
                f"Reconnecting {robot.get('name') or robot_id} in a disarmed state",
            )
            try:
                result = _paired_device_client(robot_id).rpc({
                    "jsonrpc": "2.0",
                    "id": f"device-resume-{robot_id}",
                    "method": "resume",
                    "params": {},
                })
                _raise_rpc_error(result, action="resume")
                _device_registry.set_device_paused(robot_id, False)
                controlled_robots.append(robot_id)
            except (DeviceRegistryError, HTTPException, KeyError) as exc:
                detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                warnings.append(
                    f"Robot {robot.get('name') or robot_id} did not reconnect: {detail}"
                )

    device = _device_registry.set_host_paused(host_id, action == "pause")
    summary = (
        "Device paused; its runtime is stopped and reachable robot endpoints accepted the stop request."
        if action == "pause"
        else "Device resumed; its runtime and robot monitoring were restored. Robots remain disarmed."
    )
    if warnings:
        summary += (
            f" Completed with {len(warnings)} warning{'s' if len(warnings) != 1 else ''}; "
            "verify the listed robot and physical torque state."
        )
    report(100, summary)
    return {
        "ok": True,
        "action": action,
        "runtime": runtime,
        "device": device,
        "stopped_deployments": stopped_deployments,
        "controlled_robots": controlled_robots,
        "warnings": warnings,
        "summary": summary,
    }


def _lifecycle_stream(worker: Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]]):
    def event_stream():
        events: queue.Queue[dict[str, Any]] = queue.Queue()

        def run() -> None:
            try:
                events.put({"progress": 1, "message": "Starting lifecycle action"})
                events.put({"type": "done", "result": worker(events.put)})
            except HTTPException as exc:
                events.put({"type": "error", "error": str(exc.detail)})
            except (
                DeviceInstallError,
                DeviceRegistryError,
                LocalRuntimeError,
                KeyError,
            ) as exc:
                events.put({"type": "error", "error": str(exc)})
            except Exception as exc:
                events.put({"type": "error", "error": f"Lifecycle action failed: {exc}"})

        threading.Thread(
            target=run,
            name="blacknode-device-lifecycle",
            daemon=True,
        ).start()
        while True:
            event = events.get()
            if "type" not in event:
                event = {"type": "progress", **event}
            yield json.dumps(event, separators=(",", ":")) + "\n"
            if event.get("type") in {"done", "error"}:
                break

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.post("/device-hosts/{host_id}/lifecycle-stream")
def stream_device_host_lifecycle(host_id: str, req: RuntimeLifecycleReq):
    return _lifecycle_stream(
        lambda progress: _control_device_host_lifecycle_payload(host_id, req, progress)
    )


def _manage_local_package_payload(
    host_id: str,
    kind: str,
    req: LocalPackageActionReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    host = _device_registry.get_host_public(host_id)
    if host is None:
        raise HTTPException(404, "Device not found")
    managed = host.get("managed_runtime")
    if (
        not isinstance(managed, dict)
        or str(managed.get("management_mode") or "") != "local"
    ):
        raise HTTPException(409, "Package controls are available for local devices.")
    clean_kind = str(kind or "").strip().lower()
    clean_action = str(req.action or "").strip().lower()
    result = manage_local_package(
        managed,
        kind=clean_kind,
        action=clean_action,
        core_root=Path(__file__).resolve().parents[1],
        progress=progress,
    )
    return {
        "ok": True,
        "kind": clean_kind,
        "action": clean_action,
        "package": result,
        "runtime": _device_host_runtime_status(host_id),
    }


@app.post("/device-hosts/{host_id}/local-packages/{kind}/action-stream")
def stream_local_package_action(
    host_id: str,
    kind: str,
    req: LocalPackageActionReq,
):
    return _lifecycle_stream(
        lambda progress: _manage_local_package_payload(
            host_id,
            kind,
            req,
            progress,
        )
    )


def _manage_remote_hardware_package_payload(
    host_id: str,
    req: RemoteHardwarePackageActionReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({"progress": percent, "message": message})

    host = _device_registry.get_host_public(host_id)
    if host is None:
        raise HTTPException(404, "Device not found")
    managed = host.get("managed_runtime")
    if not isinstance(managed, dict) or str(managed.get("management_mode") or "") == "local":
        raise HTTPException(409, "Remote Hardware package controls require verified SSH management.")
    action = str(req.action or "").strip().lower()
    if action not in {"run", "stop", "restart"}:
        raise HTTPException(400, "Hardware package action must be run, stop, or restart.")
    if not str(req.password or ""):
        raise HTTPException(400, "Enter the SSH password to control the Hardware package.")
    robots = list(host.get("robots") or [])
    if not robots:
        raise HTTPException(409, "Attach a robot before controlling the remote Hardware package.")

    service_action = {"run": "start", "stop": "stop", "restart": "restart"}[action]
    services: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, robot in enumerate(robots):
        robot_id = str(robot.get("id") or "")
        robot_name = str(robot.get("name") or robot_id or "Robot")
        if not robot_id:
            continue
        if action in {"stop", "restart"}:
            report(
                5 + int(index * 35 / max(1, len(robots))),
                f"Stopping deployments and disarming {robot_name}",
            )
            try:
                _control_robot_lifecycle_payload(
                    robot_id,
                    RobotLifecycleReq(action="pause"),
                )
            except (DeviceRegistryError, HTTPException, KeyError) as exc:
                detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                raise HTTPException(
                    409,
                    f"{robot_name} could not confirm deployment stop and disarm before "
                    f"service control: {detail}",
                ) from exc
        try:
            hardware_port = urllib.parse.urlsplit(str(robot.get("base_url") or "")).port
        except ValueError as exc:
            raise HTTPException(409, f"{robot_name} has an invalid hardware service URL.") from exc
        if not hardware_port:
            raise HTTPException(409, f"{robot_name} has no hardware service port.")
        report(
            40 + int(index * 50 / max(1, len(robots))),
            f"{'Stopping' if service_action == 'stop' else service_action.title() + 'ing'} "
            f"{robot_name} Hardware service",
        )
        services.append(restart_hardware_service(
            host=str(managed.get("ssh_host") or ""),
            port=int(managed.get("ssh_port") or 22),
            username=str(managed.get("ssh_username") or ""),
            password=req.password,
            host_fingerprint=str(managed.get("host_fingerprint") or ""),
            hardware_port=hardware_port,
            action=service_action,
        ))
        _device_registry.set_device_paused(robot_id, action == "stop")

    hardware_state = "stopped" if action == "stop" else "running"
    device = _device_registry.set_host_management(
        host_id,
        {**managed, "hardware_state": hardware_state},
    )
    summary = (
        f"Hardware package {hardware_state} across {len(services)} robot service"
        f"{'' if len(services) == 1 else 's'}; motion remains disarmed."
    )
    if warnings:
        summary += f" Completed with {len(warnings)} safety warning{'' if len(warnings) == 1 else 's'}."
    report(100, summary)
    return {
        "ok": True,
        "action": action,
        "state": hardware_state,
        "services": services,
        "device": device,
        "warnings": warnings,
        "summary": summary,
    }


@app.post("/device-hosts/{host_id}/hardware-package/action-stream")
def stream_remote_hardware_package_action(
    host_id: str,
    req: RemoteHardwarePackageActionReq,
):
    return _lifecycle_stream(
        lambda progress: _manage_remote_hardware_package_payload(host_id, req, progress)
    )


def _update_device_host_payload(
    host_id: str,
    req: UpdateManagedDeviceReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    scope = str(req.scope or "all").strip().lower()
    if scope not in {"all", "runtime", "hardware"}:
        raise HTTPException(400, "Update scope must be all, runtime, or hardware.")
    host = _device_registry.get_host_public(host_id)
    if host is None:
        raise HTTPException(404, "Device not found")
    managed = host.get("managed_runtime")
    if not isinstance(managed, dict):
        raise HTTPException(
            409,
            "Enable SSH controls for this device before updating its services.",
        )
    if str(managed.get("management_mode") or "") == "local":
        operation = str(req.operation or "auto").strip().lower()
        if operation not in {"auto", "update", "reinstall"}:
            raise HTTPException(
                400,
                "Local package operation must be update or reinstall.",
            )
        before_report = inspect_local_package_updates(managed)
        before_components = {
            str(item.get("kind") or ""): item
            for item in before_report.get("components") or []
            if isinstance(item, dict)
        }
        kinds = ["runtime", "hardware"] if scope == "all" else [scope]
        results: list[dict[str, Any]] = []
        for index, kind in enumerate(kinds):
            before = before_components.get(kind)
            if before is None:
                raise HTTPException(409, f"The local {kind.title()} package is unavailable.")
            selected_operation = (
                "update"
                if operation == "auto" and before.get("update_available")
                else "reinstall"
                if operation == "auto"
                else operation
            )
            report(
                10 + int(index * 75 / max(1, len(kinds))),
                f"{selected_operation.title()}ing the local {kind.title()} package",
            )
            package_result = manage_local_package(
                managed,
                kind=kind,
                action=selected_operation,
                core_root=Path(__file__).resolve().parents[1],
                progress=lambda value, offset=index: report(
                    10
                    + int(offset * 75 / max(1, len(kinds)))
                    + int(
                        int(value.get("progress") or 0)
                        * 70
                        / max(1, len(kinds))
                        / 100
                    ),
                    str(value.get("message") or "Managing local package"),
                ),
            )
            results.append(package_result)
        after_report = inspect_local_package_updates(managed)
        after_components = {
            str(item.get("kind") or ""): item
            for item in after_report.get("components") or []
            if isinstance(item, dict)
        }
        update_components: list[dict[str, Any]] = []
        for kind in kinds:
            before = before_components[kind]
            after = after_components.get(kind, before)
            update_components.append({
                "kind": kind,
                "service_name": str(after.get("service_name") or ""),
                "port": int(after.get("port") or 0),
                "before": dict(before.get("installed") or {}),
                "after": dict(after.get("installed") or {}),
                "reported_version": str(
                    after.get("reported_version")
                    or (after.get("installed") or {}).get("version")
                    or "unknown"
                ),
                "changed": (
                    (before.get("installed") or {}).get("commit")
                    != (after.get("installed") or {}).get("commit")
                ),
                "state": str(after.get("state") or "unknown"),
            })
        device = _device_registry.get_host_public(host_id)
        summary = (
            f"Local {' + '.join(kind.title() for kind in kinds)} package "
            f"{'operation' if len(kinds) == 1 else 'operations'} completed."
        )
        report(100, summary)
        return {
            "ok": True,
            "scope": scope,
            "device": device,
            "update": {"ok": True, "components": update_components},
            "runtime": (
                inspect_local_runtime(managed).get("manifest")
                if str(managed.get("runtime_dir") or "")
                else {}
            ) or {},
            "robots": [],
            "stopped_deployments": [],
            "controlled_robots": [],
            "warnings": [],
            "summary": summary,
            "packages": results,
        }
    if not str(req.password or ""):
        raise HTTPException(400, "Enter the SSH password to update this device.")

    robots = list(host.get("robots") or [])
    hardware_ports: list[int] = []
    hardware_device_ids: dict[int, str] = {}
    for robot in robots:
        try:
            hardware_port = urllib.parse.urlsplit(
                str(robot.get("base_url") or "")
            ).port
        except ValueError as exc:
            raise HTTPException(
                409,
                f"{robot.get('name') or 'A robot'} has an invalid hardware URL.",
            ) from exc
        if not hardware_port:
            raise HTTPException(
                409,
                f"{robot.get('name') or 'A robot'} has no hardware service port.",
            )
        hardware_ports.append(hardware_port)
        hardware_device_ids[hardware_port] = str(
            robot.get("remote_device_id") or ""
        )
    include_runtime = scope in {"all", "runtime"}
    selected_hardware_ports = (
        hardware_ports if scope in {"all", "hardware"} else []
    )
    if scope == "hardware" and not selected_hardware_ports:
        operation = str(req.operation or "auto").strip().lower()
        if operation not in {"auto", "update", "reinstall"}:
            raise HTTPException(
                400,
                "Hardware package operation must be update or reinstall.",
            )
        report(10, "Reinstalling Robot Hardware before robot discovery")
        installed = _install_device_host_hardware_payload(
            host_id,
            DiscoverHostRobotsReq(password=req.password),
            progress=lambda value: report(
                10 + int(int(value.get("progress") or 0) * 0.85),
                str(value.get("message") or "Installing Robot Hardware"),
            ),
        )
        hardware_commit = str(
            (installed.get("install") or {}).get("hardware_commit") or ""
        )
        summary = (
            "Robot Hardware package reinstalled. Use Find and attach robots "
            "to configure the detected hardware provider."
        )
        report(100, summary)
        return {
            "ok": True,
            "scope": "hardware",
            "device": installed["device"],
            "update": {
                "ok": True,
                "components": [{
                    "kind": "hardware",
                    "service_name": "blacknode-hardware-awaiting-device",
                    "port": 0,
                    "before": {"version": "unknown", "commit": ""},
                    "after": {
                        "version": "unknown",
                        "commit": hardware_commit[:12],
                    },
                    "changed": True,
                    "state": "configured",
                    "source_mode": "snapshot",
                }],
            },
            "runtime": {},
            "robots": [],
            "stopped_deployments": [],
            "controlled_robots": [],
            "warnings": [],
            "summary": summary,
        }

    stopped_deployments: list[str] = []
    controlled_robots: list[str] = []
    warnings: list[str] = []
    runtime_api_unavailable = False
    runtime_manifest_before: dict[str, Any] | None = None
    report(5, "Stopping running deployments")
    if not host.get("paused"):
        last_runtime_error = ""
        for attempt in range(3):
            try:
                runtime_client = _device_registry.host_client(host_id)
                if runtime_manifest_before is None:
                    runtime_manifest_before = runtime_client.manifest()
                for deployment in runtime_client.list_deployments().get("deployments") or []:
                    if (
                        isinstance(deployment, dict)
                        and str(deployment.get("state") or "") == "running"
                        and str(deployment.get("id") or "")
                    ):
                        deployment_id = str(deployment["id"])
                        runtime_client.stop_deployment(deployment_id)
                        stopped_deployments.append(deployment_id)
                last_runtime_error = ""
                break
            except (DeviceRegistryError, KeyError) as exc:
                last_runtime_error = str(exc)
                if attempt < 2:
                    time.sleep(0.35)
        if last_runtime_error:
            runtime_api_unavailable = True
            warnings.append(
                "The Runtime API could not stop deployments directly. Blacknode "
                "used the verified SSH service identity to stop the Runtime and its "
                "deployment process group before updating. "
                f"API error: {last_runtime_error}"
            )

    report(12, "Stopping and disarming attached robots")
    for robot in robots:
        robot_id = str(robot.get("id") or "")
        if not robot_id:
            continue
        try:
            result = _paired_device_client(robot_id).rpc({
                "jsonrpc": "2.0",
                "id": f"device-update-stop-{robot_id}",
                "method": "stop",
                "params": {},
            })
            _raise_rpc_error(result, action="prepare update for")
            _device_registry.set_device_paused(robot_id, True)
            controlled_robots.append(robot_id)
        except (DeviceRegistryError, HTTPException, KeyError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            raise DeviceRegistryError(
                f"Robot {robot.get('name') or robot_id} could not be stopped "
                f"before update: {detail}"
            ) from exc

    runtime_paused_for_fallback = False
    try:
        if runtime_api_unavailable and not host.get("paused"):
            report(14, "Stopping the unreachable Runtime safely over SSH")
            control_runtime(
                host=str(managed.get("ssh_host") or ""),
                port=int(managed.get("ssh_port") or 22),
                username=str(managed.get("ssh_username") or ""),
                password=req.password,
                host_fingerprint=str(managed.get("host_fingerprint") or ""),
                instance_id=str(managed.get("instance_id") or "default"),
                action="pause",
            )
            runtime_paused_for_fallback = True
        replace_runtime_snapshot = bool(
            include_runtime
            and str(managed.get("delivery_mode") or "") == "pc_assisted"
        )
        if replace_runtime_snapshot:
            report(15, "Preparing the latest Runtime bundle on this computer")
            installed = install_runtime(
                host=str(managed.get("ssh_host") or ""),
                port=int(managed.get("ssh_port") or 22),
                username=str(managed.get("ssh_username") or ""),
                password=req.password,
                host_fingerprint=str(managed.get("host_fingerprint") or ""),
                action="replace_runtime",
                instance_id=str(managed.get("instance_id") or "default"),
                progress=lambda value: report(
                    15 + int(int(value.get("progress") or 0) * 0.6),
                    str(value.get("message") or "Replacing Runtime snapshot"),
                ),
            )
            runtime_host = str(managed.get("ssh_host") or "").strip()
            runtime_host = f"[{runtime_host}]" if ":" in runtime_host else runtime_host
            runtime_url = f"http://{runtime_host}:{int(installed['runtime_port'])}"
            runtime_token = str(installed["runtime_token"])
            replacement_manifest = RuntimeDeviceClient(
                runtime_url,
                runtime_token,
            ).manifest()
            replacement_management = dict(managed)
            replacement_management.update({
                "host_fingerprint": installed["host_fingerprint"],
                "instance_id": installed["instance_id"],
                "runtime_port": installed["runtime_port"],
                "service_name": installed["service_name"],
                "install_root": installed.get("install_root", ""),
                "runtime_dir": installed["runtime_dir"],
                "packages_dir": installed.get("packages_dir", ""),
                "firewall_source": installed.get("firewall_source", ""),
                "delivery_mode": installed.get("delivery_mode", "pc_assisted"),
                "core_dir": installed.get("core_dir", ""),
                "python_dir": installed.get("python_dir", ""),
                "python_version": installed.get("python_version", ""),
                "stack_mode": installed.get("stack_mode", "runtime_only"),
                "hardware_dir": installed.get("hardware_dir", ""),
            })
            _device_registry.pair_host(
                name=str(host.get("name") or "Compute device"),
                runtime_url=runtime_url,
                runtime_token=runtime_token,
                manifest=replacement_manifest,
                managed_runtime=replacement_management,
                host_id=host_id,
            )
            before_version = str(
                (runtime_manifest_before or {}).get("runtime_version") or "unknown"
            )
            after_version = str(
                replacement_manifest.get("runtime_version") or "unknown"
            )
            update = {
                "ok": True,
                "components": [{
                    "kind": "runtime",
                    "service_name": str(installed.get("service_name") or ""),
                    "port": int(installed.get("runtime_port") or 0),
                    "before": {"version": before_version, "commit": ""},
                    "after": {
                        "version": after_version,
                        "commit": str(installed.get("runtime_commit") or "")[:12],
                    },
                    "changed": before_version != after_version,
                    "state": "active",
                    "source_mode": "snapshot",
                }],
                "host_fingerprint": installed["host_fingerprint"],
            }
            if selected_hardware_ports:
                hardware_update = update_managed_services(
                    host=str(managed.get("ssh_host") or ""),
                    port=int(managed.get("ssh_port") or 22),
                    username=str(managed.get("ssh_username") or ""),
                    password=req.password,
                    host_fingerprint=str(managed.get("host_fingerprint") or ""),
                    instance_id=str(managed.get("instance_id") or "default"),
                    runtime_port=int(installed.get("runtime_port") or 0),
                    hardware_ports=selected_hardware_ports,
                    hardware_device_ids={
                        hardware_port: hardware_device_ids.get(hardware_port, "")
                        for hardware_port in selected_hardware_ports
                    },
                    include_runtime=False,
                    stack_mode=str(managed.get("stack_mode") or "runtime_only"),
                    progress=lambda value: report(
                        75 + int(int(value.get("progress") or 0) * 0.15),
                        str(value.get("message") or "Updating Robot Hardware"),
                    ),
                )
                update["components"].extend(hardware_update.get("components") or [])
        else:
            update = update_managed_services(
                host=str(managed.get("ssh_host") or ""),
                port=int(managed.get("ssh_port") or 22),
                username=str(managed.get("ssh_username") or ""),
                password=req.password,
                host_fingerprint=str(managed.get("host_fingerprint") or ""),
                instance_id=str(managed.get("instance_id") or "default"),
                runtime_port=int(managed.get("runtime_port") or 0),
                hardware_ports=selected_hardware_ports,
                hardware_device_ids={
                    hardware_port: hardware_device_ids.get(hardware_port, "")
                    for hardware_port in selected_hardware_ports
                },
                include_runtime=include_runtime,
                stack_mode=str(managed.get("stack_mode") or "runtime_only"),
                progress=lambda value: report(
                    15 + int(int(value.get("progress") or 0) * 0.75),
                    str(value.get("message") or "Updating managed services"),
                ),
            )
    except Exception:
        if runtime_paused_for_fallback:
            try:
                control_runtime(
                    host=str(managed.get("ssh_host") or ""),
                    port=int(managed.get("ssh_port") or 22),
                    username=str(managed.get("ssh_username") or ""),
                    password=req.password,
                    host_fingerprint=str(managed.get("host_fingerprint") or ""),
                    instance_id=str(managed.get("instance_id") or "default"),
                    action="resume",
                )
            except DeviceInstallError:
                pass
        for robot_id in controlled_robots:
            try:
                result = _paired_device_client(robot_id).rpc({
                    "jsonrpc": "2.0",
                    "id": f"device-update-recover-{robot_id}",
                    "method": "resume",
                    "params": {},
                })
                _raise_rpc_error(result, action="recover after update failure for")
                _device_registry.set_device_paused(robot_id, False)
            except (DeviceRegistryError, HTTPException, KeyError):
                pass
        raise

    report(92, "Verifying reported runtime and hardware versions")
    runtime_manifest: dict[str, Any] | None = None
    extension_update: dict[str, Any] = {
        "ok": True,
        "installed": [],
        "already_present": [],
        "activated": [],
        "messages": [],
    }
    runtime_error = ""
    for _attempt in range(40):
        try:
            candidate = _device_registry.host_client(host_id).manifest()
            if (
                candidate.get("service") == "blacknode-runtime"
                and candidate.get("protocol_version") == 1
            ):
                runtime_manifest = candidate
                break
        except (DeviceRegistryError, KeyError) as exc:
            runtime_error = str(exc)
            time.sleep(0.25)
    if runtime_manifest is None:
        raise DeviceRegistryError(
            f"The runtime service updated but did not pass verification: {runtime_error}"
        )

    if include_runtime:
        extension_specs, extension_warnings = _runtime_extension_update_specs(
            runtime_manifest_before or runtime_manifest
        )
        warnings.extend(extension_warnings)
        if extension_specs:
            if "package_refresh_v1" not in set(
                runtime_manifest.get("features") or []
            ):
                raise DeviceRegistryError(
                    "Runtime updated but does not support refreshing installed "
                    "workflow packages. Install Runtime 0.3.15 or newer."
                )
            report(
                93,
                f"Updating {len(extension_specs)} installed workflow package"
                f"{'s' if len(extension_specs) != 1 else ''}",
            )
            extension_update = _device_registry.host_client(
                host_id
            ).sync_packages(extension_specs)
            if extension_update.get("ok") is not True:
                raise DeviceRegistryError(
                    "The Runtime updated, but its workflow packages did not."
                )
            # Package modules are imported into Runtime and deployment
            # processes. Reload Runtime after refreshing the checkouts so every
            # later deployment start sees one coherent package set.
            report(95, "Reloading Runtime with updated workflow packages")
            control_runtime(
                host=str(managed.get("ssh_host") or ""),
                port=int(managed.get("ssh_port") or 22),
                username=str(managed.get("ssh_username") or ""),
                password=req.password,
                host_fingerprint=str(managed.get("host_fingerprint") or ""),
                instance_id=str(managed.get("instance_id") or "default"),
                action="pause",
            )
            control_runtime(
                host=str(managed.get("ssh_host") or ""),
                port=int(managed.get("ssh_port") or 22),
                username=str(managed.get("ssh_username") or ""),
                password=req.password,
                host_fingerprint=str(managed.get("host_fingerprint") or ""),
                instance_id=str(managed.get("instance_id") or "default"),
                action="resume",
            )
            runtime_manifest = None
            for _attempt in range(40):
                try:
                    candidate = _device_registry.host_client(host_id).manifest()
                    if (
                        candidate.get("service") == "blacknode-runtime"
                        and candidate.get("protocol_version") == 1
                    ):
                        runtime_manifest = candidate
                        break
                except (DeviceRegistryError, KeyError) as exc:
                    runtime_error = str(exc)
                    time.sleep(0.25)
            if runtime_manifest is None:
                raise DeviceRegistryError(
                    "Workflow packages updated, but Runtime did not return after "
                    f"its package reload: {runtime_error}"
                )

    verified_robots: list[dict[str, Any]] = []
    for robot in robots:
        robot_id = str(robot.get("id") or "")
        expected_id = str(robot.get("remote_device_id") or "")
        verified_status: dict[str, Any] | None = None
        last_error = ""
        for _attempt in range(40):
            try:
                candidate = _paired_device_client(robot_id).status()
                actual_id = str(candidate.get("device_id") or "")
                if expected_id and actual_id != expected_id:
                    raise DeviceRegistryError(
                        f"returned robot '{actual_id}', expected '{expected_id}'"
                    )
                verified_status = candidate
                break
            except (DeviceRegistryError, HTTPException) as exc:
                last_error = exc.detail if isinstance(exc, HTTPException) else str(exc)
                time.sleep(0.25)
        if verified_status is None:
            raise DeviceRegistryError(
                f"{robot.get('name') or robot_id} did not pass verification: {last_error}"
            )
        if verified_status.get("armed"):
            raise DeviceRegistryError(
                f"{robot.get('name') or robot_id} returned armed after its update."
            )
        if verified_status.get("torque_enabled") is True:
            warnings.append(
                f"{robot.get('name') or robot_id} reports physical servo torque enabled. "
                "The software update did not turn off actuator power."
            )
        verified_status["paused"] = False
        _device_registry.set_device_paused(robot_id, False)
        verified_robots.append({
            "id": robot_id,
            "name": str(robot.get("name") or robot_id),
            "port": urllib.parse.urlsplit(str(robot.get("base_url") or "")).port,
            "software_version": str(
                verified_status.get("software_version") or "not reported"
            ),
            "status": verified_status,
        })

    for component in update.get("components") or []:
        if not isinstance(component, dict):
            continue
        if component.get("kind") == "runtime":
            component["reported_version"] = str(
                runtime_manifest.get("runtime_version") or "not reported"
            )
            continue
        component_port = int(component.get("port") or 0)
        robot_report = next(
            (
                item for item in verified_robots
                if int(item.get("port") or 0) == component_port
            ),
            None,
        )
        if robot_report:
            component["reported_version"] = robot_report["software_version"]

    device = _device_registry.set_host_paused(host_id, False)
    changed = sum(
        1
        for component in update.get("components") or []
        if isinstance(component, dict) and component.get("changed")
    )
    service_count = len(update.get("components") or [])
    current_reinstalled = service_count - changed
    if changed:
        summary = (
            f"Updated {changed} managed service"
            f"{'s' if changed != 1 else ''}"
            + (
                f" and reinstalled {current_reinstalled} current service"
                f"{'s' if current_reinstalled != 1 else ''}"
                if current_reinstalled
                else ""
            )
            + ". "
        )
    else:
        summary = (
            f"Reinstalled {service_count} current managed service"
            f"{'s' if service_count != 1 else ''}. "
        )
    summary += (
        "The runtime and robot monitoring are online, and Blacknode motion remains disarmed."
    )
    refreshed_extensions = len(extension_update.get("already_present") or []) + len(
        extension_update.get("installed") or []
    )
    if refreshed_extensions:
        summary += (
            f" Refreshed {refreshed_extensions} installed workflow package"
            f"{'s' if refreshed_extensions != 1 else ''}."
        )
    if warnings:
        summary += (
            f" Completed with {len(warnings)} warning"
            f"{'s' if len(warnings) != 1 else ''}; check the report."
        )
    report(100, summary)
    return {
        "ok": True,
        "scope": scope,
        "device": device,
        "update": update,
        "runtime": runtime_manifest,
        "extension_packages": extension_update,
        "robots": verified_robots,
        "stopped_deployments": stopped_deployments,
        "controlled_robots": controlled_robots,
        "warnings": warnings,
        "summary": summary,
    }


@app.post("/device-hosts/{host_id}/update-stream")
def stream_device_host_update(host_id: str, req: UpdateManagedDeviceReq):
    return _lifecycle_stream(
        lambda progress: _update_device_host_payload(host_id, req, progress)
    )


def _check_device_host_updates_payload(
    host_id: str,
    req: UpdateManagedDeviceReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    host = _device_registry.get_host_public(host_id)
    if host is None:
        raise HTTPException(404, "Device not found")
    managed = host.get("managed_runtime")
    if not isinstance(managed, dict):
        raise HTTPException(
            409,
            "Enable SSH controls for this device before checking upstream versions.",
        )
    if str(managed.get("management_mode") or "") == "local":
        report(8, "Checking local Runtime and Hardware packages")
        checked = inspect_local_package_updates(
            managed,
            progress=lambda value: report(
                10 + int(int(value.get("progress") or 0) * 0.8),
                str(value.get("message") or "Comparing package versions"),
            ),
        )
        components = [
            item for item in checked.get("components") or []
            if isinstance(item, dict)
        ]
        available = sum(1 for item in components if item.get("update_available"))
        blockers = sum(1 for item in components if item.get("error"))
        if blockers:
            summary = (
                f"Checked {len(components)} packages; {blockers} "
                f"{'needs' if blockers == 1 else 'need'} attention."
            )
        elif available:
            summary = (
                f"{available} of {len(components)} packages "
                f"{'has' if available == 1 else 'have'} updates available."
            )
        else:
            summary = f"All {len(components)} local packages are current."
        report(100, summary)
        return {
            "ok": blockers == 0,
            "check": checked,
            "warnings": [],
            "summary": summary,
        }
    if not str(req.password or ""):
        raise HTTPException(400, "Enter the SSH password to check software versions.")

    robots = list(host.get("robots") or [])
    hardware_ports: list[int] = []
    hardware_device_ids: dict[int, str] = {}
    for robot in robots:
        try:
            hardware_port = urllib.parse.urlsplit(
                str(robot.get("base_url") or "")
            ).port
        except ValueError as exc:
            raise HTTPException(
                409,
                f"{robot.get('name') or 'A robot'} has an invalid hardware URL.",
            ) from exc
        if not hardware_port:
            raise HTTPException(
                409,
                f"{robot.get('name') or 'A robot'} has no hardware service port.",
            )
        hardware_ports.append(hardware_port)
        hardware_device_ids[hardware_port] = str(
            robot.get("remote_device_id") or ""
        )

    report(8, "Checking installed Runtime and Hardware software")
    checked = inspect_managed_service_updates(
        host=str(managed.get("ssh_host") or ""),
        port=int(managed.get("ssh_port") or 22),
        username=str(managed.get("ssh_username") or ""),
        password=req.password,
        host_fingerprint=str(managed.get("host_fingerprint") or ""),
        instance_id=str(managed.get("instance_id") or "default"),
        runtime_port=int(managed.get("runtime_port") or 0),
        hardware_ports=hardware_ports,
        hardware_device_ids=hardware_device_ids,
        progress=lambda value: report(
            10 + int(int(value.get("progress") or 0) * 0.75),
            str(value.get("message") or "Comparing software versions"),
        ),
    )

    warnings: list[str] = []
    runtime_version = "not reported"
    try:
        manifest = _device_registry.host_client(host_id).manifest()
        runtime_version = str(manifest.get("runtime_version") or "not reported")
    except (DeviceRegistryError, KeyError) as exc:
        warnings.append(f"Runtime live-version check failed: {exc}")

    hardware_versions: dict[int, str] = {}
    for robot in robots:
        robot_id = str(robot.get("id") or "")
        try:
            robot_port = urllib.parse.urlsplit(str(robot.get("base_url") or "")).port
            status = _paired_device_client(robot_id).status()
            if robot_port:
                hardware_versions[robot_port] = str(
                    status.get("software_version") or "not reported"
                )
        except (DeviceRegistryError, HTTPException, ValueError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            warnings.append(
                f"{robot.get('name') or robot_id} live-version check failed: {detail}"
            )

    for component in checked.get("components") or []:
        if not isinstance(component, dict):
            continue
        if component.get("kind") == "runtime":
            component["reported_version"] = runtime_version
        else:
            component["reported_version"] = hardware_versions.get(
                int(component.get("port") or 0),
                "not reported",
            )

    components = [
        item for item in checked.get("components") or []
        if isinstance(item, dict)
    ]
    includes_hardware = any(
        item.get("kind") == "hardware" for item in components
    )
    target_label = "Runtime + Hardware" if includes_hardware else "Runtime"
    available = sum(1 for item in components if item.get("update_available"))
    blockers = sum(1 for item in components if item.get("error"))
    if blockers:
        summary = (
            f"Checked {len(components)} service"
            f"{'s' if len(components) != 1 else ''}; {blockers} "
            f"{'needs' if blockers == 1 else 'need'} attention before "
            f"{target_label} can be updated."
        )
    elif available:
        summary = (
            f"{available} of {len(components)} service"
            f"{'s' if len(components) != 1 else ''} "
            f"{'has' if len(components) == 1 else 'have'} updates available."
        )
    elif includes_hardware:
        summary = (
            f"Runtime + Hardware are current across {len(components)} services."
        )
    else:
        summary = "Runtime is current."
    if warnings:
        summary += (
            f" {len(warnings)} live service check"
            f"{'s' if len(warnings) != 1 else ''} could not be completed."
        )
    report(100, summary)
    return {
        "ok": blockers == 0,
        "check": checked,
        "warnings": warnings,
        "summary": summary,
    }


@app.post("/device-hosts/{host_id}/update-check-stream")
def stream_device_host_update_check(host_id: str, req: UpdateManagedDeviceReq):
    return _lifecycle_stream(
        lambda progress: _check_device_host_updates_payload(host_id, req, progress)
    )


def _control_robot_lifecycle_payload(
    device_id: str,
    req: RobotLifecycleReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    action = str(req.action or "").strip().lower()
    if action not in {"pause", "resume", "restart"}:
        raise HTTPException(400, "Robot action must be pause, resume, or restart.")
    report(5, "Checking the robot")
    saved_device = _device_registry.get_public(device_id)
    if saved_device is None:
        raise HTTPException(404, "Device not found")

    warnings: list[str] = []
    if action == "restart":
        if not str(req.password or ""):
            raise HTTPException(400, "Enter the SSH password to restart this robot service.")
        status = _deployment_aware_device_status(device_id)
        if status.get("deployment_lease") or status.get("leased_to_deployment"):
            raise HTTPException(
                409,
                "Stop the robot's active deployment before restarting its hardware service.",
            )
        if status.get("armed"):
            raise HTTPException(
                409,
                "Pause and disarm the robot before restarting its hardware service.",
            )
        host_id = str(saved_device.get("host_id") or "")
        host = _device_registry.get_host_public(host_id) if host_id else None
        managed = host.get("managed_runtime") if isinstance(host, dict) else None
        if not isinstance(managed, dict):
            raise HTTPException(
                409,
                "This robot's compute device was paired manually. Restart its "
                "robot device service on the device.",
            )
        try:
            hardware_port = urllib.parse.urlsplit(
                str(saved_device.get("base_url") or "")
            ).port
        except ValueError as exc:
            raise HTTPException(409, "The saved robot hardware URL has an invalid port.") from exc
        if not hardware_port:
            raise HTTPException(409, "The saved robot hardware URL has no service port.")

        report(35, f"Resolving the hardware service on port {hardware_port}")
        service = restart_hardware_service(
            host=str(managed.get("ssh_host") or ""),
            port=int(managed.get("ssh_port") or 22),
            username=str(managed.get("ssh_username") or ""),
            password=req.password,
            host_fingerprint=str(managed.get("host_fingerprint") or ""),
            hardware_port=hardware_port,
        )
        report(75, "Verifying the authenticated robot after restart")
        verified_status: dict[str, Any] | None = None
        last_error = ""
        for _attempt in range(30):
            try:
                candidate = _paired_device_client(device_id).status()
                expected_id = str(saved_device.get("remote_device_id") or "")
                actual_id = str(candidate.get("device_id") or "")
                if expected_id and actual_id != expected_id:
                    raise DeviceRegistryError(
                        f"port {hardware_port} returned robot '{actual_id}', expected '{expected_id}'"
                    )
                verified_status = candidate
                break
            except (DeviceRegistryError, HTTPException) as exc:
                last_error = exc.detail if isinstance(exc, HTTPException) else str(exc)
                time.sleep(0.25)
        if verified_status is None:
            raise DeviceRegistryError(
                f"{service['service_name']} restarted, but the robot did not return: {last_error}"
            )
        if verified_status.get("armed"):
            result = _paired_device_client(device_id).rpc({
                "jsonrpc": "2.0",
                "id": f"robot-restart-stop-{device_id}",
                "method": "stop",
                "params": {},
            })
            _raise_rpc_error(result, action="disarm restarted")
            verified_status = _paired_device_client(device_id).status()
        if verified_status.get("armed"):
            raise DeviceRegistryError(
                "The restarted robot service did not return to a disarmed state."
            )
        if not verified_status.get("connected"):
            warnings.append(
                "The service restarted, but the hardware provider reports disconnected."
            )
        _device_registry.set_device_paused(device_id, False)
        verified_status["paused"] = False
        summary = (
            f"Restarted {service['service_name']} for hardware port {hardware_port}; "
            "robot monitoring is online and motion remains disarmed."
        )
        if warnings:
            summary += f" Completed with {len(warnings)} warning."
        report(100, summary)
        return {
            "ok": True,
            "action": action,
            "status": verified_status,
            "service": service,
            "warnings": warnings,
            "summary": summary,
        }

    if action == "pause":
        report(20, "Stopping every deployment targeting this robot")
        stopped_deployments: list[str] = []
        try:
            status = _deployment_aware_device_status(device_id)
            lease = status.get("deployment_lease")
            runtime_client = _runtime_client_or_404(device_id)
            deployment_ids = {
                str(item.get("id") or "")
                for item in (
                    runtime_client.list_deployments().get("deployments") or []
                )
                if (
                    isinstance(item, dict)
                    and str(item.get("state") or "") == "running"
                    and str(item.get("target_device_id") or "") == device_id
                    and str(item.get("id") or "")
                )
            }
            if isinstance(lease, dict) and lease.get("id"):
                deployment_ids.add(str(lease["id"]))
            for deployment_id in sorted(deployment_ids):
                runtime_client.stop_deployment(deployment_id)
                stopped_deployments.append(deployment_id)
        except (DeviceRegistryError, HTTPException, KeyError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            warnings.append(
                "The deployment runtime at "
                f"{saved_device.get('runtime_url') or 'the saved runtime URL'} could not be reached: "
                f"{detail}. Blacknode continued with the robot hardware stop request, "
                "but physical torque cannot be verified through this status endpoint."
            )
        method = "stop"
        report(60, "Stopping and disarming the robot directly")
    else:
        method = "resume"
        report(60, "Reconnecting robot monitoring in a disarmed state")

    result = _paired_device_client(device_id).rpc({
        "jsonrpc": "2.0",
        "id": f"robot-{action}-{device_id}",
        "method": method,
        "params": {},
    })
    _raise_rpc_error(result, action=action)
    _device_registry.set_device_paused(device_id, action == "pause")
    report(85, "Verifying robot status")
    status = _paired_device_client(device_id).status()
    status["paused"] = action == "pause"
    summary = (
        "Robot paused; Blacknode motion is disarmed."
        if action == "pause"
        else "Robot monitoring resumed; motion remains disarmed."
    )
    if warnings:
        summary += (
            f" Completed with {len(warnings)} warning{'s' if len(warnings) != 1 else ''}; "
            "verify physical torque before handling the robot."
        )
    report(100, summary)
    return {
        "ok": True,
        "action": action,
        "status": status,
        "stopped_deployments": (
            stopped_deployments if action == "pause" else []
        ),
        "warnings": warnings,
        "summary": summary,
    }


def _uninstall_device_host_payload(
    host_id: str,
    req: UninstallDeviceHostReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": str(message),
            })

    report(3, "Loading the managed device")
    try:
        host = _device_registry.get_host_public(host_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if host is None:
        raise HTTPException(404, "Device not found")
    managed = host.get("managed_runtime")
    if not isinstance(managed, dict):
        raise HTTPException(
            409,
            "This runtime was paired manually, so Blacknode does not have its SSH "
            "installation identity. Remove it from the editor or uninstall it on the device.",
        )
    try:
        if str(managed.get("management_mode") or "") == "local":
            result = uninstall_local_runtime(managed, progress=progress)
        else:
            hardware_ports: set[int] = set()
            for robot in host.get("robots", []):
                if not isinstance(robot, dict):
                    continue
                try:
                    hardware_port = urllib.parse.urlsplit(
                        str(robot.get("base_url") or "")
                    ).port
                except ValueError:
                    continue
                if hardware_port is not None:
                    hardware_ports.add(int(hardware_port))
            result = uninstall_runtime(
                host=str(managed.get("ssh_host") or ""),
                port=int(managed.get("ssh_port") or 22),
                username=str(managed.get("ssh_username") or ""),
                password=req.password,
                host_fingerprint=str(managed.get("host_fingerprint") or ""),
                instance_id=str(managed.get("instance_id") or "default"),
                runtime_port=int(managed.get("runtime_port") or 0),
                firewall_source=str(managed.get("firewall_source") or ""),
                stack_mode=str(managed.get("stack_mode") or "runtime_only"),
                hardware_ports=sorted(hardware_ports),
                progress=progress,
            )
        report(97, "Removing the saved device registration")
        _device_registry.delete_host(host_id, cascade=True)
    except (DeviceInstallError, LocalRuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except DeviceRegistryError as exc:
        raise HTTPException(409, str(exc)) from exc
    if str(managed.get("management_mode") or "") == "local":
        if result.get("source_preserved"):
            summary = "Local services uninstalled; source checkout preserved"
        elif managed.get("hardware_dir"):
            summary = "Local robot stack deleted"
        else:
            summary = "Local Runtime installation deleted"
    else:
        summary = "Device deleted"
    report(100, summary)
    return {
        "ok": True,
        "id": host_id,
        "uninstall": result,
        "summary": summary,
    }


@app.post("/device-hosts/{host_id}/uninstall")
def uninstall_device_host(host_id: str, req: UninstallDeviceHostReq):
    return _uninstall_device_host_payload(host_id, req)


@app.post("/device-hosts/{host_id}/uninstall-stream")
def uninstall_device_host_stream(host_id: str, req: UninstallDeviceHostReq):
    return _lifecycle_stream(
        lambda progress: _uninstall_device_host_payload(host_id, req, progress)
    )


@app.post("/device-hosts/{host_id}/robots")
def pair_host_robot(host_id: str, req: PairHostRobotReq):
    try:
        if _device_registry.get_host_public(host_id) is None:
            raise HTTPException(404, "Device not found")
        client = HardwareDeviceClient(req.base_url, req.token)
        status = client.validate_pairing()
        device = _device_registry.pair(
            name=req.name,
            base_url=client.base_url,
            token=req.token,
            host_id=host_id,
            status=status,
        )
    except DeviceRegistryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "robot": device,
        "status": status,
        "runtime": _device_host_runtime_status(host_id),
    }


@app.post("/device-hosts/{host_id}/robots/discover")
def discover_and_pair_host_robots(host_id: str, req: DiscoverHostRobotsReq):
    try:
        host = _device_registry.get_host_public(host_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if host is None:
        raise HTTPException(404, "Device not found")
    managed = host.get("managed_runtime")
    if not isinstance(managed, dict):
        raise HTTPException(
            409,
            "Enable verified SSH controls before finding installed robots.",
        )
    if str(managed.get("management_mode") or "") == "local":
        raise HTTPException(
            409,
            "Use the local Hardware package controls for this computer.",
        )
    if not str(req.password or ""):
        raise HTTPException(
            400,
            "Enter the device SSH password to find installed robots.",
        )
    try:
        discovered = discover_hardware_pairings(
            host=str(managed.get("ssh_host") or ""),
            port=int(managed.get("ssh_port") or 22),
            username=str(managed.get("ssh_username") or ""),
            password=req.password,
            host_fingerprint=str(managed.get("host_fingerprint") or ""),
            expected_hardware_dir=str(managed.get("hardware_dir") or ""),
        )
        adopted = 0
        configured = 0
        if (
            int(discovered.get("discovered") or 0) == 0
            and str(managed.get("stack_mode") or "") == "isolated"
            and str(managed.get("instance_id") or "default") == "default"
        ):
            adoption = adopt_legacy_hardware_services(
                host=str(managed.get("ssh_host") or ""),
                port=int(managed.get("ssh_port") or 22),
                username=str(managed.get("ssh_username") or ""),
                password=req.password,
                host_fingerprint=str(managed.get("host_fingerprint") or ""),
                instance_id="default",
            )
            adopted = int(adoption.get("adopted") or 0)
            if adopted:
                discovered = discover_hardware_pairings(
                    host=str(managed.get("ssh_host") or ""),
                    port=int(managed.get("ssh_port") or 22),
                    username=str(managed.get("ssh_username") or ""),
                    password=req.password,
                    host_fingerprint=str(managed.get("host_fingerprint") or ""),
                    expected_hardware_dir=str(managed.get("hardware_dir") or ""),
                )
            else:
                configuration = configure_hardware_services(
                    host=str(managed.get("ssh_host") or ""),
                    port=int(managed.get("ssh_port") or 22),
                    username=str(managed.get("ssh_username") or ""),
                    password=req.password,
                    host_fingerprint=str(managed.get("host_fingerprint") or ""),
                    instance_id="default",
                    runtime_port=int(managed.get("runtime_port") or 0),
                    robot_name=str(host.get("name") or "ROS 2 Robot"),
                )
                configured = int(configuration.get("configured") or 0)
                if configured:
                    discovered = discover_hardware_pairings(
                        host=str(managed.get("ssh_host") or ""),
                        port=int(managed.get("ssh_port") or 22),
                        username=str(managed.get("ssh_username") or ""),
                        password=req.password,
                        host_fingerprint=str(managed.get("host_fingerprint") or ""),
                        expected_hardware_dir=str(
                            managed.get("hardware_dir") or ""
                        ),
                    )
    except DeviceInstallError as exc:
        raise HTTPException(400, str(exc)) from exc

    runtime_url = urllib.parse.urlsplit(str(host.get("runtime_url") or ""))
    runtime_hostname = str(runtime_url.hostname or "")
    if not runtime_hostname:
        raise HTTPException(409, "The paired Runtime URL has no hostname.")
    service_host = (
        f"[{runtime_hostname}]" if ":" in runtime_hostname else runtime_hostname
    )
    scheme = runtime_url.scheme or "http"
    attached: list[dict[str, Any]] = []
    statuses: dict[str, dict[str, Any]] = {}
    errors = [
        str(value)
        for value in discovered.get("errors", [])
        if str(value).strip()
    ]
    for pairing in discovered.get("pairings", []):
        if not isinstance(pairing, dict):
            continue
        service_name = str(
            pairing.get("service_name") or "Robot Hardware service"
        )
        if not pairing.get("active"):
            errors.append(
                f"{service_name}: service is installed but not running."
            )
            continue
        try:
            service_port = int(pairing.get("port") or 0)
            client = HardwareDeviceClient(
                f"{scheme}://{service_host}:{service_port}",
                str(pairing.get("token") or ""),
            )
            status = client.validate_pairing()
            configured_device_id = str(pairing.get("device_id") or "")
            actual_device_id = str(status.get("device_id") or "")
            if configured_device_id and actual_device_id != configured_device_id:
                raise DeviceRegistryError(
                    f"returned robot '{actual_device_id}', expected "
                    f"'{configured_device_id}' from its saved configuration"
                )
            robot = _device_registry.pair(
                name=str(pairing.get("name") or ""),
                base_url=client.base_url,
                token=str(pairing.get("token") or ""),
                host_id=host_id,
                status=status,
            )
            attached.append(robot)
            statuses[str(robot["id"])] = status
        except (DeviceRegistryError, ValueError) as exc:
            errors.append(f"{service_name}: {exc}")

    if not attached:
        if int(discovered.get("discovered") or 0) == 0:
            detail = (
                "No installed Robot Hardware services were found in this device "
                "stack. Connect and configure the robot, install its Hardware "
                "service, then press Find and attach robots again."
            )
        else:
            detail = (
                "Installed Robot Hardware services were found, but none could be "
                "paired. " + " ".join(errors)
            )
        raise HTTPException(409, detail)
    summary = (
        f"Attached {len(attached)} installed robot"
        f"{'s' if len(attached) != 1 else ''} securely over verified SSH."
    )
    if adopted:
        summary = (
            f"Moved {adopted} existing Robot Hardware service"
            f"{'s' if adopted != 1 else ''} into this device stack. "
            + summary
        )
    elif configured:
        summary = (
            f"Configured {configured} connected robot"
            f"{'s' if configured != 1 else ''} in this device stack. "
            + summary
        )
    if errors:
        summary += (
            f" {len(errors)} service"
            f"{'s' if len(errors) != 1 else ''} need attention."
        )
    return {
        "ok": True,
        "robots": attached,
        "statuses": statuses,
        "errors": errors,
        "summary": summary,
    }


def _install_device_host_hardware_payload(
    host_id: str,
    req: DiscoverHostRobotsReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    try:
        host = _device_registry.get_host_public(host_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if host is None:
        raise HTTPException(404, "Device not found")
    managed = host.get("managed_runtime")
    if not isinstance(managed, dict):
        raise HTTPException(
            409,
            "Enable verified SSH controls before installing Robot Hardware.",
        )
    if str(managed.get("management_mode") or "") == "local":
        raise HTTPException(
            409,
            "Use the local Hardware package controls for this computer.",
        )
    if not str(req.password or ""):
        raise HTTPException(
            400,
            "Enter the device SSH password to install Robot Hardware.",
        )
    try:
        inspection = (
            host.get("last_inspection")
            if isinstance(host.get("last_inspection"), dict)
            else {}
        )
        environment = (
            inspection.get("environment")
            if isinstance(inspection.get("environment"), dict)
            else {}
        )
        operating_system = (
            environment.get("os")
            if isinstance(environment.get("os"), dict)
            else {}
        )
        installed = install_hardware_environment(
            host=str(managed.get("ssh_host") or ""),
            port=int(managed.get("ssh_port") or 22),
            username=str(managed.get("ssh_username") or ""),
            password=req.password,
            host_fingerprint=str(managed.get("host_fingerprint") or ""),
            instance_id=str(managed.get("instance_id") or "default"),
            delivery_mode=str(managed.get("delivery_mode") or "device_online"),
            architecture=str(operating_system.get("architecture") or ""),
            progress=progress,
        )
        updated_management = {
            **managed,
            "hardware_dir": str(installed["hardware_dir"]),
            "stack_mode": str(installed.get("stack_mode") or "isolated"),
        }
        device = _device_registry.set_host_management(
            host_id,
            updated_management,
        )
    except DeviceInstallError as exc:
        raise HTTPException(400, str(exc)) from exc
    except DeviceRegistryError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "ok": True,
        "device": device,
        "install": installed,
        "summary": (
            "Robot Hardware package installed. Connect and configure a robot, "
            "then use Find and attach robots."
        ),
    }


@app.post("/device-hosts/{host_id}/hardware-package/install-stream")
def install_device_host_hardware_stream(
    host_id: str,
    req: DiscoverHostRobotsReq,
):
    return _lifecycle_stream(
        lambda progress: _install_device_host_hardware_payload(
            host_id,
            req,
            progress,
        )
    )


@app.patch("/device-hosts/{host_id}")
def rename_device_host(host_id: str, req: RenameDeviceReq):
    try:
        return {"device": _device_registry.rename_host(host_id, req.name)}
    except KeyError as exc:
        raise HTTPException(404, "Device not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.delete("/device-hosts/{host_id}")
def delete_device_host(host_id: str):
    try:
        deleted = _device_registry.delete_host(host_id)
    except DeviceRegistryError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, "Device not found")
    return {"ok": True, "id": host_id}


@app.get("/devices")
def list_devices():
    try:
        return {"devices": _device_registry.list()}
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc


def _device_runtime_status(device_id: str) -> dict[str, Any]:
    try:
        device = _device_registry.get_public(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if device is None:
        raise HTTPException(404, "Device not found")
    try:
        manifest = _device_registry.runtime_client(device_id).manifest()
        if (
            manifest.get("service") != "blacknode-runtime"
            or manifest.get("protocol_version") != 1
        ):
            raise DeviceRegistryError(
                "Runtime service identity or protocol is incompatible."
            )
    except (DeviceRegistryError, KeyError) as exc:
        return {
            "ok": False,
            "state": "unreachable",
            "runtime_url": device["runtime_url"],
            "error": str(exc),
        }
    return {
        "ok": True,
        "state": "running",
        "runtime_url": device["runtime_url"],
        "manifest": manifest,
    }


@app.post("/devices")
def pair_device(req: PairDeviceReq):
    try:
        client = HardwareDeviceClient(req.base_url, req.token)
        status = client.validate_pairing()
        device = _device_registry.pair(
            name=req.name,
            base_url=client.base_url,
            token=req.token,
            runtime_token=req.runtime_token,
            status=status,
        )
    except DeviceRegistryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "device": device,
        "status": status,
        "runtime": _device_runtime_status(device["id"]),
    }


@app.get("/devices/{device_id}")
def get_device(device_id: str):
    try:
        device = _device_registry.get_public(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if device is None:
        raise HTTPException(404, "Device not found")
    return device


def _robot_attachment_values(req: RobotAttachmentReq) -> dict[str, Any]:
    return {
        "attachment_id": req.attachment_id,
        "display_name": req.display_name,
        "attachment_type": req.attachment_type,
        "capability": req.capability,
        "provider_package": req.provider_package,
        "provider_component": req.provider_component,
        "provider_adapter": req.provider_adapter,
        "provider_profile": req.provider_profile,
        "topic": req.topic,
        "message_type": req.message_type,
        "camera_info_topic": req.camera_info_topic,
        "depth_topic": req.depth_topic,
        "point_cloud_topic": req.point_cloud_topic,
        "launch_package": req.launch_package,
        "launch_target": req.launch_target,
        "launch_arguments": req.launch_arguments,
        "parent_frame": req.parent_frame,
        "frame_id": req.frame_id,
        "x_m": req.x_m,
        "y_m": req.y_m,
        "z_m": req.z_m,
        "roll_rad": req.roll_rad,
        "pitch_rad": req.pitch_rad,
        "yaw_rad": req.yaw_rad,
        "hardware_id": req.hardware_id,
        "required": req.required,
        "enabled": req.enabled,
    }


def _attachment_primary_interface(
    attachment: dict[str, Any],
) -> dict[str, Any]:
    return next(
        (
            dict(item)
            for item in (attachment.get("interfaces") or [])
            if isinstance(item, dict)
            and str(item.get("kind") or "topic") == "topic"
            and str(item.get("topic") or "")
        ),
        {},
    )


def _attachment_provider_package_spec(
    attachment: dict[str, Any],
) -> dict[str, Any] | None:
    provider = (
        attachment.get("provider")
        if isinstance(attachment.get("provider"), dict)
        else {}
    )
    service = (
        attachment.get("service")
        if isinstance(attachment.get("service"), dict)
        else {}
    )
    if str(service.get("profile") or "existing_topics") == "existing_topics":
        return None
    name = str(provider.get("package") or "").strip()
    component = str(provider.get("component") or "").strip()
    adapter = str(provider.get("adapter") or "").strip()
    if not name:
        raise DeviceRegistryError(
            "Attachment provider package is required before starting it."
        )
    indexed = (package_index_payload().get("packages") or {}).get(name)
    local = next(
        (info for info in installed_packages() if info.name == name),
        None,
    )
    git_url = (
        _package_git_source(str(local.path or ""))
        if local is not None
        else str(indexed.get("git_url") or "")
        if isinstance(indexed, dict)
        else ""
    )
    if not git_url:
        raise DeviceRegistryError(
            f"{name} has no trusted package source and cannot be installed "
            "on the device automatically."
        )
    version = (
        str(local.version or "")
        if local is not None
        else str(indexed.get("version") or "")
        if isinstance(indexed, dict)
        else ""
    )
    components = {component} if component else set()
    profile = str(service.get("profile") or "")
    if name == "blacknode-perception" and profile in {
        "usb_cam",
        "blacknode_rgbd",
    }:
        components.add("camera")
        if profile == "blacknode_rgbd":
            components.add("depth")
    adapters = [
        {"component": value, "adapter": adapter}
        for value in sorted(components)
        if adapter
    ]
    return {
        "name": name,
        "git_url": git_url,
        "version": version,
        "components": sorted(components),
        "adapters": adapters,
    }


def _sync_attachment_provider_package(
    runtime_client: RuntimeDeviceClient,
    attachment: dict[str, Any],
) -> dict[str, Any] | None:
    spec = _attachment_provider_package_spec(attachment)
    if spec is None:
        return None
    result = runtime_client.sync_packages([spec])
    setup_failures = [
        str(message)
        for message in (result.get("messages") or [])
        if "package setup script failed" in str(message).lower()
    ]
    if setup_failures:
        raise DeviceRegistryError(
            f"{spec['name']} installed, but its device setup failed: "
            + " ".join(setup_failures[-3:])
        )
    manifest = runtime_client.manifest()
    installed = {
        str(item.get("name") or ""): str(item.get("version") or "")
        for item in (manifest.get("packages") or [])
        if isinstance(item, dict)
    }
    actual_version = installed.get(str(spec["name"]))
    if actual_version is None:
        raise DeviceRegistryError(
            f"{spec['name']} did not appear in the Runtime after synchronization."
        )
    required_version = str(spec.get("version") or "")
    if required_version and actual_version != required_version:
        raise DeviceRegistryError(
            f"{spec['name']} {required_version} is required, but the Runtime "
            f"reports {actual_version or 'an unknown version'}."
        )
    return result


def _attachment_service_payload(
    attachment: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    service = (
        attachment.get("service")
        if isinstance(attachment.get("service"), dict)
        else {}
    )
    service_id = str(
        service.get("id") or attachment.get("id") or ""
    ).replace("_", "-")
    profile = str(service.get("profile") or "existing_topics")
    if profile == "existing_topics":
        return service_id, None
    if profile == "usb_cam":
        primary = _attachment_primary_interface(attachment)
        topic = str(primary.get("topic") or "/camera/image_raw")
        info = next(
            (
                str(item.get("topic") or "")
                for item in (attachment.get("interfaces") or [])
                if isinstance(item, dict)
                and str(item.get("role") or "") == "camera_info"
            ),
            "",
        )
        arguments = list(service.get("launch_arguments") or [])
        arguments.append(f"image_topic:={topic}")
        if info:
            arguments.append(f"camera_info_topic:={info}")
        arguments.append(
            f"frame_id:={str(primary.get('frame_id') or 'camera')}"
        )
        command = {
            "verb": "launch",
            "package": "perception_camera",
            "target": "usb_camera.launch.py",
            "arguments": arguments,
        }
    elif profile == "blacknode_rgbd":
        primary = _attachment_primary_interface(attachment)
        info = next(
            (
                str(item.get("topic") or "")
                for item in (attachment.get("interfaces") or [])
                if isinstance(item, dict)
                and str(item.get("role") or "") == "camera_info"
            ),
            "",
        )
        depth = next(
            (
                str(item.get("topic") or "")
                for item in (attachment.get("interfaces") or [])
                if isinstance(item, dict)
                and str(item.get("role") or "") == "depth"
            ),
            "",
        )
        arguments = (
            list(service.get("launch_arguments") or [])
            or ["rgb_device:=0", "depth_device:=1"]
        )
        arguments.extend([
            f"rgb_topic:={str(primary.get('topic') or '/camera/rgb/image_raw')}",
            f"rgb_info_topic:={info or '/camera/rgb/camera_info'}",
            f"depth_topic:={depth or '/camera/depth/image_raw'}",
            f"rgb_frame_id:={str(primary.get('frame_id') or 'camera_rgb')}",
            f"depth_frame_id:={str(primary.get('frame_id') or 'camera_depth')}",
        ])
        command = {
            "verb": "launch",
            "package": "perception_camera",
            "target": "rgbd_camera.launch.py",
            "arguments": arguments,
        }
    elif profile == "custom_launch":
        command = {
            "verb": "launch",
            "package": str(service.get("launch_package") or ""),
            "target": str(service.get("launch_target") or ""),
            "arguments": list(service.get("launch_arguments") or []),
        }
    else:
        raise DeviceRegistryError(f"Unsupported attachment provider profile: {profile}")
    interfaces = [
        {
            "topic": str(item.get("topic") or ""),
            "type": str(item.get("message_type") or ""),
            "required": bool(item.get("required", index == 0)),
            "direction": "publisher",
        }
        for index, item in enumerate(attachment.get("interfaces") or [])
        if isinstance(item, dict) and str(item.get("topic") or "")
    ]
    return service_id, {
        "name": str(attachment.get("display_name") or service_id),
        "command": command,
        "interfaces": interfaces,
        "wait_seconds": 15.0,
    }


def _attachment_topic_check(
    attachment: dict[str, Any],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    interface = _attachment_primary_interface(attachment)
    topic = str(interface.get("topic") or "")
    expected_type = str(interface.get("message_type") or "")
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    if not diagnostics.get("available", diagnostics.get("ok", False)):
        return {
            "ok": False,
            "status": "unavailable",
            "topic": topic,
            "expected_message_type": expected_type,
            "actual_message_type": "",
            "publisher_count": None,
            "checked_at": checked_at,
            "message": str(
                diagnostics.get("error")
                or diagnostics.get("summary")
                or "ROS 2 diagnostics are unavailable on this device."
            ),
        }

    actual_type = ""
    topic_found = False
    for value in diagnostics.get("topics") or []:
        if isinstance(value, dict):
            candidate_topic = str(value.get("name") or value.get("topic") or "")
            candidate_type = str(value.get("type") or value.get("message_type") or "")
        else:
            text = str(value or "")
            match = re.match(r"^(\S+)\s+\[([^\]]+)\]\s*$", text)
            candidate_topic = match.group(1) if match else text.strip()
            candidate_type = match.group(2) if match else ""
        if candidate_topic == topic:
            topic_found = True
            actual_type = candidate_type
            break
    if not topic_found:
        return {
            "ok": False,
            "status": "missing",
            "topic": topic,
            "expected_message_type": expected_type,
            "actual_message_type": "",
            "publisher_count": 0,
            "checked_at": checked_at,
            "message": f"{topic} is not present in the live ROS 2 graph.",
        }
    if actual_type and expected_type and actual_type != expected_type:
        return {
            "ok": False,
            "status": "type_mismatch",
            "topic": topic,
            "expected_message_type": expected_type,
            "actual_message_type": actual_type,
            "publisher_count": None,
            "checked_at": checked_at,
            "message": (
                f"{topic} publishes {actual_type}, but this attachment expects "
                f"{expected_type}."
            ),
        }

    publisher_count: int | None = None
    topic_detail = next(
        (
            item
            for item in (diagnostics.get("topic_details") or [])
            if isinstance(item, dict)
            and str(item.get("topic") or "") == topic
        ),
        None,
    )
    if topic_detail and topic_detail.get("ok", True):
        match = re.search(
            r"Publisher count:\s*(\d+)",
            str(topic_detail.get("stdout") or ""),
            re.IGNORECASE,
        )
        if match:
            publisher_count = int(match.group(1))
    if publisher_count == 0:
        return {
            "ok": False,
            "status": "no_publisher",
            "topic": topic,
            "expected_message_type": expected_type,
            "actual_message_type": actual_type or expected_type,
            "publisher_count": 0,
            "checked_at": checked_at,
            "message": f"{topic} exists, but no ROS 2 publisher is active.",
        }
    if publisher_count is None:
        return {
            "ok": True,
            "status": "topic_present",
            "topic": topic,
            "expected_message_type": expected_type,
            "actual_message_type": actual_type or expected_type,
            "publisher_count": None,
            "checked_at": checked_at,
            "message": (
                f"{topic} is present with the expected type. Publisher count "
                "was not sampled."
            ),
        }
    return {
        "ok": True,
        "status": "streaming",
        "topic": topic,
        "expected_message_type": expected_type,
        "actual_message_type": actual_type or expected_type,
        "publisher_count": publisher_count,
        "checked_at": checked_at,
        "message": (
            f"{topic} has {publisher_count} active ROS 2 "
            f"publisher{'s' if publisher_count != 1 else ''}."
        ),
    }


def _attachment_service_check(
    attachment: dict[str, Any],
    service: dict[str, Any],
    *,
    provider_logs: str = "",
) -> dict[str, Any]:
    primary = _attachment_primary_interface(attachment)
    topic = str(primary.get("topic") or "")
    expected_type = str(primary.get("message_type") or "")
    diagnostics = (
        service.get("diagnostics")
        if isinstance(service.get("diagnostics"), dict)
        else {}
    )
    interfaces = [
        item
        for item in (diagnostics.get("interfaces") or [])
        if isinstance(item, dict)
    ]
    primary_result = next(
        (item for item in interfaces if str(item.get("topic") or "") == topic),
        {},
    )
    missing = [str(value) for value in (diagnostics.get("missing") or [])]
    state = str(service.get("state") or "stopped")
    ok = state == "running" and bool(diagnostics.get("ok"))
    message = (
        f"{attachment.get('display_name') or topic} is running and all "
        "required ROS 2 streams are publishing."
        if ok
        else (
            "Provider is running, but required streams are not ready: "
            + ", ".join(missing)
            if state == "running" and missing
            else str(
                service.get("error")
                or "Attachment provider is stopped."
            )
        )
    )
    clean_logs = re.sub(r"\x1b\[[0-9;]*m", "", provider_logs).strip()
    if not ok and clean_logs:
        log_tail = " | ".join(
            line.strip()
            for line in clean_logs.splitlines()[-8:]
            if line.strip()
        )
        if log_tail:
            message += f" Provider log: {log_tail[-1600:]}"
    return {
        "ok": ok,
        "status": (
            "streaming"
            if ok
            else "missing"
            if state == "running"
            else "unavailable"
        ),
        "topic": topic,
        "expected_message_type": expected_type,
        "actual_message_type": str(
            primary_result.get("type") or expected_type
        ),
        "publisher_count": primary_result.get("publishers"),
        "checked_at": str(
            diagnostics.get("checked_at")
            or datetime.now().astimezone().isoformat(timespec="seconds")
        ),
        "message": message,
        "interfaces": interfaces,
        "missing": missing,
        "service_state": state,
    }


def _attachment_provider_logs(
    runtime_client: RuntimeDeviceClient,
    service_id: str,
    check: dict[str, Any],
) -> str:
    if check.get("ok"):
        return ""
    try:
        result = runtime_client.service_logs(service_id, limit=12000)
    except DeviceRegistryError:
        return ""
    return str(result.get("logs") or "")


def _find_robot_attachment(
    device_id: str,
    attachment_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        device = _device_registry.get_public(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if device is None:
        raise HTTPException(404, "Device not found")
    attachment = next(
        (
            item
            for item in (device.get("attachments") or [])
            if isinstance(item, dict)
            and str(item.get("id") or "") == attachment_id
        ),
        None,
    )
    if attachment is None:
        raise HTTPException(404, "Attachment not found")
    return device, attachment


@app.get("/devices/{device_id}/attachments")
def list_robot_attachments(device_id: str):
    try:
        device = _device_registry.get_public(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if device is None:
        raise HTTPException(404, "Device not found")
    return {
        "device_id": device_id,
        "attachments": list(device.get("attachments") or []),
    }


@app.post("/devices/{device_id}/attachments")
def create_robot_attachment(device_id: str, req: RobotAttachmentReq):
    try:
        device, attachment = _device_registry.save_attachment(
            device_id,
            _robot_attachment_values(req),
        )
    except KeyError as exc:
        raise HTTPException(404, "Device not found") from exc
    except DeviceRegistryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"device": device, "attachment": attachment}


@app.put("/devices/{device_id}/attachments/{attachment_id}")
def update_robot_attachment(
    device_id: str,
    attachment_id: str,
    req: RobotAttachmentReq,
):
    try:
        device, attachment = _device_registry.save_attachment(
            device_id,
            _robot_attachment_values(req),
            attachment_id=attachment_id,
        )
    except KeyError as exc:
        raise HTTPException(404, "Device or attachment not found") from exc
    except DeviceRegistryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"device": device, "attachment": attachment}


@app.delete("/devices/{device_id}/attachments/{attachment_id}")
def delete_robot_attachment(device_id: str, attachment_id: str):
    try:
        device = _device_registry.delete_attachment(device_id, attachment_id)
    except KeyError as exc:
        raise HTTPException(404, "Device or attachment not found") from exc
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"ok": True, "device": device, "id": attachment_id}


@app.post("/devices/{device_id}/attachments/{attachment_id}/check")
def check_robot_attachment(device_id: str, attachment_id: str):
    device, attachment = _find_robot_attachment(device_id, attachment_id)
    try:
        runtime_client = _runtime_client_or_404(device_id)
        service_id, service_payload = _attachment_service_payload(attachment)
        if service_payload is not None:
            try:
                service = runtime_client.get_service(service_id)
            except DeviceRegistryError:
                service = {}
            if service:
                check = _attachment_service_check(attachment, service)
                check = _attachment_service_check(
                    attachment,
                    service,
                    provider_logs=_attachment_provider_logs(
                        runtime_client,
                        service_id,
                        check,
                    ),
                )
            else:
                diagnostics = runtime_client.ros2_diagnostics()
                check = _attachment_topic_check(attachment, diagnostics)
        else:
            diagnostics = runtime_client.ros2_diagnostics()
            check = _attachment_topic_check(attachment, diagnostics)
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    try:
        updated_device, updated_attachment = (
            _device_registry.remember_attachment_check(
                device_id,
                attachment_id,
                check,
            )
        )
    except KeyError as exc:
        raise HTTPException(404, "Device or attachment not found") from exc
    return {
        "device": updated_device,
        "attachment": updated_attachment,
        "check": check,
    }


@app.post("/devices/{device_id}/attachments/{attachment_id}/start")
def start_robot_attachment(device_id: str, attachment_id: str):
    _, attachment = _find_robot_attachment(device_id, attachment_id)
    if attachment.get("enabled") is False:
        raise HTTPException(409, "Enable this attachment before starting it.")
    try:
        service_id, payload = _attachment_service_payload(attachment)
        if payload is None:
            raise HTTPException(
                409,
                "This attachment uses an existing ROS 2 topic. Start its external "
                "driver, then press Check ROS.",
            )
        runtime_client = _runtime_client_or_404(device_id)
        _sync_attachment_provider_package(runtime_client, attachment)
        service = runtime_client.start_service(
            service_id,
            payload,
        )
        check = _attachment_service_check(attachment, service)
        check = _attachment_service_check(
            attachment,
            service,
            provider_logs=_attachment_provider_logs(
                runtime_client,
                service_id,
                check,
            ),
        )
        updated_device, updated_attachment = (
            _device_registry.remember_attachment_check(
                device_id,
                attachment_id,
                check,
            )
        )
    except HTTPException:
        raise
    except DeviceRegistryError as exc:
        message = str(exc)
        if "404" in message or "not found" in message.lower():
            message = (
                "This device Runtime does not support managed attachments yet. "
                "Update Blacknode Runtime, then start the camera again."
            )
        raise HTTPException(502, message) from exc
    except KeyError as exc:
        raise HTTPException(404, "Device or attachment not found") from exc
    return {
        "device": updated_device,
        "attachment": updated_attachment,
        "service": service,
        "check": check,
    }


@app.post("/devices/{device_id}/attachments/{attachment_id}/stop")
def stop_robot_attachment(device_id: str, attachment_id: str):
    _, attachment = _find_robot_attachment(device_id, attachment_id)
    try:
        service_id, payload = _attachment_service_payload(attachment)
        if payload is None:
            raise HTTPException(
                409,
                "This attachment is provided externally and is not owned by Blacknode.",
            )
        service = _runtime_client_or_404(device_id).stop_service(service_id)
        check = _attachment_service_check(attachment, service)
        updated_device, updated_attachment = (
            _device_registry.remember_attachment_check(
                device_id,
                attachment_id,
                check,
            )
        )
    except HTTPException:
        raise
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "Device or attachment not found") from exc
    return {
        "device": updated_device,
        "attachment": updated_attachment,
        "service": service,
        "check": check,
    }


@app.patch("/devices/{device_id}")
def rename_device(device_id: str, req: RenameDeviceReq):
    try:
        return {"device": _device_registry.rename(device_id, req.name)}
    except KeyError as exc:
        raise HTTPException(404, "Device not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/devices/{device_id}/status")
def get_device_status(device_id: str):
    try:
        return _deployment_aware_device_status(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/devices/{device_id}/monitor")
def get_device_monitor(device_id: str, profile_id: str = "auto"):
    try:
        return _device_monitor_snapshot(device_id, profile_id)
    except KeyError as exc:
        raise HTTPException(404, "Device not found") from exc
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/devices/{device_id}/lifecycle")
def control_robot_lifecycle(device_id: str, req: RobotLifecycleReq):
    try:
        return _control_robot_lifecycle_payload(device_id, req)
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/devices/{device_id}/lifecycle-stream")
def stream_robot_lifecycle(device_id: str, req: RobotLifecycleReq):
    return _lifecycle_stream(
        lambda progress: _control_robot_lifecycle_payload(device_id, req, progress)
    )


@app.get("/devices/{device_id}/runtime-status")
def get_device_runtime_status(device_id: str):
    return _device_runtime_status(device_id)


@app.get("/devices/{device_id}/capabilities")
def get_device_capabilities(device_id: str):
    try:
        return _paired_device_client(device_id).capabilities()
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/devices/{device_id}/calibration")
def activate_device_calibration(device_id: str):
    workflow = _device_deployment_workflow()
    try:
        profile, calibration = _selected_local_calibration(workflow)
        client = _paired_device_client(device_id)
        status = client.status()
        if not status.get("connected"):
            raise HTTPException(
                409,
                str(status.get("error") or "Hardware must be connected first."),
            )
        selection = {
            "profile_id": str(calibration.get("profile_id") or profile.get("id") or ""),
            "hardware_id": str(calibration.get("hardware_id") or ""),
        }
        if _remote_hardware_identity_match(status, selection["hardware_id"]) is False:
            raise HTTPException(
                409,
                _calibration_hardware_mismatch_message(selection, status),
            )
        if status.get("armed"):
            raise HTTPException(409, "Disarm the device before activating calibration.")
        result = client.activate_calibration(profile, calibration)
        refreshed = client.status()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True, "activation": result, "status": refreshed}


def _preflight_check(
    check_id: str,
    label: str,
    status: str,
    message: str,
    *,
    blocking: bool = False,
    action: str | None = None,
    action_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    check = {
        "id": check_id,
        "label": label,
        "status": status,
        "message": message,
        "blocking": blocking,
    }
    if action:
        check["action"] = action
    if action_data:
        check["action_data"] = action_data
    return check


def _workflow_required_capabilities(workflow: dict[str, Any]) -> list[str]:
    metadata = workflow.get("metadata")
    if not isinstance(metadata, dict):
        return []
    raw = metadata.get("required_capabilities")
    if not isinstance(raw, list):
        return []
    return sorted({
        str(item).strip()
        for item in raw
        if isinstance(item, str) and str(item).strip()
    })


def _workflow_requires_deployment_telemetry(workflow: dict[str, Any]) -> bool:
    robot_capabilities = {
        "joint_group",
        "position_feedback",
        "servo_bus",
    }
    if robot_capabilities.intersection(_workflow_required_capabilities(workflow)):
        return True
    robot_node_types = {
        "Robot",
        "RobotDriverLauncher",
        "ROS2JointSliders",
        "ROS2LeaderFollower",
        "ROS2PublishJointState",
        "ROS2SubscribeJointState",
        "ROS2JointController",
        "ROS2ManualMove",
        "ROS2SetJoint",
    }
    return any(
        isinstance(meta, dict)
        and str(meta.get("type") or "") in robot_node_types
        for meta in (workflow.get("node_meta") or {}).values()
    )


def _leader_follower_control_topic(run_id: str, requested: str = "") -> str:
    explicit = str(requested or "").strip()
    if re.fullmatch(
        r"/blacknode/leader_follower/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*",
        explicit,
    ):
        return explicit
    segment = re.sub(
        r"[^a-zA-Z0-9_]+",
        "_",
        str(run_id or "leader_follower"),
    ).strip("_")
    return f"/blacknode/leader_follower/{segment or 'leader_follower'}/control"


def _workflow_motion_controls(workflow: dict[str, Any]) -> list[dict[str, str]]:
    controls: list[dict[str, str]] = []
    for node_id, meta in (workflow.get("node_meta") or {}).items():
        if (
            not isinstance(meta, dict)
            or str(meta.get("type") or "") not in {
                "ROS2LeaderFollower",
                "ROS2JointController",
            }
        ):
            continue
        params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
        run_id = str(params.get("run_id") or "leader_follower").strip()
        controls.append({
            "kind": "ros2_leader_follower",
            "node_id": str(node_id),
            "run_id": run_id,
            "topic": _leader_follower_control_topic(
                run_id,
                str(params.get("control_topic") or ""),
            ),
        })
    return controls


def _workflow_mapping_controls(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Capture the portable MapEnvironment settings for device-side controls."""
    controls: list[dict[str, Any]] = []
    for node_id, meta in (workflow.get("node_meta") or {}).items():
        if not isinstance(meta, dict) or str(meta.get("type") or "") != "MapEnvironment":
            continue
        params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
        controls.append({
            "kind": "slam_toolbox",
            "node_id": str(node_id),
            "map_topic": str(params.get("map_topic") or "/map"),
            "save_directory": str(params.get("save_directory") or "~/Blacknode/maps"),
            "map_name": str(params.get("map_name") or "map_01"),
            "save_map_service": str(
                params.get("save_map_service") or "/slam_toolbox/save_map"
            ),
            "serialize_service": str(
                params.get("serialize_service") or "/slam_toolbox/serialize_map"
            ),
            "serialize_pose_graph": bool(params.get("serialize_pose_graph", True)),
            "service_timeout": float(params.get("service_timeout") or 30.0),
        })
    return controls


def _disarm_workflow_motion_controls(workflow: dict[str, Any]) -> list[str]:
    """Force remotely controlled motion gates off in the deployed snapshot."""
    node_meta = workflow.get("node_meta")
    if not isinstance(node_meta, dict):
        return []
    controlled_ids = {
        str(node_id)
        for node_id, meta in node_meta.items()
        if isinstance(meta, dict)
        and str(meta.get("type") or "") in {
            "ROS2LeaderFollower",
            "ROS2JointController",
        }
    }
    if not controlled_ids:
        return []
    for node_id in controlled_ids:
        meta = node_meta.get(node_id)
        if not isinstance(meta, dict):
            continue
        params = meta.setdefault("params", {})
        if isinstance(params, dict):
            params["armed"] = False

    safe_edges: list[Any] = []
    for edge in workflow.get("edges") or []:
        if not isinstance(edge, dict):
            safe_edges.append(edge)
            continue
        target_id = str(edge.get("to") or "")
        target_port = str(edge.get("to_port") or "")
        if target_id not in controlled_ids or target_port != "armed":
            safe_edges.append(edge)
            continue
        source = node_meta.get(str(edge.get("from") or ""))
        if isinstance(source, dict) and str(source.get("type") or "") == "Bool":
            params = source.setdefault("params", {})
            if isinstance(params, dict):
                params["value"] = False
            safe_edges.append(edge)
        # Dynamic armed inputs are omitted from physical deployments. The
        # deployment-owned control topic becomes the only live arm path.
    workflow["edges"] = safe_edges
    metadata = workflow.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["deployment_motion_default"] = "disarmed"
    return sorted(controlled_ids)


def _workflow_calibration_selection(
    workflow: dict[str, Any],
) -> dict[str, str] | None:
    metadata = workflow.get("metadata")
    raw = metadata.get("device_calibration") if isinstance(metadata, dict) else None
    if not isinstance(raw, dict):
        return None
    profile_id = str(raw.get("profile_id") or "").strip()
    hardware_id = str(raw.get("hardware_id") or "").strip()
    if not profile_id or not hardware_id:
        return None
    return {"profile_id": profile_id, "hardware_id": hardware_id}


def _normalized_hardware_identity(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _identity_value_matches(candidate: Any, hardware_id: str) -> bool:
    candidate_token = _normalized_hardware_identity(candidate)
    hardware_token = _normalized_hardware_identity(hardware_id)
    if not candidate_token or not hardware_token:
        return False
    if candidate_token == hardware_token:
        return True
    # USB serials are commonly embedded in a stable by-id path or an
    # auto-generated service ID. Avoid substring matching tiny identifiers.
    return len(hardware_token) >= 6 and hardware_token in candidate_token


def _remote_hardware_identity_match(
    remote_status: dict[str, Any],
    hardware_id: str,
) -> bool | None:
    """Compare a calibration identity with authoritative hardware status.

    Older hardware services expose the stable USB identity only inside their
    /dev/serial/by-id path or generated device ID. None means the service did
    not expose enough identity information to make a safe comparison.
    """
    connection = (
        remote_status.get("connection")
        if isinstance(remote_status.get("connection"), dict)
        else {}
    )
    explicit = [
        connection.get("hardware_id"),
        connection.get("serial"),
        connection.get("serial_number"),
        remote_status.get("hardware_id"),
    ]
    explicit = [value for value in explicit if str(value or "").strip()]
    if explicit:
        return any(_identity_value_matches(value, hardware_id) for value in explicit)

    port = str(connection.get("port") or "").strip()
    device_id = str(remote_status.get("device_id") or "").strip()
    if _identity_value_matches(port, hardware_id) or _identity_value_matches(
        device_id,
        hardware_id,
    ):
        return True

    normalized_port = port.replace("\\", "/").casefold()
    normalized_device_id = device_id.casefold()
    if "/dev/serial/by-id/" in normalized_port:
        return False
    if "usb" in normalized_device_id and "serial" in normalized_device_id:
        return False
    return None


def _calibration_hardware_mismatch_message(
    selection: dict[str, str],
    remote_status: dict[str, Any],
) -> str:
    connection = (
        remote_status.get("connection")
        if isinstance(remote_status.get("connection"), dict)
        else {}
    )
    device_id = str(remote_status.get("device_id") or "unknown device")
    port = str(connection.get("port") or "unknown serial port")
    return (
        f"Selected calibration {selection['profile_id']} / "
        f"{selection['hardware_id']} belongs to a different physical robot. "
        f"Connected device: {device_id} on {port}. Choose a calibration whose "
        "hardware ID matches this device, or select the paired device that owns "
        f"{selection['hardware_id']}. Do not activate this calibration here."
    )


def _inactive_calibration_message(
    workflow: dict[str, Any],
    remote_status: dict[str, Any],
) -> str:
    selection = _workflow_calibration_selection(workflow)
    if selection is None:
        return (
            "No calibration is selected or active. This feedback-only workflow "
            "may run, but workflows requiring joint_group remain blocked."
        )

    prefix = (
        f"Selected calibration {selection['profile_id']} / "
        f"{selection['hardware_id']} is saved but not active on this device."
    )
    try:
        profile, _calibration = _selected_local_calibration(workflow)
    except ValueError:
        return (
            prefix
            + " The saved calibration file is unavailable. Select or record it "
            "again before using joint_group."
        )

    expected_ids = {
        int(joint["servo_id"])
        for joint in (profile.get("joints") or [])
        if (
            isinstance(joint, dict)
            and isinstance(joint.get("servo_id"), int)
            and not isinstance(joint.get("servo_id"), bool)
        )
    }
    observed_ids = {
        int(match.group(1))
        for name in (remote_status.get("joint_names") or [])
        if (match := re.fullmatch(r"servo_(\d+)", str(name)))
    }
    missing_ids = sorted(expected_ids - observed_ids)
    if expected_ids and observed_ids and missing_ids:
        missing = ", ".join(str(value) for value in missing_ids)
        return (
            prefix
            + f" The current device configuration reports {len(observed_ids)} "
            f"of {len(expected_ids)} expected servos; missing servo ID"
            f"{'s' if len(missing_ids) != 1 else ''}: {missing}. Check that "
            "servo's power, bus connector, and configured ID, then run read-only "
            "robot discovery again. This feedback-only workflow may run, but "
            "joint_group remains blocked."
        )
    return (
        prefix
        + " This feedback-only workflow may run. A workflow requiring "
        "joint_group will prepare the matching calibration during Check setup "
        "while the device is disarmed."
    )


def _robot_profiles_root() -> Path:
    configured = str(os.environ.get("BLACKNODE_ROBOTS_DIR") or "").strip()
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (Path.cwd() / "robots").resolve()
    )


def _workflow_robot_profile_ids(workflow: dict[str, Any]) -> set[str]:
    profile_ids: set[str] = set()
    for meta in (workflow.get("node_meta") or {}).values():
        if not isinstance(meta, dict) or meta.get("type") not in {"Robot", "RobotProfileLoad"}:
            continue
        params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
        profile_id = str(params.get("profile_id") or "").strip()
        if profile_id:
            profile_ids.add(profile_id)
    return profile_ids


def _workflow_robot_nodes(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        meta
        for meta in (workflow.get("node_meta") or {}).values()
        if isinstance(meta, dict) and meta.get("type") in {"Robot", "RobotProfileLoad"}
    ]


def _local_calibration_candidates(
    workflow: dict[str, Any],
) -> list[dict[str, Any]]:
    profile_ids = _workflow_robot_profile_ids(workflow)
    if not profile_ids:
        return []
    root = _robot_profiles_root()
    if not root.is_dir():
        return []
    candidates: list[dict[str, Any]] = []
    for profile_path in sorted(root.glob("*/profile.json")):
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(profile, dict):
            continue
        profile_id = str(profile.get("id") or "").strip()
        if profile_id not in profile_ids:
            continue
        calibration_dir = profile_path.parent / "calibrations"
        for calibration_path in sorted(calibration_dir.glob("*.json")):
            try:
                calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(calibration, dict):
                continue
            hardware_id = str(calibration.get("hardware_id") or "").strip()
            if (
                not hardware_id
                or str(calibration.get("profile_id") or "").strip() != profile_id
            ):
                continue
            candidates.append({
                "profile_id": profile_id,
                "profile_name": str(profile.get("display_name") or profile_id),
                "name": str(calibration.get("name") or hardware_id),
                "hardware_id": hardware_id,
                "recorded_at": str(calibration.get("recorded_at") or ""),
                "joint_count": len(calibration.get("joints") or {}),
            })
    return candidates


def _available_robot_profiles(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    profile_ids = set(_workflow_robot_profile_ids(workflow))
    robot_fn = _NODE_REGISTRY.get("Robot")
    choices = getattr(robot_fn, "_bn_input_choices", {}) if robot_fn else {}
    raw_choices = choices.get("profile_id") if isinstance(choices, dict) else []
    if isinstance(raw_choices, list):
        profile_ids.update(str(value).strip() for value in raw_choices if str(value).strip())

    profiles: dict[str, dict[str, Any]] = {
        profile_id: {
            "id": profile_id,
            "name": profile_id,
            "saved": False,
            "calibration_count": 0,
        }
        for profile_id in profile_ids
    }
    # The enum persists stable profile ids, while the profile registry owns the
    # operator-facing names. Read both so built-ins and saved profiles are
    # presented as "full name · id" instead of exposing only the enum token.
    module = sys.modules.get(getattr(robot_fn, "__module__", "")) if robot_fn else None
    list_profiles = getattr(module, "list_profiles", None)
    if callable(list_profiles):
        try:
            for profile in list_profiles():
                if not isinstance(profile, dict):
                    continue
                profile_id = str(profile.get("id") or "").strip()
                if not profile_id:
                    continue
                profiles[profile_id] = {
                    "id": profile_id,
                    "name": str(profile.get("display_name") or profile_id),
                    "saved": not bool(profile.get("builtin")),
                    "calibration_count": 0,
                }
        except (OSError, ValueError):
            pass
    root = _robot_profiles_root()
    if root.is_dir():
        for profile_path in sorted(root.glob("*/profile.json")):
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(profile, dict):
                continue
            profile_id = str(profile.get("id") or "").strip()
            if not profile_id:
                continue
            calibration_dir = profile_path.parent / "calibrations"
            profiles[profile_id] = {
                "id": profile_id,
                "name": str(profile.get("display_name") or profile_id),
                "saved": True,
                "calibration_count": sum(1 for _ in calibration_dir.glob("*.json")),
            }
    return sorted(profiles.values(), key=lambda item: (item["name"].lower(), item["id"]))


def _selected_local_calibration(
    workflow: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    selection = _workflow_calibration_selection(workflow)
    if selection is None:
        raise ValueError("Select a device calibration for this workflow.")
    root = _robot_profiles_root()
    for profile_path in sorted(root.glob("*/profile.json")):
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            not isinstance(profile, dict)
            or str(profile.get("id") or "").strip() != selection["profile_id"]
        ):
            continue
        calibration_dir = profile_path.parent / "calibrations"
        for calibration_path in sorted(calibration_dir.glob("*.json")):
            try:
                calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(calibration, dict)
                and str(calibration.get("profile_id") or "").strip()
                == selection["profile_id"]
                and str(calibration.get("hardware_id") or "").strip()
                == selection["hardware_id"]
            ):
                return profile, calibration
    raise ValueError(
        "The selected calibration file is unavailable for "
        f"{selection['profile_id']} / {selection['hardware_id']}."
    )


def _embed_selected_calibration(workflow: dict[str, Any]) -> None:
    selection = _workflow_calibration_selection(workflow)
    if selection is None:
        return
    profile, calibration = _selected_local_calibration(workflow)
    robot_nodes = _workflow_robot_nodes(workflow)
    matching_nodes = [
        meta
        for meta in robot_nodes
        if str((meta.get("params") or {}).get("profile_id") or "").strip()
        == selection["profile_id"]
    ]
    if len(robot_nodes) != 1 or len(matching_nodes) != 1:
        raise ValueError(
            "Remote device calibration currently requires exactly one Robot node "
            "using the selected profile."
        )
    meta = matching_nodes[0]
    params = meta.setdefault("params", {})
    params["profile"] = profile
    params["calibration"] = calibration
    inputs = list(meta.get("inputs") or [])
    for port in ("profile", "calibration"):
        if port not in inputs:
            inputs.append(port)
    meta["inputs"] = inputs
    input_types = dict(meta.get("input_types") or {})
    input_types.update({"profile": "Dict", "calibration": "Dict"})
    meta["input_types"] = input_types
    defaults = dict(meta.get("input_defaults") or {})
    defaults.update({"profile": {}, "calibration": {}})
    meta["input_defaults"] = defaults


def _bind_robot_to_device(
    workflow: dict[str, Any],
    remote_status: dict[str, Any],
) -> None:
    """Bind a one-robot deployment to the serial device behind its paired service."""
    robot_nodes = _workflow_robot_nodes(workflow)
    if not robot_nodes:
        return
    if len(robot_nodes) != 1:
        raise ValueError(
            "Deploy one Robot node per device so its physical hardware binding is unambiguous."
        )
    connection = (
        remote_status.get("connection")
        if isinstance(remote_status.get("connection"), dict)
        else {}
    )
    serial_port = str(connection.get("port") or "").strip()
    if str(connection.get("transport") or "").strip() != "serial" or not serial_port:
        raise ValueError(
            "The paired hardware service did not report its serial port. "
            "Update blacknode-robot and restart this robot service."
        )
    calibration = (
        remote_status.get("calibration")
        if isinstance(remote_status.get("calibration"), dict)
        else {}
    )
    hardware_id = str(
        calibration.get("hardware_id")
        or remote_status.get("device_id")
        or ""
    ).strip()
    if not hardware_id:
        raise ValueError("The paired hardware service did not report a hardware identity.")

    recommended = {
        "path": serial_port,
        "serial": hardware_id,
        "serial_number": hardware_id,
    }
    hardware = {
        "found": True,
        "ready": bool(remote_status.get("connected")),
        "port": serial_port,
        "serial": hardware_id,
        "recommended": recommended,
        "devices": [recommended],
        "permissions": {},
        "report": (
            "Deployment target\n"
            f"serial_port: {serial_port}\n"
            f"hardware_id: {hardware_id}"
        ),
    }
    meta = robot_nodes[0]
    params = meta.setdefault("params", {})
    params["hardware"] = hardware
    params["auto_discover"] = False
    params["serial_port"] = serial_port
    inputs = list(meta.get("inputs") or [])
    for port in ("hardware", "auto_discover", "serial_port"):
        if port not in inputs:
            inputs.append(port)
    meta["inputs"] = inputs
    input_types = dict(meta.get("input_types") or {})
    input_types.update({
        "hardware": "Dict",
        "auto_discover": "Bool",
        "serial_port": "Text",
    })
    meta["input_types"] = input_types
    defaults = dict(meta.get("input_defaults") or {})
    defaults.update({
        "hardware": {},
        "auto_discover": True,
        "serial_port": "",
    })
    meta["input_defaults"] = defaults


@app.get("/graph/calibrations")
def list_graph_calibrations():
    workflow = _device_deployment_workflow()
    return {
        "profiles": _available_robot_profiles(workflow),
        "calibrations": _local_calibration_candidates(workflow),
        "selected": _workflow_calibration_selection(workflow),
    }


def _profile_editor_node(
    node_id: str,
    type_name: str,
    pos: list[float],
    params: dict[str, Any],
) -> dict[str, Any]:
    fn = _NODE_REGISTRY.get(type_name)
    if fn is None:
        raise HTTPException(503, f"{type_name} is unavailable; reload blacknode-robot")
    definition = _node_def_payload(type_name, fn)
    return {
        "id": node_id,
        "type": type_name,
        "pos": pos,
        "params": params,
        "inputs": list(definition["inputs"]),
        "outputs": list(definition["outputs"]),
        "input_types": dict(definition["input_types"]),
        "output_types": dict(definition["output_types"]),
        "input_defaults": dict(definition["input_defaults"]),
        "input_choices": dict(definition["input_choices"]),
        "variadic_input": definition["variadic_input"],
        "promoted_inputs": definition["primary_inputs"],
        "promoted_outputs": definition["primary_outputs"],
        "live_capable": bool(definition["live_capable"]),
    }


@app.get("/graph/profiles/{profile_id}/editor")
def robot_profile_editor_graph(profile_id: str):
    clean_id = str(profile_id or "").strip()
    if not clean_id or clean_id == "auto":
        raise HTTPException(400, "Select a concrete robot profile to edit.")
    profile_path = _robot_profiles_root() / clean_id / "profile.json"
    profile: dict[str, Any] | None = None
    if profile_path.is_file():
        try:
            value = json.loads(profile_path.read_text(encoding="utf-8"))
            profile = value if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(409, f"Could not read profile '{clean_id}': {exc}") from exc
    if profile is None:
        robot_fn = _NODE_REGISTRY.get("Robot")
        module = sys.modules.get(getattr(robot_fn, "__module__", "")) if robot_fn else None
        load_profile = getattr(module, "load_profile", None)
        if callable(load_profile):
            profile, _path = load_profile(clean_id)
    if not isinstance(profile, dict):
        raise HTTPException(404, f"Robot profile '{clean_id}' was not found.")
    joints = [
        dict(joint)
        for joint in (profile.get("joints") or [])
        if isinstance(joint, dict) and joint.get("id")
    ]
    joints.sort(key=lambda joint: (int(joint.get("servo_id") or 0), str(joint.get("id"))))
    if not joints:
        raise HTTPException(409, "This profile has no editable joints.")
    if len(joints) > 16:
        raise HTTPException(409, "The visual profile editor currently supports up to 16 joints.")
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for index, joint in enumerate(joints):
        node_id = f"joint_{index + 1}"
        nodes.append(_profile_editor_node(
            node_id,
            "RobotJointDefinition",
            [40.0 + (index % 3) * 340.0, 40.0 + (index // 3) * 300.0],
            {
                "joint_id": str(joint.get("id")),
                "display_name": str(joint.get("display_name") or joint.get("id")),
                "servo_id": int(joint.get("servo_id") or index + 1),
                "min_deg": float(joint.get("min_deg", joint.get("safe_min_deg", -90.0))),
                "max_deg": float(joint.get("max_deg", joint.get("safe_max_deg", 90.0))),
                "home_ticks": int(joint.get("home_ticks") or 2048),
                "invert": bool(joint.get("invert", False)),
                "velocity_limit": float(joint.get("velocity_limit") or 0.0),
                "torque_limit": float(joint.get("torque_limit") or 0.0),
            },
        ))
        edges.append({
            "from": node_id,
            "from_port": "joint",
            "to": "joints",
            "to_port": f"joint_{index + 1}",
        })
    driver = profile.get("driver") if isinstance(profile.get("driver"), dict) else {}
    match = profile.get("match") if isinstance(profile.get("match"), dict) else {}
    rows = (len(joints) + 2) // 3
    nodes.extend([
        _profile_editor_node("joints", "RobotJointList", [1080.0, 170.0 + rows * 150.0], {}),
        _profile_editor_node("definition", "RobotDefinition", [1440.0, 110.0 + rows * 150.0], {
            "profile_id": str(profile.get("id") or clean_id),
            "display_name": str(profile.get("display_name") or clean_id),
            "protocol": str(profile.get("protocol") or "custom"),
            "driver_script": str(driver.get("script") or ""),
            "command_template": str(driver.get("command_template") or ""),
            "baudrate": int(driver.get("baudrate") or 1_000_000),
            "vendor_id": str(match.get("vendor_id") or ""),
            "product_id": str(match.get("product_id") or ""),
            "transport": str(driver.get("transport") or "auto"),
            "host": str(driver.get("host") or "127.0.0.1"),
            "port": int(driver.get("port") or 9090),
            "state_topic": str(driver.get("state_topic") or "/joint_states"),
            "command_topic": str(driver.get("command_topic") or "/joint_commands"),
            "config_topic": str(driver.get("config_topic") or "/joint_config"),
            "control_topic": str(driver.get("control_topic") or "/robot_control"),
            "rate_hz": float(driver.get("rate_hz") or 15.0),
            "units": str(driver.get("units") or "degrees"),
        }),
        _profile_editor_node("save", "RobotProfileSave", [1850.0, 170.0 + rows * 150.0], {"overwrite": True}),
        _profile_editor_node("out", "Output", [2220.0, 190.0 + rows * 150.0], {"label": f"Saved {clean_id}"}),
    ])
    edges.extend([
        {"from": "joints", "from_port": "joints", "to": "definition", "to_port": "joints"},
        {"from": "definition", "from_port": "profile", "to": "save", "to_port": "profile"},
        {"from": "save", "from_port": "report", "to": "out", "to_port": "value"},
    ])
    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "description": f"Edit existing robot profile {clean_id}.",
            "required_packages": ["blacknode-robot"],
        },
    }


def _workflow_required_packages(workflow: dict[str, Any]) -> list[str]:
    metadata = workflow.get("metadata")
    raw = metadata.get("required_packages") if isinstance(metadata, dict) else None
    if not isinstance(raw, list):
        return []
    names: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = ""
        if name:
            names.add(canonical_package_name(name))
    return sorted(names)


def _workflow_target_packages(workflow: dict[str, Any]) -> list[str]:
    """Return explicit and indexed extension packages needed on a target."""
    return sorted({
        item["name"]
        for item in _workflow_target_package_specs(workflow)
        if item.get("name")
    })


def _package_git_source(path: str) -> str:
    package_path = Path(path)
    if not package_path.is_dir():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(package_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    source = result.stdout.strip()
    match = re.fullmatch(r"git@([^:]+):(.+)", source)
    if match:
        return f"https://{match.group(1)}/{match.group(2)}"
    return source


def _runtime_extension_update_specs(
    runtime_manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build latest-revision sync requests for installed extension packages."""
    remote_package_names = {
        str(item.get("name") or "")
        for item in (runtime_manifest.get("packages") or [])
        if (
            isinstance(item, dict)
            and str(item.get("name") or "").startswith("blacknode-")
            and str(item.get("name") or "")
            not in {"blacknode-runtime", "blacknode-robot", "blacknode-hardware"}
        )
    }
    local_packages = {
        info.name: info
        for info in installed_packages()
    }
    indexed_packages = package_index_payload().get("packages") or {}
    specs: list[dict[str, Any]] = []
    warnings: list[str] = []
    for name in sorted(remote_package_names):
        local = local_packages.get(name)
        indexed = indexed_packages.get(name)
        git_url = (
            _package_git_source(str(local.path or ""))
            if local is not None
            else ""
        )
        if not git_url and isinstance(indexed, dict):
            git_url = str(indexed.get("git_url") or "").strip()
        if not git_url:
            warnings.append(
                f"{name} is installed on the Runtime but has no trusted update source."
            )
            continue
        specs.append({
            "name": name,
            "git_url": git_url,
            "update": True,
        })
    return specs, warnings


def _workflow_target_package_specs(
    workflow: dict[str, Any],
) -> list[dict[str, Any]]:
    index = package_index_payload()
    indexed_packages = index.get("packages") or {}
    node_index = index.get("nodes") or {}
    specs: dict[str, dict[str, str]] = {}
    local_packages = {
        info.name: info
        for info in installed_packages()
    }
    local_node_packages = {
        str(node_type): info
        for info in local_packages.values()
        for node_type in info.node_types
    }

    metadata = workflow.get("metadata")
    raw_requirements = (
        metadata.get("required_packages")
        if isinstance(metadata, dict)
        else None
    )
    if isinstance(raw_requirements, list):
        for item in raw_requirements:
            if isinstance(item, str):
                name = item.strip()
                git_url = ""
                version = ""
            elif isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                git_url = str(item.get("git_url") or "").strip()
                version = str(item.get("version") or "").strip()
            else:
                continue
            name = canonical_package_name(name)
            indexed = indexed_packages.get(name)
            if not git_url and isinstance(indexed, dict):
                git_url = str(indexed.get("git_url") or "").strip()
            local = local_packages.get(name)
            if not version and local is not None:
                version = str(local.version or "").strip()
            if not version and isinstance(indexed, dict):
                version = str(indexed.get("version") or "").strip()
            if name:
                specs[name] = {
                    "name": name,
                    "git_url": git_url,
                    "version": version,
                }

    for node_type in workflow_node_types(workflow):
        resolution = node_index.get(node_type)
        local_owner = local_node_packages.get(node_type)
        if isinstance(resolution, dict):
            name = str(resolution.get("package") or "").strip()
            git_url = str(resolution.get("git_url") or "").strip()
        elif local_owner is not None:
            name = str(local_owner.name or "").strip()
            git_url = _package_git_source(str(local_owner.path or ""))
        else:
            continue
        if name:
            existing = specs.get(name)
            local = local_packages.get(name)
            indexed = indexed_packages.get(name)
            version = (
                str(existing.get("version") or "")
                if existing
                else str(local.version or "")
                if local is not None
                else str(indexed.get("version") or "")
                if isinstance(indexed, dict)
                else ""
            )
            specs[name] = {
                "name": name,
                "git_url": (
                    str(existing.get("git_url") or "")
                    if existing
                    else git_url
                ) or git_url,
                "version": version,
            }

    def requirement_spec(package_name: str) -> dict[str, Any]:
        existing = specs.get(package_name)
        if existing is not None:
            return existing
        indexed = indexed_packages.get(package_name)
        local = local_packages.get(package_name)
        spec: dict[str, Any] = {
            "name": package_name,
            "git_url": (
                _package_git_source(str(local.path or ""))
                if local is not None
                else str(indexed.get("git_url") or "")
                if isinstance(indexed, dict)
                else ""
            ),
            "version": (
                str(local.version or "")
                if local is not None
                else str(indexed.get("version") or "")
                if isinstance(indexed, dict)
                else ""
            ),
        }
        specs[package_name] = spec
        return spec

    for requirement in template_component_requirements(workflow):
        package_name = str(requirement.get("package") or "").strip()
        component_name = str(requirement.get("component") or "").strip()
        if not package_name or not component_name:
            continue
        spec = requirement_spec(package_name)
        components = {
            str(item)
            for item in spec.get("components", [])
            if str(item)
        }
        components.add(component_name)
        spec["components"] = sorted(components)

    for requirement in template_adapter_requirements(workflow):
        package_name = str(requirement.get("package") or "").strip()
        component_name = str(requirement.get("component") or "").strip()
        adapter_name = str(requirement.get("adapter") or "").strip()
        if not package_name or not component_name or not adapter_name:
            continue
        spec = requirement_spec(package_name)
        adapters = {
            (
                str(item.get("component") or ""),
                str(item.get("adapter") or ""),
            )
            for item in spec.get("adapters", [])
            if isinstance(item, dict)
        }
        adapters.add((component_name, adapter_name))
        spec["adapters"] = [
            {"component": component, "adapter": adapter}
            for component, adapter in sorted(adapters)
            if component and adapter
        ]
    ordered_specs = [specs[name] for name in sorted(specs)]
    for spec in ordered_specs:
        if spec.get("git_url"):
            # Package versions describe API compatibility, so multiple
            # revisions can legitimately share one version. Deployments must
            # still refresh Git-backed packages or a device may keep running
            # stale driver/runtime adapter code indefinitely.
            spec["update"] = True
    return ordered_specs


def _device_deployment_workflow(
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(workflow, dict):
        data = json.loads(json.dumps(workflow))
    else:
        data = _workflow_payload(
            "Current graph",
            metadata={"source": "remote_deployment"},
        )
    if not isinstance(data.get("entrypoint"), dict):
        entrypoint = _infer_export_entrypoint(data)
        if entrypoint is not None:
            data["entrypoint"] = entrypoint
    try:
        _embed_selected_calibration(data)
    except ValueError:
        # Preflight reports a focused calibration error. Keeping the graph
        # intact here lets workflow validation and dependency checks still run.
        pass
    return data


def _device_deployment_hash(workflow: dict[str, Any]) -> str:
    """Hash deployable graph content without volatile display timestamps."""
    content = {
        key: workflow[key]
        for key in (
            "kind",
            "schema_version",
            "node_meta",
            "edges",
            "entrypoint",
            "metadata",
        )
        if key in workflow
    }
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _device_deployment_attachments(device_id: str) -> list[dict[str, Any]]:
    """Return enabled robot attachments as stable deployment configuration."""
    try:
        device = _device_registry.get_public(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if device is None:
        raise HTTPException(404, "Device not found")
    attachments: list[dict[str, Any]] = []
    for item in device.get("attachments") or []:
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        attachment = json.loads(json.dumps(item))
        attachment.pop("last_check", None)
        attachments.append(attachment)
    return attachments


def _ready_attachment_capabilities(device: dict[str, Any]) -> set[str]:
    """Return enabled attachment capabilities proven ready by their latest check."""
    return {
        str(item.get("capability") or "").strip()
        for item in (device.get("attachments") or [])
        if (
            isinstance(item, dict)
            and item.get("enabled") is not False
            and isinstance(item.get("last_check"), dict)
            and item["last_check"].get("ok") is True
            and str(item.get("capability") or "").strip()
        )
    }


@app.post("/devices/{device_id}/deployment-preflight")
def validate_device_deployment(device_id: str, req: DeploymentPreflightReq):
    try:
        device = _device_registry.get_public(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if device is None:
        raise HTTPException(404, "Device not found")

    workflow = _device_deployment_workflow(req.workflow)

    checks: list[dict[str, Any]] = []
    workflow_validation = validate_bn_workflow(workflow).to_dict()
    if workflow_validation.get("ok"):
        checks.append(_preflight_check(
            "workflow",
            "Workflow",
            "pass",
            f"{len(workflow.get('node_meta') or {})} nodes passed workflow validation.",
        ))
    else:
        errors = workflow_validation.get("errors") or []
        message = "; ".join(
            str(item.get("message") or item.get("code") or "invalid workflow")
            for item in errors[:3]
            if isinstance(item, dict)
        ) or "Workflow validation failed."
        checks.append(_preflight_check(
            "workflow", "Workflow", "fail", message, blocking=True,
        ))

    dependencies = _workflow_dependency_report(workflow)
    if dependencies.get("ok"):
        checks.append(_preflight_check(
            "local_dependencies",
            "Editor dependencies",
            "pass",
            "The editor can resolve every node and declared package requirement.",
        ))
    else:
        package_repairs = sorted({
            (
                str(item.get("name") or ""),
                str(item.get("git_url") or ""),
            )
            for item in dependencies.get("missing_packages", [])
            if (
                isinstance(item, dict)
                and not bool(item.get("installed"))
                and str(item.get("name") or "")
                and str(item.get("git_url") or "")
            )
        })
        installable_package_names = {
            package for package, _git_url in package_repairs
        }
        component_repairs = sorted({
            (
                str(item.get("package") or ""),
                str(item.get("component") or ""),
            )
            for item in dependencies.get("missing_components", [])
            if (
                isinstance(item, dict)
                and (
                    str(item.get("reason") or "") == "component is disabled"
                    or (
                        str(item.get("reason") or "") == "package is not installed"
                        and str(item.get("package") or "")
                        in installable_package_names
                    )
                )
                and str(item.get("package") or "")
                and str(item.get("component") or "")
            )
        })
        adapter_repairs = sorted({
            (
                str(item.get("package") or ""),
                str(item.get("component") or ""),
                str(item.get("adapter") or ""),
            )
            for item in dependencies.get("missing_adapters", [])
            if (
                isinstance(item, dict)
                and str(item.get("reason") or "") in {
                    "adapter is disabled",
                    "parent component is disabled",
                    "package is not installed",
                }
                and (
                    str(item.get("reason") or "") != "package is not installed"
                    or str(item.get("package") or "")
                    in installable_package_names
                )
                and str(item.get("package") or "")
                and str(item.get("component") or "")
                and str(item.get("adapter") or "")
            )
        })
        dependency_action_data = {
            "packages": [
                {"name": package, "git_url": git_url}
                for package, git_url in package_repairs
            ],
            "components": [
                {"package": package, "component": component}
                for package, component in component_repairs
            ],
            "adapters": [
                {
                    "package": package,
                    "component": component,
                    "adapter": adapter,
                }
                for package, component, adapter in adapter_repairs
            ],
        }
        can_repair_dependencies = bool(
            package_repairs or component_repairs or adapter_repairs
        )
        checks.append(_preflight_check(
            "local_dependencies",
            "Editor dependencies",
            "fail",
            str(dependencies.get("message") or "Workflow dependencies are incomplete."),
            blocking=True,
            action=(
                "enable_editor_dependencies"
                if can_repair_dependencies
                else None
            ),
            action_data=(
                dependency_action_data
                if can_repair_dependencies
                else None
            ),
        ))

    try:
        remote_status = _deployment_aware_device_status(device_id)
    except DeviceRegistryError as exc:
        checks.append(_preflight_check(
            "service",
            "Device service",
            "fail",
            str(exc),
            blocking=True,
        ))
        checks.extend([
            _preflight_check(
                "hardware", "Hardware connection", "pending",
                "Waiting for the device service.", blocking=True,
            ),
            _preflight_check(
                "safety", "Safety state", "pending",
                "Waiting for the device service.", blocking=True,
            ),
            _preflight_check(
                "capabilities", "Capabilities", "pending",
                "Waiting for the device service.", blocking=True,
            ),
            _preflight_check(
                "target_runtime", "Target runtime", "pending",
                "Waiting for the device service runtime manifest.", blocking=True,
            ),
        ])
        return _deployment_preflight_payload(device, workflow, checks, None, None)

    checks.append(_preflight_check(
        "service",
        "Device service",
        "pass",
        f"Authenticated with {remote_status.get('device_id') or device['remote_device_id']}.",
    ))

    connected = bool(remote_status.get("connected"))
    checks.append(_preflight_check(
        "hardware",
        "Hardware connection",
        "pass" if connected else "fail",
        (
            f"{len(remote_status.get('joint_names') or [])} joints are reporting state."
            if connected
            else str(
                remote_status.get("error")
                or remote_status.get("notice")
                or "Hardware is not connected."
            )
        ),
        blocking=not connected,
    ))

    armed = bool(remote_status.get("armed"))
    checks.append(_preflight_check(
        "safety",
        "Safety state",
        "fail" if armed else "pass",
        (
            "Device is armed. Disarm it before staging a deployment."
            if armed
            else "Device is disarmed."
        ),
        blocking=armed,
    ))

    robot_nodes = _workflow_robot_nodes(workflow)
    if robot_nodes:
        try:
            binding_probe = json.loads(json.dumps(workflow))
            _bind_robot_to_device(binding_probe, remote_status)
        except ValueError as exc:
            checks.append(_preflight_check(
                "hardware_binding",
                "Robot hardware binding",
                "fail",
                str(exc),
                blocking=True,
            ))
        else:
            connection = remote_status.get("connection") or {}
            checks.append(_preflight_check(
                "hardware_binding",
                "Robot hardware binding",
                "pass",
                f"Deployment will use {connection.get('port')}.",
            ))

    required_capabilities = _workflow_required_capabilities(workflow)
    available_capabilities = sorted({
        str(item)
        for item in (remote_status.get("capabilities") or [])
        if isinstance(item, str)
    } | _ready_attachment_capabilities(device))
    if required_capabilities:
        missing_capabilities = sorted(set(required_capabilities) - set(available_capabilities))
        checks.append(_preflight_check(
            "capabilities",
            "Capabilities",
            "fail" if missing_capabilities else "pass",
            (
                "Missing: " + ", ".join(missing_capabilities)
                if missing_capabilities
                else "Available: " + ", ".join(required_capabilities)
            ),
            blocking=bool(missing_capabilities),
        ))
    else:
        checks.append(_preflight_check(
            "capabilities",
            "Capabilities",
            "warning",
            (
                "Workflow does not declare metadata.required_capabilities. "
                f"Device reports: {', '.join(available_capabilities) or 'none'}."
            ),
        ))

    calibrated = remote_status.get("calibrated")
    selection = _workflow_calibration_selection(workflow)
    hardware_identity_match = (
        _remote_hardware_identity_match(
            remote_status,
            selection["hardware_id"],
        )
        if selection
        else None
    )
    hardware_mismatch = hardware_identity_match is False
    requires_joint_motion = "joint_group" in required_capabilities
    if selection and hardware_mismatch:
        checks.append(_preflight_check(
            "calibration",
            "Calibration",
            "fail",
            _calibration_hardware_mismatch_message(selection, remote_status),
            blocking=True,
            action="choose_matching_hardware",
        ))
    elif requires_joint_motion:
        active_calibration = (
            remote_status.get("calibration")
            if isinstance(remote_status.get("calibration"), dict)
            else {}
        )
        calibration_matches = bool(
            selection
            and calibrated is True
            and str(active_calibration.get("profile_id") or "") == selection["profile_id"]
            and str(active_calibration.get("hardware_id") or "") == selection["hardware_id"]
            and not hardware_mismatch
        )
        selection_error = ""
        if selection is not None:
            try:
                _selected_local_calibration(workflow)
                robot_nodes = _workflow_robot_nodes(workflow)
                matching_nodes = [
                    meta
                    for meta in robot_nodes
                    if str((meta.get("params") or {}).get("profile_id") or "").strip()
                    == selection["profile_id"]
                ]
                if len(robot_nodes) != 1 or len(matching_nodes) != 1:
                    selection_error = (
                        "Remote device calibration currently requires exactly one "
                        "Robot node using the selected profile."
                    )
            except ValueError as exc:
                selection_error = str(exc)
        calibration_action = (
            "select_calibration"
            if selection is None or selection_error
            else "activate_calibration"
            if not calibration_matches
            else None
        )
        checks.append(_preflight_check(
            "calibration",
            "Calibration",
            "pass" if calibration_matches and not selection_error else "fail",
            (
                (
                    f"Active: {selection['profile_id']} / {selection['hardware_id']}."
                    if selection
                    else ""
                )
                if calibration_matches and not selection_error
                else selection_error
                or (
                    "Select a saved device calibration."
                    if selection is None
                    else (
                        (
                            "Disarm this device, then Check setup will prepare "
                            f"{selection['profile_id']} / {selection['hardware_id']}."
                        )
                        if armed
                        else (
                            f"Check setup will prepare {selection['profile_id']} / "
                            f"{selection['hardware_id']} automatically."
                        )
                    )
                )
            ),
            blocking=not calibration_matches or bool(selection_error),
            action=calibration_action,
        ))
    elif calibrated is False and "joint_group" in available_capabilities:
        checks.append(_preflight_check(
            "calibration",
            "Calibration",
            "warning",
            _inactive_calibration_message(workflow, remote_status),
        ))

    runtime_manifest = None
    try:
        runtime_manifest = _device_registry.runtime_client(device_id).manifest()
        if (
            runtime_manifest.get("service") != "blacknode-runtime"
            or runtime_manifest.get("protocol_version") != 1
        ):
            raise DeviceRegistryError("Runtime service identity or protocol is incompatible.")
        features = set(runtime_manifest.get("features") or [])
        required_features = {"manifest_v1", "deployment_bundle_v1", "process_supervision_v1", "rollback_v1"}
        missing_features = sorted(required_features - features)
        blacknode_info = runtime_manifest.get("blacknode") or {}
        python_version = str((runtime_manifest.get("python") or {}).get("version") or "")
        try:
            python_parts = tuple(int(part) for part in python_version.split(".")[:2])
        except ValueError:
            python_parts = (0, 0)
        runtime_package_versions = {
            str(item.get("name")): str(item.get("version") or "")
            for item in (runtime_manifest.get("packages") or [])
            if isinstance(item, dict) and item.get("name")
        }
        runtime_packages = set(runtime_package_versions)
        package_specs = _workflow_target_package_specs(workflow)
        missing_packages = sorted(
            set(_workflow_target_packages(workflow)) - runtime_packages
        )
        outdated_packages = sorted({
            item["name"]
            for item in package_specs
            if (
                item.get("version")
                and item["name"] in runtime_package_versions
                and runtime_package_versions[item["name"]] != item["version"]
            )
        })
        packages_to_sync = sorted(set(missing_packages) | set(outdated_packages))
        registered_node_types = runtime_manifest.get("node_types")
        missing_node_types: list[str] = []
        if isinstance(registered_node_types, list):
            missing_node_types = sorted(
                workflow_node_types(workflow) - {
                    str(item)
                    for item in registered_node_types
                    if isinstance(item, str)
                }
            )
        problems = []
        if python_parts < (3, 11):
            problems.append(f"Python {python_version or 'unknown'} is below 3.11")
        if not blacknode_info.get("installed"):
            problems.append("Blacknode core is not installed")
        if missing_features:
            problems.append("missing runtime features: " + ", ".join(missing_features))
        package_sync_available = "package_sync_v1" in features
        component_sync_available = "component_sync_v1" in features
        installable_packages = {
            item["name"]
            for item in package_specs
            if item.get("git_url")
        }
        activation_packages = {
            str(item["name"])
            for item in package_specs
            if item.get("components") or item.get("adapters")
        }
        package_sync_ready = (
            package_sync_available
            and set(packages_to_sync) <= installable_packages
        )
        preparable_packages = (
            set(packages_to_sync) - activation_packages
            if package_sync_ready
            else set()
        )
        if package_sync_ready and component_sync_available:
            preparable_packages.update(set(packages_to_sync) & activation_packages)
        if component_sync_available:
            preparable_packages.update(activation_packages)
        package_owned_nodes = {
            str(node_type)
            for node_type, resolution in (package_index_payload().get("nodes") or {}).items()
            if (
                isinstance(resolution, dict)
                and str(resolution.get("package") or "") in preparable_packages
            )
        }
        auto_installable = package_sync_ready
        hard_missing_nodes = (
            sorted(set(missing_node_types) - package_owned_nodes)
            if package_sync_ready or component_sync_available
            else missing_node_types
        )
        if packages_to_sync and not auto_installable:
            if missing_packages:
                problems.append("missing target packages: " + ", ".join(missing_packages))
            if outdated_packages:
                problems.append("outdated target packages: " + ", ".join(outdated_packages))
        activation_missing_nodes = sorted(
            set(missing_node_types)
            & {
                str(node_type)
                for node_type, resolution in (package_index_payload().get("nodes") or {}).items()
                if (
                    isinstance(resolution, dict)
                    and str(resolution.get("package") or "") in activation_packages
                )
            }
        )
        if activation_missing_nodes and not component_sync_available:
            problems.append(
                "target runtime must be updated to activate workflow components: "
                + ", ".join(activation_missing_nodes)
            )
            hard_missing_nodes = sorted(
                set(hard_missing_nodes) - set(activation_missing_nodes)
            )
        if hard_missing_nodes:
            problems.append("unregistered target nodes: " + ", ".join(hard_missing_nodes))
        activation_to_sync = sorted({
            str(resolution.get("package") or "")
            for node_type, resolution in (package_index_payload().get("nodes") or {}).items()
            if (
                node_type in set(missing_node_types)
                and isinstance(resolution, dict)
                and str(resolution.get("package") or "") in activation_packages
                and component_sync_available
            )
        })
        preparation_to_sync = sorted(set(packages_to_sync) | set(activation_to_sync))
        package_message = (
            " · will synchronize " + ", ".join(preparation_to_sync) + " when sent"
            if preparation_to_sync and auto_installable
            else ""
        )
        checks.append(_preflight_check(
            "target_runtime",
            "Target runtime",
            (
                "fail"
                if problems
                else "warning"
                if preparation_to_sync and auto_installable
                else "pass"
            ),
            (
                "; ".join(problems)
                if problems
                else (
                    f"Runtime {runtime_manifest.get('runtime_version')} · "
                    f"Python {python_version} · "
                    f"Blacknode {blacknode_info.get('version')}"
                    f"{package_message}"
                )
            ),
            blocking=bool(problems),
        ))
    except (DeviceRegistryError, KeyError) as exc:
        runtime_error = str(exc)
        if "pairing token was rejected" in runtime_error.casefold():
            runtime_error = (
                "Runtime authentication needs attention. Open Devices, choose "
                "Re-pair, and paste the token shown by ./service.sh pairing."
            )
        checks.append(_preflight_check(
            "target_runtime",
            "Target runtime",
            "pending",
            (
                f"{runtime_error} Install and start blacknode-runtime on "
                f"{device.get('runtime_url')}."
            ),
            blocking=True,
        ))
    return _deployment_preflight_payload(
        device, workflow, checks, remote_status, runtime_manifest,
    )


def _deployment_preflight_payload(
    device: dict[str, Any],
    workflow: dict[str, Any],
    checks: list[dict[str, Any]],
    remote_status: dict[str, Any] | None,
    runtime_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    blocking = [
        check for check in checks
        if check.get("blocking") and check.get("status") != "pass"
    ]
    return {
        "ready": not blocking,
        "summary": (
            "Deployment preflight passed."
            if not blocking
            else f"{len(blocking)} blocking check{'s' if len(blocking) != 1 else ''} need attention."
        ),
        "device": device,
        "workflow": {
            "name": str(workflow.get("name") or "Current graph"),
            "node_count": len(workflow.get("node_meta") or {}),
            "required_capabilities": _workflow_required_capabilities(workflow),
            "hash": _device_deployment_hash(workflow),
        },
        "status": remote_status,
        "runtime": runtime_manifest,
        "checks": checks,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _runtime_client_or_404(device_id: str):
    try:
        return _device_registry.runtime_client(device_id)
    except KeyError as exc:
        raise HTTPException(404, "Device not found") from exc
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc


def _require_device_safe_to_start(device_id: str) -> None:
    try:
        status = _deployment_aware_device_status(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not status.get("connected"):
        raise HTTPException(
            409,
            str(status.get("error") or "Hardware is not connected."),
        )
    if status.get("armed"):
        raise HTTPException(
            409,
            "Device is armed. Disarm it before starting a deployment.",
        )


def _set_device_deployment_lease(device_id: str, *, leased: bool) -> None:
    method = "release" if leased else "resume"
    payload = {
        "jsonrpc": "2.0",
        "id": f"deployment-{method}",
        "method": method,
        "params": {},
    }
    try:
        result = _paired_device_client(device_id).rpc(payload)
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    error = result.get("error") if isinstance(result, dict) else None
    if error:
        message = (
            str(error.get("message") or error)
            if isinstance(error, dict)
            else str(error)
        )
        raise HTTPException(
            502,
            f"Could not {method} robot hardware access: {message}",
        )


def _robot_deployment_summary(
    deployment: dict[str, Any],
    *,
    include_motion: bool = True,
) -> dict[str, Any]:
    """Keep robot-card lifecycle fields portable and credential free."""
    summary: dict[str, Any] = {
        "id": str(deployment.get("id") or ""),
        "name": str(
            deployment.get("name")
            or deployment.get("id")
            or "Deployment"
        ),
        "state": str(deployment.get("state") or "stopped"),
    }
    motion_count = int(deployment.get("motion_control_count") or 0)
    if include_motion or motion_count or deployment.get("motion_armed"):
        summary["motion_armed"] = bool(deployment.get("motion_armed"))
        summary["motion_control_count"] = motion_count
    mapping_count = int(deployment.get("mapping_control_count") or 0)
    if mapping_count:
        summary["mapping_control_count"] = mapping_count
        summary["mapping_topic"] = str(
            deployment.get("mapping_topic") or "/map"
        )
        artifact = deployment.get("last_map_artifact")
        if isinstance(artifact, dict):
            summary["last_map_artifact"] = dict(artifact)
    return summary


def _deployment_aware_device_status(device_id: str) -> dict[str, Any]:
    """Report running deployments separately from physical motion ownership."""
    client = _paired_device_client(device_id)
    status = client.status()
    status = {
        **status,
        "connection_state": (
            "connected" if bool(status.get("connected")) else "disconnected"
        ),
    }
    saved_device = _device_registry.get_public(device_id)
    reported_version = str(status.get("software_version") or "").strip()
    saved_version = str((saved_device or {}).get("software_version") or "").strip()
    if reported_version and reported_version.casefold() != "unknown":
        try:
            _device_registry.remember_device_software_version(
                device_id,
                reported_version,
            )
        except KeyError:
            pass
    elif saved_version:
        status = {
            **status,
            "software_version": saved_version,
            "software_version_cached": True,
        }
    paused = bool(saved_device and saved_device.get("paused"))
    if paused:
        status = {**status, "paused": True}
    error = str(status.get("error") or "")
    folded_error = error.casefold()
    hardware_is_leased = (
        "leased" in folded_error
        and "deployment" in folded_error
    )

    try:
        runtime_client = _device_registry.runtime_client(device_id)
        payload = runtime_client.list_deployments()
    except (DeviceRegistryError, KeyError, AttributeError, TypeError):
        return status
    deployments = [
        item
        for item in (payload.get("deployments") or [])
        if isinstance(item, dict)
    ]
    active = [
        item
        for item in deployments
        if (
            str(item.get("state") or "") == "running"
            and str(item.get("target_device_id") or "") in {"", device_id}
        )
    ]
    if active:
        owner = active[0]
        result = dict(status)
        conflicting_deployments = [
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or item.get("id") or "Deployment"),
                "state": "running",
            }
            for item in active
        ]
        deployment = _robot_deployment_summary(owner)
        if hardware_is_leased:
            result["deployment_lease"] = deployment
            result["armed"] = bool(deployment.get("motion_armed"))
            connection_present = status.get("connection_present")
            presence_reported = isinstance(connection_present, bool)
            result["connected"] = bool(connection_present) if presence_reported else False
            result["connection_state"] = (
                "connected" if result["connected"] else "disconnected"
            )
            result["connection_reported"] = presence_reported
            connection_source = "device_path" if presence_reported else ""
            telemetry_message = ""
            try:
                telemetry = runtime_client.deployment_telemetry(deployment["id"])
                telemetry_payload = telemetry.get("payload")
                telemetry_message = str(telemetry.get("message") or "").strip()
                telemetry_connected = (
                    telemetry_payload.get("connected")
                    if isinstance(telemetry_payload, dict)
                    else None
                )
                if (
                    bool(telemetry.get("available"))
                    and not bool(telemetry.get("stale"))
                    and isinstance(telemetry_connected, bool)
                ):
                    result["connected"] = telemetry_connected
                    result["connection_reported"] = True
                    result["connection_source"] = "deployment_telemetry"
                    connection_source = "deployment_telemetry"
                    result["connection_state"] = (
                        "connected" if telemetry_connected else "disconnected"
                    )
                    telemetry_torque = telemetry_payload.get("torque_enabled")
                    if isinstance(telemetry_torque, bool):
                        result["torque_enabled"] = telemetry_torque
            except (DeviceRegistryError, AttributeError, TypeError) as exc:
                telemetry_message = str(exc)
            result.pop("error", None)
            if not result["connection_reported"]:
                result["notice"] = (
                    f"Running deployment '{owner.get('name') or owner.get('id')}' "
                    "did not report a fresh hardware connection, so Blacknode treats "
                    "the robot as disconnected."
                    + (f" {telemetry_message}" if telemetry_message else "")
                    + " Stop the deployment, then check the device to verify a "
                    "physical disconnect."
                )
            elif connection_source == "device_path":
                result["notice"] = (
                    f"Running deployment '{owner.get('name') or owner.get('id')}' "
                    f"controls this robot. Its configured serial device path is "
                    f"{'present' if result['connected'] else 'missing'}; this check "
                    "does not open or compete for the serial port."
                )
            else:
                result["notice"] = (
                    f"Running deployment '{owner.get('name') or owner.get('id')}' "
                    "controls this robot. Connection state comes from its fresh "
                    "deployment telemetry."
                )
        else:
            result["running_deployment"] = deployment
            result["notice"] = (
                f"Deployment '{owner.get('name') or owner.get('id')}' is running, "
                "but the hardware service does not report that it owns motion control."
            )
        if len(conflicting_deployments) > 1:
            result["conflicting_deployments"] = conflicting_deployments
            result["notice"] = (
                f"Safety conflict: {len(conflicting_deployments)} deployments are "
                f"running for this robot. Pause the robot to stop all of them. "
                + str(result.get("notice") or "")
            )
        return result

    if hardware_is_leased:
        try:
            _set_device_deployment_lease(device_id, leased=False)
            status = client.status()
            if paused:
                status = {**status, "paused": True}
        except HTTPException:
            pass

    stored = sorted(
        (
            item
            for item in deployments
            if (
                str(item.get("state") or "") != "running"
                and str(item.get("target_device_id") or "") in {"", device_id}
                and str(item.get("id") or "")
            )
        ),
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("created_at") or ""),
        ),
        reverse=True,
    )
    if stored:
        deployment = stored[0]
        result = dict(status)
        inactive_deployment = _robot_deployment_summary(
            deployment,
            include_motion=False,
        )
        # Keep the old field as a compatibility alias for existing clients.
        result["inactive_deployment"] = inactive_deployment
        result["stored_deployment"] = inactive_deployment
        deployment_name = str(
            deployment.get("name") or deployment.get("id") or "Deployment"
        )
        deployment_state = str(deployment.get("state") or "stopped")
        state_detail = {
            "stopped": "stopped",
            "exited": "completed",
            "failed": "failed",
            "staged": "ready to start",
        }.get(deployment_state, f"inactive ({deployment_state})")
        next_action = (
            "Resume this robot before restarting it."
            if paused
            else (
                "Review its details before restarting it."
                if deployment_state == "failed"
                else "It can be restarted."
            )
        )
        result["notice"] = (
            f"Deployment '{deployment_name}' is {state_detail} on the Runtime. "
            f"{next_action}"
        )
        return result

    if paused:
        result = dict(status)
        result["notice"] = (
            "Robot is paused and disarmed. Resume it before starting a workflow."
        )
        return result
    return status


def _monitor_payload_from_device_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert canonical Blacknode robot state into the editor view model."""
    if payload.get("kind") != "blacknode.device-state":
        return payload
    joint_state = payload.get("joint_state")
    joint_state = joint_state if isinstance(joint_state, dict) else {}
    positions = dict(joint_state.get("positions") or {})
    velocities = dict(joint_state.get("velocities") or {})
    limits = dict(joint_state.get("limits") or {})
    values = (
        payload.get("values")
        if isinstance(payload.get("values"), dict)
        else {}
    )
    raw_positions = dict(values.get("raw_positions") or {})
    servo_ids = dict(values.get("servo_ids") or {})
    bus = values.get("bus") if isinstance(values.get("bus"), dict) else {}
    temperatures_c = dict(payload.get("temperatures_c") or {})
    voltages_v = dict(bus.get("voltages_v") or {})
    hardware_error_flags = dict(bus.get("hardware_error_flags") or {})
    hardware_errors = dict(bus.get("hardware_errors") or {})
    servo_status = dict(bus.get("servo_status") or {})
    calibration = (
        values.get("calibration")
        if isinstance(values.get("calibration"), dict)
        else {}
    )
    position_unit = str(joint_state.get("position_unit") or "radian")
    velocity_unit = str(joint_state.get("velocity_unit") or "radian/s")
    to_display = math.degrees if position_unit == "radian" else float
    velocity_to_display = (
        math.degrees if velocity_unit == "radian/s" else float
    )
    joints = []
    for name, raw_position in positions.items():
        try:
            position = to_display(float(raw_position))
            velocity = velocity_to_display(float(velocities.get(name, 0.0)))
        except (TypeError, ValueError):
            continue
        item = {
            "name": str(name),
            "position": position,
            "velocity": velocity,
        }
        reported_servo_id = servo_ids.get(name)
        servo_match = re.fullmatch(r"servo_(\d+)", str(name))
        if (
            isinstance(reported_servo_id, int)
            and not isinstance(reported_servo_id, bool)
        ):
            item["servo_id"] = int(reported_servo_id)
        elif servo_match:
            item["servo_id"] = int(servo_match.group(1))
        if name in raw_positions and isinstance(raw_positions[name], int):
            item["raw_position"] = int(raw_positions[name])
        if bus:
            item["communication_ok"] = True
        if isinstance(temperatures_c.get(name), (int, float)):
            item["temperature_c"] = float(temperatures_c[name])
        if isinstance(voltages_v.get(name), (int, float)):
            item["voltage_v"] = float(voltages_v[name])
        if isinstance(hardware_error_flags.get(name), int):
            item["hardware_error_flags"] = int(hardware_error_flags[name])
        if isinstance(hardware_errors.get(name), list):
            item["hardware_errors"] = [
                str(value) for value in hardware_errors[name]
            ]
        if isinstance(servo_status.get(name), int):
            item["servo_status"] = int(servo_status[name])
        raw_limits = limits.get(name)
        if isinstance(raw_limits, dict):
            try:
                item["lower_limit"] = to_display(float(raw_limits["lower"]))
                item["upper_limit"] = to_display(float(raw_limits["upper"]))
            except (KeyError, TypeError, ValueError):
                pass
        joints.append(item)
    return {
        "connected": bool(payload.get("connected")),
        "armed": bool(payload.get("armed")),
        "torque_enabled": payload.get("torque_enabled"),
        "position_unit": "degree" if position_unit == "radian" else position_unit,
        "velocity_unit": (
            "degree/s" if velocity_unit == "radian/s" else velocity_unit
        ),
        "joints": joints,
        "error": str(payload.get("error") or ""),
        "faults": list(payload.get("faults") or []),
        "temperatures_c": temperatures_c,
        "voltage_v": payload.get("voltage_v"),
        "voltages_v": voltages_v,
        "bus": dict(bus),
        "calibrated": values.get("calibrated"),
        "calibration": calibration,
    }


def _monitor_payload_with_status_metadata(
    payload: dict[str, Any],
    status: dict[str, Any],
) -> dict[str, Any]:
    """Fill stable robot identity metadata missing from live driver samples."""
    result = dict(payload)
    telemetry_calibration = (
        result.get("calibration")
        if isinstance(result.get("calibration"), dict)
        else {}
    )
    status_calibration = (
        status.get("calibration")
        if isinstance(status.get("calibration"), dict)
        else {}
    )
    calibration = {
        **status_calibration,
        **telemetry_calibration,
    }
    if calibration:
        for field in (
            "name",
            "profile_id",
            "hardware_id",
            "activated_at",
            "digest",
        ):
            if not calibration.get(field) and status_calibration.get(field):
                calibration[field] = status_calibration[field]
        expected_joint_count = calibration.get("joint_count")
        if not isinstance(expected_joint_count, int) or isinstance(
            expected_joint_count,
            bool,
        ):
            topology = calibration.get("topology")
            calibrated_joints = calibration.get("joints")
            if isinstance(topology, dict) and topology:
                calibration["joint_count"] = len(topology)
            elif isinstance(calibrated_joints, dict) and calibrated_joints:
                calibration["joint_count"] = len(calibrated_joints)
        result["calibration"] = calibration

    status_calibrated = status.get("calibrated")
    if isinstance(status_calibrated, bool):
        result["calibrated"] = status_calibrated
    return result


def _monitor_profile_selection(value: Any) -> str:
    selected = str(value or "auto").strip()
    return selected if selected else "auto"


def _local_robot_monitor_targets(
    requested_profile_id: str = "auto",
) -> list[dict[str, Any]]:
    """Discover local USB robots and resolve each through the Robot contract."""
    discover = _NODE_REGISTRY.get("RobotUSBDiscovery")
    robot_node = _NODE_REGISTRY.get("Robot")
    raw_monitor = _NODE_REGISTRY.get("RobotRawMonitor")
    selection = _monitor_profile_selection(requested_profile_id)
    raw_mode = selection.lower() == "none"
    if discover is None or (robot_node is None and not raw_mode):
        return []
    try:
        discovered = discover({"probe_open": False})
    except Exception:
        return []
    targets: list[dict[str, Any]] = []
    for device in discovered.get("devices") or []:
        if not isinstance(device, dict):
            continue
        serial_port = str(device.get("path") or "").strip()
        if not serial_port or device.get("accessible") is False:
            continue
        hardware = {
            "found": True,
            "ready": bool(device.get("accessible", True)),
            "port": serial_port,
            "serial": str(
                device.get("serial")
                or device.get("serial_number")
                or serial_port
            ),
            "devices": [dict(device)],
            "recommended": dict(device),
            "permissions": dict(discovered.get("permissions") or {}),
            "report": str(discovered.get("report") or ""),
        }
        if raw_mode:
            resolved = {
                "profile": {},
                "calibration": {},
                "hardware_id": hardware["serial"],
                "report": (
                    "Raw read-only mode discovers responding servo IDs and "
                    "shows uncalibrated register values."
                    if raw_monitor is not None
                    else "RobotRawMonitor is unavailable; reload blacknode-robot."
                ),
            }
        else:
            try:
                resolved = robot_node({
                    "profile_id": selection,
                    "hardware": hardware,
                    "auto_discover": False,
                    "action": "check",
                    "require_hardware": True,
                    "serial_port": serial_port,
                })
            except Exception as exc:
                resolved = {
                    "profile": {},
                    "calibration": {},
                    "hardware_id": hardware["serial"],
                    "report": f"{type(exc).__name__}: {exc}",
                }
        profile = (
            resolved.get("profile")
            if isinstance(resolved.get("profile"), dict)
            else {}
        )
        profile_id = str(profile.get("id") or "").strip()
        hardware_id = str(
            resolved.get("hardware_id")
            or hardware.get("serial")
            or serial_port
        ).strip()
        target_token = json.dumps(
            [serial_port, hardware_id, profile_id],
            separators=(",", ":"),
        ).encode("utf-8")
        target_id = (
            "local-usb-"
            + hashlib.sha256(target_token).hexdigest()[:16]
        )
        profile_name = str(
            profile.get("display_name")
            or profile_id
            or ("Raw servos" if raw_mode else "Unmatched robot")
        )
        targets.append({
            "id": target_id,
            "name": f"{profile_name} · {serial_port}",
            "kind": "local_usb",
            "available": bool(
                hardware.get("ready")
                and ((raw_mode and raw_monitor is not None) or profile_id)
            ),
            "profile_id": profile_id,
            "requested_profile_id": selection,
            "raw_mode": raw_mode,
            "hardware_id": hardware_id,
            "port": serial_port,
            "profile": dict(profile),
            "hardware": hardware,
            "calibration": (
                dict(resolved.get("calibration"))
                if isinstance(resolved.get("calibration"), dict)
                else {}
            ),
            "message": str(resolved.get("report") or ""),
        })
    return targets


def _local_robot_monitor_target(
    target_id: str,
    profile_id: str = "auto",
) -> dict[str, Any] | None:
    return next(
        (
            target
            for target in _local_robot_monitor_targets(profile_id)
            if target["id"] == target_id
        ),
        None,
    )


@app.get("/robot-monitor-targets")
def list_robot_monitor_targets(profile_id: str = "auto"):
    selection = _monitor_profile_selection(profile_id)
    try:
        registered = _device_registry.list()
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    targets = [
        {
            "id": str(device.get("id") or ""),
            "name": str(device.get("name") or device.get("id") or "Robot"),
            "kind": "registered",
            "available": not bool(device.get("paused")),
            "hardware_id": str(device.get("remote_device_id") or ""),
            "device": device,
        }
        for device in registered
        if str(device.get("id") or "")
    ]
    targets.extend(
        _local_robot_monitor_targets()
        if selection == "auto"
        else _local_robot_monitor_targets(selection)
    )
    profiles = [
        profile
        for profile in _available_robot_profiles({})
        if str(profile.get("id") or "").lower() not in {"auto", "none"}
    ]
    return {
        "targets": targets,
        "profiles": profiles,
        "profile_id": selection,
    }


def _local_raw_robot_monitor_snapshot(
    target: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    """Read one profile-free sample through a registered read-only provider."""
    target_id = str(target.get("id") or "")
    target_name = str(target.get("name") or target_id)
    raw_monitor = _NODE_REGISTRY.get("RobotRawMonitor")
    if raw_monitor is None:
        return {
            "type": "robot_telemetry",
            "robot_id": target_id,
            "robot_name": target_name,
            "source": "hardware",
            "source_label": f"Local USB raw · {target.get('port') or ''}",
            "available": False,
            "stale": True,
            "received_at": now,
            "message": "RobotRawMonitor is unavailable; reload blacknode-robot.",
        }
    result = raw_monitor({
        "hardware": dict(target.get("hardware") or {}),
        "max_servo_id": 32,
        "__run_mode__": "once",
    })
    joints = [
        dict(value)
        for value in (result.get("joints") or [])
        if isinstance(value, dict)
    ]
    warnings = [str(value) for value in (result.get("warnings") or []) if value]
    errors = [str(value) for value in (result.get("errors") or []) if value]
    faults: list[dict[str, Any]] = []
    for joint in joints:
        flags = int(joint.get("hardware_error_flags") or 0)
        if not flags:
            continue
        message = next(
            (
                warning
                for warning in warnings
                if warning.startswith(f"{joint.get('name')} (")
            ),
            (
                f"{joint.get('name')} hardware warning 0x{flags:02x}: "
                + (
                    ", ".join(
                        str(value)
                        for value in (joint.get("hardware_errors") or [])
                    )
                    or "vendor status"
                )
            ),
        )
        faults.append({
            "kind": "blacknode.fault-state",
            "schema_version": 1,
            "code": "hardware-warning",
            "message": message,
            "severity": "warning",
            "active": True,
            "details": {
                "joint": str(joint.get("name") or ""),
                "servo_id": int(joint.get("servo_id") or 0),
                "flags": flags,
                "decoded": list(joint.get("hardware_errors") or []),
            },
        })
    temperatures_c = {
        str(joint.get("name") or ""): float(joint["temperature_c"])
        for joint in joints
        if isinstance(joint.get("temperature_c"), (int, float))
        and not isinstance(joint.get("temperature_c"), bool)
    }
    voltages_v = {
        str(joint.get("name") or ""): float(joint["voltage_v"])
        for joint in joints
        if isinstance(joint.get("voltage_v"), (int, float))
        and not isinstance(joint.get("voltage_v"), bool)
    }
    available = bool(result.get("available") and joints)
    return {
        "type": "robot_telemetry",
        "robot_id": target_id,
        "robot_name": target_name,
        "source": "hardware",
        "source_label": f"Local USB raw · {target.get('port') or ''}",
        "available": available,
        "stale": not available,
        "sequence": int(time.time() * 1000),
        "sent_at": now,
        "received_at": now,
        "payload": {
            "connected": available,
            "armed": False,
            "torque_enabled": result.get("torque_enabled"),
            "raw_mode": True,
            "position_unit": str(result.get("position_unit") or "ticks"),
            "velocity_unit": str(result.get("velocity_unit") or "ticks/s"),
            "joints": joints,
            "error": "\n".join(errors),
            "faults": faults,
            "temperatures_c": temperatures_c,
            "voltage_v": min(voltages_v.values()) if voltages_v else None,
            "voltages_v": voltages_v,
            "bus": dict(result.get("diagnostics") or {}),
            "calibrated": False,
            "calibration": {
                "hardware_id": str(target.get("hardware_id") or ""),
                "joint_count": 0,
            },
            "provider": dict(result.get("provider") or {}),
        },
        "message": str(result.get("report") or "\n".join(errors)),
    }


def _local_robot_monitor_snapshot(target: dict[str, Any]) -> dict[str, Any]:
    """Read one local USB robot sample through its bound provider."""
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    target_id = str(target.get("id") or "")
    target_name = str(target.get("name") or target_id)
    if target.get("raw_mode"):
        return _local_raw_robot_monitor_snapshot(target, now)
    profile = (
        target.get("profile")
        if isinstance(target.get("profile"), dict)
        else {}
    )
    if not target.get("available") or not profile:
        return {
            "type": "robot_telemetry",
            "robot_id": target_id,
            "robot_name": target_name,
            "source": "hardware",
            "source_label": f"Local USB · {target.get('port') or ''}",
            "available": False,
            "stale": True,
            "received_at": now,
            "message": str(
                target.get("message")
                or "Select or save one matching robot profile for this USB device."
            ),
        }
    control = _NODE_REGISTRY.get("RobotCalibrationControl")
    if control is None:
        return {
            "type": "robot_telemetry",
            "robot_id": target_id,
            "robot_name": target_name,
            "source": "hardware",
            "source_label": f"Local USB · {target.get('port') or ''}",
            "available": False,
            "stale": True,
            "received_at": now,
            "message": "RobotCalibrationControl is unavailable; reload blacknode-robot.",
        }
    motion_sample = _runtime_callable(
        "robot_servo_motion",
        _RUNTIME_MODULES["robot_servo_motion"],
        "sample_servo_motion_for_robot",
    )
    result = motion_sample(target_id) if motion_sample is not None else None
    if not isinstance(result, dict):
        result = control({
            "action": "check",
            "profile": profile,
            "hardware": dict(target.get("hardware") or {}),
            "__run_mode__": "once",
        })
    pose = {
        str(name): float(value)
        for name, value in dict(result.get("pose") or {}).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    servos = {
        str(name): dict(value)
        for name, value in dict(result.get("servos") or {}).items()
        if isinstance(value, dict)
    }
    joints = []
    for raw_joint in profile.get("joints") or []:
        if not isinstance(raw_joint, dict):
            continue
        name = str(raw_joint.get("id") or "").strip()
        if not name or name not in pose:
            continue
        servo = servos.get(name, {})
        item: dict[str, Any] = {
            "name": name,
            "semantic_name": str(
                raw_joint.get("display_name")
                or name
            ),
            "servo_id": int(
                servo.get("servo_id")
                or raw_joint.get("servo_id")
                or 0
            ),
            "position": pose[name],
            "velocity": 0.0,
            "communication_ok": bool(
                servo.get("communication_ok", True)
            ),
        }
        for field in (
            "ticks",
            "temperature_c",
            "voltage_v",
            "hardware_error_flags",
            "hardware_errors",
            "servo_status",
        ):
            if servo.get(field) is not None:
                item[
                    "raw_position" if field == "ticks" else field
                ] = servo[field]
        try:
            item["lower_limit"] = float(
                raw_joint.get("safe_min_deg", raw_joint.get("min_deg"))
            )
            item["upper_limit"] = float(
                raw_joint.get("safe_max_deg", raw_joint.get("max_deg"))
            )
        except (TypeError, ValueError):
            pass
        joints.append(item)
    diagnostics = dict(result.get("diagnostics") or {})
    hardware_error_flags = {
        name: int(servo.get("hardware_error_flags") or 0)
        for name, servo in servos.items()
    }
    hardware_errors = {
        name: list(servo.get("hardware_errors") or [])
        for name, servo in servos.items()
        if servo.get("hardware_errors")
    }
    servo_status = {
        name: int(servo.get("servo_status") or 0)
        for name, servo in servos.items()
        if servo.get("servo_status") is not None
    }
    voltages_v = {
        name: float(servo["voltage_v"])
        for name, servo in servos.items()
        if isinstance(servo.get("voltage_v"), (int, float))
    }
    temperatures_c = {
        name: float(servo["temperature_c"])
        for name, servo in servos.items()
        if isinstance(servo.get("temperature_c"), (int, float))
    }
    bus = {
        **diagnostics,
        "hardware_error_flags": hardware_error_flags,
        "hardware_errors": hardware_errors,
        "servo_status": servo_status,
        "voltages_v": voltages_v,
    }
    warnings = [str(value) for value in (result.get("warnings") or [])]
    faults: list[dict[str, Any]] = []
    joint_warning_messages: set[str] = set()
    for name, servo in servos.items():
        flags = int(servo.get("hardware_error_flags") or 0)
        if not flags:
            continue
        warning = next(
            (
                value
                for value in warnings
                if value.startswith(f"{name} (")
            ),
            (
                f"{name} (servo {servo.get('servo_id') or '?'}) "
                f"hardware warning 0x{flags:02x}: "
                + (
                    ", ".join(str(value) for value in (servo.get("hardware_errors") or []))
                    or "vendor status"
                )
            ),
        )
        joint_warning_messages.add(warning)
        faults.append({
            "kind": "blacknode.fault-state",
            "schema_version": 1,
            "code": "hardware-warning",
            "message": warning,
            "severity": "warning",
            "active": True,
            "details": {
                "joint": name,
                "servo_id": int(servo.get("servo_id") or 0),
                "flags": flags,
                "decoded": list(servo.get("hardware_errors") or []),
            },
        })
    faults.extend(
        {
            "kind": "blacknode.fault-state",
            "schema_version": 1,
            "code": "hardware-warning",
            "message": warning,
            "severity": "warning",
            "active": True,
        }
        for warning in warnings
        if warning not in joint_warning_messages
    )
    calibration = dict(target.get("calibration") or {})
    calibration.setdefault("profile_id", str(profile.get("id") or ""))
    calibration.setdefault("hardware_id", str(target.get("hardware_id") or ""))
    available = bool(result.get("data_ready") and joints)
    return {
        "type": "robot_telemetry",
        "robot_id": target_id,
        "robot_name": target_name,
        "source": "hardware",
        "source_label": f"Local USB · {target.get('port') or ''}",
        "available": available,
        "stale": not available,
        "sequence": int(time.time() * 1000),
        "sent_at": now,
        "received_at": now,
        "payload": {
            "connected": available,
            "armed": result.get("torque_enabled") is True,
            "torque_enabled": result.get("torque_enabled"),
            "position_unit": "degree",
            "velocity_unit": "degree/s",
            "joints": joints,
            "error": "" if result.get("command_ok") else str(result.get("report") or ""),
            "faults": faults,
            "temperatures_c": temperatures_c,
            "voltage_v": min(voltages_v.values()) if voltages_v else None,
            "voltages_v": voltages_v,
            "bus": bus,
            "calibrated": bool(target.get("calibration")),
            "calibration": calibration,
        },
        "message": str(result.get("report") or ""),
    }


_ROBOT_MONITOR_SAMPLE_INTERVAL_SECONDS = 0.05
_ROBOT_MONITOR_STALE_GRACE_SECONDS = 1.5
_robot_monitor_cache_lock = threading.Lock()
_robot_monitor_device_locks: dict[str, threading.Lock] = {}
_robot_monitor_snapshot_cache: dict[str, dict[str, Any]] = {}


def _robot_monitor_device_lock(device_id: str) -> threading.Lock:
    with _robot_monitor_cache_lock:
        return _robot_monitor_device_locks.setdefault(
            device_id,
            threading.Lock(),
        )


def _cached_local_robot_monitor_snapshot(
    device_id: str,
    profile_id: str = "auto",
) -> dict[str, Any]:
    """Serialize local bus reads and preserve one brief failed sample as stale."""
    target = _local_robot_monitor_target(device_id, profile_id)
    if target is None:
        raise KeyError(device_id)
    physical_key = str(
        target.get("hardware_id")
        or target.get("port")
        or device_id
    )
    selection = _monitor_profile_selection(profile_id)
    cache_key = (
        device_id
        if selection == "auto"
        else f"{device_id}\0{selection}"
    )
    lock = _robot_monitor_device_lock(physical_key)
    with lock:
        sampled_at = time.monotonic()
        with _robot_monitor_cache_lock:
            cached = _robot_monitor_snapshot_cache.get(cache_key)
            if (
                cached
                and sampled_at - float(cached.get("sampled_at") or 0.0)
                < _ROBOT_MONITOR_SAMPLE_INTERVAL_SECONDS
            ):
                return copy.deepcopy(cached["latest"])

        snapshot = _local_robot_monitor_snapshot(target)
        sampled_at = time.monotonic()
        with _robot_monitor_cache_lock:
            cached = _robot_monitor_snapshot_cache.setdefault(cache_key, {})
            if snapshot.get("available"):
                cached["last_good"] = copy.deepcopy(snapshot)
                cached["last_good_at"] = sampled_at
                latest = snapshot
            else:
                last_good = cached.get("last_good")
                last_good_at = float(cached.get("last_good_at") or 0.0)
                age = sampled_at - last_good_at
                if (
                    isinstance(last_good, dict)
                    and age <= _ROBOT_MONITOR_STALE_GRACE_SECONDS
                ):
                    latest = copy.deepcopy(last_good)
                    latest["stale"] = True
                    latest["age_seconds"] = max(0.0, age)
                    latest["message"] = (
                        "Telemetry retrying; keeping the last good joint "
                        "positions visible."
                    )
                    latest["transient_error"] = str(
                        snapshot.get("message") or ""
                    )
                else:
                    latest = snapshot
            cached["latest"] = copy.deepcopy(latest)
            cached["sampled_at"] = sampled_at
        return copy.deepcopy(latest)


def _device_monitor_snapshot(
    device_id: str,
    profile_id: str = "auto",
) -> dict[str, Any]:
    """Return one normalized robot-state sample from the current bus owner."""
    if device_id.startswith("local-usb-"):
        return _cached_local_robot_monitor_snapshot(device_id, profile_id)
    device = _device_registry.get_public(device_id)
    if device is None:
        raise KeyError(device_id)
    status = _deployment_aware_device_status(device_id)
    deployment = status.get("deployment_lease") or status.get("running_deployment")
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    if isinstance(deployment, dict) and deployment.get("id"):
        deployment_id = str(deployment["id"])
        try:
            telemetry = _device_registry.runtime_client(device_id).deployment_telemetry(
                deployment_id,
            )
        except (DeviceRegistryError, AttributeError, TypeError) as exc:
            detail = str(exc)
            endpoint_missing = "HTTP 404" in detail or "not found" in detail.casefold()
            return {
                "type": "robot_telemetry",
                "robot_id": device_id,
                "robot_name": str(device.get("name") or device_id),
                "source": "deployment",
                "source_label": str(deployment.get("name") or deployment_id),
                "deployment": deployment,
                "available": False,
                "stale": True,
                "received_at": now,
                "message": (
                    (
                        "This device Runtime does not support deployed monitoring yet. "
                        "Update Runtime to 0.3.9 or newer; Robot Hardware does not "
                        "need to be reinstalled. Then stage the workflow again to sync "
                        "blacknode-drivers 0.2.1 or newer and restart the deployment."
                    )
                    if endpoint_missing
                    else (
                        "The running deployment has not exposed live telemetry yet. "
                        "Update Runtime and the robot driver package, then restart the "
                        f"deployment. Details: {detail}"
                    )
                ),
            }
        payload = telemetry.get("payload")
        available = bool(telemetry.get("available") and isinstance(payload, dict))
        monitor_payload = (
            _monitor_payload_from_device_state(payload)
            if available
            else None
        )
        if isinstance(monitor_payload, dict):
            monitor_payload = _monitor_payload_with_status_metadata(
                monitor_payload,
                status,
            )
        return {
            "type": "robot_telemetry",
            "robot_id": device_id,
            "robot_name": str(device.get("name") or device_id),
            "source": "deployment",
            "source_label": str(deployment.get("name") or deployment_id),
            "deployment": deployment,
            "available": available,
            "stale": bool(telemetry.get("stale", not available)),
            "sequence": int(telemetry.get("sequence") or 0),
            "sent_at": str(telemetry.get("sent_at") or ""),
            "received_at": str(telemetry.get("received_at") or now),
            "age_seconds": telemetry.get("age_seconds"),
            "payload": monitor_payload,
            "message": str(
                telemetry.get("message")
                or (
                    "Receiving state from the running deployment."
                    if available
                    else "Waiting for the running deployment to publish robot state."
                )
            ),
        }

    positions = {
        str(name): float(value)
        for name, value in dict(status.get("positions") or {}).items()
        if isinstance(value, (int, float))
    }
    reported_joint_names = [
        str(name)
        for name in (status.get("joint_names") or [])
        if str(name) in positions
    ]
    joint_names = reported_joint_names + [
        name for name in positions if name not in reported_joint_names
    ]
    raw_positions = dict(status.get("raw_positions") or {})
    status_limits = dict(status.get("limits") or {})
    calibration = (
        status.get("calibration")
        if isinstance(status.get("calibration"), dict)
        else {}
    )
    calibration_topology = dict(calibration.get("topology") or {})
    calibration_joints = dict(calibration.get("joints") or {})
    status_values = (
        status.get("values")
        if isinstance(status.get("values"), dict)
        else {}
    )
    status_bus = (
        status.get("bus")
        if isinstance(status.get("bus"), dict)
        else status_values.get("bus")
        if isinstance(status_values.get("bus"), dict)
        else {}
    )
    temperatures_c = dict(status.get("temperatures_c") or {})
    voltages_v = dict(
        status.get("voltages_v")
        or status_bus.get("voltages_v")
        or {}
    )
    hardware_error_flags = dict(
        status.get("hardware_error_flags")
        or status_bus.get("hardware_error_flags")
        or {}
    )
    hardware_errors = dict(
        status.get("hardware_errors")
        or status_bus.get("hardware_errors")
        or {}
    )
    servo_status = dict(
        status.get("servo_status")
        or status_bus.get("servo_status")
        or {}
    )

    def hardware_joint(name: str) -> dict[str, Any]:
        item: dict[str, Any] = {
            "name": name,
            "position": positions[name],
            "velocity": 0.0,
        }
        servo_match = re.fullmatch(r"servo_(\d+)", name)
        servo_id = int(servo_match.group(1)) if servo_match else None
        if servo_id is not None:
            item["servo_id"] = servo_id
            semantic_name = str(calibration_topology.get(str(servo_id)) or "")
            if semantic_name:
                item["semantic_name"] = semantic_name
        if isinstance(raw_positions.get(name), int):
            item["raw_position"] = int(raw_positions[name])
        if status_bus:
            item["communication_ok"] = True
        if isinstance(temperatures_c.get(name), (int, float)):
            item["temperature_c"] = float(temperatures_c[name])
        if isinstance(voltages_v.get(name), (int, float)):
            item["voltage_v"] = float(voltages_v[name])
        if isinstance(hardware_error_flags.get(name), int):
            item["hardware_error_flags"] = int(hardware_error_flags[name])
        if isinstance(hardware_errors.get(name), list):
            item["hardware_errors"] = [
                str(value) for value in hardware_errors[name]
            ]
        if isinstance(servo_status.get(name), int):
            item["servo_status"] = int(servo_status[name])

        raw_limit = status_limits.get(name)
        if isinstance(raw_limit, dict):
            try:
                item["lower_limit"] = float(
                    raw_limit["lower"]
                    if "lower" in raw_limit
                    else raw_limit["min"]
                )
                item["upper_limit"] = float(
                    raw_limit["upper"]
                    if "upper" in raw_limit
                    else raw_limit["max"]
                )
            except (KeyError, TypeError, ValueError):
                pass
        semantic_name = str(item.get("semantic_name") or "")
        calibrated_joint = calibration_joints.get(semantic_name)
        if isinstance(calibrated_joint, dict):
            try:
                item["lower_limit"] = float(calibrated_joint["safe_min_deg"])
                item["upper_limit"] = float(calibrated_joint["safe_max_deg"])
            except (KeyError, TypeError, ValueError):
                pass
        return item

    available = bool(status.get("connected") and positions)
    error = str(status.get("error") or "")
    faults = [
        dict(item)
        for item in (status.get("faults") or [])
        if isinstance(item, dict)
    ]
    if error and not faults:
        faults = [{
            "kind": "blacknode.fault-state",
            "schema_version": 1,
            "code": "device-error",
            "message": error,
            "severity": "error",
            "active": True,
        }]
    return {
        "type": "robot_telemetry",
        "robot_id": device_id,
        "robot_name": str(device.get("name") or device_id),
        "source": "hardware",
        "source_label": "Robot Hardware",
        "available": available,
        "stale": not available,
        "sequence": int(time.time() * 1000),
        "sent_at": now,
        "received_at": now,
        "payload": _monitor_payload_with_status_metadata({
            "connected": bool(status.get("connected")),
            "armed": bool(status.get("armed")),
            "torque_enabled": status.get("torque_enabled"),
            "position_unit": "degree",
            "velocity_unit": "degree/s",
            "joints": [
                hardware_joint(name)
                for name in joint_names
                if name in positions
            ],
            "error": error,
            "faults": faults,
            "temperatures_c": temperatures_c,
            "voltage_v": status.get("voltage_v"),
            "voltages_v": voltages_v,
            "bus": dict(status_bus),
            "calibrated": status.get("calibrated"),
            "calibration": calibration,
        }, status),
        "message": (
            "Receiving state from Robot Hardware."
            if available
            else str(
                status.get("error")
                or "Robot Hardware is connected but has not reported joint positions."
            )
        ),
    }


@app.websocket("/api/devices/{device_id}/monitor/ws")
@app.websocket("/devices/{device_id}/monitor/ws")
async def device_monitor_socket(
    websocket: WebSocket,
    device_id: str,
    profile_id: str = "auto",
):
    await websocket.accept()
    receive_task = asyncio.create_task(websocket.receive())
    try:
        while True:
            if receive_task.done():
                message = receive_task.result()
                if message.get("type") == "websocket.disconnect":
                    return
                receive_task = asyncio.create_task(websocket.receive())
            try:
                snapshot = await asyncio.to_thread(
                    _device_monitor_snapshot,
                    device_id,
                    profile_id,
                )
            except KeyError:
                await websocket.send_json({
                    "type": "robot_telemetry",
                    "robot_id": device_id,
                    "available": False,
                    "stale": True,
                    "message": "Robot is no longer paired with this editor.",
                })
                await websocket.close(code=1008)
                return
            except Exception as exc:  # keep a transient device outage visible
                snapshot = {
                    "type": "robot_telemetry",
                    "robot_id": device_id,
                    "available": False,
                    "stale": True,
                    "received_at": datetime.now().astimezone().isoformat(
                        timespec="milliseconds"
                    ),
                    "message": f"Monitoring temporarily unavailable: {exc}",
                }
            try:
                await websocket.send_json(snapshot)
            except Exception:
                return
            done, _pending = await asyncio.wait(
                {receive_task},
                timeout=_ROBOT_MONITOR_SAMPLE_INTERVAL_SECONDS,
            )
            if done:
                message = receive_task.result()
                if message.get("type") == "websocket.disconnect":
                    return
                receive_task = asyncio.create_task(websocket.receive())
    except (WebSocketDisconnect, RuntimeError, OSError, asyncio.CancelledError):
        return
    finally:
        if not receive_task.done():
            receive_task.cancel()
        with contextlib.suppress(
            asyncio.CancelledError,
            WebSocketDisconnect,
            RuntimeError,
        ):
            await receive_task


@app.get("/devices/{device_id}/deployments")
def list_device_deployments(device_id: str):
    try:
        payload = _runtime_client_or_404(device_id).list_deployments()
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    deployments = [
        deployment
        for deployment in (payload.get("deployments") or [])
        if (
            isinstance(deployment, dict)
            and str(deployment.get("target_device_id") or "").strip()
            in {"", device_id}
        )
    ]
    return {**payload, "deployments": deployments}


def _require_targeted_deployment(
    device_id: str,
    deployment_id: str,
) -> dict[str, Any]:
    try:
        deployment = _runtime_client_or_404(device_id).get_deployment(deployment_id)
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    target_device_id = str(deployment.get("target_device_id") or "").strip()
    if target_device_id and target_device_id != device_id:
        raise HTTPException(
            404,
            f"Deployment '{deployment_id}' does not belong to this robot.",
        )
    return deployment


def _remote_deployment_owner(
    device_id: str,
    req: RemoteDeployReq,
) -> dict[str, str]:
    project_id = str(req.project_id or "").strip()
    workflow_slug = str(req.workflow_slug or "").strip()
    if not project_id and not workflow_slug:
        return {}
    if not project_id or not workflow_slug:
        raise HTTPException(
            400,
            "Deployment ownership requires both project_id and workflow_slug.",
        )
    try:
        project = _project_store.get(project_id)
    except ProjectStoreError as exc:
        raise HTTPException(400, str(exc)) from exc
    if project is None:
        raise HTTPException(404, f"Project '{project_id}' not found")
    if workflow_slug not in project.get("workflow_slugs", []):
        raise HTTPException(
            409,
            f"Workflow '{workflow_slug}' is not linked to project "
            f"'{project.get('name') or project_id}'.",
        )
    if device_id not in project.get("device_ids", []):
        raise HTTPException(
            409,
            f"Device '{device_id}' is not linked to project "
            f"'{project.get('name') or project_id}'. Link it in Projects before staging.",
        )
    if not os.path.exists(_workflow_path(workflow_slug)):
        raise HTTPException(
            409,
            f"Workflow '{workflow_slug}' is no longer saved. Save it again before staging.",
        )
    return {
        "project_id": project_id,
        "workflow_slug": workflow_slug,
    }


def _target_deployment_records(
    runtime_client,
    device_id: str,
    *,
    exclude_id: str = "",
) -> list[dict[str, Any]]:
    return [
        item
        for item in (
            runtime_client.list_deployments().get("deployments") or []
        )
        if (
            isinstance(item, dict)
            and str(item.get("target_device_id") or "") == device_id
            and str(item.get("id") or "")
            and str(item.get("id") or "") != exclude_id
        )
    ]


def _start_replacing_device_deployment(
    device_id: str,
    runtime_client,
    deployment_id: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    superseded = _target_deployment_records(
        runtime_client,
        device_id,
        exclude_id=deployment_id,
    )
    for item in superseded:
        if str(item.get("state") or "") == "running":
            runtime_client.stop_deployment(str(item["id"]))

    _require_device_safe_to_start(device_id)
    _set_device_deployment_lease(device_id, leased=True)
    try:
        deployment = runtime_client.start_deployment(deployment_id)
    except Exception:
        _set_device_deployment_lease(device_id, leased=False)
        raise

    superseded_ids = {
        str(item.get("id") or "")
        for item in superseded
        if str(item.get("id") or "")
    }
    superseded_ids.update(
        str(item)
        for item in (deployment.get("superseded_deployment_ids") or [])
        if str(item)
    )
    # Retain stopped deployments and their revisions until the operator uses
    # the explicit Remove action. Automatic deletion made a deployment appear
    # to vanish and could erase the recoverable record when multiple robots
    # share one Runtime.
    return deployment, sorted(superseded_ids), []


def _stage_device_deployment_payload(
    device_id: str,
    req: RemoteDeployReq,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress({
                "progress": max(0, min(100, int(percent))),
                "message": message,
            })

    report(4, "Preparing deployment")
    deployment_owner = _remote_deployment_owner(device_id, req)
    workflow = _device_deployment_workflow()
    current_hash = _device_deployment_hash(workflow)
    requested_hash = req.workflow_hash.strip().lower()
    report(10, "Confirming the validated graph revision")
    if not requested_hash or requested_hash != current_hash:
        raise HTTPException(
            409,
            "The graph changed after validation. Validate deployment again before staging.",
        )

    report(18, "Running deployment safety checks")
    preflight = validate_device_deployment(
        device_id,
        DeploymentPreflightReq(workflow=workflow),
    )
    if not preflight.get("ready"):
        blocking = [
            str(check.get("message") or check.get("label") or "deployment is not ready")
            for check in preflight.get("checks", [])
            if check.get("blocking") and check.get("status") != "pass"
        ]
        raise HTTPException(
            409,
            "Deployment preflight failed: " + "; ".join(blocking[:3]),
        )

    robot_attachments = _device_deployment_attachments(device_id)
    report(28, "Exporting the workflow with motion disarmed")
    try:
        _bind_robot_to_device(workflow, preflight.get("status") or {})
        _disarm_workflow_motion_controls(workflow)
        workflow["entrypoint"] = resolve_entrypoint(workflow)
        script = export_workflow_python(workflow)
    except (WorkflowRunError, ValueError) as exc:
        raise HTTPException(400, f"Could not export workflow: {exc}") from exc

    name = req.name.strip() or str(workflow.get("name") or "Deployed graph")
    runtime_manifest = preflight.get("runtime") or {}
    if (
        deployment_owner
        and "deployment_ownership_v1" not in set(runtime_manifest.get("features") or [])
    ):
        raise HTTPException(
            409,
            "This target runtime cannot record Project ownership yet. Update "
            "blacknode-runtime to 0.3.8 or newer, restart it, and check setup again.",
        )
    payload: dict[str, Any] = {
        "name": name,
        "script": script,
        "workflow": workflow,
        "manifest": {
            "schema_version": 1,
            "workflow_hash": current_hash,
            "workflow_name": str(workflow.get("name") or name),
            "entrypoint": dict(workflow["entrypoint"]),
            "node_count": len(workflow.get("node_meta") or {}),
            "required_capabilities": _workflow_required_capabilities(workflow),
            "telemetry_required": _workflow_requires_deployment_telemetry(workflow),
            "motion_controls": _workflow_motion_controls(workflow),
            "mapping_controls": _workflow_mapping_controls(workflow),
            "required_packages": _workflow_target_packages(workflow),
            "package_requirements": _workflow_target_package_specs(workflow),
            "blacknode_version": str(getattr(bn, "__version__", "")),
            "runtime_protocol_version": runtime_manifest.get("protocol_version"),
            "target_device_id": device_id,
            "robot_attachments": robot_attachments,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            **deployment_owner,
        },
    }
    if req.deployment_id:
        payload["deployment_id"] = req.deployment_id
    try:
        report(36, "Connecting to the target Runtime")
        client = _runtime_client_or_404(device_id)
        package_specs = _workflow_target_package_specs(workflow)
        if package_specs:
            report(
                42,
                f"Synchronizing {len(package_specs)} required workflow "
                f"package{'s' if len(package_specs) != 1 else ''}",
            )
            client.sync_packages(package_specs)
            report(62, "Verifying synchronized packages and workflow nodes")
            synced_manifest = client.manifest()
            synced_packages = {
                str(item.get("name")): str(item.get("version") or "")
                for item in (synced_manifest.get("packages") or [])
                if isinstance(item, dict) and item.get("name")
            }
            missing_after_sync = sorted(
                set(_workflow_target_packages(workflow)) - set(synced_packages)
            )
            outdated_after_sync = sorted({
                item["name"]
                for item in package_specs
                if (
                    item.get("version")
                    and synced_packages.get(item["name"]) != item["version"]
                )
            })
            synced_node_types = {
                str(item)
                for item in (synced_manifest.get("node_types") or [])
                if isinstance(item, str)
            }
            missing_nodes_after_sync = sorted(
                workflow_node_types(workflow) - synced_node_types
            )
            if missing_after_sync or outdated_after_sync or missing_nodes_after_sync:
                details = []
                if missing_after_sync:
                    details.append("packages: " + ", ".join(missing_after_sync))
                if outdated_after_sync:
                    details.append(
                        "package versions: " + ", ".join(outdated_after_sync)
                    )
                if missing_nodes_after_sync:
                    details.append("nodes: " + ", ".join(missing_nodes_after_sync))
                raise HTTPException(
                    409,
                    "Target package synchronization did not provide " + "; ".join(details),
                )
        else:
            report(62, "No workflow package updates are required")
        report(70, "Uploading the workflow bundle")
        deployment = client.stage_deployment(payload)
        report(80, "Workflow stored on the target Runtime")
        superseded_deployments: list[str] = []
        cleanup_warnings: list[str] = []
        if req.start:
            report(84, "Checking robot safety and replacing the previous workflow")
            (
                deployment,
                superseded_deployments,
                cleanup_warnings,
            ) = _start_replacing_device_deployment(
                device_id,
                client,
                str(deployment["id"]),
            )
            report(98, "Workflow started; confirming replacement cleanup")
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    result = {
        "deployment": deployment,
        "workflow_hash": current_hash,
        "started": bool(req.start),
        "superseded_deployments": superseded_deployments,
        "cleanup_warnings": cleanup_warnings,
    }
    report(100, "Workflow sent and started" if req.start else "Workflow sent to robot")
    return result


@app.post("/devices/{device_id}/deployments")
def stage_device_deployment(device_id: str, req: RemoteDeployReq):
    return _stage_device_deployment_payload(device_id, req)


@app.post("/devices/{device_id}/deployments-stream")
def stream_device_deployment(device_id: str, req: RemoteDeployReq):
    return _lifecycle_stream(
        lambda report: _stage_device_deployment_payload(device_id, req, report)
    )


@app.get("/devices/{device_id}/deployments/{deployment_id}")
def get_device_deployment(device_id: str, deployment_id: str):
    return _require_targeted_deployment(device_id, deployment_id)


@app.get("/devices/{device_id}/deployments/{deployment_id}/workflow")
def get_device_deployment_workflow(
    device_id: str,
    deployment_id: str,
    revision: str = "",
):
    _require_targeted_deployment(device_id, deployment_id)
    try:
        return _runtime_client_or_404(device_id).deployment_workflow(
            deployment_id,
            revision=revision,
        )
    except DeviceRegistryError as exc:
        detail = str(exc)
        if "HTTP 404" in detail or "not found" in detail.casefold():
            raise HTTPException(
                409,
                "This Runtime cannot return deployed graphs yet. Update "
                "blacknode-runtime to 0.3.13 or newer, then try again.",
            ) from exc
        raise HTTPException(502, detail) from exc


@app.post("/devices/{device_id}/deployments/{deployment_id}/motion")
def control_device_deployment_motion(
    device_id: str,
    deployment_id: str,
    req: RemoteMotionControlReq,
):
    deployment = _require_targeted_deployment(device_id, deployment_id)
    if str(deployment.get("state") or "") != "running":
        raise HTTPException(409, "Start the deployment before arming it.")
    try:
        result = _runtime_client_or_404(device_id).set_deployment_motion_armed(
            deployment_id,
            armed=req.armed,
        )
    except DeviceRegistryError as exc:
        detail = str(exc)
        if "HTTP 404" in detail or "not found" in detail.casefold():
            raise HTTPException(
                409,
                "This Runtime cannot control a deployed armed gate yet. Update "
                "blacknode-runtime to 0.3.13 or newer and stage the workflow again.",
            ) from exc
        raise HTTPException(502, detail) from exc
    return result


@app.post("/devices/{device_id}/deployments/{deployment_id}/mapping/save")
def save_device_deployment_map(device_id: str, deployment_id: str):
    deployment = _require_targeted_deployment(device_id, deployment_id)
    if str(deployment.get("state") or "") != "running":
        raise HTTPException(409, "Start mapping before saving the map.")
    if int(deployment.get("mapping_control_count") or 0) != 1:
        raise HTTPException(409, "This deployment does not contain one MapEnvironment control.")
    try:
        return _runtime_client_or_404(device_id).save_deployment_map(deployment_id)
    except DeviceRegistryError as exc:
        detail = str(exc)
        if "HTTP 404" in detail or "not found" in detail.casefold():
            raise HTTPException(
                409,
                "This Runtime cannot save deployed maps yet. Update blacknode-runtime "
                "to 0.4.13 or newer and stage the mapping workflow again.",
            ) from exc
        raise HTTPException(502, detail) from exc


@app.get("/devices/{device_id}/deployments/{deployment_id}/mapping/snapshot")
def get_device_deployment_map_snapshot(device_id: str, deployment_id: str):
    deployment = _require_targeted_deployment(device_id, deployment_id)
    if str(deployment.get("state") or "") != "running":
        raise HTTPException(409, "Start mapping to view the live occupancy map.")
    if int(deployment.get("mapping_control_count") or 0) != 1:
        raise HTTPException(409, "This deployment does not contain one MapEnvironment control.")
    topic = str(deployment.get("mapping_topic") or "/map").strip()
    stream_id = ("map-" + re.sub(r"[^a-z0-9-]+", "-", deployment_id.lower()))[:64].rstrip("-")
    try:
        client = _runtime_client_or_404(device_id)
        response = client.ros2_topic_status(stream_id)
        current_outputs = (
            response.get("outputs")
            if isinstance(response.get("outputs"), dict)
            else {}
        )
        current_status = (
            current_outputs.get("status")
            if isinstance(current_outputs.get("status"), dict)
            else {}
        )
        if not current_status.get("worker_alive"):
            response = client.start_ros2_topic(
                stream_id,
                {
                    "topic": topic,
                    "message_type": "nav_msgs/msg/OccupancyGrid",
                    "node_name": "blacknode_mapping_view",
                    "history": 1,
                    "timeout": 3.0,
                    "stale_after_seconds": 5.0,
                    "qos": "transient_local",
                },
            )
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    outputs = response.get("outputs") if isinstance(response.get("outputs"), dict) else {}
    return {
        "deployment_id": deployment_id,
        "topic": topic,
        "message": outputs.get("message") if isinstance(outputs.get("message"), dict) else {},
        "status": outputs.get("status") if isinstance(outputs.get("status"), dict) else {},
        "report": str(outputs.get("report") or ""),
    }


@app.get("/devices/{device_id}/ros2-diagnostics")
def get_device_ros2_diagnostics(device_id: str):
    try:
        _device_registry.get_public(device_id)
        return _runtime_client_or_404(device_id).ros2_diagnostics()
    except DeviceRegistryError as exc:
        detail = str(exc)
        if "HTTP 404" in detail or "not found" in detail.casefold():
            raise HTTPException(
                409,
                "This Runtime does not expose ROS 2 diagnostics yet. Update "
                "blacknode-runtime to 0.3.13 or newer.",
            ) from exc
        raise HTTPException(502, detail) from exc


@app.post("/devices/{device_id}/deployments/{deployment_id}/start")
def start_device_deployment(device_id: str, deployment_id: str):
    _require_targeted_deployment(device_id, deployment_id)
    try:
        deployment, superseded, cleanup_warnings = (
            _start_replacing_device_deployment(
                device_id,
                _runtime_client_or_404(device_id),
                deployment_id,
            )
        )
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {
        **deployment,
        "superseded_deployments": superseded,
        "cleanup_warnings": cleanup_warnings,
    }


@app.post("/devices/{device_id}/deployments/{deployment_id}/stop")
def stop_device_deployment(device_id: str, deployment_id: str):
    current = _require_targeted_deployment(device_id, deployment_id)
    try:
        runtime_client = _runtime_client_or_404(device_id)
        deployment = runtime_client.stop_deployment(deployment_id)
        if int(current.get("mapping_control_count") or 0) == 1:
            stream_id = (
                "map-" + re.sub(r"[^a-z0-9-]+", "-", deployment_id.lower())
            )[:64].rstrip("-")
            try:
                runtime_client.stop_ros2_topic(stream_id)
            except DeviceRegistryError:
                pass
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc
    remaining = _target_deployment_records(
        runtime_client,
        device_id,
        exclude_id=deployment_id,
    )
    if not any(
        str(item.get("state") or "") == "running"
        for item in remaining
    ):
        _set_device_deployment_lease(device_id, leased=False)
    return deployment


@app.post("/devices/{device_id}/deployments/{deployment_id}/rollback")
def rollback_device_deployment(
    device_id: str,
    deployment_id: str,
    req: RemoteRollbackReq,
):
    _require_targeted_deployment(device_id, deployment_id)
    try:
        runtime_client = _runtime_client_or_404(device_id)
        deployment = runtime_client.rollback_deployment(
            deployment_id,
            start=False,
        )
        if req.start:
            deployment, superseded, cleanup_warnings = (
                _start_replacing_device_deployment(
                    device_id,
                    runtime_client,
                    deployment_id,
                )
            )
            return {
                **deployment,
                "superseded_deployments": superseded,
                "cleanup_warnings": cleanup_warnings,
            }
        remaining = _target_deployment_records(
            runtime_client,
            device_id,
            exclude_id=deployment_id,
        )
        if not any(
            str(item.get("state") or "") == "running"
            for item in remaining
        ):
            _set_device_deployment_lease(device_id, leased=False)
        return deployment
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/devices/{device_id}/deployments/{deployment_id}/logs")
def get_device_deployment_logs(
    device_id: str,
    deployment_id: str,
    limit: int = 20000,
):
    _require_targeted_deployment(device_id, deployment_id)
    try:
        return _runtime_client_or_404(device_id).deployment_logs(
            deployment_id,
            limit=limit,
        )
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/devices/{device_id}/deployments/{deployment_id}")
def delete_device_deployment(device_id: str, deployment_id: str):
    _require_targeted_deployment(device_id, deployment_id)
    try:
        return _runtime_client_or_404(device_id).delete_deployment(deployment_id)
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/devices/{device_id}/rpc")
def call_device_rpc(device_id: str, req: DeviceRpcReq):
    method = req.method.strip()
    if not method:
        raise HTTPException(400, "RPC method is required")
    payload = {
        "jsonrpc": "2.0",
        "id": req.id,
        "method": method,
        "params": req.params,
    }
    try:
        return _paired_device_client(device_id).rpc(payload)
    except DeviceRegistryError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/devices/{device_id}/release-torque")
def release_device_torque(device_id: str):
    status = _deployment_aware_device_status(device_id)
    if status.get("deployment_lease") or status.get("running_deployment"):
        raise HTTPException(
            409,
            "Stop the robot deployment before releasing physical torque.",
        )
    if status.get("paused"):
        raise HTTPException(
            409,
            "Resume the robot hardware monitor before releasing physical torque.",
        )
    if status.get("torque_enabled") is False:
        return {"ok": True, "status": status, "already_released": True}
    result = _paired_device_client(device_id).rpc({
        "jsonrpc": "2.0",
        "id": f"release-torque-{device_id}",
        "method": "disable_torque",
        "params": {},
    })
    _raise_rpc_error(result, action="release physical torque for")
    verified = _paired_device_client(device_id).status()
    if verified.get("torque_enabled") is True:
        raise HTTPException(
            409,
            "The Hardware service accepted the request but still reports physical torque on.",
        )
    verification_warning = ""
    if verified.get("torque_enabled") is None:
        verification_warning = str(
            verified.get("torque_report_error")
            or (
                "Robot Hardware sent the torque-off command successfully, but could "
                "not read every servo torque-enable register to verify the result."
            )
        )
    return {
        "ok": True,
        "status": verified,
        "already_released": False,
        "verification_warning": verification_warning,
    }


@app.delete("/devices/{device_id}")
def delete_device(device_id: str):
    try:
        deleted = _device_registry.delete(device_id)
    except DeviceRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, "Device not found")
    return {"ok": True, "id": device_id}


@app.get("/deployments")
def list_deployments():
    return {"deployments": _deployment_store.list()}


@app.post("/deployments")
def create_deployment(req: DeployReq):
    workflow = req.workflow if isinstance(req.workflow, dict) else _workflow_payload(
        req.name or "Deployed graph",
        metadata={"source": "deploy"},
    )
    # This is the button the editor's Deploy uses, and it autostarts. A
    # deployment runs its own copy of the graph, so if the editor is still live
    # both open the camera and the deployment lands on the next device. Stop the
    # editor's live runtime first and wait for it to release the hardware; the
    # camera stop blocks until the process is gone, so the device is free before
    # the deployment claims it. The canvas graph is left untouched.
    if req.autostart:
        try:
            _stop_active_cook()
            _stop_runtime_services()
        except Exception:
            pass
    try:
        record = _deployment_store.create(
            workflow,
            name=req.name,
            target=req.target,
            autostart=req.autostart,
        )
    except DeploymentError as exc:
        # The graph is fine as a document but cannot be deployed as-is
        # (no inferable entrypoint, unsupported target). That is a request
        # problem the user can fix in the editor, not a server fault.
        raise HTTPException(400, str(exc)) from exc
    return record


@app.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: str):
    record = _deployment_store.get(deployment_id)
    if record is None:
        raise HTTPException(404, "Deployment not found")
    return record


@app.post("/deployments/{deployment_id}/start")
def start_deployment(deployment_id: str):
    # A deployment runs the same graph as its own process. If the editor is
    # still live, two copies fight over the camera and the second lands on the
    # "next available" device. Hand the hardware over: stop the editor's live
    # runtime first, then deploy. The graph on the canvas is untouched.
    try:
        _stop_active_cook()
        _stop_runtime_services()
    except Exception:
        pass
    try:
        return _deployment_store.start(deployment_id)
    except DeploymentError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/deployments/{deployment_id}/stop")
def stop_deployment(deployment_id: str):
    try:
        return _deployment_store.stop(deployment_id)
    except DeploymentError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/yolo-models")
def list_yolo_models():
    """Built-in YOLO weights plus any custom model dropped in .blacknode/models,
    so DetectionYolo can offer a pick-by-name menu instead of a typed path."""
    from blacknode.vision_models import BUILTIN_MODELS, custom_models, models_dir
    custom = custom_models()
    return {
        "ok": True,
        "builtin": list(BUILTIN_MODELS),
        "custom": custom,
        "models_dir": str(models_dir()),
    }


@app.get("/cameras")
def list_cameras(max_devices: int = 8):
    """Discovered local cameras, so the editor can offer a pick-by-name menu.

    Runs the camera discovery node, which only returns devices that actually
    open and deliver a frame - so a virtual camera with no source (a common
    index-0 trap) is filtered out and you pick the real webcam by name instead
    of guessing the index.
    """
    fn = _NODE_REGISTRY.get("CameraDiscovery")
    if fn is None:
        return {"ok": False, "cameras": [], "report": "camera discovery is not installed"}
    try:
        result = fn({"backend": "auto", "max_devices": max(1, min(32, int(max_devices)))})
    except Exception as exc:  # pragma: no cover - discovery is best-effort
        return {"ok": False, "cameras": [], "report": f"{type(exc).__name__}: {exc}"}
    cameras = [
        {
            "index": item.get("index"),
            "label": item.get("label") or f"Camera {item.get('index')}",
            "device": item.get("device"),
            "width": item.get("width"),
            "height": item.get("height"),
        }
        for item in (result.get("devices") or [])
        if isinstance(item, dict)
    ]
    return {"ok": bool(cameras), "cameras": cameras, "report": result.get("report", "")}


@app.post("/deployments/{deployment_id}/export")
def export_deployment(deployment_id: str):
    try:
        path = _deployment_store.export(deployment_id)
    except DeploymentError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True, "id": deployment_id, "path": str(path)}


@app.delete("/deployments/{deployment_id}")
def delete_deployment(deployment_id: str):
    if not _deployment_store.delete(deployment_id):
        raise HTTPException(404, "Deployment not found")
    return {"ok": True, "id": deployment_id}


@app.get("/deployments/{deployment_id}/logs")
def deployment_logs(deployment_id: str, limit_bytes: int = 20000):
    if _deployment_store.get(deployment_id) is None:
        raise HTTPException(404, "Deployment not found")
    return {
        "id": deployment_id,
        "logs": _deployment_store.logs(deployment_id, limit_bytes=max(512, min(limit_bytes, 200000))),
    }


@app.get("/runs")
def list_runs(limit: int = 50):
    return {"runs": _run_store.list_runs(limit=max(1, min(limit, 500)))}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    record = _run_store.get_run(run_id)
    if record is None:
        raise HTTPException(404, "Run not found")
    return record


@app.delete("/runs/{run_id}")
def delete_run(run_id: str):
    if not _run_store.delete_run(run_id):
        raise HTTPException(404, "Run not found")
    return {"ok": True, "run_id": run_id}


@app.delete("/runs")
def clear_runs():
    return {"ok": True, "removed": _run_store.clear()}


@app.post("/sync/runs")
def sync_begin_run(req: SyncRunReq):
    workflow = req.workflow
    if isinstance(workflow, dict):
        _ensure_workflow_header(workflow)
        _enqueue_editor_action(
            "open_workflow_tab",
            {
                "name": str(workflow.get("name") or "Python Live Sync"),
                "workflow": workflow,
                "organize": False,
            },
        )
    run_id = _run_store.begin(
        node_id=req.node_id,
        port=req.port,
        node_type=req.node_type,
        workflow=workflow,
    )
    record = _run_store.snapshot(run_id)
    if record is not None:
        _enqueue_sync_run_update(record, playing=True)
    return {"ok": True, "run_id": run_id}


@app.post("/sync/events")
def sync_record_event(req: SyncEventReq):
    _run_store.record_event(req.run_id, req.event)
    record = _run_store.snapshot(req.run_id)
    if record is None:
        raise HTTPException(404, "Run not found")
    _enqueue_sync_run_update(record, playing=True)
    events = record.get("events") or []
    return {"ok": True, "run_id": req.run_id, "cursor": len(events) - 1}


@app.post("/sync/runs/{run_id}/finish")
def sync_finish_run(run_id: str, req: SyncFinishReq):
    if req.status == "error" or req.error:
        record = _run_store.finalize_error(run_id, error=req.error or "External Python run failed")
    else:
        record = _run_store.finalize_success(run_id, value=req.value)
    if record is None:
        raise HTTPException(404, "Run not found")
    _enqueue_sync_run_update(record, playing=False)
    return {"ok": True, "run": record}


@app.get("/sync/runs/{run_id}")
def sync_get_run(run_id: str):
    record = _run_store.snapshot(run_id)
    if record is None:
        raise HTTPException(404, "Run not found")
    return record


@app.get("/mcp/status")
def mcp_status():
    import importlib.util
    import shutil
    mcp_installed = importlib.util.find_spec("mcp") is not None
    cli_path = shutil.which("blacknode")
    return {
        "mcp_installed": mcp_installed,
        "blacknode_cli": cli_path,
        "install_command": "pip install -e \".[mcp]\"",
        "launch_command": "blacknode mcp",
    }


@app.post("/editor/actions/workflow-tab")
def queue_new_workflow_tab(req: NewWorkflowTabReq):
    name = req.name.strip() or "Untitled"
    action = _enqueue_editor_action("new_workflow_tab", {"name": name})
    return {"ok": True, "action": action}


@app.post("/editor/actions/open-workflow-tab")
def queue_open_workflow_tab(req: OpenWorkflowTabReq):
    workflow = req.workflow
    _ensure_workflow_header(workflow)
    report = validate_bn_workflow(workflow)
    if not report.ok:
        raise HTTPException(400, report.to_dict())
    name = (req.name or workflow.get("name") or "Untitled").strip() or "Untitled"
    action = _enqueue_editor_action("open_workflow_tab", {
        "name": name,
        "workflow": workflow,
        "organize": req.organize,
    })
    return {"ok": True, "action": action}


@app.post("/editor/actions/cook-node")
def queue_cook_node(req: CookEditorNodeReq):
    node_id = req.node_id.strip()
    port = req.port.strip() or "value"
    if node_id not in _session.node_meta:
        raise HTTPException(404, f"Node '{node_id}' not found")
    action = _enqueue_editor_action("cook_node", {
        "node_id": node_id,
        "port": port,
    })
    return {"ok": True, "action": action}


@app.post("/editor/actions/load-saved-workflow-tab")
def queue_load_saved_workflow_tab(req: LoadSavedWorkflowTabReq):
    slug = req.slug.strip()
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    name = (req.name or data.get("name") or slug).strip() or slug
    action = _enqueue_editor_action("load_saved_workflow_tab", {
        "slug": slug,
        "name": name,
        "organize": req.organize,
    })
    return {"ok": True, "action": action}


@app.post("/editor/actions/organize-graph")
def queue_organize_graph():
    action = _enqueue_editor_action("organize_graph")
    return {"ok": True, "action": action}


@app.post("/editor/actions/rename-tab")
def queue_rename_tab(req: RenameEditorTabReq):
    name = req.name.strip() or "Untitled"
    action = _enqueue_editor_action("rename_tab", {"name": name})
    return {"ok": True, "action": action}


@app.post("/editor/actions/close-tab")
def queue_close_tab():
    action = _enqueue_editor_action("close_tab")
    return {"ok": True, "action": action}


@app.get("/editor/actions")
def consume_editor_actions():
    with _editor_action_lock:
        actions = list(_editor_action_queue)
        _editor_action_queue.clear()
    return {"actions": actions}


@app.get("/learned-nodes")
def list_learned_nodes():
    return mcp_tools.list_learned_nodes()


@app.get("/learned-nodes/{name}/source")
def get_learned_node_source(name: str):
    result = mcp_tools.get_learned_node_source(name)
    if result.get("status") == "not_found":
        raise HTTPException(404, f"Learned node '{name}' not found")
    if result.get("status") == "rejected":
        raise HTTPException(400, result.get("reason", "Invalid learned node name"))
    return result


@app.delete("/learned-nodes/{name}")
def delete_learned_node(name: str):
    result = mcp_tools.delete_learned_node(name, confirm=True, notify_editor=False)
    if result.get("status") == "not_found":
        raise HTTPException(404, f"Learned node '{name}' not found")
    if result.get("status") == "rejected":
        raise HTTPException(400, result.get("reason", "Could not delete learned node"))
    _broadcast_learned_node_event("learned_node_deleted", name)
    return result


@app.post("/learned-nodes/{name}/promote")
def promote_learned_node(name: str):
    result = mcp_tools.promote_learned_node(name, notify_editor=False)
    if result.get("status") == "not_found":
        raise HTTPException(404, f"Learned node '{name}' not found")
    if result.get("status") == "rejected":
        raise HTTPException(400, result.get("reason", "Could not promote learned node"))
    _broadcast_learned_node_event("learned_node_deleted", name)
    return result


@app.get("/learned-nodes/events")
def learned_nodes_events():
    def event_generator():
        subscriber: queue.Queue = queue.Queue()
        with _learned_node_event_lock:
            _learned_node_event_subscribers.append(subscriber)
        try:
            while True:
                try:
                    event = subscriber.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            with _learned_node_event_lock:
                if subscriber in _learned_node_event_subscribers:
                    _learned_node_event_subscribers.remove(subscriber)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/internal/learned-node-added")
def internal_learned_node_added(req: LearnedNodeEventReq):
    name = req.name.strip()
    try:
        learned_registry.register_one(name)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    event = _broadcast_learned_node_event("learned_node_added", name)
    return {"ok": True, "event": event}


@app.post("/internal/learned-node-deleted")
def internal_learned_node_deleted(req: LearnedNodeEventReq):
    name = req.name.strip()
    learned_registry.unregister_one(name)
    event = _broadcast_learned_node_event("learned_node_deleted", name)
    return {"ok": True, "event": event}


def _subgraph_cook_trace(
    subnet_id: str,
    node_id: str,
    port: str,
    stop_event: threading.Event | None = None,
    targets: list[tuple[str, str]] | None = None,
    run_mode: str = "once",
):
    import traceback

    logger = _CookStreamLogger()
    resolved_targets = targets or [(node_id, port)]

    def drain_logger():
        for event in logger.drain():
            yield _json_line(event)

    try:
        if subnet_id not in _session.node_meta:
            raise KeyError(f"Subnet node {subnet_id} not found")
        subgraph = _session.node_meta[subnet_id].get("subgraph", {})
        inner_meta = subgraph.get("node_meta", {})
        inner_edges = subgraph.get("edges", [])
        for target_id, _target_port in resolved_targets:
            if target_id not in inner_meta:
                raise KeyError(f"Node {target_id} not found inside subnet")

        inner = bn.Graph.__new__(bn.Graph)
        inner._edges = inner_edges
        inner._cache = {}
        inner._dirty = set(inner_meta.keys())
        inner._nodes = {}
        inner._runtime_context = dict(
            getattr(_session.graph, "_runtime_context", {})
        )
        for nid, meta in inner_meta.items():
            entry = {"type": meta["type"], "params": dict(meta.get("params", {}))}
            if "subgraph" in meta:
                entry["subgraph"] = meta["subgraph"]
            inner._nodes[nid] = entry

        emitted_outer_cached: set[tuple[str, str]] = set()

        def emit_outer_cached_success(current_id: str, current_port: str):
            cache_key = (current_id, current_port)
            if cache_key in emitted_outer_cached or cache_key not in _session.graph._cache:
                return
            emitted_outer_cached.add(cache_key)
            yield _node_event({
                "type": "success",
                "node_id": current_id,
                "port": current_port,
                "value": _session.graph._cache[cache_key],
                "cached": True,
            })

        def emit_outer_cached_upstream(current_id: str, visiting: set[str] | None = None):
            if visiting is None:
                visiting = set()
            if current_id in visiting:
                return
            visiting.add(current_id)
            for edge in _session.graph._edges:
                if edge["to"] == current_id:
                    yield from emit_outer_cached_upstream(edge["from"], visiting)
                    yield from emit_outer_cached_success(edge["from"], edge["from_port"])
            visiting.remove(current_id)

        def cook_outer_one(current_id: str, current_port: str):
            _raise_if_stopped(stop_event)
            if current_id not in _session.node_meta:
                raise KeyError(f"Node {current_id} not found")
            if current_id not in _session.graph._nodes:
                raise KeyError(f"Node {current_id} missing from graph")

            cache_key = (current_id, current_port)
            if current_id not in _session.graph._dirty and cache_key in _session.graph._cache:
                value = _session.graph._cache[cache_key]
                yield from emit_outer_cached_upstream(current_id)
                yield from emit_outer_cached_success(current_id, current_port)
                return value

            node_def = _session.graph._nodes[current_id]
            ctx = dict(node_def["params"])

            for edge in _session.graph._edges:
                if edge["to"] == current_id:
                    val = yield from cook_outer_one(edge["from"], edge["from_port"])
                    _raise_if_stopped(stop_event)
                    ctx[edge["to_port"]] = val

            try:
                yield _json_line({"type": "start", "node_id": current_id, "port": current_port})
                if node_def["type"] in {"Subnet", "VisualAgentLoop"}:
                    result = _session.graph._cook_subnet(current_id, current_port, ctx)
                else:
                    fn = _NODE_REGISTRY[node_def["type"]]
                    ctx.update(getattr(_session.graph, "_runtime_context", {}))
                    ctx["__graph__"] = _session.graph
                    ctx["__node_id__"] = current_id
                    ctx["__run_logger__"] = logger
                    ctx["__run_mode__"] = "live" if run_mode == "live" else "once"
                    try:
                        result = fn(ctx)
                        if isinstance(result, dict):
                            result = bn_fill_frame_stream(result, list(getattr(fn, "_bn_outputs", []) or []))
                    finally:
                        yield from drain_logger()
                    if not isinstance(result, dict):
                        result = {"output": result}
                _raise_if_stopped(stop_event)

                for key, value in result.items():
                    _session.graph._cache[(current_id, key)] = value
                _session.graph._dirty.discard(current_id)

                if cache_key not in _session.graph._cache:
                    raise KeyError(
                        f"Node '{node_def['type']}' did not produce port '{current_port}'. "
                        f"Available: {[key for (nid, key) in _session.graph._cache if nid == current_id]}"
                    )

                value = _session.graph._cache[cache_key]
                yield _node_event({
                    "type": "success",
                    "node_id": current_id,
                    "port": current_port,
                    "value": value,
                    "outputs": _event_outputs(result),
                })
                return value
            except Exception as exc:
                yield from drain_logger()
                error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
                yield _node_event({
                    "type": "error",
                    "node_id": current_id,
                    "port": current_port,
                    "error": error,
                })
                raise

        outer_ctx = dict(_session.graph._nodes.get(subnet_id, {}).get("params", {}))
        for edge in _session.graph._edges:
            if edge["to"] == subnet_id:
                outer_ctx[edge["to_port"]] = yield from cook_outer_one(edge["from"], edge["from_port"])

        for nid, meta in inner_meta.items():
            if meta["type"] == "SubnetInput":
                injected: dict[str, Any] = {}
                for out_port in meta.get("outputs", []):
                    injected[out_port] = outer_ctx.get(out_port)
                    inner._cache[(nid, out_port)] = injected[out_port]
                inner._dirty.discard(nid)
                _record_node_success(inner_meta, nid, "inputs", injected)
                yield _json_line({
                    "type": "success",
                    "node_id": nid,
                    "port": "inputs",
                    "value": injected,
                    "outputs": _event_outputs(injected),
                })

        emitted_inner_cached: set[tuple[str, str]] = set()

        def emit_inner_cached_success(current_id: str, current_port: str):
            cache_key = (current_id, current_port)
            if cache_key in emitted_inner_cached or cache_key not in inner._cache:
                return
            emitted_inner_cached.add(cache_key)
            value = inner._cache[cache_key]
            _record_node_success(
                inner_meta,
                current_id,
                current_port,
                _node_cached_outputs(inner._cache, current_id, current_port, value),
            )
            yield _json_line({
                "type": "success",
                "node_id": current_id,
                "port": current_port,
                "value": value,
                "cached": True,
            })

        def emit_inner_cached_upstream(current_id: str, visiting: set[str] | None = None):
            if visiting is None:
                visiting = set()
            if current_id in visiting:
                return
            visiting.add(current_id)
            for edge in inner._edges:
                if edge["to"] == current_id:
                    yield from emit_inner_cached_upstream(edge["from"], visiting)
                    yield from emit_inner_cached_success(edge["from"], edge["from_port"])
            visiting.remove(current_id)

        def cook_one(current_id: str, current_port: str):
            _raise_if_stopped(stop_event)
            if current_id not in inner_meta:
                raise KeyError(f"Node {current_id} not found inside subnet")
            if current_id not in inner._nodes:
                raise KeyError(f"Node {current_id} missing from inner graph")

            cache_key = (current_id, current_port)
            if current_id not in inner._dirty and cache_key in inner._cache:
                value = inner._cache[cache_key]
                yield from emit_inner_cached_upstream(current_id)
                yield from emit_inner_cached_success(current_id, current_port)
                _record_node_success(
                    inner_meta,
                    current_id,
                    current_port,
                    _node_cached_outputs(inner._cache, current_id, current_port, value),
                )
                return value

            node_def = inner._nodes[current_id]
            ctx = dict(node_def["params"])

            for edge in inner._edges:
                if edge["to"] == current_id:
                    val = yield from cook_one(edge["from"], edge["from_port"])
                    _raise_if_stopped(stop_event)
                    ctx[edge["to_port"]] = val

            try:
                node_type = node_def["type"]
                yield _json_line({"type": "start", "node_id": current_id, "port": current_port, "node_type": node_type})
                if node_def["type"] in {"Subnet", "VisualAgentLoop"}:
                    result = inner._cook_subnet(current_id, current_port, ctx)
                else:
                    fn = _NODE_REGISTRY[node_def["type"]]
                    ctx.update(getattr(inner, "_runtime_context", {}))
                    ctx["__graph__"] = inner
                    ctx["__node_id__"] = current_id
                    result = fn(ctx)
                    if isinstance(result, dict):
                        result = bn_fill_frame_stream(result, list(getattr(fn, "_bn_outputs", []) or []))
                    if not isinstance(result, dict):
                        result = {"output": result}
                _raise_if_stopped(stop_event)

                for key, value in result.items():
                    inner._cache[(current_id, key)] = value
                inner._dirty.discard(current_id)

                if cache_key not in inner._cache:
                    raise KeyError(
                        f"Node '{node_def['type']}' did not produce port '{current_port}'. "
                        f"Available: {[key for (nid, key) in inner._cache if nid == current_id]}"
                    )

                value = inner._cache[cache_key]
                _record_node_success(
                    inner_meta,
                    current_id,
                    current_port,
                    result if len(result) > 1 else value,
                )
                yield _json_line({
                    "type": "success",
                    "node_id": current_id,
                    "port": current_port,
                    "value": value,
                    "outputs": _event_outputs(result),
                })
                return value
            except Exception as exc:
                error = str(exc) if exc.__class__.__name__ == "ProviderConfigError" else traceback.format_exc()
                _record_node_error(inner_meta, current_id, current_port, error)
                yield _json_line({
                    "type": "error",
                    "node_id": current_id,
                    "port": current_port,
                    "error": error,
                })
                raise

        yield from _cook_target_batch_trace(cook_one, resolved_targets)
    except _CookStopped:
        yield _json_line({"type": "done", "port": "leaves" if len(resolved_targets) > 1 else port, "error": "stopped"})
    except Exception:
        yield _json_line({"type": "done", "port": "leaves" if len(resolved_targets) > 1 else port, "error": traceback.format_exc()})


@app.post("/nodes/{subnet_id}/cook-stream")
def cook_subgraph_stream(subnet_id: str, req: CookReq):
    stop_event = _prepare_cook()
    _begin_fresh_cook()
    return StreamingResponse(
        _stream_in_worker(
            lambda: _subgraph_cook_trace(subnet_id, req.node_id, req.port, stop_event, run_mode=req.run_mode),
            stop_event,
            req.port,
        ),
        media_type="application/x-ndjson",
    )


@app.post("/nodes/{subnet_id}/cook-graph-stream")
def cook_subgraph_graph_stream(subnet_id: str, req: CookGraphReq):
    targets = _graph_cook_targets(req)
    stop_event = _prepare_cook()
    _begin_fresh_cook()
    first_node, first_port = targets[0]
    return StreamingResponse(
        _stream_in_worker(
            lambda: _subgraph_cook_trace(
                subnet_id,
                first_node,
                first_port,
                stop_event,
                targets=targets,
                run_mode=req.run_mode,
            ),
            stop_event,
            "leaves",
        ),
        media_type="application/x-ndjson",
    )


@app.get("/settings/api-keys")
def get_api_keys():
    return _api_keys


@app.get("/settings/api-key-status")
def get_api_key_status():
    """Return credential availability without exposing secret values."""
    return _api_key_status()


@app.post("/settings/api-key")
def set_api_key(req: SetApiKeyReq):
    env_var = _PROVIDER_ENV.get(req.provider)
    if env_var:
        if req.key:
            if not os.environ.get(env_var) or env_var in _injected_api_key_envs:
                os.environ[env_var] = req.key
                _injected_api_key_envs.add(env_var)
        elif env_var in _injected_api_key_envs:
            del os.environ[env_var]
            _injected_api_key_envs.discard(env_var)
    changed = _api_keys.get(req.provider) != req.key
    _api_keys[req.provider] = req.key
    _save_api_keys()
    # If this is a bot token and that driver is running, restart it so the new
    # token takes effect (a running bot reads its token only at startup).
    restarted = _restart_running_driver_for(req.provider) if changed else None
    return {
        "ok": True,
        "restarted": restarted,
        "credential": _api_key_status().get(req.provider),
    }


@app.get("/settings/onboarding")
def get_onboarding_state():
    return dict(_onboarding_state)


@app.post("/settings/onboarding")
def set_onboarding_state(req: SetOnboardingReq):
    _onboarding_state["package_welcome_seen"] = req.package_welcome_seen
    _save_onboarding_state()
    return {"ok": True, **_onboarding_state}


# ── Driver status bridge ──────────────────────────────────────────────────
# Running drivers (blacknode slack/telegram, separate processes) POST heartbeats
# here so the canvas can show a truthful live/offline badge on trigger nodes.
_driver_status: dict[str, dict] = {}
_DRIVER_STALE_S = 15.0  # no heartbeat within this window → considered offline


class DriverStatusReq(BaseModel):
    name: str
    workflow: str = ""
    label: str = ""
    state: str = "listening"
    processed: int = 0
    pid: int = 0
    ts: float = 0.0


@app.post("/drivers/status")
def post_driver_status(req: DriverStatusReq):
    _driver_status[req.name] = {
        "name": req.name,
        "workflow": req.workflow,
        "label": req.label,
        "state": req.state,
        "processed": req.processed,
        "pid": req.pid,
        "ts": req.ts,
        "received": time.time(),
    }
    return {"ok": True}


@app.get("/drivers/status")
def get_driver_status():
    now = time.time()
    out: dict[str, dict] = {}
    for name, st in _driver_status.items():
        live = (now - st.get("received", 0.0)) < _DRIVER_STALE_S
        out[name] = {**st, "live": live and st.get("state") != "stopped"}
    return out


@app.get("/drivers")
def list_drivers():
    """Readiness of each registered driver: ready / needs env / needs install."""
    return [driver_registry.driver_status(s) for s in driver_registry.list_drivers()]


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Driver subprocesses started from the editor (name -> Popen). Launched with the
# server's own interpreter, so they inherit the env the Install button uses.
_driver_procs: dict[str, "subprocess.Popen"] = {}
import collections
_driver_logs: dict[str, "collections.deque[str]"] = {}
_RUNTIME_KEYS = {"cookResult", "cookError", "cooking", "cookPort"}


def _drain_driver_output(name: str, proc: "subprocess.Popen") -> None:
    buf = _driver_logs[name]
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            buf.append(line.rstrip("\n"))
    except Exception:
        pass
    buf.append(f"[process exited, code {proc.poll()}]")


def _current_workflow() -> tuple[dict, dict | None]:
    """Build a runnable workflow from the live editor graph + pick an entrypoint."""
    node_meta = {
        nid: {k: v for k, v in meta.items() if k not in _RUNTIME_KEYS}
        for nid, meta in _session.node_meta.items()
    }
    entry = dict(_session.entrypoint) if _session.entrypoint else None
    if entry is None:
        for nid, meta in node_meta.items():
            if meta.get("type") in ("SlackReply", "TelegramReply"):
                entry = {"node_id": nid, "port": "text"}
                break
    if entry is None:
        for nid, meta in node_meta.items():
            if meta.get("type") == "Output":
                entry = {"node_id": nid, "port": "value"}
                break
    wf = {
        "kind": "blacknode.workflow",
        "schema_version": 1,
        "name": "Editor graph",
        "node_meta": node_meta,
        "edges": [dict(e) for e in _session.graph._edges],
        "entrypoint": entry,
    }
    return wf, entry


def _driver_running(name: str) -> bool:
    proc = _driver_procs.get(name)
    return proc is not None and proc.poll() is None


def _terminate_driver_process(proc: "subprocess.Popen") -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
        return
    except Exception:
        pass
    try:
        if os.name != "nt":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=3)
    except Exception:
        pass


def _stop_driver_proc(name: str) -> None:
    proc = _driver_procs.pop(name, None)
    if proc is not None:
        _terminate_driver_process(proc)
    _driver_status.pop(name, None)  # flip the badge offline immediately


def _spawn_driver(name: str) -> tuple[bool, str]:
    """Launch a driver subprocess on the current graph. Returns (ok, detail)."""
    spec = driver_registry.get_driver(name)
    if spec is None:
        return False, f"Unknown driver '{name}'"
    if not driver_registry.packages_installed(spec):
        return False, f"{spec.required_extra} is not installed — install it first."
    missing = driver_registry.missing_env(spec)
    if missing:
        return False, f"Set {', '.join(missing)} on the node first."
    if _driver_running(name):
        return True, "already running"
    wf, entry = _current_workflow()
    if entry is None:
        return False, "Graph needs a reply node (or Output) to drive."
    if not validate_bn_workflow(wf).ok:
        return False, "Graph is invalid; fix errors before starting."
    path = os.path.join(os.path.dirname(__file__), f".driver-{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2)
    # Tell the bot where the editor is, so each message cooks through live-sync
    # and the real run animates on the canvas (BLACKNODE_SYNC_URL), and so its
    # heartbeat reaches us (BLACKNODE_EDITOR_URL).
    env = dict(os.environ)
    env["BLACKNODE_SYNC_URL"] = "http://127.0.0.1:7777"
    env["BLACKNODE_EDITOR_URL"] = "http://127.0.0.1:7777"
    env["PYTHONIOENCODING"] = "utf-8"  # bot logs may contain unicode/emoji (Windows)
    process_group: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "blacknode.cli", name, path],
        cwd=_REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace", env=env,
        **process_group,
    )
    _driver_procs[name] = proc
    _driver_logs[name] = collections.deque(maxlen=300)
    threading.Thread(target=_drain_driver_output, args=(name, proc), daemon=True).start()
    return True, str(proc.pid)


def _restart_running_driver_for(provider: str) -> str | None:
    """If ``provider`` is a token for a *running* driver, restart it so the new
    value takes effect. Returns the restarted driver name, or None."""
    for spec in driver_registry.list_drivers():
        if provider in spec.required_env:
            if _driver_running(spec.name):
                _stop_driver_proc(spec.name)
                ok, _ = _spawn_driver(spec.name)
                return spec.name if ok else None
            return None
    return None


@app.post("/drivers/{name}/start")
def start_driver(name: str):
    ok, detail = _spawn_driver(name)
    if not ok:
        raise HTTPException(status_code=404 if detail.startswith("Unknown") else 400, detail=detail)
    return {"ok": True, "detail": detail}


@app.get("/drivers/{name}/logs")
def driver_logs(name: str):
    return {"running": _driver_running(name), "lines": list(_driver_logs.get(name, []))}


@app.get("/drivers/workflow")
def driver_current_workflow():
    """The live editor graph, so a running bot cooks the current shape per message."""
    wf, _ = _current_workflow()
    return wf


@app.post("/drivers/{name}/stop")
def stop_driver(name: str):
    _stop_driver_proc(name)
    return {"ok": True}


import atexit


@atexit.register
def _stop_all_drivers() -> None:
    for proc in list(_driver_procs.values()):
        _terminate_driver_process(proc)


@atexit.register
def _stop_all_runtime_services() -> None:
    """Stop streams and workers on the way out.

    Helper processes are spawned detached so a cook can end without killing
    them, which also means closing Blacknode used to leave every camera server
    running - holding the device, the port, and serving stale frames.
    """
    try:
        _stop_runtime_services()
    except Exception:  # pragma: no cover - shutdown must not raise
        pass


@app.post("/drivers/{name}/install")
def install_driver(name: str):
    """Install a registered driver's optional extra (pip install -e .[extra])."""
    spec = driver_registry.get_driver(name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown driver '{name}'")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", f".[{spec.required_extra}]"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="pip install timed out")
    importlib.invalidate_caches()  # so the next readiness check sees the new package
    log = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "log": log,
        "status": driver_registry.driver_status(spec),
    }


@app.get("/settings/custom-models")
def get_custom_models():
    return _custom_models


@app.post("/settings/custom-models")
def add_custom_model(req: AddCustomModelReq):
    if req.value and req.value not in _custom_models:
        _custom_models.append(req.value)
        _save_custom_models()
    return {"ok": True}


@app.delete("/settings/custom-models")
def remove_custom_model(value: str):
    if value in _custom_models:
        _custom_models.remove(value)
        _save_custom_models()
    return {"ok": True}


def _custom_node_globals() -> dict[str, Any]:
    return {
        "Any": bn.Any,
        "Bool": bn.Bool,
        "Dict": bn.Dict,
        "Embedding": bn.Embedding,
        "Float": bn.Float,
        "Fn": bn.Fn,
        "Int": bn.Int,
        "List": bn.List,
        "Model": bn.Model,
        "Number": bn.Number,
        "Text": bn.Text,
        "blacknode": bn,
        "bn": bn,
        "node": bn.node,
        "__builtins__": __builtins__,
    }


@app.post("/exec-node")
def exec_node(req: ExecNodeReq):
    import traceback
    before = dict(_NODE_REGISTRY)
    globs: dict = _custom_node_globals()
    try:
        exec(compile(req.code, "<custom>", "exec"), globs)
        registered_types = sorted(
            name for name, fn in _NODE_REGISTRY.items()
            if before.get(name) is not fn
        )
        new_types = sorted(name for name in registered_types if name not in before)
        return {
            "ok": True,
            "new_types": new_types,
            "registered_types": registered_types,
        }
    except Exception:
        raise HTTPException(400, traceback.format_exc())


@app.get("/custom-nodes")
def list_custom_nodes():
    custom_dir = Path(_CUSTOM_NODES_DIR).resolve()
    files = []
    if custom_dir.exists():
        files = [str(path.relative_to(custom_dir)) for path in sorted(custom_dir.rglob("*.py")) if not path.name.startswith("_")]
    registered = [
        _node_def_payload(name, fn)
        for name, fn in sorted(_NODE_REGISTRY.items())
        if getattr(fn, "_bn_source_path", "")
    ]
    return {"directory": str(custom_dir), "files": files, "registered": registered}


@app.get("/custom-nodes/source")
def get_custom_node_source(filename: str):
    custom_dir = Path(_CUSTOM_NODES_DIR).resolve()
    path = (custom_dir / _safe_custom_node_filename(filename)).resolve()
    if custom_dir not in path.parents:
        raise HTTPException(400, "Invalid custom node path")
    if not path.is_file():
        raise HTTPException(404, f"Custom node file '{path.name}' was not found")
    return {
        "filename": path.name,
        "path": str(path),
        "code": path.read_text(encoding="utf-8"),
    }


@app.get("/packages")
def list_packages(git: bool = False):
    # git status is ~6 subprocesses per folder package; only the Packages panel
    # needs it (git=true). The default hot path (node grouping) skips it.
    return {"packages": package_statuses(fetch=False, git=git)}


@app.get("/packages/index")
def get_package_index():
    return package_index_payload()


@app.post("/packages/reload")
def reload_packages():
    report = discover_bn_packages()
    importlib.reload(bn_package_index)
    return {"ok": not report["failed"], "index_refreshed": True, **report}


class InstallPackageReq(BaseModel):
    url: str
    install_deps: bool = True


@app.post("/packages/install")
def install_package(req: InstallPackageReq):
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "Git URL is required")
    log: list[str] = []
    # Blocking on purpose: clone + pip + docker pulls can take minutes and the
    # panel shows a busy state. Progress lines come back in the response.
    result = bn_install_from_git(url, install_deps=req.install_deps, progress=log.append)
    return {**result, "log": log}


@app.post("/packages/{name}/setup")
def setup_package(name: str):
    """Install an already-cloned package's prerequisites (pip deps, Docker
    images) into this server's interpreter, then reload it."""
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", name):
        raise HTTPException(400, "Invalid package name")
    dest = (bn_packages_root() / name).resolve()
    if not (dest / BN_MANIFEST_NAME).exists():
        raise HTTPException(404, f"No package folder '{name}' under packages/")
    log: list[str] = []
    # Blocking on purpose: pip installs and Docker pulls can take minutes.
    bn_install_prerequisites(dest, progress=log.append)
    info = bn_load_package(dest)
    return {"ok": info.ok, "package": info.to_dict(), "log": log}


@app.post("/packages/{name}/components/{component}/{action}")
def set_package_component(name: str, component: str, action: str):
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", name):
        raise HTTPException(400, "Invalid package name")
    component_name, separator, adapter_name = component.partition("@")
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", component_name):
        raise HTTPException(400, "Invalid component name")
    if separator and not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", adapter_name):
        raise HTTPException(400, "Invalid adapter name")
    if action not in {"enable", "disable", "reset"}:
        raise HTTPException(400, "Component action must be enable, disable, or reset")
    try:
        if adapter_name and action == "enable":
            info = bn_ensure_adapter_enabled(name, component_name, adapter_name)
        elif adapter_name and action == "disable":
            info = bn_set_adapter_enabled(name, component_name, adapter_name, False)
        elif adapter_name:
            info = bn_reset_component(name, component_name, adapter_name)
        elif action == "enable":
            info = bn_ensure_component_enabled(name, component_name)
        elif action == "disable":
            info = bn_set_component_enabled(name, component_name, False)
        else:
            info = bn_reset_component(name, component_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "package": info.to_dict()}


@app.get("/packages/{name}/components/{component}/dependencies")
def get_package_component_dependencies(name: str, component: str):
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", name):
        raise HTTPException(400, "Invalid package name")
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", component):
        raise HTTPException(400, "Invalid component name")
    try:
        return bn_component_dependency_plan(name, component)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/packages/{name}/components/{component}/adapters/{adapter}/{action}")
def set_package_adapter(name: str, component: str, adapter: str, action: str):
    for value, label in ((name, "package"), (component, "component"), (adapter, "adapter")):
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", value):
            raise HTTPException(400, f"Invalid {label} name")
    if action not in {"enable", "disable", "reset"}:
        raise HTTPException(400, "Adapter action must be enable, disable, or reset")
    try:
        if action == "enable":
            info = bn_ensure_adapter_enabled(name, component, adapter)
        elif action == "disable":
            info = bn_set_adapter_enabled(name, component, adapter, False)
        else:
            info = bn_reset_component(name, component, adapter)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "package": info.to_dict()}


@app.get("/packages/{name}/components/{component}/adapters/{adapter}/dependencies")
def get_package_adapter_dependencies(name: str, component: str, adapter: str):
    for value, label in ((name, "package"), (component, "component"), (adapter, "adapter")):
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", value):
            raise HTTPException(400, f"Invalid {label} name")
    try:
        return bn_adapter_dependency_plan(name, component, adapter)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.delete("/packages/{name}")
def delete_package(name: str):
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", name):
        raise HTTPException(400, "Invalid package name")
    result = bn_remove_package(name)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result


@app.post("/custom-nodes/reload")
def reload_custom_nodes():
    report = discover_node_modules()
    if report.get("failed"):
        return {"ok": False, **report}
    return {"ok": True, **report}


@app.post("/custom-nodes")
def save_custom_node(req: SaveCustomNodeReq):
    import traceback

    try:
        compile(req.code, "<custom-node>", "exec")
    except Exception:
        raise HTTPException(400, traceback.format_exc())

    filename = _safe_custom_node_filename(req.filename)
    custom_dir = Path(_CUSTOM_NODES_DIR).resolve()
    custom_dir.mkdir(parents=True, exist_ok=True)
    path = (custom_dir / filename).resolve()
    if custom_dir not in path.parents and path != custom_dir:
        raise HTTPException(400, "Invalid custom node path")

    path.write_text(req.code, encoding="utf-8")
    result = load_node_file(path)
    if not result["ok"]:
        raise HTTPException(400, result.get("error", "Could not load custom node"))
    return {"ok": True, "path": str(path), "new_types": result["new_types"]}


def _safe_custom_node_filename(filename: str) -> str:
    raw = Path(filename or "custom_node").name.strip()
    if raw.lower().endswith(".py"):
        raw = raw[:-3]
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw)
    stem = stem.strip("._-") or "custom_node"
    return f"{stem}.py"


@app.post("/reset")
def reset():
    _session.graph = bn.Graph()
    _session.node_meta.clear()
    _session.metadata.clear()
    _session.entrypoint = None
    _save()
    return {"ok": True}


# ── Workflow persistence ──────────────────────────────────────────────────────

def _portable_subgraph(subgraph: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_meta": _portable_node_meta(subgraph.get("node_meta", {})),
        "edges": [dict(edge) for edge in subgraph.get("edges", [])],
    }


def _portable_node_meta(node_meta: dict[str, dict]) -> dict[str, dict]:
    portable: dict[str, dict] = {}
    for node_id, meta in node_meta.items():
        clean = {
            key: value
            for key, value in meta.items()
            if key not in _RUNTIME_STATUS_KEYS
        }
        if isinstance(clean.get("subgraph"), dict):
            clean["subgraph"] = _portable_subgraph(clean["subgraph"])
        portable[node_id] = clean
    return portable


def _workflow_payload(
    name: str,
    *,
    entrypoint: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": _WORKFLOW_KIND,
        "schema_version": _WORKFLOW_SCHEMA_VERSION,
        "name": name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "node_meta": _portable_node_meta(_session.node_meta),
        "edges": [dict(edge) for edge in _session.graph._edges],
    }
    selected_entrypoint = entrypoint if entrypoint is not None else _session.entrypoint
    if selected_entrypoint is not None:
        payload["entrypoint"] = dict(selected_entrypoint)
    combined_metadata = dict(_session.metadata)
    if metadata is not None:
        combined_metadata.update(metadata)
    if combined_metadata:
        payload["metadata"] = combined_metadata
    return payload


def _infer_export_entrypoint(data: dict[str, Any]) -> dict[str, str] | None:
    entrypoint = data.get("entrypoint")
    if isinstance(entrypoint, dict) and entrypoint.get("node_id") and entrypoint.get("port"):
        return {"node_id": str(entrypoint["node_id"]), "port": str(entrypoint["port"])}

    node_meta = data.get("node_meta")
    if not isinstance(node_meta, dict):
        return None

    preferred_ids = (
        "overlay_out",
        "reason_dashboard_out",
        "reasoning_out",
        "stream_out",
        "image_out",
        "snapshot_out",
        "mask_out",
        "out",
    )
    for node_id in preferred_ids:
        meta = node_meta.get(node_id)
        if isinstance(meta, dict):
            if meta.get("type") == "OutputImage":
                return {"node_id": node_id, "port": "image"}
            if meta.get("type") == "Output":
                return {"node_id": node_id, "port": "value"}

    for node_id, meta in node_meta.items():
        if isinstance(meta, dict) and meta.get("type") == "OutputImage":
            return {"node_id": str(node_id), "port": "image"}
    for node_id, meta in node_meta.items():
        if isinstance(meta, dict) and meta.get("type") == "Output":
            return {"node_id": str(node_id), "port": "value"}
    return None


def _workflow_for_export(workflow: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(workflow) if workflow is not None else _workflow_payload(
        "Current Graph",
        metadata={"source": "editor"},
    )
    _ensure_workflow_header(data)
    if not isinstance(data.get("entrypoint"), dict):
        entrypoint = _infer_export_entrypoint(data)
        if entrypoint is not None:
            data["entrypoint"] = entrypoint
    return data


def _export_framework_payload(target: str, workflow: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return export_framework_workflow(_workflow_for_export(workflow), target)
    except Exception as exc:
        raise HTTPException(400, str(exc))


def _enqueue_sync_run_update(record: dict[str, Any], *, playing: bool) -> None:
    events = record.get("events") if isinstance(record.get("events"), list) else []
    cursor = len(events) - 1
    _enqueue_editor_action(
        "sync_run_event",
        {
            "record": _redact_run_snapshot_secrets(record),
            "cursor": cursor,
            "playing": playing,
        },
    )


def _redact_run_snapshot_secrets(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            item_key: _redact_run_snapshot_secrets(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_run_snapshot_secrets(item) for item in value]
    if key and _SECRET_FIELD_RE.search(key) and value not in (None, ""):
        return "[redacted]"
    return value


def _run_workflow_snapshot(node_id: str, port: str) -> dict[str, Any]:
    node_type = _session.node_meta.get(node_id, {}).get("type", "Graph")
    workflow = _workflow_payload(
        f"Run: {node_type}.{port}",
        entrypoint={"node_id": node_id, "port": port},
        metadata={"source": "run_history"},
    )
    return _redact_run_snapshot_secrets(workflow)


def _run_graph_workflow_snapshot(targets: list[tuple[str, str]]) -> dict[str, Any]:
    workflow = _workflow_payload(
        f"Run Graph: {len(targets)} terminal node{'s' if len(targets) != 1 else ''}",
        metadata={
            "source": "run_history",
            "run_scope": "terminal_nodes",
            "targets": [
                {"node_id": node_id, "port": port}
                for node_id, port in targets
            ],
        },
    )
    return _redact_run_snapshot_secrets(workflow)


def _ensure_workflow_header(data: dict[str, Any]) -> None:
    data.setdefault("kind", _WORKFLOW_KIND)
    data.setdefault("schema_version", _WORKFLOW_SCHEMA_VERSION)


def _slug(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name.strip())[:60] or "workflow"

def _workflow_path(slug: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", slug):
        raise HTTPException(400, "Invalid workflow slug")
    return os.path.join(_WORKFLOWS_DIR, f"{slug}.json")


def _template_dirs() -> list[str]:
    # Root templates first so they win slug collisions with package templates.
    return [_TEMPLATES_DIR, *package_template_dirs()]


def _template_sources() -> list[tuple[str, str, str]]:
    """Return template directories with stable editor grouping metadata."""
    sources = [(_TEMPLATES_DIR, "Core", "#6366f1")]
    for info in installed_packages():
        if not info.ok:
            continue
        if info.categories:
            group, color = next(iter(info.categories.items()))
        else:
            group = info.name.removeprefix("blacknode-").replace("-", " ").title()
            color = "#6366f1"
        # Every directory the package contributes, not just its root: a
        # component or adapter that ships its own templates would otherwise be
        # loadable by slug yet never listed in the Templates tab.
        dirs = info.template_dirs or ([info.templates_dir] if info.templates_dir else [])
        for templates_dir in dirs:
            sources.append((templates_dir, group, color))
    return sources


def _template_path(slug: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", slug):
        raise HTTPException(400, "Invalid template slug")
    for templates_dir in _template_dirs():
        path = os.path.join(templates_dir, f"{slug}.json")
        if os.path.exists(path):
            return path
    return os.path.join(_TEMPLATES_DIR, f"{slug}.json")


def _read_workflow_file(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise HTTPException(400, "Workflow file must contain a JSON object")
    _ensure_workflow_header(data)
    return data


def _workflow_summary(
    slug: str,
    data: dict[str, Any],
    *,
    group: str = "Core",
    group_color: str = "#6366f1",
) -> dict[str, Any]:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    categories: list[str] = []
    for node_meta in (data.get("node_meta") or {}).values():
        if not isinstance(node_meta, dict):
            continue
        node_type = str(node_meta.get("type") or "").strip()
        fn = _NODE_REGISTRY.get(node_type)
        if fn is None:
            continue
        category = _category_for_node(fn)
        if category and category not in categories:
            categories.append(category)
    return {
        "slug": slug,
        "name": data.get("name", slug),
        "saved_at": data.get("saved_at", ""),
        "description": metadata.get("description", ""),
        "color": metadata.get("color", "#6366f1"),
        "node_count": len(data.get("node_meta", {}) or {}),
        "group": group,
        "group_color": group_color,
        "categories": categories,
        "required_packages": _workflow_required_packages(data),
        "required_capabilities": _workflow_required_capabilities(data),
    }


def _workflow_dependency_report(data: dict[str, Any]) -> dict[str, Any]:
    # Pass the full package state (version, components, adapters), not just
    # {ok, error}: the resolver checks state["components"][…]["adapters"] to see
    # whether a template's required component/adapter is published and enabled.
    # A stripped state made every adapter read as "not published".
    package_states = {
        info.name: info.to_dict()
        for info in installed_packages()
    }
    return resolve_workflow_dependencies(
        data,
        available_node_types={*_NODE_REGISTRY, *_SUBGRAPH_NODE_TYPES},
        installed_packages=package_states,
    )


def _unique_workflow_slug(base_slug: str) -> str:
    slug = base_slug
    i = 2
    while os.path.exists(_workflow_path(slug)):
        suffix = f"_{i}"
        slug = f"{base_slug[:60 - len(suffix)]}{suffix}"
        i += 1
    return slug

def _save_workflow(name: str, previous_slug: str | None = None):
    os.makedirs(_WORKFLOWS_DIR, exist_ok=True)
    clean_name = name.strip() or "Untitled"
    slug = _slug(clean_name)
    data = _workflow_payload(clean_name)
    with open(_workflow_path(slug), "w") as f:
        json.dump(data, f, indent=2)
    if previous_slug and previous_slug != slug:
        old_path = _workflow_path(previous_slug)
        if os.path.exists(old_path):
            os.remove(old_path)
        _project_store.replace_workflow_slug(previous_slug, slug)
    return {"ok": True, "slug": slug}

def _restore_session(
    node_meta: dict,
    edges: list,
    *,
    metadata: dict[str, Any] | None = None,
    entrypoint: dict[str, str] | None = None,
):
    """Replace current session with the given node_meta + edges."""
    _session.graph = bn.Graph()
    _session.node_meta.clear()
    _session.metadata = dict(metadata) if isinstance(metadata, dict) else {}
    _session.entrypoint = dict(entrypoint) if isinstance(entrypoint, dict) else None
    for node_id, meta in node_meta.items():
        if meta["type"] not in _NODE_REGISTRY and meta["type"] not in _SUBGRAPH_NODE_TYPES:
            continue
        _migrate_legacy_node_meta(meta)
        if meta["type"] in _SUBGRAPH_NODE_TYPES:
            _sync_subgraph_node_ports(meta)
        elif meta["type"] in _TOOLBOX_NODE_TYPES:
            _sync_toolbox_ports(meta, edges)
        _session.node_meta[node_id] = meta
        node_entry = {
            "type":   meta["type"],
            "params": dict(meta.get("params", {})),
        }
        if meta["type"] in _SUBGRAPH_NODE_TYPES:
            node_entry["subgraph"] = meta.get("subgraph", {"node_meta": {}, "edges": []})
        _session.graph._nodes[node_id] = node_entry
        _session.graph._dirty.add(node_id)
    _session.graph._edges = [
        e for e in edges
        if e["from"] in _session.graph._nodes and e["to"] in _session.graph._nodes
    ]


def _restore_session_from_nodes(
    nodes: list[dict],
    edges: list,
    *,
    metadata: dict[str, Any] | None = None,
    entrypoint: dict[str, str] | None = None,
):
    _restore_session(
        {node["id"]: node for node in nodes if "id" in node},
        edges,
        metadata=metadata,
        entrypoint=entrypoint,
    )


def _node_pos(meta: dict) -> tuple[float, float]:
    pos = meta.get("pos", [0, 0])
    try:
        return float(pos[0]), float(pos[1])
    except Exception:
        return 0.0, 0.0


def _insert_workflow(node_meta: dict, edges: list):
    valid_nodes = [
        meta for meta in node_meta.values()
        if meta.get("type") in _NODE_REGISTRY or meta.get("type") in _SUBGRAPH_NODE_TYPES
    ]
    if not valid_nodes:
        return

    current_positions = [_node_pos(meta) for meta in _session.node_meta.values()]
    import_positions = [_node_pos(meta) for meta in valid_nodes]
    if current_positions:
        offset_x = max(x for x, _ in current_positions) - min(x for x, _ in import_positions) + 360
        offset_y = 0
    else:
        offset_x = 0
        offset_y = 0

    id_map: dict[str, str] = {}
    for meta in valid_nodes:
        old_id = meta["id"]
        new_id = str(uuid.uuid4())
        id_map[old_id] = new_id
        x, y = _node_pos(meta)
        next_meta = {
            **meta,
            "id": new_id,
            "params": dict(meta.get("params", {})),
            "pos": [x + offset_x, y + offset_y],
        }
        _migrate_legacy_node_meta(next_meta)
        if next_meta["type"] in _SUBGRAPH_NODE_TYPES:
            _sync_subgraph_node_ports(next_meta)
        elif next_meta["type"] in _TOOLBOX_NODE_TYPES:
            old_id_meta = {**next_meta, "id": old_id}
            _sync_toolbox_ports(old_id_meta, edges)
            next_meta.update({
                "inputs": old_id_meta["inputs"],
                "outputs": old_id_meta["outputs"],
                "input_types": old_id_meta["input_types"],
                "output_types": old_id_meta["output_types"],
                "input_defaults": old_id_meta["input_defaults"],
            })
        _session.node_meta[new_id] = next_meta
        _session.graph._nodes[new_id] = {
            "type": next_meta["type"],
            "params": dict(next_meta.get("params", {})),
        }
        if next_meta["type"] in _SUBGRAPH_NODE_TYPES:
            _session.graph._nodes[new_id]["subgraph"] = next_meta.get("subgraph", {"node_meta": {}, "edges": []})
        _session.graph._dirty.add(new_id)

    for edge in edges:
        from_id = id_map.get(edge.get("from"))
        to_id = id_map.get(edge.get("to"))
        if not from_id or not to_id:
            continue
        _session.graph._edges.append({
            "from": from_id,
            "from_port": edge.get("from_port", "output"),
            "to": to_id,
            "to_port": edge.get("to_port", "input"),
        })


_PROJECT_COLLECT_NODES = {
    "EpisodeRecorder",
}
_PROJECT_TRAIN_NODES = {
    "ACTTraining",
    "PPOTraining",
}
_PROJECT_SIMULATE_NODES = {
    "IsaacPolicySafetyGate",
    "IsaacPolicyBridge",
    "IsaacPolicyRuntime",
}
_PROJECT_STARTER_KITS = {
    "robot_learning": {
        "collect": {
            "template_slug": "teleoperation-episode-recording",
            "name": "Collect demonstrations",
        },
        "train": {
            "template_slug": "act-training",
            "name": "Train ACT policy",
        },
        "simulate": {
            "template_slug": "isaac-act-policy-deployment",
            "name": "Evaluate policy in Isaac",
        },
    },
}
_PROJECT_STARTER_LOCK = threading.RLock()
_PROJECT_ROBOT_NODE_MARKERS = (
    "robot",
    "servo",
    "joint",
    "leaderfollower",
    "policydeployment",
)


def _project_workflow_reference(slug: str) -> dict[str, Any]:
    path = _workflow_path(slug)
    if not os.path.exists(path):
        return {
            "slug": slug,
            "name": slug,
            "exists": False,
            "node_types": [],
            "stages": [],
            "requires_calibration": False,
            "calibration": None,
        }
    try:
        data = _read_workflow_file(path)
    except (OSError, json.JSONDecodeError, HTTPException):
        return {
            "slug": slug,
            "name": slug,
            "exists": False,
            "node_types": [],
            "stages": [],
            "requires_calibration": False,
            "calibration": None,
        }
    node_meta = data.get("node_meta")
    node_types = sorted({
        str(meta.get("type"))
        for meta in (node_meta.values() if isinstance(node_meta, dict) else [])
        if isinstance(meta, dict) and meta.get("type")
    })
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    required_capabilities = [
        str(value)
        for value in metadata.get("required_capabilities", [])
        if isinstance(value, str)
    ]
    raw_calibration = metadata.get("device_calibration")
    calibration = (
        {
            key: str(raw_calibration[key])
            for key in ("profile_id", "hardware_id")
            if raw_calibration.get(key)
        }
        if isinstance(raw_calibration, dict)
        else None
    )
    calibration = calibration or None
    lowered_types = [node_type.lower() for node_type in node_types]
    requires_calibration = (
        "joint_group" in required_capabilities
        or any(
            marker in node_type
            for node_type in lowered_types
            for marker in _PROJECT_ROBOT_NODE_MARKERS
        )
    )
    stages = []
    if any(node_type in _PROJECT_COLLECT_NODES for node_type in node_types):
        stages.append("collect")
    if any(node_type in _PROJECT_TRAIN_NODES for node_type in node_types):
        stages.append("train")
    if any(node_type in _PROJECT_SIMULATE_NODES for node_type in node_types):
        stages.append("simulate")
    return {
        "slug": slug,
        "name": data.get("name", slug),
        "saved_at": data.get("saved_at", ""),
        "exists": True,
        "node_types": node_types,
        "stages": stages,
        "requires_calibration": requires_calibration,
        "calibration": calibration,
        "starter_kit": (
            str(metadata.get("starter_kit"))
            if metadata.get("starter_kit")
            else None
        ),
        "starter_stage": (
            str(metadata.get("starter_stage"))
            if metadata.get("starter_stage")
            else None
        ),
        "source_template": (
            str(metadata.get("source_template"))
            if metadata.get("source_template")
            else None
        ),
    }


def _project_payload(record: dict[str, Any]) -> dict[str, Any]:
    workflows = [
        _project_workflow_reference(str(slug))
        for slug in record.get("workflow_slugs", [])
    ]
    devices = []
    for device_id in record.get("device_ids", []):
        device = _device_registry.get_public(str(device_id))
        devices.append(
            {**device, "exists": True}
            if device is not None
            else {"id": str(device_id), "name": str(device_id), "exists": False}
        )
    return {
        **record,
        "workflows": workflows,
        "devices": devices,
        "artifacts": _artifact_store.list(record.get("artifact_ids", [])),
    }


def _project_error(exc: ProjectStoreError) -> HTTPException:
    return HTTPException(400, str(exc))


@app.get("/projects")
def list_projects():
    try:
        return [_project_payload(record) for record in _project_store.list()]
    except ProjectStoreError as exc:
        raise _project_error(exc) from exc


@app.post("/projects")
def create_project(req: CreateProjectReq):
    try:
        return _project_payload(_project_store.create(
            name=req.name,
            description=req.description,
            workflow_slugs=req.workflow_slugs,
            device_ids=req.device_ids,
            artifact_ids=req.artifact_ids,
            starter_kit=req.starter_kit,
            active_workflow_slug=req.active_workflow_slug,
        ))
    except ProjectStoreError as exc:
        raise _project_error(exc) from exc


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    try:
        record = _project_store.get(project_id)
    except ProjectStoreError as exc:
        raise _project_error(exc) from exc
    if record is None:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return _project_payload(record)


@app.patch("/projects/{project_id}")
def update_project(project_id: str, req: UpdateProjectReq):
    fields_set = (
        req.model_fields_set
        if hasattr(req, "model_fields_set")
        else req.__fields_set__
    )
    try:
        return _project_payload(_project_store.update(
            project_id,
            name=req.name,
            description=req.description,
            workflow_slugs=req.workflow_slugs,
            device_ids=req.device_ids,
            artifact_ids=req.artifact_ids,
            starter_kit=req.starter_kit,
            active_workflow_slug=req.active_workflow_slug,
            update_active_workflow="active_workflow_slug" in fields_set,
            update_starter_kit="starter_kit" in fields_set,
        ))
    except KeyError as exc:
        raise HTTPException(404, f"Project '{project_id}' not found") from exc
    except ProjectStoreError as exc:
        raise _project_error(exc) from exc


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    try:
        deleted = _project_store.delete(project_id)
    except ProjectStoreError as exc:
        raise _project_error(exc) from exc
    if not deleted:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return {"ok": True}


def _project_artifact_error(
    exc: ProjectStoreError | ArtifactStoreError,
) -> HTTPException:
    return HTTPException(400, str(exc))


def _require_project(project_id: str) -> dict[str, Any]:
    record = _project_store.get(project_id)
    if record is None:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return record


def _set_starter_node_defaults(
    data: dict[str, Any],
    node_id: str,
    values: dict[str, Any],
) -> None:
    node_meta = data.get("node_meta")
    node = node_meta.get(node_id) if isinstance(node_meta, dict) else None
    if not isinstance(node, dict):
        return
    params = node.setdefault("params", {})
    if isinstance(params, dict):
        params.update(values)
    defaults = node.get("input_defaults")
    if isinstance(defaults, dict):
        defaults.update({
            key: value
            for key, value in values.items()
            if key in defaults
        })


def _configure_project_starter_workflow(
    data: dict[str, Any],
    stage: str,
    project: dict[str, Any],
) -> None:
    """Prefill safe Project context while keeping all actions disarmed."""
    project_id = str(project["id"])
    if stage == "collect":
        _set_starter_node_defaults(data, "rosbridge", {"transport": "auto"})
        _set_starter_node_defaults(data, "follow", {
            "transport": "auto",
            "run_id": f"{project_id}-teleoperation",
            "armed": False,
        })
        _set_starter_node_defaults(data, "dataset", {
            "dataset_id": f"{project_id}-demonstrations"[:120],
            "task": str(project.get("description") or project.get("name") or ""),
            "metadata": {"project_id": project_id},
        })
        _set_starter_node_defaults(data, "recorder", {
            "action": "status",
            "run_id": f"{project_id}-episode",
        })
        return

    artifacts = _artifact_store.list(project.get("artifact_ids", []))
    if stage == "train":
        dataset = next((
            artifact
            for artifact in reversed(artifacts)
            if artifact.get("artifact_type") == "dataset"
            and artifact.get("exists")
            and int((artifact.get("metadata") or {}).get("episode_count") or 0) > 0
        ), None)
        if dataset is not None:
            locator = str(dataset["locator"])
            metadata = dict(dataset.get("metadata") or {})
            descriptor = {
                "kind": str(dataset.get("kind") or "blacknode.episode-dataset"),
                "schema_version": 1,
                "dataset_id": str(metadata.get("dataset_id") or dataset["name"]),
                "path": locator,
                "fps": int(metadata.get("fps") or 0),
                "task": str(metadata.get("task") or ""),
                "episode_count": int(metadata.get("episode_count") or 0),
            }
            _set_starter_node_defaults(data, "dataset_browser", {
                "dataset": descriptor,
                "root": str(Path(locator).parent),
                "dataset_id": descriptor["dataset_id"],
            })
        _set_starter_node_defaults(data, "training", {
            "action": "start",
            "run_id": f"{project_id}-act",
        })
        _set_starter_node_defaults(data, "policy_stream", {
            "run_id": f"{project_id}-policy-replay",
        })
        return

    if stage == "simulate":
        policy = next((
            artifact
            for artifact in reversed(artifacts)
            if artifact.get("artifact_type") == "policy"
            and artifact.get("exists")
        ), None)
        if policy is not None:
            _set_starter_node_defaults(data, "artifact_path", {
                "value": str(policy["locator"]),
            })
        _set_starter_node_defaults(data, "bridge", {
            "action": "status",
            "run_id": f"{project_id}-isaac-bridge",
        })
        _set_starter_node_defaults(data, "runtime", {
            "action": "status",
            "run_id": f"{project_id}-isaac-policy",
        })


@app.post("/projects/{project_id}/starter-workflows/{stage}")
def create_project_starter_workflow(project_id: str, stage: str):
    with _PROJECT_STARTER_LOCK:
        return _materialize_project_starter_workflow(project_id, stage)


def _materialize_project_starter_workflow(project_id: str, stage: str):
    try:
        project = _require_project(project_id)
        starter_kit = str(project.get("starter_kit") or "")
        kit = _PROJECT_STARTER_KITS.get(starter_kit)
        if kit is None:
            raise HTTPException(
                409,
                "Enable the Robot learning starter for this Project first.",
            )
        starter = kit.get(stage)
        if starter is None:
            raise HTTPException(404, f"Starter stage '{stage}' was not found.")

        for workflow_slug in project.get("workflow_slugs", []):
            reference = _project_workflow_reference(str(workflow_slug))
            if (
                reference.get("exists")
                and reference.get("starter_kit") == starter_kit
                and reference.get("starter_stage") == stage
            ):
                return {
                    "created": False,
                    "workflow": reference,
                    "project": _project_payload(project),
                }

        template_slug = str(starter["template_slug"])
        template_path = _template_path(template_slug)
        if not os.path.exists(template_path):
            raise HTTPException(
                409,
                f"The {starter['name']} template is unavailable. Install and "
                "enable its Blacknode package, then try again.",
            )
        data = _read_workflow_file(template_path)
        dependencies = _workflow_dependency_report(data)
        if not dependencies["ok"]:
            raise HTTPException(409, dependencies)
        report = validate_bn_workflow(data)
        if not report.ok:
            raise HTTPException(400, report.to_dict())
        _configure_project_starter_workflow(data, stage, project)

        workflow_name = f"{project['name']} · {starter['name']}"
        workflow_slug = _unique_workflow_slug(_slug(workflow_name))
        metadata = (
            dict(data.get("metadata"))
            if isinstance(data.get("metadata"), dict)
            else {}
        )
        metadata.pop("template", None)
        metadata.update({
            "starter_kit": starter_kit,
            "starter_stage": stage,
            "source_template": template_slug,
            "project_id": project_id,
        })
        data["name"] = workflow_name
        data["saved_at"] = datetime.now().isoformat(timespec="seconds")
        data["metadata"] = metadata
        os.makedirs(_WORKFLOWS_DIR, exist_ok=True)
        with open(_workflow_path(workflow_slug), "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
        try:
            project = _project_store.link_workflow_slug(
                project_id,
                workflow_slug,
            )
        except KeyError as exc:
            os.remove(_workflow_path(workflow_slug))
            raise HTTPException(
                404,
                f"Project '{project_id}' not found",
            ) from exc
        return {
            "created": True,
            "workflow": _project_workflow_reference(workflow_slug),
            "project": _project_payload(project),
        }
    except ProjectStoreError as exc:
        raise _project_error(exc) from exc


def _link_project_artifacts(
    project_id: str,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    _require_project(project_id)
    artifact_ids = [
        str(artifact.get("id") or "")
        for artifact in artifacts
        if artifact.get("id")
    ]
    try:
        record = _project_store.link_artifact_ids(project_id, artifact_ids)
    except KeyError as exc:
        raise HTTPException(404, f"Project '{project_id}' not found") from exc
    return _project_payload(record)


@app.post("/projects/{project_id}/artifacts/import")
def import_project_artifacts(project_id: str, req: ImportProjectArtifactsReq):
    try:
        project = _require_project(project_id)
        if req.workflow_slug and req.workflow_slug not in project.get(
            "workflow_slugs", []
        ):
            raise HTTPException(
                400,
                "workflow_slug must be linked to the project before its artifacts "
                "can be captured.",
            )
        artifacts = _artifact_store.import_value(
            req.value,
            node_type=req.node_type,
            workflow_slug=req.workflow_slug,
        )
        return {
            "artifacts": artifacts,
            "project": _link_project_artifacts(project_id, artifacts),
        }
    except (ProjectStoreError, ArtifactStoreError) as exc:
        raise _project_artifact_error(exc) from exc


@app.post("/projects/{project_id}/artifacts/inspect")
def inspect_project_artifact(project_id: str, req: InspectProjectArtifactReq):
    try:
        project = _require_project(project_id)
        if req.workflow_slug and req.workflow_slug not in project.get(
            "workflow_slugs", []
        ):
            raise HTTPException(
                400,
                "workflow_slug must be linked to the project before its artifacts "
                "can be added.",
            )
        artifacts = _artifact_store.inspect_path(
            req.path,
            workflow_slug=req.workflow_slug,
        )
        return {
            "artifacts": artifacts,
            "project": _link_project_artifacts(project_id, artifacts),
        }
    except (ProjectStoreError, ArtifactStoreError) as exc:
        raise _project_artifact_error(exc) from exc


@app.get("/workflows")
def list_workflows():
    os.makedirs(_WORKFLOWS_DIR, exist_ok=True)
    result = []
    for fname in sorted(os.listdir(_WORKFLOWS_DIR)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_WORKFLOWS_DIR, fname)) as f:
                data = json.load(f)
            result.append({
                "slug":     fname[:-5],
                "name":     data.get("name", fname[:-5]),
                "saved_at": data.get("saved_at", ""),
            })
        except Exception:
            pass
    return result


@app.get("/templates")
def list_templates():
    result = []
    seen: set[str] = set()
    for templates_dir, group, group_color in _template_sources():
        if not os.path.isdir(templates_dir):
            continue
        for fname in sorted(os.listdir(templates_dir)):
            if not fname.endswith(".json"):
                continue
            slug = fname[:-5]
            if slug in seen:
                continue
            try:
                data = _read_workflow_file(os.path.join(templates_dir, fname))
                metadata = (
                    data.get("metadata")
                    if isinstance(data.get("metadata"), dict)
                    else {}
                )
                if bool(metadata.get("hidden", False)):
                    continue
                result.append(_workflow_summary(
                    slug,
                    data,
                    group=group,
                    group_color=group_color,
                ))
                seen.add(slug)
            except Exception:
                pass
    return result


@app.get("/templates/{slug}/validate")
def validate_template(slug: str):
    path = _template_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Template '{slug}' not found")
    return validate_bn_workflow(_read_workflow_file(path)).to_dict()


@app.post("/templates/{slug}/load")
def load_template(slug: str):
    path = _template_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Template '{slug}' not found")
    data = _read_workflow_file(path)
    dependencies = _workflow_dependency_report(data)
    if not dependencies["ok"]:
        raise HTTPException(409, dependencies)
    report = validate_bn_workflow(data)
    if not report.ok:
        raise HTTPException(400, report.to_dict())
    _restore_session(
        data.get("node_meta", {}),
        data.get("edges", []),
        metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        entrypoint=data.get("entrypoint") if isinstance(data.get("entrypoint"), dict) else None,
    )
    _save()
    return get_graph()


@app.get("/validate")
def validate_current_workflow():
    report = validate_bn_graph(
        _portable_node_meta(_session.node_meta),
        [dict(edge) for edge in _session.graph._edges],
        entrypoint=_session.entrypoint,
    )
    return report.to_dict()


@app.get("/export/frameworks")
def export_frameworks():
    return {"targets": list_export_targets()}


@app.post("/export/framework")
def export_framework(req: FrameworkExportReq):
    return _export_framework_payload(req.target, req.workflow)


@app.post("/export/langgraph")
def export_langgraph(req: ExportWorkflowReq | None = None):
    return _export_framework_payload("langgraph", req.workflow if req else None)


@app.post("/import/python")
@app.post("/api/workflows/current/import-python")
def import_python_workflow(req: ImportPythonReq):
    try:
        workflow = import_workflow_python(req.code, name=req.name.strip() or "Imported Python Workflow")
        _ensure_workflow_header(workflow)
        validation = validate_bn_workflow(workflow).to_dict()
    except SyntaxError as exc:
        raise HTTPException(400, f"Python parse error: {exc}")
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"workflow": workflow, "validation": validation}


@app.get("/api/workflows/current")
def api_current_workflow():
    workflow = _workflow_for_export()
    return {"workflow": workflow, "validation": validate_current_workflow()}


@app.post("/api/workflows/current/nodes")
def api_create_node(req: AddNodeReq):
    return add_node(req)


@app.post("/api/workflows/current/edges")
def api_connect_node(req: ConnectReq):
    return connect(req)


@app.get("/api/workflows/current/validate")
def api_validate_current_workflow():
    return validate_current_workflow()


@app.post("/api/workflows/current/run")
def api_run_current_workflow(req: CookReq):
    return cook(req)


@app.post("/api/workflows/current/export")
def api_export_current_workflow(req: FrameworkExportReq):
    return _export_framework_payload(req.target, req.workflow)


@app.websocket("/api/workflows/current/ws")
@app.websocket("/ws/workflows/current")
async def workflow_socket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "state", **api_current_workflow()})
    try:
        while True:
            message = await websocket.receive_json()
            action = str(message.get("action") or "get_state")
            if action == "get_state":
                await websocket.send_json({"type": "state", **api_current_workflow()})
            elif action == "validate":
                await websocket.send_json({"type": "validation", "validation": validate_current_workflow()})
            elif action == "export":
                target = str(message.get("target") or "langgraph")
                await websocket.send_json({"type": "export", **_export_framework_payload(target, message.get("workflow"))})
            else:
                await websocket.send_json({"type": "error", "error": f"Unknown action '{action}'"})
    except WebSocketDisconnect:
        return


@app.get("/workflows/{slug}/validate")
def validate_saved_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    return validate_bn_workflow(data).to_dict()


@app.post("/workflows")
def save_workflow(req: SaveWorkflowReq):
    return _save_workflow(req.name, req.previous_slug)


@app.post("/workflows/{name}")
def save_workflow_legacy(name: str):
    return _save_workflow(name)


@app.patch("/workflows/{slug}")
def rename_workflow(slug: str, req: RenameWorkflowReq):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    clean_name = req.name.strip() or "Untitled"
    next_slug = _slug(clean_name)
    next_path = _workflow_path(next_slug)
    if next_slug != slug and os.path.exists(next_path):
        raise HTTPException(409, f"Workflow '{clean_name}' already exists")
    with open(path) as f:
        data = json.load(f)
    _ensure_workflow_header(data)
    data["name"] = clean_name
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    with open(next_path, "w") as f:
        json.dump(data, f, indent=2)
    if next_slug != slug:
        os.remove(path)
        _project_store.replace_workflow_slug(slug, next_slug)
    return {"slug": next_slug, "name": clean_name, "saved_at": data["saved_at"]}


@app.post("/workflows/{slug}/duplicate")
def duplicate_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    _ensure_workflow_header(data)
    name = f"{data.get('name', slug)} copy"
    next_slug = _unique_workflow_slug(_slug(name))
    data["name"] = name
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    with open(_workflow_path(next_slug), "w") as f:
        json.dump(data, f, indent=2)
    return {"slug": next_slug, "name": name, "saved_at": data["saved_at"]}


@app.post("/workflows/{slug}/insert")
def insert_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    _insert_workflow(data.get("node_meta", {}), data.get("edges", []))
    _save()
    return get_graph()


@app.post("/workflows/{slug}/load")
def load_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    with open(path) as f:
        data = json.load(f)
    _restore_session(
        data.get("node_meta", {}),
        data.get("edges", []),
        metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        entrypoint=data.get("entrypoint") if isinstance(data.get("entrypoint"), dict) else None,
    )
    _save()
    return get_graph()


@app.delete("/workflows/{slug}")
def delete_workflow(slug: str):
    path = _workflow_path(slug)
    if not os.path.exists(path):
        raise HTTPException(404, f"Workflow '{slug}' not found")
    os.remove(path)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    # Clear orphaned stream servers once, at cold boot - not on every worker
    # import, which under auto-reload would kill live streams on each reload.
    _reap_orphaned_stream_servers()
    # Auto-reload is a code-editing convenience, not something an app being used
    # should do: every reload restarts the worker, and a worker that owns live
    # streams tears them down on the way out. Off by default; opt in with
    # BLACKNODE_DEV_RELOAD=1 when actually editing the server.
    dev_reload = os.environ.get("BLACKNODE_DEV_RELOAD", "").strip().lower() in {"1", "true", "yes"}
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=7777,
        reload=dev_reload,
        reload_dirs=[
            os.path.dirname(__file__),
            os.path.join(os.path.dirname(__file__), "..", "python"),
        ] if dev_reload else None,
    )
