# Arm parts

The arm is the "Robotic Arm with Servo & Arduino" by Emre Kalem (MakerWorld, Standard Digital
File License). **The original STLs and anything made from them are not stored here**: that
licence does not allow sharing the files, and this repo is public. Download the originals
yourself, then run the script.

## `build_arm_ducts.py` (2026-10-14)

Adds wire ducts to the two arm links, starting from the original designs:

| Part | Original file | Output | Duct |
|---|---|---|---|
| Upper arm (`Alt_Kol` / `Arm A`) | `Arm.stl` | `Alt_Kol_duct18.stl` | 18 mm; both openings on the face with the elbow horn recess, ~46 mm from the shoulder pivot and ~50 mm from the elbow pivot. The I-beam face grooves are filled along the run, which gives 6 mm walls. |
| Forearm (`On_Kol` / `Arm B`) | `Arm B.stl` | `On_Kol_duct10_<L>.stl`, stretched to `FOREARM_PIVOT_MM` pivot to pivot (env var; cut through the plain middle of the tongue, filled with its own section; both ends unchanged). **220** = the arm on Willie now; **265** = for the NEW body (2026-10-15): the dome raises the shoulder to an estimated ~516 mm, where 220 cannot reach the floor; 265 reaches 220-345 mm from the base at 516 (220-415 at 480, 220-275 at 540) and its 297 mm part still fits a P1S bed diagonally. When fitted, set `ARM_L2_MM=265` and measure the new shoulder height. | 10 mm; in at the top ~36 mm from the wrist axle, out on the servo-flange side ~47 mm before the elbow hub. Side recesses filled along the run, giving 4.5 mm walls. Servo plugs come off and are re-crimped after threading. |

Both come out slightly lighter than the originals. `arm_ducts_check.png` shows where the
openings are. Input and output paths are set at the top of the script (`~/Downloads`).

Needs `trimesh` and `manifold3d`.

## Link lengths (pivot centre to pivot centre)

- Upper arm L1 = **200.1 mm** (hole line runs 10.9 deg off the part's long edge)
- Forearm L2 = **140.1 mm** original (elbow hub to wrist axle). **Too short:** with the shoulder 446 mm
  up, `arm_ik.solve` finds no pose reaching the floor past the front wheels (2026-10-14). Willie runs
  the 220 mm stretched forearm; the script now builds the ducted forearm at 220 mm (2026-10-14).
- Hand, wrist-pitch pivot to fingertip: 227 mm closed, 180 mm open

## `build_hand_camera_mount.py` (2026-10-14)

Hand back plate (`El.stl`, downloaded as `hand back.stl`) with a **two-piece case** for the
InnoMaker U20CAM-1080P hand camera (32 x 32 mm board, four 2.2 mm M2 holes, M12 lens, 1 m cable).
- `hand_back_camera.stl`: the plate with the case's back on its outer face -- a wall leaning to
  look past the **angled end** (the fingertip end) **20 deg down**, a rim the board sits in, a
  24 x 24 mm pocket for the parts on the board's back, and a **12 x 8 mm cable notch** (2026-10-16, owner: was a hole in the middle) open to the case's
  bottom (D-C) edge beside corner D -- seen from behind, just right of the bottom-left screw slot, through the
  back wall and the rim, so the cable lies in it.
- `hand_camera_cap.stl`: the front, 34.4 x 34.4 x 6 mm, with a 17 mm lens hole and corner bosses
  that clamp the board. Print face down.
- Four **M2 x 16** screws through cap, board and wall, nuts behind. The hole spacing is not in
  InnoMaker's manual, so all holes are slots covering 26-30 mm.
- Checked by the script: the cap clears the plate (1.7 mm), and a 4 mm screwdriver still reaches
  all six plate screws from above. Assumes the plate's top face (as downloaded) is the outside.
- Outputs go to `~/Downloads`; preview `hand_back_camera_preview.png`.

## `build_forearm_split.py` (2026-10-15)

Splits the ducted forearm into **two pieces joined with four M3 x 30 bolts and nuts** (owner), so it
fits the bed easily. Run after `build_arm_ducts.py` with the same `FOREARM_PIVOT_MM` (default 265).
- Half-lap joint, 44 mm long, in the plain middle of the tongue, split at the duct's centre height:
  the 10 mm duct is a half-channel in each piece (lay the wires in, then close it). The joint is a
  smooth swell of the arm's own profile (corner chamfers kept), 37 mm wide, blending back to the
  arm over 18 mm each side; bolts 10.5 mm either side of the duct (3.8 mm clear of it), nut traps
  and head counterbores checked fully enclosed.
- `On_Kol_duct10_265_A.stl` (wrist end, 162 mm): print flat; hex nut traps underneath.
- `On_Kol_duct10_265_B.stl` (elbow end, 180 mm): print upright, supports under the lap only.
- Pivot distance unchanged (265 mm) when joined.

## `build_shoulder_base.py` (2026-10-15)

**One-servo shoulder** (owner): the two opposed shoulder servos fought each other. One DS3225 MG on
the +Y cheek (the elbow-servo side of the upper arm), a **608 bearing** (22 x 8 x 7, same as the
elbow) in the -Y cheek, and an extension spring on a crank as a counterbalance.
- `Shoulder_Base_1servo.stl`: the original yoke (`Base.stl`, not committed) with the -Y servo window,
  its outer flange recess and screw holes filled; a 32 mm boss outside; the 608 pressed in from
  outside against a 5 mm lip (14 mm hole, touches the outer race only); a pocket with a printed
  4 mm bar in the disk outside the -Y cheek as the spring anchor.
- `Shoulder_Rod.stl` (2026-10-16, owner: printed rod): 8 mm D-rod, 48 mm, from past the crank through the
  608 into the arm hub, stopping short of the servo horn. **Print lying on its flat** so the layers run
  lengthwise -- the spring bends it at the bearing. The flat also drives the crank.
- `Shoulder_Rod_Hub.stl`: keys the rod to the arm -- disk in the -Y horn recess (4 x M2 at r=7, like a
  horn), sleeve into the arm's 10 mm centre hole, 10 mm collar onto the bearing's inner race. Print disk down.
- Fix 2026-10-16: the 14 mm hole through the bearing cheek's inner face printed blind (a 1 mm skin, then a
  1 mm wall before the seat). Now clear through; checked by rays along the axis.
- `Shoulder_Crank.stl`: clamps the D-flat (M3 grub), spring holes at r = 15 / 20 / 25 mm. Fit it
  pointing opposite the upper arm; spring (via a short cord) from the crank pin to the anchor bar.
  Start on r=15, move out until the arm stays level with the servo off.
- **Check before printing:** the axis is taken at the spline end over the turntable centre
  (`SHOULDER_X=9.7`). If the old base's spline sits at the other end of the window, run with
  `SHOULDER_X=29.8`.

### Forearm duct 18 mm, widened arm (2026-10-16, owner; 14 then 12.5 mm tried first)

`FOREARM_PIVOT_MM=265 FOREARM_DUCT_MM=18 FOREARM_WIDE_MM=28 FOREARM_EXIT_X=92 FOREARM_WRIST_SHIFT=10 python build_arm_ducts.py`
-> `~/Downloads/On_Kol_duct18_265.stl` (one piece, 297 mm). Same 18 mm duct as the upper arm. The arm is
widened from 20 to 28 mm (its own section spread sideways, chamfers kept) from just behind the wrist
joint (taper x 26-36) to the elbow fork, so the duct walls stay 5.0 mm all along (the original 10 mm
duct had 4.5). The wrist hub and elbow fork are unchanged, so both joints fit as before. The side exit
moved 6 mm toward the wrist (`FOREARM_EXIT_X` 98 -> 92): at 98 the 18 mm duct broke into the elbow
servo's screw hole; now 5.2 mm clear.
Owner 2026-10-16: the wrist-end duct opening and the start of the widening moved 10 mm toward the
elbow (`FOREARM_WRIST_SHIFT=10`; taper now x 36-46, opening from ~x 41) -- at 0 they hit the wrist servo.
