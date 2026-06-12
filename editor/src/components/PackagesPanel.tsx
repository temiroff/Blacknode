import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { BnPackage } from '../types'

export default function PackagesPanel() {
  const [packages, setPackages] = useState<BnPackage[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const loadNodeTypes = useStore(s => s.loadNodeTypes)

  const refresh = async () => {
    try {
      setPackages((await api.packages()).packages)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => { refresh() }, [])

  const reload = async () => {
    setBusy(true)
    try {
      await api.reloadPackages()
      await refresh()
      await loadNodeTypes()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--line)', display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ flex: 1, fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-ui)' }}>
          {packages.length} installed
        </span>
        <button
          onClick={reload}
          disabled={busy}
          style={{
            background: 'transparent',
            border: '1px solid var(--line2)',
            borderRadius: 5,
            color: 'var(--tx2)',
            cursor: busy ? 'wait' : 'pointer',
            fontSize: 11,
            fontFamily: 'var(--font-ui)',
            padding: '3px 10px',
          }}
        >
          {busy ? 'Reloading…' : 'Reload'}
        </button>
      </div>

      {error && (
        <div style={{ padding: '8px 12px', color: 'var(--err)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
          {error}
        </div>
      )}

      {!error && packages.length === 0 && (
        <div style={{ padding: '14px 12px', color: 'var(--tx3)', fontSize: 12, fontFamily: 'var(--font-ui)', lineHeight: 1.5 }}>
          No extension packages installed. Clone one into the <code>packages/</code> folder
          (or run <code>blacknode packages install &lt;git-url&gt;</code>) and restart.
        </div>
      )}

      {packages.map(pkg => {
        const open = expanded === pkg.name
        return (
          <div key={pkg.name} style={{ borderBottom: '1px solid var(--line)' }}>
            <button
              onClick={() => setExpanded(open ? null : pkg.name)}
              style={{
                width: '100%',
                background: open ? 'var(--menu-active)' : 'transparent',
                border: 'none',
                color: 'var(--tx1)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                padding: '9px 12px',
                textAlign: 'left',
                fontFamily: 'var(--font-ui)',
              }}
            >
              <span style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: pkg.ok ? 'var(--ok)' : 'var(--err)',
                flexShrink: 0,
              }} />
              <span style={{ flex: 1, fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {pkg.name}
              </span>
              <span style={{ color: 'var(--tx3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>
                {pkg.version || '?'}
              </span>
            </button>
            {open && (
              <div style={{ padding: '0 12px 10px 26px', fontSize: 11, fontFamily: 'var(--font-ui)', color: 'var(--tx2)', lineHeight: 1.5 }}>
                {pkg.description && <div style={{ marginBottom: 6 }}>{pkg.description}</div>}
                <div style={{ color: 'var(--tx3)' }}>
                  {pkg.node_types.length} nodes · {pkg.source}
                  {pkg.templates_dir ? ' · templates' : ''}
                </div>
                {pkg.docker_images?.length > 0 && (
                  <div style={{ marginTop: 2, color: 'var(--tx3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>
                    docker: {pkg.docker_images.join(', ')}
                  </div>
                )}
                {pkg.node_types.length > 0 && (
                  <div style={{ marginTop: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--tx3)', wordBreak: 'break-word' }}>
                    {pkg.node_types.join(', ')}
                  </div>
                )}
                {!pkg.ok && (
                  <pre style={{
                    marginTop: 6,
                    padding: 8,
                    background: 'var(--hover)',
                    borderRadius: 5,
                    color: 'var(--err)',
                    fontSize: 10,
                    fontFamily: 'var(--font-mono)',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    maxHeight: 180,
                    overflowY: 'auto',
                  }}>
                    {pkg.error.trim().split('\n').slice(-12).join('\n')}
                  </pre>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
