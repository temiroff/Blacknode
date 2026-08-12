import { useEffect, useRef, useState } from 'react'

import { api, type MappingSnapshot } from '../api'


export default function LiveOccupancyMap({
  deviceId,
  deploymentId,
  topic,
}: {
  deviceId: string
  deploymentId: string
  topic: string
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [snapshot, setSnapshot] = useState<MappingSnapshot | null>(null)
  const [message, setMessage] = useState('Connecting to the live map…')

  useEffect(() => {
    let cancelled = false
    const pull = async () => {
      try {
        const next = await api.remoteDeploymentMapSnapshot(deviceId, deploymentId)
        if (cancelled) return
        setSnapshot(next)
        setMessage(next.report || 'Waiting for occupancy data…')
      } catch (err) {
        if (!cancelled) setMessage(err instanceof Error ? err.message : String(err))
      }
    }
    void pull()
    const timer = window.setInterval(pull, 2000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [deviceId, deploymentId])

  useEffect(() => {
    const canvas = canvasRef.current
    const info = snapshot?.message?.info
    const data = snapshot?.message?.data
    const width = Math.max(0, Number(info?.width || 0))
    const height = Math.max(0, Number(info?.height || 0))
    if (!canvas || !Array.isArray(data) || !width || !height || data.length < width * height) return
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) return
    const image = context.createImageData(width, height)
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const sourceIndex = y * width + x
        const targetIndex = ((height - y - 1) * width + x) * 4
        const occupancy = Number(data[sourceIndex])
        const color = occupancy < 0 ? [30, 36, 48] : occupancy >= 65 ? [20, 24, 31] : [226, 232, 240]
        image.data[targetIndex] = color[0]
        image.data[targetIndex + 1] = color[1]
        image.data[targetIndex + 2] = color[2]
        image.data[targetIndex + 3] = 255
      }
    }
    context.putImageData(image, 0, 0)
  }, [snapshot])

  const info = snapshot?.message?.info
  const fresh = snapshot?.status?.source_fresh !== false && Boolean(snapshot?.message?.data?.length)
  return (
    <section className="bn-live-map" aria-label={`Live occupancy map from ${topic}`}>
      <div className="bn-live-map-head">
        <strong>Live mapping · {topic}</strong>
        <span className={fresh ? 'is-live' : ''}>{fresh ? 'LIVE' : 'WAITING'}</span>
      </div>
      <canvas ref={canvasRef} />
      <div className="bn-live-map-foot">
        <span>{message}</span>
        {info?.width && info?.height && (
          <span>{info.width} × {info.height} cells · {Number(info.resolution || 0).toFixed(3)} m/cell</span>
        )}
      </div>
    </section>
  )
}
