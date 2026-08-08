import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from brain import RoverBrain

# 2026-08-08 audit P1: no systemd WatchdogSec is actually configured (confirmed via
# `systemctl cat willy-rover.service`), so a hung tick loop has no OS-level backstop today.
# _record_tick_duration() is pure bookkeeping (no hardware, no I/O besides a log call) --
# tested the same lightweight-stand-in way as _bat_tier_for/_update_bat_tier in
# tests/test_brain_battery.py, without constructing a full RoverBrain.

def _brain():
    ns=types.SimpleNamespace(_last_tick_duration_s=0.0,_max_tick_duration_s=0.0,_tick_overrun_count=0)
    ns._record_tick_duration=types.MethodType(RoverBrain._record_tick_duration,ns)
    return ns

def test_records_last_duration():
    b=_brain()
    b._record_tick_duration(0.02)
    assert b._last_tick_duration_s==0.02

def test_tracks_running_max_not_just_last():
    b=_brain()
    b._record_tick_duration(0.05)
    b._record_tick_duration(0.01)  # smaller -- max should not regress
    assert b._max_tick_duration_s==0.05
    assert b._last_tick_duration_s==0.01

def test_under_threshold_does_not_count_as_overrun():
    b=_brain()
    b._record_tick_duration(config.TICK_OVERRUN_THRESHOLD_S-0.001)
    assert b._tick_overrun_count==0

def test_over_threshold_counts_as_overrun():
    b=_brain()
    b._record_tick_duration(config.TICK_OVERRUN_THRESHOLD_S+0.001)
    assert b._tick_overrun_count==1

def test_overrun_count_accumulates_across_multiple_overruns():
    b=_brain()
    for _ in range(3): b._record_tick_duration(config.TICK_OVERRUN_THRESHOLD_S+0.05)
    assert b._tick_overrun_count==3

def test_properties_expose_milliseconds():
    ns=types.SimpleNamespace(_last_tick_duration_s=0.025,_max_tick_duration_s=0.075,_tick_overrun_count=2)
    assert RoverBrain.tick_duration_ms.fget(ns)==25.0
    assert RoverBrain.max_tick_duration_ms.fget(ns)==75.0
    assert RoverBrain.tick_overrun_count.fget(ns)==2
