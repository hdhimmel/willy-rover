import os,sqlite3,threading,time,config,logsetup
import numpy as np
log=logsetup.setup('identity')

# FR-2100. The store and the matcher, and NOTHING else -- no camera, no models, no frames.
# Vectors in, names out. That boundary is deliberate (design §4): it keeps the one piece of
# person recognition that carries the safety properties fully unit-testable off the rover, and
# it means swapping the embedding source later (CPU ArcFace -> Hailo, or adding a voice
# embedding) is a change in recognition.py alone.
#
# TWO PROPERTIES DO THE SAFETY WORK HERE. Both are easy to delete by accident:
#
# 1. THREE BANDS, NOT TWO. A single threshold turns every uncertain match into a loud
#    "Stranger Danger!" at an enrolled person in bad lighting. The middle band exists to be
#    silent -- recorded present, deliberately unnamed. Announcing a stranger requires positive
#    evidence of DISSIMILARITY, not merely the absence of a match.
#
# 2. PENDING IS INERT. Enrolment is authorised by an email confirmation this process cannot
#    verify locally (FR-2100-006), so an unapproved identity takes no part in matching at all.
#    A soft-gate bypass therefore buys an attacker a database row that does nothing. That is
#    what keeps a misidentification embarrassing rather than dangerous, which in turn is what
#    licenses the practical accuracy target in the design's §7.
#
# Storage is its own SQLite file, NOT a table inside memory.db. A wipe is then a file delete
# rather than a careful DELETE, and biometric data sits on a visibly separate boundary from
# ordinary learned facts (FR-2100-005).

RECOGNISED='recognised'
UNCERTAIN='uncertain'
UNKNOWN='unknown'

_SCHEMA="""
CREATE TABLE IF NOT EXISTS identities(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, kind TEXT NOT NULL DEFAULT 'person',
    pending INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS vectors(
    id INTEGER PRIMARY KEY, identity_id INTEGER NOT NULL, created_at REAL NOT NULL,
    vec BLOB NOT NULL, FOREIGN KEY(identity_id) REFERENCES identities(id));
CREATE TABLE IF NOT EXISTS presence(
    identity_id INTEGER PRIMARY KEY, at REAL NOT NULL, room TEXT);
"""


class Match:
    """What the matcher returns. `name` is None unless the band is RECOGNISED -- naming someone
    on an uncertain match is the failure that actually stings, so it is not merely discouraged,
    it is structurally impossible from here."""
    __slots__=('name','distance','band')
    def __init__(self,name,distance,band):
        self.name=name; self.distance=distance; self.band=band
    def __repr__(self):
        return f'Match(name={self.name!r},distance={self.distance:.3f},band={self.band})'


class Seen:
    __slots__=('name','at','room')
    def __init__(self,name,at,room):
        self.name=name; self.at=at; self.room=room
    def __repr__(self): return f'Seen({self.name!r},at={self.at},room={self.room!r})'


def _normalise(v):
    v=np.asarray(v,dtype=np.float32)
    n=float(np.linalg.norm(v))
    return v if n==0 else (v/n)


def cosine_distance(a,b):
    """1 - cosine similarity, so 0.0 is identical and larger is less similar. Both operands are
    re-normalised: an un-normalised vector from a future embedding source would otherwise
    silently scale every distance and move the bands."""
    return float(1.0-np.dot(_normalise(a),_normalise(b)))


class IdentityStore:
    def __init__(self,db_path=None):
        db_path=db_path or config.IDENTITY_DB_PATH
        self.path=os.path.join(config.WILLY_MEMORY_ROOT,db_path)
        self._lock=threading.Lock()
        self._conn=None
        self._open()

    def _c(self):
        """The connection, opened on demand. Lazy so that forget_all() can genuinely leave no
        file on disk -- a wipe that immediately recreates the file is not a wipe you can point
        at. The next call recreates an empty schema."""
        if self._conn is None: self._open()
        return self._conn

    # --- lifecycle ---------------------------------------------------------------

    def _open(self):
        os.makedirs(os.path.dirname(self.path) or '.',exist_ok=True)
        self._conn=sqlite3.connect(self.path,check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close(); self._conn=None

    def forget_all(self):
        """FR-2100-005. Deletes the FILE, not the rows -- that is the point. Un-enrolment has to
        be as reachable as enrolment, which is voice-driven, or the only way to undo it is SSH."""
        with self._lock:
            if self._conn is not None:
                self._conn.close(); self._conn=None
            try: os.remove(self.path)
            except OSError as e: log.warning(f'forget_all: {e}')
            log.info('All identities wiped.')
        # Deliberately NOT reopened here: the file must actually be absent afterwards, which is
        # what makes "a wipe is a file delete" a checkable claim rather than a description.

    # --- enrolment ---------------------------------------------------------------

    def enrol(self,name,vectors,kind='person'):
        """Stores an identity as PENDING. It takes no part in matching until approve() is called
        -- see this module's header. Defaulting to pending rather than active is the whole gate;
        a refactor that flips it would remove the email confirmation without touching anything
        called 'approval'."""
        vectors=[_normalise(v) for v in vectors]
        if not vectors:
            log.warning(f'enrol({name!r}): refused, no vectors'); return None
        now=time.time()
        with self._lock:
            cur=self._c().execute(
                'INSERT OR IGNORE INTO identities(name,kind,pending,created_at) VALUES(?,?,1,?)',
                (name,kind,now))
            row=self._c().execute('SELECT id FROM identities WHERE name=?',(name,)).fetchone()
            ident=row[0]
            for v in vectors:
                self._c().execute('INSERT INTO vectors(identity_id,created_at,vec) VALUES(?,?,?)',
                                    (ident,now,v.astype(np.float32).tobytes()))
            self._c().commit()
        self._trim(name)
        log.info(f'Enrolled {name!r} as PENDING with {len(vectors)} vector(s).')
        return ident

    def approve(self,name):
        """Flips a pending identity to active. Returns False for a name that is not already
        pending -- a spoken name may RESOLVE an identity, never CREATE one, so approval cannot
        be a back door to enrolment."""
        with self._lock:
            cur=self._c().execute('UPDATE identities SET pending=0 WHERE name=? AND pending=1',
                                    (name,))
            self._c().commit()
            ok=cur.rowcount>0
        log.info(f'Approve {name!r}: {"activated" if ok else "no pending identity"}')
        return ok

    def is_pending(self,name):
        with self._lock:
            r=self._c().execute('SELECT pending FROM identities WHERE name=?',(name,)).fetchone()
        return None if r is None else bool(r[0])

    def names(self,include_pending=True):
        q='SELECT name FROM identities' if include_pending else \
          'SELECT name FROM identities WHERE pending=0'
        with self._lock:
            return [r[0] for r in self._c().execute(q).fetchall()]

    # --- vectors -----------------------------------------------------------------

    def add_vector(self,name,vector):
        """Strengthens an ACTIVE identity -- used when someone rescues a failed match by saying
        their name (FR-2100-003), which yields a genuinely valuable vector: it is them, under
        exactly the conditions that just failed.

        Refuses on a pending identity. Otherwise an unapproved row would quietly accumulate
        evidence while claiming to be inert."""
        with self._lock:
            r=self._c().execute('SELECT id,pending FROM identities WHERE name=?',(name,)).fetchone()
            if r is None:
                log.warning(f'add_vector({name!r}): unknown identity'); return False
            if r[1]:
                log.warning(f'add_vector({name!r}): refused, identity is pending'); return False
            self._c().execute('INSERT INTO vectors(identity_id,created_at,vec) VALUES(?,?,?)',
                                (r[0],time.time(),_normalise(vector).astype(np.float32).tobytes()))
            self._c().commit()
        self._trim(name)
        return True

    def vector_count(self,name):
        with self._lock:
            r=self._c().execute(
                'SELECT COUNT(*) FROM vectors v JOIN identities i ON v.identity_id=i.id '
                'WHERE i.name=?',(name,)).fetchone()
        return r[0] if r else 0

    def _trim(self,name):
        """Cap per identity, oldest evicted. Rescued matches add vectors indefinitely otherwise."""
        cap=config.FACE_MAX_VECTORS_PER_IDENTITY
        with self._lock:
            self._c().execute(
                'DELETE FROM vectors WHERE id IN ('
                '  SELECT v.id FROM vectors v JOIN identities i ON v.identity_id=i.id'
                '  WHERE i.name=? ORDER BY v.created_at DESC, v.id DESC LIMIT -1 OFFSET ?)',
                (name,cap))
            self._c().commit()

    # --- matching ----------------------------------------------------------------

    def match(self,vector):
        """Vector in, Match out. PENDING IDENTITIES ARE EXCLUDED -- see the header.

        Returns UNCERTAIN, never UNKNOWN, when there is nothing to compare against. With an
        empty store every face is trivially 'confidently unknown', and the first thing the
        feature would ever do is shout at the whole household because enrolment has not happened
        yet. Silence is the correct behaviour for 'I have no basis for an opinion'."""
        vector=_normalise(vector)
        rows=self._active_vectors()
        if not rows:
            return Match(None,float('inf'),UNCERTAIN)
        best_name,best_d=None,float('inf')
        for name,vec in rows:
            d=cosine_distance(vector,vec)
            if d<best_d: best_name,best_d=name,d
        if best_d<config.FACE_MATCH_MAX_DISTANCE:
            return Match(best_name,best_d,RECOGNISED)
        if best_d>=config.FACE_STRANGER_MIN_DISTANCE:
            return Match(None,best_d,UNKNOWN)
        return Match(None,best_d,UNCERTAIN)   # deliberately unnamed

    def _active_vectors(self):
        with self._lock:
            rows=self._c().execute(
                'SELECT i.name,v.vec FROM vectors v JOIN identities i ON v.identity_id=i.id '
                'WHERE i.pending=0').fetchall()
        return [(n,np.frombuffer(b,dtype=np.float32)) for n,b in rows]

    def vector_at_distance(self,reference,distance):
        """Test/calibration helper: a unit vector at a given cosine distance from `reference`.
        Lives here rather than in the tests because tuning scripts need the same construction,
        and a second implementation would drift from this module's distance metric."""
        reference=_normalise(reference)
        rng=np.random.default_rng(0)
        perp=rng.normal(size=reference.shape).astype(np.float32)
        perp-=np.dot(perp,reference)*reference
        perp=_normalise(perp)
        cos=1.0-float(distance)
        return _normalise(cos*reference+np.sqrt(max(0.0,1.0-cos*cos))*perp)

    # --- presence ----------------------------------------------------------------

    def note_seen(self,name,room=None):
        """A decaying 'last seen' record: name, time, and room if the world model knows one.
        There is no tracking and no re-identification across frames -- this is the whole of
        presence awareness (design §2)."""
        with self._lock:
            r=self._c().execute('SELECT id FROM identities WHERE name=?',(name,)).fetchone()
            if r is None: return False
            self._c().execute(
                'INSERT INTO presence(identity_id,at,room) VALUES(?,?,?) '
                'ON CONFLICT(identity_id) DO UPDATE SET at=excluded.at,room=excluded.room',
                (r[0],time.time(),room))
            self._c().commit()
        return True

    def last_seen(self,name):
        with self._lock:
            r=self._c().execute(
                'SELECT p.at,p.room FROM presence p JOIN identities i ON p.identity_id=i.id '
                'WHERE i.name=?',(name,)).fetchone()
        return None if r is None else Seen(name,r[0],r[1])

    def greeting_due(self,name,now=None):
        """True when this person has not been greeted within FACE_GREET_SESSION_S. Debounced off
        the same presence record, because without it he greets on every frame in which he sees a
        face."""
        seen=self.last_seen(name)
        if seen is None: return True
        return ((now or time.time())-seen.at)>=config.FACE_GREET_SESSION_S
