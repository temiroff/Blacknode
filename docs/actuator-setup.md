# Actuator Setup

The first shelf button, **Actuator Setup**, opens a Local USB scanner. Pick the
USB port and press **Scan**. Each responding servo appears as a separate connected
node with its own ID, torque state, position, voltage, temperature and settings.
Discovery and per-servo calibration/testing need only the USB port. A robot
profile can be selected later for whole-robot calibration and testing.
Unreadable replies appear as **Unresolved ID** cards while discovery continues.
These show the attempted address and error; they do not claim a physical servo
count or confirmed duplicate. Servos sharing an ID must be connected one at a
time to receive unique IDs before the full chain can be identified separately.
The workflow is also available under **Templates → Actuator Setup**. Existing
shelves receive the button first while keeping their other shortcuts; it remains
customizable through the shelf's settings.

1. Select the USB adapter. Stop other sessions using that adapter, check power
   and wiring, and press **Scan**. Rescanning refreshes existing servo cards,
   adds newly discovered IDs and flags previously seen IDs that no longer respond.
2. To program an ID, support the arm and power off before changing wiring.
   Connect only the selected actuator, power on and scan again. Enter **New ID**
   on its servo card and press **Set ID**. Keep the isolated actuator supported;
   changing its ID retires the assembly's saved calibration.
3. Power off, reconnect the complete arm and rescan. Resolve missing IDs, open
   **Calibration and motion test** on a servo card, select the robot profile and
   press **Calibrate** to record new hand-guided limits and home.
4. Press **Open motion test** to open that servo in Servo Debug Monitor. Motion
   requires its explicit **Arm** action, fresh feedback and calibrated limits.

New IDs can be entered directly from 1–253. Robot profiles must match the final
joint IDs before calibration and motion. Initial ID programming supports STS3215;
unsupported models remain visible for diagnosis. Discovery is bounded, scans
IDs 0–253 and preserves torque. Running or reopening this workflow performs
no physical operation until an operator presses a control.

**Hardware settings** shows a read-only snapshot of the baud rate code, position
register limits, torque limit, operating mode and EEPROM lock for supported
models. These raw limits are separate from calibrated safe motion limits.
Use **Advanced** on the USB scanner to change baud rate or refresh USB ports.

## Per-servo calibration, test slider and saved poses

The card opens on **1. Set ID**, with the New ID field and assignment controls
visible first. **2. Calibrate / test** contains the motion and capture controls;
disabled actions explain the missing prerequisite beside the button.
ID setup uses **New ID → Set ID**, with no confirmation checkboxes or manual
scan-expiry step. The button is the explicit assignment action after the inline
isolation/support and calibration-reset instructions. Its owning control scans
the bus, checks the selected ID and torque, writes, and verifies the result.

Each servo card has **Calibration and test** controls. Capture **Min** and **Max**
from fresh measurements while the servo is supported and torque is released.
Either tick direction is accepted. Use comfortable positions clear of mechanical
stops. Testing uses those exact endpoints as command limits. Existing setup files
also use their exact captures when reopened; saving retires the old automatic
20-tick inset. **Home** is optional:
an interior capture supplies the test origin; otherwise the midpoint is calculated
for tick-to-angle conversion. This calculated center does not replace a captured
Home or command the motor to move there. Partial points and named poses can also
be saved with **Save states**.

Before arming, the slider follows the motor's measured position as you move it
by hand, showing the full raw tick range even before calibration is saved.
Read-only feedback refreshes while the panel is visible and pauses while another
control is working. Connection errors replace the live status. Capture buttons
read the current position again; captured points are retained as drafts across
reloads. **Arm** validates and saves a complete range before enabling torque;
**Save states** is also available separately.

After **Arm**, the slider controls the target. The Arm button is the
explicit authorization; there is no extra checkbox. Use the calibrated actuator
with its unique ID and keep the assembly supported. Arm holds the measured
position anywhere within the captured endpoints, including either endpoint.
It holds still until a slider command arrives. Each new slider target is sent
directly to the servo's position controller, within the saved limits. The driver
sets and verifies a finite 180°/s speed ceiling, acceleration 50 and zero goal
time in the same RAM command. The servo controls the movement between targets.
New targets replace pending targets immediately; the managed loop checks
feedback on a 20 ms cadence, subject to USB latency.
The UI uses fresh shared feedback for acknowledgements and updates readings
every 100 ms. **Stop** releases torque and
ends the session. Closing or hiding the controls stops it; a managed three-second
lease also releases torque if the UI disconnects. Stale requests and invalid
feedback disarm the test. STS3215 position mode must be verified before arming.

The slider spans the captured Min/Max ticks and follows their direction, including
decreasing tick values from Min to Max. Both exact endpoints are reachable targets;
commands outside them are rejected.
While calibration controls are open, the card's position and torque fields use
live feedback; scan-only values are labeled as scan snapshots. Unavailable live
feedback displays an unknown state instead of an old torque reading.

Enter a **Pose name**, press **Capture pose**, then stop any active test and press
**Save states**. Captures read measured positions, including while testing;
they do not save the requested slider value as if it were feedback. Select a
pose to preview its target before moving. Saved poses outside the calibrated
range are clamped to that range for testing.

State files live under the robot data directory's `actuator_setups/` folder,
keyed by USB hardware identity, provider and servo ID, with the actuator model
recorded. They load when the same servo card is reopened. ID assignment retires
these files alongside existing assembly calibration. Replacing a same-model
actuator at the same address requires recapturing calibration; these servos do
not expose an individual serial identity through this setup protocol. Whole-robot
profile calibration remains available from the card's expandable controls.

Assignment retires saved calibration files for the selected physical USB
identity into `calibrations/retired/`, preserving them for review while requiring
new calibration for the changed assembly. It verifies EEPROM relocking and the
new ID and keeps uncertain results visible. Each assignment uses a fresh,
single-use discovery token for legacy clients; the current **Set ID** button
performs fresh discovery on every click. It never enables torque or commands motion.

## Delivery

Select the USB scanner or a servo card and drag a corner to resize it. The
controls fill the available space, with scrolling available inside smaller
cards. Save the workflow to retain the card sizes.

Managed Runtime release decision: **no Runtime release for this workstation
Local USB workflow**. The editor UI and editor-server control routes run on the
workstation; the robot and driver changes load through the existing package
contract. This change does not add managed-device commissioning or modify the
device source lock. Local verification does not publish a release. A future
managed-device delivery must verify its actual Software update controls and
follow the owning package/Runtime release sequence in `AGENTS.md`.
