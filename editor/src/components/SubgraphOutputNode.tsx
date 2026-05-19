import { memo, useState } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { useStore } from '../store'
import { portColor } from '../portColors'

const HEADER = '#6366f1'

interface NodeData {
  id: string
  type: string
  inputs: string[]
  outputs: string[]
  input_types: Record<string, string>
  output_types: Record<string, string>
  params: Record<string, unknown>
}

function SubgraphOutputNode({ id, data, selected }: NodeProps<NodeData>) {
  const { updateSubgraphBoundaryPorts } = useStore()
  const [editingPort, setEditingPort] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [addingPort, setAddingPort] = useState(false)
  const [newName, setNewName] = useState('')

  const inputs: string[] = data.inputs ?? []
  const inputTypes: Record<string, string> = data.input_types ?? {}

  const addPort = async () => {
    const name = newName.trim()
    if (!name || inputs.includes(name)) { setAddingPort(false); setNewName(''); return }
    const newInputs = [...inputs, name]
    const newInputTypes = { ...inputTypes, [name]: 'Any' }
    await updateSubgraphBoundaryPorts(id, undefined, newInputs, undefined, newInputTypes)
    setNewName('')
    setAddingPort(false)
  }

  const renamePort = async (oldName: string) => {
    const name = editDraft.trim()
    setEditingPort(null)
    if (!name || name === oldName) return
    const newInputs = inputs.map(p => p === oldName ? name : p)
    const newInputTypes: Record<string, string> = {}
    for (const [k, v] of Object.entries(inputTypes)) {
      newInputTypes[k === oldName ? name : k] = v
    }
    await updateSubgraphBoundaryPorts(id, undefined, newInputs, undefined, newInputTypes)
  }

  const removePort = async (name: string) => {
    const newInputs = inputs.filter(p => p !== name)
    const newInputTypes = { ...inputTypes }
    delete newInputTypes[name]
    await updateSubgraphBoundaryPorts(id, undefined, newInputs, undefined, newInputTypes)
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
        <span>⬡</span> Subnet Output
      </div>

      {/* input ports */}
      <div style={{ padding: '4px 0' }}>
        {inputs.map(port => {
          const color = portColor(inputTypes[port] ?? 'Any')
          return (
            <div
              key={port}
              style={{ position: 'relative', display: 'flex', alignItems: 'center', padding: '3px 10px 3px 32px', gap: 4 }}
              title="Double-click to rename"
            >
              <Handle
                type="target"
                position={Position.Left}
                id={port}
                style={{
                  left: -5, top: '50%',
                  background: color, width: 9, height: 9,
                  border: `1.5px solid ${color}`, borderRadius: 3,
                }}
              />

              {/* remove button */}
              <button
                onClick={e => { e.stopPropagation(); removePort(port) }}
                onMouseDown={e => e.stopPropagation()}
                style={{
                  position: 'absolute', left: 6,
                  background: 'transparent', border: 'none',
                  color: 'var(--tx3)', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: '0 2px',
                  opacity: 0.5,
                }}
                onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                onMouseLeave={e => (e.currentTarget.style.opacity = '0.5')}
              >
                ×
              </button>

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
                  style={{ fontSize: 11, color: 'var(--tx1)', fontFamily: 'var(--font-mono)', textAlign: 'right', flex: 1, cursor: 'text' }}
                >
                  {port}
                </span>
              )}
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
              + Add output
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default memo(SubgraphOutputNode)
