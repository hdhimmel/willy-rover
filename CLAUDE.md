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
| 0x43 | PCA9685 | Arm servos, CH1–CH7 (CH0 unused, shifted 2026-08-21) |
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

**Witty Pi 5 install/config runbook — install + config both done, 2026-08-20/21.** `wp5` (CLI)
+ `wp5d` (daemon, `systemctl status wp5d.service`) are installed and running, confirmed talking
to the HAT (`/var/log/wp5d.log`: "Connected to Witty Pi 5", firmware v1.4). RTC synced. Via
`wp5`'s "Other settings..." submenu, configured 2026-08-21:
- **Default state when powered → ON, 2s delay** — Willy now boots when power is connected
  rather than requiring the HAT's physical button; the 2s delay is just a debounce against a
  brief power blip triggering a full boot.
- **Power source priority → V-USB first** (matches actual wiring).
- **Watchdog → Enabled, 200 missed heartbeats** (~10-20s at `brain.py`'s tick's ~50-100ms
  heartbeat cadence — tolerant of ordinary hiccups, still catches a genuinely wedged kernel).
- **Low-voltage threshold (options 7/8) deliberately left untouched** — still confirmed
  VIN-specific behavior per the manual; don't set this until it's verified to do something sane
  on VUSB. The existing software battery-tier system (real ADC) remains primary regardless.

`config.ENABLE_WITTY_PI=True` is now set, 0x51 is in `brain.py`'s self-test expected-device set.
See the Power section below for a live under-voltage issue found 2026-08-20 — still open, needs
a physical cable/connector check, independent of the above.

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
- GP7 — encoder interrupt (`config.ENCODER_INT_PIN`), interrupt-driven quadrature decode.
  Hardware prerequisite: MCP23017 INTA must be wired to this pin — not yet done, falls back
  to polling until it is.
- GP8–GP11 — free (retired SPI/MCP3008)

**SPI0 must stay disabled (`dtparam=spi=off` in `/boot/firmware/config.txt`).** Found and
fixed 2026-08-20: even with the MCP3008 physically removed, `dtparam=spi=on` still made the
kernel unconditionally reserve GP7/CE1, GP8/CE0, GP9/MISO, GP10/MOSI, GP11/SCLK as SPI0
hardware pins at boot — regardless of whether anything used the bus. This crash-looped
`willy-rover.service` on every single restart: `Encoders.start()`'s `GPIO.setup(config.
ENCODER_INT_PIN, ...)` hit `lgpio.error: 'GPIO busy'` deterministically (confirmed even with
the service fully stopped, via a standalone script — not a restart race), and the uncaught
exception's native unwind then crashed the process with a different signal each time (SIGABRT/
SIGSEGV/SIGBUS), which is why it initially looked like two unrelated bugs. Verify with
`sudo cat /sys/kernel/debug/gpio | grep spi0` before reusing any of GP7–GP11 — it should show
nothing if SPI0 is genuinely off.

**Serial console must stay disabled.** GP14 and GP15 are UART0 TXD/RXD. With
the console enabled the kernel drives GP14 as an output onto the left sonar's
divider node. Disabled and verified 2026-08-14. Symptom if it regresses:
front and right sonar read fine, left returns garbage.

---

## Hardware pitfalls that have already cost time

- **Arm servo connector(s) found disconnected under the cover, 2026-08-20 — unresolved,
  physical fix needed.** Voice-triggered `arm_home`/`wave` both dispatched correctly in
  software (heard, matched, `brain.py::_drain_voice_commands()` called `arm.center_all()`/
  `_start_wave()`, TTS ack played) but produced zero physical motion. Owner felt the wrist
  joint resist manual movement (taut, consistent with a powered/holding servo elsewhere on the
  chain), then opened the cover and found some servo connector(s) actually unplugged — this is
  the real cause, not the live under-voltage issue investigated the same day (that remains a
  separate, still-open item — see Power section). Re-seat the disconnected connector(s) and
  retest with a voice `arm_home` before assuming this is closed; which specific joint(s) were
  disconnected was not identified before stopping for the day.
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
2. **Arm shoulder channels — resolved.** J1a=CH2, J1b=CH3 (channels shifted +1 on
   2026-08-21 — was CH1/CH2 before), a mirrored pair driving one physical axis:
   `J1b = 2×1500µs − J1a`. See §8.

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
`vision.py`/`ObjectDetector` is now wired to use it (2026-08-21, `ENABLE_HAILO_VISION=True` —
see the CSI/Hailo note below). The older CPU/ultralytics path against the Arducam remains in
place as an unconditional fallback and stays off (`ENABLE_OBJECT_RETRIEVAL=False`).

**Camera orientation — corrected 2026-08-20, was wrong in code.** There are two physical
cameras: the Arducam OV9281 (USB, `config.CAMERA_DEVICE=/dev/video8`) and a Pi Camera Module
(CSI, imx708, `rp1-cfe` driver, `/dev/video0`-`7`). Owner confirmed **the Arducam is mounted
REAR-facing and the CSI camera is FRONT-facing** — the opposite of what `vision.py`'s
`_CAMERA_ID='front'` label and `retrieval_task.py`'s detect-then-drive-forward logic both
assume. `ENABLE_OBJECT_RETRIEVAL` was briefly flipped True and live-verified working end-to-end
(model, cv2 5.0.0, ultralytics 8.4.115, real frame captured, mean brightness confirmed non-zero
— the full pipeline genuinely works), then reverted immediately once the orientation was
flagged, since driving toward what a rear camera sees would misdirect retrieval/pursuit.

**CSI/Hailo vision backend — live-verified working 2026-08-21.** The orientation correction above
led to CSI front camera + Hailo-10H backend integration (using picamera2.devices.Hailo for NPU
access, CSI imx708 for capture). Integration complete and live-verified end-to-end.
`config.ENABLE_HAILO_VISION=True` (enabled 2026-08-21). Hailo backend loads correctly at startup;
real detection round-trips confirmed working with `camera_id='front'` on the CSI camera.
Reflex/deliberative layer separation still applies:

- **Reflex layer** — sonars, encoders, INA260 current monitors. Deterministic,
  drives the emergency stop. Must never wait on vision.
- **Deliberative layer** — the NPU. Frame-rate at best, variable latency,
  seconds-scale for LLM/VLM. Feeds `world_model.py` for planning and
  classification only.

An obstacle stop must never depend on a detection frame arriving. Vision
informs navigation; it does not gate the stop.

**Autonomous ROAM gated off pending vision — added 2026-08-20.** `brain.py::_idle()`'s
idle-timeout auto-wander and the post-charging auto-resume (`_tick()`'s `DOCK` handling) both
now check `config.ENABLE_AUTONOMOUS_ROAM` (default `False`) before calling `_go('ROAM')`.
Found live: with only sonar for obstacle sensing (no vision yet), Willy was wandering
unprompted and tripping repeated `STALL_FAULT`s against things sonar didn't catch — sometimes
5 of 6 wheels at once. Owner decision: no unprompted autonomous driving until vision is live-
verified working (see the camera-orientation note above — not there yet). Manual/voice-
commanded driving is unaffected; this only blocks the unprompted idle/post-charge wander.

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
  the Pi's own OS/kernel is doing — now installed and software-configured
  (see below), but the underlying undervoltage gap itself is still open.

**Live under-voltage found 2026-08-20, root-caused and fixed 2026-08-21 — degraded AMS1117-3.3.**
`dmesg -T | grep -i voltage` showed `hwmon3: Under-voltage detected!` / `Voltage normalised`
cycling every 15-30s continuously, confirmed present even with `willy-rover.service` fully
stopped (owner caught this independently; not driven by rover software/CPU load). The next day
this had escalated into the isolated I2C bus itself flickering — repeated `i2cdetect -y 1`
scans one second apart showed *different devices* dropping in and out unpredictably (0x27,
0x42, 0x43, 0x44 flickering; 0x45/0x48/0x4a not appearing at all for a stretch), not a clean
single-device failure. Owner found and reconnected two separate loose connectors along the way
(a servo connector, then a "base side" power connector) — real issues, but neither one fully
stabilized the bus. **Root cause**: the AMS1117-3.3 regulator (VCC2, feeding the isolated bus
side) had degraded — the same failure category already documented above (fed the wrong
voltage, or just failed from that historical stress), pulling down its shared upstream supply
enough to also trip the Pi's own brownout detector, which is why both symptoms tracked
together. **Fixed by physically swapping the part** — confirmed with 18 consecutive
`i2cdetect -y 1` scans (10 before + 8 after reinstalling the ADS1115), one second apart, **zero
flicker**, full 11-device set present every single time. The `hwmon3` under-voltage messages
also stopped recurring the same moment (40+ min clean afterward, vs. cycling every 15-30s
before) — one root cause explains both symptoms, not two separate issues.

**Planned upgrade, not yet done**: replacing the AMS1117-3.3 (linear regulator, prone to this
exact thermal-foldback failure mode) with a **TI TPSM84203EAB** integrated buck power module —
4.5-28V input (would have tolerated the original 12V-miswiring failure mode instead of cooking
itself), fixed 3.3V/1.5A output, ~95% efficiency, 3-pin TO-220 footprint confirmed by the owner
as a direct drop-in for the current part, no rewiring needed. Do this before the replacement
linear part fails the same way a third time.

The abnormally slow local-LLM voice latency measured 2026-08-20 (`intent=40.9s` vs. this repo's
own documented ~15-20s expectation from the 2026-08-15 voice latency work, `vcgencmd
get_throttled` reading `0x50000`) was measured *before* this fix — likely explained by CPU
throttling from the same under-voltage condition. Not yet re-measured post-fix; do that before
any further voice-latency software work (see owner's 2026-08-20 "needs to be immediate" ask).
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
