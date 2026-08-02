# WildWilly — PCA9685 Arrival Punch-List
*Execute in order. Don't skip ahead — each step gates the next.*

## 0. Before touching anything — safety first
- [ ] **Install / verify the physical E-stop** (latching NC mushroom, cuts 12V bus). BOM says ON HAND but no build-log entry confirms it's actually mounted. This is a hard prerequisite before any powered test with motors connected — do this before step 2, not after.
- [ ] Confirm KCD4 master switch is OFF and stays OFF until explicitly needed.

## 1. Bench-check the new PCA9685 boards BEFORE they go anywhere near the tray
- [ ] Bare-board power test: 3V3 + GND only, no servos, no other devices on the bus. i2cdetect should show a clean address (0x42 default, 0x43 once A0 jumper bridged) with zero dmesg errors.
- [ ] Meter-verify VCC=3.3V pin and the V+ screw terminal are NOT bridged (per the standing rule from the earlier bus-node-board incident).
- [ ] Only after both boards individually pass bare-bus test → proceed to landing.

## 2. Land the 4 remaining connection points (§0.2 of the master doc)
Work in this order — deepest/most failure-prone first:
- [ ] **Arm bulkhead → PCA9685 0x43 CH9–15** — 7 servo signal leads (base→gripper order), V+/GND direct to 6V rail. This was the actual blocker; do it first so if anything's wrong you find out early.
- [ ] **40-pin ribbon, base → top** — route flat, no fold, stripe→pin1 both ends, meter-verify before power.
- [ ] **Pi power feed** — DROK 5.1V rail to the Pi.
- [ ] **Sonar harness join** — base ↔ top/head (mechanical only, already electrically complete).

## 3. Re-run I²C roll-call (bus node board still connected, base 12V still OFF)
- [ ] i2cdetect -y 1 should show all 9: **0x27, 0x40, 0x42, 0x43, 0x44, 0x45, 0x4A, 0x60, 0x61** (+0x70 All-Call).
- [ ] If either PCA9685 fails to show or hangs the bus again (SDA stuck low symptom from before) — STOP. Don't push forward into powered tests. That's a hardware issue on the new board or the landing, not a "keep going and see."

## 4. Commissioning gates — power up in this exact order (§21.1)
- [ ] **C-5**: Staged Pi power-up. Set `usb_max_current_enable=1` first. Connect Pi power. Boot. INA260 0x44 shows Pi rail ≥4.85V under boot load, no brownout. **Do not command any actuators yet.**
- [ ] **C-6**: Post-boot I²C confirm — i2cdetect shows the same 9 addresses with the Pi fully booted.
- [ ] **C-7**: FET temp under sustained ~15A load — Q1 tab warm-not-hot.
- [ ] **C-8**: Steering torque check — each DS041MG turns its loaded wheel at 5V.

## 5. First movement — low duty, one subsystem at a time
- [ ] Motors: each of the 6, low duty, one direction then the other, confirm encoder counts increment in the expected sign.
- [ ] Steering: sweep each of the 6 servos through its centered range, confirm no crab/skew at "straight."
- [ ] Arm: move each of the 7 joints through range at low speed — watch for the arm turret clearing the AI HAT+ through the FULL sweep, not just stow.
- [ ] Sonar: confirm front/left/right ranging (this was never functionally pulse-timing tested).
- [ ] IMU: confirm tilt/heading reads sane.

## 6. If it all passes
- Willy drives, steers, and the arm moves under manual/teleop command. That's the realistic "alive" milestone for today — not autonomy, not the handoff pose, not YOLO.
- Log actual pass values (voltages, PPR measured vs. the 823 PPR starting estimate, servo end-stops vs. the 500–2500µs starting values) back into the master engineering package so the next session isn't re-deriving them.

## If something goes sideways
Given this build's track record (Pi replacement, INA219 fault, bus-node miswiring, MCP3008 CH7 over-voltage, now the PCA9685 fault), assume something unexpected is more likely than a clean pass. Stop at whichever step fails, don't push through to the next one, and note the exact symptom (which gate, what reading, what dmesg said) — that's the pattern that's resolved every prior incident on this build.
