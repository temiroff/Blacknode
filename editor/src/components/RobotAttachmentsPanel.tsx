import { useState, type FormEvent } from 'react'
import {
  api,
  type HardwareDevice,
  type RobotAttachment,
  type RobotAttachmentInput,
  type RobotAttachmentType,
} from '../api'
import './RobotAttachmentsPanel.css'

type AttachmentPreset = Pick<
  RobotAttachmentInput,
  | 'display_name'
  | 'attachment_type'
  | 'capability'
  | 'provider_package'
  | 'provider_component'
  | 'provider_adapter'
  | 'topic'
  | 'message_type'
  | 'parent_frame'
  | 'frame_id'
>

const ATTACHMENT_TYPES: Array<{ value: RobotAttachmentType; label: string }> = [
  { value: 'camera', label: 'Camera' },
  { value: 'depth_camera', label: 'Depth camera' },
  { value: 'lidar', label: 'LiDAR' },
  { value: 'imu', label: 'IMU' },
  { value: 'gps', label: 'GPS' },
  { value: 'microphone', label: 'Microphone' },
  { value: 'custom', label: 'Custom ROS 2 device' },
]

const PRESETS: Record<RobotAttachmentType, AttachmentPreset> = {
  camera: {
    display_name: 'Front camera',
    attachment_type: 'camera',
    capability: 'camera',
    provider_package: 'blacknode-perception',
    provider_component: 'camera',
    provider_adapter: 'ros2',
    topic: '/camera/image_raw',
    message_type: 'sensor_msgs/msg/Image',
    parent_frame: 'base_link',
    frame_id: 'camera_link',
  },
  depth_camera: {
    display_name: 'Front depth camera',
    attachment_type: 'depth_camera',
    capability: 'depth_camera',
    provider_package: 'blacknode-perception',
    provider_component: 'depth',
    provider_adapter: 'ros2',
    topic: '/depth_cam/rgb/image_raw',
    message_type: 'sensor_msgs/msg/Image',
    parent_frame: 'base_link',
    frame_id: 'depth_camera_link',
  },
  lidar: {
    display_name: 'Front LiDAR',
    attachment_type: 'lidar',
    capability: 'lidar',
    provider_package: 'blacknode-perception',
    provider_component: 'lidar',
    provider_adapter: 'ros2',
    topic: '/scan',
    message_type: 'sensor_msgs/msg/LaserScan',
    parent_frame: 'base_link',
    frame_id: 'lidar_link',
  },
  imu: {
    display_name: 'Body IMU',
    attachment_type: 'imu',
    capability: 'imu',
    provider_package: 'blacknode-perception',
    provider_component: 'imu',
    provider_adapter: 'ros2',
    topic: '/imu',
    message_type: 'sensor_msgs/msg/Imu',
    parent_frame: 'base_link',
    frame_id: 'imu_link',
  },
  gps: {
    display_name: 'GPS',
    attachment_type: 'gps',
    capability: 'gps',
    provider_package: 'blacknode-perception',
    provider_component: 'localization',
    provider_adapter: 'ros2',
    topic: '/fix',
    message_type: 'sensor_msgs/msg/NavSatFix',
    parent_frame: 'base_link',
    frame_id: 'gps_link',
  },
  microphone: {
    display_name: 'Microphone',
    attachment_type: 'microphone',
    capability: 'microphone',
    provider_package: 'blacknode-perception',
    provider_component: 'audio',
    provider_adapter: 'ros2',
    topic: '/audio',
    message_type: 'audio_common_msgs/msg/AudioData',
    parent_frame: 'base_link',
    frame_id: 'microphone_link',
  },
  custom: {
    display_name: 'ROS 2 attachment',
    attachment_type: 'custom',
    capability: 'sensor',
    provider_package: 'blacknode-ros2',
    provider_component: 'topics',
    provider_adapter: 'ros2',
    topic: '/sensor/data',
    message_type: 'std_msgs/msg/String',
    parent_frame: 'base_link',
    frame_id: 'sensor_link',
  },
}

function attachmentId(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  if (!normalized) return 'attachment'
  return /^[a-z]/.test(normalized) ? normalized.slice(0, 64) : `attachment_${normalized}`.slice(0, 64)
}

function emptyDraft(type: RobotAttachmentType = 'camera'): RobotAttachmentInput {
  const preset = PRESETS[type]
  return {
    ...preset,
    attachment_id: attachmentId(preset.display_name),
    x_m: 0,
    y_m: 0,
    z_m: 0,
    roll_rad: 0,
    pitch_rad: 0,
    yaw_rad: 0,
    hardware_id: '',
    required: true,
    enabled: true,
  }
}

function attachmentInterface(attachment: RobotAttachment) {
  return attachment.interfaces.find(item => item.kind === 'topic')
}

function editDraft(attachment: RobotAttachment): RobotAttachmentInput {
  const topic = attachmentInterface(attachment)
  const translation = attachment.mount.translation_m ?? [0, 0, 0]
  const rotation = attachment.mount.rotation_rpy_rad ?? [0, 0, 0]
  return {
    attachment_id: attachment.id,
    display_name: attachment.display_name,
    attachment_type: attachment.attachment_type,
    capability: attachment.capability,
    provider_package: attachment.provider.package,
    provider_component: attachment.provider.component,
    provider_adapter: attachment.provider.adapter || 'ros2',
    topic: topic?.topic || '',
    message_type: topic?.message_type || '',
    parent_frame: attachment.parent_frame,
    frame_id: attachment.frame_id,
    x_m: Number(translation[0] || 0),
    y_m: Number(translation[1] || 0),
    z_m: Number(translation[2] || 0),
    roll_rad: Number(rotation[0] || 0),
    pitch_rad: Number(rotation[1] || 0),
    yaw_rad: Number(rotation[2] || 0),
    hardware_id: attachment.hardware_identity.id || '',
    required: attachment.required,
    enabled: attachment.enabled !== false,
  }
}

function attachmentStatus(attachment: RobotAttachment) {
  if (attachment.enabled === false) {
    return { label: 'DISABLED', tone: 'disabled', message: 'This attachment is saved but excluded.' }
  }
  const check = attachment.last_check
  if (!check) {
    return { label: 'NOT CHECKED', tone: 'unchecked', message: 'Press Check ROS to inspect its live topic.' }
  }
  if (check.status === 'streaming') {
    return { label: 'STREAMING', tone: 'healthy', message: check.message }
  }
  if (check.status === 'topic_present') {
    return { label: 'TOPIC FOUND', tone: 'present', message: check.message }
  }
  return { label: 'ATTENTION', tone: 'attention', message: check.message }
}

export function RobotAttachmentsPanel({
  robot,
  onRobotUpdated,
}: {
  robot: HardwareDevice
  onRobotUpdated: (robot: HardwareDevice) => void
}) {
  const attachments = robot.attachments ?? []
  const [draft, setDraft] = useState<RobotAttachmentInput | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')

  const beginAdd = () => {
    setEditingId(null)
    setDraft(emptyDraft())
    setError('')
  }

  const beginEdit = (attachment: RobotAttachment) => {
    setEditingId(attachment.id)
    setDraft(editDraft(attachment))
    setError('')
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (!draft) return
    setBusyId(editingId || 'new')
    setError('')
    try {
      const result = editingId
        ? await api.updateRobotAttachment(robot.id, editingId, draft)
        : await api.createRobotAttachment(robot.id, draft)
      onRobotUpdated(result.device)
      setDraft(null)
      setEditingId(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusyId('')
    }
  }

  const remove = async (attachment: RobotAttachment) => {
    if (!window.confirm(
      `Remove “${attachment.display_name}” from ${robot.name}? This removes its saved attachment configuration; it does not uninstall system ROS 2 packages.`,
    )) return
    setBusyId(attachment.id)
    setError('')
    try {
      const result = await api.deleteRobotAttachment(robot.id, attachment.id)
      onRobotUpdated(result.device)
      if (editingId === attachment.id) {
        setDraft(null)
        setEditingId(null)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusyId('')
    }
  }

  const check = async (attachment: RobotAttachment) => {
    setBusyId(attachment.id)
    setError('')
    try {
      const result = await api.checkRobotAttachment(robot.id, attachment.id)
      onRobotUpdated(result.device)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusyId('')
    }
  }

  return (
    <section className="bn-robot-attachments" aria-label={`Attachments for ${robot.name}`}>
      <header className="bn-robot-attachments-head">
        <div>
          <strong>Attachments</strong>
          <span>
            Cameras and sensors mounted on this robot. Each attachment keeps its
            ROS topic, frame, provider, and physical mounting transform. Register
            the stream here after its ROS 2 driver is running.
          </span>
        </div>
        {!draft && (
          <button
            type="button"
            className="bn-device-action-button is-primary"
            onClick={beginAdd}
          >
            Add attachment
          </button>
        )}
      </header>

      {error && <div className="bn-run-error-line bn-device-error" role="alert">{error}</div>}

      {!draft && attachments.length === 0 && (
        <div className="bn-robot-attachments-empty">
          <strong>No attachments configured</strong>
          <span>Add a camera, depth camera, LiDAR, IMU, GPS, microphone, or ROS 2 device.</span>
          <button type="button" className="bn-device-action-button" onClick={beginAdd}>
            Add the first attachment
          </button>
        </div>
      )}

      {!draft && attachments.length > 0 && (
        <div className="bn-robot-attachment-list">
          {attachments.map(attachment => {
            const topic = attachmentInterface(attachment)
            const status = attachmentStatus(attachment)
            return (
              <article className="bn-robot-attachment-card" key={attachment.id}>
                <div className="bn-robot-attachment-card-head">
                  <div>
                    <span className="bn-robot-attachment-kind">
                      {ATTACHMENT_TYPES.find(item => item.value === attachment.attachment_type)?.label
                        || attachment.attachment_type}
                    </span>
                    <strong>{attachment.display_name}</strong>
                  </div>
                  <span
                    className={`bn-robot-attachment-status is-${status.tone}`}
                    title={status.message}
                  >
                    {status.label}
                  </span>
                </div>
                <dl className="bn-robot-attachment-facts">
                  <div>
                    <dt>ROS topic</dt>
                    <dd>{topic?.topic || 'Not configured'}</dd>
                  </div>
                  <div>
                    <dt>Message</dt>
                    <dd>{topic?.message_type || 'Not configured'}</dd>
                  </div>
                  <div>
                    <dt>Frame</dt>
                    <dd>{attachment.parent_frame} → {attachment.frame_id}</dd>
                  </div>
                  <div>
                    <dt>Provider</dt>
                    <dd>
                      {attachment.provider.package}/{attachment.provider.component}
                      {attachment.provider.adapter ? `@${attachment.provider.adapter}` : ''}
                    </dd>
                  </div>
                </dl>
                <p className="bn-robot-attachment-message">{status.message}</p>
                <div className="bn-robot-attachment-actions">
                  <button
                    type="button"
                    className="bn-device-action-button is-primary"
                    disabled={Boolean(busyId)}
                    onClick={() => void check(attachment)}
                  >
                    {busyId === attachment.id ? 'Checking…' : 'Check ROS'}
                  </button>
                  <button
                    type="button"
                    className="bn-device-action-button"
                    disabled={Boolean(busyId)}
                    onClick={() => beginEdit(attachment)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="bn-device-action-button is-danger"
                    disabled={Boolean(busyId)}
                    onClick={() => void remove(attachment)}
                  >
                    Remove
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      )}

      {draft && (
        <form className="bn-robot-attachment-form" onSubmit={save}>
          <div className="bn-robot-attachment-form-title">
            <div>
              <strong>{editingId ? 'Edit attachment' : 'Add attachment'}</strong>
              <span>
                Associate an existing ROS 2 stream with this robot, then use Check
                ROS to verify its publisher.
              </span>
            </div>
            <button
              type="button"
              className="bn-device-action-button"
              disabled={Boolean(busyId)}
              onClick={() => {
                setDraft(null)
                setEditingId(null)
                setError('')
              }}
            >
              Cancel
            </button>
          </div>

          <div className="bn-robot-attachment-form-grid">
            <label>
              <span>Attachment type</span>
              <select
                value={draft.attachment_type}
                disabled={Boolean(editingId)}
                onChange={event => {
                  const type = event.target.value as RobotAttachmentType
                  setDraft(emptyDraft(type))
                }}
              >
                {ATTACHMENT_TYPES.map(item => (
                  <option value={item.value} key={item.value}>{item.label}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Name</span>
              <input
                value={draft.display_name}
                onChange={event => {
                  const displayName = event.target.value
                  setDraft(current => current && ({
                    ...current,
                    display_name: displayName,
                    attachment_id: editingId
                      ? current.attachment_id
                      : attachmentId(displayName),
                  }))
                }}
                required
              />
            </label>
            <label>
              <span>Stable attachment ID</span>
              <input
                value={draft.attachment_id}
                disabled={Boolean(editingId)}
                onChange={event => setDraft(current => current && ({
                  ...current,
                  attachment_id: attachmentId(event.target.value),
                }))}
                required
              />
            </label>
            <label>
              <span>Capability</span>
              <input
                value={draft.capability}
                onChange={event => setDraft(current => current && ({
                  ...current,
                  capability: attachmentId(event.target.value),
                }))}
                required
              />
            </label>
            <label className="is-wide">
              <span>ROS 2 topic</span>
              <input
                value={draft.topic}
                placeholder="/camera/image_raw"
                onChange={event => setDraft(current => current && ({
                  ...current,
                  topic: event.target.value,
                }))}
                required
              />
            </label>
            <label className="is-wide">
              <span>ROS 2 message type</span>
              <input
                value={draft.message_type}
                placeholder="sensor_msgs/msg/Image"
                onChange={event => setDraft(current => current && ({
                  ...current,
                  message_type: event.target.value,
                }))}
                required
              />
            </label>
            <label>
              <span>Parent frame</span>
              <input
                value={draft.parent_frame}
                onChange={event => setDraft(current => current && ({
                  ...current,
                  parent_frame: event.target.value,
                }))}
                required
              />
            </label>
            <label>
              <span>Attachment frame</span>
              <input
                value={draft.frame_id}
                onChange={event => setDraft(current => current && ({
                  ...current,
                  frame_id: event.target.value,
                }))}
                required
              />
            </label>
          </div>

          <details className="bn-robot-attachment-advanced">
            <summary>Mount position and provider</summary>
            <div className="bn-robot-attachment-form-grid">
              {([
                ['x_m', 'X (m)'],
                ['y_m', 'Y (m)'],
                ['z_m', 'Z (m)'],
                ['roll_rad', 'Roll (rad)'],
                ['pitch_rad', 'Pitch (rad)'],
                ['yaw_rad', 'Yaw (rad)'],
              ] as const).map(([field, label]) => (
                <label key={field}>
                  <span>{label}</span>
                  <input
                    type="number"
                    step="any"
                    value={draft[field]}
                    onChange={event => setDraft(current => current && ({
                      ...current,
                      [field]: Number(event.target.value || 0),
                    }))}
                  />
                </label>
              ))}
              <label>
                <span>Provider package</span>
                <input
                  value={draft.provider_package}
                  onChange={event => setDraft(current => current && ({
                    ...current,
                    provider_package: event.target.value,
                  }))}
                  required
                />
              </label>
              <label>
                <span>Provider component</span>
                <input
                  value={draft.provider_component}
                  onChange={event => setDraft(current => current && ({
                    ...current,
                    provider_component: event.target.value,
                  }))}
                  required
                />
              </label>
              <label>
                <span>Provider adapter</span>
                <input
                  value={draft.provider_adapter}
                  onChange={event => setDraft(current => current && ({
                    ...current,
                    provider_adapter: event.target.value,
                  }))}
                />
              </label>
              <label>
                <span>Physical hardware ID</span>
                <input
                  value={draft.hardware_id}
                  placeholder="Serial number or stable path"
                  onChange={event => setDraft(current => current && ({
                    ...current,
                    hardware_id: event.target.value,
                  }))}
                />
              </label>
            </div>
          </details>

          <div className="bn-robot-attachment-switches">
            <label>
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={event => setDraft(current => current && ({
                  ...current,
                  enabled: event.target.checked,
                }))}
              />
              Enabled for this robot
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.required}
                onChange={event => setDraft(current => current && ({
                  ...current,
                  required: event.target.checked,
                }))}
              />
              Required for robot readiness
            </label>
          </div>

          <div className="bn-robot-attachment-form-actions">
            <button
              type="submit"
              className="bn-device-action-button is-primary"
              disabled={Boolean(busyId)}
            >
              {busyId ? 'Saving…' : editingId ? 'Save changes' : 'Add attachment'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
