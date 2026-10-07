#!/usr/bin/env python3
"""Rotation-mode bench test (rotate.py): steer the corners onto the turning circle, spin on IMU.

MOVES THE ROVER. Floor, room to spin, nothing within ~0.5 m. Stop the service first:

    sudo systemctl stop willy-rover
    venv/bin/python3 scripts/rotate_test.py 90        # 90 deg LEFT (CCW); -90 = right
    venv/bin/python3 scripts/rotate_test.py 90 --no-camera
    sudo systemctl start willy-rover

Drive is feed-forward only (no encoder speed loop): the speed loop has never been proven on the
rover and must not ride along untested. Sonar + ToF stop it inside ROTATE_CLEAR_CM; the front
camera cross-checks the IMU unless --no-camera. Ctrl-C stops the motors.
"""
import os,sys,time,argparse
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from motors import DriveBase,Steering
from sensors import SonarArray,IMU
from rotate import Rotation,rotation_pulses


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('degrees',type=float)
    ap.add_argument('--no-camera',action='store_true'); a=ap.parse_args()
    son=SonarArray(); son.start()
    if config.ENABLE_TOF:
        try:
            from tof import ToFSensor,SerialFrameSource,BackgroundFrames
            son.tof=ToFSensor(source=BackgroundFrames(SerialFrameSource()))
        except Exception as e: print('ToF unavailable, sonar only:',e)
    imu=IMU(reset=son.reset_imu); imu.start()
    grab=None
    if not a.no_camera:
        from vision import ObjectDetector
        det=ObjectDetector(); grab=det.capture_frame if det.available else None
        if grab is None: print('Camera unavailable: IMU only')
    steer=Steering(); drive=DriveBase()
    time.sleep(2.0)
    print('corner pulses:',{k:round(v) for k,v in rotation_pulses().items()})
    r=Rotation(steer,drive,imu,None,camera_grab=grab,say=lambda t:print('SAY:',t))
    ok,msg=r.start(a.degrees); print('start:',msg)
    t0=time.time()
    try:
        while r.active:
            r.tick(son.distances,imu.tilt); time.sleep(0.05)
    except KeyboardInterrupt:
        r.abort('Ctrl-C')
    finally:
        drive.brake(); time.sleep(0.5)
    turned=r._turned()
    cam=getattr(r,'_cam',None)
    print(f'result: {r.state} {r.fail_reason}  turned {turned:+.1f} deg of {a.degrees:+.0f} '
          f'in {time.time()-t0:.1f}s; camera estimate '
          f'{"n/a" if cam is None or not cam.ok else f"{cam.deg:.0f} deg"}')
    time.sleep(1.0); print(f'heading after settling: {r._turned():+.1f} deg (coast included)')
    return 0 if r.state=='DONE' else 1


if __name__=='__main__':
    sys.exit(main())
