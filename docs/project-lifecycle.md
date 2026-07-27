# Project Lifecycle

Blacknode guides a robot application from the first installation through a
running deployment. Projects keep the workflow, paired robot, configuration,
deployment state, and generated artifacts together.

## 1. Start the editor

Install Blacknode on the computer where workflows will be built:

```powershell
git clone https://github.com/temiroff/Blacknode.git
cd Blacknode
.\start.bat
```

On macOS or Linux, run `./start.sh` from the cloned repository. The launcher
prepares the Python and editor dependencies, starts the backend and editor, and
opens Blacknode in the browser.

Create a Project from the **Projects** panel. The standard robot-deployment
setup is the default. Robot-learning projects can select the learning starter
when they also need collection, training, and simulation stages.

## 2. Add a device, then its robots

Select **Set up robot** from the Project's Next step and open **Devices**. Start
with the Jetson, Raspberry Pi, or Ubuntu computer that will run Blacknode
workflows.

For a local setup, choose **Add device → Local computer**, select the local
stack installation folder, and press **Add local computer**. Blacknode prepares
separate Runtime and Robot Hardware checkouts, Python environments,
authentication, and state; selects separate loopback ports; starts both
processes; verifies the Runtime manifest and the Hardware service's disconnected,
disarmed state; and pairs the Runtime automatically. Robot Hardware waits for a
physical robot configuration. Deployments, logs, monitoring, Projects, and
locally attached robots use the same device interfaces as a remote target. The
device card can pause, resume, check, and uninstall the managed local stack.
Uninstall removes checkout folders created by Blacknode and preserves existing
source checkouts.
Every managed device summary shows the Runtime and Hardware package cards in
the same layout. Each package reports its installed version and current
RUNNING, STOPPED, UNREACHABLE, or NOT INSTALLED state, with aligned Run/Stop,
Restart, Update, Reinstall, and Delete controls. Restart stops and starts only
the selected local package service. Deleting a local package removes its
environment while preserving its checkout and configuration for reinstall.
Runtime state is normalized across local and remote computers: a successful
health check reports RUNNING, a paused service reports STOPPED, and a failed
health check reports UNREACHABLE.
Robot connection status is binary in the device UI. CONNECTED requires a fresh
positive hardware or deployment report; every other completed connection check
shows DISCONNECTED. When an active deployment has not published fresh
connectivity telemetry, the detail explains that Blacknode treated the robot as
disconnected and asks the user to stop the deployment before verifying the
physical connection directly.
Robot Hardware also reports non-invasive serial-device presence while a
deployment owns the port. This lets a reconnected or unplugged robot move
between CONNECTED and DISCONNECTED without opening the serial bus twice.
On Windows, local Runtime and Hardware services use the windowless Python
launcher and continue in the background with output written to their package
log files.
Checking the device or package versions does not start a stopped service.
Remote package actions use the verified SSH identity and one unsaved password
field above the same two cards.
Remote Hardware Run, Stop, and Restart control every exact
`blacknode-hardware` service attached to that compute device. Stop first ends
active deployments and disarms each robot; Run and Restart return with motion
disarmed.

For remote SSH setup, choose **Add device → Remote SSH** and enter the
computer's IP address, username, and password. Blacknode first displays the
SSH host-key fingerprint for confirmation. After confirmation it installs the
runtime service, configures runtime port `8766` in UFW when UFW is active, and
pairs the runtime with the editor. The SSH password remains in memory for that
setup request and is not saved.

When another robot needs complete separation on the same Linux computer,
choose **Install a complete isolated robot stack** during the SSH review. The
new stack receives separate Runtime and Robot Hardware repositories,
environments, tokens, state, calibration, systemd service names, and ports.
Its Hardware environment starts empty. The new device card shows the
instance-scoped command for adding one newly connected stable serial path;
existing robots remain assigned to their current stacks.

For manual setup, install `blacknode-runtime` on the device, run
`./service.sh pairing`, and enter the printed runtime URL and token under
**Add device → Remote Manual**. You can add SSH management later from that
device's details with **Enable SSH controls**. Blacknode confirms the SSH host
key, verifies that the installed systemd runtime has the same port and runtime
device identity as the existing pairing, and then enables device lifecycle and
robot-service restart actions. The SSH password is used for that request and is
not saved.

Open the new square device card and choose **Add robot** for each hardware
service connected to that computer. Enter the robot URL and token printed by
`blacknode-hardware/pair.sh`. One device may contain several robots; each robot
remains a distinct deployment target and uses its parent device's shared
runtime. Pairing and discovery keep physical motion disarmed.

When a robot is added while a Project is active, Blacknode links that robot to
the Project automatically.

## 3. Choose the workflow

Return to the Project and select **Choose workflow**. Start with a tested
template or link a saved workflow. Templates declare their required Blacknode
packages, and deployment synchronizes those package requirements to the target
device.

The workflow remains portable. Robot-specific topics, device paths, providers,
and calibration belong to its selected robot profile and capability adapters.

## 4. Configure the robot

The Project's Configure stage opens the linked robot workflow. Select the robot
profile and the saved calibration for the physical hardware identity. Read-only
workflows can proceed when calibration is optional. Motion workflows require
the matching calibration, feedback capabilities, and safe limits.

## 5. Check and deploy

Open **Deploy**, select the linked device, and choose **Check setup**. Preflight
verifies:

- authenticated hardware and runtime services;
- required packages and capabilities;
- robot profile and physical hardware identity;
- selected and active calibration;
- disarmed state and deployment ownership; and
- the validated workflow revision.

After preflight succeeds, **Send to device** stages the workflow.
**Send & run** stages and explicitly starts it. Neither action bypasses the
hardware service's arming, freshness, limit, or shutdown checks.

## 6. Operate and iterate

The Project shows the running deployment and its owning device. Use
**Deployments** to inspect logs, stop, update, or roll back a revision. Stops
remain explicit because stopping a hardware workflow may release actuator
torque.
The robot card reports hardware connection separately from deployment status.
Connection can be connected, disconnected, checking, unknown, or unreachable;
deployment can be active, inactive, completed, failed, or absent. The latest
inactive deployment remains available on the Runtime and can restart after the
robot passes the same connected, disarmed, calibration, and ownership checks.

Update the graph, check setup again, and send a new revision to iterate. Project
artifacts retain evidence from datasets, training runs, policies, evaluations,
and simulations while their extension packages continue to own the underlying
files.
