import glob,os,config,logsetup
log=logsetup.setup('thermal')

# M-009 thermal monitoring (2026-10-08). The Pi 5 throttles itself (soft cap ~80 C, hard 85 C),
# so this module takes no action on motion: heat is a slowdown, not a Directive hazard. It makes
# the heat VISIBLE -- a trend line in the log, an EVENT=THERMAL line on every level change, a
# spoken warning once on reaching HOT, the temperature on the face, and a fan-stopped check
# (the active cooler's tach reads ~5700 rpm at 58 C on willie, 2026-10-08).

def read_cpu_c():
    """SoC temperature in C, or None if it cannot be read (not a Pi, sysfs missing)."""
    try:
        with open(config.THERMAL_ZONE_PATH) as f: return int(f.read().strip())/1000.0
    except (OSError,ValueError):
        return None

def read_fan_rpm():
    """Active-cooler tach, or None when there is no pwmfan hwmon device."""
    for d in glob.glob('/sys/class/hwmon/hwmon*'):
        try:
            with open(os.path.join(d,'name')) as f:
                if f.read().strip()!='pwmfan': continue
            with open(os.path.join(d,'fan1_input')) as f: return int(f.read().strip())
        except (OSError,ValueError):
            continue
    return None


class ThermalMonitor:
    """Level ok / warm / hot with hysteresis, plus a fan-stopped flag. poll(now) is cheap (two
    sysfs reads) and rate-limits itself to THERMAL_POLL_S. Returns the new level on a change,
    else None. The readers are injectable for tests."""
    def __init__(self,read_temp=read_cpu_c,read_fan=read_fan_rpm):
        self.read_temp=read_temp; self.read_fan=read_fan
        self.level='ok'; self.temp_c=None; self.fan_rpm=None; self.fan_stopped=False
        self._next_poll=0.0; self._next_trend=0.0

    def _level_for(self,t):
        h=config.THERMAL_HYSTERESIS_C
        if t>=config.THERMAL_HOT_C: return 'hot'
        if self.level=='hot' and t>config.THERMAL_HOT_C-h: return 'hot'
        if t>=config.THERMAL_WARM_C: return 'warm'
        if self.level in ('warm','hot') and t>config.THERMAL_WARM_C-h: return 'warm'
        return 'ok'

    def poll(self,now):
        if now<self._next_poll: return None
        self._next_poll=now+config.THERMAL_POLL_S
        t=self.read_temp()
        if t is None: return None
        self.temp_c=t; self.fan_rpm=self.read_fan()
        stopped=(self.fan_rpm is not None and self.fan_rpm==0 and t>=config.THERMAL_FAN_CHECK_C)
        if stopped and not self.fan_stopped:
            logsetup.log_event(log,'THERMAL',severity='warning',subsystem='thermal',status='fan_stopped',
                               cpu_c=f'{t:.1f}')
        self.fan_stopped=stopped
        if now>=self._next_trend:
            self._next_trend=now+config.THERMAL_TREND_LOG_S
            log.info(f'CPU {t:.1f} C, fan {self.fan_rpm if self.fan_rpm is not None else "?"} rpm')
        new=self._level_for(t)
        if new==self.level: return None
        old,self.level=self.level,new
        logsetup.log_event(log,'THERMAL',severity='warning' if new=='hot' else 'info',subsystem='thermal',
                           status=new,previous=old,cpu_c=f'{t:.1f}',fan_rpm=self.fan_rpm)
        return new
