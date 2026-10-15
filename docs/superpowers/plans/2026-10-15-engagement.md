# Engagement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Willie greets people he sees and starts short conversations about what he sees and remembers (FR-2400).

**Architecture:** A pure decision module (`engage.py`) picks at most one topic per tick from detections, face matches, memory and a "previously seen" snapshot. A words module (`engage_words.py`) turns a topic into a spoken line (cloud model, 3 s cap, template fallback) and turns a spoken answer into facts to store. `brain.py` adds an `ENGAGE` state that stops, turns via the existing `Rotation`, speaks, listens once, stores, and resumes.

**Tech Stack:** Python 3.13 on a Pi 5, SQLite (memory.db, WAL), Hailo YOLO detections, YuNet/SFace faces, Anthropic cloud via `ai_provider.CloudAIProvider`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-engagement-design.md`

## Global Constraints

- Engage only in states `IDLE`, `ROAM`, `SLOW`. Never during a task, `AVOID`, `STUCK`, a fault, low battery, privacy mode, or while voice is busy.
- At most one non-greeting topic every `ENGAGE_GAP_S=300` s. Each person greeted once per visit; a visit ends after `ENGAGE_VISIT_S=1800` s unseen.
- Never the same (kind, subject) twice in one calendar day — counted when the topic is CHOSEN, spoken or not.
- Topics 3-7 (everything except greetings) need a person in view (a `person` detection or a face). Clarification of the spec: he engages *with people*; he does not talk to an empty room.
- The cloud gets text facts only, never an image (FR-1800).
- Engagement never drives itself: stops go through `SafetyController`, turns through `RoverBrain.start_rotation` (`Rotation` and all its guards).
- "Stranger danger" is removed. A stranger's name is kept for the visit only; no face vector is stored except by the existing UNCERTAIN-band path.
- Code style: match the repo — compact lines, no type annotations in brain.py, comments dated `2026-10-15` where they explain a decision.
- Local tests on Windows run through the shim: `python "$TMP/shim_run.py" -q <tests>`. Tests that import `brain` must run out-of-process (pattern: `tests/test_stuck_ai_fallback_chain.py`) — on Windows they fail on `pygame`; CI (Linux) is the judge for those.
- Every commit: push, wait for CI green (public API `actions/runs?per_page=1`), then `git pull` on willie. Restarting willie needs the owner's go.

## Review Focus

1. **Several faces at once** (two people walk in): greet each known person once, in turn — not all in one tick, not none. → Task 3 test `test_two_known_faces_greeted_one_per_tick`.
2. **Answer arrives after the topic was cancelled** ("stop" during the question, then someone answers): nothing stored, nothing said. → Task 5 test `test_answer_after_stop_is_ignored`.
3. **Cloud returns junk for a line** (empty, over-long, JSON, a refusal): template used instead. → Task 2 test `test_bad_cloud_lines_fall_back`.
4. **Day rollover**: a topic said at 23:59 may fire again at 00:01. → Task 3 test `test_said_today_resets_at_midnight`.
5. **Restart mid-visit**: after a service restart the same person is greeted again at most once (no greeting storm), and things seen before the restart still count as "seen before". → Task 1 test `test_upsert_returns_previous_last_seen_across_reopen`, Task 3 test `test_greet_once_after_restart`.

---

## File Structure

| File | Responsibility |
|---|---|
| `memory_store.py` (modify) | `things` and `person_notes` tables + API |
| `engage_words.py` (create) | `when_words`, `template`, `line`, `extract` |
| `engage.py` (create) | `FaceSeen`, `Topic`, `Engagement.tick` — the rules |
| `config.py` (modify) | `ENABLE_ENGAGEMENT`, `ENGAGE_*`, `ENGAGE_TEMPLATES` |
| `voice.py` (modify) | `VoicePipeline.busy` property |
| `recognition.py` (modify) | record `frame_w` of the last scanned frame |
| `brain.py` (modify) | sightings → `prev_seen`; `_engage_step`; `ENGAGE` state; answers → memory; stop cancels; face code moved |
| `docs/…` (modify) | FRD FR-2400, SDD, User Guide |
| tests (create) | `test_memory_things.py`, `test_engage_words.py`, `test_engage.py`, `test_engage_brain.py` |

---

### Task 1: Memory — things and person notes

**Files:**
- Modify: `memory_store.py` (`_SCHEMA`, new methods after `experiences_since`, `purge_expired`)
- Test: `tests/test_memory_things.py`

**Interfaces:**
- Produces:
  - `MemoryStore.upsert_thing(kind, room=None, at=None) -> float|None` — previous `last_seen` for (kind, room), or None if the row is new.
  - `MemoryStore.name_thing(kind, room, owner, label, at=None) -> None`
  - `MemoryStore.things(kind=None, room=None, any_room=False) -> list[dict]` with keys `kind,label,owner,room,first_seen,last_seen`. `room=None` and `any_room=False` matches rows whose room IS NULL; `any_room=True` ignores room.
  - `MemoryStore.add_person_note(name, note, at=None) -> None`
  - `MemoryStore.person_notes(name, n=3) -> list[dict]` newest first, keys `note,at`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python "$TMP/shim_run.py" -q tests/test_memory_things.py`
Expected: FAIL — `AttributeError: 'MemoryStore' object has no attribute 'upsert_thing'`

- [ ] **Step 3: Implement**

In `memory_store.py`, append to `_SCHEMA` (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS things(
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, label TEXT, owner TEXT, room TEXT,
    first_seen REAL NOT NULL, last_seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS person_notes(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, note TEXT NOT NULL, at REAL NOT NULL);
```

After `experiences_since`:

```python
    # --- FR-2400 engagement (2026-10-15): things he has seen, what people told him ---
    _THING_COLS=('kind','label','owner','room','first_seen','last_seen')

    def upsert_thing(self,kind,room=None,at=None):
        """A sighting. Returns the previous last_seen for (kind, room), None if never seen there --
        read BEFORE the update, so engagement can tell 'back again after hours' and 'new here'."""
        at=at or time.time()
        with self._lock:
            row=self._conn.execute('SELECT MAX(last_seen) FROM things WHERE kind=? AND room IS ?',
                                   (kind,room)).fetchone()
            prev=row[0] if row else None
            if prev is None:
                self._conn.execute('INSERT INTO things(kind,room,first_seen,last_seen) VALUES(?,?,?,?)',
                                   (kind,room,at,at))
            else:
                self._conn.execute('UPDATE things SET last_seen=? WHERE kind=? AND room IS ?',(at,kind,room))
            self._conn.commit()
        return prev

    def name_thing(self,kind,room,owner,label,at=None):
        at=at or time.time()
        with self._lock:
            cur=self._conn.execute('UPDATE things SET owner=?,label=? WHERE kind=? AND room IS ?',
                                   (owner,label,kind,room))
            if cur.rowcount==0:
                self._conn.execute('INSERT INTO things(kind,label,owner,room,first_seen,last_seen) '
                                   'VALUES(?,?,?,?,?,?)',(kind,label,owner,room,at,at))
            self._conn.commit()

    def things(self,kind=None,room=None,any_room=False):
        q='SELECT '+','.join(self._THING_COLS)+' FROM things WHERE 1=1'; args=[]
        if kind is not None: q+=' AND kind=?'; args.append(kind)
        if not any_room: q+=' AND room IS ?'; args.append(room)
        return [dict(zip(self._THING_COLS,r)) for r in self._conn.execute(q+' ORDER BY last_seen DESC',args)]

    def add_person_note(self,name,note,at=None):
        with self._lock:
            self._conn.execute('INSERT INTO person_notes(name,note,at) VALUES(?,?,?)',(name,note,at or time.time()))
            self._conn.commit()

    def person_notes(self,name,n=3):
        rows=self._conn.execute('SELECT note,at FROM person_notes WHERE lower(name)=lower(?) '
                                'ORDER BY at DESC LIMIT ?',(name,n)).fetchall()
        return [{'note':r[0],'at':r[1]} for r in rows]
```

Note `things(room='den')` with `kind=None` must work (test `test_things_any_room`): the code above handles it.

In `purge_expired`, after the experiences delete:

```python
            self._conn.execute('DELETE FROM person_notes WHERE at<?',(cutoff,))
```

- [ ] **Step 4: Run to verify they pass**

Run: `python "$TMP/shim_run.py" -q tests/test_memory_things.py tests/test_experiences.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_store.py tests/test_memory_things.py
git commit -m "Memory: things and person_notes tables for engagement (FR-2400)"
```

---

### Task 2: Words — lines and answers

**Files:**
- Create: `engage_words.py`
- Modify: `config.py` (add the `ENGAGE_TEMPLATES` and `ENGAGE_WORDS_TIMEOUT_S` block after `VOICE_LOCAL_AI_MAX_S`)
- Test: `tests/test_engage_words.py`

**Interfaces:**
- Consumes: `Topic` shape (defined in Task 3 — use this exact shape): `Topic(kind:str, subject:str, facts:dict, question:bool, bearing_deg:float|None)`; this task only reads `.kind`, `.facts`, `.question`.
- Consumes: a cloud object with `.available` (bool) and `.ask_sync(prompt, system=None, schema=None)` returning `AIResult` (`.parse_success`, `.payload`).
- Produces:
  - `engage_words.when_words(t, now) -> str` ("just now", "this morning", "this afternoon", "this evening", "last night", "yesterday", "on Tuesday", "3 days ago"…)
  - `engage_words.template(topic, n=0) -> str`
  - `engage_words.line(topic, cloud, timeout_s=None) -> str` (never raises, never empty)
  - `engage_words.extract(topic, text, cloud, timeout_s=None) -> dict|None`

- [ ] **Step 1: Add config**

```python
# FR-2400 engagement words (2026-10-15). The cloud writes the line; these fill in when it is slow,
# offline or returns junk. Keys: topic kind, or kind_about for callback/change. {fields} come from
# Topic.facts; a template whose fields are missing is skipped.
ENGAGE_WORDS_TIMEOUT_S=3.0
ENGAGE_LINE_MAX_CHARS=200
ENGAGE_TEMPLATES={
    'greet_known':["Hi {name}!","Hello {name}, good to see you.","Hey {name}!"],
    'greet_known_back':["Hi {name}! I last saw you {when}.","Hello again, {name}. Last time I saw you was {when}."],
    'greet_stranger':["Hi, I'm Willie! What's your name?"],
    'ask_room':["What room is this?","Can you tell me what room I'm in?"],
    'ask_thing':["Whose {thing} is that?","Is that someone's {thing}?"],
    'callback_seen':["{who}! I last saw you {when}.","Hello again, {who}. Last time I saw you was {when}."],
    'callback_thing':["There's {label}. I last saw it {when}."],
    'callback_note':["{name}, last time you told me you {note}. How did that go?"],
    'change_new':["I haven't seen a {thing} in the {room} before."],
    'change_missing':["{label} isn't in the {room}. It was here {when}."],
    'ask_person':["How's your day going, {name}?","What have you been up to, {name}?"],
}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_engage_words.py
import os,sys,time,types,threading
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config,engage_words as ew
from ai_provider import AIResult

def T(kind,facts,question=False): return types.SimpleNamespace(kind=kind,subject='s',facts=facts,question=question,bearing_deg=None)

def cloud(reply=None,delay=0.0,available=True,raises=False):
    def ask_sync(prompt,system=None,schema=None):
        time.sleep(delay)
        if raises: raise RuntimeError('net')
        return reply
    return types.SimpleNamespace(available=available,ask_sync=ask_sync)

def test_when_words():
    now=time.mktime((2026,10,15,15,0,0,0,0,-1))
    assert ew.when_words(now-60,now)=='just now'
    assert ew.when_words(time.mktime((2026,10,15,9,0,0,0,0,-1)),now)=='this morning'
    assert ew.when_words(time.mktime((2026,10,14,20,0,0,0,0,-1)),now)=='yesterday evening'
    assert ew.when_words(now-3*86400,now)=='3 days ago'

def test_template_fills_facts_and_skips_missing_fields():
    assert ew.template(T('ask_thing',{'thing':'ball'}))=='Whose ball is that?'
    assert ew.template(T('greet_known',{'name':'Howard','when':'this morning'},),n=0)=='Hi Howard!'
    t=T('callback',{'about':'thing','label':"Storm's ball",'when':'yesterday'})
    assert ew.template(t)=="There's Storm's ball. I last saw it yesterday."

def test_line_uses_the_cloud():
    r=AIResult(True,1.0,None,True,'  Hey Howard, nice to see you!  ','')
    assert ew.line(T('greet_known',{'name':'Howard'}),cloud(r))=='Hey Howard, nice to see you!'

def test_bad_cloud_lines_fall_back():
    t=T('ask_thing',{'thing':'ball'},question=True)
    for payload in ('','x'*500,'{"intent":"chat"}',"I'm sorry, I can't help with that."):
        assert ew.line(t,cloud(AIResult(True,1.0,None,True,payload,'')))=='Whose ball is that?'
    assert ew.line(t,cloud(raises=True))=='Whose ball is that?'
    assert ew.line(t,cloud(available=False))=='Whose ball is that?'
    assert ew.line(t,None)=='Whose ball is that?'

def test_line_slow_cloud_times_out():
    t=T('ask_room',{},question=True)
    t0=time.time(); out=ew.line(t,cloud(AIResult(True,1.0,None,True,'Late.',''),delay=2.0),timeout_s=0.2)
    assert time.time()-t0<1.0 and out in config.ENGAGE_TEMPLATES['ask_room']

def test_extract_from_cloud():
    t=T('ask_thing',{'thing':'sports ball'},question=True)
    r=AIResult(True,0.9,None,True,{'label':"Storm's ball",'owner':'Storm'},'')
    assert ew.extract(t,"It's Storm's",cloud(r))=={'label':"Storm's ball",'owner':'Storm'}

def test_extract_offline_patterns():
    off=cloud(available=False)
    assert ew.extract(T('greet_stranger',{},True),"My name is Alice.",off)=={'name':'Alice'}
    assert ew.extract(T('greet_stranger',{},True),"Bob",off)=={'name':'Bob'}
    assert ew.extract(T('ask_room',{},True),"This is the kitchen.",off)=={'room':'kitchen'}
    assert ew.extract(T('ask_room',{},True),"Living room",off)=={'room':'living room'}
    assert ew.extract(T('ask_thing',{'thing':'sports ball'},True),"It's Storm's.",off)=={'owner':'Storm','label':"Storm's sports ball"}
    assert ew.extract(T('ask_person',{'name':'Howard'},True),"Pretty busy, fixing the arm.",off)=={'note':'pretty busy, fixing the arm'}

def test_extract_unusable_is_none():
    off=cloud(available=False)
    assert ew.extract(T('greet_stranger',{},True),"",off) is None
    assert ew.extract(T('greet_stranger',{},True),"I don't know what you mean by that",off) is None
    assert ew.extract(T('ask_room',{},True),"No.",off) is None
```

- [ ] **Step 3: Run to verify they fail**

Run: `python "$TMP/shim_run.py" -q tests/test_engage_words.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'engage_words'`

- [ ] **Step 4: Implement `engage_words.py`**

```python
"""FR-2400 engagement words (2026-10-15): a topic -> one spoken line; a spoken answer -> facts.

The cloud model writes the line in Willie's persona (CloudAIProvider defaults to
CLAUDE_CHAT_SYSTEM when given no system and no schema) from TEXT facts only -- never an image
(FR-1800). It gets ENGAGE_WORDS_TIMEOUT_S; slow, offline, failing or junk replies fall back to
config.ENGAGE_TEMPLATES. Nothing here raises."""
import json,re,threading,time
import config,logsetup
log=logsetup.setup('engage')

_DESCRIBE={
    'greet_known':'You have just noticed {name}, someone you know, nearby. Greet them.',
    'greet_stranger':"Someone you don't know is here. Say hello, say you are Willie, and ask their name.",
    'ask_room':"You don't know which room you are in. Ask the person what room this is.",
    'ask_thing':'You can see a {thing}. Ask the person whose it is or what it is.',
    'callback':'You remember something: {facts}. Mention it in a friendly way.',
    'change':'You noticed a change in the {room}: {facts}. Mention it.',
    'ask_person':'Ask {name} a friendly question about their day.',
}
_REFUSALS=re.compile(r"\b(i'?m sorry|i can'?t|as an ai|i cannot)\b",re.I)

def when_words(t,now=None):
    now=now or time.time(); d=now-t
    if d<15*60: return 'just now'
    lt,ln=time.localtime(t),time.localtime(now)
    days=(time.mktime(ln[:3]+(0,0,0,0,0,-1))-time.mktime(lt[:3]+(0,0,0,0,0,-1)))/86400
    part='morning' if lt.tm_hour<12 else 'afternoon' if lt.tm_hour<17 else 'evening'
    if days<0.5: return f'this {part}'
    if days<1.5: return 'last night' if lt.tm_hour>=21 else f'yesterday {part}'
    if days<7: return f'{round(days)} days ago'
    return time.strftime('on %B %d',lt)

def _keys(topic):
    about=topic.facts.get('about')
    return ([f'{topic.kind}_{about}'] if about else [])+[topic.kind]

def template(topic,n=0):
    for key in _keys(topic):
        for i in range(len(config.ENGAGE_TEMPLATES.get(key,[]))):
            tpl=config.ENGAGE_TEMPLATES[key][(n+i)%len(config.ENGAGE_TEMPLATES[key])]
            try: return tpl.format(**topic.facts)
            except (KeyError,IndexError): continue
    return "Hello!" if topic.kind.startswith('greet') else "Hi there."

def _capped(fn,timeout_s):
    box={}
    def run():
        try: box['r']=fn()
        except Exception as e: box['e']=e
    t=threading.Thread(target=run,daemon=True,name='engage-words'); t.start(); t.join(timeout_s)
    if t.is_alive(): log.info(f'Engage words: cloud gave nothing in {timeout_s:.0f} s'); return None
    if 'e' in box: log.info(f"Engage words: cloud failed ({box['e']})"); return None
    return box.get('r')

def _usable_line(txt):
    if not isinstance(txt,str): return None
    txt=txt.strip().strip('"').strip()
    if not txt or len(txt)>config.ENGAGE_LINE_MAX_CHARS or txt.startswith('{') or _REFUSALS.search(txt): return None
    return txt

def line(topic,cloud,timeout_s=None):
    fallback=template(topic,n=int(time.time())//60)
    if cloud is None or not getattr(cloud,'available',False): return fallback
    desc=_DESCRIBE.get(topic.kind,'Say something friendly.')
    try: desc=desc.format(facts=json.dumps(topic.facts),**topic.facts)
    except (KeyError,IndexError): desc=desc.replace('{','(').replace('}',')')
    prompt=(f'{desc} Facts: {json.dumps(topic.facts)}. You are speaking first, out loud. Say ONE short '
            f'friendly sentence, under 20 words{", ending with your question" if topic.question else ""}. '
            f'Reply with only the sentence.')
    r=_capped(lambda: cloud.ask_sync(prompt),timeout_s or config.ENGAGE_WORDS_TIMEOUT_S)
    got=_usable_line(getattr(r,'payload',None)) if r is not None and getattr(r,'parse_success',False) else None
    return got or fallback

_SCHEMAS={'greet_stranger':{'name':str},'ask_room':{'room':str},'ask_thing':{'label':str},'ask_person':{'note':str}}
_ASK={'greet_stranger':'the person\'s first name as "name"',
      'ask_room':'the room name, lower case, as "room"',
      'ask_thing':'a short label for the thing as "label" (e.g. "Storm\'s ball") and its owner\'s name as "owner" (null if none)',
      'ask_person':'what they told you, as a short phrase in the second person past tense without "you", as "note"'}
_NOT_A_NAME={'no','yes','what','huh','sorry','i','me','nobody','none','willie'}

def _offline(topic,text):
    t=text.strip().rstrip('.!?').strip()
    if not t: return None
    if topic.kind=='greet_stranger':
        m=re.fullmatch(r"(?:(?:hi|hello|hey)[, ]+)?(?:my name is|i'?m|i am|it'?s|call me)?\s*([A-Za-z][a-z'-]+)",t,re.I)
        name=m.group(1).capitalize() if m else None
        return {'name':name} if name and name.lower() not in _NOT_A_NAME else None
    if topic.kind=='ask_room':
        m=re.fullmatch(r"(?:this is |it'?s |we'?re in |you'?re in )?(?:the |my |our )?([a-z ]{3,30}?)",t.lower())
        room=m.group(1).strip() if m else None
        return {'room':room} if room and room not in ('no','yes','i don\'t know','not sure') else None
    if topic.kind=='ask_thing':
        thing=topic.facts.get('thing','thing')
        m=re.fullmatch(r"(?:it'?s |that'?s |it belongs to |that belongs to )?([A-Z][a-z]+)'?s?(?: \w+)?",t)
        if m: return {'owner':m.group(1),'label':f"{m.group(1)}'s {thing}"}
        return None
    if topic.kind=='ask_person':
        return {'note':t[0].lower()+t[1:]} if len(t)>=3 else None
    return None

def extract(topic,text,cloud,timeout_s=None):
    text=(text or '').strip()
    if not text or topic.kind not in _SCHEMAS: return None
    if cloud is not None and getattr(cloud,'available',False):
        prompt=(f'Willie asked: "{template(topic)}" The person answered: "{text}". '
                f'Return JSON with {_ASK[topic.kind]}. If the answer does not contain it, return {{}}.')
        r=_capped(lambda: cloud.ask_sync(prompt,schema=_SCHEMAS[topic.kind]),timeout_s or config.ENGAGE_WORDS_TIMEOUT_S)
        if r is not None and getattr(r,'parse_success',False) and isinstance(r.payload,dict):
            out={k:v for k,v in r.payload.items() if k in ('name','room','label','owner','note') and v}
            if out: return out
    return _offline(topic,text)
```

- [ ] **Step 5: Run to verify they pass**

Run: `python "$TMP/shim_run.py" -q tests/test_engage_words.py`
Expected: PASS. If `test_extract_unusable_is_none` fails on "I don't know what you mean by that", it is the greet_stranger regex accepting "I": the `fullmatch` requires the whole utterance to be a name phrase, so that sentence must return None — fix the regex, not the test.

- [ ] **Step 6: Commit**

```bash
git add engage_words.py config.py tests/test_engage_words.py
git commit -m "Engagement words: cloud line with template fallback, answer extraction (FR-2400)"
```

---

### Task 3: The decision rules

**Files:**
- Create: `engage.py`
- Modify: `config.py` (add the `ENGAGE_*` rule constants next to Task 2's block)
- Test: `tests/test_engage.py`

**Interfaces:**
- Consumes: Task 1 `MemoryStore.things`, `person_notes`, `last_experience`; Task 2 `engage_words.when_words`.
- Produces:
  - `engage.FaceSeen(band, name, bearing_deg)` — namedtuple; `band` is `identity.RECOGNISED|UNCERTAIN|UNKNOWN`.
  - `engage.Topic(kind, subject, facts, question, bearing_deg)` — namedtuple.
  - `engage.bearing_of(det) -> float` — degrees, + = left.
  - `engage.Engagement(memory, clock=time.time)` with
    `tick(state, dets, faces, pose, room, busy, prev_seen) -> Topic|None`
    - `dets`: list of detection dicts (`class`, `bbox`, `frame_w`) or `[]`
    - `faces`: list of `FaceSeen`, or `None` when no NEW face scan arrived this tick
    - `pose`: object with `.x .y` or None; `room`: room name or None
    - `busy`: bool
    - `prev_seen`: dict from Task 4 — keys `'thing:<kind>@<room>'` and `'saw:<name>'`, values previous last-seen time or None (never seen there); only keys sighted since the last tick.

- [ ] **Step 1: Add config**

```python
# FR-2400 engagement rules (2026-10-15, owner: idle + roaming, moderate, all four topic kinds,
# friendly to strangers). See docs/superpowers/specs/2026-10-15-engagement-design.md.
ENABLE_ENGAGEMENT=True
ENGAGE_STATES=('IDLE','ROAM','SLOW')
ENGAGE_GAP_S=300.0              # at most one non-greeting topic this often
ENGAGE_VISIT_S=1800.0           # unseen this long = the next sighting is a new visit (greet again)
ENGAGE_STRANGER_CONFIRM_N=3     # consecutive face scans with an UNKNOWN face before he says hello
ENGAGE_ASK_ROOM_GAP_S=3600.0
ENGAGE_ASK_PERSON_AFTER_S=120.0 # greeted this long ago and still here -> may ask about their day
ENGAGE_CALLBACK_MIN_H=2.0       # 'last time I saw you' only if it was at least this long ago
ENGAGE_MISSING_H=4.0            # a thing usually here, unseen this long while he has looked
ENGAGE_LOOK_ROOM_S=60.0         # ...and he has been in this room at least this long
ENGAGE_THING_CLASSES=('sports ball','frisbee','teddy bear','cup','bottle','wine glass','bowl','backpack',
                      'handbag','suitcase','umbrella','cell phone','remote','laptop','book','scissors',
                      'kite','skateboard')
ENGAGE_TURN_MIN_DEG=15.0
ENGAGE_MAX_S=20.0
ENGAGE_LOOK_S=2.0               # IDLE: run a detection this often for engagement
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_engage.py
import os,sys,time,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import config
from engage import Engagement,FaceSeen,Topic,bearing_of
from identity import RECOGNISED,UNCERTAIN,UNKNOWN
from memory_store import MemoryStore

T0=time.mktime((2026,10,15,10,0,0,0,0,-1))
P=types.SimpleNamespace(x=1.0,y=2.0)

class Clock:
    def __init__(self,t=T0): self.t=t
    def __call__(self): return self.t

def det(cls,cx=0.5): return {'class':cls,'bbox':(cx*1280-20,300,cx*1280+20,400),'frame_w':1280,'frame_h':720}
def me(name='Howard',bearing=0.0): return FaceSeen(RECOGNISED,name,bearing)
def stranger(): return FaceSeen(UNKNOWN,None,5.0)

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    clk=Clock(); m=MemoryStore('e.db')
    return Engagement(m,clock=clk),m,clk

def tick(e,state='IDLE',dets=(),faces=None,room=None,busy=False,prev=None):
    return e.tick(state,list(dets),faces,P,room,busy,prev or {})

def test_bearing_of():
    assert bearing_of(det('cup',0.5))==pytest.approx(0.0)
    assert bearing_of(det('cup',0.0))==pytest.approx(config.CAM_FRONT_HFOV_DEG/2)    # left edge = +
    assert bearing_of(det('cup',1.0))==pytest.approx(-config.CAM_FRONT_HFOV_DEG/2)

def test_greets_a_known_person_once_per_visit(env):
    e,m,clk=env
    t=tick(e,faces=[me()])
    assert t.kind=='greet_known' and t.facts['name']=='Howard' and not t.question
    clk.t+=60; assert tick(e,faces=[me()]) is None                       # same visit
    clk.t+=config.ENGAGE_VISIT_S+1; assert tick(e,faces=[me()]).kind=='greet_known'   # new visit

def test_greet_once_after_restart(env,tmp_path):
    e,m,clk=env
    assert tick(e,faces=[me()]).kind=='greet_known'
    e2=Engagement(m,clock=clk); clk.t+=5
    assert tick(e2,faces=[me()]).kind=='greet_known'                     # one greeting, not a storm
    clk.t+=5; assert tick(e2,faces=[me()]) is None

def test_greeting_mentions_last_time_when_long_ago(env):
    e,m,clk=env
    t=tick(e,faces=[me()],prev={'saw:Howard':T0-5*3600})
    assert t.facts.get('about')=='back' and t.facts['when']

def test_two_known_faces_greeted_one_per_tick(env):
    e,m,clk=env
    both=[me('Howard'),me('Carolyn')]
    a=tick(e,faces=both); b=tick(e,faces=both); c=tick(e,faces=both)
    assert {a.facts['name'],b.facts['name']}=={'Howard','Carolyn'} and c is None

def test_stranger_needs_three_scans_and_is_asked_once(env):
    e,m,clk=env
    assert tick(e,faces=[stranger()]) is None
    assert tick(e,faces=[stranger()]) is None
    t=tick(e,faces=[stranger()])
    assert t.kind=='greet_stranger' and t.question
    for _ in range(5): assert tick(e,faces=[stranger()]) is None
    assert tick(e,faces=None) is None                                    # no new scan: no change

def test_uncertain_face_is_silent(env):
    e,m,clk=env
    for _ in range(5): assert tick(e,faces=[FaceSeen(UNCERTAIN,'Howard',0.0)]) is None

def test_nothing_in_other_states_or_when_busy(env):
    e,m,clk=env
    for st in ('AVOID','STUCK','RETRIEVE','WAVE','ROTATE','ENGAGE'):
        assert tick(e,state=st,faces=[me()]) is None
    assert tick(e,faces=[me()],busy=True) is None
    assert tick(e,state='ROAM',faces=[me()]).kind=='greet_known'

def test_no_person_no_questions(env):
    e,m,clk=env
    assert tick(e,dets=[det('sports ball')]) is None
    t=tick(e,dets=[det('sports ball',0.2),det('person')])
    assert t.kind in ('ask_room','ask_thing')

def test_ask_room_in_an_unnamed_spot_once_an_hour(env):
    e,m,clk=env
    t=tick(e,dets=[det('person')])
    assert t.kind=='ask_room' and t.question
    clk.t+=config.ENGAGE_GAP_S+1; assert tick(e,dets=[det('person')]) is None
    clk.t+=config.ENGAGE_ASK_ROOM_GAP_S; P.x+=3
    assert tick(e,dets=[det('person')]).kind=='ask_room'; P.x-=3

def test_ask_thing_then_gap_then_no_repeat_today(env):
    e,m,clk=env
    t=tick(e,dets=[det('sports ball',0.2),det('person')],room='kitchen')
    assert t.kind=='ask_thing' and t.facts['thing']=='sports ball' and t.question
    assert t.bearing_deg==pytest.approx(bearing_of(det('sports ball',0.2)))
    clk.t+=10; assert tick(e,dets=[det('cup'),det('person')],room='kitchen') is None   # 5-min gap
    clk.t+=config.ENGAGE_GAP_S
    assert tick(e,dets=[det('cup'),det('person')],room='kitchen').facts['thing']=='cup'
    clk.t+=config.ENGAGE_GAP_S+1
    assert tick(e,dets=[det('sports ball'),det('person')],room='kitchen') is None      # said today

def test_a_named_thing_is_not_asked_about(env):
    e,m,clk=env
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball")
    assert tick(e,dets=[det('sports ball'),det('person')],room='kitchen') is None

def test_said_today_resets_at_midnight(env):
    e,m,clk=env
    clk.t=time.mktime((2026,10,15,23,59,0,0,0,-1))
    assert tick(e,dets=[det('cup'),det('person')],room='den').kind=='ask_thing'
    clk.t=time.mktime((2026,10,16,0,6,0,0,0,-1))
    assert tick(e,dets=[det('cup'),det('person')],room='den').kind=='ask_thing'

def test_callback_for_a_named_thing_back_after_hours(env):
    e,m,clk=env
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball",at=T0-6*3600)
    t=tick(e,dets=[det('sports ball'),det('person')],room='kitchen',
           prev={'thing:sports ball@kitchen':T0-6*3600})
    assert t.kind=='callback' and t.facts['about']=='thing' and t.facts['label']=="Storm's ball"

def test_callback_for_a_note_about_a_greeted_person(env):
    e,m,clk=env
    m.add_person_note('Howard','were fixing the arm',at=T0-86400)
    assert tick(e,faces=[me()]).kind=='greet_known'
    clk.t+=config.ENGAGE_GAP_S+1
    t=tick(e,faces=[me()])
    assert t.kind=='callback' and t.facts['about']=='note' and 'arm' in t.facts['note']

def test_change_new_here(env):
    e,m,clk=env
    m.name_thing('backpack','hall',None,'the blue backpack',at=T0-86400)
    t=tick(e,dets=[det('backpack'),det('person')],room='kitchen',prev={'thing:backpack@kitchen':None})
    assert t.kind=='change' and t.facts['about']=='new' and t.facts['room']=='kitchen'

def test_change_missing_needs_time_in_the_room(env):
    e,m,clk=env
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball",at=T0-8*3600)
    assert tick(e,dets=[det('person')],room='kitchen') is None           # just arrived
    clk.t+=config.ENGAGE_LOOK_ROOM_S+1
    t=tick(e,dets=[det('person')],room='kitchen')
    assert t.kind=='change' and t.facts['about']=='missing' and t.facts['label']=="Storm's ball"

def test_ask_person_after_greeting(env):
    e,m,clk=env
    tick(e,faces=[me()])
    clk.t+=config.ENGAGE_ASK_PERSON_AFTER_S-1; assert tick(e,faces=[me()]) is None
    clk.t+=config.ENGAGE_GAP_S
    t=tick(e,faces=[me()])
    assert t.kind=='ask_person' and t.question and t.facts['name']=='Howard'

def test_greeting_ignores_the_gap(env):
    e,m,clk=env
    assert tick(e,dets=[det('cup'),det('person')],room='den').kind=='ask_thing'
    clk.t+=5; assert tick(e,faces=[me()]).kind=='greet_known'
```

- [ ] **Step 3: Run to verify they fail**

Run: `python "$TMP/shim_run.py" -q tests/test_engage.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'engage'`

- [ ] **Step 4: Implement `engage.py`**

```python
"""FR-2400 engagement (2026-10-15, owner): greet people, ask about and remark on what he sees and
remembers. Pure decisions -- no I/O but memory reads; brain.py acts on the Topic returned.

Rules in priority order (spec §2.1): greet_known, greet_stranger, ask_room, ask_thing, callback,
change, ask_person. Greetings ignore the ENGAGE_GAP_S gap; everything else needs a person in view
and the gap. Choosing a topic records it as said today, spoken or not."""
import collections,time
import config
from identity import RECOGNISED,UNKNOWN
from engage_words import when_words

FaceSeen=collections.namedtuple('FaceSeen','band name bearing_deg')
Topic=collections.namedtuple('Topic','kind subject facts question bearing_deg')

def bearing_of(det):
    x1,_,x2,_=det['bbox']; w=det.get('frame_w') or 1280
    return (0.5-((x1+x2)/2)/w)*config.CAM_FRONT_HFOV_DEG

class Engagement:
    def __init__(self,memory,clock=time.time):
        self.m=memory; self.clock=clock
        self._seen={}            # name -> last time in view (visit tracking)
        self._greeted={}         # name -> when greeted this visit
        self._unknown_run=0; self._stranger_t=-1e18
        self._said=set(); self._said_day=None
        self._gap_t=-1e18; self._ask_room_t=-1e18
        self._room=None; self._room_since=0.0

    def _day(self,now): return time.localtime(now)[:3]

    def _fresh(self,kind,subject,now):
        if self._said_day!=self._day(now): self._said=set(); self._said_day=self._day(now)
        return (kind,subject) not in self._said

    def _pick(self,now,topic,greeting=False):
        self._said.add((topic.kind,topic.subject))
        if not greeting: self._gap_t=now
        return topic

    def tick(self,state,dets,faces,pose,room,busy,prev_seen):
        now=self.clock()
        if room!=self._room: self._room=room; self._room_since=now
        known=[f for f in (faces or []) if f.band==RECOGNISED and f.name]
        if faces is not None:   # a new scan: track visits and strangers
            for f in known: self._seen.setdefault(f.name,now)
            self._unknown_run=(self._unknown_run+1 if any(f.band==UNKNOWN for f in faces) else 0)
        if state not in config.ENGAGE_STATES or busy:
            for f in known: self._seen[f.name]=now
            return None
        t=self._greet(now,known,prev_seen) or self._stranger(now,faces)
        for f in known: self._seen[f.name]=now
        if t: return t
        person=bool(known) or any(d.get('class')=='person' for d in dets) or bool(faces)
        if not person or now-self._gap_t<config.ENGAGE_GAP_S: return None
        for rule in (self._ask_room,self._ask_thing,self._callback,self._change,self._ask_person):
            t=rule(now,dets,known,pose,room,prev_seen)
            if t: return self._pick(now,t)
        return None

    # --- 1, 2: greetings ---
    def _greet(self,now,known,prev_seen):
        for f in known:
            last=self._seen.get(f.name)
            g=self._greeted.get(f.name)
            new_visit=g is None or (last is not None and now-last>config.ENGAGE_VISIT_S)
            if not new_visit: continue
            self._greeted[f.name]=now
            facts={'name':f.name}
            before=prev_seen.get(f'saw:{f.name}')
            if before and now-before>=config.ENGAGE_CALLBACK_MIN_H*3600:
                facts.update(about='back',when=when_words(before,now))
            return self._pick(now,Topic('greet_known',f.name,facts,False,f.bearing_deg),greeting=True)
        return None

    def _stranger(self,now,faces):
        if (faces and self._unknown_run>=config.ENGAGE_STRANGER_CONFIRM_N
                and now-self._stranger_t>config.ENGAGE_VISIT_S):
            self._stranger_t=now; self._unknown_run=0
            f=next(f for f in faces if f.band==UNKNOWN)
            return self._pick(now,Topic('greet_stranger','stranger',{},True,f.bearing_deg),greeting=True)
        return None

    # --- 3..7 ---
    def _ask_room(self,now,dets,known,pose,room,prev):
        if room is not None or pose is None or now-self._ask_room_t<config.ENGAGE_ASK_ROOM_GAP_S: return None
        cell=f'{round(pose.x)},{round(pose.y)}'
        if not self._fresh('ask_room',cell,now): return None
        self._ask_room_t=now
        return Topic('ask_room',cell,{},True,None)

    def _things_in_view(self,dets):
        return [d for d in dets if d.get('class') in config.ENGAGE_THING_CLASSES]

    def _ask_thing(self,now,dets,known,pose,room,prev):
        for d in self._things_in_view(dets):
            kind=d['class']; subject=f'{kind}@{room}'
            if any(r.get('label') for r in self.m.things(kind,room)): continue
            if not self._fresh('ask_thing',subject,now): continue
            return Topic('ask_thing',subject,{'thing':kind,'room':room},True,bearing_of(d))
        return None

    def _callback(self,now,dets,known,pose,room,prev):
        long_ago=config.ENGAGE_CALLBACK_MIN_H*3600
        for d in self._things_in_view(dets):
            kind=d['class']; before=prev.get(f'thing:{kind}@{room}')
            if not before or now-before<long_ago: continue
            rows=[r for r in self.m.things(kind,room) if r.get('label')]
            if rows and self._fresh('callback',f'{kind}@{room}',now):
                return Topic('callback',f'{kind}@{room}',{'about':'thing','label':rows[0]['label'],
                             'when':when_words(before,now)},False,bearing_of(d))
        for f in known:
            g=self._greeted.get(f.name)
            if g is None or now-g<1: continue
            notes=self.m.person_notes(f.name,n=1)
            if notes and self._fresh('callback',f'note:{f.name}',now):
                return Topic('callback',f'note:{f.name}',{'about':'note','name':f.name,'note':notes[0]['note']},
                             False,f.bearing_deg)
        return None

    def _change(self,now,dets,known,pose,room,prev):
        if room is None: return None
        for d in self._things_in_view(dets):
            kind=d['class']; key=f'thing:{kind}@{room}'
            if key in prev and prev[key] is None and self.m.things(kind,any_room=True) \
                    and any(r['room']!=room for r in self.m.things(kind,any_room=True)) \
                    and self._fresh('change',f'new:{kind}@{room}',now):
                return Topic('change',f'new:{kind}@{room}',{'about':'new','thing':kind,'room':room},False,bearing_of(d))
        if now-self._room_since<config.ENGAGE_LOOK_ROOM_S: return None
        here={d['class'] for d in dets}
        for r in self.m.things(room=room):
            if (r.get('label') and r['kind'] not in here
                    and now-r['last_seen']>=config.ENGAGE_MISSING_H*3600
                    and self._fresh('change',f"missing:{r['kind']}@{room}",now)):
                return Topic('change',f"missing:{r['kind']}@{room}",{'about':'missing','label':r['label'],
                             'room':room,'when':when_words(r['last_seen'],now)},False,None)
        return None

    def _ask_person(self,now,dets,known,pose,room,prev):
        for f in known:
            g=self._greeted.get(f.name)
            if g is None or now-g<config.ENGAGE_ASK_PERSON_AFTER_S: continue
            if self._fresh('ask_person',f.name,now):
                return Topic('ask_person',f.name,{'name':f.name},True,f.bearing_deg)
        return None
```

Notes for the implementer:
- `test_two_known_faces_greeted_one_per_tick`: `_greet` returns after the first new-visit face, so the second is greeted next tick — by design.
- `test_greet_once_after_restart`: a fresh `Engagement` has an empty `_greeted`, so the first sighting after a restart greets once; `_greeted` then blocks repeats.
- `test_callback_for_a_note_about_a_greeted_person`: the note rule needs the person greeted before this tick (`now-g>=1`), so the greeting comes first.

- [ ] **Step 5: Run to verify they pass**

Run: `python "$TMP/shim_run.py" -q tests/test_engage.py`
Expected: PASS. Fix code, not tests, unless a test contradicts the spec (then stop and report).

- [ ] **Step 6: Commit**

```bash
git add engage.py config.py tests/test_engage.py
git commit -m "Engagement rules: greetings, questions, callbacks, changes (FR-2400)"
```

---

### Task 4: Sightings feed `prev_seen`; one detection shared with the camera brake

**Files:**
- Modify: `brain.py` — `_note_sightings` (around line 1907), `_camera_front_cm` (the `detect(classes=…)` call around line 2470)
- Modify: `recognition.py` — `_loop` records `self.frame_w`
- Test: `tests/test_engage_brain.py` (out-of-process, created here, extended in Task 5)

**Interfaces:**
- Consumes: Task 1 `MemoryStore.upsert_thing`, `last_experience`.
- Produces:
  - `RoverBrain._note_sightings(dets) -> None` now also records things and merges into `self._engage_prev` (dict, same keys as Task 3's `prev_seen`).
  - `RoverBrain._last_dets` — `(time, dets)` of the latest full-class detection.
  - `FaceRecognizer.frame_w` — int width of the last scanned frame (default 1280).

- [ ] **Step 1: Write the failing test** (out-of-process, like `tests/test_stuck_ai_fallback_chain.py`)

```python
# tests/test_engage_brain.py
import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _run(script):
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',script],cwd=_REPO_ROOT,env=env,capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
    assert 'OK' in r.stdout

_COMMON=r'''
import types,time,tempfile,config
config.WILLY_MEMORY_ROOT=tempfile.mkdtemp()
from brain import RoverBrain
from memory_store import MemoryStore
def det(cls): return {'class':cls,'bbox':(600,300,680,400),'frame_w':1280,'frame_h':720}
def brain():
    b=types.SimpleNamespace(memory=MemoryStore('b.db'),_engage_prev={},
        world_model=types.SimpleNamespace(get_robot_pose=lambda: types.SimpleNamespace(x=0.0,y=0.0),
                                          get_room=lambda x,y: types.SimpleNamespace(name='kitchen')),
        _experience=lambda kind,what: b.memory.add_experience(kind,what),
        _called=lambda c: 'Storm' if c=='dog' else c)
    for n in ('_note_sightings',):
        setattr(b,n,types.MethodType(getattr(RoverBrain,n),b))
    return b
'''

def test_sightings_record_things_and_previous_times():
    _run(_COMMON+r'''
b=brain()
b._note_sightings([det('sports ball'),det('chair')])
assert b._engage_prev=={'thing:sports ball@kitchen':None}, b._engage_prev
assert b.memory.things('sports ball','kitchen')
assert not b.memory.things('chair','kitchen')
b._engage_prev.clear(); b.__dict__['_sighted']={}
b._note_sightings([det('sports ball')])
assert b._engage_prev['thing:sports ball@kitchen'] is not None
b._engage_prev.clear(); b.__dict__['_sighted']={}
b._note_sightings([det('dog')])
assert 'saw:Storm' in b._engage_prev
print('OK')
''')
```

- [ ] **Step 2: Run to verify it fails**

Run (CI or Linux; on Windows it fails on pygame — that is the baseline, not this test): `pytest tests/test_engage_brain.py -v`
Expected on Linux: FAIL — `AssertionError: {}`

- [ ] **Step 3: Implement**

Replace `_note_sightings` in `brain.py`:

```python
    def _note_sightings(self,dets):
        """Remember seeing a person or a dog -- at most once per EXPERIENCE_SIGHTING_GAP_S each.
        2026-10-15 (FR-2400): movable things too (memory.things), and the time each was last seen
        BEFORE this sighting goes to self._engage_prev for engagement ('back after hours',
        'new here'). Read before the update, or every sighting would look fresh."""
        now=time.time(); last=self.__dict__.setdefault('_sighted',{})
        prev=self.__dict__.setdefault('_engage_prev',{})
        room=None
        try:
            p=self.world_model.get_robot_pose(); r=self.world_model.get_room(p.x,p.y); room=r.name if r else None
        except Exception: pass
        for d in dets:
            c=d.get('class')
            if c in config.ENGAGE_THING_CLASSES:
                key=f'thing:{c}@{room}'
                if now-last.get(key,0.0)>=config.EXPERIENCE_SIGHTING_GAP_S:
                    last[key]=now
                    try: prev[key]=self.memory.upsert_thing(c,room,at=now)
                    except Exception: log.warning('Thing sighting not recorded',exc_info=True)
                continue
            if c not in config.EXPERIENCE_SIGHT_CLASSES: continue
            if now-last.get(c,0.0)<config.EXPERIENCE_SIGHTING_GAP_S: continue
            last[c]=now
            name=self._called(c)
            try:
                e=self.memory.last_experience(name,'saw'); prev[f'saw:{name}']=e['at'] if e else None
            except Exception: pass
            self._experience('saw',name)
```

In `_camera_front_cm`, replace the detect call so one detection serves both:

```python
            dets=self.detector.detect()             # all classes: the brake filters, engagement reads all (2026-10-15)
            self._last_dets=(time.time(),dets)
            cm=arm_ik.obstacle_cm([d for d in dets if d.get('class') in config.CAMERA_BRAKE_CLASSES])
```

In `recognition.py` `_loop`, record the frame width before embedding:

```python
                frame=self._frame_source()
                if frame is not None: self.frame_w=int(frame.shape[1])
                faces=self.embed(frame)
```

and in `__init__`: `self.frame_w=1280`.

Check `tests/test_camera_brake_roam.py` still passes: its fake detector must accept `detect()` with no `classes` argument — if the fake requires `classes`, give its parameter a default of `None` (test-fake change only).

- [ ] **Step 4: Run tests**

Run: `python "$TMP/shim_run.py" -q tests/test_camera_brake_roam.py tests/test_experiences.py tests/test_storm_and_toys.py` (Windows) and let CI run `tests/test_engage_brain.py`.
Expected: PASS (Windows ones); CI green.

- [ ] **Step 5: Commit, push, check CI**

```bash
git add brain.py recognition.py tests/test_engage_brain.py tests/test_camera_brake_roam.py
git commit -m "Sightings record things and previous times for engagement; brake shares one detection (FR-2400)"
git push
```

---

### Task 5: The ENGAGE state in the brain

**Files:**
- Modify: `brain.py` — `__init__` (create `self.engage`), `_tick` (call `_engage_step` before the state dispatch), the dispatch dict (add `'ENGAGE':self._engage_tick`), `_idle` (remove `_face_tick` call), `_face_tick` (keep scanning/matching only; remove greeting and stranger code), `_go` (face scanning on in `ENGAGE_STATES` and `ENGAGE`), the voice-stop branch (cancel engagement), new methods `_engage_step`, `_start_engage`, `_engage_tick`, `_engage_say`, `_engage_answer`, `_engage_store`, `_engage_end`.
- Modify: `voice.py` — `VoicePipeline.busy` property.
- Test: extend `tests/test_engage_brain.py`

**Interfaces:**
- Consumes: Task 3 `Engagement.tick`, `Topic`, `FaceSeen`; Task 2 `engage_words.line`, `extract`; Task 4 `_engage_prev`, `_last_dets`, `faces.frame_w`; existing `start_rotation(degrees, then)`, `voice.speak`, `voice.prompt_listen(cb, timeout_s)`, `voice.set_current_person(name)`, `world_model.add_room/save`, `identity.match/note_seen/names/add_vector`.
- Produces: state `'ENGAGE'`; `RoverBrain._engage_end(reason)`.

- [ ] **Step 1: Add `VoicePipeline.busy`** in `voice.py` after `available`:

```python
    @property
    def busy(self):
        """2026-10-15 (FR-2400): speaking, recording or answering, or a prompted listen is open --
        engagement must not start a new remark on top."""
        return (self._speaking.is_set() or getattr(self,'_prompt',None) is not None
                or getattr(self,'_in_utterance',False) or not self._speak_queue.empty())
```

and in `_handle_wake`, wrap the existing body so `_in_utterance` is set for the whole handling:

```python
    def _handle_wake(self,stream,frame_len,t_wake,on_text=None):
        if self.display: self.display.update_state(state='listening',status='Listening...')
        self._set_listening(True); self._in_utterance=True
        try: self._capture_utterance(stream,frame_len,t_wake,on_text)
        finally: self._set_listening(False); self._in_utterance=False
```

- [ ] **Step 2: Write the failing brain tests** (append to `tests/test_engage_brain.py`)

```python
_ENGAGE=_COMMON+r'''
from engage import Topic
said=[]; prompts=[]; rot=[]
def b2(state='ROAM',rotate_ok=True):
    b=brain()
    b._state=state; b._engage_topic=None; b._engage_prev_state=None
    b.voice=types.SimpleNamespace(available=True,busy=False,speak=said.append,
        prompt_listen=lambda cb,t: prompts.append(cb),set_current_person=lambda n: None)
    b.cloud_ai=None
    b.safety=types.SimpleNamespace(stop=lambda: None,emergency_stop=lambda why: None)
    def start_rotation(deg,then='IDLE'):
        rot.append((deg,then)); return (rotate_ok,'' if rotate_ok else 'blocked')
    b.start_rotation=start_rotation
    went=[]; b._go=lambda s: (went.append(s),setattr(b,'_state',s)); b.went=went
    b._upd=lambda *a,**k: None
    for n in ('_start_engage','_engage_tick','_engage_say','_engage_answer','_engage_store','_engage_end'):
        setattr(b,n,types.MethodType(getattr(RoverBrain,n),b))
    return b
def wait(b):
    for _ in range(100):
        if getattr(b,'_engage_thread',None) is None or not b._engage_thread.is_alive(): return
        time.sleep(0.02)
'''

def test_roam_stops_turns_speaks_and_resumes():
    _run(_ENGAGE+r'''
b=b2('ROAM')
b._start_engage(Topic('ask_thing','sports ball@kitchen',{'thing':'sports ball','room':'kitchen'},True,30.0))
assert rot==[(30.0,'ENGAGE')], rot                      # turned toward it via Rotation
b._state='ENGAGE'; b._engage_tick({},0.0); wait(b)
assert said==['Whose sports ball is that?'] and len(prompts)==1
prompts[0]("It's Storm's"); wait(b)
assert b.memory.things('sports ball','kitchen')[0]['label']=="Storm's sports ball"
b._engage_tick({},0.0)
assert b.went[-1]=='ROAM', b.went
print('OK')
''')

def test_refused_turn_still_speaks():
    _run(_ENGAGE+r'''
b=b2('IDLE',rotate_ok=False)
b._start_engage(Topic('greet_known','Howard',{'name':'Howard'},False,40.0))
assert b._state=='ENGAGE'
b._engage_tick({},0.0); wait(b)
assert said and said[0].startswith(('Hi','Hello','Hey'))
b._engage_tick({},0.0); assert b.went[-1]=='IDLE'
print('OK')
''')

def test_answer_after_stop_is_ignored():
    _run(_ENGAGE+r'''
b=b2('IDLE')
b._start_engage(Topic('ask_room','0,0',{},True,None))
b._engage_tick({},0.0); wait(b)
b._engage_end('voice stop')
prompts[0]('This is the kitchen'); wait(b)
assert not hasattr(b.world_model,'added'), 'stored after stop'
assert said==['What room is this?'] or said==["Can you tell me what room I'm in?"]
print('OK')
''')

def test_engage_times_out():
    _run(_ENGAGE+r'''
b=b2('IDLE')
b._start_engage(Topic('ask_room','0,0',{},True,None))
b._engage_tick({},0.0); wait(b)
b._engage_t0-=config.ENGAGE_MAX_S+1
b._engage_tick({},0.0)
assert b.went[-1]=='IDLE'
print('OK')
''')

def test_stranger_danger_is_gone():
    src=open(os.path.join(_REPO_ROOT,'brain.py'),encoding='utf8').read()
    assert 'Stranger danger' not in src
```

- [ ] **Step 3: Run to verify they fail** (CI / Linux): `pytest tests/test_engage_brain.py -v`
Expected: FAIL — `AttributeError: type object 'RoverBrain' has no attribute '_start_engage'`

- [ ] **Step 4: Implement in `brain.py`**

`__init__`, after `self.identity` and `self.memory` exist:

```python
        # FR-2400 engagement (2026-10-15) -- engage.py decides, _engage_* act.
        from engage import Engagement
        self.engage=Engagement(self.memory)
        self._engage_topic=None; self._engage_prev_state=None; self._engage_thread=None
        self._engage_prev={}; self._engage_look_t=0.0; self._last_dets=(0.0,[])
```

Dispatch dict: add `'ENGAGE':self._engage_tick,`.

`_tick`: immediately before the state-dispatch dict lookup, add:

```python
        if config.ENABLE_ENGAGEMENT and self._state in config.ENGAGE_STATES:
            try: self._engage_step()
            except Exception: log.warning('Engagement step failed',exc_info=True)
```

`_idle`: delete the line `self._face_tick()` (faces are read in `_engage_step` now; when engagement is disabled, call `self._face_tick()` from `_engage_step`'s early return — see below).

Replace `_face_tick` with a reader that returns `FaceSeen`s and keeps the presence bookkeeping:

```python
    def _face_tick(self):
        """FR-2100 matching + presence; greetings moved to engage.py (FR-2400, 2026-10-15).
        Returns [FaceSeen] for a NEW scan, or None when no new scan arrived."""
        if not self.faces.available: return None
        self.faces.set_scanning(True)
        res=self.faces.latest()
        if res is None: return None
        from engage import FaceSeen
        _,faces=res; out=[]; w=getattr(self.faces,'frame_w',1280) or 1280
        pose=self.world_model.get_robot_pose(); room=self.world_model.get_room(pose.x,pose.y)
        for box,vec in faces:
            m=self.identity.match(vec)
            x,_,bw,_=box; bearing=(0.5-(x+bw/2)/w)*config.CAM_FRONT_HFOV_DEG
            if m.band==RECOGNISED:
                self.identity.note_seen(m.name,room.name if room else None)
                self.voice.set_current_person(m.name)
            elif m.band==UNCERTAIN:
                self._face_last_uncertain=(time.time(),vec)
            out.append(FaceSeen(m.band,m.name if m.band==RECOGNISED else None,bearing))
        return out
```

Delete `_stranger_answer` and every reference to `_face_asking`, `_face_asked_t`, `_face_unknown_run` (grep for them; the enrol code keeps `_face_last_uncertain`).

New methods (put them after `_face_tick`):

```python
    def _engage_busy(self):
        try: priv=not privacy.mic_enabled()
        except Exception: priv=False
        return (priv or getattr(self.voice,'busy',False) or not self.voice.available
                or getattr(self,'_bat_tier','normal')!='normal' or self._engage_topic is not None)

    def _engage_step(self):
        faces=self._face_tick()
        if not config.ENABLE_ENGAGEMENT: return
        now=time.time()
        if self._state=='IDLE' and now-self._engage_look_t>=config.ENGAGE_LOOK_S:
            self._engage_look_t=now
            try:
                dets=self.detector.detect(); self._last_dets=(now,dets); self._note_sightings(dets)
            except Exception: log.warning('Engagement look failed',exc_info=True)
        t,dets=self._last_dets
        dets=dets if now-t<=2*config.ENGAGE_LOOK_S else []
        pose=self.world_model.get_robot_pose(); r=self.world_model.get_room(pose.x,pose.y)
        prev=self._engage_prev; self._engage_prev={}
        topic=self.engage.tick(self._state,dets,faces,pose,r.name if r else None,self._engage_busy(),prev)
        if topic is not None: self._start_engage(topic)

    def _start_engage(self,topic):
        log_event(log,'ENGAGE',subsystem='engage',kind=topic.kind,subject=topic.subject,status='start')
        self._engage_topic=topic; self._engage_prev_state=self._state
        self._engage_t0=time.time(); self._engage_phase='say'; self._engage_answer_text=None
        if self._state in ('ROAM','SLOW'): self.safety.stop()
        b=topic.bearing_deg
        if b is not None and abs(b)>=config.ENGAGE_TURN_MIN_DEG:
            ok,msg=self.start_rotation(b,then='ENGAGE')
            if ok: return
            log.info(f'Engage: not turning ({msg}); speaking from here')
        self._go('ENGAGE')

    def _engage_tick(self,d,tilt):
        self._upd('idle','',d,tilt)
        t=self._engage_topic
        if t is None: return self._engage_end('no topic')
        if time.time()-self._engage_t0>config.ENGAGE_MAX_S: return self._engage_end('timed out')
        if self._engage_phase=='say':
            self._engage_phase='talking'
            import threading
            self._engage_thread=threading.Thread(target=self._engage_say,args=(t,),daemon=True,name='engage')
            self._engage_thread.start(); return
        if self._engage_phase=='done' and not getattr(self.voice,'busy',False):
            self._engage_end('done')

    def _engage_say(self,t):
        import engage_words
        try:
            text=engage_words.line(t,getattr(self,'cloud_ai',None))
            self.voice.speak(text)
            log.info(f'ENGAGE said kind={t.kind} subject={t.subject}: {text!r}')
            if t.question:
                self._engage_phase='listening'
                self.voice.prompt_listen(lambda ans,t=t: self._engage_answer(t,ans),config.FACE_ASK_TIMEOUT_S)
                return
        except Exception: log.warning('Engage: saying failed',exc_info=True)
        self._engage_phase='done'

    def _engage_answer(self,t,text):
        if self._engage_topic is not t:
            log.info(f'Engage answer ignored (topic ended): {text!r}'); return
        import threading
        def work():
            try: self._engage_store(t,text)
            except Exception: log.warning('Engage: storing failed',exc_info=True)
            finally: self._engage_phase='done'
        self._engage_thread=threading.Thread(target=work,daemon=True,name='engage-answer'); self._engage_thread.start()

    def _engage_store(self,t,text):
        import engage_words
        if not text:
            log.info(f'ENGAGE answered=no kind={t.kind}'); return
        data=engage_words.extract(t,text,getattr(self,'cloud_ai',None))
        if self._engage_topic is not t: return
        if not data:
            log.info(f'Engage answer not used: {t.kind} heard {text!r}'); return
        log.info(f'ENGAGE stored kind={t.kind} {data}')
        if t.kind=='greet_stranger':
            name=data['name']
            if name in self.identity.names(include_pending=False):
                self.voice.set_current_person(name); self.voice.speak(f"Oh, hi {name}! Sorry, I didn't recognise you.")
            else:
                self.voice.set_current_person(name); self._experience('met',name)
                self.voice.speak(f'Nice to meet you, {name}!')
        elif t.kind=='ask_room':
            pose=self.world_model.get_robot_pose()
            self.world_model.add_room(data['room'],pose.x,pose.y); self.world_model.save()
            self.voice.speak(f"Got it, this is the {data['room']}.")
        elif t.kind=='ask_thing':
            label=data.get('label') or f"the {t.facts.get('thing','thing')}"
            self.memory.name_thing(t.facts['thing'],t.facts.get('room'),data.get('owner'),label)
            self.voice.speak(f"Thanks, I'll remember that's {label}.")
        elif t.kind=='ask_person':
            self.memory.add_person_note(t.facts['name'],data['note'])
            self.voice.speak('Thanks for telling me.')

    def _engage_end(self,reason):
        t=self._engage_topic; self._engage_topic=None
        if t is not None: log_event(log,'ENGAGE',subsystem='engage',kind=t.kind,subject=t.subject,status=reason)
        back=self._engage_prev_state if self._engage_prev_state in config.ENGAGE_STATES else 'IDLE'
        if back in ('ROAM','SLOW') and not getattr(self,'_roam_permission',True): back='IDLE'
        if self._state=='ENGAGE': self._go('ROAM' if back=='SLOW' else back)
```

Voice-stop branch (the block that calls `self.safety.emergency_stop('voice stop')`): add before the emergency stop:

```python
            if self._engage_topic is not None: self._engage_end('voice stop')
```

`_go`: change the face-scanning line so scanning stays on in the engagement states:

```python
            if state=='IDLE': self._idle_t=0.0
            if getattr(self,'faces',None) is not None and state not in config.ENGAGE_STATES+('ENGAGE','ROTATE'):
                self.faces.set_scanning(False)   # FR-2400: scans run in IDLE/ROAM/SLOW (+ENGAGE) since 2026-10-15
```

In `tests/test_answer_after_stop_is_ignored` the fake `world_model` has no `add_room`; if the answer were stored, `add_room` would raise and be logged — the assertion that matters is that `_engage_answer` returns early (`topic ended`). Keep it.

Config: `ENGAGE_STATES` is a tuple, so `config.ENGAGE_STATES+('ENGAGE','ROTATE')` is valid.

`config.FACE_GREET_SESSION_S` stays (identity.greeting_due still reads it); `ENGAGE_VISIT_S` is the engagement window.

- [ ] **Step 5: Run tests**

Windows: `python "$TMP/shim_run.py" -q tests/test_engage.py tests/test_engage_words.py tests/test_memory_things.py tests/test_voice_reopen.py`
CI: everything, including `tests/test_engage_brain.py` and the existing face tests. Existing face tests that assert "Stranger danger" or `_stranger_answer` (grep `tests/` for `Stranger danger`, `_stranger_answer`, `_face_asking`) must be updated to the FR-2400 behaviour: a stranger gets `greet_stranger` from `engage.py`; a claimed enrolled name gets "Sorry, I didn't recognise you."
Expected: PASS.

- [ ] **Step 6: Commit, push, check CI**

```bash
git add brain.py voice.py tests/
git commit -m "Brain: ENGAGE state -- stop, turn, speak, listen, remember (FR-2400); stranger danger removed"
git push
```

---

### Task 6: What he's learned shows up in conversation

**Files:**
- Modify: `memory_store.py` `get_context_for` (around line 153)
- Modify: `brain.py` `_last_seen_reply` (labels of things)
- Test: append to `tests/test_memory_things.py`

**Interfaces:**
- Consumes: Task 1 tables.
- Produces: `get_context_for(query_text, person=None)` result dict gains `'things'` (labels mentioned in the query, up to 5) and `'notes'` (3 newest for `person`).

- [ ] **Step 1: Failing test**

```python
def test_context_includes_things_and_notes(tmp_path,monkeypatch):
    m=_store(tmp_path,monkeypatch)
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball",at=1.0)
    m.add_person_note('Howard','were fixing the arm')
    ctx=m.get_context_for("where is Storm's ball?",person='Howard')
    assert any("Storm's ball" in t for t in ctx['things'])
    assert ctx['notes']==['were fixing the arm']
```

- [ ] **Step 2: Run, expect FAIL** (`KeyError: 'things'`): `python "$TMP/shim_run.py" -q tests/test_memory_things.py`

- [ ] **Step 3: Implement** — at the end of `get_context_for`, before `return`:

```python
        # FR-2400 (2026-10-15): things he has been told about, and what this person told him.
        q=(query_text or '').lower()
        rows=self._conn.execute('SELECT kind,label,room FROM things WHERE label IS NOT NULL').fetchall()
        ctx['things']=[f'{lbl} ({kind}, usually in the {room})' if room else f'{lbl} ({kind})'
                       for kind,lbl,room in rows
                       if kind in q or any(w in q for w in lbl.lower().replace("'s",'').split() if len(w)>2)][:5]
        ctx['notes']=[n['note'] for n in self.person_notes(person,n=3)] if person else []
```

(Use the variable name the method already returns; if it builds the dict inline in `return {...}`, assign it to `ctx` first.)

In `brain._last_seen_reply`, before the "I don't remember seeing" return, try labelled things:

```python
        if not e:
            for r in self.memory.things(any_room=True):
                if r.get('label') and r['label'].lower()==what:
                    where=f" in the {r['room']}" if r.get('room') else ''
                    return f"I last saw {r['label']} {self._when(r['last_seen'])}{where}."
```

- [ ] **Step 4: Run, expect PASS**: `python "$TMP/shim_run.py" -q tests/test_memory_things.py tests/test_experiences.py`

- [ ] **Step 5: Commit**

```bash
git add memory_store.py brain.py tests/test_memory_things.py
git commit -m "Conversation context and 'when did you last see' use learned things and notes (FR-2400)"
git push
```

---

### Task 7: Docs, deploy, live check

**Files:**
- Modify: `docs/WildWilly_Functional_Requirements_v3.1.md` — new `FR-2400 Engagement` group (requirements FR-2400-001…007 = spec §2.1 rules 1-7, FR-2400-008 = the safety gates in spec §3), status register row `FR-2400 Engagement — built, not yet live-verified`; mark FR-2100-002/003 "superseded by FR-2400 (2026-10-15)".
- Modify: `docs/WildWilly_Software_Design_v1.0.md` — an "Engagement (FR-2400)" section: modules, rules table, ENGAGE state, prev_seen, words fallback.
- Modify: `docs/WildWilly_User_Guide.md` — "Willie starts conversations": what he says, how to answer after the beep (green circle), that answers are remembered, that `ENABLE_ENGAGEMENT=False` turns it off.

- [ ] **Step 1: Write the three doc sections** (text per the spec; keep each ≤ 40 lines).
- [ ] **Step 2: Commit and push; wait for CI green.**

```bash
git add docs/
git commit -m "Docs: FR-2400 engagement in the FRD, software design and user guide"
git push
```

- [ ] **Step 3: Pull on willie** — `ssh hhimmel@willie.local 'cd ~/rover && git pull -q && git log --oneline -1'`
- [ ] **Step 4: Ask the owner for a go**, then restart: `sudo -n systemctl restart willy-rover`.
- [ ] **Step 5: Live check, idle first.** Owner stands in front of him. Watch:
  `journalctl -u willy-rover -f | grep -E "ENGAGE|Engage|Say:|Answer"`
  Expect within ~10 s: `ENGAGE ... kind=greet_known`, a `Say:` with the owner's name. Then with a ball in view and the owner present: `ask_room` (if no rooms) or `ask_thing`; answer; expect `ENGAGE stored`.
- [ ] **Step 6: Live check, roaming** (owner's go): he stops, turns, speaks, resumes `ROAM`.
- [ ] **Step 7: Update memory** (status file + MEMORY.md line) with what ran live.

---

## Self-review notes

- Spec §2.1 rules 1-7 → Task 3; §2.2 → Task 2; §2.3 → Tasks 1, 4, 6; §2.4 → Task 5; §3 → Tasks 3 (busy/state gates), 5 (stop, timeout, refused turn); §4 config → Tasks 2, 3; §5 tests → each task; §6 docs → Task 7.
- Clarification added beyond the spec: topics 3-7 need a person in view (Global Constraints). Raised with the owner at plan review.
- Names checked across tasks: `upsert_thing`, `name_thing`, `things(kind, room, any_room)`, `add_person_note`, `person_notes`, `FaceSeen`, `Topic`, `bearing_of`, `Engagement.tick(state,dets,faces,pose,room,busy,prev_seen)`, `engage_words.line/extract/template/when_words`, `_engage_prev`, `_last_dets`, `faces.frame_w`, `VoicePipeline.busy`, `_start_engage/_engage_tick/_engage_say/_engage_answer/_engage_store/_engage_end`.
