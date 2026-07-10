import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { BnPackage } from '../types'

const inputStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  background: 'var(--bg)',
  border: '1px solid var(--line2)',
  borderRadius: 5,
  color: 'var(--tx1)',
  fontSize: 11,
  fontFamily: 'var(--font-mono)',
  padding: '4px 8px',
}

const buttonStyle = (busy: boolean): React.CSSProperties => ({
  background: 'transparent',
  border: '1px solid var(--line2)',
  borderRadius: 5,
  color: 'var(--tx2)',
  cursor: busy ? 'wait' : 'pointer',
  fontSize: 11,
  fontFamily: 'var(--font-ui)',
  padding: '3px 10px',
  whiteSpace: 'nowrap',
})

export default function PackagesPanel() {
  const [packages, setPackages] = useState<BnPackage[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [gitUrl, setGitUrl] = useState('')
  const [installing, setInstalling] = useState(false)
  const [installLog, setInstallLog] = useState<string | null>(null)
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

  const install = async () => {
    const url = gitUrl.trim()
    if (!url || installing) return
    setInstalling(true)
    setInstallLog(null)
    setError(null)
    try {
      const result = await api.installPackage(url)
      setInstallLog(result.log?.length ? result.log.join('\n') : null)
      if (result.ok) {
        setGitUrl('')
        await refresh()
        await loadNodeTypes()
      } else {
        setError(result.error || 'Install failed')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setInstalling(false)
    }
  }

  const setup = async (name: string) => {
    setBusy(true)
    setError(null)
    setInstallLog(null)
    try {
      const result = await api.setupPackage(name)
      setInstallLog(result.log?.length ? result.log.join('\n') : 'Prerequisites installed.')
      await refresh()
      await loadNodeTypes()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (name: string) => {
    if (!window.confirm(`Delete package '${name}'?\n\nThis removes its folder (and any local changes in it) from packages/.`)) return
    setBusy(true)
    setError(null)
    try {
      await api.deletePackage(name)
      setExpanded(null)
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
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--line)', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={gitUrl}
            onChange={e => setGitUrl(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') install() }}
            placeholder="git URL, e.g. git@github.com:user/blacknode-pkg.git"
            disabled={installing}
            style={inputStyle}
          />
          <button onClick={install} disabled={installing || !gitUrl.trim()} style={buttonStyle(installing)}>
            {installing ? 'Installing…' : 'Install'}
          </button>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ flex: 1, fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-ui)' }}>
            {packages.length} installed
          </span>
          <button onClick={reload} disabled={busy} style={buttonStyle(busy)}>
            {busy ? 'Working…' : 'Reload'}
          </button>
        </div>
      </div>

      {installing && (
        <div style={{ padding: '8px 12px', color: 'var(--tx3)', fontSize: 11, fontFamily: 'var(--font-ui)' }}>
          Cloning and installing prerequisites — large Docker images can take a few minutes…
        </div>
      )}

      {installLog && !installing && (
        <pre style={{
          margin: 0,
          padding: '8px 12px',
          borderBottom: '1px solid var(--line)',
          color: 'var(--tx3)',
          fontSize: 10,
          fontFamily: 'var(--font-mono)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          maxHeight: 120,
          overflowY: 'auto',
        }}>
          {installLog}
        </pre>
      )}

      {error && (
        <div style={{ padding: '8px 12px', color: 'var(--err)', fontSize: 11, fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {error}
        </div>
      )}

      {!error && packages.length === 0 && (
        <div style={{ padding: '14px 12px', color: 'var(--tx3)', fontSize: 12, fontFamily: 'var(--font-ui)', lineHeight: 1.5 }}>
          No extension packages installed. Paste a git URL above, or clone one
          into the <code>packages/</code> folder and press Reload.
        </div>
      )}

      {packages.map(pkg => {
        const open = expanded === pkg.name
        const hasWarnings = (pkg.warnings?.length ?? 0) > 0
        const prereqsMet = pkg.ok && !hasWarnings
        const dotTitle = !pkg.ok
          ? 'Package failed to load — see the error below'
          : hasWarnings
            ? 'Prerequisites missing — press "Install prerequisites"'
            : 'Loaded; declared prerequisites satisfied'
        const setupTitle = hasWarnings
          ? pkg.warnings.join('\n')
          : pkg.import_dependencies.length
            ? `Python prerequisites installed (${pkg.import_dependencies.join(', ')}).`
              + (pkg.docker_images.length ? ` Docker image ${pkg.docker_images.join(', ')} pulls on first use.` : '')
              + ' Click to re-run setup (e.g. to pre-pull Docker images).'
            : 'No prerequisites declared. Click to re-run setup.'
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
              <span title={dotTitle} style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: !pkg.ok ? 'var(--err)' : (hasWarnings ? '#e0a000' : 'var(--ok)'),
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
                {pkg.ok && pkg.warnings?.length > 0 && (
                  <pre style={{
                    marginTop: 6,
                    padding: 8,
                    background: 'var(--hover)',
                    borderRadius: 5,
                    color: '#e0a000',
                    fontSize: 10,
                    fontFamily: 'var(--font-mono)',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    maxHeight: 200,
                    overflowY: 'auto',
                  }}>
                    {pkg.warnings.join('\n')}
                  </pre>
                )}
                {pkg.source === 'folder' && (
                  <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => setup(pkg.name)}
                      disabled={busy}
                      title={setupTitle}
                      style={hasWarnings
                        ? { ...buttonStyle(busy), color: '#e0a000', borderColor: '#e0a000' }
                        : prereqsMet
                          ? { ...buttonStyle(busy), color: 'var(--ok)', borderColor: 'var(--ok)' }
                          : buttonStyle(busy)}
                    >
                      {busy
                        ? 'Working…'
                        : hasWarnings
                          ? 'Install prerequisites'
                          : 'Prerequisites ✓'}
                    </button>
                    <button
                      onClick={() => remove(pkg.name)}
                      disabled={busy}
                      style={{ ...buttonStyle(busy), color: 'var(--err)', borderColor: 'var(--err)' }}
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
