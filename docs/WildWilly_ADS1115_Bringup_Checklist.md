# WildWilly — ADS1115 Bring-up Checklist

Replaces the MCP3008 for battery/charge sensing (see `WildWilly_MCP3008_AllZero_Checklist.md`, closed 2026-08-02 — that chip's fault was never conclusively isolated; switching ADC families sidestepped the ambiguity rather than resolving it).

I²C @ 0x48 (ADDR→GND, default), joins the existing 9-device bus fan-out (§17.2 master doc). SPI0 pins (phys 19/21/23/24) freed by this swap.

## Bring-up status

- [x] Chip enumerates on the I²C bus (`i2cdetect -y 1` shows 0x48, no address conflict with the other 9 devices) — confirmed 2026-08-02.
- [x] Standalone probe script written: `/home/hhimmel/ads1115_probe.py` (raw smbus2 register I/O, single-shot mode, PGA ±4.096V, all 4 channels) — mirrors `mcp_probe_all.py`'s role for this chip.
- [x] AIN0 (battery divider) reads a real, stable, proportional value — confirmed 2026-08-02.
- [x] `sensors.py`'s `ADC` class rewritten for I²C/ADS1115 (was SPI/MCP3008); `config.py` updated (`ADS_ADDR`, `ADS_CH_BATTERY`, `BATTERY_DIVIDER_SCALE`, `BAT_FULL_V`/`BAT_LOW_V`/`BAT_CRITICAL_V`). Verified: imports clean, `read_channel`/`start`/`stop` all exercised live against hardware, `brain.py`'s existing call sites (`battery_pct`, `battery_low`, `battery_critical`, `is_charging`) unchanged.
- [ ] **Re-calibrate `BATTERY_DIVIDER_SCALE` against a multimeter.** The current value (0.2481) is carried over from the MCP3008 and was trimmed specifically for *that* chip's input loading (§20.4 master doc). The ADS1115 has much higher input impedance and loads the divider less — bench reading right now implies ~13.2V battery via the old constant, which is above the documented 10.2–12.6V pack range, consistent with the old scale no longer being correct for this chip. Meter the actual pack voltage and recompute the scale (and `BAT_FULL_V`/`BAT_LOW_V`/`BAT_CRITICAL_V` if the pack chemistry/range assumption needs revisiting too).
- [ ] Wire the charge-sense divider to AIN1 (mirrors old MCP3008 CH6 usage) and implement `ADC.is_charging` for real — currently hardcoded to always return `False` since no charge signal exists yet. Note: `brain.py`'s DOCK-state logic (`if self.adc.is_charging: motors.stop()`) will not fire until this is wired — currently the conservative/safe default (never assumes charging), not a bug.
- [ ] AIN2/AIN3 unused for now — leave floating or decide a future use.

## Session log — 2026-08-02

- Part arrived and installed. Bus scan, probe script, and `sensors.py`/`config.py` rewrite all done this session (see checkboxes above). Calibration and charge-sense wiring deliberately deferred — user chose to skip multimeter calibration for this session; flagged clearly rather than guessing a new constant.
