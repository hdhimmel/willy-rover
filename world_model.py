import sqlite3,json,math,time,os,threading,config,logsetup
log=logsetup.setup('world_model')

# §9/§10 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: "the major missing subsystem."
# Explicitly NOT full SLAM (§9's own instruction) — a layered model built on top of what already
# exists rather than a replacement for it:
#   Layer 1 local obstacle map      -> self._obstacles (ephemeral, age-decayed, never persisted;
#                                       sonar/vision re-observe every session)
#   Layer 2 robot odometry          -> delegates to the existing odometry.Odometry/Pose, not
#                                       duplicated here
#   Layer 3 room/semantic info      -> self._rooms (starts empty; §10's "identify probable rooms"
#                                       is a documented gap this milestone, not attempted)
#   Layer 4 known objects/landmarks -> self._objects / self._landmarks
#   Layer 5 learned routes          -> self._routes
# Persistence mirrors memory_store.py's convention (own SQLite file, WAL, one lock-guarded
# connection, upsert via ON CONFLICT) but writes only happen on save() -- not on every
# update_observation()/remember_object() call, since those can fire every tick (20Hz) and a
# per-call disk write would be wasteful/blocking. Master doc §13.4 names this DB's intended home
# explicitly: "SQLite on the SSD = spatial/semantic memory (object sightings, room map, AprilTag
# anchors) -- live source of truth" -- a separate file from memory.db, not a new table in it.

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, cx REAL NOT NULL, cy REAL NOT NULL,
    radius_m REAL NOT NULL);
CREATE TABLE IF NOT EXISTS doorways(
    id INTEGER PRIMARY KEY, room_a_name TEXT NOT NULL, room_b_name TEXT NOT NULL,
    x REAL NOT NULL, y REAL NOT NULL, UNIQUE(room_a_name,room_b_name));
CREATE TABLE IF NOT EXISTS landmarks(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, x REAL NOT NULL, y REAL NOT NULL,
    kind TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS objects(
    id INTEGER PRIMARY KEY, cls TEXT NOT NULL, x REAL NOT NULL, y REAL NOT NULL,
    confidence REAL NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS routes(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, waypoints_json TEXT NOT NULL,
    created_at REAL NOT NULL);
"""

def _dist(x1,y1,x2,y2): return math.hypot(x2-x1,y2-y1)

def project_point(pose,bearing_deg,distance_m):
    """Pure function, no hardware access: world (x,y) of a sensor hit at bearing_deg (degrees,
    relative to chassis forward -- same convention as config.SONAR_BEARING_DEG/odometry.Pose's
    heading) and distance_m from the given Pose. Used by brain.py's per-tick sonar feed and
    mapping.py's vision-landmark projection alike."""
    angle=pose.heading+math.radians(bearing_deg)
    return pose.x+distance_m*math.cos(angle),pose.y+distance_m*math.sin(angle)

class Room:
    __slots__=('id','name','cx','cy','radius_m')
    def __init__(self,name,cx,cy,radius_m,id=None):
        self.id=id; self.name=name; self.cx=cx; self.cy=cy; self.radius_m=radius_m
    def __repr__(self): return f'Room({self.name!r},cx={self.cx:.2f},cy={self.cy:.2f},r={self.radius_m:.2f})'

class Doorway:
    __slots__=('id','room_a_name','room_b_name','x','y')
    def __init__(self,room_a_name,room_b_name,x,y,id=None):
        self.id=id; self.room_a_name=room_a_name; self.room_b_name=room_b_name; self.x=x; self.y=y
    def __repr__(self): return f'Doorway({self.room_a_name!r}<->{self.room_b_name!r})'

class Obstacle:
    __slots__=('x','y','timestamp','source')
    def __init__(self,x,y,timestamp=None,source='sonar'):
        self.x=x; self.y=y; self.timestamp=timestamp if timestamp is not None else time.time()
        self.source=source
    def __repr__(self): return f'Obstacle(x={self.x:.2f},y={self.y:.2f},source={self.source})'

class Object:
    __slots__=('id','cls','x','y','confidence','first_seen','last_seen')
    def __init__(self,cls,x,y,confidence,first_seen=None,last_seen=None,id=None):
        self.id=id; self.cls=cls; self.x=x; self.y=y; self.confidence=confidence
        now=time.time()
        self.first_seen=first_seen if first_seen is not None else now
        self.last_seen=last_seen if last_seen is not None else now
    def __repr__(self): return f'Object({self.cls!r},x={self.x:.2f},y={self.y:.2f},conf={self.confidence:.2f})'

class Landmark:
    __slots__=('id','name','x','y','kind')
    def __init__(self,name,x,y,kind='generic',id=None):
        self.id=id; self.name=name; self.x=x; self.y=y; self.kind=kind
    def __repr__(self): return f'Landmark({self.name!r},kind={self.kind},x={self.x:.2f},y={self.y:.2f})'

class Route:
    __slots__=('id','name','waypoints')
    def __init__(self,name,waypoints,id=None):
        self.id=id; self.name=name; self.waypoints=list(waypoints)  # [(x,y),...]
    def __repr__(self): return f'Route({self.name!r},{len(self.waypoints)} waypoints)'

class Observation:
    # The single ingestion type update_observation() accepts. kind in
    # ('obstacle','object','landmark') selects which layer/table it routes into.
    # payload carries kind-specific fields: obstacle->{'source'}, object->{'cls','confidence'},
    # landmark->{'name','kind'}.
    __slots__=('kind','x','y','timestamp','payload')
    def __init__(self,kind,x,y,timestamp=None,payload=None):
        self.kind=kind; self.x=x; self.y=y
        self.timestamp=timestamp if timestamp is not None else time.time()
        self.payload=payload or {}

class RobotState:
    # Convenience bundle for callers (navigation/mapping) that want pose + battery/motion context
    # in one object rather than threading brain.py's individual fields through. Not persisted --
    # constructed fresh from live values by the caller.
    __slots__=('pose','bat_tier','motion_enabled','fsm_state')
    def __init__(self,pose,bat_tier,motion_enabled,fsm_state):
        self.pose=pose; self.bat_tier=bat_tier; self.motion_enabled=motion_enabled; self.fsm_state=fsm_state

class WorldModel:
    def __init__(self,odometry,db_path=None):
        self.odometry=odometry
        db_path=db_path or config.WORLD_MODEL_DB_PATH
        self._path=os.path.join(config.WILLY_MAP_ROOT,db_path)  # §13 -- was __file__-relative directly
        self._lock=threading.Lock()
        self._conn=self._open(self._path)
        self._obstacles=[]           # list[Obstacle], ephemeral, never persisted
        self._rooms={}               # name -> Room
        self._doorways=[]            # list[Doorway]
        self._landmarks={}           # name -> Landmark
        self._objects={}             # id -> Object
        self._routes={}              # name -> Route
        self._object_seq=1
        self.load()  # §10 step 8: resume a later session automatically

    def _open(self,path):
        # §20: mirrors memory_store.py's MemoryStore._open() -- a corrupted file must not crash
        # the whole service on startup. Moved aside rather than deleted.
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

    # --- Layer 1: local obstacle map ---
    def _prune_obstacles(self):
        cutoff=time.time()-config.OBSTACLE_MAX_AGE_S
        self._obstacles=[o for o in self._obstacles if o.timestamp>=cutoff]

    def get_nearby_obstacles(self,x,y,radius_m):
        self._prune_obstacles()
        return [o for o in self._obstacles if _dist(x,y,o.x,o.y)<=radius_m]

    # --- Layer 2: odometry (delegated, not duplicated) ---
    def get_robot_pose(self): return self.odometry.pose

    # --- Layer 3: rooms ---
    def add_room(self,name,cx,cy,radius_m=None):
        radius_m=config.ROOM_MATCH_RADIUS_M if radius_m is None else radius_m
        self._rooms[name]=Room(name,cx,cy,radius_m)
        return self._rooms[name]

    def add_doorway(self,room_a_name,room_b_name,x,y):
        self._doorways.append(Doorway(room_a_name,room_b_name,x,y))

    def get_room(self,x,y):
        best=None; best_d=None
        for room in self._rooms.values():
            d=_dist(x,y,room.cx,room.cy)
            if d<=room.radius_m and (best_d is None or d<best_d): best=room; best_d=d
        return best

    def all_rooms(self): return list(self._rooms.values())
    def all_doorways(self): return list(self._doorways)

    # --- Layer 4: objects/landmarks ---
    def _upsert_object(self,cls,x,y,confidence,timestamp):
        for obj in self._objects.values():
            if obj.cls==cls and _dist(x,y,obj.x,obj.y)<=config.OBJECT_DEDUPE_RADIUS_M:
                obj.x=x; obj.y=y; obj.confidence=max(obj.confidence,confidence); obj.last_seen=timestamp
                return obj
        obj=Object(cls,x,y,confidence,first_seen=timestamp,last_seen=timestamp,id=self._object_seq)
        self._object_seq+=1; self._objects[obj.id]=obj
        return obj

    def remember_object(self,obj):
        # Plan-named explicit method (§9) distinct from the generic update_observation() path --
        # same dedupe-on-proximity logic either way.
        return self._upsert_object(obj.cls,obj.x,obj.y,obj.confidence,obj.last_seen or time.time())

    def remember_landmark(self,name,x,y,kind='generic'):
        self._landmarks[name]=Landmark(name,x,y,kind)
        return self._landmarks[name]

    def get_objects(self,cls=None):
        objs=list(self._objects.values())
        return [o for o in objs if o.cls==cls] if cls else objs

    def get_landmark(self,name): return self._landmarks.get(name)
    def all_landmarks(self): return list(self._landmarks.values())

    # --- Layer 5: routes ---
    def add_route(self,name,waypoints):
        self._routes[name]=Route(name,waypoints)
        return self._routes[name]

    def get_route(self,name): return self._routes.get(name)
    def all_routes(self): return list(self._routes.values())

    # --- single ingestion entry point (§9) ---
    def update_observation(self,obs):
        if obs.kind=='obstacle':
            self._obstacles.append(Obstacle(obs.x,obs.y,obs.timestamp,obs.payload.get('source','sonar')))
            self._prune_obstacles()
        elif obs.kind=='object':
            self._upsert_object(obs.payload['cls'],obs.x,obs.y,obs.payload.get('confidence',0.5),obs.timestamp)
        elif obs.kind=='landmark':
            self.remember_landmark(obs.payload['name'],obs.x,obs.y,obs.payload.get('kind','generic'))
        else:
            log.warning(f'update_observation: unknown kind {obs.kind!r}, ignored')

    # --- persistence (§10 steps 7/8) ---
    def save(self):
        # Snapshots the in-memory Rooms/Doorways/Landmarks/Objects/Routes to disk. The Layer-1
        # obstacle list is intentionally excluded -- see module docstring.
        with self._lock:
            for r in self._rooms.values():
                self._conn.execute(
                    'INSERT INTO rooms(name,cx,cy,radius_m) VALUES(?,?,?,?) '
                    'ON CONFLICT(name) DO UPDATE SET cx=excluded.cx,cy=excluded.cy,radius_m=excluded.radius_m',
                    (r.name,r.cx,r.cy,r.radius_m))
            for dw in self._doorways:
                self._conn.execute(
                    'INSERT INTO doorways(room_a_name,room_b_name,x,y) VALUES(?,?,?,?) '
                    'ON CONFLICT(room_a_name,room_b_name) DO UPDATE SET x=excluded.x,y=excluded.y',
                    (dw.room_a_name,dw.room_b_name,dw.x,dw.y))
            for lm in self._landmarks.values():
                self._conn.execute(
                    'INSERT INTO landmarks(name,x,y,kind,updated_at) VALUES(?,?,?,?,?) '
                    'ON CONFLICT(name) DO UPDATE SET x=excluded.x,y=excluded.y,kind=excluded.kind,'
                    'updated_at=excluded.updated_at',(lm.name,lm.x,lm.y,lm.kind,time.time()))
            self._conn.execute('DELETE FROM objects')  # objects are re-snapshotted wholesale, not upserted
            for obj in self._objects.values():
                self._conn.execute(
                    'INSERT INTO objects(id,cls,x,y,confidence,first_seen,last_seen) VALUES(?,?,?,?,?,?,?)',
                    (obj.id,obj.cls,obj.x,obj.y,obj.confidence,obj.first_seen,obj.last_seen))
            for rt in self._routes.values():
                self._conn.execute(
                    'INSERT INTO routes(name,waypoints_json,created_at) VALUES(?,?,?) '
                    'ON CONFLICT(name) DO UPDATE SET waypoints_json=excluded.waypoints_json',
                    (rt.name,json.dumps(rt.waypoints),time.time()))
            self._conn.commit()  # must commit before checkpointing -- an open write transaction
                                  # on this same connection blocks PRAGMA wal_checkpoint(FULL)
            self._conn.execute('PRAGMA wal_checkpoint(FULL)')
        log.info(f'World model saved: {len(self._rooms)} rooms, {len(self._landmarks)} landmarks, '
                  f'{len(self._objects)} objects, {len(self._routes)} routes.')

    def load(self):
        with self._lock:
            rooms={}
            for id,name,cx,cy,radius_m in self._conn.execute('SELECT id,name,cx,cy,radius_m FROM rooms'):
                rooms[name]=Room(name,cx,cy,radius_m,id=id)
            doorways=[Doorway(a,b,x,y,id=id) for id,a,b,x,y in
                      self._conn.execute('SELECT id,room_a_name,room_b_name,x,y FROM doorways')]
            landmarks={}
            for id,name,x,y,kind in self._conn.execute('SELECT id,name,x,y,kind FROM landmarks'):
                landmarks[name]=Landmark(name,x,y,kind,id=id)
            objects={}; max_id=0
            for id,cls,x,y,conf,fs,ls in self._conn.execute(
                    'SELECT id,cls,x,y,confidence,first_seen,last_seen FROM objects'):
                objects[id]=Object(cls,x,y,conf,first_seen=fs,last_seen=ls,id=id); max_id=max(max_id,id)
            routes={}
            for id,name,wp_json in self._conn.execute('SELECT id,name,waypoints_json FROM routes'):
                routes[name]=Route(name,[tuple(p) for p in json.loads(wp_json)],id=id)
        self._rooms=rooms; self._doorways=doorways; self._landmarks=landmarks
        self._objects=objects; self._routes=routes; self._object_seq=max_id+1
        log.info(f'World model loaded: {len(rooms)} rooms, {len(landmarks)} landmarks, '
                 f'{len(objects)} objects, {len(routes)} routes.')

    def close(self): self.save(); self._conn.close()
