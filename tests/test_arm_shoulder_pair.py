import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config

# 2026-10-12: the shoulder is two servos (CH2 + CH3) on one joint, driven with the SAME pulse.

def _arm(monkeypatch):
    monkeypatch.setattr(config,'ARM_RELEASE_WHEN_IDLE',False)
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',True)   # another test may leave it off
    import arm; return arm.Arm()

def test_shoulder_drives_both_channels_with_the_same_pulse(monkeypatch):
    monkeypatch.setattr(config,'ARM_SHOULDER_PAIR',True)
    a=_arm(monkeypatch)
    a.set_pulse('shoulder',1700)
    d=[a._pca.channels[c].duty_cycle for c in (config.ARM_SHOULDER,config.ARM_SHOULDER_B)]
    assert d[0]==d[1]>0
    assert 'shoulder_b' not in a.joints            # no way to drive one servo of the pair alone

def test_single_servo_shoulder_leaves_ch3_unpowered(monkeypatch):
    monkeypatch.setattr(config,'ARM_SHOULDER_PAIR',False)
    a=_arm(monkeypatch); a.set_pulse('shoulder',1700)
    assert a._pca.channels[config.ARM_SHOULDER].duty_cycle>0==a._pca.channels[config.ARM_SHOULDER_B].duty_cycle

def test_elbow_limit_while_reaching_down(monkeypatch):
    monkeypatch.setattr(config,'ARM_JOINT_LIMITS_US',{})
    a=_arm(monkeypatch)
    a.set_pulse('shoulder',1500)
    assert a.set_pulse('elbow',1000)==1000                 # upright: full range
    a.set_pulse('shoulder',1350)
    assert a.set_pulse('elbow',1000)==1300 and a.set_pulse('elbow',2000)==1850

def test_release_zeroes_both_shoulder_channels(monkeypatch):
    a=_arm(monkeypatch)
    a.set_pulse('shoulder',1700); a.release()
    assert a._pca.channels[config.ARM_SHOULDER].duty_cycle==0==a._pca.channels[config.ARM_SHOULDER_B].duty_cycle

def test_per_joint_limits_clamp(monkeypatch):
    monkeypatch.setattr(config,'ARM_JOINT_LIMITS_US',{'elbow':(1100,2400)})
    a=_arm(monkeypatch)
    lo,hi=config.ARM_JOINT_LIMITS_US['elbow']
    assert a.set_pulse('elbow',700)==lo and a.set_pulse('elbow',2600)==hi


def test_pair_engages_for_a_move_then_drops(monkeypatch):
    monkeypatch.setattr(config,'ARM_SHOULDER_PAIR',False)
    a=_arm(monkeypatch); a.set_pulse('shoulder',1500)
    a.set_pulse('shoulder_pair',1); a.set_pulse('shoulder',1525)
    d=[a._pca.channels[c].duty_cycle for c in (config.ARM_SHOULDER,config.ARM_SHOULDER_B)]
    assert d[0]==d[1]>0
    a.set_pulse('shoulder_pair',0)
    assert a._pca.channels[config.ARM_SHOULDER_B].duty_cycle==0
