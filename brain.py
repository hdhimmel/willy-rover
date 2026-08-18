import json,time,socket,os,subprocess,config,logsetup,storage
from logsetup import log_event
if not config.SIMULATE_HARDWARE: import board,busio
from motors import DriveBase,Steering
from sensors import SonarArray,IMU,ADC,Encoders,CurrentMonitor
from display import WillyFace
from ai_provider import CloudAIProvider,build_world_state
from safety import SafetyController,Rejected
from odometry import Odometry
from world_model import WorldModel,Observation,project_point
from mapping import MappingSession
from navigation import Navigator,Mission
from arm import Arm
from memory_store import MemoryStore
from smart_home import SmartHomeClient
from voice import VoicePipeline
from vision import ObjectDetector
from retrieval_task import RetrievalTask
from pursuit_task import PursuitTask
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

# I2C addresses expected present per §5.2's authoritative map. Deliberately excludes 0x70 (PCA9685
# all-call broadcast) — PCA9685.reset() clears MODE1's ALLCALL bit during motors.py/arm.py's
# construction in RoverBrain.__init__, which runs before this self-test, so 0x70 legitimately
# never answers by the time we scan; it was never a real device to begin with.
_EXPECTED_I2C={config.ENCODER_ADDR,config.INA260_SERVO_ADDR,config.STEER_PCA_ADDR,config.ARM_PCA_ADDR,
               config.INA260_PI_ADDR,config.INA260_MOTOR_ADDR,config.ADS_ADDR,config.IMU_ADDR,
               config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR}

# Battery ladder (§13.2), most severe first. Each entry's threshold is the "below this" boundary;
# recovering to a less severe tier requires climbing BAT_HYSTERESIS_V above that boundary, not
# just crossing it, so a hovering voltage doesn't flap the state back and forth.
_BAT_TIERS=[('shutdown',config.BAT_SHUTDOWN_V),('safe',config.BAT_SAFE_V),
            ('rth',config.BAT_RTH_V),('warn',config.BAT_WARN_V)]
_BAT_SEVERITY={'shutdown':4,'safe':3,'rth':2,'warn':1,'normal':0}

# §14/§15: what _stuck() asks the AI for — was ai_provider.py's predecessor claude_client.py's
# module-level SYSTEM constant. _MOTION_SCHEMA is what ai_provider.py structurally validates the
# response against (AIResult.parse_success/action_confidence) — this is NOT the safety gate,
# safety.py::SafetyController.approve_motion() still independently clamps/rejects whatever action
# comes out of this, unchanged.
_MOTION_SYSTEM=("You are the brain of WildWilly, a 6-wheel autonomous rover.\n"
                "Safety: never forward if front<15cm. Stop if tilt>22deg.")
_MOTION_SCHEMA={'action':str,'duration':(int,float),'speed':(int,float)}

class RoverBrain:
    def __init__(self):
        log.info('Initialising WildWilly v2...')
        self.display=WillyFace(); self.motors=DriveBase(); self.steering=Steering()
        self.safety=SafetyController(self.motors)
        self.sonars=SonarArray(); self.imu=IMU(); self.adc=ADC()
        self.encoders=Encoders(); self.current=CurrentMonitor(); self.arm=Arm()
        self.odometry=Odometry(self.encoders)
        self.world_model=WorldModel(self.odometry)  # §9: loads any previously saved map in __init__
        self._sd=_SdNotify()
        # v2.2 subsystems (docs/archive/WildWilly_Functional_Requirements_Document_v2.2.md,
        # superseded by v3.0 but kept for the v2.2-era subsystem notes) — each stays
        # inert unless its config.ENABLE_* flag is on and its assets/credentials are present; see
        # config.py's v2.2 block and docs/WildWilly_v2.2_Programming_Pass.md for what's open.
        # §14: one CloudAIProvider instance now serves both STUCK-state motion decisions (below)
        # and voice.py's free-text fallback — was two separate, un-unified clients hitting the
        # same Anthropic endpoint (ClaudeClient + CloudAIClient).
        self.memory=MemoryStore(); self.cloud_ai=CloudAIProvider(); self.smart_home=SmartHomeClient()
        self.voice=VoicePipeline(memory=self.memory,cloud_ai=self.cloud_ai,display=self.display,
                                  smart_home=self.smart_home)
        self.detector=ObjectDetector()
        self.mapping=MappingSession(self.world_model,self.detector)  # §10
        self.navigator=Navigator(self.safety,self.odometry,self.world_model)  # §11
        self.retrieval=RetrievalTask(self.safety,self.arm,self.detector,display=self.display,voice=self.voice)
        self.pursuit=PursuitTask(self.safety,self.detector,display=self.display,voice=self.voice)  # FR-1000
        self.email=EmailClient()
        self._state='INIT'; self._stuck_count=0; self._last_action='none'; self._manual_action=None
        self._idle_t=0.0; self._avoid_start=0.0; self._avoid_phase=None; self._running=False
        self._motion_enabled=False; self._init_fail_reason=''
        self._bat_tier='normal'; self._health={}; self._fault_since={}
        # 2026-08-08 audit P1 found no systemd WatchdogSec configured, confirmed via `systemctl
        # cat willy-rover.service` on the live unit -- but this repo's own willy-rover.service
        # has specified WatchdogSec=500ms since 2026-08-02 (df24199, predates that audit). The
        # audit was checking the live *installed* unit, not this file, so the likely explanation
        # is a stale deploy (the live systemd unit hadn't picked up the repo's version yet), not
        # a wrong repo file -- unreconciled since 08-08, needs a fresh `systemctl cat
        # willy-rover.service` on the actual Pi to confirm which is currently true. Tick-overrun
        # counting below is pure visibility either way -- it doesn't do anything about an
        # overrun, just makes one observable instead of silent.
        self._last_tick_duration_s=0.0; self._max_tick_duration_s=0.0; self._tick_overrun_count=0
        self._stopped=False
        self._claude_pending=False; self._claude_move_pending=False
        self._stuck_history=[]; self._last_stuck_prompt=''  # §14: caller-owned conversation history
        self._pose_log_t=0.0
        self._shutdown_pending=False; self._shutdown_deadline=0.0  # FR-900-005 voice-commanded shutdown confirm
        self._shutdown_after_stop=False  # set by _begin_shutdown() -- see stop()'s tail

    def start(self):
        log.info('Starting subsystems...')
        # FR-100-002 (initialize I2C bus and connected devices): bringing up every sensor
        # and actuator subsystem is the whole point of start() below.
        self.display.start(); self.sonars.start(); self.imu.start(); self.adc.start()
        self.encoders.start(); self.current.start()
        self.steering.center_all(); self.arm.center_all()
        # v2.2: voice/email run their own background threads regardless of self-test result —
        # neither can move the robot on its own (voice queues motion intents for _tick() to
        # gate; email never acts autonomously per FR-2000-004) — but both stay inert no-ops if
        # their ENABLE_* flag is off or credentials/models are missing (see each module).
        self.voice.start(); self.email.start()
        self._running=True
        # FR-100-003 (run startup self-test): _self_test() below.
        ok,reason=self._self_test()
        # FR-100-004 (prevent motion until startup checks pass): _motion_enabled gates
        # every call into safety.approve_motion() -- see 'motion disabled (self-test
        # failed)' there. Set once here; not touched again afterward (see safety.py's
        # emergency_stop() for why that does NOT also cover FR-300-003's post-E-stop
        # reset requirement, which is a different, unimplemented, gate).
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
        # config.validate() (2026-08-08 audit P2) is deliberately NOT added to `problems` below --
        # a config inconsistency (e.g. today's real BAT_FULL_V vs BAT_WARN_V finding) doesn't mean
        # the robot can't safely hold still, and turning it into a new motion-blocking gate is an
        # owner decision, not something to flip silently. Logged for visibility only.
        config_problems=config.validate()
        if config_problems: log.warning('Config validation found issues (non-blocking): '+'; '.join(config_problems))
        problems=[]
        storage_ok,storage_problems=storage.check_storage({'data':config.WILLY_DATA_ROOT,
            'map':config.WILLY_MAP_ROOT,'memory':config.WILLY_MEMORY_ROOT,'log':config.WILLY_LOG_ROOT})
        if not storage_ok: problems.extend(storage_problems)  # §13: startup availability/permission check
        if config.SIMULATE_HARDWARE:
            pass  # no real bus to scan — every sim class already reports itself healthy below
        else:
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
        # Not just a nicety -- found live 2026-08-08: a second stop() call used to crash on
        # memory.close()'s already-closed sqlite connection (sqlite3.ProgrammingError), which
        # silently skipped every cleanup step after it (world_model.close(), motors.cleanup(),
        # every sensor's stop()). run()'s own `finally: self.stop()` plus any external caller
        # invoking stop() independently (this session's own live smoke test did exactly that)
        # is a real double-call path, not a hypothetical.
        if self._stopped: return
        self._stopped=True
        log.info('Shutting down...')
        self._running=False; self.safety.emergency_stop('shutdown'); time.sleep(0.2)
        if self.retrieval.active: self.retrieval.abort('shutdown')
        if self.mapping.active: self.mapping.abort('shutdown')
        if self.navigator.active: self.navigator.abort('shutdown')
        if self.pursuit.active: self.pursuit.abort('shutdown')
        self.voice.stop(); self.email.stop(); self.detector.close()
        self.memory.close()  # FR-1900-011: persist any new/updated memory before power-off
        self.world_model.close()  # §9/§10: persist rooms/landmarks/objects/routes before power-off
        self.motors.cleanup(); self.sonars.stop(); self.imu.stop(); self.adc.stop()
        self.encoders.stop(); self.current.stop(); self.display.stop()
        if self._shutdown_after_stop:
            # FR-900-005's actual `shutdown -h now` -- deliberately only fires from here, gated on
            # a flag only _begin_shutdown() ever sets, so a plain service restart/SIGTERM/Ctrl-C
            # calling this same stop() never powers off the Pi. voice.stop() above already waited
            # (join timeout=3.0) for the "Shutting down now" line queued in _begin_shutdown() to
            # finish playing before we get here.
            log_event(log,'COMMANDED_SHUTDOWN',severity='warning',subsystem='system',status='shutdown_h_now')
            try:
                subprocess.run(['sudo','shutdown','-h','now'],check=True,timeout=10)
            except Exception as e:
                log.error(f'shutdown -h now failed: {e}')

    def run(self):
        self.start()
        try:
            while self._running:
                t0=time.perf_counter(); self._tick(); self._record_tick_duration(time.perf_counter()-t0)
                time.sleep(0.05)
        except KeyboardInterrupt: log.info('Stopped.')
        finally: self.stop()

    def _record_tick_duration(self,dt):
        self._last_tick_duration_s=dt
        if dt>self._max_tick_duration_s: self._max_tick_duration_s=dt
        if dt>config.TICK_OVERRUN_THRESHOLD_S:
            self._tick_overrun_count+=1
            log_event(log,'TICK_OVERRUN',severity='warning',subsystem='brain',
                      duration_ms=f'{dt*1000:.0f}',threshold_ms=f'{config.TICK_OVERRUN_THRESHOLD_S*1000:.0f}')

    @property
    def tick_duration_ms(self): return self._last_tick_duration_s*1000
    @property
    def max_tick_duration_ms(self): return self._max_tick_duration_s*1000
    @property
    def tick_overrun_count(self): return self._tick_overrun_count

    # FR-200-002/003/004 (undervoltage/warning/critical-cutoff thresholds and shutdown):
    # tiered against calibrated volts (see sensors.py's ADC for FR-200-001's raw-to-volts
    # scaling), with hysteresis in _update_bat_tier() below so tier doesn't chatter at a
    # boundary. 'shutdown' tier below triggers emergency_stop() + SAFE_MODE in the battery
    # check further down this file.
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
        #
        # §4 watchdog (docs/WildWilly_Claude_Fix_Implementation_Plan.md): logging alone isn't
        # enough — a fault sustained past SENSOR_FAULT_GRACE_S must force a safe stopped state.
        # battery_adc is excluded from that escalation: a failed read already defaults
        # battery_volts to 0, which _update_bat_tier() correctly treats as 'shutdown' on its own,
        # so this would be a redundant/less-informative path to the same outcome. imu is the
        # sharpest case — self.imu.tilt returns the last cached reading even after the read
        # thread dies, so a stale tilt can silently pass the TILT_FAULT check below forever
        # without this.
        # FR-300-004 (controller failure halts motion) -- PARTIAL: this covers IMU,
        # encoders, current sensor and battery ADC health, escalating to emergency_stop()
        # below. It does NOT directly check the drive/arm PCA9685 controllers' own I2C
        # reads/writes for failure -- a total bus dropout would likely show up here via
        # the other devices going unhealthy, but an isolated motor-driver disconnect
        # would not be caught by this check on its own.
        checks={'imu':self.imu.is_healthy,'encoders':self.encoders.is_healthy,
                'current':self.current.is_healthy,'battery_adc':self.adc.battery_volts>0}
        now=time.time(); sustained_fault=None
        for name,healthy in checks.items():
            was=self._health.get(name,True)
            if was and not healthy:
                log_event(log,f'{name.upper()}_FAULT',severity='warning',subsystem=name,status='fault')
            elif not was and healthy: log.info(f'{name} recovered'); self._fault_since.pop(name,None)
            self._health[name]=healthy
            if not healthy:
                self._fault_since.setdefault(name,now)
                if name!='battery_adc' and now-self._fault_since[name]>config.SENSOR_FAULT_GRACE_S:
                    sustained_fault=name
        return sustained_fault

    def _abandon_stuck_if_active(self):
        # Called alongside every retrieval.abort() at a Directive 1-4 preemption point (tilt,
        # battery, sensor fault). If STUCK was mid-flight — waiting on Claude, or executing a
        # Claude-issued timed move — this drops that in-flight work so the next STUCK entry
        # starts clean rather than replaying a stale poll/move-pending state.
        if self._state=='STUCK':
            self.cloud_ai.reset_async(); self._claude_pending=False; self._claude_move_pending=False

    def _tick(self):
        if self.voice.stop_requested.is_set():
            # Checked before any Directive gating below — see voice.py's stop_requested docstring.
            # This is the only place that ever clears it, and this is the tick thread, so
            # SafetyController still only ever has one caller.
            self.voice.stop_requested.clear()
            if self.retrieval.active: self.retrieval.abort('voice stop')
            if self.mapping.active: self.mapping.abort('voice stop')
            if self.navigator.active: self.navigator.abort('voice stop')
            if self.pursuit.active: self.pursuit.abort('voice stop')
            self._abandon_stuck_if_active()
            self.safety.emergency_stop('voice stop')
            log.info('Voice-triggered immediate stop')
        if self._shutdown_pending and time.time()>self._shutdown_deadline:
            self._shutdown_pending=False
            log.info('Voice shutdown confirmation timed out — cancelled.')
            if self.voice.available: self.voice.speak("Never mind, I won't shut down.")
        sustained_fault=self._check_health()
        # FR-000 Prime Directives, in order — Directive 2 (self-test gate) and Directive 4
        # (tilt/physical-limit fault) and Directive 3 (battery ladder) are checked here, each
        # able to pre-empt Directive 6 (voice/retrieval/smart-home/email, everything added in
        # v2.2) mid-task. E-stop (Directive 1) is listed in the doc's priority table too but
        # software has no way to observe it — the hardware-only latching cut has no documented
        # GPIO sense pin, so there is no check for it here, same gap as the baseline pass.
        self._sd.notify('WATCHDOG=1')
        pose=self.odometry.update()  # §8: passive dead-reckoning, runs regardless of motion_enabled
                                      # — no motor consequence, just keeps the estimate current for
                                      # logging/diagnostics (nothing consumes it for navigation yet).
        if time.time()-self._pose_log_t>config.POSE_LOG_INTERVAL_S:
            self._pose_log_t=time.time(); log.info(f'pose: {pose}')
        if not self._motion_enabled:
            self._upd('fault',f'SELF-TEST FAILED: {self._init_fail_reason}',
                       {'front':999,'left':999,'right':999},0.0)
            return
        d=self.sonars.distances; tilt=self.imu.tilt; bat_v=self.adc.battery_volts; bat=self.adc.battery_pct
        self.safety.update_context(front_cm=d['front'],tilt_deg=tilt,motion_enabled=self._motion_enabled)
        # §9: passive Layer-1 obstacle feed, same "no motor consequence, just keeps an estimate
        # current" spirit as the odometry pose logging above -- every real (non-timeout) sonar hit
        # this tick becomes a world_model Obstacle point at the robot's current pose+bearing.
        for name,dist_cm in d.items():
            if dist_cm<999.0:
                x,y=project_point(pose,config.SONAR_BEARING_DEG[name],dist_cm/100.0)
                self.world_model.update_observation(Observation('obstacle',x,y,payload={'source':f'sonar_{name}'}))
        # §10: orthogonal to self._state -- see mapping.py's module docstring for why this is a
        # passive tick alongside whatever ROAM/SLOW/AVOID/STUCK is already doing, not its own FSM state.
        if self.mapping.active: self.mapping.tick(d,tilt)

        if sustained_fault:
            # §4 watchdog escalation (see _check_health) — a sensor fault this sustained means we
            # can no longer trust our own safety checks (tilt above all), so stop unconditionally
            # rather than let TILT_FAULT/battery logic below run on possibly-stale inputs.
            if self.retrieval.active: self.retrieval.abort(f'sensor fault: {sustained_fault}')
            if self.mapping.active: self.mapping.abort(f'sensor fault: {sustained_fault}')
            if self.navigator.active: self.navigator.abort(f'sensor fault: {sustained_fault}')
            if self.pursuit.active: self.pursuit.abort(f'sensor fault: {sustained_fault}')
            self._abandon_stuck_if_active()
            self.safety.emergency_stop(f'{sustained_fault} sensor fault')
            if self._state!='SENSOR_FAULT': log.warning(f'  {self._state}->SENSOR_FAULT ({sustained_fault})')
            self._state='SENSOR_FAULT'
            self._upd('fault',f'SENSOR FAULT: {sustained_fault}',d,tilt); return
        if self._state=='SENSOR_FAULT': self._go('IDLE')  # sustained_fault cleared -> recovered

        if tilt>config.IMU_TILT_LIMIT:
            if self.retrieval.active: self.retrieval.abort(f'tilt fault {tilt:.1f}deg')  # FR-1700-007
            if self.mapping.active: self.mapping.abort(f'tilt fault {tilt:.1f}deg')
            if self.navigator.active: self.navigator.abort(f'tilt fault {tilt:.1f}deg')
            if self.pursuit.active: self.pursuit.abort(f'tilt fault {tilt:.1f}deg')
            self._abandon_stuck_if_active()
            if self._state!='TILT_FAULT': log.warning(f'TILT_FAULT tilt={tilt:.1f}'); self._go('TILT_FAULT')
            self.safety.emergency_stop(f'tilt fault {tilt:.1f}deg')
            self._upd('fault',f'TILT {tilt:.1f}deg STOP',d,tilt); return  # FR-1600-003
        if self._state=='TILT_FAULT' and tilt<config.IMU_TILT_WARN: self._go('IDLE')

        tier=self._update_bat_tier(bat_v); self.safety.update_context(bat_tier=tier)
        if tier=='shutdown':
            if self.retrieval.active: self.retrieval.abort(f'battery shutdown {bat_v:.2f}V')  # FR-1700-007
            if self.mapping.active: self.mapping.abort(f'battery shutdown {bat_v:.2f}V')
            if self.navigator.active: self.navigator.abort(f'battery shutdown {bat_v:.2f}V')
            if self.pursuit.active: self.pursuit.abort(f'battery shutdown {bat_v:.2f}V')
            self._abandon_stuck_if_active()
            self.safety.emergency_stop(f'battery shutdown {bat_v:.2f}V')
            if self._state!='SHUTDOWN':
                log_event(log,'LOW_BATTERY',severity='error',subsystem='battery',
                          status='shutdown',volts=f'{bat_v:.2f}')
                # best-effort backstop — the guaranteed save already ran at 'rth'. Guarded like
                # the 'rth' branch below: without this, every tick while voltage stays under the
                # threshold re-runs a full WAL checkpoint to disk, forever (found 2026-08-07 —
                # spun at ~9Hz for over an hour with the base powered off, pinning CPU).
                self._go('SHUTDOWN'); self.memory.save_all_now()
            self._upd('lowbatt',f'BATTERY {bat_v:.2f}V — controlled shutdown, restart required',d,tilt); return
        if tier=='safe':
            if self.retrieval.active: self.retrieval.abort(f'battery safe mode {bat_v:.2f}V')  # FR-1700-007
            if self.mapping.active: self.mapping.abort(f'battery safe mode {bat_v:.2f}V')
            if self.navigator.active: self.navigator.abort(f'battery safe mode {bat_v:.2f}V')
            if self.pursuit.active: self.pursuit.abort(f'battery safe mode {bat_v:.2f}V')
            self._abandon_stuck_if_active()
            if self._state!='SAFE_MODE':
                log_event(log,'LOW_BATTERY',severity='warning',subsystem='battery',
                          status='safe_mode',volts=f'{bat_v:.2f}')
            self.safety.emergency_stop(f'battery safe mode {bat_v:.2f}V'); self._go('SAFE_MODE')
            self._upd('lowbatt',f'SAFE_MODE bat={bat_v:.2f}V',d,tilt); return  # FR-1600-004
        if tier=='rth':
            if self._state not in('DOCK','TILT_FAULT'):
                if self.retrieval.active: self.retrieval.abort(f'return-to-home {bat_v:.2f}V')  # FR-1700-007
                if self.mapping.active: self.mapping.abort(f'return-to-home {bat_v:.2f}V')
                if self.navigator.active: self.navigator.abort(f'return-to-home {bat_v:.2f}V')
                if self.pursuit.active: self.pursuit.abort(f'return-to-home {bat_v:.2f}V')
                self._abandon_stuck_if_active()
                # FR-200-005/FR-1900-011: the GUARANTEED memory save happens here, at the earlier
                # RTH threshold, while there's still time for a full graceful save — not at the
                # actual SHUTDOWN tier below, which only gets a best-effort backstop attempt.
                self.memory.save_all_now()
                log_event(log,'LOW_BATTERY',severity='warning',subsystem='battery',
                          status='return_to_home',volts=f'{bat_v:.2f}')
                self._go('DOCK')
        elif self._state in('SAFE_MODE','SHUTDOWN','DOCK'):
            # Tier no longer forces a battery-driven state. Recovery can skip straight from
            # shutdown/safe to warn/normal in one hysteresis step (bypassing 'rth') — handle
            # release here rather than only on DOCK, or SAFE_MODE/SHUTDOWN would never exit.
            self._go('IDLE')

        self.safety.tick()  # services any in-flight timed move's deadline/obstacle re-check —
                             # must run every tick regardless of which state started the move
                             # (AVOID's reverse/turn or STUCK's Claude-issued action alike).

        if self._state=='DOCK':
            if self.adc.is_charging:
                self.safety.stop(); self._upd('idle',f'Charging {bat}%',d,tilt)
                if bat>=95: self._go('ROAM')
                return

        # FR-000 Directive 6 (v2.2): voice-queued task-level commands are only ever picked up
        # here, after every Directive 1-5 check above has already run this tick and none of
        # them pre-empted (FR-1500-007). Only intake a new task from IDLE — never interrupt an
        # in-progress ROAM/AVOID/etc. state to start one. Exception: mapping.active also opens
        # the gate (§10) -- mapping never touches self._state (see mapping.py's module docstring),
        # so without this a voice-issued "stop mapping" could never be drained while ROAM/SLOW/
        # AVOID legitimately keeps running the whole session.
        if (self._state=='IDLE' or self.mapping.active) and not self.retrieval.active and not self.pursuit.active:
            self._drain_voice_commands()

        {'IDLE':self._idle,'ROAM':self._roam,'SLOW':self._slow,'AVOID':self._avoid,
         'STUCK':self._stuck,'DOCK':self._dock,'WARN':self._warn,'RETRIEVE':self._retrieve,
         'NAVIGATE':self._navigate,'MANUAL':self._manual,'PURSUE':self._pursue,
         'TILT_FAULT':lambda d,t:None,'SAFE_MODE':lambda d,t:None,'SHUTDOWN':lambda d,t:None,
        }.get(self._state,lambda d,t:None)(d,tilt)

    def _drain_voice_commands(self):
        try:
            cmd=self.voice.pending_commands.get_nowait()
        except Exception:
            return
        if self._shutdown_pending:
            # First queued command after a 'shutdown' intent is treated as the yes/no answer to
            # that confirmation, not dispatched normally below -- see the 'shutdown' branch and
            # _tick()'s timeout check for the other two ways out of this pending state.
            self._shutdown_pending=False
            text=cmd.get('text','').lower()
            if cmd.get('intent')=='confirm_receipt' or 'confirm' in text or 'yes' in text:
                self._begin_shutdown()
            else:
                log.info('Voice shutdown declined.')
                if self.voice.available: self.voice.speak("Okay, I won't shut down.")
            return
        if cmd.get('intent')=='retrieve':
            target=cmd.get('args',{}).get('object','object')
            ok,msg=self.retrieval.start(target)
            if ok: self._go('RETRIEVE')
            log.info(f'Voice-triggered retrieval: {target} ({msg})')
        elif cmd.get('intent')=='map':
            ok,msg=self.mapping.start(); log.info(f'Voice-triggered mapping start: {msg}')
        elif cmd.get('intent')=='stop_map':
            ok,msg=self.mapping.stop(); log.info(f'Voice-triggered mapping stop: {msg}')
        elif cmd.get('intent')=='go_to':
            # §11: mission target from whatever shape the local LLM's free-form args happened to
            # produce -- 'room' (name) or 'x'/'y' (raw world coords) are the two shapes navigation.py
            # understands; anything else is reported rather than guessed at (FR-1500-005).
            args=cmd.get('args',{})
            mission=(Mission(room=args['room']) if 'room' in args else
                     Mission(xy=(float(args['x']),float(args['y']))) if 'x' in args and 'y' in args else None)
            if mission is None:
                log.info(f'Voice go_to intent missing room/x,y args: {args}')
            else:
                ok,msg=self.navigator.start(mission)
                if ok: self._go('NAVIGATE')
                log.info(f'Voice-triggered navigation: {mission} ({msg})')
        elif cmd.get('intent') in('forward','reverse','turn_left','turn_right'):
            # Manual nudge driving — timed move through the same safety.request()/tick() deadline
            # mechanism ROAM/AVOID/STUCK already use (§25: nothing bypasses SafetyController).
            # duration/speed default to a short conservative nudge; approve_motion() clamps both
            # to MAX_COMMAND_DURATION_S/SPEED_MAX regardless of what's requested here or by the LLM.
            action=cmd['intent']; args=cmd.get('args',{})
            speed=args.get('speed',config.SPEED_ROAM); duration=args.get('duration',1.5)
            method={'forward':self.safety.forward_for,'reverse':self.safety.reverse_for,
                    'turn_left':self.safety.turn_left_for,'turn_right':self.safety.turn_right_for}[action]
            result=method(duration,speed)
            if isinstance(result,Rejected):
                log.info(f'Voice-triggered {action} rejected: {result.reason}')
                if self.voice.available: self.voice.speak(f"Can't do that — {result.reason}")
            else:
                self._manual_action=action; self._go('MANUAL')
                log.info(f'Voice-triggered manual move: {action} speed={result.speed} duration={result.duration}')
        elif cmd.get('intent') in('come_here','follow'):
            if not self.detector.available:
                if self.voice.available: self.voice.speak("My camera isn't available, I can't find you.")
            else:
                mode='follow' if cmd['intent']=='follow' else 'come_here'
                ok,msg=self.pursuit.start(mode=mode)
                if ok: self._go('PURSUE')
                log.info(f'Voice-triggered pursuit: mode={mode} ({msg})')
        elif cmd.get('intent')=='status':
            bat_v=self.adc.battery_volts; bat_pct=self.adc.battery_pct
            if self.voice.available:
                self.voice.speak(f"I'm currently {self._state.lower()}, battery at {bat_v:.1f} volts, {bat_pct} percent.")
        elif cmd.get('intent')=='battery':
            bat_v=self.adc.battery_volts; bat_pct=self.adc.battery_pct
            if self.voice.available:
                self.voice.speak(f"Battery is at {bat_v:.1f} volts, about {bat_pct} percent.")
        elif cmd.get('intent') in('arm_stow','arm_home'):
            # No calibrated stow/home pose exists yet (§20.6) -- both alias to center_all() as a
            # known-safe placeholder position until real per-joint poses are bench-calibrated.
            self.arm.center_all()
            if self.voice.available: self.voice.speak('Arm centered.')
        elif cmd.get('intent')=='wave':
            self._wave_hello()
        elif cmd.get('intent')=='diagnostics':
            # Deliberately does NOT touch self._motion_enabled either way afterward -- that's the
            # startup gate, and silently flipping it from a possibly-transient on-demand result is
            # an owner decision, not something to do automatically (same reasoning as
            # config.validate() staying non-blocking in _self_test() above). Runs synchronously on
            # the tick thread (~0.5s+, real I2C scan) -- accepted: this only ever runs from IDLE.
            if self.voice.available: self.voice.speak('Running diagnostics now, one moment.')
            ok,reason=self._self_test()
            if self.voice.available:
                self.voice.speak('Everything checks out.' if ok else f'Diagnostics found a problem: {reason}')
        elif cmd.get('intent')=='where_are_you':
            pose=self.world_model.get_robot_pose()
            room=self.world_model.get_room(pose.x,pose.y)
            if self.voice.available:
                self.voice.speak(f"I'm in the {room.name}." if room else "I'm not sure which room I'm in.")
        elif cmd.get('intent')=='what_do_you_see':
            # v1: names detected object classes from the existing CPU-YOLO detector, not a real
            # VLM caption (no Hailo-backed VLM wired into vision.py yet -- see its module docstring).
            if not self.detector.available:
                reply="My camera isn't available right now."
            else:
                classes=sorted({det['class'] for det in self.detector.detect()})
                reply=f"I can see {', '.join(classes)}." if classes else "I don't see anything right now."
            if self.voice.available: self.voice.speak(reply)
        elif cmd.get('intent')=='shutdown':
            if self.voice.available:
                self.voice.speak('Are you sure you want me to shut down? Say confirm to proceed.')
            self._shutdown_pending=True; self._shutdown_deadline=time.time()+15.0
        elif cmd.get('intent'):
            log.info(f'Voice intent "{cmd["intent"]}" received but not wired to an executor.')
            # FR-800-004 principle applied to voice too: a command that can't be carried out
            # should be reported, not silently absorbed -- the LLM's own free-form 'reply' already
            # got spoken by voice.py's _act_on_intent when this was queued, which can sound like
            # confident compliance even though nothing is wired here. This is the corrective.
            if self.voice.available: self.voice.speak("I heard you, but I don't know how to do that yet.")

    def _retrieve(self,d,tilt):
        self.retrieval.tick(d,tilt)
        if self.retrieval.state in('DONE','FAILED','ABORTED'):
            if self.retrieval.state=='DONE' and self.voice.available: self.voice.speak('All done!')
            self.retrieval.reset(); self._go('IDLE')

    def _pursue(self,d,tilt):
        self.pursuit.tick(d,tilt)
        if self.pursuit.state in('DONE','FAILED','ABORTED'):
            if self.pursuit.state=='DONE' and self.voice.available: self.voice.speak('Here I am!')
            self.pursuit.reset(); self._go('IDLE')

    def _wave_hello(self):
        # Fixed primitive sequence, not calibrated IK — same category of gap as
        # retrieval_task.py's _grasp() (§20.6 pending, see its module docstring). wrist_rot
        # oscillates +-300us off center, the same offset magnitude already trusted there, well
        # inside ARM_SERVO_MIN/MAX_US. Blocks the tick thread for ~1.5s (3 back-and-forth swings)
        # -- accepted, same tradeoff already made for _grasp() and the on-demand diagnostics
        # intent: this only ever runs from IDLE.
        if self.voice.available: self.voice.speak('Hello!')
        center=config.ARM_SERVO_CENTER_US
        for _ in range(3):
            self.arm.set_pulse('wrist_rot',center-300); time.sleep(0.25)
            self.arm.set_pulse('wrist_rot',center+300); time.sleep(0.25)
        self.arm.set_pulse('wrist_rot',center)

    def _begin_shutdown(self):
        # FR-900-005: halt motion, stow arm, persist state, then `shutdown -h now`. Reuses
        # stop()'s existing graceful-cleanup sequence (task aborts, memory/world_model
        # persistence, motor/sensor teardown) rather than duplicating it — that's already what
        # run()'s `finally` calls on any exit. The actual OS shutdown call only ever fires from
        # stop()'s tail, gated on _shutdown_after_stop, so this never risks a plain service
        # restart/SIGTERM/Ctrl-C powering off the Pi.
        log.warning('Voice-commanded shutdown confirmed.')
        self.safety.emergency_stop('commanded shutdown')
        self.arm.center_all()  # stow placeholder -- no calibrated stow pose exists yet (§20.6)
        if self.voice.available: self.voice.speak('Shutting down now. Goodbye.')
        self._shutdown_after_stop=True; self._running=False

    def _navigate(self,d,tilt):
        self.navigator.tick(d,tilt)
        if self.navigator.state in('DONE','FAILED','ABORTED'):
            if self.navigator.state=='DONE' and self.voice.available: self.voice.speak("I'm here.")
            self.navigator.reset(); self._go('IDLE')

    def _manual(self,d,tilt):
        # self.safety.tick() (called once centrally, see its own call site above) already
        # services the deadline/obstacle re-check for the in-flight move started in
        # _drain_voice_commands() — this just watches for it finishing and returns to IDLE,
        # same pattern as _retrieve()/_navigate() above.
        if self.safety.timed_move_active:
            self._upd('manual',f'Manual: {self._manual_action}',d,tilt,config.SPEED_ROAM)
        else:
            self._go('IDLE')

    def _idle(self,d,tilt):
        self.safety.stop(); self._idle_t+=0.05
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
        self.safety.forward(config.SPEED_ROAM); self._last_action='forward'
        self._upd('roam',f'Cruising f={f:.0f}cm bat={self.adc.battery_pct}%',d,tilt,config.SPEED_ROAM)

    def _slow(self,d,tilt):
        f=d['front']
        if f>config.DIST_CLEAR: self._go('ROAM'); return
        if f<config.DIST_STOP: self._go('AVOID'); return
        self.safety.forward(config.SPEED_SLOW); self._upd('slow',f'Slowing f={f:.0f}cm',d,tilt,config.SPEED_SLOW)

    def _avoid(self,d,tilt):
        # Non-blocking (§2 of docs/WildWilly_Claude_Fix_Implementation_Plan.md): every branch that
        # used to be a blocking motors.*_for() call now starts a deadline-based timed move via
        # self.safety and returns immediately — self.safety.tick() (called once centrally in
        # _tick()) services the deadline on every subsequent tick, and the timed_move_active guard
        # below keeps this state from issuing a second, overlapping command while one is in flight.
        # The old single-call "back up then turn" combo becomes two ticks via _avoid_phase.
        f=d['front']; l=d['left']; r=d['right']
        if self.safety.timed_move_active:
            self._upd('stop',f'Avoiding l={l:.0f} r={r:.0f}',d,tilt); return
        if self._avoid_phase=='turn_after_reverse':
            self._avoid_phase=None
            self.safety.request('turn_right',None,config.TURN_TIME_90); self._last_action='back_turn'
            self._upd('stop',f'Avoiding l={l:.0f} r={r:.0f}',d,tilt); return
        if time.time()-self._avoid_start>config.STUCK_TIMEOUT:
            self._stuck_count+=1
            if self._stuck_count>=config.CLAUDE_ESCALATE_AFTER: self._go('STUCK'); return
            self._avoid_start=time.time(); self.safety.request('reverse',None,config.BACK_UP_TIME); return
        if f>config.DIST_CLEAR: self._stuck_count=0; self._go('ROAM'); return
        self.safety.stop()
        if r>l: self.safety.request('turn_right',None,config.TURN_TIME_90*0.5); self._last_action='turn_right'
        elif l>r: self.safety.request('turn_left',None,config.TURN_TIME_90*0.5); self._last_action='turn_left'
        else:
            self.safety.request('reverse',None,config.BACK_UP_TIME)
            self._avoid_phase='turn_after_reverse'; self._last_action='back_turn'
        self._upd('stop',f'Avoiding l={l:.0f} r={r:.0f}',d,tilt)

    def _stuck(self,d,tilt):
        # Non-blocking (§2): the AI call runs on CloudAIProvider's own worker thread
        # (ai_provider.py) — this state polls rather than blocks, so _tick() keeps running (and
        # Directive 1-4 checks keep firing) for however long the API call takes.
        if self.safety.timed_move_active:
            self._upd('stuck',f'Executing: {self._last_action}',d,tilt); return
        if self._claude_move_pending:
            # the Claude-issued timed move just finished (checked above) — wrap up this episode
            self._claude_move_pending=False; self._stuck_count=0; self._go('ROAM'); return
        if self._claude_pending:
            result=self.cloud_ai.poll_async()
            if result is None:
                self._upd('stuck','Calling Claude...',d,tilt); return
            self._claude_pending=False
            log.info(f'Claude: parse_success={result.parse_success} '
                     f'intent_confidence={result.intent_confidence} '
                     f'action_confidence={result.action_confidence} payload={result.payload}')  # §15
            payload=result.payload if(result.parse_success and isinstance(result.payload,dict)) else {}
            if result.parse_success:
                # §14: caller-owned history (see ai_provider.py's CloudAIProvider docstring) —
                # only recorded on a successful parse, matching the old claude_client.py's own
                # _call()'s behavior (its except-branch never appended to history either).
                self._stuck_history.append({'role':'user','content':self._last_stuck_prompt})
                self._stuck_history.append({'role':'assistant','content':json.dumps(payload)})
                self._stuck_history=self._stuck_history[-12:]
            cmd=payload.get('action','stop'); dur=float(payload.get('duration',1.0)); spd=float(payload.get('speed',config.SPEED_SLOW))
            self._last_action=cmd
            if cmd in('forward','reverse','turn_left','turn_right','stop','wait'):
                # 'wait' has no dedicated safety action — hold position via 'stop' for the same
                # requested duration, matching the original blocking behavior's intent.
                move_cmd='stop' if cmd=='wait' else cmd
                self.safety.request(move_cmd,spd,dur); self._claude_move_pending=True  # clamped/rejected by approve_motion, not trusted blindly
            else:
                self.safety.stop(); self._stuck_count=0; self._go('ROAM')  # unrecognized action — no hold, matches prior behavior
            return
        self.safety.stop()
        situation=build_world_state(self.world_model,goal='find a clear path to continue roaming',
                                     battery=self.adc.battery_pct,front_cm=d['front'],left_cm=d['left'],
                                     right_cm=d['right'],tilt_deg=tilt,stuck_count=self._stuck_count,
                                     last_action=self._last_action)  # §14: structured world state, not raw sensor values
        self._last_stuck_prompt=(
            f'Situation: {json.dumps(situation)}\nWhat should I do? Respond ONLY with JSON: '
            f'{{"action":"forward"|"reverse"|"turn_left"|"turn_right"|"stop"|"wait","duration":<float>,'
            f'"speed":<0.0-1.0>,"reason":"<60 chars>","confidence":<0.0-1.0, how sure you are>}}')
        self.cloud_ai.request_async(self._last_stuck_prompt,system=_MOTION_SYSTEM,
                                     schema=_MOTION_SCHEMA,history=self._stuck_history)
        self._claude_pending=True
        self._upd('stuck','Calling Claude...',d,tilt)

    def _dock(self,d,tilt):
        if self.adc.is_charging: self.safety.stop(); return
        f=d['front']
        if f>30: self.safety.forward(0.2); self._upd('think',f'Seeking dock bat={self.adc.battery_pct}%',d,tilt,0.2)
        elif f>8: self.safety.forward(0.12); self._upd('think',f'Docking f={f:.0f}cm',d,tilt,0.12)
        else: self.safety.stop(); self._upd('idle','At dock - no contact',d,tilt)

    def _warn(self,d,tilt):
        self.safety.stop(); self._upd('warn',f'High tilt {tilt:.1f}deg',d,tilt)
        if tilt<config.IMU_TILT_WARN: self._go('ROAM')

    def _go(self,state):
        if state!=self._state:
            log.info(f'  {self._state}->{state}'); self._state=state
            if state=='AVOID': self._avoid_start=time.time(); self._avoid_phase=None
            if state=='IDLE': self._idle_t=0.0

    def _upd(self,fs,st,d,tilt,spd=0.0):
        self.display.update_state(state=fs,status=st,distances=d,tilt=tilt,speed=spd)
