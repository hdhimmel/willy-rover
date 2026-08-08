import os,sys,time,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from world_model import WorldModel,Object as WMObject
from ai_provider import (AIProvider,AIResult,_validate_schema,_clamp01,_action_confidence,
                          _parse_response,build_world_state)

# Pure-logic tests for ai_provider.py -- no network access, no hardware (§20/§14/§15 of
# docs/WildWilly_Claude_Fix_Implementation_Plan.md). HTTP calls are never exercised here; a
# _FakeProvider subclass stands in for CloudAIProvider/LocalAIProvider to test the shared
# request_async/poll_async/reset_async/ask_sync machinery in AIProvider's base class.

# --- _validate_schema ---

def test_validate_schema_all_present_and_correct():
    assert _validate_schema({'action':'forward','duration':1.0},{'action':str,'duration':(int,float)})

def test_validate_schema_missing_key():
    assert not _validate_schema({'action':'forward'},{'action':str,'duration':(int,float)})

def test_validate_schema_wrong_type():
    assert not _validate_schema({'action':'forward','duration':'soon'},{'action':str,'duration':(int,float)})

def test_validate_schema_non_dict_input():
    assert not _validate_schema(['not','a','dict'],{'action':str})

# --- _clamp01 ---

def test_clamp01_valid_value_passes_through():
    assert _clamp01(0.7)==0.7

def test_clamp01_out_of_range_clamped():
    assert _clamp01(5.0)==1.0
    assert _clamp01(-3.0)==0.0

def test_clamp01_missing_or_invalid_uses_low_default():
    assert _clamp01(None)==0.3
    assert _clamp01('not a number')==0.3

# --- _action_confidence ---

def test_action_confidence_known_action_sane_params():
    assert _action_confidence({'action':'forward','duration':1.0,'speed':0.5})==1.0

def test_action_confidence_unknown_action_is_zero():
    assert _action_confidence({'action':'levitate'})==0.0

def test_action_confidence_duration_out_of_range_is_zero():
    assert _action_confidence({'action':'forward','duration':999999.0})==0.0

def test_action_confidence_speed_out_of_range_is_zero():
    assert _action_confidence({'action':'forward','speed':5.0})==0.0

def test_action_confidence_missing_optional_fields_still_one():
    assert _action_confidence({'action':'stop'})==1.0

# --- _parse_response ---

def test_parse_response_freeform_schema_none():
    r=_parse_response('just some text back',None)
    assert r.parse_success is True and r.payload=='just some text back' and r.action_confidence is None

def test_parse_response_valid_json_matching_schema():
    txt='{"action":"forward","duration":1.0,"speed":0.5,"confidence":0.9}'
    r=_parse_response(txt,{'action':str,'duration':(int,float),'speed':(int,float)})
    assert r.parse_success is True
    assert r.payload['action']=='forward'
    assert r.intent_confidence==0.9
    assert r.action_confidence==1.0
    assert r.safety_validation is True

def test_parse_response_code_fence_stripped():
    txt='```json\n{"action":"stop","duration":1.0,"speed":0.0}\n```'
    r=_parse_response(txt,{'action':str,'duration':(int,float),'speed':(int,float)})
    assert r.parse_success is True and r.payload['action']=='stop'

def test_parse_response_invalid_json_fails_parse():
    r=_parse_response('not json at all',{'action':str})
    assert r.parse_success is False and r.payload is None and r.intent_confidence==0.0

def test_parse_response_schema_mismatch_fails_parse():
    r=_parse_response('{"wrong_key":"value"}',{'action':str})
    assert r.parse_success is False

def test_parse_response_non_motion_schema_has_no_action_confidence():
    r=_parse_response('{"intent":"forward","args":{},"reply":"ok"}',
                       {'intent':str,'args':dict,'reply':str})
    assert r.parse_success is True and r.action_confidence is None and r.safety_validation is True

# --- build_world_state ---

class _FakePose:
    def __init__(self,x=0.0,y=0.0,heading=0.0): self.x=x; self.y=y; self.heading=heading

class _FakeOdometry:
    def __init__(self,pose=None): self.pose=pose or _FakePose()

def test_build_world_state_shape_and_content():
    with tempfile.TemporaryDirectory() as d:
        wm=WorldModel(_FakeOdometry(_FakePose(x=1.0,y=2.0,heading=0.5)),db_path=os.path.join(d,'ai_test.db'))
        wm.add_room('kitchen',cx=1.0,cy=2.0,radius_m=1.0)
        wm.remember_object(WMObject('bottle',1.2,2.1,0.9))
        wm.add_route('to_kitchen',[(0.0,0.0),(1.0,2.0)])
        state=build_world_state(wm,goal='find a clear path',battery=80,stuck_count=2)
        assert state['robot']['room']=='kitchen'
        assert state['robot']['pose']['x']==1.0 and state['robot']['battery']==80
        assert state['goal']=='find a clear path'
        assert any(o['cls']=='bottle' for o in state['nearby_objects'])
        assert state['available_routes']==['to_kitchen']
        assert state['stuck_count']==2  # **extra merged in

def test_build_world_state_far_object_excluded():
    with tempfile.TemporaryDirectory() as d:
        wm=WorldModel(_FakeOdometry(_FakePose(x=0.0,y=0.0)),db_path=os.path.join(d,'ai_test2.db'))
        wm.remember_object(WMObject('bottle',100.0,100.0,0.9))  # far outside AI_NEARBY_RADIUS_M
        state=build_world_state(wm)
        assert state['nearby_objects']==[]

# --- AIProvider base class (async/sync contract) via a fake subclass ---

class _FakeProvider(AIProvider):
    def __init__(self,result_fn):
        self._result_fn=result_fn
        super().__init__()
    @property
    def available(self): return True
    def _call(self,prompt,system=None,schema=None,history=None):
        return self._result_fn(prompt,system,schema,history)

def _wait_poll(provider,timeout=2.0):
    deadline=time.time()+timeout
    while time.time()<deadline:
        r=provider.poll_async()
        if r is not None: return r
        time.sleep(0.01)
    raise TimeoutError('provider did not respond in time')

def test_request_async_poll_async_roundtrip():
    p=_FakeProvider(lambda prompt,system,schema,history: AIResult(True,0.9,None,True,prompt,''))
    ok=p.request_async('hello')
    assert ok is True
    result=_wait_poll(p)
    assert result.payload=='hello'

def test_request_async_busy_rejects_second_request():
    p=_FakeProvider(lambda prompt,system,schema,history: (time.sleep(0.3) or AIResult(True,1.0,None,True,prompt,'')))
    assert p.request_async('first') is True
    assert p.request_async('second') is False  # worker still busy

def test_reset_async_clears_busy_and_drops_stale_result():
    p=_FakeProvider(lambda prompt,system,schema,history: AIResult(True,1.0,None,True,prompt,''))
    p.request_async('hello')
    time.sleep(0.05)  # let the worker finish and populate _out_q
    p.reset_async()
    assert p.poll_async() is None  # stale result was dropped
    assert p.request_async('again') is True  # _busy was cleared, a new request is accepted

def test_ask_sync_bypasses_queue_and_worker_state():
    p=_FakeProvider(lambda prompt,system,schema,history: AIResult(True,1.0,None,True,prompt,''))
    result=p.ask_sync('direct')
    assert result.payload=='direct'
    assert p.poll_async() is None  # nothing was ever queued -- ask_sync doesn't touch _busy/_out_q

def test_history_threaded_through_to_call():
    seen=[]
    p=_FakeProvider(lambda prompt,system,schema,history: (seen.append(history) or AIResult(True,1.0,None,True,prompt,'')))
    history=[{'role':'user','content':'earlier turn'}]
    p.request_async('hello',history=history)
    _wait_poll(p)
    assert seen[0]==history
