import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-01: the self-test retry used to re-scan the whole I2C bus every SELFTEST_RETRY_S.
# Each scan quick-writes 0x4A, the BNO085 logs "host write too short", and its Error List packet
# crashes adafruit_bno08x (KeyError: 12). Pinned here: after the first full scan, a retry probes
# ONLY the expected addresses still missing. Since 2026-10-02 there is no full scan at all and
# 0x4A is never probed: the startup scan alone latched SENSOR_FAULT on the first boot.
#
# Subprocess under WILLY_SIMULATE=1, same reason as test_selftest_override_classification.py.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import config
from brain import _i2c_present,_EXPECTED_I2C

probed=[]
def probe(a): probed.append(a); return a!=config.ADS_ADDR

# 1. First run probes every expected address EXCEPT the IMU, which is never touched.
seen=_i2c_present(None,probe)
assert config.IMU_ADDR not in probed, probed
assert set(probed)==_EXPECTED_I2C-{config.IMU_ADDR}, probed
assert seen==_EXPECTED_I2C-{config.ADS_ADDR}

# 2. Retry probes only what is still missing.
probed.clear()
seen=_i2c_present(seen,lambda a: (probed.append(a),True)[1])
assert probed==[config.ADS_ADDR], probed
assert seen==_EXPECTED_I2C

# 3. Everything seen: the bus is not touched at all.
probed.clear()
assert _i2c_present(seen,probe)==_EXPECTED_I2C and probed==[]
print("OK")
'''

def test_selftest_retry_probes_only_missing_addresses():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,capture_output=True,text=True,timeout=120)
    assert r.returncode==0 and 'OK' in r.stdout, r.stdout+r.stderr
