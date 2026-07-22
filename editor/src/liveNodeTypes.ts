// Node types whose live output is a continuously-updating stream (a
// stream_url/preview that keeps changing while the node is running), as
// opposed to `live_capable` in general, which covers any node that accepts
// __run_mode__: "live" (background loops, controllers, etc). Keep this in
// sync with the actual `live=True` stream nodes in the Python registry.
export const LIVE_STREAM_NODE_TYPES = new Set([
  'Camera',
  'ROS2ImageStream',
  'ROS2USBCamera',
  'ROS2WebVideoStream',
  'CV2ColorObjectStream',
  'ReasoningStream',
  'CUDAImageFilterStream',
  'StreamPublisher',
])
