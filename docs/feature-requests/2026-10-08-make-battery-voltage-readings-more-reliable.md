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
