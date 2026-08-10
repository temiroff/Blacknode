import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  api,
  type CloudArtifact,
  type CloudCreditEntry,
  type CloudDataset,
  type CloudJob,
  type CloudJobEvent,
  type CloudProviderPreference,
  type CloudStatus,
} from '../api'

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELED', 'TIMED_OUT'])

interface Props {
  open: boolean
  view: 'account' | 'job'
  pending: boolean
  initialJob: CloudJob | null
  error: string
  accountStatus: CloudStatus | null
  onAccountStatus: (status: CloudStatus) => void
  onRun: () => void
  onRunVla: (request: {
    dataset_uri: string
    dataset_revision: string
    steps: number
    batch_size: number
    action_horizon: number
    max_runtime_seconds: number
  }) => Promise<void>
  onJobCompleted: (job: CloudJob) => void
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
  if (entry.reason === 'gpu-job') return 'Cloud GPU job'
  return entry.reason.split('-').join(' ')
}

export default function CloudRunPanel({
  open,
  view,
  pending,
  initialJob,
  error,
  accountStatus,
  onAccountStatus,
  onRun,
  onRunVla,
  onJobCompleted,
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
  const [providerPending, setProviderPending] = useState(false)
  const [providerError, setProviderError] = useState('')
  const [providerPreference, setProviderPreference] = useState<CloudProviderPreference>('auto')
  const [datasets, setDatasets] = useState<CloudDataset[]>([])
  const [vlaSource, setVlaSource] = useState<'huggingface' | 'cloud'>('huggingface')
  const [vlaDatasetUri, setVlaDatasetUri] = useState('hf://lerobot/aloha_sim_insertion_human')
  const [vlaDatasetRevision, setVlaDatasetRevision] = useState('')
  const [vlaDatasetId, setVlaDatasetId] = useState('')
  const [vlaSteps, setVlaSteps] = useState(5000)
  const [vlaBatchSize, setVlaBatchSize] = useState(8)
  const [vlaActionHorizon, setVlaActionHorizon] = useState(10)
  const [vlaRuntime, setVlaRuntime] = useState(14400)
  const [vlaPending, setVlaPending] = useState(false)
  const [vlaError, setVlaError] = useState('')
  const nextSeq = useRef(0)
  const completedJobId = useRef('')

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
    if (!open || !accountStatus?.authenticated) return
    void api.listCloudDatasets()
      .then(items => {
        setDatasets(items)
        setVlaDatasetId(current => current || items[0]?.id || '')
      })
      .catch(cause => setVlaError(cause instanceof Error ? cause.message : String(cause)))
  }, [accountStatus?.authenticated, open])

  useEffect(() => {
    setProviderPreference(
      accountStatus?.account?.compute_provider_preference
        ?? accountStatus?.compute_providers?.preference
        ?? 'auto',
    )
  }, [accountStatus?.account?.compute_provider_preference, accountStatus?.compute_providers?.preference])

  useEffect(() => {
    if (job && TERMINAL.has(job.status)) void refreshAccount()
    if (job?.status === 'COMPLETED' && completedJobId.current !== job.id) {
      completedJobId.current = job.id
      onJobCompleted(job)
    }
  }, [job, onJobCompleted, refreshAccount])

  useEffect(() => {
    if (!open || view !== 'job' || !initialJob) return undefined
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
  }, [initialJob, open, view])

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
  const loss = metrics.filter(metric => metric.name.toLowerCase() === 'loss').slice(-60)
  const lossPoints = useMemo(() => {
    if (loss.length < 2) return ''
    const values = loss.map(item => item.value)
    const low = Math.min(...values)
    const high = Math.max(...values)
    const span = Math.max(0.0001, high - low)
    return values.map((value, index) => {
      const x = (index / (values.length - 1)) * 300
      const y = 76 - ((value - low) / span) * 68
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
  }, [loss])
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

  const refreshVerification = async () => {
    setAuthPending(true)
    setAuthError('')
    try {
      await refreshAccount()
    } catch (cause) {
      setAuthError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setAuthPending(false)
    }
  }

  const updateProviderPreference = async (preference: CloudProviderPreference) => {
    const previous = providerPreference
    setProviderPreference(preference)
    setProviderPending(true)
    setProviderError('')
    try {
      onAccountStatus(await api.updateCloudAccount({ compute_provider_preference: preference }))
    } catch (cause) {
      setProviderPreference(previous)
      setProviderError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setProviderPending(false)
    }
  }

  const uploadDataset = async (file: File | undefined) => {
    if (!file) return
    setVlaPending(true)
    setVlaError('')
    try {
      const uploaded = await api.uploadCloudDataset(file)
      setDatasets(current => [uploaded, ...current.filter(item => item.id !== uploaded.id)])
      setVlaDatasetId(uploaded.id)
      setVlaSource('cloud')
    } catch (cause) {
      setVlaError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setVlaPending(false)
    }
  }

  const runVla = async () => {
    const datasetUri = vlaSource === 'cloud'
      ? (vlaDatasetId ? `blacknode-cloud://datasets/${vlaDatasetId}` : '')
      : vlaDatasetUri.trim()
    if (!datasetUri) {
      setVlaError('Choose a dataset.')
      return
    }
    setVlaPending(true)
    setVlaError('')
    try {
      await onRunVla({
        dataset_uri: datasetUri,
        dataset_revision: vlaSource === 'huggingface' ? vlaDatasetRevision.trim() : '',
        steps: vlaSteps,
        batch_size: vlaBatchSize,
        action_horizon: vlaActionHorizon,
        max_runtime_seconds: vlaRuntime,
      })
    } catch (cause) {
      setVlaError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setVlaPending(false)
    }
  }

  if (!open) return null
  const credits = accountStatus?.credits
  const account = accountStatus?.account
  const emailVerified = Boolean(account?.email_verified_at)
  const availableCredits = emailVerified ? credits?.available ?? 0 : 0
  const lockedCredits = emailVerified
    ? credits?.locked ?? 0
    : Math.max(credits?.locked ?? 0, credits?.available ?? 0)
  const activeJob = job && !TERMINAL.has(job.status)
  const visibleJob = view === 'job' ? job : null
  const vlaModel = visibleJob?.result && typeof visibleJob.result === 'object'
    ? visibleJob.result as Record<string, unknown>
    : null
  const providerOptions = accountStatus?.compute_providers?.options ?? []
  const selectedProvider = providerOptions.find(option => option.id === providerPreference)
  const providerLabel = selectedProvider?.label ?? 'Auto'

  return (
    <div className="bn-cloud-run-backdrop" role="presentation">
      <section className="bn-cloud-run-panel" role="dialog" aria-modal="true" aria-label="Blacknode Cloud">
        <header>
          <div>
            <span>BLACKNODE CLOUD</span>
            <strong>{visibleJob ? visibleJob.workflow_name : account?.display_name || 'Cloud account'}</strong>
          </div>
          <button type="button" onClick={onClose} aria-label="Close Blacknode Cloud">×</button>
        </header>

        {(pending || (!accountStatus && !error)) && <div className="bn-cloud-run-message">Connecting to Blacknode Cloud…</div>}
        {(error || pollError || authError || providerError || vlaError) && <div className="bn-cloud-run-error">{error || pollError || authError || providerError || vlaError}</div>}
        {!pending && accountStatus && !accountStatus.configured && !error && (
          <div className="bn-cloud-run-error">Blacknode Cloud is not configured on this editor server.</div>
        )}

        {!pending && accountStatus?.configured && !accountStatus.authenticated && !visibleJob && (
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
            <p>
              Your Cloud session stays on this editor server and is not placed in browser storage or workflow payloads.
              {authMode === 'register' && ' An unverified account can sign up again with the same password to receive a fresh verification email.'}
            </p>
          </div>
        )}

        {!visibleJob && accountStatus?.authenticated && account && credits && (
          <>
            <div className="bn-cloud-account">
              <header>
                <div>
                  <strong>{account.display_name}</strong>
                  <span>{account.email}</span>
                  <small className={account.email_verified_at ? 'is-verified' : 'is-unverified'}>
                    {account.email_verified_at ? 'Email verified' : 'Email verification pending'}
                  </small>
                </div>
                <button type="button" onClick={() => void logout()} disabled={authPending}>Log out</button>
              </header>
              <div className="bn-cloud-credit-grid">
                <div><span>Available</span><strong>{availableCredits.toLocaleString()}</strong></div>
                <div><span>Locked</span><strong>{lockedCredits.toLocaleString()}</strong></div>
                <div><span>Reserved</span><strong>{credits.reserved.toLocaleString()}</strong></div>
                <div><span>Balance</span><strong>{credits.balance.toLocaleString()}</strong></div>
              </div>
              <label className="bn-cloud-provider-setting">
                <span>Cloud compute provider</span>
                <select
                  value={providerPreference}
                  disabled={providerPending}
                  onChange={event => void updateProviderPreference(event.target.value as CloudProviderPreference)}
                >
                  {providerOptions.map(option => (
                    <option key={option.id} value={option.id} disabled={!option.available}>
                      {option.label}{option.available ? '' : ' (unavailable)'}
                    </option>
                  ))}
                </select>
                <small>
                  {providerPending
                    ? 'Saving provider preference…'
                    : providerPreference === 'auto'
                      ? 'Auto uses the Cloud service default provider.'
                      : `New jobs will use ${providerLabel}. Existing jobs stay with their original provider.`}
                </small>
              </label>
              <small>Credits are GPU-seconds. This job reserves its runtime limit and charges measured GPU time.</small>
              {!emailVerified && (
                <div className="bn-cloud-verification-lock" role="status">
                  <strong>Verify your email to unlock Cloud runs</strong>
                  <span>Your signup credits are saved and will become available after verification.</span>
                  <button type="button" onClick={() => void refreshVerification()} disabled={authPending}>
                    {authPending ? 'Refreshing…' : 'I verified — refresh status'}
                  </button>
                </div>
              )}
              <button type="button" className="is-primary bn-cloud-submit" onClick={onRun} disabled={pending || !emailVerified}>
                {emailVerified ? `Run workflow via ${providerLabel} · NVIDIA L40S` : 'Email verification required'}
              </button>
            </div>

            <div className="bn-cloud-run-section bn-cloud-vla-form">
              <header><strong>Fine Tune VLA</strong><span>π0.5 · JAX LoRA</span></header>
              <label>
                <span>Dataset source</span>
                <select value={vlaSource} onChange={event => setVlaSource(event.target.value as 'huggingface' | 'cloud')}>
                  <option value="huggingface">Pinned Hugging Face dataset</option>
                  <option value="cloud">Uploaded Blacknode dataset</option>
                </select>
              </label>
              {vlaSource === 'huggingface' ? (
                <>
                  <label>
                    <span>Dataset URI</span>
                    <input value={vlaDatasetUri} onChange={event => setVlaDatasetUri(event.target.value)} placeholder="hf://owner/dataset" />
                  </label>
                  <label>
                    <span>Immutable revision</span>
                    <input value={vlaDatasetRevision} onChange={event => setVlaDatasetRevision(event.target.value)} placeholder="commit SHA" />
                  </label>
                </>
              ) : (
                <>
                  <label>
                    <span>Cloud dataset</span>
                    <select value={vlaDatasetId} onChange={event => setVlaDatasetId(event.target.value)}>
                      <option value="">Choose uploaded dataset</option>
                      {datasets.map(dataset => (
                        <option key={dataset.id} value={dataset.id}>{dataset.name} · {bytes(dataset.size_bytes)}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Upload LeRobot archive</span>
                    <input type="file" accept=".tar.gz,.tgz,application/gzip" disabled={vlaPending} onChange={event => void uploadDataset(event.target.files?.[0])} />
                  </label>
                </>
              )}
              <div className="bn-cloud-credit-grid">
                <label><span>Steps</span><input type="number" min={1} max={10000000} value={vlaSteps} onChange={event => setVlaSteps(Number(event.target.value))} /></label>
                <label><span>Batch size</span><input type="number" min={1} max={1024} value={vlaBatchSize} onChange={event => setVlaBatchSize(Number(event.target.value))} /></label>
                <label><span>Action horizon</span><input type="number" min={1} max={256} value={vlaActionHorizon} onChange={event => setVlaActionHorizon(Number(event.target.value))} /></label>
                <label><span>Max runtime (seconds)</span><input type="number" min={60} max={86400} value={vlaRuntime} onChange={event => setVlaRuntime(Number(event.target.value))} /></label>
              </div>
              <small>GPU is selected by Blacknode Cloud. V0 resolves to one NVIDIA L40S and produces a downloadable Blacknode VLA model.</small>
              <button type="button" className="is-primary bn-cloud-submit" onClick={() => void runVla()} disabled={vlaPending || !emailVerified}>
                {vlaPending ? 'Preparing…' : 'Fine tune π0.5'}
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

        {visibleJob && credits && (
          <div className="bn-cloud-job-credits">
            <span>{availableCredits.toLocaleString()} available</span>
            <span>{credits.reserved.toLocaleString()} reserved</span>
          </div>
        )}

        {visibleJob && (
          <>
            <div className="bn-cloud-run-facts">
              <div><span>Job</span><strong>{visibleJob.id}</strong></div>
              <div><span>GPU</span><strong>NVIDIA L40S</strong></div>
              <div><span>Workload</span><strong>{visibleJob.workload_kind === 'vla_train' ? 'VLA training' : 'Workflow'}</strong></div>
              <div><span>Provider</span><strong>{visibleJob.compute_provider}</strong></div>
              <div><span>Status</span><strong className={`is-${visibleJob.status.toLowerCase()}`}>● {visibleJob.status}</strong></div>
              <div><span>Runtime</span><strong>{elapsed(visibleJob)}</strong></div>
              {vlaModel?.kind === 'blacknode.vla-model' && (
                <div><span>Inference</span><strong>{(vlaModel.inference as Record<string, unknown> | undefined)?.verified ? 'Verified' : 'Unavailable'}</strong></div>
              )}
            </div>
            <div className="bn-cloud-progress" aria-label={`${visibleJob.progress}% complete`}>
              <i style={{ width: `${visibleJob.progress}%` }} />
            </div>
            <div className="bn-cloud-progress-label"><span>Progress</span><strong>{visibleJob.progress}%</strong></div>

            {rewardPoints && (
              <div className="bn-cloud-metric-chart">
                <header><span>Reward</span><strong>{reward[reward.length - 1]?.value.toFixed(3)}</strong></header>
                <svg viewBox="0 0 300 84" preserveAspectRatio="none" aria-label="Reward metric">
                  <polyline points={rewardPoints} fill="none" stroke="currentColor" strokeWidth="2" />
                </svg>
              </div>
            )}

            {lossPoints && (
              <div className="bn-cloud-metric-chart">
                <header><span>Loss</span><strong>{loss[loss.length - 1]?.value.toFixed(4)}</strong></header>
                <svg viewBox="0 0 300 84" preserveAspectRatio="none" aria-label="Loss metric">
                  <polyline points={lossPoints} fill="none" stroke="currentColor" strokeWidth="2" />
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
                  <a key={artifact.id} href={api.cloudArtifactDownloadUrl(visibleJob.id, artifact.id)} download={artifact.name}>
                    <span>{artifact.name}</span><small>{bytes(artifact.size_bytes)} · download</small>
                  </a>
                ))}
                {artifacts.length === 0 && <p>Artifacts appear here as the job completes.</p>}
              </div>
            </div>

            {visibleJob.result !== null && visibleJob.result !== undefined && (
              <div className="bn-cloud-run-section">
                <header><strong>Result</strong></header>
                <pre>{JSON.stringify(visibleJob.result, null, 2)}</pre>
              </div>
            )}
            {visibleJob.error_message && <div className="bn-cloud-run-error">{visibleJob.error_message}</div>}
            {activeJob && (
              <footer>
                <button type="button" onClick={() => void api.cancelCloudJob(visibleJob.id).then(setJob)}>
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
