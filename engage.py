"""FR-2400 engagement (2026-10-15, owner): greet people, ask about and remark on what he sees and
remembers. Pure decisions -- no I/O but memory reads; brain.py acts on the Topic returned.

Rules in priority order (spec §2.1): greet_known, greet_stranger, ask_room, ask_thing, callback,
change, ask_person. Greetings ignore the ENGAGE_GAP_S gap but start it; everything else needs a person in view
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

    def _pick(self,now,topic):
        self._said.add((topic.kind,topic.subject))
        self._gap_t=now
        return topic

    def tick(self,state,dets,faces,pose,room,busy,prev_seen):
        now=self.clock()
        if room!=self._room: self._room=room; self._room_since=now
        known=[f for f in (faces or []) if f.band==RECOGNISED and f.name]
        if faces is not None:   # a new scan: track visits and strangers
            for f in known:
                if f.name in self._seen and now-self._seen[f.name]>config.ENGAGE_VISIT_S: self._greeted.pop(f.name,None)
                self._seen.setdefault(f.name,now)
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
            if f.name in self._greeted: continue
            self._greeted[f.name]=now
            facts={'name':f.name}
            before=prev_seen.get(f'saw:{f.name}')
            if before and now-before>=config.ENGAGE_CALLBACK_MIN_H*3600:
                facts.update(about='back',when=when_words(before,now))
            return self._pick(now,Topic('greet_known',f.name,facts,False,f.bearing_deg))
        return None

    def _stranger(self,now,faces):
        if (faces and self._unknown_run>=config.ENGAGE_STRANGER_CONFIRM_N
                and now-self._stranger_t>config.ENGAGE_VISIT_S):
            self._stranger_t=now; self._unknown_run=0
            f=next(f for f in faces if f.band==UNKNOWN)
            return self._pick(now,Topic('greet_stranger','stranger',{},True,f.bearing_deg))
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
            if any(r.get('label') for r in self.m.things(kind,any_room=True)): continue
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
            elsewhere=self.m.things(kind,any_room=True)
            if key in prev and prev[key] is None and any(r['room']!=room for r in elsewhere) \
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
