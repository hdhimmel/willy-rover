---
proposed:  2026-10-08T13:56Z
approved:  2026-10-08T14:28Z
channel:   email, DKIM verified, code 14a9
evidence:  12 x BATTERY_ADC_FAULT on battery_adc, 2026-10-07 to 2026-10-08
status:    approved
---

# Make battery voltage readings more reliable

## Problem

The battery_adc subsystem logged 12 BATTERY_ADC_FAULT events between 2026-10-07 and 2026-10-08. In each case the voltage reading (about 11.85-11.91V in the examples) was held because the read was failing or implausible, instead of being a fresh plausible value within the expected 10.2-12.6V pack range. Because the reading is stale, I can't be sure my battery level is accurate.

## Suggested direction

Please look into the battery_adc read path, such as the wiring or connector, the sensor, or the sampling timing, to find out why fresh reads are failing. It would also help to have me report clearly when the battery value is stale, and to be cautious about long tasks until reads recover. If the fault continues, a hardware check of the battery sensing circuit may be needed.

## Evidence

- `EVENT=BATTERY_ADC_FAULT subsystem=battery_adc status=fault value=11.89V held (read failing or implausible) expected=fresh plausible read, pack 10.2-12.6V`
- `EVENT=BATTERY_ADC_FAULT subsystem=battery_adc status=fault value=11.91V held (read failing or implausible) expected=fresh plausible read, pack 10.2-12.6V`
- `EVENT=BATTERY_ADC_FAULT subsystem=battery_adc status=fault value=11.85V held (read failing or implausible) expected=fresh plausible read, pack 10.2-12.6V`

*Machine-proposed by Willie from his own logs and approved by the owner by email. Approval is not a specification: anything non-trivial goes through design before implementation.*

## Root cause (2026-10-08, after approval)

Hardware, already found and fixed. All 12 events fall inside the divider fault of 2026-10-06/08:
the lower-leg 10 kΩ of the 4.7k∥10k divider was open, putting the A0 midpoint at 4.07 V on a
3.3 V ADS1115 — readings went implausible (7.2 V, 15.4 V, 1.77 V) and the overdriven chip then
dropped off I²C. The 10 kΩ was soldered (midpoint 2.89 V at 12 V) and the ADS1115 replaced.
Others were Pi-only power (the divider is fed from the +12 V bus, so it reads ~0 V) and the Hailo
freeze that faults every sensor at once (FR-1400-006). Still to do: confirm A0 matches the
midpoint with 12 V on. "Report clearly when stale" already exists: the BATTERY_ADC_FAULT event and
the `⚠BATTERY SENSE SUSPECT` prefix on the face; while the bus is live the battery reading comes
from the bus monitor, not this ADC.
