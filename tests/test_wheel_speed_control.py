import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-500-004 closed-loop wheel speed (2026-10-02), owner speeds 0.5 / 1.0 / 1.5 mph.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import config,motors
from motors import wheel_duty,cap_rpm
# speeds are fractions of the 1.5 mph cap
assert abs(config.SPEED_ROAM-1.0/1.5)<1e-9 and abs(config.SPEED_SLOW-0.5/1.5)<1e-9
assert 120<cap_rpm()<130, cap_rpm()                       # 1.5 mph on a 4 in wheel ~126 RPM
# zero target -> zero duty, integrator cleared
assert wheel_duty("lf",0,10,0.2,0.02)==(0.0,0.0)
# no feedback -> feed-forward only
d0,slope=config.WHEEL_FF["lf"]
d,i=wheel_duty("lf",84.0,None,0.0,0.02); assert abs(d-(d0+84/slope))<1e-9 and i==0.0
# a stuck wheel: trim grows, but never more than WHEEL_TRIM_MAX above feed-forward
ff=config.WHEEL_FF["rm"][0]+42/config.WHEEL_FF["rm"][1]
i=0.0
for _ in range(500): d,i=wheel_duty("rm",42.0,0.0,i,0.02)
assert abs(d-(ff+config.WHEEL_TRIM_MAX))<1e-9, (d,ff)
# a wheel already too fast is trimmed down, but never reversed against the target
d,_=wheel_duty("lf",42.0,400.0,-0.3,0.02); assert 0.0<=d<d0+42/slope, d
# reverse targets mirror forward ones
df,_=wheel_duty("lr",60.0,None,0.0,0.02); dr,_=wheel_duty("lr",-60.0,None,0.0,0.02); assert abs(df+dr)<1e-12
# saturation holds the integrator (anti-windup)
d,i2=wheel_duty("lf",cap_rpm()*2,0.0,0.25,0.02); assert d==1.0 and i2==0.25
print("WSC_OK")
'''

def test_wheel_speed_controller():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'WSC_OK' in r.stdout, r.stdout+r.stderr
