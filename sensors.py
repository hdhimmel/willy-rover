import RPi.GPIO as GPIO
import smbus2, spidev, time, math, threading, statistics, config

class Sonar:
    def __init__(self,trig,echo):
        self.trig=trig; self.echo=echo
        GPIO.setup(trig,GPIO.OUT,initial=GPIO.LOW); GPIO.setup(echo,GPIO.IN)
        self._lock=threading.Lock(); self._last=999.0
    def _ping(self):
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
        GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
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
    _MPU=config.IMU_I2C_ADDR; _AS=16384.0; _GS=131.0
    def __init__(self,bus=1):
        self._bus=smbus2.SMBus(bus); self._pitch=0.0; self._roll=0.0
        self._lock=threading.Lock(); self._last_t=time.perf_counter()
        self._alpha=0.96; self._running=False; self._thread=None
        self._bus.write_byte_data(self._MPU,0x6B,0x00); time.sleep(0.1)
        self._bus.write_byte_data(self._MPU,0x1A,0x03)
    def _update(self):
        now=time.perf_counter(); dt=now-self._last_t; self._last_t=now
        d=self._bus.read_i2c_block_data(self._MPU,0x3B,14)
        def s16(h,l): v=(h<<8)|l; return v-65536 if v>=32768 else v
        ax=s16(d[0],d[1])/self._AS; ay=s16(d[2],d[3])/self._AS; az=s16(d[4],d[5])/self._AS
        gx=s16(d[8],d[9])/self._GS; gy=s16(d[10],d[11])/self._GS
        n=math.sqrt(ax*ax+ay*ay+az*az) or 1.0
        pa=math.degrees(math.asin(max(-1,min(1,ax/n)))); ra=math.degrees(math.atan2(ay,az))
        with self._lock:
            self._pitch=self._alpha*(self._pitch+gy*dt)+(1-self._alpha)*pa
            self._roll=self._alpha*(self._roll+gx*dt)+(1-self._alpha)*ra
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self): self._running=False
    def _loop(self):
        iv=1.0/config.IMU_POLL_HZ
        while self._running:
            try: self._update()
            except: pass
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
    def is_safe(self): return self.tilt<config.IMU_TILT_LIMIT
    def should_warn(self): return self.tilt>config.IMU_TILT_WARN

class ADC:
    def __init__(self):
        self._spi=spidev.SpiDev(); self._spi.open(0,0)
        self._spi.max_speed_hz=1350000; self._spi.mode=0
        self._lock=threading.Lock(); self._bat=0; self._chg=0
        self._running=False; self._thread=None
    def read_channel(self,ch):
        with self._lock: r=self._spi.xfer2([1,(8+ch)<<4,0])
        return ((r[1]&3)<<8)|r[2]
    @property
    def battery_raw(self): return self._bat
    @property
    def battery_volts(self): return self._bat*(3.3/1023)/0.2481
    @property
    def battery_pct(self):
        if self._bat>=config.BAT_FULL: return 100
        if self._bat<=config.BAT_CRITICAL: return 0
        return int((self._bat-config.BAT_CRITICAL)/(config.BAT_FULL-config.BAT_CRITICAL)*100)
    @property
    def is_charging(self): return self._chg>100
    @property
    def battery_low(self): return self._bat<config.BAT_LOW
    @property
    def battery_critical(self): return self._bat<config.BAT_CRITICAL
    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
    def stop(self): self._running=False; self._spi.close()
    def _loop(self):
        while self._running:
            try: self._bat=self.read_channel(config.MCP_CH_BATTERY); self._chg=self.read_channel(config.MCP_CH_CHARGE)
            except: pass
            time.sleep(1.0)
