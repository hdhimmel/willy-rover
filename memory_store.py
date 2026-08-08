import sqlite3,json,time,os,threading,config,logsetup,privacy
log=logsetup.setup('memory')

# FR-1900: memory-BASED learning, not model retraining (no on-device fine-tuning is realistic
# on this hardware — see the FRD's feasibility note on FR-1900). Willie stores demonstrations,
# environment facts, and verbal instructions in this local SQLite store, then retrieves them as
# context at decision time. get_context_for() below is the retrieval-augmented lookup other
# subsystems (voice.py, retrieval_task.py) call before acting — it is keyword matching against
# stored text, not an embedding/semantic search; there's no local embedding model to run one.

_SCHEMA = """
CREATE TABLE IF NOT EXISTS demonstrations(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, created_at REAL NOT NULL,
    context_json TEXT NOT NULL, waypoints_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS environment_facts(
    id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, value TEXT NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS instructions(
    id INTEGER PRIMARY KEY, trigger_phrase TEXT NOT NULL, action_text TEXT NOT NULL,
    created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS routines(
    id INTEGER PRIMARY KEY, pattern_desc TEXT UNIQUE NOT NULL, count INTEGER NOT NULL,
    last_seen REAL NOT NULL);
"""

class MemoryStore:
    def __init__(self,db_path=None):
        db_path=db_path or config.MEMORY_DB_PATH
        self._path=os.path.join(config.WILLY_MEMORY_ROOT,db_path)  # §13 -- was __file__-relative directly
        self._lock=threading.Lock()
        self._conn=self._open(self._path)

    def _open(self,path):
        # §20: a corrupted file (e.g. from an unclean shutdown mid-write -- a real failure mode on
        # a robot that can lose power) must not crash the whole service on startup. Moved aside
        # rather than deleted, matching this file's own never-silently-discard-data instinct
        # elsewhere (purge_expired only ever deletes on an explicit age cutoff).
        conn=None
        try:
            conn=sqlite3.connect(path,check_same_thread=False)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn
        except sqlite3.DatabaseError as e:
            log.error(f'{path} is corrupted ({e}) — moving it aside and starting fresh.')
            if conn is not None:
                try: conn.close()
                except Exception: pass
            os.replace(path,f'{path}.corrupted.{int(time.time())}')
            conn=sqlite3.connect(path,check_same_thread=False)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn

    # --- demonstrations (FR-1900-001/002/003) ---
    def record_demonstration(self,name,waypoints,context=None):
        now=time.time()
        with self._lock:
            self._conn.execute(
                'INSERT INTO demonstrations(name,created_at,context_json,waypoints_json) VALUES(?,?,?,?) '
                'ON CONFLICT(name) DO UPDATE SET created_at=excluded.created_at,'
                'context_json=excluded.context_json,waypoints_json=excluded.waypoints_json',
                (name,now,json.dumps(context or {}),json.dumps(waypoints)))
            self._conn.commit()
        log.info(f'Demonstration recorded: {name} ({len(waypoints)} waypoints)')
        return name

    def replay_demonstration(self,name,current_context=None):
        # FR-1900-002/003: returns (waypoints, similarity) if close enough to replay, else
        # (None, similarity) so the caller reports a mismatch instead of proceeding blindly.
        # Similarity is a plain heuristic (fraction of matching context keys/values) — there is
        # no embedding model on this hardware to do anything fancier.
        row=self._conn.execute(
            'SELECT context_json,waypoints_json FROM demonstrations WHERE name=?',(name,)).fetchone()
        if row is None:
            log.warning(f'Replay requested for unknown demonstration: {name}')
            return None,0.0
        stored_ctx=json.loads(row[0]); waypoints=json.loads(row[1])
        sim=_context_similarity(stored_ctx,current_context or {})
        if sim<config.MEMORY_REPLAY_SIMILARITY_FLOOR:
            log.warning(f'Replay of {name} rejected: similarity {sim:.2f} below floor '
                        f'{config.MEMORY_REPLAY_SIMILARITY_FLOOR}')
            return None,sim
        return waypoints,sim

    # --- environment facts (FR-1900-004) ---
    def add_fact(self,key,value):
        now=time.time()
        with self._lock:
            self._conn.execute(
                'INSERT INTO environment_facts(key,value,created_at,updated_at) VALUES(?,?,?,?) '
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
                (key,value,now,now))
            self._conn.commit()

    def get_fact(self,key):
        row=self._conn.execute('SELECT value FROM environment_facts WHERE key=?',(key,)).fetchone()
        return row[0] if row else None

    def all_facts(self):
        return {k:v for k,v in self._conn.execute('SELECT key,value FROM environment_facts')}

    # --- verbal instructions (FR-1900-006) ---
    def add_instruction(self,trigger_phrase,action_text):
        with self._lock:
            cur=self._conn.execute(
                'INSERT INTO instructions(trigger_phrase,action_text,created_at) VALUES(?,?,?)',
                (trigger_phrase,action_text,time.time()))
            self._conn.commit()
        log.info(f'Instruction learned: "{trigger_phrase}" -> "{action_text}"')
        return cur.lastrowid

    def all_instructions(self):
        return [{'id':r[0],'trigger_phrase':r[1],'action_text':r[2]} for r in
                self._conn.execute('SELECT id,trigger_phrase,action_text FROM instructions')]

    # --- routines (FR-1900-005, low priority) ---
    def note_routine(self,pattern_desc):
        now=time.time()
        with self._lock:
            self._conn.execute(
                'INSERT INTO routines(pattern_desc,count,last_seen) VALUES(?,1,?) '
                'ON CONFLICT(pattern_desc) DO UPDATE SET count=count+1,last_seen=excluded.last_seen',
                (pattern_desc,now))
            self._conn.commit()

    # --- retrieval-augmented context (FR-1900-007) ---
    def get_context_for(self,query_text):
        q=query_text.lower()
        facts=self.all_facts()
        matched_facts={k:v for k,v in facts.items() if k.lower() in q or q in k.lower()}
        matched_instr=[i for i in self.all_instructions() if i['trigger_phrase'].lower() in q]
        return {'facts':matched_facts,'instructions':matched_instr}

    # --- correction/deletion (FR-1900-008) ---
    def delete_fact(self,key):
        with self._lock: self._conn.execute('DELETE FROM environment_facts WHERE key=?',(key,)); self._conn.commit()
    def delete_instruction(self,instr_id):
        with self._lock: self._conn.execute('DELETE FROM instructions WHERE id=?',(instr_id,)); self._conn.commit()
    def delete_demonstration(self,name):
        with self._lock: self._conn.execute('DELETE FROM demonstrations WHERE name=?',(name,)); self._conn.commit()

    def save_all_now(self):
        # FR-1900-011: called from brain.py's shutdown sequence BEFORE power-off. Every add_*
        # above already commits immediately, so this is a WAL checkpoint (flush the write-ahead
        # log into the main db file) rather than a batch flush — belt-and-suspenders so a
        # shutdown mid-checkpoint doesn't leave new learning stranded in the WAL file.
        with self._lock:
            self._conn.execute('PRAGMA wal_checkpoint(FULL)'); self._conn.commit()
        log.info('Memory store checkpointed for shutdown.')

    def purge_expired(self,max_age_days=None):
        # FR-1800-004/FR-1900-010: demonstrations/facts/instructions are small structured rows,
        # not raw audio/frames, but still subject to the same retention ceiling.
        max_age_days=config.DATA_RETENTION_DAYS if max_age_days is None else max_age_days
        cutoff=time.time()-max_age_days*86400
        with self._lock:
            self._conn.execute('DELETE FROM demonstrations WHERE created_at<?',(cutoff,))
            self._conn.execute('DELETE FROM instructions WHERE created_at<?',(cutoff,))
            self._conn.commit()

    def close(self):
        self.save_all_now(); self._conn.close()


def _context_similarity(a,b):
    if not a and not b: return 1.0
    keys=set(a)|set(b)
    if not keys: return 1.0
    matches=sum(1 for k in keys if str(a.get(k))==str(b.get(k)))
    return matches/len(keys)
