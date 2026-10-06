import config,logsetup
log=logsetup.setup('avoidance')

# FR-1000-002 (obstacle avoidance): WHICH WAY TO TURN, from every sensor that can see sideways.
#
# Owner, 2026-10-06: "avoidance needs to use tof and cameras". Before this, the only input to the
# turn choice was the two side sonars (r>l -> right), in both brain._avoid() and
# Navigator._avoiding(); the ToF and the front camera fed nothing but the stop.
#
# WHAT THIS DOES NOT DO: decide whether to stop. That stays with sonar + ToF through
# sensors.distances()['front'] (Master Hardware Design §12 rule 15: vision informs navigation, it
# does not gate the stop). Everything here only picks a side once something else has already
# stopped him, so a wrong camera estimate can at worst pick the worse of two turns.
#
# Fusion is min() per side, the same fail-safe rule sensors.distances() uses for 'front': any
# source that sees something closer on a side makes that side look worse, and a source with
# nothing to say (None) never makes a side look better.

def _tof_sides(tof):
    if tof is None or not getattr(tof,'available',False): return None,None
    try: return tof.side_obstacles_cm()
    except Exception:
        log.warning('ToF side read failed; turning on sonar alone',exc_info=True)
        return None,None

def _camera_sides(detector):
    """Nearest camera detection left and right of centre, in cm (heuristic range -- see
    vision.localize()). Detections within AVOID_CAMERA_CENTRE_DEG of dead ahead count for neither
    side: they are what is in front, which the stop already handles."""
    if detector is None or not config.AVOID_USE_CAMERA or not getattr(detector,'available',False):
        return None,None
    try: dets=detector.detect()
    except Exception:
        log.warning('Camera detect failed; turning without it',exc_info=True); return None,None
    left=right=None
    for det in dets:
        try: dist,bearing=detector.localize(det)
        except Exception: continue
        if bearing<=-config.AVOID_CAMERA_CENTRE_DEG: left=dist if left is None else min(left,dist)
        elif bearing>=config.AVOID_CAMERA_CENTRE_DEG: right=dist if right is None else min(right,dist)
    return left,right

def side_clearance(d,tof=None,detector=None):
    """(left_cm,right_cm): the closest thing each side, over sonar, ToF columns and camera."""
    l,r=d['left'],d['right']
    for sl,sr in (_tof_sides(tof),_camera_sides(detector)):
        if sl is not None: l=min(l,sl)
        if sr is not None: r=min(r,sr)
    return l,r

def choose_turn(d,tof=None,detector=None):
    """'turn_left', 'turn_right', or None when neither side is better (caller backs up)."""
    l,r=side_clearance(d,tof,detector)
    if r>l: return 'turn_right'
    if l>r: return 'turn_left'
    return None
