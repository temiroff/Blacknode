import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import type { NewtonWorkspaceStatus } from '../api'

interface SimulationViewerPaneProps {
  url: string
  label: string
  phase: string
  armed: boolean
  visible: boolean
  floating: boolean
  height: number
  onHeightChange: (height: number) => void
  onDetach: () => void
  onAttach: () => void
  onClose: () => void
  workspace?: boolean
  sceneLabel?: string
  simulationRunning?: boolean
  busy?: boolean
  warning?: string
  onNewStage?: () => void
  onOpenUsd?: () => void
  onPlay?: () => void
  onStop?: () => void
  onReset?: () => void
  onCloseWorkspace?: () => void
  workspaceStatus?: NewtonWorkspaceStatus | null
  onWorkspaceAction?: (action: string, payload?: Record<string, unknown>) => void
  onChooseHdri?: () => void
}

interface FloatingRect {
  x: number
  y: number
  width: number
  height: number
}

const MIN_FLOATING_WIDTH = 420
const MIN_FLOATING_HEIGHT = 260
const MENU_CLOSE_DELAY_MS = 500
const DEFAULT_OUTLINER_WIDTH = 220
const DEFAULT_INSPECTOR_WIDTH = 270
const MIN_PANEL_WIDTH = 160
const MAX_PANEL_WIDTH = 720
const MIN_VIEWPORT_WIDTH = 180
const OUTLINER_WIDTH_STORAGE_KEY = 'blacknode-newton-outliner-width'
const INSPECTOR_WIDTH_STORAGE_KEY = 'blacknode-newton-inspector-width'

const storedPanelWidth = (key: string, fallback: number) => {
  try {
    const value = Number(window.localStorage.getItem(key))
    if (Number.isFinite(value)) return Math.max(MIN_PANEL_WIDTH, Math.min(MAX_PANEL_WIDTH, value))
  } catch {
    // Panel resizing remains available for this session when storage is unavailable.
  }
  return fallback
}

const linearToSrgb = (value: number) => {
  const linear = Math.max(0, Math.min(1, value))
  return linear <= 0.0031308
    ? linear * 12.92
    : 1.055 * Math.pow(linear, 1 / 2.4) - 0.055
}

const srgbToLinear = (value: number) => {
  const srgb = Math.max(0, Math.min(1, value))
  return srgb <= 0.04045
    ? srgb / 12.92
    : Math.pow((srgb + 0.055) / 1.055, 2.4)
}

const rgbToHex = (rgb: [number, number, number]) => `#${rgb
  .map(value => Math.round(linearToSrgb(value) * 255).toString(16).padStart(2, '0'))
  .join('')}`

const hexToRgb = (hex: string): [number, number, number] => [
  srgbToLinear(Number.parseInt(hex.slice(1, 3), 16) / 255),
  srgbToLinear(Number.parseInt(hex.slice(3, 5), 16) / 255),
  srgbToLinear(Number.parseInt(hex.slice(5, 7), 16) / 255),
]

const formNumber = (data: FormData, name: string, fallback = 0) => {
  const value = Number(data.get(name))
  return Number.isFinite(value) ? value : fallback
}

const committedFormNumber = (form: HTMLFormElement, name: string) => {
  const input = form.elements.namedItem(name)
  if (!(input instanceof HTMLInputElement)) return null
  const value = Number(input.value.trim())
  if (!input.value.trim() || !Number.isFinite(value)) {
    input.setCustomValidity('Enter a finite decimal or scientific-notation number.')
    input.reportValidity()
    return null
  }
  input.setCustomValidity('')
  return value
}

const commitNumberOnEnter = (event: React.KeyboardEvent<HTMLInputElement>) => {
  if (event.key !== 'Enter') return
  event.preventDefault()
  event.currentTarget.form?.requestSubmit()
}

const compactNumber = (value: number, digits = 4) => {
  if (!Number.isFinite(value)) return '—'
  const magnitude = Math.abs(value)
  if (magnitude !== 0 && (magnitude >= 1e5 || magnitude < 1e-3)) {
    return value.toExponential(Math.max(0, digits - 1))
  }
  return Number(value.toPrecision(digits)).toString()
}

export default function SimulationViewerPane({
  url,
  label,
  phase,
  armed,
  visible,
  floating,
  height,
  onHeightChange,
  onDetach,
  onAttach,
  onClose,
  workspace = false,
  sceneLabel = '',
  simulationRunning = false,
  busy = false,
  warning = '',
  onNewStage,
  onOpenUsd,
  onPlay,
  onStop,
  onReset,
  onCloseWorkspace,
  workspaceStatus,
  onWorkspaceAction,
  onChooseHdri,
}: SimulationViewerPaneProps) {
  const [reloadKey, setReloadKey] = useState(0)
  const [outlinerVisible, setOutlinerVisible] = useState(true)
  const [propertiesVisible, setPropertiesVisible] = useState(true)
  const [controllerVisible, setControllerVisible] = useState(true)
  const [environmentVisible, setEnvironmentVisible] = useState(false)
  const [perceptionVisible, setPerceptionVisible] = useState(true)
  const [perceptionMode, setPerceptionMode] = useState('rgb')
  const [collapsedPaths, setCollapsedPaths] = useState<Set<string>>(() => new Set())
  const [outlinerWidth, setOutlinerWidth] = useState(() => storedPanelWidth(
    OUTLINER_WIDTH_STORAGE_KEY, DEFAULT_OUTLINER_WIDTH,
  ))
  const [inspectorWidth, setInspectorWidth] = useState(() => storedPanelWidth(
    INSPECTOR_WIDTH_STORAGE_KEY, DEFAULT_INSPECTOR_WIDTH,
  ))
  const [floatingRect, setFloatingRect] = useState<FloatingRect>({
    x: 24,
    y: 24,
    width: 760,
    height: 520,
  })
  const rootRef = useRef<HTMLElement | null>(null)
  const viewerFrameRef = useRef<HTMLIFrameElement | null>(null)
  const menuCloseTimerRef = useRef<number | null>(null)
  const pendingJointTargetRef = useRef<{ name: string; target: number } | null>(null)
  const jointTargetFrameRef = useRef<number | null>(null)

  const queueJointTarget = useCallback((name: string, target: number) => {
    pendingJointTargetRef.current = { name, target }
    if (jointTargetFrameRef.current !== null) return
    jointTargetFrameRef.current = requestAnimationFrame(() => {
      jointTargetFrameRef.current = null
      const pending = pendingJointTargetRef.current
      pendingJointTargetRef.current = null
      if (pending) onWorkspaceAction?.('joint_target', pending)
    })
  }, [onWorkspaceAction])

  useEffect(() => setPerceptionMode('rgb'), [url])
  useEffect(() => setCollapsedPaths(new Set()), [url])
  useEffect(() => {
    try {
      window.localStorage.setItem(OUTLINER_WIDTH_STORAGE_KEY, String(Math.round(outlinerWidth)))
    } catch {
      // The resized Outliner remains active for this session.
    }
  }, [outlinerWidth])
  useEffect(() => {
    try {
      window.localStorage.setItem(INSPECTOR_WIDTH_STORAGE_KEY, String(Math.round(inspectorWidth)))
    } catch {
      // The resized Properties panel remains active for this session.
    }
  }, [inspectorWidth])
  const cancelMenuClose = useCallback(() => {
    if (menuCloseTimerRef.current === null) return
    window.clearTimeout(menuCloseTimerRef.current)
    menuCloseTimerRef.current = null
  }, [])

  const scheduleMenuClose = useCallback((menuBar: HTMLElement) => {
    cancelMenuClose()
    menuCloseTimerRef.current = window.setTimeout(() => {
      menuCloseTimerRef.current = null
      menuBar.querySelectorAll('details[open]').forEach(menu => menu.removeAttribute('open'))
    }, MENU_CLOSE_DELAY_MS)
  }, [cancelMenuClose])

  const closeSiblingMenus = useCallback((event: React.MouseEvent<HTMLElement>) => {
    const target = event.target
    if (!(target instanceof Element)) return
    const summary = target.closest('summary')
    const selectedMenu = summary?.parentElement
    if (!(selectedMenu instanceof HTMLDetailsElement) || selectedMenu.parentElement !== event.currentTarget) return
    cancelMenuClose()
    event.currentTarget.querySelectorAll(':scope > details[open]').forEach(openMenu => {
      if (openMenu !== selectedMenu) openMenu.removeAttribute('open')
    })
  }, [cancelMenuClose])

  useEffect(() => () => {
    if (jointTargetFrameRef.current !== null) cancelAnimationFrame(jointTargetFrameRef.current)
    cancelMenuClose()
  }, [cancelMenuClose])

  useEffect(() => {
    let viewerOrigin = ''
    try {
      viewerOrigin = new URL(url).origin
    } catch {
      return
    }
    const receiveViewerInteraction = (event: MessageEvent) => {
      if (event.source !== viewerFrameRef.current?.contentWindow || event.origin !== viewerOrigin) return
      const message = event.data
      if (!message || typeof message !== 'object') return
      if (message.type === 'blacknode-newton-selection') {
        onWorkspaceAction?.('select', { path: String(message.path || '') })
        return
      }
      if (message.type === 'blacknode-newton-view-state') {
        const mode = String(message.mode || '')
        if (['rgb', 'depth', 'segmentation', 'detection', 'composite'].includes(mode)) {
          setPerceptionMode(mode)
        }
        return
      }
      if (message.type !== 'blacknode-newton-transform') return
      const transform = message.transform
      const vector = (name: string) => Array.isArray(transform?.[name])
        ? transform[name].slice(0, 3).map(Number)
        : []
      const translate_m = vector('translate_m')
      const rotate_deg = vector('rotate_deg')
      const scale = vector('scale')
      if (
        !message.path
        || [translate_m, rotate_deg, scale].some(values => values.length !== 3 || values.some(value => !Number.isFinite(value)))
        || scale.some(value => value <= 0)
      ) return
      onWorkspaceAction?.('set_transform', {
        path: String(message.path), translate_m, rotate_deg, scale,
      })
    }
    window.addEventListener('message', receiveViewerInteraction)
    return () => window.removeEventListener('message', receiveViewerInteraction)
  }, [onWorkspaceAction, url])

  const changePerceptionMode = useCallback((mode: string) => {
    if (workspaceStatus?.viewer_provider !== 'ovrtx') return
    if (!['rgb', 'depth', 'segmentation', 'detection', 'composite'].includes(mode)) return
    try {
      const viewerOrigin = new URL(url).origin
      viewerFrameRef.current?.contentWindow?.postMessage({
        type: 'blacknode-newton-view', mode,
      }, viewerOrigin)
    } catch {
      // The embedded viewer retains its current mode if its URL is unavailable.
    }
  }, [url, workspaceStatus?.viewer_provider])

  useLayoutEffect(() => {
    if (!floating) return
    const parent = rootRef.current?.parentElement
    if (!parent) return
    const bounds = parent.getBoundingClientRect()
    setFloatingRect(current => {
      const width = Math.min(Math.max(MIN_FLOATING_WIDTH, current.width), Math.max(1, bounds.width - 24))
      const height = Math.min(Math.max(MIN_FLOATING_HEIGHT, current.height), Math.max(1, bounds.height - 24))
      return {
        width,
        height,
        x: Math.max(0, Math.min(current.x, bounds.width - width)),
        y: Math.max(0, Math.min(current.y, bounds.height - height)),
      }
    })
  }, [floating])

  const beginDockedResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const startY = event.clientY
    const startHeight = height
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)

    const move = (moveEvent: PointerEvent) => {
      const maximum = Math.max(260, window.innerHeight - 300)
      onHeightChange(Math.max(180, Math.min(maximum, startHeight + moveEvent.clientY - startY)))
    }
    const finish = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', finish)
      target.removeEventListener('pointercancel', finish)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', finish)
    target.addEventListener('pointercancel', finish)
  }, [height, onHeightChange])

  const beginFloatingMove = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (!floating || event.button !== 0 || (event.target as HTMLElement).closest('button, summary, details')) return
    event.preventDefault()
    const parent = rootRef.current?.parentElement
    if (!parent) return
    const bounds = parent.getBoundingClientRect()
    const start = floatingRect
    const startX = event.clientX
    const startY = event.clientY
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)

    const move = (moveEvent: PointerEvent) => {
      const x = start.x + moveEvent.clientX - startX
      const y = start.y + moveEvent.clientY - startY
      setFloatingRect(current => ({
        ...current,
        x: Math.max(0, Math.min(x, bounds.width - start.width)),
        y: Math.max(0, Math.min(y, bounds.height - start.height)),
      }))
    }
    const finish = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', finish)
      target.removeEventListener('pointercancel', finish)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', finish)
    target.addEventListener('pointercancel', finish)
  }, [floating, floatingRect])

  const beginFloatingResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!floating) return
    event.preventDefault()
    event.stopPropagation()
    const parent = rootRef.current?.parentElement
    if (!parent) return
    const bounds = parent.getBoundingClientRect()
    const start = floatingRect
    const startX = event.clientX
    const startY = event.clientY
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)

    const move = (moveEvent: PointerEvent) => {
      const maximumWidth = Math.max(1, bounds.width - start.x)
      const maximumHeight = Math.max(1, bounds.height - start.y)
      setFloatingRect(current => ({
        ...current,
        width: Math.min(maximumWidth, Math.max(Math.min(MIN_FLOATING_WIDTH, maximumWidth), start.width + moveEvent.clientX - startX)),
        height: Math.min(maximumHeight, Math.max(Math.min(MIN_FLOATING_HEIGHT, maximumHeight), start.height + moveEvent.clientY - startY)),
      }))
    }
    const finish = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', finish)
      target.removeEventListener('pointercancel', finish)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', finish)
    target.addEventListener('pointercancel', finish)
  }, [floating, floatingRect])

  const panelMaximumWidth = useCallback((currentWidth: number) => {
    const viewport = rootRef.current?.querySelector<HTMLElement>('.bn-simulation-viewport')
    const viewportWidth = viewport?.getBoundingClientRect().width ?? MIN_VIEWPORT_WIDTH
    return Math.max(
      MIN_PANEL_WIDTH,
      Math.min(MAX_PANEL_WIDTH, currentWidth + viewportWidth - MIN_VIEWPORT_WIDTH),
    )
  }, [])

  const beginPanelResize = useCallback((side: 'outliner' | 'inspector', event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startWidth = side === 'outliner' ? outlinerWidth : inspectorWidth
    const maximum = panelMaximumWidth(startWidth)
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)

    const move = (moveEvent: PointerEvent) => {
      const delta = side === 'outliner'
        ? moveEvent.clientX - startX
        : startX - moveEvent.clientX
      const width = Math.max(MIN_PANEL_WIDTH, Math.min(maximum, startWidth + delta))
      if (side === 'outliner') setOutlinerWidth(width)
      else setInspectorWidth(width)
    }
    const finish = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', finish)
      target.removeEventListener('pointercancel', finish)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', finish)
    target.addEventListener('pointercancel', finish)
  }, [inspectorWidth, outlinerWidth, panelMaximumWidth])

  const resizePanelWithKeyboard = useCallback((
    side: 'outliner' | 'inspector',
    event: React.KeyboardEvent<HTMLDivElement>,
  ) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const currentWidth = side === 'outliner' ? outlinerWidth : inspectorWidth
    const direction = event.key === 'ArrowRight' ? 1 : -1
    const delta = side === 'outliner' ? direction * 24 : direction * -24
    const width = Math.max(MIN_PANEL_WIDTH, Math.min(panelMaximumWidth(currentWidth), currentWidth + delta))
    if (side === 'outliner') setOutlinerWidth(width)
    else setInspectorWidth(width)
  }, [inspectorWidth, outlinerWidth, panelMaximumWidth])

  const style = floating
    ? {
        left: floatingRect.x,
        top: floatingRect.y,
        width: floatingRect.width,
        height: floatingRect.height,
      }
    : { height }
  const selectedItem = workspaceStatus?.selected_item ?? null
  const environment = workspaceStatus?.environment
  const digitalTwin = workspaceStatus?.digital_twin
  const twinGhost = digitalTwin?.ghost
  const twinGhostPlacement = twinGhost?.placement ?? 'beside'
  const twinGhostOffset = twinGhost?.offset_m ?? [0.35, 0, 0]
  const twinJoints = (workspaceStatus?.joints ?? []).filter(
    joint => joint.reference_position !== null && joint.reference_position !== undefined,
  )
  const twinUnits = new Set(twinJoints.map(joint => joint.units))
  const twinSummaryFactor = twinUnits.size === 1 && twinUnits.has('radians') ? 180 / Math.PI : 1
  const twinSummaryUnit = twinUnits.size === 1
    ? (twinUnits.has('radians') ? '°' : twinUnits.has('metres') ? 'm' : 'SI')
    : ''
  const twinHistory = digitalTwin?.history ?? []
  const twinBaseline = digitalTwin?.baseline
  const twinBaselineHistory = twinBaseline?.history ?? []
  const twinArtifacts = workspaceStatus?.digital_twin_artifacts ?? []
  const twinHistorySpan = twinHistory.length > 1
    ? Math.max(0, twinHistory[twinHistory.length - 1].received_at - twinHistory[0].received_at)
    : 0
  const twinTraceWidth = 240
  const twinTraceHeight = 58
  const twinTraceMaximum = Math.max(
    Number.EPSILON,
    ...twinHistory.flatMap(sample => [sample.max_abs_error, sample.rms_error]),
    ...twinBaselineHistory.flatMap(sample => [sample.max_abs_error, sample.rms_error]),
  )
  const twinTracePoints = (
    samples: typeof twinHistory,
    field: 'max_abs_error' | 'rms_error',
  ) => samples
    .map((sample, index) => {
      const x = samples.length > 1 ? index * twinTraceWidth / (samples.length - 1) : 0
      const y = twinTraceHeight - Math.max(0, sample[field]) * twinTraceHeight / twinTraceMaximum
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
  const sceneItems = workspaceStatus?.scene_items ?? []
  const lightsItem = sceneItems.find(item => item.type_name === 'LightScope')
  const parentPaths = new Set(sceneItems.map(item => item.parent_path))
  const visibleSceneItems = sceneItems.filter(item => {
    const parts = item.path.split('/').filter(Boolean)
    return !parts.slice(0, -1).some((_part, index) =>
      collapsedPaths.has(`/${parts.slice(0, index + 1).join('/')}`))
  })

  const toggleHierarchy = (path: string) => {
    setCollapsedPaths(current => {
      const next = new Set(current)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  return (
    <section
      ref={rootRef}
      className={`bn-simulation-viewer${floating ? ' is-floating' : ''}${visible ? '' : ' is-hidden'}`}
      style={style}
      aria-label="Simulation viewer"
      aria-hidden={!visible}
    >
      <header
        className={`bn-simulation-viewer-header${floating ? ' is-draggable' : ''}`}
        onPointerDown={beginFloatingMove}
      >
        <span className={`bn-simulation-viewer-dot${phase === 'fault' ? ' is-fault' : ''}`} />
        <strong>{label}</strong>
        <span className="bn-simulation-viewer-state">
          {workspace
            ? `${sceneLabel || 'Empty stage'} · ${simulationRunning ? 'playing' : 'stopped'} · ${armed ? 'ARMED' : 'motion disarmed'}`
            : `${phase || 'running'} · ${armed ? 'ARMED' : 'motion disarmed'}`}
        </span>
        {workspace && (
          <nav
            className="bn-simulation-app-menus"
            aria-label="Newton menus"
            onMouseEnter={cancelMenuClose}
            onMouseLeave={event => scheduleMenuClose(event.currentTarget)}
            onClick={closeSiblingMenus}
          >
            <details>
              <summary>File</summary>
              <div role="menu">
                <button type="button" role="menuitem" disabled={busy} onClick={event => {
                  onNewStage?.()
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>New stage</button>
                <button type="button" role="menuitem" disabled={busy} onClick={event => {
                  onOpenUsd?.()
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>Open scene…</button>
                <button type="button" role="menuitem" disabled={busy} onClick={event => {
                  onCloseWorkspace?.()
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>Close Newton</button>
              </div>
            </details>
            <details>
              <summary>Simulation</summary>
              <div role="menu">
                <button type="button" role="menuitem" disabled={busy || simulationRunning} onClick={event => {
                  onPlay?.()
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>Start</button>
                <button type="button" role="menuitem" disabled={busy || !simulationRunning} onClick={event => {
                  onStop?.()
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>Stop</button>
                <button type="button" role="menuitem" disabled={busy} onClick={event => {
                  onReset?.()
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>Reset</button>
              </div>
            </details>
            <details>
              <summary>Edit</summary>
              <div role="menu">
                <button type="button" role="menuitem" disabled={busy || !workspaceStatus?.selected_item} onClick={event => {
                  if (workspaceStatus?.selected_item) onWorkspaceAction?.('set_visibility', {
                    path: workspaceStatus.selected_item.path,
                    visible: false,
                  })
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>Hide selected</button>
                <button type="button" role="menuitem" disabled={busy || !workspaceStatus?.selected_item} onClick={event => {
                  if (workspaceStatus?.selected_item) onWorkspaceAction?.('set_visibility', {
                    path: workspaceStatus.selected_item.path,
                    visible: true,
                  })
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>Show selected</button>
              </div>
            </details>
            <details>
              <summary>View</summary>
              <div role="menu">
                <button type="button" role="menuitemcheckbox" aria-checked={workspaceStatus?.show_grid ?? true} disabled={busy} onClick={event => {
                  onWorkspaceAction?.('set_grid', { show_grid: !(workspaceStatus?.show_grid ?? true) })
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>{workspaceStatus?.show_grid ? '✓ ' : ''}Grid</button>
                <button type="button" role="menuitemcheckbox" aria-checked={workspaceStatus?.show_visuals ?? true} disabled={busy} onClick={event => {
                  onWorkspaceAction?.('set_render_options', {
                    show_visuals: !(workspaceStatus?.show_visuals ?? true),
                    show_colliders: workspaceStatus?.show_colliders ?? false,
                  })
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>{workspaceStatus?.show_visuals ?? true ? '✓ ' : ''}Visual geometry</button>
                <button type="button" role="menuitemcheckbox" aria-checked={workspaceStatus?.show_colliders ?? false} disabled={busy} onClick={event => {
                  onWorkspaceAction?.('set_render_options', {
                    show_visuals: workspaceStatus?.show_visuals ?? true,
                    show_colliders: !(workspaceStatus?.show_colliders ?? false),
                  })
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>{workspaceStatus?.show_colliders ? '✓ ' : ''}Collision geometry</button>
                <button type="button" role="menuitemcheckbox" aria-checked={lightsItem?.visible ?? false} disabled={busy || !lightsItem || lightsItem.visibility_editable === false} onClick={event => {
                  if (lightsItem) onWorkspaceAction?.('set_visibility', {
                    path: lightsItem.path,
                    visible: !lightsItem.visible,
                  })
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>{lightsItem?.visible ? '✓ ' : ''}All lights</button>
                <button type="button" role="menuitemcheckbox" aria-checked={environmentVisible} onClick={event => {
                  setEnvironmentVisible(value => !value)
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>{environmentVisible ? '✓ ' : ''}Environment</button>
                <button type="button" role="menuitemcheckbox" aria-checked={perceptionVisible} onClick={event => {
                  setPerceptionVisible(value => !value)
                  event.currentTarget.closest('details')?.removeAttribute('open')
                }}>{perceptionVisible ? '✓ ' : ''}Perception views</button>
              </div>
            </details>
            <details>
              <summary>Window</summary>
              <div role="menu">
                <button type="button" role="menuitemcheckbox" aria-checked={outlinerVisible} onClick={() => setOutlinerVisible(value => !value)}>{outlinerVisible ? '✓ ' : ''}Outliner</button>
                <button type="button" role="menuitemcheckbox" aria-checked={propertiesVisible} onClick={() => setPropertiesVisible(value => !value)}>{propertiesVisible ? '✓ ' : ''}Properties</button>
                <button type="button" role="menuitemcheckbox" aria-checked={controllerVisible} onClick={() => setControllerVisible(value => !value)}>{controllerVisible ? '✓ ' : ''}Robot Controller</button>
              </div>
            </details>
          </nav>
        )}
        <span className="bn-simulation-viewer-url" title={warning || url}>{warning || url}</span>
        {workspace && (
          <div className="bn-simulation-app-transport" aria-label="Simulation controls">
            <button type="button" onClick={simulationRunning ? onStop : onPlay} disabled={busy}>
              {simulationRunning ? '■ Stop' : '▶ Start'}
            </button>
            <button type="button" onClick={onReset} disabled={busy}>↺ Reset</button>
          </div>
        )}
        <button type="button" onClick={() => setReloadKey(value => value + 1)} title="Reload embedded viewer">
          Reload
        </button>
        <button
          type="button"
          onClick={floating ? onAttach : onDetach}
          title={floating ? 'Attach the viewer above the node canvas' : 'Float the live viewer inside Blacknode'}
        >
          {floating ? 'Attach' : 'Float'}
        </button>
        <button type="button" onClick={onClose} title="Hide viewer and expand the node canvas">
          Hide
        </button>
      </header>
      <div className={`bn-simulation-workspace${workspace ? ' is-editor' : ''}`}>
        {workspace && outlinerVisible && <>
          <aside
            className="bn-simulation-panel bn-simulation-outliner"
            aria-label="Scene outliner"
            style={{ width: outlinerWidth }}
          >
            <div className="bn-simulation-panel-title"><strong>Outliner</strong><span>{workspaceStatus?.scene_items.length ?? 0}</span></div>
            <div className="bn-simulation-outliner-list">
              {visibleSceneItems.map(item => (
                <div
                  key={item.path}
                  className={`bn-simulation-outliner-item${item.path === workspaceStatus?.selected_path ? ' is-selected' : ''}`}
                  style={{ paddingLeft: 8 + Math.max(0, item.path.split('/').length - 2) * 12 }}
                >
                  {parentPaths.has(item.path) ? <button
                    type="button"
                    className="bn-simulation-disclosure"
                    title={collapsedPaths.has(item.path) ? 'Expand hierarchy' : 'Collapse hierarchy'}
                    aria-expanded={!collapsedPaths.has(item.path)}
                    onClick={() => toggleHierarchy(item.path)}
                  >{collapsedPaths.has(item.path) ? '▸' : '▾'}</button> : <span className="bn-simulation-disclosure-spacer" />}
                  <button
                    type="button"
                    className="bn-simulation-object"
                    title={item.path}
                    onClick={() => onWorkspaceAction?.('select', { path: item.path })}
                  ><span>{item.name}</span><small>{item.render_role === 'collider' ? `COL · ${item.type_name}` : item.type_name}</small></button>
                  <button
                    type="button"
                    className="bn-simulation-eye"
                    title={item.visibility_editable === false
                      ? 'This light is unavailable in the active viewer'
                      : item.visible ? 'Hide object' : 'Show object'}
                    aria-label={item.visible ? `Hide ${item.name}` : `Show ${item.name}`}
                    disabled={busy || item.visibility_editable === false}
                    onClick={() => onWorkspaceAction?.('set_visibility', { path: item.path, visible: !item.visible })}
                  >{item.visible ? '◉' : '○'}</button>
                </div>
              ))}
              {!workspaceStatus?.scene_items.length && <p className="bn-simulation-empty">No scene objects</p>}
            </div>
          </aside>
          <div
            className="bn-simulation-panel-resize is-outliner"
            role="separator"
            aria-label="Resize Outliner"
            aria-orientation="vertical"
            aria-valuemin={MIN_PANEL_WIDTH}
            aria-valuemax={MAX_PANEL_WIDTH}
            aria-valuenow={Math.round(outlinerWidth)}
            title="Drag to resize Outliner · double-click to reset"
            tabIndex={0}
            onPointerDown={event => beginPanelResize('outliner', event)}
            onKeyDown={event => resizePanelWithKeyboard('outliner', event)}
            onDoubleClick={() => setOutlinerWidth(DEFAULT_OUTLINER_WIDTH)}
          ><i /></div>
        </>}
        <div className="bn-simulation-viewport">
          <iframe
            ref={viewerFrameRef}
            key={`${url}:${reloadKey}`}
            className="bn-simulation-viewer-frame"
            src={url}
            title={label}
            allow="clipboard-read; clipboard-write; fullscreen"
            referrerPolicy="no-referrer"
          />
        </div>
        {workspace && (propertiesVisible || controllerVisible || environmentVisible || perceptionVisible) && <>
          <div
            className="bn-simulation-panel-resize is-inspector"
            role="separator"
            aria-label="Resize Properties and workspace tools"
            aria-orientation="vertical"
            aria-valuemin={MIN_PANEL_WIDTH}
            aria-valuemax={MAX_PANEL_WIDTH}
            aria-valuenow={Math.round(inspectorWidth)}
            title="Drag to resize Properties · double-click to reset"
            tabIndex={0}
            onPointerDown={event => beginPanelResize('inspector', event)}
            onKeyDown={event => resizePanelWithKeyboard('inspector', event)}
            onDoubleClick={() => setInspectorWidth(DEFAULT_INSPECTOR_WIDTH)}
          ><i /></div>
          <aside
            className="bn-simulation-panel bn-simulation-inspector"
            aria-label="Newton workspace tools"
            style={{ width: inspectorWidth }}
          >
            {perceptionVisible && (
              <section>
                <div className="bn-simulation-panel-title"><strong>Perception</strong><button type="button" onClick={() => setPerceptionVisible(false)}>×</button></div>
                {workspaceStatus?.viewer_provider === 'ovrtx' ? <>
                  <div className="bn-simulation-mode-grid" role="group" aria-label="OVRT perception view">
                    {[
                      ['rgb', 'RGB'],
                      ['depth', 'Depth IR'],
                      ['segmentation', 'Segments'],
                      ['detection', 'Boxes'],
                      ['composite', 'Composite'],
                    ].map(([mode, modeLabel]) => <button
                      key={mode}
                      type="button"
                      className={perceptionMode === mode ? 'is-active' : ''}
                      onClick={() => void changePerceptionMode(mode)}
                    >{modeLabel}</button>)}
                  </div>
                  <p className="bn-simulation-hint">Depth uses an infrared heat palette. Segments and boxes are exact USD ground truth from semantic object labels.</p>
                </> : <p className="bn-simulation-hint">Switch the Newton viewer to OVRT (RTX) to use depth, segmentation, and detection overlays.</p>}
              </section>
            )}
            {environmentVisible && environment && (
              <section>
                <div className="bn-simulation-panel-title"><strong>Environment</strong><button type="button" onClick={() => setEnvironmentVisible(false)}>×</button></div>
                <form key={`environment:${environment.hdri_enabled}`} onChange={event => event.currentTarget.requestSubmit()} onSubmit={event => {
                  event.preventDefault()
                  const data = new FormData(event.currentTarget)
                  const hdri = String(data.get('hdri'))
                  onWorkspaceAction?.('set_environment', {
                    background_color: String(data.get('background_color')),
                    hdri,
                    hdri_path: hdri === 'custom' ? environment.hdri_path : '',
                    hdri_enabled: data.get('hdri_enabled') === 'on',
                    intensity: formNumber(data, 'intensity', 1),
                    show_background: data.get('show_background') === 'on',
                  })
                }}>
                  <label>Fallback background <input name="background_color" type="color" defaultValue={environment.background_color} /></label>
                  <label>HDRI preset <select
                    key={`${environment.hdri}:${environment.hdri_path}`}
                    name="hdri"
                    defaultValue={environment.hdri_path ? 'custom' : environment.hdri || 'none'}
                  >
                    <option value="none">None</option><option value="apartment">Apartment</option><option value="city">City</option>
                    <option value="dawn">Dawn</option><option value="forest">Forest</option><option value="lobby">Lobby</option>
                    <option value="night">Night</option><option value="park">Park</option><option value="studio">Studio</option>
                    <option value="sunset">Sunset</option><option value="warehouse">Warehouse</option>
                    {environment.hdri_path && <option value="custom">Custom · {environment.hdri_path.split(/[\\/]/).pop()}</option>}
                  </select></label>
                  <label>Intensity <input name="intensity" type="number" min="0" max="100" step="0.1" defaultValue={environment.intensity} /></label>
                  <label className="bn-simulation-checkbox"><input name="hdri_enabled" type="checkbox" defaultChecked={environment.hdri_enabled} /> Enable HDRI light</label>
                  <label className="bn-simulation-checkbox"><input name="show_background" type="checkbox" defaultChecked={environment.show_background} /> Show HDRI background</label>
                  <div className="bn-simulation-file-row">
                    <button type="button" onClick={onChooseHdri}>Choose custom HDRI…</button>
                    {environment.hdri_path && <small title={environment.hdri_path}>{environment.hdri_path.split(/[\\/]/).pop()}</small>}
                  </div>
                  <p className="bn-simulation-hint">HDRI lighting remains active when its background is hidden. The fallback color does not tint an active HDRI; intensity affects the dome light.</p>
                  {!environment.custom_hdri_supported && environment.hdri_path && <p className="bn-simulation-hint">Switch to OVRT to render the selected HDRI file.</p>}
                </form>
              </section>
            )}
            {propertiesVisible && (
              <section>
                <div className="bn-simulation-panel-title"><strong>Properties</strong><button type="button" onClick={() => setPropertiesVisible(false)}>×</button></div>
                {!selectedItem ? <p className="bn-simulation-empty">Select an object in the Outliner.</p> : <>
                  <div className="bn-simulation-selection"><strong>{selectedItem.name}</strong><small>{selectedItem.path}</small></div>
                  <div className="bn-simulation-inline-actions">
                    <button type="button" disabled={busy || selectedItem.visibility_editable === false} onClick={() => onWorkspaceAction?.('set_visibility', { path: selectedItem.path, visible: !selectedItem.visible })}>{selectedItem.visible ? 'Hide' : 'Show'}</button>
                  </div>
                  {selectedItem.light ? <>
                    {selectedItem.light.kind === 'scope' && <p className="bn-simulation-hint">The Lights eye and View → All lights switch the distant and HDRI lights together.</p>}
                    {selectedItem.light.kind === 'distant' && <form key={`light:${selectedItem.path}:${selectedItem.light.enabled}`} onInput={event => event.currentTarget.requestSubmit()} onSubmit={event => {
                      event.preventDefault()
                      const data = new FormData(event.currentTarget)
                      onWorkspaceAction?.('set_light', {
                        path: selectedItem.path,
                        enabled: data.get('enabled') === 'on',
                        intensity: formNumber(data, 'intensity', 2500),
                        color: String(data.get('color')),
                        angle_deg: formNumber(data, 'angle_deg', 4),
                        rotation_deg: ['rx', 'ry', 'rz'].map(name => formNumber(data, name)),
                      })
                    }}>
                      <fieldset disabled={busy || selectedItem.available === false}><legend>Distant light</legend>
                        <label className="bn-simulation-checkbox"><input name="enabled" type="checkbox" defaultChecked={selectedItem.light.enabled} /> Enabled</label>
                        <label>Intensity <input name="intensity" type="number" min="0" max="10000000" step="100" defaultValue={selectedItem.light.intensity ?? 2500} /></label>
                        <label>Color <input name="color" type="color" defaultValue={selectedItem.light.color ?? '#fff2e0'} /></label>
                        <label>Angular size <input name="angle_deg" type="number" min="0" max="180" step="0.1" defaultValue={selectedItem.light.angle_deg ?? 4} /></label>
                        <div className="bn-simulation-vector">
                          <span>Rotate</span>
                          {(selectedItem.light.rotation_deg ?? [-35, 25, -25]).map((value, axis) => <label key={axis}>{'XYZ'[axis]}<input name={`r${'xyz'[axis]}`} type="number" step="1" defaultValue={value} /></label>)}
                        </div>
                      </fieldset>
                      <p className="bn-simulation-hint">Intensity, color, softness angle, and direction update the OVRT sun live.</p>
                    </form>}
                    {selectedItem.light.kind === 'dome' && <form key={`dome:${selectedItem.path}:${selectedItem.light.enabled}`} onInput={event => event.currentTarget.requestSubmit()} onSubmit={event => {
                      event.preventDefault()
                      const data = new FormData(event.currentTarget)
                      onWorkspaceAction?.('set_environment', {
                        hdri_enabled: data.get('enabled') === 'on',
                        intensity: formNumber(data, 'intensity', 1),
                        show_background: data.get('show_background') === 'on',
                      })
                    }}>
                      <fieldset disabled={busy || !selectedItem.light.selected}><legend>HDRI dome light</legend>
                        <label className="bn-simulation-checkbox"><input name="enabled" type="checkbox" defaultChecked={selectedItem.light.enabled} /> Enabled</label>
                        <label>Intensity <input name="intensity" type="number" min="0" max="100" step="0.1" defaultValue={selectedItem.light.intensity ?? 1} /></label>
                        <label className="bn-simulation-checkbox"><input name="show_background" type="checkbox" defaultChecked={selectedItem.light.show_background} /> Show background</label>
                      </fieldset>
                      {!selectedItem.light.selected && <p className="bn-simulation-hint">Choose an HDRI in the Environment panel to enable this dome light.</p>}
                    </form>}
                  </> : <>
                  <form key={`xform:${selectedItem.path}`} onInput={event => event.currentTarget.requestSubmit()} onSubmit={event => {
                    event.preventDefault()
                    const data = new FormData(event.currentTarget)
                    onWorkspaceAction?.('set_transform', {
                      path: selectedItem.path,
                      translate_m: ['tx', 'ty', 'tz'].map(name => formNumber(data, name)),
                      rotate_deg: ['rx', 'ry', 'rz'].map(name => formNumber(data, name)),
                      scale: ['sx', 'sy', 'sz'].map(name => formNumber(data, name, 1)),
                    })
                  }}>
                    <fieldset disabled={!selectedItem.editable || busy}><legend>Transform</legend>
                      {(['translate_m', 'rotate_deg', 'scale'] as const).map((group, row) => <div className="bn-simulation-vector" key={group}>
                        <span>{row === 0 ? 'Move' : row === 1 ? 'Rotate' : 'Scale'}</span>
                        {selectedItem.transform[group].map((value, axis) => <label key={axis}>{'XYZ'[axis]}<input name={`${['t', 'r', 's'][row]}${'xyz'[axis]}`} type="number" step={row === 1 ? '1' : '0.01'} defaultValue={value} /></label>)}
                      </div>)}
                    </fieldset>
                  </form>
                  <form key={`material:${selectedItem.path}`} onInput={event => event.currentTarget.requestSubmit()} onSubmit={event => {
                    event.preventDefault()
                    const data = new FormData(event.currentTarget)
                    onWorkspaceAction?.('set_material', {
                      path: selectedItem.path,
                      base_color: hexToRgb(String(data.get('base_color'))),
                      metallic: formNumber(data, 'metallic'),
                      roughness: formNumber(data, 'roughness', 0.5),
                      opacity: formNumber(data, 'opacity', 1),
                    })
                  }}>
                    <fieldset disabled={busy || !selectedItem.material_editable}><legend>Material</legend>
                      <label>Base color <input name="base_color" type="color" defaultValue={rgbToHex(selectedItem.material.base_color)} /></label>
                      <label>Metallic <input name="metallic" type="range" min="0" max="1" step="0.01" defaultValue={selectedItem.material.metallic} /></label>
                      <label>Roughness <input name="roughness" type="range" min="0" max="1" step="0.01" defaultValue={selectedItem.material.roughness} /></label>
                      <label>Opacity <input name="opacity" type="range" min="0" max="1" step="0.01" defaultValue={selectedItem.material.opacity} /></label>
                    </fieldset>
                  </form>
                  </>}
                </>}
              </section>
            )}
            {controllerVisible && (
              <section>
                <div className="bn-simulation-panel-title"><strong>Robot Controller</strong><button type="button" onClick={() => setControllerVisible(false)}>×</button></div>
                <button
                  type="button"
                  className={`bn-simulation-arm${workspaceStatus?.armed ? ' is-armed' : ''}`}
                  disabled={busy || !workspaceStatus?.joints.length}
                  onClick={() => onWorkspaceAction?.(workspaceStatus?.armed ? 'disarm' : 'arm')}
                >{workspaceStatus?.armed ? 'Disarm motion' : 'Arm motion'}</button>
                {!!workspaceStatus?.joints.length && <small className="bn-simulation-controller-meta">
                  XPBD · {workspaceStatus.fps ?? 60} Hz · {workspaceStatus.substeps ?? 4} substeps · {workspaceStatus.solver_iterations ?? 16} iterations
                </small>}
                {digitalTwin?.available && <div className={`bn-simulation-digital-twin${digitalTwin.stale ? ' is-stale' : ' is-live'}`}>
                  <div className="bn-simulation-digital-twin-header">
                    <strong>Digital Twin</strong>
                    <div><span>{digitalTwin.stale ? 'STALE' : 'LIVE'}</span>
                      <button type="button" disabled={busy || twinHistory.length === 0} onClick={() => onWorkspaceAction?.('clear_digital_twin_history')}>Clear trace</button>
                    </div>
                  </div>
                  <small title={digitalTwin.source}>{digitalTwin.source || 'external joint telemetry'}</small>
                  <div className="bn-simulation-digital-twin-metrics">
                    <span><strong>{digitalTwin.matched_joint_count}</strong> joints</span>
                    <span><strong>{digitalTwin.age_seconds === null ? '—' : compactNumber(digitalTwin.age_seconds * 1000, 3)}</strong> ms age</span>
                    <span><strong>{digitalTwin.source_latency_seconds === null ? '—' : compactNumber(digitalTwin.source_latency_seconds * 1000, 3)}</strong> ms source</span>
                    {twinSummaryUnit && <span><strong>{compactNumber(digitalTwin.max_abs_error * twinSummaryFactor, 3)}</strong> {twinSummaryUnit} max error</span>}
                    {twinSummaryUnit && <span><strong>{compactNumber(digitalTwin.rms_error * twinSummaryFactor, 3)}</strong> {twinSummaryUnit} RMS error</span>}
                  </div>
                  <div className="bn-simulation-digital-twin-sync">
                    <label><input
                      type="checkbox"
                      checked={twinGhost?.visible ?? true}
                      onChange={event => onWorkspaceAction?.('set_digital_twin_ghost', {
                        visible: event.currentTarget.checked,
                        placement: twinGhostPlacement,
                        offset_m: twinGhostOffset,
                      })}
                    /> Show real-pose ghost</label>
                    <label>Placement <select
                      value={twinGhostPlacement}
                      onChange={event => onWorkspaceAction?.('set_digital_twin_ghost', {
                        visible: twinGhost?.visible ?? true,
                        placement: event.currentTarget.value,
                        offset_m: twinGhostOffset,
                      })}
                    >
                      <option value="beside">Beside simulation</option>
                      <option value="overlay">Overlay simulation</option>
                      <option value="custom">Custom offset</option>
                    </select></label>
                    {twinGhostPlacement === 'custom' && <form
                      key={twinGhostOffset.join(':')}
                      className="bn-simulation-digital-twin-offset"
                      onInput={event => {
                        const data = new FormData(event.currentTarget)
                        onWorkspaceAction?.('set_digital_twin_ghost', {
                          visible: twinGhost?.visible ?? true,
                          placement: 'custom',
                          offset_m: [
                            formNumber(data, 'ghost_x', twinGhostOffset[0]),
                            formNumber(data, 'ghost_y', twinGhostOffset[1]),
                            formNumber(data, 'ghost_z', twinGhostOffset[2]),
                          ],
                        })
                      }}
                    >
                      {(['x', 'y', 'z'] as const).map((axis, index) => <label key={axis}>{axis.toUpperCase()}
                        <input name={`ghost_${axis}`} type="number" step="0.01" defaultValue={compactNumber(twinGhostOffset[index])} aria-label={`Ghost offset ${axis.toUpperCase()} in metres`} />
                      </label>)}
                    </form>}
                    <button
                      type="button"
                      disabled={busy || !workspaceStatus?.armed || digitalTwin.stale || digitalTwin.matched_joint_count === 0}
                      title="Simulation only: uses the existing arm, stale-data, rate, and joint-limit safety gates"
                      onClick={() => onWorkspaceAction?.('sync_digital_twin_pose')}
                    >Sync Newton once to real pose</button>
                    <small>Ghost updates are read-only. Sync once moves only Newton and requires armed motion plus fresh telemetry.</small>
                  </div>
                  {twinBaseline?.artifact_id && <div className="bn-simulation-digital-twin-baseline">
                    <span><strong>Baseline</strong> {twinBaseline.name}{twinSummaryUnit ? ` · max ${compactNumber((twinBaseline.summary.max_abs_error ?? 0) * twinSummaryFactor, 3)} ${twinSummaryUnit}` : ''}</span>
                    <button type="button" disabled={busy} onClick={() => onWorkspaceAction?.('clear_digital_twin_baseline')}>Clear baseline</button>
                  </div>}
                  {twinSummaryUnit && (twinHistory.length > 1 || twinBaselineHistory.length > 1) && <div className="bn-simulation-digital-twin-trace">
                    <svg viewBox={`0 0 ${twinTraceWidth} ${twinTraceHeight}`} role="img" aria-label="Digital Twin tracking error history">
                      <line x1="0" y1={twinTraceHeight / 2} x2={twinTraceWidth} y2={twinTraceHeight / 2} />
                      {twinBaselineHistory.length > 1 && <polyline className="is-baseline" points={twinTracePoints(twinBaselineHistory, 'max_abs_error')} />}
                      {twinHistory.length > 1 && <polyline className="is-maximum" points={twinTracePoints(twinHistory, 'max_abs_error')} />}
                      {twinHistory.length > 1 && <polyline className="is-rms" points={twinTracePoints(twinHistory, 'rms_error')} />}
                    </svg>
                    <small><i className="is-maximum" /> max <i className="is-rms" /> RMS {twinBaselineHistory.length > 1 && <><i className="is-baseline" /> baseline </>}· {twinHistory.length}/{digitalTwin.history_limit} samples · {compactNumber(twinHistorySpan, 3)} s</small>
                  </div>}
                  <small>Reference telemetry is read-only. Arm motion explicitly before ROS commands can drive Newton.</small>
                </div>}
                {(twinHistory.length > 0 || twinArtifacts.length > 0 || workspaceStatus?.digital_twin_artifact_error) && <div className="bn-simulation-digital-twin-artifacts">
                  <strong>Saved tracking runs</strong>
                  {twinHistory.length > 0 && <form onSubmit={event => {
                    event.preventDefault()
                    const data = new FormData(event.currentTarget)
                    onWorkspaceAction?.('save_digital_twin_artifact', { name: String(data.get('name') || '') })
                  }}>
                    <input name="name" type="text" maxLength={120} placeholder="Run name (optional)" aria-label="Newton run artifact name" />
                    <button type="submit" disabled={busy}>Save trace</button>
                  </form>}
                  {twinArtifacts.length > 0 && <form onSubmit={event => {
                    event.preventDefault()
                    const data = new FormData(event.currentTarget)
                    onWorkspaceAction?.('load_digital_twin_baseline', { artifact_id: String(data.get('artifact_id') || '') })
                  }}>
                    <select name="artifact_id" defaultValue={twinBaseline?.artifact_id || twinArtifacts[0].artifact_id} aria-label="Saved Newton run">
                      {twinArtifacts.map(artifact => <option key={artifact.artifact_id} value={artifact.artifact_id}>{artifact.name} · {artifact.sample_count} samples</option>)}
                    </select>
                    <button type="submit" disabled={busy}>Compare</button>
                  </form>}
                  {workspaceStatus?.digital_twin_artifact_error && <small>{workspaceStatus.digital_twin_artifact_error}</small>}
                </div>}
                {(workspaceStatus?.joints ?? []).map(joint => {
                  const angular = joint.units === 'radians'
                  const factor = angular ? 180 / Math.PI : 1
                  const lower = joint.limits[0] * factor
                  const upper = joint.limits[1] * factor
                  const target = joint.target * factor
                  const applied = (joint.applied_target ?? joint.target) * factor
                  const speed = (joint.max_velocity ?? Math.PI / 4) * factor
                  const maxStep = (joint.max_step ?? Math.PI / 90) * factor
                  const effectiveSpeed = Math.min(speed, maxStep * (workspaceStatus?.fps ?? 60))
                  const remaining = effectiveSpeed > 0 ? Math.abs(target - applied) / effectiveSpeed : 0
                  const stiffnessUnit = angular ? 'N·m/rad' : 'N/m'
                  const dampingUnit = angular ? 'N·m·s/rad' : 'N·s/m'
                  const coordinateUnit = angular ? '°' : 'm'
                  const speedUnit = angular ? '°/s' : 'm/s'
                  const sendTarget = (value: string) => queueJointTarget(
                    joint.name, Number(value) / factor,
                  )
                  return <details className="bn-simulation-joint" key={joint.name} open>
                    <summary><strong>{joint.name}</strong><span>{(joint.position * factor).toFixed(2)} {angular ? '°' : 'm'}</span></summary>
                    <label className="bn-simulation-joint-slider">Target
                      <input type="range" min={lower} max={upper} step={Math.max((upper - lower) / 720, 0.001)} defaultValue={target} disabled={busy || !workspaceStatus?.armed}
                        onInput={event => sendTarget(event.currentTarget.value)} />
                    </label>
                    <small>{lower.toFixed(2)} … {upper.toFixed(2)} {angular ? 'degrees' : 'metres'}</small>
                    <small className="bn-simulation-joint-dynamics">
                      Command {compactNumber(target)} {coordinateUnit} · ramped {compactNumber(applied)} {coordinateUnit} · current {compactNumber(joint.position * factor)} {coordinateUnit}
                      {remaining > 0.02 ? ` · ${compactNumber(remaining, 3)} s ramp` : ''}<br />
                      {joint.reference_position !== null && joint.reference_position !== undefined && <>
                        Twin {compactNumber(joint.reference_position * factor)} {coordinateUnit} · tracking Δ {compactNumber((joint.tracking_error ?? 0) * factor)} {coordinateUnit}<br />
                      </>}
                      Child link {joint.child_body || '—'} · mass {compactNumber(joint.child_body_mass_kg ?? 0)} kg · inertia diag [{(joint.child_body_inertia_kg_m2 ?? [0, 0, 0]).map(value => compactNumber(value, 3)).join(', ')}] kg·m²
                    </small>
                    <form key={`${joint.name}:drive`} onSubmit={event => {
                      event.preventDefault()
                      const stiffness = committedFormNumber(event.currentTarget, 'stiffness')
                      const damping = committedFormNumber(event.currentTarget, 'damping')
                      if (stiffness === null || damping === null) return
                      onWorkspaceAction?.('set_joint_properties', {
                        name: joint.name,
                        stiffness,
                        damping,
                      })
                    }}>
                      <label>Drive stiffness <input aria-label={`Drive stiffness in ${stiffnessUnit}`} title={stiffnessUnit} name="stiffness" type="text" inputMode="decimal" defaultValue={String(joint.stiffness)} onInput={event => event.currentTarget.setCustomValidity('')} onKeyDown={commitNumberOnEnter} onBlur={event => event.currentTarget.form?.requestSubmit()} /></label>
                      <label>Drive damping <input aria-label={`Drive damping in ${dampingUnit}`} title={dampingUnit} name="damping" type="text" inputMode="decimal" defaultValue={String(joint.damping)} onInput={event => event.currentTarget.setCustomValidity('')} onKeyDown={commitNumberOnEnter} onBlur={event => event.currentTarget.form?.requestSubmit()} /></label>
                      <small>{stiffnessUnit} stiffness · {dampingUnit} damping · passive {compactNumber(joint.passive_damping ?? 0)}</small>
                    </form>
                    <form key={`${joint.name}:motion`} onSubmit={event => {
                      event.preventDefault()
                      const maxVelocity = committedFormNumber(event.currentTarget, 'max_velocity')
                      const maxStepValue = committedFormNumber(event.currentTarget, 'max_step')
                      if (maxVelocity === null || maxStepValue === null) return
                      onWorkspaceAction?.('set_joint_motion', {
                        name: joint.name,
                        max_velocity: maxVelocity / factor,
                        max_step: maxStepValue / factor,
                      })
                    }}>
                      <label>Target speed <input aria-label={`Target speed in ${speedUnit}`} title={speedUnit} name="max_velocity" type="text" inputMode="decimal" defaultValue={compactNumber(speed, 8)} onInput={event => event.currentTarget.setCustomValidity('')} onKeyDown={commitNumberOnEnter} onBlur={event => event.currentTarget.form?.requestSubmit()} /></label>
                      <label>Max step <input aria-label={`Maximum step in ${coordinateUnit} per frame`} title={`${coordinateUnit}/frame`} name="max_step" type="text" inputMode="decimal" defaultValue={compactNumber(maxStep, 8)} onInput={event => event.currentTarget.setCustomValidity('')} onKeyDown={commitNumberOnEnter} onBlur={event => event.currentTarget.form?.requestSubmit()} /></label>
                      <small>{speedUnit} target · {coordinateUnit}/frame step · effective {compactNumber(effectiveSpeed)} {speedUnit}</small>
                    </form>
                  </details>
                })}
                {!workspaceStatus?.joints.length && <p className="bn-simulation-empty">No controllable one-DOF joints in this stage.</p>}
              </section>
            )}
          </aside>
        </>}
      </div>
      {floating ? (
        <div
          className="bn-simulation-viewer-float-resize"
          role="separator"
          aria-label="Resize floating simulation viewer"
          tabIndex={0}
          onPointerDown={beginFloatingResize}
        />
      ) : (
        <div
          className="bn-simulation-viewer-resize"
          role="separator"
          aria-label="Resize simulation viewer and node canvas"
          aria-orientation="horizontal"
          aria-valuemin={180}
          aria-valuenow={Math.round(height)}
          tabIndex={0}
          onPointerDown={beginDockedResize}
          onKeyDown={event => {
            if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
            event.preventDefault()
            onHeightChange(Math.max(180, height + (event.key === 'ArrowDown' ? 24 : -24)))
          }}
        >
          <i />
        </div>
      )}
    </section>
  )
}
