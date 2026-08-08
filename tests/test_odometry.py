import os,sys,math
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from odometry import integrate,Pose

# Pure-logic tests for integrate() — no hardware/mocking needed, per
# docs/WildWilly_Claude_Fix_Implementation_Plan.md §20/§8. TRACK_WIDTH_M is patched to 1.0 in the
# rotation tests below purely to make the expected angle arithmetic simple by hand; it does not
# depend on config.py's actual (unconfirmed) chassis value.

def test_straight_line_no_rotation():
    p=Pose()
    p2=integrate(p,1.0,1.0,1.0,10.0)
    assert math.isclose(p2.x,1.0,abs_tol=1e-9)
    assert math.isclose(p2.y,0.0,abs_tol=1e-9)
    assert math.isclose(p2.heading,0.0,abs_tol=1e-9)
    assert math.isclose(p2.linear_velocity,1.0,abs_tol=1e-9)
    assert math.isclose(p2.angular_velocity,0.0,abs_tol=1e-9)
    assert p2.timestamp==10.0 and p2.stale is False

def test_zero_dt_returns_same_pose_unchanged():
    p=Pose(x=3.0,y=4.0,heading=1.0)
    p2=integrate(p,1.0,1.0,0.0,10.0)
    assert p2 is p  # explicit no-op, not just numerically unchanged

def test_pure_rotation_in_place():
    config.TRACK_WIDTH_M=1.0
    p=Pose()
    # left back 0.5m, right forward 0.5m, track=1.0 -> d_heading = (0.5-(-0.5))/1.0 = 1.0 rad
    p2=integrate(p,-0.5,0.5,1.0,1.0)
    assert math.isclose(p2.x,0.0,abs_tol=1e-9) and math.isclose(p2.y,0.0,abs_tol=1e-9)
    assert math.isclose(p2.heading,1.0,abs_tol=1e-9)
    assert math.isclose(p2.linear_velocity,0.0,abs_tol=1e-9)
    assert math.isclose(p2.angular_velocity,1.0,abs_tol=1e-9)

def test_heading_wraps_to_pi_range():
    config.TRACK_WIDTH_M=1.0
    p=Pose(heading=3.0)  # close to pi already
    p2=integrate(p,-1.0,1.0,1.0,1.0)  # d_heading=2.0 -> raw heading 5.0, must wrap into (-pi,pi]
    assert -math.pi<=p2.heading<=math.pi
    assert math.isclose(p2.heading,math.atan2(math.sin(5.0),math.cos(5.0)),abs_tol=1e-9)

def test_arc_uses_midpoint_heading_not_endpoint():
    config.TRACK_WIDTH_M=1.0
    p=Pose(heading=0.0)
    p2=integrate(p,0.0,math.pi,1.0,1.0)  # d_heading=pi -> quarter-turn-scale arc, not a straight line
    # midpoint heading = pi/2 -> displacement should be almost entirely in y, not x
    assert abs(p2.x)<abs(p2.y)

def test_original_pose_not_mutated():
    p=Pose(x=1.0,y=2.0,heading=0.5)
    integrate(p,1.0,1.0,1.0,10.0)
    assert p.x==1.0 and p.y==2.0 and p.heading==0.5
