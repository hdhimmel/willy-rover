# WildWilly Rover — Claude Code Fix & Architecture Implementation Plan

## Purpose

This document is the implementation directive for Claude to modify the current `willy-rover` repository.

The goal is **not** to throw away the existing code. Preserve good existing abstractions and documentation where practical, but correct the safety, timing, autonomy, hardware-integration, memory, navigation, and configuration issues identified during engineering review.

The resulting software must be suitable for incremental testing on the physical WildWilly rover.

---

# 1. Implementation Rules

1. Do not make large destructive rewrites unless required.
2. Preserve working hardware abstractions and existing interfaces where possible.
3. Do not claim a capability is implemented unless the code actually implements it.
4. Do not allow an LLM/cloud AI to directly bypass safety controls or directly command motors.
5. Keep real-time/safety-critical control independent of slow AI/network operations.
6. Every new subsystem must have:
   - configuration
   - logging
   - error handling
   - a safe failure mode
   - unit tests where practical
7. Hardware-dependent functionality must support a simulation/mock mode.
8. Update documentation whenever behavior or configuration changes.
9. Clearly distinguish:
   - implemented
   - simulated
   - hardware-dependent
   - planned/not yet implemented
10. Do not silently change GPIO/I²C addresses from the WildWilly hardware specification.

---

# 2. Priority 0 — Safety and Control-Loop Architecture

## 2.1 Eliminate blocking operations from the primary control loop

### Problem

The current brain/control path can block for:
- cloud/LLM requests
- timed reverse operations
- timed turns
- other potentially slow operations

The systemd watchdog is configured around a very short interval. A blocked main loop can therefore cause a watchdog failure or, more importantly, prevent timely safety processing.

### Required architecture

Create a non-blocking control loop.

Recommended structure:

```text
                    MAIN CONTROL LOOP
                         20 Hz+
                           |
          +----------------+----------------+
          |                |                |
       Sensors          Safety          State/FSM
          |                |                |
          +----------------+----------------+
                           |
                    Motion Request
                           |
                    Safety Gate
                           |
                    Motor Command
```

Slow operations must run asynchronously/outside the control loop:

```text
AI/LLM Worker
Vision Worker
Memory Worker
Mapping Worker
Voice Worker
Email/Cloud Worker
```

The main control loop must continue running while these workers are busy.

### Acceptance criteria

- No HTTP/API call occurs directly inside the motor/control tick.
- No `sleep()` is used to hold the control loop while a movement is executing.
- Timed movement becomes a state with a deadline, not a blocking function.
- The watchdog heartbeat continues at the required rate regardless of AI/network latency.
- A slow or crashed worker cannot freeze motor safety processing.

---

# 3. Priority 0 — Safety Gate Between AI and Motors

## Problem

The AI currently returns movement decisions that can flow too directly toward motor execution.

An LLM must never be the final authority over physical movement.

## Required architecture

Implement:

```text
AI proposal
    |
    v
Intent validator
    |
    v
Navigation constraints
    |
    v
Safety gate
    |
    +--> E-stop
    +--> battery
    +--> motor current
    +--> tilt
    +--> obstacle
    +--> speed limit
    +--> command timeout
    +--> hardware fault
    |
    v
Approved motor command
```

The AI can propose:

```json
{
  "action": "forward",
  "speed": 0.25,
  "duration": 0.5
}
```

but the safety controller must independently determine whether that command is legal.

### Safety gate must be authoritative

The AI must not be able to:
- disable E-stop
- ignore an obstacle
- exceed configured speed limits
- override low-battery protection
- override over-current protection
- command motion after a fault
- command indefinite motion
- directly access low-level motor GPIO/PWM

### Acceptance criteria

Create a single authoritative safety/motion interface such as:

```python
SafetyController.approve_motion(request) -> ApprovedMotion | Rejected
```

All motor commands must pass through it.

---

# 4. Priority 0 — Watchdog Redesign

## Problem

The watchdog heartbeat currently depends on a loop that can perform blocking operations.

## Required changes

- Make the watchdog heartbeat independent of AI/network calls.
- Prefer a dedicated watchdog/supervision task.
- The supervisor must detect:
  - control-loop stall
  - motor-controller communication failure
  - sensor subsystem failure
  - worker failure
- On a control fault, place the robot in a safe stopped state.

Do not simply increase the watchdog timeout to hide the problem.

### Acceptance criteria

Simulate:
1. Claude/API hangs for 10 seconds.
2. Vision worker hangs.
3. Sensor worker fails.
4. Control loop stalls.

In each case, the robot must enter a safe state without waiting for the AI.

---

# 5. Priority 0 — E-Stop Integration

## Current issue

The physical E-stop provides hardware safety, but software should also know that E-stop is active.

## Required design

Support an E-stop status input to the controller/Pi when the hardware design permits it.

State:

```text
ESTOP_ACTIVE
ESTOP_RELEASED
ESTOP_RESET_REQUIRED
```

When E-stop is active:

- motor commands are rejected
- autonomous navigation stops
- AI-generated motion is ignored
- current mission pauses/fails safely
- system logs the event
- recovery requires an explicit reset sequence

Do not automatically resume motion merely because the E-stop signal returns to normal.

---

# 6. Priority 0 — Battery Voltage Logic

## Problem

The current configuration mixes voltage thresholds with implied state-of-charge terminology.

WildWilly uses a 3S LiPo architecture.

A fully charged 3S LiPo is approximately 12.6 V.

Do not label ~11.4 V as "full" unless a measured/load-compensated model explicitly justifies that terminology.

## Required changes

Separate:

### Protection thresholds

```text
BATTERY_WARN_V
BATTERY_RTH_V
BATTERY_SAFE_V
BATTERY_SHUTDOWN_V
```

from:

### State-of-charge estimation

Create a separate SOC model if desired.

SOC should not be calculated from a simple linear voltage mapping while the battery is under significant load.

Document that voltage under load is not equivalent to open-circuit voltage.

---

# 7. Priority 1 — RP2040 Encoder Architecture

## Problem

MCP23017 polling from the Pi can miss encoder edges at higher speeds.

WildWilly's planned architecture includes an RP2040 encoder processor.

## Required direction

Implement an RP2040 encoder interface as the preferred encoder source:

```text
Wheel encoder A/B
       |
       v
RP2040 hardware quadrature decoding
       |
       +--> left count
       +--> right count
       +--> velocity
       +--> timestamp
       |
       v
Raspberry Pi
```

The Pi should receive accumulated counts rather than attempting to decode high-rate quadrature transitions itself.

## Required API

Define a stable interface returning at minimum:

```text
timestamp
left_count
right_count
left_velocity
right_velocity
status
```

Include rollover/error handling.

Keep a mock encoder provider for development.

---

# 8. Priority 1 — Odometry

Add a proper differential-drive odometry layer.

Inputs:

- left encoder count
- right encoder count
- wheel diameter
- wheel track
- encoder resolution
- direction

Output:

```text
x
y
heading
linear_velocity
angular_velocity
timestamp
```

Maintain a robot pose object.

The pose must be available to navigation, mapping, logging, and diagnostics.

Do not claim localization accuracy beyond what the sensors support.

---

# 9. Priority 1 — World Model

## This is the major missing subsystem.

WildWilly needs a persistent representation of its environment.

Implement a `world_model` package with a clean interface.

At minimum support:

```text
RobotState
Pose
Room
Doorway
Obstacle
Object
Landmark
Route
Observation
```

Example:

```python
WorldModel.update_observation(...)
WorldModel.get_robot_pose()
WorldModel.get_nearby_obstacles(...)
WorldModel.get_room(...)
WorldModel.remember_object(...)
WorldModel.save()
WorldModel.load()
```

Do not pretend this is full SLAM initially.

The first implementation can be a layered world model:

```text
Layer 1: local obstacle map
Layer 2: robot odometry
Layer 3: room/semantic information
Layer 4: known objects/landmarks
Layer 5: learned routes
```

---

# 10. Priority 1 — Mapping / Learning Mode

Implement a dedicated learning/exploration mode.

The robot should be able to:

1. Start mapping mode.
2. Record odometry.
3. Record sensor observations.
4. Detect obstacles.
5. Record visual landmarks.
6. Identify probable rooms/areas when possible.
7. Store the resulting map.
8. Resume a later session and load the map.

The system should not require a complete SLAM implementation in the first milestone.

Create the architecture so a proper SLAM backend can later replace the initial mapping backend.

---

# 11. Priority 1 — Navigation Layer

Separate navigation from raw obstacle avoidance.

Required layers:

```text
Mission
  |
  v
Global route/path
  |
  v
Local planner
  |
  v
Obstacle avoidance
  |
  v
Safety gate
  |
  v
Motor controller
```

The current sonar-based reactive avoidance can remain as the local fallback.

Do not remove it.

It should become a safety/local-avoidance mechanism rather than the complete navigation system.

---

# 12. Priority 1 — YOLO / Vision Integration

Keep the existing detector abstraction.

Improve it so detections can eventually become world-model observations.

A detection should include:

```text
class
confidence
bounding_box
timestamp
camera_id
estimated bearing
estimated range (if available)
```

Do not describe bounding-box-size distance estimation as accurate ranging.

If depth/range is unavailable, explicitly mark range as estimated.

Future architecture:

```text
Camera
  |
YOLO
  |
Detection
  |
Sensor fusion
  |
World Model
```

---

# 13. Priority 1 — Memory Architecture

The current SQLite memory system is a useful starting point.

Expand it into three logical categories.

## Operational memory

RAM:

- current mission
- current robot state
- current map
- active obstacles

## Long-term robot memory

SSD:

- maps
- experiences
- object locations
- room knowledge
- learned routes
- semantic memories
- mission history

## System/recovery storage

SD:

- OS
- configuration
- logs needed for recovery
- deployment files
- backup configuration

Do not hard-code assumptions about exact mount paths.

Create configurable storage paths.

Example:

```text
WILLY_DATA_ROOT
WILLY_MAP_ROOT
WILLY_MEMORY_ROOT
WILLY_LOG_ROOT
```

Add startup checks for storage availability and permissions.

---

# 14. Priority 1 — AI / LLM Interface

Keep AI modular.

Implement:

```text
AIProvider
LocalAIProvider
CloudAIProvider
```

The rest of Willy should not care which model is used.

The AI should receive a structured world state rather than raw random sensor values.

Example:

```json
{
  "robot": {
    "room": "kitchen",
    "pose": {...},
    "battery": 78
  },
  "goal": "find the red cup",
  "nearby_objects": [...],
  "nearby_obstacles": [...],
  "available_routes": [...]
}
```

AI output must be structured and validated.

---

# 15. Priority 1 — AI Confidence

Do not use "valid JSON" as AI confidence.

Separate:

```text
parse_success
intent_confidence
action_confidence
safety_validation
```

A correctly parsed answer is not automatically a confident answer.

If confidence is insufficient:

- ask for clarification
- fall back to deterministic behavior
- or safely stop

---

# 16. Priority 1 — Retrieval Behavior

Keep the existing retrieval state machine, but restructure it so that:

```text
LOCALIZE
APPROACH
GRASP
VERIFY
PLAN_RETURN
NAVIGATE_RETURN
DELIVER
CONFIRM
```

are distinct states.

The current handoff behavior must not be described as full requester navigation.

Add interfaces for:

- arm calibration
- inverse kinematics
- object pose
- grasp verification
- requester location
- return navigation

Stub unsupported capabilities cleanly rather than pretending they exist.

---

# 17. Priority 2 — Stair-Climbing Preparation

WildWilly is built on a stair-climbing rover chassis.

Do not implement autonomous stair climbing yet unless the hardware and testing plan explicitly support it.

However, prepare the software architecture for it.

Add a future navigation state:

```text
STAIR_DETECTED
STAIR_ASSESSMENT
STAIR_APPROACH
STAIR_CLIMB
STAIR_EXIT
STAIR_ABORT
```

Initially these may be disabled.

The safety controller must be able to reject stair commands unless stair mode is explicitly enabled and the required sensors/calibration are available.

---

# 18. Priority 2 — Configuration Cleanup

Audit every configuration value against the current WildWilly engineering package.

Especially verify:

- I²C addresses
- GPIO assignments
- battery thresholds
- watchdog
- motor limits
- servo limits
- camera settings
- AI settings
- email/cloud settings
- storage locations

Remove contradictions between documentation and code.

Do not enable cloud AI or email by default unless the engineering package explicitly says so.

Use environment/configuration values for credentials.

Never hard-code credentials.

---

# 19. Priority 2 — Hardware Abstraction

The hardware layer should expose clean interfaces such as:

```text
MotorController
ServoController
EncoderProvider
IMUProvider
RangeSensorProvider
PowerMonitor
CameraProvider
EStopProvider
```

Every interface needs:

- real implementation
- mock/simulation implementation
- health/status reporting

This will allow the complete autonomy stack to be tested without the physical robot.

---

# 20. Testing Requirements

Add automated tests for:

### Safety

- E-stop
- low battery
- obstacle
- invalid AI command
- excessive speed
- command timeout
- sensor failure

### Control

- non-blocking movement
- watchdog heartbeat
- motor stop
- command cancellation

### Encoders

- forward motion
- reverse motion
- differential motion
- rollover
- missing encoder data

### Odometry

- straight line
- rotation
- combined motion

### AI

- malformed JSON
- missing fields
- invalid action
- excessive duration
- invalid speed
- AI timeout

### Memory

- save/load
- corrupted database handling
- unavailable SSD
- unavailable SD

### Navigation

- blocked path
- obstacle avoidance
- no route
- return-to-home

---

# 21. Logging / Diagnostics

Use structured logging.

Every major subsystem should report:

```text
timestamp
subsystem
event
severity
status
```

Important safety events must be persistent.

Examples:

```text
ESTOP_ACTIVE
LOW_BATTERY
MOTOR_FAULT
ENCODER_FAULT
IMU_FAULT
AI_TIMEOUT
WATCHDOG_FAULT
NAVIGATION_ABORT
OBSTACLE_STOP
```

---

# 22. Documentation Update

Update the repository documentation after implementation.

Every subsystem must clearly identify:

```text
IMPLEMENTED
HARDWARE REQUIRED
SIMULATION ONLY
PARTIALLY IMPLEMENTED
PLANNED
```

Update architecture diagrams to reflect:

```text
AI
World Model
Navigation
Safety
Hardware
```

Do not describe the robot as having SLAM, autonomous house navigation, persistent spatial memory, or stair climbing unless those functions are actually implemented and tested.

---

# 23. Required Final Deliverables

After making changes, provide:

1. Modified source code.
2. Updated configuration.
3. Updated documentation.
4. Unit tests.
5. Simulation/mock tests.
6. A migration/change log.
7. A list of hardware tests still required.
8. A list of capabilities that remain unimplemented.
9. A final architecture diagram.

Also provide a file-by-file summary:

```text
FILE
CHANGE
REASON
TEST STATUS
HARDWARE DEPENDENCY
```

---

# 24. Implementation Order

Do not implement everything simultaneously.

Use this order:

## Phase 1 — Safety

1. Non-blocking control loop
2. Safety gate
3. Watchdog
4. E-stop
5. Battery logic
6. Motor command validation

## Phase 2 — Motion foundation

7. RP2040 encoder interface
8. Odometry
9. Robot pose
10. Hardware health/status

## Phase 3 — World model

11. World-model data structures
12. Local obstacle map
13. Persistent storage
14. Learning/exploration mode

## Phase 4 — Navigation

15. Global navigation interface
16. Local planner
17. Reactive sonar fallback
18. Route persistence

## Phase 5 — Vision/AI

19. YOLO → world observations
20. AI world-state interface
21. AI worker
22. AI validation
23. Local/cloud provider abstraction

## Phase 6 — Memory

24. SSD persistent memory
25. semantic memory
26. episodic memory
27. learned routes

## Phase 7 — Advanced behavior

28. Retrieval improvements
29. requester navigation
30. stair-climbing software preparation
31. future stair autonomy

---

# 25. Critical Design Principle

The final architecture must enforce this rule:

> **Willy's AI may decide what it wants to accomplish, but it may never decide whether it is safe to move.**

The hierarchy must be:

```text
AI / Mission
      ↓
World Model
      ↓
Navigation
      ↓
Safety Controller
      ↓
Motor Controller
      ↓
Hardware
```

Safety is authoritative.

AI is advisory/planning.

Real-time motor protection must continue operating if the AI disappears completely.

---

# 26. Do Not Overbuild the First Milestone

The immediate target is NOT "finish autonomous Willy."

The immediate target is:

> Build a reliable, non-blocking, safety-controlled motion platform with accurate encoder/odometry data and a persistent world-model foundation.

Once that exists, YOLO, local AI, memory, navigation, and autonomous behavior can be added without having to rewrite the robot's core control architecture.

---

# 27. Final Instruction to Claude

Review the existing repository against this document first.

Before modifying code:

1. Identify which requirements are already satisfied.
2. Identify partial implementations.
3. Identify missing components.
4. Identify conflicts with the existing hardware/documentation.
5. Produce a concise implementation plan.

Then implement the changes in the priority order above.

Do not fabricate hardware capabilities.

Do not bypass safety for convenience.

Do not make the LLM responsible for real-time motor safety.

Preserve working code where it is architecturally sound.

After implementation, run all available tests and clearly report what was tested versus what still requires physical WildWilly hardware testing.
