import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  api,
  type CloudArtifact,
  type CloudCreditEntry,
  type CloudJob,
  type CloudJobEvent,
  type CloudStatus,
} from '../api'

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELED', 'TIMED_OUT'])

interface Props {
  open: boolean
  pending: boolean
  initialJob: CloudJob | null
  error: string
  accountStatus: CloudStatus | null
  onAccountStatus: (status: CloudStatus) => void
  onRun: () => void
  onClose: () => void
}

function elapsed(job: CloudJob): string {
  const start = job.started_at || job.created_at
  const end = job.finished_at || new Date().toISOString()
  const seconds = Math.max(0, Math.floor((Date.parse(end) - Date.parse(start)) / 1000))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  return [hours, minutes, rest].map(value => String(value).padStart(2, '0')).join(':')
}

function bytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MiB`
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GiB`
}

function creditReason(entry: CloudCreditEntry): string {
  if (entry.reason === 'signup-credit') return 'Signup credits'
  if (entry.reason === 'gpu-job') return 'NVIDIA GPU job'
  return entry.reason.split('-').join(' ')
}

export default function CloudRunPanel({
  open,
  pending,
  initialJob,
  error,
  accountStatus,
  onAccountStatus,
  onRun,
  onClose,
}: Props) {
  const [job, setJob] = useState<CloudJob | null>(initialJob)
  const [events, setEvents] = useState<CloudJobEvent[]>([])
  const [artifacts, setArtifacts] = useState<CloudArtifact[]>([])
  const [history, setHistory] = useState<CloudCreditEntry[]>([])
  const [pollError, setPollError] = useState('')
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [authPending, setAuthPending] = useState(false)
  const [authError, setAuthError] = useState('')
  const nextSeq = useRef(0)

  const refreshAccount = useCallback(async () => {
    const nextStatus = await api.cloudStatus()
    onAccountStatus(nextStatus)
    if (nextStatus.authenticated) {
      const page = await api.getCloudCreditHistory()
      setHistory(page.entries)
    } else {
      setHistory([])
    }
  }, [onAccountStatus])

  useEffect(() => {
    setJob(initialJob)
    setEvents([])
    setArtifacts([])
    setPollError('')
    nextSeq.current = 0
  }, [initialJob?.id])

  useEffect(() => {
    if (!open || !accountStatus?.authenticated) return
    void api.getCloudCreditHistory()
      .then(page => setHistory(page.entries))
      .catch(cause => setAuthError(cause instanceof Error ? cause.message : String(cause)))
  }, [accountStatus?.authenticated, accountStatus?.account?.id, open])

  useEffect(() => {
    if (job && TERMINAL.has(job.status)) void refreshAccount()
  }, [job?.status, refreshAccount])

  useEffect(() => {
    if (!open || !initialJob) return undefined
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async () => {
      try {
        const [nextJob, logPage, artifactPage] = await Promise.all([
          api.getCloudJob(initialJob.id),
          api.getCloudJobLogs(initialJob.id, nextSeq.current),
          api.getCloudJobArtifacts(initialJob.id),
        ])
        if (stopped) return
        setJob(nextJob)
        if (logPage.events.length) {
          setEvents(current => [...current, ...logPage.events].slice(-1000))
          nextSeq.current = logPage.next_seq
        }
        setArtifacts(artifactPage.artifacts)
        setPollError('')
        if (!TERMINAL.has(nextJob.status)) timer = setTimeout(poll, 1000)
      } catch (cause) {
        if (stopped) return
        setPollError(cause instanceof Error ? cause.message : String(cause))
        timer = setTimeout(poll, 2000)
      }
    }

    void poll()
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }
  }, [initialJob, open])

  const metrics = useMemo(() => events
    .filter(event => event.type === 'metric')
    .map(event => ({
      name: String(event.payload.name ?? 'metric'),
      value: Number(event.payload.value ?? 0),
      step: Number(event.payload.step ?? 0),
    }))
    .filter(metric => Number.isFinite(metric.value)), [events])
  const reward = metrics.filter(metric => metric.name.toLowerCase().includes('reward')).slice(-60)
  const rewardPoints = useMemo(() => {
    if (reward.length < 2) return ''
    const values = reward.map(item => item.value)
    const low = Math.min(...values)
    const high = Math.max(...values)
    const span = Math.max(0.0001, high - low)
    return values.map((value, index) => {
      const x = (index / (values.length - 1)) * 300
      const y = 76 - ((value - low) / span) * 68
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
  }, [reward])
  const logs = events.filter(event => event.type === 'log').slice(-300)

  const submitAuth = async (event: FormEvent) => {
    event.preventDefault()
    if (authMode === 'register' && password !== confirmPassword) {
      setAuthError('Passwords do not match.')
      return
    }
    setAuthPending(true)
    setAuthError('')
    try {
      const nextStatus = authMode === 'register'
        ? await api.registerCloudAccount(email, password, displayName)
        : await api.loginCloudAccount(email, password)
      onAccountStatus(nextStatus)
      setPassword('')
      setConfirmPassword('')
      const page = await api.getCloudCreditHistory()
      setHistory(page.entries)
    } catch (cause) {
      setAuthError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setAuthPending(false)
    }
  }

  const logout = async () => {
    setAuthPending(true)
    setAuthError('')
    try {
      await api.logoutCloudAccount()
      await refreshAccount()
    } catch (cause) {
      setAuthError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setAuthPending(false)
    }
  }

  if (!open) return null
  const credits = accountStatus?.credits
  const account = accountStatus?.account
  const activeJob = job && !TERMINAL.has(job.status)

  return (
    <div className="bn-cloud-run-backdrop" role="presentation">
      <section className="bn-cloud-run-panel" role="dialog" aria-modal="true" aria-label="Blacknode Cloud">
        <header>
          <div>
            <span>BLACKNODE CLOUD</span>
            <strong>{job ? job.workflow_name : account?.display_name || 'Cloud account'}</strong>
          </div>
          <button type="button" onClick={onClose} aria-label="Close Blacknode Cloud">×</button>
        </header>

        {(pending || (!accountStatus && !error)) && <div className="bn-cloud-run-message">Connecting to Blacknode Cloud…</div>}
        {(error || pollError || authError) && <div className="bn-cloud-run-error">{error || pollError || authError}</div>}

        {!pending && accountStatus?.configured && !accountStatus.authenticated && !job && (
          <div className="bn-cloud-auth">
            <div className="bn-cloud-auth-tabs">
              <button type="button" className={authMode === 'login' ? 'is-active' : ''} onClick={() => setAuthMode('login')}>
                Log in
              </button>
              <button type="button" className={authMode === 'register' ? 'is-active' : ''} onClick={() => setAuthMode('register')}>
                Sign up
              </button>
            </div>
            <form onSubmit={event => void submitAuth(event)}>
              {authMode === 'register' && (
                <label>
                  <span>Display name</span>
                  <input value={displayName} onChange={event => setDisplayName(event.target.value)} autoComplete="name" maxLength={100} />
                </label>
              )}
              <label>
                <span>Email</span>
                <input type="email" required value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" maxLength={254} />
              </label>
              <label>
                <span>Password</span>
                <input
                  type="password"
                  required
                  minLength={authMode === 'register' ? 10 : 1}
                  value={password}
                  onChange={event => setPassword(event.target.value)}
                  autoComplete={authMode === 'register' ? 'new-password' : 'current-password'}
                />
              </label>
              {authMode === 'register' && (
                <label>
                  <span>Confirm password</span>
                  <input type="password" required minLength={10} value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} autoComplete="new-password" />
                </label>
              )}
              <button type="submit" className="is-primary" disabled={authPending}>
                {authPending ? 'Connecting…' : authMode === 'register' ? 'Create account' : 'Log in'}
              </button>
            </form>
            <p>Your Cloud session stays on this editor server and is not placed in browser storage or workflow payloads.</p>
          </div>
        )}

        {!job && accountStatus?.authenticated && account && credits && (
          <>
            <div className="bn-cloud-account">
              <header>
                <div><strong>{account.display_name}</strong><span>{account.email}</span></div>
                <button type="button" onClick={() => void logout()} disabled={authPending}>Log out</button>
              </header>
              <div className="bn-cloud-credit-grid">
                <div><span>Available</span><strong>{credits.available.toLocaleString()}</strong></div>
                <div><span>Reserved</span><strong>{credits.reserved.toLocaleString()}</strong></div>
                <div><span>Balance</span><strong>{credits.balance.toLocaleString()}</strong></div>
              </div>
              <small>Credits are GPU-seconds. This job reserves its runtime limit and charges measured GPU time.</small>
              <button type="button" className="is-primary bn-cloud-submit" onClick={onRun} disabled={pending}>
                Run workflow on NVIDIA L40S
              </button>
            </div>

            <div className="bn-cloud-run-section">
              <header><strong>Credit history</strong><span>{history.length}</span></header>
              <div className="bn-cloud-credit-history">
                {history.map(entry => (
                  <div key={entry.id}>
                    <span>{creditReason(entry)}<small>{new Date(entry.created_at).toLocaleString()}</small></span>
                    <strong className={entry.delta_seconds >= 0 ? 'is-credit' : 'is-charge'}>
                      {entry.delta_seconds >= 0 ? '+' : ''}{entry.delta_seconds.toLocaleString()}
                    </strong>
                  </div>
                ))}
                {history.length === 0 && <p>No credit activity yet.</p>}
              </div>
            </div>
          </>
        )}

        {job && credits && (
          <div className="bn-cloud-job-credits">
            <span>{credits.available.toLocaleString()} available</span>
            <span>{credits.reserved.toLocaleString()} reserved</span>
          </div>
        )}

        {job && (
          <>
            <div className="bn-cloud-run-facts">
              <div><span>Job</span><strong>{job.id}</strong></div>
              <div><span>GPU</span><strong>NVIDIA L40S</strong></div>
              <div><span>Status</span><strong className={`is-${job.status.toLowerCase()}`}>● {job.status}</strong></div>
              <div><span>Runtime</span><strong>{elapsed(job)}</strong></div>
            </div>
            <div className="bn-cloud-progress" aria-label={`${job.progress}% complete`}>
              <i style={{ width: `${job.progress}%` }} />
            </div>
            <div className="bn-cloud-progress-label"><span>Progress</span><strong>{job.progress}%</strong></div>

            {rewardPoints && (
              <div className="bn-cloud-metric-chart">
                <header><span>Reward</span><strong>{reward[reward.length - 1]?.value.toFixed(3)}</strong></header>
                <svg viewBox="0 0 300 84" preserveAspectRatio="none" aria-label="Reward metric">
                  <polyline points={rewardPoints} fill="none" stroke="currentColor" strokeWidth="2" />
                </svg>
              </div>
            )}

            <div className="bn-cloud-run-section">
              <header><strong>Logs</strong><span>{logs.length} events</span></header>
              <pre>{logs.length
                ? logs.map(event => `[${String(event.payload.stream ?? 'stdout')}] ${String(event.payload.text ?? '')}`).join('\n')
                : 'Waiting for executor output…'}</pre>
            </div>

            <div className="bn-cloud-run-section">
              <header><strong>Artifacts</strong><span>{artifacts.length}</span></header>
              <div className="bn-cloud-artifact-list">
                {artifacts.map(artifact => (
                  <a key={artifact.id} href={api.cloudArtifactDownloadUrl(job.id, artifact.id)} download={artifact.name}>
                    <span>{artifact.name}</span><small>{bytes(artifact.size_bytes)} · download</small>
                  </a>
                ))}
                {artifacts.length === 0 && <p>Artifacts appear here as the job completes.</p>}
              </div>
            </div>

            {job.result !== null && job.result !== undefined && (
              <div className="bn-cloud-run-section">
                <header><strong>Result</strong></header>
                <pre>{JSON.stringify(job.result, null, 2)}</pre>
              </div>
            )}
            {job.error_message && <div className="bn-cloud-run-error">{job.error_message}</div>}
            {activeJob && (
              <footer>
                <button type="button" onClick={() => void api.cancelCloudJob(job.id).then(setJob)}>
                  Cancel job
                </button>
              </footer>
            )}
          </>
        )}
      </section>
    </div>
  )
}
