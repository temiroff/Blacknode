import { useCallback, useEffect, useRef, useState } from 'react'

import { api, type FileBrowserListing } from '../api'

interface LocalFilePickerProps {
  title: string
  initialPath: string
  extensions: string[]
  onSelect: (path: string) => void
  onCancel: () => void
}

function formatSize(size: number | null): string {
  if (size === null) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

export default function LocalFilePicker({
  title,
  initialPath,
  extensions,
  onSelect,
  onCancel,
}: LocalFilePickerProps) {
  const [listing, setListing] = useState<FileBrowserListing | null>(null)
  const [pathDraft, setPathDraft] = useState(initialPath)
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const requestSequence = useRef(0)

  const openDirectory = useCallback(async (path: string) => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setError('')
    try {
      const next = await api.browseFiles(path, extensions)
      if (sequence !== requestSequence.current) return
      setListing(next)
      setPathDraft(next.path)
      setSelected(next.selected)
    } catch (reason) {
      if (sequence !== requestSequence.current) return
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      if (sequence === requestSequence.current) setLoading(false)
    }
  }, [extensions])

  useEffect(() => {
    void openDirectory(initialPath)
  }, [initialPath, openDirectory])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onCancel])

  return (
    <div
      className="bn-local-file-picker-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="bn-local-file-picker-title"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onCancel()
        event.stopPropagation()
      }}
    >
      <section className="bn-local-file-picker">
        <header>
          <div>
            <strong id="bn-local-file-picker-title">{title}</strong>
            <span>Select a local {extensions.join(', ')} scene</span>
          </div>
          <button type="button" onClick={onCancel} aria-label="Close file browser">×</button>
        </header>

        <div className="bn-local-file-picker-location">
          <button
            type="button"
            onClick={() => listing?.parent && void openDirectory(listing.parent)}
            disabled={!listing?.parent || loading}
            title="Parent folder"
          >
            ↑ Up
          </button>
          <input
            autoFocus
            value={pathDraft}
            onChange={event => setPathDraft(event.target.value)}
            onKeyDown={event => {
              if (event.key !== 'Enter') return
              event.preventDefault()
              void openDirectory(pathDraft)
            }}
            aria-label="Folder path"
          />
          <button type="button" onClick={() => void openDirectory(pathDraft)} disabled={loading}>
            Go
          </button>
        </div>

        {listing && listing.roots.length > 1 && (
          <nav className="bn-local-file-picker-roots" aria-label="Filesystem drives">
            {listing.roots.map(root => (
              <button type="button" key={root} onClick={() => void openDirectory(root)}>{root}</button>
            ))}
          </nav>
        )}

        <div className="bn-local-file-picker-list" role="listbox" aria-label="Files and folders">
          {loading && <div className="bn-local-file-picker-message">Opening folder…</div>}
          {!loading && error && <div className="bn-local-file-picker-message is-error">{error}</div>}
          {!loading && !error && listing?.entries.length === 0 && (
            <div className="bn-local-file-picker-message">No matching USD files or folders here.</div>
          )}
          {!loading && !error && listing?.entries.map(entry => (
            <button
              type="button"
              role="option"
              aria-selected={!entry.is_directory && selected === entry.path}
              className={`${entry.is_directory ? 'is-directory' : 'is-file'}${selected === entry.path ? ' is-selected' : ''}`}
              key={entry.path}
              onClick={() => {
                if (entry.is_directory) void openDirectory(entry.path)
                else setSelected(entry.path)
              }}
              onDoubleClick={() => {
                if (!entry.is_directory) onSelect(entry.path)
              }}
            >
              <span className="bn-local-file-picker-icon">{entry.is_directory ? '▸' : 'USD'}</span>
              <span className="bn-local-file-picker-name">{entry.name}</span>
              <span className="bn-local-file-picker-size">{formatSize(entry.size)}</span>
            </button>
          ))}
        </div>

        <footer>
          <span title={selected}>{selected || 'Choose a USD file'}</span>
          <button type="button" onClick={onCancel}>Cancel</button>
          <button type="button" className="is-primary" disabled={!selected} onClick={() => onSelect(selected)}>
            Open file
          </button>
        </footer>
      </section>
    </div>
  )
}
