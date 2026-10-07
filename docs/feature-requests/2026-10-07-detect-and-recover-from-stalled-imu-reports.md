---
proposed:  2026-10-07T12:42Z
approved:  2026-10-07T13:49Z
channel:   email, DKIM verified, code 4d09
evidence:  7 x IMU_FAULT on imu, 2026-10-07 to 2026-10-07
status:    approved
---

# Detect and recover from stalled IMU reports

## Problem

On 2026-10-07, my logs recorded 7 IMU_FAULT events on the imu subsystem. In the examples, tilt readings stayed fixed at about 8.9 to 9.5 degrees, and no fresh IMU report arrived with a changing quaternion or acceleration within the expected 3.0 seconds.

## Suggested direction

Please add a watchdog that treats a stale IMU stream as invalid data, instead of continuing to trust the last held tilt value. When it trips, I could slow or pause movement, try to restart or re-initialize the IMU, and tell you if it keeps failing. It would also help to log how long each report stalled, so you can tell whether the cause is a loose connection, a driver problem, or a failing sensor.

## Evidence

- `EVENT=IMU_FAULT subsystem=imu status=fault value=tilt 9.5deg held, no fresh IMU report expected=quaternion or acceleration changing within 3.0s`
- `EVENT=IMU_FAULT subsystem=imu status=fault value=tilt 9.4deg held, no fresh IMU report expected=quaternion or acceleration changing within 3.0s`
- `EVENT=IMU_FAULT subsystem=imu status=fault value=tilt 8.9deg held, no fresh IMU report expected=quaternion or acceleration changing within 3.0s`

*Machine-proposed by Willie from his own logs and approved by the owner by email. Approval is not a specification: anything non-trivial goes through design before implementation.*

## Root cause (found 2026-10-07, after approval)

Not a stalled IMU. At 10:08:35 "Explore." went to the Hailo model, which took 5.4 s; the moment it
returned, the IMU, encoders, current monitors, battery ADC and sonars all faulted and all recovered
within 0.1 s. Five devices on two UARTs and an I2C bus cannot fail together: Hailo's
`generate_all()` holds Python's GIL and freezes every thread, so every freshness check expired at
once. The IMU watchdog and RST recovery this request asks for already exist and worked; what it saw
was the freeze. Interim fix: brake synchronously before every generation (`hailo_llm.set_before_
generate`, brain `_brake_before_hailo`). Real fix: the model in its own process -- needs design,
because the Hailo VDevice is shared with vision.
