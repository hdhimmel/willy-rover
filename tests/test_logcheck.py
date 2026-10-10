import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# "Hey Willie, check your logs" (2026-10-10).
NOW=time.mktime(time.strptime('2026-10-10 12:00:00','%Y-%m-%d %H:%M:%S'))
LOG=[
 "2026-10-10 06:34:32 WARNING sensors Rear ToF: DROP BEHIND -- reversing stopped (r1c1=None)",
 "2026-10-10 06:34:33 WARNING sensors Rear ToF: DROP BEHIND -- reversing stopped (r0c0=None)",
 "2026-10-10 06:38:40 WARNING brain   SLOW->STALL_FAULT (wheel stall: ['rr'])",
 "2026-10-10 06:34:47 WARNING brain EVENT=TICK_OVERRUN subsystem=brain duration_ms=897 threshold_ms=150",
 "2026-10-10 06:46:14 WARNING brain EVENT=CURRENT_FAULT subsystem=current status=fault value=no INA260 read",
 "2026-10-10 06:46:28 WARNING brain EVENT=CURRENT_FAULT subsystem=current status=fault value=no INA260 read",
 "2026-10-10 06:46:30 INFO    brain Self-test passed",
 "2026-10-08 06:00:00 WARNING brain EVENT=IMU_FAULT subsystem=imu status=fault",   # outside 24 h
 "2026-10-10 07:00:00 WARNING brain Self-test retry failed (3x): x",                 # ignored chatter
 "2026-10-10 06:46:15 WARNING brain   IDLE->SENSOR_FAULT (current)",                   # consequence
 "2026-10-10 06:46:16 WARNING safety emergency stop: sensor fault",                    # consequence
]

def test_summary_counts_problems_in_the_window():
    import logcheck
    s=logcheck.summarize(LOG,now=NOW)
    names={n:c for n,c,_ in s}
    assert names['rear drop warnings']==2 and names['current monitor faults']==2
    assert names['wheel stalls on rr']==1 and names['control-loop overruns']==1
    assert not any('imu' in n for n in names) and not any('retry' in n for n in names)
    assert not any('emergency' in n or 'sensor_fault' in n for n in names)

def test_spoken_is_brief_with_the_top_three_and_a_count_of_the_rest():
    import logcheck
    t=logcheck.spoken(logcheck.summarize(LOG,now=NOW))
    assert t.startswith('Today:') and 'and 1 other kind' in t and 'The last one was at' in t
    assert t.count(',')<=4

def test_clean_log():
    import logcheck
    assert 'clean' in logcheck.spoken([])

@pytest.mark.parametrize('said',['check your logs','Willie, scan your logs for errors.','any errors today','read the logs'])
def test_phrases(said):
    import voice
    v=object.__new__(voice.VoicePipeline)
    assert v._fast_path(said)['intent']=='check_logs'
