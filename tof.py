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

    def __init__(self,source=None,profile_path=None):
        self.source=source
        self._available=False
        self._last_error=None
        self.profile_path=profile_path or os.path.join(
            config.WILLY_MEMORY_ROOT,config.TOF_FLOOR_PROFILE_PATH)
        self.profile=FloorProfile.load(self.profile_path)

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
            if self.profile.classify(i,v)!=OBSTACLE: continue
            if best is None or v<best: best=v
        return None if best is None else best/10.0

    def drop_detected(self):
        """True when any zone reports open space where the profile expects floor.

        Dark or absorbing carpet also returns nothing, so this will sometimes fire on a rug.
        That is the safe direction -- he stops for nothing rather than driving off an edge --
        and it is why the margin is tuned against the floors he actually roams."""
        if self.profile is None: return False
        frame=self._frame()
        if frame is None: return False
        return any(self.profile.classify(i,v)==DROP for i,v in enumerate(frame))

    def capture_profile(self,samples=None):
        """Average several frames of clear floor into a new profile. Does NOT save -- the caller
        decides, so a bad capture is not written over a good one by accident."""
        samples=samples or config.TOF_PROFILE_SAMPLES
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
        zones=[(sums[i]/counts[i]) if counts[i] else None for i in range(config.TOF_ZONES)]
        missing=sum(1 for z in zones if z is None)
        if missing:
            log.warning(f'Floor profile: {missing} zone(s) never returned a reading; they will '
                        f'report NO_DATA rather than a guessed baseline')
        log.info(f'Floor profile captured from {samples} frame(s)')
        return FloorProfile(zones)


def read_frame(port=None,baud=None,timeout=0.2):
    """The real transport: one 8x8 frame from the SEN0628 over UART.

    Deliberately the only untestable part of this module, and deliberately thin. `pyserial` is
    imported here rather than at module scope so the rest of this file imports and tests on a
    machine without it -- which is how everything above was developed while the rover was
    powered down."""
    import serial
    port=port or config.TOF_PORT; baud=baud or config.TOF_BAUD
    with serial.Serial(port,baud,timeout=timeout) as ser:
        raise NotImplementedError(
            'SEN0628 frame parsing is not written. The PROTOCOL is now known -- read verbatim '
            'from DFRobot_MatrixLidar.cpp on 2026-09-15 and implemented in scripts/tof_probe.py: '
            'request [0x55][argsNumH][argsNumL][cmd][args] with argsNum = len(args)+1; reply '
            '[status][cmd][lenL][lenH][payload] where 0x53 is SUCCESS, 0x63 FAILED and 0xFF is '
            'skippable filler; getAllData is 55 00 01 02; payload is little-endian uint16 mm, '
            '64 zones = 128 bytes, 4000 = invalid. It is POLLED, never streaming -- passive '
            'listening returns nothing, and that is correct. '
            'What is missing is a working sensor: unit #1 returned a handful of valid readings '
            'on 2026-09-15 and nothing since, and a replacement was ordered. Implement this '
            'against a real stable stream (scripts/tof_probe.py -n 200) rather than against the '
            'protocol alone -- Master Hardware Design 6.5 requires a stable multi-minute stream '
            'before this goes anywhere near the reflex path. Everything above this function is '
            'complete and tested, and takes any callable returning 64 millimetre values.')
