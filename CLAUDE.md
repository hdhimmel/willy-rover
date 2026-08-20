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

**Witty Pi 5 HAT+ (0x51) — NOT YET PHYSICALLY INSTALLED, software prepared ahead of it
(2026-08-20).** Per its own user manual, it uses only SDA/SCL — confirmed no conflict with
anything above. Wired via VUSB (USB-C, off the existing 5V/0x44-monitored rail), not the VIN
screw terminal. `config.ENABLE_WITTY_PI` stays `False` (and 0x51 stays out of `brain.py`'s
self-test expected-device set) until it's actually connected — flip it on then, not before.
See `docs/WildWilly_Software_Design_v1.0.md` §4.1 for the integration story and the open
VIN-vs-VUSB low-voltage-threshold question that needs live testing, not a guessed number.

**Witty Pi 5 install/config runbook — not yet run, execute once the HAT is physically on:**
```
wget https://www.uugear.com/repo/WittyPi5/wp5_latest.deb
sudo apt install ./wp5_latest.deb
wp5   # interactive menu:
      #   Other settings... -> Power source priority -> V-USB first (matches actual wiring)
      #   Other settings... -> Watchdog -> Enabled, pick a missed-heartbeat count once
      #     witty_pi.py's heartbeat cadence is live-observed (don't guess a number blind)
      #   Do NOT set the low-voltage threshold (options 7/8) yet -- confirmed VIN-specific
      #     behavior per the manual; verify it does something sane on VUSB before relying on it
i2cdetect -y 1   # confirm 0x51 answers
```
Then in the repo: set `config.ENABLE_WITTY_PI=True`, `git commit`/push/pull-on-rover, restart
`willy-rover.service`, and confirm the self-test still passes with 0x51 now in the expected set.

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

## Contradictions from older docs — resolved by Master Hardware Design v2.0

These used to be genuine open disagreements between the engineering docs
(flagged here 2026-08-14 against the old Master Engineering Package's
internal inconsistencies). Master Hardware Design v2.0 gives each a single,
unambiguous answer now — recorded here only so nobody re-opens them by
citing the old, superseded wording:

1. **Motor mapping — resolved.** 0x60 drives the LEFT side (LF/LM/LR),
   0x61 drives the RIGHT side (RF/RM/RR), one board per side. See
   `docs/WildWilly_Master_Hardware_Design_v2.0.md` §7.2.
2. **Arm shoulder channels — resolved.** J1a=CH1, J1b=CH2, a mirrored pair
   driving one physical axis: `J1b = 2×1500µs − J1a`. See §8.

Still genuinely open (not a doc contradiction — a real unverified-hardware
item, tracked in Master Hardware Design v2.0 §14):

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
- Separately, worst-case steering draw is also near 9A, but through the
  PCA9685 boards' own V+ terminal/PCB trace/channel-header path, not the Pi's
  5V rail above — servo current now flows through the board itself, not just
  signal current. Confirm against the board's ratings before running all six
  steering servos under load simultaneously (Master Hardware Design v2.0 §14).
- GPIO power bypasses the Pi's onboard input protection, so brownout
  protection is firmware-only via the 0x44 INA260. There is no hardware
  supervisor behind it. **The Witty Pi 5 HAT+ (above) is the intended fix for
  this** — its own MCU can force a real power cycle independent of whatever
  the Pi's own OS/kernel is doing — but it isn't installed yet; don't treat
  this gap as closed until it is, live-verified.
- A hard cut at the main switch or E-stop with the OS running risks filesystem
  corruption. The graceful path is `shutdown -h now` followed by Switch 2.
  Bulk capacitance cannot hold a Pi 5 up long enough to shut down — that would
  need farads, not microfarads.

---

## Reference documents

The authoritative set, as of 2026-08-18, is three companion documents:

- **WildWilly Master Hardware Design v2.0** — as-built hardware, BOM,
  pin-to-pin connection schedule (§16). Section numbers cited elsewhere in
  this file (§7.2 motor mapping, §8 arm, §14 open items) refer to this
  document.
- **Functional Requirements Document v3.1** — what the rover must do and how
  each requirement is proven (§V verification register, §V.1 coverage,
  §V.2 known gaps).
- **WildWilly Software Design v1.0** — module architecture, control
  layering, FSM, safety gate.

**Do not cite the old Master Engineering Package (any revision) as
authoritative.** `docs/archive/WildWilly_Master_Engineering_Package_rev6.0.7.md`
is the oldest document in the repo — it predates the isolator orientation
fix, the Seengreat breakout swap, channel-header servo power, the
FeatherWings and the ADS1115, and its §5.7/§17.4 section numbers do not
exist in it (they were only ever created in a later "rev 6.2.0" that was
never committed to this repository — the historical record is a real
document, it just isn't in git). If that history is wanted in-repo, commit
it as its own file; don't treat citing its section numbers as equivalent to
having it, and don't resurrect rev 6.0.7 as a stand-in for it (found and
corrected 2026-08-18 — an earlier pass in this file wrongly did exactly
that, pointing here at rev 6.0.7 instead of recognizing rev 6.2.0 as a real,
newer, uncommitted document; see Master Hardware Design v2.0 §17.2 for the
full finding).
