# ROS 2 in Blacknode: a baby-step tutorial

This tutorial builds a small ROS 2 graph visually, then replaces the generated
publisher with a standalone Python `rclpy` program. Every completed step has
been exercised with the Blacknode ROS Docker backend.

## The four things to keep separate

```text
ROS 2 package
  └─ contains executable programs
       └─ a running executable creates ROS node(s)
            ├─ publishers
            ├─ subscriptions
            ├─ services
            └─ timers
```

- A **package** organizes source code and executable registrations.
- An **executable** is a program that ROS can start.
- A **ROS node** is a running participant in the ROS graph.
- A **topic** is a named channel shared by publisher and subscription endpoints.

A topic becomes discoverable when a running ROS node creates a publisher or
subscription for it. One ROS node can own several publishers, subscriptions,
services, and timers.

Blacknode workflow blocks are the visual configuration and lifecycle controls.
Some blocks start real ROS nodes; others inspect or process their data.

## Step 1: inspect the ROS graph

Add `ROS2GraphExplorer` and run its `graph` output. Its three tabs show:

- **Topics**: publishers → typed topic → subscribers
- **Nodes**: running ROS node names
- **Services**: available ROS service names and types

Keep **Show infrastructure** off while learning to hide rosbridge and ROS
middleware plumbing. Press **Refresh** after starting or stopping a ROS node.

Graph Explorer offers two different actions:

- **Add subscriber** creates a persistent named subscriber.
- **Add one-shot monitor** reads briefly for debugging and exits.

## Step 2: publish `/chatter`

Add `ROS2TopicPublisher` and set:

```text
action: start
node_name: step_02_publisher
topic: /chatter
msg_type: std_msgs/msg/String
payload: data: hello from Blacknode
rate_hz: 2
```

Run its `report` output. The card shows **LIVE • PUBLISHING**.

The ROS graph now contains:

```text
/step_02_publisher ──publishes──> /chatter
```

Use the card's **Stop** action to stop the managed publisher.

## Step 3: subscribe to `/chatter`

Add `ROS2TopicSubscriber` and set:

```text
action: start
node_name: step_03_subscriber
topic: /chatter
msg_type: std_msgs/msg/String
history: 10
```

Run its `report` output. The card shows **LIVE • SUBSCRIBING**. Its outputs have
different purposes:

- `latest`: the newest structured message dictionary
- `messages`: a bounded list of recent messages
- `received`: the total message count for this run
- `report`: lifecycle and backend status

The graph is now:

```text
/step_02_publisher ──publishes──> /chatter ──subscribed by──> /step_03_subscriber
```

This publisher and subscriber are reusable Blacknode-managed ROS processes.
The next steps create the ROS behavior directly in Python source code.

## Step 4: understand the standalone Python node

Open [lesson_01_publisher.py](lesson_01_publisher.py).

The program creates:

```text
Python file: lesson_01_publisher.py
ROS node:    /lesson_01_publisher
Publisher:   std_msgs/msg/String
Topic:       /lesson_01/message
Timer:       one publication per second
```

The node name comes from:

```python
super().__init__("lesson_01_publisher")
```

The publisher and topic come from:

```python
self.publisher = self.create_publisher(String, "/lesson_01/message", 10)
```

The timer asks ROS to call `publish_message` once per second:

```python
self.timer = self.create_timer(1.0, self.publish_message)
```

Finally, `rclpy.spin(node)` keeps the process alive so ROS can execute timers
and callbacks.

## Step 5: run the Python file from the canvas

Enable the `blacknode-ros2` **Processes** component if `ROS2PythonNode` is not
in the palette, then press **Refresh canvas**.

Add `ROS2PythonNode` and set:

```text
action: start
run_id: lesson_01_publisher
source_mode: file
script_path: tutorials/ros2/lesson_01_publisher.py
arguments:
```

Run its `report` output. The block:

1. resolves the workspace-relative file path;
2. validates the Python syntax;
3. copies the file into the ROS helper container when Docker is active;
4. starts it as a managed process;
5. exposes the latest 50 stdout/stderr lines through `logs`;
6. provides **ROS2 PYTHON RUNNING** and a direct **Stop** action.

Refresh Graph Explorer. It should show:

```text
/lesson_01_publisher ──publishes──> /lesson_01/message
```

The live log contains lines similar to:

```text
[lesson_01_publisher]: Published: hello from lesson 01 #12
```

`source_mode=inline` is also available. In that mode, place the Python program
in the block's `code` field. File mode is used here so the program remains easy
to edit, test, and later convert into a package.

## Step 6: read the Python node's messages

Reuse `ROS2TopicSubscriber` or add another one:

```text
action: start
node_name: lesson_01_reader
topic: /lesson_01/message
msg_type: std_msgs/msg/String
history: 10
```

Run `report`. Its `latest` output updates every second:

```json
{
  "data": "hello from lesson 01 #12"
}
```

The completed graph is:

```text
/lesson_01_publisher
        │ publishes
        ▼
/lesson_01/message
        │ subscribed by
        ▼
/lesson_01_reader
```

## Refresh and lifecycle rules

- **Refresh canvas** reloads node schemas and current managed-runtime state.
- **Refresh** inside Graph Explorer captures a new ROS topology snapshot.
- Editing a running Python file takes effect after stopping and starting its
  `ROS2PythonNode`, which recopies the selected file.
- Use each managed block's **Stop** action before deleting its canvas block.
- Use a unique `run_id` for every independently managed Python process.

## Step 7: one Python node with two topic endpoints

Keep the first lesson unchanged. Open
[lesson_02_pub_sub.py](lesson_02_pub_sub.py). This separate program
creates one ROS node with both a publisher and a subscription:

```text
                           /lesson_02_pub_sub
                        /                    \
       subscribes from /                      \ publishes to
                      ▼                        ▼
          /lesson_02/command              /lesson_02/status
```

The subscription callback remembers the newest command. Once per second, the
timer publishes a status message containing that command.

Add a new `ROS2PythonNode` block and set:

```text
action: start
run_id: lesson_02_pub_sub
source_mode: file
script_path: tutorials/ros2/lesson_02_pub_sub.py
arguments:
```

Run its `report` output, then refresh Graph Explorer. You should see the ROS
node `/lesson_02_pub_sub`, its publisher on `/lesson_02/status`, and its
subscription on `/lesson_02/command`.

Before any command is sent, its log will contain messages similar to:

```text
Published status: status #3; last command: <none>
```

## Step 8: send one command into the Python node

Add `ROS2TopicPublisher` and set:

```text
action: once
node_name: lesson_02_one_shot_sender
topic: /lesson_02/command
msg_type: std_msgs/msg/String
payload: data: start
count: 1
```

Run its `report` output once. The temporary `/lesson_02_one_shot_sender` ROS node
publishes one message and exits. The persistent `/lesson_02_pub_sub` receives
that message through its subscription callback.

Its log should change to messages similar to:

```text
Received command: start
Published status: status #17; last command: start
```

The complete message path is:

```text
/lesson_02_one_shot_sender
        │ publishes once
        ▼
/lesson_02/command
        │ subscribed by
        ▼
/lesson_02_pub_sub
        │ publishes repeatedly
        ▼
/lesson_02/status
```

The sender may disappear before Graph Explorer captures it because `once`
finishes immediately. The command topic remains visible while the persistent
subscription exists.

## Step 9: connect two custom Python ROS nodes

Keep `/lesson_02_pub_sub` running. Open
[lesson_03_command.py](lesson_03_command.py). This third lesson file
creates `/lesson_03_command`, which sends a new command every five seconds
and listens to the resulting status messages.

Add another `ROS2PythonNode` block and set:

```text
action: start
run_id: lesson_03_command
source_mode: file
script_path: tutorials/ros2/lesson_03_command.py
arguments:
```

Run its `report` output. The two persistent ROS nodes now communicate in both
directions:

```text
/lesson_03_command
        │ publishes every five seconds
        ▼
/lesson_02/command
        │
        ▼
/lesson_02_pub_sub
        │ publishes every second
        ▼
/lesson_02/status
        │
        └──────────────> /lesson_03_command
```

The third node's log should contain messages similar to:

```text
Sent command: command #1
Received status: status #42; last command: command #1
```

This is the first complete custom ROS application in the tutorial: two source
files create two persistent ROS nodes, and typed topics connect their publisher
and subscription endpoints.

## Step 10: build and run a real ROS 2 package

Lessons 1–3 ran source files directly. Lesson 4 introduces a standard ROS 2
Python workspace and package:

```text
lesson_04_workspace/
└─ src/
   └─ lesson_04_package/
      ├─ package.xml
      ├─ setup.py
      ├─ setup.cfg
      ├─ resource/lesson_04_package
      └─ lesson_04_package/
         ├─ __init__.py
         └─ publisher.py
```

Each part has one job:

- `package.xml` gives ROS the package name and dependencies.
- `setup.py` registers the executable name `publisher`.
- `setup.cfg` installs that executable where `ros2 run` expects it.
- `resource/lesson_04_package` adds the package to the ament index.
- `publisher.py` contains the `rclpy` node source code.

Reload the `blacknode-ros2` package from the editor's **Packages** panel, then
press **Refresh canvas**. Add `ROS2WorkspaceBuild` and set:

```text
workspace_path: tutorials/ros2/lesson_04_workspace
packages_select: lesson_04_package
timeout: 300
```

Run its `report` output. A successful build reports `built: true`, and its
`logs` output ends with a line similar to:

```text
Finished <<< lesson_04_package
```

Now add `ROS2Run` and set:

```text
action: start
run_id: lesson_04_publisher
workspace_path: tutorials/ros2/lesson_04_workspace
package: lesson_04_package
executable: publisher
arguments:
expected_topic: /lesson_04/message
wait_seconds: 10
```

Run its `report` output and refresh Graph Explorer. The graph should show:

```text
/lesson_04_publisher ──publishes──> /lesson_04/message
```

Use `ROS2TopicEcho` on `/lesson_04/message` to inspect its data. Use the Stop
action on `ROS2Run` before rebuilding or changing the packaged node.

The important new distinction is:

```text
package:    lesson_04_package
executable: publisher
ROS node:   /lesson_04_publisher
topic:      /lesson_04/message
```

## Next lesson

The next step adds a second executable and a ROS 2 launch file to this package.
One `ROS2Launch` block will then start both packaged nodes together.
