# 2026-08-21 — Power delivery fault + voice latency work

Session record. Two threads: a hardware power fault that turned out to be the
rover's real blocker, and a voice-latency pass that cut a spoken command from
16.7s toward ~6-8s.

---

## 1. The power delivery fault (unresolved — next session's job)

### What it is

**~0.223 Ω of resistance in the Pi's 5V power path.** Not the battery, not the
software, not supply capacity. Four instruments, same moment:

| Point | Reading | Source |
|---|---|---|
| Witty Pi V-OUT | 5.06V | `wp5` |
| 5V rail | 5.04V @ 1.39A | INA260 @ 0x45 |
| Multimeter at USB-C | 4.98V | handheld |
| **Pi's own input** | **4.73V** | `vcgencmd pmic_read_adc EXT5V_V` |

Everything upstream reads ~5.0V; only the Pi reads 4.73V.
`(5.04 − 4.73) / 1.39 = 0.223 Ω`.

### Why it kills the rover

Drop = I × R, so it scales with load:

| Current | Drop | Pi sees | Result |
|---|---|---|---|
| 1.4A (idle) | 0.31V | 4.73V | ok, barely |
| 2.0A | 0.45V | 4.59V | under-voltage + throttling |
| 2.9A | 0.65V | **4.40V** | observed low today |
| 3.8A | 0.85V | **4.19V** | **brownout / reset** |
| 5.0A | 1.12V | 3.92V | brownout |

A Whisper burst reaches that range; motors exceed it comfortably. This is why
"Hey Willie, what time is it?" reproducibly powered the rover off.

**A bigger buck will not fix this.** The supply is already holding 5.04V — it is
meeting demand. Adding capacity to a supply that is not the bottleneck changes
nothing.

### Where the resistance is

Almost certainly the **HAT header stack**, not a cable. `wp5` reports *V-OUT*,
and Witty Pi 5 is a Mode 1 Power HAT+ delivering through the 40-pin header. An
11-inch 7A USB-C cable swap changed nothing, and disturbing the stack to fit it
made things marginally worse. Both the AI HAT+ 2 and Witty Pi sit on that header.

### Done so far

- **Witty Pi low-voltage cutoff 4.8V → 4.5V.** It was set *above* the Pi's own
  4.63V threshold, so it cut power while the Pi was still fine. Bought a 3h19m
  stable stretch with 0 restarts.
- **`avoid_warnings=1`** added to `/boot/firmware/config.txt`. Backup at
  `/boot/firmware/config.txt.bak-1329`.

### Plan for next session — no new parts

1. Buck → **9.0V**, current limit **4-5A**
2. Buck output → Witty Pi **KF350-2P screw terminal** (spec: 6-30V in, 5A out),
   correct polarity
3. **Remove the USB-C feed** — one input only
4. **Reseat the HAT stack** ← likely the actual fix
5. Screen → the existing **5.14V rail** (INA260 @ 0x40, idling at 0.03A)
6. **5A fuse** battery-side
7. Re-check the Witty Pi cutoff afterwards

**Target: `EXT5V_V` = 4.95-5.05V** (from 4.73V).

Why 9V: the battery runs 11.24V down to 10.2V and a buck needs ~0.7V headroom, so
10V+ falls out of regulation before the pack empties. 9V still draws 1.8× less
current than 5V, cutting I²R losses ~3.2×.

**Warning:** 4.5V is meaningless as a threshold against a 9V input. And with the
buck regulating, a VIN-based cutoff can no longer detect a low battery at all —
software `BAT_SHUTDOWN_V=10.2V` remains, but the hardware layer stops guarding
the pack.

### Battery is not a constraint

2 × 16Ah at ~11.1V ≈ **355Wh** against ~9.3W measured idle draw ≈ **29h idle**,
4-7h driving. The rail cuts him after minutes, so energy is not remotely the
limit.

`battery_pct` on screen is a linear *voltage* map (0% = 10.2V, 100% = 11.58V —
only 1.38V wide), not a fuel gauge. It sags under load and recovers, so motion
will look like it drains far faster than it does.

---

## 2. Voice latency — 16.7s → ~6-8s

Baseline measured live for `"what time is it"`:
`stt=12.1s intent=0.0s tts=4.6s total=16.7s`, with the CPU at a full
**un-throttled 2.4GHz** — so this was real compute cost, not the power throttling
the NPU spec speculated about.

### Shipped

- **`WHISPER_MODEL_SIZE` `small.en` → `base.en`** — benchmarked on the device
  against a real clip: **5.71s → 1.88s, 3× faster, identical transcription.**
- **`WHISPER_CPU_THREADS=3`** (was unset = all 4 cores). 3t benchmarks no slower
  than 4t, so it lowers the current spike for free.
- **Endpointed capture** replacing the fixed 4s window (~2.1s saved).
- **Widened fast-path**, tiered by consequence of a false match.

### Fast-path tiering

The local LLM fallback is **74.2s** (total round trip 84.9s). The original
narrow-`fullmatch` design budgeted a miss at "15-20s" — it is ~15× worse than
that, so a missed phrasing reads as "not responding".

- **Tier 1** (time, battery, status, what_do_you_see, wave, arm, mapping) — a
  false fire only makes him speak. Widened aggressively.
- **Tier 2** (forward, reverse, turn left/right, shutdown) — cores unchanged;
  only address/trailer wrappers added.
- **`stop`** — widened despite being motion, because a false positive stops a
  robot nobody asked to stop. Fails safe.

Verified: **42 should-match phrasings, 19 adversarial rejections** including
`"don't stop"`, `"don't go forward"`, `"do not shut down"`, `"go to the kitchen"`.

### Still untested: endpointing

Two regressions shipped in one session, both from the wake chirp, both caught
only by live logs:

1. Discarding 0.3s of capture ate the first word → `"Time is it"` → fast-path
   miss → 84.9s.
2. After keeping the audio, the chirp itself latched `heard=True`, so the
   speaker's natural pause read as end-of-utterance and capture cut at 0.9s
   mid-sentence → empty transcript → `"How can I help?"`.

Both fixed (`deaf_frames` ignores the chirp window for the *decision* while
keeping its audio; two consecutive loud frames to latch; `VOICE_CAPTURE_MIN_S`
0.8 → 1.2s) and simulated — **but never confirmed on hardware.**

Escape hatch: `VOICE_ACK_ENABLED=False` drops the chirp and that entire bug
class, keeping `base.en` and the fast-path wins.

### Next biggest win: Piper

`voice.py::_synthesize_and_play()` spawns `piper` as a **subprocess per reply**,
reloading the ONNX voice every time. Benchmarked 2.3-2.5s standalone, 4.7s under
load — nearly all fixed overhead. Making it resident should land total ~6s.

---

## 3. Gotchas worth keeping

**`config.py` INA260 rail names do not match the wiring.** Measured:
`INA260_PI_ADDR` (0x44) = **11.24V** (battery rail), `INA260_MOTOR_ADDR` (0x45) =
**5.04V @ 1.39A** (the Pi's 5V), `INA260_SERVO_ADDR` (0x40) = 5.14V @ 0.03A.
Reasoning from the names produces false conclusions.

**`/boot/config.txt` is a stub on Debian 13.** Its contents literally say "DO NOT
EDIT THIS FILE". The firmware reads `/boot/firmware/config.txt` on a separate
vfat mount.

**journald does not retain previous boots** despite `/var/log/journal` existing —
`journalctl --list-boots` only ever shows boot 0, because hard power cuts never
flush. Post-mortem after a power loss is impossible; capture live.

**Probing I2C from a second process while the service runs causes false
failures.** `read_byte()` is not a valid probe for BNO08x/PCA9685/INA260 either.
The service's own `Self-test passed — all subsystems present` is the trustworthy
signal. Two false alarms were raised this way (the IMU, and Witty Pi apparently
"vanishing") — both were the probe, not the hardware.

**`i2c-tools` is not installed** on the rover. Use `smbus2` via
`./venv/bin/python3`, not `i2cget`/`i2cdetect`.

**`WHISPER_MODEL_SIZE` must be pre-downloaded** before changing. `voice.py` loads
with `local_files_only=True`, so an uncached name raises, is swallowed by
`_load_models()`'s except, and **silently disables the whole voice pipeline** with
no obvious symptom.

## 4. Useful commands

```bash
vcgencmd get_throttled            # 0x50005 = under-voltage NOW + throttled
                                  # 0x50000 = historical bits only
vcgencmd pmic_read_adc EXT5V_V    # the Pi's own view of its 5V input
sudo wp5                          # Witty Pi menu (stop the service first — I2C)
journalctl -u willy-rover.service -b 0 --no-pager | grep -E "capture:|Heard:|Fast-path|voice timing"
```
