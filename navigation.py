import math,time,config,logsetup
import networkx as nx
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
    __slots__=('room','route','xy')
    def __init__(self,room=None,route=None,xy=None):
        self.room=room; self.route=route; self.xy=xy
    def __repr__(self): return f'Mission(room={self.room!r},route={self.route!r},xy={self.xy!r})'

def _wrap_deg(a):
    return (a+180)%360-180

class Navigator:
    def __init__(self,safety,odometry,world_model):
        self.safety=safety; self.odometry=odometry; self.world_model=world_model
        self.state='IDLE'  # IDLE|SEEKING|AVOIDING|DONE|FAILED|ABORTED
        self._waypoints=[]; self._wp_index=0
        self._avoid_start=0.0; self._avoid_phase=None
        self._fail_reason=''

    @property
    def active(self): return self.state in('SEEKING','AVOIDING')

    def start(self,mission):
        if self.active: return False,'navigation already in progress'
        waypoints=self._resolve_route(mission)
        if not waypoints:
            self.state='FAILED'; self._fail_reason='could not resolve a route for mission'
            return False,self._fail_reason
        self._waypoints=waypoints; self._wp_index=0; self._fail_reason=''
        self.state='SEEKING'
        log.info(f'Navigation started: {mission} -> {len(waypoints)} waypoint(s)')
        return True,'started'

    def abort(self,reason):
        # Mirrors RetrievalTask.abort()'s shape -- brain.py calls this on a Directive 1-4
        # preemption, never decided internally.
        if self.active:
            self.safety.stop()
            log.warning(f'Navigation ABORTED: {reason}')
        self.state='ABORTED'; self._fail_reason=reason

    def reset(self): self.state='IDLE'

    def _resolve_route(self,mission):
        if mission.route is not None:
            route=self.world_model.get_route(mission.route)
            if route is None:
                log.warning(f'Navigation: unknown route {mission.route!r}'); return []
            return list(route.waypoints)
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
            return [(rooms[n].cx,rooms[n].cy) for n in path[1:]]
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
        {'SEEKING':self._seeking,'AVOIDING':self._avoiding}.get(self.state,lambda d,t:None)(d,tilt)

    def _seeking(self,d,tilt):
        if self.safety.timed_move_active: return
        f=d['front']
        if f<config.DIST_STOP:
            self.safety.stop(); self.state='AVOIDING'
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

    def _avoiding(self,d,tilt):
        # Mirrors brain.py's _avoid() reverse-then-turn pattern -- see module docstring for why
        # this is a self-contained copy rather than a direct call into _avoid() itself.
        if self.safety.timed_move_active: return
        f=d['front']; l=d['left']; r=d['right']
        if self._avoid_phase=='turn_after_reverse':
            self._avoid_phase=None
            self.safety.request('turn_right',None,config.TURN_TIME_90)
            return
        if time.time()-self._avoid_start>config.STUCK_TIMEOUT:
            self.safety.stop(); self.state='FAILED'; self._fail_reason='stuck avoiding obstacle'
            log.warning('Navigation FAILED: stuck avoiding obstacle.')
            return
        if f>config.DIST_CLEAR:
            self.state='SEEKING'; return
        if r>l: self.safety.request('turn_right',None,config.TURN_TIME_90*0.5)
        elif l>r: self.safety.request('turn_left',None,config.TURN_TIME_90*0.5)
        else:
            self.safety.request('reverse',None,config.BACK_UP_TIME)
            self._avoid_phase='turn_after_reverse'
