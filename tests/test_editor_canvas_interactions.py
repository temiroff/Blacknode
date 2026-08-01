from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mouse_wheel_zoom_remains_active_over_canvas_nodes():
    app_source = (ROOT / "editor" / "src" / "App.tsx").read_text(encoding="utf-8")
    explorer_source = (
        ROOT / "editor" / "src" / "components" / "ROS2GraphExplorerNode.tsx"
    ).read_text(encoding="utf-8")

    assert "zoomOnScroll={true}" in app_source
    assert 'noWheelClassName="bn-canvas-wheel-suppression-disabled"' in app_source
    assert 'className="bn-ros-explorer-content nodrag nowheel"' not in explorer_source


def test_topic_publisher_card_shows_live_state_and_stop_control():
    node_source = (
        ROOT / "editor" / "src" / "components" / "BlackNode.tsx"
    ).read_text(encoding="utf-8")
    store_source = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "topicPublisherActive" in node_source
    assert "LIVE • PUBLISHING" in node_source
    assert "onStopTopicPublisher" in node_source
    assert "topic-publisher:${owned('topic') || '/chatter'}" in store_source
    assert "function clearReplayDataPreservingRuntime" in store_source
    assert "clearReplayDataPreservingRuntime(n.data)" in store_source


def test_topic_subscriber_card_shows_live_state_messages_and_stop_control():
    node_source = (
        ROOT / "editor" / "src" / "components" / "BlackNode.tsx"
    ).read_text(encoding="utf-8")
    store_source = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "topicSubscriberActive" in node_source
    assert "LIVE • SUBSCRIBING" in node_source
    assert "onStopTopicSubscriber" in node_source
    assert "topic-subscriber:${owned('topic') || '/chatter'}" in store_source
    assert "n.data.type === 'ROS2TopicSubscriber'" in store_source


def test_ros2_python_node_card_shows_managed_live_state_and_stop_control():
    node_source = (
        ROOT / "editor" / "src" / "components" / "BlackNode.tsx"
    ).read_text(encoding="utf-8")
    store_source = (ROOT / "editor" / "src" / "store.ts").read_text(encoding="utf-8")

    assert "rosPythonActive" in node_source
    assert "ROS2 PYTHON RUNNING" in node_source
    assert "onStopROS2PythonNode" in node_source
    assert "n.data.type === 'ROS2PythonNode'" in store_source
    assert "node.data.params?.run_id ?? node.data.input_defaults?.run_id" in store_source
