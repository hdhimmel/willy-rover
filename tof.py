import json,os,time,config,logsetup
log=logsetup.setup('tof')

# FR-1000-002 / FR-1200-005. DFRobot SEN0628 -- VL53L7CX behind an RP2040, 8x8 zones, 60 degrees
# horizontal and vertical. Master Hardware Design §6.5, Software Design §6.5/§6.6.
#
# THIS MODULE TURNS 64 DISTANCES INTO MEANING. It holds no UART and no hardware: the frame
# source is injected, which is what lets every rule below be tested without a sensor. The
# transport lives in read_frame() at the bottom and is the only part that cannot be.
#
# THE CENTRAL RULE, and the one most likely to be "simplified" into a bug: the floor is ALWAYS
# in view, and it is SUBTRACTED, not masked.
#
# Masking the bottom rows is the obvious fix and the wrong one. Mounted around 20cm, the floor
# first appears roughly 34cm out (60 degrees vertical is about 1.7x mount height), which is
# inside DIST_SLOW -- so the rows a mask would throw away are exactly where a shoe or a trailing
# cable at close range shows up. Instead every zone carries its own expected floor distance,
# captured once on clear floor, and counts as an obstacle only when it comes back MEANINGFULLY
# SHORTER than that.
#
# The inverse is cliff detection, and it is not a bonus -- it is the only cliff detection this
# rover has. Dedicated IR cliff sensors were dropped on 2026-09-12 because the chassis extends
# past the body and nothing can be mounted ahead of the front wheels. A zone returning nothing,
# or much further than its profile, where floor is expected, is a drop.
#
# Two rules that exist to stop this subsystem making things worse than no sensor at all:
#   - UNCALIBRATED REPORTS NOTHING, never raw ranges. Raw would make the floor a permanent
#     obstacle and immobilise the rover on the first boot after a rebuild.
#   - UNAVAILABLE IS NOT A FAULT. A dropped UART or a resetting RP2040 means sensors.py falls
#     back to sonar alone and logs it. Adding a sensor must never lower the availability floor.

OBSTACLE='obstacle'
FLOOR='floor'
DROP='drop'
NO_DATA='no_data'


class FloorProfile:
    """The expected floor distance for each of the 64 zones, captured on clear level floor.

    Tied to the sensor's exact pose: a bracket that shifts invalidates it. That failure is
    deliberately loud rather than silent -- a moved sensor produces phantom obstacles (he stops
    for nothing) rather than blindness (he drives into something) -- but it still means
    re-running the capture after any mechanical change."""

    def __init__(self,zones):
        self.zones=[None if z is None else float(z) for z in zones]

    def __len__(self): return len(self.zones)

    def classify(self,index,value):
        """One zone's reading against its own baseline. `value` is millimetres, or None for the
        sensor's no-target case."""
        expected=self.zones[index] if index<len(self.zones) else None
        if expected is None: return NO_DATA
        if value is None: return DROP          # open space where floor should be
        margin=config.TOF_FLOOR_MARGIN_MM
        if value<expected-margin: return OBSTACLE
        if value>expected+margin: return DROP
        return FLOOR

    def save(self,path):
        tmp=path+'.tmp'
        with open(tmp,'w') as f: json.dump({'zones':self.zones},f)
        os.replace(tmp,path)                   # atomic: a half-written profile is worse than none
        log.info(f'Floor profile saved to {path} ({len(self.zones)} zones)')

    @classmethod
    def load(cls,path):
        """Returns None rather than raising on anything unusable -- a missing file, malformed
        JSON, or the wrong zone count. A profile captured against a different zone count cannot
        be mapped onto this frame, and using it anyway would compare every zone against the
        wrong baseline."""
        try:
            with open(path) as f: data=json.load(f)
            zones=data['zones']
        except (OSError,ValueError,KeyError,TypeError) as e:
            log.info(f'No usable floor profile at {path}: {e}')
            return None
        if len(zones)!=config.TOF_ZONES:
            log.warning(f'Floor profile at {path} has {len(zones)} zones, expected '
                        f'{config.TOF_ZONES} — refusing it rather than comparing against the '
                        f'wrong baseline')
            return None
        return cls(zones)


class ToFSensor:
    """Frames in, meaning out. `source` is any callable returning a list of `TOF_ZONES`
    millimetre readings (None for no target); read_frame() below is the real one."""

    def __init__(self,source=None,profile_path=None,floor_rows='config',left_columns='config',drop_rows=None):
        # Geometry is per sensor (2026-10-10): the rear unit is mounted upside down, so its floor
        # is rows 0-1, not the front's 6-7. 'config' = the front sensor's config values, read at
        # call time so tests that patch config keep working.
        self._floor_rows=floor_rows; self._left_columns=left_columns
        # Rows allowed to report a DROP. None = every profiled zone (the front, unchanged). The rear
        # floor profile includes row 2, which meets the floor at a grazing ~45 cm and drops returns
        # now and then -- 4 false "drop behind" in 9 s on clear floor, 2026-10-10.
        self.drop_rows=drop_rows
        self.source=source
        self._available=False
        self._last_error=None
        self.profile_path=profile_path or os.path.join(
            config.WILLY_MEMORY_ROOT,config.TOF_FLOOR_PROFILE_PATH)
        self.profile=FloorProfile.load(self.profile_path)

    @property
    def floor_rows(self):
        return config.TOF_FLOOR_ROWS if self._floor_rows=='config' else self._floor_rows

    @property
    def left_columns(self):
        return config.TOF_LEFT_COLUMNS if self._left_columns=='config' else self._left_columns

    @property
    def available(self):
        """False after a read that failed or returned an unusable frame. Not a fault -- see the
        header. sensors.py degrades to sonar on this."""
        return self._available

    def _frame(self):
        if self.source is None: return None
        try:
            frame=self.source()
        except Exception as e:
            if self._available or self._last_error is None:
                log.warning(f'ToF read failed ({e}) — falling back to sonar alone')
            self._available=False; self._last_error=str(e)
            return None
        if frame is None or len(frame)!=config.TOF_ZONES:
            n='none' if frame is None else len(frame)
            if self._available:
                log.warning(f'ToF frame has {n} zones, expected {config.TOF_ZONES} — '
                            f'desynchronised UART, not data. Ignoring the frame.')
            self._available=False
            return None
        if not self._available:
            log.info('ToF frames healthy')
        self._available=True; self._last_error=None
        return frame

    def classify_frame(self):
        """Per-zone classification, or [] when there is nothing trustworthy to say."""
        if self.profile is None: return []
        frame=self._frame()
        if frame is None: return []
        return [self.profile.classify(i,v) for i,v in enumerate(frame)]

    def nearest_obstacle_cm(self):
        """Distance in CENTIMETRES to the closest zone reading as an obstacle, or None.

        Centimetres because that is what `DIST_STOP`/`DIST_SLOW`/`DIST_CLEAR` and the whole of
        sensors.py already speak; the sensor reports millimetres. Converting here keeps the unit
        boundary in one place instead of at every call site.

        None means *no obstacle to report* -- whether because the floor is clear, the sensor is
        uncalibrated, or it is unavailable. Every one of those is a case where sonar alone
        should decide, so they deliberately collapse to the same answer."""
        if self.profile is None: return None
        frame=self._frame()
        if frame is None: return None
        best=None
        for i,v in enumerate(frame):
            if not self._is_obstacle(i,v): continue
            if best is None or v<best: best=v
        return None if best is None else best/10.0

    def _is_obstacle(self,i,v):
        """A floor row: shorter than its floor baseline (the profile). Any OTHER row: anything
        nearer than TOF_NOFLOOR_OBSTACLE_MM. 2026-10-07: only floor rows carry a profile, which
        left the upper rows -- the ones that see a couch edge or table top at body height --
        saying nothing at all. Those rows never see floor this close (row 5, the nearest of them,
        first meets floor at ~86 cm), so a near return there is something in the way, with no
        baseline needed."""
        if self.profile.classify(i,v)==OBSTACLE: return True
        rows=self.floor_rows
        if rows is None or v is None: return False
        return (i//config.TOF_ZONE_COLUMNS) not in rows and v<config.TOF_NOFLOOR_OBSTACLE_MM

    def side_obstacles_cm(self):
        """(left_cm,right_cm): nearest obstacle zone in the left and right column halves, or
        None for a side with nothing to report. FR-1000-002 turn choice (avoidance.py).

        (None,None) until config.TOF_LEFT_COLUMNS is set. Which zone columns face left depends
        on how the sensor is mounted (the VL53L7CX's zone order is mirrored relative to its
        field of view) and has not been checked on the rover. Guessing would make a turn steer
        INTO what the ToF sees, so an unknown orientation reports nothing. Check: hand on one
        side, scripts/tof_probe.py, see which columns drop."""
        if self.profile is None or self.left_columns is None: return None,None
        frame=self._frame()
        if frame is None: return None,None
        left=right=None; cols=config.TOF_ZONE_COLUMNS; left_cols=set(self.left_columns)
        for i,v in enumerate(frame):
            if not self._is_obstacle(i,v): continue
            cm=v/10.0
            if i%cols in left_cols: left=cm if left is None else min(left,cm)
            else: right=cm if right is None else min(right,cm)
        return left,right

    def drop_detected(self):
        """True when any zone reports open space where the profile expects floor.

        Dark or absorbing carpet also returns nothing, so this will sometimes fire on a rug.
        That is the safe direction -- he stops for nothing rather than driving off an edge --
        and it is why the margin is tuned against the floors he actually roams."""
        if self.profile is None: return False
        frame=self._frame()
        if frame is None: return False
        rows=self.drop_rows; cols=config.TOF_ZONE_COLUMNS
        return any(self.profile.classify(i,v)==DROP for i,v in enumerate(frame)
                   if rows is None or i//cols in rows)

    def capture_profile(self,samples=None,floor_rows=None):
        """Average several frames of clear floor into a new profile. Does NOT save -- the caller
        decides, so a bad capture is not written over a good one by accident.

        Only `floor_rows` (default config.TOF_FLOOR_ROWS) are kept; every other zone is stored as
        None -> NO_DATA. 2026-10-07: the rows above the floor band see the ROOM (desk, boxes, a
        person, 1.3-1.8 m away), not floor. Baked in as "floor", the same zones elsewhere would
        see open space where the profile expects a return -- DROP -- and he would stop for
        nothing. This is not the bottom-row mask the header warns against: it keeps exactly the
        rows that see floor and drops the ones that never do."""
        samples=samples or config.TOF_PROFILE_SAMPLES
        if floor_rows is None: floor_rows=self.floor_rows
        sums=[0.0]*config.TOF_ZONES; counts=[0]*config.TOF_ZONES
        for _ in range(samples):
            frame=self._frame()
            if frame is None: continue
            for i,v in enumerate(frame):
                if v is None: continue
                sums[i]+=float(v); counts[i]+=1
        if not any(counts):
            log.warning('Floor profile capture got no usable frames'); return None
        # A zone that never returned anything over the whole capture has no floor to expect --
        # stored as None, and classify() reports NO_DATA for it rather than guessing a baseline.
        keep=lambda i: floor_rows is None or i//config.TOF_ZONE_COLUMNS in floor_rows
        zones=[(sums[i]/counts[i]) if counts[i] and keep(i) else None for i in range(config.TOF_ZONES)]
        missing=sum(1 for z in zones if z is None)
        if missing:
            log.warning(f'Floor profile: {missing} zone(s) never returned a reading; they will '
                        f'report NO_DATA rather than a guessed baseline')
        log.info(f'Floor profile captured from {samples} frame(s)')
        return FloorProfile(zones)


_STATUS_SUCCESS=0x53; _STATUS_FAILED=0x63; _FILLER=0xFF
_CMD_SETMODE=1; _CMD_ALLDATA=2; _MATRIX_8X8=8; _INVALID_MM=4000

def _req(cmd,args=b''):
    n=len(args)+1                                   # argsNum counts the cmd byte: len+1
    return bytes([0x55,(n>>8)&0xFF,n&0xFF,cmd])+args

def _recv(ser,timeout):
    """[status][cmd][lenL][lenH][payload], 0xFF filler skipped (DFRobot_MatrixLidar.cpp)."""
    t0=time.time()
    while time.time()-t0<timeout:
        b=ser.read(1)
        if not b or b[0]==_FILLER: continue
        if b[0] not in (_STATUS_SUCCESS,_STATUS_FAILED): continue
        hdr=b''
        while len(hdr)<3 and time.time()-t0<timeout: hdr+=ser.read(3-len(hdr))
        if len(hdr)<3: return None
        n=hdr[1]|(hdr[2]<<8); pay=b''
        while len(pay)<n and time.time()-t0<timeout:
            c=ser.read(n-len(pay))
            if not c: break
            pay+=c
        return b[0],hdr[0],pay
    return None

def decode_frame(pay):
    """128 payload bytes -> 64 millimetre values, None for the firmware's 4000 'no return'."""
    if len(pay)<2*config.TOF_ZONES: return None
    v=[pay[i]|(pay[i+1]<<8) for i in range(0,2*config.TOF_ZONES,2)]
    return [None if x>=_INVALID_MM else x for x in v]

class SerialFrameSource:
    """The real transport, ported from scripts/tof_probe.py (2026-10-02). Keeps the port open,
    sets 8x8 once, then polls getAllData. Polled, never streaming -- see that script."""
    def __init__(self,port=None,baud=None):
        self.port=port or config.TOF_PORT; self.baud=baud or config.TOF_BAUD; self._ser=None
    def _open(self):
        import serial
        self._ser=serial.Serial(self.port,self.baud,timeout=0.2)
        self._ser.reset_input_buffer(); self._ser.write(_req(_CMD_SETMODE,bytes([0,0,0,_MATRIX_8X8])))
        self._ser.flush(); _recv(self._ser,8.0)
        time.sleep(5.5)                              # the vendor library's delay(5000)
    def __call__(self):
        try:
            if self._ser is None: self._open()
            self._ser.reset_input_buffer(); self._ser.write(_req(_CMD_ALLDATA)); self._ser.flush()
            r=_recv(self._ser,1.0)
        except Exception:
            try: self._ser and self._ser.close()
            except Exception: pass
            self._ser=None; raise
        if r is None or r[0]!=_STATUS_SUCCESS or r[1]!=_CMD_ALLDATA: return None
        return decode_frame(r[2])

class BackgroundFrames:
    """2026-10-02: a frame takes ~0.13 s over UART, far too long for the 20 Hz tick, which
    used to call the source directly (twice per tick). This thread polls; the tick reads the
    newest frame, and only if it is younger than TOF_FRAME_MAX_AGE_S -- a stale frame is no
    frame, so ToFSensor reports unavailable and sensors.py falls back to sonar."""
    def __init__(self,source):
        import threading
        self._source=source; self._latest=None; self._t=0.0; self._err=None
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True,name='tof'); self._thread.start()
    def _loop(self):
        while self._running:
            try:
                f=self._source(); self._err=None
                if f is not None: self._latest=f; self._t=time.monotonic()
            except Exception as e:
                if self._err is None: log.warning(f'ToF read failed: {e} -- retrying')
                self._err=str(e); time.sleep(2.0)
            time.sleep(config.TOF_POLL_S)
    def stop(self): self._running=False
    def __call__(self):
        if self._latest is None or time.monotonic()-self._t>config.TOF_FRAME_MAX_AGE_S:
            raise RuntimeError(self._err or 'no fresh ToF frame')
        return self._latest

def read_frame(port=None,baud=None,timeout=0.2):
    """One frame, opening and setting the sensor up each call (5 s). For scripts only; the
    service uses SerialFrameSource inside BackgroundFrames."""
    return SerialFrameSource(port,baud)()
