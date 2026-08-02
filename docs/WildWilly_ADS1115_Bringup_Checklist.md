# WildWilly — ADS1115 Bring-up Checklist

Replaces the MCP3008 for battery/charge sensing (see `WildWilly_MCP3008_AllZero_Checklist.md`, closed 2026-08-02 — that chip's fault was never conclusively isolated; switching ADC families sidestepped the ambiguity rather than resolving it).

I²C @ 0x48 (ADDR→GND, default), joins the existing 9-device bus fan-out (§17.2 master doc). SPI0 pins (phys 19/21/23/24) freed by this swap.

## Bring-up status

- [x] Chip enumerates on the I²C bus (`i2cdetect -y 1` shows 0x48, no address conflict with the other 9 devices) — confirmed 2026-08-02.
- [x] Standalone probe script written: `/home/hhimmel/ads1115_probe.py` (raw smbus2 register I/O, single-shot mode, PGA ±4.096V, all 4 channels) — mirrors `mcp_probe_all.py`'s role for this chip.
- [x] AIN0 (battery divider) reads a real, stable, proportional value — confirmed 2026-08-02.
- [x] `sensors.py`'s `ADC` class rewritten for I²C/ADS1115 (was SPI/MCP3008); `config.py` updated (`ADS_ADDR`, `ADS_CH_BATTERY`, `BATTERY_DIVIDER_SCALE`, `BAT_FULL_V`/`BAT_LOW_V`/`BAT_CRITICAL_V`). Verified: imports clean, `read_channel`/`start`/`stop` all exercised live against hardware, `brain.py`'s existing call sites (`battery_pct`, `battery_low`, `battery_critical`, `is_charging`) unchanged.
- [x] **Re-calibrate `BATTERY_DIVIDER_SCALE` against a multimeter.** Done 2026-08-02: AIN0 read 3.2749V (raw 26199) while a multimeter on the pack terminals read 11.43V. New scale = 3.2749/11.43 = 0.2865 (was 0.2481, MCP3008-era). Verified: `battery_volts` now reads 11.431V against the 11.43V meter reading — matches to 1mV. `BAT_FULL_V`/`BAT_LOW_V`/`BAT_CRITICAL_V` left unchanged since those are already in battery-terminal volts (chip-independent).
- [ ] Wire the charge-sense divider to AIN1 (mirrors old MCP3008 CH6 usage) and implement `ADC.is_charging` for real — currently hardcoded to always return `False` since no charge signal exists yet. Note: `brain.py`'s DOCK-state logic (`if self.adc.is_charging: motors.stop()`) will not fire until this is wired — currently the conservative/safe default (never assumes charging), not a bug.
- [ ] AIN2/AIN3 unused for now — leave floating or decide a future use.

## Session log — 2026-08-02

- Part arrived and installed. Bus scan, probe script, and `sensors.py`/`config.py` rewrite all done this session (see checkboxes above). Calibration and charge-sense wiring deliberately deferred — user chose to skip multimeter calibration for this session; flagged clearly rather than guessing a new constant.
- Committed (`09e305c`): ADS1115 swap in `sensors.py`/`config.py`, plus first-time commit of `docs/`.

## Session log — 2026-08-02 (cont.)

- User metered the pack: **11.43V**. `BATTERY_DIVIDER_SCALE` recalculated and updated in `config.py` (0.2481 → 0.2865); `battery_volts` now reads 11.431V, matching the meter to 1mV. Checklist item closed above.
- Remaining open item: charge-sense divider (AIN1) still not wired; `is_charging` still hardcoded `False`.
