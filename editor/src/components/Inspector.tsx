import { useState, useEffect, useRef } from 'react'
import { useStore } from '../store'
import { portColor } from '../portColors'

const WIRE_ONLY = new Set(['List', 'Dict', 'Fn', 'Embedding'])
const TOP_BAR_H = 44
const RAIL_W = 78
const PANEL_DEFAULT_W = 260
const PANEL_MIN_W = 200
const PANEL_MAX_W = 560
const CUSTOM_KERNEL_TEMPLATE_PRESETS: Record<string, { code: string; signature: string; output_mode: string }> = {
  image_invert: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int p = i * channels;
    float r = in[p + 0];
    float g = in[p + 1];
    float b = in[p + 2];

    out[p + 0] = 1.0f - r;
    out[p + 1] = 1.0f - g;
    out[p + 2] = 1.0f - b;
}`,
  },
  cinematic_teal_orange: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;

    int pixels = width * height;
    if (i >= pixels) return;

    int p = i * channels;

    float r = in[p + 0];
    float g = in[p + 1];
    float b = in[p + 2];

    // cinematic contrast
    r = powf(r, 0.85f);
    g = powf(g, 0.90f);
    b = powf(b, 1.05f);

    // teal-orange grade
    r *= 1.15f;
    g *= 1.00f;
    b *= 0.90f;

    // vignette
    int x = i % width;
    int y = i / width;

    float nx = (x / (float)width) * 2.0f - 1.0f;
    float ny = (y / (float)height) * 2.0f - 1.0f;

    float dist = sqrtf(nx * nx + ny * ny);
    float vignette = 1.0f - fminf(dist * 0.4f, 0.4f);

    r *= vignette;
    g *= vignette;
    b *= vignette;

    out[p + 0] = fminf(fmaxf(r, 0.0f), 1.0f);
    out[p + 1] = fminf(fmaxf(g, 0.0f), 1.0f);
    out[p + 2] = fminf(fmaxf(b, 0.0f), 1.0f);

    if (channels == 4)
        out[p + 3] = in[p + 3];
}`,
  },
  neon_edge_glow_2d: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels)
{
    int x = blockDim.x * blockIdx.x + threadIdx.x;
    int y = blockDim.y * blockIdx.y + threadIdx.y;

    if (x >= width || y >= height) return;

    int i = y * width + x;
    int p = i * channels;

    float r = in[p + 0];
    float g = in[p + 1];
    float b = in[p + 2];

    float lum = 0.299f * r + 0.587f * g + 0.114f * b;

    int xl = x > 0 ? x - 1 : 0;
    int xr = x + 1 < width ? x + 1 : width - 1;
    int yu = y > 0 ? y - 1 : 0;
    int yd = y + 1 < height ? y + 1 : height - 1;

    int pl = (y * width + xl) * channels;
    int pr = (y * width + xr) * channels;
    int pu = (yu * width + x) * channels;
    int pd = (yd * width + x) * channels;

    float lumL = 0.299f * in[pl] + 0.587f * in[pl + 1] + 0.114f * in[pl + 2];
    float lumR = 0.299f * in[pr] + 0.587f * in[pr + 1] + 0.114f * in[pr + 2];
    float lumU = 0.299f * in[pu] + 0.587f * in[pu + 1] + 0.114f * in[pu + 2];
    float lumD = 0.299f * in[pd] + 0.587f * in[pd + 1] + 0.114f * in[pd + 2];

    float edge = fabsf(lumR - lumL) + fabsf(lumD - lumU);
    edge = fminf(edge * 4.0f, 1.0f);

    float nx = (x / (float)width)  * 2.0f - 1.0f;
    float ny = (y / (float)height) * 2.0f - 1.0f;
    float dist = sqrtf(nx * nx + ny * ny);
    float vignette = 1.0f - fminf(dist * 0.55f, 0.55f);

    r = powf(r, 0.95f) * 1.08f;
    g = powf(g, 1.00f) * 1.02f;
    b = powf(b, 1.08f) * 0.95f;

    r += edge * 0.95f;
    g += edge * 0.35f;
    b += edge * 0.10f;

    r *= vignette;
    g *= vignette;
    b *= vignette;

    out[p + 0] = fminf(fmaxf(r, 0.0f), 1.0f);
    out[p + 1] = fminf(fmaxf(g, 0.0f), 1.0f);
    out[p + 2] = fminf(fmaxf(b, 0.0f), 1.0f);

    if (channels == 4)
        out[p + 3] = in[p + 3];
}`,
  },
  comic_ink_2d: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels)
{
    int x = blockDim.x * blockIdx.x + threadIdx.x;
    int y = blockDim.y * blockIdx.y + threadIdx.y;
    if (x >= width || y >= height) return;

    int i = y * width + x;
    int p = i * channels;

    int xl = x > 0 ? x - 1 : 0;
    int xr = x + 1 < width ? x + 1 : width - 1;
    int yu = y > 0 ? y - 1 : 0;
    int yd = y + 1 < height ? y + 1 : height - 1;

    int pl = (y * width + xl) * channels;
    int pr = (y * width + xr) * channels;
    int pu = (yu * width + x) * channels;
    int pd = (yd * width + x) * channels;

    float lumL = 0.299f * in[pl] + 0.587f * in[pl + 1] + 0.114f * in[pl + 2];
    float lumR = 0.299f * in[pr] + 0.587f * in[pr + 1] + 0.114f * in[pr + 2];
    float lumU = 0.299f * in[pu] + 0.587f * in[pu + 1] + 0.114f * in[pu + 2];
    float lumD = 0.299f * in[pd] + 0.587f * in[pd + 1] + 0.114f * in[pd + 2];
    float edge = fminf((fabsf(lumR - lumL) + fabsf(lumD - lumU)) * 5.5f, 1.0f);

    float levels = 5.0f;
    float r = floorf(in[p + 0] * levels) / levels;
    float g = floorf(in[p + 1] * levels) / levels;
    float b = floorf(in[p + 2] * levels) / levels;

    r = powf(fminf(r * 1.22f, 1.0f), 0.82f);
    g = powf(fminf(g * 1.12f, 1.0f), 0.86f);
    b = powf(fminf(b * 1.05f, 1.0f), 0.90f);

    float ink = 1.0f - fminf(edge * 0.9f, 0.9f);
    out[p + 0] = r * ink;
    out[p + 1] = g * ink;
    out[p + 2] = b * ink;

    if (channels == 4)
        out[p + 3] = in[p + 3];
}`,
  },
  thermal_vision: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels)
{
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int p = i * channels;
    float lum = 0.299f * in[p + 0] + 0.587f * in[p + 1] + 0.114f * in[p + 2];
    float hotT = fminf(fmaxf((lum - 0.50f) / 0.50f, 0.0f), 1.0f);
    float hot = hotT * hotT * (3.0f - 2.0f * hotT);
    float mid = 1.0f - fabsf(lum - 0.52f) * 2.1f;
    mid = fminf(fmaxf(mid, 0.0f), 1.0f);
    float coldT = fminf(fmaxf((lum - 0.10f) / 0.65f, 0.0f), 1.0f);
    float cold = 1.0f - coldT * coldT * (3.0f - 2.0f * coldT);

    out[p + 0] = fminf(fmaxf(hot * 1.15f + mid * 0.65f, 0.0f), 1.0f);
    out[p + 1] = fminf(fmaxf(mid * 1.05f + cold * 0.15f, 0.0f), 1.0f);
    out[p + 2] = fminf(fmaxf(cold * 0.95f + (1.0f - hot) * 0.20f, 0.0f), 1.0f);

    if (channels == 4)
        out[p + 3] = in[p + 3];
}`,
  },
  dream_glow_2d: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels)
{
    int x = blockDim.x * blockIdx.x + threadIdx.x;
    int y = blockDim.y * blockIdx.y + threadIdx.y;
    if (x >= width || y >= height) return;

    int i = y * width + x;
    int p = i * channels;

    int xl = x > 0 ? x - 1 : 0;
    int xr = x + 1 < width ? x + 1 : width - 1;
    int yu = y > 0 ? y - 1 : 0;
    int yd = y + 1 < height ? y + 1 : height - 1;

    int pl = (y * width + xl) * channels;
    int pr = (y * width + xr) * channels;
    int pu = (yu * width + x) * channels;
    int pd = (yd * width + x) * channels;

    float blurR = (in[p + 0] * 4.0f + in[pl] + in[pr] + in[pu] + in[pd]) * 0.125f;
    float blurG = (in[p + 1] * 4.0f + in[pl + 1] + in[pr + 1] + in[pu + 1] + in[pd + 1]) * 0.125f;
    float blurB = (in[p + 2] * 4.0f + in[pl + 2] + in[pr + 2] + in[pu + 2] + in[pd + 2]) * 0.125f;

    float r = in[p + 0] * 0.70f + blurR * 0.45f + 0.04f;
    float g = in[p + 1] * 0.70f + blurG * 0.38f + 0.03f;
    float b = in[p + 2] * 0.72f + blurB * 0.50f + 0.08f;

    out[p + 0] = fminf(fmaxf(powf(r, 0.82f), 0.0f), 1.0f);
    out[p + 1] = fminf(fmaxf(powf(g, 0.86f), 0.0f), 1.0f);
    out[p + 2] = fminf(fmaxf(powf(b, 0.78f), 0.0f), 1.0f);

    if (channels == 4)
        out[p + 3] = in[p + 3];
}`,
  },
  grayscale: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int p = i * channels;
    float y = in[p + 0] * 0.2126f + in[p + 1] * 0.7152f + in[p + 2] * 0.0722f;
    out[p + 0] = y;
    out[p + 1] = y;
    out[p + 2] = y;
}`,
  },
  channel_swap: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int p = i * channels;
    out[p + 0] = in[p + 2];
    out[p + 1] = in[p + 1];
    out[p + 2] = in[p + 0];
}`,
  },
  vignette: {
    signature: 'image_rgb',
    output_mode: 'image',
    code: `extern "C" __global__
void user_kernel(const float* in, float* out, int width, int height, int channels) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    int n = width * height;
    if (i >= n) return;

    int x = i % width;
    int y = i / width;
    float nx = (x / (float)width) * 2.0f - 1.0f;
    float ny = (y / (float)height) * 2.0f - 1.0f;
    float dist = sqrtf(nx * nx + ny * ny);
    float v = 1.0f - fminf(dist * 0.45f, 0.55f);

    int p = i * channels;
    out[p + 0] = in[p + 0] * v;
    out[p + 1] = in[p + 1] * v;
    out[p + 2] = in[p + 2] * v;
}`,
  },
}

const formatFloat = (v: unknown): string => {
  const n = parseFloat(String(v))
  if (isNaN(n)) return '0.0'
  return Number.isInteger(n) ? `${n}.0` : String(n)
}

export const isImageDataUrl = (v: unknown): v is string =>
  typeof v === 'string' && v.startsWith('data:image/')

const ICON_PARAMS = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <line x1="3" y1="5"  x2="15" y2="5"  stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    <circle cx="7"  cy="5"  r="2" fill="var(--panel)" stroke="currentColor" strokeWidth="1.3"/>
    <line x1="3" y1="9"  x2="15" y2="9"  stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    <circle cx="11" cy="9"  r="2" fill="var(--panel)" stroke="currentColor" strokeWidth="1.3"/>
    <line x1="3" y1="13" x2="15" y2="13" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    <circle cx="6"  cy="13" r="2" fill="var(--panel)" stroke="currentColor" strokeWidth="1.3"/>
  </svg>
)

export default function Inspector() {
  const { nodes, edges, nodeDefs, selectedId, updateParam, cookNode, stopCook, removeNode } = useStore()
  const node = nodes.find(n => n.id === selectedId)

  const [open, setOpen]             = useState(true)
  const [panelWidth, setPanelWidth] = useState(PANEL_DEFAULT_W)
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startW: panelWidth }
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      // dragging left = wider (right panel resizes from left edge)
      const next = dragRef.current.startW - (ev.clientX - dragRef.current.startX)
      setPanelWidth(Math.max(PANEL_MIN_W, Math.min(PANEL_MAX_W, next)))
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const panelContent = (() => {
    if (!node) {
      return (
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--tx3)', fontSize: 13,
        }}>
          Select a node
        </div>
      )
    }

    const { data } = node
    const connectedPorts = new Set(
      edges.filter(e => e.target === node.id).map(e => e.targetHandle).filter(Boolean)
    )
    const visibleInputs = data.inputs

    return (
      <>
        {/* header */}
        <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid var(--line)', flexShrink: 0 }}>
          <div style={{ color: 'var(--tx1)', fontWeight: 600, fontSize: 15, marginBottom: 4 }}>
            {data.type}
          </div>
          <div style={{ color: 'var(--tx2)', fontSize: 12, fontFamily: 'var(--font-mono)', letterSpacing: '0.03em' }}>
            {data.id.slice(0, 14)}…
          </div>
        </div>

        {/* params */}
        <div style={{ padding: '12px 16px', flex: 1, overflowY: 'auto' }}>
          {visibleInputs.length > 0 ? (
            <>
              <div style={{
                color: 'var(--tx2)', fontSize: 12, fontWeight: 700,
                letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10,
              }}>
                Parameters
              </div>
              {visibleInputs.map(inp => {
                const type = (data.input_types as Record<string, string>)?.[inp] ?? 'Any'
                const def  = (data.input_defaults as Record<string, unknown>)?.[inp]
                          ?? nodeDefs[data.type]?.input_defaults?.[inp]
                const choices = nodeDefs[data.type]?.input_choices?.[inp]
                const changeParam = (v: unknown) => {
                  if (data.type === 'CUDACustomKernel' && inp === 'template') {
                    void (async () => {
                      const name = String(v)
                      await updateParam(node.id, inp, name)
                      const preset = CUSTOM_KERNEL_TEMPLATE_PRESETS[name]
                      if (!preset) return
                      await updateParam(node.id, 'code', preset.code)
                      await updateParam(node.id, 'signature', preset.signature)
                      await updateParam(node.id, 'output_mode', preset.output_mode)
                    })()
                    return
                  }
                  if (data.type === 'CUDACustomKernel' && inp === 'code') {
                    void (async () => {
                      await updateParam(node.id, inp, v)
                      const activeTemplate = String(
                        data.params.template
                        ?? data.input_defaults?.template
                        ?? nodeDefs[data.type]?.input_defaults?.template
                        ?? 'custom'
                      )
                      if (activeTemplate !== 'custom') {
                        await updateParam(node.id, 'template', 'custom')
                      }
                    })()
                    return
                  }
                  void updateParam(node.id, inp, v)
                }
                return (
                  <ParamRow
                    key={`${node.id}-${inp}`}
                    label={inp}
                    type={type}
                    value={data.params[inp]}
                    defaultValue={def}
                    choices={choices}
                    connected={connectedPorts.has(inp)}
                    onChange={changeParam}
                  />
                )
              })}
            </>
          ) : (
            <div style={{ color: 'var(--tx2)', fontSize: 13 }}>
              {data.type === 'ToolBox' ? 'No tools connected' : 'No inputs'}
            </div>
          )}
        </div>

        {/* cook result */}
        {(data.cookResult !== undefined || data.cookError) && (
          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--line)', flexShrink: 0 }}>
            <div style={{
              color: 'var(--tx3)', fontSize: 11, fontWeight: 600,
              letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8,
            }}>
              Result
            </div>
            {!data.cookError && isImageDataUrl(data.cookResult) ? (
              <img
                src={data.cookResult as string}
                alt="result"
                style={{
                  maxWidth: '100%', borderRadius: 6,
                  border: '1px solid var(--line2)', background: 'var(--lift)',
                  imageRendering: 'auto', display: 'block',
                }}
              />
            ) : (
              <pre style={{
                background: 'var(--lift)',
                border: `1px solid ${data.cookError ? 'var(--err)' : 'var(--line2)'}`,
                borderRadius: 6, padding: '8px 10px',
                color: data.cookError ? 'var(--err)' : 'var(--ok)',
                fontSize: 12, fontFamily: 'var(--font-mono)',
                whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                maxHeight: 200, overflowY: 'auto', margin: 0,
              }}>
                {data.cookError
                  ? data.cookError
                  : typeof data.cookResult === 'object'
                    ? JSON.stringify(data.cookResult, null, 2)
                    : String(data.cookResult)}
              </pre>
            )}
          </div>
        )}

        {/* actions */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--line)', display: 'flex', gap: 8, flexShrink: 0 }}>
          {data.cooking ? (
            <button
              onClick={() => stopCook()}
              style={btnStyle('var(--err)', true)}
            >
              ■  Stop
            </button>
          ) : (
            <button
              onClick={() => cookNode(node.id, data.outputs[0] ?? 'output')}
              style={btnStyle('var(--accent)', true)}
            >
              ▶  Cook
            </button>
          )}
          <button
            onClick={() => removeNode(node.id)}
            style={btnStyle('var(--err)', false)}
          >
            Delete
          </button>
        </div>
      </>
    )
  })()

  return (
    <div style={{ display: 'flex', flexShrink: 0, height: '100%' }}>

      {/* ── Content panel ── */}
      {open && (
        <div style={{
          width: panelWidth,
          background: 'var(--panel)',
          borderLeft: '1px solid var(--line)',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          position: 'relative',
          overflow: 'hidden',
        }}>
          {/* resize handle at left edge */}
          <div
            onMouseDown={startResize}
            style={{ position: 'absolute', left: -2, top: 0, bottom: 0, width: 4, cursor: 'col-resize', zIndex: 5 }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--accent)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          />
          {/* panel title */}
          <div style={{
            height: TOP_BAR_H, padding: '0 14px',
            borderBottom: '1px solid var(--line)',
            display: 'flex', alignItems: 'center', flexShrink: 0,
          }}>
            <span style={{
              fontSize: 11, fontWeight: 700, fontFamily: 'var(--font-ui)',
              letterSpacing: 0, textTransform: 'uppercase', color: 'var(--tx2)',
            }}>
              Properties
            </span>
          </div>
          {panelContent}
        </div>
      )}

      {/* ── Icon rail ── */}
      <div style={{
        width: RAIL_W,
        background: 'var(--panel)',
        borderLeft: '1px solid var(--line)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        flexShrink: 0,
      }}>
        {/* logo area matching left rail */}
        <div style={{
          height: TOP_BAR_H, borderBottom: '1px solid var(--line)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }} />

        {/* Parameters tab button */}
        <button
          onClick={() => setOpen(o => !o)}
          title="Properties"
          style={{
            width: '100%', height: 50,
            background: open ? 'var(--menu-active)' : 'transparent',
            border: 'none', borderRadius: 0,
            color: open ? 'var(--tx1)' : 'var(--tx3)',
            cursor: 'pointer',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 3,
            padding: '0 4px',
            boxShadow: open ? 'inset -3px 0 0 var(--accent)' : 'none',
            transition: 'color 0.13s, background 0.13s',
          }}
          onMouseEnter={e => {
            if (!open) {
              e.currentTarget.style.background = 'var(--menu-hover)'
              e.currentTarget.style.color = 'var(--tx1)'
            }
          }}
          onMouseLeave={e => {
            if (!open) {
              e.currentTarget.style.background = 'transparent'
              e.currentTarget.style.color = 'var(--tx3)'
            }
          }}
        >
          {ICON_PARAMS}
          <span style={{
            fontSize: 9, fontFamily: 'var(--font-ui)',
            fontWeight: open ? 700 : 500, userSelect: 'none', lineHeight: 1.1,
          }}>
            Properties
          </span>
        </button>
      </div>
    </div>
  )
}

function ParamRow({ label, type, value, defaultValue, choices, connected, onChange }: {
  label: string
  type: string
  value: unknown
  defaultValue: unknown
  choices?: string[]
  connected: boolean
  onChange: (v: unknown) => void
}) {
  const color = portColor(type)
  const wireOnly = WIRE_ONLY.has(type)

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ color: 'var(--tx1)', fontSize: 12, fontWeight: 500, textTransform: 'capitalize' }}>
          {label}
        </span>
        <span style={{
          fontSize: 10,
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          color,
          background: `${color}22`,
          borderRadius: 4,
          padding: '1px 5px',
          letterSpacing: '0.02em',
        }}>
          {type}
        </span>
      </div>

      {connected ? (
        <div style={{
          background: 'var(--lift)',
          border: `1px solid ${color}44`,
          borderRadius: 6,
          padding: '5px 8px',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          color: 'var(--tx3)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          minHeight: 28,
          opacity: 0.7,
        }}>
          <span style={{ color, fontSize: 8 }}>●</span>
          connected
        </div>
      ) : wireOnly ? (
        <div style={{
          background: 'var(--lift)',
          border: '1px dashed var(--line2)',
          borderRadius: 6,
          padding: '5px 8px',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          color: 'var(--tx3)',
          minHeight: 28,
          display: 'flex',
          alignItems: 'center',
        }}>
          ← connect a wire
        </div>
      ) : type === 'Image' ? (
        <ImageControl value={value} onChange={onChange} />
      ) : choices && choices.length > 0 ? (
        <EnumControl value={value} defaultValue={defaultValue} choices={choices} onChange={onChange} />
      ) : type === 'Bool' ? (
        <BoolControl value={value} onChange={onChange} />
      ) : type === 'Int' ? (
        <IntControl value={value} defaultValue={defaultValue} onChange={onChange} />
      ) : type === 'Float' ? (
        <FloatControl value={value} defaultValue={defaultValue} onChange={onChange} />
      ) : label === 'code' ? (
        <CodeControl value={value} defaultValue={defaultValue} onChange={onChange} />
      ) : (
        <TextControl value={value} defaultValue={defaultValue} onChange={onChange} multiline={type !== 'Model'} />
      )}
    </div>
  )
}

function ImageControl({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const current = typeof value === 'string' ? value : ''
  const isImg = isImageDataUrl(current)
  const [draft, setDraft] = useState(isImg ? '' : current)
  useEffect(() => { setDraft(isImageDataUrl(current) ? '' : current) }, [current])

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => onChange(String(reader.result))
    reader.readAsDataURL(file)
    e.target.value = ''
  }

  const btn: React.CSSProperties = {
    background: 'var(--lift)', border: '1px solid var(--line)', borderRadius: 6,
    color: 'var(--tx1)', fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 600,
    padding: '5px 10px', cursor: 'pointer',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <button type="button" style={btn} onClick={() => fileRef.current?.click()}>Browse…</button>
        {current && (
          <button type="button" style={{ ...btn, color: 'var(--err)' }} onClick={() => onChange('')}>Clear</button>
        )}
        <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={onPick} />
      </div>
      {isImg ? (
        <img
          src={current}
          alt="preview"
          style={{ maxWidth: '100%', borderRadius: 6, border: '1px solid var(--line2)', background: 'var(--lift)', display: 'block' }}
        />
      ) : (
        <input
          type="text"
          value={draft}
          placeholder="or paste a file path"
          onChange={e => setDraft(e.target.value)}
          onBlur={() => onChange(draft)}
          style={{
            background: 'var(--lift)', border: '1px solid var(--line)', borderRadius: 6,
            color: 'var(--tx1)', fontFamily: 'var(--font-mono)', fontSize: 12,
            padding: '5px 8px', outline: 'none', minHeight: 28,
          }}
        />
      )}
    </div>
  )
}

function EnumControl({ value, defaultValue, choices, onChange }: {
  value: unknown; defaultValue: unknown; choices: string[]; onChange: (v: unknown) => void
}) {
  const current = value !== undefined && value !== null ? String(value)
    : defaultValue !== undefined && defaultValue !== null ? String(defaultValue)
    : choices[0]
  const color = portColor('Text')
  return (
    <select
      value={current}
      onChange={e => onChange(e.target.value)}
      style={{
        width: '100%',
        background: 'var(--lift)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        padding: '5px 8px',
        minHeight: 28,
        color: 'var(--tx1)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        fontWeight: 600,
        outline: 'none',
        cursor: 'pointer',
        borderLeft: `2px solid ${color}`,
      }}
    >
      {choices.map(opt => (
        <option key={opt} value={opt}>{opt}</option>
      ))}
    </select>
  )
}

function BoolControl({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const on = Boolean(value)
  const color = portColor('Bool')
  return (
    <div
      onClick={() => onChange(!on)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'var(--lift)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        padding: '5px 8px',
        cursor: 'pointer',
        minHeight: 28,
      }}
    >
      <div style={{
        width: 30, height: 16, borderRadius: 8, position: 'relative', flexShrink: 0,
        background: on ? color : 'var(--line2)', transition: 'background .15s',
      }}>
        <div style={{
          position: 'absolute', top: 2, left: on ? 16 : 2,
          width: 12, height: 12, borderRadius: '50%', background: '#fff',
          transition: 'left .15s', boxShadow: '0 1px 3px rgba(0,0,0,.3)',
        }} />
      </div>
      <span style={{
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        fontWeight: 600,
        color: on ? color : 'var(--tx2)',
      }}>
        {on ? 'true' : 'false'}
      </span>
    </div>
  )
}

function IntControl({ value, defaultValue, onChange }: { value: unknown; defaultValue: unknown; onChange: (v: unknown) => void }) {
  const resolve = (v: unknown) =>
    v !== undefined && v !== null ? String(Number(v))
    : defaultValue !== undefined && defaultValue !== null ? String(Number(defaultValue))
    : ''

  const [draft, setDraft] = useState<string>(() => resolve(value))

  useEffect(() => { setDraft(resolve(value)) }, [value, defaultValue])

  const commit = (raw: string) => {
    const v = parseInt(raw)
    if (!isNaN(v)) onChange(v)
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 2,
      background: 'var(--lift)', border: '1px solid var(--line)', borderRadius: 6,
      padding: '4px 8px', minHeight: 28,
    }}>
      <input
        type="text"
        inputMode="numeric"
        value={draft}
        onChange={e => {
          const raw = e.target.value.replace(/[^-\d]/g, '')
          setDraft(raw)
          if (raw !== '') {
            const v = parseInt(raw)
            if (!isNaN(v)) onChange(v)
          }
        }}
        onBlur={() => commit(draft)}
        style={{
          flex: 1, background: 'transparent', border: 'none',
          color: 'var(--tx1)', fontFamily: 'var(--font-mono)',
          fontSize: 12, fontWeight: 600, outline: 'none', minWidth: 0,
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        {([['▲', 1], ['▼', -1]] as const).map(([label, delta]) => (
          <button
            key={label}
            onClick={() => {
              const v = (parseInt(draft) || 0) + delta
              setDraft(String(v))
              onChange(v)
            }}
            style={{
              background: 'transparent', border: 'none', color: 'var(--tx2)',
              cursor: 'pointer', fontSize: 7, lineHeight: 1.3, padding: '0 2px',
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function FloatControl({ value, defaultValue, onChange }: { value: unknown; defaultValue: unknown; onChange: (v: unknown) => void }) {
  const resolve = (v: unknown) =>
    v !== undefined && v !== null ? formatFloat(v)
    : defaultValue !== undefined && defaultValue !== null ? formatFloat(defaultValue)
    : ''

  const [draft, setDraft] = useState<string>(() => resolve(value))

  useEffect(() => { setDraft(resolve(value)) }, [value, defaultValue])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 2,
      background: 'var(--lift)', border: '1px solid var(--line)', borderRadius: 6,
      padding: '4px 8px', minHeight: 28,
    }}>
      <input
        type="text"
        inputMode="decimal"
        value={draft}
        onChange={e => {
          setDraft(e.target.value)
          const v = parseFloat(e.target.value)
          if (!isNaN(v)) onChange(v)
        }}
        onBlur={() => {
          if (draft === '') { onChange(undefined); return }
          const v = parseFloat(draft)
          if (!isNaN(v)) { setDraft(formatFloat(v)); onChange(v) }
          else setDraft('')
        }}
        style={{
          flex: 1, background: 'transparent', border: 'none',
          color: 'var(--tx1)', fontFamily: 'var(--font-mono)',
          fontSize: 12, fontWeight: 600, outline: 'none', minWidth: 0,
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        {([['▲', 1], ['▼', -1]] as const).map(([label, delta]) => (
          <button
            key={label}
            onClick={() => {
              const v = (parseFloat(draft) || 0) + delta
              setDraft(formatFloat(v))
              onChange(v)
            }}
            style={{
              background: 'transparent', border: 'none', color: 'var(--tx2)',
              cursor: 'pointer', fontSize: 7, lineHeight: 1.3, padding: '0 2px',
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function TextControl({ value, defaultValue, onChange, multiline }: {
  value: unknown
  defaultValue: unknown
  onChange: (v: unknown) => void
  multiline: boolean
}) {
  const resolve = (v: unknown) =>
    v !== undefined && v !== null && v !== '' ? String(v)
    : defaultValue !== undefined && defaultValue !== null ? String(defaultValue)
    : ''

  const [draft, setDraft] = useState(() => resolve(value))

  useEffect(() => { setDraft(resolve(value)) }, [value, defaultValue])

  const commit = () => onChange(draft)
  const sharedStyle: React.CSSProperties = {
    width: '100%',
    background: 'var(--lift)',
    border: '1px solid var(--line)',
    borderRadius: 6,
    color: 'var(--tx1)',
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    padding: '5px 8px',
    outline: 'none',
    boxSizing: 'border-box',
  }

  const placeholder = defaultValue !== undefined ? String(defaultValue) : undefined

  return multiline ? (
    <textarea
      value={draft}
      placeholder={placeholder}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit() } }}
      rows={3}
      style={{ ...sharedStyle, resize: 'vertical' }}
    />
  ) : (
    <input
      type="text"
      value={draft}
      placeholder={placeholder}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); commit() } }}
      style={sharedStyle}
    />
  )
}

function CodeControl({ value, defaultValue, onChange }: {
  value: unknown
  defaultValue: unknown
  onChange: (v: unknown) => void
}) {
  const resolve = (v: unknown) =>
    v !== undefined && v !== null && v !== '' ? String(v)
    : defaultValue !== undefined && defaultValue !== null ? String(defaultValue)
    : ''

  const [draft, setDraft] = useState(() => resolve(value))
  const taRef = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { setDraft(resolve(value)) }, [value, defaultValue])

  return (
    <textarea
      ref={taRef}
      value={draft}
      placeholder={'def run(x: str) -> str:\n    return x'}
      onChange={e => setDraft(e.target.value)}
      onBlur={() => onChange(draft)}
      onKeyDown={e => {
        if (e.key === 'Tab') {
          e.preventDefault()
          const ta = taRef.current
          if (!ta) return
          const start = ta.selectionStart
          const end   = ta.selectionEnd
          const next = draft.slice(0, start) + '    ' + draft.slice(end)
          setDraft(next)
          requestAnimationFrame(() => {
            if (taRef.current) {
              taRef.current.selectionStart = start + 4
              taRef.current.selectionEnd   = start + 4
            }
          })
        }
      }}
      rows={8}
      spellCheck={false}
      style={{
        width: '100%',
        background: 'var(--lift)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        color: 'var(--tx1)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        lineHeight: 1.65,
        padding: '6px 8px',
        outline: 'none',
        boxSizing: 'border-box',
        resize: 'vertical',
        tabSize: 4,
      }}
    />
  )
}

function btnStyle(color: string, primary: boolean): React.CSSProperties {
  return {
    flex: 1,
    padding: '7px 12px',
    border: `1px solid ${color}`,
    borderRadius: 6,
    background: primary ? color : 'transparent',
    color: primary ? '#fff' : color,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    fontFamily: 'var(--font-ui)',
    transition: 'opacity 0.15s',
  }
}
