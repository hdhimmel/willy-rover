# tests/test_memory_things.py
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from memory_store import MemoryStore

# FR-2400 (2026-10-15): what he has seen and been told, for engagement.

def _store(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    return MemoryStore('m.db')

def test_upsert_thing_returns_previous_last_seen(tmp_path,monkeypatch):
    m=_store(tmp_path,monkeypatch)
    assert m.upsert_thing('sports ball','kitchen',at=100.0) is None
    assert m.upsert_thing('sports ball','kitchen',at=200.0)==100.0
    assert m.upsert_thing('sports ball',None,at=300.0) is None          # unnamed place = its own row
    rows=m.things('sports ball','kitchen')
    assert len(rows)==1 and rows[0]['first_seen']==100.0 and rows[0]['last_seen']==200.0

def test_upsert_returns_previous_last_seen_across_reopen(tmp_path,monkeypatch):
    m=_store(tmp_path,monkeypatch); m.upsert_thing('cup','den',at=50.0); m.close()
    m2=MemoryStore('m.db')
    assert m2.upsert_thing('cup','den',at=60.0)==50.0

def test_name_thing_labels_the_row(tmp_path,monkeypatch):
    m=_store(tmp_path,monkeypatch)
    m.upsert_thing('sports ball','kitchen',at=1.0)
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball",at=2.0)
    r=m.things('sports ball','kitchen')[0]
    assert r['owner']=='Storm' and r['label']=="Storm's ball"
    m.name_thing('frisbee','yard',None,'the red frisbee',at=3.0)   # never seen: still stored
    assert m.things('frisbee','yard')[0]['label']=='the red frisbee'

def test_things_any_room(tmp_path,monkeypatch):
    m=_store(tmp_path,monkeypatch)
    m.upsert_thing('cup','den',at=1.0); m.upsert_thing('cup','kitchen',at=2.0)
    assert {r['room'] for r in m.things('cup',any_room=True)}=={'den','kitchen'}
    assert {r['kind'] for r in m.things(room='den')}=={'cup'}

def test_person_notes_newest_first_and_purged(tmp_path,monkeypatch):
    m=_store(tmp_path,monkeypatch)
    now=time.time()
    m.add_person_note('Howard','had a long day',at=now-10)
    m.add_person_note('Howard','is fixing the arm',at=now)
    m.add_person_note('Howard','very old',at=now-400*86400)
    assert [n['note'] for n in m.person_notes('Howard',n=2)]==['is fixing the arm','had a long day']
    m.purge_expired(max_age_days=30)
    assert [n['note'] for n in m.person_notes('Howard',n=5)]==['is fixing the arm','had a long day']

def test_context_includes_things_and_notes(tmp_path,monkeypatch):
    m=_store(tmp_path,monkeypatch)
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball",at=1.0)
    m.add_person_note('Howard','were fixing the arm')
    ctx=m.get_context_for("where is Storm's ball?",person='Howard')
    assert any("Storm's ball" in t for t in ctx['things'])
    assert ctx['notes']==['were fixing the arm']
