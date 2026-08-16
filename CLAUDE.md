# WildWilly / willy-rover

Six-wheel rocker-bogie autonomous rover. Raspberry Pi 5 host, 5-DOF arm,
galvanically isolated I²C bus. Hardware is 100% built as of 2026-08-14;
the phase now is **live verification, not construction**.

This file records hardware facts and pitfalls that cannot be derived from the
code. Where code and this file disagree, assume the hardware is right and the
code needs fixing — every line below was confirmed on the bench.

---

## Bus state — verified 2026-08-13

`i2cdetect -y 1` returns **ten devices plus one broadcast address**:

| Addr | Device | Notes |
|------|--------|-------|
| 0x27 | MCP23017 | Encoder expander, 6 channels |
| 0x40 | INA260 | Servo/steering 5V rail current |
| 0x42 | PCA9685 | Steering servos, CH0–CH5 |
| 0x43 | PCA9685 | Arm servos, CH0–CH6 |
| 0x44 | INA260 | **Pi 5V rail** — SAFE_MODE brownout trip reads this |
| 0x45 | INA260 | Motor 12V rail current |
| 0x48 | ADS1115 | Battery voltage ADC, A0 |
| 0x4A | BNO085 | 9-DoF IMU |
| 0x60 | FeatherWing | Motor driver, LEFT side |
| 0x61 | FeatherWing | Motor driver, RIGHT side |

**0x70 is NOT a device.** It is the PCA9685 All-Call broadcast address and
answers whenever either PCA9685 is alive. Any roll-call check that counts
0x70 toward the device total will pass a scan that is actually missing a
device. Expect ten, not eleven.

**The Pi-rail INA260 is at 0x44, not 0x46.** Confirmed by scan — 0x46 does
not answer. If `config.py` names 0x46, the brownout trip reads nothing and
fails silently.

---

## Pin assignments (BCM)

**Sonar** — three units, front/left/right. There is no rear sonar.

| Position | TRIG | ECHO |
|----------|------|------|
| Front (centre) | 5 | 26 |
| Left | 13 | 14 |
| Right | 4 | 21 |

ECHO lines pass through 1k/2k dividers (HC-SR04 echoes at 5V). TRIG is
driven directly. Sonar VCC is 5V, not 3V3.

**Other GPIO**

- GP2 / GP3 — I²C, via ISO1540 isolator to the whole device bus
- GP15 — BNO085 interrupt
- GP0 / GP1 — RESERVED for AI HAT EEPROM, do not use
- GP7, GP8–GP11 — free (retired SPI/MCP3008)

**Serial console must stay disabled.** GP14 and GP15 are UART0 TXD/RXD. With
the console enabled the kernel drives GP14 as an output onto the left sonar's
divider node. Disabled and verified 2026-08-14. Symptom if it regresses:
front and right sonar read fine, left returns garbage.

---

## Hardware pitfalls that have already cost time

- **Motor− (white) never lands on an MCP23017 GPIO.** It goes to a FeatherWing
  motor terminal. A motor lead on a logic pin destroyed the first MCP23017.
- **ADS1115 A0 must read 2.76–3.06V before the ADC is powered.** It sits on a
  10k / ~3.2k divider off the 12V bus. A reading near 12V means the divider is
  open and the part will be destroyed on power-up.
- **AMS1117-3.3 input is the 5V rail, never 12V.** Fed from 12V it dissipates
  ~9V across the pass element, overheats, and drags VCC2 down progressively.
  This presented as devices dropping off successive scans — ten, then six,
  then four — with no rewiring between them.
- **ISO1540 sides are not interchangeable.** Side 1 (Pi side) takes max 40pF
  and one device; Side 2 (bus side) takes 400pF and multiple nodes. Wiring the
  ten-device bus to Side 1 silences the bus. This has cost the build twice.
- **A degrading failure means thermal.** A wiring fault gives the same wrong
  answer every time; a part in thermal foldback gives a progressively worse one.

---

## Known contradictions — resolve before trusting either source

These are unresolved disagreements between the engineering docs. Do not
silently pick one; flag them.

1. **Motor mapping.** §9.1 assigns 0x60 → LF/LM/LR and 0x61 → RF/RM/RR (one
   board per side). The §17.4 row labels alternate sides. §9.1 is the
   wiring-level table and should win. Wrong mapping means the rover turns the
   wrong way rather than failing outright.
2. **Arm shoulder channels.** §11.1's table gives J1a=CH1, J1b=CH2; the prose
   below it says CH10/CH11, which is outside the CH0–CH6 range that section
   defines. J1a/J1b are a mirrored pair driving one axis:
   `J1b = 2×1500µs − J1a`.
3. **Motor crimps unverified.** Five of six motors have not been checked
   against the corrected colour scheme (Red=Motor+, White=Motor−, Blue=Enc
   VCC, Black=Enc GND, Yellow=Phase A, Green=Phase B). Meter before trusting
   wire colour — batch variation is documented.

---

## Architecture constraint — keep the NPU out of the safety path

An AI HAT+ 2 (Hailo-10H) is installed and PCIe-bonded as of 2026-08-16 (`/dev/hailo0`,
`hailortcli fw-control identify` reports firmware 5.1.1, architecture HAILO10H). This was a
driver/package mismatch, not a hardware fault: the board had the Hailo-8-only package line
(`hailo-all`) installed, whose driver's PCI ID table doesn't include the Hailo-10H's ID
(`1e60:45c4`) — it loaded but silently never bound the device. Fixed by swapping to the
`hailo-h10-all` package line (`h10-hailort`, `h10-hailort-pcie-driver`, `python3-h10-hailort`).
`vision.py`/`ObjectDetector` has not yet been wired to use it — still CPU-only YOLOv8,
`ENABLE_OBJECT_RETRIEVAL=False`. When integrating it:

- **Reflex layer** — sonars, encoders, INA260 current monitors. Deterministic,
  drives the emergency stop. Must never wait on vision.
- **Deliberative layer** — the NPU. Frame-rate at best, variable latency,
  seconds-scale for LLM/VLM. Feeds `world_model.py` for planning and
  classification only.

An obstacle stop must never depend on a detection frame arriving. Vision
informs navigation; it does not gate the stop.

---

## Power

- Pi 5V rail measured 5.144V under boot load, `vcgencmd get_throttled` = 0x0.
  Floor is 4.85V. Do not let changes erode that margin.
- Worst-case 5V draw is already near 9A against an 8A UBEC rating. The AI HAT
  draws from this same rail — budget before fitting.
- GPIO power bypasses the Pi's onboard input protection, so brownout
  protection is firmware-only via the 0x44 INA260. There is no hardware
  supervisor behind it.
- A hard cut at the main switch or E-stop with the OS running risks filesystem
  corruption. The graceful path is `shutdown -h now` followed by Switch 2.
  Bulk capacitance cannot hold a Pi 5 up long enough to shut down — that would
  need farads, not microfarads.

---

## Reference documents

The authoritative source is the **WildWilly Master Engineering Package
rev 6.2.0** and the **Functional Requirements Document v2.3**. Section numbers
cited above (§5.7, §9.1, §11.1, §17.4) refer to rev 6.2.0.
