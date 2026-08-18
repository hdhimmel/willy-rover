**Willy Functional Requirements Document (FRD)\
Version 3.0**

**Document control**

  -----------------------------------------------------------------------
  Field                   Value
  ----------------------- -----------------------------------------------
  Revision                3.0

  Date                    2026-08-15

  Owner                   Howard Himmel

  Status                  Hardware build complete; live verification in
                          progress

  Companion document      WildWilly As-Built Design v1.0 --- current
                          hardware configuration. Section references of the
                          form §n refer to it unless stated otherwise.

  Supersedes              v2.3 (2026-08-11), v2.2
  -----------------------------------------------------------------------

*v3.0 gives every previously empty Acceptance Criteria section concrete
pass/fail conditions, adds a verification-status register (§V), and aligns all
hardware references with the as-built configuration. **No requirement has been
added, removed, or reworded.** All 113 requirement IDs from v2.2 are retained
unchanged --- this revision states how each is proven, not what each demands.*

# V. Verification Status Register

Requirements are implemented and unit-tested off-hardware unless noted.
"Live-verified" means proven on the assembled rover.

  -----------------------------------------------------------------------
  Group                   Status                  Notes
  ----------------------- ----------------------- -----------------------
  FR-000 Prime Directives Implemented, not        Requires E-stop and
                          live-verified           motion testing

  FR-100 Startup          PARTIAL --- I²C         Ten-device roll-call
                          enumeration             passes through the
                          live-verified           isolator. Encoder and
                                                  IMU checks outstanding.

  FR-200 Power            PARTIAL --- rail        Pi rail 5.144V,
                          measurement             throttled 0x0. Battery
                          live-verified           divider not yet
                                                  calibrated, so
                                                  thresholds are not
                                                  trustworthy.

  FR-300 Safety / E-stop  Not live-verified       Blocking for any motion
                                                  testing

  FR-400 Drive            Not live-verified       Motor crimps unverified
                                                  on five of six units

  FR-500 Encoders         Not live-verified       Requires manual rotation
                                                  test

  FR-600 Steering         Not live-verified       Servo V+ current path
                                                  unconfirmed

  FR-700 Arm              Not live-verified       

  FR-800 Sensors          PARTIAL --- sonars      Range test and IMU
                          connected               output outstanding

  FR-900 onwards          Implemented, off-       
                          hardware tested only    
  -----------------------------------------------------------------------

Motion-related groups (FR-400 through FR-700) must not be live-tested until
FR-300 passes --- that is Directive 2.

# 1. Purpose

This Functional Requirements Document defines the required behavior,
safety functions, control systems, autonomy, mobility, and future
capabilities of the WildWilly robotic platform.

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

Verification of FR-100-002 through FR-100-004 is the bus node board
commissioning gate (Master Engineering Package rev 6.2.0 §17.5). Pass
conditions:

-   **FR-100-002 (I²C bus and device init).** `i2cdetect -y 1` enumerates the
    ten expected devices: 0x27 MCP23017, 0x40/0x44/0x45 INA260, 0x42/0x43
    PCA9685, 0x48 ADS1115, 0x4A BNO085, 0x60/0x61 FeatherWing. Any missing
    address fails the gate; the run must not continue to FR-100-004 release.

-   **FR-100-002, 0x70 is not a device.** A scan will also show 0x70. Per
    Master Engineering Package §5.2 this is the PCA9685 All-Call broadcast
    address, present whenever either PCA9685 is alive, and the LTC4311 has no
    address of its own --- it is a transparent pass-through. The self-test must
    not count 0x70 toward the device total, and must not report the LTC4311 as
    verified on the strength of it.

-   **FR-100-002, false-negative exclusion.** A blank or partial scan while the
    base is unpowered is expected behaviour, not a fault --- Side 2 of the
    isolation barrier is fed by the AMS1117-3.3 off the 5V servo rail, so all
    downstream devices go dark when the Pi is powered by USB-C alone. The
    startup self-test must distinguish "base off" from "bus fault" before
    reporting a failure, or every dev-only session will raise a spurious
    critical.

-   **FR-100-003 (startup self-test).** The self-test additionally confirms the
    BNO085 interrupt is live on GP15 and that all six encoder channels on the
    MCP23017 change count under manual wheel rotation. Address enumeration
    alone is not sufficient --- a device can ACK and still be miswired.

-   **FR-100-004 (motion inhibit).** Motion stays inhibited unless the two
    preceding checks both pass. This is Directive 2 in FR-000; a release of
    motion following a failed or skipped self-test is a critical defect.

Pre-power hardware conditions that gate the first execution of this test are
listed in rev 6.2.0 §17.5 and are not restated here; the three marked BLOCKING
(AMS1117 decoupling, SDA2/SCL2 pull-ups, ISO1540 orientation) have each already
cost hardware on this build.

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

Battery telemetry under FR-200-001 is read on ADS1115 channel A0 from the
10kΩ / ~3.2kΩ divider (Master Engineering Package rev 6.2.0 §8.4). Pass
conditions:

-   **FR-200-001 (voltage/current/power).** Reported pack voltage tracks a
    meter reading within 0.05V across the 10.2--12.6V range, after the divider
    scale factor in `config.py` is set. Rail currents are read from the three
    INA260s at 0x40 (servo/steering 5V), 0x44 (Pi 5V) and 0x45 (motor 12V).

-   **FR-200-001, pre-power safety condition.** A0 must be metered before the
    ADS1115 is first energised and must sit in the 2.76--3.06V window. A
    reading at or near 12V means the divider is open and the ADC will be
    destroyed on power-up --- this exact fault previously reached the
    superseded MCP3008 CH7 channel, where the internal clamp diodes were
    absorbing it (raw 1016/1023). Do not power the board to "see what it
    reads."

-   **FR-200-002/003/004 (thresholds and shutdown).** Undervoltage, warning and
    critical-cutoff thresholds are verified against the calibrated reading
    above, not against raw counts. FR-200-004 shutdown must fire from
    calibrated volts so that a divider or scale-factor error cannot silently
    move the cutoff.

-   **FR-200-005 (proactive graceful shutdown).** Verified by driving the
    reported voltage across the low-battery threshold on the bench and
    confirming the same shutdown sequence executes as for the critical case,
    ahead of the RTH threshold.

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

FR-300 is Directive 1 and gates every motion group. It must pass before
FR-400 through FR-700 are live-tested at all.

-   **FR-300-001 (continuous monitoring).** The E-stop state is polled or
    interrupt-driven on every control cycle, not checked once at startup.
    Verified by triggering the E-stop mid-cycle and confirming detection
    within one cycle period.

-   **FR-300-002 (immediate motion disable).** With all six drive motors
    running and the arm mid-trajectory, triggering the E-stop halts motor
    output and arm output in the same cycle. No queued command executes
    afterwards. A queued arm motion completing after an E-stop trigger is a
    critical defect, not a tuning issue.

-   **FR-300-003 (operator reset).** After an E-stop, no motion command
    succeeds until an explicit operator reset. Verified by issuing drive and
    arm commands post-trigger and confirming all are refused.

-   **FR-300-004 (controller failure).** Loss of the I²C bus, or a failed read
    from either motor driver, halts motion rather than continuing on stale
    state. Verified by disconnecting the bus mid-run.

-   **Coverage note.** The E-stop cuts motor and arm power in hardware. That
    is the backstop, not the requirement --- FR-300 governs the software path,
    which must reach the same state independently so that logic remains
    consistent after the hardware cut.

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

Wheel and driver assignment is fixed by the as-built wiring: 0x60 drives the
left side (LF, LM, LR) and 0x61 the right (RF, RM, RR).

-   **FR-400-001 (independent control).** Each of the six motors can be
    commanded individually and the correct wheel responds. Verified one motor
    at a time, wheels off the ground, against the driver map above. A wheel
    turning when a different one was commanded is a mapping error, not a
    wiring fault, and must be corrected in software.

-   **FR-400-002 (forward, reverse, turning).** All three produce the expected
    wheel directions. On a six-wheel rocker-bogie with independent steering,
    confirm that a turn command drives the steering group and the drive group
    consistently rather than fighting each other.

-   **FR-400-003 (smooth ramping).** A step command produces a ramped current
    profile rather than an inrush spike. Verified against the motor-rail
    INA260 --- an unramped six-motor start is one of the larger transients on
    the 12V rail.

-   **FR-400-004 (speed limits).** A command above the software cap is clamped,
    not refused silently and not passed through. This is Directive 4 and is a
    hard cap, not a default.

-   **Precondition.** Motor crimps must be metered against the as-built colour
    scheme before first motion. Five of six remain unverified.

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

Encoders are read through the MCP23017 at 0x27, two channels per motor.

-   **FR-500-001 (read encoders).** All six channels change count under manual
    wheel rotation, and each maps to the correct wheel. Quadrature direction
    must be correct: forward rotation increments, reverse decrements. A
    channel counting backwards indicates the A and B lines are swapped for
    that motor.

-   **FR-500-002 (speed and distance).** Counts convert to distance using the
    measured wheel circumference and the encoder resolution. Verified by
    driving a measured straight line --- a fixed offset means the constant is
    wrong; a proportional error that grows with distance means slip.

-   **FR-500-003 (stall detection).** A commanded motor showing no count
    change within the stall window triggers stop-and-report, not increased
    drive. This is Directive 5 --- the failure mode being prevented is
    continued force application into a blocked wheel. Also covers the inverse:
    counts changing with no command issued.

-   **FR-500-004 (closed-loop speed).** Commanded speed is held across a
    surface change without oscillation or sustained offset.

-   **Signal note.** Encoder lines land directly on MCP23017 GPIO with no
    filtering. If spurious counts appear under motor load, the correct
    responses are firmware debounce or small-value filtering sized to the
    measured pulse rate --- not arbitrary capacitance, which at these rates
    would destroy the count.

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

Six steering servos on PCA9685 0x42, channels CH0--CH5.

-   **FR-600-001 (servo control).** Each corner responds on its own channel
    and moves the expected wheel. Verified one channel at a time.

-   **FR-600-002 (calibration).** Centre and end positions are stored and
    survive a power cycle. Confirm the pulse-width range per unit before
    relying on a common constant --- some stock ships in a narrower range and
    a shorter travel than the nominal 500--2500µs / 180°.

-   **FR-600-003 (travel limits).** Commands beyond the mechanical limit are
    clamped in software. This is Directive 4. A servo driven into a hard stop
    stalls at maximum current and will overheat --- so this limit is a
    hardware-protection requirement, not a nicety.

-   **FR-600-004 (manual override).** Override takes effect within one control
    cycle and is itself subject to the travel limits above.

-   **Load precondition.** Servo current flows through the PCA9685's V+
    terminal, PCB trace and channel headers. Worst-case draw with all six
    moving together approaches the 5V rail's supply rating. Verify the board's
    current path before running all six under load simultaneously, and monitor
    the 5V INA260 during the first such test.

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

Seven servos on PCA9685 0x43, channels CH0--CH6.

-   **FR-700-001 (all joints).** Each joint responds on its own channel across
    its range. The shoulder is a mirrored pair driving one physical axis and
    must be commanded together as `J1b = 2 × 1500µs − J1a`. Driving either
    shoulder servo alone fights the other through the linkage and is a
    mechanical-damage risk --- test the pair as a unit from the outset.

-   **FR-700-002 (preset positions).** Named poses are repeatable to within
    the mechanical backlash of the joint, and a stow pose is reachable from
    any starting configuration without self-collision.

-   **FR-700-003 (joint limits).** Software limits are enforced per joint
    before any command reaches the driver. As with steering, a servo held
    against a hard stop draws stall current continuously.

-   **FR-700-004 (E-stop).** The arm stops on E-stop in the same cycle as the
    drive motors, and no queued arm motion resumes afterwards. This is the
    specific case named in the FR-000 acceptance criteria.

-   **Hold-current note.** Seven servos holding a pose against gravity draw
    continuously, unlike drive motors which draw only while moving. Arm duty
    cycle is therefore a material factor in the power budget and should be
    measured on the 6V rail rather than estimated.

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

-   **FR-800-001 (IMU orientation).** The BNO085 at 0x4A returns stable fused
    orientation. Heading holds steady with the rover stationary and tracks
    correctly through a known rotation. Because the sensor's reset line runs
    through the MCP23017, the expander must be initialised first --- an
    ordering dependency, not a wiring choice. If initialisation succeeds but
    reads fail intermittently, the cause is I²C clock stretching rather than
    wiring.

-   **FR-800-002 (sonar).** All three units return distance tracking a tape
    measure across their usable range. Test each independently before
    trusting any of them together. Front and right reading correctly while
    left returns garbage is the specific signature of the serial console
    having been re-enabled --- the left echo pin doubles as UART transmit.

-   **FR-800-003 (tilt detection).** Excessive tilt is detected from IMU
    output and halts motion. Verify the threshold against the rover's actual
    tipping angle with the arm extended, which is its least stable
    configuration --- not with the arm stowed.

-   **FR-800-004 (sensor health).** A disconnected or non-responding sensor is
    reported as failed rather than silently returning stale or default
    values. Verified by disconnecting each sensor in turn during operation.
    Silent staleness on a ranging sensor is more dangerous than a reported
    fault.

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

-   **FR-900-001 (remote commands).** Commands are accepted and acted on, and
    every one remains subject to Directives 1--5. A remote command cannot
    bypass the E-stop, the startup gate, or the speed limits.

-   **FR-900-002 (status display).** Rover state, battery level and fault
    conditions are visible to the operator. Battery must be shown in
    calibrated volts, not raw ADC counts.

-   **FR-900-003 (comms loss).** Loss of the operator link halts motion within
    a defined timeout rather than continuing on the last command. Verified by
    disconnecting mid-motion. A rover that keeps driving on a stale command
    after link loss is the failure this requirement exists to prevent.

-   **FR-900-004 (emergency override).** Available at all times and takes
    effect immediately.

-   **FR-900-005 (commanded shutdown).** A voice or manual shutdown runs the
    graceful sequence with the rail still powered: motion halts, the arm
    stows, state is persisted, then `shutdown -h now`. Distinct from the
    FR-200-004 critical-battery path in trigger only --- both end in the same
    clean halt. Power is removed afterwards by the operator, so no hold-up
    energy is required or available.

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

Scope is flat-terrain autonomy. Stair navigation is a stretch goal covered
separately under FR-1200.

-   **FR-1000-001 (navigate unaided).** The rover reaches a commanded
    destination on flat ground without operator input.

-   **FR-1000-002 (obstacle avoidance).** Obstacles are detected and avoided.
    **Detection must not depend on the vision pipeline.** Sonar and encoders
    are the reflex layer: deterministic, fast, and the sole gate on stopping.
    Vision runs at frame rate with variable latency and informs route choice
    and classification only. Verified by confirming the rover still stops for
    an obstacle with the vision pipeline disabled entirely.

-   **FR-1000-003 (route maintenance).** The planned route is followed within
    tolerance, with odometry drift corrected against IMU heading.

-   **FR-1000-004 (handover).** Operator control is regained on demand within
    one control cycle, from any autonomous state.

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

-   **FR-1100-001 (subsystem health).** Every I²C device, all six encoders and
    all three sonars are health-checked. A device that acknowledges on the bus
    but returns implausible data must be reported as failed --- bus presence
    is not health.

-   **FR-1100-002 (warnings and faults).** Faults are recorded with enough
    context to diagnose after the fact: which subsystem, what value, what the
    expected range was.

-   **FR-1100-003 (timestamped logs).** Logs survive a graceful shutdown and
    are timestamped consistently.

-   **FR-1100-004 (diagnostic mode).** A mode exists that exercises each
    subsystem independently with motion inhibited, so faults can be isolated
    without risk.

-   **Known false positives to handle explicitly.** Two states look like
    faults but are not, and must be distinguished rather than reported as
    errors. A blank or partial I²C scan with the base unpowered is expected ---
    the isolated bus dies with the 12V chain. And the Pi-rail monitor showing
    a healthy voltage with near-zero current while the Pi is plainly running
    indicates USB-C bench power, not a sensor fault.

-   **Roll-call note.** The expected count is ten devices. The All-Call
    broadcast address also answers whenever either servo controller is alive
    and must not be counted toward the total --- doing so lets a scan pass
    while a real device is missing.

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

-   Smart-home commands are accepted and acted on, and remain subject to
    Directives 1--5 exactly as remote operator commands are. An external
    integration is not a privileged path.
-   Loss of the integration degrades gracefully --- local control continues
    unaffected. The rover must remain fully operable with no network at all.
-   No smart-home command can initiate motion while the startup self-test is
    unsatisfied.

# FR-1400 Cloud AI Assistance (Gemini Fallback)

ASSUMPTION (flag for review): Gemini is a FALLBACK path used only when
the onboard Llama 3.2 3B cannot adequately handle a request --- not a
primary dependency. This preserves the existing local-first architecture
(faster-whisper, Llama 3.2 3B, Piper TTS all run onboard); Gemini would
be Willie\'s first cloud-dependent capability if implemented as anything
more than an optional fallback. Verify this priority with the owner
before implementation. Added 2026-08-01, v1.3. Not yet in scope for any
CC session to date.

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

-   Wake-word detection, speech-to-text and response run on-device using the
    NPU accelerator, with no network dependency for core interaction.
-   Voice commands are subject to Directives 1--5. A spoken motion command is
    refused if the self-test has not passed, exactly as any other command
    would be.
-   A commanded shutdown by voice runs the FR-900-005 graceful sequence.
-   Speech recognition latency does not gate any safety behaviour --- voice is
    deliberative-layer, and a stop must never wait on a transcription.
-   Recognition failures are reported rather than silently ignored, so an
    unheard command is never mistaken for a refused one.

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

-   Object detection runs on the NPU and identifies target objects at
    sufficient rate for approach and grasp.
-   Approach uses the reflex layer for collision avoidance throughout ---
    detection guides where to go, sonar decides when to stop. A grasp approach
    must still stop for an unexpected obstacle with vision disabled.
-   Grasp attempts respect the FR-700 joint limits, and a failed grasp
    stop-and-reports rather than retrying with increased force. This mirrors
    Directive 5.
-   The arm stows before any drive motion resumes, so the rover never
    translates with the arm extended --- that is its least stable
    configuration and the basis of the FR-800-003 tilt threshold.

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

WildWilly shall initialize correctly, operate safely under manual
control, detect faults, avoid obstacles, support autonomous navigation,
and enter a safe state when power, communications, or safety conditions
become invalid.

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

-   Email handling operates only when explicitly invoked and never initiates
    motion or any physical action on its own.
-   Credentials are held outside the repository and are not present in any
    committed file or commit history.
-   Failures degrade gracefully --- loss of email connectivity does not affect
    local rover operation in any way.

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
