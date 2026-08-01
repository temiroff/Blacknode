import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'

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
}

interface FloatingRect {
  x: number
  y: number
  width: number
  height: number
}

const MIN_FLOATING_WIDTH = 420
const MIN_FLOATING_HEIGHT = 260

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
}: SimulationViewerPaneProps) {
  const [reloadKey, setReloadKey] = useState(0)
  const [floatingRect, setFloatingRect] = useState<FloatingRect>({
    x: 24,
    y: 24,
    width: 760,
    height: 520,
  })
  const rootRef = useRef<HTMLElement | null>(null)

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

  const style = floating
    ? {
        left: floatingRect.x,
        top: floatingRect.y,
        width: floatingRect.width,
        height: floatingRect.height,
      }
    : { height }

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
          <nav className="bn-simulation-app-menus" aria-label="Newton menus">
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
                }}>Open USD…</button>
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
      <iframe
        key={`${url}:${reloadKey}`}
        className="bn-simulation-viewer-frame"
        src={url}
        title={label}
        allow="clipboard-read; clipboard-write; fullscreen"
        referrerPolicy="no-referrer"
      />
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
