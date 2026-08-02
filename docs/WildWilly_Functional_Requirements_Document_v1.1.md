**Willy Functional Requirements Document (FRD)\
Version 1.0**

# 1. Purpose

This Functional Requirements Document defines the required behavior, safety functions, control systems, autonomy, mobility, and future capabilities of the WildWilly robotic platform.

# FR-100 System Startup and Initialization

  --------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                        Priority          Verification
  ----------------- -------------------------------------------------- ----------------- -----------------
  FR-100-001        Automatically start control software at power-up   High              Test

  FR-100-002        Initialize I2C bus and connected devices           High              Test

  FR-100-003        Run startup self-test                              High              Test

  FR-100-004        Prevent motion until startup checks pass           High              Test
  --------------------------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-200 Power Monitoring and Protection

  -------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                       Priority          Verification
  ----------------- ------------------------------------------------- ----------------- -----------------
  FR-200-001        Monitor battery voltage, current and power        High              Test

  FR-200-002        Detect undervoltage and overcurrent conditions    High              Test

  FR-200-003        Warn user before critical battery level           High              Test

  FR-200-004        Perform safe shutdown at critical battery level   High              Test
  -------------------------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-300 Safety and Emergency Stop

  ------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                      Priority          Verification
  ----------------- ------------------------------------------------ ----------------- -----------------
  FR-300-001        Monitor physical E-stop continuously             High              Test

  FR-300-002        Disable all motion immediately on E-stop         High              Test

  FR-300-003        Require operator reset before movement resumes   High              Test

  FR-300-004        Stop robot on critical controller failure        High              Test
  ------------------------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-400 Mobility and Drive Control

  ---------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                         Priority          Verification
  ----------------- --------------------------------------------------- ----------------- -----------------
  FR-400-001        Control left and right drive motors independently   High              Test

  FR-400-002        Support forward, reverse and turning motion         High              Test

  FR-400-003        Ramp speed commands smoothly                        High              Test

  FR-400-004        Enforce software speed limits                       High              Test
  ---------------------------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-500 Encoder and Speed Control

  ---------------------------------------------------------------------------------------------
  Requirement ID    Requirement                             Priority          Verification
  ----------------- --------------------------------------- ----------------- -----------------
  FR-500-001        Read wheel encoders                     High              Test

  FR-500-002        Calculate speed and distance            High              Test

  FR-500-003        Detect stalls and unexpected movement   High              Test

  FR-500-004        Maintain closed-loop speed control      High              Test
  ---------------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-600 Steering Control

  -------------------------------------------------------------------------------------
  Requirement ID    Requirement                     Priority          Verification
  ----------------- ------------------------------- ----------------- -----------------
  FR-600-001        Control steering servo          High              Test

  FR-600-002        Maintain calibration settings   High              Test

  FR-600-003        Limit steering travel           High              Test

  FR-600-004        Support manual override         High              Test
  -------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-700 Robotic Arm Control

  --------------------------------------------------------------------------------
  Requirement ID    Requirement                Priority          Verification
  ----------------- -------------------------- ----------------- -----------------
  FR-700-001        Control all arm joints     High              Test

  FR-700-002        Support preset positions   High              Test

  FR-700-003        Enforce joint limits       High              Test

  FR-700-004        Stop arm during E-stop     High              Test
  --------------------------------------------------------------------------------

# Acceptance Criteria

# FR-800 Sensor Systems

  ---------------------------------------------------------------------------------
  Requirement ID    Requirement                 Priority          Verification
  ----------------- --------------------------- ----------------- -----------------
  FR-800-001        Read IMU orientation data   High              Test

  FR-800-002        Read sonar obstacle data    High              Test

  FR-800-003        Detect excessive tilt       High              Test

  FR-800-004        Report sensor health        High              Test
  ---------------------------------------------------------------------------------

# Acceptance Criteria

# FR-900 Manual Operations

  ---------------------------------------------------------------------------------------
  Requirement ID    Requirement                       Priority          Verification
  ----------------- --------------------------------- ----------------- -----------------
  FR-900-001        Accept remote operator commands   High              Test

  FR-900-002        Display robot status              High              Test

  FR-900-003        Stop on communication loss        High              Test

  FR-900-004        Allow emergency override          High              Test
  ---------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-1000 Autonomous Navigation

  ---------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                   Priority          Verification
  ----------------- --------------------------------------------- ----------------- -----------------
  FR-1000-001       Navigate without operator input               High              Test

  FR-1000-002       Avoid obstacles                               High              Test

  FR-1000-003       Maintain planned route                        High              Test

  FR-1000-004       Transfer control back to operator on demand   High              Test
  ---------------------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-1100 Diagnostics and Logging

  ------------------------------------------------------------------------------------
  Requirement ID    Requirement                    Priority          Verification
  ----------------- ------------------------------ ----------------- -----------------
  FR-1100-001       Monitor subsystem health       High              Test

  FR-1100-002       Record warnings and faults     High              Test

  FR-1100-003       Maintain timestamped logs      High              Test

  FR-1100-004       Provide diagnostic test mode   High              Test
  ------------------------------------------------------------------------------------

# Acceptance Criteria

# FR-1200 Mobility Intelligence and Stair Navigation

  --------------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                              Priority          Verification
  ----------------- -------------------------------------------------------- ----------------- -----------------
  FR-1200-001       Detect stairways                                         High              Test

  FR-1200-002       Select floor or stair mode                               High              Test

  FR-1200-003       Monitor traction and tilt during climbing                High              Test

  FR-1200-004       Support multi-floor navigation through the world model   High              Test
  --------------------------------------------------------------------------------------------------------------

# Acceptance Criteria

WildWilly shall initialize correctly, operate safely under manual control, detect faults, avoid obstacles, support autonomous navigation, and enter a safe state when power, communications, or safety conditions become invalid.

# Mission-Level Functional Requirements (M-001--M-012)

Moved here from the WildWilly Master Engineering Package (rev 6.0) so this document is the single source for all functional-requirement content. These are the mission-level requirements referenced by that document\'s requirements-traceability table (its section 2.3); the FR-xxx requirements above remain the detailed, subsystem-level breakdown. M-006 (stair climbing) was reclassified from a must-have to a stretch goal on 2026-07-18 --- the rover\'s baseline scope is drive, see, talk/listen, arm pick/place on flat ground, and basic flat-terrain autonomy.

  ---------------------------------------------------------------------------------------------------------
  ID             Requirement                                            Class
  -------------- ------------------------------------------------------ -----------------------------------
  M-001          Autonomous navigation                                  Baseline

  M-002          Voice command processing                               Baseline

  M-003          Local AI inference                                     Baseline

  M-004          Object recognition                                     Baseline

  M-005          Obstacle avoidance                                     Baseline

  M-006          Stair climbing                                         STRETCH (reclassified 2026-07-18)

  M-007          Robotic-arm manipulation (pick/place on flat ground)   Baseline

  M-008          Battery monitoring                                     Baseline

  M-009          Thermal monitoring                                     Baseline

  M-010          Emergency shutdown                                     Baseline

  M-011          Remote administration                                  Baseline

  M-012          Local data storage                                     Baseline
  ---------------------------------------------------------------------------------------------------------
