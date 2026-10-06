import logsetup
from navigation import Mission
log=logsetup.setup('come_to_me')

# FR-1000-006 "Willie, I'm in the kitchen, come to me".
# Design: docs/superpowers/specs/2026-09-10-come-to-me-design.md.
#
# Sequences two machines that already exist, and owns none of the motion itself:
#   LEG_NAVIGATE  Navigator, Mission(room=...) -- through labelled doorways, asks at a shut one
#   LEG_FIND      PursuitTask in come_here mode -- its search sweep looks around on arrival
#   DONE          "Found you."
# Same shape as RetrievalTask/Navigator/PursuitTask: one top-level brain.py state (COME_TO_ME),
# Directives 1-5 enforced by RoverBrain._tick() before this ticks.
#
# ABORTS GO THROUGH THE LEGS. Every Directive 1-4 site in brain.py already aborts
# navigator/pursuit when they are active; this task sees its leg come back ABORTED and stops.
# That is why `active` is defined by the leg's own state rather than by this task's -- a task
# whose leg was aborted while brain was elsewhere (TILT_FAULT, LOW_BATTERY) must not refuse the
# next command as "already in progress".
#
# Success is being within PURSUIT_STANDOFF_CM of a person, not arriving in the room. Arriving
# and finding nobody is its own spoken outcome. Every failure is spoken (design §5).

class ComeToMeTask:
    def __init__(self,navigator,pursuit,world_model,detector,say=None):
        self.navigator=navigator; self.pursuit=pursuit; self.world_model=world_model
        self.detector=detector; self.say=say or (lambda text:None)
        self.state='IDLE'   # IDLE|LEG_NAVIGATE|LEG_FIND|DONE|FAILED|ABORTED
        self.room=None; self._fail_reason=''

    @property
    def active(self):
        return ((self.state=='LEG_NAVIGATE' and self.navigator.active) or
                (self.state=='LEG_FIND' and self.pursuit.active))

    def start(self,room):
        room=(room or '').strip().lower()
        if self.active: return False,'already on my way'
        if not any(r.name==room for r in self.world_model.all_rooms()):
            self.state='FAILED'; self._fail_reason=f'unknown room {room!r}'
            self.say(f"I don't know where the {room} is."); return False,self._fail_reason
        if not self.detector.available:
            # Refused before moving: without the camera the find leg cannot succeed, and driving
            # to the room only to say so is the silent-failure shape in slower form.
            self.state='FAILED'; self._fail_reason='camera unavailable'
            self.say("My camera isn't available, so I wouldn't be able to find you."); return False,self._fail_reason
        pose=self.world_model.get_robot_pose()
        here=self.world_model.get_room(pose.x,pose.y)
        self.room=room; self._fail_reason=''
        if here is not None and here.name==room:
            return self._start_find()
        ok,msg=self.navigator.start(Mission(room=room))
        if not ok:
            self.state='FAILED'; self._fail_reason=msg
            self.say(f"I couldn't work out how to get to the {room}."); return False,msg
        self.state='LEG_NAVIGATE'
        self.say(f"I'm not sure where I am, heading over to the {room}." if here is None
                 else f'Coming to the {room}.')
        log.info(f'Come to me: {room} (from {here.name if here else "unknown room"})')
        return True,'started'

    def _start_find(self):
        ok,msg=self.pursuit.start(mode='come_here')
        if not ok:
            self.state='FAILED'; self._fail_reason=msg
            self.say(f"I'm in the {self.room} but I can't look for you."); return False,msg
        self.state='LEG_FIND'; log.info(f'Come to me: in the {self.room}, looking for you')
        return True,'started'

    def abort(self,reason):
        if self.state=='LEG_NAVIGATE' and self.navigator.active: self.navigator.abort(reason)
        if self.state=='LEG_FIND' and self.pursuit.active: self.pursuit.abort(reason)
        if self.state in('LEG_NAVIGATE','LEG_FIND'): log.warning(f'Come to me ABORTED: {reason}')
        self.state='ABORTED'; self._fail_reason=reason

    def reset(self):
        self.state='IDLE'

    def tick(self,d,tilt):
        if self.state=='LEG_NAVIGATE': self._navigate(d,tilt)
        elif self.state=='LEG_FIND': self._find(d,tilt)

    def _navigate(self,d,tilt):
        self.navigator.tick(d,tilt)
        st=self.navigator.state
        if st=='DONE':
            self.navigator.reset(); self._start_find()
        elif st=='FAILED':
            # A shut door has already been announced by the Navigator ("nobody let me in").
            reason=self.navigator.fail_reason; self.navigator.reset()
            self.state='FAILED'; self._fail_reason=reason
            if reason!='door shut': self.say(f"I couldn't get to the {self.room}.")
        elif st=='ABORTED':
            self._fail_reason=self.navigator.fail_reason; self.navigator.reset(); self.state='ABORTED'

    def _find(self,d,tilt):
        self.pursuit.tick(d,tilt)
        st=self.pursuit.state
        if st=='DONE':
            self.pursuit.reset(); self.state='DONE'; self.say('Found you.')
        elif st=='FAILED':
            self._fail_reason=self.pursuit._fail_reason; self.pursuit.reset(); self.state='FAILED'
            self.say(f"I'm in the {self.room} but I can't see you.")
        elif st=='ABORTED':
            self._fail_reason=self.pursuit._fail_reason; self.pursuit.reset(); self.state='ABORTED'
