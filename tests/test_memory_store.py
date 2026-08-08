import os,sys,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from memory_store import MemoryStore

# §20 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: corrupted database handling. No test
# file existed for memory_store.py before this -- just the one gap that matters most (the
# world_model.py version of this same fix is covered in tests/test_world_model.py).

def test_corrupted_database_is_moved_aside_and_starts_fresh():
    with tempfile.TemporaryDirectory() as d:
        path=os.path.join(d,'corrupt.db')
        with open(path,'wb') as f: f.write(b'not a sqlite database'*5)
        ms=MemoryStore(db_path=path)  # must not raise
        assert ms.all_facts()=={}  # usable, empty
        moved=[f for f in os.listdir(d) if f.startswith('corrupt.db.corrupted.')]
        assert len(moved)==1  # original renamed aside, not deleted
        with open(os.path.join(d,moved[0]),'rb') as f: assert f.read()==b'not a sqlite database'*5

def test_normal_construction_and_fact_roundtrip_still_works():
    with tempfile.TemporaryDirectory() as d:
        ms=MemoryStore(db_path=os.path.join(d,'normal.db'))
        ms.add_fact('battery_type','3S LiPo')
        assert ms.get_fact('battery_type')=='3S LiPo'
