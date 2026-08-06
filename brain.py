import time,socket,os,board,busio,config,logsetup
from motors import DriveBase,Steering
from sensors import SonarArray,IMU,ADC,Encoders,CurrentMonitor
from display import WillyFace
from claude_client import ClaudeClient
from arm import Arm
from memory_store import MemoryStore
from cloud_ai import CloudAIClient
from smart_home import SmartHomeClient
from voice import VoicePipeline
from vision import ObjectDetector
from retrieval_task import RetrievalTask
from email_client import EmailClient
log=logsetup.setup('brain')

class _SdNotify:
    # Hand-rolled systemd sd_notify (no extra dependency) — sends READY=1 once init passes and
    # periodic WATCHDOG=1 so systemd's WatchdogSec can restart us on a stalled tick loop
    # (§14.2: "Controller/process crash — systemd watchdog — motors disable, arm holds position").
    def __init__(self):
        addr=os.environ.get('NOTIFY_SOCKET'); self._sock=None; self._addr=None
        if addr:
            if addr.startswith('@'): addr='\0'+addr[1:]
            self._sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM); self._addr=addr
    def notify(self,msg):
        if self._sock:
            try: self._sock.sendto(msg.encode(),self._addr)
            except OSError: pass

# I2C addresses expected present per §5.2's authoritative map (+0x70 PCA9685 all-call broadcast).
_EXPECTED_I2C={config.ENCODER_ADDR,config.INA260_SERVO_ADDR,config.STEER_PCA_ADDR,config.ARM_PCA_ADDR,
               config.INA260_PI_ADDR,config.INA260_MOTOR_ADDR,config.ADS_ADDR,config.IMU_ADDR,
               config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR,0x70}

# Battery ladder (§13.2), most severe first. Each entry's threshold is the "below this" boundary;
# recovering to a less severe tier requires climbing BAT_HYSTERESIS_V above that boundary, not
# just crossing it, so a hovering voltage doesn't flap the state back and forth.
_BAT_TIERS=[('shutdown',config.BAT_SHUTDOWN_V),('safe',config.BAT_SAFE_V),
            ('rth',config.BAT_RTH_V),('warn',config.BAT_WARN_V)]
_BAT_SEVERITY={'shutdown':4,'safe':3,'rth':2,'warn':1,'normal':0}

class RoverBrain:
    def __init__(self):
        log.info('Initialising WildWilly v2...')
        self.display=WillyFace(); self.motors=DriveBase(); self.steering=Steering()
        self.sonars=SonarArray(); self.imu=IMU(); self.adc=ADC()
        self.encoders=Encoders(); self.current=CurrentMonitor(); self.arm=Arm()
        self.claude=ClaudeClient(); self._sd=_SdNotify()
        # v2.2 subsystems (docs/WildWilly_Functional_Requirements_Document_v2.2.md) — each stays
        # inert unless its config.ENABLE_* flag is on and its assets/credentials are present; see
        # config.py's v2.2 block and docs/WildWilly_v2.2_Programming_Pass.md for what's open.
        self.memory=MemoryStore(); self.cloud_ai=CloudAIClient(); self.smart_home=SmartHomeClient()
        self.voice=VoicePipeline(memory=self.memory,cloud_ai=self.cloud_ai,display=self.display,
                                  smart_home=self.smart_home)
        self.detector=ObjectDetector()
        self.retrieval=RetrievalTask(self.motors,self.arm,self.detector,display=self.display,voice=self.voice)
        self.email=EmailClient()
        self._state='INIT'; self._stuck_count=0; self._last_action='none'
        self._idle_t=0.0; self._avoid_start=0.0; self._running=False
        self._motion_enabled=False; self._init_fail_reason=''
        self._bat_tier='normal'; self._health={}

    def start(self):
        log.info('Starting subsystems...')
        self.display.start(); self.sonars.start(); self.imu.start(); self.adc.start()
        self.encoders.start(); self.current.start()
        self.steering.center_all(); self.arm.center_all()
        # v2.2: voice/email run their own background threads regardless of self-test result —
        # neither can move the robot on its own (voice queues motion intents for _tick() to
        # gate; email never acts autonomously per FR-2000-004) — but both stay inert no-ops if
        # their ENABLE_* flag is off or credentials/models are missing (see each module).
        self.voice.start(); self.email.start()
        self._running=True
        ok,reason=self._self_test()
        self._motion_enabled=ok; self._init_fail_reason=reason
        if ok:
            self._go('IDLE'); self.display.update_state('idle','WildWilly v2 ready')
            log.info('WildWilly v2 ready.')
        else:
            log.error(f'Startup self-test FAILED — motion disabled: {reason}')
            self.display.update_state('warn',f'SELF-TEST FAILED: {reason}')
        self._sd.notify('READY=1')

    def _self_test(self):
        # FR-100-002/003/004: no motion permitted until this passes (§13.1/§14.2 INIT->IDLE gate).
        problems=[]
        try:
            i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)
            while not i2c.try_lock(): pass
            found=set(i2c.scan()); i2c.unlock()
            missing=_EXPECTED_I2C-found
            if missing: problems.append('I2C missing: '+','.join(hex(a) for a in sorted(missing)))
        except Exception as e:
            problems.append(f'I2C scan failed: {e}')
        time.sleep(0.5)  # let sensor threads take a first reading (current monitor is the slowest, 10Hz)
        if not self.imu.is_healthy: problems.append('IMU not reporting')
        if self.adc.battery_volts<=0: problems.append('battery ADC not reporting')
        if not self.encoders.is_healthy: problems.append('encoders not reporting')
        if not self.current.is_healthy: problems.append('current monitors not reporting')
        if problems:
            log.error('SELF-TEST FAILED: '+'; '.join(problems))
            return False,'; '.join(problems)
        log.info('Self-test passed — all subsystems present.')
        return True,''

    def stop(self):
        log.info('Shutting down...')
        self._running=False; self.motors.brake(); time.sleep(0.2)
        if self.retrieval.active: self.retrieval.abort('shutdown')
        self.voice.stop(); self.email.stop(); self.detector.close()
        self.memory.close()  # FR-1900-011: persist any new/updated memory before power-off
        self.motors.cleanup(); self.sonars.stop(); self.imu.stop(); self.adc.stop()
        self.encoders.stop(); self.current.stop(); self.display.stop()

    def run(self):
        self.start()
        try:
            while self._running: self._tick(); time.sleep(0.05)
        except KeyboardInterrupt: log.info('Stopped.')
        finally: self.stop()

    def _bat_tier_for(self,volts):
        for name,threshold in _BAT_TIERS:
            if volts<threshold: return name
        return 'normal'

    def _update_bat_tier(self,volts):
        raw=self._bat_tier_for(volts)
        if _BAT_SEVERITY[raw]>=_BAT_SEVERITY[self._bat_tier]:
            self._bat_tier=raw  # worsening (or unchanged) — react immediately, no hysteresis
        else:
            cur_threshold=next((t for n,t in _BAT_TIERS if n==self._bat_tier),None)
            if cur_threshold is not None and volts>=cur_threshold+config.BAT_HYSTERESIS_V:
                self._bat_tier=raw  # recovered enough to step down in severity
        return self._bat_tier

    def _check_health(self):
        # FR-1100-001/002: continuous subsystem health monitoring, independent of the one-shot
        # startup self-test in _self_test(). Before this, a sensor dying mid-run (e.g. the IMU
        # thread stalling) went completely unnoticed — is_healthy was only ever read once, at
        # INIT — so a live fault produced no log entry and no operator-visible signal at all.
        checks={'imu':self.imu.is_healthy,'encoders':self.encoders.is_healthy,
                'current':self.current.is_healthy,'battery_adc':self.adc.battery_volts>0}
        for name,healthy in checks.items():
            was=self._health.get(name,True)
            if was and not healthy: log.warning(f'{name} FAULT — stopped reporting')
            elif not was and healthy: log.info(f'{name} recovered')
            self._health[name]=healthy

    def _tick(self):
        self._check_health()
        # FR-000 Prime Directives, in order — Directive 2 (self-test gate) and Directive 4
        # (tilt/physical-limit fault) and Directive 3 (battery ladder) are checked here, each
        # able to pre-empt Directive 6 (voice/retrieval/smart-home/email, everything added in
        # v2.2) mid-task. E-stop (Directive 1) is listed in the doc's priority table too but
        # software has no way to observe it — the hardware-only latching cut has no documented
        # GPIO sense pin, so there is no check for it here, same gap as the baseline pass.
        self._sd.notify('WATCHDOG=1')
        if not self._motion_enabled:
            self._upd('fault',f'SELF-TEST FAILED: {self._init_fail_reason}',
                       {'front':999,'left':999,'right':999},0.0)
            return
        d=self.sonars.distances; tilt=self.imu.tilt; bat_v=self.adc.battery_volts; bat=self.adc.battery_pct
        if tilt>config.IMU_TILT_LIMIT:
            if self.retrieval.active: self.retrieval.abort(f'tilt fault {tilt:.1f}deg')  # FR-1700-007
            if self._state!='TILT_FAULT': log.warning(f'TILT_FAULT tilt={tilt:.1f}'); self._go('TILT_FAULT')
            self.motors.brake(); self._upd('fault',f'TILT {tilt:.1f}deg STOP',d,tilt); return  # FR-1600-003
        if self._state=='TILT_FAULT' and tilt<config.IMU_TILT_WARN: self._go('IDLE')

        tier=self._update_bat_tier(bat_v)
        if tier=='shutdown':
            if self.retrieval.active: self.retrieval.abort(f'battery shutdown {bat_v:.2f}V')  # FR-1700-007
            self.motors.brake(); self._go('SHUTDOWN')
            self.memory.save_all_now()  # best-effort backstop — the guaranteed save already ran at 'rth'
            self._upd('lowbatt',f'BATTERY {bat_v:.2f}V — controlled shutdown, restart required',d,tilt); return
        if tier=='safe':
            if self.retrieval.active: self.retrieval.abort(f'battery safe mode {bat_v:.2f}V')  # FR-1700-007
            self.motors.brake(); self._go('SAFE_MODE')
            self._upd('lowbatt',f'SAFE_MODE bat={bat_v:.2f}V',d,tilt); return  # FR-1600-004
        if tier=='rth':
            if self._state not in('DOCK','TILT_FAULT'):
                if self.retrieval.active: self.retrieval.abort(f'return-to-home {bat_v:.2f}V')  # FR-1700-007
                # FR-200-005/FR-1900-011: the GUARANTEED memory save happens here, at the earlier
                # RTH threshold, while there's still time for a full graceful save — not at the
                # actual SHUTDOWN tier below, which only gets a best-effort backstop attempt.
                self.memory.save_all_now()
                log.info(f'Battery {bat_v:.2f}V -> DOCK (return-to-home)'); self._go('DOCK')
        elif self._state in('SAFE_MODE','SHUTDOWN','DOCK'):
            # Tier no longer forces a battery-driven state. Recovery can skip straight from
            # shutdown/safe to warn/normal in one hysteresis step (bypassing 'rth') — handle
            # release here rather than only on DOCK, or SAFE_MODE/SHUTDOWN would never exit.
            self._go('IDLE')

        if self._state=='DOCK':
            if self.adc.is_charging:
                self.motors.stop(); self._upd('idle',f'Charging {bat}%',d,tilt)
                if bat>=95: self._go('ROAM')
                return

        # FR-000 Directive 6 (v2.2): voice-queued task-level commands are only ever picked up
        # here, after every Directive 1-5 check above has already run this tick and none of
        # them pre-empted (FR-1500-007). Only intake a new task from IDLE — never interrupt an
        # in-progress ROAM/AVOID/etc. state to start one.
        if self._state=='IDLE' and not self.retrieval.active:
            self._drain_voice_commands()

        {'IDLE':self._idle,'ROAM':self._roam,'SLOW':self._slow,'AVOID':self._avoid,
         'STUCK':self._stuck,'DOCK':self._dock,'WARN':self._warn,'RETRIEVE':self._retrieve,
         'TILT_FAULT':lambda d,t:None,'SAFE_MODE':lambda d,t:None,'SHUTDOWN':lambda d,t:None,
        }.get(self._state,lambda d,t:None)(d,tilt)

    def _drain_voice_commands(self):
        try:
            cmd=self.voice.pending_commands.get_nowait()
        except Exception:
            return
        if cmd.get('intent')=='retrieve':
            target=cmd.get('args',{}).get('object','object')
            ok,msg=self.retrieval.start(target)
            if ok: self._go('RETRIEVE')
            log.info(f'Voice-triggered retrieval: {target} ({msg})')
        # Other queued motion intents (forward/reverse/turn_*/stop/go_to) are logged but not
        # wired to an executor this pass — FR-1000 autonomous navigation and free-form manual
        # driving via voice were not part of the v2.2 scope actually implemented here, only the
        # FR-1700 retrieval task was. Put back unhandled so nothing is silently swallowed.
        elif cmd.get('intent'):
            log.info(f'Voice intent "{cmd["intent"]}" received but not wired to an executor.')

    def _retrieve(self,d,tilt):
        self.retrieval.tick(d,tilt)
        if self.retrieval.state in('DONE','FAILED','ABORTED'):
            if self.retrieval.state=='DONE' and self.voice.available: self.voice.speak('All done!')
            self.retrieval.reset(); self._go('IDLE')

    def _idle(self,d,tilt):
        self.motors.stop(); self._idle_t+=0.05
        self._upd('idle',f'Waiting... bat={self.adc.battery_pct}%',d,tilt)
        summaries=self.email.get_new_summaries() if self.email.available else []
        for s in summaries:
            msg=f'New email from {s["from"]}: {s["subject"]}'
            log.info(msg)
            if self.voice.available: self.voice.speak(msg)  # FR-2000-003: surfaced, never acted on
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
        else: self._go('TILT_FAULT')

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
