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
| Forearm (`On_Kol` / `Arm B`) | `Arm B.stl` | `On_Kol_duct10.stl` | 10 mm; in at the top ~36 mm from the wrist axle, out on the servo-flange side ~47 mm before the elbow hub. Side recesses filled along the run, giving 4.5 mm walls. Servo plugs come off and are re-crimped after threading. |

Both come out slightly lighter than the originals. `arm_ducts_check.png` shows where the
openings are. Input and output paths are set at the top of the script (`~/Downloads`).

Needs `trimesh` and `manifold3d`.

## Link lengths (pivot centre to pivot centre)

- Upper arm L1 = **200.1 mm** (hole line runs 10.9 deg off the part's long edge)
- Forearm L2 = **140.1 mm** original (elbow hub to wrist axle). **Too short:** with the shoulder 446 mm
  up, `arm_ik.solve` finds no pose reaching the floor past the front wheels (2026-10-14). Willie runs
  the 220 mm stretched forearm; the ducted forearm needs stretching to match before it is fitted.
- Hand, wrist-pitch pivot to fingertip: 227 mm closed, 180 mm open

## `build_hand_camera_mount.py` (2026-10-14)

Hand back plate (`El.stl`, downloaded as `hand back.stl`) with a **two-piece case** for the
InnoMaker U20CAM-1080P hand camera (32 x 32 mm board, four 2.2 mm M2 holes, M12 lens, 1 m cable).
- `hand_back_camera.stl`: the plate with the case's back on its outer face -- a wall leaning to
  look past the **angled end** (the fingertip end) **20 deg down**, a rim the board sits in, a
  24 x 24 mm pocket for the parts on the board's back, and a **12 x 8 mm cable hole out the back**.
- `hand_camera_cap.stl`: the front, 34.4 x 34.4 x 6 mm, with a 17 mm lens hole and corner bosses
  that clamp the board. Print face down.
- Four **M2 x 16** screws through cap, board and wall, nuts behind. The hole spacing is not in
  InnoMaker's manual, so all holes are slots covering 26-30 mm.
- Checked by the script: the cap clears the plate (1.7 mm), and a 4 mm screwdriver still reaches
  all six plate screws from above. Assumes the plate's top face (as downloaded) is the outside.
- Outputs go to `~/Downloads`; preview `hand_back_camera_preview.png`.
