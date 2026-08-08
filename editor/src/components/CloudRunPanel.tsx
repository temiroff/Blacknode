import { useEffect, useMemo, useRef, useState } from 'react'

import {
  api,
  type CloudArtifact,
  type CloudJob,
  type CloudJobEvent,
} from '../api'

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELED', 'TIMED_OUT'])

interface Props {
  open: boolean
  pending: boolean
  initialJob: CloudJob | null
  error: string
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

export default function CloudRunPanel({ open, pending, initialJob, error, onClose }: Props) {
  const [job, setJob] = useState<CloudJob | null>(initialJob)
  const [events, setEvents] = useState<CloudJobEvent[]>([])
  const [artifacts, setArtifacts] = useState<CloudArtifact[]>([])
  const [pollError, setPollError] = useState('')
  const nextSeq = useRef(0)

  useEffect(() => {
    setJob(initialJob)
    setEvents([])
    setArtifacts([])
    setPollError('')
    nextSeq.current = 0
  }, [initialJob?.id])

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

  if (!open) return null
  return (
    <div className="bn-cloud-run-backdrop" role="presentation">
      <section className="bn-cloud-run-panel" role="dialog" aria-modal="true" aria-label="Blacknode Cloud job">
        <header>
          <div>
            <span>BLACKNODE CLOUD</span>
            <strong>{job ? job.workflow_name : 'Submitting workflow'}</strong>
          </div>
          <button type="button" onClick={onClose} aria-label="Close Cloud job">×</button>
        </header>

        {(pending || (!job && !error)) && <div className="bn-cloud-run-message">Creating NVIDIA L40S job…</div>}
        {(error || pollError) && <div className="bn-cloud-run-error">{error || pollError}</div>}

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
                  <a
                    key={artifact.id}
                    href={api.cloudArtifactDownloadUrl(job.id, artifact.id)}
                    download={artifact.name}
                  >
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
            {!TERMINAL.has(job.status) && (
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
