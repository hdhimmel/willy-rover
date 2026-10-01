import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-01: the self-test retry used to re-scan the whole I2C bus every SELFTEST_RETRY_S.
# Each scan quick-writes 0x4A, the BNO085 logs "host write too short", and its Error List packet
# crashes adafruit_bno08x (KeyError: 12). Pinned here: after the first full scan, a retry probes
# ONLY the expected addresses still missing -- never one already seen, so never a healthy 0x4A.
#
# Subprocess under WILLY_SIMULATE=1, same reason as test_selftest_override_classification.py.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import config
from brain import _i2c_present,_EXPECTED_I2C

scans=[]; probed=[]
def scan(): scans.append(1); return sorted((_EXPECTED_I2C-{config.ADS_ADDR})|{0x70})
def probe(a): probed.append(a); return True

# 1. First run is a full scan; non-expected addresses (0x70) are dropped.
seen=_i2c_present(None,scan,probe)
assert scans==[1] and probed==[], (scans,probed)
assert seen==_EXPECTED_I2C-{config.ADS_ADDR}

# 2. Retry: no scan, and only the missing address is probed -- the IMU is left alone.
seen=_i2c_present(seen,scan,probe)
assert scans==[1], scans
assert probed==[config.ADS_ADDR], probed
assert config.IMU_ADDR not in probed
assert seen==_EXPECTED_I2C

# 3. Once everything is seen, a retry touches the bus not at all.
probed.clear()
assert _i2c_present(seen,scan,probe)==_EXPECTED_I2C
assert probed==[] and scans==[1]

# 4. A probe that fails leaves the address missing.
assert _i2c_present(set(),scan,lambda a: a!=config.IMU_ADDR)==_EXPECTED_I2C-{config.IMU_ADDR}
print("OK")
'''

def test_selftest_retry_probes_only_missing_addresses():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,capture_output=True,text=True,timeout=120)
    assert r.returncode==0 and 'OK' in r.stdout, r.stdout+r.stderr
