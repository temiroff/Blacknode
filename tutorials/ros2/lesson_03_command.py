"""ROS 2 tutorial lesson three: communicate with another Python node."""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class Lesson03Command(Node):
    """Send commands and listen for status responses."""

    def __init__(self) -> None:
        super().__init__("lesson_03_command")

        # Send commands to the subscription owned by lesson_02_pub_sub.
        self.command_publisher = self.create_publisher(
            String,
            "/lesson_02/command",
            10,
        )

        # Receive the status published by lesson_02_pub_sub.
        self.status_subscription = self.create_subscription(
            String,
            "/lesson_02/status",
            self.receive_status,
            10,
        )

        self.command_number = 0

        # Send a new command every five seconds.
        self.command_timer = self.create_timer(5.0, self.publish_command)

    def publish_command(self) -> None:
        """Publish the next numbered command."""
        self.command_number += 1

        message = String()
        message.data = f"command #{self.command_number}"

        self.command_publisher.publish(message)
        self.get_logger().info(f"Sent command: {message.data}")

    def receive_status(self, message: String) -> None:
        """Run whenever the other ROS node publishes a status message."""
        self.get_logger().info(f"Received status: {message.data}")


def main(args=None) -> None:
    """Start ROS, run the node, and cleanly shut it down."""
    rclpy.init(args=args)
    node = Lesson03Command()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
