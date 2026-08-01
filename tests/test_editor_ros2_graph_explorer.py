from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ros2_graph_explorer_hides_infrastructure_by_default():
    source = (
        ROOT / "editor" / "src" / "components" / "ROS2GraphExplorerNode.tsx"
    ).read_text(encoding="utf-8")

    assert "const [showInfrastructure, setShowInfrastructure] = useState(false)" in source
    assert "Show infrastructure" in source
    assert "Infrastructure hidden:" in source
    assert "rosapi" in source
    assert "rosbridge_websocket" in source
    assert "client_count" in source
    assert "connected_clients" in source


def test_ros2_graph_explorer_supports_robot_namespace_filtering():
    source = (
        ROOT / "editor" / "src" / "components" / "ROS2GraphExplorerNode.tsx"
    ).read_text(encoding="utf-8")

    assert "Namespace" in source
    assert 'placeholder="/my_robot/**"' in source
    assert "nameInNamespace" in source
    assert "topicInNamespace" in source


def test_ros2_graph_explorer_distinguishes_persistent_subscriber_from_monitor():
    source = (
        ROOT / "editor" / "src" / "components" / "ROS2GraphExplorerNode.tsx"
    ).read_text(encoding="utf-8")

    assert "const addSubscriber" in source
    assert "ROS2TopicSubscriber" in source
    assert "Add subscriber" in source
    assert "Add one-shot monitor" in source
