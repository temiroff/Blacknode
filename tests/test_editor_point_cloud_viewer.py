from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "editor" / "src" / "components" / "PointCloudViewer.tsx"
BLACK_NODE = ROOT / "editor" / "src" / "components" / "BlackNode.tsx"
APP = ROOT / "editor" / "src" / "App.tsx"
INDEX_CSS = ROOT / "editor" / "src" / "index.css"


def test_point_cloud_viewer_exposes_spatial_orientation_and_scale():
    source = VIEWER.read_text(encoding="utf-8")

    assert "Robot forward" not in source
    assert "const [showAxes, setShowAxes] = useState(false)" in source
    assert "const [showFreeSpace, setShowFreeSpace] = useState(true)" in source
    assert 'type="checkbox"' in source
    assert "checked={showAxes}" in source
    assert "roundedPolygonPath" in source
    assert "'/blacknode-logo-dark.png'" in source
    assert "const ROBOT_LOGO_ROTATION_RAD = -Math.PI / 2" in source
    assert "const ROBOT_LOGO_SOURCE = { x: 78, y: 48, width: 352, height: 415 }" in source
    assert "const ROBOT_LOGO_FOOTPRINT_SCALE = 0.58" in source
    assert "const ROBOT_FOOTPRINT_VISUAL_SCALE = 0.88" in source
    assert "const visualRobotLength = robotLength * ROBOT_FOOTPRINT_VISUAL_SCALE" in source
    assert "const visualRobotWidth = robotWidth * ROBOT_FOOTPRINT_VISUAL_SCALE" in source
    assert "const robotCornerRadius = clamp(shortestRobotEdge * 0.44, 3, 14)" in source
    assert "const logoWorldScale = Math.min(" in source
    assert "const logoWidth = ROBOT_LOGO_SOURCE.width * logoWorldScale / visualRobotWidth" in source
    assert "const logoHeight = ROBOT_LOGO_SOURCE.height * logoWorldScale / visualRobotLength" in source
    assert "(forwardUnit[0] - sensorScreen[0]) * visualRobotLength" in source
    assert "(lateralUnit[0] - sensorScreen[0]) * visualRobotWidth" in source
    assert "context.rotate(ROBOT_LOGO_ROTATION_RAD)" in source
    assert "context.rotate(-robotHeadingYaw" not in source
    assert "projectedHeading" not in source
    assert "rgba(30, 199, 220, 0.3)" in source
    assert "robotHeadingYaw" in source
    assert "robotCorners" in source
    assert "finite(parsed.robot?.length_m, 0.25)" in source
    assert "finite(parsed.robot?.width_m, 0.22)" in source
    assert "filtered laser returns" in source
    assert "3D orbit · LaserScan lies on XY plane" in source
    assert "meterLabel" in source
    assert "angle_min_rad" in source
    assert "angle_max_rad" in source
    assert "CURRENT SCAN" in source
    assert "accumulated returns" in source
    assert "history is sensor-local" in source
    assert "pose-registered history" in source
    assert "scanCoverageDeg" in source
    assert "360° scan" in source
    assert "sequenceRef" not in source
    assert "sweepOrderedPoints" in source
    assert "parsed.sequence, replayDurationMs" in source
    assert "Math.max(scanPeriodMs, 700)" in source
    assert "replayInProgress" in source
    assert "paced replay" in source
    assert "Warp occupancy" in source
    assert "fixed free-floor cells" in source
    assert "occupied wall cells" in source
    assert "unknown map extent" in source
    assert "occupied_points" in source
    assert "gl.TRIANGLES" in source
    assert "occupiedCellCount" in source
    assert "WARP MAP · FILLING" in source
    assert "WARP MAP · FROZEN" in source
    assert "decodeOccupancyTexture" in source
    assert "u2-base64" in source
    assert "gl.LUMINANCE" in source
    assert "gl.NEAREST" in source
    assert "GPU map texture · all cells" in source
    assert "occupancyEncodeMs" in source
    assert "Warp match" in source
    assert "matching_kernel_ms" in source
    assert "fixed map grid" in source
    assert "#72ff9d" in source
    assert ") % 1" not in source
    assert "real_scan_pulse" not in source
    assert "Accumulate:" in source
    assert "uniform float u_show_free" in source
    assert "u_show_free < 0.5" in source
    assert "vec3(0.18, 0.68, 0.36)" in source
    assert "Floor: {showFreeSpace ? 'On' : 'Off'}" in source
    assert "const visibleFloorPoints = useMemo(" in source
    assert "const occupancyCanvasRef = useRef<HTMLCanvasElement | null>(null)" in source
    assert "const occupancyRasterRef = useRef<{" in source
    assert "const distanceMix = clamp(Math.hypot(worldX - sensor.x, worldY - sensor.y) / gradientDistance, 0, 1)" in source
    assert "Math.max(viewport.width, viewport.height) / Math.max(1, pixelsPerMeter) * 0.55" in source
    assert "image.data[offset + 1] = Math.round(181 + (108 - 181) * smoothMix)" in source
    assert "image.data[offset + 2] = Math.round(108 + (190 - 108) * smoothMix)" in source
    assert "image.data[offset + 3] = Math.round(115 + (80 - 115) * smoothMix)" in source
    assert "context.globalCompositeOperation = 'screen'" in source
    assert "context.drawImage(raster.canvas, 0, 0)" in source
    assert "canvas.getContext('webgl', { antialias: true, alpha: true })" in source
    assert "gl.clearColor(0, 0, 0, 0)" in source
    assert "position: 'absolute', inset: 0, zIndex: 0" in source
    assert "position: 'relative', zIndex: 1" in source


def test_point_cloud_viewer_has_direct_camera_navigation():
    source = VIEWER.read_text(encoding="utf-8")

    assert "onWheel" in source
    assert 'className="bn-viewer-wheel-capture"' in source
    assert "onPointerMove" in source
    assert "left-drag pan" in source
    assert "right-drag orbit" in source
    assert "middle-drag pan" in source
    assert "double-click reset" in source
    assert "Orbit left" in source
    assert "Orbit right" in source
    assert "Tilt camera up" in source
    assert "pitch:" in source
    assert "onClear" in source
    assert "clearViewRadiusFloorRef" in source
    assert "const viewRadius = Math.max(automaticViewRadius, clearViewRadiusFloorRef.current)" in source
    assert "onDoubleClick={resetCamera}" in source
    assert "const ROBOT_FIT_RADIUS_MULTIPLIER = 1.65" in source
    assert "const MAX_CAMERA_ZOOM = 120" in source
    assert "const TOP_VIEW_YAW = Math.PI / 2" in source
    assert "yaw: TOP_VIEW_YAW" in source
    assert "pitch: 0" in source
    assert "const initialResetPendingRef = useRef(true)" in source
    assert "initialResetPendingRef.current = false" in source
    assert "resetCamera()" in source
    assert "const focusRadius = Math.max(0.35" in source
    assert "const resetYaw = TOP_VIEW_YAW - robotHeadingYaw" in source
    assert "yaw: resetYaw" in source
    assert "const [gridFrame, setGridFrame] = useState<GridFrame>({ x: 0, y: 0, yaw: 0 })" in source
    assert "setGridFrame({ x: sensor.x, y: sensor.y, yaw: robotHeadingYaw })" in source
    assert "pitch: 0" in source
    assert "const focusedSensorX = resetYawCosine * sensor.x - resetYawSine * sensor.y" in source
    assert "const focusedSensorY = resetYawSine * sensor.x + resetYawCosine * sensor.y" in source
    assert "panX: -focusedSensorX * appliedPixelsPerMeter" in source
    assert "panY: focusedSensorY * appliedPixelsPerMeter" in source
    assert 'title="Top view with world +X (red axis) pointing up"' in source
    assert 'title="Capture and align the grid at the current robot pose, then keep the grid and map fixed"' in source
    assert ">Reset</button>" in source
    assert "const ROBOT_LOGO_ROTATION_RAD = -Math.PI / 2" in source
    assert "const gridFrameToScreen = (forward: number, lateral: number, z: number)" in source
    assert "gridFrame.x + gridHeadingCosine * forward - gridHeadingSine * lateral" in source
    assert "const [x1, y1] = gridFrameToScreen(value, -reach, 0)" in source
    assert "const [x3, y3] = gridFrameToScreen(-reach, value, 0)" in source
    assert 'title="Show fixed map X, Y, and Z axes with metric tick labels"' in source
    assert "event.button === 2 ? 'rotate' : 'pan'" in source
    assert "event.preventDefault()" in source
    assert "event.stopPropagation()" in source
    assert "setSceneCopyMenu" not in source
    assert "Viewer value menu" not in source
    assert "copyTextToClipboard" not in source
    assert "if (event.button === 2) return" not in source


def test_point_cloud_viewer_exposes_accumulation_control():
    source = BLACK_NODE.read_text(encoding="utf-8")

    assert "onToggleViewerAccumulation" in source
    assert "viewerHistoryPaused ? 'resume' : 'pause'" in source
    assert "await controlNode(id, 'clear')" in source
    assert "await controlNode(id, 'stop')" in source
    assert "await controlNode(id, viewerHistoryPaused ? 'resume' : 'pause')" in source
    assert "await updateParam(id, 'action', 'clear')" not in source
    assert "data.type === 'Viewer' || data.type === 'SLAM'" in source
    assert "optimized trajectory" not in VIEWER.read_text(encoding="utf-8")
    assert "if (trajectory.length > 1)" not in VIEWER.read_text(encoding="utf-8")
    assert "rgba(224, 105, 255, 0.9)" not in VIEWER.read_text(encoding="utf-8")
    assert "deskew on" in VIEWER.read_text(encoding="utf-8")
    assert "uncertain scan match rejected" in VIEWER.read_text(encoding="utf-8")
    assert "stationary odometry lock" in VIEWER.read_text(encoding="utf-8")
    assert "large pose correction smoothed across scans" in VIEWER.read_text(encoding="utf-8")
    assert "uncertain keyframe excluded" in VIEWER.read_text(encoding="utf-8")


def test_point_cloud_viewer_fills_resized_node_in_both_dimensions():
    viewer_source = VIEWER.read_text(encoding="utf-8")
    node_source = BLACK_NODE.read_text(encoding="utf-8")

    assert 'className="bn-node-parameter-area"' in node_source
    assert "The viewer is a direct flex child" in node_source
    assert "margin: '7px 9px 8px'" in viewer_source
    assert "width: 'calc(100% - 18px)'" in viewer_source
    assert "flex: '1 1 auto'" in viewer_source
    assert "minHeight: 0" in viewer_source
    assert "flex: '1 1 auto'" in viewer_source
    assert "minHeight: 80" in viewer_source
    assert "flexWrap: 'wrap'" in viewer_source
    assert "data-bn-viewer-telemetry" in viewer_source
    assert "height: 28, flex: '0 0 28px', overflow: 'hidden', whiteSpace: 'nowrap'" in viewer_source
    assert "data-bn-viewer-legend" in viewer_source
    assert "height: 25, flex: '0 0 25px', overflow: 'hidden', whiteSpace: 'nowrap'" in viewer_source
    assert "minWidth={isViewer ? 360 : 160}" in node_source
    assert "minHeight={isViewer ? 300 : 60}" in node_source
    assert "display: isViewer ? 'none' : 'flex'" in node_source


def test_dynamic_motion_uses_orange_points_without_direction_vectors():
    viewer_source = VIEWER.read_text(encoding="utf-8")

    assert "Motion is position-only for now" in viewer_source
    assert "const color = '255, 169, 64'" in viewer_source
    assert "coherent motion · orange points" in viewer_source
    assert "point[0] - velocityX" not in viewer_source
    assert "amber/magenta velocity trails" not in viewer_source


def test_trajectory_evaluation_draws_safe_blocked_and_best_paths_without_motion_control():
    viewer_source = VIEWER.read_text(encoding="utf-8")

    assert "trajectory_paths" in viewer_source
    assert "const trajectoryPaths = useMemo" in viewer_source
    assert "safe ? '102, 224, 145' : '255, 91, 91'" in viewer_source
    assert "best ? '91, 235, 255'" in viewer_source
    assert "WARP PATHS" in viewer_source
    assert "best GPU path" in viewer_source
    assert "Warp paths" in viewer_source


def test_slam_viewer_shift_click_sets_connected_warp_trajectory_goal_without_recook():
    viewer_source = VIEWER.read_text(encoding="utf-8")
    node_source = BLACK_NODE.read_text(encoding="utf-8")
    store_source = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "function screenToWorldPlane(" in viewer_source
    assert "event.shiftKey && event.button === 0 && onGoalSet" in viewer_source
    assert "shift-click goal" in viewer_source
    assert "edge.targetHandle === 'trajectory_evaluation'" in node_source
    assert "edge.sourceHandle === 'stage'" in node_source
    assert "node.data.type === 'WarpTrajectoryEvaluator'" in node_source
    assert "updateParam(trajectoryNode.id, 'goal_x_m', goalXMetres)" in node_source
    assert "updateParam(trajectoryNode.id, 'goal_y_m', goalYMetres)" in node_source
    assert "await controlNode(id, 'set-goal', {" in node_source
    assert "controlNode: async (id, action, payload = {})" in store_source
    assert "api.controlNode(id, action, payload)" in store_source
    assert "cookNode" not in node_source[node_source.index("const onSetSlamGoal"):node_source.index("const runManualMoveAction")]


def test_viewer_ports_are_compact_and_new_viewers_start_square():
    node_source = BLACK_NODE.read_text(encoding="utf-8")
    viewer_source = VIEWER.read_text(encoding="utf-8")
    styles = INDEX_CSS.read_text(encoding="utf-8")
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "function ViewerInputStrip" in node_source
    assert 'className="bn-viewer-input-strip"' in node_source
    assert "position={Position.Left}" in node_source
    assert "ports={visibleInputs}" in node_source
    assert "inputRail={(" in node_source
    assert "inputRail?: ReactNode" in viewer_source
    assert "{inputRail}" in viewer_source
    assert "data-bn-viewer-canvas-region" in viewer_source
    assert "el.querySelector('[data-bn-viewer-canvas-region]')" in node_source
    assert "if (viewerRegion) observer.observe(viewerRegion)" in node_source
    assert "requestAnimationFrame(() => updateNodeInternals(id))" in node_source
    assert 'className="bn-viewer-hidden-output-anchors"' in node_source
    assert "opacity: 0, pointerEvents: 'none'" in node_source
    assert "!isViewer && nodeStats.length > 0" in node_source
    assert ".bn-viewer-input-strip" in styles
    assert ".bn-viewer-input-anchor .react-flow__handle" in styles
    assert "flex-direction: column" in styles
    assert "position: absolute" in styles
    assert "top: 12px" in styles
    assert "left: -10px" in styles
    assert "left: -5px" in styles
    assert "margin-top: 0" in styles
    assert "border-radius: 3px !important" in styles
    assert "meta.type === 'Viewer' || meta.type === 'SLAM'" in store
    assert "style: { width: 720, height: 720 }" in store


def test_point_cloud_viewer_draws_current_scan_when_map_is_empty():
    source = VIEWER.read_text(encoding="utf-8")

    assert "() => [...visibleFloorPoints, ...occupiedPoints, ...points, ...currentPoints]" in source
    assert "currentColors[currentIndex]" in source
    assert "if (vertexCount === 0) return" in source
    assert "Live scan; map is empty" in source


def test_go_live_button_becomes_stop_live_for_viewer_and_slam_sessions():
    source = APP.read_text(encoding="utf-8")
    styles = INDEX_CSS.read_text(encoding="utf-8")
    store = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "const [activeRunMode, setActiveRunMode]" in source
    assert "const visualizerRunCount" in source
    assert "const liveRunActive" in source
    assert "liveRunActive ? '■ Stop live' : '● Go live'" in source
    assert "onceRunActive ? '■ Stop once' : '▶ Run once'" in source
    assert """className="bn-top-button bn-top-run-button"
                onClick={() => (onceRunActive ? stopCook() : void handleRunGraph('once'))}""" in source
    assert """className={`bn-top-button bn-top-run-button bn-top-live-button${liveRunActive ? ' is-stop-live' : ' is-start-live'}`}
                onClick={() => (liveRunActive ? void handleStopRuntime() : void handleRunGraph('live'))}""" in source
    assert 'className="bn-top-button bn-top-reset-button"' in source
    assert ".bn-top-live-button.is-start-live" in styles
    assert "background: var(--ok)" in styles
    assert ".bn-top-live-button.is-stop-live" in styles
    assert "background: var(--err)" in styles
    assert ".bn-top-reset-button" in styles
    assert "background: var(--warn-soft)" in styles
    assert "n.data.type === 'Viewer' ||" in store
    assert "n.data.type === 'SLAM'" in store
    assert "(node.data.type === 'Viewer' || node.data.type === 'SLAM')" in store
    assert "if (data.type === 'Viewer' || data.type === 'SLAM')" in store
    assert "report: `${data.type} stopped by workflow control`" in store
    assert "running: false" in store
    assert "live: false" in store
    assert "status: { ...status, state: 'stopped' }" in store
