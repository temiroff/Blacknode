import { memo, useEffect, useRef, useState } from 'react'
import { Handle, Position, NodeProps, useUpdateNodeInternals } from 'reactflow'
import { NodeResizer } from '@reactflow/node-resizer'
import '@reactflow/node-resizer/dist/style.css'
import { useStore } from '../store'
import { portColor } from '../portColors'
import {
  DEFAULT_MODEL,
  MODEL_PROVIDERS,
  isKnownStarterModel,
  modelDisplayName,
  modelNameForProvider,
  modelProviderApiKeyNameById,
  modelProviderById,
  modelValueForProvider,
  providerIdForModelValue,
  providerPlaceholderById,
  savedModelsForProvider,
  shouldShowApiKeyForProvider,
  starterModelsForProvider,
} from '../models'
import { useQualifiedTypeLabel } from '../nodeTypeLabel'
import NodeFrame from './NodeFrame'
import type { NodeCookState } from '../types'

interface NodeData extends NodeCookState {
  id: string
  type: string
  params: Record<string, unknown>
  outputs: string[]
  output_types: Record<string, string>
  promoted_outputs?: string[] | null
}

const LAST_MODELS_PARAM = 'last_models_by_provider'

function lastModelsFromParam(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  const entries = Object.entries(value as Record<string, unknown>)
    .filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].trim().length > 0)
  return Object.fromEntries(entries)
}

function ModelNode({ id, data, selected }: NodeProps<NodeData>) {
  const { updateParam, apiKeys, apiKeyStatus, setApiKey, customModels, addCustomModel, removeCustomModel, edges } = useStore()
  const updateNodeInternals = useUpdateNodeInternals()
  const qualifiedType = useQualifiedTypeLabel(data.type)
  const showValueOutput = data.promoted_outputs == null
    || data.promoted_outputs.includes('value')
    || edges.some(edge => edge.source === id && edge.sourceHandle === 'value')

  useEffect(() => { updateNodeInternals(id) }, [id, showValueOutput, updateNodeInternals])

  const current = String(data.params.value ?? DEFAULT_MODEL)
  const [providerId, setProviderId] = useState(providerIdForModelValue(current))
  const [modelDraft, setModelDraft] = useState(modelNameForProvider(current, providerIdForModelValue(current)))
  const [showKey, setShowKey] = useState(false)
  const [providerOpen, setProviderOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const draftRef = useRef<HTMLInputElement>(null)
  const menusRef = useRef<HTMLDivElement>(null)

  const provider = modelProviderById(providerId)
  const color = provider.color
  const storedDraft = modelValueForProvider(providerId, modelDraft)
  const savedLastModels = lastModelsFromParam(data.params[LAST_MODELS_PARAM])
  const rememberedModels = {
    ...savedLastModels,
    [providerIdForModelValue(current)]: current,
  }
  const savedForProvider = savedModelsForProvider(customModels, providerId)
  const starterModels = starterModelsForProvider(providerId)
  const savedModelSet = new Set(savedForProvider)
  const modelChoices = [
    ...savedForProvider.map(value => ({ value, label: modelNameForProvider(value, providerId), group: 'Saved' })),
    ...starterModels
      .filter(model => !savedModelSet.has(model.value))
      .map(model => ({ value: model.value, label: model.label, group: 'Starter' })),
  ]
  const showApiKey = shouldShowApiKeyForProvider(providerId)
  const keyName = modelProviderApiKeyNameById(providerId)
  const apiKey = apiKeys[keyName] ?? ''
  const keyStatus = apiKeyStatus[keyName]

  useEffect(() => {
    const nextProvider = providerIdForModelValue(current)
    setProviderId(nextProvider)
    setModelDraft(modelNameForProvider(current, nextProvider))
  }, [current])

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!menusRef.current?.contains(event.target as Node)) {
        setProviderOpen(false)
        setModelOpen(false)
      }
    }
    window.addEventListener('mousedown', close, true)
    return () => window.removeEventListener('mousedown', close, true)
  }, [])

  const selectProvider = (nextProviderId: string) => {
    const currentProvider = providerIdForModelValue(current)
    const nextRemembered = { ...rememberedModels, [currentProvider]: current }
    const nextSaved = savedModelsForProvider(customModels, nextProviderId)
    const nextStarter = starterModelsForProvider(nextProviderId)
    const nextValue = currentProvider === nextProviderId
      ? current
      : nextRemembered[nextProviderId] ?? nextSaved[0] ?? nextStarter[0]?.value ?? ''

    if (nextValue) nextRemembered[nextProviderId] = nextValue

    setProviderId(nextProviderId)
    setModelDraft(modelNameForProvider(nextValue, nextProviderId))
    updateParam(id, LAST_MODELS_PARAM, nextRemembered)
    if (nextValue && nextValue !== current) updateParam(id, 'value', nextValue)
    setProviderOpen(false)
    setModelOpen(false)
    setTimeout(() => draftRef.current?.focus(), 0)
  }

  const useModel = (value: string, save = true) => {
    const trimmed = value.trim()
    if (!trimmed) return
    const nextProvider = providerIdForModelValue(trimmed)
    updateParam(id, LAST_MODELS_PARAM, { ...rememberedModels, [nextProvider]: trimmed })
    updateParam(id, 'value', trimmed)
    if (save && !isKnownStarterModel(trimmed)) addCustomModel(trimmed)
    setProviderId(nextProvider)
    setModelDraft(modelNameForProvider(trimmed, nextProvider))
    setModelOpen(false)
  }

  const saveDraft = () => {
    if (!storedDraft) return
    useModel(storedDraft, true)
  }

  const updateKey = (value: string) => {
    setApiKey(keyName, value)
  }

  const removeModelChoice = (value: string) => {
    removeCustomModel(value)
    const removedProvider = providerIdForModelValue(value)
    if (rememberedModels[removedProvider] === value && current !== value) {
      const nextRemembered = { ...rememberedModels }
      delete nextRemembered[removedProvider]
      updateParam(id, LAST_MODELS_PARAM, nextRemembered)
    }
  }

  const stopPointer = (e: React.SyntheticEvent) => {
    e.stopPropagation()
  }

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color={color}
      style={{
        width: '100%',
        minWidth: 260,
      }}
    >
      <NodeResizer
        minWidth={260}
        minHeight={170}
        isVisible={selected}
        lineStyle={{ borderColor: color }}
        handleStyle={{ background: color, borderColor: color, width: 8, height: 8, borderRadius: 2 }}
      />

      <div style={{
        background: color,
        borderRadius: '8px 8px 0 0',
        padding: '5px 10px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
      }}>
        <div style={{ minWidth: 0 }}>
          <span style={{ display: 'block', fontWeight: 700, fontSize: 11, fontFamily: 'var(--font-ui)', letterSpacing: '0.08em' }}>
            MODEL
          </span>
          <span
            title={`Node type ${data.type}`}
            style={{ fontSize: 9, opacity: 0.65, fontFamily: 'var(--font-mono)', display: 'block', marginTop: 1, whiteSpace: 'nowrap' }}
          >
            {qualifiedType}
          </span>
        </div>
        <span style={{
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          fontSize: 10,
          background: 'rgba(0,0,0,.22)',
          padding: '1px 6px',
          borderRadius: 4,
          fontFamily: 'var(--font-ui)',
          fontWeight: 600,
        }}>
          {modelDisplayName(current)}
        </span>
      </div>

      <div
        ref={menusRef}
        className="nodrag nopan"
        style={{ padding: '8px 8px 10px', display: 'flex', flexDirection: 'column', gap: 8 }}
        onPointerDownCapture={stopPointer}
        onMouseDownCapture={stopPointer}
        onPointerDown={stopPointer}
        onMouseDown={stopPointer}
        onClick={stopPointer}
        onDoubleClick={stopPointer}
        onDragStart={e => e.preventDefault()}
      >
        <div>
          <label style={{
            display: 'block',
            color: 'var(--tx3)',
            fontSize: 10,
            fontWeight: 700,
            textTransform: 'uppercase',
            marginBottom: 4,
          }}>
            Provider
          </label>
          <div style={{ position: 'relative' }}>
            <button
              className="nodrag nopan"
              onClick={() => { setProviderOpen(o => !o); setModelOpen(false) }}
              onPointerDownCapture={stopPointer}
              style={{
                width: '100%',
                background: 'var(--lift)',
                border: `1px solid ${color}`,
                borderRadius: 5,
                color,
                cursor: 'pointer',
                fontSize: 11,
                fontFamily: 'var(--font-ui)',
                fontWeight: 700,
                outline: 'none',
                padding: '5px 7px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 7, height: 7, borderRadius: 2, background: color }} />
                {provider.label}
              </span>
              <span style={{ color: 'var(--tx3)' }}>{providerOpen ? '▲' : '▼'}</span>
            </button>
            {providerOpen && (
              <div style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: 'calc(100% + 3px)',
                background: 'var(--panel)',
                border: '1px solid var(--line2)',
                borderRadius: 6,
                boxShadow: '0 10px 30px rgba(0,0,0,.35)',
                overflow: 'hidden',
                zIndex: 10000,
              }}>
                {MODEL_PROVIDERS.map(p => (
                  <button
                    className="nodrag nopan"
                    key={p.id}
                    onClick={() => selectProvider(p.id)}
                    onPointerDownCapture={stopPointer}
                    style={{
                      width: '100%',
                      background: p.id === providerId ? `${p.color}1f` : 'transparent',
                      border: 'none',
                      borderLeft: `3px solid ${p.color}`,
                      color: p.color,
                      cursor: 'pointer',
                      fontFamily: 'var(--font-ui)',
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '6px 8px',
                      textAlign: 'left',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 7,
                    }}
                  >
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: p.color }} />
                    {p.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            marginBottom: 4,
          }}>
            <input
              className="nodrag nopan"
              ref={draftRef}
              value={modelDraft}
              placeholder={providerPlaceholderById(providerId)}
              onPointerDownCapture={stopPointer}
              onMouseDownCapture={stopPointer}
              onPointerDown={stopPointer}
              onMouseDown={stopPointer}
              onClick={stopPointer}
              onDoubleClick={stopPointer}
              onDragStart={e => e.preventDefault()}
              onChange={e => setModelDraft(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  saveDraft()
                }
              }}
              style={{
                flex: 1,
                minWidth: 0,
                background: 'var(--lift)',
                border: `1px solid ${storedDraft === current ? color : 'var(--line2)'}`,
                borderRadius: 5,
                color: 'var(--tx1)',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                outline: 'none',
                padding: '5px 7px',
              }}
            />
            <button
              className="nodrag nopan"
              onClick={e => { e.stopPropagation(); saveDraft() }}
              onPointerDownCapture={stopPointer}
              onPointerDown={stopPointer}
              onMouseDown={stopPointer}
              disabled={!storedDraft}
              style={{
                background: storedDraft ? color : 'var(--line2)',
                border: 'none',
                borderRadius: 5,
                color: '#fff',
                cursor: storedDraft ? 'pointer' : 'default',
                fontFamily: 'var(--font-ui)',
                fontSize: 10,
                fontWeight: 700,
                padding: '6px 8px',
                whiteSpace: 'nowrap',
              }}
            >
              Save to list
            </button>
          </div>
        </div>

        <div style={{ position: 'relative' }}>
          <button
            className="nodrag nopan"
            onClick={() => { setModelOpen(o => !o); setProviderOpen(false) }}
            onPointerDownCapture={stopPointer}
            disabled={modelChoices.length === 0}
            style={{
              width: '100%',
              background: 'var(--lift)',
              border: `1px solid ${modelOpen ? color : 'var(--line2)'}`,
              borderRadius: 5,
              color: modelChoices.length ? 'var(--tx2)' : 'var(--tx3)',
              cursor: modelChoices.length ? 'pointer' : 'default',
              fontSize: 11,
              fontFamily: 'var(--font-ui)',
              fontWeight: 600,
              padding: '5px 7px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
            }}
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              Saved and starter models
            </span>
            <span style={{ color: 'var(--tx3)' }}>{modelOpen ? '▲' : '▼'}</span>
          </button>
          {modelOpen && (
            <div style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: 'calc(100% + 3px)',
              maxHeight: 210,
              overflowY: 'auto',
              background: 'var(--panel)',
              border: '1px solid var(--line2)',
              borderRadius: 6,
              boxShadow: '0 10px 30px rgba(0,0,0,.35)',
              zIndex: 9999,
            }}>
              {['Saved', 'Starter'].map(group => {
                const rows = modelChoices.filter(choice => choice.group === group)
                if (rows.length === 0) return null
                return (
                  <div key={group}>
                    <div style={{
                      padding: '6px 8px 3px',
                      color: group === 'Saved' ? color : 'var(--tx3)',
                      fontSize: 10,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                    }}>
                      {group === 'Saved' ? 'Saved local models' : 'Starter examples'}
                    </div>
                    {rows.map(choice => (
                      <div
                        key={choice.value}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 5,
                          background: choice.value === current ? `${color}18` : 'transparent',
                          borderLeft: `3px solid ${choice.value === current ? color : 'transparent'}`,
                        }}
                      >
                        <button
                          className="nodrag nopan"
                          onClick={() => useModel(choice.value, false)}
                          onPointerDownCapture={stopPointer}
                          style={{
                            flex: 1,
                            minWidth: 0,
                            background: 'transparent',
                            border: 'none',
                            color: choice.value === current ? color : 'var(--tx2)',
                            cursor: 'pointer',
                            fontFamily: 'var(--font-mono)',
                            fontSize: 10,
                            textAlign: 'left',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            padding: '5px 7px',
                          }}
                        >
                          {choice.label}
                        </button>
                        {group === 'Saved' && (
                          <button
                            className="nodrag nopan"
                            title="Remove saved model"
                            onClick={e => { e.stopPropagation(); removeModelChoice(choice.value) }}
                            onPointerDownCapture={stopPointer}
                            style={{
                              background: 'var(--lift)',
                              border: '1px solid var(--line2)',
                              borderRadius: 4,
                              color: 'var(--err)',
                              cursor: 'pointer',
                              fontFamily: 'var(--font-ui)',
                              fontSize: 10,
                              fontWeight: 700,
                              lineHeight: 1,
                              padding: '3px 6px',
                              marginRight: 5,
                              flexShrink: 0,
                            }}
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {showApiKey ? (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <input
                className="nodrag nopan"
                value={apiKey}
                placeholder={`${keyName} API key`}
                onPointerDownCapture={stopPointer}
                onMouseDownCapture={stopPointer}
                onPointerDown={stopPointer}
                onMouseDown={stopPointer}
                onClick={stopPointer}
                onDoubleClick={stopPointer}
                onDragStart={e => e.preventDefault()}
                onChange={e => updateKey(e.target.value)}
                type={showKey ? 'text' : 'password'}
                style={{
                  flex: 1,
                  minWidth: 0,
                  background: 'transparent',
                  border: 'none',
                  borderBottom: `1px solid ${keyStatus?.configured ? color + '80' : 'var(--line2)'}`,
                  color: keyStatus?.configured ? 'var(--tx1)' : 'var(--tx3)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  outline: 'none',
                  padding: '3px 2px',
                }}
              />
              <button
                className="nodrag nopan"
                onClick={e => { e.stopPropagation(); setShowKey(s => !s) }}
                onPointerDownCapture={stopPointer}
                onMouseDown={e => e.stopPropagation()}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: showKey ? color : 'var(--tx3)',
                  cursor: 'pointer',
                  fontSize: 10,
                  padding: '2px 3px',
                  flexShrink: 0,
                }}
              >
                {showKey ? 'hide' : 'show'}
              </button>
            </div>
            <div style={{
              marginTop: 4, fontSize: 9, fontFamily: 'var(--font-mono)',
              color: keyStatus?.configured ? 'var(--ok)' : 'var(--warn)',
            }}>
              {keyStatus?.configured
                ? `✓ Shared key ready (${keyStatus.source === 'saved' ? 'saved in editor' : keyStatus.env_var || 'environment'})`
                : '! Key missing'}
            </div>
          </div>
        ) : (
          <div style={{ color: 'var(--tx3)', fontSize: 10 }}>
            Ollama uses the local server at localhost:11434.
          </div>
        )}

      </div>

      {showValueOutput && (
        <Handle
          type="source"
          position={Position.Right}
          id="value"
          style={{
            right: -5,
            background: portColor('Model'),
            width: 9, height: 9,
            border: `1.5px solid ${portColor('Model')}`,
            borderRadius: 3,
          }}
        />
      )}
    </NodeFrame>
  )
}

export default memo(ModelNode)
