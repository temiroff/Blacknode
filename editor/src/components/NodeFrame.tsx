import type { CSSProperties, ReactNode } from 'react'
import { useStore } from '../store'
import NodeStatus from './NodeStatus'
import type { NodeCookState } from '../types'

interface NodeFrameProps {
  id: string
  data: NodeCookState
  selected: boolean
  color: string
  children: ReactNode
  style?: CSSProperties
  selectedRingAlpha?: string
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

export default function NodeFrame({
  id,
  data,
  selected,
  color,
  children,
  style,
  selectedRingAlpha = '55',
  onMouseEnter,
  onMouseLeave,
}: NodeFrameProps) {
  const selectNode = useStore(s => s.selectNode)

  return (
    <div
      onClick={() => selectNode(id)}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{
        position: 'relative',
        background: 'var(--node)',
        border: `1px solid ${selected ? color : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${color}${selectedRingAlpha}, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
        cursor: 'default',
        boxSizing: 'border-box',
        overflow: 'visible',
        ...style,
      }}
    >
      <NodeStatus data={data} />
      {children}
    </div>
  )
}
