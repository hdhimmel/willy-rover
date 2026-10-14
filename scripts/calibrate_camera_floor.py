#!/usr/bin/env python3
"""Fit the front camera's height, tilt and field of view for the vision-guided reach (arm_ik.py).

    sudo systemctl stop willy-rover
    cd ~/rover && venv/bin/python scripts/calibrate_camera_floor.py --object "sports ball"
    sudo systemctl start willy-rover

RUN ON THE ROVER with a tape measure. Put the ball on the floor at 4-6 spots spread over the view
(near and far, left and right). For each spot type two numbers:
    forward  -- cm from the FRONT OF THE FRONT WHEELS to where the ball touches the floor
    left     -- cm left of Willie's centreline (negative = right)
The script records where the ball appears, then fits CAM_FRONT_HEIGHT_MM, CAM_FRONT_TILT_DEG and
CAM_FRONT_HFOV_DEG and prints the config lines. It does NOT edit config.py.

You also need CAM_FRONT_X_MM: how far the lens is AHEAD of the arm base axis (tape, mm). The
script asks for it first because the fit depends on it.
"""
import argparse,os,statistics,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config,arm_ik


def _sample(detector,cls,n):
    boxes=[]
    for _ in range(n*3):
        dets=[d for d in detector.detect(classes=[cls])]
        if dets:
            d=max(dets,key=lambda x:x['conf']); boxes.append(d)
            if len(boxes)>=n: break
        time.sleep(0.1)
    if not boxes: return None
    med=[statistics.median(b['bbox'][i] for b in boxes) for i in range(4)]
    return {'bbox':tuple(med),'frame_w':boxes[0]['frame_w'],'frame_h':boxes[0]['frame_h']}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--object',default='sports ball')
    ap.add_argument('--frames',type=int,default=5)
    args=ap.parse_args()
    cam_x=float(input('Lens ahead of the arm base axis, mm (CAM_FRONT_X_MM): '))
    cam_y=float(input('Lens left of the centreline, mm (0 if centred): ') or 0)
    from vision import ObjectDetector
    det=ObjectDetector()
    if not getattr(det,'available',False):
        print('Detector unavailable -- is the service still running and holding the camera?'); return 1
    wheels=config.ARM_FRONT_REACH_CLEAR_MM
    samples=[]
    while True:
        raw=input('\nBall placed. forward cm from the wheels, left cm (blank to finish): ').strip()
        if not raw: break
        try: fwd,left=(float(v) for v in raw.replace(',',' ').split())
        except ValueError: print('  two numbers, e.g. "20 -10"'); continue
        s=_sample(det,args.object,args.frames)
        if s is None: print(f'  no {args.object} seen -- move it into view'); continue
        s.update(x=wheels+fwd*10,y=left*10); samples.append(s)
        print(f"  recorded: box {tuple(round(v) for v in s['bbox'])} at x {s['x']:.0f} y {s['y']:.0f} mm")
    if len(samples)<4:
        print('Need at least 4 spots; nothing fitted.'); return 1
    hgt,tilt,hfov,rms=arm_ik.fit_camera(samples,cam_x,cam_y)
    print(f'\nFit over {len(samples)} spots, rms error {rms:.0f} mm on the floor.')
    print('Put these in config.py:\n')
    print(f'CAM_FRONT_HEIGHT_MM={hgt:.0f}\nCAM_FRONT_TILT_DEG={tilt:.1f}\nCAM_FRONT_HFOV_DEG={hfov:.1f}')
    print(f'CAM_FRONT_X_MM={cam_x:.0f}\nCAM_FRONT_Y_MM={cam_y:.0f}')
    if rms>25: print('\nrms is high: check the tape numbers, or add more spots.')
    return 0


if __name__=='__main__':
    sys.exit(main())
