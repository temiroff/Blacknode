import { memo, useState, useRef, useEffect } from 'react'
import { Handle, Position, NodeProps, useReactFlow, useUpdateNodeInternals } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import {
  api,
  type DeviceCalibrationCandidate,
  type DeviceRobotProfile,
} from '../api'
import { portColor, portVisualColor } from '../portColors'
import { headerColor } from '../categories'
import { isWireOnlyInput } from '../inputControls'
import { copyTextToClipboard } from '../clipboard'
import { portDisplayHint, portDisplayName } from '../portLabels'
import { useQualifiedTypeLabel } from '../nodeTypeLabel'
import NodeFrame from './NodeFrame'
import NodeGlyph from './NodeGlyph'
import DatasetBrowserPanel from './DatasetBrowserPanel'
import type { NodeCookState } from '../types'
import { LIVE_STREAM_NODE_TYPES } from '../liveNodeTypes'

const TOOLBOX_NEW_HANDLE_COLOR = '#ef444488'

// Widest a live camera preview grows its node to on the first frame.
const STREAM_FIT_MAX_WIDTH = 480

// A node shows at most one status badge. Every state below renders through the
// same popup so two conditions can never stack at the same coordinates.
type BadgeTone = 'ok' | 'warn' | 'err' | 'muted'
const BADGE_TONE: Record<BadgeTone, string> = {
  ok: 'var(--ok)',
  warn: 'var(--warn)',
  err: 'var(--err)',
  muted: 'var(--tx3)',
}
interface StatusBadge {
  text: string
  tone: BadgeTone
  title: string
  action?: { label: string; pending: boolean; onClick: () => void }
}

// Chat trigger node types → the driver the Start/Stop buttons control.
const TRIGGER_DRIVER: Record<string, string> = {
  SlackMessage: 'slack',
  TelegramMessage: 'telegram',
}

export 
function driverBtn(color: string, disabled = false): React.CSSProperties {
  return {
    flex: 1,
    padding: '3px 8px',
    borderRadius: 5,
    border: `1px solid ${color}`,
    background: 'transparent',
    color,
    fontSize: 13,
    fontWeight: 600,
    fontFamily: 'var(--font-ui)',
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.6 : 1,
  }
}

interface NodeData extends NodeCookState {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  params: Record<string, unknown>
  live_capable?: boolean
  variadic_input?: { prefix: string; type: string } | null
  promoted_inputs?: string[] | null
  promoted_outputs?: string[] | null
}

function formatPortValue(v: unknown): string {
  if (v === undefined || v === null) return ''
  if (typeof v === 'string' && v.startsWith('data:image/')) {
    return `[image data URL, ${v.length} characters]`
  }
  return typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)
}

function PortRow({
  nodeId,
  name,
  type,
  dir,
  result,
  onRemove,
}: {
  nodeId: string
  name: string
  type: string
  dir: 'input' | 'output'
  result?: unknown
  onRemove?: () => void
}) {
  const [hovering, setHovering] = useState(false)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const [copyMenu, setCopyMenu] = useState<{ x: number; y: number } | null>(null)
  const closeTimer = useRef<number | null>(null)
  const color   = portColor(type)
  const visualColor = portVisualColor(type)
  const isInput = dir === 'input'
  const resultText = result !== undefined ? formatPortValue(result) : ''
  const popupText = `${dir} · ${name} · ${type}${resultText ? `\n${resultText}` : ''}`
  const displayName = portDisplayName(name, dir)

  const openTooltip = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
    setHovering(true)
  }
  const copyPort = async () => {
    try {
      await copyTextToClipboard(resultText || popupText)
      setCopyState('copied')
      setCopyMenu(null)
      window.setTimeout(() => setCopyState('idle'), 1200)
    } catch (err) {
      setCopyState('error')
      console.error('Failed to copy port value', err)
    }
  }
  const openCopyMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    openTooltip()
    setCopyMenu({ x: e.clientX, y: e.clientY })
  }
  const closeTooltipSoon = () => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(() => {
      closeTimer.current = null
      setHovering(false)
      setCopyMenu(null)
    }, 220)
  }

  useEffect(() => () => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current)
  }, [])

  return (
    <div
      className="bn-port-row"
      data-direction={dir}
      onMouseEnter={() => window.dispatchEvent(new CustomEvent('blacknode:port-hover', {
        detail: { nodeId, port: name, dir },
      }))}
      onMouseLeave={() => window.dispatchEvent(new CustomEvent('blacknode:port-hover', {
        detail: null,
      }))}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: isInput ? 'flex-start' : 'flex-end',
        padding: isInput ? `4px 10px 4px ${onRemove ? 28 : 12}px` : '4px 12px 4px 10px',
        position: 'relative',
        gap: 5,
        '--bn-port-color': visualColor,
      } as React.CSSProperties}
    >
      <Handle
        type={isInput ? 'target' : 'source'}
        position={isInput ? Position.Left : Position.Right}
        id={name}
        onMouseEnter={openTooltip}
        onMouseLeave={closeTooltipSoon}
        onContextMenu={openCopyMenu}
        style={{
          [isInput ? 'left' : 'right']: -5,
          background: color,
          width: 9, height: 9,
          border: `1.5px solid ${color}`,
          borderRadius: 3,
          boxShadow: hovering ? `0 0 6px ${color}` : undefined,
          transition: 'box-shadow 0.15s',
        }}
      />
      {onRemove && (
        <button
          onClick={e => { e.stopPropagation(); onRemove() }}
          onMouseDown={e => e.stopPropagation()}
          title="Remove slot"
          style={{
            position: 'absolute',
            left: 7,
            background: 'transparent',
            border: 'none',
            color: 'var(--tx3)',
            cursor: 'pointer',
            fontSize: 14,
            lineHeight: 1,
            padding: '0 2px',
            opacity: hovering ? 1 : 0.55,
          }}
        >
          x
        </button>
      )}
      <span style={{
        flex: '0 1 auto',
        minWidth: 0,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        color: 'var(--tx2)',
        fontSize: 14,
        fontFamily: 'var(--font-ui)',
      }}>
        {displayName}
      </span>
      <span
        className="bn-port-type-pill"
        title={`${displayName}: ${type}`}
        style={{ color: visualColor, borderColor: `${visualColor}66`, background: `${visualColor}16` }}
      >
        {type.toUpperCase()}
      </span>
      {hovering && (type || resultText) && (
        <div
          className="nodrag"
          onMouseEnter={openTooltip}
          onMouseLeave={closeTooltipSoon}
          onMouseDown={e => e.stopPropagation()}
          onClick={e => e.stopPropagation()}
          onContextMenu={openCopyMenu}
          style={{
            position: 'absolute',
            bottom: '100%',
            [isInput ? 'left' : 'right']: 10,
            zIndex: 100,
            width: 'min(420px, calc(100vw - 32px))',
            padding: '8px 10px',
            borderRadius: 8,
            border: `1px solid ${resultText ? 'var(--ok)' : color}`,
            background: 'var(--panel)',
            boxShadow: '0 8px 24px rgba(0,0,0,.3)',
            pointerEvents: 'auto',
            userSelect: 'text',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: resultText ? 6 : 0 }}>
            <div style={{
              minWidth: 0,
              flex: 1,
              fontSize: 13,
              color,
              fontFamily: 'var(--font-ui)',
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}>
              {displayName} · {type}
            </div>
            {resultText && (
              <button
                type="button"
                onMouseDown={e => e.stopPropagation()}
                onClick={e => { e.stopPropagation(); void copyPort() }}
                style={{
                  flex: '0 0 auto',
                  padding: '3px 7px',
                  borderRadius: 5,
                  border: '1px solid var(--border)',
                  background: 'var(--panel2)',
                  color: copyState === 'error' ? 'var(--err)' : copyState === 'copied' ? 'var(--ok)' : 'var(--tx1)',
                  cursor: 'pointer',
                  fontSize: 13,
                  fontFamily: 'var(--font-ui)',
                }}
              >
                {copyState === 'copied' ? 'Copied' : copyState === 'error' ? 'Copy failed' : 'Copy value'}
              </button>
            )}
          </div>
          <div style={{ color: 'var(--tx3)', fontSize: 11, marginBottom: resultText ? 6 : 0 }}>
            {portDisplayHint(name, dir)}
          </div>
          {resultText && (
            <div
              style={{
                fontSize: 14,
                color: 'var(--tx1)',
                fontFamily: 'var(--font-mono)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                maxHeight: 280,
                overflow: 'auto',
              }}
            >
              {resultText}
            </div>
          )}
          {copyMenu && (
            <div
              className="nodrag"
              onMouseEnter={openTooltip}
              onMouseDown={e => e.stopPropagation()}
              onClick={e => e.stopPropagation()}
              onContextMenu={e => { e.preventDefault(); e.stopPropagation() }}
              style={{
                position: 'fixed',
                top: copyMenu.y,
                left: copyMenu.x,
                zIndex: 1000,
                minWidth: 150,
                padding: 4,
                borderRadius: 7,
                border: '1px solid var(--border)',
                background: 'var(--panel)',
                boxShadow: '0 8px 24px rgba(0,0,0,.4)',
              }}
            >
              <button
                type="button"
                onClick={() => { void copyPort() }}
                style={{
                  width: '100%',
                  padding: '6px 9px',
                  border: 'none',
                  borderRadius: 5,
                  background: 'transparent',
                  color: 'var(--tx1)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontSize: 14,
                  fontFamily: 'var(--font-ui)',
                }}
              >
                Copy value
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const isImageSrc = (v: unknown): v is string =>
  typeof v === 'string' && (v.startsWith('data:image/') || /^https?:\/\//i.test(v))

const normalizedImageSrc = (v: unknown): string | null => {
  if (isImageSrc(v)) return v
  if (typeof v !== 'string') return null
  const svg = v.trim()
  return svg.startsWith('<svg') && svg.endsWith('</svg>')
    ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
    : null
}

const imgBtn: React.CSSProperties = {
  background: 'var(--lift)', border: '1px solid var(--line)', borderRadius: 5,
  color: 'var(--tx1)', fontFamily: 'var(--font-ui)', fontSize: 13, fontWeight: 600,
  padding: '3px 9px', cursor: 'pointer',
}

const previewImg: React.CSSProperties = {
  width: '100%',
  height: '100%',
  minWidth: 0,
  minHeight: 0,
  objectFit: 'contain',
  display: 'block',
}

const widthFitResultImg: React.CSSProperties = {
  width: '100%',
  height: 'auto',
  minWidth: 0,
  display: 'block',
}

const imageResultWrap: React.CSSProperties = {
  padding: '0 10px 10px',
  flex: 1,
  minHeight: 70,
  display: 'grid',
  placeItems: 'center',
  overflow: 'hidden',
}

const imagePreviewFrame: React.CSSProperties = {
  width: '100%',
  height: '100%',
  minHeight: 56,
  display: 'grid',
  placeItems: 'center',
  overflow: 'hidden',
  borderRadius: 6,
  border: '1px solid var(--line2)',
  background: 'var(--lift)',
  boxSizing: 'border-box',
}

function NodeImageInput({
  value,
  onChange,
  onFitNatural,
}: {
  value: unknown
  onChange: (v: string) => void
  onFitNatural: (width: number, height: number) => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const v = typeof value === 'string' ? value : ''
  const hasImage = isImageSrc(v)
  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => onChange(String(r.result))
    r.readAsDataURL(f)
    e.target.value = ''
  }
  return (
    <div
      style={{
        padding: '2px 10px 8px',
        display: 'flex',
        flexDirection: 'column',
        flex: hasImage ? 1 : undefined,
        minHeight: 0,
      }}
    >
      <div
        className="nodrag"
        style={{ display: 'flex', gap: 6, marginBottom: hasImage ? 6 : 0, flexShrink: 0 }}
        onMouseDown={e => e.stopPropagation()}
      >
        <button className="nodrag" style={imgBtn}
          onClick={e => { e.stopPropagation(); fileRef.current?.click() }}>Browse…</button>
        {v && (
          <button className="nodrag" style={{ ...imgBtn, color: 'var(--err)' }}
            onClick={e => { e.stopPropagation(); onChange('') }}>Clear</button>
        )}
        <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={pick} />
      </div>
      {hasImage && (
        <div style={imagePreviewFrame}>
          <img
            src={v}
            alt=""
            draggable={false}
            style={previewImg}
            onDragStart={e => e.preventDefault()}
            onDoubleClick={e => {
              e.stopPropagation()
              onFitNatural(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)
            }}
          />
        </div>
      )}
    </div>
  )
}

function BlackNode({ id, data, selected }: NodeProps<NodeData>) {
  const cookNode    = useStore(s => s.cookNode)
  const updateParam = useStore(s => s.updateParam)
  const controlNode = useStore(s => s.controlNode)
  const pickDirectory = useStore(s => s.pickDirectory)
  const resizeNode  = useStore(s => s.resizeNode)
  const disconnectEdge = useStore(s => s.disconnectEdge)
  const edges       = useStore(s => s.edges)
  const nodes       = useStore(s => s.nodes)
  const driverStatus = useStore(s => s.driverStatus)
  const drivers     = useStore(s => s.drivers)
  const startDriver = useStore(s => s.startDriver)
  const stopDriver  = useStore(s => s.stopDriver)
  const loadDriverStatus = useStore(s => s.loadDriverStatus)
  const workflowMetadata = useStore(s => s.workflowMetadata)
  const setWorkflowRequirements = useStore(s => s.setWorkflowRequirements)
  const openGraphAsTab = useStore(s => s.openGraphAsTab)
  const qualifiedType = useQualifiedTypeLabel(data.type)
  const driverName  = TRIGGER_DRIVER[data.type]
  const driverLive  = driverName ? Boolean(driverStatus[driverName]?.live) : false
  const driverNotInstalled = driverName ? drivers[driverName]?.packages_installed === false : false
  const [driverPending, setDriverPending] = useState<null | 'start' | 'stop'>(null)
  const [streamStopPending, setStreamStopPending] = useState(false)
  const [streamStartPending, setStreamStartPending] = useState(false)
  const [rosRunStopPending, setRosRunStopPending] = useState(false)
  const [rosPythonStopPending, setRosPythonStopPending] = useState(false)
  const [topicPublisherStopPending, setTopicPublisherStopPending] = useState(false)
  const [topicSubscriberStopPending, setTopicSubscriberStopPending] = useState(false)
  const [manualMovePending, setManualMovePending] = useState<null | 'release' | 'monitor' | 'hold'>(null)
  const [calibrationPending, setCalibrationPending] = useState<null | 'start' | 'pause' | 'capture_home' | 'finish' | 'cancel'>(null)
  const [episodePending, setEpisodePending] = useState<null | 'start' | 'pause' | 'resume' | 'save' | 'stop' | 'discard'>(null)
  const [trainingPending, setTrainingPending] = useState<null | 'start' | 'stop'>(null)
  const [datasetFolderPending, setDatasetFolderPending] = useState(false)
  const dashboardAutoFitDone = useRef(false)
  const streamFitDone = useRef(false)
  // A camera node picks its device by index today; discovery already knows the
  // names, so offer a pick-by-name menu instead of guessing which index is the
  // real webcam versus a virtual camera with no source.
  const hasCameraSelection = data.type === 'Camera' && (data.inputs ?? []).includes('selection')
  const [cameraList, setCameraList] = useState<Array<{ index: number; label: string }>>([])
  const [cameraScanning, setCameraScanning] = useState(false)
  const loadCameras = async () => {
    setCameraScanning(true)
    try {
      const res = await api.listCameras()
      setCameraList(res.cameras.map(c => ({ index: c.index, label: c.label })))
    } catch { /* leave the list empty; the number field still works */ }
    finally { setCameraScanning(false) }
  }
  // DetectionYolo picks its model by name; offer built-in weights plus any
  // custom model dropped in .blacknode/models, rather than a typed path.
  const hasModelPicker = data.type === 'DetectionYolo' && (data.inputs ?? []).includes('model')
  // TrackingObject hot-updates these while the stream runs (no recook), so expose
  // them as live sliders right on the node.
  const isTrackingObject = data.type === 'TrackingObject'
  const isJointSliders = data.type === 'ROS2JointSliders'
  const [pingPending, setPingPending] = useState(false)
  const pingRobot = async () => {
    setPingPending(true)
    try {
      const res = await controlNode(id, 'ping')
      const report = (res?.outputs?.report as string) ?? ''
      const moved = res?.outputs?.moved === true
      // Report through a toast, not inline text — the Robot node auto-sizes to
      // its content, so a message on the node would grow it.
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: { kind: moved ? 'info' : 'error', title: moved ? 'Robot ping' : 'Ping failed', message: report },
      }))
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: { kind: 'error', title: 'Ping failed', message: err instanceof Error ? err.message : String(err) },
      }))
    } finally {
      setPingPending(false)
    }
  }
  // YOLO-World is open-vocabulary: it detects whatever classes you type. Show the
  // classes field only for those weights, where it actually does something.
  const isWorldModel = /world/i.test(String(data.params?.model ?? ''))
  const [modelList, setModelList] = useState<{ builtin: string[]; custom: string[]; dir: string }>({ builtin: [], custom: [], dir: '' })
  const loadModels = async () => {
    try {
      const res = await api.listYoloModels()
      setModelList({ builtin: res.builtin, custom: res.custom, dir: res.models_dir })
    } catch { /* the typed field still works */ }
  }
  // A browser <img> pointed at an MJPEG stream keeps showing the last frame of
  // its old connection when the src does not change - so restarting a stream on
  // the same URL looks frozen, a "snapshot". Bump a key when a new stream
  // starts (turned on, or a different URL) to force a fresh connection, but not
  // on the per-frame runtime updates that would otherwise remount constantly.
  const [streamConnKey, setStreamConnKey] = useState(0)
  const prevStreamingRef = useRef(false)
  const prevStreamUrlRef = useRef('')
  const { getNode } = useReactFlow()
  const updateNodeInternals = useUpdateNodeInternals()
  const color       = headerColor(data.type)
  const isToolBox   = data.type === 'ToolBox'
  const isRobotJointDefinition = data.type === 'RobotJointDefinition'
  const isRobotJointList = data.type === 'RobotJointList'
  const variadicInput = data.variadic_input ?? null
  const isVariadic = Boolean(variadicInput)
  const isManualMove = (
    data.type === 'ROS2ManualMove'
    || data.type === 'RobotCalibrationControl'
  )
  const isRobot = data.type === 'Robot'
  const robotProfileId = String(data.params?.profile_id ?? 'auto').trim() || 'auto'
  const requiredCapabilities = Array.isArray(workflowMetadata.required_capabilities)
    ? workflowMetadata.required_capabilities.map(String)
    : []
  const selectedRobotCalibration = (
    workflowMetadata.device_calibration
    && typeof workflowMetadata.device_calibration === 'object'
  )
    ? workflowMetadata.device_calibration
    : null
  const [robotProfiles, setRobotProfiles] = useState<DeviceRobotProfile[]>([])
  const [robotCalibrations, setRobotCalibrations] = useState<DeviceCalibrationCandidate[]>([])
  const [robotCalibrationsLoading, setRobotCalibrationsLoading] = useState(false)
  const [robotProfilePending, setRobotProfilePending] = useState(false)
  const [robotProfileEditPending, setRobotProfileEditPending] = useState(false)
  const [robotCalibrationPending, setRobotCalibrationPending] = useState(false)
  const [robotCalibrationError, setRobotCalibrationError] = useState('')
  const matchingRobotCalibrations = robotCalibrations.filter(
    calibration => !robotProfileId || calibration.profile_id === robotProfileId,
  )
  const selectedRobotCalibrationKey = selectedRobotCalibration
    ? `${selectedRobotCalibration.profile_id}\u0000${selectedRobotCalibration.hardware_id}`
    : ''
  const selectedRobotCalibrationCandidate = robotCalibrations.find(
    calibration => (
      calibration.profile_id === selectedRobotCalibration?.profile_id
      && calibration.hardware_id === selectedRobotCalibration?.hardware_id
    ),
  )
  const selectableRobotProfiles = robotProfiles.filter(profile => profile.id !== 'auto')
  const robotProfileChoices = Array.from(new Map([
    ...(robotProfileId !== 'auto'
      ? [[
          robotProfileId,
          selectableRobotProfiles.find(profile => profile.id === robotProfileId) ?? {
            id: robotProfileId,
            name: robotProfileId,
            saved: false,
            calibration_count: 0,
          },
        ] as const]
      : []),
    ...selectableRobotProfiles.map(profile => [profile.id, profile] as const),
  ]).values())
  const selectedRobotProfileChoice = robotProfileChoices.find(
    profile => profile.id === robotProfileId,
  )
  const appliedRobotCalibration = (
    data.portResults?.calibration
    && typeof data.portResults.calibration === 'object'
  ) ? data.portResults.calibration as Record<string, unknown> : null
  const appliedRobotCalibrationCandidate = appliedRobotCalibration
    ? robotCalibrations.find(calibration => (
        calibration.profile_id === String(appliedRobotCalibration.profile_id || '')
        && calibration.hardware_id === String(appliedRobotCalibration.hardware_id || '')
      ))
    : undefined
  const loadRobotSetup = async () => {
    if (!isRobot) return
    setRobotCalibrationsLoading(true)
    setRobotCalibrationError('')
    try {
      const result = await api.listGraphCalibrations()
      setRobotProfiles(result.profiles ?? [])
      setRobotCalibrations(result.calibrations ?? [])
    } catch (err) {
      setRobotCalibrationError(err instanceof Error ? err.message : String(err))
    } finally {
      setRobotCalibrationsLoading(false)
    }
  }
  useEffect(() => {
    if (!isRobot) return
    let cancelled = false
    setRobotCalibrationsLoading(true)
    setRobotCalibrationError('')
    void api.listGraphCalibrations()
      .then(result => {
        if (!cancelled) {
          setRobotProfiles(result.profiles ?? [])
          setRobotCalibrations(result.calibrations ?? [])
        }
      })
      .catch(err => {
        if (!cancelled) {
          setRobotCalibrationError(err instanceof Error ? err.message : String(err))
        }
      })
      .finally(() => {
        if (!cancelled) setRobotCalibrationsLoading(false)
      })
    return () => { cancelled = true }
  }, [isRobot, robotProfileId])
  useEffect(() => {
    if (!isRobot) return
    const refresh = () => { void loadRobotSetup() }
    window.addEventListener('blacknode:robot-profiles-changed', refresh)
    return () => window.removeEventListener('blacknode:robot-profiles-changed', refresh)
  }, [isRobot])
  useEffect(() => {
    if (
      !isRobot
      || selectedRobotCalibration
      || !appliedRobotCalibrationCandidate
      || robotCalibrationPending
    ) return
    let cancelled = false
    setRobotCalibrationPending(true)
    setRobotCalibrationError('')
    void setWorkflowRequirements(requiredCapabilities, {
      profile_id: appliedRobotCalibrationCandidate.profile_id,
      hardware_id: appliedRobotCalibrationCandidate.hardware_id,
    }).catch(err => {
      if (!cancelled) {
        setRobotCalibrationError(err instanceof Error ? err.message : String(err))
      }
    }).finally(() => {
      if (!cancelled) setRobotCalibrationPending(false)
    })
    return () => { cancelled = true }
  }, [
    isRobot,
    selectedRobotCalibrationKey,
    appliedRobotCalibrationCandidate?.profile_id,
    appliedRobotCalibrationCandidate?.hardware_id,
  ])
  const selectRobotProfile = async (profileId: string) => {
    if (!profileId || profileId === robotProfileId) return
    setRobotProfilePending(true)
    setRobotCalibrationError('')
    try {
      await updateParam(id, 'profile_id', profileId)
      if (
        selectedRobotCalibration
        && selectedRobotCalibration.profile_id !== profileId
      ) {
        await setWorkflowRequirements(requiredCapabilities, null)
      }
      await loadRobotSetup()
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setRobotCalibrationError(message)
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: { kind: 'error', title: 'Robot profile selection failed', message },
      }))
    } finally {
      setRobotProfilePending(false)
    }
  }
  const editRobotProfile = async () => {
    if (!robotProfileId || robotProfileId === 'auto' || robotProfileEditPending) return
    setRobotProfileEditPending(true)
    try {
      const graph = await api.robotProfileEditorGraph(robotProfileId)
      const profile = selectableRobotProfiles.find(item => item.id === robotProfileId)
      await openGraphAsTab(`Edit ${profile?.name || robotProfileId}`, graph)
      window.dispatchEvent(new Event('blacknode:fit-view'))
    } catch (err) {
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: {
          kind: 'error',
          title: 'Could not open profile editor',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setRobotProfileEditPending(false)
    }
  }
  const selectRobotCalibration = async (value: string) => {
    const calibration = robotCalibrations.find(
      item => `${item.profile_id}\u0000${item.hardware_id}` === value,
    )
    setRobotCalibrationPending(true)
    setRobotCalibrationError('')
    try {
      await setWorkflowRequirements(
        requiredCapabilities,
        calibration
          ? { profile_id: calibration.profile_id, hardware_id: calibration.hardware_id }
          : null,
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setRobotCalibrationError(message)
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: { kind: 'error', title: 'Calibration selection failed', message },
      }))
    } finally {
      setRobotCalibrationPending(false)
    }
  }
  const isRobotCalibration = data.type === 'RobotCalibrationRecorder'
  const isEpisodeRecorder = data.type === 'EpisodeRecorder'
  const isDatasetCreate = data.type === 'DatasetCreate'
  const isDatasetBrowser = data.type === 'DatasetBrowser'
  const isACTTraining = data.type === 'ACTTraining'
  const availableInputs = isRobotJointList
    ? (data.inputs ?? []).filter(port => edges.some(edge => edge.target === id && edge.targetHandle === port))
    : isVariadic
      ? (data.inputs ?? []).filter(port => {
          const dynamic = new RegExp(`^${(variadicInput?.prefix || 'item').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}_[0-9]+$`).test(port)
          return !dynamic || edges.some(edge => edge.target === id && edge.targetHandle === port)
        })
      : (data.inputs ?? [])
  const visibleInputs = availableInputs.filter(port =>
    edges.some(edge => edge.target === id && edge.targetHandle === port)
    || data.promoted_inputs == null
    || data.promoted_inputs.includes(port)
  )
  const visibleOutputs = (data.outputs ?? []).filter(port =>
    edges.some(edge => edge.source === id && edge.sourceHandle === port)
    || data.promoted_outputs == null
    || data.promoted_outputs.includes(port)
  )
  const usedJointNumbers = new Set(visibleInputs.map(port => {
    const value = Number(port.split('_').pop())
    return Number.isFinite(value) ? value : 0
  }))
  let nextJointNumber = 1
  while (usedJointNumbers.has(nextJointNumber)) nextJointNumber += 1
  const variadicPrefix = variadicInput?.prefix || 'item'
  const usedVariadicNumbers = new Set(visibleInputs.map(port => {
    const match = port.match(new RegExp(`^${variadicPrefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}_(\\d+)$`))
    return match ? Number(match[1]) : 0
  }))
  let nextVariadicNumber = 1
  while (usedVariadicNumbers.has(nextVariadicNumber)) nextVariadicNumber += 1
  const inputsKey = visibleInputs.join('|')
  const outputsKey = visibleOutputs.join('|')
  // Explicit OutputImage nodes always render their image. Dashboard producers
  // also render their dashboard image when that port is terminal, so a graph
  // can present status in place without requiring a redundant OutputImage.
  // Once dashboard is wired downstream, the inline panel disappears and the
  // connected node owns presentation instead.
  const nodeImage = (): string | null => {
    const cookedImage = normalizedImageSrc(data.cookResult)
    if (cookedImage) return cookedImage
    for (const v of Object.values(data.portResults ?? {})) {
      const image = normalizedImageSrc(v)
      if (image) return image
    }
    return null
  }
  const imageResult = !data.cookError ? nodeImage() : null
  const inlineDashboardPort = (data.outputs ?? []).find(port =>
    port === 'dashboard'
    && data.output_types?.[port] === 'Image'
    && !edges.some(edge => edge.source === id && edge.sourceHandle === port)
    && normalizedImageSrc(data.portResults?.[port]) !== null
  )
  const inlineDashboardImage = inlineDashboardPort
    ? normalizedImageSrc(data.portResults?.[inlineDashboardPort])
    : null
  // Stream nodes show their own picture in place: the live MJPEG URL while
  // streaming, or the single frame a one-shot run captured. Without this a
  // camera node renders only a STREAMING badge and the video is visible only
  // if the graph happens to wire a separate OutputImage downstream.
  const streamPreview = LIVE_STREAM_NODE_TYPES.has(data.type)
    ? normalizedImageSrc(data.portResults?.preview)
    : null
  const showImageResult = data.type === 'OutputImage'
    ? imageResult
    : streamPreview ?? (isImageSrc(inlineDashboardImage) ? inlineDashboardImage : null)
  const streamUrl = typeof data.portResults?.stream_url === 'string' ? data.portResults.stream_url : ''
  const streamActive = LIVE_STREAM_NODE_TYPES.has(data.type) && data.portResults?.streaming === true && streamUrl.length > 0
  const manualMoveLive = isManualMove && data.portResults?.live === true
  const manualMoveReady = manualMoveLive && data.portResults?.data_ready === true
  const manualMoveMode = data.portResults?.mode === 'released' ? 'RELEASED' : 'HOLD'
  const manualMoveJointCount = Array.isArray(data.portResults?.joints) ? data.portResults.joints.length : 0
  const manualMovePoseEntries = isManualMove && data.portResults?.pose && typeof data.portResults.pose === 'object'
    ? Object.entries(data.portResults.pose as Record<string, unknown>)
      .filter((entry): entry is [string, number] => typeof entry[1] === 'number')
      .sort(([left], [right]) => left.localeCompare(right))
    : []
  const manualMoveWarnings = isManualMove && Array.isArray(data.portResults?.warnings)
    ? data.portResults.warnings.length
    : 0
  const manualMoveReport = isManualMove && (
    data.portResults?.command_ok === false || manualMoveWarnings > 0
  )
    ? String(data.portResults?.report ?? '')
    : ''
  const selectedManualAction = String(data.params?.action ?? 'check').toLowerCase()
  const releaseSelected = selectedManualAction === 'release' || selectedManualAction === 'enter'
  const holdSelected = selectedManualAction === 'hold' || selectedManualAction === 'exit'
  const monitorSelected = !releaseSelected && !holdSelected
  const manualReleaseMismatch = isManualMove
    && releaseSelected
    && data.portResults?.torque_enabled === true
  const manualHoldMismatch = isManualMove
    && holdSelected
    && data.portResults?.torque_enabled === false
  const calibrationActive = isRobotCalibration && data.portResults?.active === true
  const calibrationState = isRobotCalibration ? String(data.portResults?.state ?? 'idle') : 'idle'
  const calibrationPaused = calibrationState === 'paused'
  const calibrationDataReady = isRobotCalibration && data.portResults?.data_ready === true
  const calibrationSamples = isRobotCalibration && typeof data.portResults?.samples === 'number'
    ? data.portResults.samples
    : 0
  const calibrationCapturingJoint = isRobotCalibration ? String(data.portResults?.capturing_joint ?? '') : ''
  const calibrationRangeUpdates = isRobotCalibration && data.portResults?.range_updates && typeof data.portResults.range_updates === 'object'
    ? data.portResults.range_updates as Record<string, { kind?: string; at?: number }>
    : {}
  const latestCalibrationRangeUpdate = Object.entries(calibrationRangeUpdates)
    .filter(([, update]) => Date.now() / 1000 - Number(update?.at ?? 0) <= 1.5)
    .sort(([, a], [, b]) => Number(b?.at ?? 0) - Number(a?.at ?? 0))[0]
  const calibrationSaved = isRobotCalibration && (data.portResults?.saved === true || calibrationState === 'saved')
  const episodeRunning = isEpisodeRecorder && data.portResults?.running === true
  const episodeRecording = isEpisodeRecorder && data.portResults?.recording === true
  const episodePaused = isEpisodeRecorder && data.portResults?.paused === true
  const episodeFrameCount = isEpisodeRecorder ? Number(data.portResults?.frame_count ?? 0) : 0
  const episodeDroppedFrames = isEpisodeRecorder ? Number(data.portResults?.dropped_frames ?? 0) : 0
  const episodeDuration = isEpisodeRecorder ? Number(data.portResults?.duration_seconds ?? 0) : 0
  const episodeLastError = isEpisodeRecorder && data.portResults?.status && typeof data.portResults.status === 'object'
    ? String((data.portResults.status as Record<string, unknown>).last_error ?? '')
    : ''
  const episodeRecoverable = isEpisodeRecorder && data.portResults?.status && typeof data.portResults.status === 'object'
    ? (data.portResults.status as Record<string, unknown>).recoverable === true
    : false
  const episodeStoragePath = isEpisodeRecorder && data.portResults?.status && typeof data.portResults.status === 'object'
    ? String(
        (data.portResults.status as Record<string, unknown>).saved_path
        ?? (data.portResults.status as Record<string, unknown>).work_path
        ?? (data.portResults.status as Record<string, unknown>).dataset_path
        ?? (data.portResults.dataset && typeof data.portResults.dataset === 'object'
          ? (data.portResults.dataset as Record<string, unknown>).path
          : '')
        ?? ''
      )
    : ''
  const episodeInputsReady = isEpisodeRecorder
    && edges.some(edge => edge.target === id && edge.targetHandle === 'dataset')
    && edges.some(edge => edge.target === id && edge.targetHandle === 'robot_stream')
    && edges.some(edge => edge.target === id && (edge.targetHandle === 'camera_stream' || edge.targetHandle === 'camera_streams'))
  const trainingRunning = isACTTraining && data.portResults?.running === true
  const trainingPhase = isACTTraining ? String(data.portResults?.phase ?? 'not started') : ''
  const trainingStopping = trainingRunning && trainingPhase === 'stopping'
  const trainingStep = isACTTraining ? Number(data.portResults?.step ?? 0) : 0
  const trainingStatus = isACTTraining && data.portResults?.status && typeof data.portResults.status === 'object'
    ? data.portResults.status as Record<string, unknown>
    : {}
  const trainingSteps = Number(trainingStatus.steps ?? data.params?.steps ?? 0)
  const trainingProgress = trainingSteps > 0 ? Math.max(0, Math.min(1, trainingStep / trainingSteps)) : 0
  const datasetRoot = isDatasetCreate ? String(data.params?.root ?? '').trim() : ''
  const datasetId = isDatasetCreate ? String(data.params?.dataset_id ?? 'dataset').trim() || 'dataset' : ''
  const datasetResolvedPath = isDatasetCreate && typeof data.portResults?.path === 'string'
    ? data.portResults.path
    : ''
  const hasLiveOutput = data.live_capable === true && (data.outputs ?? []).includes('live')
  const liveStateReport = hasLiveOutput ? String(data.portResults?.report ?? '').trim() : ''
  const liveServiceRunning = hasLiveOutput && data.portResults?.running === true
  const liveBlocked = liveServiceRunning
    && data.portResults?.live !== true
    && /^(blocked|failed|error)\b/i.test(liveStateReport)
  const liveWaiting = liveServiceRunning && data.portResults?.live !== true && !liveBlocked
  const liveStateReason = liveStateReport
    .replace(/^(blocked|failed|error)\s*:\s*/i, '')
    .trim()
  const genericNodeLive = data.live_capable === true && data.portResults?.live === true && !manualMoveLive && !streamActive
  // StreamPublisher gets its own Go live / Stop controls, so it should never fall
  // back to the generic "snapshot" badge — that badge is what read as "broken".
  const streamStartable = data.type === 'StreamPublisher' && !streamActive
  const snapshotResult = data.live_capable === true
    && !isACTTraining
    && !streamActive
    && !streamStartable
    && !manualMoveLive
    && !genericNodeLive
    && !liveBlocked
    && !liveWaiting
    && data.portResults?.running !== true
    && !data.cooking
    // Stream nodes are started and stopped deliberately, so "not updating" is
    // the state the operator asked for, not a warning. Keyed on the node type
    // rather than the preview: stopping clears the preview, which would
    // otherwise let this badge reappear exactly when it is least wanted.
    && !LIVE_STREAM_NODE_TYPES.has(data.type)
    && Object.keys(data.portResults ?? {}).length > 0
  const rosRunActive = data.type === 'ROS2Run' && data.portResults?.running === true
  const rosRunId = typeof data.portResults?.run_id === 'string' ? data.portResults.run_id : 'ros2_run'
  const rosPythonActive = data.type === 'ROS2PythonNode' && data.portResults?.running === true
  const rosPythonRunId = String(data.params?.run_id ?? data.portResults?.run_id ?? 'ros2_python_node')
  const rosPythonSource = String(
    data.params?.source_mode === 'inline'
      ? 'inline code'
      : data.params?.script_path ?? data.portResults?.script ?? 'Python script',
  )
  const topicPublisherActive = data.type === 'ROS2TopicPublisher' && data.portResults?.running === true
  const topicPublisherName = String(data.params?.node_name ?? '').trim().replace(/^\/+/, '')
  const topicPublisherTopic = String(data.params?.topic ?? '/chatter').trim() || '/chatter'
  const topicSubscriberActive = (data.type === 'ROS2TopicSubscriber' || data.type === 'ROS2')
    && data.portResults?.running === true
  const topicSubscriberName = String(
    data.params?.node_name ?? (data.type === 'ROS2' ? 'blacknode_ros2_topic' : 'blacknode_subscriber')
  ).trim().replace(/^\/+/, '')
  const topicSubscriberTopic = String(
    data.params?.topic ?? (data.type === 'ROS2' ? '/scan' : '/chatter')
  ).trim() || (data.type === 'ROS2' ? '/scan' : '/chatter')

  // Ordered by urgency: a running process outranks a waiting one, which
  // outranks a passive "this result is stale" note.
  const statusBadge: StatusBadge | null =
    streamActive ? {
      text: 'STREAMING',
      tone: 'ok',
      title: streamUrl ? `Live stream: ${streamUrl}` : 'Live image stream is running',
      action: {
        label: streamStopPending ? 'Stopping...' : 'Stop stream',
        pending: streamStopPending,
        onClick: () => { void onStopImageStream() },
      },
    }
    : rosRunActive ? {
      text: 'ROS2 RUNNING',
      tone: 'ok',
      title: `ROS 2 run process is active: ${rosRunId}`,
      action: {
        label: rosRunStopPending ? 'Stopping...' : 'Stop run',
        pending: rosRunStopPending,
        onClick: () => { void onStopROS2Run() },
      },
    }
    : rosPythonActive ? {
      text: 'ROS2 PYTHON RUNNING',
      tone: 'ok',
      title: `${rosPythonRunId} is running from ${rosPythonSource}`,
      action: {
        label: rosPythonStopPending ? 'Stopping...' : 'Stop',
        pending: rosPythonStopPending,
        onClick: () => { void onStopROS2PythonNode() },
      },
    }
    : topicPublisherActive ? {
      text: 'LIVE • PUBLISHING',
      tone: 'ok',
      title: `${topicPublisherName ? `/${topicPublisherName} is` : 'ROS 2 node is'} publishing on ${topicPublisherTopic}`,
      action: {
        label: topicPublisherStopPending ? 'Stopping...' : 'Stop',
        pending: topicPublisherStopPending,
        onClick: () => { void onStopTopicPublisher() },
      },
    }
    : topicSubscriberActive ? {
      text: 'LIVE • SUBSCRIBING',
      tone: 'ok',
      title: `/${topicSubscriberName || 'blacknode_subscriber'} is subscribing to ${topicSubscriberTopic}`,
      action: {
        label: topicSubscriberStopPending ? 'Stopping...' : 'Stop',
        pending: topicSubscriberStopPending,
        onClick: () => { void onStopTopicSubscriber() },
      },
    }
    : liveBlocked || liveWaiting ? {
      text: `${liveBlocked ? 'BLOCKED' : 'LIVE • WAITING'}`
        + (liveStateReason ? ` • ${liveStateReason}` : liveWaiting ? ' • waiting for source data' : ''),
      tone: liveBlocked ? 'err' : 'warn',
      title: liveStateReport || (liveBlocked ? 'Live service is blocked' : 'Live service is waiting for source data'),
    }
    : manualMoveLive ? {
      text: manualMoveReady
        ? `LIVE • ${manualMoveMode} • ${manualMoveJointCount} JOINTS`
        : 'LIVE • WAITING FOR JOINT DATA',
      tone: 'ok',
      title: manualMoveReady
        ? `Live pose monitor: ${manualMoveJointCount} joint(s)`
        : 'Live monitor is running; waiting for the first joint-state message',
    }
    : genericNodeLive ? {
      text: 'LIVE • UPDATING',
      tone: 'ok',
      title: 'This node is receiving continuous runtime updates.',
    }
    : snapshotResult ? {
      text: 'SNAPSHOT • NOT UPDATING',
      tone: 'muted',
      title: 'This is the result of one evaluation. It is not updating; use Go live to start supported continuous output.',
    }
    : null
  const headerState = data.cookError || data.replayStatus === 'error' || liveBlocked
    ? { label: 'Error', tone: 'error' }
    : data.cooking || data.replayStatus === 'running' || data.replayStatus === 'model' || data.replayStatus === 'tool'
      ? { label: data.replayStatus === 'model' ? 'Reasoning' : data.replayStatus === 'tool' ? 'Using tool' : 'Running', tone: 'running' }
      : streamActive || rosRunActive || rosPythonActive || topicPublisherActive || topicSubscriberActive || manualMoveLive || genericNodeLive || liveServiceRunning
        ? { label: liveWaiting ? 'Waiting' : 'Live', tone: liveWaiting ? 'waiting' : 'live' }
        : snapshotResult || data.cookResult !== undefined || Object.keys(data.portResults ?? {}).length > 0
          ? { label: 'Ready', tone: 'ready' }
          : { label: 'Idle', tone: 'idle' }
  const hoverPreviewImage = streamPreview ?? imageResult
  const hasVisualHoverPreview = /camera|detect|vision|image|track|segment/i.test(data.type)
    && Boolean(hoverPreviewImage)
  const previewFps = Number(data.portResults?.fps ?? data.portResults?.frame_rate ?? 0)
  const previewConfidence = Number(data.portResults?.confidence ?? data.portResults?.score ?? 0)
  const previewWidth = Number(data.portResults?.width ?? data.portResults?.frame_width ?? 0)
  const previewHeight = Number(data.portResults?.height ?? data.portResults?.frame_height ?? 0)
  const nodeStats: Array<{ label: string; tone?: 'live' | 'warn' | 'muted' }> = []
  const addStat = (value: unknown, tone?: 'live' | 'warn' | 'muted') => {
    const text = String(value ?? '').trim()
    if (text && !nodeStats.some(stat => stat.label === text)) nodeStats.push({ label: text, tone })
  }
  if (/camera|stream|video|detect|vision|track|segment/i.test(data.type)) {
    if (previewFps > 0) addStat(`${Math.round(previewFps)} FPS`, 'live')
    if (previewWidth > 0 && previewHeight > 0) addStat(`${previewWidth}×${previewHeight}`)
    if (streamActive) addStat('LIVE', 'live')
  }
  if (/robot|joint|controller|motion|follow/i.test(data.type)) {
    if (typeof data.portResults?.connected === 'boolean') {
      addStat(data.portResults.connected ? 'Connected' : 'Disconnected', data.portResults.connected ? 'live' : 'warn')
    }
    const latency = Number(
      data.portResults?.latency_ms
      ?? data.portResults?.round_trip_ms
      ?? data.portResults?.response_ms
      ?? 0,
    )
    if (latency > 0) addStat(`${Math.round(latency)} ms`)
    const motionState = String(data.portResults?.mode ?? data.portResults?.state ?? '').trim()
    if (motionState && motionState.length <= 18) addStat(motionState)
  }
  if (/agent|reason|llm|model|nim/i.test(data.type)) {
    const modelName = String(data.portResults?.model ?? data.params?.model ?? '').trim()
    if (modelName) addStat(modelName.split('/').pop()?.replace(/^nim:/, '') || modelName)
    const duration = Number(data.replayDurationMs ?? data.portResults?.duration_ms ?? data.portResults?.latency_ms ?? 0)
    if (duration > 0) addStat(`${Math.round(duration)} ms`)
  }
  if (/cuda|gpu|tensor|nvidia/i.test(data.type)) {
    const gpuName = String(
      data.portResults?.gpu_name
      ?? data.portResults?.device_name
      ?? data.portResults?.device
      ?? '',
    ).trim()
    if (gpuName) addStat(gpuName)
    addStat('GPU', 'live')
    const memoryGb = Number(
      data.portResults?.memory_gb
      ?? data.portResults?.vram_gb
      ?? data.portResults?.gpu_memory_gb
      ?? 0,
    )
    if (memoryGb > 0) addStat(`${memoryGb.toFixed(memoryGb >= 10 ? 0 : 1)} GB`)
  }

  const effectivePortType = (portName: string, side: 'input' | 'output'): string => {
    const declared = side === 'input'
      ? (data.input_types?.[portName] ?? 'Any')
      : (data.output_types?.[portName] ?? 'Any')
    if (declared !== 'Any') return declared
    if (side === 'input') {
      const edge = edges.find(e => e.target === id && e.targetHandle === portName)
      if (edge) {
        const src = nodes.find(n => n.id === edge.source)
        const t = src?.data?.output_types?.[edge.sourceHandle!] ?? 'Any'
        if (t !== 'Any') return t
      }
    } else {
      const edge = edges.find(e => e.source === id && e.sourceHandle === portName)
      if (edge) {
        const tgt = nodes.find(n => n.id === edge.target)
        const t = tgt?.data?.input_types?.[edge.targetHandle!] ?? 'Any'
        if (t !== 'Any') return t
      }
    }
    return 'Any'
  }
  const [editingLabel, setEditingLabel] = useState(false)
  const [labelDraft, setLabelDraft] = useState('')
  const label = data.params?.label ? String(data.params.label) : null

  const startRename = (e: React.MouseEvent) => {
    e.stopPropagation()
    setLabelDraft(label ?? data.type)
    setEditingLabel(true)
  }
  const commitRename = () => {
    setEditingLabel(false)
    const v = labelDraft.trim()
    updateParam(id, 'label', v || null).catch(() => {})
  }

  const removeToolSlot = async (port: string) => {
    const edge = edges.find(e => e.target === id && e.targetHandle === port)
    if (edge) await disconnectEdge(edge.id)
  }

  // Poll status quickly until the driver reaches the wanted live state (the
  // subprocess takes a couple seconds to boot + connect before it heartbeats).
  const pollDriverUntil = async (live: boolean) => {
    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 1000))
      await loadDriverStatus()
      if (Boolean(useStore.getState().driverStatus[driverName!]?.live) === live) return
    }
  }
  const onStartDriver = async () => {
    setDriverPending('start')
    const r = await startDriver(driverName!)
    if (!r.ok) {
      setDriverPending(null)
      window.dispatchEvent(new CustomEvent('blacknode:notice', {
        detail: { kind: 'error', title: `Could not start ${driverName}`, message: r.error ?? '' },
      }))
      return
    }
    await pollDriverUntil(true)
    setDriverPending(null)
  }
  const onStopDriver = async () => {
    setDriverPending('stop')
    try {
      await stopDriver(driverName!)
    } finally {
      setDriverPending(null)
    }
  }

  const onStartStream = async () => {
    setStreamStartPending(true)
    try {
      await updateParam(id, 'action', 'start')
      await cookNode(id, 'dashboard')
    } finally {
      setStreamStartPending(false)
    }
  }

  const onStopImageStream = async () => {
    setStreamStopPending(true)
    try {
      await updateParam(id, 'action', 'stop')
      await cookNode(id, 'report')
    } finally {
      try {
        await updateParam(id, 'action', 'start')
      } catch {
        // Keep the stop control responsive even if the editor cannot write the param.
      }
      setStreamStopPending(false)
    }
  }

  const onStopROS2Run = async () => {
    setRosRunStopPending(true)
    try {
      await updateParam(id, 'action', 'stop')
      await cookNode(id, 'report')
    } finally {
      try {
        await updateParam(id, 'action', 'start')
      } catch {
        // Keep the stop control responsive even if the editor cannot write the param.
      }
      setRosRunStopPending(false)
    }
  }

  const onStopROS2PythonNode = async () => {
    setRosPythonStopPending(true)
    try {
      await updateParam(id, 'action', 'stop')
      await cookNode(id, 'report')
    } finally {
      try {
        await updateParam(id, 'action', 'start')
      } catch {
        // The script is already stopped; leave the visual control responsive.
      }
      setRosPythonStopPending(false)
    }
  }

  const onStopTopicPublisher = async () => {
    setTopicPublisherStopPending(true)
    try {
      await updateParam(id, 'action', 'stop')
      await cookNode(id, 'report')
    } finally {
      try {
        await updateParam(id, 'action', 'start')
      } catch {
        // The publisher is already stopped; leave the visual control responsive.
      }
      setTopicPublisherStopPending(false)
    }
  }

  const onStopTopicSubscriber = async () => {
    setTopicSubscriberStopPending(true)
    try {
      await updateParam(id, 'action', 'stop')
      await cookNode(id, 'report')
    } finally {
      try {
        await updateParam(id, 'action', 'start')
      } catch {
        // The subscriber is already stopped; leave the visual control responsive.
      }
      setTopicSubscriberStopPending(false)
    }
  }

  const runManualMoveAction = async (action: 'release' | 'monitor' | 'hold') => {
    if (manualMovePending) return
    if (action === 'release' && !window.confirm(
      'Support the arm before releasing it. This turns motor torque OFF so gravity may move the arm. Continue?'
    )) return
    setManualMovePending(action)
    try {
      const nodeAction = action === 'monitor' ? 'check' : action
      await updateParam(id, 'action', nodeAction)
      // Every manual-mode button keeps the same live pose subscription alive.
      // Treating Hold as a one-shot used to tear down the rosbridge subscriber;
      // a subsequent Monitor/Go live could then reopen onto a stale topic.
      await cookNode(id, 'report', undefined, 'live')
    } finally {
      setManualMovePending(null)
    }
  }

  const runCalibrationAction = async (action: 'start' | 'pause' | 'capture_home' | 'finish' | 'cancel') => {
    if (calibrationPending) return
    if (action === 'start' && !window.confirm(
      'Support the robot and release motor torque before calibration. Calibration records hand-moved positions and never commands motion. Continue?'
    )) return
    if (action === 'finish' && !window.confirm(
      'Save the observed range, captured Home pose, and safety margin for this physical robot?'
    )) return
    setCalibrationPending(action)
    try {
      await updateParam(id, 'action', action)
      // Keep the upstream Manual Move subscription alive while changing the
      // recorder state; live pose samples are pushed into this node.
      await cookNode(id, 'report', undefined, 'live')
    } finally {
      setCalibrationPending(null)
    }
  }

  const runEpisodeAction = async (action: 'start' | 'pause' | 'resume' | 'save' | 'stop' | 'discard') => {
    if (episodePending) return
    if (action === 'discard' && !window.confirm(
      'Discard this incomplete episode and all of its recorded frames? This cannot be undone.'
    )) return
    setEpisodePending(action)
    try {
      try {
        await controlNode(id, action)
      } catch (error) {
        // A fresh graph has no resolved recorder handles yet. Record may cook
        // once to configure them; every subsequent control is runtime-only.
        if (action !== 'start') throw error
        await updateParam(id, 'action', action)
        try {
          await cookNode(id, 'dashboard', undefined, 'live')
        } finally {
          await updateParam(id, 'action', 'status')
        }
      }
    } finally {
      setEpisodePending(null)
    }
  }

  const runTrainingAction = async (action: 'start' | 'stop') => {
    if (trainingPending) return
    setTrainingPending(action)
    try {
      if (action === 'stop') {
        await controlNode(id, 'stop')
      } else {
        await updateParam(id, 'action', 'start')
        await cookNode(id, 'dashboard')
      }
    } finally {
      setTrainingPending(null)
    }
  }

  const chooseDatasetFolder = async () => {
    if (datasetFolderPending) return
    setDatasetFolderPending(true)
    try {
      const selected = await pickDirectory(String(data.params?.root ?? ''))
      if (selected) await updateParam(id, 'root', selected)
    } finally {
      setDatasetFolderPending(false)
    }
  }

  const fitNodeToImage = (naturalWidth: number, naturalHeight: number, extraControls = 0) => {
    if (!naturalWidth || !naturalHeight) return
    // Count only the rows that actually render: a node with primary_outputs
    // hides most of its ports, and budgeting for all of them leaves a large
    // empty gap under the image.
    const portRows = visibleInputs.length + visibleOutputs.length + (isToolBox ? 1 : 0)
    const chromeHeight = 34 + portRows * 22 + extraControls + 24
    resizeNode(id, {
      width: Math.max(160, Math.ceil(naturalWidth + 22)),
      height: Math.max(60, Math.ceil(naturalHeight + chromeHeight)),
    })
    requestAnimationFrame(() => updateNodeInternals(id))
  }

  // A live camera preview arrives at the sensor's own resolution. Growing the
  // node once on the first frame keeps the stream legible even when the node
  // was dropped small; without this the image is just squeezed to whatever
  // width the node already had, because fitResultToNodeWidth only fixes height.
  const fitNodeToStream = (image: HTMLImageElement) => {
    if (streamFitDone.current || !image.naturalWidth || !image.naturalHeight) return
    streamFitDone.current = true
    // Cap the width so a 1080p camera does not produce a node that swamps the
    // canvas; the sensor's aspect ratio is preserved either way.
    const width = Math.max(160, Math.ceil(Math.min(image.naturalWidth, STREAM_FIT_MAX_WIDTH) + 22))
    const current = getNode(id)
    // Set the width only. The height then comes from measuring where the image
    // actually starts, which accounts for the header, the status badge, port
    // rows and any control strip without this code knowing they exist.
    resizeNode(id, { width, height: current?.height ?? 200 })
    // React Flow caches handle positions; without this the edges keep starting
    // from where the ports used to be until something else forces a recalc.
    updateNodeInternals(id)
    requestAnimationFrame(() => {
      if (!image.isConnected) return
      dashboardAutoFitDone.current = false
      fitResultToNodeWidth(image)
    })
  }

  const fitResultToNodeWidth = (image: HTMLImageElement) => {
    if (dashboardAutoFitDone.current || !image.naturalWidth || !image.naturalHeight) return
    requestAnimationFrame(() => {
      if (dashboardAutoFitDone.current || !image.isConnected) return
      const frame = image.closest<HTMLElement>(`[data-bn-node-frame="${id}"]`)
      const dashboard = image.closest<HTMLElement>('[data-bn-dashboard-result]')
      if (!frame || !dashboard) return
      // Read from React Flow's live store, not the `nodes` array captured in
      // this render: a resize applied moments ago is not in the closure yet,
      // and using the stale width would undo it.
      const currentNode = getNode(id)
      const styledWidth = typeof currentNode?.style?.width === 'number' ? currentNode.style.width : undefined
      const styledHeight = typeof currentNode?.style?.height === 'number' ? currentNode.style.height : undefined
      const frameRect = frame.getBoundingClientRect()
      const dashboardRect = dashboard.getBoundingClientRect()
      const imageRect = image.getBoundingClientRect()
      const dashboardStyle = window.getComputedStyle(dashboard)
      const frameStyle = window.getComputedStyle(frame)
      const dashboardPaddingBottom = Number.parseFloat(dashboardStyle.paddingBottom) || 0
      const frameBorderBottom = Number.parseFloat(frameStyle.borderBottomWidth) || 0
      const nodeWidth = Math.max(160, currentNode?.width ?? styledWidth ?? Math.ceil(frameRect.width))
      const currentHeight = currentNode?.height ?? styledHeight ?? Math.ceil(frameRect.height)
      const canvasScale = frameRect.width > 0 ? frameRect.width / nodeWidth : 1

      // DOM rectangles are in zoomed screen pixels, while React Flow node
      // dimensions are unscaled graph pixels. Convert the image's top/width
      // back to graph space, then use its natural aspect ratio for an exact
      // required height even when the current flex box is compressed.
      const imageTop = (imageRect.top - frameRect.top) / canvasScale
      const imageWidth = imageRect.width / canvasScale
      const requiredImageHeight = imageWidth * image.naturalHeight / image.naturalWidth
      const measuredDashboardBottom = (dashboardRect.bottom - frameRect.top) / canvasScale
      const aspectRatioBottom = imageTop + requiredImageHeight + dashboardPaddingBottom
      const targetHeight = Math.max(
        60,
        Math.ceil(Math.max(measuredDashboardBottom, aspectRatioBottom) + frameBorderBottom),
      )

      dashboardAutoFitDone.current = true
      if (Math.abs(currentHeight - targetHeight) >= 3) {
        resizeNode(id, { width: nodeWidth, height: targetHeight })
      }
      // Always refresh handle positions, even when the height was already
      // right: an earlier width change in this same fit still moved the ports.
      requestAnimationFrame(() => updateNodeInternals(id))
    })
  }

  useEffect(() => {
    // Dashboard SVGs can grow when a later result contains longer reports,
    // paths, or errors. Re-fit on every image-source change, including one
    // truthy data URL replacing another, so updated content is never clipped
    // by the node's previous height.
    dashboardAutoFitDone.current = false
  }, [showImageResult])

  useEffect(() => {
    // Re-fit when a stream restarts: the next run may use a different camera
    // or resolution than the one this node was sized for.
    if (!streamPreview) streamFitDone.current = false
  }, [streamPreview])

  useEffect(() => {
    const streamingNow = data.portResults?.streaming === true
    const url = typeof data.portResults?.stream_url === 'string' ? data.portResults.stream_url : ''
    if (streamingNow && (!prevStreamingRef.current || url !== prevStreamUrlRef.current)) {
      setStreamConnKey(k => k + 1)
    }
    prevStreamingRef.current = streamingNow
    prevStreamUrlRef.current = url
  }, [data.portResults])

  useEffect(() => {
    updateNodeInternals(id)
  }, [id, inputsKey, outputsKey, updateNodeInternals])

  // Whenever the node's rendered size changes — a manual resize, the camera
  // preview auto-fit, or content growth — the right/bottom handles move but
  // React Flow keeps their cached positions, so edges connect to the old spot
  // and read as offset. Remeasure internals on every size change so the wires
  // follow the knobs.
  useEffect(() => {
    const el = document.querySelector(`[data-bn-node-frame="${CSS.escape(id)}"]`)
    if (!el) return
    const observer = new ResizeObserver(() => updateNodeInternals(id))
    observer.observe(el)
    return () => observer.disconnect()
  }, [id, updateNodeInternals])

  useEffect(() => {
    if (!isACTTraining || !trainingRunning) return
    let cancelled = false
    const refresh = async () => {
      try {
        await controlNode(id, 'status')
      } catch {
        // The next poll or backend connection notice will surface the state.
      }
    }
    const timer = window.setInterval(() => {
      if (!cancelled) void refresh()
    }, 1000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [controlNode, id, isACTTraining, trainingRunning])

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color={color}
      nodeType={data.type}
      style={{
        width: '100%',
        height: '100%',
        minWidth: 160,
        minHeight: 60,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <NodeResizer
        minWidth={160}
        minHeight={60}
        isVisible={selected}
        lineStyle={{ borderColor: color }}
        handleStyle={{ background: color, borderColor: color, width: 8, height: 8, borderRadius: 2 }}
      />


      {streamStartable && (
        <div className="nodrag" onMouseDown={e => e.stopPropagation()}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px 2px' }}>
          <button
            disabled={streamStartPending}
            onClick={e => { e.stopPropagation(); void onStartStream() }}
            style={{
              padding: '4px 10px', borderRadius: 5, border: '1px solid var(--ok)',
              background: 'rgba(61,220,151,.18)',
              color: streamStartPending ? 'var(--tx3)' : 'var(--tx1)',
              cursor: streamStartPending ? 'default' : 'pointer',
              fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 700, letterSpacing: 0,
            }}
          >
            {streamStartPending ? 'Starting…' : 'Go live'}
          </button>
          <span style={{ color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 11 }}>
            starts the WebSocket stream (action=start)
          </span>
        </div>
      )}

      {isACTTraining && (
        <div
          className="nodrag"
          onMouseDown={e => e.stopPropagation()}
          style={{ padding: '7px 10px', borderBottom: '1px solid var(--line)', fontFamily: 'var(--font-ui)' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
              background: trainingRunning ? 'var(--ok)' : trainingPhase === 'failed' ? 'var(--err)' : 'var(--tx3)',
              boxShadow: trainingRunning ? '0 0 8px var(--ok)' : 'none',
            }} />
            <strong style={{ color: trainingRunning ? 'var(--ok)' : trainingPhase === 'failed' ? 'var(--err)' : 'var(--tx2)', fontSize: 12 }}>
              {trainingStopping ? 'STOPPING' : trainingRunning ? 'TRAINING' : trainingPhase.toUpperCase()}
            </strong>
            <span style={{ marginLeft: 'auto', color: 'var(--tx2)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              {trainingStep}/{trainingSteps || '—'} · {Math.round(trainingProgress * 100)}%
            </span>
            <button
              disabled={Boolean(trainingPending) || trainingStopping}
              onClick={e => { e.stopPropagation(); void runTrainingAction(trainingRunning ? 'stop' : 'start') }}
              style={{
                ...driverBtn(trainingRunning ? 'var(--err)' : 'var(--ok)', Boolean(trainingPending) || trainingStopping),
                padding: '3px 8px', fontSize: 11,
              }}
            >
              {trainingPending === 'stop' || trainingStopping ? 'Stopping…' : trainingPending === 'start' ? 'Starting…' : trainingRunning ? '■ Stop' : '▶ Start / resume'}
            </button>
          </div>
          <div style={{ height: 5, marginTop: 6, borderRadius: 3, overflow: 'hidden', background: 'var(--line2)' }}>
            <div style={{ width: `${trainingProgress * 100}%`, height: '100%', background: trainingPhase === 'failed' ? 'var(--err)' : 'var(--ok)', transition: 'width .25s ease' }} />
          </div>
          <div style={{ marginTop: 5, color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.35 }}>
            {String(data.portResults?.report ?? (trainingRunning ? 'Training status refreshes every second.' : 'Ready to start training.'))}
          </div>
        </div>
      )}


      {/* header */}
      <div className="bn-node-header" style={{
        background: color,
        borderRadius: '8px 8px 0 0',
        padding: '6px 10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 6,
      }}>
        <NodeGlyph type={data.type} className="bn-node-header-glyph" />
        <div style={{ flex: 1, minWidth: 0 }}>
          {editingLabel ? (
            <input
              autoFocus
              value={labelDraft}
              onChange={e => setLabelDraft(e.target.value)}
              onBlur={commitRename}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); commitRename() }
                if (e.key === 'Escape') setEditingLabel(false)
              }}
              onClick={e => e.stopPropagation()}
              onMouseDown={e => e.stopPropagation()}
              style={{
                background: 'rgba(0,0,0,.25)', border: 'none', outline: 'none',
                color: '#fff', fontWeight: 600, fontSize: 15,
                fontFamily: 'var(--font-ui)', width: '100%', borderRadius: 3,
                padding: '1px 4px',
              }}
            />
          ) : (
            <span
              className="bn-node-title"
              title="Double-click to rename"
              onDoubleClick={startRename}
              style={{ fontWeight: 600, fontSize: 15, fontFamily: 'var(--font-ui)', display: 'block', cursor: 'text', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {label ?? data.type}
            </span>
          )}
          {!editingLabel && (
            <span
              className="bn-node-type"
              title={`Node type ${data.type}`}
              style={{ fontSize: 11, opacity: 0.65, fontFamily: 'var(--font-mono)', display: 'block', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {qualifiedType}
            </span>
          )}
        </div>
        <div
          className="bn-node-runtime-state"
          data-tone={headerState.tone}
          title={`Node state: ${headerState.label}`}
        >
          <i />
          <span>{headerState.label}</span>
        </div>
        <button
          className="bn-node-cook-button"
          onClick={e => { e.stopPropagation(); cookNode(id, data.outputs[0] ?? 'output') }}
          title="Cook once"
          style={{
            background: 'rgba(0,0,0,.2)',
            border: 'none',
            borderRadius: 4,
            color: '#fff',
            cursor: 'pointer',
            fontSize: 12,
            padding: '2px 7px',
            fontFamily: 'var(--font-ui)',
            flexShrink: 0,
          }}
        >
          {data.cooking ? '…' : '▶'}
        </button>
      </div>

      {hasVisualHoverPreview && hoverPreviewImage && (
        <div className="bn-node-hover-preview" role="status" aria-label={`${data.type} preview`}>
          <div className="bn-node-hover-preview-head">
            <span>{streamActive ? 'LIVE' : 'PREVIEW'}</span>
            {previewFps > 0 && <b>{Math.round(previewFps)} FPS</b>}
          </div>
          <img src={hoverPreviewImage} alt="" draggable={false} />
          <div className="bn-node-hover-preview-meta">
            <strong>{label ?? data.type}</strong>
            <span>
              {previewWidth > 0 && previewHeight > 0
                ? `${previewWidth}×${previewHeight}`
                : streamActive
                  ? 'Streaming'
                  : 'Latest result'}
            </span>
            {previewConfidence > 0 && <span>{Math.round(previewConfidence * 100)}% confidence</span>}
          </div>
        </div>
      )}

      {nodeStats.length > 0 && (
        <div className="bn-node-stat-strip" aria-label={`${data.type} runtime statistics`}>
          {nodeStats.slice(0, 4).map(stat => (
            <span key={stat.label} className={stat.tone ? `is-${stat.tone}` : undefined}>
              {stat.label}
            </span>
          ))}
        </div>
      )}

      <div className="bn-node-parameter-area">
      {isRobotJointDefinition && (
        <div
          className="bn-joint-definition-fields nodrag"
          onMouseDown={e => e.stopPropagation()}
          onKeyDown={e => e.stopPropagation()}
        >
          <div className="bn-joint-definition-fields-head">
            <span>Joint identity</span>
            <strong>Servo {String(data.params?.servo_id ?? 1)}</strong>
          </div>
          <div className="bn-joint-definition-fields-grid">
            <label>
              <span>Servo ID</span>
              <input
                key={`servo-${String(data.params?.servo_id ?? 1)}`}
                type="number"
                min={1}
                step={1}
                defaultValue={Number(data.params?.servo_id ?? 1)}
                onBlur={e => {
                  const next = Math.max(1, Math.trunc(Number(e.target.value) || 1))
                  e.target.value = String(next)
                  void updateParam(id, 'servo_id', next)
                }}
              />
            </label>
            <label>
              <span>Joint ID</span>
              <input
                type="text"
                value={String(data.params?.joint_id ?? 'joint')}
                spellCheck={false}
                onChange={e => { void updateParam(id, 'joint_id', e.target.value) }}
              />
            </label>
            <label>
              <span>Display name</span>
              <input
                type="text"
                value={String(data.params?.display_name ?? 'Joint')}
                onChange={e => { void updateParam(id, 'display_name', e.target.value) }}
              />
            </label>
          </div>
        </div>
      )}
      {isRobot && (
        <div className="nodrag" onMouseDown={e => e.stopPropagation()}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, margin: '6px 8px 0' }}>
            <button
              disabled={pingPending}
              title="Wiggle a joint a few degrees and back so you can see which physical robot this node controls (needs the driver running and armed)."
              onClick={e => { e.stopPropagation(); void pingRobot() }}
              style={{
                padding: '4px 10px', borderRadius: 5, border: '1px solid var(--accent)',
                background: 'rgba(99,102,241,.18)',
                color: pingPending ? 'var(--tx3)' : 'var(--tx1)',
                cursor: pingPending ? 'default' : 'pointer',
                fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 700, flexShrink: 0,
              }}
            >
              {pingPending ? 'Pinging…' : '📍 Ping'}
            </button>
            <span style={{
              color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 11,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0,
            }}>
              identify this robot
            </span>
          </div>
          <div style={{
            margin: '6px 8px 0', padding: '6px 7px', borderRadius: 6,
            border: '1px solid var(--line)', background: 'rgba(0,0,0,.12)',
            fontFamily: 'var(--font-ui)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{ color: 'var(--tx2)', fontSize: 12, fontWeight: 700, flex: 1 }}>
                Robot profile &amp; calibration
              </span>
              <button
                disabled={robotProfileId === 'auto' || robotProfileEditPending}
                title="Open the selected profile as editable joint nodes in a new tab"
                onClick={e => { e.stopPropagation(); void editRobotProfile() }}
                style={{
                  padding: '1px 6px', borderRadius: 4, border: '1px solid var(--accent)',
                  background: 'rgba(99,102,241,.12)', color: 'var(--tx1)',
                  cursor: robotProfileId === 'auto' || robotProfileEditPending ? 'default' : 'pointer',
                  fontSize: 11, fontWeight: 700,
                  opacity: robotProfileId === 'auto' ? 0.55 : 1,
                }}
              >
                {robotProfileEditPending ? 'Opening…' : 'Edit profile'}
              </button>
              <button
                disabled={robotCalibrationsLoading}
                title="Refresh saved profiles and calibrations"
                onClick={e => { e.stopPropagation(); void loadRobotSetup() }}
                style={{
                  padding: '1px 5px', borderRadius: 4, border: '1px solid var(--line)',
                  background: 'var(--lift)', color: 'var(--tx2)',
                  cursor: robotCalibrationsLoading ? 'default' : 'pointer', fontSize: 12,
                }}
              >
                {robotCalibrationsLoading ? '…' : '⟳'}
              </button>
            </div>
            <label style={{
              display: 'block', color: 'var(--tx3)', fontSize: 11,
              marginBottom: 3,
            }}>
              Profile
            </label>
            <select
              aria-label="Robot profile"
              title={selectedRobotProfileChoice
                ? `${selectedRobotProfileChoice.name} · ${selectedRobotProfileChoice.id}`
                : 'Select a saved robot profile'}
              value={robotProfileId === 'auto' ? '' : robotProfileId}
              disabled={robotProfilePending}
              onFocus={() => { void loadRobotSetup() }}
              onChange={e => { void selectRobotProfile(e.target.value) }}
              style={{
                boxSizing: 'border-box', width: '100%', minWidth: 0,
                background: 'var(--lift)', color: 'var(--tx1)',
                border: '1px solid var(--line)', borderRadius: 5, padding: '3px 5px',
                fontFamily: 'var(--font-ui)', fontSize: 12, marginBottom: 6,
              }}
            >
              {robotProfileId === 'auto' && (
                <option value="" disabled>Select a saved profile…</option>
              )}
              {robotProfileChoices.map(profile => (
                <option value={profile.id} key={profile.id}>
                  {profile.name === profile.id ? profile.id : `${profile.name} · ${profile.id}`}
                  {profile.calibration_count
                    ? ` · ${profile.calibration_count} calibration${profile.calibration_count === 1 ? '' : 's'}`
                    : ' · no calibration'}
                </option>
              ))}
            </select>
            {selectedRobotProfileChoice && (
              <div className="bn-robot-node-profile-summary">
                <strong>{selectedRobotProfileChoice.name}</strong>
                <span>
                  ID: {selectedRobotProfileChoice.id}
                  {' · '}
                  {selectedRobotProfileChoice.calibration_count
                    ? `${selectedRobotProfileChoice.calibration_count} calibration${selectedRobotProfileChoice.calibration_count === 1 ? '' : 's'}`
                    : 'No saved calibration'}
                </span>
              </div>
            )}
            <label style={{
              display: 'block', color: 'var(--tx3)', fontSize: 11,
              marginBottom: 3,
            }}>
              Calibration
            </label>
            <select
              aria-label="Calibration used for deployment"
              value={selectedRobotCalibrationKey}
              disabled={robotCalibrationPending || robotCalibrationsLoading}
              onChange={e => { void selectRobotCalibration(e.target.value) }}
              style={{
                boxSizing: 'border-box', width: '100%', minWidth: 0,
                background: 'var(--lift)', color: 'var(--tx1)',
                border: '1px solid var(--line)', borderRadius: 5, padding: '3px 5px',
                fontFamily: 'var(--font-ui)', fontSize: 12,
              }}
            >
              <option value="">
                {robotCalibrationsLoading
                  ? 'Loading calibrations…'
                  : matchingRobotCalibrations.length
                    ? 'Choose a calibration…'
                    : robotProfileId
                      ? `No calibrations saved for ${robotProfileId}`
                      : 'Choose a robot profile first'}
              </option>
              {selectedRobotCalibration && !selectedRobotCalibrationCandidate && (
                <option value={selectedRobotCalibrationKey}>
                  {robotCalibrationsLoading
                    ? `Loading ${selectedRobotCalibration.hardware_id}…`
                    : `Selected: ${selectedRobotCalibration.hardware_id} (not found)`}
                </option>
              )}
              {matchingRobotCalibrations.map(calibration => (
                <option
                  key={`${calibration.profile_id}\u0000${calibration.hardware_id}`}
                  value={`${calibration.profile_id}\u0000${calibration.hardware_id}`}
                >
                  {calibration.name} · {calibration.hardware_id} · {calibration.joint_count} joints
                </option>
              ))}
            </select>
            <div
              title={selectedRobotCalibrationCandidate
                ? `${selectedRobotCalibrationCandidate.name} — ${selectedRobotCalibrationCandidate.profile_name} — ${selectedRobotCalibrationCandidate.hardware_id}`
                : undefined}
              style={{
                marginTop: 4, fontSize: 11, lineHeight: 1.35,
                color: robotCalibrationError
                  ? 'var(--err)'
                  : selectedRobotCalibrationCandidate
                    ? 'var(--ok)'
                    : 'var(--warn)',
                overflowWrap: 'anywhere',
              }}
            >
              {robotCalibrationPending
                ? 'Saving selection…'
                : robotCalibrationError
                  ? robotCalibrationError
                  : robotCalibrationsLoading
                    ? 'Loading saved calibration details…'
                  : selectedRobotCalibrationCandidate
                    ? `Using “${selectedRobotCalibrationCandidate.name}” on ${selectedRobotCalibrationCandidate.hardware_id}. Deployment Step 2 uses this same selection.`
                    : selectedRobotCalibration
                      ? `Selected hardware ${selectedRobotCalibration.hardware_id} is not available for profile ${robotProfileId || selectedRobotCalibration.profile_id}.`
                      : 'No calibration selected. Pick the named physical robot before deployment.'}
            </div>
          </div>
        </div>
      )}

      {hasCameraSelection && (
        <div
          className="nodrag"
          onMouseDown={e => e.stopPropagation()}
          style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '6px 8px 0' }}
        >
          <span style={{ fontSize: 12, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', flexShrink: 0 }}>Camera</span>
          <select
            value={String(data.params?.selection ?? 0)}
            onFocus={() => { if (!cameraList.length && !cameraScanning) void loadCameras() }}
            onChange={e => { void updateParam(id, 'selection', Number(e.target.value)) }}
            style={{
              flex: 1, minWidth: 0, background: 'var(--lift)', color: 'var(--tx1)',
              border: '1px solid var(--line)', borderRadius: 5, padding: '2px 5px',
              fontFamily: 'var(--font-ui)', fontSize: 13,
            }}
          >
            {/* Always offer the current value; discovery fills real names on focus. */}
            {cameraList.length === 0 && (
              <option value={String(data.params?.selection ?? 0)}>
                {cameraScanning ? 'Scanning…' : `Camera ${data.params?.selection ?? 0} — click to scan`}
              </option>
            )}
            {cameraList.map(c => (
              <option key={c.index} value={String(c.index)}>{c.index}: {c.label}</option>
            ))}
          </select>
          <button
            title="Rescan cameras"
            onClick={e => { e.stopPropagation(); void loadCameras() }}
            style={{
              flexShrink: 0, background: 'var(--lift)', border: '1px solid var(--line)',
              borderRadius: 5, color: 'var(--tx2)', cursor: 'pointer', fontSize: 13, padding: '2px 6px',
            }}
          >
            ⟳
          </button>
        </div>
      )}

      {hasModelPicker && (
        <div
          className="nodrag"
          onMouseDown={e => e.stopPropagation()}
          style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '6px 8px 0' }}
        >
          <span style={{ fontSize: 12, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', flexShrink: 0 }}>Model</span>
          <select
            value={String(data.params?.model ?? 'yolov8n.pt')}
            onFocus={() => { if (!modelList.builtin.length) void loadModels() }}
            onChange={e => {
              const next = e.target.value
              void updateParam(id, 'model', next)
              // Open-vocab models score low; drop the threshold to a workable
              // default when switching to one, unless the user already set a
              // low conf themselves. Standard models keep 0.35.
              const conf = Number(data.params?.conf ?? 0.35)
              if (/world/i.test(next) && conf >= 0.3) void updateParam(id, 'conf', 0.1)
            }}
            title={modelList.dir ? `Custom models: drop .pt/.onnx into ${modelList.dir}` : undefined}
            style={{
              flex: 1, minWidth: 0, background: 'var(--lift)', color: 'var(--tx1)',
              border: '1px solid var(--line)', borderRadius: 5, padding: '2px 5px',
              fontFamily: 'var(--font-ui)', fontSize: 13,
            }}
          >
            {/* Keep the current value selectable even before a scan. */}
            {![...modelList.builtin, ...modelList.custom].includes(String(data.params?.model ?? 'yolov8n.pt')) && (
              <option value={String(data.params?.model ?? 'yolov8n.pt')}>{String(data.params?.model ?? 'yolov8n.pt')}</option>
            )}
            {modelList.custom.length > 0 && (
              <optgroup label="Custom (.blacknode/models)">
                {modelList.custom.map(m => <option key={m} value={m}>{m}</option>)}
              </optgroup>
            )}
            <optgroup label="Built-in (auto-download)">
              {(modelList.builtin.length ? modelList.builtin : ['yolov8n.pt']).map(m => <option key={m} value={m}>{m}</option>)}
            </optgroup>
          </select>
        </div>
      )}

      {hasModelPicker && isWorldModel && (
        <>
          <div
            className="nodrag"
            onMouseDown={e => e.stopPropagation()}
            style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '6px 8px 0' }}
          >
            <span style={{ fontSize: 12, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', flexShrink: 0 }}>Classes</span>
            {/* Controlled + commit on every keystroke: a blur-only commit lost the
                text when Go Live was clicked before the field lost focus, so the
                model ran with no prompt and found nothing. */}
            <input
              value={String(data.params?.classes ?? '')}
              placeholder="box, red cube, coffee mug"
              title="Comma-separated objects to find. Use plain nouns/short phrases ('box', 'red cube') — abstract words like 'cube' score near zero. Empty falls back to the model's default classes."
              onChange={e => { void updateParam(id, 'classes', e.target.value) }}
              style={{
                flex: 1, minWidth: 0, background: 'var(--lift)', color: 'var(--tx1)',
                border: '1px solid var(--line)', borderRadius: 5, padding: '2px 5px',
                fontFamily: 'var(--font-ui)', fontSize: 13,
              }}
            />
          </div>
          <div
            className="nodrag"
            onMouseDown={e => e.stopPropagation()}
            style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '4px 8px 0' }}
          >
            <span style={{ fontSize: 12, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', flexShrink: 0 }}>Confidence</span>
            {/* Open-vocab scores are low (often 0.1–0.3); the 0.35 default hides
                them, so surface conf here with a world-appropriate default. */}
            <input
              type="number" min={0.01} max={1} step={0.01}
              value={String(data.params?.conf ?? 0.1)}
              title="Detection threshold. YOLO-World custom classes score low — start around 0.05–0.15 and raise if you get false boxes."
              onChange={e => { void updateParam(id, 'conf', Math.max(0.01, Math.min(1, Number(e.target.value) || 0.1))) }}
              style={{
                width: 64, background: 'var(--lift)', color: 'var(--tx1)',
                border: '1px solid var(--line)', borderRadius: 5, padding: '2px 5px',
                fontFamily: 'var(--font-ui)', fontSize: 13,
              }}
            />
            <span style={{ fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-ui)' }}>lower = more boxes</span>
          </div>
        </>
      )}

      {isTrackingObject && (
        <div className="nodrag" onMouseDown={e => e.stopPropagation()}
          style={{ margin: '6px 8px 0', display: 'flex', flexDirection: 'column', gap: 3 }}>
          {([
            { key: 'min_area', label: 'Min area', min: 0, max: 3000, step: 50, def: 300 },
            { key: 'blur', label: 'Blur', min: 0, max: 25, step: 2, def: 5 },
            { key: 'morphology_iters', label: 'Cleanup', min: 0, max: 6, step: 1, def: 1 },
            { key: 'follow_target_x', label: 'Aim X', min: 0, max: 1, step: 0.05, def: 0.4 },
            { key: 'follow_deadband', label: 'Deadband', min: 0, max: 0.5, step: 0.01, def: 0.12 },
          ] as const).map(s => {
            const val = Number(data.params?.[s.key] ?? s.def)
            return (
              <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', width: 54, flexShrink: 0 }}>{s.label}</span>
                <input
                  type="range" min={s.min} max={s.max} step={s.step} value={val}
                  onChange={e => { void updateParam(id, s.key, Number(e.target.value)) }}
                  style={{ flex: 1, minWidth: 0, accentColor: 'var(--accent)', height: 3 }}
                />
                <span style={{ fontSize: 11, color: 'var(--tx2)', fontFamily: 'var(--font-mono)', width: 32, textAlign: 'right', flexShrink: 0 }}>
                  {s.step < 1 ? val.toFixed(2) : val}
                </span>
              </div>
            )
          })}
          <span style={{ fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-ui)' }}>adjusts live while streaming — no recook</span>
        </div>
      )}

      {isJointSliders && (() => {
        const joints = Array.isArray(data.portResults?.joints) ? data.portResults!.joints as Array<{ name: string; min: number; max: number; value: number }> : []
        const armed = data.params?.armed === true
        const targets = (data.params?.targets as Record<string, number> | undefined) ?? {}
        return (
          <div className="nodrag" onMouseDown={e => e.stopPropagation()}
            style={{ margin: '6px 8px 4px', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={armed}
                onChange={e => { void updateParam(id, 'armed', e.target.checked) }}
                style={{ accentColor: armed ? 'var(--err)' : 'var(--tx3)' }}
              />
              <span style={{ fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-ui)', color: armed ? 'var(--err)' : 'var(--tx3)' }}>
                {armed ? 'ARMED — sliders move the robot' : 'Arm to move'}
              </span>
            </label>
            {joints.length === 0 && (
              <span style={{ fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-ui)' }}>
                Go Live to read the robot's joints
              </span>
            )}
            {joints.map(j => {
              const val = typeof targets[j.name] === 'number' ? targets[j.name] : j.value
              return (
                <div key={j.name} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span title={j.name} style={{ fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', width: 68, flexShrink: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{j.name}</span>
                  <input
                    type="range" min={j.min} max={j.max} step={0.5} value={val}
                    disabled={!armed}
                    onChange={e => { void updateParam(id, 'targets', { ...targets, [j.name]: Number(e.target.value) }) }}
                    style={{ flex: 1, minWidth: 0, accentColor: 'var(--accent)', height: 3, opacity: armed ? 1 : 0.45 }}
                  />
                  <span style={{ fontSize: 11, color: 'var(--tx2)', fontFamily: 'var(--font-mono)', width: 38, textAlign: 'right', flexShrink: 0 }}>{Number(val).toFixed(1)}</span>
                </div>
              )
            })}
          </div>
        )
      })()}

      {statusBadge && (statusBadge.text || statusBadge.action) && (
        <div
          className="nodrag"
          title={statusBadge.title}
          onMouseDown={e => e.stopPropagation()}
          style={{
            display: 'flex', alignItems: 'center', gap: 7,
            margin: '6px 8px 0', padding: '5px 8px', borderRadius: 6,
            border: `1px solid ${BADGE_TONE[statusBadge.tone]}`,
            background: 'var(--lift)', color: BADGE_TONE[statusBadge.tone],
            fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 800,
            letterSpacing: '0.03em', lineHeight: 1,
          }}
        >
          {statusBadge.text && (
            <>
              <span style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: BADGE_TONE[statusBadge.tone],
                boxShadow: statusBadge.tone === 'muted' ? 'none' : `0 0 8px ${BADGE_TONE[statusBadge.tone]}`,
              }} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {statusBadge.text}
              </span>
            </>
          )}
          {statusBadge.action && (
            <button
              disabled={statusBadge.action.pending}
              onClick={e => { e.stopPropagation(); statusBadge.action!.onClick() }}
              style={{
                marginLeft: 2, padding: '2px 6px', borderRadius: 4,
                border: '1px solid var(--err)', background: 'transparent',
                color: statusBadge.action.pending ? 'var(--tx3)' : 'var(--err)',
                cursor: statusBadge.action.pending ? 'default' : 'pointer',
                fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 700,
                letterSpacing: 0,
              }}
            >
              {statusBadge.action.label}
            </button>
          )}
        </div>
      )}

      {/* Start/Stop for chat trigger nodes — the server launches the driver. */}
      {driverName && (
        <div className="nodrag" style={{ display: 'flex', gap: 6, padding: '6px 10px 2px' }} onMouseDown={e => e.stopPropagation()}>
          {driverPending ? (
            <button disabled style={driverBtn('var(--tx2)', true)}>
              {driverPending === 'start' ? '⏳ Starting…' : '⏳ Stopping…'}
            </button>
          ) : driverLive ? (
            <button
              onClick={e => { e.stopPropagation(); void onStopDriver() }}
              style={driverBtn('var(--err)')}
            >
              ■ Stop bot
            </button>
          ) : (
            <button
              disabled={driverNotInstalled}
              title={driverNotInstalled ? 'Install the package first (select the node)' : `Start the ${driverName} bot`}
              onClick={e => { e.stopPropagation(); void onStartDriver() }}
              style={driverBtn(driverNotInstalled ? 'var(--tx3)' : 'var(--ok)', driverNotInstalled)}
            >
              ▶ Start bot
            </button>
          )}
        </div>
      )}

      {isManualMove && (
        <div
          className="nodrag"
          onMouseDown={e => e.stopPropagation()}
          style={{ padding: '8px 10px 4px', borderBottom: '1px solid var(--line)' }}
        >
          <div style={{
            marginBottom: 7, color: data.portResults?.torque_enabled === false ? 'var(--warn)' : 'var(--tx2)',
            fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 750,
          }}>
            {`SELECTED: ${releaseSelected ? 'RELEASE + LIVE POSE' : holdSelected ? 'HOLD POSITION' : 'MONITOR ONLY'} · `}
            {data.portResults?.torque_enabled === false
              ? 'ROBOT: TORQUE OFF · RELEASED'
              : data.portResults?.torque_enabled === true
                ? 'ROBOT: TORQUE ON · HOLDING'
              : 'ROBOT STATE UNKNOWN'}
          </div>
          {manualReleaseMismatch && (
            <div style={{
              marginBottom: 7, padding: '5px 7px', borderRadius: 5,
              border: '1px solid var(--err)', background: 'rgba(239,68,68,.12)', color: 'var(--err)',
              fontFamily: 'var(--font-ui)', fontSize: 11, fontWeight: 800, lineHeight: 1.35,
            }}>
              RELEASE NOT APPLIED · TORQUE IS STILL ON
            </div>
          )}
          {manualHoldMismatch && (
            <div style={{
              marginBottom: 7, padding: '5px 7px', borderRadius: 5,
              border: '1px solid var(--err)', background: 'rgba(239,68,68,.12)', color: 'var(--err)',
              fontFamily: 'var(--font-ui)', fontSize: 11, fontWeight: 800, lineHeight: 1.35,
            }}>
              HOLD NOT APPLIED · TORQUE IS STILL OFF
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button
              disabled={Boolean(manualMovePending)}
              title="Turn torque off and immediately start the live pose monitor"
              onClick={e => { e.stopPropagation(); void runManualMoveAction('release') }}
              style={{
                ...driverBtn('var(--warn)', Boolean(manualMovePending)),
                background: releaseSelected ? 'rgba(245,158,11,.22)' : 'transparent',
              }}
            >
              {manualMovePending === 'release' ? 'Releasing…' : `${releaseSelected ? '✓ ' : ''}Release + live pose`}
            </button>
            <button
              disabled={Boolean(manualMovePending)}
              title="Watch joint positions continuously without changing torque"
              onClick={e => { e.stopPropagation(); void runManualMoveAction('monitor') }}
              style={{
                ...driverBtn('var(--tx2)', Boolean(manualMovePending)),
                background: monitorSelected ? 'rgba(46,159,230,.22)' : 'transparent',
              }}
            >
              {manualMovePending === 'monitor' ? 'Starting…' : `${monitorSelected ? '✓ ' : ''}Monitor only`}
            </button>
            <button
              disabled={Boolean(manualMovePending)}
              title="Read the current pose safely, turn torque on to hold it, and keep live feedback running"
              onClick={e => { e.stopPropagation(); void runManualMoveAction('hold') }}
              style={{
                ...driverBtn('var(--ok)', Boolean(manualMovePending)),
                background: holdSelected ? 'rgba(61,220,151,.22)' : 'transparent',
              }}
            >
              {manualMovePending === 'hold' ? 'Holding…' : `${holdSelected ? '✓ ' : ''}Hold position`}
            </button>
          </div>
          {manualMovePoseEntries.length > 0 && (
            <div style={{
              marginTop: 8, display: 'grid', gridTemplateColumns: 'minmax(110px, 1fr) auto',
              gap: '3px 10px', fontFamily: 'var(--font-mono)', fontSize: 12,
            }}>
              {manualMovePoseEntries.map(([joint, value]) => (
                <div key={joint} style={{ display: 'contents' }}>
                  <span style={{ color: 'var(--tx2)' }}>{joint}</span>
                  <span style={{ color: 'var(--tx1)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {value.toFixed(2)}°
                  </span>
                </div>
              ))}
            </div>
          )}
          {manualMoveReport && (
            <div style={{
              marginTop: 7, padding: '5px 7px', borderRadius: 5,
              border: '1px solid var(--warn)', background: 'rgba(245,158,11,.08)',
              color: 'var(--warn)', fontFamily: 'var(--font-ui)', fontSize: 11,
              lineHeight: 1.35, whiteSpace: 'pre-wrap',
            }}>
              {manualMoveReport}
            </div>
          )}
          <div style={{ marginTop: 6, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 11, lineHeight: 1.35 }}>
            Go live never changes torque by itself; it only keeps supported outputs updating.
          </div>
        </div>
      )}

      {isRobotCalibration && (
        <div style={{
          margin: '7px 9px 3px', padding: 8, borderRadius: 7,
          border: `1px solid ${calibrationActive ? 'var(--warn)' : calibrationPaused ? 'var(--accent)' : calibrationSaved ? 'var(--ok)' : 'var(--line)'}`,
          background: calibrationActive ? 'rgba(245,158,11,.08)' : 'rgba(255,255,255,.02)',
        }}>
          <label style={{
            display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8,
            color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 11,
            fontWeight: 700, textTransform: 'uppercase',
          }}>
            Calibration name
            <input
              key={String(data.params?.calibration_name ?? '')}
              defaultValue={String(data.params?.calibration_name ?? '')}
              placeholder="Workshop arm"
              onClick={e => e.stopPropagation()}
              onKeyDown={e => {
                e.stopPropagation()
                if (e.key === 'Enter') e.currentTarget.blur()
              }}
              onBlur={e => {
                const name = e.currentTarget.value.trim()
                if (name !== String(data.params?.calibration_name ?? '')) {
                  void updateParam(id, 'calibration_name', name)
                }
              }}
              style={{
                width: '100%', boxSizing: 'border-box', padding: '6px 7px',
                border: '1px solid var(--line2)', borderRadius: 5,
                background: 'var(--lift)', color: 'var(--tx1)',
                fontFamily: 'var(--font-ui)', fontSize: 13,
              }}
            />
          </label>
          <div style={{
            marginBottom: 7, color: calibrationActive ? 'var(--warn)' : calibrationPaused ? 'var(--accent)' : calibrationSaved ? 'var(--ok)' : 'var(--tx2)',
            fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 800,
          }}>
            {calibrationActive ? `● RECORDING LIVE · ${calibrationSamples} samples` : calibrationPaused ? `Ⅱ RECORDING PAUSED · ${calibrationSamples} samples` : calibrationSaved ? '✓ CALIBRATION SAVED' : '○ CALIBRATION IDLE'}
          </div>
          {calibrationActive && (calibrationCapturingJoint || latestCalibrationRangeUpdate) && (
            <div style={{ margin: '-3px 0 7px', color: 'var(--accent)', fontFamily: 'var(--font-ui)', fontSize: 11, fontWeight: 700 }}>
              {calibrationCapturingJoint ? `CAPTURING ${calibrationCapturingJoint}` : ''}
              {latestCalibrationRangeUpdate
                ? `${calibrationCapturingJoint ? ' · ' : ''}${latestCalibrationRangeUpdate[0]} ${String(latestCalibrationRangeUpdate[1]?.kind ?? 'range').toUpperCase()} UPDATED`
                : ''}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button
              disabled={Boolean(calibrationPending) || calibrationActive}
              title="Start recording observed positions. Torque must already be released."
              onClick={e => { e.stopPropagation(); void runCalibrationAction('start') }}
              style={driverBtn('var(--warn)', Boolean(calibrationPending) || calibrationActive)}
            >
              {calibrationPending === 'start' ? 'Starting…' : calibrationPaused ? 'Resume recording' : 'Start recording'}
            </button>
            <button
              disabled={Boolean(calibrationPending) || !calibrationActive}
              title="Pause range recording without discarding samples; live pose continues"
              onClick={e => { e.stopPropagation(); void runCalibrationAction('pause') }}
              style={driverBtn('var(--accent)', Boolean(calibrationPending) || !calibrationActive)}
            >
              {calibrationPending === 'pause' ? 'Stopping…' : 'Stop recording'}
            </button>
            <button
              disabled={Boolean(calibrationPending) || !calibrationDataReady}
              title="Capture the current released pose as the neutral Home pose"
              onClick={e => { e.stopPropagation(); void runCalibrationAction('capture_home') }}
              style={driverBtn('var(--accent)', Boolean(calibrationPending) || !calibrationDataReady)}
            >
              {calibrationPending === 'capture_home' ? 'Capturing…' : 'Capture Home'}
            </button>
            <button
              disabled={Boolean(calibrationPending) || !calibrationDataReady}
              title="Review and save observed and safe ranges for this hardware serial"
              onClick={e => { e.stopPropagation(); void runCalibrationAction('finish') }}
              style={driverBtn('var(--ok)', Boolean(calibrationPending) || !calibrationDataReady)}
            >
              {calibrationPending === 'finish' ? 'Saving…' : 'Save calibration'}
            </button>
            <button
              disabled={Boolean(calibrationPending) || (!calibrationActive && !calibrationPaused)}
              title="Discard this unsaved calibration session"
              onClick={e => { e.stopPropagation(); void runCalibrationAction('cancel') }}
              style={driverBtn('var(--err)', Boolean(calibrationPending) || (!calibrationActive && !calibrationPaused))}
            >
              Cancel
            </button>
          </div>
          <div style={{ marginTop: 6, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 11, lineHeight: 1.35 }}>
            Move every released joint slowly through its intended usable range. Mechanical hard stops are not treated as safe limits.
          </div>
        </div>
      )}

      {isDatasetBrowser && <DatasetBrowserPanel id={id} data={data} />}

      {isDatasetCreate && (
        <div style={{
          margin: '7px 9px 3px', padding: 8, borderRadius: 7,
          border: '1px solid var(--line)', background: 'rgba(255,255,255,.02)',
        }}>
          <div style={{ color: 'var(--tx2)', fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 800 }}>
            DATASET STORAGE
          </div>
          <div title={datasetRoot || '~/.blacknode/datasets'} style={{ marginTop: 5, color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.35, wordBreak: 'break-all' }}>
            Root: {datasetRoot || '~/.blacknode/datasets (default)'}
          </div>
          <div style={{ marginTop: 2, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 11 }}>
            Blacknode stores this dataset in a “{datasetId}” subfolder.
          </div>
          {datasetResolvedPath && (
            <div title={datasetResolvedPath} style={{ marginTop: 3, color: 'var(--ok)', fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.35, wordBreak: 'break-all' }}>
              Current: {datasetResolvedPath}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 7, flexWrap: 'wrap' }}>
            <button
              disabled={datasetFolderPending}
              onClick={e => { e.stopPropagation(); void chooseDatasetFolder() }}
              style={driverBtn('var(--accent)', datasetFolderPending)}
            >
              {datasetFolderPending ? 'Choosing…' : 'Choose folder…'}
            </button>
            <button
              disabled={datasetFolderPending || !datasetRoot}
              onClick={e => { e.stopPropagation(); void updateParam(id, 'root', '') }}
              style={driverBtn('var(--tx2)', datasetFolderPending || !datasetRoot)}
            >
              Use default
            </button>
          </div>
        </div>
      )}

      {isEpisodeRecorder && (
        <div style={{
          margin: '7px 9px 3px', padding: 8, borderRadius: 7,
          border: `1px solid ${episodeRecording ? 'var(--err)' : episodePaused ? 'var(--warn)' : 'var(--line)'}`,
          background: episodeRecording ? 'rgba(239,68,68,.08)' : 'rgba(255,255,255,.02)',
        }}>
          <div style={{
            marginBottom: 7,
            color: episodeRecording ? 'var(--err)' : episodePaused ? 'var(--warn)' : 'var(--tx2)',
            fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 800,
          }}>
            {episodeRecording
              ? `● RECORDING · ${episodeFrameCount} FRAMES · ${episodeDuration.toFixed(1)}s`
              : episodePaused
                ? `Ⅱ PAUSED · ${episodeFrameCount} FRAMES · ${episodeDuration.toFixed(1)}s`
                : episodeRecoverable
                  ? `↻ RECOVERABLE · ${episodeFrameCount} FRAMES · ${episodeDuration.toFixed(1)}s`
                  : '○ READY FOR A NEW EPISODE'}
            {episodeDroppedFrames > 0 ? ` · ${episodeDroppedFrames} DROPPED` : ''}
          </div>
          {episodeLastError && (
            <div style={{ margin: '-3px 0 7px', color: 'var(--warn)', fontFamily: 'var(--font-ui)', fontSize: 11, lineHeight: 1.35 }}>
              {episodeLastError}
            </div>
          )}
          {episodeStoragePath && (
            <div title={episodeStoragePath} style={{ margin: '-2px 0 7px', color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.35, wordBreak: 'break-all' }}>
              Saving to: {episodeStoragePath}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button
              disabled={Boolean(episodePending) || episodeRunning || episodeRecoverable || !episodeInputsReady}
              title={episodeRecoverable ? 'Save or discard the recoverable episode first' : episodeInputsReady ? 'Start a new synchronized robot and camera episode' : 'Connect dataset, robot stream, and at least one camera stream first'}
              onClick={e => { e.stopPropagation(); void runEpisodeAction('start') }}
              style={driverBtn('var(--err)', Boolean(episodePending) || episodeRunning || episodeRecoverable || !episodeInputsReady)}
            >
              {episodePending === 'start' ? 'Starting…' : '● Record'}
            </button>
            <button
              disabled={Boolean(episodePending) || !episodeRecording}
              title="Pause recording without losing captured frames"
              onClick={e => { e.stopPropagation(); void runEpisodeAction('pause') }}
              style={driverBtn('var(--warn)', Boolean(episodePending) || !episodeRecording)}
            >
              {episodePending === 'pause' ? 'Pausing…' : 'Ⅱ Pause'}
            </button>
            <button
              disabled={Boolean(episodePending) || !episodePaused}
              title="Continue the paused episode"
              onClick={e => { e.stopPropagation(); void runEpisodeAction('resume') }}
              style={driverBtn('var(--ok)', Boolean(episodePending) || !episodePaused)}
            >
              {episodePending === 'resume' ? 'Resuming…' : '▶ Resume'}
            </button>
            <button
              disabled={Boolean(episodePending) || (!episodeRunning && (!episodeRecoverable || episodeFrameCount === 0))}
              title="Finalize and save this episode to the dataset"
              onClick={e => { e.stopPropagation(); void runEpisodeAction('save') }}
              style={driverBtn('var(--ok)', Boolean(episodePending) || (!episodeRunning && (!episodeRecoverable || episodeFrameCount === 0)))}
            >
              {episodePending === 'save' ? 'Saving…' : '✓ Save episode'}
            </button>
            <button
              disabled={Boolean(episodePending) || !episodeRunning}
              title="Stop recording but keep the episode journal recoverable"
              onClick={e => { e.stopPropagation(); void runEpisodeAction('stop') }}
              style={driverBtn('var(--tx2)', Boolean(episodePending) || !episodeRunning)}
            >
              {episodePending === 'stop' ? 'Stopping…' : '■ Stop'}
            </button>
            <button
              disabled={Boolean(episodePending) || (!episodeRunning && !episodeRecoverable)}
              title="Permanently discard this incomplete episode"
              onClick={e => { e.stopPropagation(); void runEpisodeAction('discard') }}
              style={driverBtn('var(--err)', Boolean(episodePending) || (!episodeRunning && !episodeRecoverable))}
            >
              {episodePending === 'discard' ? 'Discarding…' : 'Discard'}
            </button>
          </div>
          <div style={{ marginTop: 6, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 11, lineHeight: 1.35 }}>
            Record starts a new episode. Save finalizes it. Stop keeps an incomplete episode recoverable.
          </div>
        </div>
      )}
      </div>

      {/* ports */}
      <div className="bn-node-ports" style={{
        flex: showImageResult ? '0 0 auto' : 1,
        padding: '6px 0',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
      }}>
        {(isToolBox || isRobotJointList || isVariadic) && (
          <div style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            padding: '6px 10px 2px 16px',
          }}>
            <Handle
              type="target"
              position={Position.Left}
              id="__new__"
              style={{
                left: -5,
                background: 'var(--node)',
                width: 11,
                height: 11,
                border: `2px dashed ${isVariadic ? portColor(variadicInput?.type || 'Any') : isRobotJointList ? portColor('Dict') : TOOLBOX_NEW_HANDLE_COLOR}`,
                borderRadius: '50%',
              }}
            />
            <span style={{ fontSize: 11, color: isVariadic ? portColor(variadicInput?.type || 'Any') : isRobotJointList ? portColor('Dict') : TOOLBOX_NEW_HANDLE_COLOR, fontFamily: 'var(--font-ui)', userSelect: 'none' }}>
              {isVariadic ? `${variadicPrefix}_${nextVariadicNumber} · connect to add` : isRobotJointList ? `joint_${nextJointNumber} · connect to add` : '← drag to create'}
            </span>
          </div>
        )}
        {visibleInputs.length > 0 && <div className="bn-port-section-label is-input">Inputs</div>}
        {visibleInputs.map(inp => {
          const type = effectivePortType(inp, 'input')
          const connected = edges.some(e => e.target === id && e.targetHandle === inp)
          if (
            (
              (isManualMove || isRobotCalibration || isEpisodeRecorder)
              && inp === 'action'
              && !connected
            )
            || (isRobotCalibration && inp === 'calibration_name' && !connected)
          ) return null
          const showImageInput = type === 'Image'
            && !connected
            && !isWireOnlyInput(data.type, inp, type)
          const hasImageInputPreview = showImageInput && isImageSrc(data.params?.[inp])
          return (
            <div
              key={inp}
              style={hasImageInputPreview ? {
                display: 'flex',
                flexDirection: 'column',
                flex: 1,
                minHeight: 0,
              } : undefined}
            >
              <PortRow
                nodeId={id}
                name={inp}
                type={type}
                dir="input"
                onRemove={(isToolBox || isRobotJointList || isVariadic) ? () => removeToolSlot(inp) : undefined}
              />
              {showImageInput && (
                <NodeImageInput
                  value={data.params?.[inp]}
                  onChange={value => { updateParam(id, inp, value).catch(() => {}) }}
                  onFitNatural={(width, height) => fitNodeToImage(width, height, 36)}
                />
              )}
            </div>
          )
        })}
        {visibleOutputs.length > 0 && <div className="bn-port-section-label is-output">Outputs</div>}
        {visibleOutputs.map(out => (
          <PortRow
            nodeId={id}
            key={out}
            name={out}
            type={effectivePortType(out, 'output')}
            dir="output"
            result={data.portResults?.[out]}
          />
        ))}
        {showImageResult && (
          <div data-bn-dashboard-result style={{ ...imageResultWrap, flex: '0 0 auto', width: '100%', boxSizing: 'border-box' }}>
            <div style={{ ...imagePreviewFrame, height: 'auto' }}>
              <img
                key={streamPreview ? `stream-${streamConnKey}` : 'static'}
                src={showImageResult}
                alt="result"
                draggable={false}
                style={widthFitResultImg}
                onDragStart={e => e.preventDefault()}
                onLoad={e => {
                  if (streamPreview) fitNodeToStream(e.currentTarget)
                  fitResultToNodeWidth(e.currentTarget)
                }}
                onDoubleClick={e => {
                  e.stopPropagation()
                  fitNodeToImage(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)
                }}
                onError={e => { (e.currentTarget as HTMLImageElement).dataset.bnFailed = '1' }}
              />
            </div>
          </div>
        )}
        {/* Stream nodes always show their own state, under the picture rather
            than over it. When the backend says it is streaming but no frame is
            on screen, this is the only visible clue to why - the node's report,
            and the live URL to open directly in a browser as a cross-check. */}
        {LIVE_STREAM_NODE_TYPES.has(data.type) && typeof data.portResults?.report === 'string' && data.portResults.report.trim() && (
          <div style={{
            padding: '4px 8px 6px', fontFamily: 'var(--font-ui)', fontSize: 12,
            color: data.portResults?.streaming === true ? 'var(--ok)' : 'var(--tx3)',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
              background: data.portResults?.streaming === true ? 'var(--ok)' : 'var(--tx3)',
            }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              title={String(data.portResults.report)}>
              {String(data.portResults.report)}
            </span>
          </div>
        )}
      </div>
    </NodeFrame>
  )
}

export default memo(BlackNode)
