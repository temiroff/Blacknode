// Node types whose live output is a continuously-updating stream (a
// stream_url/preview that keeps changing while the node is running), as
// opposed to `live_capable` in general, which covers any node that accepts
// __run_mode__: "live" (background loops, controllers, etc). Keep this in
// sync with the actual `live=True` stream nodes in the Python registry.
export const LIVE_STREAM_NODE_TYPES = new Set([
  'Camera',
  'CameraROS2Subscribe',
  'CameraROS2Publish',
  'CameraROS2Http',
  'CV2ColorObjectStream',
  'DetectionStream',
  'DetectionYolo',
  'ReasoningStream',
  'CUDAImageFilterStream',
  'StreamPublisher',
])
