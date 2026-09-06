import { describe, expect, it } from 'vitest'
import { appTargets, buildAppView, designerControls, type AppControl } from './appDesigner'
import { isWorkflowOperatorView, type WorkflowOperatorView } from './operatorView'
import type { BnNodeMeta } from './types'

const node: BnNodeMeta = { id: 'task', type: 'Task', pos: [0, 0], params: {},
  inputs: ['task', 'steps', 'api_key', 'dataset'], outputs: ['result', 'viewer_url'],
  input_types: { task: 'Text', steps: 'Int', api_key: 'Text', dataset: 'Text' },
  output_types: { result: 'Text', viewer_url: 'Text' }, input_defaults: {} }
const targets = appTargets([node], {}, new Set([JSON.stringify(['task', 'dataset'])]))
const controls: AppControl[] = [
  { id: 'task-input', kind: 'setting', target: JSON.stringify(['task', 'task']), label: 'Task' },
  { id: 'steps-input', kind: 'setting', target: JSON.stringify(['task', 'steps']), label: 'Steps' },
  { id: 'run', kind: 'action', target: JSON.stringify(['task', 'result']), label: 'Train', mode: 'live', confirm: 'Start training?' },
  { id: 'result', kind: 'result', target: JSON.stringify(['task', 'result']), label: 'Result', display: 'text' },
  { id: 'viewer', kind: 'result', target: JSON.stringify(['task', 'viewer_url']), label: 'Preview', display: 'viewer' },
]

describe('App designer', () => {
  it('offers unconnected typed parameters and excludes credentials', () => {
    expect(targets.settings.map(item => item.port)).toEqual(['task', 'steps'])
  })
  it('includes saved value-node parameters even when the node has no input ports', () => {
    const value = { ...node, type: 'Text', inputs: [], input_types: {}, params: { value: 'Hello', _label: 'Greeting' } }
    expect(appTargets([value], {}, new Set()).settings.map(item => item.port)).toEqual(['value'])
  })
  it('offers the cooked value of terminal Output nodes', () => {
    expect(appTargets([{ ...node, type: 'Output', outputs: [] }], {}, new Set()).outputs[0].port).toBe('value')
  })
  it('builds a valid App with numeric fields, confirmed live actions, and visible outputs', () => {
    const view = buildAppView('My task', 'my-task', controls, targets, null)
    expect(isWorkflowOperatorView(view)).toBe(true)
    expect(view.sections[1].widgets[1]).toMatchObject({ type: 'fields', items: [{ input: 'number' }] })
    expect(view.sections[0].widgets[0]).toMatchObject({ type: 'actions', items: [{ confirm: 'Start training?', cook_target: { mode: 'live' } }] })
    expect(designerControls(view)).toEqual([controls[2], controls[3], controls[4], controls[0], controls[1]])
  })
  it('preserves existing safety controls, settings, and primary run targets when adding controls', () => {
    const existing: WorkflowOperatorView = { schema_version: 1, id: 'robot', title: 'Robot',
      run_target: { node_id: 'task', port: 'result', confirm: 'Authorize?', mode: 'once' },
      settings: { groups: [{ id: 'connection', title: 'Connection', items: [{ node_id: 'task', param: 'task', label: 'Task' }] }] },
      sections: [{ id: 'safety', widgets: [{ type: 'actions', id: 'arm', items: [{ id: 'arm', label: 'Arm', confirm: 'Arm robot?', control: { node_id: 'task', action: 'arm' } }] }] }] }
    const original = structuredClone(existing)
    const view = buildAppView('Custom robot', 'robot', controls, targets, existing)
    expect(view.sections[0]).toEqual(original.sections[0])
    expect(view.run_target).toEqual(original.run_target)
    expect(view.settings).toEqual(original.settings)
    expect(existing).toEqual(original)
  })
  it('rejects missing references and empty apps before saving', () => {
    expect(() => buildAppView('App', 'app', [{ ...controls[0], target: 'missing' }], targets, null)).toThrow('available workflow parameter')
    expect(() => buildAppView('App', 'app', [], targets, null)).toThrow('Add a parameter')
  })
})
