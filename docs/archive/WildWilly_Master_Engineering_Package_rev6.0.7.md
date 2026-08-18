**WildWilly Autonomous Rover**

Master Engineering Package

**Revision 6.0 · Reorganized & Finalized Baseline**

Document Control

  -----------------------------------------------------------------------
  **Field**                           **Value**
  ----------------------------------- -----------------------------------
  Project                             WildWilly Autonomous Rover

  Revision                            6.0 (supersedes 5.80; consolidates
                                      and corrects all content through
                                      2026-07-30)

  Document Type                       Master Engineering Package

  Status                              Engineering Baseline ---
                                      Reorganized, De-duplicated,
                                      Corrected

  Owner                               Howard Himmel

  Scope baseline                      Drive + see + talk/listen + arm
                                      pick/place (flat ground) + basic
                                      flat-terrain autonomy.
                                      Stair-climbing is a STRETCH goal
                                      (reclassified 2026-07-18).
  -----------------------------------------------------------------------

**NOTE:** This revision is a structural and factual cleanup of rev 5.80,
not a new design pass. Rev 5.80 accumulated \~80 dated micro-revisions
as inline narrative, and several of those corrections never fully
propagated into the body sections they corrected --- multiple tables
still showed superseded I²C addresses, buck assignments, and servo
channel maps years (in build-time) after the correct values were
established. This revision (a) resolves every such contradiction in
favor of the latest bench-confirmed fact, (b) moves narrative \"DESIGN
ADDITION / INCIDENT / MILESTONE\" entries into the section they actually
belong to, (c) adds one authoritative address/pin table that the rest of
the document refers back to instead of restating, and (d) condenses the
80-entry revision log into a readable changelog. No new engineering
decisions were made in this pass --- where rev 5.80\'s own text
disagreed with itself, the entry with the latest date and
\"AUTHORITATIVE\" / \"CONFIRMED\" / \"bench-confirmed\" language won.

0\. Current Build Status & Open Items

This section is the fastest way to answer \"where does the build
actually stand.\" Everything below is current as of the last logged
session (2026-07-30).

0.1 Done

-   Rocker-bogie chassis: both suspension halves (L/R, 3 wheels each)
    built and joined; standing on all 6 wheels. Suspension issue
    reported 2026-08-02 --- resolved, confirmed functional.

-   Top/head assembly secured to the main frame: clasps installed
    2026-08-02.

-   Arm mechanically complete: base/shoulder, forearm, elbow, wrist,
    gripper assembled; link lengths measured (§11.6).

-   Power distribution physically finished: 12V, 6V, and 5V rails each
    on dedicated distribution boards (4 boards total after the 6V
    rearrangement).

-   All 6 drive motors landed: power to the two FeatherWings, encoders
    to the MCP23017, encoder VCC to the 3.3V rail (36 wires).

-   All 6 steering servos landed: signal to PCA9685 0x42, power direct
    to the 5V rail.

-   Sonar wiring complete on the base side (EPLZON → GPIO, all 3
    sensors).

-   Charging interface installed: shrouded EC5 pair + JST-XH balance
    lead, externally accessible for charge-in-place.

-   Switch 2 (Pi-cutoff in the DROK input line) built --- full wiring
    audit closed, no unbuilt items remain outside the 4 listed below.

-   Physical E-stop (latching NC mushroom, cuts the 12V bus) installed
    (2026-07-31) --- functional cut/latch/release test still to run
    during commissioning (§21.1).

-   Base-only staged power-up passed: 12V / 6V / 5V rails all verified
    good with the top assembly disconnected.

-   Full 9-device I²C roll-call was previously confirmed working
    end-to-end (see §0.3 for the current regression).

-   Claude Code installed and authenticated on Willy for on-device
    software development.

0.2 Remaining --- 4 deliberate connection points

These are intentionally the last connections: disconnecting all 4 fully
separates the top assembly (Pi, sensors, arm) from the base (chassis,
motors, steering, power) with nothing to desolder, which the build has
repeatedly needed for internal access.

  -----------------------------------------------------------------------
  **\#**                  **Connection**          **Detail**
  ----------------------- ----------------------- -----------------------
  1                       40-pin ribbon, base →   Route flat, no fold (a
                          top                     180° fold mirrors the
                                                  pinout); stripe → pin 1
                                                  at both ends;
                                                  meter-verify before
                                                  power (per the §7.4
                                                  ribbon incident).

  2                       Arm bulkhead → PCA9685  7 servo signal leads to
                          0x43                    CH0--CH6 (base→gripper
                                                  order); V+/GND direct
                                                  to the 6V rail.

  3                       Pi power feed           DROK 5.1V rail to the
                                                  Pi.

  4                       Sonar harness join      Base ↔ top/head ---
                                                  electrically already
                                                  complete; mechanical
                                                  join only.
  -----------------------------------------------------------------------

0.3 §Incident 25.16, PCA9685 boards hanging the I²C bus --- RESOLVED
(2026-08-01)

Both PCA9685 boards were found holding SDA stuck low, even completely
bare (no servos attached) and with base 12V power off. Isolation ruled
out servo wiring, VCC/V+ mixups, the ribbon, the bus node board, and the
Pi --- the fault was in the PCA9685 boards themselves. Replacement
boards ordered from Adafruit (same known-good-supplier approach that
resolved the earlier INA219 fault); both installed with their V+
decoupling caps (§10, §11.2) and confirmed on the bus. Full 9-device
roll-call passed clean 2026-08-01: 0x27, 0x40, 0x42, 0x43, 0x44, 0x45,
0x4A, 0x60, 0x61 (+0x70 All-Call) --- nothing missing, nothing
colliding. This closes the incident and clears commissioning gate C-4
(§21.1).

**NOTE:** A late design note (2026-07-30) observed that the original
\"leave PCA9685 V+ unused, run every servo\'s power leads directly to a
distribution board\" guidance was more complex than necessary --- with
two separate PCA9685 boards, each can simply take its own V+ (0x42→5V,
0x43→6V) and servos can plug straight into the channel headers. The
physical steering/arm harnesses are already built the split-lead way and
are not being redone; this is recorded for awareness on the replacement
boards or any future rebuild, not as a pending task.

0.4 Safety-critical open items

-   Physical E-stop (latching NC mushroom, cuts the 12V bus) ---
    INSTALLED (2026-07-31). Functional test (latch + release, motion cut
    confirmed) still to be run as part of the C-gates below.

-   Commissioning gates C-3 through C-8 (junction polarity, post-boot
    I²C, FET temperature under sustained load, steering torque under
    load) still need to be run and logged now that the base and top are
    close to fully landed --- see §21.

0.5 Engineering-review gates still open

-   §4.6 Mass properties & stability --- PENDING MEASUREMENT. Needs real
    CG data (arm stowed/deployed, full/low battery) once the top
    assembly is landed.

-   §21.7 Thermal acceptance --- proposed limits defined, not yet tested
    under sustained load.

-   USB-boot order (Pi 5 → boot from the SanDisk SSD rather than
    microSD) --- listed as a pending deploy task; not confirmed done in
    any later entry.

1\. System Overview

1.1 Purpose

WildWilly is a six-wheel autonomous rocker-bogie rover built for
mobile-robotics experimentation and, specifically, as a
fetch-and-deliver helper for a wheelchair-using family member. Core
capabilities: autonomous navigation, local AI inference, voice
interaction, object detection and tracking, obstacle avoidance, and
robotic manipulation. Rough-terrain and curb handling come from the
rocker-bogie suspension as a side benefit; autonomous stair-climbing
itself is a stretch goal, not a baseline requirement (§2.1).

1.2 Platform Summary

Base platform: WildWilly Stair-Climbing Rover (Printables #194299),
six-wheel rocker-bogie suspension. Nominal envelope 430 × 330 × 220 mm,
103 mm wheels. The original single-piece chassis was outgrown by the
payload (Pi 5, AI HAT+, power electronics, robotic arm, sensors, dual
battery packs) and replaced by an owner-designed widened, two-level,
multi-piece printed chassis (§4).

1.3 Current Architecture

Major subsystems beyond the base rover: Raspberry Pi 5 + Hailo AI HAT+
compute (front-mounted, \"Pi5 Face\"), two-camera vision, voice
interface, a 6-DOF/7-servo robotic arm, a 13-sensor network, a 5-rail
power-distribution system with per-pack battery protection and
charge-in-place, layered electrical safety, and a local-first autonomous
software stack. Motor control is fully I²C-based (2× Adafruit
FeatherWing #2927) --- there is no discrete motor-driver chip and no
direction/PWM GPIO wiring anywhere in the current design.

2\. Mission Requirements

2.1 Functional Requirements

The full functional requirements list has moved to the Functional
Requirements Document (WildWilly_Functional_Requirements_Document.docx),
which is the authoritative source for FR-xxx requirements, priorities,
and verification methods. The mission-level requirements (M-001--M-012)
referenced by the traceability table in §2.3 are enumerated there as
well, in a new \"Mission-Level Functional Requirements\" section.

**NOTE:** M-006 (stair climbing) was reclassified from must-have to
stretch goal on 2026-07-18 --- see the Functional Requirements Document
and §2.3 below for current status. This removes drivetrain stall-torque
pressure (the FeatherWing\'s 1.2 A/channel, 3 A peak, rating is ample
for flat/moderate terrain --- the concern only applied to sustained
stair climbing) and demotes the rocker-bogie flex-mechanism question
from a blocker to a future refinement.

2.2 Performance Objectives

Target runtime 4--8 h by mode. Navigation indoor/outdoor. Real-time
vision object detection. Compute: 26 TOPS local inference (Hailo AI
HAT+). Arm reach: 60.5 cm calculated / 59 cm measured fully extended
(§11.6) --- supersedes the earlier \~345 mm placeholder figure used
before the arm was physically measured.

2.3 Requirements Traceability

Verification method key: I = Inspection · A = Analysis · T = Test · D =
Demonstration.

  -----------------------------------------------------------------------------------------
  **ID**      **Owner        **Method**   **Verification**   **Pass/fail    **Status**
              subsystem**                                    criteria**     
  ----------- -------------- ------------ ------------------ -------------- ---------------
  M-001       software +     T/D          autonomy course    completes      pending build
              sensors +                   test               course, avoids 
              drive                                          obstacles      

  M-002       software       T            spoken-command     recognized +   pending build
              (audio)                     test               correct action 

  M-003       compute (AI    T            inference          runs offline   pending build
              HAT+)                       benchmark          at target rate 

  M-004       compute +      T            labeled-object     correct        pending build
              vision                      test               detection ≥    
                                                             target         

  M-005       sensors +      T/D          obstacle-course    no collisions  pending build
              software                    test                              

  M-006       mechanical +   T            stair test         climbs target  deferred ---
  (stretch)   drive                                          step height    not gating
                                                                            baseline

  M-007       arm + software T/D          pick/place test    reaches +      pending --- arm
                                                             grips target   mechanically
                                                                            complete, final
                                                                            electrical
                                                                            landing blocked
                                                                            on §0.3

  M-008       sensor +       T            calibrated voltage reported V     divider fixed
              software                    comparison         within 0.05 V  (§8.4);
                                                                            calibration
                                                                            pending

  M-009       sensors +      T            thermal-load test  flags          pending build
              software                                       over-temp      
                                                             correctly      

  M-010       safety + power T            E-stop cut test    motion bus     E-stop
                                                             cut, latched   installed
                                                                            (2026-07-31);
                                                                            functional cut
                                                                            test pending

  M-011       software       D            Cockpit access     admin          partial (host
              (network)                   test               reachable on   up)
                                                             :9090          

  M-012       compute (SSD)  T            read/write + boot  boots + logs   SSD on hand,
                                          test               from SSD       USB-boot order
                                                                            pending (§0.5)
  -----------------------------------------------------------------------------------------

**As-built note (2026-08-09):** this table's Status column predates the
entire software build (Phases 1-6 + audit follow-on, landed
2026-08-07/09) and was never revisited alongside it — most rows still
read "pending build" for software that has since shipped.
`WildWilly_Functional_Requirements_Document_v2.2.md` is now the
authoritative, actively-maintained source for M-table status (its own
text: "moved here... so this document is the single source for all
functional-requirement content") — see that file's M-table section for
current per-item status rather than trusting this row's "Status" text.
Compact gloss, software side only (mechanical/electrical build status
above in §0 is separately current): M-001 (navigation), M-002 (voice),
M-003 (local AI), M-004 (vision/YOLO), M-005 (obstacle avoidance) are
all code-complete at milestone-1 scope but motion has not been
hardware-verified live; M-002's voice pipeline is additionally disabled
today (`ENABLE_VOICE=False` — model files not yet provisioned on this
unit); M-009 (thermal monitoring) is fully unbuilt, not just untested;
M-011 as defined *here* ("Cockpit access test, :9090") is a different
capability than M-011 as defined in the FRD ("Remote administration") —
neither is built, but the two documents don't even agree on what M-011
means; worth reconciling with the owner rather than guessing which
definition is authoritative.

3\. System Architecture

3.1 System Actuator & Sensor Census (final)

Totals: 6 drive motors + 13 servos (6 steering + 7 arm) = 19 actuators;
6 encoders + 3 sonar + 1 IMU + 3 current monitors = 13 sensors; 2
cameras.

  --------------------------------------------------------------------------
  **Class**               **Qty**                 **Detail (bus / channel /
                                                  rail)**
  ----------------------- ----------------------- --------------------------
  Drive motors            6                       JGA25-370B 12V gearmotors
                                                  --- 2× Adafruit
                                                  FeatherWing #2927 (I²C
                                                  \@0x60 LEFT / 0x61 RIGHT),
                                                  12V to VIN via F2 10A. No
                                                  discrete driver chip, no
                                                  direction/PWM GPIO.

  Wheel encoders          6                       Integral to the drive
                                                  motors --- quadrature A/B
                                                  via MCP23017 0x27
                                                  (bench-confirmed; corrects
                                                  the originally-documented
                                                  0x20).

  Steering servos         6                       GDW DS041MG 180° ---
                                                  PCA9685 0x42, CH0--5, 5V
                                                  rail direct.

  Arm servos              7                       4× MG996R (base J0,
                                                  shoulder J1a/J1b, elbow
                                                  J2) + 3× MG90S (wrist
                                                  rotate J3, wrist pitch J4,
                                                  gripper J5) --- PCA9685
                                                  0x43, CH0--6, ALL on the
                                                  6V/DZS rail (final,
                                                  2026-07-28).

  Cameras                 2                       Front Arducam IMX708 (CSI,
                                                  ORB-SLAM3 + forward YOLO);
                                                  Rear OV9782 (USB,
                                                  YOLO/monitoring + descent
                                                  view).

  Sonar                   3                       HC-SR04
                                                  front(center)/left/right
                                                  --- TRIG GP5/13/4, ECHO
                                                  GP26/14/21 (÷ dividers).
                                                  No rear sonar exists.

  IMU                     1                       BNO085 9-DoF, I²C 0x4A,
                                                  INT→GP15, RST→MCP23017
                                                  spare pin.

  Current monitors        3                       INA260 servo/steering 0x40
                                                  (replaced a faulty
                                                  INA219), INA260 Pi 0x44,
                                                  INA260 motor 0x45.
  --------------------------------------------------------------------------

3.2 Subsystems

Nine major subsystems: A. Structure · B. Power Distribution · C. Compute
Core · D. Sensor Network · E. Drive System · F. Steering System · G.
Robotic Arm · H. User Interface · I. Safety System.

3.3 Architectural Philosophy

Modular construction, serviceable wiring (four deliberate top/base
disconnect points, §0.2), independent power rails, distributed sensing,
centralized decision making, fail-safe operation, expandability.

3.4 High-Level Architecture

Battery System → Protection System → Power Distribution → Compute +
Sensors + Motion Systems → Autonomous Control.

4\. Mechanical Design Package

4.1 Chassis

Widened two-level architecture, developed because the original WildWilly
frame could not house the Pi 5, AI HAT+, power electronics, arm,
sensors, and dual battery packs. Retains the original rocker-bogie
suspension geometry. Frame is split multi-piece (also exceeds the print
bed as a single piece); mirrored parts (suffix \"m\") must be printed
mirrored, not duplicated.

4.2 Structural Layout

Lower level: left and right battery bays flanking a central power tray
(packs mounted low, vented, hatch-accessible for charge/swap). Upper
level: sensor tray and controller tray, both mounted horizontally,
wiring distribution, compute support structure.

4.3 Front Compute Bay (\"Pi5 Face\")

Raspberry Pi 5, AI HAT+, display, audio, and active cooling are mounted
LOW on the front of the body, with the arm turret directly above. The
display faces forward, top edge nearly flush with the top of the body.
This front-mounted layout (lower CG, no overhang, short camera FFC)
supersedes an earlier rear-cantilever \"pod\" concept. The active cooler
must exhaust to the front/sides, not straight up into the arm above it
--- confirm airflow path and AI HAT+ temperature under sustained
inference. The arm turret\'s full sweep, not just its stow position,
must clear the AI HAT+ (the tallest element of the stack).

4.4 Robotic Arm Mount

Arm mounts to the front deck, J0 turret \~40 mm aft of the Pi5 Face
front face to avoid collision. 6-DOF, 7 servos (§11) sourced from
MakerWorld 1134925 (standalone 6-axis arm), adapted onto WildWilly\'s
front-deck turret. Stow pose: single boom folded/pitched down, confirmed
to sit below the front camera\'s sightline through the full motion
envelope, not just at rest.

4.5 Weight and Center of Gravity

The CG model remains ESTIMATED. See §4.6 --- this is an open
engineering-review gate, not yet closed.

4.6 Mass Properties & Stability Closure --- PENDING MEASUREMENT

Required closure data, to be measured on the assembled rover:

  -----------------------------------------------------------------------
  **Condition**     **Whole-rover CG  **Static tip-over **Notes**
                    (x/y/z)**         angle**           
  ----------------- ----------------- ----------------- -----------------
  Arm stowed, full  --- / --- / ---   ---°              baseline
  battery                                               

  Arm stowed, low   --- / --- / ---   ---°              CG shift as packs
  battery                                               deplete

  Arm deployed (max --- / --- / ---   ---°              worst forward
  reach), full                                          moment
  battery                                               

  Arm deployed, low --- / --- / ---   ---°              combined worst
  battery                                               case
  -----------------------------------------------------------------------

Operating limits to derive from the above (also pending): max safe arm
extension while moving, speed limit while arm deployed, payload limit at
full reach, payload limit at mid reach.

5\. Electrical Design Package

5.1 Design Philosophy

Four principles: independent power domains, single-point grounding,
distributed protection, serviceable wiring.

5.2 Address & Pin Map --- the single authoritative table

This is the corrected, bench-confirmed, final address map. Every other
section and table in this document refers back to this one rather than
restating it. Where any figure elsewhere in earlier revisions disagreed
with this table (several did --- see the rev 6.0 note in Document
Control), this table is correct.

  -----------------------------------------------------------------------
  **Address / Bus**       **Device**              **Role**
  ----------------------- ----------------------- -----------------------
  0x27                    MCP23017                Encoder GPIO expander
                                                  (6 encoders, quadrature
                                                  A/B). Bench reads 0x27,
                                                  not the
                                                  originally-documented
                                                  0x20 --- address pins
                                                  read CLOSED; owner
                                                  elected to keep
                                                  switches as-is rather
                                                  than re-flip.

  0x40                    INA260 (servo/steering  Replaced a faulty
                          current)                INA219 (2026-07-27). No
                                                  jumpers = default
                                                  address, freed by
                                                  removing the INA219.

  0x42                    PCA9685                 Steering --- 6
                                                  channels, CH0--5.

  0x43                    PCA9685                 Arm --- 7 channels,
                                                  CH0--6.

  0x44                    INA260                  Pi 5V rail current.

  0x45                    INA260                  Motor 12V rail current.

  0x4A                    BNO085                  IMU. INT→GP15 (labeled
                                                  \"RX\" on the Nano HAT
                                                  Hacker, UART group ---
                                                  not a numbered pin),
                                                  RST→MCP23017 (0x27)
                                                  port B bit 4, confirmed
                                                  2026-08-08 (previously
                                                  only \"spare pin\", no
                                                  bit number) --- now
                                                  wired in software too
                                                  (§8.2, §13.1).

  0x60                    Adafruit FeatherWing    LEFT motor driver ---
                          #2927                   LF/LM/LR.

  0x61                    Adafruit FeatherWing    RIGHT motor driver ---
                          #2927                   RF/RM/RR.

  0x70                    (PCA9685 All-Call)      Reserved broadcast
                                                  address --- appears in
                                                  roll-call, not a real
                                                  device.

  0x48                    ADS1115                 Battery-voltage ADC, A0
                                                  (divider --- §8.4).
                                                  Replaced MCP3008
                                                  2026-08-01 (§25
                                                  changelog) --- MCP3008
                                                  retired to spares.

  no address              LTC4311                 I²C bus accelerator,
                                                  transparent
                                                  pass-through at the far
                                                  end of the bus run.
  -----------------------------------------------------------------------

**NOTE:** Full 10-device roll-call (excludes LTC4311, which is a
transparent pass-through with no address of its own): 0x27, 0x40, 0x42,
0x43, 0x44, 0x45, 0x48, 0x4A, 0x60, 0x61 (+0x70 All-Call). 0x48
(ADS1115) added 2026-08-01, replacing the SPI-only MCP3008 for battery
sensing. This has been bench-confirmed working simultaneously multiple
times; the current open incident (§0.3) is isolated to the two PCA9685
boards themselves, not the bus or address map.

5.3 Power Domains

Domain A motor rail (12V) · Domain B servo/steering rail (5V) · Domain C
arm rail (6V) · Domain D compute rail (5V, isolated from Domain B).

5.4 Protection Layers

Primary: 30A ATC main fuse (F1, off-board). Secondary: branch fuses
F2--F6 (§6.4). Reverse-polarity: FQP27P06 P-channel MOSFET (Q1) with a
220nF gate-source soft-start cap (added after the DZS failure incident,
§6.7). Transient: P6KE15A TVS (D1). Per-pack backstop: dual 3S BMS
(§6.2). Emergency shutdown: physical latching mushroom E-stop ---
INSTALLED (2026-07-31) --- plus Switch 2 (Pi-only cutoff, §6.6).

5.5 Grounding Strategy

Single-point, two-level (star-of-stars) ground. Power-tray grounds
return to the common rail (single-point star / battery-return side);
control-tray grounds collect on local buses that connect to the common
rail by exactly one link. Rule: no second inter-tray ground path (a
conductive standoff, frame, or dual-grounded device bridging both trays
is a ground loop). PCA9685 reference-grounds and encoder logic grounds
land on the control-tray bus, not the power rail directly.

5.6 Formal Schematic Set --- status

Ten schematic-style sheets exist as a build/wiring reference. Two are
confirmed current against this revision\'s address map (Power Schematic
and I²C Network Schematic, both redrawn 2026-07-19/20 against
bench-confirmed addressing). The remaining sheets (GPIO, Motor, Servo,
Arm, Pi5 Face wiring, and the two reference sheets) were drawn against
the pre-FeatherWing / pre-final-address architecture and are flagged for
a redraw pass in a future revision --- treat the tables in this document
as authoritative over any schematic image until that redraw is done. The
recently-added reference diagrams (BMS wiring, charge-in-place,
I²C/power bus node board, EPLZON CH7 divider) are current as of their
addition date and are reproduced below.

![](media/b8d5106fdcb3a289da623dc616271951b40236c0.png){width="6.0in"
height="4.3125in"}

*Power Schematic --- current, bench-confirmed addressing (2026-07-19).*

![](media/660192b49ed6b5b918dcad10134802b1f0686b8c.png){width="6.0in"
height="4.177083333333333in"}

*I²C Network Schematic --- current, bench-confirmed addressing including
0x60/0x61 (2026-07-20).*

![](media/e4db6e77a4cc638d5ef6385fbac4059f07a0178f.png){width="6.0in"
height="4.104166666666667in"}

*I²C / Power Bus Node Board --- 4 rails (3V3/SDA/SCL/GND), 8 device
taps, LTC4311 + pull-ups. This exact board previously had 3V3/GND
swapped onto SDA/SCL (§7.5 incident) --- the standing rule since then is
to meter-verify every tap of any home-built bus board before first
power-up.*

![](media/bb9edc485277287abeb6c2f39bc697000a7ada78.png){width="5.5in"
height="5.39494750656168in"}

*EPLZON board --- updated 2026-08-02 to remove the retired MCP3008
(§8.4); board now shows all 4 voltage dividers (3× sonar ECHO + 1×
battery sense) with the battery divider\'s midpoint routed to ADS1115 A0
off-board. Schematic reference only --- use the board\'s own printed
A--J/numbered grid for physical placement.*

![](media/ff4f9c1a07bd9290ed9e43623695b4357ee669f9.png){width="6.0in"
height="4.0625in"}

*Dual-BMS wiring --- one BMS per pack before the parallel junction;
positives bypass, negatives through B−/P−; balance taps and the
paraboard share cell nodes.*

![](media/915e6c0f66756fd166fcf639a281a56867297407.png){width="6.0in"
height="4.0625in"}

*iMAX B6 charge-in-place --- T-tapped main leads to a shrouded jack,
paraboard-combined balance via JST-XH extension to the charger.*

6\. Power System Design

6.1 Battery System

Two 3S LiPo packs, 8000 mAh each, hard-paralleled (\~16,000 mAh @ 11.1V
nominal). Mounted low, left and right, flanking the central power tray.
Packs must be within 0.05 V/cell before paralleling --- never join a
charged pack to a depleted one.

6.2 Per-Pack BMS (added 2026-07-18)

One BMS per pack (40--60A, with balance), wired BEFORE the parallel
junction, permanent (soldered) install --- a discharge/short backstop
layered under the existing P-FET/TVS/fuse protection, not a replacement
for it.

-   Pack + (positive) bypasses the BMS, straight to the parallel
    junction.

-   Pack − → BMS B−; BMS P− (protected negative) → parallel junction.
    Negative-side switching only, never positive.

-   Balance taps: each pack\'s JST-XH 4-pin → BMS pads B0/B1/B2/B+,
    strictly in 0/4.2/8.4/12.6V order (out-of-order = board damage). The
    2×3S paraboard shares the same nodes.

-   Main current wire ≥12 AWG. Test every undocumented board (B−→P−
    pass, cell taps read) before soldering in permanently.

6.3 Main Power Path

Battery → per-pack BMS → parallel junction → 30A main fuse (F1) → KCD4
master switch → E-stop → FQP27P06 reverse-polarity FET (Q1) → protected
12V bus → subsystem fuses F2--F6.

6.4 Power Rails & Distribution Boards

Five voltage rails, five distribution boards. The Pi 5V rail is the only
one with no distribution board (feeds the header pins directly).

  ---------------------------------------------------------------------------------
  **Rail**         **Nominal   **Source**   **Fuse**    **Feeds**     **Current
                   V**                                                monitor**
  ---------------- ----------- ------------ ----------- ------------- -------------
  Motor (VM)       12V         +12V bus     F2 10A      2×            INA260 0x45,
                                                        FeatherWing   inline before
                                                        VIN (6 drive  the
                                                        motors)       FeatherWing
                                                                      split

  Pi input         12V         +12V bus     F3 5A       DROK 12A buck ---
                                                        input         

  Servo/steering   5V          FEICHAO 8A   F4 10A      6× DS041MG    INA260 0x40
                               UBEC                     steering + 3× 
                                                        sonar VCC     

  Arm              6V          DZS 12A buck F5 10A      All 7 arm     monitored via
                                                        servos (4×    0x40 rail
                                                        MG996R + 3×   history;
                                                        MG90S)        dedicated
                                                                      stall-cut
                                                                      logic
                                                                      recommended

  Pi output        5V          DROK 12A     F6 10A      Pi 5 + AI     INA260 0x44
                               buck                     HAT+ + SSD +  
                                                        display +     
                                                        audio + fan   

  Logic            3.3V        Pi onboard   ---         All I²C VCC + \<0.5A, no
                               reg                      6 encoder VCC monitor
                                                                      needed
  ---------------------------------------------------------------------------------

**NOTE:** CONVERTER MAP --- the DROK 12A LCD-display buck feeds the Pi
\@5.1V; the DZS 12A buck feeds the arm 6V rail; the FEICHAO 8A UBEC
feeds the 5V servo/steering rail. Earlier drafts of this document
repeatedly had DROK and DZS swapped --- this is the corrected,
owner-confirmed (2026-07-19) mapping and overrides any contrary text.

6.5 Acceptance Criteria

-   Pi rail at the Pi5 Face junction: 5.0--5.1V no-load, not below 4.85V
    at peak combined load.

-   FQP27P06 FET: warm, not hot, under sustained \~15A (with copper
    heatsink and isolated tab).

-   No nuisance fuse trips during worst-case validated transient loads.

-   Parallel packs within 0.05 V/cell before joining.

6.6 Switch 2 --- Pi-cutoff (built 2026-07-30)

A second switch in the DROK input line, separate from the main
KCD4/E-stop. Purpose: \`shutdown -h now\` halts the OS but leaves the
Pi\'s regulator --- and therefore the entire 3.3V/I²C bus --- energized
as long as 12V input power is present. Switch 2 fully de-powers the Pi
and 3.3V bus after a software shutdown.

6.7 DZS Buck Failure --- Root Cause & Fix (resolved)

An earlier live adjustment of a buck converter\'s trim pot (under load)
shorted the DZS buck internally, back-fed the bus, and destroyed the
P-FET, repeatedly blowing F3. Root cause: never adjust a converter pot
while it feeds a live load. Standing rule since: pre-set every buck pot
OFF-LOAD on the bench first, then wire it in. Fix: FET, TVS, and buck
replaced; 220nF gate-source soft-start cap added to Q1 to limit turn-on
inrush (§5.6, Sheet 8). Retested OK 2026-06-29.

6.8 Charge-in-Place Subsystem

Goal: recharge both packs without unbolting them. The charge connector
taps the common battery node ahead of the KCD4 master switch, so
switching the rover off isolates all rover loads while the cells remain
reachable for charging. Because the two packs share only their outer
terminals, both balance ports are brought out and paralleled into one 3S
balance breakout (paraboard) --- the charger sees a single 3S, \~16 Ah
pack.

  -----------------------------------------------------------------------
  **Item**                **Detail**              **Status**
  ----------------------- ----------------------- -----------------------
  Bulkhead connector      Shrouded EC5 pair,      INSTALLED (2026-07-30)
                          recessed, through the   
                          chassis wall            

  Balance extension       JST-XH 4-pin, routed to INSTALLED (2026-07-30)
                          the same access point   

  Inline charge fuse      \~15A ATC, sized to     to verify installed
                          charger output, in the  
                          charge+ line            

  Paraboard               2×3S parallel-charge    per BOM
                          board, combines both    
                          packs\' balance taps    

  External charger        iMAX B6 80W, \~4A       ON HAND
                          (\~0.25C of the 16Ah    
                          pair) balance charge    
  -----------------------------------------------------------------------

During charging, the iMAX is primary (per-cell monitor + balance + 4.2V
cutoff); the per-pack BMS rides along as backstop. KCD4 must be OFF
during charge --- charge access still reaches the cells with the rover
fully isolated.

7\. Compute System Design

7.1 Core Compute

Raspberry Pi 5 (8GB) + Hailo AI HAT+ (26 TOPS, PCIe FFC) in the front
compute bay, with a USB SSD, DSI Touch Display 2, and USB audio. AI
stack: YOLOv8 (Hailo), faster-whisper STT, Llama 3.2 3B, Piper TTS,
openwakeword --- all local/offline inference. Model training happens
off-board on a PC; the Pi does inference only.

7.2 GPIO Breakout --- Pimoroni Nano HAT Hacker

Replaced the original ZDE-type GPIO expansion board (2026-07-24) ---
smaller footprint, 4-corner mounting (the original had only 2, both at
one end), and every pin labeled with both BCM number and descriptive
function (I2C/UART/SPI/PWM/I2S) directly on the silkscreen. Confirmed:
I²C group reads \"5V · 5V · DA · CL\" --- DA = SDA = physical pin 3, CL
= SCL = physical pin 5. It is a straight 1:1 passthrough with no active
circuitry --- verification is done by reading the board\'s own
silkscreen rather than inferring from documentation. Caution: a second
\"CL\" label appears elsewhere under the SPI group (a different pin, SPI
clock) --- read the category header above a label, not just the label.

7.3 Camera / Vision Architecture

Two cameras, fixed roles, neither doing audio:

-   FRONT --- Arducam IMX708 Module 3 Wide (CSI): mounted on the front
    face, just below the display/arm-stow line, slight down-tilt. Short
    CSI FFC directly to the Pi CAM0 port. Runs ORB-SLAM3 (forward visual
    odometry/mapping) and forward YOLOv8 object detection.

-   REAR --- OV9782 (USB, UVC): mounted on the rear of the body.
    Plug-and-play, no FFC. YOLO/monitoring + descent view.

Front-stack thermal note: the Pi5 Face stack runs hot under simultaneous
SLAM + YOLO and is now capped by the arm above it rather than venting to
open air --- the active cooler must exhaust to the front/sides.

7.4 Storage

SanDisk Extreme PRO Portable SSD 500GB via USB 3.0 (strain-relieved with
a short extension + mount clip) as the primary boot drive --- OS, AI
models, and the local chat-memory DB. A high-endurance A2 microSD is
kept as a recovery/initial-flash fallback, not primary. USB-boot order
(Pi 5 booting from the SSD rather than the microSD) is a listed pending
task --- no later entry confirms it done; verify before relying on it.

7.5 Pi 5 Replacement --- Incident Summary (closed)

The original Pi 5 developed a hardware fault on its I²C-1 controller
(physical pins 3/5): every device on the bus went silent, and the fault
persisted even with nothing wired to the header at all (ruling out any
device, wiring, hub, or ribbon cause) and even under a deliberate
SDA/SCL-to-GND short test that a healthy controller should have reacted
to. Root cause, identified afterward: an earlier session had 3V3/GND
wired onto the SDA/SCL lines of the I²C/power bus node board (§5.6) ---
the Pi\'s open-drain I²C driver was fighting a hard 3V3 source instead
of a resistor under live power, which is consistent with damaging the
GPIO pin-driver. A same-spec replacement Pi 5 was ordered and installed
(2026-07-24, old SSD carried over intact); the new board\'s I²C-1 tested
clean (zero dmesg errors) on a bare-bus test, and the full 9-device
roll-call was subsequently reconfirmed working end-to-end, closing the
incident.

Standing rule adopted from this incident: before first power-up of any
home-built bus/breakout board, meter-verify each of its rails against
the known Pi pin it should trace to --- do not assume a board\'s
silkscreen or hole order matches the intended signal, even on a board
you built yourself.

8\. Sensor System Design

8.1 Sonar

3× HC-SR04, front(center)/left/right. There is no rear sonar --- the
only rear-facing device on the rover is the rear USB camera (§7.3). This
corrects a naming error present throughout earlier drafts, which
repeatedly labeled the third sonar \"rear\"; the GPIO assignments were
never wrong, only the position name.

  -----------------------------------------------------------------------
  **Position**            **TRIG**                **ECHO (via 1k/2k
                                                  divider)**
  ----------------------- ----------------------- -----------------------
  Front (center)          GP5                     GP26

  Left                    GP13                    GP14

  Right                   GP4                     GP21
  -----------------------------------------------------------------------

Wire color key (physical harness, distinct from schematic
role-coloring): BLUE = GND, PURPLE = ECHO, GRAY = TRIG, WHITE = VCC.
Each sonar uses a two-part plug connector (not direct solder) --- verify
plug orientation against this key before mating. Wiring is complete on
the base side (2026-07-29); the sonar base-to-top harness join is one of
the four remaining connection points (§0.2).

8.2 IMU --- BNO085

9-DoF, I²C 0x4A, replaces an earlier MPU-6050 plan. On-chip SH-2 sensor
fusion gives drift-free heading without a magnetometer (useful given six
nearby motors). VIN = 3.3V, P0/P1 floating selects I²C mode.

  -----------------------------------------------------------------------
  **Pin**           **Dir**           **Connects to**   **Note**
  ----------------- ----------------- ----------------- -----------------
  VIN               IN                3.3V              board supply

  GND               IN                logic ground bus  

  SDA / SCL         I/O               I²C bus (GP2/GP3) shared bus

  AD0               IN                GND               sets address 0x4A

  INT               OUT               Raspberry Pi GP15 required for SH-2
                                                        report timing.
                                                        Still unused in
                                                        software as of
                                                        2026-08-08 ---
                                                        `sensors.py`
                                                        polls over I²C
                                                        alone; its own
                                                        code comment
                                                        calls INT
                                                        optional, which
                                                        contradicts this
                                                        row and hasn't
                                                        been reconciled.

  RST               IN                MCP23017 (0x27)   software-reset
                                      port B bit 4       capable ---
                                      (confirmed         wired up in
                                      2026-08-08)        software
                                                        2026-08-08
                                                        (`sensors.py::
                                                        IMU`, via
                                                        `adafruit_mcp230xx`);
                                                        previously a
                                                        silent no-op even
                                                        though physically
                                                        wired. Verified
                                                        live: real
                                                        `hard_reset()`
                                                        pulse, no
                                                        register conflict
                                                        with the encoders
                                                        on the same chip.

  P0 / P1           ---               unconnected       selects I²C mode
  -----------------------------------------------------------------------

8.3 Current Sensing

Three INA260 modules (§5.2): 0x40 servo/steering rail, 0x44 Pi rail,
0x45 motor rail --- all inline (series), not parallel taps. 0x40
originally held an INA219, replaced 2026-07-27 after an intermittent,
inconclusive voltage-sag fault on the servo rail (drop varied
0.23--1.07V under similar conditions across repeated tests); root cause
was traced to the INA219 module itself, not the UBEC, EPLZON board, or
wiring. All three power rails were confirmed healthy after the swap.

8.4 Battery Voltage Sensing --- ADS1115 A0

Battery voltage is read on ADS1115 channel A0 (I²C, address 0x48, shares
the existing bus --- no dedicated SPI wiring). This replaces the
original MCP3008 CH7 design (2026-08-01) after repeated SPI
wiring/pinout confusion on that channel made it an unreliable point of
failure; the MCP3008 itself was not confirmed dead, and is retained as a
bench spare. An earlier build error had also had the old CH7 line wired
directly to the +12V rail with no divider at all --- an over-voltage
exposure that the MCP3008\'s internal clamp diodes were absorbing at the
time (confirmed via a near-full-scale raw reading, 1016/1023). Root
cause: the EPLZON\'s six built-in divider resistors are all dedicated to
the three sonar ECHO lines; this channel was never given its own divider
in the original board design.

Fix (2026-07-27): a standalone 10kΩ / \~3.2kΩ divider (4.7kΩ ∥ 10kΩ
substituted for an unavailable 3.3kΩ) was added between the +12V rail
and CH7, with the divider midpoint --- not raw 12V --- landing on the
ADC pin. Result: \~2.76V at 11.4V (nominal) and \~3.06V at 12.6V (full
charge), both safely inside a 0--3.3V ADC input range (unchanged
requirement under ADS1115, whose ADDR pin is tied to GND for the 0x48
address and which runs from the same 3.3V rail). Divider resistors
installed and the EPLZON remounted (2026-07-27). Note: the EPLZON is a
perfboard (confirmed by photo), not a breadboard --- use the board\'s
own printed A--J/numbered grid to place components, not the \"column
19/28\" labels used in early design notes for this fix (those describe
the circuit topology correctly, not real hole positions).

8.5 Sensor Polling & Fault Behavior

  -----------------------------------------------------------------------
  **Sensor**              **Target poll**         **Timeout / fault
                                                  response**
  ----------------------- ----------------------- -----------------------
  BNO085 IMU              100 Hz                  read stale >1s
                                                  (`SENSOR_FAULT_GRACE_S`)
                                                  → `SafetyController.
                                                  emergency_stop()` (hard
                                                  brake) + `SENSOR_FAULT`
                                                  FSM state, not the
                                                  \"disable autonomy,
                                                  allow limited manual\"
                                                  this row previously
                                                  said (as-built
                                                  2026-08-08, `brain.py::
                                                  _check_health()`)

  INA current (×3)        10 Hz                   read fail → log, hold
                                                  last; sustained fail (>1s)
                                                  → same `SENSOR_FAULT`
                                                  escalation as IMU
                                                  above, corrected
                                                  2026-08-08 (this row
                                                  previously said
                                                  \"SAFE_MODE\", which
                                                  isn\'t what the code
                                                  does)

  Encoders (MCP23017)     continuous (IRQ/poll)   sustained fail (>1s) →
                                                  same `SENSOR_FAULT`
                                                  escalation, not just
                                                  \"stop affected drive\"
                                                  (corrected 2026-08-08)

  HC-SR04 sonar (×3)      10--20 Hz               echo timeout → treat as
                                                  \"no obstacle in
                                                  range\", flag noisy

  Battery (ADS1115 A0)    1 Hz                    read fail → defaults to
                                                  0V, which the battery
                                                  tier ladder (§13.2)
                                                  already treats as
                                                  \`shutdown\` on its own
                                                  --- deliberately
                                                  excluded from the
                                                  `SENSOR_FAULT` path
                                                  above as a redundant
                                                  route to the same
                                                  outcome
  -----------------------------------------------------------------------

**As-built correction (2026-08-08):** none of the three current-monitor
rows above actually trip on an overcurrent *value* --- `sensors.py`\'s
own long-standing comment confirms \"no numeric overcurrent trip
threshold exists anywhere in the documentation to hardcode an automatic
cutoff against.\" `is_healthy` for all three current/IMU/encoder
sensors is **read-recency only** (last successful I²C read <1s ago),
not a threshold on the reading\'s value. The Hazard Response Matrix
(§14.1) rows for servo-rail/motor-rail overcurrent and Pi undervoltage
describe intended, not yet implemented, behavior --- see that section\'s
own as-built note.

9\. Drive System Design

6× JGA25-370B 12V gearmotors, driven entirely over I²C by 2× Adafruit
FeatherWing #2927 boards --- 0x60 (LEFT: LF/LM/LR) and 0x61 (RIGHT:
RF/RM/RR), via the Adafruit MotorKit library. This is a complete
architecture change from an earlier discrete 3× TB6612FNG design: there
is no direction GPIO wiring, no STBY line, and no external PWM anywhere
in the current build --- speed, direction, and (via MotorKit)
proportional control are fully internal to each FeatherWing. The
formerly-used GP7 (STBY) line and the twelve direction-GPIO lines are
freed for other use.

9.1 Motor / Encoder Wiring (complete)

  -----------------------------------------------------------------------
  **Motor**         **Power (2-wire)  **Encoder         **Note**
                    →**               (4-wire) →**      
  ----------------- ----------------- ----------------- -----------------
  LF                FeatherWing 0x60, MCP23017          LEFT board, port
                    M1                GPA0/GPA1         1

  LM                FeatherWing 0x60, MCP23017          LEFT board, port
                    M2                GPA2/GPA3         2

  LR                FeatherWing 0x60, MCP23017          LEFT board, port
                    M3                GPB0/GPB1         3 (M4 spare)

  RF                FeatherWing 0x61, MCP23017          RIGHT board, port
                    M1                GPA4/GPA5         1

  RM                FeatherWing 0x61, MCP23017          RIGHT board, port
                    M2                GPA6/GPA7         2

  RR                FeatherWing 0x61, MCP23017          RIGHT board, port
                    M3                GPB2/GPB3         3 (M4 spare)
  -----------------------------------------------------------------------

6-wire JGA25-370B crimp reference by color --- CORRECTED 2026-08-02,
superseding the table above: Red = motor+, White = motor− (to
FeatherWing M-terminals); Blue = encoder VCC → 3.3V distribution board;
Black = encoder GND; Yellow/Green = encoder Phase A/B → MCP23017. This
correction is backed by two independent sources: a Xuulan JGA25-370
manufacturer manual (24V/35RPM variant, same body/encoder family) and a
second independent listing, both agreeing against the original color
assignment below. The original table\'s Black=motor− / Green=encoder GND
assignment is confirmed WRONG. Wire color can still vary by
manufacturing batch in general --- meter each motor\'s actual crimp
before trusting any color chart, including this corrected one. PIN
CONVENTION (owner-specified, 2026-08-02): within each motor\'s Phase A/B
pin pair on the MCP23017, Yellow → the even-numbered pin, Green → the
odd-numbered pin (e.g. LF: Yellow→GPA0, Green→GPA1). Applied
consistently across all 6 motors per the table above. Which physical
phase (A vs. B) each corresponds to is not specified by either
manufacturer source --- doesn\'t affect basic operation, only matters if
direction-sensing logic depends on knowing which phase leads.

**OPEN INCIDENT (2026-08-02, unresolved): field wiring on at least one
already-crimped motor was reported as Red+Black landed in the
FeatherWing motor terminals --- i.e. Black (encoder GND per the
correction above) may be sitting on a motor power terminal instead of
White. A later message reported Blue+Black on the 3.3V rail instead,
which conflicts with the first report (Black cannot be in two places).
This has NOT been physically re-verified as of this writing. 12V power
was reportedly applied at least once while in this uncertain state.
Before any further power-up: (1) physically confirm, per motor, which
wire actually sits in each FeatherWing terminal and each 3.3V rail
position; (2) if Black and White read as electrically common
(continuity) at the motor\'s own PCB, the miswiring is likely harmless
since both would land on the same net; if they read isolated, treat the
encoder as a damage suspect and test Hall-sensor pulse output by
hand-spinning the shaft, unpowered, before trusting that motor\'s
encoder data. Do not close this incident until all 6 motors are
individually reverified against the corrected color reference above.
UPDATE 2026-08-02: first motor checked --- no apparent
Hall-sensor/encoder damage found. Harness (connector/crimp) rework is
still needed on the affected motor(s) to move the misplaced wire onto
the correct terminal per the corrected table. Remaining 5 motors not yet
individually re-checked as of this writing.**

Status: COMPLETE (landed 2026-07-30) but color-reference corrected
2026-08-02 --- re-verification of all 6 motors against the corrected
table is a new pending item (see Open Incident above), not yet done as
of this writing. Original claim was \"all 6 motors landed (power +
encoder + VCC, 36 wires total)\"; that physical completeness is not in
question, only whether each wire landed on the intended pin per the
corrected color reference.

9.2 Gear Ratio & Encoder Resolution --- starting values from the
manufacturer listing

The BOM specifies \"JGA25-370B 12V 620RPM.\" No official datasheet PDF
exists for this generic motor family, but the matching commercial
listing for the 12V/620RPM variant (JGA25-370-12V620-E) gives a 1:75
reduction ratio and a Hall-sensor resolution of 823.1 pulses per
revolution at the output shaft --- consistent with the encoder\'s native
11 PPR on the motor shaft × 75:1 gearing. Use these as the starting
constants in config.py, then confirm against the build: bench-measured
PPR can vary a few percent between \"620RPM\" listings from different
sellers, and §9.3 below already flags this as something to measure on
the build rather than assume.

  -----------------------------------------------------------------------
  **Constant**            **Starting value (from  **Note**
                          matching commercial     
                          listing)**              
  ----------------------- ----------------------- -----------------------
  Reduction ratio         1:75                    motor-shaft encoder ×
                                                  gearbox

  Encoder PPR (single     823.1 PPR               11 PPR (motor shaft) ×
  channel, output shaft)                          75

  Quadrature counts/rev   \~3,292 counts/rev      823.1 × 4 --- use this
  (if decoding both edges                         constant if the encoder
  of both channels)                               driver does full
                                                  quadrature decoding
                                                  rather than single-edge
                                                  counting

  No-load speed           620 RPM @ 12V           per BOM/listing; actual
                                                  under load will be
                                                  lower
  -----------------------------------------------------------------------

9.3 Drive Conventions (confirm on first movement test)

-   Encoder counts per wheel revolution --- starting value \~823 PPR at
    the output shaft per §9.2 (matching commercial listing); confirm on
    the actual build, since seller-to-seller variance on \"620RPM\"
    units is real.

-   Wheel direction/sign convention --- forward = positive count;
    confirm per-corner polarity during the dry test.

-   Acceptance: commanded direction matches observed rotation on all 6
    wheels; encoder counts increment in the commanded sign.

9.4 Drive Verification & Control Parameters (proposed --- confirm/tune
on build)

  -----------------------------------------------------------------------
  **Parameter**           **Value / method**      **Acceptance**
  ----------------------- ----------------------- -----------------------
  Left/right direction    per-corner polarity     commanded dir =
  map                     recorded in config.py   observed rotation, all
                          (MotorKit)              6

  Minimum controllable    lowest stable MotorKit  wheel turns smoothly,
  speed                   throttle (measure)      no stall

  E-stop command behavior hardware cut + software all motion ceases
                          stop                    immediately

  Fail-safe on controller motors disable (I²C     default-off, no runaway
  disconnect              command stop), arm      
                          holds                   
  -----------------------------------------------------------------------

10\. Steering System

6× GDW DS041MG steering servos (180°, coreless digital, metal gear, 12g,
25T spline) --- replaces an earlier MG90S plan (2026-07-03) for adequate
torque. PCA9685 0x42, CH0--5.

  -----------------------------------------------------------------------
  **Servo**               **Signal →**            **Power rail**
  ----------------------- ----------------------- -----------------------
  LF steer                PCA9685 0x42, CH0       5V servo rail

  RF steer                PCA9685 0x42, CH1       5V servo rail

  LM steer                PCA9685 0x42, CH2       5V servo rail

  RM steer                PCA9685 0x42, CH3       5V servo rail

  LR steer                PCA9685 0x42, CH4       5V servo rail

  RR steer                PCA9685 0x42, CH5       5V servo rail
  -----------------------------------------------------------------------

Center = 1500 µs (wheels straight); 500--2500 µs = full 180°,
software-limited per corner to wheel-well clearance. This matches the
manufacturer\'s own default signal spec for the DS041MG (500--2500µs =
180°, 1000--2000µs = the narrower 90° mode some units ship configured
for) --- confirm which mode a given unit is in before setting per-corner
limits, since some DS041MG stock ships in the 900--2100µs/120° mode
instead. Power (V+ and GND) runs directly from the 5V FEICHAO rail to
each servo; only the signal wire goes to the PCA9685 channel pin, plus a
thin reference-ground tie so the PWM signal shares a ground potential
with the servo. Status: COMPLETE (all 6 landed, milestone 2026-07-30).

Independent per-wheel steering enables point-turn (rotate in place),
crab (all wheels parallel, translate sideways), and coordinated
Ackermann turns. Pending in software: steering kinematics, per-corner
angle limits from wheel-well clearance, and crab/spin coordination math.

**NOTE:** Add a V+ decoupling capacitor to the PCA9685 0x42 board at its
unpopulated \"C2\" pad (Adafruit boards ship without one --- pad only).
Adafruit\'s own sizing guidance is \~100µF per servo driven; with 6
steering servos potentially moving together, install a \~1000µF ≥16V
low-ESR electrolytic, positive lead to the pad marked \"+\". On hand:
1000µF/16V electrolytics (15 pcs) --- one is exactly the target size. Do
this before landing the replacement board (§0.3).

11\. Robotic Arm Design

11.1 Architecture --- final, as-built

6-DOF, 7 servos, sourced from MakerWorld 1134925 (standalone 6-axis arm,
adapted onto WildWilly\'s front-deck turret). This is the corrected
final map after several intermediate revisions (an elbow-removed 2-DOF
variant, a 5-servo variant) --- the 7-servo/6-DOF configuration below is
owner-confirmed against the physical hardware and authoritative.

  --------------------------------------------------------------------------
  **Joint**      **Motion**     **Servo**      **PCA9685 0x43 **Rail**
                                               channel**      
  -------------- -------------- -------------- -------------- --------------
  J0 Base        Yaw ---        MG996R         CH0            6V (DZS)
                 left-right,                                  
                 whole arm                                    

  J1a Shoulder A Pitch ---      MG996R         CH1            6V (DZS)
                 up-down                                      
                 (paired with                                 
                 J1b)                                         

  J1b Shoulder B Pitch ---      MG996R         CH2            6V (DZS)
                 up-down                                      
                 (paired with                                 
                 J1a, same                                    
                 axis)                                        

  J2 Elbow       Pitch ---      MG996R         CH3            6V (DZS)
                 up-down                                      

  J3 Wrist       Yaw --- hand   MG90S          CH4            6V (DZS)
  rotate         left-right                                   

  J4 Wrist pitch Bend ---       MG90S          CH5            6V (DZS)
                 up-down                                      

  J5 Gripper     Open/close jaw MG90S          CH6            6V (DZS)
  --------------------------------------------------------------------------

All 7 servos share the 6V/DZS rail --- this is the final decision
(2026-07-28), superseding an earlier split-rail plan (MG996R@6V /
MG90S@5V) that was tried the same day and reversed. Reason: the 5V rail
(6× DS041MG steering + 3× MG90S + 3× sonar) worst-cased to \~11.4A
against the FEICHAO UBEC\'s 8A rating; moving the three MG90S to 6V
drops worst-case 5V load to \~9A (steering only, still near the rail
limit --- monitor) and removes arm-servo switching noise from the sonar
power rail. MG90S is rated 4.8--6.0V, so 6V is in-spec at the ceiling,
not overdriving.

Shoulder pair: J1a (CH10) is physically the RIGHT-side servo, J1b (CH11)
is LEFT-side; both drive the same pitch axis and must be commanded as a
coordinated/mirrored pair in software (one likely needs an inverted
angle command relative to the other), not independently.

11.2 Power Routing

Each servo\'s V+ and GND leads run directly to the 6V rail (not through
the PCA9685 V+ pin); only the signal wire threads through the PCA9685
channel pin, with a thin reference-ground tie to the star so the PWM
signal shares ground with the servo. This is the physically-built method
--- see §0.3 for a late design note on a simpler alternative that was
not retroactively applied.

**NOTE:** Add a V+ decoupling capacitor to the PCA9685 0x43 board at its
unpopulated \"C2\" pad, same as §10 for the steering board. With 7 arm
servos (4× MG996R at meaningfully higher stall current than the
steering/wrist servos) potentially moving together, size generously:
\~1500--2200µF ≥16V low-ESR. Preferred part, arriving 2026-08-01:
Rubycon 2200µF 16V 12.5×20mm low-ESR (0.041Ω) radial electrolytic --- a
single can lands right at the top of the target range, so the earlier
\"two 1000µF caps, one external\" workaround (§0.3/§18.4) is no longer
needed once these arrive; check the C2 pad\'s lead spacing before
soldering, as this is a larger can than the on-hand 1000µF units. If
landing the board before 08-01, the interim 1000µF (on C2) + 1000µF
(external, on the V+/GND screw terminal) combo works fine and can simply
be desoldered and replaced with the single Rubycon can later --- no
rework elsewhere needed.

11.3 Wiring Status

Mechanically COMPLETE (2026-07-24) --- base/shoulder, forearm, elbow,
wrist, gripper all assembled, signal wires routed and joint-labeled
(SHO/ELB/WRI tags). A bulkhead connector was added for the full 7-servo
harness so the arm can be detached without desoldering. Final landing to
PCA9685 0x43 CH0--6 is one of the four remaining top/base connection
points (§0.2), currently blocked on the PCA9685 replacement (§0.3).

11.4 Kinematics

IK approach: elbow-up (base yaw + shoulder + elbow position the wrist),
with a 2-axis wrist (pitch + roll\... i.e. rotate) orienting the
gripper. Dual shoulder is driven as one mirrored joint (J1b = 2×1500µs −
J1a); watch the current sensor on the arm rail --- sustained current
with no commanded motion means the pair is fighting, and PWM should be
cut.

11.5 Servo Pulse-Width Starting Values (manufacturer defaults ---
bench-verify per unit)

No per-unit calibration exists yet in config.py/arm.py. These are
manufacturer-published nominal defaults to seed the calibration step in
§20.6 --- not a substitute for it. Cheap-clone MG996R units in
particular are known to fall short of the full nominal 180° sweep (one
documented case measured only \~130° of real mechanical travel before
the gears bound), so treat these as safe starting bounds to probe inward
from, not values to trust blind.

  -----------------------------------------------------------------------
  **Servo**         **Nominal pulse   **Center          **Note**
                    width @ 180°**    (0°/mid)**        
  ----------------- ----------------- ----------------- -----------------
  MG996R (J0, J1a,  500--2500µs       1500µs            Manufacturer spec
  J1b, J2)                                              sheet. Real
                                                        clones commonly
                                                        bind before the
                                                        full range ---
                                                        verify per-joint
                                                        end-stops on the
                                                        bench before
                                                        committing limits
                                                        to arm.py.

  MG90S (J3, J4,    \~500--2400µs     1500µs            No single
  J5)               (sources vary                       authoritative
                    400--2400 to                        datasheet across
                    500--2400)                          vendors; treat
                                                        500--2400 as the
                                                        conservative
                                                        starting bound.

  GDW DS041MG       500--2500µs (180° 1500µs            See §10 note ---
  (steering)        mode) or                            confirm which
                    900--2100µs (120°                   mode a given unit
                    mode, some stock)                   shipped in.
  -----------------------------------------------------------------------

11.6 Link Lengths --- measured (2026-07-26, supersedes all earlier
figures)

Physically measured off the assembled arm, pivot-to-pivot along the
centerline. This supersedes an old unverified L1=L2=150mm figure and the
\~345mm reach placeholder used earlier in this document.

  -----------------------------------------------------------------------
  **Segment**                         **Length**
  ----------------------------------- -----------------------------------
  Base height (mount surface →        4 cm (\~1.6 in)
  shoulder pivot J1)                  

  L1 --- upper arm (shoulder J1 →     21 cm (\~8.3 in)
  elbow J2)                           

  L2 --- forearm (elbow J2 → wrist    21.5 cm (\~8.5 in)
  J3/J4)                              

  L3 --- wrist-to-gripper-tip         14 cm (\~5.5 in)

  Max reach (fully extended,          60.5 cm calculated / 59 cm measured
  horizontal)                         actual (\~1.5cm difference
                                      consistent with real joint-pivot
                                      stackup)
  -----------------------------------------------------------------------

11.7 Wheelchair-Handoff Use Case

Willy is intended as a fetch-and-deliver helper for a wheelchair-using
family member. Target handoff height \~24--30 in (lap/armrest/tray zone
for a seated user).

-   Priority: predictable, boring reliability over cleverness ---
    fixed/known pickup zones and a known object set, not open-ended
    \"pick up anything, anywhere.\"

-   Handoff pose is a hardcoded fixed pose (§11.8) rather than a fresh
    IK solution computed on every delivery.

-   Safety: an instant, top-priority STOP (voice command overriding any
    in-progress motion, ideally plus a physical stop within reach) is a
    requirement given the proximity to a mobility-limited user.

-   Design tension to balance in software: reliability-first fixed poses
    vs. leveraging the AI stack\'s adaptability where it genuinely helps
    handle real-world variation (owner-stated principle, 2026-07-24) ---
    not yet resolved, to be worked out as the software architecture
    develops.

11.8 Handoff Pose --- FINAL (owner-specified, 2026-07-31)

Arm fully extended (elbow straight, J2 at its zero/straight position ---
not bent), shoulder (J1a/J1b) pitched at a 15° tilt.

  -----------------------------------------------------------------------
  **Joint**                           **Handoff pose**
  ----------------------------------- -----------------------------------
  J0 base yaw                         per delivery target --- not fixed
                                      by this pose

  J1a / J1b shoulder                  15° tilt (mirrored pair, per §11.4
                                      J1b = 2×1500µs − J1a convention
                                      once zeroed)

  J2 elbow                            straight / fully extended (0°
                                      relative bend)

  J3 wrist rotate                     not yet specified --- hold neutral
                                      until decided

  J4 wrist pitch                      not yet specified --- hold neutral
                                      until decided

  J5 gripper                          open, until grasp
  -----------------------------------------------------------------------

**NOTE:** This is a geometric pose, not yet servo pulse-width values ---
translating it into arm.py requires the same joint-zero calibration step
already called out in §20.6 (the shoulder\'s 0°/tilt reference and the
elbow\'s \"straight\" pulse width are per-unit and not yet bench-set).
Once §20.6 is run, record the resulting µs values for J1a/J1b and J2
here and in arm.py\'s handoff-pose constant. Fully extended at only a
15° shoulder tilt puts the gripper close to the arm\'s maximum reach
(§11.6: 60.5cm calculated / 59cm measured) at a shallow angle --- worth
a bench dry-run against the target 24--30in handoff zone once J0/wrist
values are picked, since a shallow tilt on a nearly-fully-extended arm
is a small angle change away from either overshooting or undershooting
that zone.

12\. Communications Architecture

All processing is local/offline. I²C (GP2/GP3) links both PCA9685
boards, the MCP23017, BNO085, and the three INA260 current sensors, with
an LTC4311 active pull-up at the far end of the run, 100 kHz bus speed.
SPI (GP8--11) --- no longer used; the MCP3008 that occupied this bus has
been retired to spares (§8.4). Wi-Fi is used only for remote
administration (Cockpit, port 9090) and is not required for any onboard
function --- see §13, local-first design.

13\. Software Architecture

13.1 Codebase (as-built, 2026-08-08 --- supersedes the description
below this note, kept for history)

**This entire §13 predates the \"WildWilly Claude Fix\" architecture
pass (`docs/WildWilly_Claude_Fix_Implementation_Plan.md`, Phases 1--6,
landed 2026-08-07/08) and describes an earlier, largely aspirational
design (\"proposed --- adopt or adjust\"). The real, current
architecture is tracked in `docs/WildWilly_Subsystem_Status.md` (per-file
IMPLEMENTED/HARDWARE REQUIRED/SIMULATION ONLY/PARTIAL tags) and
`docs/WildWilly_Claude_Fix_Gap_Analysis.md` (plan-section-by-section
status, DONE:14/PARTIAL:2/MISSING:1(§17, correctly hardware-gated) as of
2026-08-08). This section is corrected below rather than left wrong.**

`/home/hhimmel/rover/`: `config.py`, `motors.py`, `sensors.py`,
`brain.py`, `display.py`, `arm.py`, `main.py`, plus (added by the Claude
fix pass) `safety.py` (the single authoritative motion gate --- see
§13.2), `odometry.py`, `world_model.py`, `mapping.py`, `navigation.py`,
`ai_provider.py` (unifies what were three separate AI call sites),
`storage.py` (configurable data-root paths), `hw_sim.py` (hardware
mocks for `WILLY_SIMULATE=1`), `logsetup.py`, plus the v2.2 additions
`voice.py`/`memory_store.py`/`vision.py`/`retrieval_task.py`/
`smart_home.py`/`email_client.py`/`diagnostics.py`/`privacy.py`.
`claude_client.py` and `cloud_ai.py` (two separate clients that had
independently been hitting the same Anthropic endpoint) were both
**fully retired 2026-08-08**, folded into `ai_provider.py`.

`motors.py` finished its MotorKit rewrite long ago --- it is not \"being
rewritten,\" it drives the two FeatherWings over I²C via the Adafruit
MotorKit library today, with no GPIO-PWM path remaining.

Real FSM states in `brain.py` (not \"INIT / IDLE / ACTIVE / SAFE_MODE\"
as this section previously said): `INIT`, `IDLE`, `ROAM`, `SLOW`,
`AVOID`, `WARN`, `STUCK`, `DOCK`, `RETRIEVE`, `NAVIGATE`, `TILT_FAULT`,
`SENSOR_FAULT`, `SAFE_MODE`, `SHUTDOWN`. There is no `ACTIVE` state.

`willy-rover.service`\'s watchdog is **not** 500ms as every other
mention in this document (§14, §14.2) claims --- the deployed unit file
(`systemctl cat willy-rover.service`, checked 2026-08-08) has **no
`WatchdogSec=` directive at all**. `brain.py` does call
`sd_notify('WATCHDOG=1')` every tick, but with no `WatchdogSec`
configured, systemd never enforces a timeout on it --- a hung (not
crashed) tick thread would not be caught by this mechanism today. What
*is* configured: `Restart=on-failure`, `RestartSec=5` --- covers a
process crash/exit, not a hang. See §14\'s as-built note.

Claude Code (native) is installed and authenticated on Willy directly
(user `hhimmel`), on Python 3.13.5 / Debian trixie. The rover code is
under local git (branch `main`, `.gitignore` protects `.env`). The
GitHub push issue this section used to describe is resolved --- pushes
to `origin/main` (`https://github.com/hdhimmel/willy-rover.git`) have
been working normally for some time; `main` was pushed current as of
2026-08-08 (`30efab7`). A personal access token was briefly exposed in
an external chat during setup and was revoked/replaced --- tokens
should only ever be pasted at the on-device `gh` prompt, never into
chat.

Test suite: 113 tests across 13 files, `WILLY_SIMULATE=1` (mostly)
hardware-independent. **One real portability gap found 2026-08-08** (an
external code audit, corroborated by direct inspection): `sensors.py`
imports `smbus2` unconditionally at module level, outside the
`SIMULATE_HARDWARE` guard that shields every other hardware import
(`RPi.GPIO`/`board`/`busio`/`adafruit_bno08x`/`adafruit_mcp230xx`). On
this Pi it\'s a non-issue (`smbus2` is installed), which is why all 113
tests pass here --- but on a machine without it (a laptop, CI), even
`WILLY_SIMULATE=1` would fail to import the app at all. Not yet fixed
as of this doc update; tracked as open work.

13.2 Software Control-Priority / Arbitration (as-built, 2026-08-08 ---
was \"proposed\"; now literally implemented in `safety.py`)

  -----------------------------------------------------------------------
  **Priority**      **Source**        **Can command**   **Override rule**
  ----------------- ----------------- ----------------- -----------------
  1                 E-stop / hardware all motion OFF    hard override,
                    safety                              latched

  2                 watchdog /        stop motion, park overrides
                    SAFE_MODE         arm               autonomy

  3                 low-battery       return-home /     overrides mission
                    manager           degrade           

  4                 autonomy          drive, steer, arm normal control

  5                 manual / admin    restricted        blocked in safety
                                      controls          states
  -----------------------------------------------------------------------

Battery-threshold transitions (one-way toward safer states until voltage
recovers above the next threshold + 0.2V hysteresis): 11.4V → warn;
10.8V → return-to-home; 10.5V → SAFE_MODE (motion stop); 10.2V →
controlled shutdown. These four values are exactly
`config.BAT_WARN_V`/`BAT_RTH_V`/`BAT_SAFE_V`/`BAT_SHUTDOWN_V` ---
verified live 2026-08-08 (`battery_volts=3.16V` correctly forced
`SHUTDOWN` with the base intentionally powered off, first live exercise
of this path).

**As-built corrections (2026-08-08):** row 1 (E-stop) is still not
software-observable at all --- no GPIO sense pin exists, so software
cannot detect or react to it; don\'t read this row as implemented. Row 2
conflates two different things: there is no configured systemd watchdog
timeout (§13.1) that could trigger a stop on its own; what actually
enforces \"stop motion\" is `safety.py::SafetyController.
emergency_stop()`, called from `brain.py` on a tilt fault, a sustained
IMU/encoder/current-sensor fault (`SENSOR_FAULT`, added 2026-08-07), or
battery shutdown/safe tier --- a real, tested, now live-verified
software safety layer, just not the OS-level watchdog this row implies.
\"Park arm\" is not implemented on any fault path --- the arm is
centered once at startup (`brain.py`\'s `start()`) and never
repositioned by `emergency_stop()` or any FSM fault state; only the
drive base is braked. The one thing genuinely new and correct in this
table: `approve_motion()` (`safety.py`) is the literal, single,
independently-unit-tested authoritative gate every motion source (the
reactive FSM, `RetrievalTask`, `MappingSession`, `Navigator`, and any
AI-proposed action) must pass through --- this row\'s \"normal control\"
language for priority 4 undersells how hard that boundary now is.

Platform constraints shaping software design: no depth sensor (3D
position from known-object-size + sonar, not a range camera); the front
SLAM camera is rolling-shutter and vibration-sensitive, so navigation
leans more on odometry (encoders + IMU + sonar) than vision; and the
Pi/Hailo do inference only --- all model training happens off-board on a
PC.

13.3 Capability Roadmap --- Post-Build Teaching

Capabilities arrive in layers, not all at once: (1) config/tuning ---
most out-of-the-box behavior (sonar avoidance, steering modes, arm IK,
the wakeword→whisper→Llama→Piper voice loop) is parameter tuning; (2)
custom object training --- teaching a new object is a PC-side fine-tune,
\~1--2 weeks per capability, compiled to the Hailo-8, since the rover
runs inference only; (3) behavior sequencing --- chaining perception +
navigation + arm into a task via a behavior tree/state machine; (4)
experiential learning (RL/imitation) --- research-grade, optional, needs
a simulator.

Worked example (\"find the dog toys, put them in the basket\"): train on
\~200--300 rover-camera images → detect & announce (Piper) → approach
(drive toward the detection, range estimated from known object size +
sonar, since there is no depth sensor) → grab (position the whole rover
to set range, since the arm reaches a fixed arc; pitch shoulder down;
close gripper) → deliver (navigate to the basket, position, release) →
loop until no toys detected or N failed attempts. A 5-step chain at 90%
per step is only \~59% end-to-end --- each stage should be built and
tuned to a demoable milestone independently, with per-stage retry/abort,
before chaining.

**As-built update (2026-08-08):** layer (3), behavior sequencing, has a
real milestone-1 foundation now: `world_model.py` (persistent
room/object/landmark/route/obstacle store), `mapping.py`
(`MappingSession`, voice-triggered, records vision detections into the
world model while active), and `navigation.py` (`Navigator`/`Mission`,
a `NAVIGATE` FSM state that resolves and drives a route through
`safety.py`\'s gate). All three are explicitly milestone-1, not SLAM ---
dead-reckoning odometry only (no slip correction, no IMU fusion), no
room-identification heuristic yet, and a straight-line fallback when no
route graph is known. `retrieval_task.py`\'s `LOCALIZE/APPROACH/GRASP/
VERIFY/DELIVER/AWAIT_CONFIRM` sub-FSM (pre-existing, v2.2) already
implements most of this worked example\'s per-stage-retry structure ---
its own remaining gaps are hardware calibration (no per-joint IK, no
tactile hand-off sensor), not missing architecture. See
`docs/WildWilly_Subsystem_Status.md` for the full per-module breakdown.

**As-built update (2026-08-09), plan closure:** every section of
`docs/WildWilly_Claude_Fix_Implementation_Plan.md` that is code-shaped
(not hardware-gated) is now done. `docs/WildWilly_Claude_Fix_Gap_Analysis.md`\'s
tally: **DONE 15, PARTIAL 1 (§12 YOLO/vision, deliberately --- bearing/
range kept as a separate `localize()` call rather than merged into
`detect()`, a documented minimal-diff choice, not a gap), MISSING 1
(§17 stair-climbing prep, correctly hardware-gated, matches M-006\'s
stretch-goal reclassification above).** A follow-on external code-audit
pass (8 more commits, `bb90e38`..`0deecc3`) closed the remaining P0/P1/P2
findings it raised: the `smbus2` import wasn\'t actually simulation-safe
(§19 had one real gap after all), storage-permission tests false-passed
under root, no regression test existed to catch a future direct
`DriveBase` bypass of `safety.py`, five background threads didn\'t
join on `stop()`, `config.validate()` now self-checks address/pin/
threshold sanity at startup (and found a real bug doing it --- see
`BAT_FULL_V` below), tick-duration telemetry was added, and
`RoverBrain.stop()` wasn\'t idempotent (a second call crashed mid-cleanup,
silently skipping `world_model.close()`/`motors.cleanup()`/every sensor\'s
`stop()` --- fixed). Two real, still-open items surfaced along the way,
not fixed because they\'re calibration values or need the owner\'s
input, not architecture: **`config.BAT_FULL_V=11.39V` sits below
`BAT_WARN_V=11.4V`** (so `battery_pct` --- display-only, never a safety
input --- could read 100% at a voltage the safety ladder already calls
\'warn\'; owner is measuring the real resting voltage to correct it), and
the tick-loop\'s `TICK_OVERRUN_THRESHOLD_S` needed live recalibration ---
see the §14 safety-architecture note below.

13.4 Persistence & Network Memory (WD My Cloud)

Principle: local-first, network-synced, never network-dependent --- a
dropped WiFi connection must never block the robot. Three memory types:
(1) local SSD = working memory (models, media, captures --- large,
occasional writes); (2) SQLite on the SSD = spatial/semantic memory
(object sightings, room map, AprilTag anchors --- live source of truth,
fast lookup); (3) operational logs/telemetry (high-volume, append-only).
Sync: Pi-side scheduled rsync to an SMB/NFS share on a WD My Cloud,
soft-mounted with a timeout so a missing NAS can never hang the Pi ---
models pulled at boot, captures pushed for off-board retraining.
LAN-only, SMB2/3 only (not SMB1), dedicated share user, credentials in a
0600 file (never in source). Optional: MQTT telemetry to
InfluxDB/Grafana for history/graphs, kept separate from the file-sync
path.

**As-built status (2026-08-08):** none of the WD My Cloud/rsync/SMB
sync described above has been built --- this section is still a
roadmap, not yet implemented. What *is* real: `storage.py::
resolve_root()` makes the four data roots
(`WILLY_DATA_ROOT`/`MAP_ROOT`/`MEMORY_ROOT`/`LOG_ROOT`) genuinely
configurable via environment variable instead of three independent
hardcoded `__file__`-relative paths (`memory_store.py`/`world_model.py`/
`logsetup.py` previously each computed their own). Confirmed via `df`/
`mount` this unit has no physical SSD/SD split yet --- all four roots
currently resolve to the same microSD card. `check_storage()` folds a
startup availability/permission check into `brain.py`\'s self-test gate
(a bad mount now blocks motion the same way a missing sensor already
does). `MemoryStore`/`WorldModel` also now survive a corrupted database
file (a real failure mode after an unclean power-loss shutdown) ---
caught, moved aside (never deleted), fresh store started, verified
2026-08-08 against a real garbage file on this Pi.

14\. Safety Architecture

Layered: 30A ATC main fuse, per-rail branch fuses, dual per-pack BMS,
FQP27P06 reverse-polarity FET, P6KE15A TVS, and a physical latching
E-stop (NC mushroom) cutting the 12V bus --- INSTALLED (2026-07-31);
functional test pending as part of first-power-on commissioning (§21.1).
Switch 2 provides a separate Pi-only cutoff (§6.6). **As-built correction
(2026-08-08): there is no 500ms software watchdog** --- the deployed
`willy-rover.service` unit has no `WatchdogSec=` directive (§13.1); the
real software safety layer is `safety.py::SafetyController.
emergency_stop()`, triggered by tilt/sustained-sensor-fault/battery
tiers, not a systemd watchdog timeout. See §14.1/§14.2\'s own
corrections below --- most of both tables describe intended, not
built, behavior.

14.1 Hazard Response Matrix

  -----------------------------------------------------------------------
  **Fault**         **Detection**     **Immediate       **Recovery**
                                      response**        
  ----------------- ----------------- ----------------- -----------------
  Pi undervoltage   INA260 0x44       stop drive + arm, manual reset
                                      enter SAFE_MODE   after power
                                                        stable

  IMU missing       I²C timeout       disable autonomy, restore sensor,
                    (0x4A)            allow limited     restart node
                                      manual            

  Encoder failure   no counts while   stop affected     diagnose hardware
                    commanded         drive mode        

  Servo-rail        INA260 0x40       freeze            cool-down +
  overcurrent       threshold         arm/steering      inspect
                                      outputs           

  Motor-rail        INA260 0x45       stop drive,       inspect for
  overcurrent       threshold         SAFE_MODE         stall/jam

  E-stop pressed    hardware          cut 12V motion    latch until
                    (latching NC)     bus               manual reset

  Battery critical  ADS1115 A0        controlled        recharge / swap
  (10.2V)                             shutdown          packs
  -----------------------------------------------------------------------

**As-built corrections (2026-08-08):** only the bottom two rows (E-stop,
battery critical) are real. \"Pi undervoltage\" and both overcurrent
rows are **not implemented** --- `CurrentMonitor.is_healthy`
(`sensors.py`) is read-recency-only, no threshold on the actual
current/voltage value exists anywhere in code (§8.5 has the full
detail); don\'t treat these three rows as built. \"IMU missing\"\'s
actual response is stronger than \"disable autonomy, allow limited
manual\" --- a sustained (>1s) IMU fault now forces a full
`emergency_stop()` and the `SENSOR_FAULT` FSM state (added
2026-08-07), same as encoder failure (also corrected here, not a
separate \"stop affected drive mode\" --- it\'s the same `SENSOR_FAULT`
path). There is no partial/\"limited manual\" mode anywhere in the
code.

14.2 Command-Loss & Fail-Safe Behavior

  -----------------------------------------------------------------------
  **Condition**           **Detection**           **Default state**
  ----------------------- ----------------------- -----------------------
  Software command-link   no valid command in     motors disable, enter
  timeout                 500ms (watchdog)        SAFE_MODE

  Controller / process    systemd watchdog        motors disable, arm
  crash                                           holds position

  Startup interlock       firmware INIT gate      no motion until
                                                  INIT→IDLE self-test
                                                  passes

  E-stop pressed          hardware latching NC    12V motion bus cut;
                                                  latch until manual
                                                  reset

  Low-voltage shutdown    ADS1115 A0 \< 10.2V     controlled shutdown,
                                                  park arm
  -----------------------------------------------------------------------

**As-built corrections (2026-08-08):** row 1 describes a remote
command-link that doesn\'t exist in the codebase at all (no teleop/RC
receive path anywhere) --- this is unbuilt, not just untested. Row 2\'s
\"systemd watchdog\" doesn\'t exist either (§13.1/§14); what actually
restarts a crashed process is `Restart=on-failure`/`RestartSec=5` ---
real, but reacts to the process exiting, not to a hang. \"Arm holds
position\" and \"park arm\" (rows 2 and 5) are both aspirational --- no
fault path in `brain.py` repositions the arm; only the drive base is
braked (same correction as §14.1). Startup interlock (row 3) and E-stop
(row 4, still not software-observable) and low-voltage shutdown\'s
detection/trigger (row 5, minus \"park arm\") are all real and, as of
2026-08-08, live-verified on hardware.

Default motor state is DISABLED --- motion requires an active, valid
command; loss of command always fails to stop, never to run.

**As-built update (2026-08-09), tick-loop timing under sustained fault:**
the first live run of the tick-duration telemetry added in the audit
pass above (`brain.py::_record_tick_duration()`) surfaced a real,
previously-unmeasured cost: while `SafetyController.emergency_stop()`
is asserting a brake every tick (battery shutdown, tilt fault, or
sensor fault --- i.e. exactly the states this section is about), each
tick does 6 real per-wheel I²C writes to the PCA9685 (`motors.py::
brake()`), measured live at 100--134ms per tick against `_tick()`\'s
50ms sleep target. Confirmed via `py-spy` against the live process, not
inferred. This is intentional, not a bug --- `safety.py`\'s own comment
notes the brake must be reasserted every tick to survive a
noise-flipped register, the same reasoning as this section\'s "default
motor state is DISABLED" principle above. Practical effect: control-loop
rate during a sustained fault is closer to 7--10Hz than the nominal 20Hz.
No functional consequence today since row 2\'s systemd watchdog was
already established above as not configured; `TICK_OVERRUN_THRESHOLD_S`
was raised 0.1s→0.15s to match the measured cost rather than the writes
being removed (owner\'s choice, given the noise-resilience tradeoff).
Separately, this same week\'s restart cycle re-confirmed live (not just
via the 2026-08-08 pass) that init, the safety FSM, and the battery-
shutdown path all behave correctly on fresh code --- motion itself
(forward/reverse/turn, `NAVIGATE`, retrieval, mapping) still has not
been commanded live; the drive base remains unpowered as of this
update.

15\. Wiring Standards

15.1 Connector Selection

  -----------------------------------------------------------------------
  **Connector**           **\~Cycles**            **Retention /
                                                  practice**
  ----------------------- ----------------------- -----------------------
  Dupont 2.54 (F)         10--30                  Low retention ---
                                                  strain-relieve; a
                                                  removable dab of hot
                                                  glue on the shell is
                                                  recommended for
                                                  critical signals.

  JST-PH (motors)         \~30                    Latching, good
                                                  retention. Verify
                                                  pin-1; do not force.

  JST-XH                  \~30                    Latching. Match pin
  (battery/balance)                               count (3S = 4-pin).

  Screw terminal (dist    effectively ∞           Best retention.
  boards)                                         Re-torque after the
                                                  first heat cycles.

  USB (rear camera/SSD)   \~1500                  Robust electrically;
                                                  strain-relieve at the
                                                  pod so the plug can\'t
                                                  wiggle.

  CSI / DSI FFC           10--20                  Fragile latch. Minimize
                                                  reseating; seat fully,
                                                  close the latch
                                                  squarely.
  -----------------------------------------------------------------------

15.2 Cable Labeling Convention

Every cable carries its harness-schedule ID (§16) and is labeled at both
ends within \~15mm of the connector. IDs are grouped by domain: P1--P7
power, R1--R4 rails, B1--B5 control/bus, M1--M6 motors, S1--S13 servos,
N1--N6 sensors, V1--V3 vision, G1 ground. Mark the source end with an
arrow toward the load.

15.3 Gauge & Ground Notes (as-built)

Power rails: 16 AWG (good for \~10--13A; covers the 12V motor rail\'s
\~6--9A and all lighter rails). Signal/logic (I²C, GPIO, sonar): 22--26
AWG. Servo V+/GND jumpers ≥22 AWG. Intentional exception: the 12V leg at
the INA screw terminal is 18 AWG solid (a properly-seated 18 AWG clamps
better than a splayed 16 AWG at that terminal size) --- acceptable for
its current, but solid-core fatigues under vibration at the clamp, so
keep it short, anchored, with a small strain-relief loop.

16\. Harness Schedule

Condensed final schedule by domain. All items below are built and landed
unless noted; the only remaining physical harness work is the four
connection points in §0.2.

16.1 Power (12V domain)

  -----------------------------------------------------------------------
  **ID**                  **From → To**           **Gauge**
  ----------------------- ----------------------- -----------------------
  P1                      2× 3S 8000mAh packs →   12--14 AWG
                          parallel                
                          (hard-paralleled,       
                          through per-pack BMS)   

  P2                      Battery+ → 30A ATC →    12 AWG
                          KCD4 → Q1 FET → +12V    
                          bus                     

  P3                      +12V bus → F2 → INA260  16 AWG
                          0x45 → 2× FeatherWing   
                          VIN                     

  P4                      +12V bus → F3 → DROK    16 AWG
                          buck IN (Pi rail)       

  P5                      +12V bus → F4 → FEICHAO 16 AWG
                          UBEC IN                 

  P6                      +12V bus → F5 → DZS     16 AWG
                          buck IN (arm rail)      

  P7                      Charge paraboard →      14 AWG
                          battery side of KCD4 (+ 
                          balance leads)          
  -----------------------------------------------------------------------

16.2 5V / 6V / 3V3 Rails

  -----------------------------------------------------------------------
  **ID**                  **From → To**           **Gauge**
  ----------------------- ----------------------- -----------------------
  R1                      DROK 5.1V → Pi header   20 AWG
                          pins 2 & 4 (GND 6 & 9)  

  R2                      FEICHAO 5V → INA260     16 AWG
                          0x40 → servo/steering   
                          distribution board      

  R3                      DZS 6V → arm            16 AWG
                          distribution board      

  R4                      Pi 3V3 (hub) → encoder  22 AWG
                          distribution + all I²C  
                          VCC                     
  -----------------------------------------------------------------------

16.3 Control / Bus

  -----------------------------------------------------------------------
  **ID**                  **From → To**           **Note**
  ----------------------- ----------------------- -----------------------
  B1                      Pi 40-pin → Nano HAT    the last of the 4
                          Hacker (1:1             remaining connections
                          passthrough)            (§0.2)

  B2                      I²C SDA/SCL (GP2/3) →   via §5.6 bus node board
                          bus node board → 9      
                          devices                 

  B3                      GP7 (SPICE1)            FREED --- was TB6612
                                                  STBY, FeatherWings have
                                                  no STBY pin

  B4                      12 motor-direction      FREED --- direction is
                          lines                   internal to each
                                                  FeatherWing

  B5                      6 motor PWM lines       FREED --- PWM is
                                                  internal to each
                                                  FeatherWing
  -----------------------------------------------------------------------

16.4 Motors, Servos, Sensors, Vision, Ground

  -----------------------------------------------------------------------
  **Group**                           **Summary**
  ----------------------------------- -----------------------------------
  Motors ×6                           PH2.0 6-pin → Dupont fan-out:
                                      Red/Black → FeatherWing, Blue/Green
                                      → encoder 3.3V dist, Yellow/White →
                                      MCP23017. COMPLETE.

  Steering ×6                         Signal → PCA9685 0x42 CH0--5;
                                      V+/GND direct to 5V rail. COMPLETE.

  Arm servos ×7                       Signal → PCA9685 0x43 CH0--6
                                      (bulkhead connector); V+/GND direct
                                      to 6V rail. Bulkhead built; final
                                      landing pending (§0.2/§0.3).

  Sonar ×3                            4-wire (VCC/TRIG/ECHO via
                                      divider/GND), two-part plugs. Base
                                      side COMPLETE; top join pending
                                      (§0.2).

  IMU                                 6-wire: 3V3/GND/SDA/SCL +
                                      INT→GP15 + RST→MCP23017. COMPLETE.

  Vision/display                      CSI FFC (front cam), USB (rear
                                      cam), DSI ribbon + separate 3-pin
                                      GPIO power (display). COMPLETE.

  Ground                              All converter −, board GND, sensor
                                      GND → single-point star. COMPLETE.
  -----------------------------------------------------------------------

17\. Interface Control Document

17.1 Physical Pin Assignment --- Pi 40-pin Header (final)

This replaces the GPIO-based motor-direction pinout used throughout
earlier drafts --- those 12 direction pins (GP17/18, 27/22, 23/24,
25/12, 16/20, 19/6) and GP7 (STBY) are now freed; motor control is
entirely I²C via the two FeatherWings (§9).

  -----------------------------------------------------------------------
  **Pin**                 **BCM/func**            **Connects to**
  ----------------------- ----------------------- -----------------------
  1                       3V3                     3V3 rail → all I²C
                                                  VCC + encoder VCC dist

  2 / 4                   5V (IN)                 Pi power in, from DROK
                                                  buck

  3                       GP2 SDA                 I²C bus (all 9 devices)

  5                       GP3 SCL                 I²C bus (all 9 devices)

  6 / 9                   GND                     Pi power return /
                                                  common

  7                       GP4                     Sonar RIGHT TRIG

  8                       GP14                    Sonar LEFT ECHO (÷)

  10                      GP15                    BNO085 INT --- labeled
                                                  \"RX\" (UART group) on
                                                  the Nano HAT Hacker
                                                  header, not \"15\" ---
                                                  GPIO15 is shared with
                                                  UART0 RXD, and this
                                                  board silkscreens by
                                                  function name, not BCM
                                                  number. Verify against
                                                  the RX pad in the UART
                                                  cluster, not a numbered
                                                  pin.

  3 / 5                   GP2/GP3 (SDA/SCL) ---   ADS1115 I²C 0x48, A0
                          shared bus, no          battery sense (§8.4)
                          dedicated pins          --- was MCP3008 SPI
                                                  (GP8--11), now
                                                  free/unused

  29                      GP5                     Sonar FRONT TRIG

  33                      GP13                    Sonar LEFT TRIG

  37                      GP26                    Sonar FRONT ECHO (÷)

  40                      GP21                    Sonar RIGHT ECHO (÷)

  27 / 28                 GP0/GP1 (ID_SD/ID_SC)   RESERVED --- AI HAT+
                                                  EEPROM, leave alone

  GP7, and the 12 former  ---                     FREED (motor control is
  motor-direction GPIOs                           I²C-only, §9)
  -----------------------------------------------------------------------

17.2 I²C Bus Fan-out & Pull-ups

**Update 2026-08-14: bus is now electrically isolated, as-built.** An ISO154x-series digital
isolator sits between the Pi's GP2/GP3 (SDA/SCL) and the bus node board fan-out described below ---
only the isolator's primary side is Pi-referenced; everything past it, including the bus node
board and all 10 devices in the table, is on the isolated secondary side. An AMS1117 LDO regulates
the isolated-side 3.3V rail independently of the Pi's own 3.3V supply, so a fault on any sensor/
device rail can no longer pull down or inject noise onto the Pi's own I²C pins. Installed to
target the 2026-08-06 noisy-bus/phantom-address fault (see [[project_rover_i2c_bus_fault]] in
session memory); by the time this was confirmed installed, that fault's actual root causes had
already been separately traced to two unrelated issues (arm PCA9685 VCC disconnect, BNO085
reset-timing bug) --- the isolator is now in place as a hardening measure regardless.

The Nano HAT Hacker exposes GP2/GP3 as one pin each, but 10 devices need
each signal (as of the ADS1115 addition, §8.4) --- a bus node board
(§5.6) fans SDA, SCL, 3V3, and GND out into four rails that every device
taps in parallel (address sorts the devices; tap order doesn\'t matter).
Required 4.7kΩ pull-ups from SDA→3V3 and SCL→3V3, placed once on the
rail. Caution: several breakouts carry their own onboard pull-ups --- 9
boards\' worth in parallel can drop the effective pull-up well below the
target \~1.5--3kΩ; measure and remove redundant onboard pull-ups if the
bus runs slow or unreliable, keeping one 4.7k pair plus the LTC4311. Bus
speed: 100kHz (i2c_arm_baudrate=100000) --- do not run 400kHz with this
many devices on a long rail.

Address-strap collision check before power: the two PCA9685 boards
(0x42/0x43) and the three INA260 boards (0x40/0x44/0x45) are identical
hardware apart from their address straps --- verify each strap before
connecting, or two devices collide silently and the bus fails.

17.3 Device Power / Signal / Ground Summary

  -------------------------------------------------------------------------------
  **Device**        **Power**         **Signal**        **Ground / note**
  ----------------- ----------------- ----------------- -------------------------
  Pi 5 + AI HAT+    5V from DROK,     ---               GND pins 6 & 9. AI HAT+
                    header pins 2 & 4                   via PCIe FFC, not via
                                                        USB-C.

  DROK 12A buck     12V in via F3     ---               5V out → Pi. USB-A port
                                                        is charge-only. Set
                                                        5.0--5.1V off-load first.

  FEICHAO UBEC 8A   12V in via F4     ---               5V out → servo/steering
                                                        rail → INA260 0x40.

  DZS 12A buck      12V in via F5     ---               6V out → arm distribution
                                                        → all 7 arm servos. Set
                                                        6.0V off-load first.

  6× JGA25 motors   12V switched via  driven by         GND → common trunk.
                    FeatherWing       FeatherWing       6-wire: 2 power + 4
                    outputs           internal driver   encoder.

  6× DS041MG        5V direct from    PCA9685 0x42      ref-GND to star.
  steering          distribution      CH0--5 (signal    
                    (V+/GND)          only)             

  7× arm servos     6V direct from    PCA9685 0x43      ref-GND to star.
                    distribution      CH0--6 (signal    Bulkhead-connectorized.
                    (V+/GND)          only)             

  3× HC-SR04 sonar  5V rail           TRIG = GPIO out;  GND. 4-pin two-part plug.
                                      ECHO = GPIO in    
                                      via divider       

  BNO085 IMU        3V3               I²C 0x4A;         GND. 0.1\" header + 6 F-F
                                      INT→GP15;         jumpers.
                                      RST→MCP23017      

  3× INA260         3V3 logic         I²C               VIN+/VIN− inline on each
                                      0x40/0x44/0x45    rail (series, not a tap).

  ADS1115 ADC       3V3               I²C 0x48 (shared  battery divider on A0
                                      bus)              (§8.4).

  6× encoders       3.3V via          A/B → MCP23017    Blue=VCC, Green=GND
                    distribution      0x27              (meter --- batch swap
                    board                               risk).

  2× FeatherWing    VM = 12V via F2;  I²C 0x60/0x61;    GND → common trunk. No
  #2927             logic 3.3V        MotorKit          STBY, no dir GPIO.
  -------------------------------------------------------------------------------

18\. Bill of Materials

Cleaned of the broken =COUNTIF() formula placeholders left over from the
spreadsheet export, and reconciled to the final address/architecture
facts throughout this document. Statuses: ON HAND · ORDERED · VERIFY ·
OPTIONAL · NOT USED · SPARE · BUILT.

18.1 Compute / Pi5 Face

  -------------------------------------------------------------------------
  **Component**     **Spec / role**     **Qty**           **Status**
  ----------------- ------------------- ----------------- -----------------
  Raspberry Pi 5    Main brain ---      1                 ON HAND
  (8GB)             REPLACED once                         
                    (§7.5); current                       
                    unit                                  
                    bench-confirmed                       
                    healthy                               

  Raspberry Pi AI   On-device           1                 ON HAND
  HAT+ (Hailo)      vision/voice NPU,                     
                    26 TOPS, PCIe                         

  5\" DSI touch     Face / UI 800×480   1                 ON HAND
  display                                                 

  Arducam IMX708    Front camera ---    1                 ON HAND
  (CSI)             SLAM + fwd YOLO                       

  OV9782 (USB)      Rear camera ---     1                 ON HAND
                    YOLO/monitoring +                     
                    descent                               

  ReSpeaker USB     Voice I/O ---       1                 ON HAND
  mic + speaker     confirmed connected                   

  Pimoroni Nano HAT GPIO breakout,      1                 ON HAND
  Hacker            replaces original                     
                    ZDE-type board                        

  Raspberry Pi      Pi 5 blower +       1                 ON HAND
  Active Cooler     heatsink                              

  5V case fan       Pi5 Face exhaust    1                 ON HAND
  30--40mm                                                

  SanDisk Extreme   Primary boot drive  1                 ON HAND
  PRO SSD 500GB     (USB-boot order                       
                    still pending)                        
  -------------------------------------------------------------------------

18.2 Drive & Steering

  -----------------------------------------------------------------------
  **Component**     **Spec / role**   **Qty**           **Status**
  ----------------- ----------------- ----------------- -----------------
  JGA25-370B        12V 620RPM, drive 6                 ON HAND ---
  gearmotor +       wheels                              landed
  encoder                                               

  Adafruit          Supersedes        2                 ON HAND ---
  FeatherWing #2927 discrete                            landed
  (I²C motor        TB6612FNG; 0x60                     
  driver)           LEFT / 0x61 RIGHT                   

  GDW DS041MG       180°, coreless    6                 ON HAND ---
  steering servo    digital ---                         landed
                    PCA9685 0x42                        
  -----------------------------------------------------------------------

18.3 Robotic Arm

  ---------------------------------------------------------------------------
  **Component**     **Spec / role**       **Qty**           **Status**
  ----------------- --------------------- ----------------- -----------------
  MG996R metal-gear J0 base, J1a/J1b      4                 ON HAND ---
  servo             shoulder, J2 elbow @                    mounted
                    6V                                      

  MG90S micro servo J3 wrist rotate, J4   3                 ON HAND ---
                    wrist pitch, J5                         mounted
                    gripper @ 6V                            

  Arm STL ---       Standalone 6-axis     print             CHOSEN / printed
  MakerWorld        arm, adapted to                         
  1134925           WildWilly turret                        
                    (PETG+PLA+)                             

  Bearings ---      Arm joint bearings    3                 VERIFY
  608 + 6203 ×2     per source model                        

  M8 60mm bolt +    Arm pivot hardware    2                 VERIFY
  anti-loosening                                            
  nut                                                       

  Arm servo         7-lead detachable     1                 BUILT
  bulkhead          harness connector                       
  connector                                                 

  Braided split     Arm servo harness     1                 ORDERED
  wire sleeve       bundling/protection                     
  ---------------------------------------------------------------------------

18.4 Servo Control & Power

  ---------------------------------------------------------------------------
  **Component**         **Spec / role**   **Qty**           **Status**
  --------------------- ----------------- ----------------- -----------------
  PCA9685 16-ch PWM     0x42 steering,    2                 REPLACEMENT
  driver                0x43 arm ---                        ORDERED
                        CURRENTLY FAULTY,                   
                        see §0.3                            

  DZS Elec 12A          12V→6.0V arm rail 1                 ON HAND ---
  adjustable buck       (all 7 arm                          installed
                        servos)                             

  DROK 12A LCD buck     12V→5.1V Pi rail  1                 ON HAND ---
  (CC/CV)                                                   installed

  FEICHAO 8A UBEC       12V→5V            1                 ON HAND ---
                        servo/steering                      installed
                        rail                                

  470µF 25V low-ESR cap Buck output surge 3                 ON HAND
                        buffer                              

  1000µF 16V            PCA9685 0x42      1 of 15           ON HAND
  electrolytic          (steering) V+                       
  (Chenxing/Throzzik,   decoupling ---                      
  10×16mm)              solder to                           
                        unpopulated                         
                        \"C2\" pad;                         
                        Adafruit ships                      
                        the board without                   
                        this cap                            
                        installed. Use 1                    
                        of 15 on hand.                      

  Rubycon 2200µF 16V    PCA9685 0x43      1 of 7            ORDERED ---
  12.5×20mm low-ESR     (arm) V+                            arriving
  (0.041Ω)              decoupling ---                      2026-08-01
  electrolytic, pack of single can on the                   
  7                     \"C2\" pad,                         
                        preferred over                      
                        the interim                         
                        two-cap                             
                        workaround.                         
                        Verify lead                         
                        spacing fits the                    
                        pad before                          
                        soldering.                          

  1000µF 16V            PCA9685 0x43      2 of 15           ON HAND ---
  electrolytic ×2       (arm) V+                            interim
  (\~2000µF combined)   decoupling,                         
  --- interim only      interim if                          
                        landing before                      
                        08-01: one cap on                   
                        the \"C2\" pad                      
                        (fits one can                       
                        only), second cap                   
                        wired externally                    
                        to the V+/GND                       
                        screw terminal                      
                        with short leads,                   
                        same net.                           
                        Superseded by the                   
                        single Rubycon                      
                        can once it                         
                        arrives.                            
  ---------------------------------------------------------------------------

18.5 Power System

  ------------------------------------------------------------------------------
  **Component**         **Spec / role**      **Qty**           **Status**
  --------------------- -------------------- ----------------- -----------------
  3S LiPo 8000mAh       Two packs,           2                 ON HAND ---
                        hard-paralleled                        installed
                        \~16Ah \@11.1V                         

  3S BMS 40--60A w/     One per pack, before 2                 per §6.2
  balance               parallel junction                      

  7-port                Single-point GND     1                 ON HAND ---
  distribution/ground   star                                   installed
  block                                                        

  FQP27P06 P-FET (Q1)   Reverse-polarity,    1                 BUILT
                        bench-confirmed from                   
                        photo                                  

  P6KE15A TVS diode     Transient            1                 ON HAND
  (D1)                  suppression                            

  30A ATC main fuse +   F1, off-board        1                 BUILT
  holder                                                       

  Branch fuses F2--F6   10A/5A/10A/10A/10A   5                 BUILT
                        per §6.4                               

  Physical E-stop       Cuts 12V bus ---     1                 INSTALLED
  (latching mushroom)   REQUIRED before                        (2026-07-31)
                        autonomy                               

  Switch 2 (Pi-cutoff)  DROK input line      1                 BUILT

  Shrouded EC5 charge   Charge-in-place      1                 INSTALLED
  bulkhead + JST-XH     access point                           
  balance ext.                                                 

  2×3S paraboard        Combines both        1                 per §6.8
                        packs\' balance taps                   
                        for charging                           

  iMAX B6 80W balance   External charger for 1                 ON HAND
  charger               charge-in-place                        
  ------------------------------------------------------------------------------

18.6 Sensing

  ------------------------------------------------------------------------
  **Component**     **Spec / role**    **Qty**           **Status**
  ----------------- ------------------ ----------------- -----------------
  BNO085 9-DoF IMU  Replaces earlier   1                 ON HAND ---
                    MPU-6050 plan ---                    landed
                    I²C 0x4A                             

  HC-SR04 sonar     Front/left/right   3                 ON HAND ---
                    --- no rear sonar                    landed

  ADS1115 ADC (I²C, CH7 battery sense, 1                 ON HAND ---
  0x48)             with divider fix                     landed
                    (§8.4)                               

  Sonar divider     ECHO dividers      6                 ON HAND
  resistors 3×1k +                                       
  3×2k                                                   

  CH7 battery       Added 2026-07-27   3                 ON HAND ---
  divider: 2×10kΩ + (§8.4)                               installed
  1×4.7kΩ                                                

  INA260 current    Servo 0x40, Pi     3                 ON HAND ---
  sensor            0x44, motor 0x45                     landed
                    --- 3rd unit                         
                    replaced a faulty                    
                    INA219                               

  MCP23017 I/O      Encoder GPIO ---   1                 ON HAND ---
  expander          bench address 0x27                   landed

  LTC4311 I²C       Bus reliability,   1                 ON HAND ---
  extender          far end of run                       landed

  4.7k I²C pull-ups On the bus node    2                 ON HAND ---
                    board                                installed
  ------------------------------------------------------------------------

18.7 Connectors, Consumables, Tools

  ------------------------------------------------------------------------
  **Component**     **Spec / role**    **Qty**           **Status**
  ----------------- ------------------ ----------------- -----------------
  JST-PH 6-pin      Motor connectors   6                 ON HAND ---
  pigtail                                                landed

  EC5 connectors +  Battery / power    1                 ON HAND
  parallel harness                                       

  M3 stainless      Servo mounts +     1 kit             ON HAND
  bolt/nut          joints + chassis                     
  assortment                                             

  PLA+ filament     Arm segments /     as needed         ON HAND
  1.75mm            brackets                             

  PETG filament     Chassis +          as needed         VERIFY
  1.75mm            load-bearing parts                   

  TPU 95A filament  Wheel treads       as needed         VERIFY

  IMAX B6 balance   LiPo               1                 ON HAND
  charger           charge/discharge                     

  4mm flange        Motor shaft        4                 ON HAND
  coupling          fittings                             
  ------------------------------------------------------------------------

19\. Assembly Procedures

Status: assembly is substantially complete. What follows is the
procedure as executed; §0.2 lists the only remaining physical
connections.

19.1 Sequence (as executed)

-   1\. Frame & suspension --- print widened two-level frame (PETG,
    mirrored parts confirmed), assemble rocker-bogie differential, mount
    6 motors, fit 6 wheels. DONE.

-   2\. Lower level / power --- mount power tray, seat both battery
    packs (voltage-matched, EC5-paralleled through per-pack BMS), land
    grounds on the distribution block, fit the EPLZON fuse board (FET,
    TVS, gate resistor, all 5 fuses). DONE.

-   3\. Upper level / control --- mount controller tray (Nano HAT
    Hacker, 2× FeatherWing, 2× PCA9685, MCP23017, BNO085, LTC4311,
    pull-ups) and sensor EPLZON (sonar dividers, battery-sense divider).
    MCP3008 retired to spares 2026-08-01, replaced by ADS1115 on the
    shared I²C bus (§8.4). DONE.

-   4\. Controller-tray harness (in situ, deepest boards first): board
    power/GND → I²C bus → FeatherWing control → signal returns → servo
    signals → 40-pin ribbon to the Pi LAST. DONE except the final ribbon
    connection (§0.2).

-   5\. Pi5 Face --- stack Pi 5 + Active Cooler + AI HAT+; connect front
    camera (CSI), rear camera (USB), display (DSI + 3-pin power); feed
    5V into the Pi5 Face junction. DONE except the final power/ribbon
    connections (§0.2).

-   6\. Arm --- mount J0 turret, fit all 7 servos, route harness,
    confirm stow pose clears the camera sightline through full motion.
    Mechanically DONE; electrical landing pending (§0.2/§0.3).

-   7\. Harness --- build every harness per §16, label both ends,
    strain-relieve. DONE.

-   8\. Final ribbon + power-up --- connect the 40-pin ribbon last, then
    run the commissioning gates (§21). PENDING --- blocked on §0.3.

19.2 Threadlocker & Adhesive Reference

  -----------------------------------------------------------------------
  **Product**             **Where**               **Caution**
  ----------------------- ----------------------- -----------------------
  Loctite 243 (blue,      Metal-to-metal: motor   NOT on plastic threads
  medium)                 mounts, brackets,       (can craze PLA/PETG).
                          bearing blocks          Full cure 24h.

  Nylon-insert lock nut / Fasteners into printed  Use instead of
  nylon-patch screw       plastic or heat-set     threadlocker on
                          inserts                 plastic.

  Heat-set brass inserts  Printed bosses needing  Install with iron
                          repeatable metal        \~200°C, square.
                          threads                 

  RTV silicone            Cable anchoring,        Semi-removable.
                          strain-relief           

  Hot glue                Removable connector     Not a structural bond.
                          retention (Dupont       
                          shells)                 

  FET insulator (nylon    Q1 FQP27P06 mounting    Stays dry --- no extra
  washer + silicone pad)                          thermal paste. Do NOT
                                                  threadlock the nylon
                                                  screw. Verify
                                                  tab↔heatsink OPEN after
                                                  assembly.
  -----------------------------------------------------------------------

19.3 Maintenance Disassembly Points

By design, the build separates into top (Pi, head, sensors, arm) and
base (chassis, motors, steering, power) at exactly four connectors ---
see §0.2. This was a deliberate choice given how often this build has
needed internal access (Pi replacement, EPLZON rework, INA swap, rail
redistribution): future maintenance is a 4-connector disconnect, not a
desoldering job.

20\. Calibration Procedures

20.1 Power (do first, before connecting the Pi)

**NOTE:** Pre-set every buck pot OFF-LOAD first --- bench the converter
alone, adjust to target, then wire it into the circuit. Never adjust a
converter pot while it feeds a live load (§6.7 --- this is exactly how
the DZS buck was destroyed previously).

-   DROK 12A buck → 5.0--5.1V measured at the output, Pi disconnected.
    Wire to the Pi5 Face junction only after confirming.

-   FEICHAO UBEC → confirm 5.0V servo rail under no load.

-   DZS 12A buck → confirm 6.0V arm rail under no load (all 7 arm servos
    share this rail).

20.2 I²C Landing Order (as-built, final address map)

Board-by-board bring-up order used successfully on the replacement Pi,
each verified before the next: MCP23017 (0x27) → INA260 servo (0x40) →
PCA9685 steering (0x42) → PCA9685 arm (0x43) → INA260 Pi (0x44) → INA260
motor (0x45) → LTC4311 (no address) → BNO085 (0x4A) → 2× FeatherWing
(0x60/0x61) → ADS1115 (0x48, battery sense --- replaced MCP3008
2026-08-01, §8.4).

Gotcha: the three INA260 boards are physically identical --- only the
address strap and which rail they sit inline on distinguishes them. If
two are swapped, roll-call still looks complete (all three addresses
present) but the current readings are crossed. Confirm each strap before
landing.

20.3 Current Sensors

Zero-offset each INA260 (0x40 servo, 0x44 Pi, 0x45 motor) at no load in
firmware; record the offsets in config.py.

20.4 Battery Sensing

Read ADS1115 A0 against a known battery voltage on a meter; trim the
divider scale factor in config.py so the reported voltage matches within
0.05V across 10.2--12.6V. Confirm the CH7 divider fix (§8.4) is in place
before trusting any reading.

20.5 Steering

Center all 6 DS041MG (PCA9685 0x42, CH0--5) to 1500µs and record the
neutral PWM per channel; set mechanical zero with wheels straight before
mounting horns --- centering after horns are on makes software-zero not
match mechanical-straight. Bench-test steering torque under load (C-8,
§21) --- DS041MG is rated \~3.1 kg-cm \@5V.

20.6 Arm / IK

Set arm.py joint zeros using the measured link lengths (§11.6: base 4cm,
L1 21cm, L2 21.5cm, L3 14cm) and the manufacturer-default pulse-width
starting values (§11.5) as calibration seeds. IK is elbow-up (base yaw +
shoulder + elbow position the wrist), 2-axis wrist orientation. Center
both shoulder servos, drive J1b as the mirror of J1a; watch the arm-rail
current sensor for sustained draw with no commanded motion (the pair
fighting) and cut PWM if seen.

20.7 IMU

Mount the BNO085 level; run the SH-2 calibration; confirm INT (GP15)
toggles on report-ready (still not done as of 2026-08-08 --- INT is
unused in software) and RST (MCP23017 port B bit 4) resets cleanly ---
this half done 2026-08-08: `sensors.py::IMU` now drives a real
`hard_reset()` pulse through it and it was verified live (§8.2).

21\. Validation and Test Plan

21.1 First-Power-On Commissioning Checklist

Single ordered runbook; work top to bottom, each gate must pass before
the next. Status reflects the last logged state --- several gates need
to be re-run now that the build is close to fully landed and the §0.3
PCA9685 fault has been isolated.

  -----------------------------------------------------------------------
  **Gate**                **Action / pass         **Status**
                          criteria**              
  ----------------------- ----------------------- -----------------------
  C-1                     Bench boards cleared    PASS
                          --- power & sensor      
                          EPLZON meter-checked    
                          (FET orientation,       
                          tab↔heatsink open, TVS  
                          band, sonar dividers,   
                          battery-sense divider   
                          rails)                  

  C-2                     All regulator rails set PASS (5.1V)
                          off-load then verified: 
                          DROK 5.0--5.1V, FEICHAO 
                          5V, DZS 6V              

  C-3                     Junction polarity ---   PASS (base-only staged
                          KCD4 on, Pi unplugged:  power-up, 2026-07-30,
                          5V on header pins 2/4,  all rails good)
                          GND on 6/9, not on any  
                          other pin               

  C-4                     I²C roll-call ---       PASS (2026-08-01, with
                          confirm all 9 devices + replacement PCA9685
                          All-Call, none shorted  boards) --- full clean
                                                  roll-call: 0x27, 0x40,
                                                  0x42, 0x43, 0x44, 0x45,
                                                  0x4A, 0x60, 0x61, +0x70

  C-5                     Staged Pi power-up ---  PENDING --- awaits
                          INA260 0x44 shows Pi    final ribbon connection
                          rail ≥4.85V under boot  (§0.2)
                          load, no brownout       

  C-6                     Post-boot I²C confirm   PENDING --- same
                          --- i2cdetect shows the blocker as C-5
                          same 9 addresses        

  C-7                     FET temp under          PENDING (needs full
                          sustained load --- Q1   load)
                          tab warm-not-hot at     
                          \~15A                   

  C-8                     Steering torque check   PENDING (needs full
                          --- DS041MG turns each  assembly)
                          loaded wheel at 5V      
  -----------------------------------------------------------------------

21.2 Subsystem Dry Tests

Motors: each direction, low duty, confirm encoder counts. Steering:
sweep each servo. Arm: move each joint through range at low speed, watch
for collisions with the compute stack. Sonar: confirm front/left/right
ranging (functional pulse-timing test still pending per §8.1). IMU:
confirm tilt/heading.

21.3 Stall & Fuse Tests

-   Arm fuse (F5, 10A): stall all 4 MG996R simultaneously, measure peak
    current, confirm the fuse holds. (Raised from an earlier 5A for
    stall margin; re-verify given the arm now runs all 7 servos, not the
    earlier 3, off this rail.)

-   Motor fuse (F2, 10A): stall all 6 motors, confirm the fuse holds.

-   Pi-rail fuse (F6, 10A): run AI inference + SSD write + display +
    audio together, confirm the fuse holds and the DROK buck stays in
    spec.

21.4 Thermal

The DZS and DROK bucks sit on their heatsinks in the lower level,
between the two LiPo packs, in a fairly enclosed bay. Two risks to check
once under sustained load: heat soaking into the adjacent LiPo cells,
and the buck heatsinks being thermally trapped with no vent path. Add a
small fan or an insulating break between the buck heatsinks and the
packs if the bay runs more than comfortably warm.

21.5 Mechanical / CG

Weigh each subsystem, replace the estimated CG values (§4.6 ---
currently PENDING). Balance-test CG arm-stowed vs. deployed; confirm the
widened body clears the wheels at full articulation.

21.6 Autonomy

End-to-end: wakeword → STT → reasoning → action; vision detection →
obstacle avoidance; battery-threshold behaviors (warn / RTH / SAFE_MODE
/ shutdown); E-stop cuts motors + arm.

21.7 Thermal Acceptance (proposed pass/fail gate --- confirm against
datasheets and measured ambient)

  -----------------------------------------------------------------------
  **Item**                **Condition**           **Pass limit**
  ----------------------- ----------------------- -----------------------
  Motor drivers           sustained driving       case warm, \< 70°C
  (FeatherWing)                                   

  DROK 12A buck (Pi,      peak                    within rating, \< 70°C,
  5.1V)                   compute+sensor+servo    no foldback
                          load                    

  DZS 12A buck (arm, 6V)  arm under load          \< 70°C

  FQP27P06 FET            sustained \~15A         warm-not-hot, within
                                                  SOA

  Battery (LiPo)          high-discharge run      \< 45°C surface

  Raspberry Pi 5          sustained AI inference  no thermal throttling

  Enclosed electronics    sustained operation     below component limits
  bay                                             with body airflow
  -----------------------------------------------------------------------

22\. Maintenance Procedures

22.1 Before Each Run

Verify both packs within 0.05V/cell; check E-stop latches and releases;
confirm no loose harness at the Pi connectors, especially the 4
maintenance-disassembly points (§0.2/§19.3).

22.2 Periodic

Re-torque arm and deck fasteners; inspect CSI/DSI/SSD strain relief;
check FET and converter temps after load; clean camera lenses; verify
wheel/bogie pivots are free.

22.3 Battery Care

Charge the two packs as a paralleled pair via the charge-in-place port
(§6.8) so they stay matched; cycle them together so they age matched;
never join a charged pack to a depleted one.

22.4 Software

Back up the SSD (OS + models + memory DB) periodically; keep config.py
offsets current after any sensor change; version willy-rover.service
config; push local git commits to GitHub once the token-scope issue
(§13.1) is resolved.

23\. Risk Register

  --------------------------------------------------------------------------
  **ID**            **Risk**             **Severity**      **Status /
                                                           mitigation**
  ----------------- -------------------- ----------------- -----------------
  R-01              Pi 5V rail brownout  MED               DROK 12A buck
                    under AI load                          installed and
                                                           confirmed at
                                                           5.1V; peak-load
                                                           verification
                                                           still pending
                                                           final landing.

  R-02              Widening the frame   LOW               Downgraded ---
                    reduces stair-climb                    stair climbing is
                    margin                                 now a stretch
                                                           goal (§2.1), not
                                                           gating.

  R-03              Arm/camera collision MED               Verify
                    through motion                         full-envelope
                    envelope                               clearance, not
                                                           just stow, once
                                                           the arm is
                                                           electrically
                                                           landed.

  R-04              Parallel-pack surge  HIGH              0.05V/cell rule;
                    if voltages                            per-pack BMS
                    unmatched                              added as a
                                                           backstop (§6.2).

  R-05              Simultaneous         MED               RESOLVED for the
                    motor/arm/steering                     arm: all 7 servos
                    stall trips fuses                      on one 12A-rated
                                                           DZS buck with CC
                                                           current limit, F5
                                                           10A ample. 5V
                                                           rail (steering +
                                                           sonar) is near
                                                           its 8A UBEC
                                                           rating ---
                                                           monitor via
                                                           INA260 0x40,
                                                           stagger
                                                           arm/steering
                                                           moves in
                                                           firmware.

  R-06              CG estimates wrong   MED               Open ---
                                                           mass-properties
                                                           closure (§4.6)
                                                           still pending
                                                           measurement.

  R-07              Pi5 Face over-temp   MED               Active cooler +
                    (Pi+AI HAT+                            Pi5 Face fan;
                    enclosed, capped by                    confirm exhaust
                    the arm above)                         path clears the
                                                           arm; thermal test
                                                           pending (§21.7).

  R-08              Motor control mode   RESOLVED          Fully I²C via 2×
                    undecided                              FeatherWing +
                                                           MotorKit --- no
                                                           external PWM/GPIO
                                                           wiring.

  R-09              DZS buck internal    RESOLVED          Root cause and
                    short from a live                      fix in §6.7 ---
                    pot adjustment                         pre-set every pot
                                                           off-load, 220nF
                                                           soft-start added,
                                                           retested OK.

  R-10              Pi 5 I²C-1 hardware  RESOLVED          Full incident and
                    fault (bus node                        fix in §7.5 ---
                    board power/data                       replacement Pi
                    swap)                                  installed, root
                                                           cause identified,
                                                           standing
                                                           meter-verify rule
                                                           adopted.

  R-11              INA219 servo-rail    RESOLVED          Swapped for a 3rd
                    intermittent fault                     INA260 (§8.3);
                                                           all rails
                                                           confirmed healthy
                                                           after.

  R-12              MCP3008 CH7          RESOLVED          Standalone
                    over-voltage                           divider added
                    exposure (no                           (§8.4); CH7
                    divider)                               verified safe.

  R-13              Both PCA9685 boards  RESOLVED          Replacement
                    hanging the I²C bus                    boards installed
                    (SDA stuck low)                        with V+
                                                           decoupling caps;
                                                           full 9-device
                                                           roll-call passed
                                                           clean 2026-08-01
                                                           (§0.3).
  --------------------------------------------------------------------------

24\. Open Items

Consolidated and de-duplicated from the rev 5.80 \"Open Items\" section,
the pending-task lists scattered through the later narrative entries,
and the BOM VERIFY rows. Superseded/completed items from earlier drafts
(e.g. the original 5-servo channel range, the discrete TB6612 driver
design, the ZDE GPIO board) have been removed --- see §25 if that build
history is needed.

24.1 Blocking further progress

-   Land the arm bulkhead to PCA9685 0x43 CH0--6 + 6V rail --- PCA9685
    replacement resolved (§0.3), this is now unblocked.

-   Connect the final 40-pin ribbon, Pi power feed, and sonar top join
    (§0.2) --- then run commissioning gates C-5 through C-8 (§21.1).

24.2 Safety-critical, not yet confirmed

-   E-stop functional test --- installed (2026-07-31); run the actual
    latch/cut/release test as part of first-power-on commissioning
    (§21.1), not just visual install confirmation.

-   Confirm the charge-port inline fuse is installed (bulkhead and
    balance lead are confirmed installed).

24.3 Engineering-review gates

-   Mass properties & stability closure (§4.6) --- weigh subsystems,
    measure real CG arm-stowed/deployed, derive tip-over/speed/payload
    limits.

-   Thermal acceptance testing (§21.7) under sustained combined load.

-   Confirm Pi 5 boot order is set to USB (SSD), not microSD.

24.4 Software

-   Rewrite motors.py against Adafruit MotorKit for the FeatherWings (in
    progress per §13.1).

-   Resolve the GitHub push token-scope issue (non-blocking, local
    commits safe).

-   Implement steering kinematics (per-corner limits, crab/point-turn
    coordination) in config.py/motors.py.

-   Decide wrist rotate (J3) and wrist pitch (J4) angles to complete the
    handoff pose (§11.8) --- base yaw, elbow, and shoulder tilt are now
    specified.

-   Decide gripper finger-grip coating (may require a closed-jaw
    calibration re-cal once chosen).

24.5 Consumables / BOM verify

-   PETG and TPU filament --- confirm on hand or order.

-   Arm bearings (608 + 6203×2) and M8 pivot hardware --- confirm on
    hand.

25\. Revision History

Condensed changelog. Rev 5.80\'s \~80 dated micro-entries are grouped
here by theme; the full line-by-line log is preserved in the rev 5.80
source file if the granular audit trail is ever needed.

  ----------------------------------------------------------------------------
  **Rev range**           **Dates**               **Summary**
  ----------------------- ----------------------- ----------------------------
  2.7 -- 3.9              2026-06-20 to 06-29     25-section baseline
                                                  established; formal
                                                  schematic set (7 sheets)
                                                  added; requirements
                                                  traceability, drive
                                                  verification,
                                                  command-loss/fail-safe,
                                                  thermal gate, and
                                                  mass-properties framework
                                                  closed into the doc
                                                  structure; fuse slot order
                                                  confirmed.

  4.0 -- 4.2              06-29 to 07-03          DZS buck destroyed by a live
                                                  pot adjustment, root-caused
                                                  and fixed with a soft-start
                                                  cap (R-09). Two-camera
                                                  architecture adopted (front
                                                  CSI SLAM+YOLO / rear USB
                                                  monitoring); compute moved
                                                  front-mounted (\"Pi5
                                                  Face\"), rear-pod concept
                                                  dropped. Steering servos
                                                  changed MG90S→GDW DS041MG.

  4.3 -- 4.14             07-03 to 07-08          First-power-on commissioning
                                                  checklist (C-1...C-8) added.
                                                  Arm architecture churned
                                                  through several
                                                  configurations (elbow
                                                  removed, then restored)
                                                  before landing on
                                                  6-DOF/7-servo. Harness
                                                  schedule populated. Power
                                                  distribution mapped to 5
                                                  rails / 5 boards.

  4.15 -- 4.27            07-08 to 07-10          BNO085 wiring finalized
                                                  (0.1\" header + jumpers).
                                                  Cable labeling and connector
                                                  mating-cycle references
                                                  added. As-built gauge/ground
                                                  notes captured. PCA9685 V+
                                                  screw terminals confirmed
                                                  unused (servo power
                                                  external) --- later
                                                  revisited and partially
                                                  reversed, see §0.3. I²C
                                                  physical fan-out and pull-up
                                                  design documented.

  4.92 -- 4.99            07-18 to 07-19          Per-pack BMS design added;
                                                  charge-in-place via iMAX B6
                                                  designed. Stair-climbing
                                                  reclassified to a stretch
                                                  goal. Claude Code installed
                                                  on Willy. Extensive,
                                                  repeated correction passes
                                                  on the DROK/DZS buck
                                                  assignment and INA/PCA9685
                                                  addressing after several
                                                  rounds of the doc
                                                  contradicting itself ---
                                                  this rev (6.0) is the final
                                                  resolution of that whole
                                                  saga.

  5.00 -- 5.13            07-19 to 07-20          Schematic images redrawn to
                                                  the FeatherWing
                                                  architecture. GPIO expansion
                                                  board replaced with the
                                                  Pimoroni Nano HAT Hacker.

  5.13 -- 5.14            07-20                   Pi 5 I²C-1 hardware fault
                                                  incident: full isolation
                                                  testing, root cause (bus
                                                  node board 3V3/GND swapped
                                                  onto SDA/SCL), replacement
                                                  Pi ordered and installed,
                                                  standing meter-verify rule
                                                  adopted. Incident closed
                                                  07-24 with a full 9-device
                                                  roll-call.

  5.15 -- 5.20            07-20 to 07-24          Both rocker-bogie
                                                  suspensions and full chassis
                                                  assembled. Arm mechanically
                                                  completed. Arm servo map
                                                  confirmed as-built (7
                                                  servos, 4×MG996R+3×MG90S)
                                                  --- resolved a long-standing
                                                  doc conflict.
                                                  Wheelchair-helper use case
                                                  and design priorities
                                                  documented.

  5.21                    07-24                   Authoritative servo channel
                                                  map published: steering
                                                  PCA9685 0x42 CH0-5, arm
                                                  PCA9685 0x43 CH9-15 ---
                                                  supersedes every earlier
                                                  0x40/0x41/CH11-14/CH6-8
                                                  reference in the document.

  5.22 -- 5.28            07-24                   MCP23017 address corrected
                                                  to bench-confirmed 0x27 (was
                                                  documented 0x20). Full
                                                  9-device I²C roll-call
                                                  achieved for the first time
                                                  on the replacement Pi,
                                                  closing the hardware-fault
                                                  incident arc.

  5.29 -- 5.33            07-26                   Arm link lengths physically
                                                  measured (base 4/L1 21/L2
                                                  21.5/L3 14cm, max reach
                                                  60.5cm) --- supersedes all
                                                  earlier reach figures.
                                                  FeatherWing #2 brought onto
                                                  the bus, completing all 9
                                                  devices simultaneously.

  5.34                    07-26                   Sensor interfaces (sonar
                                                  GPIO, battery-voltage SPI)
                                                  confirmed as-is --- no
                                                  migration to I²C
                                                  alternatives.

  5.35 -- 5.38            07-27                   Servo/INA219 rail voltage
                                                  sag investigated and
                                                  resolved by replacing the
                                                  INA219 with a 3rd INA260 at
                                                  0x40.

  5.39 -- 5.43            07-27                   MCP3008 CH7 found wired
                                                  directly to 12V with no
                                                  divider (over-voltage
                                                  exposure) --- root-caused to
                                                  a genuine gap in the
                                                  EPLZON\'s original design,
                                                  fixed with a standalone
                                                  10k/3.2k divider.

  5.44 -- 5.51            07-28                   Final arm servo voltage
                                                  decision: all 7 servos on
                                                  the 6V rail (moved off a
                                                  brief split-rail attempt the
                                                  same day) after a 5V-rail
                                                  load review showed
                                                  steering+arm+sonar exceeding
                                                  the UBEC rating. Sonar
                                                  naming corrected:
                                                  front/left/RIGHT, not
                                                  front/left/rear --- no rear
                                                  sonar exists.

  5.52 -- 5.65            07-28 to 07-29          6V rail rearranged for a 7th
                                                  connection point. Drive
                                                  motor and steering harnesses
                                                  built, labeled, and landed.
                                                  Sonar wiring completed on
                                                  the base side. Arm bulkhead
                                                  connector added for
                                                  serviceability.

  5.66 -- 5.79            07-29 to 07-30          All drive motors and
                                                  steering servos fully
                                                  landed. Design rationale for
                                                  keeping two PCA9685 boards
                                                  recorded (not strictly
                                                  required, kept for
                                                  isolation/practicality).
                                                  Shoulder servo physical-side
                                                  orientation confirmed
                                                  (J1a=RIGHT, J1b=LEFT).
                                                  Charging interface
                                                  installed. Switch 2
                                                  (Pi-cutoff) built, closing
                                                  the full wiring audit.

  5.80                    07-30                   PCA9685 §0.3 incident opened
                                                  (both boards found hanging
                                                  the I²C bus, isolated to the
                                                  boards themselves;
                                                  replacements ordered). Late
                                                  design note on simplifying
                                                  servo power routing recorded
                                                  for future reference.

  6.0                     2026-07-31              Full structural
                                                  reorganization: single
                                                  authoritative address/pin
                                                  table (§5.2) replacing a
                                                  dozen inconsistent
                                                  restatements; every \"DESIGN
                                                  ADDITION / INCIDENT /
                                                  MILESTONE\" entry folded
                                                  into its proper home
                                                  section; M-006 reclassified
                                                  to stretch in the
                                                  traceability table; broken
                                                  BOM spreadsheet formulas
                                                  removed; new §0 Current
                                                  Build Status added as the
                                                  fastest entry point into
                                                  where the build actually
                                                  stands; revision history
                                                  condensed from \~80 line
                                                  items to this table; §2.1
                                                  functional-requirements list
                                                  moved to the Functional
                                                  Requirements Document,
                                                  replaced with a reference;
                                                  added manufacturer-sourced
                                                  starting values for
                                                  drive-encoder resolution
                                                  (§9.2) and servo pulse-width
                                                  calibration (§11.5) to
                                                  unblock initial software
                                                  bring-up --- flagged
                                                  everywhere as starting
                                                  points for bench
                                                  calibration, not substitutes
                                                  for it; wheelchair handoff
                                                  pose specified (§11.8):
                                                  fully extended, 15° shoulder
                                                  tilt, elbow straight ---
                                                  wrist angles still open;
                                                  physical E-stop confirmed
                                                  installed --- closes the
                                                  last open safety-critical
                                                  item ahead of PCA9685
                                                  replacement and first
                                                  power-up.

  6.0.1                   2026-08-01              PCA9685 incident (§0.3/R-13)
                                                  closed --- replacement
                                                  boards installed, full
                                                  9-device I²C roll-call
                                                  passed clean, commissioning
                                                  gate C-4 marked PASS. Arm
                                                  servo channel map on PCA9685
                                                  0x43 corrected to CH0--6
                                                  (was documented CH9--15 per
                                                  the 5.21 map) --- as-built,
                                                  the arm board starts its
                                                  channel assignment at CH0,
                                                  same base→gripper joint
                                                  order (J0=CH0 \... J5=CH6).
                                                  Updated throughout §3.1,
                                                  §5.2, §11.1, §16.4, §17.3,
                                                  §24.1.

  6.0.2                   2026-08-01              Battery-voltage sensing
                                                  (§8.4) migrated from MCP3008
                                                  (SPI, CH7) to ADS1115 (I²C,
                                                  address 0x48, channel A0)
                                                  --- repeated SPI
                                                  pinout/wiring confusion on
                                                  the MCP3008 channel made it
                                                  an unreliable point of
                                                  failure; the chip itself was
                                                  never confirmed dead and is
                                                  retained as a bench spare.
                                                  Existing CH7/A0 divider
                                                  hardware (10kΩ / 4.7kΩ∥10kΩ)
                                                  is unchanged, only the ADC
                                                  changed. Updated §5.2
                                                  address table and roll-call
                                                  (now 10-device, adds 0x48),
                                                  §8.4, §8.5, §14, §14.2, §15,
                                                  §17, §18 BOM, §20.4, §24.2
                                                  assembly notes, and the I²C
                                                  bus chain description.
                                                  Historical incident entries
                                                  describing the original
                                                  MCP3008 CH7 over-voltage
                                                  exposure are preserved as-is
                                                  for record-keeping.

  6.0.3                   2026-08-02              CORRECTED §9.1 motor/encoder
                                                  wire-color reference: was
                                                  Black=motor−/Green=encoder
                                                  GND (unverified, sourced
                                                  only from an earlier build
                                                  note), now Black=encoder
                                                  GND/White=motor− and
                                                  Yellow/Green=Phase A/B
                                                  (Green replaces the prior
                                                  Yellow/White hedge),
                                                  confirmed by two independent
                                                  JGA25-370 sources including
                                                  a Xuulan manufacturer
                                                  manual. OPEN INCIDENT
                                                  logged: field wiring on at
                                                  least one already-crimped
                                                  motor did not match the
                                                  corrected table (Black found
                                                  in a FeatherWing motor
                                                  terminal); 12V was applied
                                                  at least once in this state.
                                                  First motor physically
                                                  re-checked --- no encoder
                                                  damage found, harness rework
                                                  still needed. Remaining 5
                                                  motors not yet re-checked.
                                                  This correction and incident
                                                  were caught by the person
                                                  after the master doc\'s
                                                  original color table was
                                                  passed along without
                                                  independent verification
                                                  against manufacturer
                                                  documentation first ---
                                                  flagged here so the doc
                                                  reflects the real sequence
                                                  of events, not just the fix.

  6.0.4                   2026-08-02              EPLZON board schematic
                                                  (§5.5) redrawn to remove the
                                                  retired MCP3008 --- the
                                                  embedded diagram previously
                                                  still showed the chip as if
                                                  in use. Board now correctly
                                                  depicts only its 4 voltage
                                                  dividers (3× sonar ECHO + 1×
                                                  battery sense); the battery
                                                  divider midpoint is now
                                                  labeled routing to ADS1115
                                                  A0 off-board instead of the
                                                  old MCP3008 CH7 pin.
                                                  External jumper map
                                                  renumbered from 26 to 22
                                                  total (removed the 4 SPI
                                                  jumpers ---
                                                  SCLK/MISO/MOSI/CE0 --- that
                                                  are no longer needed now
                                                  that battery sensing is
                                                  I²C). Figure caption updated
                                                  to match. This was a
                                                  visual-only correction: no
                                                  physical board rework
                                                  required, since the MCP3008
                                                  footprint was already
                                                  unpopulated per §8.4 ---
                                                  only the diagram was stale.

  6.0.5                   2026-08-02              Noted BNO085 INT (GP15) is
                                                  labeled \"RX\" in the UART
                                                  group on the Nano HAT Hacker
                                                  header, not a numbered pin
                                                  --- GPIO15 doubles as UART0
                                                  RXD and this board
                                                  silkscreens by function
                                                  name. Added to §5.2 address
                                                  table and §15 GPIO wiring
                                                  table to prevent a repeat of
                                                  tonight\'s SPI pin-label
                                                  confusion (pin 12 vs 13) on
                                                  this connection.

  6.0.6                   2026-08-02              Documented owner-specified
                                                  encoder pin convention in
                                                  §9.1: Yellow wire →
                                                  even-numbered MCP23017 pin,
                                                  Green wire → odd-numbered
                                                  pin, within each motor\'s
                                                  Phase A/B pair. Applied
                                                  consistently across all 6
                                                  motors. Added alongside the
                                                  existing
                                                  corrected-wire-color note
                                                  from earlier today.

  6.0.7                   2026-08-02              §0 build status updated:
                                                  suspension issue reported
                                                  and resolved; top/head
                                                  assembly clasped to main
                                                  frame. Two physical
                                                  milestones logged.

  6.0.8                   2026-08-08              As-built pass over §§5.2,
                                                  8.2, 8.5, 13.1--13.4,
                                                  14--14.2, 20.7, correcting
                                                  drift against the
                                                  \"WildWilly Claude Fix\"
                                                  software architecture
                                                  (Phases 1--6, landed
                                                  2026-08-07/08) that this
                                                  doc predated. Key
                                                  corrections: no configured
                                                  systemd `WatchdogSec`
                                                  (500ms claim was never
                                                  deployed); real FSM states
                                                  and `SafetyController.
                                                  emergency_stop()`
                                                  documented in place of
                                                  \"ACTIVE/SAFE_MODE\" and
                                                  \"disable autonomy, allow
                                                  limited manual\"; servo/
                                                  motor-rail overcurrent and
                                                  Pi-undervoltage hazard rows
                                                  marked not implemented (no
                                                  numeric current/voltage
                                                  trip threshold exists in
                                                  code); \"park arm\" on
                                                  fault marked not
                                                  implemented; remote
                                                  command-link timeout marked
                                                  unbuilt (no teleop path
                                                  exists); BNO085 RST pin
                                                  bit-number confirmed
                                                  (MCP23017 port B bit 4) and
                                                  wired in software for the
                                                  first time; GitHub push
                                                  status corrected (working,
                                                  not parked); WD My Cloud
                                                  sync marked roadmap-only,
                                                  `storage.py`\'s real
                                                  configurable-root
                                                  implementation documented
                                                  in its place; world
                                                  model/mapping/navigation
                                                  milestone-1 status added to
                                                  the capability roadmap. See
                                                  `docs/
                                                  WildWilly_Claude_Fix_Gap_Analysis.md`
                                                  and `docs/
                                                  WildWilly_Subsystem_Status.md`
                                                  for the full detail behind
                                                  each correction.

  6.0.9                   2026-08-09              Plan closure: gap-analysis
                                                  tally now DONE 15/PARTIAL 1
                                                  (§12, deliberate)/MISSING 1
                                                  (§17, hardware-gated) ---
                                                  every code-shaped section
                                                  of the Claude Fix plan is
                                                  done. External code-audit
                                                  follow-on closed (8 more
                                                  commits): `smbus2` import
                                                  simulation-safety gap,
                                                  root-false-passing storage
                                                  tests, a new regression
                                                  test against direct
                                                  `DriveBase` bypass,
                                                  thread-join on shutdown for
                                                  5 background threads,
                                                  `config.validate()`
                                                  startup self-check, tick-
                                                  duration telemetry, and a
                                                  `RoverBrain.stop()`
                                                  non-idempotency bug (2nd
                                                  call crashed mid-cleanup).
                                                  Live-verified again on
                                                  fresh code after two
                                                  owner-run restarts: clean
                                                  init, safety FSM, battery-
                                                  shutdown; motion still not
                                                  commanded live. `TICK_
                                                  OVERRUN_THRESHOLD_S` raised
                                                  0.1s→0.15s after `py-spy`
                                                  traced the real cause to
                                                  `brake()`\'s intentional
                                                  per-tick PCA9685
                                                  reassertion (§14). Two
                                                  items remain genuinely
                                                  open, not fixed here:
                                                  `BAT_FULL_V` calibration
                                                  (below `BAT_WARN_V`,
                                                  awaiting owner\'s meter
                                                  reading) and live motion
                                                  verification. See `docs/
                                                  WildWilly_Claude_Fix_Gap_Analysis.md`
                                                  for the section-by-section
                                                  detail.
  ----------------------------------------------------------------------------
