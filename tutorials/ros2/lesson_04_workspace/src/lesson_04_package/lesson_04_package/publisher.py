"""Lesson 04: a ROS 2 publisher installed as a package executable."""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class Lesson04Publisher(Node):
    def __init__(self) -> None:
        super().__init__("lesson_04_publisher")
        self.publisher = self.create_publisher(String, "/lesson_04/message", 10)
        self.counter = 0
        self.timer = self.create_timer(1.0, self.publish_message)

    def publish_message(self) -> None:
        self.counter += 1
        message = String()
        message.data = f"hello from packaged lesson 04 #{self.counter}"
        self.publisher.publish(message)
        self.get_logger().info(f"Published: {message.data}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Lesson04Publisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
