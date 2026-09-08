> ⚠ **NOT BUILT — status corrected 2026-09-08.**
>
> The TCA9548A was bought, strapped to `0x74`, wired, and **proven working** on
> 2026-09-08: `pca954x 1-0074: registered 8 multiplexed busses`, channels
> scannable, devices reachable through them. It was then **removed** in favour
> of a simpler topology — two passive GODIY hubs, every device on one segment.
>
> The design below is therefore sound and tested but **not the current build**.
> Master Hardware Design §0 is authoritative. The overlay line remains in
> `config.txt` and harmlessly fails to probe at boot.
>
> Worth keeping: the fault that motivated this spec — one device clamping the
> bus and taking down all eleven — remains entirely possible in the current
> topology, because passive hubs give no containment. If that recurs, this is
> the answer and the hardware is already on the shelf.

---

# I²C Segmentation via TCA9548A Multiplexer — Design

**Date:** 2026-09-07
**Status:** Design approved, not implemented
**Supersedes:** the second-Pi-bus approach explored earlier the same day
(`dtoverlay=i2c3-pi5,pins_22_23` + a second ISO1540). Not built; the mux
achieves the same separation with one part instead of three.

---

## 1. Goal

Separate the actuator drivers (PCA9685 ×2, FeatherWing ×2) from the sensing and
monitoring devices, to reduce bus loading and to make a dead segment
diagnosable.

Bus capacitance is the driver. §3.2 of Master Hardware Design records 300–400pF
across twelve taps on drop cables, against ~75pF supported by a 4.7kΩ pull-up —
which is why an LTC4311 was fitted. The Side-2 4.7kΩ rail pair has since been
removed (undocumented; see §8), so the margin is worse than the document
describes.

A multiplexer presents only the selected channel's taps to the master, so each
segment is ~50pF rather than 300–400pF. That is a larger improvement than
splitting the bus in two, which would only have halved it.

## 2. Topology

```
Pi GP2/GP3  ──  ISO1540  ──  isolated rail (SDA2/SCL2)
                                 │
                                 ├── INA260 0x40, 0x44, 0x45     (trunk)
                                 ├── Witty Pi 0x51               (trunk)
                                 └── TCA9548A 0x71               (trunk)
                                        ├── ch0: 0x42, 0x43, 0x60, 0x61  (+0x70)
                                        └── ch1: 0x27, 0x48, 0x4A
                                            ch2–ch7 unused
```

**One isolator, everything behind it** (owner-confirmed 2026-09-07). There is a
single ISO1540; the trunk devices and the mux both sit on Side 2. Nothing in
this design lives on Side 1 except the Pi's own GP2/GP3.

**Trunk devices stay always-visible.** The INA260s and Witty Pi are the
instruments and the power backstop — the set you read *to diagnose a fault*.
Putting them behind a new single point of failure would mean a mux failure costs
power management and current monitoring at the moment they are most needed.
Their addresses are unique, so trunk placement costs nothing.

| Segment | Devices | Rationale |
|---|---|---|
| Trunk | `0x40` `0x44` `0x45` INA260 · `0x51` Witty Pi · `0x71` mux | Survive a mux fault |
| ch0 | `0x42` `0x43` PCA9685 · `0x60` `0x61` FeatherWing | Noisy actuators; confines `0x70` |
| ch1 | `0x27` MCP23017 · `0x48` ADS1115 · `0x4A` BNO085 | Reflex-path sensors |
| ch2–7 | — | Spare; see §9 |

## 3. Addressing — the `0x70` collision

**The TCA9548A must be strapped to `0x71`.** Its default address is `0x70`,
which on this build is the PCA9685 All-Call broadcast — answered whenever either
PCA9685 is alive (CLAUDE.md, Master Hardware Design §3.3).

At the default address the collision is bidirectional and silent: every
channel-select write to the mux is simultaneously an All-Call write to both
PCA9685s, and any All-Call the servo code issues lands on the mux control
register and reroutes the bus mid-transaction.

Strap A0 high, A1/A2 low. `0x71` is unused in the current map.

Confining the PCA9685s to ch0 also means `0x70` never appears on ch1. The
sensor segment's roll-call becomes unambiguous for the first time, and
CLAUDE.md's "expect ten, not eleven" caveat stops applying to it.

## 4. Electrical

- **Pull-ups per channel.** Each active downstream channel needs its own pair.
  The breakout carries pull-ups on the trunk side only. Values to be chosen
  against measured per-segment capacitance, not inherited from §3.2's figures,
  which describe a bus that no longer exists in that form.
- **LTC4311.** Its disposition is open. With ~50pF per segment the accelerator
  may be unnecessary; if retained it belongs on the trunk. Decide by
  measurement after segmentation, not before.
- **Power.** Mux sits on VCC2. Adds a few mA to the AMS1117, which is already
  carrying bus devices plus the touch sensor with no measured total (Master
  Hardware Design §14 item 6). Not thermally significant on its own, but it
  belongs in that measurement when it happens.
- **Isolation.** The mux provides electrical separation between deselected
  channels only. It is not isolation: one VCC2, one ground. A rail fault still
  takes everything. This design does not improve fault independence, only
  loading and diagnosability.

## 5. Software — bus registry

`config.py`:

```python
I2C_TRUNK_BUS  = 1       # /dev/i2c-N of the existing bus
ENABLE_I2C_MUX = False   # flip when the hardware lands (see §7)
I2C_MUX_ADDR   = 0x71    # NOT 0x70 — see §3
I2C_CH_ACTUATOR = 0
I2C_CH_SENSOR   = 1
PCA9685_ALLCALL_ADDR = 0x70   # broadcast, never counted as a device
```

New module `i2c_buses.py`, the single place a bus or channel is opened:

- `trunk()` → the underlying `busio.I2C`, cached
- `channel(n)` → `TCA9548A(trunk(), address=I2C_MUX_ADDR)[n]`, cached
- **When `ENABLE_I2C_MUX` is False, `channel(n)` returns `trunk()`** — behaviour
  identical to today on unmodified hardware. This is what makes Phase 1 a no-op.
- Sole place `SIMULATE_HARDWARE` is honoured; today each of six call sites
  decides independently.

Call sites, replacing six separate `busio.I2C(board.SCL, board.SDA)`
constructions:

| File | Uses |
|---|---|
| `motors.py` | `channel(I2C_CH_ACTUATOR)` — FeatherWings *and* `Steering`'s `0x42` |
| `arm.py` | `channel(I2C_CH_ACTUATOR)` — `0x43` |
| `sensors.py` | `channel(I2C_CH_SENSOR)` for `0x27`/`0x48`/`0x4A`; `trunk()` for INA260 |
| `brain.py` | both, plus `trunk()`, for the self-test |
| `diagnostics.py` | all segments |
| `scripts/wheel_current_test.py` | `trunk()` |

**Thread safety.** Channel selection is mux state, and Willy runs a tick thread
alongside AI worker threads. `adafruit_tca9548a` takes the I²C lock for the
duration of a transaction, which is sufficient — provided nothing bypasses the
channel objects to touch the trunk directly while a channel is selected. No
current code does; `i2c_buses.py` being the only construction point is what
keeps that true.

**Latency is not a constraint.** A channel select is a one-byte write, ~19 bits
at 100kHz ≈ 190µs. A tick that reads sensors then commands motors pays two
switches ≈ 0.4ms, against `TICK_OVERRUN_THRESHOLD_S = 0.15`. This does not
influence channel allocation.

## 6. Self-test and validation

`brain.py::_self_test()` becomes per-segment: select each channel, scan, compare
against that segment's expected set, and name the failing segment in the
message. `0x70` is excluded from every count and can only appear on ch0.

`config.validate()` gains: the two channel numbers differ; `I2C_MUX_ADDR` is not
`0x70`; the three expected sets are pairwise disjoint; every configured device
address appears in exactly one set. Given this repo's history of transposed and
drifting addresses, this check earns its place.

## 7. Rollout

**Phase 1 — software only, ships before any hardware.**
`ENABLE_I2C_MUX=False`, so every segment resolves to the trunk and behaviour is
byte-for-byte today's. All six call sites, the registry, the per-segment
self-test and the validation land and are exercised on the real rover against
the existing single bus.

**Phase 2 — hardware.** Strap the mux to `0x71`, fit it on the isolated rail,
move the seven muxed devices onto ch0/ch1, add per-channel pull-ups, then flip
`ENABLE_I2C_MUX=True`.

The point of the ordering is that the hardware day becomes a one-line config
change rather than a rewire and a code change at once.

## 8. Open items

1. ~~Which side of the ISO1540 do the INA260s and Witty Pi sit on?~~
   **RESOLVED 2026-09-07 (owner): one isolator, everything behind it.** §3.2's
   diagram was right to place the INA260s on Side 2, and Witty Pi joins them.

   This has a diagnostic consequence for the fault open on the same day. On
   2026-09-07 `0x40`, `0x44`, `0x45` and `0x51` answered while `0x27`, `0x42`,
   `0x43`, `0x48`, `0x4A`, `0x60` and `0x61` were dark, repeatably. If every one
   of those devices sits behind the same isolator on the same rail, then **the
   ISO1540, VCC2 and the SDA2/SCL2 trunk are all proven good** — a rail or
   isolator failure could not spare four devices on it. The fault is therefore
   confined to whatever the seven dark devices share and the four live ones do
   not: a branch, a connector, or a sub-rail. Hypotheses involving the AMS1117
   or a loose VCC2 feed are excluded by the same reasoning, since either would
   have taken the INA260s down too.
2. **The 4.7kΩ Side-2 pull-ups were removed** and this is recorded nowhere.
   §3.2 still lists them; §14's pre-power check still says to verify them. Needs
   folding into the three documents independently of this work.
3. **Is the LTC4311 still fitted and enabled?** Removing static pull-ups is
   sound *with* an accelerator and a bus-killer without one. Leading candidate
   for the 2026-09-07 dead segment.
4. **Per-channel pull-up values** — measure segment capacitance first.
5. **AMS1117 total load** with the touch sensor, per §14 item 6.

## 9. Consequences worth keeping

The six spare channels are a diagnostic asset, not just headroom. A dead segment
can be bisected by bringing devices up channel by channel — which on 2026-09-07
would have separated "rail fault", "one bad device pulling the bus down" and
"pull-up/rise-time failure" in minutes rather than a day.

## 10. What this design does not do

It does not improve fault independence. One rail, one ground, **one isolator
with every device behind it**, and now one more part in series with seven of
them. The single isolator is confirmed as-built, not an assumption — so it
remains a whole-bus single point of failure, and the mux adds a second one
covering seven of the eleven devices. If the goal shifts from loading
to surviving a rail failure, that needs a second isolator and a second
regulator, which this explicitly does not provide.
