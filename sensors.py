import time, math, threading, statistics, logging, config
import pico_link
if not config.SIMULATE_HARDWARE:
    import smbus2
    import board, busio
    import adafruit_bno08x
    from adafruit_bno08x.i2c import BNO08X_I2C
    from adafruit_bno08x import BNO_REPORT_ROTATION_VECTOR,BNO_REPORT_ACCELEROMETER
    # RPi.GPIO and the MCP23017 both left on 2026-09-30 (§4.7). Nothing in this module
    # drives a Pi GPIO any more: the sonars answer through Pico B and the encoders
    # through Pico A. GP4, GP5 and GP13 -- the pins Sonar used to time -- are TXD2,
    # RXD2 and RXD4 now, and driving them would fight the UART overlays.

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

# FR-800-002 (read sonar obstacle data): three HC-SR04s, read over uart2-pi5 from Pico B.
#
# MOVED OFF THE PI 2026-09-30, Master Hardware Design §4.7. This class used to time GP4,
# GP5 and GP13 itself. Those three pins are now TXD2, RXD2 and RXD4 -- the two UART
# overlays claim them -- so the old code was driving UART pins at sensors that are no
# longer on the Pi at all.
#
# ⚠ S-9 LIVES HERE. The old code returned 999.0 on a timeout and safety.py defaulted to
#   the same value, so "I got no reading" and "nothing is in front of me" were one
#   number. Behind a serial link that is a fail-open: a dropped frame becomes a positive
#   assertion of clear path. Two different silences now get two different answers:
#
#     FRESH frame, channel reads -1  -> the Pico pinged and heard nothing back. For a
#                                       sensor pointed at an open room that is true, and
#                                       it means CLEAR -> SONAR_MAX_CM.
#     NO fresh frame                 -> link down, board unpowered, wire out. Nothing is
#                                       known -> STOP -> 0.0, which every existing
#                                       comparison already reads as blocked.
#
#   The firmware sends a per-channel age so the Pi never has to guess which it is.
class SonarArray:
    _ORDER = ('front', 'left', 'right')      # $S field order, firmware/README.md

    def __init__(self, link=None):
        self._link = link if link is not None else pico_link.PicoLink(
            config.PICO_B_DEVICE, 'pico_b')
        self._owns_link = link is None
        self._sim = dict.fromkeys(self._ORDER, config.SONAR_MAX_CM)
        # Optional multi-zone ToF (§6.5). Set by brain.py when ENABLE_TOF; None otherwise,
        # which is also what an unavailable sensor degrades to. ALONGSIDE the sonar, never
        # replacing it -- the two are blind to different things, and ToF looks through glass.
        self.tof = None
        # REAR ToF (2026-10-10), set by brain.py when ENABLE_TOF_REAR. Read through rear_cm()
        # only -- NOT folded into distances(), whose three keys are sonar directions that the
        # world model plots and the avoidance code compares.
        self.tof_rear = None

    def start(self):
        if self._owns_link:
            self._link.start()

    def stop(self):
        if self._owns_link:
            self._link.stop()

    def reset_imu(self, timeout_s=0.5):
        """Pulse the BNO085's RST through Pico B GP15. True only once the board acknowledges.

        Lives here because Pico B's link does; IMU takes it as a callable. Proven on the rover
        2026-10-01: `$R,ok,<count>` back, then the chip reboots. A bare newline goes first:
        that day the first RST after opening the port was lost, most likely to a stray byte
        in front of it, and the Pico ignores an empty line.

        ⚠ Never send speculatively -- this is called from IMU recovery only."""
        if config.SIMULATE_HARDWARE:
            return True
        before, _ = self._link.latest('R')
        if not (self._link.send('') and self._link.send('RST')):
            return False
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            f, _ = self._link.latest('R')
            if f is not None and f != before:
                return len(f) > 1 and f[1] == 'ok'
            time.sleep(0.01)
        return False

    # --- the reading ---------------------------------------------------------------
    def _read_all(self):
        """{'front':cm,...}. Stale link -> 0.0 on every channel, which means STOP."""
        if config.SIMULATE_HARDWARE:
            return dict(self._sim)
        f = self._link.fresh('S', config.SONAR_STALE_S)
        if f is None:
            return dict.fromkeys(self._ORDER, 0.0)
        out = {}
        for i, name in enumerate(self._ORDER):
            try:
                mm = int(f[3 + i * 2])
                age_ms = int(f[4 + i * 2])
            except (IndexError, ValueError):
                out[name] = 0.0
                continue
            if mm < 0:
                # No echo. Nothing within range -- genuinely clear, not a failure.
                out[name] = config.SONAR_MAX_CM
            elif age_ms >= 0 and age_ms > config.SONAR_STALE_S * 1000:
                # The frame is fresh but THIS channel has not been updated inside it.
                # Per-channel staleness is why the protocol carries an age per channel.
                out[name] = 0.0
            else:
                out[name] = mm / 10.0
        return out

    @property
    def failed_channels(self):
        """FR-800-004: sonar channels that are not ranging, as {name: why}. A dead channel
        already reads 0.0 (= stop), which is safe but was SILENT -- this names it. Two causes:
        Pico B's stuck-ECHO flag (a destroyed sensor) and per-channel staleness inside a fresh
        frame. A whole stale link is is_healthy's job, not this."""
        if config.SIMULATE_HARDWARE: return {}
        f = self._link.fresh('S', config.SONAR_STALE_S)
        if f is None: return {}
        out = {}
        try: fl = int(f[9])
        except (IndexError, ValueError): fl = 0
        for i, name in enumerate(self._ORDER):
            if fl & (1 << i):
                out[name] = 'ECHO stuck high (sensor likely destroyed)'; continue
            try:
                age_ms = int(f[4 + i * 2])
            except (IndexError, ValueError):
                out[name] = 'unreadable field'; continue
            if age_ms > config.SONAR_STALE_S * 1000:
                out[name] = f'not updated for {age_ms} ms'
        return out

    @property
    def flags(self):
        """Pico B's flag byte. Bit 0/1/2 = front/left/right ECHO stuck high, which is the
        signature of a DESTROYED sensor rather than a timeout -- four have died on this
        rover. Bit 6 = an IMU reset has been performed since boot."""
        f = self._link.fresh('S', config.SONAR_STALE_S) if not config.SIMULATE_HARDWARE else None
        try:
            return int(f[9]) if f else 0
        except (IndexError, ValueError):
            return 0

    @property
    def is_healthy(self):
        if config.SIMULATE_HARDWARE:
            return True
        return self._link.is_healthy('S', config.SONAR_STALE_S)

    @property
    def distances(self):
        """THE fusion point (§6.5). 'front' is the minimum of the sonar reading and the
        nearest ToF zone reporting an obstacle -- whichever sensor sees something closer
        wins.

        min() is the whole design: fail-safe by construction, no arbitration logic, no new
        FSM state, no threshold changes. DIST_STOP/DIST_SLOW/DIST_CLEAR, _roam(), _slow()
        and _avoid() all keep working against the same dict key and never learn the ToF
        exists.

        The ToF only ever pulls 'front' DOWN. A None from it means "nothing to report" --
        not "the way is clear" -- so an uncalibrated or unavailable sensor can never mask a
        real sonar obstacle. Sides are untouched: this is a front sensor, and the
        left/right sonars are the only side coverage there is."""
        d = self._read_all()
        front = d['front']
        tof = self.tof
        # NOT gated on tof.available (fixed 2026-10-10). available only turns True inside a read,
        # and this was the read that never happened: gated on it, the front ToF stayed "unavailable"
        # for good and never fed the forward stop -- unless an avoidance turn happened to read it
        # first. nearest_obstacle_cm()/drop_detected() already return None/False on a failed or
        # stale read, so calling them unconditionally still falls back to sonar alone.
        if tof is not None:
            try:
                near = tof.nearest_obstacle_cm()
                if near is not None and near < front:
                    front = near
                # The ToF is the ONLY cliff detection (dedicated IR cliff sensors were dropped
                # 2026-09-12). Open space where the profile expects floor reads as an obstacle
                # at zero, so every forward gate stops. A dark rug can trip it: the safe way.
                drop = tof.drop_detected()
                if drop != getattr(self, '_tof_drop', False):
                    self._tof_drop = drop
                    (log.warning if drop else log.info)(
                        'ToF: DROP AHEAD -- stopping forward motion' if drop else 'ToF: floor ahead again')
                if drop:
                    front = 0.0
            except Exception:
                # distances() runs on the 20Hz tick. An exception escaping here would stop
                # obstacle checks entirely -- strictly worse than having no ToF at all.
                log.warning('ToF read raised inside distances(); using sonar alone',
                            exc_info=True)
        return {'front': front, 'left': d['left'], 'right': d['right']}

    def rear_cm(self):
        """Nearest obstacle BEHIND, in cm, from the rear ToF; a drop behind reads 0.0 (stop).
        None = nothing known: no rear sensor, uncalibrated, or no fresh frame. Reversing then
        behaves as it always has (there is no rear sonar); it never blocks motion by itself.
        Never raises: this runs on the tick."""
        tof = self.tof_rear
        if tof is None: return None
        try:
            now = time.monotonic()
            if tof.drop_detected():
                # Believed only once it has lasted TOF_DROP_CONFIRM_S (2+ frames): on 2026-10-10
                # the service saw ~1 Hz flickers, mostly while someone moved behind him, that 80
                # frames read standalone never showed. A real edge does not go away.
                since = getattr(self, '_rear_drop_since', None)
                if since is None: since = self._rear_drop_since = now
                if now - since >= config.TOF_DROP_CONFIRM_S:
                    if not getattr(self, '_rear_drop', False):
                        self._rear_drop = True
                        z = ', '.join(f'r{i//8}c{i%8}={v}' for i, v in getattr(tof, 'last_drop_zones', [])[:6])
                        log.warning(f'Rear ToF: DROP BEHIND -- reversing stopped ({z})')
                    return 0.0
            else:
                self._rear_drop_since = None
                if getattr(self, '_rear_drop', False):
                    self._rear_drop = False; log.info('Rear ToF: floor behind again')
            return tof.nearest_obstacle_cm()
        except Exception:
            log.warning('Rear ToF read raised; reversing without it', exc_info=True)
            return None

    def obstacle_ahead(self):
        return self.distances['front'] < config.DIST_STOP

    def should_slow(self):
        return self.distances['front'] < config.DIST_SLOW

    def better_side(self):
        d = self.distances
        return 'left' if d['left'] >= d['right'] else 'right'
# FR-800-001 (read IMU orientation data). tilt/is_safe below feed FR-800-003 (excessive
# tilt halts motion) and FR-300 approve_motion()'s tilt check -- the halt itself lives in
# safety.py/brain.py, this class only supplies the reading.
class IMU:
    # BNO085 SH-2 fusion chip — quaternion already drift-free, no complementary filter needed.
    # Mounting-axis convention (which physical axis reads as pitch/roll) is unconfirmed —
    # §20.7 bench calibration (mount level, verify) hasn't been run yet. RST: see the note in
    # __init__ and _poll_once. Between 2026-08-14 and 2026-09-30 it was a GPIO pulse through
    # the MCP23017's port B bit 4; since 2026-10-01 it is Pico B GP15, used for recovery.
    # INT (GP15) is still unused — the library works over I2C polling alone; §8.2 of
    # the master doc calls INT "required for SH-2 report timing" while this comment previously
    # called it optional, a still-unreconciled contradiction (not addressed by this change).
    def __init__(self, reset=None):
        # reset: a callable that pulses the chip's RST and returns True when acknowledged --
        # SonarArray.reset_imu, wired by brain.py. None leaves only the library's soft reset.
        self._reset = reset
        self._fails = 0; self._last_recover = float('-inf'); self.recoveries = 0
        self._settle_s = 0.5      # after RST: the chip reboots and re-advertises before I2C works
        self._last_q = None; self._last_change = time.monotonic()   # frozen-value check, _update
        if not config.SIMULATE_HARDWARE:
            # frequency= does NOT set the bus speed on Blinka/Linux -- the kernel i2c driver
            # does, via dtparam=i2c_arm_baudrate. Passing config.I2C_BAUDRATE keeps the stated
            # intent in one place rather than leaving a 100000 literal here that would quietly
            # contradict the kernel the moment the dtparam is raised. See config.I2C_BAUDRATE.
            self._i2c=busio.I2C(board.SCL,board.SDA,frequency=config.I2C_BAUDRATE)
            # RST is NOT the library's reset= pin. It is Pico B GP15 (§4.7 consequence 1),
            # driven open-drain against R4 and reached by an acknowledged RST command over
            # uart2-pi5 -- self._reset above. The library is still given reset=None, so at
            # construction it does its I2C soft reset as before. The hardware line is for
            # recovery (_poll_once), proven on the rover 2026-10-01 once the Pi -> Pico B
            # wire was resoldered.
            self._bno=self._make_bno()
        self._pitch=0.0; self._roll=0.0; self._yaw=0.0
        self._lock=threading.Lock(); self._last_ok=0.0
        self._running=False; self._thread=None
    def _make_bno(self):
        b=BNO08X_I2C(self._i2c,reset=None,address=config.IMU_ADDR)
        b.enable_feature(BNO_REPORT_ROTATION_VECTOR)
        b.enable_feature(BNO_REPORT_ACCELEROMETER)   # freshness signal, see config.IMU_STALE_S
        return b
    def _poll_once(self):
        """One read. Consecutive failures escalate to a hardware reset AND a rebuild.

        Always both. Measured 2026-10-01: across an RST the existing driver raised twice
        (KeyError, then 'Unprocessable Batch bytes') and then silently returned the last cached
        quaternion forever -- no error, no new data. A reset without a rebuild would leave tilt
        frozen at whatever it read before, which is worse than a visible fault."""
        try:
            self._update(); self._fails=0; return
        except Exception:
            self._fails+=1
            if self._fails==1:
                log.warning('BNO085 read failed (§8.5: disable autonomy, allow limited manual)', exc_info=True)
        if self._fails<config.IMU_RESET_AFTER_FAILS: return
        now=time.monotonic()
        if now-self._last_recover<config.IMU_RESET_MIN_INTERVAL_S: return
        self._last_recover=now; self.recoveries+=1
        acked=False
        if self._reset is not None:
            try: acked=bool(self._reset())
            except Exception: log.warning('BNO085 RST via Pico B raised', exc_info=True)
        how='hardware RST acknowledged' if acked else 'no hardware RST, soft path only'
        log.warning(f'BNO085: {self._fails} consecutive failed reads -- {how}, '
                    f'rebuilding the driver (recovery #{self.recoveries})')
        time.sleep(self._settle_s)
        try:
            self._bno=self._make_bno(); self._fails=0
            self._last_q=None; self._last_change=time.monotonic()
            log.info('BNO085 driver rebuilt')
        except Exception:
            log.warning('BNO085 rebuild failed; will retry after the rate limit', exc_info=True)
    def _update(self):
        if config.SIMULATE_HARDWARE:
            with self._lock: self._pitch=0.0; self._roll=0.0; self._yaw=0.0  # simulated level chassis
            self._last_ok=time.perf_counter(); return
        q=self._bno.quaternion; now=time.monotonic()
        try: sig=(q,self._bno.acceleration)   # raw accel noise moves even when he is still
        except Exception: sig=(q,None)
        if sig!=self._last_q:
            self._last_q=sig; self._last_change=now
        elif now-self._last_change>config.IMU_STALE_S:
            raise RuntimeError(f'BNO085 quaternion+acceleration unchanged for {now-self._last_change:.1f}s')
        i,j,k,w=q
        roll=math.degrees(math.atan2(2*(w*i+j*k),1-2*(i*i+j*j)))
        pitch=math.degrees(math.asin(max(-1.0,min(1.0,2*(w*j-k*i)))))
        yaw=math.degrees(math.atan2(2*(w*k+i*j),1-2*(j*j+k*k)))
        with self._lock:
            self._pitch=pitch; self._roll=roll; self._yaw=yaw
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
            self._poll_once()
            time.sleep(iv)
    @property
    def pitch(self):
        with self._lock: return self._pitch
    @property
    def heading(self):
        """FR-800-001: yaw in degrees (-180..180) from the fused quaternion. With the
        ROTATION_VECTOR report this is magnetometer-referenced; anything magnetic on the chassis
        biases it."""
        with self._lock: return self._yaw
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
        # I2C wire took the bus down and Willie powered himself off believing the battery was
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
    def accept_battery_raw(self,raw):
        """Adopt a raw ADC count only if it could plausibly be a real pack. Returns True if
        adopted, False if refused.

        The 2026-08-24 guard covers a read that FAILS. This covers one that SUCCEEDS and returns
        something impossible -- which is not hypothetical: with the battery divider unfed, A0
        read 0.0146V, scaling to a pack voltage near 0.06V. That read succeeds, passes every
        existing check, and walks brain.py's tier ladder to `shutdown`. The Pi is powered from
        that same pack; at 0.06V nothing would be executing this code, so the number is
        structurally impossible rather than merely alarming.

        A refusal is deliberately handled EXACTLY like a failure -- hold the last good value,
        do not refresh the timestamp -- so `is_healthy` goes False and brain.py escalates it
        through SENSOR_FAULT (grace period, visible fault, operator reset). No new path and no
        new state: the difference between a broken sensor and a flat battery is made once, here,
        and everything downstream already knows what to do with staleness."""
        volts=raw*self._LSB/config.BATTERY_DIVIDER_SCALE
        if volts<config.BAT_IMPLAUSIBLE_V:
            self._bat_fail_count+=1
            if self._bat_fail_count==1:
                log.warning(f'ADS1115 battery read implausible ({volts:.3f}V < '
                            f'{config.BAT_IMPLAUSIBLE_V}V) — treating as a BROKEN SENSOR, not a '
                            f'flat pack. Holding last good value and marking stale.')
            elif self._bat_fail_count%60==0:
                log.warning(f'ADS1115 battery reading still implausible ({volts:.3f}V, '
                            f'{self._bat_fail_count} consecutive)')
            return False
        self._bat_raw=raw
        if self._bat_fail_count:
            log.info(f'ADS1115 battery read recovered after {self._bat_fail_count} rejected/failed reads')
            self._bat_fail_count=0
        self._bat_last_ok=time.perf_counter()
        return True

    def grip_feedback_volts(self):
        """Gripper servo pot wiper voltage, servo side of the 47k/47k divider on AIN2.

        On demand, not polled: only the gripper calibration and (later) hand-off confirmation
        need it. Uncalibrated -- this is volts, not a jaw opening (MHD §6.6)."""
        return self.read_channel(config.ADS_CH_GRIP_FB)*self._LSB/config.GRIP_FB_DIVIDER_SCALE

    @property
    def battery_raw(self): return self._bat_raw
    @property
    def divider_volts(self):
        """The ADS1115 A0 divider reading alone (cross-check and fallback only)."""
        return self._bat_raw*self._LSB/config.BATTERY_DIVIDER_SCALE
    # 2026-10-02: the pack voltage comes from the +12V bus INA260 (0x45) whenever that rail is
    # live. The A0 divider read 7.19 V on an 11.98 V pack while 0x45 read 11.90 V; the bus
    # monitor is the trustworthy one. The divider is only used when the bus is switched off
    # (SW-M / base off), where 0x45 has nothing to measure. brain.py sets bus_source.
    bus_source=None
    @property
    def battery_volts(self):
        src=self.bus_source
        if src is not None:
            try:
                bus=src()
                if bus>=config.MOTOR_RAIL_MIN_V: return bus+config.BUS_TO_PACK_DROP_V
            except Exception:
                pass
        return self.divider_volts
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
                # accept_battery_raw() owns the adopt/refuse decision, the fail counter and
                # the timestamp -- a successful-but-impossible read is refused there and is then
                # indistinguishable, downstream, from the failed read handled below.
                self.accept_battery_raw(self.read_channel(config.ADS_CH_BATTERY))
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
    """Per-wheel counts, read over uart4-pi5 from Pico A at 50 Hz.

    MOVED OFF THE MCP23017 2026-09-30, Master Hardware Design §4.7. This class used to
    poll an I²C expander at 0x27 that is no longer on the bus -- a live scan returns ten
    devices and none of them is it. Until this change, constructing it raised
    `ValueError: No I2C device at address: 0x27`, `_init_device` retried eight times and
    re-raised, and `RoverBrain.__init__` died. The rover could not start.

    ⚠ COUNTS ARE UNSIGNED AND HAVE NO DIRECTION. `pico_a.py` counts rising edges on
      Phase A only, because all six Phase B greens have read dead since 2026-09-18 and
      may have been destroyed by that day's reversed supply. A wheel driven backwards
      counts UP exactly like one driven forwards. `lf` was found running in reverse on
      2026-09-29 and the telemetry could not see it. The quadrature table this class used
      to carry is gone with the expander; when the greens are repaired the firmware gains
      a decoder and the counts gain a sign, and **this docstring is the thing to delete
      that day.**

    `config.ENCODER_COUNTS_PER_REV` = 382 is MEASURED for these counts (2026-10-01, ×1 on
      the 35.5:1 motors). It quadruples the day Phase B is repaired and decoded -- see the
      config.py note; nothing here will notice on its own.

    The wheel order comes from the frame, and the frame's order is the as-built landing
    proved on hardware one wheel at a time on 2026-09-29: lf, lm, rf, rm, lr, rr.
    """

    _ORDER = ('lf', 'lm', 'rf', 'rm', 'lr', 'rr')      # $E field order == as-built J3

    def __init__(self, link=None):
        self._link = link if link is not None else pico_link.PicoLink(
            config.PICO_A_DEVICE, 'pico_a')
        self._owns_link = link is None
        self._counts = dict.fromkeys(self._ORDER, 0)
        self._prev_raw = dict.fromkeys(self._ORDER)     # last value off the wire, for unwrap
        self._seen_reboots = 0
        self._rate = dict.fromkeys(self._ORDER, 0.0)
        self._last_counts = dict(self._counts)
        self._last_rate_t = time.perf_counter()
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._last_ok = 0.0

    def start(self):
        if self._owns_link:
            self._link.start()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._owns_link:
            self._link.stop()

    def _update(self):
        if config.SIMULATE_HARDWARE:
            # No simulated physics loop drives wheel rotation -- counts hold their value.
            # Enough to exercise is_healthy/stalled()/the odometry wiring path off real
            # hardware; not a claim that simulated counts track simulated motion.
            self._last_ok = time.perf_counter()
            return
        f = self._link.fresh('E', config.ENCODER_STALE_S)
        if f is None:
            return                      # stale link: hold, and let is_healthy report it
        reboots = getattr(self._link, 'reboots', 0)
        rebase = reboots != getattr(self, '_seen_reboots', 0)
        self._seen_reboots = reboots
        with self._lock:
            for i, w in enumerate(self._ORDER):
                try:
                    raw = int(f[3 + i])
                except (IndexError, ValueError):
                    continue
                p = self._prev_raw[w]
                if p is None:
                    self._counts[w] = raw
                elif rebase:
                    # Pico A rebooted and started again from zero. Keep the running total and
                    # take the new origin, rather than reading the reset as a backwards move.
                    pass
                else:
                    # Unwrap across the 32-bit boundary, signed (a-0.3) or unsigned (a-0.2):
                    # the step is the shortest way round, and _counts is an unbounded int.
                    self._counts[w] += ((raw - p + 0x80000000) & 0xFFFFFFFF) - 0x80000000
                self._prev_raw[w] = raw
        self._last_ok = time.perf_counter()

    def _loop(self):
        # No 1 ms sleep and no bus contention any more: the old loop had to be throttled
        # because it shared I²C bus 1 with both MotorKits, the battery ADC and the IMU, and
        # a back-to-back encoder read stream queued stop commands behind it. This reads a
        # dedicated UART, so the constraint is gone -- but there is no point running faster
        # than Pico A emits, which is 50 Hz.
        iv = 1.0 / max(1.0, config.ENCODER_POLL_HZ)
        while self._running:
            try:
                self._update()
            except Exception:
                log.warning('Pico A encoder read failed', exc_info=True)
            now = time.perf_counter()
            if now - self._last_rate_t >= 0.2:
                with self._lock:
                    dt = now - self._last_rate_t
                    for w in self._counts:
                        self._rate[w] = (self._counts[w] - self._last_counts[w]) / dt
                        self._last_counts[w] = self._counts[w]
                self._last_rate_t = now
            time.sleep(iv)

    @property
    def r5_millivolts(self):
        """Pico A's own ADC reading of the R5 encoder rail, via its 10k/10k divider.

        This did not exist while the expander owned the encoders: the rail that powers the
        encoders had no monitor, and a sagging R5 looked exactly like six dead channels.
        It is already corrected for the divider by the firmware.
        """
        f = self._link.fresh('E', config.ENCODER_STALE_S)
        try:
            return int(f[9]) if f else None
        except (IndexError, ValueError):
            return None

    _F_R5_LOW = 0x02          # firmware/pico_a.py F_R5_LOW, set below its R5_WARN_MV

    @property
    def r5_low(self):
        """Pico A says R5 is below its warning threshold. False when no fresh frame: nothing is
        known about R5 then, and the link's own staleness is what is_healthy reports."""
        f = self._link.fresh('E', config.ENCODER_STALE_S)
        try:
            return bool(int(f[10]) & self._F_R5_LOW) if f else False
        except (IndexError, ValueError):
            return False

    @property
    def flags(self):
        """Pico A's flag byte. Bit 0 = at least one Phase B pin has transitioned since
        boot, which turns the open question about the six dead greens into telemetry.
        Bit 1 = R5 below its warning threshold. Bit 2 = a counter wrapped between reports.
        """
        f = self._link.fresh('E', config.ENCODER_STALE_S)
        try:
            return int(f[10]) if f else 0
        except (IndexError, ValueError):
            return 0

    @property
    # FR-500-001 (read wheel encoders): per-wheel counts, SIGNED since Pico A a-0.3, in the
    # board's raw sign -- +throttle counts up on every wheel. Rover-forward is
    # config.ENCODER_SIGN, applied in odometry.py.
    def counts(self):
        with self._lock:
            return dict(self._counts)

    @property
    # FR-500-002 (speed and distance): rate here; distance-over-time conversion using
    # wheel circumference happens in odometry.py, not this class.
    def counts_per_sec(self):
        with self._lock:
            return dict(self._rate)

    # FR-500-003 (stall detection, Directive 5).
    def stalled(self, wheel, commanded):
        # §8.5 fault behaviour: no counts while commanded -> caller should stop that drive.
        # ⚠ A stale link makes every wheel look stalled, which is the safe direction: it
        #   stops a rover that has lost sight of its own wheels rather than driving one
        #   blind. is_healthy is what distinguishes the two for anything that cares.
        with self._lock:
            return commanded and abs(self._rate.get(wheel, 0.0)) < 1.0

    @property
    def is_healthy(self):
        if config.SIMULATE_HARDWARE:
            return (time.perf_counter() - self._last_ok) < 1.0
        return self._link.is_healthy('E', config.ENCODER_STALE_S)
class CurrentMonitor:
    # INA260 x3 (§5.2): 0x40 = R2 5V (steering servos, sonar, screen), 0x44 = R3 6V (arm servo
    # distribution), 0x45 = +12V bus (both FeatherWing VIN). CORRECTED 2026-09-15 -- this comment
    # previously read "0x44 Pi rail, 0x45 motor rail" and contradicted the _RAILS dict directly
    # below it, which is part of how the mis-identification survived. Rail keys now state the
    # VOLTAGE, so they cannot quietly stop describing the wire. Monitor/log
    # only (feeds FR-1100 diagnostics) — no numeric overcurrent trip threshold exists anywhere
    # in the documentation to hardcode an automatic cutoff against (§14.1 uses "threshold" as a
    # literal placeholder with no value attached).
    _REG_CURRENT=0x01; _REG_VOLTAGE=0x02; _REG_POWER=0x03  # 1.25mA/bit, 1.25mV/bit, 10mW/bit
    _RAILS={'steering_5v':config.INA260_5V_ADDR,'arm_6v':config.INA260_ARM_6V_ADDR,
            'bus_12v':config.INA260_BUS_12V_ADDR}
    def __init__(self,bus=1):
        self._bus=None if config.SIMULATE_HARDWARE else smbus2.SMBus(bus)
        self._data={r:{'current_a':0.0,'voltage_v':0.0,'power_w':0.0} for r in self._RAILS}
        self._lock=threading.Lock(); self._running=False; self._thread=None; self._last_ok=0.0
        self._fail_counts={r:0 for r in self._RAILS}  # consecutive per-rail read failures
        self._rail_ok_t={r:0.0 for r in self._RAILS}   # per-rail last good read, see fresh_volts()
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
            now=time.perf_counter()
            with self._lock:
                for rail in self._RAILS:
                    self._data[rail]={'current_a':0.5,'voltage_v':12.0,'power_w':6.0}; self._rail_ok_t[rail]=now
            self._last_ok=now; return
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
            with self._lock:
                self._data[rail]={'current_a':cur,'voltage_v':volt,'power_w':pwr}
                self._rail_ok_t[rail]=time.perf_counter()
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
    def fresh_volts(self,name):
        """The rail voltage if read within INA_FRESH_S, else None. rail() holds the LAST GOOD value
        forever (§8.5 "log, hold last"), which is right for diagnostics and wrong for anything that
        decides on it: a dead 0x45 would freeze the battery reading at its last value (outside
        review 2026-10-08)."""
        with self._lock:
            if time.perf_counter()-self._rail_ok_t[name]>config.INA_FRESH_S: return None
            return self._data[name]['voltage_v']
    @property
    def all_rails(self):
        with self._lock: return {k:dict(v) for k,v in self._data.items()}
    @property
    def is_healthy(self): return (time.perf_counter()-self._last_ok)<1.0
