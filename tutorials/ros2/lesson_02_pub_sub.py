"""ROS 2 tutorial lesson two: one node that publishes and subscribes."""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class Lesson02PubSub(Node):
    """Receive commands and publish a status message once per second."""

    def __init__(self) -> None:
        # This is the name that appears in the live ROS graph.
        super().__init__("lesson_02_pub_sub")

        # A publisher is an output endpoint owned by this ROS node.
        self.publisher = self.create_publisher(
            String,
            "/lesson_02/status",
            10,
        )

        # A subscription is an input endpoint owned by the same ROS node.
        # ROS calls receive_command whenever a new command arrives.
        self.subscription = self.create_subscription(
            String,
            "/lesson_02/command",
            self.receive_command,
            10,
        )

        self.last_command = "<none>"
        self.counter = 0

        # ROS calls publish_status once per second while the node is spinning.
        self.timer = self.create_timer(1.0, self.publish_status)

    def receive_command(self, message: String) -> None:
        """Remember and display the newest command."""
        self.last_command = message.data
        self.get_logger().info(f"Received command: {message.data}")

    def publish_status(self) -> None:
        """Publish a status message containing the last received command."""
        self.counter += 1

        message = String()
        message.data = (
            f"status #{self.counter}; last command: {self.last_command}"
        )

        self.publisher.publish(message)
        self.get_logger().info(f"Published status: {message.data}")


def main(args=None) -> None:
    """Start ROS, run the node, and cleanly shut it down."""
    rclpy.init(args=args)
    node = Lesson02PubSub()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
