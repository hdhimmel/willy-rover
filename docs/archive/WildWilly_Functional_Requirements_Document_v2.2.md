**Willy Functional Requirements Document (FRD)\
Version 2.2**

# 1. Purpose

This Functional Requirements Document defines the required behavior,
safety functions, control systems, autonomy, mobility, and future
capabilities of the WildWilly robotic platform.

**As-built status pass added 2026-08-09.** This document — not
`WildWilly_Functional_Requirements_Document_v1.1.md` — is the FRD that
matches the current codebase: every FR-ID actually cited in
`/home/hhimmel/rover`'s `.py` files (55 distinct IDs, repo-wide grep)
appears here; `v1.1.md` is missing 50 of those 55 and predates the
entire v2.2 subsystem set (smart home, cloud AI, voice, display
expressions, retrieval, learning, email). An earlier as-built pass
(2026-08-08) was mistakenly applied to `v1.1.md` instead of this file —
a same-named-family versioning trap matching the one already documented
for the two Master Engineering Package files. `v1.1.md` should be
treated as superseded; a note has been added there pointing here. Every
requirement group below now has an "Implementation status" note
verified directly against the current code (not carried over from the
misapplied v1.1.md pass). See `docs/WildWilly_Claude_Fix_Gap_Analysis.md`
and `docs/WildWilly_Subsystem_Status.md` for the software-architecture
detail behind these notes.

# FR-000 Prime Directives (Arbitration Priority Order)

This section establishes a single enforceable priority hierarchy for
brain.py arbitration logic. It does not introduce new capability --- it
orders existing FR-100/200/300/400/500 requirements so that
safety-critical behavior cannot be raced, deferred, or overridden by
task-level logic (navigation, voice interaction, arm control, etc.).
Lower-numbered directives always take precedence over higher-numbered
ones. Added 2026-08-01, v1.2.

  --------------------------------------------------------------------------------
  Priority   Directive           Governs                     Overrides
  ---------- ------------------- --------------------------- ---------------------
  1          E-stop overrides    All motion, immediately,    Every other directive
             everything          regardless of command or    and any in-progress
                                 state                       action
                                                             (FR-300-002/003)

  2          Safety checks gate  No movement until startup   All motion commands
             motion              self-test passes            (FR-100-004)

  3          Power protection    Safe shutdown at critical   Navigation, arm
             supersedes task     battery level, even         tasks, voice
             execution           mid-task                    commands, queued
                                                             actions (FR-200-004)

  4          Motion stays within Software speed limits and   Any higher-level
             enforced limits     steering travel limits are  behavior requesting
                                 hard caps                   motion beyond the cap
                                                             (FR-400-004,
                                                             FR-600-003)

  5          Stalls halt, not    Stall/unexpected-movement   Continued force
             retry blindly       triggers stop-and-report    application
                                                             (FR-500-003)

  6          All other behavior  Navigation, voice           Nothing --- operates
                                 interaction, object         only after Directives
                                 retrieval, arm tasks        1--5 are satisfied
  --------------------------------------------------------------------------------

Acceptance Criteria: brain.py must check Directives 1--5, in order,
before executing any task-level (Directive 6) behavior. A directive
violation (e.g. a queued arm motion executing after E-stop trigger) is a
critical defect, not a tuning issue.

**Implementation status (2026-08-09): DONE for Directives 2-6, with one
hardware gap.** `brain.py::_tick()` checks sensor faults, tilt, and
battery tier in that order, each able to preempt retrieval/mapping/
navigation/voice before Directive 6's FSM dispatch runs -- matches this
table exactly, and the code's own comments cite "FR-000 Directive N" at
each check. Directive 1 (E-stop) is **not software-observable** -- no
GPIO sense pin exists for the physical latching E-stop, so nothing in
`brain.py` can check it; the hardware cut works independently of
software. Directives 2-5 are live-verified as of 2026-08-09 (init,
safety FSM, and battery-shutdown all reconfirmed on a fresh restart);
Directive 6 task-level behavior (voice/retrieval/mapping/navigation)
has not yet been live-verified in motion.

# FR-100 System Startup and Initialization

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-100-001        Automatically     High              Test
                    start control                       
                    software at                         
                    power-up                            

  FR-100-002        Initialize I2C    High              Test
                    bus and connected                   
                    devices                             

  FR-100-003        Run startup       High              Test
                    self-test                           

  FR-100-004        Prevent motion    High              Test
                    until startup                       
                    checks pass                         
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): DONE, live-verified.**
`willy-rover.service` (systemd, `WantedBy=multi-user.target`) auto-starts
`main.py`; `RoverBrain.__init__`/`_self_test()` probes every I2C device
before `INIT->IDLE`; `_motion_enabled` stays `False` until self-test
passes. Live-verified repeatedly, most recently 2026-08-09 across two
restarts picking up this session's commits -- clean init both times.

# FR-200 Power Monitoring and Protection

  --------------------------------------------------------------------------
  Requirement ID    Requirement          Priority          Verification
  ----------------- -------------------- ----------------- -----------------
  FR-200-001        Monitor battery      High              Test
                    voltage, current and                   
                    power                                  

  FR-200-002        Detect undervoltage  High              Test
                    and overcurrent                        
                    conditions                             

  FR-200-003        Warn user before     High              Test
                    critical battery                       
                    level                                  

  FR-200-004        Perform safe         High              Test
                    shutdown at critical                   
                    battery level                          

  FR-200-005        On reaching a        High              Test
                    low-battery                            
                    threshold (below the                   
                    RTH/return-to-home                     
                    threshold, before                      
                    the critical/SAFE                      
                    cutoff), proactively                   
                    initiate the same                      
                    graceful shutdown                      
                    sequence as                            
                    FR-900-005 ---                         
                    including a                            
                    guaranteed memory                      
                    save per FR-1900-011                   
                    --- rather than                        
                    waiting for the                        
                    critical-level                         
                    emergency cutoff in                    
                    FR-200-004, which                      
                    only offers a                          
                    best-effort save                       
  --------------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): PARTIAL, plus one open calibration
bug.** FR-200-001/003/004/005 DONE and live-verified: `ADC` (ADS1115
@0x48) reads battery voltage; three `INA260`s log current/power per
rail; the tier ladder (`config.BAT_WARN/RTH/SAFE/SHUTDOWN_V`, with
hysteresis) warns, proactively return-to-homes at the RTH threshold
with a guaranteed `memory.save_all_now()` (FR-200-005/FR-1900-011), then
controlled-shuts-down at the SHUTDOWN threshold -- reconfirmed live
2026-08-09 (`battery_volts=3.16-3.17V` correctly forced `SHUTDOWN` on a
fresh restart). FR-200-002 is **half-missing**: undervoltage detection
works via the ladder above; overcurrent detection does not exist --
`CurrentMonitor.is_healthy` is read-recency only, no numeric overcurrent
trip threshold exists anywhere in the code. **Open bug, not yet fixed:**
`config.validate()`'s startup self-check (added this session) found
`BAT_FULL_V=11.39` is below `BAT_WARN_V=11.4` -- `battery_pct` (display-
only, never a safety input) could report 100% at a voltage the tier
ladder has already escalated to 'warn'. Owner is taking a real meter
reading to correct the calibration value.

# FR-300 Safety and Emergency Stop

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-300-001        Monitor physical  High              Test
                    E-stop                              
                    continuously                        

  FR-300-002        Disable all       High              Test
                    motion                              
                    immediately on                      
                    E-stop                              

  FR-300-003        Require operator  High              Test
                    reset before                        
                    movement resumes                    

  FR-300-004        Stop robot on     High              Test
                    critical                            
                    controller                          
                    failure                             
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): PARTIAL, with a real gap.**
FR-300-001 is **not satisfiable in software today** -- no GPIO sense pin
exists for the physical E-stop, so nothing in `brain.py` can observe
it; the latching NC mushroom switch cuts the 12V motion bus directly in
hardware, which incidentally satisfies FR-300-002/003 (immediate cut,
manual-latch reset) at the hardware layer only. FR-300-004 is partial:
a process crash/exit triggers `Restart=on-failure`/`RestartSec=5`
(motors de-energize when the process exits) -- but there is still no
configured `WatchdogSec` on the deployed unit (confirmed again
2026-08-09), so a *hang* (not a crash) would not be caught by anything.
Do not describe the physical E-stop as software-observable, and do not
describe a systemd watchdog as configured -- it isn't.

# FR-400 Mobility and Drive Control

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-400-001        Control left and  High              Test
                    right drive                         
                    motors                              
                    independently                       

  FR-400-002        Support forward,  High              Test
                    reverse and                         
                    turning motion                      

  FR-400-003        Ramp speed        High              Test
                    commands smoothly                   

  FR-400-004        Enforce software  High              Test
                    speed limits                        
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): DONE.** `motors.py`'s `DriveBase`
(Adafruit MotorKit, 2x FeatherWing) controls left/right independently;
forward/reverse/turn all implemented; `_ramp_loop()` slew-rate-limits
throttle changes (cited as FR-400-003 in the code's own comment);
`safety.py::approve_motion()` clamps every commanded speed to
`config.SPEED_MAX` before it reaches the motors -- the single
authoritative gate (a static-scan regression test, added this session,
now proves no other module calls `DriveBase` motion methods directly).

# FR-500 Encoder and Speed Control

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-500-001        Read wheel        High              Test
                    encoders                            

  FR-500-002        Calculate speed   High              Test
                    and distance                        

  FR-500-003        Detect stalls and High              Test
                    unexpected                          
                    movement                            

  FR-500-004        Maintain          High              Test
                    closed-loop speed                   
                    control                             
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): PARTIAL.** FR-500-001/002 DONE:
`Encoders` (MCP23017 @0x27 polling) reads quadrature counts;
`odometry.py::Odometry.update()` converts them into a dead-reckoning
`Pose` (speed/distance). FR-500-003 is a **real gap, still dead code**:
`Encoders.stalled()` exists but has zero call sites anywhere in
production code (confirmed again this session via repo-wide grep).
FR-500-004 is **not implemented**: odometry is a passive read logged
every tick with no motor consequence -- `navigation.py::Navigator` does
close a heading-correction loop (bearing-to-waypoint steering), but
that's directional, not speed control; there is no closed-loop *speed*
control anywhere in the codebase.

# FR-600 Steering Control

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-600-001        Control steering  High              Test
                    servo                               

  FR-600-002        Maintain          High              Test
                    calibration                         
                    settings                            

  FR-600-003        Limit steering    High              Test
                    travel                              

  FR-600-004        Support manual    High              Test
                    override                            
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): PARTIAL.** FR-600-001/002/003
DONE: `Steering` (PCA9685 @0x42) controls all 6 channels; `config.py`
holds per-servo pulse-width calibration; travel is limited to the
configured range. FR-600-004 (manual override) is **not built** -- no
teleop/RC input path exists anywhere in the codebase (see FR-900); the
only external control surface is voice commands (when
`ENABLE_VOICE=True` -- see FR-1500's status note on why that's currently
`False` on this unit), which is not a manual override during autonomy.

# FR-700 Robotic Arm Control

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-700-001        Control all arm   High              Test
                    joints                              

  FR-700-002        Support preset    High              Test
                    positions                           

  FR-700-003        Enforce joint     High              Test
                    limits                              

  FR-700-004        Stop arm during   High              Test
                    E-stop                              
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): PARTIAL, with a real gap.**
FR-700-001/002 DONE: `arm.py`'s `Arm` (PCA9685 @0x43) controls all
joints; `retrieval_task.py` sequences fixed preset positions -- not full
inverse kinematics (no per-joint calibration exists, honestly flagged
in the code's own comments). FR-700-003 (joint limits) is enforced via
configured pulse-width ranges, same mechanism as steering. **FR-700-004
is still not implemented**: no fault path in `brain.py` (tilt fault,
sensor fault, battery shutdown) repositions or freezes the arm -- only
`safety.py::SafetyController.emergency_stop()` brakes the *drive base*
(`self.steering.center_all(); self.arm.center_all()` runs once at
startup self-test, not on any later fault). The arm holds whatever PWM
position it was last commanded to through any live fault.

# FR-800 Sensor Systems

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-800-001        Read IMU          High              Test
                    orientation data                    

  FR-800-002        Read sonar        High              Test
                    obstacle data                       

  FR-800-003        Detect excessive  High              Test
                    tilt                                

  FR-800-004        Report sensor     High              Test
                    health                              
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): DONE, live-verified.**
`sensors.py::IMU` (BNO085 @0x4A, 100Hz) reports orientation;
`SonarArray` (3x HC-SR04) reports obstacle ranges; `TILT_FAULT` FSM
state trips at `config.IMU_TILT_LIMIT`; `brain.py::_check_health()`
reports IMU/encoder/current/battery-ADC health every tick and escalates
a sustained (>1s) fault to `SENSOR_FAULT` + `emergency_stop()`. Live-
verified repeatedly, most recently on the 2026-08-09 restarts.

# FR-900 Manual Operations

  ----------------------------------------------------------------------------------
  Requirement ID    Requirement                  Priority          Verification
  ----------------- ---------------------------- ----------------- -----------------
  FR-900-001        Accept remote operator       High              Test
                    commands                                       

  FR-900-002        Display robot status         High              Test

  FR-900-003        Stop on communication loss   High              Test

  FR-900-004        Allow emergency override     High              Test

  FR-900-005        Accept a commanded shutdown  High              Test
                    (voice or manual) and                          
                    initiate a graceful shutdown                   
                    sequence, distinct from the                    
                    FR-200-004                                     
                    emergency/critical-battery                     
                    shutdown                                       
  ----------------------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): MOSTLY MISSING, and FR-900-005 is
also not built.** This group describes a remote-operator capability
that does not exist -- no teleop/RC/remote-command receive path was
found anywhere (repo-wide grep, confirmed again this session).
FR-900-002 is the one partial exception: `display.py` shows live
state/status on the rover's own local screen, but that's a local HUD,
not remote operator display. FR-900-001/003/004 are unbuilt: no remote
commands to accept, no communication-loss detection (nothing to lose),
no remote emergency-override path. **FR-900-005 (accept a voice/manual
commanded graceful shutdown) is also unbuilt** -- confirmed via grep:
`voice.py` only pattern-matches the word "shutdown" as part of its
FR-1500-010 safety-tone-forcing regex (to keep TTS neutral when
*describing* a shutdown), there is no voice intent that *triggers* one.
The only shutdown paths today are the FR-200-004/005 battery-tier ones
and `systemctl stop` from outside the process. This matches M-011
(Remote administration), also not built -- see the M-table status below.

# FR-1000 Autonomous Navigation

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1000-001       Navigate without  High              Test
                    operator input                      

  FR-1000-002       Avoid obstacles   High              Test

  FR-1000-003       Maintain planned  High              Test
                    route                               

  FR-1000-004       Transfer control  High              Test
                    back to operator                    
                    on demand                           
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): DONE at milestone-1 scope, not
live-verified for motion.** `navigation.py::Navigator` resolves and
drives routes (known waypoints, room-graph shortest-path via
`networkx`, or straight-line fallback) through a `NAVIGATE` FSM state;
obstacle avoidance exists both in the base reactive FSM (`ROAM`/`AVOID`)
and as `Navigator`'s own self-contained copy of that logic. Explicitly
milestone-1, not SLAM: dead-reckoning odometry only, no room-
identification heuristic, no obstacle-aware global planner beyond the
straight-line fallback. Voice `stop`/similar commands would return
control to the operator once voice is enabled (see FR-1500's status).
**Caveat, unchanged since 2026-08-08 and reconfirmed 2026-08-09:** init/
safety/battery-shutdown are live-verified on hardware; nothing has yet
commanded the drive base live -- `NAVIGATE`/obstacle avoidance remain
sim-tested only, not yet hardware-verified in motion.

# FR-1100 Diagnostics and Logging

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1100-001       Monitor subsystem High              Test
                    health                              

  FR-1100-002       Record warnings   High              Test
                    and faults                          

  FR-1100-003       Maintain          High              Test
                    timestamped logs                    

  FR-1100-004       Provide           High              Test
                    diagnostic test                     
                    mode                                
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): DONE.** `brain.py::_check_health()`
monitors IMU/encoders/current/battery-ADC every tick;
`logsetup.py::log_event()` tags real fault/abort sites with structured
`EVENT=<NAME>` markers (`IMU_FAULT`, `LOW_BATTERY`, `OBSTACLE_STOP`,
`NAVIGATION_ABORT`, `AI_TIMEOUT`, and -- added this session --
`AI_REQUEST`/`AI_RESULT`/`AI_REJECTED`/`AI_UNAVAILABLE` and
`TICK_OVERRUN`); a rotating file handler keeps timestamped persistent
logs; `diagnostics.py` provides the self-test/diagnostic mode.
`ESTOP_ACTIVE`/`WATCHDOG_FAULT` are deliberately untagged -- the first
has no GPIO sense pin to observe, the second can't self-log since the
process is being killed by the time it would fire (moot anyway, since
no watchdog timeout is configured -- see FR-300).

# FR-1200 Mobility Intelligence and Stair Navigation

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1200-001       Detect stairways  High              Test

  FR-1200-002       Select floor or   High              Test
                    stair mode                          

  FR-1200-003       Monitor traction  High              Test
                    and tilt during                     
                    climbing                            

  FR-1200-004       Support           High              Test
                    multi-floor                         
                    navigation                          
                    through the world                   
                    model                               
  -----------------------------------------------------------------------

**Implementation status (2026-08-09): MISSING, confirmed and expected.**
FR-1200-001 through FR-1200-004 have zero code presence anywhere
(`grep -rni "stair"` across every `.py` file, excluding venv, returns no
hits in `brain.py`/`world_model.py`/`navigation.py`/`safety.py`; no
`STAIR_*` FSM state exists; `world_model.py`'s `Room` schema has no
floor/level concept at all). Matches the project's own documented
decision: `docs/WildWilly_Claude_Fix_Implementation_Plan.md` explicitly
says not to implement this yet, and M-006 below was reclassified to a
stretch goal on 2026-07-18. Clean, intentional deferral, not a
partially-started feature.

# FR-1300 Smart Home Integration (Google Home)

ASSUMPTION (flag for review): direction is Willie sending commands OUT
to existing Google Home devices (e.g. \"turn on the lights\"), not
Willie being controlled BY Google Home/Assistant. This is the more
common use case for a mobile assistant robot but has not been confirmed
with the owner --- verify before implementation. Added 2026-08-01, v1.3.
Not yet in scope for any CC session to date.

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1300-001       Discover and      Medium            Test
                    enumerate Google                    
                    Home devices on                     
                    the local network                   

  FR-1300-002       Send on/off, dim, Medium            Test
                    and scene                           
                    commands to                         
                    discovered                          
                    devices                             

  FR-1300-003       Report device     Medium            Test
                    command                             
                    success/failure                     
                    back to the user                    
                    (voice or                           
                    display)                            

  FR-1300-004       Operate           High              Test
                    independently of                    
                    smart-home                          
                    connectivity ---                    
                    loss of network                     
                    access to Google                    
                    Home must not                       
                    affect core                         
                    mobility, safety,                   
                    or FR-000                           
                    directives                          

  FR-1300-005       Authenticate to   High              Test
                    Google Home using                   
                    Willie\'s own                       
                    dedicated Google                    
                    account (not the                    
                    owner\'s personal                   
                    account);                           
                    credentials                         
                    stored securely                     
                    on-device per                       
                    FR-2000                             
  -----------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): PARTIAL --- built and disabled,
plus one real wiring gap.** `smart_home.py::SmartHomeClient` implements
device discovery (FR-1300-001) and on/off/dim/scene commands that
report success/failure back through `voice.py` (FR-1300-002/003).
FR-1300-004 (works independently of connectivity) is real: missing
credentials or a network error disable the feature/return an error
tuple rather than raising, and nothing in `safety.py`/`brain.py`'s
Directive 1-5 path references this class at all. The real gap:
**`discover_devices()` is never called from anywhere in the codebase**
--- no caller ever populates an `entity_id` for `send_command()`, so the
discovery half is dead code today. FR-1300-005's dedicated-account
design is sound, but the actual backend is a **Home Assistant REST
bridge, not the real Google Home/Home Graph API** (documented in the
module's own comment --- Google doesn't expose third-party control of
existing Home devices). `ENABLE_SMART_HOME=False` by default with no
credentials file present on this unit; never exercised end-to-end.

# FR-1400 Cloud AI Assistance (Gemini Fallback)

ASSUMPTION (flag for review): Gemini is a FALLBACK path used only when
the onboard Llama 3.2 3B cannot adequately handle a request --- not a
primary dependency. This preserves the existing local-first architecture
(faster-whisper, Llama 3.2 3B, Piper TTS all run onboard); Gemini would
be Willie\'s first cloud-dependent capability if implemented as anything
more than an optional fallback. Verify this priority with the owner
before implementation. Added 2026-08-01, v1.3. Not yet in scope for any
CC session to date.

**CORRECTION (2026-08-09): this assumption is stale --- the FALLBACK
provider that got built is Anthropic Claude, not Gemini.**
`config.py:199-204`\'s own comment documents why: Willie\'s dedicated
Google account\'s Gemini API key hit a persistent zero free-tier quota
even with billing linked (a Google-side provisioning gap, parked
2026-08-06), so the fallback was swapped to Anthropic\'s API instead,
reusing the same `ANTHROPIC_API_KEY` already configured for `brain.py`\'s
STUCK-state motion decisions. The fallback-not-primary-dependency
priority this ASSUMPTION cared about is still honored (see the
implementation-status note below) --- only the specific provider
changed. FR-1400-005\'s "same dedicated Google account as FR-1300-005"
authentication requirement is now inaccurate as literally written:
Anthropic auth is an unrelated API key, not a Google-account credential.

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1400-001       Detect when a     Medium            Test
                    request exceeds                     
                    onboard Llama 3.2                   
                    3B capability or                    
                    confidence                          
                    threshold                           

  FR-1400-002       Route qualifying  Medium            Test
                    requests to                         
                    Gemini only with                    
                    active internet                     
                    connectivity                        

  FR-1400-003       Fall back to      High              Test
                    onboard-only                        
                    response (with                      
                    limitation                          
                    notice) when                        
                    cloud access is                     
                    unavailable                         

  FR-1400-004       Never allow cloud High              Test
                    AI response                         
                    latency or                          
                    failure to block                    
                    or delay FR-000                     
                    Directives 1-5                      
                    (E-stop, safety                     
                    checks, power                       
                    protection,                         
                    motion limits,                      
                    stall handling)                     

  FR-1400-005       Authenticate to   High              Test
                    Gemini using the                    
                    same dedicated                      
                    Google account as                   
                    FR-1300-005 (not                    
                    the owner\'s                        
                    personal                            
                    account);                           
                    credentials                         
                    stored securely                     
                    on-device per                       
                    FR-2000                             
  -----------------------------------------------------------------------

**Implementation status (2026-08-09): PARTIAL, with a confirmed spec-
vs-implementation mismatch --- see the CORRECTION note above the
ASSUMPTION callout for the Gemini-to-Claude swap itself.** Sound parts:
FR-1400-001 (confidence-threshold routing, `LOCAL_LLM_CONFIDENCE_FLOOR=0.55`),
FR-1400-003 (graceful onboard-only fallback, never guesses), and
FR-1400-004 (never blocks Directives 1-5 --- `ai_provider.py`'s
`AIProvider` runs every cloud call on its own worker thread, `brain.py`'s
`_stuck()` polls non-blockingly) are all genuinely satisfied. FR-1400-002
(only with active connectivity) is satisfied reactively, not
proactively --- there is no pre-flight connectivity check; a request is
attempted and a `URLError`/`TimeoutError` is caught and treated as
unavailable, which is functionally equivalent but worth being precise
about.

# FR-1500 Voice Interaction

Covers the onboard voice pipeline already built into the
hardware/software stack (faster-whisper STT, openwakeword wake-word
detection, Llama 3.2 3B for command interpretation, Piper TTS for speech
output) but never previously captured as a functional requirement ---
M-002 in the traceability matrix referenced this capability with no FR
section behind it until now. Added 2026-08-02, v1.4.

  ----------------------------------------------------------------------------
  Requirement ID    Requirement            Priority          Verification
  ----------------- ---------------------- ----------------- -----------------
  FR-1500-001       Detect wake word via   High              Test
                    openwakeword before                      
                    processing any spoken                    
                    audio as a command                       

  FR-1500-002       Transcribe speech to   High              Test
                    text via onboard                         
                    faster-whisper (no                       
                    cloud dependency for                     
                    basic STT)                               

  FR-1500-003       Interpret transcribed  Medium            Test
                    commands via onboard                     
                    Llama 3.2 3B, falling                    
                    back per FR-1400 only                    
                    when configured                          

  FR-1500-004       Synthesize and play    Medium            Test
                    spoken responses via                     
                    Piper TTS                                

  FR-1500-005       Gracefully handle      Medium            Test
                    unrecognized or                          
                    low-confidence speech                    
                    (ask for repeat, do                      
                    not guess and act)                       

  FR-1500-006       Never allow voice      High              Test
                    pipeline processing                      
                    latency or failure to                    
                    delay or block FR-000                    
                    Directives 1-5                           

  FR-1500-007       Voice commands that    High              Test
                    would trigger motion                     
                    must still pass all                      
                    FR-000 gating                            
                    (self-test, E-stop                       
                    state, power state)                      
                    before execution                         

  FR-1500-008       Support an optional    Low               Test
                    playful/humorous                         
                    response tone (e.g.                      
                    funny, silly) for                        
                    non-critical                             
                    conversational                           
                    exchanges, distinct                      
                    from Willie\'s default                   
                    neutral tone                             

  FR-1500-009       Support a bashful/shy  Low               Test
                    response tone for                        
                    specific                                 
                    conversational                           
                    triggers (e.g. being                     
                    complimented, asked                      
                    personal questions)                      

  FR-1500-010       Personality tone       High              Test
                    (funny, silly,                           
                    bashful, or any                          
                    non-neutral tone) MUST                   
                    NOT be applied to                        
                    safety-critical                          
                    communications -                         
                    E-stop status, fault                     
                    reports,                                 
                    low-battery/shutdown                     
                    warnings, or command                     
                    confirmations for                        
                    motion. These always                     
                    use a clear, neutral,                    
                    unambiguous tone                         
                    regardless of                            
                    personality mode                         
  ----------------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): PARTIAL. Core pipeline is real;
the personality-tone system (FR-1500-008/009) is unused plumbing, not a
working capability.** FR-1500-001-004 are implemented and correctly
wired: openwakeword (currently the bundled "Hey Jarvis" model as a
documented placeholder for an untrained "Hey Willie" wake word --- see
[[project_rover_wakeword_training]]), faster-whisper STT, local Llama
3.2 3B with FR-1400 fallback only below the confidence floor, and Piper
TTS. FR-1500-005/006/007 (never guess, non-blocking, Directive-gated)
are all correctly enforced --- `speak()` only enqueues to a
dedicated-thread queue, and every motion-triggering voice intent is
queued for `brain.py` to drain and gate through Directives 1-5, never
executed directly by `voice.py`. **FR-1500-008/009 (playful/bashful
tone) are effectively not implemented**: `speak(text, tone=...)` accepts
a `tone` argument and `_SAFETY_PATTERN` correctly forces it to
`'neutral'` for safety-shaped text (satisfying FR-1500-010's guard) ---
but after that check `tone` is never actually used for anything; no
caller in the codebase ever requests `'funny'`/`'silly'`/`'bashful'`,
only the default `'neutral'`. The guard rail is real and correctly
built; the capability it guards doesn't exist yet. **Operational update
(2026-08-09): `ENABLE_VOICE` flipped to `True` on owner's go-ahead** ---
model files were confirmed present (dated 2026-08-06, the "not
downloaded yet" comment was stale) and all required packages import
cleanly. Flipping it on surfaced one real, now-fixed gap:
`WhisperModel(config.WHISPER_MODEL_SIZE, ...)` made a live HTTP request
to huggingface.co at construction time on every startup, even with the
model already cached locally --- `WHISPER_MODEL_SIZE` is a hub name, not
a filesystem path like the other three models, so without
`local_files_only=True` it phones home to check the cached revision.
This violated FR-1500-002's "no cloud dependency for basic STT" and
added a startup network dependency; fixed in `voice.py` by passing
`local_files_only=True` (the cache already exists locally). Not yet
live-verified end-to-end on hardware --- wake phrase is still the "Hey
Jarvis" placeholder, not "Hey Willie".

# FR-1600 Facial Expression / Display Feedback

Covers runtime use of the RPi Touch Display 2 (already wired, §7.x) for
expressive/status feedback during operation --- distinct from
FR-900-002\'s status telemetry display. Not previously specified
anywhere in the FRD or master doc. Added 2026-08-02, v1.4.

  --------------------------------------------------------------------------------
  Requirement ID    Requirement                Priority          Verification
  ----------------- -------------------------- ----------------- -----------------
  FR-1600-001       Display a distinct visual  Medium            Test
                    state while idle/listening                   
                    vs. actively processing a                    
                    command                                      

  FR-1600-002       Display a distinct visual  Low               Test
                    state while speaking (TTS                    
                    output active)                               

  FR-1600-003       Display a clear,           High              Test
                    unambiguous visual state                     
                    when a safety fault or                       
                    E-stop is active                             

  FR-1600-004       Display a distinct visual  High              Test
                    state during low-battery                     
                    warning and critical                         
                    shutdown (FR-200-003/004)                    

  FR-1600-005       Facial/expression          High              Test
                    rendering must never                         
                    consume enough CPU/GPU to                    
                    delay FR-000 Directives                      
                    1-5 or the FR-100 startup                    
                    self-test                                    

  FR-1600-006       Display a \'bashful\'      Low               Test
                    expression (e.g. brief                       
                    look-away animation) for                     
                    the same conversational                      
                    triggers as FR-1500-009                      

  FR-1600-007       Display a                  Low               Test
                    \'silly/playful\' idle                       
                    animation that cycles                        
                    occasionally during                          
                    extended periods with no                     
                    interaction, to convey a                     
                    lighthearted default                         
                    personality                                  

  FR-1600-008       Personality expressions    High              Test
                    (bashful, silly, playful)                    
                    MUST NOT override or delay                   
                    the mandatory                                
                    fault/E-stop/low-battery                     
                    display states                               
                    (FR-1600-003/004) - those                    
                    always take immediate                        
                    visual priority                              
  --------------------------------------------------------------------------------

**Implementation status (2026-08-09): MOSTLY DONE, one dead trigger.**
`display.py::WillyFace` implements distinct idle/listening/processing
(FR-1600-001), speaking (FR-1600-002), and an unambiguous fault/E-stop
and low-battery badge (FR-1600-003/004) driven off the true FSM state,
never the personality overlay. FR-1600-005 (never delay the tick loop)
is genuinely satisfied --- rendering runs on its own dedicated thread,
entirely separate from `brain.py`'s tick thread. FR-1600-007 (silly idle
animation) is real and working, triggered every `IDLE_PERSONALITY_CYCLE_S`
(90s) while idle. FR-1600-008 (personality never overrides fault/lowbatt)
is correctly enforced via an explicit safe-states exclusion list. **The
one real gap: FR-1600-006 ("bashful" expression) is built but never
triggered** --- the rendering exists but nothing anywhere detects the
"being complimented"/personal-question triggers that would call it,
mirroring FR-1500-009's same non-implementation.

# FR-1700 Object Detection and Retrieval Task

Covers the core long-term mission stated in the project vision
(assisted-living object retrieval for wheelchair users) as an actual
task-level requirement, not just generic arm joint control (FR-700) or
generic sensing (FR-800). This is arguably the single most important
capability in the spec and was not previously captured anywhere. Added
2026-08-02, v1.6.

  ------------------------------------------------------------------------
  Requirement ID    Requirement        Priority          Verification
  ----------------- ------------------ ----------------- -----------------
  FR-1700-001       Detect a           High              Test
                    dropped/target                       
                    object in the                        
                    camera field of                      
                    view via onboard                     
                    YOLOv8 (Hailo NPU)                   

  FR-1700-002       Localize the       High              Test
                    target object\'s                     
                    position relative                    
                    to the rover                         
                    (distance,                           
                    bearing) for                         
                    approach planning                    

  FR-1700-003       Plan and execute a High              Test
                    safe approach path                   
                    to the object,                       
                    respecting                           
                    obstacle avoidance                   
                    (FR-1000) and the                    
                    head/arm keep-out                    
                    volume (arm.py)                      

  FR-1700-004       Plan a grasp pose  High              Test
                    for the detected                     
                    object within the                    
                    arm\'s reach                         
                    envelope (§11.6)                     
                    and attempt pickup                   
                    via FR-700 arm                       
                    control                              

  FR-1700-005       Detect grasp       High              Test
                    failure (object                      
                    dropped or missed)                   
                    and retry or                         
                    report failure                       
                    rather than                          
                    proceeding as if                     
                    successful                           

  FR-1700-006       On successful      High              Test
                    retrieval,                           
                    approach the                         
                    requesting person                    
                    and execute a                        
                    safe, controlled                     
                    hand-off (e.g.                       
                    present object at                    
                    a fixed                              
                    height/distance,                     
                    wait for                             
                    confirmation of                      
                    receipt before                       
                    releasing grip)                      

  FR-1700-007       Abort the          High              Test
                    retrieval task at                    
                    any point if                         
                    FR-000 Directives                    
                    1-5 are triggered                    
                    (E-stop, fault,                      
                    low battery,                         
                    motion limits,                       
                    stall) --- never                     
                    complete a grasp                     
                    or hand-off motion                   
                    while a                              
                    higher-priority                      
                    directive is                         
                    active                               

  FR-1700-008       Do not attempt     High              Test
                    hand-off if a                        
                    person is not                        
                    detected within a                    
                    safe, defined                        
                    proximity range                      
                    --- do not release                   
                    the object                           
                    unattended near an                   
                    edge, stairs, or                     
                    into open air                        
  ------------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): DONE mostly, hardware-calibration
gaps confirmed accurate, plus one additional hand-off gap found this
pass.** The most complete v2.2 subsystem. FR-1700-001 detection works
via YOLOv8 through `ultralytics` on **CPU, not the Hailo NPU** the FRD
assumes --- no Hailo hardware is installed on this unit, and
`vision.py`'s detect/localize interface is written as a backend swap
point for later. FR-1700-002 localization is an explicitly documented
heuristic (no depth sensor/camera calibration), "usable for coarse...
approach control, not for precision placement" per the code's own
comment. FR-1700-003 obstacle avoidance during approach is real, but
the "head/arm keep-out volume (arm.py)" the FRD cites **does not
exist** --- `arm.py` states plainly no per-joint safe limits or IK exist
yet. FR-1700-004 is confirmed a fixed primitive sequence, not IK, as
previously known. FR-1700-005 (grasp-failure retry) is real, capped at
`RETRIEVAL_GRASP_RETRIES`. FR-1700-006 hand-off confirmation is
confirmed timeout-based (15s), not tactile, as previously known, and
honestly logged as such on a timeout release. FR-1700-007 (abort on any
Directive 1-5 trigger) is correctly wired at every battery
tier/tilt/sensor-fault call site. **New gap found this pass, beyond what
was previously known: FR-1700-008 is only partially satisfied** ---
person presence is checked before entering the hand-off wait, but is
**never re-checked before a timeout-triggered release**; if the person
walks away during the 15s window, the object still releases with no
re-verification anyone is there to receive it.

# FR-1800 Privacy and Data Handling

Covers microphone, camera, and cloud-fallback data handling --- relevant
given the assisted-living use case involves an always-listening
microphone (FR-1500 wake word) and a camera (FR-1700) operating inside a
person\'s home. Not previously specified anywhere. Added 2026-08-02,
v1.6.

  ------------------------------------------------------------------------
  Requirement ID    Requirement        Priority          Verification
  ----------------- ------------------ ----------------- -----------------
  FR-1800-001       Audio is processed High              Test
                    locally by default                   
                    (openwakeword +                      
                    faster-whisper);                     
                    raw audio is not                     
                    transmitted                          
                    off-device except                    
                    when FR-1400 cloud                   
                    fallback is                          
                    explicitly                           
                    triggered                            

  FR-1800-002       Camera frames are  High              Test
                    processed locally                    
                    by default                           
                    (YOLOv8/Hailo) and                   
                    are not                              
                    transmitted or                       
                    persisted beyond                     
                    what\'s needed for                   
                    the current task,                    
                    unless diagnostic                    
                    logging is                           
                    explicitly enabled                   

  FR-1800-003       When FR-1400 cloud Medium            Test
                    fallback (Gemini)                    
                    is triggered,                        
                    provide a clear                      
                    indication (voice                    
                    or display, per                      
                    FR-1600) that data                   
                    is being sent                        
                    off-device                           

  FR-1800-004       Diagnostic/log     Medium            Test
                    retention                            
                    (FR-1100) has a                      
                    defined maximum                      
                    retention period                     
                    and does not                         
                    indefinitely                         
                    accumulate raw                       
                    audio or camera                      
                    frames                               

  FR-1800-005       Provide a way to   Medium            Test
                    disable the                          
                    microphone and/or                    
                    camera entirely                      
                    (hardware or                         
                    software) for                        
                    privacy,                             
                    independent of                       
                    E-stop                               
  ------------------------------------------------------------------------

**Implementation status (2026-08-09): PARTIAL --- real-time behaviors
are solid, retention enforcement is dead code.** FR-1800-001/002
(local-only by default) hold by construction: no raw audio/frame ever
gets written to disk or transmitted outside the FR-1400 cloud path.
FR-1800-003 (indicate when data leaves the device) is real but
**incompletely wired**: the cloud-send notice fires from `voice.py`'s
free-text fallback path, but is **never called from `brain.py`'s
`_stuck()`**, which uses the same shared `CloudAIProvider` for
STUCK-state motion decisions --- no privacy indication when Claude is
queried for navigation, only for voice free-text. FR-1800-004 (defined
retention period) has a real config value and a real purge function
(`memory_store.py`/`privacy.py::purge_expired()`) --- but **neither is
ever called from anywhere in production**; retention is configured but
not actually enforced by any scheduled job, so data accumulates
indefinitely in practice despite the documented 30-day ceiling.
FR-1800-005 (disable mic/camera) is real as a mechanism --- a flag-file
check, re-evaluated continuously by both `voice.py` and `vision.py` ---
but `disable_mic_camera()`/`enable_mic_camera()` are **never called from
any voice intent or exposed control path**; the only way to trigger it
today is manually creating the flag file by hand.

# FR-1900 Learning from Observation and Instruction

Covers learning from watched demonstrations, observed
environment/routine patterns, and explicit verbal instruction. Added
2026-08-02, v1.7.

FEASIBILITY NOTE: on this hardware (Pi 5 + Hailo NPU, local Llama 3.2
3B), on-device neural network training/fine-tuning is not realistic.
This section specifies MEMORY-BASED learning instead --- Willie stores
observed demonstrations, environment facts, and verbal instructions in a
local structured store, then retrieves and applies that stored context
at decision time (retrieval-augmented behavior). The underlying models
themselves are not retrained. This is a real, working pattern, but it is
not \"the model gets smarter\" --- it is \"the model gets better
context.\" Worth confirming this framing matches the intent before CC
builds against it.

  ------------------------------------------------------------------------
  Requirement ID    Requirement        Priority          Verification
  ----------------- ------------------ ----------------- -----------------
  FR-1900-001       Capture a          Medium            Test
                    demonstrated task                    
                    (human performs an                   
                    action while                         
                    Willie observes                      
                    via camera) as a                     
                    stored                               
                    action/waypoint                      
                    sequence                             

  FR-1900-002       Replay a           Medium            Test
                    previously                           
                    captured                             
                    demonstration on                     
                    request, adapting                    
                    to current                           
                    object/position if                   
                    reasonably close                     
                    to the original                      

  FR-1900-003       Detect and report  High              Test
                    when a replay                        
                    attempt fails or                     
                    the current                          
                    situation differs                    
                    too much from the                    
                    captured                             
                    demonstration,                       
                    rather than                          
                    proceeding blindly                   

  FR-1900-004       Persist observed   Medium            Test
                    environment facts                    
                    over time (e.g.                      
                    typical object                       
                    locations, room                      
                    layout) in local                     
                    structured storage                   

  FR-1900-005       Recognize and      Low               Test
                    store repeated                       
                    routine patterns                     
                    (e.g. time-of-day,                   
                    recurring                            
                    requests) for                        
                    later reference                      

  FR-1900-006       Accept explicit    Medium            Test
                    verbal teaching                      
                    commands (e.g.                       
                    \'remember                           
                    that\...\', \'when                   
                    I say X, do Y\')                     
                    and store them as                    
                    retrievable                          
                    instructions                         

  FR-1900-007       Apply stored       Medium            Test
                    verbal                               
                    instructions and                     
                    environment facts                    
                    as context for                       
                    future FR-1700                       
                    retrieval tasks                      
                    and FR-1500                          
                    conversational                       
                    responses                            

  FR-1900-008       Confirm back to    Medium            Test
                    the user                             
                    (voice/display)                      
                    what was                             
                    learned/stored,                      
                    and support                          
                    correction or                        
                    deletion of a                        
                    stored item on                       
                    request                              

  FR-1900-009       Learned/replayed   High              Test
                    behavior is always                   
                    subject to FR-000                    
                    Directives 1-5 and                   
                    FR-1700\'s                           
                    grasp/hand-off                       
                    safety                               
                    requirements --- a                   
                    demonstrated task                    
                    never bypasses                       
                    safety gating                        

  FR-1900-010       Stored             Medium            Test
                    demonstrations,                      
                    environment facts,                   
                    and instructions                     
                    are subject to                       
                    FR-1800\'s                           
                    retention and                        
                    privacy                              
                    requirements                         

  FR-1900-011       On receiving a     High              Test
                    commanded shutdown                   
                    (FR-900-005),                        
                    persist any new or                   
                    updated memories                     
                    (demonstrations,                     
                    environment facts,                   
                    verbal                               
                    instructions) to                     
                    non-volatile                         
                    storage BEFORE the                   
                    shutdown sequence                    
                    completes                            
                    power-off --- new                    
                    learning must not                    
                    be silently lost                     
  ------------------------------------------------------------------------

Note on FR-1900-011 vs. the FR-200-004 emergency/critical-battery
shutdown: the critical-level hard cutoff (FR-200-004) may not have time
for a full graceful memory-save, and safety (Directive 3) takes priority
over data persistence in that path --- best-effort save is acceptable
there. However, FR-200-005 exists specifically to avoid reaching that
point unprepared: at the earlier low-battery/RTH threshold, Willie
proactively initiates the same graceful shutdown as a commanded shutdown
(FR-900-005), giving FR-1900-011\'s guaranteed save time to complete
before the hard cutoff would ever be needed. The critical-level cutoff
remains a backstop for cases where the proactive path didn\'t trigger in
time (e.g. rapid voltage drop).

# Acceptance Criteria

# Acceptance Criteria

# Acceptance Criteria

# Acceptance Criteria

# Acceptance Criteria

WildWilly shall initialize correctly, operate safely under manual
control, detect faults, avoid obstacles, support autonomous navigation,
and enter a safe state when power, communications, or safety conditions
become invalid.

**Implementation status (2026-08-09): PARTIAL/MISSING --- no
demonstration capture/replay exists; verbal-instruction and fact
storage are real but narrower than specced.** **FR-1900-001/002/003
(capture, replay, and mismatch-detection of a camera-observed human
demonstration) do not exist as a working capability**: the storage-layer
methods (`record_demonstration()`/`replay_demonstration()`) are fully
implemented but **never called from anywhere outside their own module**
--- no camera-watching capture loop exists anywhere, and `retrieval_task.py`'s
grasp is the fixed primitive sequence confirmed under FR-1700, not
anything demonstration-learned. What does work: FR-1900-004 (persist
environment facts) is real for objects via `mapping.py`'s voice-triggered
`MappingSession` in production, but "room layout" is not --- `world_model.add_room()`
is only ever called from test files, never production code (matches
`mapping.py`'s own documented "room identification is an explicit gap
this milestone" note). FR-1900-005 (routine-pattern recognition) exists
at the storage layer only, never called. FR-1900-006 (verbal "remember
that.../when I say X do Y") is real and wired via `voice.py::_maybe_learn()`.
FR-1900-007 (apply stored context) is **only half-wired**: voice
free-text interpretation pulls stored facts/instructions into the LLM
prompt, but `RetrievalTask` is constructed with no `memory` reference at
all --- stored facts/instructions are never available as context for
FR-1700 retrieval tasks. FR-1900-008 (confirm + support deletion) is
half-real: storage confirms back via speech, but delete methods exist
with no voice intent ever calling them --- no way to actually ask Willie
to forget something today. **FR-1900-011 (guaranteed save before
shutdown) is confirmed correctly implemented**, including proactively at
the earlier RTH battery threshold, not just at commanded shutdown.

# FR-2000 Email Account and Management

Covers Willie\'s own dedicated Google/Gmail account --- used both as the
authentication identity for FR-1300 (Google Home) and FR-1400 (Gemini),
and as an actively managed inbox (not just an auth token). Added
2026-08-02, v2.0.

SECURITY NOTE: this is the first requirement area where WildWilly
processes content authored by an external, potentially untrusted party
(email senders) and feeds it into an LLM. Email content must be treated
as data to summarize/act on for the OWNER, never as instructions the LLM
itself follows. Without this boundary, a malicious or malformed email
could attempt a prompt-injection attack --- text in the email body
written to look like a command to Willie (e.g. \"ignore previous
instructions and \...\") --- and get treated as if the owner said it.
FR-2000-006 exists specifically to close this gap. FR-2000-009 adds a
second, independent layer: outbound email is hard-restricted to a single
allowlisted recipient (h.d.himmel@gmail.com) at the code level, so even
if the confirmation requirement (FR-2000-004) or the injection boundary
(FR-2000-006) were somehow bypassed, there is still no path for Willie
to send email to anyone but the owner. FR-2000-010/011 add a third layer
on the inbound side: only the owner and an owner-managed allowlist of
senders are ever read/processed at all --- content from anyone else is
never parsed or summarized, so it can\'t reach the LLM as a
prompt-injection vector in the first place, and only the owner can
expand who\'s trusted enough to be read.

  -------------------------------------------------------------------------------------
  Requirement ID    Requirement                     Priority          Verification
  ----------------- ------------------------------- ----------------- -----------------
  FR-2000-001       Maintain a dedicated Google     High              Test
                    account for Willie                                
                    (willie.pi5.droid@gmail.com),                     
                    separate from the owner\'s                        
                    personal account, for Google                      
                    Home (FR-1300-005) and Gemini                     
                    (FR-1400-005) authentication                      
                    and for email                                     

  FR-2000-002       Periodically check the inbox    Medium            Test
                    for new messages                                  

  FR-2000-003       Surface relevant email content  Medium            Test
                    to the owner via voice                            
                    (FR-1500) and/or display                          
                    (FR-1600) summary, rather than                    
                    acting on it silently                             

  FR-2000-004       Never send an email             High              Test
                    autonomously on the owner\'s                      
                    behalf without explicit                           
                    real-time confirmation for that                   
                    specific message                                  

  FR-2000-005       Store account credentials       High              Test
                    securely on-device (not in                        
                    plaintext logs or diagnostics                     
                    output per FR-1100)                               

  FR-2000-006       Treat all email body/subject    High              Test
                    content as untrusted data to be                   
                    summarized or acted upon FOR                      
                    the owner --- never interpret                     
                    instructions embedded in email                    
                    content as commands to execute                    
                    (prompt-injection boundary)                       

  FR-2000-007       Email content and any derived   Medium            Test
                    summaries are subject to                          
                    FR-1800\'s retention and                          
                    privacy requirements                              

  FR-2000-008       Email checking/processing must  High              Test
                    never delay or block FR-000                       
                    Directives 1-5                                    

  FR-2000-009       Outbound email is               High              Test
                    hard-restricted to a single                       
                    allowlisted recipient,                            
                    h.d.himmel@gmail.com ---                          
                    enforced at the code level (not                   
                    just a UI default),                               
                    reject/block any attempt to                       
                    send to any other address                         
                    regardless of what triggered                      
                    the send attempt (owner                           
                    confirmation, LLM output, or                      
                    email content per FR-2000-006)                    

  FR-2000-010       Inbound email is only           High              Test
                    read/processed if the sender is                   
                    h.d.himmel@gmail.com or on an                     
                    owner-managed sender allowlist.                   
                    Email from any other sender is                    
                    not parsed, summarized, or                        
                    acted upon --- at most its                        
                    existence (sender/subject) may                    
                    be noted, never its body                          
                    content                                           

  FR-2000-011       Only the owner                  High              Test
                    (h.d.himmel@gmail.com,                            
                    authenticated) can add or                         
                    remove senders from the inbound                   
                    allowlist --- this list cannot                    
                    be modified by a voice command                    
                    alone, by content in an email,                    
                    or by any other unauthenticated                   
                    path                                              
  -------------------------------------------------------------------------------------

# Acceptance Criteria

**Implementation status (2026-08-09): PARTIAL --- the three documented
security layers are real and well-written in-code, but the outbound/
allowlist-management paths are entirely unwired to any live caller.**
FR-2000-001/002/005 are solid: dedicated-account app-password login,
120s inbox polling on its own thread (satisfying FR-2000-008's
never-block-Directives requirement by construction), credentials never
in plaintext logs. FR-2000-003 (surface, don't act silently) is real ---
`brain.py::_idle()` speaks new-mail summaries only, never acts on
content. **FR-2000-006's prompt-injection boundary is exactly as
documented**, worth quoting directly from `email_client.py`'s own
comment: *"this module never itself constructs an LLM prompt from email
content... it wraps the body in an explicit untrusted-data delimiter and
instructs the model not to treat it as commands."* FR-2000-009's
single-recipient allowlist is enforced at two independent code points
(queue time and send time), not just config. FR-2000-010/011 (inbound
allowlist) is enforced via `_sender_allowed()`, with the module's own
comment honestly flagging the real limit of "owner-confirmed": *"there
is no voiceprint/biometric auth anywhere in this codebase... in practice
this means 'a command spoken at the physical device,' not a
cryptographically verified owner identity."* **The gap beyond what the
code already self-documents:** outbound sending, allowlist management,
and the prompt-template helper are **never called from `voice.py` or
`brain.py`** --- only inbound summarization is wired end-to-end today.
FR-2000-004's "never send without confirmation" is true today only
because sending is unreachable from any live user-facing trigger, not
because a tested confirm-then-send flow has been exercised.

# Mission-Level Functional Requirements (M-001--M-012)

Moved here from the WildWilly Master Engineering Package (rev 6.0) so
this document is the single source for all functional-requirement
content. These are the mission-level requirements referenced by that
document\'s requirements-traceability table (its section 2.3); the
FR-xxx requirements above remain the detailed, subsystem-level
breakdown. M-006 (stair climbing) was reclassified from a must-have to a
stretch goal on 2026-07-18 --- the rover\'s baseline scope is drive,
see, talk/listen, arm pick/place on flat ground, and basic flat-terrain
autonomy.

  ------------------------------------------------------------------------
  ID             Requirement                               Class
  -------------- ----------------------------------------- ---------------
  M-001          Autonomous navigation                     Baseline

  M-002          Voice command processing                  Baseline

  M-003          Local AI inference                        Baseline

  M-004          Object recognition                        Baseline

  M-005          Obstacle avoidance                        Baseline

  M-006          Stair climbing                            STRETCH
                                                           (reclassified
                                                           2026-07-18)

  M-007          Robotic-arm manipulation (pick/place on   Baseline
                 flat ground)                              

  M-008          Battery monitoring                        Baseline

  M-009          Thermal monitoring                        Baseline

  M-010          Emergency shutdown                        Baseline

  M-011          Remote administration                     Baseline

  M-012          Local data storage                        Baseline

  M-013          Smart home integration (Google Home) ---  NEW v1.3 ---
                 FR-1300                                   unassigned

  M-014          Cloud AI fallback (Gemini) --- FR-1400    NEW v1.3 ---
                                                           unassigned

  M-015          Voice interaction pipeline --- FR-1500    NEW v1.4 ---
                 (retroactively backs M-002)               unassigned

  M-016          Facial expression / display feedback ---  NEW v1.4 ---
                 FR-1600                                   unassigned

  M-017          Object detection and retrieval task (core NEW v1.6 ---
                 mission) --- FR-1700                      unassigned

  M-018          Privacy and data handling --- FR-1800     NEW v1.6 ---
                                                           unassigned

  M-019          Learning from observation and instruction NEW v1.7 ---
                 --- FR-1900                               unassigned

  M-020          Email account and management --- FR-2000  NEW v2.0 ---
                                                           unassigned
  ------------------------------------------------------------------------

**Implementation status (2026-08-09), per mission item:**

| ID | Status | Reason |
|---|---|---|
| M-001 Autonomous navigation | DONE | `navigation.py::Navigator` FSM wired as `brain.py`'s `NAVIGATE` state; raw-coordinate targets work, room-name resolution untested in production (`world_model.add_room()` only ever called from tests). |
| M-002 Voice command processing | PARTIAL | Pipeline fully built and now enabled (`ENABLE_VOICE=True`, 2026-08-09); not yet live-verified end-to-end on hardware (see FR-1500 status note). |
| M-003 Local AI inference | DONE | `ai_provider.py::LocalAIProvider` wraps `llama_cpp.Llama`, confirmed importable; gates FR-1400 fallback via confidence floor. |
| M-004 Object recognition | PARTIAL | YOLOv8 on CPU, not the Hailo NPU the FRD assumes (none installed); `ENABLE_OBJECT_RETRIEVAL=False` by default. |
| M-005 Obstacle avoidance | DONE | Sonar-driven `AVOID` state backed by `safety.py::approve_motion()`'s unconditional obstacle reject. |
| M-006 Stair climbing | MISSING (STRETCH, confirmed deferred) | Zero code presence anywhere; correctly reclassified 2026-07-18. |
| M-007 Arm pick/place (flat ground) | PARTIAL | Fixed primitive grasp sequence, not IK; no per-joint calibration run. |
| M-008 Battery monitoring | DONE | Full voltage/current tier ladder with hysteresis, backed by real ADC threads. |
| M-009 Thermal monitoring | MISSING, confirmed | Zero hits for "thermal"/"temperature" anywhere in the codebase — no sensing, no fault handling. |
| M-010 Emergency shutdown | PARTIAL | No GPIO E-stop sense pin; graceful low-battery shutdown + guaranteed memory save work. Repo's `willy-rover.service` file has `WatchdogSec=500ms`, but the **deployed** unit does not — config drift, not just "never configured" (see note below). |
| M-011 Remote administration | MISSING, confirmed | No listening sockets, teleop, HTTP/websocket server, or remote-command receive path anywhere. Note: this table's own M-011 wording ("Cockpit access test, :9090") describes a different capability than the FRD's "Remote administration" — the two documents don't agree on what M-011 even means; worth reconciling with the owner. |
| M-012 Local data storage | DONE | `memory.db` + `world_model.db`, both SQLite/WAL, both checkpointed on shutdown. |
| M-013 Smart home integration | PARTIAL | Built, fails open correctly, but `discover_devices()` is dead code and disabled by default. |
| M-014 Cloud AI fallback | PARTIAL, mismatch | Actually Anthropic Claude, not Gemini — see the CORRECTION note under FR-1400. Confidence-routing and non-blocking design are solid. |
| M-015 Voice interaction pipeline | PARTIAL | Code-complete but disabled by default; personality-tone system unimplemented. |
| M-016 Facial expression/display | DONE (mostly) | Real, own thread, correctly prioritizes fault states; only the bashful-trigger wiring is missing. |
| M-017 Object detection/retrieval (core mission) | PARTIAL | DONE mostly, hardware-calibration gaps only, plus a hand-off re-verification gap found this pass (FR-1700-008). |
| M-018 Privacy and data handling | PARTIAL | Real-time behaviors solid; retention purge and mic/camera-disable are unwired dead code from a usability standpoint. |
| M-019 Learning from observation/instruction | PARTIAL/MISSING | Demonstration capture/replay entirely unimplemented; verbal fact/instruction storage works but isn't consumed by FR-1700 retrieval. |
| M-020 Email account and management | PARTIAL | Inbound polling/summarization and all three security layers are real; outbound sending and allowlist management are unwired to any caller. |

**Cross-cutting findings from this pass, flagged for the owner rather
than silently fixed:**

1. **Service-config drift, confirmed via `systemctl cat` vs. the repo
   file:** `willy-rover.service` in the repo (last touched 2026-08-02)
   includes `WatchdogSec=500ms`, but the *deployed* unit does not have
   that line at all. Someone edited the repo copy but it was never
   redeployed (`cp` to `/etc/systemd/system/` + `daemon-reload` never
   ran, or ran before the edit). This is a real drift, not just "the
   watchdog was never configured" as prior sessions' notes assumed —
   worth a deploy-and-verify pass if the watchdog is wanted, since right
   now the two files disagree about whether it exists at all.
2. **Several security/privacy-relevant methods are implemented and
   tested as library functions but have no production caller anywhere**:
   `discover_devices()` (smart_home.py), `queue_outbound()`/
   `confirm_and_send()`/`add_allowed_sender()` (email_client.py),
   `delete_fact()`/`delete_instruction()`/`delete_demonstration()`
   (memory_store.py), `disable_mic_camera()`/`enable_mic_camera()`/
   `purge_expired()` (privacy.py/memory_store.py), and
   `record_demonstration()`/`replay_demonstration()`/`note_routine()`
   (memory_store.py). None of these are bugs — the code that exists is
   careful and well-guarded — but "implemented and reachable by a real
   user action" and "implemented as a tested function nothing calls" are
   different claims, and several FR sub-requirements above (FR-1800-004/
   005, FR-1900-001/002/005/008, FR-2000-004/010/011's practical
   reachability) only hold under the weaker of the two.
