import { useEffect, useState } from 'react'
import { api, type LearnedNodeSummary } from '../api'
import { useStore } from '../store'

export default function LearnedNodesPanel() {
  const { learnedNodes, loadLearnedNodes, loadNodeTypes } = useStore()
  const [source, setSource] = useState<{ name: string; body: string } | null>(null)
  const [error, setError] = useState('')
  const [busyName, setBusyName] = useState('')

  useEffect(() => {
    void loadLearnedNodes()
  }, [loadLearnedNodes])

  const viewSource = async (node: LearnedNodeSummary) => {
    setError('')
    setBusyName(node.name)
    try {
      const result = await api.getLearnedNodeSource(node.name)
      setSource({ name: node.name, body: result.source })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyName('')
    }
  }

  const deleteNode = async (node: LearnedNodeSummary) => {
    if (!window.confirm(`Delete learned node ${node.name}?`)) return
    setError('')
    setBusyName(node.name)
    try {
      await api.deleteLearnedNode(node.name)
      await Promise.all([loadLearnedNodes(), loadNodeTypes()])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyName('')
    }
  }

  return (
    <div className="bn-learned-panel">
      <div className="bn-learned-toolbar">
        <button className="bn-top-button" onClick={() => void loadLearnedNodes()}>
          Refresh
        </button>
      </div>

      {error && <div className="bn-learned-error">{error}</div>}

      <div className="bn-learned-list">
        {learnedNodes.length === 0 ? (
          <div className="bn-learned-empty">No learned nodes found.</div>
        ) : learnedNodes.map(node => (
          <div className="bn-learned-row" key={node.name}>
            <div className="bn-learned-row-head">
              <div className="bn-learned-name">{node.name}</div>
              <span className={node.permissions.network ? 'bn-learned-perm is-network' : 'bn-learned-perm'}>
                {node.permissions.network ? 'network' : 'no network'}
              </span>
            </div>
            <div className="bn-learned-desc">{node.description}</div>
            <div className="bn-learned-meta">
              <span>{formatDate(node.created_at)}</span>
              <span>{node.inputs.length} in</span>
              <span>{node.outputs.length} out</span>
            </div>
            <div className="bn-learned-actions">
              <button
                className="bn-top-button"
                disabled={busyName === node.name}
                onClick={() => void viewSource(node)}
              >
                View source
              </button>
              <button
                className="bn-top-button"
                disabled={busyName === node.name}
                onClick={() => void deleteNode(node)}
                style={{ borderColor: 'var(--err)', color: 'var(--err)' }}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {source && (
        <div className="bn-learned-modal" role="dialog" aria-modal="true" aria-labelledby="learned-source-title">
          <div className="bn-learned-source">
            <div className="bn-learned-source-head">
              <div id="learned-source-title">{source.name}</div>
              <button className="bn-top-button" onClick={() => setSource(null)}>Close</button>
            </div>
            <pre>{source.body}</pre>
          </div>
        </div>
      )}
    </div>
  )
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

