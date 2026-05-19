import { useStore } from '../store'

export default function SubnetBreadcrumb() {
  const { subnetStack, exitSubnet, exitToRoot } = useStore()

  if (subnetStack.length === 0) return null

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '0 14px',
      background: '#3730a3',
      borderBottom: '1px solid #4338ca',
      fontSize: 12,
      color: '#c7d2fe',
      flexShrink: 0,
      height: 32,
      zIndex: 15,
      position: 'relative',
    }}>
      {/* Exit button */}
      <button
        onClick={exitSubnet}
        title="Exit subnet (Escape)"
        style={{
          background: 'rgba(255,255,255,0.12)',
          border: '1px solid rgba(255,255,255,0.2)',
          borderRadius: 5,
          color: '#e0e7ff',
          cursor: 'pointer',
          fontSize: 11,
          fontWeight: 600,
          padding: '2px 10px',
          fontFamily: 'var(--font-ui)',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          flexShrink: 0,
        }}
        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.22)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.12)')}
      >
        ↑ Exit
      </button>

      {/* Breadcrumb path */}
      <button
        onClick={exitToRoot}
        style={{
          background: 'none', border: 'none', color: '#a5b4fc',
          cursor: 'pointer', fontSize: 12, padding: '0 2px',
          fontFamily: 'var(--font-ui)',
        }}
        onMouseEnter={e => (e.currentTarget.style.color = '#fff')}
        onMouseLeave={e => (e.currentTarget.style.color = '#a5b4fc')}
      >
        Root
      </button>

      {subnetStack.map((frame, i) => (
        <span key={frame.subnetId} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ opacity: 0.5 }}>›</span>
          <button
            onClick={() => {
              const stepsBack = subnetStack.length - 1 - i
              for (let s = 0; s < stepsBack; s++) exitSubnet()
            }}
            style={{
              background: 'none', border: 'none',
              color: i === subnetStack.length - 1 ? '#fff' : '#a5b4fc',
              cursor: i === subnetStack.length - 1 ? 'default' : 'pointer',
              fontSize: 12,
              fontWeight: i === subnetStack.length - 1 ? 700 : 400,
              padding: '0 2px',
              fontFamily: 'var(--font-ui)',
            }}
            onMouseEnter={e => { if (i < subnetStack.length - 1) e.currentTarget.style.color = '#fff' }}
            onMouseLeave={e => { if (i < subnetStack.length - 1) e.currentTarget.style.color = '#a5b4fc' }}
          >
            {frame.subnetLabel}
          </button>
        </span>
      ))}

      <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.5 }}>Esc to exit</span>
    </div>
  )
}
