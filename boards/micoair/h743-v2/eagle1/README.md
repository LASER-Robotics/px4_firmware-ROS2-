# eagle1 — PX4 1.17.0 firmware for the MicoAir H743 v2 (LASER eagle drone)

PX4 **1.17.0** firmware with our own changes for the **MicoAir H743 v2** flight controller (FC), plus its parameters.
A new FC set up this way matches the one on the `real_livox` drone: it flies for real and in HIL (the real FC flying
the MuJoCo simulator).

---

## Installation prompt

Clone this repo on the `release/1.17-eagle1` branch, open your coding assistant in its folder and paste:

```text
Install the firmware and parameters from this repo on the MicoAir H743 v2 FC connected over USB (/dev/ttyACM0).
Follow boards/micoair/h743-v2/eagle1/README.md, steps 1 to 3 and 5:
1. Back up the FC's current parameters.
2. Check the binary's sha256 and flash it.
3. Load boards/micoair/h743-v2/eagle1/config/fc/referencia_real_livox.params and repeat until nothing is written.
5. Verify with boards/micoair/h743-v2/eagle1/scripts/fc_modo.sh estado.
Use only the scripts in boards/micoair/h743-v2/eagle1/scripts. Show the real output of each step. If something fails, stop and tell me what failed.
When done, list the step 4 calibrations I have to do in QGroundControl.
```

---

## Map: what is where

| Path (inside `boards/micoair/h743-v2/eagle1/`) | What it is | When it is used |
|---|---|---|
| `firmware/micoair_h743-v2_px4-1.17.0_pwmoutsim_tonobat_batcbrk_bidir4_tonos.px4` | **The firmware**, already built | Step 2: flashing |
| `config/fc/referencia_real_livox.params` | **All** FC parameters in real-flight mode | Step 3: configuring a new FC |
| `scripts/fc_params.py` | Read, back up and write parameters over USB | Steps 1, 3 and 5 |
| `scripts/rc_monitor.py` | Shows which channel each radio switch moves | Step 4, radio |
| `scripts/fc_modo.sh` | Switch the FC between real and HIL mode, with backup and verification | Daily use |
| `config/fc/modo_vuelo_real.params` | What differs between real and HIL mode, with the real-flight value | Applied by `fc_modo.sh real` |
| `config/fc/hil_real_livox.params` | The same, with the HIL value | Applied by `fc_modo.sh hil` |
| `config/fc/radio.params` · `bateria.params` · `dshot_bidir.params` · `logging.params` · `solo_mtf02p.params` · `position_sala.params` | Parameters by topic, with the reason for each value | Reference |
| the rest of this branch | Source of the firmware: PX4 v1.17.0 plus the `eagle1:` commit | Reference |

## What the firmware changes with respect to official PX4

| Change | Why |
|---|---|
| `pwm_out_sim` module enabled on the board | HIL: without it the FC never sends motor commands back to the simulator |
| Bidirectional DShot: RPM of all 4 motors in every frame | Per-motor RPM at 666 Hz (official PX4: one motor per frame, 166 Hz) |
| Bidirectional DShot: recovery of stuck AM32 ESCs | An ESC left in its bootloader after an FC reboot recovers by itself |
| `CBRK_SUPPLY_CHK` no longer silences the battery alarm | Low, critical and emergency battery warnings (this board does not measure its own supply) |
| The battery emergency beep is not cut off | No silent flying on an empty battery |
| Arming tones | Arming accepted: one short beep. Rejected: two low beeps |
| Logger: `esc_status` without the 200 Hz cap | RPM is logged at its real rate |

---

## Requirements

- MicoAir H743 v2 FC (board id 1179) with its factory bootloader.
- A microSD card in the FC: this board stores its parameters on the card (`/fs/microsd/params`), and the flight logs too.
- Linux PC with `python3`, `pymavlink` and `pyserial`: `pip install pymavlink pyserial`.
- USB cable to the FC. QGroundControl closed while the scripts run: the port must be free.
- Propellers off.

Run the commands below from `boards/micoair/h743-v2/eagle1/`.

## Step 1 — Back up the FC as it comes

```bash
python3 scripts/fc_params.py dump ~/new_fc_factory.params
```

## Step 2 — Flash the firmware

```bash
sha256sum firmware/micoair_h743-v2_px4-1.17.0_pwmoutsim_tonobat_batcbrk_bidir4_tonos.px4
#  must print: 3e56493eac7d3c483280744f9558ecd6991d6a41b838b963a0dffcd62cba0c15
python3 ../../../../Tools/px_uploader.py --force --port /dev/ttyACM0 \
    firmware/micoair_h743-v2_px4-1.17.0_pwmoutsim_tonobat_batcbrk_bidir4_tonos.px4
```

`--force` is required: the bootloader accepts 1920 KB and the board declares 1792 KB. The board id (1179) is still
verified.

Check: the FC reboots, shows up again at `/dev/ttyACM0` and answers
`python3 scripts/fc_params.py get SYS_AUTOSTART`.

## Step 3 — Load the parameters

```bash
python3 scripts/fc_params.py apply --reboot config/fc/referencia_real_livox.params
```

It writes only what differs and reboots the FC. Repeat the same command until it writes nothing: some parameters
only exist after a reboot.

The file holds the complete configuration of the `real_livox` drone in real-flight mode: vehicle type, gains, radio,
battery, bidirectional DShot, ports, estimator and logging. It assumes a drone with the same components (motors,
ESCs, propellers, 6S battery and sensors).

## Step 4 — Calibrate this board

The file from step 3 carries the calibration of another board. On the new FC, redo with QGroundControl:

1. Accelerometer, gyroscope and level horizon.
2. Radio: stick calibration. Then confirm the switches with `python3 scripts/rc_monitor.py /dev/ttyACM0`:
   ARM, MODE (POSITION / ALTITUDE), OFFBOARD and KILL must move the channels listed in `config/fc/radio.params`.
3. Battery: voltage divider and amps per volt (`BAT1_V_DIV`, `BAT1_A_PER_V`), against a multimeter.
4. ESCs: every AM32 ESC with bidirectional DShot enabled and the right spin direction.

## Step 5 — Verify

```bash
bash scripts/fc_modo.sh estado      # read-only: must report that the FC is in real mode
```

With the battery connected and propellers off, wait 10 s and check in the QGroundControl MAVLink console:

| Command | What must show |
|---|---|
| `ver all` | PX4 1.17.0 and the MicoAir H743 v2 board |
| `dshot status` | all 4 channels online, with RPM when spinning |
| `listener esc_status` | RPM of the 4 motors |
| `listener battery_status` | voltage equal to the multimeter's |
| `uxrce_dds_client status` | connected, once the onboard computer runs the agent |

---

## Connections the firmware expects

| FC port | What goes there | Configuration |
|---|---|---|
| USB | PC: parameters, QGroundControl, HIL | — |
| TELEM2 (UART4) | Onboard computer (Jetson, `/dev/ttyTHS1`): uXRCE-DDS agent | 921600 baud, `UXRCE_DDS_CFG 102`, domain 11 |
| TELEM3 | MicoAir MTF-02P sensor (optical flow + range) | 115200 baud, `MAV_2_CONFIG 103` |
| RC port | ELRS receiver | `RC_PORT_CONFIG 300` |
| Outputs 1-4 | AM32 4-in-1 ESC, bidirectional DShot600 | `DSHOT_BIDIR_EN 1` |

TELEM2 to the Jetson (40-pin header): pin 6 GND, pin 8 (Jetson TX) to FC RX, pin 10 (Jetson RX) to FC TX.

## Switching between real flight and HIL

```bash
bash scripts/fc_modo.sh estado     # which mode it is in (read-only)
bash scripts/fc_modo.sh hil        # HIL: the FC flies the simulator. Propellers off
bash scripts/fc_modo.sh real       # real flight
```

Each switch makes a full backup, writes what differs, reboots and verifies parameter by parameter.

## Known pitfalls

- After connecting the battery, wait about 10 s before arming: the FC refuses to arm while an ESC is not responding.
- If a motor does not respond after rebooting the FC with the battery on, the recovery brings it back by itself in a
  few seconds (`dshot status` shows how many recoveries happened). If not, unplug and replug the battery.
- In HIL mode the real MTF-02P sensor is switched off (`MAV_2_CONFIG 0`): before a real flight, `fc_modo.sh real`.
- Between two HIL sessions the FC must be rebooted: otherwise its estimator stays diverged and it will not arm.

## Status of this recipe

Tested on the `real_livox` drone's FC (same binary, same scripts). Not yet tested on a second, factory-fresh FC.
