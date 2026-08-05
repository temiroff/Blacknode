export type SpatialViewerRole =
  | 'legacy'
  | 'generic'
  | 'lidar'
  | 'depth-cloud'
  | 'reconstruction'
  | 'fusion'
  | 'map'

export const SPATIAL_VIEWER_TYPES = new Set([
  'Viewer',
  'GenericViewer',
  'LiDARViewer',
  'DepthCloudViewer',
  'ReconstructionViewer',
  'FusionViewer',
  'MapViewer',
  'SLAM',
])

export const MANAGED_SPATIAL_VIEWER_TYPES = new Set([
  'Viewer',
  'LiDARViewer',
  'DepthCloudViewer',
  'ReconstructionViewer',
  'FusionViewer',
  'MapViewer',
])

export const IMAGE_SENSOR_VIEWER_TYPES = new Set(['CameraViewer', 'DepthViewer'])

export const VIEWER_NODE_TYPES = new Set([
  ...SPATIAL_VIEWER_TYPES,
  ...IMAGE_SENSOR_VIEWER_TYPES,
  'IMUViewer',
])

export function spatialViewerRole(type: string): SpatialViewerRole {
  if (type === 'GenericViewer') return 'generic'
  if (type === 'LiDARViewer') return 'lidar'
  if (type === 'DepthCloudViewer') return 'depth-cloud'
  if (type === 'ReconstructionViewer') return 'reconstruction'
  if (type === 'FusionViewer') return 'fusion'
  if (type === 'MapViewer' || type === 'SLAM') return 'map'
  return 'legacy'
}
