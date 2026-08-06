**Willy Functional Requirements Document (FRD)\
Version 2.2**

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

# Acceptance Criteria

# Acceptance Criteria

# Acceptance Criteria

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
