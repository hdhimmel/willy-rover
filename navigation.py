import math,time,config,logsetup
import networkx as nx
import avoidance
from logsetup import log_event
log=logsetup.setup('navigation')

# §11 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: Mission -> Global route -> Local
# planner -> obstacle avoidance -> safety gate -> motor controller. Only the top two layers are
# new here -- safety gate (safety.py) and motor controller (motors.py) are reused completely
# unchanged, and the sonar-reactive obstacle-avoidance *pattern* (reverse-then-turn, same
# config.STUCK_TIMEOUT/BACK_UP_TIME/TURN_TIME_90 constants as brain.py's own _avoid()) is mirrored
# here rather than called into directly.
#
# NOT calling brain.py's _avoid()/_stuck() directly is a deliberate choice, same reasoning as
# mapping.py's decision not to be a passive-but-competing FSM state (see its module docstring):
# those methods' own self._go('ROAM')/self._go('STUCK') transitions are written for brain.py's
# top-level FSM and would corrupt whichever state Navigator is actually running under. Unlike
# mapping, Navigator *does* need to actively drive -- so instead of avoiding a top-level FSM state
# entirely, it owns one (NAVIGATE, brain.py's own dispatch table) but keeps its own self-contained
# sub-state machine (mirrors RetrievalTask's shape: brain._state stays 'NAVIGATE' throughout,
# Navigator.state cycles SEEKING/AVOIDING/DONE/FAILED/ABORTED underneath it).
#
# Global route resolution is honest about what's not known yet: with no Room/Doorway data (likely
# -- §10's room-identification step is an explicit unimplemented gap), a Room-targeted Mission
# falls back to a single straight-line waypoint at that room's centroid rather than pretending to
# plan an obstacle-aware global path. "Do not pretend this is full SLAM" (§9) applies here too.

class Mission:
    # start: first waypoint of a route to drive (FR-1900-002 joining a learned route partway,
    # 2026-10-08); the navigator heads for it first, then follows the rest.
    __slots__=('room','route','xy','start')
    def __init__(self,room=None,route=None,xy=None,start=0):
        self.room=room; self.route=route; self.xy=xy; self.start=start
    def __repr__(self): return f'Mission(room={self.room!r},route={self.route!r},xy={self.xy!r},start={self.start})'

def _wrap_deg(a):
    return (a+180)%360-180

class Navigator:
    def __init__(self,safety,odometry,world_model,sonars=None,detector=None,say=None):
        self.safety=safety; self.odometry=odometry; self.world_model=world_model
        # sonars/detector feed only the avoidance TURN choice (avoidance.py); say speaks the
        # doorway request. All optional: without them he turns on side sonar and asks silently.
        self.sonars=sonars; self.detector=detector; self.say=say
        self.state='IDLE'  # IDLE|SEEKING|AVOIDING|DOOR_WAIT|DONE|FAILED|ABORTED
        self._waypoints=[]; self._wp_index=0; self._doorway_wps=set(); self._target_room=None
        self._avoid_start=0.0; self._avoid_phase=None
        self._door_asks=0; self._door_since=0.0
        self._fail_reason=''

    # DOOR_WAIT is active: he is stopped, but mid-mission, and every abort path has to reach it.
    @property
    def active(self): return self.state in('SEEKING','AVOIDING','DOOR_WAIT')

    @property
    def fail_reason(self): return self._fail_reason

    # FR-1000-001 (navigate unaided): reaches a commanded destination without operator
    # intervention -- PARTIAL per Subsystem_Status.md: dead-reckoning odometry only
    # (no SLAM, no IMU fusion, no obstacle-aware global path planning).
    def start(self,mission):
        if self.active: return False,'navigation already in progress'
        waypoints=self._resolve_route(mission)
        if not waypoints:
            self.state='FAILED'; self._fail_reason='could not resolve a route for mission'
            return False,self._fail_reason
        self._waypoints=waypoints; self._wp_index=0; self._fail_reason=''; self._door_asks=0
        self.state='SEEKING'
        log.info(f'Navigation started: {mission} -> {len(waypoints)} waypoint(s)')
        return True,'started'

    # FR-1000-004 (handover): operator control regained on demand via Directive 1-4 preemption.
    def abort(self,reason):
        # Mirrors RetrievalTask.abort()'s shape -- brain.py calls this on a Directive 1-4
        # preemption, never decided internally.
        if self.active:
            self.safety.stop()
            log_event(log,'NAVIGATION_ABORT',severity='warning',subsystem='navigation',
                      status='aborted',reason=reason)
        self.state='ABORTED'; self._fail_reason=reason

    def reset(self): self.state='IDLE'

    def _resolve_route(self,mission):
        self._doorway_wps=set(); self._target_room=mission.room
        if mission.route is not None:
            route=self.world_model.get_route(mission.route)
            if route is None:
                log.warning(f'Navigation: unknown route {mission.route!r}'); return []
            return list(route.waypoints)[max(0,int(getattr(mission,'start',0) or 0)):]
        if mission.room is not None:
            return self._resolve_room(mission.room)
        if mission.xy is not None:
            return [tuple(mission.xy)]
        return []

    def _resolve_room(self,room_name):
        rooms={r.name:r for r in self.world_model.all_rooms()}
        target=rooms.get(room_name)
        if target is None:
            log.warning(f'Navigation: unknown room {room_name!r}'); return []
        px,py=self.odometry.pose.x,self.odometry.pose.y
        current=self.world_model.get_room(px,py)
        if current is None or current.name==target.name:
            return [(target.cx,target.cy)]  # already there, or current room unknown -- direct waypoint
        path=self._graph_path(current.name,target.name,rooms)
        if path:
            # FR-1000-006 (come-to-me design §4.4): through each DOORWAY, then that room's centroid.
            # Centroid to centroid drives at the wall between two rooms.
            doors={frozenset((dw.room_a_name,dw.room_b_name)):(dw.x,dw.y) for dw in self.world_model.all_doorways()}
            wps=[]
            for a,b in zip(path,path[1:]):
                self._doorway_wps.add(len(wps)); wps.append(doors[frozenset((a,b))])
                wps.append((rooms[b].cx,rooms[b].cy))
            return wps
        # No known Room/Doorway connectivity between here and there -- honest straight-line
        # fallback (§9's "do not pretend this is full SLAM"), not fake obstacle-aware planning.
        log.info(f'Navigation: no known room graph path {current.name!r}->{room_name!r}, '
                 f'falling back to a direct waypoint.')
        return [(target.cx,target.cy)]

    def _graph_path(self,a,b,rooms):
        g=nx.Graph()
        for name in rooms: g.add_node(name)
        for dw in self.world_model.all_doorways():
            if dw.room_a_name in rooms and dw.room_b_name in rooms:
                w=math.hypot(rooms[dw.room_a_name].cx-rooms[dw.room_b_name].cx,
                             rooms[dw.room_a_name].cy-rooms[dw.room_b_name].cy)
                g.add_edge(dw.room_a_name,dw.room_b_name,weight=w)
        try: return nx.shortest_path(g,a,b,weight='weight')
        except (nx.NetworkXNoPath,nx.NodeNotFound): return None

    def tick(self,d,tilt):
        {'SEEKING':self._seeking,'AVOIDING':self._avoiding,
         'DOOR_WAIT':self._door_wait}.get(self.state,lambda d,t:None)(d,tilt)

    def _at_blocked_doorway(self):
        """Only a LABELLED doorway waypoint counts (design §4.7) -- never an arbitrary obstacle,
        or a sofa in the hall gets asked to let him in."""
        if self._wp_index not in self._doorway_wps: return False
        pose=self.odometry.pose; wx,wy=self._waypoints[self._wp_index]
        return math.hypot(wx-pose.x,wy-pose.y)<=config.DOOR_BLOCKED_RADIUS_M

    def _ask_at_door(self):
        self._door_asks+=1; self._door_since=time.time()
        log_event(log,'DOOR_BLOCKED',severity='info',subsystem='navigation',status='asking',
                  attempt=self._door_asks,room=self._target_room or '')
        if self.say:
            where=f' the {self._target_room}' if self._target_room else ' through'
            self.say(f"Can someone let me in? I'm trying to get to{where}.")

    # Design §4.7, ask-only. THE KNOCK IS NOT BUILT: it needs a tap motion with measured joint
    # limits, and nothing defines one yet. The spec's own rule for a missing arm -- "skip the
    # knock, still ask aloud, then apply the same retry rule" -- is what runs here.
    def _door_wait(self,d,tilt):
        self.safety.stop()
        if d['front']>config.DIST_CLEAR:
            log.info('Doorway cleared -- resuming the route at the same waypoint.')
            self.state='SEEKING'; return
        if time.time()-self._door_since<config.DOOR_WAIT_S: return
        if self._door_asks>=config.DOOR_MAX_ASKS:
            self.state='FAILED'; self._fail_reason='door shut'
            log.warning('Navigation FAILED: doorway stayed blocked.')
            if self.say: self.say("I asked, but nobody let me in.")
            return
        self._ask_at_door()

    # FR-1000-003 (route maintenance): drives toward the next waypoint, arrival tolerance
    # is config.NAV_ARRIVAL_RADIUS_M. Straight-line waypoint following, no obstacle-aware
    # global replanning -- see world_model.py for the route-graph limits.
    def _seeking(self,d,tilt):
        if self.safety.timed_move_active: return
        f=d['front']
        if f<config.DIST_STOP:
            getattr(self.safety,'obstacle_stop',self.safety.stop)()   # brake, not ramp (2026-10-07)
            if self._at_blocked_doorway():
                self.state='DOOR_WAIT'; self._ask_at_door(); return
            self.state='AVOIDING'
            self._avoid_start=time.time(); self._avoid_phase=None
            return
        pose=self.odometry.pose
        wx,wy=self._waypoints[self._wp_index]
        dist=math.hypot(wx-pose.x,wy-pose.y)
        if dist<=config.NAV_ARRIVAL_RADIUS_M:
            self._wp_index+=1
            if self._wp_index>=len(self._waypoints):
                self.safety.stop(); self.state='DONE'; log.info('Navigation complete: arrived.')
            return
        # Positive bearing_err means the waypoint is CCW of current heading -- odometry.py's own
        # convention (integrate()'s d_heading grows when the right wheel outpaces the left, which
        # curves the chassis CCW) means CCW = turn_left, not turn_right.
        bearing_err=_wrap_deg(math.degrees(math.atan2(wy-pose.y,wx-pose.x)-pose.heading))
        if abs(bearing_err)>config.NAV_HEADING_DEADBAND_DEG:
            (self.safety.turn_left_for if bearing_err>0 else self.safety.turn_right_for)(
                config.NAV_TURN_STEP_S,config.SPEED_TURN)
        else:
            self.safety.forward(config.SPEED_SLOW)

    # FR-1000-002 (obstacle avoidance): obstacles are detected (sonar) and avoided.
    def _avoiding(self,d,tilt):
        # Mirrors brain.py's _avoid() reverse-then-turn pattern -- see module docstring for why
        # this is a self-contained copy rather than a direct call into _avoid() itself.
        if self.safety.timed_move_active: return
        f=d['front']; l=d['left']; r=d['right']
        if self._avoid_phase=='turn_after_reverse':
            self._avoid_phase=None
            self.safety.request(self._turn(d) or 'turn_right',None,config.TURN_TIME_90)
            return
        if time.time()-self._avoid_start>config.STUCK_TIMEOUT:
            self.safety.stop(); self.state='FAILED'; self._fail_reason='stuck avoiding obstacle'
            log.warning('Navigation FAILED: stuck avoiding obstacle.')
            return
        if f>config.DIST_CLEAR:
            self.state='SEEKING'; return
        turn=self._turn(d)
        if turn: self.safety.request(turn,None,config.TURN_TIME_90*0.5)
        else:
            self.safety.request('reverse',None,config.BACK_UP_TIME)
            self._avoid_phase='turn_after_reverse'

    def _turn(self,d):
        # FR-1000-002: side sonar + ToF columns + camera (avoidance.py), not side sonar alone.
        return avoidance.choose_turn(d,getattr(self.sonars,'tof',None),self.detector)
