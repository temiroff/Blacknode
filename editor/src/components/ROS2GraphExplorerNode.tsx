import { useMemo, useState, type CSSProperties } from 'react'
import { NodeResizer } from '@reactflow/node-resizer'
import { Handle, Position, type NodeProps } from 'reactflow'

import { portColor, portVisualColor } from '../portColors'
import { portDisplayName } from '../portLabels'
import { useStore, type NodeData } from '../store'
import NodeFrame from './NodeFrame'
import NodeGlyph from './NodeGlyph'

type RosEndpoint = {
  node?: string
  topic_type?: string
  gid?: string
  qos?: Record<string, string>
}

type RosTopic = {
  name: string
  types?: string[]
  publisher_count?: number
  subscription_count?: number
  publishers?: RosEndpoint[]
  subscribers?: RosEndpoint[]
}

type RosService = {
  name: string
  types?: string[]
}

type RosGraph = {
  captured_at?: string
  backend?: string
  namespace?: string
  nodes?: string[]
  topics?: RosTopic[]
  services?: RosService[]
  errors?: string[]
  truncated?: boolean
}

type ExplorerTab = 'topics' | 'nodes' | 'services'

const INFRASTRUCTURE_NODE_NAMES = new Set([
  'rosapi',
  'rosbridge_websocket',
])

const INFRASTRUCTURE_TOPIC_NAMES = new Set([
  'client_count',
  'connected_clients',
  'parameter_events',
  'rosout',
])

function rosNameParts(value: unknown) {
  return String(value ?? '')
    .split('/')
    .map(part => part.trim())
    .filter(Boolean)
}

function normalizedRosName(value: unknown) {
  const parts = rosNameParts(value)
  return parts.length > 0 ? `/${parts.join('/')}` : '/'
}

function infrastructureNode(value: unknown) {
  const parts = rosNameParts(value)
  return parts.length > 0 && INFRASTRUCTURE_NODE_NAMES.has(parts[parts.length - 1])
}

function infrastructureService(service: RosService) {
  return rosNameParts(service.name).some(part => INFRASTRUCTURE_NODE_NAMES.has(part))
}

function infrastructureTopic(topic: RosTopic) {
  const parts = rosNameParts(topic.name)
  if (parts.length > 0 && INFRASTRUCTURE_TOPIC_NAMES.has(parts[parts.length - 1])) {
    return true
  }
  const endpoints = [...(topic.publishers ?? []), ...(topic.subscribers ?? [])]
  return endpoints.length > 0 && endpoints.every(endpoint => infrastructureNode(endpoint.node))
}

function namespacePrefix(value: string) {
  return normalizedRosName(value.trim().replace(/\/\*+$/, ''))
}

function nameInNamespace(value: unknown, prefix: string) {
  if (prefix === '/') return true
  const name = normalizedRosName(value)
  return name === prefix || name.startsWith(`${prefix}/`)
}

function topicInNamespace(topic: RosTopic, prefix: string) {
  if (nameInNamespace(topic.name, prefix)) return true
  return [...(topic.publishers ?? []), ...(topic.subscribers ?? [])]
    .some(endpoint => nameInNamespace(endpoint.node, prefix))
}

function graphValue(value: unknown): RosGraph {
  return value && typeof value === 'object' ? value as RosGraph : {}
}

function contains(value: unknown, query: string) {
  return String(value ?? '').toLowerCase().includes(query)
}

function endpointMatches(endpoint: RosEndpoint, query: string) {
  return contains(endpoint.node, query)
    || contains(endpoint.topic_type, query)
    || Object.values(endpoint.qos ?? {}).some(value => contains(value, query))
}

function topicMatches(topic: RosTopic, query: string) {
  return contains(topic.name, query)
    || (topic.types ?? []).some(value => contains(value, query))
    || (topic.publishers ?? []).some(endpoint => endpointMatches(endpoint, query))
    || (topic.subscribers ?? []).some(endpoint => endpointMatches(endpoint, query))
}

function qosLabel(endpoint: RosEndpoint) {
  const qos = endpoint.qos ?? {}
  return [qos.reliability, qos.durability]
    .filter(Boolean)
    .map(value => String(value).toLowerCase().replace(/_/g, ' '))
    .join(' · ')
}

function EndpointList({ endpoints, empty }: { endpoints: RosEndpoint[]; empty: string }) {
  if (endpoints.length === 0) {
    return <span className="bn-ros-explorer-empty-endpoint">{empty}</span>
  }
  return (
    <div className="bn-ros-explorer-endpoints">
      {endpoints.map((endpoint, index) => {
        const qos = qosLabel(endpoint)
        return (
          <div
            className="bn-ros-explorer-endpoint"
            key={`${endpoint.node || 'endpoint'}-${endpoint.gid || index}`}
            title={[endpoint.topic_type, qos].filter(Boolean).join('\n')}
          >
            <strong>{endpoint.node || 'unknown node'}</strong>
            {qos && <span>{qos}</span>}
          </div>
        )
      })}
    </div>
  )
}

function ExplorerPort({
  direction,
  name,
  type,
}: {
  direction: 'input' | 'output'
  name: string
  type: string
}) {
  const input = direction === 'input'
  const color = portColor(type)
  const visualColor = portVisualColor(type)
  return (
    <div
      className="bn-ros-explorer-port"
      data-direction={direction}
      style={{ '--bn-port-color': visualColor } as CSSProperties}
    >
      <Handle
        type={input ? 'target' : 'source'}
        position={input ? Position.Left : Position.Right}
        id={name}
        title={`${name}: ${type}`}
        style={{
          [input ? 'left' : 'right']: -5,
          width: 9,
          height: 9,
          border: `1.5px solid ${color}`,
          borderRadius: 3,
          background: color,
        }}
      />
      <span>{portDisplayName(name, direction)}</span>
      <i style={{ color: visualColor }}>{type.toUpperCase()}</i>
    </div>
  )
}

export default function ROS2GraphExplorerNode({ id, data, selected }: NodeProps<NodeData>) {
  const [query, setQuery] = useState('')
  const [namespace, setNamespace] = useState('/')
  const [showInfrastructure, setShowInfrastructure] = useState(false)
  const [tab, setTab] = useState<ExplorerTab>('topics')
  const [notice, setNotice] = useState('')
  const cookNode = useStore(state => state.cookNode)
  const addNode = useStore(state => state.addNode)
  const nodes = useStore(state => state.nodes)
  const nodeDefs = useStore(state => state.nodeDefs)
  const graph = graphValue(data.portResults?.graph)
  const normalizedQuery = query.trim().toLowerCase()
  const topics = Array.isArray(graph.topics) ? graph.topics : []
  const rosNodes = Array.isArray(graph.nodes) ? graph.nodes : []
  const services = Array.isArray(graph.services) ? graph.services : []
  const activeNamespace = namespacePrefix(namespace)
  const infrastructureCounts = useMemo(() => ({
    topics: topics.filter(infrastructureTopic).length,
    nodes: rosNodes.filter(infrastructureNode).length,
    services: services.filter(infrastructureService).length,
  }), [topics, rosNodes, services])
  const scopedTopics = useMemo(
    () => topics.filter(topic => (
      topicInNamespace(topic, activeNamespace)
      && (showInfrastructure || !infrastructureTopic(topic))
    )),
    [activeNamespace, showInfrastructure, topics],
  )
  const scopedNodes = useMemo(
    () => rosNodes.filter(node => (
      nameInNamespace(node, activeNamespace)
      && (showInfrastructure || !infrastructureNode(node))
    )),
    [activeNamespace, rosNodes, showInfrastructure],
  )
  const scopedServices = useMemo(
    () => services.filter(service => (
      nameInNamespace(service.name, activeNamespace)
      && (showInfrastructure || !infrastructureService(service))
    )),
    [activeNamespace, services, showInfrastructure],
  )
  const filteredTopics = useMemo(
    () => normalizedQuery
      ? scopedTopics.filter(topic => topicMatches(topic, normalizedQuery))
      : scopedTopics,
    [normalizedQuery, scopedTopics],
  )
  const filteredNodes = useMemo(
    () => normalizedQuery ? scopedNodes.filter(node => contains(node, normalizedQuery)) : scopedNodes,
    [normalizedQuery, scopedNodes],
  )
  const filteredServices = useMemo(
    () => normalizedQuery
      ? scopedServices.filter(service => contains(service.name, normalizedQuery)
        || (service.types ?? []).some(value => contains(value, normalizedQuery)))
      : scopedServices,
    [normalizedQuery, scopedServices],
  )
  const hasSnapshot = topics.length > 0 || rosNodes.length > 0 || services.length > 0
  const hiddenInfrastructure = infrastructureCounts.topics
    + infrastructureCounts.nodes
    + infrastructureCounts.services
  const available = data.portResults?.available === true

  const refresh = async () => {
    setNotice('')
    await cookNode(id, 'graph')
  }

  const addMonitor = async (topic: RosTopic) => {
    const messageType = topic.types?.[0] || ''
    const lowerName = topic.name.toLowerCase()
    let type = 'ROS2TopicEcho'
    let params: Record<string, unknown> = {
      topic: topic.name,
      msg_type: messageType,
      count: 1,
    }
    if (messageType === 'sensor_msgs/msg/Image' || messageType === 'sensor_msgs/msg/CompressedImage') {
      if (lowerName.includes('depth') && nodeDefs.DepthROS2Subscribe) {
        type = 'DepthROS2Subscribe'
        params = { topic: topic.name }
      } else if (nodeDefs.CameraROS2Subscribe) {
        type = 'CameraROS2Subscribe'
        params = { topic: topic.name, message_type: messageType || 'auto' }
      }
    } else if (messageType === 'sensor_msgs/msg/JointState' && nodeDefs.ROS2JointState) {
      type = 'ROS2JointState'
      params = { topic: topic.name }
    }
    if (!nodeDefs[type]) {
      type = 'ROS2TopicEcho'
      params = { topic: topic.name, msg_type: messageType, count: 1 }
    }
    const self = nodes.find(node => node.id === id)
    const existingMonitors = nodes.filter(node => (
      String(node.data.params?.topic || '') === topic.name
    )).length
    await addNode(type, {
      x: (self?.position.x ?? 0) + 1080,
      y: (self?.position.y ?? 0) + existingMonitors * 190,
    }, params)
    setNotice(`Added ${type} for ${topic.name}`)
  }

  const addSubscriber = async (topic: RosTopic) => {
    if (!nodeDefs.ROS2TopicSubscriber) {
      setNotice('ROS2TopicSubscriber is unavailable. Refresh canvas schemas after updating blacknode-ros2.')
      return
    }
    const self = nodes.find(node => node.id === id)
    const existingReaders = nodes.filter(node => (
      String(node.data.params?.topic || '') === topic.name
    )).length
    const safeName = topic.name
      .replace(/^\/+/, '')
      .replace(/[^A-Za-z0-9_]+/g, '_')
      .replace(/^[^A-Za-z_]+/, '') || 'topic'
    await addNode('ROS2TopicSubscriber', {
      x: (self?.position.x ?? 0) + 1080,
      y: (self?.position.y ?? 0) + existingReaders * 190,
    }, {
      action: 'start',
      node_name: `${safeName}_subscriber`,
      topic: topic.name,
      msg_type: topic.types?.[0] || 'std_msgs/msg/String',
      history: 10,
      timeout: 10.0,
    })
    setNotice(`Added named subscriber for ${topic.name}`)
  }

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      color="#2e9fe6"
      nodeType={data.type}
      style={{
        width: '100%',
        height: '100%',
        minWidth: 760,
        minHeight: 580,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <NodeResizer
        minWidth={760}
        minHeight={580}
        isVisible={selected}
        lineStyle={{ borderColor: '#2e9fe6' }}
        handleStyle={{
          width: 8,
          height: 8,
          borderRadius: 2,
          borderColor: '#2e9fe6',
          background: '#2e9fe6',
        }}
      />

      <header className="bn-node-header bn-ros-explorer-header">
        <NodeGlyph type={data.type} className="bn-node-header-glyph" />
        <div>
          <strong className="bn-node-title">ROS 2 Graph Explorer</strong>
          <span className="bn-node-type">
            {graph.namespace || String(data.params?.namespace || '/')}
            {' · '}{graph.backend || String(data.portResults?.backend || 'not scanned')}
          </span>
        </div>
        <div
          className="bn-node-runtime-state"
          data-tone={data.cooking ? 'running' : available ? 'ready' : 'idle'}
        >
          <i />
          <span>{data.cooking ? 'Scanning' : available ? 'Ready' : 'Run to scan'}</span>
        </div>
        <button
          type="button"
          className="bn-ros-explorer-refresh nodrag"
          disabled={Boolean(data.cooking)}
          onMouseDown={event => event.stopPropagation()}
          onClick={event => {
            event.stopPropagation()
            void refresh()
          }}
        >
          {data.cooking ? 'Scanning…' : hasSnapshot ? 'Refresh graph' : 'Scan graph'}
        </button>
      </header>

      <div
        className="bn-ros-explorer-toolbar nodrag"
        onMouseDown={event => event.stopPropagation()}
        onClick={event => event.stopPropagation()}
      >
        <label>
          <span>Filter topology</span>
          <input
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="topic, node, type, QoS…"
          />
        </label>
        <label className="bn-ros-explorer-namespace">
          <span>Namespace</span>
          <input
            type="text"
            value={namespace}
            onChange={event => setNamespace(event.target.value)}
            placeholder="/my_robot/**"
            spellCheck={false}
          />
        </label>
        <label className="bn-ros-explorer-system-toggle">
          <input
            type="checkbox"
            checked={showInfrastructure}
            onChange={event => setShowInfrastructure(event.target.checked)}
          />
          <span>Show infrastructure</span>
        </label>
        <div className="bn-ros-explorer-tabs" role="tablist" aria-label="ROS graph sections">
          {([
            ['topics', `Topics ${scopedTopics.length}`],
            ['nodes', `Nodes ${scopedNodes.length}`],
            ['services', `Services ${scopedServices.length}`],
          ] as Array<[ExplorerTab, string]>).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              className={tab === value ? 'is-active' : ''}
              onClick={() => setTab(value)}
            >
              {label}
            </button>
          ))}
        </div>
        {graph.captured_at && <time>{graph.captured_at}</time>}
      </div>

      {!showInfrastructure && hiddenInfrastructure > 0 && (
        <div className="bn-ros-explorer-filter-summary nodrag">
          <span>
            Infrastructure hidden: {infrastructureCounts.nodes} nodes ·{' '}
            {infrastructureCounts.topics} topics · {infrastructureCounts.services} services
          </span>
          <button type="button" onClick={() => setShowInfrastructure(true)}>Show</button>
        </div>
      )}

      <div className="bn-ros-explorer-content nodrag">
        {!hasSnapshot && !data.cooking && (
          <div className="bn-ros-explorer-empty">
            <strong>Scan the ROS 2 graph</strong>
            <span>Read-only discovery will map publishers, typed topics, subscribers, services, and QoS.</span>
          </div>
        )}

        {hasSnapshot && tab === 'topics' && (
          <div className="bn-ros-explorer-topology">
            <div className="bn-ros-explorer-column-head">
              <span>Publishers</span><span>Typed topics</span><span>Subscribers</span>
            </div>
            {filteredTopics.map(topic => (
              <article className="bn-ros-explorer-topic-row" key={topic.name}>
                <EndpointList endpoints={topic.publishers ?? []} empty="No publisher" />
                <div className="bn-ros-explorer-topic-card">
                  <strong>{topic.name}</strong>
                  <span>{(topic.types ?? []).join(', ') || 'type unavailable'}</span>
                  <small>
                    {topic.publisher_count ?? topic.publishers?.length ?? 0} pub
                    {' · '}{topic.subscription_count ?? topic.subscribers?.length ?? 0} sub
                  </small>
                  <button type="button" onClick={() => void addSubscriber(topic)}>Add subscriber</button>
                  <button type="button" onClick={() => void addMonitor(topic)}>Add one-shot monitor</button>
                </div>
                <EndpointList endpoints={topic.subscribers ?? []} empty="No subscriber" />
              </article>
            ))}
            {filteredTopics.length === 0 && (
              <div className="bn-ros-explorer-no-match">
                {showInfrastructure ? 'No matching topics.' : 'No robot or application topics match these filters.'}
              </div>
            )}
          </div>
        )}

        {hasSnapshot && tab === 'nodes' && (
          <div className="bn-ros-explorer-inventory">
            {filteredNodes.map(node => <code key={node}>{node}</code>)}
            {filteredNodes.length === 0 && (
              <div className="bn-ros-explorer-no-match">
                {showInfrastructure ? 'No matching nodes.' : 'No robot or application nodes match these filters.'}
              </div>
            )}
          </div>
        )}

        {hasSnapshot && tab === 'services' && (
          <div className="bn-ros-explorer-service-list">
            {filteredServices.map(service => (
              <div key={service.name}>
                <code>{service.name}</code>
                <span>{(service.types ?? []).join(', ') || 'type unavailable'}</span>
              </div>
            ))}
            {filteredServices.length === 0 && (
              <div className="bn-ros-explorer-no-match">
                {showInfrastructure ? 'No matching services.' : 'No robot or application services match these filters.'}
              </div>
            )}
          </div>
        )}
      </div>

      {(graph.truncated || (graph.errors?.length ?? 0) > 0 || notice) && (
        <div className="bn-ros-explorer-notice">
          {notice && <span>{notice}</span>}
          {graph.truncated && <span>Topic inspection reached the configured max_topics limit.</span>}
          {(graph.errors ?? []).slice(0, 2).map(error => <span key={error}>{error}</span>)}
        </div>
      )}

      <footer className="bn-ros-explorer-ports">
        <div>
          <strong>Inputs</strong>
          {data.inputs.map(name => (
            <ExplorerPort
              key={name}
              direction="input"
              name={name}
              type={data.input_types?.[name] || 'Any'}
            />
          ))}
        </div>
        <div>
          <strong>Outputs</strong>
          {data.outputs.map(name => (
            <ExplorerPort
              key={name}
              direction="output"
              name={name}
              type={data.output_types?.[name] || 'Any'}
            />
          ))}
        </div>
      </footer>
    </NodeFrame>
  )
}
