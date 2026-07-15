import { memo, useState, useRef, useEffect } from 'react'
import { Handle, Position, NodeProps, useUpdateNodeInternals } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { portColor } from '../portColors'
import { headerColor } from '../categories'
import { isWireOnlyInput } from '../inputControls'
import NodeFrame from './NodeFrame'
import type { NodeCookState } from '../types'

const TOOLBOX_NEW_HANDLE_COLOR = '#ef444488'

// Chat trigger node types → the driver the Start/Stop buttons control.
const TRIGGER_DRIVER: Record<string, string> = {
  SlackMessage: 'slack',
  TelegramMessage: 'telegram',
}

const LIVE_STREAM_NODE_TYPES = new Set([
  'ROS2ImageStream',
  'CV2ColorObjectStream',
  'VisionReasoningStream',
  'CUDAImageFilterStream',
])

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
}

function previewPortValue(v: unknown): string {
  if (v === undefined || v === null) return ''
  const s = typeof v === 'object' ? JSON.stringify(v) : String(v)
  return s.length > 160 ? s.slice(0, 160) + '…' : s
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
  const color   = portColor(type)
  const isInput = dir === 'input'
  const resultText = result !== undefined ? previewPortValue(result) : ''

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
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <Handle
        type={isInput ? 'target' : 'source'}
        position={isInput ? Position.Left : Position.Right}
        id={name}
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
        {name}
      </span>
      {hovering && (type || resultText) && (
        <div
          title={resultText || type}
          style={{
            position: 'absolute',
            top: -30,
            [isInput ? 'left' : 'right']: 10,
            zIndex: 30,
            maxWidth: 260,
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            padding: '4px 7px',
            borderRadius: 6,
            border: '1px solid var(--line2)',
            background: 'var(--panel)',
            boxShadow: '0 8px 20px rgba(0,0,0,.28)',
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
          }}
        >
          <span style={{
            fontSize: 11,
            color,
            fontFamily: 'var(--font-mono)',
          }}>
            {type}
          </span>
          {resultText && (
            <span
              style={{
                fontSize: 11,
                color: 'var(--ok)',
                fontFamily: 'var(--font-mono)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              = {resultText}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

const isImageSrc = (v: unknown): v is string =>
  typeof v === 'string' && (v.startsWith('data:image/') || /^https?:\/\//i.test(v))

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
  const resizeNode  = useStore(s => s.resizeNode)
  const disconnectEdge = useStore(s => s.disconnectEdge)
  const edges       = useStore(s => s.edges)
  const nodes       = useStore(s => s.nodes)
  const driverStatus = useStore(s => s.driverStatus)
  const drivers     = useStore(s => s.drivers)
  const startDriver = useStore(s => s.startDriver)
  const stopDriver  = useStore(s => s.stopDriver)
  const loadDriverStatus = useStore(s => s.loadDriverStatus)
  const driverName  = TRIGGER_DRIVER[data.type]
  const driverLive  = driverName ? Boolean(driverStatus[driverName]?.live) : false
  const driverNotInstalled = driverName ? drivers[driverName]?.packages_installed === false : false
  const [driverPending, setDriverPending] = useState<null | 'start' | 'stop'>(null)
  const [streamStopPending, setStreamStopPending] = useState(false)
  const [rosRunStopPending, setRosRunStopPending] = useState(false)
  const updateNodeInternals = useUpdateNodeInternals()
  const color       = headerColor(data.type)
  const isToolBox   = data.type === 'ToolBox'
  const visibleInputs = data.inputs ?? []
  const inputsKey = visibleInputs.join('|')
  const outputsKey = (data.outputs ?? []).join('|')
  // Only explicit display nodes render image panels. Processing nodes keep
  // image-valued ports wireable without expanding into duplicate previews.
  const nodeImage = (): string | null => {
    if (isImageSrc(data.cookResult)) return data.cookResult
    for (const v of Object.values(data.portResults ?? {})) {
      if (isImageSrc(v)) return v
    }
    return null
  }
  const imageResult = !data.cookError ? nodeImage() : null
  const showImageResult = data.type === 'OutputImage' ? imageResult : null
  const streamUrl = typeof data.portResults?.stream_url === 'string' ? data.portResults.stream_url : ''
  const streamActive = LIVE_STREAM_NODE_TYPES.has(data.type) && data.portResults?.streaming === true && streamUrl.length > 0
  const rosRunActive = data.type === 'ROS2Run' && data.portResults?.running === true
  const rosRunId = typeof data.portResults?.run_id === 'string' ? data.portResults.run_id : 'ros2_run'

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

  const fitNodeToImage = (naturalWidth: number, naturalHeight: number, extraControls = 0) => {
    if (!naturalWidth || !naturalHeight) return
    const portRows = visibleInputs.length + (data.outputs?.length ?? 0) + (isToolBox ? 1 : 0)
    const chromeHeight = 34 + portRows * 22 + extraControls + 24
    resizeNode(id, {
      width: Math.max(160, Math.ceil(naturalWidth + 22)),
      height: Math.max(60, Math.ceil(naturalHeight + chromeHeight)),
    })
    requestAnimationFrame(() => updateNodeInternals(id))
  }

  useEffect(() => {
    updateNodeInternals(id)
  }, [id, inputsKey, outputsKey, updateNodeInternals])

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

      {streamActive && (
        <div
          className="nodrag"
          title={streamUrl ? `Live stream: ${streamUrl}` : 'Live image stream is running'}
          onMouseDown={e => e.stopPropagation()}
          style={{
            position: 'absolute',
            left: 8,
            top: -28,
            zIndex: 22,
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            padding: '4px 7px',
            borderRadius: 6,
            border: '1px solid var(--ok)',
            background: 'var(--panel)',
            color: 'var(--ok)',
            boxShadow: '0 6px 18px rgba(0,0,0,.3)',
            fontFamily: 'var(--font-ui)',
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: '0.06em',
            lineHeight: 1,
          }}
        >
          <span style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'var(--ok)',
            boxShadow: '0 0 8px var(--ok)',
            flexShrink: 0,
          }} />
          <span>STREAMING</span>
          <button
            disabled={streamStopPending}
            onClick={e => { e.stopPropagation(); void onStopImageStream() }}
            style={{
              marginLeft: 2,
              padding: '2px 6px',
              borderRadius: 4,
              border: '1px solid var(--err)',
              background: 'transparent',
              color: streamStopPending ? 'var(--tx3)' : 'var(--err)',
              cursor: streamStopPending ? 'default' : 'pointer',
              fontFamily: 'var(--font-ui)',
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0,
            }}
          >
            {streamStopPending ? 'Stopping...' : 'Stop stream'}
          </button>
        </div>
      )}

      {rosRunActive && (
        <div
          className="nodrag"
          title={`ROS 2 run process is active: ${rosRunId}`}
          onMouseDown={e => e.stopPropagation()}
          style={{
            position: 'absolute',
            left: 8,
            top: -28,
            zIndex: 22,
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            padding: '4px 7px',
            borderRadius: 6,
            border: '1px solid var(--ok)',
            background: 'var(--panel)',
            color: 'var(--ok)',
            boxShadow: '0 6px 18px rgba(0,0,0,.3)',
            fontFamily: 'var(--font-ui)',
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: '0.06em',
            lineHeight: 1,
          }}
        >
          <span style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'var(--ok)',
            boxShadow: '0 0 8px var(--ok)',
            flexShrink: 0,
          }} />
          <span>ROS2 RUNNING</span>
          <button
            disabled={rosRunStopPending}
            onClick={e => { e.stopPropagation(); void onStopROS2Run() }}
            style={{
              marginLeft: 2,
              padding: '2px 6px',
              borderRadius: 4,
              border: '1px solid var(--err)',
              background: 'transparent',
              color: rosRunStopPending ? 'var(--tx3)' : 'var(--err)',
              cursor: rosRunStopPending ? 'default' : 'pointer',
              fontFamily: 'var(--font-ui)',
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0,
            }}
          >
            {rosRunStopPending ? 'Stopping...' : 'Stop run'}
          </button>
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
          {label && !editingLabel && (
            <span style={{ fontSize: 9, opacity: 0.65, fontFamily: 'var(--font-mono)', display: 'block', marginTop: 1 }}>
              {data.type}
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

      {/* ports */}
      <div style={{ flex: 1, padding: '6px 0', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {isToolBox && (
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
                border: `2px dashed ${TOOLBOX_NEW_HANDLE_COLOR}`,
                borderRadius: '50%',
              }}
            />
            <span style={{ fontSize: 9, color: TOOLBOX_NEW_HANDLE_COLOR, fontFamily: 'var(--font-ui)', userSelect: 'none' }}>
              ← drag to create
            </span>
          </div>
        )}
        {visibleInputs.map(inp => {
          const type = effectivePortType(inp, 'input')
          const connected = edges.some(e => e.target === id && e.targetHandle === inp)
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
                onRemove={isToolBox ? () => removeToolSlot(inp) : undefined}
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
        {data.outputs.map(out => (
          <PortRow
            key={out}
            name={out}
            type={effectivePortType(out, 'output')}
            dir="output"
            result={data.portResults?.[out]}
          />
        ))}
        {showImageResult && (
          <div style={imageResultWrap}>
            <div style={imagePreviewFrame}>
              <img
                src={showImageResult}
                alt="result"
                draggable={false}
                style={previewImg}
                onDragStart={e => e.preventDefault()}
                onDoubleClick={e => {
                  e.stopPropagation()
                  fitNodeToImage(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)
                }}
              />
            </div>
          </div>
        )}
      </div>
    </NodeFrame>
  )
}

export default memo(BlackNode)
