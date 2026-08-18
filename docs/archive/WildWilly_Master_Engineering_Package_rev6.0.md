**WildWilly Autonomous Rover**

Master Engineering Package

**Revision 6.0 · Reorganized & Finalized Baseline**

Document Control

  -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Field**                           **Value**
  ----------------------------------- -----------------------------------------------------------------------------------------------------------------------------------------------------
  Project                             WildWilly Autonomous Rover

  Revision                            6.0 (supersedes 5.80; consolidates and corrects all content through 2026-07-30)

  Document Type                       Master Engineering Package

  Status                              Engineering Baseline --- Reorganized, De-duplicated, Corrected

  Owner                               Howard Himmel

  Scope baseline                      Drive + see + talk/listen + arm pick/place (flat ground) + basic flat-terrain autonomy. Stair-climbing is a STRETCH goal (reclassified 2026-07-18).
  -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**NOTE:** This revision is a structural and factual cleanup of rev 5.80, not a new design pass. Rev 5.80 accumulated \~80 dated micro-revisions as inline narrative, and several of those corrections never fully propagated into the body sections they corrected --- multiple tables still showed superseded I²C addresses, buck assignments, and servo channel maps years (in build-time) after the correct values were established. This revision (a) resolves every such contradiction in favor of the latest bench-confirmed fact, (b) moves narrative \"DESIGN ADDITION / INCIDENT / MILESTONE\" entries into the section they actually belong to, (c) adds one authoritative address/pin table that the rest of the document refers back to instead of restating, and (d) condenses the 80-entry revision log into a readable changelog. No new engineering decisions were made in this pass --- where rev 5.80\'s own text disagreed with itself, the entry with the latest date and \"AUTHORITATIVE\" / \"CONFIRMED\" / \"bench-confirmed\" language won.

0\. Current Build Status & Open Items

This section is the fastest way to answer \"where does the build actually stand.\" Everything below is current as of the last logged session (2026-07-30).

0.1 Done

-   Rocker-bogie chassis: both suspension halves (L/R, 3 wheels each) built and joined; standing on all 6 wheels.

-   Arm mechanically complete: base/shoulder, forearm, elbow, wrist, gripper assembled; link lengths measured (§11.6).

-   Power distribution physically finished: 12V, 6V, and 5V rails each on dedicated distribution boards (4 boards total after the 6V rearrangement).

-   All 6 drive motors landed: power to the two FeatherWings, encoders to the MCP23017, encoder VCC to the 3.3V rail (36 wires).

-   All 6 steering servos landed: signal to PCA9685 0x42, power direct to the 5V rail.

-   Sonar wiring complete on the base side (EPLZON → GPIO, all 3 sensors).

-   Charging interface installed: shrouded EC5 pair + JST-XH balance lead, externally accessible for charge-in-place.

-   Switch 2 (Pi-cutoff in the DROK input line) built --- full wiring audit closed, no unbuilt items remain outside the 4 listed below.

-   Physical E-stop (latching NC mushroom, cuts the 12V bus) installed (2026-07-31) --- functional cut/latch/release test still to run during commissioning (§21.1).

-   Base-only staged power-up passed: 12V / 6V / 5V rails all verified good with the top assembly disconnected.

-   Full 9-device I²C roll-call was previously confirmed working end-to-end (see §0.3 for the current regression).

-   Claude Code installed and authenticated on Willy for on-device software development.

0.2 Remaining --- 4 deliberate connection points

These are intentionally the last connections: disconnecting all 4 fully separates the top assembly (Pi, sensors, arm) from the base (chassis, motors, steering, power) with nothing to desolder, which the build has repeatedly needed for internal access.

  ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **\#**                  **Connection**                **Detail**
  ----------------------- ----------------------------- ----------------------------------------------------------------------------------------------------------------------------------------------
  1                       40-pin ribbon, base → top     Route flat, no fold (a 180° fold mirrors the pinout); stripe → pin 1 at both ends; meter-verify before power (per the §7.4 ribbon incident).

  2                       Arm bulkhead → PCA9685 0x43   7 servo signal leads to CH0--CH6 (base→gripper order); V+/GND direct to the 6V rail.

  3                       Pi power feed                 DROK 5.1V rail to the Pi.

  4                       Sonar harness join            Base ↔ top/head --- electrically already complete; mechanical join only.
  ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

0.3 §Incident 25.16, PCA9685 boards hanging the I²C bus --- RESOLVED (2026-08-01)

Both PCA9685 boards were found holding SDA stuck low, even completely bare (no servos attached) and with base 12V power off. Isolation ruled out servo wiring, VCC/V+ mixups, the ribbon, the bus node board, and the Pi --- the fault was in the PCA9685 boards themselves. Replacement boards ordered from Adafruit (same known-good-supplier approach that resolved the earlier INA219 fault); both installed with their V+ decoupling caps (§10, §11.2) and confirmed on the bus. Full 9-device roll-call passed clean 2026-08-01: 0x27, 0x40, 0x42, 0x43, 0x44, 0x45, 0x4A, 0x60, 0x61 (+0x70 All-Call) --- nothing missing, nothing colliding. This closes the incident and clears commissioning gate C-4 (§21.1).

**NOTE:** A late design note (2026-07-30) observed that the original \"leave PCA9685 V+ unused, run every servo\'s power leads directly to a distribution board\" guidance was more complex than necessary --- with two separate PCA9685 boards, each can simply take its own V+ (0x42→5V, 0x43→6V) and servos can plug straight into the channel headers. The physical steering/arm harnesses are already built the split-lead way and are not being redone; this is recorded for awareness on the replacement boards or any future rebuild, not as a pending task.

0.4 Safety-critical open items

-   Physical E-stop (latching NC mushroom, cuts the 12V bus) --- INSTALLED (2026-07-31). Functional test (latch + release, motion cut confirmed) still to be run as part of the C-gates below.

-   Commissioning gates C-3 through C-8 (junction polarity, post-boot I²C, FET temperature under sustained load, steering torque under load) still need to be run and logged now that the base and top are close to fully landed --- see §21.

0.5 Engineering-review gates still open

-   §4.6 Mass properties & stability --- PENDING MEASUREMENT. Needs real CG data (arm stowed/deployed, full/low battery) once the top assembly is landed.

-   §21.7 Thermal acceptance --- proposed limits defined, not yet tested under sustained load.

-   USB-boot order (Pi 5 → boot from the SanDisk SSD rather than microSD) --- listed as a pending deploy task; not confirmed done in any later entry.

1\. System Overview

1.1 Purpose

WildWilly is a six-wheel autonomous rocker-bogie rover built for mobile-robotics experimentation and, specifically, as a fetch-and-deliver helper for a wheelchair-using family member. Core capabilities: autonomous navigation, local AI inference, voice interaction, object detection and tracking, obstacle avoidance, and robotic manipulation. Rough-terrain and curb handling come from the rocker-bogie suspension as a side benefit; autonomous stair-climbing itself is a stretch goal, not a baseline requirement (§2.1).

1.2 Platform Summary

Base platform: WildWilly Stair-Climbing Rover (Printables #194299), six-wheel rocker-bogie suspension. Nominal envelope 430 × 330 × 220 mm, 103 mm wheels. The original single-piece chassis was outgrown by the payload (Pi 5, AI HAT+, power electronics, robotic arm, sensors, dual battery packs) and replaced by an owner-designed widened, two-level, multi-piece printed chassis (§4).

1.3 Current Architecture

Major subsystems beyond the base rover: Raspberry Pi 5 + Hailo AI HAT+ compute (front-mounted, \"Pi5 Face\"), two-camera vision, voice interface, a 6-DOF/7-servo robotic arm, a 13-sensor network, a 5-rail power-distribution system with per-pack battery protection and charge-in-place, layered electrical safety, and a local-first autonomous software stack. Motor control is fully I²C-based (2× Adafruit FeatherWing #2927) --- there is no discrete motor-driver chip and no direction/PWM GPIO wiring anywhere in the current design.

2\. Mission Requirements

2.1 Functional Requirements

The full functional requirements list has moved to the Functional Requirements Document (WildWilly_Functional_Requirements_Document.docx), which is the authoritative source for FR-xxx requirements, priorities, and verification methods. The mission-level requirements (M-001--M-012) referenced by the traceability table in §2.3 are enumerated there as well, in a new \"Mission-Level Functional Requirements\" section.

**NOTE:** M-006 (stair climbing) was reclassified from must-have to stretch goal on 2026-07-18 --- see the Functional Requirements Document and §2.3 below for current status. This removes drivetrain stall-torque pressure (the FeatherWing\'s 1.2 A/channel, 3 A peak, rating is ample for flat/moderate terrain --- the concern only applied to sustained stair climbing) and demotes the rocker-bogie flex-mechanism question from a blocker to a future refinement.

2.2 Performance Objectives

Target runtime 4--8 h by mode. Navigation indoor/outdoor. Real-time vision object detection. Compute: 26 TOPS local inference (Hailo AI HAT+). Arm reach: 60.5 cm calculated / 59 cm measured fully extended (§11.6) --- supersedes the earlier \~345 mm placeholder figure used before the arm was physically measured.

2.3 Requirements Traceability

Verification method key: I = Inspection · A = Analysis · T = Test · D = Demonstration.

  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **ID**            **Owner subsystem**          **Method**   **Verification**                **Pass/fail criteria**               **Status**
  ----------------- ---------------------------- ------------ ------------------------------- ------------------------------------ ---------------------------------------------------------------------------------
  M-001             software + sensors + drive   T/D          autonomy course test            completes course, avoids obstacles   pending build

  M-002             software (audio)             T            spoken-command test             recognized + correct action          pending build

  M-003             compute (AI HAT+)            T            inference benchmark             runs offline at target rate          pending build

  M-004             compute + vision             T            labeled-object test             correct detection ≥ target           pending build

  M-005             sensors + software           T/D          obstacle-course test            no collisions                        pending build

  M-006 (stretch)   mechanical + drive           T            stair test                      climbs target step height            deferred --- not gating baseline

  M-007             arm + software               T/D          pick/place test                 reaches + grips target               pending --- arm mechanically complete, final electrical landing blocked on §0.3

  M-008             sensor + software            T            calibrated voltage comparison   reported V within 0.05 V             divider fixed (§8.4); calibration pending

  M-009             sensors + software           T            thermal-load test               flags over-temp correctly            pending build

  M-010             safety + power               T            E-stop cut test                 motion bus cut, latched              E-stop installed (2026-07-31); functional cut test pending

  M-011             software (network)           D            Cockpit access test             admin reachable on :9090             partial (host up)

  M-012             compute (SSD)                T            read/write + boot test          boots + logs from SSD                SSD on hand, USB-boot order pending (§0.5)
  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

3\. System Architecture

3.1 System Actuator & Sensor Census (final)

Totals: 6 drive motors + 13 servos (6 steering + 7 arm) = 19 actuators; 6 encoders + 3 sonar + 1 IMU + 3 current monitors = 13 sensors; 2 cameras.

  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Class**               **Qty**                 **Detail (bus / channel / rail)**
  ----------------------- ----------------------- --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  Drive motors            6                       JGA25-370B 12V gearmotors --- 2× Adafruit FeatherWing #2927 (I²C \@0x60 LEFT / 0x61 RIGHT), 12V to VIN via F2 10A. No discrete driver chip, no direction/PWM GPIO.

  Wheel encoders          6                       Integral to the drive motors --- quadrature A/B via MCP23017 0x27 (bench-confirmed; corrects the originally-documented 0x20).

  Steering servos         6                       GDW DS041MG 180° --- PCA9685 0x42, CH0--5, 5V rail direct.

  Arm servos              7                       4× MG996R (base J0, shoulder J1a/J1b, elbow J2) + 3× MG90S (wrist rotate J3, wrist pitch J4, gripper J5) --- PCA9685 0x43, CH0--6, ALL on the 6V/DZS rail (final, 2026-07-28).

  Cameras                 2                       Front Arducam IMX708 (CSI, ORB-SLAM3 + forward YOLO); Rear OV9782 (USB, YOLO/monitoring + descent view).

  Sonar                   3                       HC-SR04 front(center)/left/right --- TRIG GP5/13/4, ECHO GP26/14/21 (÷ dividers). No rear sonar exists.

  IMU                     1                       BNO085 9-DoF, I²C 0x4A, INT→GP15, RST→MCP23017 spare pin.

  Current monitors        3                       INA260 servo/steering 0x40 (replaced a faulty INA219), INA260 Pi 0x44, INA260 motor 0x45.
  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

3.2 Subsystems

Nine major subsystems: A. Structure · B. Power Distribution · C. Compute Core · D. Sensor Network · E. Drive System · F. Steering System · G. Robotic Arm · H. User Interface · I. Safety System.

3.3 Architectural Philosophy

Modular construction, serviceable wiring (four deliberate top/base disconnect points, §0.2), independent power rails, distributed sensing, centralized decision making, fail-safe operation, expandability.

3.4 High-Level Architecture

Battery System → Protection System → Power Distribution → Compute + Sensors + Motion Systems → Autonomous Control.

4\. Mechanical Design Package

4.1 Chassis

Widened two-level architecture, developed because the original WildWilly frame could not house the Pi 5, AI HAT+, power electronics, arm, sensors, and dual battery packs. Retains the original rocker-bogie suspension geometry. Frame is split multi-piece (also exceeds the print bed as a single piece); mirrored parts (suffix \"m\") must be printed mirrored, not duplicated.

4.2 Structural Layout

Lower level: left and right battery bays flanking a central power tray (packs mounted low, vented, hatch-accessible for charge/swap). Upper level: sensor tray and controller tray, both mounted horizontally, wiring distribution, compute support structure.

4.3 Front Compute Bay (\"Pi5 Face\")

Raspberry Pi 5, AI HAT+, display, audio, and active cooling are mounted LOW on the front of the body, with the arm turret directly above. The display faces forward, top edge nearly flush with the top of the body. This front-mounted layout (lower CG, no overhang, short camera FFC) supersedes an earlier rear-cantilever \"pod\" concept. The active cooler must exhaust to the front/sides, not straight up into the arm above it --- confirm airflow path and AI HAT+ temperature under sustained inference. The arm turret\'s full sweep, not just its stow position, must clear the AI HAT+ (the tallest element of the stack).

4.4 Robotic Arm Mount

Arm mounts to the front deck, J0 turret \~40 mm aft of the Pi5 Face front face to avoid collision. 6-DOF, 7 servos (§11) sourced from MakerWorld 1134925 (standalone 6-axis arm), adapted onto WildWilly\'s front-deck turret. Stow pose: single boom folded/pitched down, confirmed to sit below the front camera\'s sightline through the full motion envelope, not just at rest.

4.5 Weight and Center of Gravity

The CG model remains ESTIMATED. See §4.6 --- this is an open engineering-review gate, not yet closed.

4.6 Mass Properties & Stability Closure --- PENDING MEASUREMENT

Required closure data, to be measured on the assembled rover:

  -----------------------------------------------------------------------------------------------------------------------------
  **Condition**                            **Whole-rover CG (x/y/z)**   **Static tip-over angle**   **Notes**
  ---------------------------------------- ---------------------------- --------------------------- ---------------------------
  Arm stowed, full battery                 --- / --- / ---              ---°                        baseline

  Arm stowed, low battery                  --- / --- / ---              ---°                        CG shift as packs deplete

  Arm deployed (max reach), full battery   --- / --- / ---              ---°                        worst forward moment

  Arm deployed, low battery                --- / --- / ---              ---°                        combined worst case
  -----------------------------------------------------------------------------------------------------------------------------

Operating limits to derive from the above (also pending): max safe arm extension while moving, speed limit while arm deployed, payload limit at full reach, payload limit at mid reach.

5\. Electrical Design Package

5.1 Design Philosophy

Four principles: independent power domains, single-point grounding, distributed protection, serviceable wiring.

5.2 Address & Pin Map --- the single authoritative table

This is the corrected, bench-confirmed, final address map. Every other section and table in this document refers back to this one rather than restating it. Where any figure elsewhere in earlier revisions disagreed with this table (several did --- see the rev 6.0 note in Document Control), this table is correct.

  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Address / Bus**       **Device**                        **Role**
  ----------------------- --------------------------------- --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  0x27                    MCP23017                          Encoder GPIO expander (6 encoders, quadrature A/B). Bench reads 0x27, not the originally-documented 0x20 --- address pins read CLOSED; owner elected to keep switches as-is rather than re-flip.

  0x40                    INA260 (servo/steering current)   Replaced a faulty INA219 (2026-07-27). No jumpers = default address, freed by removing the INA219.

  0x42                    PCA9685                           Steering --- 6 channels, CH0--5.

  0x43                    PCA9685                           Arm --- 7 channels, CH0--6.

  0x44                    INA260                            Pi 5V rail current.

  0x45                    INA260                            Motor 12V rail current.

  0x4A                    BNO085                            IMU. INT→GP15, RST→MCP23017 spare pin.

  0x60                    Adafruit FeatherWing #2927        LEFT motor driver --- LF/LM/LR.

  0x61                    Adafruit FeatherWing #2927        RIGHT motor driver --- RF/RM/RR.

  0x70                    (PCA9685 All-Call)                Reserved broadcast address --- appears in roll-call, not a real device.

  SPI (not I²C)           MCP3008                           Battery-voltage ADC, CH7 (divider --- §8.4).

  no address              LTC4311                           I²C bus accelerator, transparent pass-through at the far end of the bus run.
  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**NOTE:** Full 9-device roll-call (excludes LTC4311 and the SPI-only MCP3008): 0x27, 0x40, 0x42, 0x43, 0x44, 0x45, 0x4A, 0x60, 0x61 (+0x70 All-Call). This has been bench-confirmed working simultaneously multiple times; the current open incident (§0.3) is isolated to the two PCA9685 boards themselves, not the bus or address map.

5.3 Power Domains

Domain A motor rail (12V) · Domain B servo/steering rail (5V) · Domain C arm rail (6V) · Domain D compute rail (5V, isolated from Domain B).

5.4 Protection Layers

Primary: 30A ATC main fuse (F1, off-board). Secondary: branch fuses F2--F6 (§6.4). Reverse-polarity: FQP27P06 P-channel MOSFET (Q1) with a 220nF gate-source soft-start cap (added after the DZS failure incident, §6.7). Transient: P6KE15A TVS (D1). Per-pack backstop: dual 3S BMS (§6.2). Emergency shutdown: physical latching mushroom E-stop --- INSTALLED (2026-07-31) --- plus Switch 2 (Pi-only cutoff, §6.6).

5.5 Grounding Strategy

Single-point, two-level (star-of-stars) ground. Power-tray grounds return to the common rail (single-point star / battery-return side); control-tray grounds collect on local buses that connect to the common rail by exactly one link. Rule: no second inter-tray ground path (a conductive standoff, frame, or dual-grounded device bridging both trays is a ground loop). PCA9685 reference-grounds and encoder logic grounds land on the control-tray bus, not the power rail directly.

5.6 Formal Schematic Set --- status

Ten schematic-style sheets exist as a build/wiring reference. Two are confirmed current against this revision\'s address map (Power Schematic and I²C Network Schematic, both redrawn 2026-07-19/20 against bench-confirmed addressing). The remaining sheets (GPIO, Motor, Servo, Arm, Pi5 Face wiring, and the two reference sheets) were drawn against the pre-FeatherWing / pre-final-address architecture and are flagged for a redraw pass in a future revision --- treat the tables in this document as authoritative over any schematic image until that redraw is done. The recently-added reference diagrams (BMS wiring, charge-in-place, I²C/power bus node board, EPLZON CH7 divider) are current as of their addition date and are reproduced below.

![](media/b8d5106fdcb3a289da623dc616271951b40236c0.png){width="6.0in" height="4.3125in"}

*Power Schematic --- current, bench-confirmed addressing (2026-07-19).*

![](media/660192b49ed6b5b918dcad10134802b1f0686b8c.png){width="6.0in" height="4.177083333333333in"}

*I²C Network Schematic --- current, bench-confirmed addressing including 0x60/0x61 (2026-07-20).*

![](media/e4db6e77a4cc638d5ef6385fbac4059f07a0178f.png){width="6.0in" height="4.104166666666667in"}

*I²C / Power Bus Node Board --- 4 rails (3V3/SDA/SCL/GND), 8 device taps, LTC4311 + pull-ups. This exact board previously had 3V3/GND swapped onto SDA/SCL (§7.5 incident) --- the standing rule since then is to meter-verify every tap of any home-built bus board before first power-up.*

![](media/bb9edc485277287abeb6c2f39bc697000a7ada78.png){width="5.5in" height="6.041666666666667in"}

*EPLZON board --- owner\'s original layout (top) plus the CH7 battery-sense divider added 2026-07-27 (bottom, schematic reference only --- use the board\'s own printed A--J/numbered grid for physical placement, not the \"column 19/28\" labels).*

![](media/ff4f9c1a07bd9290ed9e43623695b4357ee669f9.png){width="6.0in" height="4.0625in"}

*Dual-BMS wiring --- one BMS per pack before the parallel junction; positives bypass, negatives through B−/P−; balance taps and the paraboard share cell nodes.*

![](media/915e6c0f66756fd166fcf639a281a56867297407.png){width="6.0in" height="4.0625in"}

*iMAX B6 charge-in-place --- T-tapped main leads to a shrouded jack, paraboard-combined balance via JST-XH extension to the charger.*

6\. Power System Design

6.1 Battery System

Two 3S LiPo packs, 8000 mAh each, hard-paralleled (\~16,000 mAh @ 11.1V nominal). Mounted low, left and right, flanking the central power tray. Packs must be within 0.05 V/cell before paralleling --- never join a charged pack to a depleted one.

6.2 Per-Pack BMS (added 2026-07-18)

One BMS per pack (40--60A, with balance), wired BEFORE the parallel junction, permanent (soldered) install --- a discharge/short backstop layered under the existing P-FET/TVS/fuse protection, not a replacement for it.

-   Pack + (positive) bypasses the BMS, straight to the parallel junction.

-   Pack − → BMS B−; BMS P− (protected negative) → parallel junction. Negative-side switching only, never positive.

-   Balance taps: each pack\'s JST-XH 4-pin → BMS pads B0/B1/B2/B+, strictly in 0/4.2/8.4/12.6V order (out-of-order = board damage). The 2×3S paraboard shares the same nodes.

-   Main current wire ≥12 AWG. Test every undocumented board (B−→P− pass, cell taps read) before soldering in permanently.

6.3 Main Power Path

Battery → per-pack BMS → parallel junction → 30A main fuse (F1) → KCD4 master switch → E-stop → FQP27P06 reverse-polarity FET (Q1) → protected 12V bus → subsystem fuses F2--F6.

6.4 Power Rails & Distribution Boards

Five voltage rails, five distribution boards. The Pi 5V rail is the only one with no distribution board (feeds the header pins directly).

  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Rail**         **Nominal V**   **Source**        **Fuse**    **Feeds**                                      **Current monitor**
  ---------------- --------------- ----------------- ----------- ---------------------------------------------- ------------------------------------------------------------------------
  Motor (VM)       12V             +12V bus          F2 10A      2× FeatherWing VIN (6 drive motors)            INA260 0x45, inline before the FeatherWing split

  Pi input         12V             +12V bus          F3 5A       DROK 12A buck input                            ---

  Servo/steering   5V              FEICHAO 8A UBEC   F4 10A      6× DS041MG steering + 3× sonar VCC             INA260 0x40

  Arm              6V              DZS 12A buck      F5 10A      All 7 arm servos (4× MG996R + 3× MG90S)        monitored via 0x40 rail history; dedicated stall-cut logic recommended

  Pi output        5V              DROK 12A buck     F6 10A      Pi 5 + AI HAT+ + SSD + display + audio + fan   INA260 0x44

  Logic            3.3V            Pi onboard reg    ---         All I²C VCC + 6 encoder VCC                    \<0.5A, no monitor needed
  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**NOTE:** CONVERTER MAP --- the DROK 12A LCD-display buck feeds the Pi \@5.1V; the DZS 12A buck feeds the arm 6V rail; the FEICHAO 8A UBEC feeds the 5V servo/steering rail. Earlier drafts of this document repeatedly had DROK and DZS swapped --- this is the corrected, owner-confirmed (2026-07-19) mapping and overrides any contrary text.

6.5 Acceptance Criteria

-   Pi rail at the Pi5 Face junction: 5.0--5.1V no-load, not below 4.85V at peak combined load.

-   FQP27P06 FET: warm, not hot, under sustained \~15A (with copper heatsink and isolated tab).

-   No nuisance fuse trips during worst-case validated transient loads.

-   Parallel packs within 0.05 V/cell before joining.

6.6 Switch 2 --- Pi-cutoff (built 2026-07-30)

A second switch in the DROK input line, separate from the main KCD4/E-stop. Purpose: \`shutdown -h now\` halts the OS but leaves the Pi\'s regulator --- and therefore the entire 3.3V/I²C bus --- energized as long as 12V input power is present. Switch 2 fully de-powers the Pi and 3.3V bus after a software shutdown.

6.7 DZS Buck Failure --- Root Cause & Fix (resolved)

An earlier live adjustment of a buck converter\'s trim pot (under load) shorted the DZS buck internally, back-fed the bus, and destroyed the P-FET, repeatedly blowing F3. Root cause: never adjust a converter pot while it feeds a live load. Standing rule since: pre-set every buck pot OFF-LOAD on the bench first, then wire it in. Fix: FET, TVS, and buck replaced; 220nF gate-source soft-start cap added to Q1 to limit turn-on inrush (§5.6, Sheet 8). Retested OK 2026-06-29.

6.8 Charge-in-Place Subsystem

Goal: recharge both packs without unbolting them. The charge connector taps the common battery node ahead of the KCD4 master switch, so switching the rover off isolates all rover loads while the cells remain reachable for charging. Because the two packs share only their outer terminals, both balance ports are brought out and paralleled into one 3S balance breakout (paraboard) --- the charger sees a single 3S, \~16 Ah pack.

  -----------------------------------------------------------------------------------------------------------------
  **Item**                **Detail**                                                       **Status**
  ----------------------- ---------------------------------------------------------------- ------------------------
  Bulkhead connector      Shrouded EC5 pair, recessed, through the chassis wall            INSTALLED (2026-07-30)

  Balance extension       JST-XH 4-pin, routed to the same access point                    INSTALLED (2026-07-30)

  Inline charge fuse      \~15A ATC, sized to charger output, in the charge+ line          to verify installed

  Paraboard               2×3S parallel-charge board, combines both packs\' balance taps   per BOM

  External charger        iMAX B6 80W, \~4A (\~0.25C of the 16Ah pair) balance charge      ON HAND
  -----------------------------------------------------------------------------------------------------------------

During charging, the iMAX is primary (per-cell monitor + balance + 4.2V cutoff); the per-pack BMS rides along as backstop. KCD4 must be OFF during charge --- charge access still reaches the cells with the rover fully isolated.

7\. Compute System Design

7.1 Core Compute

Raspberry Pi 5 (8GB) + Hailo AI HAT+ (26 TOPS, PCIe FFC) in the front compute bay, with a USB SSD, DSI Touch Display 2, and USB audio. AI stack: YOLOv8 (Hailo), faster-whisper STT, Llama 3.2 3B, Piper TTS, openwakeword --- all local/offline inference. Model training happens off-board on a PC; the Pi does inference only.

7.2 GPIO Breakout --- Pimoroni Nano HAT Hacker

Replaced the original ZDE-type GPIO expansion board (2026-07-24) --- smaller footprint, 4-corner mounting (the original had only 2, both at one end), and every pin labeled with both BCM number and descriptive function (I2C/UART/SPI/PWM/I2S) directly on the silkscreen. Confirmed: I²C group reads \"5V · 5V · DA · CL\" --- DA = SDA = physical pin 3, CL = SCL = physical pin 5. It is a straight 1:1 passthrough with no active circuitry --- verification is done by reading the board\'s own silkscreen rather than inferring from documentation. Caution: a second \"CL\" label appears elsewhere under the SPI group (a different pin, SPI clock) --- read the category header above a label, not just the label.

7.3 Camera / Vision Architecture

Two cameras, fixed roles, neither doing audio:

-   FRONT --- Arducam IMX708 Module 3 Wide (CSI): mounted on the front face, just below the display/arm-stow line, slight down-tilt. Short CSI FFC directly to the Pi CAM0 port. Runs ORB-SLAM3 (forward visual odometry/mapping) and forward YOLOv8 object detection.

-   REAR --- OV9782 (USB, UVC): mounted on the rear of the body. Plug-and-play, no FFC. YOLO/monitoring + descent view.

Front-stack thermal note: the Pi5 Face stack runs hot under simultaneous SLAM + YOLO and is now capped by the arm above it rather than venting to open air --- the active cooler must exhaust to the front/sides.

7.4 Storage

SanDisk Extreme PRO Portable SSD 500GB via USB 3.0 (strain-relieved with a short extension + mount clip) as the primary boot drive --- OS, AI models, and the local chat-memory DB. A high-endurance A2 microSD is kept as a recovery/initial-flash fallback, not primary. USB-boot order (Pi 5 booting from the SSD rather than the microSD) is a listed pending task --- no later entry confirms it done; verify before relying on it.

7.5 Pi 5 Replacement --- Incident Summary (closed)

The original Pi 5 developed a hardware fault on its I²C-1 controller (physical pins 3/5): every device on the bus went silent, and the fault persisted even with nothing wired to the header at all (ruling out any device, wiring, hub, or ribbon cause) and even under a deliberate SDA/SCL-to-GND short test that a healthy controller should have reacted to. Root cause, identified afterward: an earlier session had 3V3/GND wired onto the SDA/SCL lines of the I²C/power bus node board (§5.6) --- the Pi\'s open-drain I²C driver was fighting a hard 3V3 source instead of a resistor under live power, which is consistent with damaging the GPIO pin-driver. A same-spec replacement Pi 5 was ordered and installed (2026-07-24, old SSD carried over intact); the new board\'s I²C-1 tested clean (zero dmesg errors) on a bare-bus test, and the full 9-device roll-call was subsequently reconfirmed working end-to-end, closing the incident.

Standing rule adopted from this incident: before first power-up of any home-built bus/breakout board, meter-verify each of its rails against the known Pi pin it should trace to --- do not assume a board\'s silkscreen or hole order matches the intended signal, even on a board you built yourself.

8\. Sensor System Design

8.1 Sonar

3× HC-SR04, front(center)/left/right. There is no rear sonar --- the only rear-facing device on the rover is the rear USB camera (§7.3). This corrects a naming error present throughout earlier drafts, which repeatedly labeled the third sonar \"rear\"; the GPIO assignments were never wrong, only the position name.

  ------------------------------------------------------------------------------
  **Position**            **TRIG**                **ECHO (via 1k/2k divider)**
  ----------------------- ----------------------- ------------------------------
  Front (center)          GP5                     GP26

  Left                    GP13                    GP14

  Right                   GP4                     GP21
  ------------------------------------------------------------------------------

Wire color key (physical harness, distinct from schematic role-coloring): BLUE = GND, PURPLE = ECHO, GRAY = TRIG, WHITE = VCC. Each sonar uses a two-part plug connector (not direct solder) --- verify plug orientation against this key before mating. Wiring is complete on the base side (2026-07-29); the sonar base-to-top harness join is one of the four remaining connection points (§0.2).

8.2 IMU --- BNO085

9-DoF, I²C 0x4A, replaces an earlier MPU-6050 plan. On-chip SH-2 sensor fusion gives drift-free heading without a magnetometer (useful given six nearby motors). VIN = 3.3V, P0/P1 floating selects I²C mode.

  -------------------------------------------------------------------------------------------
  **Pin**           **Dir**           **Connects to**       **Note**
  ----------------- ----------------- --------------------- ---------------------------------
  VIN               IN                3.3V                  board supply

  GND               IN                logic ground bus      

  SDA / SCL         I/O               I²C bus (GP2/GP3)     shared bus

  AD0               IN                GND                   sets address 0x4A

  INT               OUT               Raspberry Pi GP15     required for SH-2 report timing

  RST               IN                MCP23017 spare GPIO   software-reset capable

  P0 / P1           ---               unconnected           selects I²C mode
  -------------------------------------------------------------------------------------------

8.3 Current Sensing

Three INA260 modules (§5.2): 0x40 servo/steering rail, 0x44 Pi rail, 0x45 motor rail --- all inline (series), not parallel taps. 0x40 originally held an INA219, replaced 2026-07-27 after an intermittent, inconclusive voltage-sag fault on the servo rail (drop varied 0.23--1.07V under similar conditions across repeated tests); root cause was traced to the INA219 module itself, not the UBEC, EPLZON board, or wiring. All three power rails were confirmed healthy after the swap.

8.4 Battery Voltage Sensing --- MCP3008 CH7

MCP3008 (SPI, on the sensor EPLZON) reads battery voltage on CH7. An early build error had CH7 wired directly to the +12V rail with no divider at all --- an over-voltage exposure that the chip\'s internal clamp diodes were absorbing (confirmed via a near-full-scale raw reading, 1016/1023). Root cause: the EPLZON\'s six built-in divider resistors are all dedicated to the three sonar ECHO lines; CH7 was never given its own divider in the original board design.

Fix (2026-07-27): a standalone 10kΩ / \~3.2kΩ divider (4.7kΩ ∥ 10kΩ substituted for an unavailable 3.3kΩ) was added between the +12V rail and CH7, with the divider midpoint --- not raw 12V --- landing on the ADC pin. Result: \~2.76V at 11.4V (nominal) and \~3.06V at 12.6V (full charge), both safely inside the MCP3008\'s 0--3.3V input range. Divider resistors installed and the EPLZON remounted (2026-07-27). Note: the EPLZON is a perfboard (confirmed by photo), not a breadboard --- use the board\'s own printed A--J/numbered grid to place components, not the \"column 19/28\" labels used in early design notes for this fix (those describe the circuit topology correctly, not real hole positions).

8.5 Sensor Polling & Fault Behavior

  --------------------------------------------------------------------------------------------------------------
  **Sensor**              **Target poll**         **Timeout / fault response**
  ----------------------- ----------------------- --------------------------------------------------------------
  BNO085 IMU              100 Hz                  I²C timeout → disable autonomy, allow limited manual

  INA current (×3)        10 Hz                   read fail → log, hold last; sustained fail → SAFE_MODE

  Encoders (MCP23017)     continuous (IRQ/poll)   no counts while commanded → stop affected drive

  HC-SR04 sonar (×3)      10--20 Hz               echo timeout → treat as \"no obstacle in range\", flag noisy

  Battery (MCP3008 CH7)   1 Hz                    read fail → assume worst-case, warn
  --------------------------------------------------------------------------------------------------------------

9\. Drive System Design

6× JGA25-370B 12V gearmotors, driven entirely over I²C by 2× Adafruit FeatherWing #2927 boards --- 0x60 (LEFT: LF/LM/LR) and 0x61 (RIGHT: RF/RM/RR), via the Adafruit MotorKit library. This is a complete architecture change from an earlier discrete 3× TB6612FNG design: there is no direction GPIO wiring, no STBY line, and no external PWM anywhere in the current build --- speed, direction, and (via MotorKit) proportional control are fully internal to each FeatherWing. The formerly-used GP7 (STBY) line and the twelve direction-GPIO lines are freed for other use.

9.1 Motor / Encoder Wiring (complete)

  --------------------------------------------------------------------------------------------------
  **Motor**         **Power (2-wire) →**   **Encoder (4-wire) →**   **Note**
  ----------------- ---------------------- ------------------------ --------------------------------
  LF                FeatherWing 0x60, M1   MCP23017 GPA0/GPA1       LEFT board, port 1

  LM                FeatherWing 0x60, M2   MCP23017 GPA2/GPA3       LEFT board, port 2

  LR                FeatherWing 0x60, M3   MCP23017 GPB0/GPB1       LEFT board, port 3 (M4 spare)

  RF                FeatherWing 0x61, M1   MCP23017 GPA4/GPA5       RIGHT board, port 1

  RM                FeatherWing 0x61, M2   MCP23017 GPA6/GPA7       RIGHT board, port 2

  RR                FeatherWing 0x61, M3   MCP23017 GPB2/GPB3       RIGHT board, port 3 (M4 spare)
  --------------------------------------------------------------------------------------------------

6-wire JGA25-370B crimp reference by color: Red/Black = motor+/− (to FeatherWing M-terminals); Blue = encoder VCC → 3.3V distribution board; Green = encoder GND; Yellow/White = encoder Phase A/B → MCP23017. Blue/Green can be swapped per manufacturing batch --- meter each motor before crimping. Encoders are powered at 3.3V (not 5V) to match MCP23017 logic levels.

Status: COMPLETE. All 6 motors landed (power + encoder + VCC, 36 wires total, milestone 2026-07-30).

9.2 Gear Ratio & Encoder Resolution --- starting values from the manufacturer listing

The BOM specifies \"JGA25-370B 12V 620RPM.\" No official datasheet PDF exists for this generic motor family, but the matching commercial listing for the 12V/620RPM variant (JGA25-370-12V620-E) gives a 1:75 reduction ratio and a Hall-sensor resolution of 823.1 pulses per revolution at the output shaft --- consistent with the encoder\'s native 11 PPR on the motor shaft × 75:1 gearing. Use these as the starting constants in config.py, then confirm against the build: bench-measured PPR can vary a few percent between \"620RPM\" listings from different sellers, and §9.3 below already flags this as something to measure on the build rather than assume.

  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Constant**                                                      **Starting value (from matching commercial listing)**   **Note**
  ----------------------------------------------------------------- ------------------------------------------------------- ----------------------------------------------------------------------------------------------------------------------
  Reduction ratio                                                   1:75                                                    motor-shaft encoder × gearbox

  Encoder PPR (single channel, output shaft)                        823.1 PPR                                               11 PPR (motor shaft) × 75

  Quadrature counts/rev (if decoding both edges of both channels)   \~3,292 counts/rev                                      823.1 × 4 --- use this constant if the encoder driver does full quadrature decoding rather than single-edge counting

  No-load speed                                                     620 RPM @ 12V                                           per BOM/listing; actual under load will be lower
  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

9.3 Drive Conventions (confirm on first movement test)

-   Encoder counts per wheel revolution --- starting value \~823 PPR at the output shaft per §9.2 (matching commercial listing); confirm on the actual build, since seller-to-seller variance on \"620RPM\" units is real.

-   Wheel direction/sign convention --- forward = positive count; confirm per-corner polarity during the dry test.

-   Acceptance: commanded direction matches observed rotation on all 6 wheels; encoder counts increment in the commanded sign.

9.4 Drive Verification & Control Parameters (proposed --- confirm/tune on build)

  --------------------------------------------------------------------------------------------------------------------------------------
  **Parameter**                        **Value / method**                                     **Acceptance**
  ------------------------------------ ------------------------------------------------------ ------------------------------------------
  Left/right direction map             per-corner polarity recorded in config.py (MotorKit)   commanded dir = observed rotation, all 6

  Minimum controllable speed           lowest stable MotorKit throttle (measure)              wheel turns smoothly, no stall

  E-stop command behavior              hardware cut + software stop                           all motion ceases immediately

  Fail-safe on controller disconnect   motors disable (I²C command stop), arm holds           default-off, no runaway
  --------------------------------------------------------------------------------------------------------------------------------------

10\. Steering System

6× GDW DS041MG steering servos (180°, coreless digital, metal gear, 12g, 25T spline) --- replaces an earlier MG90S plan (2026-07-03) for adequate torque. PCA9685 0x42, CH0--5.

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

Center = 1500 µs (wheels straight); 500--2500 µs = full 180°, software-limited per corner to wheel-well clearance. This matches the manufacturer\'s own default signal spec for the DS041MG (500--2500µs = 180°, 1000--2000µs = the narrower 90° mode some units ship configured for) --- confirm which mode a given unit is in before setting per-corner limits, since some DS041MG stock ships in the 900--2100µs/120° mode instead. Power (V+ and GND) runs directly from the 5V FEICHAO rail to each servo; only the signal wire goes to the PCA9685 channel pin, plus a thin reference-ground tie so the PWM signal shares a ground potential with the servo. Status: COMPLETE (all 6 landed, milestone 2026-07-30).

Independent per-wheel steering enables point-turn (rotate in place), crab (all wheels parallel, translate sideways), and coordinated Ackermann turns. Pending in software: steering kinematics, per-corner angle limits from wheel-well clearance, and crab/spin coordination math.

**NOTE:** Add a V+ decoupling capacitor to the PCA9685 0x42 board at its unpopulated \"C2\" pad (Adafruit boards ship without one --- pad only). Adafruit\'s own sizing guidance is \~100µF per servo driven; with 6 steering servos potentially moving together, install a \~1000µF ≥16V low-ESR electrolytic, positive lead to the pad marked \"+\". On hand: 1000µF/16V electrolytics (15 pcs) --- one is exactly the target size. Do this before landing the replacement board (§0.3).

11\. Robotic Arm Design

11.1 Architecture --- final, as-built

6-DOF, 7 servos, sourced from MakerWorld 1134925 (standalone 6-axis arm, adapted onto WildWilly\'s front-deck turret). This is the corrected final map after several intermediate revisions (an elbow-removed 2-DOF variant, a 5-servo variant) --- the 7-servo/6-DOF configuration below is owner-confirmed against the physical hardware and authoritative.

  ---------------------------------------------------------------------------------------------------------------------------
  **Joint**         **Motion**                                       **Servo**      **PCA9685 0x43 channel**   **Rail**
  ----------------- ------------------------------------------------ -------------- -------------------------- --------------
  J0 Base           Yaw --- left-right, whole arm                    MG996R         CH0                        6V (DZS)

  J1a Shoulder A    Pitch --- up-down (paired with J1b)              MG996R         CH1                        6V (DZS)

  J1b Shoulder B    Pitch --- up-down (paired with J1a, same axis)   MG996R         CH2                        6V (DZS)

  J2 Elbow          Pitch --- up-down                                MG996R         CH3                        6V (DZS)

  J3 Wrist rotate   Yaw --- hand left-right                          MG90S          CH4                        6V (DZS)

  J4 Wrist pitch    Bend --- up-down                                 MG90S          CH5                        6V (DZS)

  J5 Gripper        Open/close jaw                                   MG90S          CH6                        6V (DZS)
  ---------------------------------------------------------------------------------------------------------------------------

All 7 servos share the 6V/DZS rail --- this is the final decision (2026-07-28), superseding an earlier split-rail plan (MG996R@6V / MG90S@5V) that was tried the same day and reversed. Reason: the 5V rail (6× DS041MG steering + 3× MG90S + 3× sonar) worst-cased to \~11.4A against the FEICHAO UBEC\'s 8A rating; moving the three MG90S to 6V drops worst-case 5V load to \~9A (steering only, still near the rail limit --- monitor) and removes arm-servo switching noise from the sonar power rail. MG90S is rated 4.8--6.0V, so 6V is in-spec at the ceiling, not overdriving.

Shoulder pair: J1a (CH10) is physically the RIGHT-side servo, J1b (CH11) is LEFT-side; both drive the same pitch axis and must be commanded as a coordinated/mirrored pair in software (one likely needs an inverted angle command relative to the other), not independently.

11.2 Power Routing

Each servo\'s V+ and GND leads run directly to the 6V rail (not through the PCA9685 V+ pin); only the signal wire threads through the PCA9685 channel pin, with a thin reference-ground tie to the star so the PWM signal shares ground with the servo. This is the physically-built method --- see §0.3 for a late design note on a simpler alternative that was not retroactively applied.

**NOTE:** Add a V+ decoupling capacitor to the PCA9685 0x43 board at its unpopulated \"C2\" pad, same as §10 for the steering board. With 7 arm servos (4× MG996R at meaningfully higher stall current than the steering/wrist servos) potentially moving together, size generously: \~1500--2200µF ≥16V low-ESR. Preferred part, arriving 2026-08-01: Rubycon 2200µF 16V 12.5×20mm low-ESR (0.041Ω) radial electrolytic --- a single can lands right at the top of the target range, so the earlier \"two 1000µF caps, one external\" workaround (§0.3/§18.4) is no longer needed once these arrive; check the C2 pad\'s lead spacing before soldering, as this is a larger can than the on-hand 1000µF units. If landing the board before 08-01, the interim 1000µF (on C2) + 1000µF (external, on the V+/GND screw terminal) combo works fine and can simply be desoldered and replaced with the single Rubycon can later --- no rework elsewhere needed.

11.3 Wiring Status

Mechanically COMPLETE (2026-07-24) --- base/shoulder, forearm, elbow, wrist, gripper all assembled, signal wires routed and joint-labeled (SHO/ELB/WRI tags). A bulkhead connector was added for the full 7-servo harness so the arm can be detached without desoldering. Final landing to PCA9685 0x43 CH0--6 is one of the four remaining top/base connection points (§0.2), currently blocked on the PCA9685 replacement (§0.3).

11.4 Kinematics

IK approach: elbow-up (base yaw + shoulder + elbow position the wrist), with a 2-axis wrist (pitch + roll\... i.e. rotate) orienting the gripper. Dual shoulder is driven as one mirrored joint (J1b = 2×1500µs − J1a); watch the current sensor on the arm rail --- sustained current with no commanded motion means the pair is fighting, and PWM should be cut.

11.5 Servo Pulse-Width Starting Values (manufacturer defaults --- bench-verify per unit)

No per-unit calibration exists yet in config.py/arm.py. These are manufacturer-published nominal defaults to seed the calibration step in §20.6 --- not a substitute for it. Cheap-clone MG996R units in particular are known to fall short of the full nominal 180° sweep (one documented case measured only \~130° of real mechanical travel before the gears bound), so treat these as safe starting bounds to probe inward from, not values to trust blind.

  -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Servo**                   **Nominal pulse width @ 180°**                                   **Center (0°/mid)**   **Note**
  --------------------------- ---------------------------------------------------------------- --------------------- ----------------------------------------------------------------------------------------------------------------------------------------------------------
  MG996R (J0, J1a, J1b, J2)   500--2500µs                                                      1500µs                Manufacturer spec sheet. Real clones commonly bind before the full range --- verify per-joint end-stops on the bench before committing limits to arm.py.

  MG90S (J3, J4, J5)          \~500--2400µs (sources vary 400--2400 to 500--2400)              1500µs                No single authoritative datasheet across vendors; treat 500--2400 as the conservative starting bound.

  GDW DS041MG (steering)      500--2500µs (180° mode) or 900--2100µs (120° mode, some stock)   1500µs                See §10 note --- confirm which mode a given unit shipped in.
  -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

11.6 Link Lengths --- measured (2026-07-26, supersedes all earlier figures)

Physically measured off the assembled arm, pivot-to-pivot along the centerline. This supersedes an old unverified L1=L2=150mm figure and the \~345mm reach placeholder used earlier in this document.

  ------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Segment**                                       **Length**
  ------------------------------------------------- ----------------------------------------------------------------------------------------------------------
  Base height (mount surface → shoulder pivot J1)   4 cm (\~1.6 in)

  L1 --- upper arm (shoulder J1 → elbow J2)         21 cm (\~8.3 in)

  L2 --- forearm (elbow J2 → wrist J3/J4)           21.5 cm (\~8.5 in)

  L3 --- wrist-to-gripper-tip                       14 cm (\~5.5 in)

  Max reach (fully extended, horizontal)            60.5 cm calculated / 59 cm measured actual (\~1.5cm difference consistent with real joint-pivot stackup)
  ------------------------------------------------------------------------------------------------------------------------------------------------------------

11.7 Wheelchair-Handoff Use Case

Willy is intended as a fetch-and-deliver helper for a wheelchair-using family member. Target handoff height \~24--30 in (lap/armrest/tray zone for a seated user).

-   Priority: predictable, boring reliability over cleverness --- fixed/known pickup zones and a known object set, not open-ended \"pick up anything, anywhere.\"

-   Handoff pose is a hardcoded fixed pose (§11.8) rather than a fresh IK solution computed on every delivery.

-   Safety: an instant, top-priority STOP (voice command overriding any in-progress motion, ideally plus a physical stop within reach) is a requirement given the proximity to a mobility-limited user.

-   Design tension to balance in software: reliability-first fixed poses vs. leveraging the AI stack\'s adaptability where it genuinely helps handle real-world variation (owner-stated principle, 2026-07-24) --- not yet resolved, to be worked out as the software architecture develops.

11.8 Handoff Pose --- FINAL (owner-specified, 2026-07-31)

Arm fully extended (elbow straight, J2 at its zero/straight position --- not bent), shoulder (J1a/J1b) pitched at a 15° tilt.

  ---------------------------------------------------------------------------------------------------------------------
  **Joint**                           **Handoff pose**
  ----------------------------------- ---------------------------------------------------------------------------------
  J0 base yaw                         per delivery target --- not fixed by this pose

  J1a / J1b shoulder                  15° tilt (mirrored pair, per §11.4 J1b = 2×1500µs − J1a convention once zeroed)

  J2 elbow                            straight / fully extended (0° relative bend)

  J3 wrist rotate                     not yet specified --- hold neutral until decided

  J4 wrist pitch                      not yet specified --- hold neutral until decided

  J5 gripper                          open, until grasp
  ---------------------------------------------------------------------------------------------------------------------

**NOTE:** This is a geometric pose, not yet servo pulse-width values --- translating it into arm.py requires the same joint-zero calibration step already called out in §20.6 (the shoulder\'s 0°/tilt reference and the elbow\'s \"straight\" pulse width are per-unit and not yet bench-set). Once §20.6 is run, record the resulting µs values for J1a/J1b and J2 here and in arm.py\'s handoff-pose constant. Fully extended at only a 15° shoulder tilt puts the gripper close to the arm\'s maximum reach (§11.6: 60.5cm calculated / 59cm measured) at a shallow angle --- worth a bench dry-run against the target 24--30in handoff zone once J0/wrist values are picked, since a shallow tilt on a nearly-fully-extended arm is a small angle change away from either overshooting or undershooting that zone.

12\. Communications Architecture

All processing is local/offline. I²C (GP2/GP3) links both PCA9685 boards, the MCP23017, BNO085, and the three INA260 current sensors, with an LTC4311 active pull-up at the far end of the run, 100 kHz bus speed. SPI (GP8--11) for the MCP3008. Wi-Fi is used only for remote administration (Cockpit, port 9090) and is not required for any onboard function --- see §13, local-first design.

13\. Software Architecture

13.1 Codebase

/home/hhimmel/rover/: config.py, motors.py, sensors.py, brain.py, display.py, claude_client.py, arm.py, main.py, willy-rover.service (systemd, 500ms watchdog). States: INIT / IDLE / ACTIVE / SAFE_MODE. motors.py is being rewritten to drive the FeatherWings via the Adafruit MotorKit library (I²C) rather than the GPIO-PWM approach an earlier hardware design assumed.

Claude Code v2.1.215 (native) is installed and authenticated on Willy directly (\~/.local/bin/claude, user hhimmel), on Python 3.13.5 / Debian trixie. The rover code is under local git (branch main, .gitignore protects .env). GitHub push is currently parked on a token permission-scope issue (non-blocking --- commits are safe locally; fix is a classic repo-scope token or broader fine-grained-token permissions). A personal access token was briefly exposed in an external chat during setup and was revoked/replaced --- tokens should only ever be pasted at the on-device gh prompt, never into chat.

13.2 Software Control-Priority / Arbitration (proposed --- adopt or adjust)

  -----------------------------------------------------------------------------------------------
  **Priority**      **Source**                 **Can command**         **Override rule**
  ----------------- -------------------------- ----------------------- --------------------------
  1                 E-stop / hardware safety   all motion OFF          hard override, latched

  2                 watchdog / SAFE_MODE       stop motion, park arm   overrides autonomy

  3                 low-battery manager        return-home / degrade   overrides mission

  4                 autonomy                   drive, steer, arm       normal control

  5                 manual / admin             restricted controls     blocked in safety states
  -----------------------------------------------------------------------------------------------

Battery-threshold transitions (one-way toward safer states until voltage recovers above the next threshold + 0.2V hysteresis): 11.4V → warn; 10.8V → return-to-home; 10.5V → SAFE_MODE (motion stop, arm park); 10.2V → controlled shutdown.

Platform constraints shaping software design: no depth sensor (3D position from known-object-size + sonar, not a range camera); the front SLAM camera is rolling-shutter and vibration-sensitive, so navigation leans more on odometry (encoders + IMU + sonar) than vision; and the Pi/Hailo do inference only --- all model training happens off-board on a PC.

13.3 Capability Roadmap --- Post-Build Teaching

Capabilities arrive in layers, not all at once: (1) config/tuning --- most out-of-the-box behavior (sonar avoidance, steering modes, arm IK, the wakeword→whisper→Llama→Piper voice loop) is parameter tuning; (2) custom object training --- teaching a new object is a PC-side fine-tune, \~1--2 weeks per capability, compiled to the Hailo-8, since the rover runs inference only; (3) behavior sequencing --- chaining perception + navigation + arm into a task via a behavior tree/state machine; (4) experiential learning (RL/imitation) --- research-grade, optional, needs a simulator.

Worked example (\"find the dog toys, put them in the basket\"): train on \~200--300 rover-camera images → detect & announce (Piper) → approach (drive toward the detection, range estimated from known object size + sonar, since there is no depth sensor) → grab (position the whole rover to set range, since the arm reaches a fixed arc; pitch shoulder down; close gripper) → deliver (navigate to the basket, position, release) → loop until no toys detected or N failed attempts. A 5-step chain at 90% per step is only \~59% end-to-end --- each stage should be built and tuned to a demoable milestone independently, with per-stage retry/abort, before chaining.

13.4 Persistence & Network Memory (WD My Cloud)

Principle: local-first, network-synced, never network-dependent --- a dropped WiFi connection must never block the robot. Three memory types: (1) local SSD = working memory (models, media, captures --- large, occasional writes); (2) SQLite on the SSD = spatial/semantic memory (object sightings, room map, AprilTag anchors --- live source of truth, fast lookup); (3) operational logs/telemetry (high-volume, append-only). Sync: Pi-side scheduled rsync to an SMB/NFS share on a WD My Cloud, soft-mounted with a timeout so a missing NAS can never hang the Pi --- models pulled at boot, captures pushed for off-board retraining. LAN-only, SMB2/3 only (not SMB1), dedicated share user, credentials in a 0600 file (never in source). Optional: MQTT telemetry to InfluxDB/Grafana for history/graphs, kept separate from the file-sync path.

14\. Safety Architecture

Layered: 30A ATC main fuse, per-rail branch fuses, dual per-pack BMS, FQP27P06 reverse-polarity FET, P6KE15A TVS, and a physical latching E-stop (NC mushroom) cutting the 12V bus --- INSTALLED (2026-07-31); functional test pending as part of first-power-on commissioning (§21.1). 500ms software watchdog → SAFE_MODE. Switch 2 provides a separate Pi-only cutoff (§6.6).

14.1 Hazard Response Matrix

  ---------------------------------------------------------------------------------------------------------------------------------
  **Fault**                  **Detection**               **Immediate response**                   **Recovery**
  -------------------------- --------------------------- ---------------------------------------- ---------------------------------
  Pi undervoltage            INA260 0x44                 stop drive + arm, enter SAFE_MODE        manual reset after power stable

  IMU missing                I²C timeout (0x4A)          disable autonomy, allow limited manual   restore sensor, restart node

  Encoder failure            no counts while commanded   stop affected drive mode                 diagnose hardware

  Servo-rail overcurrent     INA260 0x40 threshold       freeze arm/steering outputs              cool-down + inspect

  Motor-rail overcurrent     INA260 0x45 threshold       stop drive, SAFE_MODE                    inspect for stall/jam

  E-stop pressed             hardware (latching NC)      cut 12V motion bus                       latch until manual reset

  Battery critical (10.2V)   MCP3008 CH7                 controlled shutdown                      recharge / swap packs
  ---------------------------------------------------------------------------------------------------------------------------------

14.2 Command-Loss & Fail-Safe Behavior

  ---------------------------------------------------------------------------------------------------------------------
  **Condition**                   **Detection**                          **Default state**
  ------------------------------- -------------------------------------- ----------------------------------------------
  Software command-link timeout   no valid command in 500ms (watchdog)   motors disable, enter SAFE_MODE

  Controller / process crash      systemd watchdog                       motors disable, arm holds position

  Startup interlock               firmware INIT gate                     no motion until INIT→IDLE self-test passes

  E-stop pressed                  hardware latching NC                   12V motion bus cut; latch until manual reset

  Low-voltage shutdown            MCP3008 CH7 \< 10.2V                   controlled shutdown, park arm
  ---------------------------------------------------------------------------------------------------------------------

Default motor state is DISABLED --- motion requires an active, valid command; loss of command always fails to stop, never to run.

15\. Wiring Standards

15.1 Connector Selection

  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Connector**                  **\~Cycles**            **Retention / practice**
  ------------------------------ ----------------------- -----------------------------------------------------------------------------------------------------------------
  Dupont 2.54 (F)                10--30                  Low retention --- strain-relieve; a removable dab of hot glue on the shell is recommended for critical signals.

  JST-PH (motors)                \~30                    Latching, good retention. Verify pin-1; do not force.

  JST-XH (battery/balance)       \~30                    Latching. Match pin count (3S = 4-pin).

  Screw terminal (dist boards)   effectively ∞           Best retention. Re-torque after the first heat cycles.

  USB (rear camera/SSD)          \~1500                  Robust electrically; strain-relieve at the pod so the plug can\'t wiggle.

  CSI / DSI FFC                  10--20                  Fragile latch. Minimize reseating; seat fully, close the latch squarely.
  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------

15.2 Cable Labeling Convention

Every cable carries its harness-schedule ID (§16) and is labeled at both ends within \~15mm of the connector. IDs are grouped by domain: P1--P7 power, R1--R4 rails, B1--B5 control/bus, M1--M6 motors, S1--S13 servos, N1--N6 sensors, V1--V3 vision, G1 ground. Mark the source end with an arrow toward the load.

15.3 Gauge & Ground Notes (as-built)

Power rails: 16 AWG (good for \~10--13A; covers the 12V motor rail\'s \~6--9A and all lighter rails). Signal/logic (I²C, GPIO, sonar): 22--26 AWG. Servo V+/GND jumpers ≥22 AWG. Intentional exception: the 12V leg at the INA screw terminal is 18 AWG solid (a properly-seated 18 AWG clamps better than a splayed 16 AWG at that terminal size) --- acceptable for its current, but solid-core fatigues under vibration at the clamp, so keep it short, anchored, with a small strain-relief loop.

16\. Harness Schedule

Condensed final schedule by domain. All items below are built and landed unless noted; the only remaining physical harness work is the four connection points in §0.2.

16.1 Power (12V domain)

  ------------------------------------------------------------------------------------------------------------------------
  **ID**                  **From → To**                                                            **Gauge**
  ----------------------- ------------------------------------------------------------------------ -----------------------
  P1                      2× 3S 8000mAh packs → parallel (hard-paralleled, through per-pack BMS)   12--14 AWG

  P2                      Battery+ → 30A ATC → KCD4 → Q1 FET → +12V bus                            12 AWG

  P3                      +12V bus → F2 → INA260 0x45 → 2× FeatherWing VIN                         16 AWG

  P4                      +12V bus → F3 → DROK buck IN (Pi rail)                                   16 AWG

  P5                      +12V bus → F4 → FEICHAO UBEC IN                                          16 AWG

  P6                      +12V bus → F5 → DZS buck IN (arm rail)                                   16 AWG

  P7                      Charge paraboard → battery side of KCD4 (+ balance leads)                14 AWG
  ------------------------------------------------------------------------------------------------------------------------

16.2 5V / 6V / 3V3 Rails

  --------------------------------------------------------------------------------------------------------------
  **ID**                  **From → To**                                                  **Gauge**
  ----------------------- -------------------------------------------------------------- -----------------------
  R1                      DROK 5.1V → Pi header pins 2 & 4 (GND 6 & 9)                   20 AWG

  R2                      FEICHAO 5V → INA260 0x40 → servo/steering distribution board   16 AWG

  R3                      DZS 6V → arm distribution board                                16 AWG

  R4                      Pi 3V3 (hub) → encoder distribution + all I²C VCC              22 AWG
  --------------------------------------------------------------------------------------------------------------

16.3 Control / Bus

  -------------------------------------------------------------------------------------------------------------------------------------
  **ID**                  **From → To**                                      **Note**
  ----------------------- -------------------------------------------------- ----------------------------------------------------------
  B1                      Pi 40-pin → Nano HAT Hacker (1:1 passthrough)      the last of the 4 remaining connections (§0.2)

  B2                      I²C SDA/SCL (GP2/3) → bus node board → 9 devices   via §5.6 bus node board

  B3                      GP7 (SPICE1)                                       FREED --- was TB6612 STBY, FeatherWings have no STBY pin

  B4                      12 motor-direction lines                           FREED --- direction is internal to each FeatherWing

  B5                      6 motor PWM lines                                  FREED --- PWM is internal to each FeatherWing
  -------------------------------------------------------------------------------------------------------------------------------------

16.4 Motors, Servos, Sensors, Vision, Ground

  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Group**                           **Summary**
  ----------------------------------- ---------------------------------------------------------------------------------------------------------------------------------
  Motors ×6                           PH2.0 6-pin → Dupont fan-out: Red/Black → FeatherWing, Blue/Green → encoder 3.3V dist, Yellow/White → MCP23017. COMPLETE.

  Steering ×6                         Signal → PCA9685 0x42 CH0--5; V+/GND direct to 5V rail. COMPLETE.

  Arm servos ×7                       Signal → PCA9685 0x43 CH0--6 (bulkhead connector); V+/GND direct to 6V rail. Bulkhead built; final landing pending (§0.2/§0.3).

  Sonar ×3                            4-wire (VCC/TRIG/ECHO via divider/GND), two-part plugs. Base side COMPLETE; top join pending (§0.2).

  IMU                                 6-wire: 3V3/GND/SDA/SCL + INT→GP15 + RST→MCP23017. COMPLETE.

  Vision/display                      CSI FFC (front cam), USB (rear cam), DSI ribbon + separate 3-pin GPIO power (display). COMPLETE.

  Ground                              All converter −, board GND, sensor GND → single-point star. COMPLETE.
  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------

17\. Interface Control Document

17.1 Physical Pin Assignment --- Pi 40-pin Header (final)

This replaces the GPIO-based motor-direction pinout used throughout earlier drafts --- those 12 direction pins (GP17/18, 27/22, 23/24, 25/12, 16/20, 19/6) and GP7 (STBY) are now freed; motor control is entirely I²C via the two FeatherWings (§9).

  -----------------------------------------------------------------------------------------------------------------------------
  **Pin**                                        **BCM/func**                       **Connects to**
  ---------------------------------------------- ---------------------------------- -------------------------------------------
  1                                              3V3                                3V3 rail → all I²C VCC + encoder VCC dist

  2 / 4                                          5V (IN)                            Pi power in, from DROK buck

  3                                              GP2 SDA                            I²C bus (all 9 devices)

  5                                              GP3 SCL                            I²C bus (all 9 devices)

  6 / 9                                          GND                                Pi power return / common

  7                                              GP4                                Sonar RIGHT TRIG

  8                                              GP14                               Sonar LEFT ECHO (÷)

  10                                             GP15                               BNO085 INT

  19 / 21 / 23 / 24                              GP10/9/11/8 (MOSI/MISO/SCLK/CE0)   MCP3008 SPI (DIN/DOUT/CLK/CS)

  29                                             GP5                                Sonar FRONT TRIG

  33                                             GP13                               Sonar LEFT TRIG

  37                                             GP26                               Sonar FRONT ECHO (÷)

  40                                             GP21                               Sonar RIGHT ECHO (÷)

  27 / 28                                        GP0/GP1 (ID_SD/ID_SC)              RESERVED --- AI HAT+ EEPROM, leave alone

  GP7, and the 12 former motor-direction GPIOs   ---                                FREED (motor control is I²C-only, §9)
  -----------------------------------------------------------------------------------------------------------------------------

17.2 I²C Bus Fan-out & Pull-ups

The Nano HAT Hacker exposes GP2/GP3 as one pin each, but 9 devices need each signal --- a bus node board (§5.6) fans SDA, SCL, 3V3, and GND out into four rails that every device taps in parallel (address sorts the devices; tap order doesn\'t matter). Required 4.7kΩ pull-ups from SDA→3V3 and SCL→3V3, placed once on the rail. Caution: several breakouts carry their own onboard pull-ups --- 9 boards\' worth in parallel can drop the effective pull-up well below the target \~1.5--3kΩ; measure and remove redundant onboard pull-ups if the bus runs slow or unreliable, keeping one 4.7k pair plus the LTC4311. Bus speed: 100kHz (i2c_arm_baudrate=100000) --- do not run 400kHz with this many devices on a long rail.

Address-strap collision check before power: the two PCA9685 boards (0x42/0x43) and the three INA260 boards (0x40/0x44/0x45) are identical hardware apart from their address straps --- verify each strap before connecting, or two devices collide silently and the bus fails.

17.3 Device Power / Signal / Ground Summary

  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Device**             **Power**                              **Signal**                                    **Ground / note**
  ---------------------- -------------------------------------- --------------------------------------------- ------------------------------------------------------------------------
  Pi 5 + AI HAT+         5V from DROK, header pins 2 & 4        ---                                           GND pins 6 & 9. AI HAT+ via PCIe FFC, not via USB-C.

  DROK 12A buck          12V in via F3                          ---                                           5V out → Pi. USB-A port is charge-only. Set 5.0--5.1V off-load first.

  FEICHAO UBEC 8A        12V in via F4                          ---                                           5V out → servo/steering rail → INA260 0x40.

  DZS 12A buck           12V in via F5                          ---                                           6V out → arm distribution → all 7 arm servos. Set 6.0V off-load first.

  6× JGA25 motors        12V switched via FeatherWing outputs   driven by FeatherWing internal driver         GND → common trunk. 6-wire: 2 power + 4 encoder.

  6× DS041MG steering    5V direct from distribution (V+/GND)   PCA9685 0x42 CH0--5 (signal only)             ref-GND to star.

  7× arm servos          6V direct from distribution (V+/GND)   PCA9685 0x43 CH0--6 (signal only)             ref-GND to star. Bulkhead-connectorized.

  3× HC-SR04 sonar       5V rail                                TRIG = GPIO out; ECHO = GPIO in via divider   GND. 4-pin two-part plug.

  BNO085 IMU             3V3                                    I²C 0x4A; INT→GP15; RST→MCP23017              GND. 0.1\" header + 6 F-F jumpers.

  3× INA260              3V3 logic                              I²C 0x40/0x44/0x45                            VIN+/VIN− inline on each rail (series, not a tap).

  MCP3008 ADC            3V3                                    SPI → Pi                                      battery divider on CH7 (§8.4).

  6× encoders            3.3V via distribution board            A/B → MCP23017 0x27                           Blue=VCC, Green=GND (meter --- batch swap risk).

  2× FeatherWing #2927   VM = 12V via F2; logic 3.3V            I²C 0x60/0x61; MotorKit                       GND → common trunk. No STBY, no dir GPIO.
  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

18\. Bill of Materials

Cleaned of the broken =COUNTIF() formula placeholders left over from the spreadsheet export, and reconciled to the final address/architecture facts throughout this document. Statuses: ON HAND · ORDERED · VERIFY · OPTIONAL · NOT USED · SPARE · BUILT.

18.1 Compute / Pi5 Face

  -----------------------------------------------------------------------------------------------------------------------------------------------
  **Component**                   **Spec / role**                                                             **Qty**           **Status**
  ------------------------------- --------------------------------------------------------------------------- ----------------- -----------------
  Raspberry Pi 5 (8GB)            Main brain --- REPLACED once (§7.5); current unit bench-confirmed healthy   1                 ON HAND

  Raspberry Pi AI HAT+ (Hailo)    On-device vision/voice NPU, 26 TOPS, PCIe                                   1                 ON HAND

  5\" DSI touch display           Face / UI 800×480                                                           1                 ON HAND

  Arducam IMX708 (CSI)            Front camera --- SLAM + fwd YOLO                                            1                 ON HAND

  OV9782 (USB)                    Rear camera --- YOLO/monitoring + descent                                   1                 ON HAND

  ReSpeaker USB mic + speaker     Voice I/O --- confirmed connected                                           1                 ON HAND

  Pimoroni Nano HAT Hacker        GPIO breakout, replaces original ZDE-type board                             1                 ON HAND

  Raspberry Pi Active Cooler      Pi 5 blower + heatsink                                                      1                 ON HAND

  5V case fan 30--40mm            Pi5 Face exhaust                                                            1                 ON HAND

  SanDisk Extreme PRO SSD 500GB   Primary boot drive (USB-boot order still pending)                           1                 ON HAND
  -----------------------------------------------------------------------------------------------------------------------------------------------

18.2 Drive & Steering

  ----------------------------------------------------------------------------------------------------------------------------------------------
  **Component**                                   **Spec / role**                                         **Qty**           **Status**
  ----------------------------------------------- ------------------------------------------------------- ----------------- --------------------
  JGA25-370B gearmotor + encoder                  12V 620RPM, drive wheels                                6                 ON HAND --- landed

  Adafruit FeatherWing #2927 (I²C motor driver)   Supersedes discrete TB6612FNG; 0x60 LEFT / 0x61 RIGHT   2                 ON HAND --- landed

  GDW DS041MG steering servo                      180°, coreless digital --- PCA9685 0x42                 6                 ON HAND --- landed
  ----------------------------------------------------------------------------------------------------------------------------------------------

18.3 Robotic Arm

  --------------------------------------------------------------------------------------------------------------------------------------------
  **Component**                       **Spec / role**                                                  **Qty**           **Status**
  ----------------------------------- ---------------------------------------------------------------- ----------------- ---------------------
  MG996R metal-gear servo             J0 base, J1a/J1b shoulder, J2 elbow @ 6V                         4                 ON HAND --- mounted

  MG90S micro servo                   J3 wrist rotate, J4 wrist pitch, J5 gripper @ 6V                 3                 ON HAND --- mounted

  Arm STL --- MakerWorld 1134925      Standalone 6-axis arm, adapted to WildWilly turret (PETG+PLA+)   print             CHOSEN / printed

  Bearings --- 608 + 6203 ×2          Arm joint bearings per source model                              3                 VERIFY

  M8 60mm bolt + anti-loosening nut   Arm pivot hardware                                               2                 VERIFY

  Arm servo bulkhead connector        7-lead detachable harness connector                              1                 BUILT

  Braided split wire sleeve           Arm servo harness bundling/protection                            1                 ORDERED
  --------------------------------------------------------------------------------------------------------------------------------------------

18.4 Servo Control & Power

  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Component**                                                           **Spec / role**                                                                                                                                                                                                                                                **Qty**           **Status**
  ----------------------------------------------------------------------- -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- ----------------- ---------------------------------
  PCA9685 16-ch PWM driver                                                0x42 steering, 0x43 arm --- CURRENTLY FAULTY, see §0.3                                                                                                                                                                                                         2                 REPLACEMENT ORDERED

  DZS Elec 12A adjustable buck                                            12V→6.0V arm rail (all 7 arm servos)                                                                                                                                                                                                                           1                 ON HAND --- installed

  DROK 12A LCD buck (CC/CV)                                               12V→5.1V Pi rail                                                                                                                                                                                                                                               1                 ON HAND --- installed

  FEICHAO 8A UBEC                                                         12V→5V servo/steering rail                                                                                                                                                                                                                                     1                 ON HAND --- installed

  470µF 25V low-ESR cap                                                   Buck output surge buffer                                                                                                                                                                                                                                       3                 ON HAND

  1000µF 16V electrolytic (Chenxing/Throzzik, 10×16mm)                    PCA9685 0x42 (steering) V+ decoupling --- solder to unpopulated \"C2\" pad; Adafruit ships the board without this cap installed. Use 1 of 15 on hand.                                                                                                          1 of 15           ON HAND

  Rubycon 2200µF 16V 12.5×20mm low-ESR (0.041Ω) electrolytic, pack of 7   PCA9685 0x43 (arm) V+ decoupling --- single can on the \"C2\" pad, preferred over the interim two-cap workaround. Verify lead spacing fits the pad before soldering.                                                                                           1 of 7            ORDERED --- arriving 2026-08-01

  1000µF 16V electrolytic ×2 (\~2000µF combined) --- interim only         PCA9685 0x43 (arm) V+ decoupling, interim if landing before 08-01: one cap on the \"C2\" pad (fits one can only), second cap wired externally to the V+/GND screw terminal with short leads, same net. Superseded by the single Rubycon can once it arrives.   2 of 15           ON HAND --- interim
  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

18.5 Power System

  -------------------------------------------------------------------------------------------------------------------------------------------------
  **Component**                                        **Spec / role**                                   **Qty**           **Status**
  ---------------------------------------------------- ------------------------------------------------- ----------------- ------------------------
  3S LiPo 8000mAh                                      Two packs, hard-paralleled \~16Ah \@11.1V         2                 ON HAND --- installed

  3S BMS 40--60A w/ balance                            One per pack, before parallel junction            2                 per §6.2

  7-port distribution/ground block                     Single-point GND star                             1                 ON HAND --- installed

  FQP27P06 P-FET (Q1)                                  Reverse-polarity, bench-confirmed from photo      1                 BUILT

  P6KE15A TVS diode (D1)                               Transient suppression                             1                 ON HAND

  30A ATC main fuse + holder                           F1, off-board                                     1                 BUILT

  Branch fuses F2--F6                                  10A/5A/10A/10A/10A per §6.4                       5                 BUILT

  Physical E-stop (latching mushroom)                  Cuts 12V bus --- REQUIRED before autonomy         1                 INSTALLED (2026-07-31)

  Switch 2 (Pi-cutoff)                                 DROK input line                                   1                 BUILT

  Shrouded EC5 charge bulkhead + JST-XH balance ext.   Charge-in-place access point                      1                 INSTALLED

  2×3S paraboard                                       Combines both packs\' balance taps for charging   1                 per §6.8

  iMAX B6 80W balance charger                          External charger for charge-in-place              1                 ON HAND
  -------------------------------------------------------------------------------------------------------------------------------------------------

18.6 Sensing

  ---------------------------------------------------------------------------------------------------------------------------------------------------------
  **Component**                           **Spec / role**                                                         **Qty**           **Status**
  --------------------------------------- ----------------------------------------------------------------------- ----------------- -----------------------
  BNO085 9-DoF IMU                        Replaces earlier MPU-6050 plan --- I²C 0x4A                             1                 ON HAND --- landed

  HC-SR04 sonar                           Front/left/right --- no rear sonar                                      3                 ON HAND --- landed

  MCP3008 ADC (SPI)                       CH7 battery sense, with divider fix (§8.4)                              1                 ON HAND --- landed

  Sonar divider resistors 3×1k + 3×2k     ECHO dividers                                                           6                 ON HAND

  CH7 battery divider: 2×10kΩ + 1×4.7kΩ   Added 2026-07-27 (§8.4)                                                 3                 ON HAND --- installed

  INA260 current sensor                   Servo 0x40, Pi 0x44, motor 0x45 --- 3rd unit replaced a faulty INA219   3                 ON HAND --- landed

  MCP23017 I/O expander                   Encoder GPIO --- bench address 0x27                                     1                 ON HAND --- landed

  LTC4311 I²C extender                    Bus reliability, far end of run                                         1                 ON HAND --- landed

  4.7k I²C pull-ups                       On the bus node board                                                   2                 ON HAND --- installed
  ---------------------------------------------------------------------------------------------------------------------------------------------------------

18.7 Connectors, Consumables, Tools

  ------------------------------------------------------------------------------------------------------------
  **Component**                       **Spec / role**                   **Qty**           **Status**
  ----------------------------------- --------------------------------- ----------------- --------------------
  JST-PH 6-pin pigtail                Motor connectors                  6                 ON HAND --- landed

  EC5 connectors + parallel harness   Battery / power                   1                 ON HAND

  M3 stainless bolt/nut assortment    Servo mounts + joints + chassis   1 kit             ON HAND

  PLA+ filament 1.75mm                Arm segments / brackets           as needed         ON HAND

  PETG filament 1.75mm                Chassis + load-bearing parts      as needed         VERIFY

  TPU 95A filament                    Wheel treads                      as needed         VERIFY

  IMAX B6 balance charger             LiPo charge/discharge             1                 ON HAND

  4mm flange coupling                 Motor shaft fittings              4                 ON HAND
  ------------------------------------------------------------------------------------------------------------

19\. Assembly Procedures

Status: assembly is substantially complete. What follows is the procedure as executed; §0.2 lists the only remaining physical connections.

19.1 Sequence (as executed)

-   1\. Frame & suspension --- print widened two-level frame (PETG, mirrored parts confirmed), assemble rocker-bogie differential, mount 6 motors, fit 6 wheels. DONE.

-   2\. Lower level / power --- mount power tray, seat both battery packs (voltage-matched, EC5-paralleled through per-pack BMS), land grounds on the distribution block, fit the EPLZON fuse board (FET, TVS, gate resistor, all 5 fuses). DONE.

-   3\. Upper level / control --- mount controller tray (Nano HAT Hacker, 2× FeatherWing, 2× PCA9685, MCP23017, BNO085, LTC4311, pull-ups) and sensor EPLZON (MCP3008, sonar dividers, CH7 divider). DONE.

-   4\. Controller-tray harness (in situ, deepest boards first): board power/GND → I²C bus → FeatherWing control → signal returns → servo signals → 40-pin ribbon to the Pi LAST. DONE except the final ribbon connection (§0.2).

-   5\. Pi5 Face --- stack Pi 5 + Active Cooler + AI HAT+; connect front camera (CSI), rear camera (USB), display (DSI + 3-pin power); feed 5V into the Pi5 Face junction. DONE except the final power/ribbon connections (§0.2).

-   6\. Arm --- mount J0 turret, fit all 7 servos, route harness, confirm stow pose clears the camera sightline through full motion. Mechanically DONE; electrical landing pending (§0.2/§0.3).

-   7\. Harness --- build every harness per §16, label both ends, strain-relieve. DONE.

-   8\. Final ribbon + power-up --- connect the 40-pin ribbon last, then run the commissioning gates (§21). PENDING --- blocked on §0.3.

19.2 Threadlocker & Adhesive Reference

  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Product**                                   **Where**                                                **Caution**
  --------------------------------------------- -------------------------------------------------------- -------------------------------------------------------------------------------------------------------------------
  Loctite 243 (blue, medium)                    Metal-to-metal: motor mounts, brackets, bearing blocks   NOT on plastic threads (can craze PLA/PETG). Full cure 24h.

  Nylon-insert lock nut / nylon-patch screw     Fasteners into printed plastic or heat-set inserts       Use instead of threadlocker on plastic.

  Heat-set brass inserts                        Printed bosses needing repeatable metal threads          Install with iron \~200°C, square.

  RTV silicone                                  Cable anchoring, strain-relief                           Semi-removable.

  Hot glue                                      Removable connector retention (Dupont shells)            Not a structural bond.

  FET insulator (nylon washer + silicone pad)   Q1 FQP27P06 mounting                                     Stays dry --- no extra thermal paste. Do NOT threadlock the nylon screw. Verify tab↔heatsink OPEN after assembly.
  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

19.3 Maintenance Disassembly Points

By design, the build separates into top (Pi, head, sensors, arm) and base (chassis, motors, steering, power) at exactly four connectors --- see §0.2. This was a deliberate choice given how often this build has needed internal access (Pi replacement, EPLZON rework, INA swap, rail redistribution): future maintenance is a 4-connector disconnect, not a desoldering job.

20\. Calibration Procedures

20.1 Power (do first, before connecting the Pi)

**NOTE:** Pre-set every buck pot OFF-LOAD first --- bench the converter alone, adjust to target, then wire it into the circuit. Never adjust a converter pot while it feeds a live load (§6.7 --- this is exactly how the DZS buck was destroyed previously).

-   DROK 12A buck → 5.0--5.1V measured at the output, Pi disconnected. Wire to the Pi5 Face junction only after confirming.

-   FEICHAO UBEC → confirm 5.0V servo rail under no load.

-   DZS 12A buck → confirm 6.0V arm rail under no load (all 7 arm servos share this rail).

20.2 I²C Landing Order (as-built, final address map)

Board-by-board bring-up order used successfully on the replacement Pi, each verified before the next: MCP23017 (0x27) → INA260 servo (0x40) → PCA9685 steering (0x42) → PCA9685 arm (0x43) → INA260 Pi (0x44) → INA260 motor (0x45) → LTC4311 (no address) → BNO085 (0x4A) → 2× FeatherWing (0x60/0x61) → MCP3008 (SPI, not I²C).

Gotcha: the three INA260 boards are physically identical --- only the address strap and which rail they sit inline on distinguishes them. If two are swapped, roll-call still looks complete (all three addresses present) but the current readings are crossed. Confirm each strap before landing.

20.3 Current Sensors

Zero-offset each INA260 (0x40 servo, 0x44 Pi, 0x45 motor) at no load in firmware; record the offsets in config.py.

20.4 Battery Sensing

Read MCP3008 CH7 against a known battery voltage on a meter; trim the divider scale factor in config.py so the reported voltage matches within 0.05V across 10.2--12.6V. Confirm the CH7 divider fix (§8.4) is in place before trusting any reading.

20.5 Steering

Center all 6 DS041MG (PCA9685 0x42, CH0--5) to 1500µs and record the neutral PWM per channel; set mechanical zero with wheels straight before mounting horns --- centering after horns are on makes software-zero not match mechanical-straight. Bench-test steering torque under load (C-8, §21) --- DS041MG is rated \~3.1 kg-cm \@5V.

20.6 Arm / IK

Set arm.py joint zeros using the measured link lengths (§11.6: base 4cm, L1 21cm, L2 21.5cm, L3 14cm) and the manufacturer-default pulse-width starting values (§11.5) as calibration seeds. IK is elbow-up (base yaw + shoulder + elbow position the wrist), 2-axis wrist orientation. Center both shoulder servos, drive J1b as the mirror of J1a; watch the arm-rail current sensor for sustained draw with no commanded motion (the pair fighting) and cut PWM if seen.

20.7 IMU

Mount the BNO085 level; run the SH-2 calibration; confirm INT (GP15) toggles on report-ready and RST (MCP23017 spare pin) resets cleanly.

21\. Validation and Test Plan

21.1 First-Power-On Commissioning Checklist

Single ordered runbook; work top to bottom, each gate must pass before the next. Status reflects the last logged state --- several gates need to be re-run now that the build is close to fully landed and the §0.3 PCA9685 fault has been isolated.

  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Gate**                **Action / pass criteria**                                                                                                                   **Status**
  ----------------------- -------------------------------------------------------------------------------------------------------------------------------------------- ------------------------------------------------------------------------------------------------------------------------------------------
  C-1                     Bench boards cleared --- power & sensor EPLZON meter-checked (FET orientation, tab↔heatsink open, TVS band, sonar dividers, MCP3008 rails)   PASS

  C-2                     All regulator rails set off-load then verified: DROK 5.0--5.1V, FEICHAO 5V, DZS 6V                                                           PASS (5.1V)

  C-3                     Junction polarity --- KCD4 on, Pi unplugged: 5V on header pins 2/4, GND on 6/9, not on any other pin                                         PASS (base-only staged power-up, 2026-07-30, all rails good)

  C-4                     I²C roll-call --- confirm all 9 devices + All-Call, none shorted                                                                             PASS (2026-08-01, with replacement PCA9685 boards) --- full clean roll-call: 0x27, 0x40, 0x42, 0x43, 0x44, 0x45, 0x4A, 0x60, 0x61, +0x70

  C-5                     Staged Pi power-up --- INA260 0x44 shows Pi rail ≥4.85V under boot load, no brownout                                                         PENDING --- awaits final ribbon connection (§0.2)

  C-6                     Post-boot I²C confirm --- i2cdetect shows the same 9 addresses                                                                               PENDING --- same blocker as C-5

  C-7                     FET temp under sustained load --- Q1 tab warm-not-hot at \~15A                                                                               PENDING (needs full load)

  C-8                     Steering torque check --- DS041MG turns each loaded wheel at 5V                                                                              PENDING (needs full assembly)
  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

21.2 Subsystem Dry Tests

Motors: each direction, low duty, confirm encoder counts. Steering: sweep each servo. Arm: move each joint through range at low speed, watch for collisions with the compute stack. Sonar: confirm front/left/right ranging (functional pulse-timing test still pending per §8.1). IMU: confirm tilt/heading.

21.3 Stall & Fuse Tests

-   Arm fuse (F5, 10A): stall all 4 MG996R simultaneously, measure peak current, confirm the fuse holds. (Raised from an earlier 5A for stall margin; re-verify given the arm now runs all 7 servos, not the earlier 3, off this rail.)

-   Motor fuse (F2, 10A): stall all 6 motors, confirm the fuse holds.

-   Pi-rail fuse (F6, 10A): run AI inference + SSD write + display + audio together, confirm the fuse holds and the DROK buck stays in spec.

21.4 Thermal

The DZS and DROK bucks sit on their heatsinks in the lower level, between the two LiPo packs, in a fairly enclosed bay. Two risks to check once under sustained load: heat soaking into the adjacent LiPo cells, and the buck heatsinks being thermally trapped with no vent path. Add a small fan or an insulating break between the buck heatsinks and the packs if the bay runs more than comfortably warm.

21.5 Mechanical / CG

Weigh each subsystem, replace the estimated CG values (§4.6 --- currently PENDING). Balance-test CG arm-stowed vs. deployed; confirm the widened body clears the wheels at full articulation.

21.6 Autonomy

End-to-end: wakeword → STT → reasoning → action; vision detection → obstacle avoidance; battery-threshold behaviors (warn / RTH / SAFE_MODE / shutdown); E-stop cuts motors + arm.

21.7 Thermal Acceptance (proposed pass/fail gate --- confirm against datasheets and measured ambient)

  ---------------------------------------------------------------------------------------------------------
  **Item**                      **Condition**                    **Pass limit**
  ----------------------------- -------------------------------- ------------------------------------------
  Motor drivers (FeatherWing)   sustained driving                case warm, \< 70°C

  DROK 12A buck (Pi, 5.1V)      peak compute+sensor+servo load   within rating, \< 70°C, no foldback

  DZS 12A buck (arm, 6V)        arm under load                   \< 70°C

  FQP27P06 FET                  sustained \~15A                  warm-not-hot, within SOA

  Battery (LiPo)                high-discharge run               \< 45°C surface

  Raspberry Pi 5                sustained AI inference           no thermal throttling

  Enclosed electronics bay      sustained operation              below component limits with body airflow
  ---------------------------------------------------------------------------------------------------------

22\. Maintenance Procedures

22.1 Before Each Run

Verify both packs within 0.05V/cell; check E-stop latches and releases; confirm no loose harness at the Pi connectors, especially the 4 maintenance-disassembly points (§0.2/§19.3).

22.2 Periodic

Re-torque arm and deck fasteners; inspect CSI/DSI/SSD strain relief; check FET and converter temps after load; clean camera lenses; verify wheel/bogie pivots are free.

22.3 Battery Care

Charge the two packs as a paralleled pair via the charge-in-place port (§6.8) so they stay matched; cycle them together so they age matched; never join a charged pack to a depleted one.

22.4 Software

Back up the SSD (OS + models + memory DB) periodically; keep config.py offsets current after any sensor change; version willy-rover.service config; push local git commits to GitHub once the token-scope issue (§13.1) is resolved.

23\. Risk Register

  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **ID**            **Risk**                                                            **Severity**      **Status / mitigation**
  ----------------- ------------------------------------------------------------------- ----------------- ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  R-01              Pi 5V rail brownout under AI load                                   MED               DROK 12A buck installed and confirmed at 5.1V; peak-load verification still pending final landing.

  R-02              Widening the frame reduces stair-climb margin                       LOW               Downgraded --- stair climbing is now a stretch goal (§2.1), not gating.

  R-03              Arm/camera collision through motion envelope                        MED               Verify full-envelope clearance, not just stow, once the arm is electrically landed.

  R-04              Parallel-pack surge if voltages unmatched                           HIGH              0.05V/cell rule; per-pack BMS added as a backstop (§6.2).

  R-05              Simultaneous motor/arm/steering stall trips fuses                   MED               RESOLVED for the arm: all 7 servos on one 12A-rated DZS buck with CC current limit, F5 10A ample. 5V rail (steering + sonar) is near its 8A UBEC rating --- monitor via INA260 0x40, stagger arm/steering moves in firmware.

  R-06              CG estimates wrong                                                  MED               Open --- mass-properties closure (§4.6) still pending measurement.

  R-07              Pi5 Face over-temp (Pi+AI HAT+ enclosed, capped by the arm above)   MED               Active cooler + Pi5 Face fan; confirm exhaust path clears the arm; thermal test pending (§21.7).

  R-08              Motor control mode undecided                                        RESOLVED          Fully I²C via 2× FeatherWing + MotorKit --- no external PWM/GPIO wiring.

  R-09              DZS buck internal short from a live pot adjustment                  RESOLVED          Root cause and fix in §6.7 --- pre-set every pot off-load, 220nF soft-start added, retested OK.

  R-10              Pi 5 I²C-1 hardware fault (bus node board power/data swap)          RESOLVED          Full incident and fix in §7.5 --- replacement Pi installed, root cause identified, standing meter-verify rule adopted.

  R-11              INA219 servo-rail intermittent fault                                RESOLVED          Swapped for a 3rd INA260 (§8.3); all rails confirmed healthy after.

  R-12              MCP3008 CH7 over-voltage exposure (no divider)                      RESOLVED          Standalone divider added (§8.4); CH7 verified safe.

  R-13              Both PCA9685 boards hanging the I²C bus (SDA stuck low)             RESOLVED          Replacement boards installed with V+ decoupling caps; full 9-device roll-call passed clean 2026-08-01 (§0.3).
  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

24\. Open Items

Consolidated and de-duplicated from the rev 5.80 \"Open Items\" section, the pending-task lists scattered through the later narrative entries, and the BOM VERIFY rows. Superseded/completed items from earlier drafts (e.g. the original 5-servo channel range, the discrete TB6612 driver design, the ZDE GPIO board) have been removed --- see §25 if that build history is needed.

24.1 Blocking further progress

-   Land the arm bulkhead to PCA9685 0x43 CH0--6 + 6V rail --- PCA9685 replacement resolved (§0.3), this is now unblocked.

-   Connect the final 40-pin ribbon, Pi power feed, and sonar top join (§0.2) --- then run commissioning gates C-5 through C-8 (§21.1).

24.2 Safety-critical, not yet confirmed

-   E-stop functional test --- installed (2026-07-31); run the actual latch/cut/release test as part of first-power-on commissioning (§21.1), not just visual install confirmation.

-   Confirm the charge-port inline fuse is installed (bulkhead and balance lead are confirmed installed).

24.3 Engineering-review gates

-   Mass properties & stability closure (§4.6) --- weigh subsystems, measure real CG arm-stowed/deployed, derive tip-over/speed/payload limits.

-   Thermal acceptance testing (§21.7) under sustained combined load.

-   Confirm Pi 5 boot order is set to USB (SSD), not microSD.

24.4 Software

-   Rewrite motors.py against Adafruit MotorKit for the FeatherWings (in progress per §13.1).

-   Resolve the GitHub push token-scope issue (non-blocking, local commits safe).

-   Implement steering kinematics (per-corner limits, crab/point-turn coordination) in config.py/motors.py.

-   Decide wrist rotate (J3) and wrist pitch (J4) angles to complete the handoff pose (§11.8) --- base yaw, elbow, and shoulder tilt are now specified.

-   Decide gripper finger-grip coating (may require a closed-jaw calibration re-cal once chosen).

24.5 Consumables / BOM verify

-   PETG and TPU filament --- confirm on hand or order.

-   Arm bearings (608 + 6203×2) and M8 pivot hardware --- confirm on hand.

25\. Revision History

Condensed changelog. Rev 5.80\'s \~80 dated micro-entries are grouped here by theme; the full line-by-line log is preserved in the rev 5.80 source file if the granular audit trail is ever needed.

  ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Rev range**           **Dates**               **Summary**
  ----------------------- ----------------------- ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  2.7 -- 3.9              2026-06-20 to 06-29     25-section baseline established; formal schematic set (7 sheets) added; requirements traceability, drive verification, command-loss/fail-safe, thermal gate, and mass-properties framework closed into the doc structure; fuse slot order confirmed.

  4.0 -- 4.2              06-29 to 07-03          DZS buck destroyed by a live pot adjustment, root-caused and fixed with a soft-start cap (R-09). Two-camera architecture adopted (front CSI SLAM+YOLO / rear USB monitoring); compute moved front-mounted (\"Pi5 Face\"), rear-pod concept dropped. Steering servos changed MG90S→GDW DS041MG.

  4.3 -- 4.14             07-03 to 07-08          First-power-on commissioning checklist (C-1...C-8) added. Arm architecture churned through several configurations (elbow removed, then restored) before landing on 6-DOF/7-servo. Harness schedule populated. Power distribution mapped to 5 rails / 5 boards.

  4.15 -- 4.27            07-08 to 07-10          BNO085 wiring finalized (0.1\" header + jumpers). Cable labeling and connector mating-cycle references added. As-built gauge/ground notes captured. PCA9685 V+ screw terminals confirmed unused (servo power external) --- later revisited and partially reversed, see §0.3. I²C physical fan-out and pull-up design documented.

  4.92 -- 4.99            07-18 to 07-19          Per-pack BMS design added; charge-in-place via iMAX B6 designed. Stair-climbing reclassified to a stretch goal. Claude Code installed on Willy. Extensive, repeated correction passes on the DROK/DZS buck assignment and INA/PCA9685 addressing after several rounds of the doc contradicting itself --- this rev (6.0) is the final resolution of that whole saga.

  5.00 -- 5.13            07-19 to 07-20          Schematic images redrawn to the FeatherWing architecture. GPIO expansion board replaced with the Pimoroni Nano HAT Hacker.

  5.13 -- 5.14            07-20                   Pi 5 I²C-1 hardware fault incident: full isolation testing, root cause (bus node board 3V3/GND swapped onto SDA/SCL), replacement Pi ordered and installed, standing meter-verify rule adopted. Incident closed 07-24 with a full 9-device roll-call.

  5.15 -- 5.20            07-20 to 07-24          Both rocker-bogie suspensions and full chassis assembled. Arm mechanically completed. Arm servo map confirmed as-built (7 servos, 4×MG996R+3×MG90S) --- resolved a long-standing doc conflict. Wheelchair-helper use case and design priorities documented.

  5.21                    07-24                   Authoritative servo channel map published: steering PCA9685 0x42 CH0-5, arm PCA9685 0x43 CH9-15 --- supersedes every earlier 0x40/0x41/CH11-14/CH6-8 reference in the document.

  5.22 -- 5.28            07-24                   MCP23017 address corrected to bench-confirmed 0x27 (was documented 0x20). Full 9-device I²C roll-call achieved for the first time on the replacement Pi, closing the hardware-fault incident arc.

  5.29 -- 5.33            07-26                   Arm link lengths physically measured (base 4/L1 21/L2 21.5/L3 14cm, max reach 60.5cm) --- supersedes all earlier reach figures. FeatherWing #2 brought onto the bus, completing all 9 devices simultaneously.

  5.34                    07-26                   Sensor interfaces (sonar GPIO, battery-voltage SPI) confirmed as-is --- no migration to I²C alternatives.

  5.35 -- 5.38            07-27                   Servo/INA219 rail voltage sag investigated and resolved by replacing the INA219 with a 3rd INA260 at 0x40.

  5.39 -- 5.43            07-27                   MCP3008 CH7 found wired directly to 12V with no divider (over-voltage exposure) --- root-caused to a genuine gap in the EPLZON\'s original design, fixed with a standalone 10k/3.2k divider.

  5.44 -- 5.51            07-28                   Final arm servo voltage decision: all 7 servos on the 6V rail (moved off a brief split-rail attempt the same day) after a 5V-rail load review showed steering+arm+sonar exceeding the UBEC rating. Sonar naming corrected: front/left/RIGHT, not front/left/rear --- no rear sonar exists.

  5.52 -- 5.65            07-28 to 07-29          6V rail rearranged for a 7th connection point. Drive motor and steering harnesses built, labeled, and landed. Sonar wiring completed on the base side. Arm bulkhead connector added for serviceability.

  5.66 -- 5.79            07-29 to 07-30          All drive motors and steering servos fully landed. Design rationale for keeping two PCA9685 boards recorded (not strictly required, kept for isolation/practicality). Shoulder servo physical-side orientation confirmed (J1a=RIGHT, J1b=LEFT). Charging interface installed. Switch 2 (Pi-cutoff) built, closing the full wiring audit.

  5.80                    07-30                   PCA9685 §0.3 incident opened (both boards found hanging the I²C bus, isolated to the boards themselves; replacements ordered). Late design note on simplifying servo power routing recorded for future reference.

  6.0                     2026-07-31              Full structural reorganization: single authoritative address/pin table (§5.2) replacing a dozen inconsistent restatements; every \"DESIGN ADDITION / INCIDENT / MILESTONE\" entry folded into its proper home section; M-006 reclassified to stretch in the traceability table; broken BOM spreadsheet formulas removed; new §0 Current Build Status added as the fastest entry point into where the build actually stands; revision history condensed from \~80 line items to this table; §2.1 functional-requirements list moved to the Functional Requirements Document, replaced with a reference; added manufacturer-sourced starting values for drive-encoder resolution (§9.2) and servo pulse-width calibration (§11.5) to unblock initial software bring-up --- flagged everywhere as starting points for bench calibration, not substitutes for it; wheelchair handoff pose specified (§11.8): fully extended, 15° shoulder tilt, elbow straight --- wrist angles still open; physical E-stop confirmed installed --- closes the last open safety-critical item ahead of PCA9685 replacement and first power-up.

  6.0.1                   2026-08-01              PCA9685 incident (§0.3/R-13) closed --- replacement boards installed, full 9-device I²C roll-call passed clean, commissioning gate C-4 marked PASS. Arm servo channel map on PCA9685 0x43 corrected to CH0--6 (was documented CH9--15 per the 5.21 map) --- as-built, the arm board starts its channel assignment at CH0, same base→gripper joint order (J0=CH0 \... J5=CH6). Updated throughout §3.1, §5.2, §11.1, §16.4, §17.3, §24.1.
  ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
