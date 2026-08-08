import smbus2, time, math, threading, statistics, logging, config
if not config.SIMULATE_HARDWARE:
    import RPi.GPIO as GPIO
    import board, busio
    from adafruit_bno08x.i2c import BNO08X_I2C
    from adafruit_bno08x import BNO_REPORT_ROTATION_VECTOR

log=logging.getLogger('sensors')

class Sonar:
    def __init__(self,trig,echo):
        self.trig=trig; self.echo=echo
        if not config.SIMULATE_HARDWARE:
            GPIO.setup(trig,GPIO.OUT,initial=GPIO.LOW); GPIO.setup(echo,GPIO.IN)
        self._lock=threading.Lock(); self._last=999.0
    def _ping(self):
        if config.SIMULATE_HARDWARE: return 200.0  # simulated "clear path" reading
        with self._lock:
            GPIO.output(self.trig,GPIO.LOW); time.sleep(0.000002)
            GPIO.output(self.trig,GPIO.HIGH); time.sleep(0.000010)
            GPIO.output(self.trig,GPIO.LOW)
            t0=time.perf_counter()
            while GPIO.input(self.echo)==0:
                if time.perf_counter()-t0>config.SONAR_TIMEOUT: return 999.0
            t1=time.perf_counter()
            while GPIO.input(self.echo)==1:
                if time.perf_counter()-t1>config.SONAR_TIMEOUT: return 999.0
            t2=time.perf_counter()
        return round((t2-t1)*34300/2,1)
    def read(self): return statistics.median([self._ping() for _ in range(config.SONAR_SAMPLES)])
    @property
    def distance(self): return self._last
    def update(self): self._last=self.read()

class SonarArray:
    def __init__(self):
        if not config.SIMULATE_HARDWARE: GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
        self.front=Sonar(config.SONAR_FRONT_TRIG,config.SONAR_FRONT_ECHO)
        self.left=Sonar(config.SONAR_LEFT_TRIG,config.SONAR_LEFT_ECHO)
        self.right=Sonar(config.SONAR_RIGHT_TRIG,config.SONAR_RIGHT_ECHO)
        self._sensors=[self.front,self.left,self.right]
        self._running=False; self._thread=None
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self): self._running=False
    def _loop(self):
        while self._running:
            for s in self._sensors: s.update(); time.sleep(config.SONAR_INTERVAL/3)
    @property
    def distances(self): return {'front':self.front.distance,'left':self.left.distance,'right':self.right.distance}
    def obstacle_ahead(self): return self.front.distance<config.DIST_STOP
    def should_slow(self): return self.front.distance<config.DIST_SLOW
    def better_side(self): return 'left' if self.left.distance>=self.right.distance else 'right'

class IMU:
    # BNO085 SH-2 fusion chip — quaternion already drift-free, no complementary filter needed.
    # Mounting-axis convention (which physical axis reads as pitch/roll) is unconfirmed —
    # §20.7 bench calibration (mount level, verify) hasn't been run yet. INT (GP15) and RST
    # (MCP23017 spare pin) are wired per §8.2 but unused here — the library works over I2C
    # polling alone; wiring them up is a latency optimization, not required for correctness.
    def __init__(self):
        if not config.SIMULATE_HARDWARE:
            self._i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)
            self._bno=BNO08X_I2C(self._i2c,address=config.IMU_ADDR)
            self._bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)
        self._pitch=0.0; self._roll=0.0
        self._lock=threading.Lock(); self._last_ok=0.0
        self._running=False; self._thread=None
    def _update(self):
        if config.SIMULATE_HARDWARE:
            with self._lock: self._pitch=0.0; self._roll=0.0  # simulated level chassis
            self._last_ok=time.perf_counter(); return
        i,j,k,w=self._bno.quaternion
        roll=math.degrees(math.atan2(2*(w*i+j*k),1-2*(i*i+j*j)))
        pitch=math.degrees(math.asin(max(-1.0,min(1.0,2*(w*j-k*i)))))
        with self._lock:
            self._pitch=pitch; self._roll=roll
        self._last_ok=time.perf_counter()
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self): self._running=False
    def _loop(self):
        iv=1.0/config.IMU_POLL_HZ
        while self._running:
            try: self._update()
            except Exception:
                log.warning('BNO085 read failed (§8.5: disable autonomy, allow limited manual)', exc_info=True)
            time.sleep(iv)
    @property
    def pitch(self):
        with self._lock: return self._pitch
    @property
    def roll(self):
        with self._lock: return self._roll
    @property
    def tilt(self):
        with self._lock: return math.sqrt(self._pitch**2+self._roll**2)
    @property
    def is_healthy(self): return (time.perf_counter()-self._last_ok)<max(0.5,4.0/config.IMU_POLL_HZ)
    def is_safe(self): return self.tilt<config.IMU_TILT_LIMIT
    def should_warn(self): return self.tilt>config.IMU_TILT_WARN

class ADC:
    _POINTER_CONFIG=0x01; _POINTER_CONVERT=0x00
    _CONFIG_BASE=0x8000|0x0200|0x0100|0x0080|0x0003  # single-shot start, PGA ±4.096V, single-shot mode, 128SPS, comparator off
    _MUX={0:0x4000,1:0x5000,2:0x6000,3:0x7000}  # AINx vs GND
    _LSB=4.096/32768  # volts/bit at this PGA setting
    def __init__(self,bus=1):
        self._bus=None if config.SIMULATE_HARDWARE else smbus2.SMBus(bus)
        self._lock=threading.Lock(); self._bat_raw=0
        self._running=False; self._thread=None
    def read_channel(self,ch):
        if config.SIMULATE_HARDWARE:
            # simulated healthy mid-charge pack (§18: not a real 100%/full-charge claim, just a
            # safe-above-BAT_WARN_V value so sim-mode brain.py doesn't sit in a battery fault state)
            return int(12.0*config.BATTERY_DIVIDER_SCALE/self._LSB)
        with self._lock:
            cfg=self._CONFIG_BASE|self._MUX[ch]
            self._bus.write_i2c_block_data(config.ADS_ADDR,self._POINTER_CONFIG,[(cfg>>8)&0xFF,cfg&0xFF])
            time.sleep(0.01)
            while self._bus.read_i2c_block_data(config.ADS_ADDR,self._POINTER_CONFIG,2)[0]&0x80==0:
                time.sleep(0.001)
            d=self._bus.read_i2c_block_data(config.ADS_ADDR,self._POINTER_CONVERT,2)
        raw=(d[0]<<8)|d[1]
        return raw-65536 if raw>=32768 else raw
    @property
    def battery_raw(self): return self._bat_raw
    @property
    def battery_volts(self): return self._bat_raw*self._LSB/config.BATTERY_DIVIDER_SCALE
    @property
    def battery_pct(self):
        # Display-only (HUD/voice) — a linear map between under-load thresholds, not a true
        # state-of-charge model. Voltage under load != open-circuit/rested voltage; see the
        # BAT_FULL_V comment in config.py. Nothing safety-relevant reads this — brain.py's tier
        # ladder always compares battery_volts against BAT_WARN/RTH/SAFE/SHUTDOWN_V directly.
        v=self.battery_volts
        if v>=config.BAT_FULL_V: return 100
        if v<=config.BAT_SHUTDOWN_V: return 0
        return int((v-config.BAT_SHUTDOWN_V)/(config.BAT_FULL_V-config.BAT_SHUTDOWN_V)*100)
    @property
    def is_charging(self): return False  # charge-sense divider not wired yet (AIN0 = battery only)
    @property
    def battery_low(self): return self.battery_volts<config.BAT_WARN_V
    @property
    def battery_critical(self): return self.battery_volts<config.BAT_SAFE_V
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self): self._running=False
    def _loop(self):
        while self._running:
            try:
                self._bat_raw=self.read_channel(config.ADS_CH_BATTERY)
            except Exception:
                log.warning('ADS1115 read failed — assuming worst-case battery state (§8.5)', exc_info=True)
                self._bat_raw=0
            time.sleep(1.0)

class Encoders:
    # MCP23017 @0x27 (§9.1), quadrature A/B per wheel. No interrupt line runs to the Pi (only
    # the IMU has one, at GP15) — this polls GPIOA/GPIOB continuously rather than decoding on
    # an edge interrupt. At the documented ~3292 counts/rev / 620rpm no-load spec, a ~1kHz poll
    # (the practical ceiling on a 100kHz I2C bus for two single-byte reads) can miss edges under
    # load — best-effort counts/stall-detection, not a substitute for a real ISR-driven decoder.
    # Sign convention (forward=+) is asserted here, not yet confirmed against a physical dry-test
    # per §9.3 — flip per-wheel in config.py if a corner reads backwards once tested.
    _IODIRA=0x00; _IODIRB=0x01; _GPPUA=0x0C; _GPPUB=0x0D; _GPIOA=0x12; _GPIOB=0x13
    _QTABLE=[0,-1,1,0, 1,0,0,-1, -1,0,0,1, 0,1,-1,0]  # [old_state<<2|new_state] -> delta
    def __init__(self,bus=1):
        if config.SIMULATE_HARDWARE:
            self._bus=None
        else:
            self._bus=smbus2.SMBus(bus)
            self._bus.write_byte_data(config.ENCODER_ADDR,self._IODIRA,0xFF)
            self._bus.write_byte_data(config.ENCODER_ADDR,self._IODIRB,0xFF)
            self._bus.write_byte_data(config.ENCODER_ADDR,self._GPPUA,0xFF)
            self._bus.write_byte_data(config.ENCODER_ADDR,self._GPPUB,0xFF)
        self._counts=dict.fromkeys(config.ENCODER_PINS,0)
        self._rate=dict.fromkeys(config.ENCODER_PINS,0.0)
        self._state=dict.fromkeys(config.ENCODER_PINS,0)
        self._last_counts=dict(self._counts); self._last_rate_t=time.perf_counter()
        self._lock=threading.Lock(); self._running=False; self._thread=None; self._last_ok=0.0
    def _update(self):
        if config.SIMULATE_HARDWARE:
            # No simulated physics loop drives wheel rotation — counts simply hold their current
            # value each tick. Enough to exercise is_healthy/stalled()/the odometry wiring path
            # off real hardware; not a claim that simulated counts track a simulated motion.
            self._last_ok=time.perf_counter(); return
        a=self._bus.read_byte_data(config.ENCODER_ADDR,self._GPIOA)
        b=self._bus.read_byte_data(config.ENCODER_ADDR,self._GPIOB)
        with self._lock:
            for w,(bank,bitA,bitB) in config.ENCODER_PINS.items():
                byte=a if bank=='A' else b
                state=(((byte>>bitA)&1)<<1)|((byte>>bitB)&1)
                self._counts[w]+=self._QTABLE[(self._state[w]<<2)|state]
                self._state[w]=state
        self._last_ok=time.perf_counter()
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self): self._running=False
    def _loop(self):
        while self._running:
            try: self._update()
            except Exception:
                log.warning('MCP23017 encoder read failed', exc_info=True)
            now=time.perf_counter()
            if now-self._last_rate_t>=0.2:
                with self._lock:
                    dt=now-self._last_rate_t
                    for w in self._counts:
                        self._rate[w]=(self._counts[w]-self._last_counts[w])/dt
                        self._last_counts[w]=self._counts[w]
                self._last_rate_t=now
            time.sleep(0.001)
    @property
    def counts(self):
        with self._lock: return dict(self._counts)
    @property
    def counts_per_sec(self):
        with self._lock: return dict(self._rate)
    def stalled(self,wheel,commanded):
        # §8.5 fault behavior: no counts while commanded -> caller should stop the affected drive.
        with self._lock: return commanded and abs(self._rate.get(wheel,0.0))<1.0
    @property
    def is_healthy(self): return (time.perf_counter()-self._last_ok)<1.0

class CurrentMonitor:
    # INA260 x3 (§5.2): 0x40 servo/steering rail, 0x44 Pi rail, 0x45 motor rail. Monitor/log
    # only (feeds FR-1100 diagnostics) — no numeric overcurrent trip threshold exists anywhere
    # in the documentation to hardcode an automatic cutoff against (§14.1 uses "threshold" as a
    # literal placeholder with no value attached).
    _REG_CURRENT=0x01; _REG_VOLTAGE=0x02; _REG_POWER=0x03  # 1.25mA/bit, 1.25mV/bit, 10mW/bit
    _RAILS={'servo':config.INA260_SERVO_ADDR,'pi':config.INA260_PI_ADDR,'motor':config.INA260_MOTOR_ADDR}
    def __init__(self,bus=1):
        self._bus=None if config.SIMULATE_HARDWARE else smbus2.SMBus(bus)
        self._data={r:{'current_a':0.0,'voltage_v':0.0,'power_w':0.0} for r in self._RAILS}
        self._lock=threading.Lock(); self._running=False; self._thread=None; self._last_ok=0.0
    def _be16(self,addr,reg):
        d=self._bus.read_i2c_block_data(addr,reg,2)
        v=(d[0]<<8)|d[1]
        return v-65536 if v>=32768 else v
    def _read_rail(self,addr):
        return (self._be16(addr,self._REG_CURRENT)*0.00125,
                self._be16(addr,self._REG_VOLTAGE)*0.00125,
                self._be16(addr,self._REG_POWER)*0.01)
    def _update(self):
        if config.SIMULATE_HARDWARE:
            with self._lock:
                for rail in self._RAILS: self._data[rail]={'current_a':0.5,'voltage_v':12.0,'power_w':6.0}
            self._last_ok=time.perf_counter(); return
        for rail,addr in self._RAILS.items():
            cur,volt,pwr=self._read_rail(addr)
            with self._lock: self._data[rail]={'current_a':cur,'voltage_v':volt,'power_w':pwr}
        self._last_ok=time.perf_counter()
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self): self._running=False
    def _loop(self):
        while self._running:
            try: self._update()
            except Exception:
                log.warning('INA260 read failed (§8.5: log, hold last; sustained fail -> SAFE_MODE)', exc_info=True)
            time.sleep(0.1)  # 10Hz per §8.5
    def rail(self,name):
        with self._lock: return dict(self._data[name])
    @property
    def all_rails(self):
        with self._lock: return {k:dict(v) for k,v in self._data.items()}
    @property
    def is_healthy(self): return (time.perf_counter()-self._last_ok)<1.0
