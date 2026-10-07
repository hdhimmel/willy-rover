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
    ap.add_argument('--no-camera',action='store_true')
    ap.add_argument('--no-rear',action='store_true',help='front camera only')
    ap.add_argument('--camera-log-only',action='store_true',
                    help='record the camera estimate without letting it stop the turn')
    a=ap.parse_args()
    if a.camera_log_only: config.ROTATE_CAMERA_STOP=False
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
        if grab is None: print('Front camera unavailable')
    rear=None
    if not a.no_camera and not a.no_rear:
        import cv2
        cap=cv2.VideoCapture(config.CAMERA_DEVICE,cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,360)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,1)            # newest frame, not a queued one
        if cap.isOpened():
            def rear():
                ok,f=cap.read(); return f if ok else None
        else: print(f'Rear camera {config.CAMERA_DEVICE} would not open')
    steer=Steering(); drive=DriveBase()
    from sensors import Encoders
    enc=Encoders(); enc.start()            # bump-stop wording only; NOT attached to the drive
    time.sleep(2.0)
    print('corner pulses:',{k:round(v) for k,v in rotation_pulses().items()})
    r=Rotation(steer,drive,imu,lambda: son.distances,camera_grab=grab,rear_grab=rear,encoders=enc,
               say=lambda t:print('SAY:',t))
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
    print(f'result: {r.state} {r.fail_reason}  turned {turned:+.1f} deg of {a.degrees:+.0f} '
          f'in {time.time()-t0:.1f}s')
    time.sleep(1.0); print(f'heading after settling: {r._turned():+.1f} deg (coast included)')
    for c in getattr(r,'_cams',[]):
        if not c.samples: print(f'{c.name} camera: no frames'); continue
        used=[x for x in c.samples if x[4]]; dts=[x[1] for x in c.samples]
        print(f'{c.name} camera: {len(c.samples)} frames, mean dt {sum(dts)/len(dts)*1000:.0f} ms, '
              f'{len(used)} clear; camera {c.deg:.1f} deg vs IMU {c.imu_deg:.1f} deg over those frames '
              f'({"agrees" if c.agrees else "DISAGREES"}{"" if c.judged else ", not enough to judge"})')
        print('   t(s)  dt(ms)  dx(px)  quality used')
        t0s=c.samples[0][0]
        for t,dt,dx,resp,u in c.samples:
            print(f'  {t-t0s:5.2f} {dt*1000:6.0f} {dx:+7.2f}  {resp:.3f}  {"*" if u else ""}')
    return 0 if r.state=='DONE' else 1


if __name__=='__main__':
    sys.exit(main())
