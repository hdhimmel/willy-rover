# WildWilly Autonomous Rover

## As-Built Design Document

**Revision 1.0 · Current Configuration**

---

## Document Control

| Field | Value |
|-------|-------|
| Project | WildWilly Autonomous Rover |
| Document | As-Built Design — current configuration only |
| Revision | 1.0 |
| Date | 2026-08-15 |
| Owner | Howard Himmel |
| Status | Build complete; live verification in progress |
| Supersedes | Nothing. This is a parallel document. |
| Historical record | Master Engineering Package rev 6.2.0 retains all incident history, superseded designs, and revision lineage. Retain it. |

**Scope of this document.** This describes the rover as it is currently built.
It contains no incident narrative, no superseded design options, and no
revision archaeology. Where a past failure produced a standing rule, the rule
appears in §12 as a constraint — without the story behind it.

**Scope baseline.** Drive, see, talk/listen, arm pick-and-place on flat ground,
and basic flat-terrain autonomy. Stair-climbing is a stretch goal, not a
baseline requirement.

---

## 1. System Overview

Six-wheel rocker-bogie rover. Independent drive and steering on all six
corners, a 5-DOF arm with gripper, and a Raspberry Pi 5 host with an NPU
accelerator for vision and speech.

| Subsystem | Configuration |
|-----------|---------------|
| Compute | Raspberry Pi 5, AI HAT+ 2 (Hailo-10H, 8GB) |
| Drive | 6 × JGA25-370B gearmotors with quadrature encoders |
| Steering | 6 × GDW DS041MG servos |
| Arm | 7 servos — 4 × MG996R, 3 × MG90S |
| Ranging | 3 × HC-SR04 sonar (front, left, right) |
| Orientation | BNO085 9-DoF IMU with on-chip fusion |
| Vision | Front CSI camera, rear USB camera |
| Power | 2 × 3S 8000mAh LiPo in parallel |
| Bus | Galvanically isolated I²C, 10 devices |

Physical layout: Pi 5, SI board and audio HAT in the head assembly; power
distribution, bus node board and motor drivers in the body tray.

---

## 2. Power Architecture

### 2.1 Distribution tree

| ID | Path | Gauge | Protection |
|----|------|-------|------------|
| P1 | 2 × 3S 8000mAh → hard parallel, per-pack BMS | 12–14 AWG | BMS per pack |
| P2 | Battery+ → F1 → KCD4 switch → Q1 FET → +12V bus | 12 AWG | F1 30A ATC |
| P3 | +12V bus → F2 → INA260 0x45 → both FeatherWing VIN | 16 AWG | F2 |
| P4 | +12V bus → F3 → Pi buck input | 16 AWG | F3 |
| P5 | +12V bus → F4 → FEICHAO UBEC input | 16 AWG | F4 10A |
| P6 | +12V bus → F5 → DZS buck input | 16 AWG | F5 |
| P7 | Charge Y-cable (main + balance) → battery side of KCD4 | 14 AWG | — |

### 2.2 Regulated rails

| ID | Rail | Source | Feeds | Monitor |
|----|------|--------|-------|---------|
| R1 | 5.0–5.1V | Pi buck | Pi header pins 2/4, GND 6/9 | INA260 0x44 |
| R2 | 5V | FEICHAO 8A UBEC | Steering servo distribution, AMS1117 input | INA260 0x40 |
| R3 | 6V | DZS buck | Arm servo distribution | — |
| R4 | 3V3 | Pi header pin 1 | Encoder distribution, ISO1540 Side 1 | — |
| — | 3V3 (VCC2) | AMS1117-3.3 | Entire isolated I²C bus | — |

Set the Pi buck to 5.0–5.1V and the DZS to 6.0V off-load before connecting
anything downstream.

### 2.3 Protection

- **F1** 30A ATC main fuse, off-board. **F2–F5** branch fuses.
- **Q1** FQP27P06 P-channel MOSFET for reverse polarity, with a 220nF
  gate-source cap limiting turn-on inrush.
- **D1** P6KE15A TVS for transients.
- Dual 3S BMS, one per pack.
- Latching mushroom E-stop cuts motors and arm.
- **Switch 2** in the Pi buck input line — de-powers the Pi and the 3V3 bus
  after a software shutdown.

### 2.4 Capacitors — complete list

| Qty | Value | Location |
|-----|-------|----------|
| 1 | 220nF | Q1 gate-source soft-start |
| 1 | 1000µF 16V + 1 × 0.1µF ceramic | Pi 5V rail, at header pins 2+4 |
| 1 | 1000µF 16V | PCA9685 0x42 V+, C2 pad |
| 1 | 2200µF 16V Rubycon low-ESR | PCA9685 0x43 V+, C2 pad |
| 2 | 10µF | AMS1117 Vin and Vout |

Seven capacitors total. The Pi-rail pair sits at the **header end** of the
feed, not at the buck — GPIO power bypasses the Pi's onboard input
protection, so that feed carries its own local decoupling and its own fuse.

### 2.5 Voltage limits

| Rail | Nominal | Floor |
|------|---------|-------|
| Pi 5V | 5.0–5.1V | 4.85V |
| Pack | 12.6V full, 11.1V nominal | 10.2V cutoff |

Charge to 12.6V (4.20V/cell). Storage charge 11.4V (3.8V/cell). Packs must be
within 0.05V per cell of each other before paralleling — connect the main Y
first, the balance Y a minute later.

---

## 3. I²C Bus and Isolation

### 3.1 Topology

The Pi's I²C controller (GND1 domain) is separated from every device (GND2
domain) by an ISO1540 bidirectional isolator. Side 2 is powered by an
AMS1117-3.3 drawing from the 5V FEICHAO rail, feeding a single 3V3 rail that
branches to the isolator's Side 2 VCC and to the bus node VCC2 rail.

```
Pi native I²C (GND1)      ISO1540        Isolated bus (GND2)
─────────────────────────────────────────────────────────────
GP2  SDA  ──────────>  Side 1 ‖ Side 2  ──────────>  SDA2 rail
GP3  SCL  ──────────>  Side 1 ‖ Side 2  ──────────>  SCL2 rail
3V3       ──────────>  Side 1 ‖ Side 2  <──────────  AMS1117 out
GND       ──────────>  Side 1 ‖ Side 2  ──────────>  GND2 star
```

GND2 has exactly one star reference, at the AMS1117 ground pin. The two
ground domains must show no DC path between them.

### 3.2 Pull-ups

| Location | Value |
|----------|-------|
| Side 1 | Pi internal 1.8kΩ + ISO1540 onboard 10kΩ |
| Side 2 | 4.7kΩ rail pair + ISO1540 onboard 10kΩ + device breakouts |

Side 2 measures approximately 1.3kΩ combined. Do not add pull-ups on Side 1 —
that side sinks only 3.5mA and is already near budget.

### 3.3 Device roll-call

`i2cdetect -y 1` returns **ten devices plus one broadcast address**:

| Address | Device | Function |
|---------|--------|----------|
| 0x27 | MCP23017 | Encoder GPIO expander, 6 channels |
| 0x40 | INA260 | 5V servo/steering rail current |
| 0x42 | PCA9685 | Steering servos, CH0–CH5 |
| 0x43 | PCA9685 | Arm servos, CH0–CH6 |
| 0x44 | INA260 | Pi 5V rail current — SAFE_MODE trip reads this |
| 0x45 | INA260 | Motor 12V rail current |
| 0x48 | ADS1115 | Battery voltage ADC |
| 0x4A | BNO085 | 9-DoF IMU |
| 0x60 | FeatherWing | Motor driver, LEFT |
| 0x61 | FeatherWing | Motor driver, RIGHT |

**0x70 is the PCA9685 All-Call broadcast address, not a device.** It answers
whenever either PCA9685 is alive. The LTC4311 bus accelerator has no address
at all — it is a transparent pass-through and never appears in a scan.

A blank or partial scan with the base unpowered is expected behaviour, not a
fault: Side 2 dies with the 12V chain, so the Pi on USB-C alone sees nothing.

---

## 4. Bus Node Board

Four rails. Colours: GND black, 3V3 red, SDA blue, SCL yellow. Note this is
schematic role-colouring and differs from the sonar harness key in §6.1.

| Row | GND | 3V3 | SDA | SCL | Device | Addr |
|-----|-----|-----|-----|-----|--------|------|
| 1 | X | X | — | — | AMS1117-3.3 | — |
| 2 | X | X | X | X | ISO1540 Side 2 | — |
| 3 | X | X | X | X | ADS1115 logic | 0x48 |
| 4 | X | — | — | — | ADS1115 ADDR→GND | 0x48 |
| 5 | X | X | X | X | INA260 servo/steering | 0x40 |
| 6 | X | X | X | X | INA260 Pi 5V | 0x44 |
| 7 | X | X | X | X | INA260 motor 12V | 0x45 |
| 8 | X | X | X | X | LTC4311 | none |
| 9 | X | X | X | X | BNO085 IMU | 0x4A |
| 10 | X | X | X | X | MCP23017 encoder | 0x27 |
| 11 | X | X | X | X | FeatherWing LEFT | 0x60 |
| 12 | X | X | X | X | FeatherWing RIGHT | 0x61 |
| 13 | X | X | X | X | PCA9685 steering | 0x42 |
| 14 | X | X | X | X | PCA9685 arm | 0x43 |
| 15 | X | X | — | — | Motor LF | — |
| 16 | X | X | — | — | Motor LM | — |
| 17 | X | X | — | — | Motor LR | — |
| 18 | X | X | — | — | Motor RF | — |
| 19 | X | X | — | — | Motor RM | — |
| 20 | X | X | — | — | Motor RR | — |
| 21 | X | — | — | — | Sonar divider GND ref | — |

**Devices taking more than one rail tap:** ADS1115 only, whose second tap is a
GND for the ADDR strap selecting 0x48.

**Single-tap devices worth noting.** The BNO085 takes four connections only —
the Adafruit breakout has no AD0 pin, and its address-select pin (DI) is
pulled low on-board, fixing it at 0x4A. The LTC4311 also takes four — its EN
pin is already pulled high to VIN on the breakout.

---

## 5. Compute and Interfaces

### 5.1 Raspberry Pi 5

Powered through the GPIO header from the Pi buck, not USB-C. The GPIO path
bypasses the Pi's onboard input protection, so brownout protection is
firmware-only, via the INA260 at 0x44. There is no hardware supervisor.

### 5.2 AI HAT+ 2

Hailo-10H with 8GB dedicated on-board RAM. Attaches by PCIe FFC, not the
40-pin header and not USB-C. Header pins 27/28 (ID_SD/ID_SC) are reserved for
its EEPROM and must not be used.

Setup: enable PCIe Gen 3 (`raspi-config` → Advanced Options → PCIe Speed —
Gen 2 is the default and halves bandwidth), then `sudo apt install hailo-all`,
verify with `hailortcli fw-control identify`. Post-processing assets install
to `/usr/share/rpi-camera-assets/`.

Capability: object detection, semantic and instance segmentation, pose
estimation, plus on-device Whisper speech-to-text and vision-language models.

### 5.3 GPIO breakout

Seengreat RPi PX00 Expansion A, ribbon-connected to the Pi 5. Passive 1:1
passthrough — standard 40-pin layout, no buffers, level shifters or added
pull-ups. Its passivity is a requirement, not a convenience: anything added to
GP2/GP3 counts against the ISO1540 Side 1 budget.

### 5.4 Vision and display

| Device | Interface |
|--------|-----------|
| Front camera | CSI FFC |
| Rear camera | USB |
| Display | DSI ribbon + separate 3-pin GPIO power |
| AI HAT+ 2 | PCIe FFC |

---

## 6. Sensors

### 6.1 Sonar

3 × HC-SR04 — front (centre), left, right. There is no rear sonar; the only
rear-facing device is the rear USB camera.

| Position | TRIG | ECHO |
|----------|------|------|
| Front | GP5 (pin 29) | GP26 (pin 37) |
| Left | GP13 (pin 33) | GP14 (pin 8) |
| Right | GP4 (pin 7) | GP21 (pin 40) |

ECHO lines pass through 1k/2k dividers on the EPLZON perfboard — the HC-SR04
echoes at 5V. TRIG is driven directly and needs no divider. Sonar VCC is 5V.

Harness colours: **blue GND, purple ECHO, grey TRIG, white VCC.**

### 6.2 Battery voltage sense

10kΩ from the +12V bus to the divider midpoint, and 4.7kΩ ∥ 10kΩ (≈3.2kΩ)
from midpoint to GND. Midpoint goes to **ADS1115 A0**. Expect ~2.76V at
11.4V pack, ~3.06V at 12.6V.

Requires calibration: meter the actual voltage at the divider high side,
compare against the reported value, and set the scale factor in `config.py`.
Verify at two points across the range. The low-voltage shutdown fires from
calibrated volts, so an error here moves the cutoff.

### 6.3 IMU

BNO085, 0x4A. On-chip SH-2 fusion gives drift-free heading without a
magnetometer — useful with six motors nearby.

| Pin | Connection |
|-----|------------|
| VIN | VCC2 rail row 9 |
| GND | GND2 rail row 9 |
| SDA / SCL | SDA2 / SCL2 rail row 9 |
| INT | GP15, physical header pin 10 |
| RST | MCP23017 GPB4 |
| DI, P0, P1, BT, 3Vo | unconnected |

The reset line runs through the MCP23017, so the expander must be initialised
before the IMU can be reset — an ordering dependency in software.

The BNO085 uses I²C clock stretching, which the Pi handles poorly at default
speed. If initialisation succeeds but reads fail intermittently, adjust
`dtparam=i2c_arm_baudrate` — for this part, raising it above the 100kHz
default is usually more effective than lowering it.

### 6.4 Current monitoring

3 × INA260, each inline in its rail rather than a parallel tap. Integrated
2mΩ shunt, factory calibrated — no calibration register to set.

---

## 7. Drive and Steering

### 7.1 Motors

6 × JGA25-370B micro metal gearmotors. 6V nominal, ~100–200 RPM, quadrature
encoders at 11 PPR on the motor shaft. One 6-pin JST-PH per motor.

| Wire | Function | Lands on |
|------|----------|----------|
| Red | Motor + | FeatherWing motor terminal |
| White | Motor − | FeatherWing motor terminal |
| Blue | Encoder VCC | 3V3 encoder distribution |
| Black | Encoder GND | Encoder GND distribution → star |
| Yellow | Encoder Phase A | MCP23017, even pin of pair |
| Green | Encoder Phase B | MCP23017, odd pin of pair |

Meter each crimp before trusting wire colour — batch variation is documented.

### 7.2 Motor driver assignment

Each FeatherWing drives one side.

| Motor | Position | Driver | Encoder A/B |
|-------|----------|--------|-------------|
| LF | Left front | 0x60 M1 | GPA0 / GPA1 |
| LM | Left middle | 0x60 M2 | GPA2 / GPA3 |
| LR | Left rear | 0x60 M3 | GPB0 / GPB1 |
| RF | Right front | 0x61 M1 | GPA4 / GPA5 |
| RM | Right middle | 0x61 M2 | GPA6 / GPA7 |
| RR | Right rear | 0x61 M3 | GPB2 / GPB3 |

Adafruit FeatherWing #2927, used standalone with no Feather host board.
Direction and PWM are handled internally over I²C — there are no direction
GPIOs and no STBY pin.

### 7.3 Steering

6 × GDW DS041MG, one per corner, on PCA9685 0x42 channels CH0–CH5 in the
order LF, RF, LM, RM, LR, RR.

Each servo plugs into a 3-pin channel header — signal, V+ and GND all pass
through the board. The board takes its own V+ from the 5V FEICHAO rail.

1500µs centre, 500–2500µs for 180°. Confirm per unit; some stock ships in
900–2100µs / 120° mode.

---

## 8. Arm

5-DOF plus gripper, 7 servos on PCA9685 0x43. The board takes its V+ from the
6V DZS rail; servos plug into 3-pin channel headers.

| Joint | Servo | Channel |
|-------|-------|---------|
| J0 base yaw | MG996R | CH0 |
| J1a shoulder (right) | MG996R | CH1 |
| J1b shoulder (left) | MG996R | CH2 |
| J2 elbow | MG996R | CH3 |
| J3 wrist rotate | MG90S | CH4 |
| J4 wrist pitch | MG90S | CH5 |
| J5 gripper | MG90S | CH6 |

J1a and J1b are a mirrored pair driving one physical axis:
`J1b = 2 × 1500µs − J1a`. They must be commanded together.

The arm connects through a bulkhead connector so it detaches without
desoldering.

---

## 9. Pin Assignments — Pi 40-pin Header

| Pin | BCM | Connects to |
|-----|-----|-------------|
| 1 | 3V3 | ISO1540 Side 1 VCC, encoder distribution |
| 2, 4 | 5V | Pi buck output |
| 3 | GP2 | ISO1540 Side 1 SDA |
| 5 | GP3 | ISO1540 Side 1 SCL |
| 6, 9 | GND | Pi return → star |
| 7 | GP4 | Sonar RIGHT TRIG |
| 8 | GP14 | Sonar LEFT ECHO (÷) |
| 10 | GP15 | BNO085 INT |
| 27, 28 | GP0/GP1 | RESERVED — AI HAT EEPROM |
| 29 | GP5 | Sonar FRONT TRIG |
| 33 | GP13 | Sonar LEFT TRIG |
| 37 | GP26 | Sonar FRONT ECHO (÷) |
| 40 | GP21 | Sonar RIGHT ECHO (÷) |

Free and unused: GP7, GP8–GP11, and the twelve pins formerly used for motor
direction.

**GP14 and GP15 are UART0 TXD/RXD.** The serial console must remain disabled
or the kernel claims both pins — and drives GP14 as an output onto the left
sonar's divider node. Disable via `raspi-config` → Interface Options → Serial
Port, answering **no** to both prompts. Verify with
`gpioinfo | grep -E 'line *1[45]'`; both must show unused.

---

## 10. Ground

Single-point star. Every converter negative, board ground and sensor return
lands on it.

The isolated GND2 domain has its own single reference at the AMS1117 ground
pin and must not bond to GND1 anywhere. All measurements stay within one
domain — a reading taken between domains is a floating value and means
nothing.

---

## 11. Software

Python, modular, running from `willy-rover.service`. Modules include
`brain`, `safety`, `motors`, `arm`, `navigation`, `odometry`, `sensors`,
`vision`, `voice`, `world_model`, `mapping`, `diagnostics`, `config`, and a
`hw_sim` mock layer selected by `WILLY_SIMULATE` for off-hardware testing.

### 11.1 Control layering

**Reflex layer** — sonar, encoders, current monitors. Deterministic, drives
the emergency stop, never waits on vision.

**Deliberative layer** — the NPU. Frame-rate at best, variable latency,
seconds-scale for language models. Feeds `world_model` for planning and
classification only.

An obstacle stop must never depend on a detection frame arriving.

### 11.2 Startup self-test

Enumerate all ten I²C devices, confirm the BNO085 interrupt is live on GP15,
and confirm all six encoder channels change count under manual rotation.
Motion stays inhibited unless every check passes.

The self-test must distinguish "base unpowered" from "bus fault" — a blank
scan on USB-C-only power is expected, not a failure.

### 11.3 Shutdown

`shutdown -h now` completes with the rail still powered; Switch 2 then
de-powers the Pi and the 3V3 bus. Low-battery shutdown triggers proactively
from calibrated pack voltage, ahead of the 10.2V cutoff.

Bulk capacitance cannot hold a Pi 5 up through a hard power cut — that would
require farads, not microfarads. A cut at the main switch or E-stop with the
OS running risks filesystem corruption.

---

## 12. Design Constraints

Standing rules. Each exists because violating it has consequences that are
not obvious from the schematic.

**Wiring**

1. Motor− (white) lands on a FeatherWing motor terminal. Never on an
   MCP23017 GPIO or any logic pin.
2. The AMS1117-3.3 input is the 5V rail. Never 12V — the dissipation drives
   it into thermal foldback and the isolated rail collapses progressively.
3. ISO1540 sides are not interchangeable. Side 1 takes 40pF and one device;
   Side 2 takes 400pF and multiple nodes. The device bus goes on Side 2.
   Identify Side 1 by the SOIC-8 pin-1 marker — pins 1–4 are VCC1, SDA1,
   SCL1, GND1 — and mark the board physically.
4. Meter every pin of an unlabelled module against its datasheet before
   applying power. Never identify a pin by swapping a live connection.

**Before power-up**

5. AMS1117 decoupling present on both Vin and Vout.
6. 4.7kΩ pull-ups present on SDA2 and SCL2.
7. GND1/GND2 isolation confirmed — no DC path between domains.
8. ADS1115 A0 metered in the 2.76–3.06V window. A reading near 12V means the
   divider is open and the ADC will be destroyed on power-up.
9. Address straps verified individually on both PCA9685s and all three
   INA260s.
10. Serial console disabled.

**Diagnostic principles**

11. A degrading failure is thermal. A wiring fault gives the same wrong
    answer every time; a part in thermal foldback gives a progressively
    worse one.
12. Cross-domain measurements are meaningless. Reference every reading to the
    ground of the side being measured.
13. 0x70 in a scan proves a PCA9685 is alive and nothing else. Never count it
    toward the device total.

**Power**

14. Never run USB-C and the Pi buck simultaneously — two sources on one rail.
15. Do not erode the Pi rail margin. Floor is 4.85V; measured 5.144V.
16. The 5V rail worst case is already near 9A against an 8A UBEC rating.
    Budget any new load on this rail before fitting it.
17. Packs within 0.05V per cell before paralleling. Main Y first, balance Y
    a minute later.

---

## 13. Verification Status

| Item | Status |
|------|--------|
| Full ten-device roll-call through the isolator | PASS |
| Pi boots from battery, rail 5.144V, throttled 0x0 | PASS |
| Serial console disabled, GP14/GP15 free | PASS |
| Bus node board fully populated | PASS |
| Breakout connections verified | PASS |
| Sonars connected | Connected, not yet range-tested |
| Encoder counts on all six channels | Not tested |
| BNO085 interrupt and fusion output | Not tested |
| Battery divider calibration | Not done |
| Steering servo sweep | Not tested |
| Arm servo range | Not tested |
| Motor direction and mapping | Not tested |

---

## 14. Open Items

1. **Motor crimps** — five of six unverified against the colour scheme in
   §7.1. Meter before first motion.
2. **Battery divider calibration** — required before the low-voltage cutoff
   can be trusted.
3. **PCA9685 V+ current path** — servo current now flows through each board's
   V+ terminal, PCB trace and channel headers rather than signal current
   only. Worst-case steering draw is near 9A. Confirm against the board's
   ratings before running all six servos under load simultaneously.
4. **AI HAT+ 2 power budget** — draws from the 5V rail, which is already the
   tightest in the design.
5. **Runtime measurement** — log the three INA260s through a representative
   run and integrate, rather than relying on estimates.
6. **AMS1117 thermal watch** — this part has seen sustained thermal stress.
   Watch for drift or shutdown as bus load increases.

---

## 15. Bill of Materials

Current components only. Anything superseded, retired or never fitted is
listed in §15.8 rather than carried as a line item.

### 15.1 Compute and interface

| Component | Role | Qty | Status |
|-----------|------|-----|--------|
| Raspberry Pi 5 (8GB) | Host controller | 1 | Installed |
| AI HAT+ 2 (Hailo-10H, 8GB) | NPU — vision, speech, VLM | 1 | On order |
| 5" DSI touch display, 800×480 | Face / UI | 1 | Installed |
| Arducam IMX708 (CSI) | Front camera | 1 | Installed |
| OV9782 (USB) | Rear camera | 1 | Installed |
| ReSpeaker USB mic + speaker | Voice I/O | 1 | Installed |
| Seengreat RPi PX00 Expansion A | 40-pin passive GPIO breakout | 1 | Installed |
| Raspberry Pi Active Cooler | Pi 5 blower + heatsink | 1 | Installed |
| 5V case fan, 30–40mm | Head assembly exhaust | 1 | Installed |
| SanDisk Extreme PRO SSD 500GB | Boot drive | 1 | Installed |

### 15.2 Drive and steering

| Component | Role | Qty | Status |
|-----------|------|-----|--------|
| JGA25-370B gearmotor + encoder | Drive wheels | 6 | Installed |
| Adafruit FeatherWing #2927 | I²C motor driver — 0x60 left, 0x61 right | 2 | Installed |
| GDW DS041MG servo | Corner steering — PCA9685 0x42 | 6 | Installed |

### 15.3 Arm

| Component | Role | Qty | Status |
|-----------|------|-----|--------|
| MG996R metal-gear servo | J0 base, J1a/J1b shoulder, J2 elbow | 4 | Installed |
| MG90S micro servo | J3 wrist rotate, J4 wrist pitch, J5 gripper | 3 | Installed |
| 608 bearing | Arm joint | 1 | Verify |
| 6203 bearing | Arm joint | 2 | Verify |
| M8 60mm bolt + anti-loosening nut | Arm pivot | 2 | Verify |
| Servo bulkhead connector | 7-lead detachable arm harness | 1 | Built |
| Braided split sleeve | Arm harness protection | 1 | Ordered |

### 15.4 I²C bus and isolation

| Component | Role | Qty | Status |
|-----------|------|-----|--------|
| Adafruit ISO1540 (#4903) | Galvanic I²C isolator | 1 | Installed |
| AMS1117-3.3 regulator module | Isolated 3V3 (VCC2) supply | 1 | Installed |
| 10µF capacitor | AMS1117 Vin and Vout decoupling | 2 | Installed |
| 4.7kΩ resistor | SDA2 / SCL2 rail pull-ups | 2 | Installed |
| Adafruit LTC4311 | I²C accelerator — no address | 1 | Installed |
| MCP23017 | Encoder GPIO expander, 0x27 | 1 | Installed |
| ADS1115 | Battery voltage ADC, 0x48 | 1 | Installed |
| INA260 current sensor | 0x40 servo, 0x44 Pi, 0x45 motor | 3 | Installed |
| Adafruit PCA9685 | 0x42 steering, 0x43 arm | 2 | Installed |
| 1000µF 16V electrolytic | PCA9685 0x42 V+, C2 pad | 1 | Installed |
| Rubycon 2200µF 16V low-ESR | PCA9685 0x43 V+, C2 pad | 1 | Installed |

### 15.5 Sensing

| Component | Role | Qty | Status |
|-----------|------|-----|--------|
| BNO085 9-DoF IMU | Orientation, 0x4A | 1 | Installed |
| HC-SR04 sonar | Front, left, right | 3 | Installed |
| 1kΩ resistor | Sonar ECHO dividers, high side | 3 | Installed |
| 2kΩ resistor | Sonar ECHO dividers, low side | 3 | Installed |
| 10kΩ resistor | Battery divider high side | 1 | Installed |
| 10kΩ + 4.7kΩ resistor | Battery divider low side (parallel ≈3.2kΩ) | 2 | Installed |
| EPLZON perfboard | Carries all four divider circuits | 1 | Installed |

### 15.6 Power

| Component | Role | Qty | Status |
|-----------|------|-----|--------|
| 3S LiPo 8000mAh | Two packs, hard-paralleled | 2 | Installed |
| 3S BMS 40–60A with balance | One per pack | 2 | Installed |
| Pi rail buck converter | 12V → 5.0–5.1V | 1 | Installed |
| FEICHAO 8A UBEC | 12V → 5V servo/steering rail | 1 | Installed |
| DZS Elec 12A adjustable buck | 12V → 6.0V arm rail | 1 | Installed |
| Rubycon ZL 1000µF 16V low-ESR | Pi 5V rail bulk, at header | 1 | Installed |
| 0.1µF ceramic | Pi 5V rail HF bypass | 1 | Installed |
| FQP27P06 P-FET (Q1) | Reverse-polarity protection | 1 | Built |
| 220nF capacitor | Q1 gate-source soft-start | 1 | Installed |
| P6KE15A TVS diode (D1) | Transient suppression | 1 | Installed |
| 30A ATC fuse + holder (F1) | Main fuse, off-board | 1 | Built |
| Branch fuses F2–F5 | 10A / 5A / 10A / 10A | 4 | Built |
| KCD4 rocker switch | Main power | 1 | Installed |
| Latching mushroom E-stop | Cuts motors and arm | 1 | Installed |
| Switch 2 | Pi-rail cutoff, in buck input line | 1 | Built |
| 7-port distribution / ground block | Single-point star | 1 | Installed |
| Shrouded EC5 bulkhead + JST-XH balance extension | Charge-in-place access | 1 | Installed |
| Charge Y-cable — main and balance | Parallel charging both packs | 1 | In use |
| iMAX B6 80W balance charger | 6A maximum | 1 | On hand |

### 15.7 Consumables and hardware

PETG filament; M2.5 and M3 fasteners; 12–14 AWG, 16 AWG, 20 AWG and 22 AWG
wire; JST-PH 6-pin motor connectors; Dupont connectors; threadlocker.

### 15.8 Removed from the design

Listed so their absence is deliberate and traceable, not an omission.

| Component | Reason |
|-----------|--------|
| MCP3008 SPI ADC | Replaced by ADS1115 on I²C. Freed GP8–GP11. |
| TB6612FNG discrete drivers | Replaced by 2 × FeatherWing #2927 |
| Pimoroni Nano HAT Hacker | Replaced by the Seengreat breakout |
| MPU-6050 IMU | Superseded at design stage by the BNO085 |
| 3 × 470µF 25V "buck output surge buffer" | Never assigned to a converter; bucks carry their own output capacitance and both servo rails carry bulk downstream |
| 0.1µF encoder filter capacitors | Never fitted. At ~114 Hz per channel they would have destroyed the count against the MCP23017's internal pull-ups. |
| 2 × 1000µF interim arm decoupling | Superseded — the single Rubycon can was fitted instead |
| 2×3S paraboard | Replaced by main + balance Y cables |
| Elecbee 5V/5A buck | Retired in favour of the current Pi rail buck |

**One item to confirm:** the Pi rail buck's identity is recorded inconsistently
across older documents — a DROK 12A LCD unit in some, an Elecbee 5V/5A in
others. The rail measures correctly and the monitor is confirmed at 0x44, so
this is a labelling question rather than an electrical one. Confirm the part
physically and settle §15.6.

---

## 16. Complete Pin-to-Pin Connection Schedule

Every conductor in the design, by connector or harness. §9 gives the Pi header
view; this gives the device view. Supersedes the standalone
`WildWilly_PIN_TO_PIN_SCHEDULE_v1.0` document, which was drafted before the
isolator orientation, breakout swap and servo power method were settled.

### 16.1 ISO1540 isolator

Both halves silkscreen VCC / GND / SDA / SCL — there are no numbered pads.
Side 1 is the half nearest the SOIC-8 pin-1 marker (§12 rule 3).

| Side 1 pad | To | | Side 2 pad | To |
|---|---|---|---|---|
| VCC | Pi header pin 1 (3V3) | | VCC | AMS1117 Vout / VCC2 rail |
| GND | Pi header pin 6 or 9 | | GND | GND2 star |
| SDA | Pi header pin 3 (GP2) | | SDA | SDA2 rail |
| SCL | Pi header pin 5 (GP3) | | SCL | SCL2 rail |

A STEMMA QT connector on each half sits on the same nets as that half's pads.

### 16.2 AMS1117-3.3 regulator

| Pin | To |
|---|---|
| Vin | 5V FEICHAO rail, downstream of INA260 0x40 |
| GND | GND2 star — single-point reference for the isolated domain |
| Vout | VCC2 rail **and** ISO1540 Side 2 VCC (one rail, two branches) |

10µF from Vin to GND and 10µF from Vout to GND, both close to the device.

### 16.3 ADS1115 — 0x48, rows 3–4

| Pin | To |
|---|---|
| VDD | VCC2 rail row 3 |
| GND | GND2 rail row 3 |
| SDA | SDA2 rail row 3 |
| SCL | SCL2 rail row 3 |
| ADDR | GND2 rail row 4 — selects 0x48 |
| A0 | Battery divider midpoint |
| A1–A3, ALRT | unconnected |

### 16.4 INA260 × 3

Each is wired **inline** in its rail — the rail passes through VIN+ and VIN−,
it is not a parallel tap.

| Addr | Row | VIN+ from | VIN− to |
|---|---|---|---|
| 0x40 | 5 | FEICHAO UBEC 5V output | Servo/steering distribution + AMS1117 Vin |
| 0x44 | 6 | Pi rail buck output | Pi header pins 2 and 4 |
| 0x45 | 7 | +12V bus via F2 | Both FeatherWing VIN terminals |

Logic pins on each: VCC, GND, SDA, SCL from that device's own row.

### 16.5 LTC4311 — no address, row 8

| Pin | To |
|---|---|
| VIN | VCC2 rail row 8 |
| GND | GND2 rail row 8 |
| SDA | SDA2 rail row 8 |
| SCL | SCL2 rail row 8 |
| EN | **unconnected** — pulled high to VIN on the breakout |

Four wires only. Transparent to the bus; never appears in a scan.

### 16.6 BNO085 — 0x4A, row 9

| Pin | To |
|---|---|
| VIN | VCC2 rail row 9 |
| GND | GND2 rail row 9 |
| SDA | SDA2 rail row 9 |
| SCL | SCL2 rail row 9 |
| INT | Pi header pin 10 (GP15) |
| RST | MCP23017 GPB4 |
| DI, P0, P1, BT, 3Vo | unconnected |

DI unconnected fixes the address at 0x4A. There is no AD0 pin on this
breakout.

### 16.7 MCP23017 — 0x27, row 10

| Pin | To |
|---|---|
| VDD | VCC2 rail row 10 |
| VSS | GND2 rail row 10 |
| SDA / SCL | SDA2 / SCL2 rail row 10 |
| A0, A1, A2 | Address straps — set for 0x27 |
| RESET | VCC2, tied high |
| GPA0 / GPA1 | LF encoder — yellow / green |
| GPA2 / GPA3 | LM encoder — yellow / green |
| GPA4 / GPA5 | RF encoder — yellow / green |
| GPA6 / GPA7 | RM encoder — yellow / green |
| GPB0 / GPB1 | LR encoder — yellow / green |
| GPB2 / GPB3 | RR encoder — yellow / green |
| GPB4 | BNO085 RST |
| GPB5–GPB7 | unused |

Encoder lines land directly on the GPIO pins — no external components.
Convention: yellow to the even-numbered pin, green to the odd.

**No motor power lead ever lands here.**

### 16.8 FeatherWing #2927 × 2 — rows 11–12

| Addr | Row | VIN | Logic | Motor terminals |
|---|---|---|---|---|
| 0x60 | 11 | +12V via F2, downstream of INA260 0x45 | VCC2/GND2/SDA2/SCL2 row 11 | M1 = LF, M2 = LM, M3 = LR, M4 spare |
| 0x61 | 12 | same | row 12 | M1 = RF, M2 = RM, M3 = RR, M4 spare |

Standalone — no Feather host board. Direction and PWM are internal, so there
are no direction GPIOs and no STBY pin.

### 16.9 PCA9685 × 2 — rows 13–14

| Addr | Row | Logic | Board V+ | Address straps |
|---|---|---|---|---|
| 0x42 | 13 | VCC2/GND2/SDA2/SCL2 row 13 | 5V FEICHAO rail | A1 bridged |
| 0x43 | 14 | row 14 | 6V DZS rail | A0 **and** A1 bridged |

Base address is 0x40; each bridged jumper adds its bit. Servos plug into the
3-pin channel headers, so signal, V+ and GND all pass through the board.

Bulk capacitance at each board's V+: 1000µF on 0x42, 2200µF on 0x43.

### 16.10 Motors × 6

One 6-pin JST-PH per motor, fanned to Dupont. Meter each crimp before
trusting the colour.

| Wire | Function | Lands on |
|---|---|---|
| Red | Motor + | FeatherWing motor terminal (+) |
| White | Motor − | FeatherWing motor terminal (−) |
| Blue | Encoder VCC | 3V3 encoder distribution |
| Black | Encoder GND | Encoder GND distribution → star |
| Yellow | Encoder phase A | MCP23017, even pin of the pair |
| Green | Encoder phase B | MCP23017, odd pin of the pair |

Motor rows 15–20 on the bus node board carry the encoder 3V3 and GND taps;
motor power itself comes from the FeatherWing terminals, not the rails.

### 16.11 Steering servos × 6

Each plugs into a 3-pin channel header on the 0x42 board.

| Servo | Channel |
|---|---|
| LF | CH0 |
| RF | CH1 |
| LM | CH2 |
| RM | CH3 |
| LR | CH4 |
| RR | CH5 |

### 16.12 Arm servos × 7

Each plugs into a 3-pin channel header on the 0x43 board, through the arm
bulkhead connector.

| Joint | Servo | Channel |
|---|---|---|
| J0 base yaw | MG996R | CH0 |
| J1a shoulder right | MG996R | CH1 |
| J1b shoulder left | MG996R | CH2 |
| J2 elbow | MG996R | CH3 |
| J3 wrist rotate | MG90S | CH4 |
| J4 wrist pitch | MG90S | CH5 |
| J5 gripper | MG90S | CH6 |

J1a and J1b drive one axis as a mirrored pair and are commanded together.

### 16.13 Sonar × 3

Harness: white VCC, blue GND, grey TRIG, purple ECHO.

| Position | VCC | TRIG → | ECHO → divider → |
|---|---|---|---|
| Front | 5V rail | Pi pin 29 (GP5) | Pi pin 37 (GP26) |
| Left | 5V rail | Pi pin 33 (GP13) | Pi pin 8 (GP14) |
| Right | 5V rail | Pi pin 7 (GP4) | Pi pin 40 (GP21) |

Each ECHO divider: 1kΩ from the sensor's ECHO to the midpoint, 2kΩ from
midpoint to GND, midpoint to the Pi. TRIG connects directly.

### 16.14 Battery divider

| Node | To |
|---|---|
| High | +12V bus |
| R1 10kΩ | High → midpoint |
| R2 10kΩ ∥ 4.7kΩ (≈3.2kΩ) | Midpoint → GND |
| Midpoint | ADS1115 A0 |
| Low | GND2, referenced at bus node row 21 |

### 16.15 Vision, display, accelerator

| Device | Interface | To |
|---|---|---|
| Front camera | CSI FFC | Pi CSI connector |
| Rear camera | USB | Pi USB port |
| Display | DSI ribbon + 3-pin GPIO power | Pi DSI + GPIO |
| AI HAT+ 2 | PCIe FFC | Pi PCIe connector |

None of these touch the 40-pin header except the display's power tap.

---

**End of As-Built Design Document rev 1.0**
