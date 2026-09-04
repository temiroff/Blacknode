import { describe, expect, it } from 'vitest'

import { isWorkflowOperatorView, normalizeViewerUrl, viewerSandbox } from './operatorView'

function operatorView(): Record<string, unknown> {
  return {
    schema_version: 1,
    id: 'robot-viewer',
    title: 'Robot viewer',
    run_target: { node_id: 'viewer', port: 'viewer_url' },
    settings: {
      groups: [{
        id: 'scene',
        title: 'Scene',
        items: [{
          node_id: 'viewer',
          param: 'model_path',
          label: 'Model',
          input: 'file_path',
          extensions: ['.usd', '.usda'],
        }],
      }],
    },
    sections: [{
      id: 'main',
      widgets: [
        { type: 'viewer', id: 'viewer', title: 'Scene', source: { node_id: 'viewer', port: 'viewer_url' } },
        { type: 'status', id: 'status', items: [{ label: 'Ready', node_id: 'viewer', port: 'ready', tone: 'success' }] },
        { type: 'metrics', id: 'metrics', items: [{ label: 'Bodies', node_id: 'viewer', port: 'body_count', format: 'number' }] },
        { type: 'actions', id: 'actions', items: [{ id: 'start', label: 'Start', cook_target: { node_id: 'viewer', port: 'viewer_url' } }] },
      ],
    }],
  }
}

describe('isWorkflowOperatorView', () => {
  it('accepts a complete operator contract', () => {
    expect(isWorkflowOperatorView(operatorView())).toBe(true)
  })

  it('rejects malformed widget payloads and duplicate widget ids', () => {
    const malformed = operatorView()
    const sections = malformed.sections as Array<Record<string, unknown>>
    const widgets = sections[0].widgets as Array<Record<string, unknown>>
    delete (widgets[1].items as Array<Record<string, unknown>>)[0].port
    expect(isWorkflowOperatorView(malformed)).toBe(false)

    const duplicate = operatorView()
    const duplicateWidgets = (duplicate.sections as Array<Record<string, unknown>>)[0].widgets as Array<Record<string, unknown>>
    duplicateWidgets[1].id = 'viewer'
    expect(isWorkflowOperatorView(duplicate)).toBe(false)
  })

  it('requires an extension allowlist for generic file fields', () => {
    const malformed = operatorView()
    const settings = malformed.settings as Record<string, unknown>
    const groups = settings.groups as Array<Record<string, unknown>>
    const field = (groups[0].items as Array<Record<string, unknown>>)[0]
    delete field.extensions
    expect(isWorkflowOperatorView(malformed)).toBe(false)
  })

  it('accepts exact viewer origins and rejects origins containing paths', () => {
    const valid = operatorView()
    const widgets = ((valid.sections as Array<Record<string, unknown>>)[0].widgets as Array<Record<string, unknown>>)
    widgets[0].trusted_origins = ['https://viewer.example.com']
    expect(isWorkflowOperatorView(valid)).toBe(true)

    widgets[0].trusted_origins = ['https://viewer.example.com/path']
    expect(isWorkflowOperatorView(valid)).toBe(false)
  })
})

describe('normalizeViewerUrl', () => {
  it('allows relative and local viewer URLs', () => {
    expect(normalizeViewerUrl('/viewer/session')).toBe('/viewer/session')
    expect(normalizeViewerUrl({ viewer_url: 'http://127.0.0.1:8090/' })).toBe('http://127.0.0.1:8090/')
    expect(normalizeViewerUrl('https://robot.local/view')).toBe('https://robot.local/view')
  })

  it('rejects active schemes, embedded credentials, and undeclared public origins', () => {
    expect(normalizeViewerUrl('javascript:alert(1)')).toBe('')
    expect(normalizeViewerUrl('https://user:secret@example.com/view')).toBe('')
    expect(normalizeViewerUrl('https://viewer.example.com/view')).toBe('')
  })

  it('allows an explicitly trusted public origin', () => {
    expect(normalizeViewerUrl('https://viewer.example.com/view', ['https://viewer.example.com']))
      .toBe('https://viewer.example.com/view')
  })
})

describe('viewerSandbox', () => {
  it('keeps same-origin viewers in an opaque sandbox', () => {
    expect(viewerSandbox('/viewer/session', 'https://app.example.com'))
      .toBe('allow-forms allow-pointer-lock allow-scripts')
  })

  it('preserves a cross-origin viewer identity for its own assets and sockets', () => {
    expect(viewerSandbox('http://127.0.0.1:8090', 'http://127.0.0.1:7777'))
      .toBe('allow-forms allow-pointer-lock allow-scripts allow-same-origin')
  })
})
