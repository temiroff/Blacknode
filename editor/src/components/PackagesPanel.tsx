import { Fragment, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { BnPackage, BnPackageIndexPackage } from '../types'

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

const sectionStyle: React.CSSProperties = {
  padding: '8px 12px 5px',
  borderBottom: '1px solid var(--line)',
  color: 'var(--tx3)',
  fontFamily: 'var(--font-ui)',
  fontSize: 10,
  fontWeight: 700,
  textTransform: 'uppercase',
}

function gitSummary(pkg: BnPackage): string {
  const git = pkg.git_status
  if (!git?.is_git_repo) return ''
  const parts = [git.branch || 'detached']
  if (git.dirty) parts.push('dirty')
  if (git.ahead) parts.push(`ahead ${git.ahead}`)
  if (git.behind) parts.push(`behind ${git.behind}`)
  if (git.fetch_error) parts.push('fetch failed')
  return parts.join(' · ')
}

const LAYER_ORDER = [
  'skills',
  'agent',
  'robot',
  'perception',
  'controllers',
  'drivers',
  'integration',
  'learning',
  'compute',
  'simulation',
  'extensions',
]

function packageLayer(pkg: { layer?: string }): string {
  return pkg.layer?.trim().toLowerCase() || 'extensions'
}

function layerLabel(layer: string): string {
  return layer.split('-').map(part => part ? part[0].toUpperCase() + part.slice(1) : '').join(' ')
}

function comparePackages(a: { name: string; layer?: string }, b: { name: string; layer?: string }): number {
  const aLayer = packageLayer(a)
  const bLayer = packageLayer(b)
  const aRank = LAYER_ORDER.includes(aLayer) ? LAYER_ORDER.indexOf(aLayer) : LAYER_ORDER.length
  const bRank = LAYER_ORDER.includes(bLayer) ? LAYER_ORDER.indexOf(bLayer) : LAYER_ORDER.length
  return aRank - bRank || aLayer.localeCompare(bLayer) || a.name.localeCompare(b.name)
}

export default function PackagesPanel() {
  const [packages, setPackages] = useState<BnPackage[]>([])
  const [catalog, setCatalog] = useState<BnPackageIndexPackage[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [gitUrl, setGitUrl] = useState('')
  const [installingName, setInstallingName] = useState<string | null>(null)
  const [componentBusy, setComponentBusy] = useState<string | null>(null)
  const [installLog, setInstallLog] = useState<string | null>(null)
  const loadNodeTypes = useStore(s => s.loadNodeTypes)

  const installedNames = useMemo(() => new Set(packages.map(pkg => pkg.name)), [packages])
  const availablePackages = useMemo(
    () => catalog.filter(pkg => !installedNames.has(pkg.name)).sort(comparePackages),
    [catalog, installedNames],
  )
  const installedPackages = useMemo(() => [...packages].sort(comparePackages), [packages])

  const refresh = async () => {
    try {
      const [installed, index] = await Promise.all([api.packages(), api.packageIndex()])
      setPackages(installed.packages)
      setCatalog(Object.values(index.packages))
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

  const installUrl = async (url: string, name: string, clearManualUrl = false) => {
    const cleanUrl = url.trim()
    if (!cleanUrl || installingName) return
    setInstallingName(name)
    setInstallLog(null)
    setError(null)
    try {
      const result = await api.installPackage(cleanUrl)
      setInstallLog(result.log?.length ? result.log.join('\n') : null)
      if (result.ok) {
        if (clearManualUrl) setGitUrl('')
        await refresh()
        await loadNodeTypes()
      } else {
        setError(result.error || 'Install failed')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setInstallingName(null)
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

  const setComponent = async (packageName: string, componentName: string, enabled: boolean) => {
    const key = `${packageName}/${componentName}`
    setComponentBusy(key)
    setError(null)
    try {
      await api.setPackageComponent(packageName, componentName, enabled)
      await refresh()
      await loadNodeTypes()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setComponentBusy(null)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--line)', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={gitUrl}
            onChange={e => setGitUrl(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') installUrl(gitUrl, 'custom', true) }}
            placeholder="git URL, e.g. git@github.com:user/blacknode-pkg.git"
            disabled={Boolean(installingName)}
            style={inputStyle}
          />
          <button onClick={() => installUrl(gitUrl, 'custom', true)} disabled={Boolean(installingName) || !gitUrl.trim()} style={buttonStyle(Boolean(installingName))}>
            {installingName === 'custom' ? 'Installing...' : 'Install'}
          </button>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ flex: 1, fontSize: 11, color: 'var(--tx3)', fontFamily: 'var(--font-ui)' }}>
            {packages.length} installed · {availablePackages.length} available
          </span>
          <button onClick={reload} disabled={busy} style={buttonStyle(busy)}>
            {busy ? 'Working...' : 'Reload'}
          </button>
        </div>
      </div>

      {installingName && (
        <div style={{ padding: '8px 12px', color: 'var(--tx3)', fontSize: 11, fontFamily: 'var(--font-ui)' }}>
          Cloning and installing prerequisites...
        </div>
      )}

      {installLog && !installingName && (
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

      {availablePackages.map((pkg, index) => {
        const installing = installingName === pkg.name
        const layer = packageLayer(pkg)
        const startsLayer = index === 0 || packageLayer(availablePackages[index - 1]) !== layer
        const componentCount = Object.keys(pkg.components ?? {}).length
        return (
          <Fragment key={pkg.name}>
          {startsLayer && <div style={sectionStyle}>Available · {layerLabel(layer)}</div>}
          <div style={{ borderBottom: '1px solid var(--line)', padding: '9px 12px', display: 'flex', gap: 10, alignItems: 'center' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--tx3)', flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <span style={{ color: 'var(--tx1)', fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {pkg.name}
                </span>
                <span style={{ color: 'var(--tx3)', fontSize: 10, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                  {pkg.node_types.length} nodes{componentCount ? ` · ${componentCount} components` : ''}
                </span>
              </div>
              {pkg.description && (
                <div style={{ color: 'var(--tx3)', fontSize: 11, lineHeight: 1.35, marginTop: 2 }}>
                  {pkg.description}
                </div>
              )}
            </div>
            <button
              onClick={() => installUrl(pkg.git_url, pkg.name)}
              disabled={Boolean(installingName) || !pkg.git_url}
              style={{ ...buttonStyle(Boolean(installingName)), color: 'var(--ok)', borderColor: 'var(--ok)' }}
            >
              {installing ? 'Installing...' : 'Install'}
            </button>
          </div>
          </Fragment>
        )
      })}

      {!error && packages.length === 0 && availablePackages.length === 0 && (
        <div style={{ padding: '14px 12px', color: 'var(--tx3)', fontSize: 12, fontFamily: 'var(--font-ui)', lineHeight: 1.5 }}>
          No extension packages installed.
        </div>
      )}

      {installedPackages.map((pkg, index) => {
        const open = expanded === pkg.name
        const layer = packageLayer(pkg)
        const startsLayer = index === 0 || packageLayer(installedPackages[index - 1]) !== layer
        const componentEntries = Object.values(pkg.components ?? {})
        const hasWarnings = (pkg.warnings?.length ?? 0) > 0
        const hasMissingNodes = (pkg.missing_node_types?.length ?? 0) > 0
        const prereqsMet = pkg.ok && !hasWarnings && !hasMissingNodes
        const dotTitle = !pkg.ok
          ? 'Package failed to load - see the error below'
          : hasMissingNodes
            ? 'Installed package is missing official nodes'
            : hasWarnings
              ? 'Package warnings - expand for details'
              : 'Loaded'
        const setupTitle = hasWarnings
          ? pkg.warnings.join('\n')
          : pkg.import_dependencies.length
            ? `Python prerequisites installed (${pkg.import_dependencies.join(', ')}).`
              + (pkg.docker_images.length ? ` Docker image ${pkg.docker_images.join(', ')} pulls on first use.` : '')
              + ' Click to re-run setup.'
            : 'No prerequisites declared. Click to re-run setup.'
        const git = gitSummary(pkg)
        return (
          <Fragment key={pkg.name}>
          {startsLayer && <div style={sectionStyle}>Installed · {layerLabel(layer)}</div>}
          <div style={{ borderBottom: '1px solid var(--line)' }}>
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
                background: !pkg.ok ? 'var(--err)' : (hasWarnings || hasMissingNodes ? '#e0a000' : 'var(--ok)'),
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
                {componentEntries.length > 0 && (
                  <div style={{ marginTop: 7, display: 'flex', flexDirection: 'column', gap: 5 }}>
                    {componentEntries.map(component => {
                      const key = `${pkg.name}/${component.name}`
                      const changing = componentBusy === key
                      const enabled = component.enabled !== false
                      return (
                        <div key={component.name} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '5px 7px', border: '1px solid var(--line)', borderRadius: 5 }}>
                          <span style={{ width: 6, height: 6, borderRadius: '50%', background: enabled ? 'var(--ok)' : 'var(--tx3)', flexShrink: 0 }} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--tx2)' }}>
                              {component.name}{component.default ? ' · default' : ''}
                            </div>
                            {component.description && (
                              <div style={{ color: 'var(--tx3)', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {component.description}
                              </div>
                            )}
                            {(component.requirements?.length ?? 0) > 0 && (
                              <div style={{ color: 'var(--tx3)', fontSize: 9, fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                requires: {component.requirements!.map(requirement => {
                                  const owner = requirement.package || pkg.name
                                  return `${owner}${requirement.component ? `/${requirement.component}` : ''}${requirement.version ? ` ${requirement.version}` : ''}`
                                }).join(', ')}
                              </div>
                            )}
                          </div>
                          {pkg.component_mode ? (
                            <button
                              onClick={() => setComponent(pkg.name, component.name, !enabled)}
                              disabled={busy || componentBusy !== null}
                              style={{
                                ...buttonStyle(busy || componentBusy !== null),
                                color: enabled ? 'var(--tx3)' : 'var(--ok)',
                                borderColor: enabled ? 'var(--line2)' : 'var(--ok)',
                              }}
                            >
                              {changing ? 'Working...' : enabled ? 'Disable' : 'Enable'}
                            </button>
                          ) : (
                            <span style={{ color: 'var(--tx3)', fontSize: 9, fontFamily: 'var(--font-mono)' }}>included</span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
                {git && (
                  <div style={{ marginTop: 2, color: 'var(--tx3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>
                    git: {git}
                  </div>
                )}
                {pkg.docker_images?.length > 0 && (
                  <div style={{ marginTop: 2, color: 'var(--tx3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>
                    docker: {pkg.docker_images.join(', ')}
                  </div>
                )}
                {hasMissingNodes && (
                  <div style={{ marginTop: 4, color: '#e0a000', fontSize: 10, fontFamily: 'var(--font-mono)', wordBreak: 'break-word' }}>
                    missing: {pkg.missing_node_types.join(', ')}
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
                        ? 'Working...'
                        : hasWarnings
                          ? 'Install prerequisites'
                          : 'Prerequisites ok'}
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
          </Fragment>
        )
      })}
    </div>
  )
}
