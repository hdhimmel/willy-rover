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
