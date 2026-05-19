import { memo, useState } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { useStore } from '../store'
import { portColor } from '../portColors'

const HEADER = '#6366f1'
const NEW_HANDLE_COLOR = '#6366f188'

interface NodeData {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  params: Record<string, unknown>
}

function SubgraphInputNode({ id, data, selected }: NodeProps<NodeData>) {
  const { updateSubgraphBoundaryPorts } = useStore()
  const edges = useStore(s => s.edges)
  const nodes = useStore(s => s.nodes)
  const [editingPort, setEditingPort] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [addingPort, setAddingPort] = useState(false)
  const [newName, setNewName] = useState('')

  const outputs: string[] = data.outputs ?? []
  const outputTypes: Record<string, string> = data.output_types ?? {}

  // Resolve effective color for "Any" outputs: adopt type of connected target's input
  const effectiveOutputColor = (port: string): string => {
    const declared = outputTypes[port] ?? 'Any'
    if (declared !== 'Any') return portColor(declared)
    const edge = edges.find(e => e.source === id && e.sourceHandle === port)
    if (edge) {
      const tgt = nodes.find(n => n.id === edge.target)
      const t = tgt?.data?.input_types?.[edge.targetHandle!] ?? 'Any'
      if (t !== 'Any') return portColor(t)
    }
    return portColor('Any')
  }

  const addPort = async () => {
    const name = newName.trim()
    if (!name || outputs.includes(name)) { setAddingPort(false); setNewName(''); return }
    const newOutputs = [...outputs, name]
    const newOutputTypes = { ...outputTypes, [name]: 'Any' }
    await updateSubgraphBoundaryPorts(id, newOutputs, undefined, newOutputTypes, undefined)
    setNewName('')
    setAddingPort(false)
  }

  const renamePort = async (oldName: string) => {
    const name = editDraft.trim()
    setEditingPort(null)
    if (!name || name === oldName) return
    const newOutputs = outputs.map(p => p === oldName ? name : p)
    const newOutputTypes: Record<string, string> = {}
    for (const [k, v] of Object.entries(outputTypes)) {
      newOutputTypes[k === oldName ? name : k] = v
    }
    await updateSubgraphBoundaryPorts(id, newOutputs, undefined, newOutputTypes, undefined)
  }

  const removePort = async (name: string) => {
    const newOutputs = outputs.filter(p => p !== name)
    const newOutputTypes = { ...outputTypes }
    delete newOutputTypes[name]
    await updateSubgraphBoundaryPorts(id, newOutputs, undefined, newOutputTypes, undefined)
  }

  return (
    <div
      style={{
        minWidth: 140,
        background: 'var(--node)',
        border: `1px solid ${selected ? HEADER : 'var(--line2)'}`,
        borderRadius: 9,
        fontSize: 12,
        color: 'var(--tx1)',
        boxShadow: selected
          ? `0 0 0 2px ${HEADER}55, 0 4px 16px rgba(0,0,0,.4)`
          : '0 2px 10px rgba(0,0,0,.25)',
      }}
    >
      {/* header */}
      <div style={{
        background: HEADER,
        borderRadius: '8px 8px 0 0',
        padding: '5px 10px',
        fontWeight: 700,
        fontSize: 11,
        color: '#fff',
        letterSpacing: '0.04em',
        display: 'flex',
        alignItems: 'center',
        gap: 5,
      }}>
        <span>⬡</span> Subnet Input
      </div>

      {/* output ports */}
      <div style={{ padding: '4px 0' }}>
        {outputs.map(port => {
          const color = effectiveOutputColor(port)
          return (
            <div
              key={port}
              style={{ position: 'relative', display: 'flex', alignItems: 'center', padding: '3px 32px 3px 10px', gap: 4 }}
              title="Double-click to rename"
            >
              {editingPort === port ? (
                <input
                  autoFocus
                  value={editDraft}
                  onChange={e => setEditDraft(e.target.value)}
                  onBlur={() => renamePort(port)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') { e.preventDefault(); renamePort(port) }
                    if (e.key === 'Escape') setEditingPort(null)
                  }}
                  onClick={e => e.stopPropagation()}
                  onMouseDown={e => e.stopPropagation()}
                  style={{
                    background: 'var(--lift)', border: `1px solid ${HEADER}`,
                    borderRadius: 4, color: 'var(--tx1)',
                    fontFamily: 'var(--font-mono)', fontSize: 11,
                    outline: 'none', padding: '1px 5px', width: 90,
                  }}
                />
              ) : (
                <span
                  onDoubleClick={e => { e.stopPropagation(); setEditingPort(port); setEditDraft(port) }}
                  style={{ fontSize: 11, color: 'var(--tx1)', fontFamily: 'var(--font-mono)', flex: 1, cursor: 'text' }}
                >
                  {port}
                </span>
              )}

              {/* remove button */}
              <button
                onClick={e => { e.stopPropagation(); removePort(port) }}
                onMouseDown={e => e.stopPropagation()}
                style={{
                  position: 'absolute', right: 6,
                  background: 'transparent', border: 'none',
                  color: 'var(--tx3)', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: '0 2px',
                  opacity: 0.5,
                }}
                onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                onMouseLeave={e => (e.currentTarget.style.opacity = '0.5')}
              >
                ×
              </button>

              <Handle
                type="source"
                position={Position.Right}
                id={port}
                style={{
                  right: -5, top: '50%',
                  background: color, width: 9, height: 9,
                  border: `1.5px solid ${color}`, borderRadius: 3,
                }}
              />
            </div>
          )
        })}

        {/* add port row */}
        <div style={{ padding: '3px 10px' }} onMouseDown={e => e.stopPropagation()}>
          {addingPort ? (
            <input
              autoFocus
              value={newName}
              placeholder="port name"
              onChange={e => setNewName(e.target.value)}
              onBlur={addPort}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); addPort() }
                if (e.key === 'Escape') { setAddingPort(false); setNewName('') }
              }}
              onClick={e => e.stopPropagation()}
              style={{
                background: 'var(--lift)', border: `1px solid ${HEADER}`,
                borderRadius: 4, color: 'var(--tx1)',
                fontFamily: 'var(--font-mono)', fontSize: 11,
                outline: 'none', padding: '2px 6px', width: 100,
              }}
            />
          ) : (
            <button
              onClick={e => { e.stopPropagation(); setAddingPort(true) }}
              style={{
                background: 'transparent', border: `1px dashed ${HEADER}88`,
                borderRadius: 4, color: HEADER, cursor: 'pointer',
                fontSize: 10, fontWeight: 600, padding: '2px 8px',
                fontFamily: 'var(--font-ui)', width: '100%', textAlign: 'center',
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = HEADER)}
              onMouseLeave={e => (e.currentTarget.style.borderColor = `${HEADER}88`)}
            >
              + Add parameter
            </button>
          )}
        </div>
      </div>

      {/* __new__ auto-create handle — drag from here to auto-add a port */}
      <div style={{
        position: 'relative', display: 'flex', justifyContent: 'flex-end',
        alignItems: 'center', padding: '2px 16px 6px 10px',
      }}>
        <span style={{ fontSize: 9, color: NEW_HANDLE_COLOR, fontFamily: 'var(--font-ui)', userSelect: 'none' }}>
          drag to create →
        </span>
        <Handle
          type="source"
          position={Position.Right}
          id="__new__"
          style={{
            right: -5,
            background: 'var(--node)',
            width: 11, height: 11,
            border: `2px dashed ${NEW_HANDLE_COLOR}`,
            borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 10, color: NEW_HANDLE_COLOR,
          }}
        />
      </div>
    </div>
  )
}

export default memo(SubgraphInputNode)
