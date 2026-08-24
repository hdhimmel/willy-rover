import time, math, threading, statistics, logging, config
if not config.SIMULATE_HARDWARE:
    import smbus2
    import RPi.GPIO as GPIO
    import board, busio
    import adafruit_bno08x
    from adafruit_bno08x.i2c import BNO08X_I2C
    from adafruit_bno08x import BNO_REPORT_ROTATION_VECTOR
    from adafruit_mcp230xx.mcp23017 import MCP23017

    # adafruit_bno08x.hard_reset() only waits 10ms after releasing RST before the caller
    # sends the first I2C command (soft_reset). The BNO085 needs longer than that to boot
    # its SH-2 firmware and start ACKing on the bus -- with the stock 10ms delay, soft_reset's
    # write NACKs every time (OSError: [Errno 121] Remote I/O error), even though a passive
    # i2cdetect probe (which only checks ACK, sent at a different, non-deterministic moment)
    # can show the chip present. Confirmed live 2026-08-14: raising this to 300ms fixed it.
    def _bno08x_hard_reset(self):
        if not self._reset: return
        import digitalio
        self._reset.direction=digitalio.Direction.OUTPUT
        self._reset.value=True; time.sleep(0.01)
        self._reset.value=False; time.sleep(0.01)
        self._reset.value=True; time.sleep(0.3)
    adafruit_bno08x.BNO08X.hard_reset=_bno08x_hard_reset

log=logging.getLogger('sensors')

# FR-800-002 (read sonar obstacle data): three independent units, see SonarArray below.
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
    def stop(self):
        self._running=False
        if self._thread is not None: self._thread.join(timeout=2.0)
    def _loop(self):
        while self._running:
            for s in self._sensors: s.update(); time.sleep(config.SONAR_INTERVAL/3)
    @property
    def distances(self): return {'front':self.front.distance,'left':self.left.distance,'right':self.right.distance}
    def obstacle_ahead(self): return self.front.distance<config.DIST_STOP
    def should_slow(self): return self.front.distance<config.DIST_SLOW
    def better_side(self): return 'left' if self.left.distance>=self.right.distance else 'right'

# FR-800-001 (read IMU orientation data). tilt/is_safe below feed FR-800-003 (excessive
# tilt halts motion) and FR-300 approve_motion()'s tilt check -- the halt itself lives in
# safety.py/brain.py, this class only supplies the reading.
class IMU:
    # BNO085 SH-2 fusion chip — quaternion already drift-free, no complementary filter needed.
    # Mounting-axis convention (which physical axis reads as pitch/roll) is unconfirmed —
    # §20.7 bench calibration (mount level, verify) hasn't been run yet. RST (MCP23017 port B
    # bit 4, confirmed 2026-08-08) is now wired up below via adafruit_mcp230xx's DigitalInOut
    # pin, so BNO08X_I2C.hard_reset() does a real GPIO pulse instead of the silent no-op it was
    # before — a genuine SH-2 chip reset before enable_feature, not just the I2C soft-reset
    # command. INT (GP15) is still unused — the library works over I2C polling alone; §8.2 of
    # the master doc calls INT "required for SH-2 report timing" while this comment previously
    # called it optional, a still-unreconciled contradiction (not addressed by this change).
    def __init__(self):
        if not config.SIMULATE_HARDWARE:
            self._i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)
            mcp=MCP23017(self._i2c,address=config.ENCODER_ADDR)
            reset_pin=mcp.get_pin(config.IMU_RST_MCP_PIN)
            self._bno=BNO08X_I2C(self._i2c,reset=reset_pin,address=config.IMU_ADDR)
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
    def stop(self):
        self._running=False
        if self._thread is not None: self._thread.join(timeout=2.0)
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
    # FR-800-004 (sensor health): a stalled read thread reports unhealthy rather than
    # silently returning a stale cached value -- see brain.py's _check_health().
    def is_healthy(self): return (time.perf_counter()-self._last_ok)<max(0.5,4.0/config.IMU_POLL_HZ)
    def is_safe(self): return self.tilt<config.IMU_TILT_LIMIT
    def should_warn(self): return self.tilt>config.IMU_TILT_WARN

# FR-200-001 (voltage/current/power monitoring): battery_volts below is the calibrated
# reading brain.py's _bat_tier_for()/_update_bat_tier() threshold against (see brain.py).
class ADC:
    _POINTER_CONFIG=0x01; _POINTER_CONVERT=0x00
    _CONFIG_BASE=0x8000|0x0200|0x0100|0x0080|0x0003  # single-shot start, PGA ±4.096V, single-shot mode, 128SPS, comparator off
    _MUX={0:0x4000,1:0x5000,2:0x6000,3:0x7000}  # AINx vs GND
    _LSB=4.096/32768  # volts/bit at this PGA setting
    def __init__(self,bus=1):
        self._bus=None if config.SIMULATE_HARDWARE else smbus2.SMBus(bus)
        self._lock=threading.Lock(); self._bat_raw=0
        self._running=False; self._thread=None
        # 2026-08-24: a failed read used to set _bat_raw=0, which brain.py's tier ladder read as
        # 0.00V -> below BAT_SHUTDOWN_V -> silent controlled shutdown. That made "the I2C bus
        # hiccupped" indistinguishable from "the pack is flat", and it fired for real: a loose
        # I2C wire took the bus down and Willy powered himself off believing the battery was
        # empty, with no low-battery warning and no fault state -- destroying the evidence and,
        # with WiFi as the only link, taking him fully offline. Now a failed read HOLDS the last
        # good value and marks the reading stale; brain.py escalates staleness through the normal
        # SENSOR_FAULT path (grace period, visible fault state, operator reset) instead.
        self._bat_last_ok=0.0; self._bat_fail_count=0
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
    def is_healthy(self):
        # Same contract as IMU.is_healthy/Encoders.is_healthy: False means the value being
        # returned is stale, not that the battery is low. Poll interval is 1.0s, so allow a few
        # missed reads before declaring staleness. In SIMULATE_HARDWARE read_channel() never
        # raises, so this is always True off-hardware.
        if config.SIMULATE_HARDWARE: return True
        return (time.perf_counter()-self._bat_last_ok)<config.BAT_ADC_STALE_S
    @property
    def is_charging(self): return False  # charge-sense divider not wired yet (AIN0 = battery only)
    @property
    def battery_low(self): return self.battery_volts<config.BAT_WARN_V
    @property
    def battery_critical(self): return self.battery_volts<config.BAT_SAFE_V
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self):
        self._running=False
        if self._thread is not None: self._thread.join(timeout=2.0)
    def _loop(self):
        while self._running:
            try:
                self._bat_raw=self.read_channel(config.ADS_CH_BATTERY)
                if self._bat_fail_count:
                    log.info(f'ADS1115 battery read recovered after {self._bat_fail_count} failures')
                    self._bat_fail_count=0
                self._bat_last_ok=time.perf_counter()
            except Exception:
                # Deliberately does NOT zero _bat_raw -- see __init__. Holding the last good
                # value keeps a transient bus glitch from reading as a flat pack; is_healthy
                # going False is what tells brain.py the number is stale, and brain.py escalates
                # that through SENSOR_FAULT (grace period + visible fault + operator reset)
                # rather than silently shutting down.
                self._bat_fail_count+=1
                if self._bat_fail_count==1:
                    log.warning('ADS1115 battery read failed — holding last good value, '
                                'marking stale (§8.5)',exc_info=True)
                elif self._bat_fail_count%60==0:
                    log.warning(f'ADS1115 battery read still failing ({self._bat_fail_count} consecutive)')
            time.sleep(1.0)

class Encoders:
    # MCP23017 @0x27 (§9.1), quadrature A/B per wheel, polled. G-2 (FRD v3.1 §V.2): interrupt-
    # driven decode was decided 2026-08-18 and retracted 2026-08-23 -- it would have wired the
    # MCP23017's INTA pin (isolated side of ISO1540, §3.1) straight to a bare Pi GPIO, running a
    # conductor across the isolation barrier, and would not actually have reduced I2C transaction
    # count anyway (an interrupt only says "something changed"; learning what still costs a
    # register read, same as polling). The "~8.5kHz/channel" figure that motivated it was also
    # wrong -- it double-counted the gearbox reduction already baked into ENCODER_COUNTS_PER_REV.
    # Real edge rate is unresolved, roughly 450-4400 Hz depending on an unconfirmed gear ratio;
    # resolve by bench test (mark a wheel, jog known turns), not more arithmetic. If polling turns
    # out to be too slow, raise dtparam=i2c_arm_baudrate (this bus carries an LTC4311 for exactly
    # that), not interrupt-driven decode.
    #
    # Sign convention (forward=+) is asserted here, not yet confirmed against a physical dry-test
    # per §9.3 — flip per-wheel in config.py if a corner reads backwards once tested.
    _IODIRA=0x00; _IODIRB=0x01; _GPPUA=0x0C; _GPPUB=0x0D
    _GPIOA=0x12; _GPIOB=0x13
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
        if not config.SIMULATE_HARDWARE:
            # Seed real initial state instead of assuming 0 for every wheel (would otherwise
            # register a spurious first-count delta on whichever wheel's real resting state isn't
            # 0b00) -- deliberately does not go through _update()/_QTABLE, just captures the
            # starting point.
            a=self._bus.read_byte_data(config.ENCODER_ADDR,self._GPIOA)
            b=self._bus.read_byte_data(config.ENCODER_ADDR,self._GPIOB)
            for w,(bank,bitA,bitB) in config.ENCODER_PINS.items():
                byte=a if bank=='A' else b
                self._state[w]=(((byte>>bitA)&1)<<1)|((byte>>bitB)&1)
            self._last_ok=time.perf_counter()
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
    def stop(self):
        self._running=False
        if self._thread is not None: self._thread.join(timeout=2.0)
    def _loop(self):
        # Polling loop -- practical ceiling near 1kHz, set by the I2C transaction cost (bus +
        # smbus2/kernel driver + CPython), not by this loop's own overhead. See this class's
        # docstring (G-2/S-2) for the real edge-rate question and how it gets resolved (bench
        # test), and dtparam=i2c_arm_baudrate as the fix if polling proves too slow.
        #
        # The 1ms sleep is NOT optional throttling -- it is what keeps this thread from
        # saturating I2C bus 1, which is shared with everything safety-relevant: both MotorKits
        # (0x60/0x61, i.e. stop commands), the ADS1115 battery ADC feeding the brownout logic,
        # and the BNO085 IMU. Without it every one of those transactions queues behind a
        # back-to-back encoder read stream. It also holds continuous CPU/GIL pressure on a Pi
        # where WHISPER_CPU_THREADS=3 was chosen specifically to keep peak draw off the 5V rail.
        # Restored 2026-08-23 after the interrupt-decode revert dropped it by accident (the
        # pre-interrupt code had it; the revert produced a sleepless loop that had never run
        # in this form). Do not remove without measuring bus occupancy against motor latency.
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
    # FR-500-001 (read wheel encoders): raw per-wheel quadrature counts.
    def counts(self):
        with self._lock: return dict(self._counts)
    @property
    # FR-500-002 (speed and distance): rate here; distance-over-time conversion using
    # wheel circumference happens in odometry.py, not this class.
    def counts_per_sec(self):
        with self._lock: return dict(self._rate)
    # FR-500-003 (stall detection, Directive 5).
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
        self._fail_counts={r:0 for r in self._RAILS}  # consecutive per-rail read failures
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
        # Per-rail isolation. This loop used to let the first failing rail's exception propagate
        # out of _update() entirely, so a single absent INA260 meant the *other* rails were never
        # read at all and every rail's data went stale -- which is how one dead device (0x40)
        # produced a self-test verdict of "current monitors not reporting", plural, and blinded
        # the motor-rail reading that diagnostics actually want. Found live 2026-08-24.
        all_ok=True
        for rail,addr in self._RAILS.items():
            try:
                cur,volt,pwr=self._read_rail(addr)
            except OSError:
                all_ok=False
                n=self._fail_counts[rail]=self._fail_counts[rail]+1
                # Throttled: this runs at 10Hz, and a permanently-absent device previously
                # emitted a full traceback every single iteration (measured: ~13k journal lines
                # in 2 minutes). Log the first failure with a traceback, then once a minute.
                if n==1:
                    log.warning(f'INA260 {rail} rail (0x{addr:02x}) read failed '
                                f'(§8.5: log, hold last; sustained fail -> SAFE_MODE)',exc_info=True)
                elif n%600==0:
                    log.warning(f'INA260 {rail} rail (0x{addr:02x}) still failing ({n} consecutive)')
                continue
            if self._fail_counts[rail]:
                log.info(f'INA260 {rail} rail (0x{addr:02x}) recovered after {self._fail_counts[rail]} failures')
                self._fail_counts[rail]=0
            with self._lock: self._data[rail]={'current_a':cur,'voltage_v':volt,'power_w':pwr}
        # Deliberately strict: _last_ok (and therefore is_healthy, which brain.py::_check_health
        # escalates on) still requires ALL rails to read. A missing monitor is a real fault and
        # should keep failing the self-test -- this fix restores the other rails' *data*, it does
        # not mask the fault.
        if all_ok: self._last_ok=time.perf_counter()
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self):
        self._running=False
        if self._thread is not None: self._thread.join(timeout=2.0)
    def _loop(self):
        while self._running:
            try: self._update()
            except Exception:
                # Per-rail OSErrors are handled and throttled inside _update(); this only catches
                # anything unexpected that escapes it, so a traceback here is genuinely notable.
                log.warning('INA260 monitor loop failed unexpectedly', exc_info=True)
            time.sleep(0.1)  # 10Hz per §8.5
    def rail(self,name):
        with self._lock: return dict(self._data[name])
    @property
    def all_rails(self):
        with self._lock: return {k:dict(v) for k,v in self._data.items()}
    @property
    def is_healthy(self): return (time.perf_counter()-self._last_ok)<1.0
