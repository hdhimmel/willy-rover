import time,logging,config
from motors import DriveBase
from sensors import SonarArray,IMU,ADC
from display import WillyFace
from claude_client import ClaudeClient
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)-7s %(message)s',datefmt='%H:%M:%S')
log=logging.getLogger('brain')

class RoverBrain:
    def __init__(self):
        log.info('Initialising WildWilly v2...')
        self.display=WillyFace(); self.motors=DriveBase()
        self.sonars=SonarArray(); self.imu=IMU(); self.adc=ADC()
        self.claude=ClaudeClient()
        self._state='IDLE'; self._stuck_count=0; self._last_action='none'
        self._idle_t=0.0; self._avoid_start=0.0; self._running=False

    def start(self):
        log.info('Starting subsystems...')
        self.display.start(); self.sonars.start(); self.imu.start(); self.adc.start()
        self._running=True; self.display.update_state('idle','WildWilly v2 ready')
        log.info('WildWilly v2 ready.')

    def stop(self):
        log.info('Shutting down...')
        self._running=False; self.motors.brake(); time.sleep(0.2)
        self.motors.cleanup(); self.sonars.stop(); self.imu.stop(); self.adc.stop(); self.display.stop()

    def run(self):
        self.start()
        try:
            while self._running: self._tick(); time.sleep(0.05)
        except KeyboardInterrupt: log.info('Stopped.')
        finally: self.stop()

    def _tick(self):
        d=self.sonars.distances; tilt=self.imu.tilt; bat=self.adc.battery_pct
        if tilt>config.IMU_TILT_LIMIT:
            if self._state!='ESTOP': log.warning(f'ESTOP tilt={tilt:.1f}'); self._go('ESTOP')
            self.motors.brake(); self._upd('warn',f'TILT {tilt:.1f}deg STOP',d,tilt); return
        if self._state=='ESTOP' and tilt<config.IMU_TILT_WARN: self._go('IDLE')
        if self.adc.battery_low and self._state not in('DOCK','ESTOP','IDLE'):
            log.info(f'Battery low {bat}% -> DOCK'); self._go('DOCK'); return
        if self._state=='DOCK' and self.adc.is_charging:
            self.motors.stop(); self._upd('idle',f'Charging {bat}%',d,tilt)
            if bat>=95: self._go('ROAM')
            return
        {'IDLE':self._idle,'ROAM':self._roam,'SLOW':self._slow,'AVOID':self._avoid,
         'STUCK':self._stuck,'DOCK':self._dock,'WARN':self._warn,'ESTOP':lambda d,t:None
        }.get(self._state,lambda d,t:None)(d,tilt)

    def _idle(self,d,tilt):
        self.motors.stop(); self._idle_t+=0.05
        self._upd('idle',f'Waiting... bat={self.adc.battery_pct}%',d,tilt)
        if self._idle_t>=config.IDLE_TIMEOUT: self._idle_t=0.0; self._go('ROAM')

    def _roam(self,d,tilt):
        f=d['front']
        if tilt>config.IMU_TILT_WARN: self._go('WARN'); return
        if f<config.DIST_STOP: self._go('AVOID'); return
        if f<config.DIST_SLOW: self._go('SLOW'); return
        self.motors.forward(config.SPEED_ROAM); self._last_action='forward'
        self._upd('roam',f'Cruising f={f:.0f}cm bat={self.adc.battery_pct}%',d,tilt,config.SPEED_ROAM)

    def _slow(self,d,tilt):
        f=d['front']
        if f>config.DIST_CLEAR: self._go('ROAM'); return
        if f<config.DIST_STOP: self._go('AVOID'); return
        self.motors.forward(config.SPEED_SLOW); self._upd('slow',f'Slowing f={f:.0f}cm',d,tilt,config.SPEED_SLOW)

    def _avoid(self,d,tilt):
        f=d['front']; l=d['left']; r=d['right']
        if time.time()-self._avoid_start>config.STUCK_TIMEOUT:
            self._stuck_count+=1
            if self._stuck_count>=config.CLAUDE_ESCALATE_AFTER: self._go('STUCK'); return
            self._avoid_start=time.time(); self.motors.reverse_for(config.BACK_UP_TIME); return
        if f>config.DIST_CLEAR: self._stuck_count=0; self._go('ROAM'); return
        self.motors.stop()
        if r>l: self.motors.turn_right_for(config.TURN_TIME_90*0.5); self._last_action='turn_right'
        elif l>r: self.motors.turn_left_for(config.TURN_TIME_90*0.5); self._last_action='turn_left'
        else: self.motors.reverse_for(config.BACK_UP_TIME); self.motors.turn_right_for(config.TURN_TIME_90); self._last_action='back_turn'
        self._upd('stop',f'Avoiding l={l:.0f} r={r:.0f}',d,tilt)

    def _stuck(self,d,tilt):
        self.motors.stop(); self._upd('stuck','Calling Claude...',d,tilt)
        action=self.claude.decide({'state':'STUCK','front_cm':d['front'],'left_cm':d['left'],
            'right_cm':d['right'],'tilt_deg':tilt,'speed':0.0,'stuck_count':self._stuck_count,
            'last_action':self._last_action,'battery_pct':self.adc.battery_pct,'notes':'Cannot find clear path.'})
        if action:
            log.info(f'Claude: {action}')
            cmd=action.get('action','stop'); dur=float(action.get('duration',1.0)); spd=float(action.get('speed',config.SPEED_SLOW))
            {'forward':self.motors.forward_for,'reverse':self.motors.reverse_for,
             'turn_left':self.motors.turn_left_for,'turn_right':self.motors.turn_right_for,
             'stop':lambda d,s=None:(self.motors.stop(),time.sleep(d)),
             'wait':lambda d,s=None:time.sleep(d)}.get(cmd,lambda d,s=None:self.motors.stop())(dur,spd)
            self._last_action=cmd; self._stuck_count=0; self._go('ROAM')
        else: self._go('ESTOP')

    def _dock(self,d,tilt):
        if self.adc.is_charging: self.motors.stop(); return
        f=d['front']
        if f>30: self.motors.forward(0.2); self._upd('think',f'Seeking dock bat={self.adc.battery_pct}%',d,tilt,0.2)
        elif f>8: self.motors.forward(0.12); self._upd('think',f'Docking f={f:.0f}cm',d,tilt,0.12)
        else: self.motors.stop(); self._upd('idle','At dock - no contact',d,tilt)

    def _warn(self,d,tilt):
        self.motors.stop(); self._upd('warn',f'High tilt {tilt:.1f}deg',d,tilt)
        if tilt<config.IMU_TILT_WARN: self._go('ROAM')

    def _go(self,state):
        if state!=self._state:
            log.info(f'  {self._state}->{state}'); self._state=state
            if state=='AVOID': self._avoid_start=time.time()
            if state=='IDLE': self._idle_t=0.0

    def _upd(self,fs,st,d,tilt,spd=0.0):
        self.display.update_state(state=fs,status=st,distances=d,tilt=tilt,speed=spd)
