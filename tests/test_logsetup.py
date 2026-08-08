import os,sys,logging
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logsetup import log_event

# §21 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: log_event() formats a grep-able
# EVENT=<NAME> tag onto an existing logger, without needing the real rotating-file setup.

class _CapturingHandler(logging.Handler):
    def __init__(self): super().__init__(); self.records=[]
    def emit(self,record): self.records.append(record)

def _logger():
    lg=logging.getLogger('test_log_event'); lg.handlers=[]; lg.propagate=False
    lg.setLevel(logging.DEBUG)
    h=_CapturingHandler(); lg.addHandler(h)
    return lg,h

def test_log_event_default_severity_is_info():
    lg,h=_logger()
    log_event(lg,'LOW_BATTERY')
    assert h.records[0].levelno==logging.INFO
    assert h.records[0].getMessage()=='EVENT=LOW_BATTERY'

def test_log_event_severity_selects_level():
    lg,h=_logger()
    log_event(lg,'IMU_FAULT',severity='warning')
    assert h.records[0].levelno==logging.WARNING

def test_log_event_fields_appended_as_key_value_pairs():
    lg,h=_logger()
    log_event(lg,'LOW_BATTERY',severity='error',subsystem='battery',status='shutdown',volts='10.10')
    msg=h.records[0].getMessage()
    assert msg.startswith('EVENT=LOW_BATTERY ')
    assert 'subsystem=battery' in msg and 'status=shutdown' in msg and 'volts=10.10' in msg
