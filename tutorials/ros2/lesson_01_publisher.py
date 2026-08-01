"""The smallest useful standalone ROS 2 node for the Blacknode tutorial."""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class Lesson01Publisher(Node):
    def __init__(self) -> None:
        # This is the name that will appear in the ROS graph.
        super().__init__("lesson_01_publisher")

        # Creating this publisher makes /lesson_01/message appear in the graph.
        self.publisher = self.create_publisher(String, "/lesson_01/message", 10)
        self.counter = 0

        # ROS calls publish_message once every second while this node spins.
        self.timer = self.create_timer(1.0, self.publish_message)

    def publish_message(self) -> None:
        self.counter += 1
        message = String()
        message.data = f"hello from lesson 01 #{self.counter}"
        self.publisher.publish(message)
        self.get_logger().info(f"Published: {message.data}")


def main() -> None:
    rclpy.init()
    node = Lesson01Publisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
