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

For automatic setup, choose **Add device → Automatic SSH** and enter the
computer's IP address, username, and password. Blacknode first displays the
SSH host-key fingerprint for confirmation. After confirmation it installs the
runtime service, configures runtime port `8766` in UFW when UFW is active, and
pairs the runtime with the editor. The SSH password remains in memory for that
setup request and is not saved.

For manual setup, install `blacknode-runtime` on the device, run
`./service.sh pairing`, and enter the printed runtime URL and token under
**Add device → Pair manually**.

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

Update the graph, check setup again, and send a new revision to iterate. Project
artifacts retain evidence from datasets, training runs, policies, evaluations,
and simulations while their extension packages continue to own the underlying
files.
