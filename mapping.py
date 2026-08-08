import config,logsetup
from world_model import Observation,project_point
log=logsetup.setup('mapping')

# §10 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: dedicated mapping/learning mode.
# Milestone 1 scope (§10's own "should not require a complete SLAM implementation in the first
# milestone"): while active, records vision landmarks/objects into world_model.py on every tick
# and snapshots the map (world_model.save()) on stop/abort. The Layer-1 obstacle map is already
# fed every tick regardless of mode (brain.py's passive sonar feed, §9) -- this only adds what
# that doesn't already cover: vision detections and an explicit session start/stop/save boundary.
#
# UNLIKE RetrievalTask, this is deliberately NOT wired in as a top-level brain.py FSM state.
# self.active is an orthogonal flag brain.py checks alongside its existing ROAM/SLOW/AVOID/STUCK
# dispatch, the same "passive, no motor consequence" pattern already used for odometry/obstacle
# logging -- MappingSession.tick() never calls self._go() or touches brain.py's self._state at
# all. This is what actually delivers the plan's own instruction to leave the sonar-reactive
# ROAM/AVOID/STUCK logic "unchanged": routing mapping through a competing top-level FSM state
# would require either duplicating _roam()/_avoid()'s reactive logic, or calling those methods
# directly from a MAP state and inheriting their internal self._go('ROAM')/self._go('STUCK')
# transitions -- which would silently exit mapping mode the instant the path cleared or a stuck
# recovery fired. Keeping mapping orthogonal avoids that collision entirely and needs no
# duplicated drive logic: whatever ROAM/SLOW/AVOID/STUCK is already doing keeps happening,
# unmodified, while this class only observes alongside it.
#
# Room identification (§10 step 6, "identify probable rooms when possible") is an explicit gap
# this milestone -- no heuristic exists yet; matches the plan's own "when possible" wording
# rather than a hard requirement.

class MappingSession:
    def __init__(self,world_model,detector=None):
        self.world_model=world_model; self.detector=detector
        self.active=False; self._observation_count=0

    def start(self):
        if self.active: return False,'mapping session already active'
        self.active=True; self._observation_count=0
        log.info('Mapping session started.')
        return True,'started'

    def tick(self,d,tilt):
        # d/tilt accepted (unused this milestone) to match every other brain.py sub-component's
        # tick(d,tilt) signature (RetrievalTask, SafetyController) -- kept for a consistent call
        # site even though vision-only recording doesn't need sonar/tilt today.
        if not self.active or self.detector is None: return
        pose=self.world_model.get_robot_pose()
        for det in self.detector.detect():
            dist_cm,bearing_deg=self.detector.localize(det)
            x,y=project_point(pose,bearing_deg,dist_cm/100.0)
            self.world_model.update_observation(
                Observation('object',x,y,payload={'cls':det['class'],'confidence':det['conf']}))
            self._observation_count+=1

    def stop(self):
        # §10 step 7: store the resulting map.
        if not self.active: return False,'no mapping session active'
        self.active=False
        self.world_model.save()
        log.info(f'Mapping session stopped -- {self._observation_count} observations recorded, map saved.')
        return True,'stopped'

    def abort(self,reason):
        # Mirrors RetrievalTask.abort()'s shape (brain.py calls this on a Directive 1-4
        # preemption) even though, unlike retrieval, aborting mapping has no motion to stop --
        # it only needs to close out the session and persist what was recorded so far.
        if self.active:
            log.warning(f'Mapping session ABORTED: {reason}')
            self.active=False
            self.world_model.save()
