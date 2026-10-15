"""Start-up sensor check (2026-10-14, owner: "at startup Willie should run a check of all sensors and
report any failures").

The boot self-test (brain._self_test) only proves each device ANSWERS on its link -- on 2026-10-14
it passed all morning while both ToF sensors delivered no frames (reversed TX/RX) and the rear sonar
was dead. This runs once, STARTUP_SENSOR_CHECK_S after start (the sensors need a few seconds for
first data), checks that every sensor is actually DELIVERING readings, then logs and says what is
not. Report only: it never blocks motion (the boot self-test and the per-tick fault handling do).
"""
import time,config,logsetup
from logsetup import log_event
log=logsetup.setup('startup_check')


def failures(b):
    """[(sensor, what's wrong)] for brain-like object b. Never raises."""
    out=[]
    def chk(name,fn):
        try:
            why=fn()
            if why: out.append((name,why))
        except Exception as e:
            out.append((name,f'check failed ({e})'))
    s=getattr(b,'sonars',None)
    for key,label,enabled in (('tof','front ToF',config.ENABLE_TOF),('tof_rear','rear ToF',config.ENABLE_TOF_REAR)):
        if not enabled: continue
        def tof_ok(key=key):
            t=getattr(s,key,None)
            if t is None: return 'did not start'
            if not getattr(t,'available',False): return 'no frames (check its TX/RX wiring)'
            if getattr(t,'profile',None) is None: return 'no floor profile'
        chk(label,tof_ok)
    chk('sonar link',lambda: None if getattr(s,'is_healthy',False) else 'Pico B not reporting')
    def sonars_ok():
        bad=getattr(s,'failed_channels',{}) or {}
        return ', '.join(f'{n}: {w}' for n,w in bad.items()) or None
    chk('sonar',sonars_ok)
    chk('IMU',lambda: None if b.imu.is_healthy else 'not reporting')
    chk('encoders',lambda: None if b.encoders.is_healthy else 'not reporting')
    chk('battery reading',lambda: None if b.adc.battery_volts>0 else 'not reporting')
    chk('current monitors',lambda: None if b.current.is_healthy else 'not reporting')
    def front_cam():
        d=getattr(b,'detector',None)
        if d is None or not getattr(d,'available',False): return 'not available'
        if getattr(d,'_hailo_backend',False) and d.capture_frame() is None: return 'no picture'
    chk('front camera',front_cam)
    def rear_cam():
        # 2026-10-15: the rear camera opens in the background and closes itself when idle, so one
        # grab can land on a closed camera -- a false "no picture". Keep asking for a few seconds.
        r=getattr(b,'rear_cam',None)
        if r is None: return 'not set up'
        end=time.monotonic()+config.STARTUP_CAM_WAIT_S
        while True:
            if r.grab() is not None: return None
            if time.monotonic()>=end: return 'no picture'
            time.sleep(0.25)
    chk('rear camera',rear_cam)
    def gripper():
        import grip
        fb=grip.read_feedback(b.adc,b.current)
        if fb is None: return 'position feedback not reading'
        lo,hi=config.STARTUP_GRIP_FB_RANGE
        if not lo<=fb<=hi: return f'position feedback reads {fb:.3f}, outside {lo}-{hi}'
    chk('gripper',gripper)
    return out


class StartupCheck:
    """Tick-driven: primes the on-demand rear camera first, checks once, reports once."""
    def __init__(self,brain,clock=time.monotonic,background=True):
        self.b=brain; self.clock=clock; self.t0=clock(); self.primed=False; self.done=False
        self.result=None; self.background=background

    def tick(self):
        if self.done or config.SIMULATE_HARDWARE or not config.STARTUP_SENSOR_CHECK: return
        el=self.clock()-self.t0
        if not self.primed and el>=config.STARTUP_SENSOR_CHECK_S/2:
            self.primed=True
            try: self.b.rear_cam.grab()          # opens in the background; checked below
            except Exception: pass
        if el<config.STARTUP_SENSOR_CHECK_S: return
        self.done=True
        # 2026-10-15: on the tick it cost 914 ms (camera grabs, I2C reads) -- run it on its own
        # thread; the report only logs, speaks and sets the screen.
        if self.background:
            import threading
            threading.Thread(target=self._run,daemon=True,name='startup-check').start()
        else:
            self._run()

    def _run(self):
        try:
            self.result=failures(self.b)
            report(self.b,self.result)
        except Exception:
            log.warning('Start-up sensor check failed to run',exc_info=True)


def report(b,fails):
    if not fails:
        log.info('Start-up sensor check: every sensor is reporting'); return
    text='; '.join(f'{n}: {w}' for n,w in fails)
    log_event(log,'STARTUP_SENSOR_CHECK',severity='warning',subsystem='sensors',status='failed',failed=text)
    log.warning(f'Start-up sensor check FAILED: {text}')
    names=[n for n,_ in fails]
    said=(names[0] if len(names)==1 else ', '.join(names[:-1])+' and '+names[-1])
    try: b._say(f"Start-up check: my {said} {'is' if len(names)==1 else 'are'} not working.")
    except Exception: pass
    try: b.display.update_state('warn',f'SENSOR CHECK: {", ".join(names)}')
    except Exception: pass
