import { useStore } from '../store'

export default function SubnetBreadcrumb() {
  const { subnetStack, exitSubnet, exitToRoot } = useStore()

  if (subnetStack.length === 0) return null

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 4,
      padding: '4px 14px',
      background: 'var(--panel)',
      borderBottom: '1px solid var(--line)',
      fontSize: 12,
      color: 'var(--tx2)',
      flexShrink: 0,
    }}>
      <button
        onClick={exitToRoot}
        style={{
          background: 'none', border: 'none', color: 'var(--accent)',
          cursor: 'pointer', fontSize: 12, padding: '0 2px',
        }}
      >
        Root
      </button>
      {subnetStack.map((frame, i) => (
        <span key={frame.subnetId} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ opacity: 0.4 }}>›</span>
          <button
            onClick={() => {
              const stepsBack = subnetStack.length - 1 - i
              for (let s = 0; s < stepsBack; s++) exitSubnet()
            }}
            style={{
              background: 'none', border: 'none',
              color: i === subnetStack.length - 1 ? 'var(--tx1)' : 'var(--accent)',
              cursor: i === subnetStack.length - 1 ? 'default' : 'pointer',
              fontSize: 12, fontWeight: i === subnetStack.length - 1 ? 600 : 400,
              padding: '0 2px',
            }}
          >
            {frame.subnetLabel}
          </button>
        </span>
      ))}
    </div>
  )
}
