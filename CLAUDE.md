# WildWilly / willy-rover

Six-wheel rocker-bogie rover. Raspberry Pi 5 host ("willie") with an AI HAT+ 2
(Hailo-10H), a 5-DOF arm, one non-isolated I²C segment of ten devices, and two Pico 2 W
co-processors on UART. Build is complete; work now is live verification and software.

**Authority order:** a live measurement beats `config.py`; `config.py` (and the rest of
the code) beats any document; the three design docs beat this file. If you find a
disagreement, fix the loser.

---

## How to work

### Documents

- The design set is three companion documents, kept in sync:
  - `docs/WildWilly_Master_Hardware_Design_v2.0.md` — as-built hardware, rails, pinouts,
    BOM, pin-to-pin schedule (§16), standing rules (§12), open items (§14).
  - `docs/WildWilly_Software_Design_v1.0.md` — modules, control layering, FSM, safety
    gate, known gaps S-1…S-10, open items (§12).
  - `docs/WildWilly_Functional_Requirements_v3.1.md` — requirements and verification.
  Filenames keep their old version numbers so cross-references stay valid; the Revision
  field inside each is authoritative.
- **Docs and this file describe the rover as built, in present tense.** No history, no
  dated change notes, no "was/now/superseded", no removed parts. Git holds the history.
- **When you change a constant, part, address or decision, `grep -rn` the OLD value
  across the whole repo** — all three docs, this file, the User Guide, the bench
  procedures and the code — before calling it done.
- Bench procedures with blank result fields are in
  `docs/WildWilly_Bench_Test_Procedures.md`. Read the relevant one before any hardware
  item; write results into that file and commit them.
- `docs/archive/` is not authoritative. Do not cite it.

### Code to the rover

- **Code reaches the rover by git only:** commit → `git push origin main` →
  `ssh hhimmel@willie.local 'cd ~/rover && git pull'`. When the owner says "commit",
  do all three.
- **Never `scp` into `~/rover`.** It has an hourly auto-backup (`scripts/auto_backup.sh`)
  that commits and pushes whatever it finds, so copied files land with different line
  endings. Throwaway probes go in `/tmp`. If a pull conflicts, check
  `git diff --ignore-cr-at-eol --stat origin/main` first — empty means line endings only,
  and origin wins.
- **Never `git add -A` / `git add .`** — stage named files only.
- **Never read, print, commit or edit anything under `secrets/`** (or `.env`). Credentials
  are never in `config.py` — only env-var names and file paths.
- Rover install: `/home/hhimmel/rover`, venv `/home/hhimmel/rover/venv/bin/python3`,
  run by `willy-rover.service`.

### Tests

- Off-hardware, always: `WILLY_SIMULATE=1` (gates every real I²C/GPIO/UART open; needs
  `pygame` and `networkx`). On willie:
  `cd ~/rover && WILLY_SIMULATE=1 venv/bin/python3 -m pytest tests/`.
- The suite's home is willie. On Windows a subset fails for environment reasons only
  (no `board`, SQLite file locking, no `AF_UNIX`, no `picamera2`).
- `config.SIMULATE_HARDWARE` is frozen at first import of `config`; setting the env var
  later in the same process does nothing.

### Working on the live rover

- Before trusting any bus observation: `systemctl is-active willy-rover` and
  `sudo lsof /dev/i2c-1`. Only `wp5d` (and the service, if running) belongs there.
- The Hailo `VDevice` is exclusive to one process — stop `willy-rover.service` before
  `hailortcli` or any NPU script.
- Pico firmware lives in `firmware/`; each board runs it as `main.py` (a Pico only
  autoruns `main.py`). Identify a board by `machine.unique_id()`, never by port or
  position: Pico A `643f69a756a232ea`, Pico B `ad25bbf0f1e1f160`.
- Troubleshoot wires first, then code, then the device. Ask whether it physically moved
  before reading a current trace.

---

## Storage and backups

- Boots from the SanDisk Extreme PRO USB SSD (`/dev/sda`, label `willyssd`); EEPROM
  `BOOT_ORDER=0xf14`, USB first. The SD card is a bootable fallback, re-cloned from the SSD
  every Sunday 04:00 by `willie-sd-refresh.timer` (`rpi-clone`).
- Nightly 03:00 `willie-backup.timer`: restic to `\MYCLOUD\heaven\willieestic` (mounted at
  `/mnt/heaven`, root-only). The repository password is `/root/.restic-pass` -- keep a copy off
  the rover.

## I²C bus

One non-isolated segment on `/dev/i2c-1` — Pi GP2 **SDA1** (phys 3) / GP3 **SCL1**
(phys 5) — fanned out through two daisy-chained passive GODIY hubs, with an LTC4311
accelerator (no address). 100 kHz. Pull-ups are the Pi's own 1.8 kΩ plus breakout
pull-ups; **do not add pull-ups without measuring the combined value.** Device logic is on
Pi header pin 1 (3V3). Any device holding SDA or SCL low takes the whole bus down.

`i2cdetect -y 1` returns **ten devices**:

| Addr | Device | Function |
|------|--------|----------|
| 0x40 | INA260 | R2 5 V rail — steering servos, sonar (`INA260_5V_ADDR`, `steering_5v`) |
| 0x42 | PCA9685 | Steering servos CH0–CH5 |
| 0x43 | PCA9685 | Arm servos CH0–CH6 (CH7 empty) |
| 0x44 | INA260 | R3 6 V arm servo rail (`INA260_ARM_6V_ADDR`, `arm_6v`) |
| 0x45 | INA260 | +12 V bus → both FeatherWing VIN (`INA260_BUS_12V_ADDR`, `bus_12v`) |
| 0x48 | ADS1115 | A0 battery divider, A1 gripper FSR402, A2/A3 spare |
| 0x4A | BNO085 | 9-DoF IMU |
| 0x51 | Witty Pi 5 HAT+ | RTC, power management, hardware watchdog |
| 0x60 | FeatherWing #2927 | Motor driver, RIGHT side |
| 0x61 | FeatherWing #2927 | Motor driver, LEFT side |

- **0x70 is the PCA9685 All-Call address, not a device.** Never count it; it stops
  answering once `motors.py`/`arm.py` construction resets the PCA9685s.
- **Never scan or quick-write 0x4A while the rover runs** — the BNO085 logs it as an SHTP
  error and stalls. The self-test counts 0x4A present when its driver constructs.
- **The expected set lives in `config.py`.** `brain.py::_EXPECTED_I2C` (motion gate) and
  `diagnostics.py::_EXPECTED_I2C` both derive from it; `tests/test_expected_i2c_agreement.py`
  keeps them equal. Add a device to `config.py`, never as a literal.
- A bus that scans as "everything present from 0x08" is a stuck-low SDA, not devices. A
  single missing address on an otherwise healthy bus is a connector before a chip.
- Board address defaults are not chip datasheet defaults — verify `0x60`/`0x61` on a scan.
- An inline INA260 can drop off the bus while its rail works; its absence blinds
  monitoring without a power fault. **Verify a monitor by reading its rail voltage**
  (5 V / 6 V / 12 V cannot be confused), never by trusting a stored name.

---

## UART links and the Pi header

Three UARTs, all with the `-pi5` overlays in `/boot/firmware/config.txt`
(`dtoverlay=uart2-pi5`, `uart3-pi5`, `uart4-pi5`). **The `-pi5` suffix is required** —
the plain names are BCM2711 mappings that boot clean on the wrong pins.

| Link | Pi pins | Device | Carries |
|------|---------|--------|---------|
| `uart2-pi5`, `/dev/ttyAMA2` | GP4 **TXD2** (phys 7) → Pico B GP13 UART0 RX (pin 17); Pico B GP12 UART0 TX (pin 16) → GP5 **RXD2** (phys 29) | Pico B | 3 × HC-SR04 sonar (`$S`, 33.3 Hz), BNO085 RST |
| `uart3-pi5`, `/dev/ttyAMA3` | GP8 **TXD3** (phys 24, silkscreen `CE0`) → sensor RX; sensor TX → GP9 **RXD3** (phys 21, silkscreen `MISO`) | SEN0628 ToF | 8×8 depth frames |
| `uart4-pi5`, `/dev/ttyAMA4` | GP12 **TXD4** (phys 32) → Pico A GP13 UART0 RX (pin 17); Pico A GP12 UART0 TX (pin 16) → GP13 **RXD4** (phys 33) | Pico A | 6 encoders (`$E`, 50 Hz), R5 rail sense |

Protocol is in `firmware/README.md` (`$<body>*<XX>`, XOR checksum, 115200). `pico_link.py`
keeps the newest frame and its age and never invents a value. **A silent UART is not
evidence of damage** — prove the board is present over USB or with a meter first.

Other header pins:

- Pin 1 **3V3** — R4: all I²C device logic, SEN0628, BNO085 RST pull-up, FSR402.
- Pins 2/4 **5V** — from the Witty Pi output; display tap; Pico B VSYS.
- GP15 **UART0 RXD** (phys 10) — BNO085 INT, wired, not read by software.
- GP0 **ID_SD** / GP1 **ID_SC** (phys 27/28) — reserved for the AI HAT EEPROM.
- GP14 **UART0 TXD** (phys 8) — unused. **The serial console stays disabled**; no Pico
  goes on `uart0`.
- **SPI0 stays disabled** (`dtparam=spi=off`) — GP8/GP9 carry `uart3-pi5`.

---

## Picos

| | Pico A | Pico B |
|---|---|---|
| Firmware | `firmware/pico_a.py` | `firmware/pico_b.py` |
| Inputs | 6 encoders, GP0–GP11 (A even, B odd; wheel order `lf, lm, rf, rm, lr, rr` from `WHEELS`) | Sonar TRIG/ECHO F GP0/GP1, L GP2/GP3, R GP4/GP5 (ECHO via the signal-board ÷2/3 dividers); BNO085 RST GP15 (open-drain) |
| Power | VSYS from R5 (DROK-4 3.3 V) | VSYS from Pi 5 V at the breakout terminal — never R2 |
| Ground | pin 38 → R5 return, pin 18 → Pi GND (both correct) | **one** wire to Pi GND — do not add a second |

- Encoder decode is PIO on Pico A, signed ×2, **763 counts per wheel rev**
  (`ENCODER_COUNTS_PER_REV`). Do not add interrupt or polled encoder decode on the Pi.
- Stale frames mean unknown: sonar older than `SONAR_STALE_S` → stop; encoders older than
  `ENCODER_STALE_S` → every wheel reads stalled.
- Feed a Pico at VSYS (pin 39), never the 3V3 pin. **D2 is not fitted on either carrier:
  nothing protects against a reversed J1 — meter polarity before every connection.**
- The Pico radios are not initialised. `Pin("LED")` is allowed; never `import network`.
- USB into a rover-powered Pico is safe only because each carrier's D1 blocks back-feed;
  unplug the rover feed when in doubt.

---

## Power

| Rail | Volts | Source | Feeds | Monitor |
|------|-------|--------|-------|---------|
| R1 | 9 V | DROK-Pi (via Switch 2) | Witty Pi 5 VIN → Pi 5 header 5 V | Witty Pi HAT |
| R2 | 5 V | DROK-5V | Steering servos (0x42 V+), sonar VCC | INA260 0x40 |
| R3 | 6 V | DROK-6V (via SW-A) | Arm servos (0x43 V+) | INA260 0x44 |
| R4 | 3.3 V | Pi header pin 1 | I²C logic, SEN0628, BNO085 RST pull-up, FSR402 | — |
| R5 | 3.3 V | DROK-4 | Hall encoders, Pico A VSYS | Pico A ADC2 (GP28), flagged < 3.0 V |
| +12 V | pack | Battery → F1 → SW-MAIN → Q1 | All DROKs; via F2 → SW-M → both FeatherWings | INA260 0x45 |

- **The E-stop is the main SPST power switch, SW-MAIN.** It cuts all power, including the
  Pi. There is no separate E-stop and no E-stop sense input. A cut with the OS running
  risks filesystem corruption; the graceful path is `shutdown -h now`, then Switch 2.
- **Never feed the Pi from USB-C and the header at the same time.**
- **HC-SR04 absolute maximum is 5.5 V — R2 must stay at 5.0 V.** The DROKs are trimpot
  modules; re-verify after any knock.
- Pi 5 V rail measured 5.144 V; floor 4.85 V. Do not erode the margin. There is no
  brownout protection for the Pi in hardware or software.
- Pi pin 1 (R4) is a loaded rail with a real budget, not a spare pin. A USB-C-powered Pi
  still powers the whole I²C bus, so a blank scan is always a fault.
- With the base 12 V off, R2, R3, R5, the FeatherWing supply and Pico A go dark; I²C
  devices and Pico B keep answering. A clean roll-call says nothing about the 12 V rails —
  `_check_motor_rail()` on 0x45 does.
- **ADS1115 A0 must read 2.76–3.06 V** (≈2.9 V at 12 V) before the ADC is trusted. Near
  12 V means the divider is open and will destroy the ADC; near 0 V means the divider's
  +12 V feed is open (a floating input here reads ~0.9 V — compare A2/A3).
- `BATTERY_DIVIDER_SCALE` = 0.2432 (one calibration point). Battery ladder: warn 11.4,
  RTH 10.8, safe 10.5, shutdown 10.2 V. A reading below 5.0 V is a failed read, not a flat
  pack; a halt is blocked while the ADC and 0x45 disagree by more than 1.5 V.
- Prove which **rail** a device is on, not merely that it has voltage. A degrading
  failure is thermal; a wiring fault gives the same wrong answer every time.

---

## Drive, steering, arm

- **FeatherWings: 0x61 LEFT, 0x60 RIGHT; ports M1 = REAR, M2 = MIDDLE, M3 = FRONT**
  (`config.MOTOR_PORT`). Left/right are from Willie's point of view. The sides are mounted
  mirrored: `MOTOR_SIGN` negates the right side at the single throttle write;
  `ENCODER_SIGN` makes counts rover-forward in odometry. A side swap is invisible to gross
  motion — verify per-wheel one wheel at a time (bench procedure M-1).
- **Motor− (white) lands on a FeatherWing motor terminal, never a logic pin.** Meter
  every crimp; wire colours vary by batch.
- A stalled wheel draws 1.8 A against the TB6612's 1.2 A continuous. A stall must stop and
  report (`STALL_GRACE_S`), never drive harder.
- Measure counts per rev under power, never by hand-turning — the hub slips on the shaft.
- Steering: 6 × DS041MG on 0x42 CH0–CH5 (LF, RF, LM, RM, LR, RR), 1000–2000 µs, centred
  and held. Skid steer is the only turning mechanism.
- **Arm map (0x43, measured):** CH0 wrist pitch, CH1 elbow, CH2 shoulder (lift; decreasing
  µs raises), CH3 second shoulder axis, CH4 wrist rotate, CH5 gripper (increasing µs
  closes), CH6 base yaw, CH7 empty. A paper remap is not a rewiring — drive one channel at
  a time and watch the joint.
- **Never centre the elbow (CH1)** — `ARM_SERVO_CENTER_US` drives it into the chassis.
  `center_all()` skips it.
- **Open the elbow before moving the shoulder**, or the arm strikes the top of Willy.
  Step the shoulder in 50 µs steps.
- **CH2 and CH3 are not a mirrored pair.** Never derive one from the other.
- **A released arm falls.** Holding a pose is nearly free; moving costs amps.
- The arm current guard (`_check_arm_current()`, 0x44, `ARM_CURRENT_LIMIT_A` 2.5 A for
  `ARM_CURRENT_LIMIT_S` 0.4 s → release) runs every tick *during* motion. A limit checked
  after a move protects nothing.

---

## Software rules

- **Nothing calls the motors except through `safety.py`.** Enforced by
  `tests/test_no_direct_drive_bypass.py`.
- **The NPU stays out of the safety path.** Reflex layer (sonar, ToF, encoders, IMU,
  current monitors) drives the stop and never waits on vision. Vision informs navigation;
  it does not gate the stop. Enforced by `tests/test_reflex_deliberative_separation.py`.
- **The model's self-reported confidence never authorises a physical action.** Do not
  raise or lower `HAILO_LLM_CONFIDENCE_FLOOR`; do not add another confidence threshold.
  The model may recommend; deterministic logic disposes (Software Design §6.7).
- **Unprompted roaming needs permission each boot.** `ENABLE_AUTONOMOUS_ROAM=True` means
  "allowed to ask". `_roam_permission` starts false, is never persisted, and is cleared by
  a voice stop. He asks by voice and the `LET ME ROAM` panel button; refusal and silence
  both start `ROAM_ASK_COOLDOWN_S`. Debug "won't roam" via `_roam_permission`, then
  `_roam_ask_next`, then the flags.
- **Email is a command channel, including motion.** Only DKIM-verified (Gmail
  `Authentication-Results`), fresh (`EMAIL_COMMAND_MAX_AGE_S`) owner mail acts; the From
  match alone is not authentication. Commands queue behind Directives 1–5 like voice and
  are announced aloud before acting. Email bodies remain untrusted data for any model.
  `ENABLE_EMAIL_COMMANDS=False` is the kill switch.
- **No systemd watchdog.** `willy-rover.service` is `Type=simple`, so `sd_notify` is
  discarded; do not add `WatchdogSec` without `Type=notify` and timeouts matched to
  measured startup. The Witty Pi 5 hardware watchdog is the live one.
- **ToF (SEN0628):** request/response only, never streams — both UART directions are
  required. Powered from R4 3.3 V, not 5 V. Per-zone floor profile, never row masking;
  **uncalibrated reports nothing** (`scripts/calibrate_tof_floor.py`). It is the only drop
  detector. ToF unavailable is not a fault — fall back to sonar. USB-C on the sensor is
  for firmware only. FOV is 60° × 60° (90° diagonal).
- **Audio:** mic = "USB PnP **Sound** Device" (`08bb:2902`), speaker = "USB PnP **Audio**
  Device" puck (`0c76:1203`). Select capture by name, never pin `hw:N,0`. The mic cannot
  do 16 kHz: capture 48 kHz and decimate with `downsample_to_16k()`, never `samples[::3]`.
  Never disable the puck — it is the only speaker. `AUDIO_OUTPUT_DEVICE` is inert;
  playback is `pw-play` to the PipeWire default sink.
- **Hailo:** driver line is `hailo-h10-all`; `hailo-all` is Hailo-8 only and silently
  never binds the 10H. Vision is YOLOv8m on the front CSI imx708; the rear USB camera is
  not used by software. Intent model prompts must be ChatML-framed.
- **Witty Pi 5:** `wp5`/`wp5d` installed; `ENABLE_WITTY_PI=True`; `witty_pi.py` only
  feeds the hardware watchdog heartbeat.

---

## Open items

Current open items are tracked in Master Hardware Design §14 and Software Design §12 —
read them there rather than restating them here.
