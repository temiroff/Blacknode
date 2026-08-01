from blacknode.node import Int, List, Text, node


@node(
      name="MyFirstNode",
      category="My Nodes",
      inputs={
          "messages": List,
          "times": Int(default=2),
      },
      outputs={"result": Text},
  )
def my_first_node(messages: list, times: int = 2) -> str:
      if not messages:
          return "No ROS message received"

      message = str(messages[0]).strip()
      if message.startswith("data:"):
          message = message.removeprefix("data:").strip()

      text = f"ROS said: {message}"
      return " | ".join([text] * max(1, int(times)))