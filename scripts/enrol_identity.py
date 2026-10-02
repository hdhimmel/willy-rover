#!/usr/bin/env python3
"""Bootstrap enrolment for FR-2100 -- run on the rover over SSH (design §5 "Bootstrap").

The voice gate needs Howard or Carolyn to be recognised before anyone new can be introduced,
which is circular on the first run. So the first identities are enrolled HERE: physical or SSH
access to the rover is the root of trust, and these are stored ACTIVE (no email approval).

Refuses to run if anyone is already enrolled unless --force is given, so it cannot be used to
quietly bypass the email approval later.

    sudo systemctl stop willy-rover          # the service owns the camera
    venv/bin/python3 scripts/enrol_identity.py Howard
    venv/bin/python3 scripts/enrol_identity.py Carolyn --force
    sudo systemctl start willy-rover

Stand about a metre from the front camera, alone in frame, facing it. Frames are embedded and
discarded; no image is saved (FR-2100-005).
"""
import os,sys,time,argparse
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from identity import IdentityStore
from recognition import FaceRecognizer

def main():
    ap=argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('name'); ap.add_argument('--force',action='store_true')
    a=ap.parse_args()
    store=IdentityStore()
    if store.names(include_pending=True) and not a.force:
        sys.exit(f'Refusing: identities already enrolled ({", ".join(store.names())}). Use --force '
                 'to add another -- and prefer "Willie, this is <name>" with email approval.')
    from picamera2 import Picamera2
    cam=Picamera2(); cam.configure(cam.create_preview_configuration(main={'size':(1280,720),'format':'XRGB8888'}))
    cam.start(); time.sleep(1.0)
    rec=FaceRecognizer(lambda: cam.capture_array('main')[:,:,:3].copy())
    if not rec.available: sys.exit('Face models not available -- see config.FACE_*_MODEL_PATH')
    print(f'Look at the camera, {a.name}...')
    vecs,why=rec.capture_for_enrolment()
    cam.stop()
    if why: sys.exit(why)
    store.enrol(a.name.capitalize(),vecs); store.approve(a.name.capitalize())
    print(f'Enrolled {a.name.capitalize()} with {len(vecs)} vectors (active).')

if __name__=='__main__':
    main()
