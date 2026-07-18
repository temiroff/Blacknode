import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'

type AnyRecord = Record<string, any>
type FrameCallbackVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (callback: (now: number, metadata: { mediaTime: number }) => void) => number
  cancelVideoFrameCallback?: (id: number) => void
}

const panel: React.CSSProperties = {
  margin: '7px 9px 3px', padding: 10, borderRadius: 8,
  border: '1px solid var(--line)', background: 'rgba(255,255,255,.02)',
  fontFamily: 'var(--font-ui)',
}

const button = (disabled = false): React.CSSProperties => ({
  border: '1px solid var(--line)', borderRadius: 5, padding: '4px 9px',
  background: disabled ? 'rgba(255,255,255,.03)' : 'rgba(139,92,246,.18)',
  color: disabled ? 'var(--tx3)' : 'var(--tx1)', cursor: disabled ? 'default' : 'pointer',
  fontSize: 10, fontWeight: 700,
})

const selectStyle: React.CSSProperties = {
  minWidth: 150, maxWidth: 260, padding: '4px 6px', borderRadius: 5,
  border: '1px solid var(--line)', background: 'var(--bg2)', color: 'var(--tx1)', fontSize: 10,
  colorScheme: 'dark',
}

const optionStyle: React.CSSProperties = { background: '#0f172a', color: '#e2e8f0' }

export default function DatasetBrowserPanel({ id, data }: {
  id: string
  data: { params?: Record<string, unknown>; portResults?: Record<string, unknown> }
}) {
  const updateParam = useStore(s => s.updateParam)
  const cookNode = useStore(s => s.cookNode)
  const pickDirectory = useStore(s => s.pickDirectory)
  const [pending, setPending] = useState(false)
  const [frame, setFrame] = useState<AnyRecord | null>(null)
  const [playing, setPlaying] = useState(false)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [loop, setLoop] = useState(false)
  const [angleUnit, setAngleUnit] = useState<'radians' | 'degrees'>('radians')
  const [trimPending, setTrimPending] = useState<'before' | 'after' | null>(null)
  const [trimMessage, setTrimMessage] = useState('')
  const lastFrame = useRef(-1)
  const lastPublishedFrame = useRef(-1)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  const catalog = data.portResults?.catalog && typeof data.portResults.catalog === 'object'
    ? data.portResults.catalog as AnyRecord : {}
  const datasets = Array.isArray(catalog.datasets) ? catalog.datasets as AnyRecord[] : []
  const selectedDataset = catalog.selected_dataset && typeof catalog.selected_dataset === 'object'
    ? catalog.selected_dataset as AnyRecord : {}
  const episodes = Array.isArray(selectedDataset.episodes) ? selectedDataset.episodes as AnyRecord[] : []
  const episode = catalog.selected_episode && typeof catalog.selected_episode === 'object'
    ? catalog.selected_episode as AnyRecord : {}
  const cameras = Array.isArray(episode.cameras) ? episode.cameras.map(String) : []
  const rawVideo = typeof catalog.video === 'string' ? catalog.video : ''
  const video = rawVideo.startsWith('/dataset/') ? `/api${rawVideo}` : rawVideo
  const token = typeof catalog.replay_token === 'string' ? catalog.replay_token : ''
  const fps = Number(episode.fps ?? 0)
  const totalFrames = Number(episode.frames ?? 0)

  useEffect(() => {
    setFrame(null)
    setPlaying(false)
    lastFrame.current = -1
    lastPublishedFrame.current = -1
  }, [token])

  const refresh = async (patch: Record<string, unknown> = {}) => {
    if (pending) return
    setPending(true)
    try {
      const effectivePatch = Object.keys(patch).length > 0 ? patch : { refresh_key: Date.now() }
      for (const [key, value] of Object.entries(effectivePatch)) await updateParam(id, key, value)
      await cookNode(id, 'catalog')
    } finally {
      setPending(false)
    }
  }

  const chooseRoot = async () => {
    if (pending) return
    const selected = await pickDirectory(String(data.params?.root ?? ''))
    if (selected) await refresh({ root: selected, dataset_id: '', episode_index: 0, camera: '' })
  }

  const updateReplayFrame = async (time: number) => {
    if (!token || !fps) return
    const index = Math.min(Math.max(0, totalFrames - 1), Math.max(0, Math.floor(time * fps)))
    if (index === lastFrame.current) return
    lastFrame.current = index
    try {
      setFrame(await api.datasetFrame(token, index))
    } catch {
      // Playback remains usable even if one metadata request races a selection change.
    }
  }

  const publishReplayPosition = (time: number, event: 'play' | 'seek', force = false) => {
    if (!token || !fps || totalFrames <= 0) return
    const index = Math.min(totalFrames - 1, Math.max(0, Math.floor(time * fps)))
    if (!force && index === lastPublishedFrame.current) return
    lastPublishedFrame.current = index
    void api.publishDatasetReplayFrame(token, index, event).catch(() => {
      // A publisher is optional; local dataset replay remains usable by itself.
    })
  }

  useEffect(() => {
    const player = videoRef.current as FrameCallbackVideo | null
    if (!playing || !player || !token || !fps || totalFrames <= 0) return
    let cancelled = false
    let callbackId: number | null = null
    let timerId: number | null = null
    const publishFrame = (_now?: number, metadata?: { mediaTime: number }) => {
      if (cancelled || player.paused) return
      publishReplayPosition(metadata?.mediaTime ?? player.currentTime, 'play')
      if (player.requestVideoFrameCallback) callbackId = player.requestVideoFrameCallback(publishFrame)
    }
    if (player.requestVideoFrameCallback) {
      callbackId = player.requestVideoFrameCallback(publishFrame)
    } else {
      timerId = window.setInterval(() => publishReplayPosition(player.currentTime, 'play'),
        Math.max(16, 1000 / fps))
    }
    return () => {
      cancelled = true
      if (callbackId !== null && player.cancelVideoFrameCallback) player.cancelVideoFrameCallback(callbackId)
      if (timerId !== null) window.clearInterval(timerId)
    }
  }, [playing, token, fps, totalFrames])

  const jointNames = frame && Array.isArray(frame.joint_names) ? frame.joint_names.map(String) : []
  const leader = (frame?.leader ?? {}) as AnyRecord
  const observation = (frame?.observation ?? {}) as AnyRecord
  const action = (frame?.action ?? {}) as AnyRecord
  const storedUnits = String(episode.units ?? 'radians').toLowerCase()
  const displayAngle = (value: unknown) => {
    const numeric = Number(value ?? 0)
    if (angleUnit === 'degrees' && storedUnits.startsWith('rad')) return numeric * 180 / Math.PI
    if (angleUnit === 'radians' && storedUnits.startsWith('deg')) return numeric * Math.PI / 180
    return numeric
  }

  const toggleReplay = async () => {
    const player = videoRef.current
    if (!player) return
    if (player.paused) await player.play()
    else player.pause()
  }

  const restartReplay = async () => {
    const player = videoRef.current
    if (!player) return
    player.currentTime = 0
    await updateReplayFrame(0)
    await player.play()
  }

  const stepFrame = async (direction: -1 | 1) => {
    const player = videoRef.current
    if (!player || !fps) return
    player.pause()
    player.currentTime = Math.max(0, Math.min(player.duration || Number.POSITIVE_INFINITY, player.currentTime + direction / fps))
    await updateReplayFrame(player.currentTime)
  }

  const trimEpisode = async (side: 'before' | 'after') => {
    const player = videoRef.current
    if (!token || !player || trimPending) return
    player.pause()
    const index = Math.min(
      Math.max(0, totalFrames - 1),
      Math.max(0, Math.floor(player.currentTime * fps)),
    )
    const removeCount = side === 'before' ? index : Math.max(0, totalFrames - index - 1)
    if (removeCount <= 0) return
    const label = side === 'before' ? `before frame ${index}` : `after frame ${index}`
    if (!window.confirm(
      `Permanently remove ${removeCount} frame(s) ${label} from episode ${episode.episode_index}?\n\n` +
      'The selected frame is kept. Every camera video and the synchronized robot data will be trimmed together.'
    )) return
    setTrimPending(side)
    setTrimMessage('')
    try {
      const result = await api.trimDatasetEpisode(token, index, side)
      setTrimMessage(`Trimmed ${Number(result.removed_frames ?? removeCount)} frame(s); ${Number(result.frames ?? 0)} remain.`)
      await refresh({ refresh_key: Date.now() })
    } catch (error) {
      setTrimMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setTrimPending(null)
    }
  }

  return (
    <div className="nodrag" style={panel}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
        <strong style={{ color: 'var(--tx1)', fontSize: 11 }}>DATASET BROWSER</strong>
        <button disabled={pending} style={button(pending)} onClick={() => void chooseRoot()}>
          Choose root…
        </button>
        <button disabled={pending} style={button(pending)} onClick={() => void refresh()}>
          {pending ? 'Loading…' : 'Refresh'}
        </button>
        <span style={{ color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 9, wordBreak: 'break-all' }}>
          {String(catalog.root ?? data.params?.root ?? '~/.blacknode/datasets')}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 9, flexWrap: 'wrap' }}>
        <label style={{ color: 'var(--tx3)', fontSize: 9 }}>
          Dataset<br />
          <select value={String(selectedDataset.dataset_id ?? '')} style={selectStyle}
            onChange={event => void refresh({ dataset_id: event.target.value, episode_index: 0, camera: '' })}>
            {datasets.length === 0 && <option style={optionStyle} value="">No datasets found</option>}
            {datasets.map(item => <option style={optionStyle} key={String(item.path)} value={String(item.dataset_id)}>{String(item.dataset_id)}</option>)}
          </select>
        </label>
        <label style={{ color: 'var(--tx3)', fontSize: 9 }}>
          Episode<br />
          <select value={String(episode.episode_index ?? 0)} style={selectStyle}
            onChange={event => void refresh({ episode_index: Number(event.target.value), camera: '' })}>
            {episodes.length === 0 && <option style={optionStyle} value="0">No saved episodes</option>}
            {episodes.map(item => <option style={optionStyle} key={String(item.episode_index)} value={String(item.episode_index)}>
              #{item.episode_index} · {Number(item.duration_seconds ?? 0).toFixed(1)}s · {item.frames} frames
            </option>)}
          </select>
        </label>
        <label style={{ color: 'var(--tx3)', fontSize: 9 }}>
          Camera<br />
          <select value={String(episode.camera ?? '')} style={selectStyle}
            onChange={event => void refresh({ camera: event.target.value })}>
            {cameras.length === 0 && <option style={optionStyle} value="">No camera video</option>}
            {cameras.map(name => <option style={optionStyle} key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>

      {video ? (
        <>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, flexWrap: 'wrap', padding: 7, borderRadius: 6, background: 'rgba(139,92,246,.09)', border: '1px solid rgba(139,92,246,.3)' }}>
          <button style={{ ...button(false), minWidth: 76, background: playing ? 'rgba(245,158,11,.2)' : 'rgba(34,197,94,.2)' }} onClick={() => void toggleReplay()}>
            {playing ? 'Ⅱ Pause' : '▶ Replay'}
          </button>
          <button style={button(false)} onClick={() => void restartReplay()}>↺ Restart</button>
          <button style={button(false)} onClick={() => void stepFrame(-1)}>‹ Frame</button>
          <button style={button(false)} onClick={() => void stepFrame(1)}>Frame ›</button>
          <label style={{ color: 'var(--tx3)', fontSize: 9 }}>
            Speed&nbsp;
            <select value={playbackRate} style={{ ...selectStyle, minWidth: 66, width: 66 }} onChange={event => {
              const rate = Number(event.target.value)
              setPlaybackRate(rate)
              if (videoRef.current) videoRef.current.playbackRate = rate
            }}>
              {[0.25, 0.5, 1, 1.5, 2].map(rate => <option style={optionStyle} key={rate} value={rate}>{rate}×</option>)}
            </select>
          </label>
          <label style={{ color: 'var(--tx2)', fontSize: 9, display: 'flex', alignItems: 'center', gap: 4 }}>
            <input type="checkbox" checked={loop} onChange={event => setLoop(event.target.checked)} /> Loop
          </label>
          <span style={{ display: 'flex', gap: 2, padding: 2, border: '1px solid var(--line)', borderRadius: 5 }}>
            <button style={{ ...button(angleUnit !== 'radians'), padding: '2px 7px', background: angleUnit === 'radians' ? 'rgba(139,92,246,.3)' : 'transparent' }} onClick={() => setAngleUnit('radians')}>rad</button>
            <button style={{ ...button(angleUnit !== 'degrees'), padding: '2px 7px', background: angleUnit === 'degrees' ? 'rgba(139,92,246,.3)' : 'transparent' }} onClick={() => setAngleUnit('degrees')}>deg</button>
          </span>
          <span style={{ display: 'flex', gap: 4, paddingLeft: 5, borderLeft: '1px solid var(--line)' }}>
            <button disabled={Boolean(trimPending) || Number(frame?.frame_index ?? 0) <= 0}
              title="Keep the selected frame and delete every earlier synchronized frame"
              style={{ ...button(Boolean(trimPending) || Number(frame?.frame_index ?? 0) <= 0), borderColor: 'rgba(239,68,68,.45)' }}
              onClick={() => void trimEpisode('before')}>
              {trimPending === 'before' ? 'Cutting…' : '✂ Cut before'}
            </button>
            <button disabled={Boolean(trimPending) || Number(frame?.frame_index ?? 0) >= totalFrames - 1}
              title="Keep the selected frame and delete every later synchronized frame"
              style={{ ...button(Boolean(trimPending) || Number(frame?.frame_index ?? 0) >= totalFrames - 1), borderColor: 'rgba(239,68,68,.45)' }}
              onClick={() => void trimEpisode('after')}>
              {trimPending === 'after' ? 'Cutting…' : '✂ Cut after'}
            </button>
          </span>
          <span style={{ marginLeft: 'auto', color: 'var(--tx3)', fontSize: 9 }}>Read-only replay · robot commands disabled</span>
        </div>
        {trimMessage && <div style={{ marginTop: 6, color: trimMessage.startsWith('Trimmed') ? 'var(--ok)' : 'var(--warn)', fontSize: 9, fontFamily: 'var(--font-mono)' }}>
          {trimMessage}
        </div>}
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 1.4fr) minmax(330px, 1fr)', gap: 10, marginTop: 8 }}>
          <video ref={videoRef} key={video} src={video} controls playsInline preload="metadata" loop={loop}
            onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
            onLoadedMetadata={event => void updateReplayFrame(event.currentTarget.currentTime)}
            onTimeUpdate={event => void updateReplayFrame(event.currentTarget.currentTime)}
            onSeeking={event => {
              void updateReplayFrame(event.currentTarget.currentTime)
              publishReplayPosition(event.currentTarget.currentTime, 'seek')
            }}
            onSeeked={event => {
              void updateReplayFrame(event.currentTarget.currentTime)
              publishReplayPosition(event.currentTarget.currentTime, 'seek', true)
            }}
            style={{ width: '100%', maxHeight: 470, background: '#020617', borderRadius: 7, objectFit: 'contain' }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ color: 'var(--tx2)', fontFamily: 'var(--font-mono)', fontSize: 10, lineHeight: 1.55 }}>
              <div>episode {episode.episode_index ?? 0} · frame {frame?.frame_index ?? 0}/{Math.max(0, totalFrames - 1)}</div>
              <div>{Number(frame?.timestamp ?? 0).toFixed(3)}s · {fps} fps · displaying {angleUnit}</div>
              <div>sample #{frame?.sample_sequence ?? 0} · camera #{frame?.cameras?.[episode.camera]?.sequence ?? 0}</div>
              <div>robot captured {frame?.captured_at_ns ?? 0}</div>
              <div>camera captured {frame?.cameras?.[episode.camera]?.captured_at_ns ?? 0}</div>
              <div>recorded {frame?.recorded_at_ns ?? 0}</div>
            </div>
            <div style={{ maxHeight: 355, overflow: 'auto', marginTop: 7, border: '1px solid var(--line)', borderRadius: 6 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 9 }}>
                <thead><tr style={{ color: 'var(--tx3)', position: 'sticky', top: 0, background: 'var(--bg2)' }}>
                  <th style={{ padding: 5, textAlign: 'left' }}>joint</th><th>leader</th><th>observed</th><th>action</th>
                </tr></thead>
                <tbody>{jointNames.map(name => <tr key={name} style={{ borderTop: '1px solid var(--line)', color: 'var(--tx2)' }}>
                  <td style={{ padding: 5 }}>{name}</td>
                  <td style={{ textAlign: 'right', padding: 5 }}>{displayAngle(leader[name]).toFixed(angleUnit === 'degrees' ? 2 : 4)}</td>
                  <td style={{ textAlign: 'right', padding: 5 }}>{displayAngle(observation[name]).toFixed(angleUnit === 'degrees' ? 2 : 4)}</td>
                  <td style={{ textAlign: 'right', padding: 5 }}>{displayAngle(action[name]).toFixed(angleUnit === 'degrees' ? 2 : 4)}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </div>
        </div>
        </>
      ) : (
        <div style={{ marginTop: 12, padding: 24, borderRadius: 7, background: '#020617', color: 'var(--tx3)', textAlign: 'center', fontSize: 11 }}>
          {datasets.length ? 'Select a dataset containing a saved episode.' : 'Choose a dataset root, then press Refresh.'}
        </div>
      )}

      {episode.episode_path && <div style={{ marginTop: 8, color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 8.5, lineHeight: 1.45, wordBreak: 'break-all' }}>
        <div>Episode: {episode.episode_path}</div>
        <div>Video: {episode.video_path}</div>
        <div>Robot data: {episode.data_path}</div>
        <div>Task: {episode.task || '—'} · saved {episode.saved_at || '—'}</div>
      </div>}
      {episode.episode_path && <details style={{ marginTop: 7, color: 'var(--tx3)', fontSize: 9 }}>
        <summary style={{ cursor: 'pointer', color: 'var(--tx2)', fontWeight: 700 }}>All episode and current-frame metadata</summary>
        <pre style={{ maxHeight: 260, overflow: 'auto', margin: '6px 0 0', padding: 7, borderRadius: 5, background: '#020617', color: 'var(--tx2)', fontFamily: 'var(--font-mono)', fontSize: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {JSON.stringify({ episode, frame }, null, 2)}
        </pre>
      </details>}
    </div>
  )
}
