import { useState, type FormEvent } from 'react'
import {
  api,
  type HardwareDevice,
  type RobotAttachment,
  type RobotAttachmentInput,
  type RobotAttachmentProviderProfile,
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
  | 'provider_profile'
  | 'topic'
  | 'message_type'
  | 'parent_frame'
  | 'frame_id'
> & Partial<Pick<
  RobotAttachmentInput,
  | 'camera_info_topic'
  | 'depth_topic'
  | 'point_cloud_topic'
  | 'launch_package'
  | 'launch_target'
  | 'launch_arguments'
>>

const ATTACHMENT_TYPES: Array<{ value: RobotAttachmentType; label: string }> = [
  { value: 'camera', label: 'Camera' },
  { value: 'depth_camera', label: 'Depth camera' },
  { value: 'lidar', label: 'LiDAR' },
  { value: 'imu', label: 'IMU' },
  { value: 'gps', label: 'GPS' },
  { value: 'microphone', label: 'Microphone' },
  { value: 'custom', label: 'Custom ROS 2 device' },
]

const CAMERA_PROFILES: Array<{
  value: RobotAttachmentProviderProfile
  label: string
}> = [
  { value: 'usb_cam', label: 'USB camera · Blacknode starts it' },
  { value: 'rosorin_depth', label: 'ROSOrin RGB-D · Blacknode starts it' },
  { value: 'existing_topics', label: 'Existing ROS 2 topics' },
  { value: 'custom_launch', label: 'Custom ROS 2 launch' },
]

const PRESETS: Record<RobotAttachmentType, AttachmentPreset> = {
  camera: {
    display_name: 'Front camera',
    attachment_type: 'camera',
    capability: 'camera',
    provider_package: 'blacknode-perception',
    provider_component: 'camera',
    provider_adapter: 'ros2',
    provider_profile: 'usb_cam',
    topic: '/camera/image_raw',
    camera_info_topic: '/camera/camera_info',
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
    provider_profile: 'rosorin_depth',
    topic: '/depth_cam/rgb0/image_raw',
    camera_info_topic: '/depth_cam/rgb0/camera_info',
    depth_topic: '/depth_cam/depth0/image_raw',
    point_cloud_topic: '/depth_cam/depth0/points',
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
    provider_profile: 'existing_topics',
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
    provider_profile: 'existing_topics',
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
    provider_profile: 'existing_topics',
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
    provider_profile: 'existing_topics',
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
    provider_profile: 'existing_topics',
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
    camera_info_topic: preset.camera_info_topic || '',
    depth_topic: preset.depth_topic || '',
    point_cloud_topic: preset.point_cloud_topic || '',
    launch_package: preset.launch_package || '',
    launch_target: preset.launch_target || '',
    launch_arguments: preset.launch_arguments || [],
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
  const topicForRole = (role: 'camera_info' | 'depth' | 'points') =>
    attachment.interfaces.find(item => item.role === role)?.topic || ''
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
    provider_profile: attachment.service?.profile
      || attachment.provider.profile
      || 'existing_topics',
    topic: topic?.topic || '',
    message_type: topic?.message_type || '',
    camera_info_topic: topicForRole('camera_info'),
    depth_topic: topicForRole('depth'),
    point_cloud_topic: topicForRole('points'),
    launch_package: attachment.service?.launch_package || '',
    launch_target: attachment.service?.launch_target || '',
    launch_arguments: attachment.service?.launch_arguments || [],
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

  const start = async (attachment: RobotAttachment) => {
    setBusyId(attachment.id)
    setError('')
    try {
      const result = await api.startRobotAttachment(robot.id, attachment.id)
      onRobotUpdated(result.device)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusyId('')
    }
  }

  const stop = async (attachment: RobotAttachment) => {
    setBusyId(attachment.id)
    setError('')
    try {
      const result = await api.stopRobotAttachment(robot.id, attachment.id)
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
            ROS topics, frame, provider, and physical mounting transform. Blacknode
            can start managed camera providers independently from motion workflows.
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
            const profile = attachment.service?.profile
              || attachment.provider.profile
              || 'existing_topics'
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
                    <dt>Primary ROS topic</dt>
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
                  <div>
                    <dt>Lifecycle</dt>
                    <dd>{profile}</dd>
                  </div>
                </dl>
                <p className="bn-robot-attachment-message">{status.message}</p>
                <div className="bn-robot-attachment-actions">
                  {profile !== 'existing_topics' && (
                    attachment.last_check?.service_state === 'running' ? (
                      <button
                        type="button"
                        className="bn-device-action-button"
                        disabled={Boolean(busyId)}
                        onClick={() => void stop(attachment)}
                      >
                        {busyId === attachment.id ? 'Stopping…' : 'Stop camera'}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="bn-device-action-button is-primary"
                        disabled={Boolean(busyId) || attachment.enabled === false}
                        onClick={() => void start(attachment)}
                      >
                        {busyId === attachment.id ? 'Starting…' : 'Start camera'}
                      </button>
                    )
                  )}
                  <button
                    type="button"
                    className="bn-device-action-button"
                    disabled={Boolean(busyId)}
                    onClick={() => void check(attachment)}
                  >
                    {busyId === attachment.id ? 'Working…' : 'Check ROS'}
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
                Choose who starts the provider, declare its streams, then verify
                live publishers from the same panel.
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
              <span>Provider lifecycle</span>
              <select
                value={draft.provider_profile}
                onChange={event => {
                  const providerProfile = event.target.value as RobotAttachmentProviderProfile
                  setDraft(current => current && ({
                    ...current,
                    provider_profile: providerProfile,
                    ...(providerProfile === 'rosorin_depth' ? {
                      topic: '/depth_cam/rgb0/image_raw',
                      camera_info_topic: '/depth_cam/rgb0/camera_info',
                      depth_topic: '/depth_cam/depth0/image_raw',
                      point_cloud_topic: '/depth_cam/depth0/points',
                    } : {}),
                  }))
                }}
              >
                {CAMERA_PROFILES.map(profile => (
                  <option value={profile.value} key={profile.value}>{profile.label}</option>
                ))}
              </select>
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
            {(draft.attachment_type === 'camera' || draft.attachment_type === 'depth_camera') && (
              <>
                <label className="is-wide">
                  <span>Camera info topic · optional</span>
                  <input
                    value={draft.camera_info_topic}
                    placeholder="/camera/camera_info"
                    onChange={event => setDraft(current => current && ({
                      ...current,
                      camera_info_topic: event.target.value,
                    }))}
                  />
                </label>
                <label className="is-wide">
                  <span>Depth image topic · required for depth camera</span>
                  <input
                    value={draft.depth_topic}
                    placeholder="/depth_cam/depth0/image_raw"
                    onChange={event => setDraft(current => current && ({
                      ...current,
                      depth_topic: event.target.value,
                    }))}
                    required={draft.attachment_type === 'depth_camera'}
                  />
                </label>
                <label className="is-wide">
                  <span>Point cloud topic · optional</span>
                  <input
                    value={draft.point_cloud_topic}
                    placeholder="/depth_cam/depth0/points"
                    onChange={event => setDraft(current => current && ({
                      ...current,
                      point_cloud_topic: event.target.value,
                    }))}
                  />
                </label>
              </>
            )}
            {draft.provider_profile === 'custom_launch' && (
              <>
                <label>
                  <span>ROS 2 launch package</span>
                  <input
                    value={draft.launch_package}
                    onChange={event => setDraft(current => current && ({
                      ...current,
                      launch_package: event.target.value,
                    }))}
                    required
                  />
                </label>
                <label>
                  <span>Launch file</span>
                  <input
                    value={draft.launch_target}
                    placeholder="camera.launch.py"
                    onChange={event => setDraft(current => current && ({
                      ...current,
                      launch_target: event.target.value,
                    }))}
                    required
                  />
                </label>
                <label className="is-wide">
                  <span>Launch arguments · one per line</span>
                  <textarea
                    value={draft.launch_arguments.join('\n')}
                    onChange={event => setDraft(current => current && ({
                      ...current,
                      launch_arguments: event.target.value.split('\n'),
                    }))}
                  />
                </label>
              </>
            )}
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
