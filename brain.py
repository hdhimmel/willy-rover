import json,math,re,time,socket,os,subprocess,threading,logging,config,logsetup,storage,privacy,thermal
from logsetup import log_event
if not config.SIMULATE_HARDWARE: import board,busio
from motors import DriveBase,Steering
from sensors import SonarArray,IMU,ADC,Encoders,CurrentMonitor
from display import WillyFace
from ai_provider import CloudAIProvider,build_world_state,build_stuck_prompt
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
from come_to_me_task import ComeToMeTask
from rotate import Rotation
from steer_override import SteerOverride
import avoidance
import grip
from email_client import EmailClient
from remote_cmd import RemoteCommandServer
from feature_requests import FeatureRequests
from identity import IdentityStore,RECOGNISED,UNCERTAIN,UNKNOWN
from recognition import FaceRecognizer
from witty_pi import WittyPi
hailo_llm=None; HailoIntentModel=None
if config.ENABLE_HAILO_LLM:
    # Tolerated, not required: the Hailo runtime (picamera2.devices, hailo_platform) exists only on
    # the rover. Without it brain.py still imports and runs, with no on-board model -- STUCK falls
    # back to the cloud. Found 2026-10-07 by the first CI run, where this import alone stopped
    # test collection on a machine without picamera2.
    try:
        import hailo_llm
        from hailo_llm import HailoIntentModel
    except ImportError as e:
        logging.getLogger('brain').warning(f'Hailo runtime not importable ({e}); running without the on-board model')
        hailo_llm=None; HailoIntentModel=None
log=logsetup.setup('brain')

# Intents that must never be dropped for age in _drain_voice_commands(). confirm_receipt answers
# retrieval_task.py's AWAIT_CONFIRM state, which can legitimately sit waiting longer than the
# expiry window -- expiring it would stall the task rather than protect anyone from a stale
# command. Everything else is safer discarded than executed out of context.
_NON_EXPIRING_INTENTS=frozenset({'confirm_receipt'})

# Intents _drain_voice_commands() will answer on ANY tick rather than only from IDLE. Everything
# here does nothing but read already-cached state and speak, so it cannot move the rover and
# cannot meaningfully block the tick thread.
#
# The test is "does it block the tick", NOT "does it only speak". Two intents that speak rather
# than move are deliberately excluded:
#   'diagnostics'     runs a real I2C scan synchronously, ~0.5s+. The branch's own comment
#                     accepts that cost specifically because it only ever runs from IDLE.
#                     Draining it mid-drive stalls obstacle checks for half a second at speed.
#   'what_do_you_see' runs a detector inference synchronously -- cheap on the Hailo, several
#                     hundred ms on the CPU-YOLO fallback, which is precisely when the rover is
#                     already under strain.
# Both belong here once they are made non-blocking, and not before.
_SPEECH_ONLY_INTENTS=frozenset({'status','battery','where_are_you','what_doing','privacy_on'})
# Command sources that are not someone in the room speaking: they never answer a pending
# yes/no ask (the shutdown confirmation, the roam permission). See answers_ask.
_NON_SPOKEN_SOURCES=frozenset({'remote','email'})
# What an email may queue: everything a spoken command could, through the same gating.
_EMAIL_QUEUEABLE=frozenset({'forward','reverse','turn_left','turn_right','go_to','retrieve','map',
    'stop_map','status','battery','arm_stow','arm_home','wave','come_here','come_to_me','rotate','steer','follow','diagnostics',
    'where_are_you','what_do_you_see','what_doing','privacy_on','privacy_off','name_room','mark_stairs','shutdown','demo_replay','roam','check_logs'})

# Intents answered while the startup self-test is failing (2026-10-01). _tick() returns early in
# that state, before either drain pass, so Willie heard every command and answered none -- with
# the base off he could not even say why he was not moving. The rover is parked with motion
# disabled, so blocking the tick is harmless here: 'diagnostics' (the self-test, ~0.5 s) is
# allowed, as is 'shutdown'. Anything else is refused out loud with the self-test reason.
_SELFTEST_FAULT_INTENTS=_SPEECH_ONLY_INTENTS|{'diagnostics','shutdown'}

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
# 0x27 REMOVED 2026-09-30. The MCP23017 is off the bus -- encoder decode moved to Pico A over
# uart4-pi5 (§4.7) and the expander is physically gone. Leaving it here made a correctly built
# rover fail its own self-test: missing={0x27} -> critical -> _motion_enabled stayed false, so
# Willie could not move no matter what else was right. Verified against a live scan the same day,
# which returns exactly these ten: 0x40 0x42 0x43 0x44 0x45 0x48 0x4a 0x51 0x60 0x61.
_EXPECTED_I2C={config.INA260_5V_ADDR,config.STEER_PCA_ADDR,config.ARM_PCA_ADDR,
               config.INA260_BUS_12V_ADDR,config.INA260_ARM_6V_ADDR,config.ADS_ADDR,config.IMU_ADDR,
               config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR}
# Witty Pi 5 only joins the expected-device set once it's actually installed and enabled --
# adding it unconditionally when the hardware is absent would make the self-test report a
# real device as missing every single run. The gate is still correct; the hardware IS now
# fitted and ENABLE_WITTY_PI is True (config.py), so 0x51 is expected. The self-test now looks
# for TEN devices: nine plus the Witty Pi. It was eleven until 2026-09-30, when 0x27 left the
# set with the MCP23017 it named. (Comment corrected 2026-09-11 -- it still said the hardware
# did not exist on this unit.)
if config.ENABLE_WITTY_PI: _EXPECTED_I2C.add(config.WITTY_PI_ADDR)

# FULL SCAN ONCE, THEN PROBE ONLY WHAT IS MISSING (2026-10-01). Blinka's scan() probes every
# address with an SMBus quick-write -- a zero-length write. The BNO085 (0x4A) logs each one as
# SHTP error 2 "host write too short" and later sends the accumulated list as a channel-0 Error
# List packet, which adafruit_bno08x mis-parses as sensor data: 'Unprocessable Batch bytes'
# while the list is short, then KeyError: 12 once it ends in 0x0C ("list truncated"). With the
# base off the self-test retried every SELFTEST_RETRY_S, so the scan knocked the IMU over every
# 30 s and the RST recovery picked it back up. A device seen once is not re-probed: each one
# already has its own health check (IMU, ADC, encoders, current, motors) for dropping out later.
# THE IMU IS NEVER PROBED (2026-10-02). The one full scan kept at startup still quick-wrote
# 0x4A, and on the first boot with this code the resulting SHTP error list stalled the BNO085
# long enough to latch SENSOR_FAULT -- every boot would have waited for an operator reset. The
# IMU's presence is already proven by its driver constructing, and its health is the
# self-test's separate 'IMU not reporting' check, so probing it adds nothing but the fault.
def _i2c_present(seen,probe):
    """seen: expected addresses already found (None before the first run). probe(addr): True if
    addr answers. Probes only expected addresses not yet seen, never the IMU, never a full scan.
    Returns the updated set of expected addresses present."""
    seen=set(seen or ())|{config.IMU_ADDR}
    return seen|{a for a in _EXPECTED_I2C-seen if probe(a)}

def _i2c_probe(addr):
    # Same two-step probe as Blinka's generic_linux scan(), for one address.
    from Adafruit_PureIO.smbus import SMBus
    with SMBus(1) as bus:
        try: bus.write_quick(addr); return True
        except OSError:
            try: bus.read_byte(addr); return True
            except OSError: return False

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

# Found 2026-08-21: constructing this many I2C devices back-to-back at startup with zero
# spacing can draw enough simultaneous inrush current to transiently sag the bus below what a
# slow, one-at-a-time i2cdetect probe ever sees -- a device's OWN construction (e.g.
# MotorKit's first PWM write) then hits 'OSError: [Errno 121] Remote I/O error' even though the
# bus is otherwise healthy moments later. Not a substitute for real hardware margin -- just
# resilience against a demonstrated transient at process startup specifically.
#
# Widened 2026-09-07 to catch ValueError as well, and the window lengthened from 4x0.3s to
# 8x0.75s. The original guard caught OSError only, which covers the Errno 121 transient above
# but NOT the case that actually crash-looped the service: Adafruit's
# I2CDevice.__probe_for_device() raises **ValueError** ("No I2C device at address: 0x60") when
# nothing ACKs, so "the isolated rail has not come up yet" propagated on the first attempt with
# zero retries -- the exact scenario this function exists for, and it never engaged. The longer
# window is for rail settling, which is seconds, not the sub-second bus transient.
#
# ValueError is caught broadly rather than matched on message text, which would be fragile
# against a library string. The cost is that a genuine ValueError bug inside a constructor is
# retried before surfacing; unrelated exception types still propagate on the first attempt.
# States in which the tick's dispatch commands motion. A voice "stop" must leave these, or the
# same tick's dispatch drives again -- see the stop_requested branch of _tick().
_MOTION_STATES=('ROAM','SLOW','AVOID','STUCK','DOCK','WAVE','RETRIEVE','NAVIGATE','MANUAL','PURSUE','COME_TO_ME','ROTATE')

def _sonar_returns(d):
    """The sonar readings that are echoes off something real, for the world model.

    NOT `< 999`. That was the timeout sentinel the Pico cutover retired (S-9). Pico B's path
    reports "no echo, nothing in range" as SONAR_MAX_CM -- a CLEAR path -- and "no fresh
    frame" as 0.0, which means unknown and makes safety STOP. Both are below 999, so until
    2026-10-01 an open room plotted a phantom wall SONAR_MAX_CM out on every tick, and a
    stale link plotted one on top of the rover. Only a reading strictly inside
    (0, SONAR_MAX_CM) is a return."""
    return {n:cm for n,cm in d.items() if 0.0<cm<config.SONAR_MAX_CM}

def _init_device(ctor,name,attempts=8,delay_s=0.75):
    for attempt in range(attempts):
        try: return ctor()
        except (OSError,ValueError) as e:
            if attempt==attempts-1: raise
            log.warning(f'{name} init failed ({e}), retrying in {delay_s}s (attempt {attempt+1}/{attempts})')
            time.sleep(delay_s)

def _bus_volts(current):
    """+12V bus voltage for BATTERY decisions: 0.0 when the 0x45 reading is stale, i.e. a dead
    monitor counts as a dead bus. Then battery_volts falls back to the divider, which the
    cross-check flag can veto -- instead of the tiers reading a frozen last-good bus value
    (outside review 2026-10-08). Plain rail() for monitors without fresh_volts (test fakes)."""
    fresh=getattr(current,'fresh_volts',None)
    if fresh is None: return current.rail('bus_12v')['voltage_v']
    v=fresh('bus_12v')
    return 0.0 if v is None else v

class RoverBrain:
    def __init__(self):
        log.info('Initialising WildWilly v2...')
        self.display=_init_device(WillyFace,'display')
        try:
            self.motors=_init_device(DriveBase,'motors')
        except (OSError,ValueError) as e:
            # Pi powered without the 12 V supply: the motor drivers do not answer. Start without
            # them (motion stays disabled by the self-test) instead of crash-looping (2026-10-08).
            log.error(f'Motor drivers unreachable ({e}) -- starting with the drive OFFLINE; no motion')
            self.motors=DriveBase(offline=True)
        self.steering=_init_device(Steering,'steering')
        self.safety=SafetyController(self.motors,steering=self.steering)
        self.sonars=_init_device(SonarArray,'sonars')
        # FR-1000-002 / FR-1200-005: the SEN0628 multi-zone ToF. It was fitted but never
        # constructed -- sensors.py had a slot "set by brain.py" that nothing set (2026-10-02).
        if config.ENABLE_TOF and not config.SIMULATE_HARDWARE:
            try:
                from tof import ToFSensor,SerialFrameSource,BackgroundFrames
                self.sonars.tof=ToFSensor(source=BackgroundFrames(SerialFrameSource()))
                if self.sonars.tof.profile is None:
                    log.warning('ToF fitted but no floor profile -- it reports nothing until '
                                'scripts/calibrate_tof_floor.py is run on clear floor')
            except Exception:
                log.warning('ToF could not start; sonar alone',exc_info=True)
        # REAR ToF (2026-10-10): second SEN0628 facing backward, mounted upside down (config).
        if config.ENABLE_TOF_REAR and not config.SIMULATE_HARDWARE:
            try:
                from tof import ToFSensor,SerialFrameSource,BackgroundFrames
                self.sonars.tof_rear=ToFSensor(
                    source=BackgroundFrames(SerialFrameSource(config.TOF_REAR_PORT)),
                    profile_path=os.path.join(config.WILLY_MEMORY_ROOT,config.TOF_REAR_FLOOR_PROFILE_PATH),
                    floor_rows=config.TOF_REAR_FLOOR_ROWS,left_columns=config.TOF_REAR_LEFT_COLUMNS,
                    drop_rows=config.TOF_REAR_DROP_ROWS,name='rear')
                if self.sonars.tof_rear.profile is None:
                    log.warning('Rear ToF fitted but no floor profile -- it reports nothing until '
                                'scripts/calibrate_tof_floor.py --rear is run on clear floor')
            except Exception:
                log.warning('Rear ToF could not start; reversing without it',exc_info=True)
        # The BNO085's RST is on Pico B, whose link SonarArray owns (§4.7 consequence 1).
        self.imu=_init_device(lambda:IMU(reset=self.sonars.reset_imu),'imu')
        self.adc=_init_device(ADC,'adc')
        self.encoders=_init_device(Encoders,'encoders')
        try: self.motors.attach_encoders(self.encoders)   # FR-500-004 closed-loop wheel speed
        except Exception: log.warning('Wheel speed control: could not attach encoders',exc_info=True)
        self.current=_init_device(CurrentMonitor,'current')
        # Battery voltage from the +12V bus monitor when the bus is live (see ADC.battery_volts).
        self.adc.bus_source=lambda: _bus_volts(self.current)
        self.arm=_init_device(Arm,'arm')
        self.odometry=Odometry(self.encoders,
                               heading_source=lambda: self.imu.heading if self.imu.is_healthy else None)
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
        self.hailo_llm=HailoIntentModel() if (config.ENABLE_HAILO_LLM and HailoIntentModel) else None  # Primary on-device reasoning (STUCK state)
        # Brake before every Hailo generation: it freezes every thread for seconds (hailo_llm.py).
        if hailo_llm is not None: hailo_llm.set_before_generate(self._brake_before_hailo)
        self.voice=VoicePipeline(memory=self.memory,cloud_ai=self.cloud_ai,display=self.display,
                                  smart_home=self.smart_home)
        self.detector=ObjectDetector()
        self.mapping=MappingSession(self.world_model,self.detector)  # §10
        self.navigator=Navigator(self.safety,self.odometry,self.world_model,  # §11
                                 sonars=self.sonars,detector=self.detector,say=self._say,
                                 arm=self.arm)   # arm: the knock at a shut door (knock.py)
        self.retrieval=RetrievalTask(self.safety,self.arm,self.detector,display=self.display,voice=self.voice,
                                     feedback=lambda: grip.read_feedback(self.adc,self.current))
        self.pursuit=PursuitTask(self.safety,self.detector,display=self.display,voice=self.voice)  # FR-1000
        # Rotation mode (rotate.py, live-verified 2026-10-07). Drives THROUGH SafetyController
        # (set_wheels is approved like a turn). Front camera only here: the rear camera is not
        # opened by the service, and opening a USB camera on the tick thread would stall it.
        # Rear camera (2026-10-10): rotation was built to use it and was never given it.
        from vision import RearCamera
        self.rear_cam=RearCamera()
        self._rear_watch=False; self._rear_block=False; self._rear_block_t=0.0; self._rear_thread_on=True
        threading.Thread(target=self._rear_watch_loop,daemon=True).start()
        self.rotation=Rotation(self.steering,self.safety,self.imu,lambda: self.sonars.distances,
                               camera_grab=self.detector.capture_frame,encoders=self.encoders,
                               rear_grab=self.rear_cam.grab,
                               say=self._say)
        self.steer_override=SteerOverride(self.steering)   # FR-600-004
        self._after_rotate='IDLE'
        self.come_to_me=ComeToMeTask(self.navigator,self.pursuit,self.world_model,self.detector,
                                     say=self._say)  # FR-1000-006
        self.email=EmailClient()
        self.remote=RemoteCommandServer(self.voice)  # HA / Google Home in, see remote_cmd.py
        self.email.set_command_handler(self._email_command)   # FR-2000-012
        self.feature_requests=FeatureRequests(self.cloud_ai,self.email)   # FR-2200
        self.email.add_approval_handler(self.feature_requests.try_approve)
        # FR-2100 person recognition: store/matcher + embedding source, both inert if disabled.
        self.identity=IdentityStore()
        self.faces=FaceRecognizer(self.detector.capture_frame)
        self.email.add_approval_handler(self._approve_enrolment)
        self._face_unknown_run=0; self._face_asked_t=0.0; self._face_asking=False
        self.witty=WittyPi()
        self._state='INIT'; self._stuck_count=0; self._last_action='none'; self._manual_action=None
        self._idle_t=0.0; self._avoid_start=0.0; self._avoid_phase=None; self._running=False
        self._motion_enabled=False; self._init_fail_reason=''; self._selftest_critical=[]
        # Self-test override (owner request 2026-08-24). While motion is gated off by a failed
        # startup self-test, retry the test periodically; after SELFTEST_OVERRIDE_AFTER
        # consecutive failures for the SAME reason, offer an on-screen button letting the
        # operator accept the risk and enable motion anyway. In-memory only -- a restart clears
        # it, deliberately, so an override can never outlive the session it was granted in.
        # Scoped to the startup self-test only: TILT/STALL/SENSOR faults keep their own reset
        # gate and are NOT overridable, since those represent live physical danger rather than
        # a missing diagnostic device.
        self._selftest_retry_t=0.0; self._selftest_fail_count=0; self._i2c_seen=None
        self._selftest_overridden=False
        # STUCK help-photo throttling (owner request 2026-08-24) -- see _send_stuck_alert().
        self._stuck_alert_t=0.0; self._stuck_alert_count=0
        # Motor-power-loss detection (2026-08-24) -- see _check_motor_rail().
        self._motor_rail_low_since=None; self._motor_rail_lost=False
        # Encoder-rail (R5) warning, 2026-10-01 -- see _check_r5(). Warn only, never a stop.
        self._r5_low_since=None; self._r5_low=False
        self._bat_halt_since=None   # battery-tier halt confirmation clock, see _battery_halt()
        self.thermal=thermal.ThermalMonitor()   # M-009, polled from _tick(), see _thermal_tick()
        self._fan_warned=False
        self._retention_t=0.0       # FR-1800-004: last retention sweep, see _retention_sweep()
        self._arm_over_since=None   # FR-700-001: arm over-current clock, see _check_arm_current()
        self._oc_since={}           # FR-200-002: per-rail overcurrent clocks, see _check_overcurrent()
        self._sonar_failed={}       # FR-800-004: channels currently reported failed
        self._sonar_edge={}         # FR-800-004: channel -> when its state started to differ
        self._uncmd_since=None; self._uncmd_reported=False  # FR-500-003 inverse case
        self._demo=None             # FR-1900-001: demonstration being recorded, see _demo_sample()
        self._bat_warned=False      # FR-200-003: warn tier announced once per descent
        # Battery sense cross-check (2026-09-15) -- see _check_battery_crosscheck().
        self._bat_xcheck_since=None; self._bat_xcheck_flagged=False
        self._bat_tier='normal'; self._health={}; self._fault_since={}; self._stall_since={}
        self._wave_step=0; self._wave_deadline=None
        # RESOLVED 2026-09-07: it was a stale deploy, exactly as guessed below. The 2026-08-08
        # audit P1 found no systemd WatchdogSec configured, confirmed via `systemctl cat` on the
        # live unit -- while this repo's own willy-rover.service has specified WatchdogSec=500ms
        # since 2026-08-02 (df24199, predating that audit). Checked on the rover 2026-09-07:
        # /etc/systemd/system/willy-rover.service was byte-identical to the repo copy EXCEPT for
        # the missing WatchdogSec line, and `systemctl show -p WatchdogUSec` returned 0. So the
        # repo file was right and simply had never been installed, for over a month.
        #
        # Consequence worth holding onto: for that whole period the watchdog described below was
        # NOT armed. Every "systemd will kill us mid-tick" risk in this file and in FRD G-5 was
        # real in the code and dormant in deployment -- including the f18af62 blocking call noted
        # further down. sd_notify's WATCHDOG=1 was a no-op, so a genuinely wedged tick loop was
        # never restarted either; the Witty Pi HAT's own watchdog was the only live backstop.
        # Installing the repo unit on 2026-09-07 to arm it was a mistake and was reverted the
        # same hour: the service was SIGABRT'd ~500ms after every start, four times in twenty
        # seconds, never reaching its own first log line. Cause: this unit is Type=simple, so
        # NotifyAccess defaults to `none` and systemd DISCARDS every sd_notify message the
        # process sends -- the WATCHDOG=1 below was never received by anything, and no heartbeat
        # rate could have satisfied the deadline. WatchdogSec=500ms is now commented out in
        # willy-rover.service with the full precondition list; the rover is back on the unit it
        # had before. So the watchdog is STILL not armed, and the figures below still describe
        # a mechanism that has never once run in this deployment.
        #
        # FRD v3.1 G-5 (2026-08-18) sharpened the risk this WatchdogSec value actually poses:
        # notify() below is called once per tick, so a single _tick() call blocking anywhere near
        # 500ms gets the whole process killed by systemd *mid-tick*, before this tick's own
        # overrun-logging (which only runs after _tick() returns, in run()'s loop) ever executes.
        # The two known culprits that could push a tick that long -- retrieval_task.py's _grasp()
        # and this file's wave-hello gesture, both previously blocking via time.sleep() -- were
        # both converted to non-blocking, tick-serviced step machines the same day (see
        # retrieval_task.py and _wave()/_start_wave() below). This closes the *known cause*,
        # not the risk structurally -- nothing stops a future blocking call from reintroducing
        # it, and this reconciliation itself is unverified on live hardware.
        #
        # A future blocking call did exactly that. f18af62 (2026-09-01) added a synchronous
        # Hailo LLM generate_all() to _stuck(), on this thread, while the paragraph above still
        # read "no other per-tick blocking call is known to remain" -- so the claim was false
        # for six days and nothing flagged it. Moved to the async worker-thread path 2026-09-07
        # (see _stuck()). Treat "no blocking call remains" as a claim to re-verify whenever an
        # AI provider or task is added, not as a standing fact. Tick-overrun counting below is pure visibility regardless --
        # it doesn't do anything about an overrun, just makes one observable instead of silent.
        self._last_tick_duration_s=0.0; self._max_tick_duration_s=0.0; self._tick_overrun_count=0
        self._stopped=False
        self._claude_pending=False; self._claude_move_pending=False
        self._hailo_pending=False  # 2026-09-07: Hailo LLM is polled, not called inline
        self._stuck_history=[]; self._last_stuck_prompt=''  # §14: caller-owned conversation history
        self._pose_log_t=0.0
        self._shutdown_pending=False; self._shutdown_deadline=0.0  # FR-900-005 voice-commanded shutdown confirm
        self._fix_ask_pending=False; self._fix_ask_deadline=0.0    # "check your logs" -> "ask for a fix?"
        # Roam permission (owner decision 2026-09-09). ENABLE_AUTONOMOUS_ROAM means "allowed to
        # ask"; this grant is what actually opens the gate, and it starts false at EVERY boot --
        # unattended roaming is never the state Willie powers up in. See _roam_allowed().
        self._roam_permission=False
        self._roam_ask_pending=False; self._roam_ask_deadline=0.0
        self._roam_ask_next=0.0     # earliest time a new ask may open, after a decline/lapse
        self._shutdown_after_stop=False  # set by _begin_shutdown() -- see stop()'s tail

    def start(self):
        log.info('Starting subsystems...')
        # FR-100-002 (initialize I2C bus and connected devices): bringing up every sensor
        # and actuator subsystem is the whole point of start() below.
        self.display.start(); self.sonars.start(); self.imu.start(); self.adc.start()
        self.encoders.start(); self.current.start()
        self.steering.center_all()
        # The ARM IS NOT CENTRED AT STARTUP (2026-10-02, seen on the rover). centre_all() jumped
        # the shoulder from rest to 1500 us in one step -- the slam config.py forbids -- and the
        # idle release dropped it again 10 s later, on every boot. The arm stays as it is
        # (released) until something asks it to move, and every arm motion steps the shoulder.
        # v2.2: voice/email run their own background threads regardless of self-test result —
        # neither can move the robot on its own (voice queues motion intents for _tick() to
        # gate; email never acts autonomously per FR-2000-004) — but both stay inert no-ops if
        # their ENABLE_* flag is off or credentials/models are missing (see each module).
        self.voice.start(); self.email.start(); self.remote.start(); self.feature_requests.start()
        self.faces.start()
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
            self._go('IDLE')
            # main.py sets this when it force-enabled WILLY_SIMULATE because no I2C device
            # acked at startup (bus physically offline) -- distinct from a developer
            # deliberately running under WILLY_SIMULATE=1, which needs no special-casing here.
            # Self-test genuinely passes either way (simulated sensors always report healthy),
            # so this is purely an operator-visible label, not a different code path.
            if os.environ.get('WILLY_I2C_FORCED_SIMULATE'):
                self.display.update_state('idle','I2C OFFLINE — degraded mode, restart to recheck')
                log.warning('WildWilly v2 ready, but I2C was offline at startup — running '
                            'forced-simulate/degraded. Restart the service once hardware is '
                            'reconnected.')
            else:
                self.display.update_state('idle','WildWilly v2 ready')
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
        # PROBLEMS ARE CLASSIFIED, ADDED 2026-09-17. `problems` used to be one flat list, and
        # brain.py offered the operator an override for ANY entry in it after
        # SELFTEST_OVERRIDE_AFTER consecutive failures -- which meant "IMU not reporting" was
        # exactly as overrideable as a log-directory permission warning. An override that
        # re-enables motion on a rover with no tilt sensing, no wheel feedback, no current
        # monitoring or no battery sensing is not a judgement call an operator should be offered.
        #
        # SAFETY-CRITICAL -> never overrideable. Anything the safety path reads: the I2C bus
        # itself (every expected address is a motor controller, a sensor, or a power monitor),
        # the IMU (tilt/stair detection), the battery ADC (the whole shutdown ladder), the
        # encoders (stall detection) and the current monitors (rail-loss detection).
        #
        # NON-CRITICAL -> overrideable. Storage: it costs logging, map persistence and memory
        # durability, which is real damage to the record but not to anyone's safety. Willy can
        # be driven home with a read-only data root.
        problems=[]; critical=[]
        storage_ok,storage_problems=storage.check_storage({'data':config.WILLY_DATA_ROOT,
            'map':config.WILLY_MAP_ROOT,'memory':config.WILLY_MEMORY_ROOT,'log':config.WILLY_LOG_ROOT})
        if not storage_ok: problems.extend(storage_problems)  # §13: startup availability/permission check
        if config.SIMULATE_HARDWARE:
            pass  # no real bus to scan — every sim class already reports itself healthy below
        else:
            try:
                self._i2c_seen=_i2c_present(self._i2c_seen,_i2c_probe)
                missing=_EXPECTED_I2C-self._i2c_seen
                if missing: critical.append('I2C missing: '+','.join(hex(a) for a in sorted(missing)))
            except Exception as e:
                critical.append(f'I2C scan failed: {e}')
        # Let the sensor threads take a first reading (current monitor is the slowest, 10 Hz) --
        # at STARTUP only. Retries run on the tick thread every SELFTEST_RETRY_S, and the threads
        # are long since running, so the sleep there was pure stall: 288 TICK_OVERRUNs of
        # ~501 ms on 2026-10-01/02, found by Willie's own feature request
        # (docs/feature-requests/2026-10-02-investigate-brain-control-loop-tick-overruns.md).
        if not getattr(self,'_selftest_settled',False):
            time.sleep(0.5); self._selftest_settled=True
        if not self.imu.is_healthy: critical.append('IMU not reporting')
        if self.adc.battery_volts<=0: critical.append('battery ADC not reporting')
        if not self.encoders.is_healthy: critical.append('encoders not reporting')
        # FR-100-003 (2026-10-08): Pico A also reports the encoder supply rail R5 -- the rail
        # whose loss killed every encoder on 2026-08-25. Watched every tick already
        # (_check_r5); now the boot gate refuses motion on it too, naming the rail.
        elif getattr(self.encoders,'r5_low',False): critical.append('encoder supply rail R5 low')
        if not self.current.is_healthy: critical.append('current monitors not reporting')
        if not self.sonars.is_healthy: critical.append('sonar link (Pico B) not reporting')
        if not self.motors.is_healthy: critical.append('motor drivers not responding')
        # FR-100-002: tell "base power off" apart from real faults. With the base switched off
        # the +12V bus monitor reads ~0V and exactly the base-fed subsystems drop out (battery
        # divider, Pico A on R5). 2026-10-01 that read as two unrelated sensor failures.
        base_fed={'battery ADC not reporting','encoders not reporting'}
        if critical and set(critical)<=base_fed|{'motor drivers not responding'}:
            try: bus=self.current.rail('bus_12v')['voltage_v']
            except Exception: bus=None
            if bus is not None and bus<config.MOTOR_RAIL_MIN_V:
                critical=[f'base power appears OFF (12V bus {bus:.1f}V) -- '+'; '.join(critical)]
        # Recorded on self so the override offer can consult it. Set on EVERY self-test run,
        # pass or fail, so a retry that clears the critical fault also clears the block.
        self._selftest_critical=list(critical)
        all_problems=critical+problems
        if all_problems:
            log.error('SELF-TEST FAILED: '+'; '.join(all_problems)
                      +(f'  [SAFETY-CRITICAL, override refused: {"; ".join(critical)}]' if critical else ''))
            return False,'; '.join(all_problems)
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
        if self.rotation.active: self.rotation.abort('shutdown')
        self.faces.stop(); self.feature_requests.stop(); self.remote.stop(); self.voice.stop(); self.email.stop(); self.detector.close()
        self._rear_thread_on=False
        try: self.rear_cam.close()
        except Exception: pass
        try:
            import hailo_server; hailo_server.close_client()   # FR-1400-006: release the chip
        except Exception: log.warning('Hailo server close failed',exc_info=True)
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
        # battery_adc WAS excluded from that escalation until 2026-08-24, on the reasoning that a
        # failed read defaulted battery_volts to 0 and _update_bat_tier() would treat that as
        # 'shutdown' anyway. That reasoning was wrong in practice: it made a bus glitch
        # indistinguishable from a flat pack and produced a SILENT power-off with no fault state
        # and no low-battery warning — which fired for real when a loose I2C wire took the bus
        # down. sensors.py::ADC now holds its last good value and reports is_healthy=False
        # instead, so staleness escalates here like every other sensor: grace period, visible
        # fault, operator reset. imu is the
        # sharpest case — self.imu.tilt returns the last cached reading even after the read
        # thread dies, so a stale tilt can silently pass the TILT_FAULT check below forever
        # without this.
        # FR-300-004 (controller failure halts motion) -- PARTIAL: this covers IMU,
        # encoders, current sensor and battery ADC health, escalating to emergency_stop()
        # below. It does NOT directly check the drive/arm PCA9685 controllers' own I2C
        # reads/writes for failure -- a total bus dropout would likely show up here via
        # the other devices going unhealthy, but an isolated motor-driver disconnect
        # would not be caught by this check on its own.
        # 'sonars' and 'motors' added 2026-10-01 (FRD gap audit). A stale Pico B link reads 0.0
        # on every channel -- fail-safe for forward motion, but with no fault raised ROAM fell
        # into AVOID and reversed blind on a loop. 'motors' is DriveBase's ramp thread: one I2C
        # error used to kill it silently, after which stop() did nothing.
        checks={'imu':self.imu.is_healthy,'encoders':self.encoders.is_healthy,
                'current':self.current.is_healthy,'battery_adc':self.adc.is_healthy,
                'sonars':self.sonars.is_healthy,'motors':self.motors.is_healthy}
        now=time.time(); sustained_fault=None
        for name,healthy in checks.items():
            was=self._health.get(name,True)
            if was and not healthy:
                # FR-1100-002: say what was seen and what was expected, not just the name.
                value,expected=self._fault_context(name)
                log_event(log,f'{name.upper()}_FAULT',severity='warning',subsystem=name,status='fault',
                          value=value,expected=expected)
            elif not was and healthy: log.info(f'{name} recovered'); self._fault_since.pop(name,None)
            self._health[name]=healthy
            if not healthy:
                self._fault_since.setdefault(name,now)
                if now-self._fault_since[name]>config.SENSOR_FAULT_GRACE_S:
                    sustained_fault=name
        return sustained_fault

    def _check_stall(self):
        # FR-500-003 (Directive 5): "a commanded motor showing no count change within the stall
        # window triggers stop-and-report, not increased drive." sensors.py::Encoders.stalled()
        # existed since the baseline pass but had no caller anywhere in the codebase (confirmed by
        # grep — found 2026-08-18) — Directive 5 was documented but not actually enforced. Same
        # sustained-past-a-grace-period shape as _check_health() above, so a wheel still ramping
        # up right after a fresh command isn't mistaken for a stall.
        now=time.time(); sustained=[]
        for wheel,is_commanded in self.motors.commanded.items():
            if is_commanded and self.encoders.stalled(wheel,True):
                self._stall_since.setdefault(wheel,now)
                if now-self._stall_since[wheel]>config.STALL_GRACE_S: sustained.append(wheel)
            else:
                self._stall_since.pop(wheel,None)
        return sustained

    def _fault_context(self,name):
        """FR-1100-002: (observed value, expected range) for a subsystem health fault."""
        try:
            if name=='battery_adc':
                return (f'{self.adc.battery_volts:.2f}V held (read failing or implausible)',
                        f'fresh plausible read, pack {config.BAT_SHUTDOWN_V}-12.6V')
            if name=='imu':
                return (f'tilt {self.imu.tilt:.1f}deg held, no fresh IMU report',
                        f'quaternion or acceleration changing within {config.IMU_STALE_S}s')
            if name=='encoders':
                return (self._encoder_fault_value(),f'$E frames within {config.ENCODER_STALE_S}s')
            if name=='sonars':
                return ('no fresh $S frame from Pico B',f'$S frames within {config.SONAR_STALE_S}s')
            if name=='current':
                return ('no INA260 read for >1s','reads from 0x40/0x44/0x45 within 1s')
            if name=='motors':
                return ('DriveBase ramp thread not running','ramp thread alive')
        except Exception:
            pass
        return ('unhealthy','is_healthy True')

    def _encoder_fault_value(self):
        """What an ENCODERS_FAULT saw, with the power state that usually explains it (feature
        request 2938, approved 2026-10-10 narrowed). 23 of these 10-07..09 all landed at service
        start with the base off: Pico A runs on R5 from the base, so "no frames" was no power, not
        a link fault -- and the log line could not say which. Now it says: the age of the last
        frame, the last R5 Pico A reported (it rides in the frame, so it can only be the last one),
        and the +12V bus, with a cause when the bus explains it."""
        parts=['no fresh $E frame from Pico A']
        try:
            f,age=self.encoders._link.latest('E')
            parts.append('never received' if f is None else f'last {age:.1f}s ago')
            if f is not None and len(f)>9: parts.append(f'last R5 {f[9]}mV')
        except Exception: pass
        try:
            bus=_bus_volts(self.current)
            parts.append(f'12V bus {bus:.1f}V')
            if bus<config.MOTOR_RAIL_MIN_V:
                parts.append('cause: base power off (Pico A and the encoders run on R5 from the base)')
            else:
                parts.append('bus live: Pico A, its power (R5) or the link')
        except Exception: pass
        return ', '.join(parts)

    def _stair_planning_front(self,d):
        """FR-1200-005, in the DELIBERATIVE layer (SWD §6.6): (front_cm for ROAM/SLOW/AVOID's
        planning, ok). A mapped stair edge ahead, in floor mode, shows up here as a nearer front
        so ROAM turns away STAIR_STANDOFF_M short of it. It never touches `d` -- the reflex
        sonar reading that safety.approve_motion() and the world model see stays the sensor's own
        -- so the map can steer the rover but is never what stops it.

        Fails CLOSED: with stairs on the map and no fresh pose (or an error reading them),
        ok=False and the caller refuses to roam. An uncomputable keep-out is not an absent one."""
        f=d['front']
        if config.MOBILITY_MODE!='floor': return f,True
        try:
            stairs=self.world_model.all_stairs()
            if not stairs: return f,True
            pose=self.world_model.get_robot_pose()
            if getattr(pose,'stale',False): return f,False
            from world_model import ray_to_segment
            best=None
            for st in stairs:
                a,b=st.endpoints()
                t=ray_to_segment(pose.x,pose.y,pose.heading,a,b)
                if t is not None and (best is None or t<best): best=t
        except Exception:
            log.warning('Stair standoff could not be computed -- refusing to roam',exc_info=True)
            return f,False
        if best is None: return f,True
        # f < DIST_STOP  <=>  the edge is closer than the standoff
        return min(f,max(0.0,(best-config.STAIR_STANDOFF_M)*100.0+config.DIST_STOP)),True

    # --- FR-2100 person recognition (2026-10-02) -----------------------------------------
    # Personality, not security: no alert, no event log, no photo, no behaviour change on a
    # stranger (design §5). Every bit of this runs from IDLE only and only reads the
    # recognizer's single-slot result, so the tick thread never waits on a model.
    def _face_tick(self):
        if not self.faces.available: return
        self.faces.set_scanning(True)
        res=self.faces.latest()
        if res is None or self._face_asking: return
        _,faces=res
        if len(faces)!=1:
            self._face_unknown_run=0; return
        m=self.identity.match(faces[0][1])
        if m.band==RECOGNISED:
            self._face_unknown_run=0
            if self.identity.greeting_due(m.name) and self.voice.available:
                self.voice.speak(f'Hi, {m.name}!')
            pose=self.world_model.get_robot_pose(); room=self.world_model.get_room(pose.x,pose.y)
            self.identity.note_seen(m.name,room.name if room else None)
            self.voice.set_current_person(m.name)
            return
        if m.band==UNCERTAIN:
            self._face_unknown_run=0
            self._face_last_uncertain=(time.time(),faces[0][1]); return   # silent (design §5)
        # Confidently unknown: ask, but only after FACE_STRANGER_CONFIRM_N in a row, only once
        # per session, and never while nobody is enrolled.
        self._face_unknown_run+=1
        if (self._face_unknown_run>=config.FACE_STRANGER_CONFIRM_N
                and self.identity.names(include_pending=False)
                and time.time()-self._face_asked_t>config.FACE_GREET_SESSION_S
                and self.voice.available):
            self._face_unknown_run=0; self._face_asked_t=time.time(); self._face_asking=True
            vec=faces[0][1]
            self.voice.speak('Hello! Who are you?')
            self.voice.prompt_listen(lambda text: self._stranger_answer(text,vec,UNKNOWN),
                                     config.FACE_ASK_TIMEOUT_S)

    def _stranger_answer(self,text,vec,band):
        """FR-2100-003. A spoken name may RESOLVE an identity, never create one. A vector is
        only added from the UNCERTAIN band -- a stranger claiming a name must not poison it."""
        self._face_asking=False
        import re as _re
        from voice import _NAME_REPLY
        m=_NAME_REPLY.fullmatch((text or '').strip()) if text else None
        name=m.group(1).capitalize() if m else None
        active=self.identity.names(include_pending=False)
        if name and name in active:
            if band==UNCERTAIN: self.identity.add_vector(name,vec)
            self.identity.note_seen(name); self.voice.set_current_person(name)
            if self.voice.available: self.voice.speak(f'Oh, hi {name}! Sorry, I didn\'t recognise you.')
            return
        if self.voice.available: self.voice.speak('Stranger danger!')

    def _start_enrolment(self,name):
        """FR-2100-001/006: soft gate, capture ~2 s off the tick thread, store PENDING (inert),
        email the owner a code, then introduce himself and wave -- after the capture."""
        if not self.faces.available:
            self._say("I can't learn faces right now; my camera or face models aren't available."); return
        if not name: self._say('Who should I meet?'); return
        now=time.time()
        seen=[s for s in (self.identity.last_seen(n) for n in config.FACE_ENROL_AUTHORISED) if s]
        if self.identity.names(include_pending=False) and not any(now-s.at<config.FACE_ENROL_SEEN_WINDOW_S for s in seen):
            # Deterrent only (design §5): the email approval below is the real authority.
            self._say(f'I can only meet someone new when {" or ".join(config.FACE_ENROL_AUTHORISED)} is with me.')
            return
        self._say(f'Hello {name}. Look at me for a moment, please.')
        def work():
            vecs,why=self.faces.capture_for_enrolment()
            if why:
                if self.voice.available: self.voice.speak(why)
                return
            self.identity.enrol(name,vecs)
            code=__import__('secrets').token_hex(2)
            pend=self._load_pending_enrol(); pend[code]={'name':name,'expires':time.time()+config.FACE_ENROL_CODE_TTL_S}
            self._save_pending_enrol(pend)
            self.email.send_alert(f'Willie met {name}',
                f'Willie was introduced to "{name}" and stored their face as PENDING. It does nothing '
                f'until you approve it.\n\nTo approve, send an email with the subject:\n\n'
                f'    Willie: approve {code}\n\nIf you did not introduce anyone, ignore this; it '
                f'expires in a day.\n\n-- Willie')
            log_event(log,'IDENTITY',subsystem='identity',status='enrolled_pending',name=name,vectors=len(vecs))
            if self.voice.available:
                self.voice.speak(f"Nice to meet you, {name}. I'm Willie. {config.OWNER_NAME} will confirm you by email.")
            self._wave_requested=True   # the wave runs AFTER the capture, from the tick (design §5)
        threading.Thread(target=work,daemon=True,name='enrol').start()

    def _load_pending_enrol(self):
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),config.FACE_PENDING_ENROL_PATH)) as f:
                return json.load(f)
        except (OSError,ValueError): return {}
    def _save_pending_enrol(self,pend):
        p=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.FACE_PENDING_ENROL_PATH)
        os.makedirs(os.path.dirname(p),exist_ok=True)
        with open(p,'w') as f: json.dump(pend,f)

    def _approve_enrolment(self,code,provenance):
        """Email approval handler (DKIM already verified). None if the code is not an enrolment.
        It may ONLY flip an already-pending identity to active (design §5)."""
        pend=self._load_pending_enrol()
        ent=pend.pop(code.lower(),None)
        if ent is None: return None
        self._save_pending_enrol(pend)
        if time.time()>ent['expires']: return False,f'the code for {ent["name"]} has expired'
        ok=self.identity.approve(ent['name'])
        log_event(log,'IDENTITY',subsystem='identity',status='approved' if ok else 'approve_failed',name=ent['name'])
        return (True,f'{ent["name"]} is now recognised') if ok else (False,f'{ent["name"]} was not pending')

    def _demo_sample(self,pose):
        """FR-1900-001: while a demonstration is recording, keep a waypoint every
        DEMO_POINT_SPACING_M of travel. Stale odometry adds nothing (no guessed points)."""
        if self._demo is None or getattr(pose,'stale',False): return
        lx,ly=self._demo['points'][-1]
        if math.hypot(pose.x-lx,pose.y-ly)>=config.DEMO_POINT_SPACING_M:
            self._demo['points'].append((pose.x,pose.y))

    def _finish_demo(self):
        """FR-1900-001: stop recording; save the path as a demonstration and as a route."""
        demo=self._demo; self._demo=None
        if self.pursuit.active: self.pursuit.abort('demonstration finished'); self._go('IDLE')
        if demo is None:
            self._say("I wasn't learning a route."); return
        pose=self.world_model.get_robot_pose()
        pts=demo['points']+([(pose.x,pose.y)] if math.hypot(pose.x-demo['points'][-1][0],
                                                            pose.y-demo['points'][-1][1])>0.05 else [])
        if len(pts)<config.DEMO_MIN_POINTS:
            self._say("We barely moved, so there's nothing to learn yet."); return
        pts=[(round(x,2),round(y,2)) for x,y in pts]
        self.memory.record_demonstration(demo['name'],pts,demo['context'])
        self.world_model.add_route(demo['name'],pts); self.world_model.save()
        log_event(log,'DEMO',subsystem='memory',status='saved',name=demo['name'],points=len(pts))
        self._say(f"Got it. I've learned the way to the {demo['name']}.")

    def _check_uncommanded_motion(self):
        """FR-500-003, inverse: counts changing with no command issued. Reported once per
        episode; not braked, because an idle rover coasts deliberately (motors.py)."""
        try:
            if any(self.motors.commanded.values()) or not self.encoders.is_healthy:
                self._uncmd_since=None; self._uncmd_reported=False; return
            rates=self.encoders.counts_per_sec
        except Exception:
            return
        moving=sorted(w for w,r in rates.items() if abs(r)>config.UNCOMMANDED_COUNTS_PER_S)
        if not moving:
            self._uncmd_since=None; self._uncmd_reported=False; return
        now=time.time()
        if self._uncmd_since is None: self._uncmd_since=now; return
        if not self._uncmd_reported and now-self._uncmd_since>=config.UNCOMMANDED_GRACE_S:
            self._uncmd_reported=True
            log_event(log,'UNCOMMANDED_MOTION',severity='warning',subsystem='encoders',
                      status='moving_without_command',wheels=','.join(moving),
                      max_counts_per_s=f'{max(abs(rates[w]) for w in moving):.0f}',
                      threshold=config.UNCOMMANDED_COUNTS_PER_S)

    def _abandon_stuck_if_active(self):
        # Called alongside every retrieval.abort() at a Directive 1-4 preemption point (tilt,
        # battery, sensor fault). If STUCK was mid-flight — waiting on Hailo or Claude, or
        # executing an AI-issued timed move — this drops that in-flight work so the next STUCK
        # entry starts clean rather than replaying a stale poll/move-pending state.
        #
        # Both providers must be reset, not just the cloud one: reset_async() exists precisely
        # because an unpolled result leaves _busy True forever, after which every future
        # request_async() silently refuses to submit. Missing the Hailo reset here would mean a
        # single tilt fault during on-device thinking permanently disables on-device thinking.
        if self._state=='STUCK':
            self.cloud_ai.reset_async(); self._claude_pending=False; self._claude_move_pending=False
            if self.hailo_llm is not None: self.hailo_llm.reset_async()
            self._hailo_pending=False

    def _tick(self):
        # On-screen STOP SVC button (owner request 2026-08-24). Checked first, before any
        # Directive gating: this is an operator explicitly asking the service to stop, and it
        # must work even when the rover is faulted, wedged, or off the network -- which is the
        # whole reason it exists (2026-08-24: Willie sat healthy but unreachable with no way to
        # stop him from the panel). display.py's two-step confirm means this only fires on a
        # deliberate second tap. Brake first, then let main.py's normal shutdown path run.
        if self.display.privacy_resume_tapped():
            privacy.enable_mic_camera()
            self._say("My microphone and camera are back on.")
        if self.display.stop_tapped():
            log.warning('STOP SVC tapped on screen — braking and stopping the service.')
            self.safety.emergency_stop('operator stop button')
            if self.retrieval.active: self.retrieval.abort('operator stop button')
            if self.mapping.active: self.mapping.abort('operator stop button')
            if self.navigator.active: self.navigator.abort('operator stop button')
            if self.pursuit.active: self.pursuit.abort('operator stop button')
            if self.rotation.active: self.rotation.abort('operator stop button')
            self.memory.save_all_now()
            self.display.update_state('warn','STOPPING SERVICE…')
            self._running=False
            return
        self._thermal_tick()
        self.steer_override.tick(self._state)   # FR-600-004: held in IDLE, ended on leaving it
        if self.voice.stop_requested.is_set():
            # Checked before any Directive gating below — see voice.py's stop_requested docstring.
            # This is the only place that ever clears it, and this is the tick thread, so
            # SafetyController still only ever has one caller.
            self.voice.stop_requested.clear()
            if self.retrieval.active: self.retrieval.abort('voice stop')
            if self.mapping.active: self.mapping.abort('voice stop')
            if self.navigator.active: self.navigator.abort('voice stop')
            if self.pursuit.active: self.pursuit.abort('voice stop')
            if self.rotation.active: self.rotation.abort('voice stop')
            self.steer_override.end('release','voice stop')
            self._abandon_stuck_if_active()
            self.safety.emergency_stop('voice stop')
            self._revoke_roam_permission()  # stop means stop, not "pause for 30 seconds"
            # LEAVE THE MOTION STATE. Found 2026-10-01 (FRD gap audit): this branch braked and
            # aborted the tasks but left _state alone, so the dispatch at the bottom of this
            # same tick ran _roam() -- or SLOW/AVOID/DOCK/WAVE -- and drove again. Braking does
            # not latch anything in SafetyController; only the state does. Fault states are
            # left as they are: a voice stop must never clear a latched fault.
            if self._state in _MOTION_STATES: self._go('IDLE')
            log.info('Voice-triggered immediate stop')
        if getattr(self,'_fix_ask_pending',False) and time.time()>self._fix_ask_deadline:
            self._fix_ask_pending=False; log.info('Fix-request offer lapsed unanswered.')
        if self._shutdown_pending and time.time()>self._shutdown_deadline:
            self._shutdown_pending=False
            log.info('Voice shutdown confirmation timed out — cancelled.')
            if self.voice.available: self.voice.speak("Never mind, I won't shut down.")
        self._service_roam_ask()  # panel tap / lapse for the roam-permission ask (2026-09-09)
        sustained_fault=self._check_health()
        # FR-000 Prime Directives, in order — Directive 2 (self-test gate) and Directive 4
        # (tilt/physical-limit fault) and Directive 3 (battery ladder) are checked here, each
        # able to pre-empt Directive 6 (voice/retrieval/smart-home/email, everything added in
        # v2.2) mid-task. E-stop (Directive 1) is listed in the doc's priority table too but
        # software has no way to observe it — the hardware-only latching cut has no documented
        # GPIO sense pin, so there is no check for it here, same gap as the baseline pass.
        self._sd.notify('WATCHDOG=1')
        self.witty.heartbeat()  # independent hardware watchdog (Witty Pi 5), no-op if not
                                 # installed/enabled -- see witty_pi.py's own module docstring
        pose=self.odometry.update()  # §8: passive dead-reckoning, runs regardless of motion_enabled
                                      # — no motor consequence, just keeps the estimate current for
                                      # logging/diagnostics (nothing consumes it for navigation yet).
        if time.time()-self._pose_log_t>config.POSE_LOG_INTERVAL_S:
            self._pose_log_t=time.time(); log.info(f'pose: {pose}')
        if not self._motion_enabled:
            now=time.time()
            # Retry the self-test on a timer. Without this nothing ever re-runs it, so a fault
            # that clears on its own (e.g. the loose I2C wire reseating) would keep motion
            # disabled until a manual restart -- and the failure count below would never reach
            # the threshold that offers the override.
            if now-self._selftest_retry_t>=config.SELFTEST_RETRY_S:
                self._selftest_retry_t=now
                ok,reason=self._self_test()
                if ok:
                    log.info('Self-test now passes on retry — motion enabled.')
                    self._motion_enabled=True; self._init_fail_reason=''
                    self._selftest_fail_count=0; self._go('IDLE')
                    self._upd('idle','Self-test recovered — ready',{'front':999,'left':999,'right':999},0.0)
                    return
                # Count consecutive failures for the SAME reason. A new/different reason resets
                # the count, so an override is never offered for a fault the operator hasn't
                # actually seen repeated.
                if reason!=self._init_fail_reason:
                    self._init_fail_reason=reason; self._selftest_fail_count=1
                else:
                    self._selftest_fail_count+=1
                log.warning(f'Self-test retry failed ({self._selftest_fail_count}x): {reason}')
            if self.display.override_tapped():
                # Refuse here as well as hiding the button. The tap event can only have been
                # armed while the offer stood, but a critical fault can appear between the offer
                # and the tap -- and this is the last gate before motion is re-enabled, so it
                # re-checks rather than trusting that the button was never shown.
                if self._selftest_critical:
                    log.error('SELF-TEST OVERRIDE REFUSED — safety-critical failure: '
                              +'; '.join(self._selftest_critical))
                else:
                    log.error(f'SELF-TEST OVERRIDDEN by operator — motion enabled despite: '
                              f'{self._init_fail_reason}')
                    self._motion_enabled=True; self._selftest_overridden=True
                    self._go('IDLE'); return
            # FR-100-004: the override is offered ONLY when every outstanding problem is
            # non-safety-critical. See the classification in _self_test().
            offer=(self._selftest_fail_count>=config.SELFTEST_OVERRIDE_AFTER
                   and not self._selftest_critical)
            self._upd('fault',f'SELF-TEST FAILED: {self._init_fail_reason}',
                       {'front':999,'left':999,'right':999},0.0,offer_override=offer)
            self._drain_voice_in_selftest_fault()
            return
        d=self.sonars.distances; tilt=self.imu.tilt; bat_v=self.adc.battery_volts; bat=self.adc.battery_pct
        self.safety.update_context(front_cm=d['front'],tilt_deg=tilt,motion_enabled=self._motion_enabled,
                                   rear_cm=self._rear_cm())
        # §9: passive Layer-1 obstacle feed, same "no motor consequence, just keeps an estimate
        # current" spirit as the odometry pose logging above -- every real (non-timeout) sonar hit
        # this tick becomes a world_model Obstacle point at the robot's current pose+bearing.
        for name,dist_cm in _sonar_returns(d).items():
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
            if self.rotation.active: self.rotation.abort(f'sensor fault: {sustained_fault}')
            self._abandon_stuck_if_active()
            self.safety.emergency_stop(f'{sustained_fault} sensor fault')
            if self._state!='SENSOR_FAULT': log.warning(f'  {self._state}->SENSOR_FAULT ({sustained_fault})')
            self._state='SENSOR_FAULT'
            self._upd('fault',f'SENSOR FAULT: {sustained_fault}',d,tilt); return
        if self._state=='SENSOR_FAULT':
            if not self._await_reset_or_resume('sensor fault',d,tilt,
                    'SENSOR FAULT CLEARED — tap screen to resume'): return

        if tilt>config.IMU_TILT_LIMIT:
            if self.retrieval.active: self.retrieval.abort(f'tilt fault {tilt:.1f}deg')  # FR-1700-007
            if self.mapping.active: self.mapping.abort(f'tilt fault {tilt:.1f}deg')
            if self.navigator.active: self.navigator.abort(f'tilt fault {tilt:.1f}deg')
            if self.pursuit.active: self.pursuit.abort(f'tilt fault {tilt:.1f}deg')
            if self.rotation.active: self.rotation.abort(f'tilt fault {tilt:.1f}deg')
            self._abandon_stuck_if_active()
            if self._state!='TILT_FAULT': log.warning(f'TILT_FAULT tilt={tilt:.1f}'); self._go('TILT_FAULT')
            self.safety.emergency_stop(f'tilt fault {tilt:.1f}deg')
            self._upd('fault',f'TILT {tilt:.1f}deg STOP',d,tilt); return  # FR-1600-003
        if self._state=='TILT_FAULT' and tilt<config.IMU_TILT_WARN:
            if not self._await_reset_or_resume('tilt fault',d,tilt,
                    'TILT CLEARED — tap screen to resume'): return

        # Motor-power observability (detection only -- never changes state, see _check_motor_rail).
        # Runs every tick regardless of FSM state so a cut is noticed while parked, not just
        # while driving.
        motor_rail_msg=self._check_motor_rail()
        # Encoder rail (detection only -- see _check_r5); feeds _upd's prefix and _stall_reason.
        self._check_r5()
        self._check_arm_current()
        self._check_sonar_channels()
        self._check_uncommanded_motion()
        self._demo_sample(pose)
        # Second opinion on the pack reading (detection only -- see _check_battery_crosscheck).
        self._check_battery_crosscheck()
        # Only advance the battery tier on a reading we actually got. A stale value must not
        # drive the ladder toward 'shutdown' -- that is exactly the silent self-power-off this
        # was changed to prevent (2026-08-24). _check_health() above is what reacts to staleness,
        # via SENSOR_FAULT, and it has already run this tick. Holding the tier here means a
        # transient glitch changes nothing and a sustained one surfaces as a visible fault.
        if self.adc.is_healthy:
            tier=self._update_bat_tier(bat_v)
        else:
            tier=self._bat_tier
        self.safety.update_context(bat_tier=tier)
        if tier=='shutdown':
            if self.retrieval.active: self.retrieval.abort(f'battery shutdown {bat_v:.2f}V')  # FR-1700-007
            if self.mapping.active: self.mapping.abort(f'battery shutdown {bat_v:.2f}V')
            if self.navigator.active: self.navigator.abort(f'battery shutdown {bat_v:.2f}V')
            if self.pursuit.active: self.pursuit.abort(f'battery shutdown {bat_v:.2f}V')
            if self.rotation.active: self.rotation.abort(f'battery shutdown {bat_v:.2f}V')
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
            # FR-200-004: the same clean halt as FR-900-005, not just a parked state.
            self._battery_halt('critical battery',bat_v,config.BAT_SHUTDOWN_V,d,tilt); return
        if tier=='safe':
            if self.retrieval.active: self.retrieval.abort(f'battery safe mode {bat_v:.2f}V')  # FR-1700-007
            if self.mapping.active: self.mapping.abort(f'battery safe mode {bat_v:.2f}V')
            if self.navigator.active: self.navigator.abort(f'battery safe mode {bat_v:.2f}V')
            if self.pursuit.active: self.pursuit.abort(f'battery safe mode {bat_v:.2f}V')
            if self.rotation.active: self.rotation.abort(f'battery safe mode {bat_v:.2f}V')
            self._abandon_stuck_if_active()
            if self._state!='SAFE_MODE':
                log_event(log,'LOW_BATTERY',severity='warning',subsystem='battery',
                          status='safe_mode',volts=f'{bat_v:.2f}')
            self.safety.emergency_stop(f'battery safe mode {bat_v:.2f}V'); self._go('SAFE_MODE')
            self._upd('lowbatt',f'SAFE_MODE bat={bat_v:.2f}V',d,tilt); return  # FR-1600-004
        if tier=='rth' and not config.ENABLE_DOCKING:
            # FR-200-005 with docking deferred: stop, save, then the FR-900-005 graceful halt.
            # This used to drive DOCK -- forward at 0.2 on sonar alone -- and re-enter it every
            # tick, so a voice "stop" could not hold the rover (FR-900-004).
            if self.retrieval.active: self.retrieval.abort(f'low battery {bat_v:.2f}V')
            if self.mapping.active: self.mapping.abort(f'low battery {bat_v:.2f}V')
            if self.navigator.active: self.navigator.abort(f'low battery {bat_v:.2f}V')
            if self.pursuit.active: self.pursuit.abort(f'low battery {bat_v:.2f}V')
            if self.rotation.active: self.rotation.abort(f'low battery {bat_v:.2f}V')
            self._abandon_stuck_if_active()
            self.safety.stop()
            if self._state!='LOW_BATTERY':
                self.memory.save_all_now()  # FR-1900-011 guaranteed save, while there is time
                log_event(log,'LOW_BATTERY',severity='warning',subsystem='battery',
                          status='low_battery_halt',volts=f'{bat_v:.2f}',threshold=config.BAT_RTH_V)
                if self.voice.available:
                    self.voice.speak(f'My battery is low, {bat_v:.1f} volts. I will shut down to protect it.')
                self._go('LOW_BATTERY')
            self._battery_halt('low battery',bat_v,config.BAT_RTH_V,d,tilt); return
        if tier=='rth':
            if self._state not in('DOCK','TILT_FAULT'):
                if self.retrieval.active: self.retrieval.abort(f'return-to-home {bat_v:.2f}V')  # FR-1700-007
                if self.mapping.active: self.mapping.abort(f'return-to-home {bat_v:.2f}V')
                if self.navigator.active: self.navigator.abort(f'return-to-home {bat_v:.2f}V')
                if self.pursuit.active: self.pursuit.abort(f'return-to-home {bat_v:.2f}V')
                if self.rotation.active: self.rotation.abort(f'return-to-home {bat_v:.2f}V')
                self._abandon_stuck_if_active()
                # ENABLE_DOCKING=True only (docking is deferred; the branch above handles rth
                # today). FR-1900-011: the guaranteed memory save happens here, at the earlier RTH
                # threshold. This does NOT by itself satisfy FR-200-005, which also requires the
                # FR-900-005 graceful halt -- with a dock, that halt is still to be designed.
                self.memory.save_all_now()
                log_event(log,'LOW_BATTERY',severity='warning',subsystem='battery',
                          status='return_to_home',volts=f'{bat_v:.2f}')
                self._go('DOCK')
        elif self._state=='SAFE_MODE':
            # FR-300-003 EXTENDED TO THE BATTERY LADDER, 2026-09-17. SAFE_MODE is entered via
            # safety.emergency_stop() (see the 'safe' tier above), so it is a latched fault like
            # tilt/sensor/stall -- and it used to be the ONE emergency_stop() path that resumed
            # automatically the moment voltage recovered. That is the worst place to auto-resume:
            # a sagging pack recovers as soon as the motors stop loading it, so the rover would
            # move, sag, cut, recover, and move again in a loop, each cycle taking the pack lower.
            # Now it holds braked and waits for an explicit operator reset like every other fault.
            if not self._await_reset_or_resume('battery safe mode',d,tilt,
                                               'Battery recovered — tap or say reset'): return
        if tier=='warn' and not self._bat_warned:
            # FR-200-003: warn BEFORE the critical level -- once per descent, not every tick.
            self._bat_warned=True
            log_event(log,'LOW_BATTERY',severity='warning',subsystem='battery',status='warn',
                      volts=f'{bat_v:.2f}',threshold=config.BAT_WARN_V)
            if self.voice.available:
                self.voice.speak(f'Heads up, my battery is getting low: {bat_v:.1f} volts.')
        elif tier=='normal':
            self._bat_warned=False
        if tier not in('shutdown','safe','rth'): self._bat_halt_since=None
        if self._state=='LOW_BATTERY' and tier in('normal','warn'):
            self._go('IDLE')   # recovered past the hysteresis band before the halt confirmed
        elif self._state in('SHUTDOWN','DOCK') and tier!='rth':
            # Unchanged. SHUTDOWN is a terminal powering-off path and DOCK is an ordinary
            # return-to-home task, not an emergency_stop() latch -- neither is a fault to reset.
            # Recovery can skip straight from shutdown/safe to warn/normal in one hysteresis step
            # (bypassing 'rth'), so release is handled here rather than only on DOCK.
            self._go('IDLE')

        # FR-000 Directive 5 (FR-500-003): stalls halt, not retry blindly. Checked after
        # Directives 2-4 above and before Directive 6's task dispatch below, per the priority
        # table's own ordering.
        stalled_wheels=self._check_stall()
        if stalled_wheels:
            why=self._stall_reason(stalled_wheels)
            if self.retrieval.active: self.retrieval.abort(why)
            if self.mapping.active: self.mapping.abort(why)
            if self.navigator.active: self.navigator.abort(why)
            if self.pursuit.active: self.pursuit.abort(why)
            if self.rotation.active: self.rotation.abort(why)
            self._abandon_stuck_if_active()
            if self._state!='STALL_FAULT':
                log_event(log,'MOTOR_STALL',severity='warning',subsystem='motors',
                          status='stalled',wheels=','.join(stalled_wheels),r5_low=self._r5_low)
                log.warning(f'  {self._state}->STALL_FAULT ({why})')
            self.safety.emergency_stop(why)
            self._state='STALL_FAULT'
            label='ENCODER RAIL LOW' if self._r5_low else f'STALL {stalled_wheels}'
            self._upd('fault',f'{label} STOP',d,tilt); return
        if self._state=='STALL_FAULT':
            if not self._await_reset_or_resume('wheel stall',d,tilt,
                    'STALL CLEARED — tap screen to resume'): return

        # FR-200-002: overcurrent latches like a stall -- stop, then wait for an operator reset.
        oc=self._check_overcurrent()
        if oc:
            if self.retrieval.active: self.retrieval.abort(oc)
            if self.mapping.active: self.mapping.abort(oc)
            if self.navigator.active: self.navigator.abort(oc)
            if self.pursuit.active: self.pursuit.abort(oc)
            if self.rotation.active: self.rotation.abort(oc)
            self._abandon_stuck_if_active()
            self.safety.emergency_stop(oc)
            if self._state!='OVERCURRENT_FAULT': log.warning(f'  {self._state}->OVERCURRENT_FAULT ({oc})')
            self._state='OVERCURRENT_FAULT'
            self._upd('fault',f'{oc.upper()} — STOP',d,tilt); return
        if self._state=='OVERCURRENT_FAULT':
            if not self._await_reset_or_resume('overcurrent',d,tilt,
                    'Current back to normal — tap screen to resume'): return

        self.safety.tick()  # services any in-flight timed move's deadline/obstacle re-check —
                             # must run every tick regardless of which state started the move
                             # (AVOID's reverse/turn or STUCK's Claude-issued action alike).

        if self._state=='DOCK':
            if self.adc.is_charging:
                self.safety.stop(); self._upd('idle',f'Charging {bat}%',d,tilt)
                if config.ENABLE_AUTONOMOUS_ROAM and bat>=95 and self._roam_allowed(): self._go('ROAM')
                return

        # FR-000 Directive 6 (v2.2): voice-queued task-level commands are only ever picked up
        # here, after every Directive 1-5 check above has already run this tick and none of
        # them pre-empted (FR-1500-007). Only intake a new task from IDLE — never interrupt an
        # in-progress ROAM/AVOID/etc. state to start one. Exception: mapping.active also opens
        # the gate (§10) -- mapping never touches self._state (see mapping.py's module docstring),
        # so without this a voice-issued "stop mapping" could never be drained while ROAM/SLOW/
        # AVOID legitimately keeps running the whole session.
        # Queries first, on every tick regardless of state. Asking "how's your battery?" while the
        # rover is driving used to leave the command sitting in the queue until it stopped, which
        # reads as being ignored. These branches only read cached state, so answering them costs
        # the tick nothing and none of the Directive 1-5 gating above is relevant to them.
        self._drain_voice_commands(speech_only=True)
        if (self._state=='IDLE' or self.mapping.active) and not self.retrieval.active and not self.pursuit.active:
            self._drain_voice_commands()

        {'IDLE':self._idle,'ROAM':self._roam,'SLOW':self._slow,'AVOID':self._avoid,
         'STUCK':self._stuck,'DOCK':self._dock,'WARN':self._warn,'RETRIEVE':self._retrieve,
         'NAVIGATE':self._navigate,'MANUAL':self._manual,'PURSUE':self._pursue,'WAVE':self._wave,
         'COME_TO_ME':self._come_to_me_tick,'ROTATE':self._rotate_tick,
         'TILT_FAULT':lambda d,t:None,'SAFE_MODE':lambda d,t:None,'SHUTDOWN':lambda d,t:None,
         'LOW_BATTERY':lambda d,t:None,'OVERCURRENT_FAULT':lambda d,t:None,
        }.get(self._state,lambda d,t:None)(d,tilt)

    def _email_command(self,text,reply):
        """FR-2000-012, on the email thread: interpret an authenticated owner command, announce
        it aloud, and queue it exactly like a spoken one (Directives 1-5 gate it at drain).
        reply(text) mails the result back; brain._say() calls it with the actual answer."""
        intent=self.voice.interpret_text(text)
        if not intent:
            reply(f"I didn't understand \"{text}\", so I did nothing."); return
        name=intent.get('intent','')
        who=config.OWNER_NAME
        if name=='stop':
            self.voice.stop_requested.set()
            if self.voice.available: self.voice.speak(f'{who} emailed: stop. Stopping.')
            reply('Stopping.'); return
        if name not in _EMAIL_QUEUEABLE:
            r=intent.get('reply') or "That isn't something I can do from an email."
            reply(r); return
        if self.voice.available: self.voice.speak(f'{who} emailed: {text}.')
        log_event(log,'EMAIL_COMMAND',subsystem='email',status='queued',intent=name)
        self.voice.pending_commands.put({'source':'email','intent':name,'args':intent.get('args',{}),
                                         'text':text,'ts':time.time(),'on_reply':reply})

    def _request_fix_now(self):
        """Off the tick thread: compose (cloud model) + email take seconds. Speaks the outcome."""
        try: r=self.feature_requests.tick(owner_asked=True)
        except Exception:
            log.warning('Owner-asked feature request failed',exc_info=True); r='error'
        msg={'proposed':"Done. Check your email for the fix request and its approval code.",
             'pending':"There's already a fix request waiting for your approval in your email.",
             'no_evidence':"None of those happen often enough, or recently enough, to ask for a fix yet.",
             'deferred':"I can't write it right now. I need the internet and my email.",
             'error':"Something went wrong writing the fix request."}.get(r,f"Fix request: {r}.")
        log.info(f'Owner-asked feature request: {r}')
        if self.voice.available: self.voice.speak(msg)

    def _ask(self,question):
        """A question that wants a spoken answer: beep and listen without the wake word after it
        (voice.ask). A remote caller gets the question text as its reply, as _say does."""
        cb=getattr(self,'_reply_to',None)
        if cb is not None or not getattr(self.voice,'available',False) or not hasattr(self.voice,'ask'):
            self._say(question); return
        self.voice.ask(question)

    def _say(self,text):
        # Every answer from the two drain passes goes through here. Speaks it, and hands it to
        # a remote caller (remote_cmd.py) when the command being answered came from one, so
        # Home Assistant can read it back on the Nest. The callback runs even with voice off.
        cb=getattr(self,'_reply_to',None)
        if cb is not None:
            self._reply_to=None
            try: cb(text)
            except Exception as e: log.warning(f'Remote reply callback failed: {e}')
        if self.voice.available: self.voice.speak(text)

    def _drain_voice_in_selftest_fault(self):
        # See _SELFTEST_FAULT_INTENTS. Peeks like the speech-only pass, but a disallowed intent
        # is popped and refused rather than left at the head, where it would block every query
        # queued behind it for as long as the fault lasts.
        q=self.voice.pending_commands
        with q.mutex:
            if not q.queue: return
            head=q.queue[0]; intent=head.get('intent')
        if (self._shutdown_pending or self._roam_ask_pending or getattr(self,'_fix_ask_pending',False)) and head.get('source') not in _NON_SPOKEN_SOURCES:
            self._drain_voice_commands(); return
        if not intent or intent in _SELFTEST_FAULT_INTENTS:
            self._drain_voice_commands(); return
        try: self._reply_to=q.get_nowait().get('on_reply')
        except Exception: return
        log.info(f'Voice intent "{intent}" refused: self-test failing ({self._init_fail_reason})')
        self._say(f"I can't do that. My self-test is failing: {self._init_fail_reason}.")

    def _drain_voice_commands(self,speech_only=False):
        # speech_only is the every-tick pass: it answers queries that read cached state and
        # leaves everything else untouched for the IDLE-gated pass below to handle normally.
        if speech_only:
            # A pending shutdown confirmation claims the NEXT queued command as its yes/no
            # answer (see the _shutdown_pending branch below). Draining anything here while
            # that is outstanding would silently eat the user's reply.
            # A REMOTE command (remote_cmd.py) is never that answer (see answers_ask below),
            # so it may pass.
            q=self.voice.pending_commands
            # Peek rather than pop-and-requeue: putting a non-matching command back would send
            # it to the tail and reorder the queue, so a task intent could be overtaken by
            # everything queued after it.
            with q.mutex:
                if not q.queue: return
                head=q.queue[0]
            if (self._shutdown_pending or self._roam_ask_pending or getattr(self,'_fix_ask_pending',False)) and head.get('source') not in _NON_SPOKEN_SOURCES: return
            if head.get('intent') not in _SPEECH_ONLY_INTENTS: return
        try:
            cmd=self.voice.pending_commands.get_nowait()
        except Exception:
            return
        self._reply_to=cmd.get('on_reply')  # remote_cmd.py: the HA caller waiting for the answer
        # FR-1900-005: every request is noted with its hour, so repeated time-of-day patterns
        # build up ("status around 07:00"). note_routine() existed and had no caller.
        if cmd.get('intent') and cmd.get('intent')!='confirm_receipt':
            try: self.memory.note_routine(f"{cmd['intent']} around {time.localtime().tm_hour:02d}:00")
            except Exception: pass
        # Only something the person SAID can answer a pending yes/no ask. A remote command
        # arriving mid-ask is a command in its own right: found live 2026-10-01, when an HA
        # "status" landed while Willie was asking to explore and was taken as a "no".
        answers_ask=cmd.get('source') not in _NON_SPOKEN_SOURCES
        if getattr(self,'_fix_ask_pending',False) and answers_ask:
            # 2026-10-10 (owner): after "check your logs" reports problems, he offers to ask for a
            # fix; yes runs the FR-2200 feature-request process now (draft + approval email).
            self._fix_ask_pending=False
            words=re.findall(r"[a-z']+",cmd.get('text','').lower())
            if cmd.get('intent')=='confirm_receipt' or any(w in words for w in ('yes','yeah','yep','sure','okay','ok','please')):
                self._say("Okay, I'll write it up and email you.")
                threading.Thread(target=self._request_fix_now,daemon=True,name='fix-request').start()
            else:
                self._say('Okay.')
            return
        if self._shutdown_pending and answers_ask:
            # First queued command after a 'shutdown' intent is treated as the yes/no answer to
            # that confirmation, not dispatched normally below -- see the 'shutdown' branch and
            # _tick()'s timeout check for the other two ways out of this pending state.
            self._shutdown_pending=False
            text=cmd.get('text','').lower()
            if cmd.get('intent')=='confirm_receipt' or 'confirm' in text or 'yes' in text:
                self._begin_shutdown()
            else:
                log.info('Voice shutdown declined.')
                self._say("Okay, I won't shut down.")
            return
        if self._roam_ask_pending and answers_ask:
            # Same contract as the shutdown confirmation above: the first queued command after the
            # ask is its answer, not a command in its own right. Anything that is not recognisably
            # a yes counts as a no -- and a no costs only a cooldown, so reading an ambiguous reply
            # as refusal is the cheap direction to be wrong in.
            text=cmd.get('text','').lower()
            words=re.findall(r"[a-z']+",text)   # "Yes." from a prompted answer keeps its full stop
            if (cmd.get('intent') in ('confirm_receipt','roam')
                    or any(w in words for w in ('yes','yeah','yep','sure','okay','ok'))
                    or 'go ahead' in text):
                self._end_roam_ask(True)
            else:
                log.info('Roam permission declined.')
                self._say('Okay, maybe later.')
                self._end_roam_ask(False)
            return
        # Drop commands that have gone stale in the queue. voice.py has always stamped 'ts' here
        # but nothing ever read it, so a command queued while a task was running executed
        # whenever the task happened to finish -- say "turn right" during a 30s retrieval and the
        # rover turns half a minute later, in a situation you have stopped watching for. Acting
        # late on a motion command is worse than not acting at all.
        #
        # confirm_receipt is exempt: it answers retrieval_task.py's AWAIT_CONFIRM, which may
        # legitimately wait longer than this window, and expiring it stalls the task rather than
        # protecting anyone. The shutdown confirmation is handled above this check for the same
        # reason, and carries its own timeout in _tick().
        #
        # A command with no 'ts' at all is treated as fresh: that means an unfamiliar source, not
        # an old command, and silently eating it would be the worse failure.
        ts=cmd.get('ts')
        if (ts is not None and cmd.get('intent') not in _NON_EXPIRING_INTENTS
                and (time.time()-ts)>config.VOICE_COMMAND_MAX_AGE_S):
            log.info(f'Dropping stale voice command "{cmd.get("intent")}" '
                     f'({time.time()-ts:.1f}s old, limit {config.VOICE_COMMAND_MAX_AGE_S}s)')
            return
        if cmd.get('intent')=='retrieve' and not config.ENABLE_RETRIEVAL_TASK:
            log.info('Voice retrieve refused: ENABLE_RETRIEVAL_TASK is off')
            self._say("I can't fetch things yet. My arm isn't safe for that.")
        elif cmd.get('intent')=='retrieve':
            target=cmd.get('args',{}).get('object','object')
            ok,msg=self.retrieval.start(target)
            if ok: self._go('RETRIEVE')
            log.info(f'Voice-triggered retrieval: {target} ({msg})')
        elif cmd.get('intent')=='name_room':
            # FR-1000-001: rooms were never added, so 'go to <room>' could not resolve. Labelled
            # by voice at the robot's current position, saved at once.
            name=cmd.get('args',{}).get('room','').strip()
            if name:
                pose=self.world_model.get_robot_pose()
                self.world_model.add_room(name,pose.x,pose.y); self.world_model.save()
                log.info(f'Room labelled: {name} at ({pose.x:.2f},{pose.y:.2f})')
                self._say(f'Got it, this is the {name}.')
        elif cmd.get('intent')=='enrol':
            self._start_enrolment(cmd.get('args',{}).get('name','').strip())
        elif cmd.get('intent')=='forget_everyone':
            self.identity.forget_all()
            log_event(log,'IDENTITY',subsystem='identity',status='forgot_everyone')
            self._say("Done. I've forgotten everyone's face.")
        elif cmd.get('intent')=='demo_start':
            # FR-1900-001: record the path while following the person (camera) or while driven.
            name=cmd.get('args',{}).get('name','').strip()
            if not name: self._say('What should I call that route?')
            else:
                pose=self.world_model.get_robot_pose()
                room=self.world_model.get_room(pose.x,pose.y)
                self._demo={'name':name,'points':[(pose.x,pose.y)],'started':time.time(),
                            'context':{'start_x':round(pose.x,2),'start_y':round(pose.y,2),
                                       'start_room':room.name if room else ''}}
                following=False
                if self.detector.available and not self.pursuit.active:
                    ok,_=self.pursuit.start(mode='follow')
                    if ok: self._go('PURSUE'); following=True
                log_event(log,'DEMO',subsystem='memory',status='recording',name=name,following=following)
                self._say(f"Okay, I'm watching. {'Lead the way' if following else 'Drive me there'}, "
                          f"and say that's it when we arrive.")
        elif cmd.get('intent')=='demo_stop':
            self._finish_demo()
        elif cmd.get('intent')=='demo_replay':
            # FR-1900-002/003: replay from near the start, or join the path partway if he is
            # near it (2026-10-08); otherwise say so.
            name=cmd.get('args',{}).get('name','').strip()
            pose=self.world_model.get_robot_pose()
            wps,sim,start=self.memory.replay_demonstration(name,{'start_x':pose.x,'start_y':pose.y})
            if sim is None:
                self._say(f"I haven't learned a way to the {name}.")
            elif wps is None:
                log_event(log,'DEMO',subsystem='memory',status='replay_refused',name=name,similarity=f'{sim:.2f}')
                self._say(f"I'm too far from the {name} route to follow it. "
                          f"Take me nearer to it, or show me again from here.")
            elif start>=len(wps)-1:
                self._say(f"I'm already at the end of the way to the {name}.")
            else:
                if self.world_model.get_route(name) is None:
                    self.world_model.add_route(name,[tuple(p) for p in wps])
                ok,msg=self.navigator.start(Mission(route=name,start=start))
                if ok: self._go('NAVIGATE')
                log_event(log,'DEMO',subsystem='memory',status='replay' if ok else 'replay_failed',
                          name=name,similarity=f'{sim:.2f}',start=start)
                said='Following the way to the' if start==0 else 'Joining the way to the'
                self._say(f'{said} {name}.' if ok else f"I can't follow that route: {msg}")
        elif cmd.get('intent')=='mark_stairs':
            # FR-1200-006: the edge sits STAIR_LABEL_AHEAD_M in front, across his heading.
            pose=self.world_model.get_robot_pose()
            import math as _m
            x=pose.x+config.STAIR_LABEL_AHEAD_M*_m.cos(pose.heading)
            y=pose.y+config.STAIR_LABEL_AHEAD_M*_m.sin(pose.heading)
            name=f'stairs{len(self.world_model.all_stairs())+1}'
            self.world_model.add_stair(name,x,y,pose.heading); self.world_model.save()
            log_event(log,'STAIR_LABELLED',subsystem='world_model',status=name,x=f'{x:.2f}',y=f'{y:.2f}')
            self._say(f"Got it, stairs marked. I'll keep {int(config.STAIR_STANDOFF_M*100)} centimetres back from them.")
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
                self._say(f"Can't do that — {result.reason}")
            else:
                self._manual_action=action; self._go('MANUAL')
                log.info(f'Voice-triggered manual move: {action} speed={result.speed} duration={result.duration}')
        elif cmd.get('intent') in('come_here','follow'):
            if not self.detector.available:
                self._say("My camera isn't available, I can't find you.")
            else:
                mode='follow' if cmd['intent']=='follow' else 'come_here'
                ok,msg=self.pursuit.start(mode=mode)
                if ok: self._go('PURSUE')
                self._say('On my way.' if ok else f"I can't come over: {msg}")
                log.info(f'Voice-triggered pursuit: mode={mode} ({msg})')
        elif cmd.get('intent')=='rotate':
            deg=float(cmd.get('args',{}).get('degrees',180))
            ok,msg=self.start_rotation(deg)
            if not ok: self._say(f"I can't turn: {msg}")
            log.info(f'Voice-triggered rotation {deg:+.0f} deg ({msg})')
        elif cmd.get('intent')=='roam':
            # 2026-10-10 (owner): roam by voice without the screen. Saying it grants the session
            # permission (same grant as the button) and, from IDLE, sets off now.
            if not self._motion_enabled:
                self._say(f"I can't explore yet. My self-test is failing: {self._init_fail_reason}.")
            else:
                if self._roam_ask_pending: self._roam_ask_pending=False; self.display.offer_roam(False)
                self._roam_permission=True
                log.info('Roam permission granted by voice command.')
                if self._state=='IDLE':
                    self._idle_t=0.0; self._say('Off I go.'); self._go('ROAM')
                else:
                    self._say("Okay, I'll explore when I'm done with this.")
        elif cmd.get('intent')=='steer':
            # FR-600-004. Applied in this same tick (one control cycle), parked only, clamped.
            r=self.safety.approve_steer(cmd.get('args',{}).get('degrees',0))
            if isinstance(r,Rejected):
                self._say(f"I can't steer: {r.reason}.")
            elif r.speed==0:
                if self.steer_override.active: self.steer_override.end('centre','wheels straight')
                else: self.steering.center_all()
                self._say('Wheels straight.')
            else:
                d=self.steer_override.apply(r.speed)
                self._say(f"Wheels {abs(d):.0f} degrees {'right' if d>0 else 'left'}. Say wheels straight to undo.")
            log.info(f'Steering override command {cmd.get("args")} ({r})')
        elif cmd.get('intent')=='come_to_me':
            ok,msg=self.come_to_me.start(cmd.get('args',{}).get('room',''))
            if ok: self._go('COME_TO_ME')
            log.info(f'Voice-triggered come to me: {cmd.get("args")} ({msg})')
        elif cmd.get('intent')=='status':
            bat_v=self.adc.battery_volts; bat_pct=self.adc.battery_pct
            if not self._motion_enabled and self._init_fail_reason:
                self._say(f"I can't move. My self-test is failing: {self._init_fail_reason}.")
            elif bat_v<=0:
                self._say(f"I'm currently {self._state.lower()}, and I can't read my battery.")
            else:
                self._say(f"I'm currently {self._state.lower()}, battery at {bat_v:.1f} volts, {bat_pct} percent."
                          +(" I'm running hot." if getattr(self,'thermal',None) and self.thermal.level=='hot' else ''))
        elif cmd.get('intent')=='battery':
            bat_v=self.adc.battery_volts; bat_pct=self.adc.battery_pct
            self._say("I can't read my battery right now." if bat_v<=0 else
                                 f"Battery is at {bat_v:.1f} volts, about {bat_pct} percent.")
        elif cmd.get('intent') in('arm_stow','arm_home'):
            # Stow/home = the REST pose, reached in steps (shoulder first, 50 us at a time, then
            # elbow, then wrist) through the same tick-serviced sequence as the wave. Used to be
            # center_all(), which jumped the shoulder to 1500 in one step.
            self._start_arm_sequence(self._rest_plan(self._shoulder_now(),
                                     int(self.arm.pulse('elbow')) if self.arm.was_driven('elbow') else None))
            self._say('Putting my arm away.')
        elif cmd.get('intent')=='wave':
            self._start_wave()
        elif cmd.get('intent')=='diagnostics':
            # Deliberately does NOT touch self._motion_enabled either way afterward -- that's the
            # startup gate, and silently flipping it from a possibly-transient on-demand result is
            # an owner decision, not something to do automatically (same reasoning as
            # config.validate() staying non-blocking in _self_test() above). Runs synchronously on
            # the tick thread (~0.5s+, real I2C scan) -- accepted: this only ever runs from IDLE.
            self._say('Running diagnostics now, one moment.')
            ok,reason=self._self_test()
            self._say('Everything checks out.' if ok else f'Diagnostics found a problem: {reason}')
        elif cmd.get('intent')=='check_logs':
            # 2026-10-10 (owner): "check your logs". Reads ~4 MB of log on this thread (well under
            # a second) -- accepted for the same reason as diagnostics: it only runs from IDLE.
            import logcheck
            text,found=logcheck.check()
            if found and getattr(self,'feature_requests',None) is not None and config.ENABLE_FEATURE_REQUESTS:
                self._say(text)
                self._ask('Do you want me to ask for a fix?')
                self._fix_ask_pending=True; self._fix_ask_deadline=time.time()+config.FIX_ASK_TIMEOUT_S
            else:
                self._say(text)
        elif cmd.get('intent')=='where_are_you':
            pose=self.world_model.get_robot_pose()
            room=self.world_model.get_room(pose.x,pose.y)
            self._say(f"I'm in the {room.name}." if room else "I'm not sure which room I'm in.")
        elif cmd.get('intent')=='privacy_on':
            # FR-1800-005. Said BEFORE the flag goes down: speaking uses the speaker, not the mic.
            self._say("Privacy on. My microphone and camera are off. Tap the button on my screen "
                      "twice to turn them back on.")
            privacy.disable_mic_camera(f'{cmd.get("source","voice")} command')
        elif cmd.get('intent')=='privacy_off':
            # Owner email only in practice -- by voice he cannot hear it, the screen has its own button.
            privacy.enable_mic_camera(); self._say("My microphone and camera are back on.")
        elif cmd.get('intent')=='what_doing':
            self._say(self._activity_phrase())
        elif cmd.get('intent')=='what_do_you_see':
            # v1: names detected object classes from the existing detector, not a real VLM caption.
            # Kept BRIEF (owner 2026-10-07): the three most confident distinct things, "and more".
            if not self.detector.available:
                reply="My camera isn't available right now."
            else:
                best={}
                for det in self.detector.detect():
                    c=det['class']; best[c]=max(best.get(c,0.0),det.get('conf',0.0))
                names=[c for c,_ in sorted(best.items(),key=lambda kv:-kv[1])]
                if not names: reply="Nothing in particular."
                else:
                    shown=names[:3]
                    said=shown[0] if len(shown)==1 else ', '.join(shown[:-1])+' and '+shown[-1]
                    reply=f"I can see {said}{', and more' if len(names)>3 else ''}."
            self._say(reply)
        elif cmd.get('intent')=='shutdown':
            self._ask('Are you sure you want me to shut down? Say confirm to proceed.')
            self._shutdown_pending=True; self._shutdown_deadline=time.time()+15.0
        elif cmd.get('intent'):
            log.info(f'Voice intent "{cmd["intent"]}" received but not wired to an executor.')
            # FR-800-004 principle applied to voice too: a command that can't be carried out
            # should be reported, not silently absorbed -- the LLM's own free-form 'reply' already
            # got spoken by voice.py's _act_on_intent when this was queued, which can sound like
            # confident compliance even though nothing is wired here. This is the corrective.
            self._say("I heard you, but I don't know how to do that yet.")

    def _retrieve(self,d,tilt):
        self.retrieval.tick(d,tilt)
        if self.retrieval.state in('DONE','FAILED','ABORTED'):
            if self.retrieval.state=='DONE' and self.voice.available: self.voice.speak('All done!')
            self.retrieval.reset(); self._go('IDLE')

    def _brake_before_hailo(self):
        """Runs on whichever thread is about to call the Hailo model (voice or the STUCK worker),
        right before the process freezes. Uses SafetyController.brake_now(), a synchronous hard
        brake -- a normal stop request would only set a target for the ramp thread, which is about
        to freeze too. (First written as a direct DriveBase call; tests/test_no_direct_drive_bypass
        caught it in CI.) The tick loop re-issues motion after the call returns; this
        does not change state, it only makes sure nothing is moving through the blind seconds."""
        if any(self.motors.commanded.values()):
            self.safety.brake_now('Hailo generation freezes every thread; braked before it')

    def _activity_phrase(self):
        """One brief sentence for "what are you doing?" (owner 2026-10-07). Read-only: it only
        looks at state that already exists, so asking never changes what he is doing."""
        st=self._state
        faults={'STALL_FAULT':'a wheel got stuck','SENSOR_FAULT':'a sensor stopped answering',
                'TILT_FAULT':'I was tipped too far','OVERCURRENT_FAULT':'something drew too much current',
                'SAFE_MODE':'my battery is very low','LOW_BATTERY':'my battery is low'}
        if st in faults: return f"I've stopped because {faults[st]}. Say reset when it's safe."
        if st=='SHUTDOWN': return "I'm shutting down."
        # A failing self-test first: on Pi-only power he never leaves INIT, and "just starting up"
        # (2026-10-08, live) hid the real reason he will not move.
        if not getattr(self,'_motion_enabled',True) and st in('IDLE','INIT'):
            return "I'm waiting. I can't move until my self-test passes."
        if st=='INIT': return "I'm just starting up."
        if st=='ROTATE':
            d=getattr(self.rotation,'_dir',1)
            return f"I'm turning {'left' if d>0 else 'right'}."
        if st=='COME_TO_ME':
            room=getattr(self.come_to_me,'room',None) or 'room'
            return (f"I'm looking for you in the {room}." if self.come_to_me.state=='LEG_FIND'
                    else f"I'm on my way to the {room}.")
        if st=='PURSUE':
            return "I'm following you." if getattr(self.pursuit,'_mode','')=='follow' else "I'm coming to you."
        if st=='NAVIGATE':
            room=getattr(self.navigator,'_target_room',None)
            if getattr(self.navigator,'state','')=='DOOR_WAIT': return "I'm waiting for someone to open the door."
            return f"I'm heading to the {room}." if room else "I'm driving to a spot I know."
        if st=='MANUAL':
            act={'forward':'moving forward','reverse':'backing up','turn_left':'turning left',
                 'turn_right':'turning right'}.get(getattr(self,'_manual_action',''),'moving')
            return f"I'm {act}, like you asked."
        phrase={'ROAM':"I'm exploring.",'SLOW':"I'm exploring, slowly, something's close.",
                'AVOID':"I'm getting around something in my way.",'WARN':"I'm being careful, the floor's uneven.",
                'STUCK':"I'm stuck and working out what to do.",'WAVE':"I'm moving my arm.",
                'RETRIEVE':"I'm fetching something.",'DOCK':"I'm heading home to charge."}.get(st)
        if phrase is None:
            phrase="Nothing much, just waiting." if st=='IDLE' else f"I'm busy ({st.lower()})."
        if getattr(self.mapping,'active',False): phrase=phrase[:-1]+", and mapping as I go."
        return phrase

    def start_rotation(self,degrees,then='IDLE'):
        """Turn on the spot by `degrees` (+ left) in rotation mode, then go to state `then`."""
        ok,msg=self.rotation.start(degrees)
        if ok: self._after_rotate=then; self._go('ROTATE')
        return ok,msg

    def _rotate_tick(self,d,tilt):
        self.rotation.tick(d,tilt)
        if not self.rotation.active:
            done=self.rotation.state; self.rotation.reset()
            nxt=self._after_rotate; self._after_rotate='IDLE'
            if nxt=='AVOID' and done!='DONE':
                # Blocked or refused mid-avoidance: back off and let AVOID try again.
                self._avoid_phase=None
                self.safety.request('reverse',None,config.BACK_UP_TIME)
            self._go(nxt)

    def _come_to_me_tick(self,d,tilt):
        # FR-1000-006. The task speaks every outcome itself; this only leaves the state.
        self.come_to_me.tick(d,tilt)
        if self.come_to_me.state not in('LEG_NAVIGATE','LEG_FIND'):
            self.come_to_me.reset(); self._go('IDLE')

    def _pursue(self,d,tilt):
        self.pursuit.tick(d,tilt)
        if self.pursuit.state in('DONE','FAILED','ABORTED'):
            if self.pursuit.state=='DONE' and self.voice.available: self.voice.speak('Here I am!')
            self.pursuit.reset(); self._go('IDLE')

    # Fixed primitive sequence, not calibrated IK — same category of gap as
    # retrieval_task.py's _grasp() (§20.6 pending, see its module docstring). wrist_rot
    # oscillates +-300us off center, the same offset magnitude already trusted there, well
    # inside ARM_SERVO_MIN/MAX_US.
    #
    # Used to block the tick thread for ~1.5s (3 back-and-forth swings via time.sleep()) —
    # "accepted, this only ever runs from IDLE" was the reasoning at the time, but that
    # reasoning assumed no systemd watchdog was actually configured. It is (WatchdogSec=500ms,
    # confirmed 2026-08-18 — see brain.py's RoverBrain.__init__ comment): a single tick blocking
    # ~1.5s gets the whole service killed and restarted by systemd mid-wave, every time, which
    # is a real reliability bug once voice is enabled (ENABLE_VOICE=True since 2026-08-15/16),
    # not an accepted tradeoff. Converted to the same non-blocking, tick-serviced step pattern as
    # _grasp() — see 'WAVE' in the state dispatch table above.
    # 2026-10-02: the wave now uses the pose verified on hardware 2026-09-17
    # (config.ARM_POSE_WAVE_HELLO). It used to twitch the wrist ROTATION +-300us from wherever
    # the arm sat, which is not the wave the owner saw. Order is the hardware rule from config:
    # open the elbow BEFORE moving the shoulder (or the arm strikes the top of Willy), shoulder in
    # ARM_WAVE_APPROACH_STEP_US steps (a single jump slams the joint), wave the wrist PITCH, then
    # come back in reverse: shoulder down first, elbow last. FR-700-002.
    @staticmethod
    def _wave_plan(shoulder_from):
        p=config.ARM_POSE_WAVE_HELLO; r=config.ARM_POSE_REST; step=config.ARM_WAVE_APPROACH_STEP_US
        def ramp(a,b):
            d=step if b>a else -step
            return [('shoulder',v,config.ARM_WAVE_STEP_S) for v in range(a+d,b,d)]+[('shoulder',b,0.3)]
        plan=[('elbow',p['elbow'],0.6)]
        plan+=ramp(shoulder_from,p['shoulder'])
        plan+=[('wrist_pitch',p['wrist_pitch'],0.3)]
        lo,hi=config.ARM_WAVE_WRIST_US
        for _ in range(config.ARM_WAVE_CYCLES):
            plan+=[('wrist_pitch',lo,config.ARM_WAVE_LEG_S),('wrist_pitch',hi,config.ARM_WAVE_LEG_S)]
        plan+=[('wrist_pitch',p['wrist_pitch'],0.3)]
        plan+=ramp(p['shoulder'],r['shoulder'])
        plan+=[('elbow',min(r['elbow'],config.ARM_SERVO_MAX_US),0.6),('wrist_pitch',config.ARM_REST_WRIST_US,0.0)]
        return plan

    @staticmethod
    def _rest_plan(shoulder_from,elbow_from=None):
        """Back to ARM_POSE_REST: shoulder in steps, then elbow, then the low-current wrist.

        FR-700-002, stow from ANY starting configuration. Owner rule: the elbow must be open
        before the shoulder moves, or the arm strikes the top of Willy. Coming back from the
        wave it already is; from anywhere else (arm_jog, a half-finished sequence) it may not
        be. So if the shoulder has to move and the elbow is not known to be at least as open as
        the wave pose's, open it first -- the same first step the hardware-verified wave takes.
        elbow_from=None means not driven this boot: position unknown, treated as closed."""
        r=config.ARM_POSE_REST; step=config.ARM_WAVE_APPROACH_STEP_US
        open_us=config.ARM_POSE_WAVE_HELLO['elbow']
        plan=[]
        if shoulder_from!=r['shoulder'] and (elbow_from is None or elbow_from>open_us):
            plan.append(('elbow',open_us,0.6))
        d=step if r['shoulder']>shoulder_from else -step
        plan+=[('shoulder',v,config.ARM_WAVE_STEP_S) for v in range(shoulder_from+d,r['shoulder'],d)]
        plan+=[('shoulder',r['shoulder'],0.3),
               ('elbow',min(r['elbow'],config.ARM_SERVO_MAX_US),0.6),
               ('wrist_pitch',config.ARM_REST_WRIST_US,0.0)]
        return plan

    def _shoulder_now(self):
        # Step from where the shoulder really is; if it has not been driven this boot its pulse
        # is a placeholder, so assume it is resting.
        return int(self.arm.pulse('shoulder') if self.arm.was_driven('shoulder') else config.ARM_POSE_REST['shoulder'])

    def _start_arm_sequence(self,plan):
        self._wave_seq=plan; self._wave_step=0; self._wave_deadline=None; self._go('WAVE')

    def _start_wave(self):
        if self.voice.available: self.voice.speak('Hello!')
        self._start_arm_sequence(self._wave_plan(self._shoulder_now()))

    def _wave(self,d,tilt):
        now=time.time()
        if self._wave_deadline is not None:
            if now<self._wave_deadline: return
            self._wave_deadline=None
        joint,us,delay=self._wave_seq[self._wave_step]
        self.arm.set_pulse(joint,us)
        self._wave_step+=1
        if self._wave_step>=len(self._wave_seq): self._go('IDLE')
        else: self._wave_deadline=now+delay

    def _begin_shutdown(self,reason='voice command'):
        # FR-900-005: halt motion, stow arm, persist state, then `shutdown -h now`. Reuses
        # stop()'s existing graceful-cleanup sequence (task aborts, memory/world_model
        # persistence, motor/sensor teardown) rather than duplicating it — that's already what
        # run()'s `finally` calls on any exit. The actual OS shutdown call only ever fires from
        # stop()'s tail, gated on _shutdown_after_stop, so this never risks a plain service
        # restart/SIGTERM/Ctrl-C powering off the Pi.
        log.warning(f'Graceful shutdown: {reason}')
        self.safety.emergency_stop(f'shutdown: {reason}')
        self.arm.release()   # power is about to go; a centring jump first only stresses the joints
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
        self._retention_sweep()
        self._face_tick()
        if getattr(self,'_wave_requested',False):
            self._wave_requested=False
            try: self._start_wave()
            except Exception: log.warning('Post-enrolment wave failed',exc_info=True)
        self._upd('idle',f'Waiting... bat={self.adc.battery_pct}%',d,tilt)
        summaries=self.email.get_new_summaries() if self.email.available else []
        for s in summaries:
            msg=f'New email from {s["from"]}: {s["subject"]}'
            log.info(msg)
            if self.voice.available: self.voice.speak(msg)  # FR-2000-003: surfaced, never acted on
        if config.ENABLE_AUTONOMOUS_ROAM and self._idle_t>=config.IDLE_TIMEOUT:
            # _roam_allowed() opens the permission ask as a side effect when there is no grant
            # yet. _idle_t is only reset when he actually goes -- while an ask is open or in
            # cooldown the timeout stays tripped, so the moment permission arrives he leaves
            # rather than waiting out another full IDLE_TIMEOUT.
            if self._roam_allowed():
                self._idle_t=0.0; self._go('ROAM')

    def _roam(self,d,tilt):
        f,ok=self._stair_planning_front(d)
        if not ok:
            self.safety.stop(); self._go('IDLE')
            self._upd('idle','Not roaming: can\'t check the stair map (no fresh position)',d,tilt); return
        if tilt>config.IMU_TILT_WARN: self._go('WARN'); return
        if f<config.DIST_STOP: self.safety.obstacle_stop(); self._go('AVOID'); return   # brake, not ramp
        if f<config.DIST_SLOW: self._go('SLOW'); return
        self.safety.forward(config.SPEED_ROAM); self._last_action='forward'
        self._upd('roam',f'Cruising f={f:.0f}cm bat={self.adc.battery_pct}%',d,tilt,config.SPEED_ROAM)

    def _slow(self,d,tilt):
        f,ok=self._stair_planning_front(d)
        if not ok: self.safety.stop(); self._go('IDLE'); return
        if f>config.DIST_CLEAR: self._go('ROAM'); return
        if f<config.DIST_STOP: self.safety.obstacle_stop(); self._go('AVOID'); return   # brake, not ramp
        self.safety.forward(config.SPEED_SLOW); self._upd('slow',f'Slowing f={f:.0f}cm',d,tilt,config.SPEED_SLOW)

    def _avoid(self,d,tilt):
        # Non-blocking (§2 of docs/WildWilly_Claude_Fix_Implementation_Plan.md): every branch that
        # used to be a blocking motors.*_for() call now starts a deadline-based timed move via
        # self.safety and returns immediately — self.safety.tick() (called once centrally in
        # _tick()) services the deadline on every subsequent tick, and the timed_move_active guard
        # below keeps this state from issuing a second, overlapping command while one is in flight.
        # The old single-call "back up then turn" combo becomes two ticks via _avoid_phase.
        f,_ok=self._stair_planning_front(d); l=d['left']; r=d['right']
        if not _ok: f=0.0   # fail closed: never treat an uncomputable keep-out as clear
        if self.safety.timed_move_active:
            self._upd('stop',f'Avoiding l={l:.0f} r={r:.0f}',d,tilt); return
        if self._avoid_phase=='turn_after_reverse':
            self._avoid_phase=None
            turn=self._avoid_turn(d) or 'turn_right'
            if not config.AVOID_USE_ROTATION:
                self.safety.request(turn,None,config.TURN_TIME_90)
            elif not self.start_rotation(90 if turn=='turn_left' else -90,then='AVOID')[0]:
                # No room to spin even after backing up: back up again rather than skid-turn,
                # which sweeps the same circle (outside review, rotation envelope).
                self.safety.request('reverse',None,config.BACK_UP_TIME)
            self._last_action='back_turn'
            self._upd('stop',f'Avoiding l={l:.0f} r={r:.0f}',d,tilt); return
        if time.time()-self._avoid_start>config.STUCK_TIMEOUT:
            self._stuck_count+=1
            if self._stuck_count>=config.CLAUDE_ESCALATE_AFTER: self._go('STUCK'); return
            self._avoid_start=time.time(); self.safety.request('reverse',None,config.BACK_UP_TIME); return
        if f>config.DIST_CLEAR: self._stuck_count=0; self._go('ROAM'); return
        self.safety.stop()
        turn=self._avoid_turn(d)
        if turn:
            # Rotation mode (live-verified 2026-10-07) when allowed; the skid turn if it will not start.
            if not config.AVOID_USE_ROTATION:
                self.safety.request(turn,None,config.TURN_TIME_90*0.5)
            elif not self.start_rotation(45 if turn=='turn_left' else -45,then='AVOID')[0]:
                # Refused (usually: not enough room). A skid turn sweeps the same circle, so back
                # off and let AVOID choose again from further away.
                self.safety.request('reverse',None,config.BACK_UP_TIME)
            self._last_action=turn
        else:
            self.safety.request('reverse',None,config.BACK_UP_TIME)
            self._avoid_phase='turn_after_reverse'; self._last_action='back_turn'
        self._upd('stop',f'Avoiding l={l:.0f} r={r:.0f}',d,tilt)

    def _avoid_turn(self,d):
        # FR-1000-002 (owner 2026-10-06): side sonar + ToF columns + front camera pick the side.
        # Only the side -- the stop is still sonar + ToF alone (avoidance.py header).
        return avoidance.choose_turn(d,getattr(self.sonars,'tof',None),self.detector)

    def _stuck(self,d,tilt):
        # Autonomous thinking: Hailo LLM primary (on-device), Claude fallback only if needed.
        #
        # Non-blocking (§2): BOTH providers run on their own AIProvider worker thread and this
        # state polls them, so a slow decision costs extra STUCK ticks instead of stalling the
        # tick loop. f18af62 (2026-09-01) called Hailo synchronously here instead, which put a
        # full generate_all() on the tick thread -- the kill-mid-tick case FRD v3.1 G-5
        # describes, and a direct violation of ai_provider.py::ask_sync()'s "only for callers
        # already off the tick thread" contract. Restored to the async path 2026-09-07.
        #
        # Accuracy note (found later the same day): the installed systemd unit had no
        # WatchdogSec at all until 2026-09-07 -- see the stale-deploy paragraph in __init__ --
        # so that blocking call was never actually killing the process in the field. It was a
        # real defect against the documented design, not a live outage. It becomes live the
        # first time the service restarts under the newly-installed unit, which is why this was
        # worth fixing before arming the watchdog rather than after. If a decision needs to be made inline for
        # latency reasons, raise WatchdogSec first -- do not put generation back on this thread.
        if self.safety.timed_move_active:
            self._upd('stuck',f'Executing: {self._last_action}',d,tilt); return
        if self._claude_move_pending:
            self._claude_move_pending=False; self._stuck_count=0; self._go('ROAM'); return
        if self._hailo_pending:
            result=self.hailo_llm.poll_async()
            if result is None:
                self._upd('stuck','Thinking on-device...',d,tilt); return
            self._hailo_pending=False
            log.info(f'Hailo(primary): parse_success={result.parse_success} '
                     f'action_confidence={result.action_confidence} payload={result.payload}')
            if result.parse_success and result.action_confidence>=config.HAILO_LLM_CONFIDENCE_FLOOR:
                # High confidence on-device decision — proceed without Claude
                self._apply_ai_motion(result,d,tilt,'Hailo(primary)')
                self._stuck_history.append({'role':'user','content':self._last_stuck_prompt})
                self._stuck_history.append({'role':'assistant','content':json.dumps(result.payload)})
                self._stuck_history=self._stuck_history[-12:]
                return
            # Hailo failed or low confidence — escalate to Claude
            log.info(f'Hailo confidence {result.action_confidence:.2f} < floor '
                     f'{config.HAILO_LLM_CONFIDENCE_FLOOR} or parse failed, escalating to Claude')
            self._escalate_to_claude(d,tilt); return
        if self._claude_pending:
            result=self.cloud_ai.poll_async()
            if result is None:
                self._upd('stuck','Escalated to Claude...',d,tilt); return
            self._claude_pending=False
            log.info(f'Claude(fallback): parse_success={result.parse_success} '
                     f'action_confidence={result.action_confidence} payload={result.payload}')
            self._apply_ai_motion(result,d,tilt,'Claude(fallback)')
            return
        # Fresh STUCK episode: halt, build the prompt, hand it to the on-device model.
        self.safety.stop()
        situation=build_world_state(self.world_model,goal='find a clear path to continue roaming',
                                     battery=self.adc.battery_pct,front_cm=d['front'],left_cm=d['left'],
                                     right_cm=d['right'],tilt_deg=tilt,stuck_count=self._stuck_count,
                                     last_action=self._last_action)
        # Built by ai_provider.build_stuck_prompt so the measurement harness sends exactly
        # what the rover sends -- see that function for the 2026-09-14 measurements behind its
        # shape. It previously lived here as a literal, with a hand-kept copy in the harness.
        self._last_stuck_prompt=build_stuck_prompt(situation)

        if config.ENABLE_HAILO_LLM and self.hailo_llm and self.hailo_llm.available:
            if self.hailo_llm.request_async(self._last_stuck_prompt,system=_MOTION_SYSTEM,
                                             schema=_MOTION_SCHEMA):
                self._hailo_pending=True
                self._upd('stuck','Thinking on-device...',d,tilt); return
            # request_async() refused: a previous result was never polled. Don't wait on it.
            log.warning('Hailo LLM still busy with an unpolled request — escalating to Claude')
            self.hailo_llm.reset_async()

        # Fall back to Claude (cloud, potentially slower but higher capability)
        self._escalate_to_claude(d,tilt)

    def _escalate_to_claude(self,d,tilt):
        """Hand self._last_stuck_prompt to the cloud provider's worker thread. Split out of
        _stuck() 2026-09-07 so the on-device-poll branch and the fresh-episode branch reach the
        fallback by the same path instead of duplicating the request/flag/_upd trio."""
        # FR-1800-003: say so whenever data leaves the device. The voice path did; this one
        # sent sonar/pose/history to the cloud with no notice at all.
        import privacy as _p; _p.note_cloud_send(self.display,self.voice if self.voice.available else None,
                                                  'my situation')
        self.cloud_ai.request_async(self._last_stuck_prompt,system=_MOTION_SYSTEM,
                                     schema=_MOTION_SCHEMA,history=self._stuck_history)
        self._claude_pending=True
        self._upd('stuck','Escalated to Claude...',d,tilt)

    def _apply_ai_motion(self,result,d,tilt,source):
        """Execute motion decision from AI (Hailo or Claude)."""
        payload=result.payload if(result.parse_success and isinstance(result.payload,dict)) else {}
        cmd=payload.get('action','stop')
        dur=float(payload.get('duration',1.0))
        spd=float(payload.get('speed',config.SPEED_SLOW))
        reason=payload.get('reason','no reason given')
        self._last_action=cmd
        log.info(f'{source} decision: action={cmd} duration={dur}s speed={spd} reason="{reason}"')
        if cmd in('forward','reverse','turn_left','turn_right','stop','wait'):
            move_cmd='stop' if cmd=='wait' else cmd
            self.safety.request(move_cmd,spd,dur); self._claude_move_pending=True
        else:
            self.safety.stop(); self._stuck_count=0; self._go('ROAM')

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
            elif getattr(self,'faces',None) is not None:
                self.faces.set_scanning(False)   # FR-2100: face scans run from IDLE only
            # Hooked here rather than in _stuck() because _go() fires exactly once on entry --
            # _stuck() runs every tick while stuck, which would be ~20Hz of email.
            if state=='STUCK': self._send_stuck_alert()

    def _check_motor_rail(self):
        """Partial software observability for a motor-power cut (E-stop / SW-M). Returns a short
        status string when power looks lost, else ''.

        G-1 says the E-stop is invisible to software because there's no sense line. That's true
        for the arm rail, but NOT for motors: INA260 0x45 is wired inline on the +12V motor bus
        (Master Hardware Design §16.4), so a cut collapses the voltage it reads. This turns a
        silent failure -- commanding motors into dead controllers -- into a logged, visible one.

        DETECTION ONLY by deliberate choice: no stop, no fault, no state change. See
        config.MOTOR_RAIL_MIN_V for why escalation is not wired up yet."""
        try:
            # 'bus_12v' (0x45), NOT 'arm_6v'. Until 2026-09-15 this read the rail then named
            # 'motor', which was the 6V ARM monitor -- so a real motor cut left it at 6.04V and
            # went undetected, while arm-servo droop past the 6.0V threshold raised false ones.
            v=self.current.rail('bus_12v')['voltage_v']
        except Exception:
            return ''  # monitor itself unreadable -- _check_health() owns that, not this
        now=time.time()
        if v>=config.MOTOR_RAIL_MIN_V:
            if self._motor_rail_lost:
                log.warning(f'Motor rail power RESTORED ({v:.2f}V)')
            self._motor_rail_low_since=None; self._motor_rail_lost=False
            return ''
        if self._motor_rail_low_since is None:
            self._motor_rail_low_since=now; return ''
        if now-self._motor_rail_low_since<config.MOTOR_RAIL_GRACE_S:
            return ''
        if not self._motor_rail_lost:
            self._motor_rail_lost=True
            log.error(f'MOTOR POWER LOST — +12V motor bus reads {v:.2f}V (E-stop or SW-M cut?). '
                      f'Motion commands will have no effect until power returns.')
        return f'MOTOR POWER LOST ({v:.2f}V)'

    def _check_arm_current(self):
        """FR-700-001: release the arm when the 6V arm rail stays above ARM_CURRENT_LIMIT_A for
        ARM_CURRENT_LIMIT_S. config.py has asked for this since 2026-09-17 -- a servo stalled
        against Willy's top held ~8A and was destroyed -- and nothing read the limit.

        Runs every tick, so it covers every arm motion (wave, grasp, stow) rather than living
        inside one movement loop. A released arm goes limp and can fall: that is the lesser harm
        than a cooked servo, and it is what config.py specifies."""
        if self.arm.released: self._arm_over_since=None; return
        try: amps=self.current.rail('arm_6v')['current_a']
        except Exception: return
        if amps<=config.ARM_CURRENT_LIMIT_A:
            self._arm_over_since=None; return
        now=time.time()
        if self._arm_over_since is None:
            self._arm_over_since=now; return
        if now-self._arm_over_since>=config.ARM_CURRENT_LIMIT_S:
            self._arm_over_since=None
            self.arm.release()
            log_event(log,'ARM_OVERCURRENT',severity='error',subsystem='arm',status='released',
                      amps=f'{amps:.2f}',limit_a=config.ARM_CURRENT_LIMIT_A,
                      limit_s=config.ARM_CURRENT_LIMIT_S)
            if self.voice.available: self.voice.speak('My arm was straining, so I let it go limp.')

    def _check_sonar_channels(self):
        """FR-800-004: report a dead sonar channel instead of letting it sit silently at 0.0.
        Debounced (2026-10-02, after the first live run logged 46 events in two minutes from
        one flapping channel): a channel is reported failed after SONAR_FAULT_DEBOUNCE_S of
        continuous failure and cleared after the same of continuous health. Logs on those
        transitions only; the status prefix in _upd() shows the confirmed set."""
        try: now_failed=dict(self.sonars.failed_channels)
        except Exception: return
        now=time.time(); deb=config.SONAR_FAULT_DEBOUNCE_S
        for name in ('front','left','right','rear'):   # rear: Pico B b-0.2, 2026-10-10
            bad=name in now_failed
            since=self._sonar_edge.get(name)
            confirmed=name in self._sonar_failed
            if bad==confirmed:
                self._sonar_edge.pop(name,None); continue
            if since is None:
                self._sonar_edge[name]=now; continue
            if now-since<deb: continue
            self._sonar_edge.pop(name,None)
            if bad:
                self._sonar_failed[name]=now_failed[name]
                log_event(log,'SONAR_FAULT',severity='error',subsystem=f'sonar_{name}',
                          status='failed',reason=now_failed[name],held_s=deb)
            else:
                self._sonar_failed.pop(name,None)
                log.info(f'Sonar {name} ranging again ({deb:.0f}s clean)')

    def _check_overcurrent(self):
        """FR-200-002: returns a reason when a rail has held above OVERCURRENT_LIMIT_A for
        OVERCURRENT_S, else ''. Undervoltage had the battery ladder; overcurrent had nothing."""
        now=time.time()
        for rail,limit in config.OVERCURRENT_LIMIT_A.items():
            try: amps=self.current.rail(rail)['current_a']
            except Exception: continue
            if amps<=limit:
                self._oc_since.pop(rail,None); continue
            t0=self._oc_since.setdefault(rail,now)
            if now-t0>=config.OVERCURRENT_S:
                self._oc_since.pop(rail,None)
                log_event(log,'OVERCURRENT',severity='error',subsystem=rail,status='stopped',
                          amps=f'{amps:.2f}',limit_a=limit,hold_s=config.OVERCURRENT_S)
                return f'overcurrent on {rail}: {amps:.1f}A > {limit}A'
        return ''

    def _check_r5(self):
        """Encoder rail (R5) below Pico A's warning threshold. DETECTION ONLY -- owner decision
        2026-10-01: warn and name the cause, never a stop. Returns a status string or ''.

        R5 powers the six Hall encoders and nothing else. When it sags they stop counting, and
        what the rover sees is six wheels reporting zero -- the 2026-08-25 failure looked exactly
        like dead channels. _check_stall() and _check_health() still stop motion if that
        happens; this exists so the stop says "encoder rail" instead of blaming the wheels."""
        low=bool(self.encoders.r5_low)
        if not low:
            if self._r5_low:
                log.info(f'Encoder rail R5 recovered ({self.encoders.r5_millivolts} mV)')
            self._r5_low_since=None; self._r5_low=False
            return ''
        now=time.time()
        if self._r5_low_since is None:
            self._r5_low_since=now; return ''
        if now-self._r5_low_since<config.ENCODER_R5_GRACE_S:
            return ''
        mv=self.encoders.r5_millivolts
        if not self._r5_low:
            self._r5_low=True
            log_event(log,'R5_LOW',severity='warning',subsystem='encoders',status='low',mv=mv)
            log.warning(f'Encoder rail R5 LOW ({mv} mV) -- encoder counts, stall detection and '
                        f'odometry are suspect until it recovers')
        return f'R5 LOW ({mv} mV)'

    def _stall_reason(self,wheels):
        """The stop reason for a stall. Names R5 when the encoder rail is low, because then
        "these wheels read zero" is most likely the rail, not the wheels."""
        if self._r5_low:
            return (f'encoder rail R5 low ({self.encoders.r5_millivolts} mV) -- '
                    f'{wheels} reading zero is likely the rail, not the wheels')
        return f'wheel stall: {wheels}'

    def _thermal_tick(self):
        """M-009. Visibility only: logs, and says once when he reaches HOT or the fan stops.
        Never touches motion -- the Pi 5 firmware throttles itself."""
        try: level=self.thermal.poll(time.time())
        except Exception: return
        if level=='hot':
            self._say(f"My processor is running hot, {self.thermal.temp_c:.0f} degrees.")
        if self.thermal.fan_stopped and not self._fan_warned:
            self._fan_warned=True
            self._say("My cooling fan has stopped.")
        elif not self.thermal.fan_stopped:
            self._fan_warned=False

    def _rear_cm(self):
        """Rear clearance for the safety gate: the rear ToF, pulled to 0 when the rear camera sees
        a person or pet close behind while reversing. The camera can only ever ADD a stop."""
        rear=self.sonars.rear_cm()
        self._rear_watch=(getattr(self.safety,'last_action','stop')=='reverse')
        try: self.rear_cam.close_if_idle()
        except Exception: pass
        if (self._rear_watch and self._rear_block
                and time.monotonic()-self._rear_block_t<config.REAR_CAM_DETECT_S*4):
            return 0.0
        return rear

    def _rear_watch_loop(self):
        """Rear detection OFF the tick thread: a detection goes through the Hailo server and can
        wait behind a 2.2 s prompt read, which the tick must never do. Runs only while reversing."""
        from vision import rear_person_close
        while self._rear_thread_on:     # not _running: that is False until run() starts
            if not self._rear_watch:
                self._rear_block=False; time.sleep(0.1); continue
            try: near=rear_person_close(self.rear_cam.detect())
            except Exception: near=False
            if near!=self._rear_block:
                (log.warning if near else log.info)(
                    'Rear camera: someone close behind -- reversing stopped' if near else 'Rear camera: clear behind')
            self._rear_block=near; self._rear_block_t=time.monotonic()
            time.sleep(config.REAR_CAM_DETECT_S)

    def _retention_sweep(self):
        """FR-1800-004 / FR-1900-010: enforce DATA_RETENTION_DAYS. Both purge functions existed
        and nothing called them; privacy.purge_expired() (log files) was added 2026-10-08. Runs from IDLE, at most once a day; the first run is at the
        first IDLE tick after start."""
        now=time.time()
        if now-self._retention_t<86400: return
        self._retention_t=now
        try: self.memory.purge_expired()
        except Exception: log.warning('Retention purge of memory.db failed',exc_info=True)
        # The rotating log is capped by SIZE (LOG_MAX_BYTES x LOG_BACKUP_COUNT); this adds the
        # TIME cap FR-1800-004 asks for. Rotated backups only -- never the live file.
        try: privacy.purge_expired(config.WILLY_LOG_ROOT,pattern=f'{config.LOG_FILE}.*')
        except Exception: log.warning('Retention purge of the logs failed',exc_info=True)

    def _battery_reading_disputed(self):
        """True when the reading a halt would act on cannot be trusted. A halt powers the Pi off.

        WHICH READING IS THE AUTHORITY (made explicit 2026-10-07 after an outside review found
        this check had silently become a no-op):
          - Bus LIVE: battery_volts IS the +12V bus INA260 (+BUS_TO_PACK_DROP_V), since b47f7d7.
            The comparison below is then only a consistency guard -- it fires if that wiring is
            ever undone. The 2026-10-01 incident (stale divider scale read 11.37V as 8.53V, rover
            walked to SHUTDOWN) cannot recur this way, because the divider is not being read.
          - Bus DEAD (motor switch off, base off): battery_volts falls back to the ADS1115
            divider, the ONLY reading left. It is disputed when the cross-check last caught the
            divider disagreeing with the bus (_bat_xcheck_flagged, kept while the bus is down).
            2026-10-06/07 the divider read 7.2V and then 15.4V on a 12V pack: halting -- or not
            halting -- on that would be acting on a number already known to be wrong."""
        try:
            bus=_bus_volts(self.current)
        except Exception:
            bus=0.0
        if bus>=config.MOTOR_RAIL_MIN_V:
            return abs(self.adc.battery_volts-bus)>config.BAT_CROSSCHECK_MAX_DIFF_V
        return getattr(self,'_bat_xcheck_flagged',False)

    def _battery_halt(self,reason,bat_v,threshold,d,tilt):
        """FR-200-004/005: the FR-900-005 graceful halt, once the reading has stayed under
        `threshold` for BAT_HALT_CONFIRM_S with the rover stopped, and is not disputed."""
        now=time.time()
        if self._battery_reading_disputed():
            self._bat_halt_since=None
            self._upd('lowbatt',f'BATTERY {bat_v:.2f}V disputed by the bus monitor — NOT shutting down',d,tilt)
            return
        if bat_v>=threshold or self._bat_halt_since is None:
            self._bat_halt_since=now   # first tick, or the sag recovered: (re)start the clock
        left=config.BAT_HALT_CONFIRM_S-(now-self._bat_halt_since)
        if left<=0 and not self._shutdown_after_stop:
            log_event(log,'BATTERY_HALT',severity='error',subsystem='battery',status=reason,
                      volts=f'{bat_v:.2f}',threshold=threshold)
            self._begin_shutdown(reason)
        self._upd('lowbatt',f'BATTERY {bat_v:.2f}V — {reason}, shutting down'
                  +(f' in {left:.0f}s' if left>0 else ''),d,tilt)

    def _check_battery_crosscheck(self):
        """Compare the ADS1115 divider against the +12V bus INA260. DETECTION, plus one effect.

        AUTHORITY (corrected 2026-10-07; this said "the divider is the AUTHORITY", untrue since
        b47f7d7): while the bus is live, battery_volts follows the BUS, and the divider is only the
        fallback for a dead bus (motor cut, base off) -- the one case where the pack-side divider
        still reads and the bus does not. So this check is about that FALLBACK: when the two
        disagree, the divider is suspect, the face says so, and _battery_reading_disputed() will
        not let a dead-bus halt act on the divider alone while the flag stands.

        Why it exists: on 2026-09-15 the divider went open and read 0.09V while the bus read
        10.97V, for hours, with nothing comparing them. That particular fault was caught by
        accept_battery_raw()'s implausibility floor. The one this catches is the fault that
        CLEARS that floor -- a divider reading 7.5V from an 11.2V pack is perfectly plausible,
        gets adopted, and walks the tier ladder to a shutdown nobody ordered.

        DELIBERATELY SILENT WHEN THE BUS IS DOWN. Per §2.1's P3 row the bus monitor sits
        downstream of SW-M, so throwing the motor cut collapses it to ~0V. Comparing then would
        turn every E-stop into "your battery sensor is lying". _check_motor_rail() already owns
        that case. This also makes the check correct whichever side of SW-M that monitor turns
        out to be on -- which is not yet confirmed at the bench -- because an implausible bus
        reading is skipped either way rather than being interpreted."""
        if not self.adc.is_healthy:
            return ''   # already stale; _check_health() owns that, and comparing noise is noise
        try:
            bus=_bus_volts(self.current)
        except Exception:
            return ''   # monitor unreadable -- _check_health() owns it
        if bus<config.MOTOR_RAIL_MIN_V:
            self._bat_xcheck_since=None
            return ''   # cut thrown or bus dead: not comparable, see the docstring
        adc=getattr(self.adc,'divider_volts',self.adc.battery_volts)
        diff=abs(adc-bus)
        now=time.time()
        if diff<=config.BAT_CROSSCHECK_MAX_DIFF_V:
            if self._bat_xcheck_flagged:
                log.info(f'Battery sense cross-check back in agreement '
                         f'(ADC {adc:.2f}V vs +12V bus {bus:.2f}V)')
            self._bat_xcheck_since=None; self._bat_xcheck_flagged=False
            return ''
        if self._bat_xcheck_since is None:
            self._bat_xcheck_since=now; return ''
        if now-self._bat_xcheck_since<config.BAT_CROSSCHECK_GRACE_S:
            return ''
        if not self._bat_xcheck_flagged:
            self._bat_xcheck_flagged=True
            log.error(f'BATTERY SENSE SUSPECT — ADS1115 says {adc:.2f}V, +12V bus INA260 says '
                      f'{bus:.2f}V ({diff:.2f}V apart, tolerance '
                      f'{config.BAT_CROSSCHECK_MAX_DIFF_V}V). One of them is wrong. battery_volts follows '
                      f'the bus while it is live (b47f7d7), so the tiers use the bus; the divider is '
                      f'only the fallback for a dead bus, and that fallback is what is suspect. '
                      f'Check the divider feed at V21.')
        return f'BATTERY SENSE SUSPECT (ADC {adc:.2f}V vs bus {bus:.2f}V)'

    def _send_stuck_alert(self):
        # STUCK help-photo (owner request 2026-08-24). Best-effort and fully swallowed: a failed
        # alert must never disturb the fault handling that triggered it.
        if not config.ENABLE_STUCK_ALERT_EMAIL: return
        if not self.email.available: return
        now=time.time()
        # Two independent limits. The cooldown stops a rover that repeatedly re-enters STUCK from
        # mailing on every episode; the session cap stops a genuinely pathological loop from
        # filling an inbox before anyone notices. This codebase has already been bitten by an
        # unthrottled per-tick action (the WAL checkpoint that spun at ~9Hz for an hour), so both
        # are deliberate rather than defensive boilerplate.
        if now-self._stuck_alert_t<config.STUCK_ALERT_COOLDOWN_S: return
        if self._stuck_alert_count>=config.STUCK_ALERT_MAX_PER_SESSION:
            return
        self._stuck_alert_t=now; self._stuck_alert_count+=1
        # FR-2000-008: the camera capture and the SMTP send (15 s timeout) run on their own
        # thread. They used to run here, on the tick thread, inside _go() -- so every fault and
        # obstacle check stalled for as long as the mail server took. Only cheap cached state is
        # read here; the slow part never touches the control loop.
        try:
            pose=self.world_model.get_robot_pose(); d=dict(self.sonars.distances)
            bat=self.adc.battery_volts; episodes=self._stuck_count; n=self._stuck_alert_count
        except Exception:
            log.warning('STUCK alert: could not read state',exc_info=True); return
        def send():
            try:
                photo=self.detector.capture_still()  # None if disabled/privacy-off/failed
                body=(f"I'm stuck and can't work out how to get free.\n\n"
                      f"Pose: x={pose.x:.2f}m y={pose.y:.2f}m heading={pose.heading:.0f}deg\n"
                      f"Sonar: front={d.get('front',999):.0f}cm left={d.get('left',999):.0f}cm "
                      f"right={d.get('right',999):.0f}cm\n"
                      f"Battery: {bat:.2f}V\n"
                      f"Stuck episodes this run: {episodes}\n"
                      f"Alert {n} of {config.STUCK_ALERT_MAX_PER_SESSION} this session.\n\n"
                      f"{'Photo attached from my front camera.' if photo else 'No photo — camera unavailable or privacy-disabled.'}\n\n-- Willie")
                self.email.send_alert('Willie is stuck and needs help',body,image_bytes=photo,
                                       image_name='willy_stuck.jpg')
            except Exception:
                log.warning('STUCK alert email failed',exc_info=True)
        threading.Thread(target=send,name='stuck-alert',daemon=True).start()

    def _upd(self,fs,st,d,tilt,spd=0.0,awaiting_reset=False,offer_override=False):
        # Motor-power loss is prepended to whatever status the caller wanted, rather than given
        # its own state: it is information, not a state change (see _check_motor_rail). Doing it
        # here means every call site surfaces it without each one having to remember to.
        if self._motor_rail_lost: st=f'⚡MOTOR POWER LOST — {st}'
        # Same treatment for a battery-sense disagreement: information, not a state change.
        # It rides in front because a pack reading you cannot trust colours everything else
        # on the face -- the percentage, the tier, the range estimate.
        if self._bat_xcheck_flagged: st=f'⚠BATTERY SENSE SUSPECT — {st}'
        if self._r5_low: st=f'⚠ENCODER RAIL LOW — {st}'
        failed=getattr(self,'_sonar_failed',{})
        if failed: st=f'⚠SONAR {"/".join(sorted(failed)).upper()} FAILED — {st}'
        # FR-1600-004: the 'warn' tier keeps driving, so it is a prefix, not a face state.
        if getattr(self,'_bat_tier','normal')=='warn':
            st=f'🔋BATTERY LOW {self.adc.battery_volts:.1f}V — {st}'
        try: rear=self.sonars.rear_cm()        # B on the status line (owner 2026-10-10)
        except Exception: rear=None
        self.display.update_state(state=fs,status=st,distances=dict(d,rear=rear),tilt=tilt,speed=spd,
                                   awaiting_reset=awaiting_reset,offer_override=offer_override)

    def _roam_allowed(self):
        """Gate on the two unprompted-ROAM triggers (idle timeout, charged-at-dock).

        Owner decision 2026-09-09: Willie asks before wandering off on his own. Returns True only
        once permission has been granted for this session; otherwise it opens the ask as a side
        effect and returns False, so the caller simply does not transition this tick. Both callers
        fire repeatedly (the idle timeout every tick once it trips), which is why the pending and
        cooldown checks come first -- without them he would re-ask 20 times a second.
        """
        if not config.ROAM_PERMISSION_REQUIRED: return True
        if self._roam_permission: return True
        if self._roam_ask_pending: return False
        # Never stack two yes/no questions on the owner: a pending shutdown confirmation already
        # claims the next spoken command, so an ask opened now would have its answer eaten.
        if self._shutdown_pending: return False
        if time.time()<self._roam_ask_next: return False
        self._begin_roam_ask()
        return False

    def _begin_roam_ask(self):
        self._roam_ask_pending=True
        self._roam_ask_deadline=time.time()+config.ROAM_ASK_TIMEOUT_S
        self.display.offer_roam(True)
        log.info('Asking permission to roam.')
        if self.voice.available: self._ask("I would like to go explore. Is that okay?")

    def _end_roam_ask(self,granted):
        # The single exit from an open ask -- granted or not, tapped or spoken or lapsed. Keeping
        # it in one place is what guarantees the panel button is always withdrawn.
        self._roam_ask_pending=False
        self.display.offer_roam(False)
        if granted:
            self._roam_permission=True
            log.info('Roam permission granted for this session.')
            if self.voice.available: self.voice.speak('Thanks. Off I go.')
        else:
            self._roam_ask_next=time.time()+config.ROAM_ASK_COOLDOWN_S

    def _service_roam_ask(self):
        # Called every tick. Handles the two ways an ask ends that are not a spoken reply: the
        # panel tap, and nobody answering at all. A lapse is deliberately silent -- if no one
        # answered, no one is there to hear him announce it either.
        if not self._roam_ask_pending: return
        if self.display.roam_tapped():
            self._end_roam_ask(True); return
        if time.time()>self._roam_ask_deadline:
            log.info('Roam permission ask lapsed unanswered -- will ask again later.')
            self._end_roam_ask(False)

    def _revoke_roam_permission(self):
        # "Stop" ends autonomy, not just the wander in progress. Without this a voice stop would
        # brake him and the idle timeout would send him straight back out 30 seconds later, which
        # is not what anyone means by stop.
        if self._roam_ask_pending: self._end_roam_ask(False)
        if self._roam_permission:
            self._roam_permission=False
            log.info('Roam permission revoked -- he must ask again.')

    def _voice_reset_requested(self):
        # FR-300-003, voice half (owner decision 2026-09-17: reset is a voice command OR a
        # screen tap). A latched fault returns early from _tick() before _drain_voice_commands()
        # ever runs, so the intent has to be pulled out of the queue here rather than waiting for
        # normal dispatch -- otherwise the only way out of a latched fault is the touchscreen.
        #
        # Scans the WHOLE queue, not just the head: a fault can sit latched for minutes while
        # other commands pile up behind it, and the reset must not be stuck behind them. Same
        # once-only contract as display.reset_tapped() -- the entry is removed when consumed.
        # getattr twice: a latched-fault unit test can construct a brain namespace with no
        # voice subsystem at all, and the reset gate must still work from the screen tap.
        q=getattr(getattr(self,'voice',None),'pending_commands',None)
        if q is None: return False
        with q.mutex:
            for i,cmd in enumerate(q.queue):
                if cmd.get('intent')=='reset':
                    del q.queue[i]
                    return True
        return False

    def _await_reset_or_resume(self,fault_desc,d,tilt,cleared_msg):
        # FR-300-003, applied to all faults (owner decision 2026-08-18, not just a future
        # E-stop): once the underlying fault condition has cleared, don't auto-resume -- keep
        # braking and wait for an explicit screen tap. Shared by SENSOR_FAULT/TILT_FAULT/
        # STALL_FAULT below rather than tripled per call site. Returns True if the tap arrived
        # this tick (caller should fall through to normal dispatch); False if still waiting
        # (caller should return without dispatching).
        if self.display.reset_tapped() or self._voice_reset_requested():
            self._go('IDLE'); return True
        self.safety.emergency_stop(f'{fault_desc} cleared, awaiting operator reset')
        self._upd('fault',cleared_msg,d,tilt,awaiting_reset=True)
        return False
