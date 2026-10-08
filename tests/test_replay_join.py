import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')

# FR-1900-002 (2026-10-08): a route joined partway is driven from the join point on.

def test_mission_start_trims_the_route():
    from navigation import Navigator,Mission
    route=types.SimpleNamespace(waypoints=[(0,0),(1,0),(2,0),(3,0)])
    wm=types.SimpleNamespace(get_route=lambda n: route if n=='kitchen' else None)
    n=object.__new__(Navigator); n.world_model=wm
    assert n._resolve_route(Mission(route='kitchen',start=2))==[(2,0),(3,0)]
    assert n._resolve_route(Mission(route='kitchen'))==[(0,0),(1,0),(2,0),(3,0)]

def test_nearest_point():
    from memory_store import _nearest_point
    i,d=_nearest_point([(0,0),(1,0),(2,0)],1.1,0.5)
    assert i==1 and abs(d-0.5099)<1e-3
