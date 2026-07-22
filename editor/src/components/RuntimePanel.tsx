import { useEffect, useState } from 'react'
import { api, RuntimeStatus } from '../api'
import { useStore } from '../store'

// Runtime work is keyed server-side by stream_id/run_id, not by which graph is
// open, so a process started in one tab keeps running after you switch away and
// its node is no longer on the canvas to stop it. This panel is the one place
// that shows what the server is actually running, whichever tab you are on.

const GROUPS: Array<{ key: keyof RuntimeStatus; label: string; idField: string }> = [
  { key: 'streams',           label: 'Image streams',    idField: 'stream_id' },
  { key: 'cv2_streams',       label: 'Camera streams',   idField: 'stream_id' },
  { key: 'reasoning_streams', label: 'Reasoning streams', idField: 'stream_id' },
  { key: 'managed_runs',      label: 'Managed processes', idField: 'run_id' },
]

const str = (v: unknown) => (typeof v === 'string' ? v : v == null ? '' : String(v))

export default function RuntimePanel() {
  const nodes = useStore(s => s.nodes)
  const stopRuntimeServices = useStore(s => s.stopRuntimeServices)
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [error, setError] = useState('')
  const [stopping, setStopping] = useState(false)

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const next = await api.runtimeStatus()
        if (alive) { setStatus(next); setError('') }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'runtime status unavailable')
      }
    }
    void poll()
    const id = setInterval(poll, 1500)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const rows = GROUPS.map(g => ({
    ...g,
    items: (status?.[g.key] as Array<Record<string, unknown>> | undefined) ?? [],
  }))
  const total = rows.reduce((n, r) => n + r.items.length, 0)
  const detached = status?.detached_count ?? 0

  const onCanvas = (id: string) => nodes.some(n =>
    str(n.data.params?.stream_id) === id || str(n.data.params?.run_id) === id)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '10px 12px', fontFamily: 'var(--font-ui)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: total ? 'var(--ok)' : 'var(--tx3)',
          boxShadow: total ? '0 0 8px var(--ok)' : 'none',
        }} />
        <span style={{ flex: 1, fontSize: 12, fontWeight: 700, color: 'var(--tx1)' }}>
          {total ? `${total} running` : 'Nothing running'}
        </span>
        <button
          disabled={!total || stopping}
          onClick={async () => { setStopping(true); try { await stopRuntimeServices() } finally { setStopping(false) } }}
          style={{
            padding: '3px 9px', borderRadius: 5,
            border: `1px solid ${total ? 'var(--err)' : 'var(--line2)'}`,
            background: 'transparent', color: total ? 'var(--err)' : 'var(--tx3)',
            cursor: total && !stopping ? 'pointer' : 'default',
            fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 700,
          }}
        >
          {stopping ? 'Stopping…' : 'Stop all'}
        </button>
      </div>

      {error && (
        <div style={{ color: 'var(--err)', fontSize: 11, marginBottom: 8 }}>{error}</div>
      )}

      {detached > 0 && (
        <div style={{
          marginBottom: 10, padding: '6px 8px', borderRadius: 6,
          border: '1px solid var(--warn)', color: 'var(--warn)', fontSize: 11,
        }}>
          {detached} detached process{detached === 1 ? '' : 'es'} — started by an earlier session and
          no longer owned by a node. Stop all clears them.
        </div>
      )}

      {rows.filter(r => r.items.length).map(row => (
        <section key={String(row.key)} style={{ marginBottom: 12 }}>
          <div style={{
            fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
            textTransform: 'uppercase', color: 'var(--tx3)', marginBottom: 5,
          }}>
            {row.label} · {row.items.length}
          </div>
          {row.items.map((item, i) => {
            const id = str(item[row.idField]) || `#${i + 1}`
            const here = onCanvas(id)
            const url = str(item.stream_url)
            return (
              <div
                key={`${id}-${i}`}
                title={url || undefined}
                style={{
                  display: 'flex', alignItems: 'center', gap: 7,
                  padding: '5px 7px', marginBottom: 3, borderRadius: 5,
                  background: 'var(--lift)', border: '1px solid var(--line)',
                }}
              >
                <span style={{
                  flex: 1, minWidth: 0, fontSize: 11, color: 'var(--tx1)',
                  fontFamily: 'var(--font-mono)', overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {id}
                </span>
                {str(item.runtime) && (
                  <span style={{ fontSize: 9, color: 'var(--tx3)' }}>{str(item.runtime)}</span>
                )}
                {/* The useful signal: work with no node in this tab is what you
                    cannot otherwise find or stop. */}
                <span
                  title={here ? 'A node in this tab owns it' : 'No node in this tab owns it'}
                  style={{
                    fontSize: 9, fontWeight: 700, flexShrink: 0,
                    color: here ? 'var(--ok)' : 'var(--warn)',
                  }}
                >
                  {here ? 'this tab' : 'other tab'}
                </span>
              </div>
            )
          })}
        </section>
      ))}

      {!total && !error && (
        <div style={{ color: 'var(--tx3)', fontSize: 11, lineHeight: 1.6 }}>
          Streams, camera captures and managed processes appear here while they run,
          including ones started from another tab.
        </div>
      )}
    </div>
  )
}
