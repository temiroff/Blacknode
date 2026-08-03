import { useEffect, useMemo, useRef } from 'react'

interface ViewerScene {
  kind?: string
  primitive?: string
  frame?: string
  points?: unknown
  colors?: unknown
  point_count?: number
  display_count?: number
  device?: string
  kernel_ms?: number
}

function numericRows(value: unknown): number[][] {
  if (!Array.isArray(value)) return []
  return value
    .filter((row): row is unknown[] => Array.isArray(row) && row.length >= 2)
    .map(row => row.slice(0, 3).map(item => Number(item)))
    .filter(row => row.every(Number.isFinite))
}

function shader(gl: WebGLRenderingContext, kind: number, source: string): WebGLShader {
  const result = gl.createShader(kind)
  if (!result) throw new Error('WebGL could not create a shader')
  gl.shaderSource(result, source)
  gl.compileShader(result)
  if (!gl.getShaderParameter(result, gl.COMPILE_STATUS)) {
    const detail = gl.getShaderInfoLog(result) || 'unknown shader error'
    gl.deleteShader(result)
    throw new Error(detail)
  }
  return result
}

export default function PointCloudViewer({ scene }: { scene: unknown }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const parsed = (scene && typeof scene === 'object' ? scene : {}) as ViewerScene
  const points = useMemo(() => numericRows(parsed.points), [parsed.points])
  const colors = useMemo(() => numericRows(parsed.colors), [parsed.colors])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const gl = canvas.getContext('webgl', { antialias: true, alpha: false })
    if (!gl) return
    const ratio = Math.min(2, window.devicePixelRatio || 1)
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio))
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio))
    if (canvas.width !== width) canvas.width = width
    if (canvas.height !== height) canvas.height = height
    gl.viewport(0, 0, width, height)
    gl.clearColor(0.012, 0.022, 0.035, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)
    if (points.length === 0) return

    const vertex = shader(gl, gl.VERTEX_SHADER, `
      attribute vec2 a_position;
      attribute vec3 a_color;
      varying vec3 v_color;
      void main() {
        gl_Position = vec4(a_position, 0.0, 1.0);
        gl_PointSize = 4.5;
        v_color = a_color;
      }
    `)
    const fragment = shader(gl, gl.FRAGMENT_SHADER, `
      precision mediump float;
      varying vec3 v_color;
      void main() {
        vec2 centered = gl_PointCoord - vec2(0.5);
        if (dot(centered, centered) > 0.25) discard;
        gl_FragColor = vec4(v_color, 1.0);
      }
    `)
    const program = gl.createProgram()
    if (!program) return
    gl.attachShader(program, vertex)
    gl.attachShader(program, fragment)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.deleteProgram(program)
      gl.deleteShader(vertex)
      gl.deleteShader(fragment)
      return
    }
    gl.useProgram(program)

    const maximum = Math.max(
      1,
      ...points.flatMap(point => [Math.abs(point[0]), Math.abs(point[1])]),
    )
    const aspect = width / Math.max(1, height)
    const positions = new Float32Array(points.length * 2)
    const palette = new Float32Array(points.length * 3)
    points.forEach((point, index) => {
      positions[index * 2] = (point[0] / maximum) * 0.9 / Math.max(1, aspect)
      positions[index * 2 + 1] = (point[1] / maximum) * 0.9 * Math.min(1, aspect)
      const color = colors[index] ?? [0.0, 0.78, 1.0]
      palette[index * 3] = color[0]
      palette[index * 3 + 1] = color[1]
      palette[index * 3 + 2] = color[2]
    })

    const positionBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW)
    const positionLocation = gl.getAttribLocation(program, 'a_position')
    gl.enableVertexAttribArray(positionLocation)
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0)

    const colorBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, palette, gl.STATIC_DRAW)
    const colorLocation = gl.getAttribLocation(program, 'a_color')
    gl.enableVertexAttribArray(colorLocation)
    gl.vertexAttribPointer(colorLocation, 3, gl.FLOAT, false, 0, 0)

    gl.drawArrays(gl.POINTS, 0, points.length)

    return () => {
      gl.deleteBuffer(positionBuffer)
      gl.deleteBuffer(colorBuffer)
      gl.deleteProgram(program)
      gl.deleteShader(vertex)
      gl.deleteShader(fragment)
    }
  }, [colors, points])

  const pointCount = Number(parsed.point_count ?? points.length)
  const displayCount = Number(parsed.display_count ?? points.length)
  const kernelMs = Number(parsed.kernel_ms ?? 0)

  return (
    <div
      className="nodrag"
      onMouseDown={event => event.stopPropagation()}
      style={{
        margin: '7px 9px 3px',
        overflow: 'hidden',
        border: '1px solid var(--line2)',
        borderRadius: 'var(--bn-node-inner-radius, 7px)',
        background: '#03070d',
      }}
    >
      <canvas
        ref={canvasRef}
        aria-label="Live point-cloud Viewer"
        style={{ display: 'block', width: '100%', height: 360 }}
      />
      <div style={{
        display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
        padding: '6px 9px', borderTop: '1px solid var(--line)',
        color: 'var(--tx3)', fontFamily: 'var(--font-mono)', fontSize: 11,
      }}>
        <span>{points.length ? `${pointCount.toLocaleString()} points` : 'Waiting for points'}</span>
        {displayCount > 0 && displayCount !== pointCount && <span>{displayCount.toLocaleString()} displayed</span>}
        {kernelMs > 0 && <span>{kernelMs.toFixed(3)} ms Warp</span>}
        {parsed.device && <span>{parsed.device}</span>}
        {parsed.frame && <span>{parsed.frame}</span>}
      </div>
    </div>
  )
}
