import { memo, useState, useRef, useEffect } from 'react'
import { Handle, Position, NodeProps, useReactFlow, useUpdateNodeInternals } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { api } from '../api'
import { portColor } from '../portColors'
import { headerColor } from '../categories'
import { isWireOnlyInput } from '../inputControls'
import { copyTextToClipboard } from '../clipboard'
import { portDisplayHint, portDisplayName } from '../portLabels'
import { useQualifiedTypeLabel } from '../nodeTypeLabel'
import NodeFrame from './NodeFrame'
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
    fontSize: 11,
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
  name,
  type,
  dir,
  result,
  onRemove,
}: {
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
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: isInput ? 'flex-start' : 'flex-end',
        padding: isInput ? `4px 10px 4px ${onRemove ? 28 : 12}px` : '4px 12px 4px 10px',
        position: 'relative',
        gap: 5,
      }}
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
            fontSize: 12,
            lineHeight: 1,
            padding: '0 2px',
            opacity: hovering ? 1 : 0.55,
          }}
        >
          x
        </button>
      )}
      <span style={{
        color: 'var(--tx2)',
        fontSize: 12,
        fontFamily: 'var(--font-ui)',
      }}>
        {displayName}
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
              fontSize: 11,
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
                  fontSize: 11,
                  fontFamily: 'var(--font-ui)',
                }}
              >
                {copyState === 'copied' ? 'Copied' : copyState === 'error' ? 'Copy failed' : 'Copy value'}
              </button>
            )}
          </div>
          <div style={{ color: 'var(--tx3)', fontSize: 9, marginBottom: resultText ? 6 : 0 }}>
            {portDisplayHint(name, dir)}
          </div>
          {resultText && (
            <div
              style={{
                fontSize: 12,
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
                  fontSize: 12,
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
  color: 'var(--tx1)', fontFamily: 'var(--font-ui)', fontSize: 11, fontWeight: 600,
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
  const qualifiedType = useQualifiedTypeLabel(data.type)
  const driverName  = TRIGGER_DRIVER[data.type]
  const driverLive  = driverName ? Boolean(driverStatus[driverName]?.live) : false
  const driverNotInstalled = driverName ? drivers[driverName]?.packages_installed === false : false
  const [driverPending, setDriverPending] = useState<null | 'start' | 'stop'>(null)
  const [streamStopPending, setStreamStopPending] = useState(false)
  const [streamStartPending, setStreamStartPending] = useState(false)
  const [rosRunStopPending, setRosRunStopPending] = useState(false)
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
  const isRobotJointList = data.type === 'RobotJointList'
  const variadicInput = data.variadic_input ?? null
  const isVariadic = Boolean(variadicInput)
  const isManualMove = data.type === 'ROS2ManualMove'
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
  const manualMoveLive = data.type === 'ROS2ManualMove' && data.portResults?.live === true
  const manualMoveReady = manualMoveLive && data.portResults?.data_ready === true
  const manualMoveMode = data.portResults?.mode === 'released' ? 'RELEASED' : 'HOLD'
  const manualMoveJointCount = Array.isArray(data.portResults?.joints) ? data.portResults.joints.length : 0
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
              background: 'rgba(34,197,94,.18)',
              color: streamStartPending ? 'var(--tx3)' : 'var(--tx1)',
              cursor: streamStartPending ? 'default' : 'pointer',
              fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 700, letterSpacing: 0,
            }}
          >
            {streamStartPending ? 'Starting…' : 'Go live'}
          </button>
          <span style={{ color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 9 }}>
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
            <strong style={{ color: trainingRunning ? 'var(--ok)' : trainingPhase === 'failed' ? 'var(--err)' : 'var(--tx2)', fontSize: 10 }}>
              {trainingStopping ? 'STOPPING' : trainingRunning ? 'TRAINING' : trainingPhase.toUpperCase()}
            </strong>
            <span style={{ marginLeft: 'auto', color: 'var(--tx2)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>
              {trainingStep}/{trainingSteps || '—'} · {Math.round(trainingProgress * 100)}%
            </span>
            <button
              disabled={Boolean(trainingPending) || trainingStopping}
              onClick={e => { e.stopPropagation(); void runTrainingAction(trainingRunning ? 'stop' : 'start') }}
              style={{
                ...driverBtn(trainingRunning ? 'var(--err)' : 'var(--ok)', Boolean(trainingPending) || trainingStopping),
                padding: '3px 8px', fontSize: 9,
              }}
            >
              {trainingPending === 'stop' || trainingStopping ? 'Stopping…' : trainingPending === 'start' ? 'Starting…' : trainingRunning ? '■ Stop' : '▶ Start / resume'}
            </button>
          </div>
          <div style={{ height: 5, marginTop: 6, borderRadius: 3, overflow: 'hidden', background: 'var(--line2)' }}>
            <div style={{ width: `${trainingProgress * 100}%`, height: '100%', background: trainingPhase === 'failed' ? 'var(--err)' : 'var(--ok)', transition: 'width .25s ease' }} />
          </div>
          <div style={{ marginTop: 5, color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 8, lineHeight: 1.35 }}>
            {String(data.portResults?.report ?? (trainingRunning ? 'Training status refreshes every second.' : 'Ready to start training.'))}
          </div>
        </div>
      )}


      {/* header */}
      <div style={{
        background: color,
        borderRadius: '8px 8px 0 0',
        padding: '6px 10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 6,
      }}>
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
                color: '#fff', fontWeight: 600, fontSize: 13,
                fontFamily: 'var(--font-ui)', width: '100%', borderRadius: 3,
                padding: '1px 4px',
              }}
            />
          ) : (
            <span
              title="Double-click to rename"
              onDoubleClick={startRename}
              style={{ fontWeight: 600, fontSize: 13, fontFamily: 'var(--font-ui)', display: 'block', cursor: 'text', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {label ?? data.type}
            </span>
          )}
          {!editingLabel && (
            <span
              title={`Node type ${data.type}`}
              style={{ fontSize: 9, opacity: 0.65, fontFamily: 'var(--font-mono)', display: 'block', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {qualifiedType}
            </span>
          )}
        </div>
        <button
          onClick={e => { e.stopPropagation(); cookNode(id, data.outputs[0] ?? 'output') }}
          title="Cook once"
          style={{
            background: 'rgba(0,0,0,.2)',
            border: 'none',
            borderRadius: 4,
            color: '#fff',
            cursor: 'pointer',
            fontSize: 10,
            padding: '2px 7px',
            fontFamily: 'var(--font-ui)',
            flexShrink: 0,
          }}
        >
          {data.cooking ? '…' : '▶'}
        </button>
      </div>

      {hasCameraSelection && (
        <div
          className="nodrag"
          onMouseDown={e => e.stopPropagation()}
          style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '6px 8px 0' }}
        >
          <span style={{ fontSize: 10, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', flexShrink: 0 }}>Camera</span>
          <select
            value={String(data.params?.selection ?? 0)}
            onFocus={() => { if (!cameraList.length && !cameraScanning) void loadCameras() }}
            onChange={e => { void updateParam(id, 'selection', Number(e.target.value)) }}
            style={{
              flex: 1, minWidth: 0, background: 'var(--lift)', color: 'var(--tx1)',
              border: '1px solid var(--line)', borderRadius: 5, padding: '2px 5px',
              fontFamily: 'var(--font-ui)', fontSize: 11,
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
              borderRadius: 5, color: 'var(--tx2)', cursor: 'pointer', fontSize: 11, padding: '2px 6px',
            }}
          >
            ⟳
          </button>
        </div>
      )}

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
            fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 800,
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
                fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 700,
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
            fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 750,
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
              fontFamily: 'var(--font-ui)', fontSize: 9, fontWeight: 800, lineHeight: 1.35,
            }}>
              RELEASE NOT APPLIED · TORQUE IS STILL ON
            </div>
          )}
          {manualHoldMismatch && (
            <div style={{
              marginBottom: 7, padding: '5px 7px', borderRadius: 5,
              border: '1px solid var(--err)', background: 'rgba(239,68,68,.12)', color: 'var(--err)',
              fontFamily: 'var(--font-ui)', fontSize: 9, fontWeight: 800, lineHeight: 1.35,
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
                background: holdSelected ? 'rgba(34,197,94,.22)' : 'transparent',
              }}
            >
              {manualMovePending === 'hold' ? 'Holding…' : `${holdSelected ? '✓ ' : ''}Hold position`}
            </button>
          </div>
          <div style={{ marginTop: 6, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 9, lineHeight: 1.35 }}>
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
          <div style={{
            marginBottom: 7, color: calibrationActive ? 'var(--warn)' : calibrationPaused ? 'var(--accent)' : calibrationSaved ? 'var(--ok)' : 'var(--tx2)',
            fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 800,
          }}>
            {calibrationActive ? `● RECORDING LIVE · ${calibrationSamples} samples` : calibrationPaused ? `Ⅱ RECORDING PAUSED · ${calibrationSamples} samples` : calibrationSaved ? '✓ CALIBRATION SAVED' : '○ CALIBRATION IDLE'}
          </div>
          {calibrationActive && (calibrationCapturingJoint || latestCalibrationRangeUpdate) && (
            <div style={{ margin: '-3px 0 7px', color: 'var(--accent)', fontFamily: 'var(--font-ui)', fontSize: 9, fontWeight: 700 }}>
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
          <div style={{ marginTop: 6, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 9, lineHeight: 1.35 }}>
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
          <div style={{ color: 'var(--tx2)', fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 800 }}>
            DATASET STORAGE
          </div>
          <div title={datasetRoot || '~/.blacknode/datasets'} style={{ marginTop: 5, color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 9, lineHeight: 1.35, wordBreak: 'break-all' }}>
            Root: {datasetRoot || '~/.blacknode/datasets (default)'}
          </div>
          <div style={{ marginTop: 2, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 9 }}>
            Blacknode stores this dataset in a “{datasetId}” subfolder.
          </div>
          {datasetResolvedPath && (
            <div title={datasetResolvedPath} style={{ marginTop: 3, color: 'var(--ok)', fontFamily: 'var(--font-mono)', fontSize: 9, lineHeight: 1.35, wordBreak: 'break-all' }}>
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
            fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 800,
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
            <div style={{ margin: '-3px 0 7px', color: 'var(--warn)', fontFamily: 'var(--font-ui)', fontSize: 9, lineHeight: 1.35 }}>
              {episodeLastError}
            </div>
          )}
          {episodeStoragePath && (
            <div title={episodeStoragePath} style={{ margin: '-2px 0 7px', color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 9, lineHeight: 1.35, wordBreak: 'break-all' }}>
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
          <div style={{ marginTop: 6, color: 'var(--tx3)', fontFamily: 'var(--font-ui)', fontSize: 9, lineHeight: 1.35 }}>
            Record starts a new episode. Save finalizes it. Stop keeps an incomplete episode recoverable.
          </div>
        </div>
      )}

      {/* ports */}
      <div style={{
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
            <span style={{ fontSize: 9, color: isVariadic ? portColor(variadicInput?.type || 'Any') : isRobotJointList ? portColor('Dict') : TOOLBOX_NEW_HANDLE_COLOR, fontFamily: 'var(--font-ui)', userSelect: 'none' }}>
              {isVariadic ? `${variadicPrefix}_${nextVariadicNumber} · connect to add` : isRobotJointList ? `joint_${nextJointNumber} · connect to add` : '← drag to create'}
            </span>
          </div>
        )}
        {visibleInputs.map(inp => {
          const type = effectivePortType(inp, 'input')
          const connected = edges.some(e => e.target === id && e.targetHandle === inp)
          if ((isManualMove || isRobotCalibration || isEpisodeRecorder) && inp === 'action' && !connected) return null
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
        {visibleOutputs.map(out => (
          <PortRow
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
            padding: '4px 8px 6px', fontFamily: 'var(--font-ui)', fontSize: 10,
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
