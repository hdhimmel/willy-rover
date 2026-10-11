import json,math,os,threading,time,config,logsetup
log=logsetup.setup('gps')

# FR-2300 GPS (built 2026-10-11): Adafruit Mini GPS PA1010D on I2C 0x10 (STEMMA QT). The chip
# streams NMEA; I2C reads return it 32 bytes at a time, padded with 0x0A when it has nothing.
#
# FR-2300-005, the rule that shapes all of this: GPS NEVER blocks motion or startup and NEVER
# feeds the stop or the Directive checks. It is optional in the self-test, and "no fix" (every
# indoor minute, and the whole basement) is the normal state, not a fault.


# ---------------------------------------------------------------- NMEA

def nmea_ok(line):
    """True if `line` is a $...*XX sentence with a correct XOR checksum."""
    if not line.startswith('$') or '*' not in line: return False
    body,_,cs=line[1:].partition('*')
    x=0
    for ch in body: x^=ord(ch)
    try: return x==int(cs[:2],16)
    except ValueError: return False

def _deg(v,hemi):
    """ddmm.mmmm / dddmm.mmmm + N/S/E/W -> signed decimal degrees, or None."""
    if not v or not hemi: return None
    try:
        dot=v.index('.'); d=float(v[:dot-2]); m=float(v[dot-2:])
    except (ValueError,IndexError): return None
    deg=d+m/60.0
    return -deg if hemi in 'SW' else deg

def parse(line):
    """One sentence -> dict of what it says, or None. RMC: valid/lat/lon/utc; GGA: quality, sats,
    hdop. Talker-agnostic (GP/GL/GN)."""
    if not nmea_ok(line): return None
    f=line[1:].split('*')[0].split(',')
    kind=f[0][2:]
    try:
        if kind=='RMC' and len(f)>=10:
            out={'kind':'RMC','valid':f[2]=='A','lat':_deg(f[3],f[4]),'lon':_deg(f[5],f[6])}
            if f[1] and f[9] and len(f[9])==6 and len(f[1])>=6:
                out['utc']=time.mktime((2000+int(f[9][4:6]),int(f[9][2:4]),int(f[9][0:2]),
                                        int(f[1][0:2]),int(f[1][2:4]),int(float(f[1][4:])),0,0,0))-time.timezone
            return out
        if kind=='GGA' and len(f)>=9:
            return {'kind':'GGA','quality':int(f[6] or 0),'sats':int(f[7] or 0),
                    'hdop':float(f[8]) if f[8] else None,'lat':_deg(f[2],f[3]),'lon':_deg(f[4],f[5])}
    except (ValueError,IndexError,OverflowError):
        return None
    return None


# ---------------------------------------------------------------- geometry

_R=6371000.0

def distance_bearing(lat1,lon1,lat2,lon2):
    """Metres and initial bearing (deg, 0 = north) from point 1 to point 2."""
    p1,p2=math.radians(lat1),math.radians(lat2); dl=math.radians(lon2-lon1)
    a=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    d=2*_R*math.asin(min(1.0,math.sqrt(a)))
    y=math.sin(dl)*math.cos(p2); x=math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl)
    return d,(math.degrees(math.atan2(y,x))+360)%360

_COMPASS=('north','north-east','east','south-east','south','south-west','west','north-west')

def compass(bearing): return _COMPASS[int((bearing+22.5)//45)%8]

def map_link(lat,lon): return f'https://maps.google.com/?q={lat:.6f},{lon:.6f}'

def relative_phrase(fix,home):
    """"about 30 metres north of home" (spoken, FR-2300-001)."""
    d,b=distance_bearing(home['lat'],home['lon'],fix['lat'],fix['lon'])
    if d<config.GPS_AT_HOME_M: return "at home"
    dist=f'{d:.0f} metres' if d<1000 else f'{d/1000:.1f} kilometres'
    return f'about {dist} {compass(b)} of home'


# ---------------------------------------------------------------- the reader

class GPS:
    """Background I2C reader. `fix()` is the only position accessor and returns None unless the
    fix is valid AND fresh -- a stale position must never be presented as current (FR-2300-001)."""
    def __init__(self,bus=None,start=True,clock=time.time):
        self._bus=bus; self._clock=clock; self._lock=threading.Lock()
        self._buf=''; self._last={}; self._fix_t=0.0; self._seen_t=0.0; self._running=False
        self.home=self._load_home()
        if start: self.start()

    # ---- home (FR-2300-002)
    @staticmethod
    def _home_path(): return os.path.join(config.WILLY_MEMORY_ROOT,config.GPS_HOME_PATH)
    def _load_home(self):
        try:
            with open(self._home_path()) as f: h=json.load(f)
            return h if 'lat' in h and 'lon' in h else None
        except (OSError,ValueError): return None
    def save_home(self,home):
        with open(self._home_path(),'w') as f: json.dump(home,f)
        self.home=home

    # ---- reading
    def start(self):
        if self._running: return
        self._running=True
        threading.Thread(target=self._loop,daemon=True,name='gps').start()
    def stop(self): self._running=False
    def _loop(self):
        bus=self._bus
        if bus is None:
            try:
                import smbus2; bus=smbus2.SMBus(1)
            except Exception as e:
                log.info(f'GPS: no I2C bus ({e})'); return
        while self._running:
            try:
                chunk=bytes(bus.read_i2c_block_data(config.GPS_ADDR,0,32))
                self.feed(chunk)
            except OSError:
                time.sleep(1.0)        # absent or unplugged: optional, try again quietly
            time.sleep(config.GPS_POLL_S)
    def feed(self,chunk):
        """Raw bytes from the chip (also the test entry point)."""
        txt=chunk.replace(b'\xff',b'').decode('ascii','replace')
        with self._lock:
            self._buf=(self._buf+txt)[-2048:]
            if '\n' not in self._buf: return
            *lines,self._buf=self._buf.split('\n')
        for ln in lines:
            ln=ln.strip()
            if not ln: continue
            s=parse(ln)
            if s is None: continue
            now=self._clock()
            with self._lock:
                self._seen_t=now
                self._last.update({k:v for k,v in s.items() if k!='kind' and v is not None})
                if s['kind']=='RMC':
                    self._last['valid']=s['valid']
                    if s['valid'] and s.get('lat') is not None: self._fix_t=now

    @property
    def present(self):
        """The chip has said something recently (it talks at 1 Hz even with no fix)."""
        return self._clock()-self._seen_t<config.GPS_STALE_S
    def fix(self):
        with self._lock:
            if not self._last.get('valid') or self._clock()-self._fix_t>config.GPS_STALE_S: return None
            if self._last.get('lat') is None or self._last.get('lon') is None: return None
            return {'lat':self._last['lat'],'lon':self._last['lon'],'sats':self._last.get('sats'),
                    'hdop':self._last.get('hdop'),'age_s':self._clock()-self._fix_t,'utc':self._last.get('utc')}
    def sats(self):
        with self._lock: return self._last.get('sats',0)

    # ---- learn home (FR-2300-002): average about a minute of fixes
    def learn_home(self,on_done,duration_s=None,sleep=time.sleep):
        """Background. on_done(ok, message)."""
        duration_s=config.GPS_LEARN_S if duration_s is None else duration_s
        def run():
            pts=[]; end=self._clock()+duration_s
            while self._clock()<end:
                f=self.fix()
                if f: pts.append((f['lat'],f['lon']))
                sleep(1.0)
            if len(pts)<config.GPS_LEARN_MIN_FIXES:
                on_done(False,f"I couldn't learn home: I only got {len(pts)} position fixes. I need to see the sky.")
                return
            lat=sum(p[0] for p in pts)/len(pts); lon=sum(p[1] for p in pts)/len(pts)
            spread=max(distance_bearing(lat,lon,a,b)[0] for a,b in pts)
            if spread>config.GPS_LEARN_MAX_SPREAD_M:
                on_done(False,f"I couldn't learn home: my position wandered {spread:.0f} metres. Try again in a clearer spot.")
                return
            keep={k:v for k,v in (self.home or {}).items() if k=='address'}   # a learned position keeps the address
            self.save_home({**keep,'lat':lat,'lon':lon,'fixes':len(pts),'spread_m':round(spread,1),'t':time.time()})
            log.info(f'GPS home learned: {lat:.6f},{lon:.6f} from {len(pts)} fixes, spread {spread:.1f} m')
            on_done(True,f"Got it. This is home. I averaged {len(pts)} fixes, within {spread:.0f} metres.")
        threading.Thread(target=run,daemon=True,name='gps-learn').start()


# ---------------------------------------------------------------- wander alert (FR-2300-003)

class WanderWatch:
    """'left' after GPS_WANDER_CONFIRM fresh fixes outside the radius (one wild fix cannot raise
    it), 'update' every GPS_ALERT_REPEAT_S while out, 'back' after the same count inside 80% of
    the radius. Feed it once per second with gps.fix() and home."""
    def __init__(self): self.out=False; self._n=0; self._last_alert=0.0
    def tick(self,fix,home,now):
        if not fix or not home: return None
        d,_=distance_bearing(home['lat'],home['lon'],fix['lat'],fix['lon'])
        if not self.out:
            self._n=self._n+1 if d>config.GPS_HOME_RADIUS_M else 0
            if self._n>=config.GPS_WANDER_CONFIRM:
                self.out=True; self._n=0; self._last_alert=now; return 'left'
        else:
            self._n=self._n+1 if d<config.GPS_HOME_RADIUS_M*0.8 else 0
            if self._n>=config.GPS_WANDER_CONFIRM:
                self.out=False; self._n=0; return 'back'
            if now-self._last_alert>=config.GPS_ALERT_REPEAT_S:
                self._last_alert=now; return 'update'
        return None


def email_position(fix,home):
    """Body text for an emailed position (FR-2300-001/003)."""
    lines=[f"Position: {fix['lat']:.6f}, {fix['lon']:.6f}",
           f"Map: {map_link(fix['lat'],fix['lon'])}",
           f"Fix age: {fix['age_s']:.0f} s, satellites: {fix.get('sats') or '?'}, HDOP: {fix.get('hdop') or '?'}"]
    if home: lines.insert(1,f"That is {relative_phrase(fix,home)}.")
    return '\n'.join(lines)
