import pygame,math,time,threading,os,config
os.environ.setdefault('SDL_VIDEODRIVER','wayland')
os.environ.setdefault('SDL_VIDEO_WAYLAND_WMCLASS','willy')
# SDL installs its own process-wide SIGINT/SIGTERM handlers by default, translating them into an
# SDL_QUIT event that only this module's own event loop consumes — that silently ate shutdown
# signals before main.py's run loop ever saw them. Disabling it lets Python's normal signal
# delivery (main.py's SIGTERM handler) through instead.
os.environ.setdefault('SDL_NO_SIGNAL_HANDLERS','1')
C_BG=(8,8,16);C_FACE=(30,30,45);C_EYE_W=(230,230,240)
C_ROAM=(0,200,80);C_STOP=(255,180,0);C_WARN=(255,80,40);C_IDLE=(80,120,255)
C_MOUTH=(200,200,210);C_ACCENT=(232,93,36);C_TEXT=(180,180,200);C_DIM=(60,60,70)
C_GREEN=(0,210,90);C_RED=(220,50,50);C_AMBER=(255,165,0)
# FR-1600: states a personality overlay (bashful/silly) is allowed to visually decorate. Any
# state NOT in this set (fault/lowbatt/warn/stuck) is mandatory and always wins — FR-1600-008.
_PERSONALITY_SAFE_STATES={'idle','roam','slow','listening','processing','think','speak'}
W,H=1280,720; FACE_CX=640; FACE_CY=360
EYE_L=415;EYE_R=865;EYE_CY=340;EYE_RX=175;EYE_RY=130;IRIS_R=86;PUPIL_R=38
MOUTH_CX=640;MOUTH_CY=535;MOUTH_W=475;MOUTH_H=110
STATUS_Y=600

class WillyFace:
    def __init__(self):
        self._state='idle';self._status='Initialising...';self._dists={'front':999,'left':999,'right':999}
        self._tilt=0.0;self._speed=0.0;self._lock=threading.Lock()
        self._t=0.0;self._blink_t=0.0;self._blink_next=3.5
        self._running=False;self._thread=None
        # FR-1600-006/007: personality overlay is a separate layer from the FSM/voice-driven
        # base state above — see _PERSONALITY_SAFE_STATES for when it's actually shown.
        self._personality=None;self._personality_until=0.0
        self._idle_cycle_t=config.IDLE_PERSONALITY_CYCLE_S
        self._heard_until=0.0  # note_heard() flashes a small corner icon, separate from state='listening'

    def note_heard(self,duration=2.0):
        # Confirms a command was actually transcribed (non-empty STT text) — distinct from the
        # LISTENING/PROCESSING state badge, which just says the mic/pipeline stage, not that
        # anything was understood as speech yet.
        with self._lock: self._heard_until=self._t+duration

    def update_state(self,state,status='',distances=None,tilt=0.0,speed=0.0):
        with self._lock:
            self._state=state
            if status: self._status=status
            if distances: self._dists=distances
            self._tilt=tilt; self._speed=speed

    def set_expression(self,expr,duration=1.5):
        # FR-1600-006 (bashful) / ad-hoc silly triggers from voice.py. Recorded unconditionally;
        # _draw() is what actually enforces FR-1600-008 by only showing it when the current base
        # state is in _PERSONALITY_SAFE_STATES — fault/lowbatt/warn/stuck always win regardless
        # of what's recorded here.
        with self._lock:
            self._personality=expr; self._personality_until=self._t+duration

    def _wrap(self,font,text,max_width,max_lines=2):
        # Greedy word-wrap capped at max_lines — overflow past the last line gets folded in
        # with a trailing ellipsis rather than silently disappearing off-screen.
        words=text.split(' '); lines=['']
        for w in words:
            trial=(lines[-1]+' '+w).strip()
            if not lines[-1] or font.size(trial)[0]<=max_width:
                lines[-1]=trial
            elif len(lines)==max_lines:
                while lines[-1] and font.size(lines[-1]+'…')[0]>max_width: lines[-1]=lines[-1][:-1]
                lines[-1]+='…'; return lines
            else:
                lines.append(w)
        return lines

    def note_interaction(self):
        # Resets the idle-personality cycle (FR-1600-007) so the silly idle animation doesn't
        # fire right after a real interaction just ended.
        with self._lock: self._idle_cycle_t=config.IDLE_PERSONALITY_CYCLE_S

    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()

    def stop(self):
        self._running=False
        if self._thread is not None: self._thread.join(timeout=2.0)

    def _loop(self):
        # SDL/Wayland requires init, window creation, and every subsequent display
        # call to happen on the same thread — creating the window in __init__ (main
        # thread) while flipping here caused frames to render but never present.
        pygame.init()
        self.screen=pygame.display.set_mode((W,H),pygame.FULLSCREEN|pygame.NOFRAME)
        pygame.display.set_caption('WildWilly'); pygame.mouse.set_visible(False)
        self.f_sm=pygame.font.SysFont('monospace',18)
        self.f_md=pygame.font.SysFont('monospace',26)
        self.f_xl=pygame.font.SysFont(None,80)
        clk=pygame.time.Clock()
        while self._running:
            for e in pygame.event.get():
                if e.type==pygame.QUIT or (e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE):
                    self._running=False
            dt=1.0/config.DISPLAY_FPS; self._t+=dt
            if config.ENABLE_DISPLAY_EXPRESSIONS:
                with self._lock:
                    idle=self._state=='idle'
                if idle:
                    self._idle_cycle_t-=dt
                    if self._idle_cycle_t<=0:
                        self.set_expression('silly',2.0); self._idle_cycle_t=config.IDLE_PERSONALITY_CYCLE_S
                else:
                    self._idle_cycle_t=config.IDLE_PERSONALITY_CYCLE_S
            self._draw(); clk.tick(config.DISPLAY_FPS)
        pygame.quit()

    def _draw(self):
        s=self.screen; t=self._t; s.fill(C_BG)
        with self._lock:
            state=self._state; status=self._status
            dists=dict(self._dists); tilt=self._tilt; speed=self._speed
            personality=self._personality if self._t<self._personality_until else None
            heard=self._t<self._heard_until
        # FR-1600-008: personality only ever substitutes the VISUAL state (vis), never the real
        # `state` used for the HUD badge/status text below — and only when `state` is itself in
        # _PERSONALITY_SAFE_STATES. A fault/lowbatt/warn/stuck state always draws as itself.
        vis=personality if (personality and state in _PERSONALITY_SAFE_STATES) else state
        ic={'idle':C_IDLE,'roam':C_ROAM,'slow':C_STOP,'stop':C_WARN,'warn':C_RED,'stuck':C_RED,
            'fault':C_RED,'lowbatt':C_AMBER,'listening':C_IDLE,'processing':C_IDLE,'think':C_IDLE,
            'speak':C_ROAM,'bashful':C_AMBER,'silly':C_GREEN}.get(vis,C_IDLE)
        pygame.draw.ellipse(s,C_FACE,pygame.Rect(FACE_CX-550,FACE_CY-320,1100,640))
        self._blink_next-=1.0/config.DISPLAY_FPS
        if self._blink_next<=0: self._blink_t=0.12; self._blink_next=3.0+math.sin(t*0.7)*1.5
        bf=0.0
        if self._blink_t>0:
            self._blink_t-=1.0/config.DISPLAY_FPS; h=0.06
            bf=(1.0-(self._blink_t-h)/h) if self._blink_t>h else self._blink_t/h
        pb=math.sin(t*1.2)*10 if vis=='roam' else 0
        ps=math.cos(t*0.8)*11 if vis in('roam','idle') else 0
        if vis=='bashful': ps=-EYE_RX*0.5; pb=EYE_RY*0.3  # look away and down (FR-1600-006)
        for ex in [EYE_L,EYE_R]:
            ery=max(2,int(EYE_RY*(1.0-bf)))
            pygame.draw.ellipse(s,C_EYE_W,pygame.Rect(ex-EYE_RX,EYE_CY-ery,EYE_RX*2,ery*2))
            if bf<0.9:
                ix=ex+int(ps*(1 if ex<FACE_CX else -1)); iz=EYE_CY+int(pb)
                pygame.draw.circle(s,ic,(ix,iz),IRIS_R)
                pygame.draw.circle(s,(0,0,0),(ix,iz),PUPIL_R)
                pygame.draw.circle(s,(255,255,255),(ix-18,iz-18),13)
            pygame.draw.ellipse(s,C_DIM,pygame.Rect(ex-EYE_RX,EYE_CY-ery,EYE_RX*2,ery*2),4)
        br={'warn':-29,'stuck':-21,'fault':-31,'lowbatt':-19,'stop':-14,'listening':19,'processing':14,
            'think':14,'idle':6,'roam':1,'silly':20,'bashful':-9}.get(vis,0)
        for ex,fl in [(EYE_L,1),(EYE_R,-1)]:
            by=EYE_CY-EYE_RY-31+br; mid=by-(19*fl if vis in('warn','stuck','fault') else 0)
            pygame.draw.lines(s,C_ACCENT,False,[(ex-130,by+9),(ex,mid),(ex+130,by+9)],7)
        ms={'roam':1.0,'speak':0.8,'silly':0.9,'listening':0.4,'idle':0.5,'slow':0.3,'processing':0.1,
            'think':0.1,'bashful':0.2,'stop':-0.3,'warn':-0.7,'stuck':-0.9,'fault':-1.0,'lowbatt':-0.5,
            }.get(vis,0.3)
        mr=pygame.Rect(MOUTH_CX-MOUTH_W//2,MOUTH_CY-MOUTH_H//2,MOUTH_W,MOUTH_H)
        # Bottom-half ellipse arc (apex at the bottom, corners raised) reads as a smile; the
        # top-half arc (apex at the top, corners drooped) reads as a frown. ms>=0 is meant to
        # mean "happy" states (roam/idle/speak/...), so it must map to the bottom-half arc —
        # was previously inverted (happy states frowned, fault states smiled).
        sa,ea=(math.pi*1.1,math.pi*1.9) if ms>=0 else (math.pi*0.1,math.pi*0.9)
        pygame.draw.arc(s,C_MOUTH,mr,sa,ea,7)
        # FR-1600-003/004: badge always reflects the true `state` (never `vis`/personality) so
        # fault/low-battery is always the unambiguous, non-decorated signal an operator sees.
        bc={'roam':C_GREEN,'slow':C_AMBER,'stop':C_RED,'warn':C_RED,'stuck':C_RED,'fault':C_RED,
            'lowbatt':C_AMBER,'listening':C_IDLE,'processing':C_IDLE,'idle':C_IDLE,'think':C_IDLE,
            'speak':C_GREEN}.get(state,C_DIM)
        if state in('fault','lowbatt') and math.sin(t*6)<0: bc=C_BG  # FR-1600-003/004: flash for attention
        pygame.draw.rect(s,(12,12,22),pygame.Rect(0,STATUS_Y,W,H-STATUS_Y))
        pygame.draw.line(s,C_DIM,(0,STATUS_Y),(W,STATUS_Y),1)
        # Telemetry line: badge/title/sensors/tilt/speed/clock, all consolidated here so every
        # piece of on-screen text lives in this 2-line footer rather than a separate HUD column.
        x=12; y=STATUS_Y+8
        def seg(text,color,bg=None):
            nonlocal x
            surf=self.f_sm.render(text,True,color,bg) if bg is not None else self.f_sm.render(text,True,color)
            s.blit(surf,(x,y)); x+=surf.get_width()+14
        seg(f' {state.upper()} ',C_BG,bc)
        seg('WILLY',C_ACCENT)
        for lbl,key in [('F','front'),('L','left'),('R','right')]:
            d=dists.get(key,999); col=C_RED if d<config.DIST_STOP else C_AMBER if d<config.DIST_SLOW else C_GREEN
            seg(f'{lbl}{d:3.0f}cm',col)
        tc=C_RED if tilt>config.IMU_TILT_LIMIT else C_AMBER if tilt>config.IMU_TILT_WARN else C_DIM
        seg(f'TILT{tilt:5.1f}',tc)
        seg(f'SPD{speed:+.2f}',C_TEXT)
        clock_surf=self.f_sm.render(time.strftime('%H:%M:%S'),True,C_DIM)
        s.blit(clock_surf,(W-clock_surf.get_width()-12,y))
        # Status line: single line now that telemetry owns the first line — still ellipsis-
        # truncated (via _wrap with max_lines=1) rather than silently clipped off-screen.
        status_ln=self._wrap(self.f_sm,status,W-24,max_lines=1)[0]
        s.blit(self.f_sm.render(status_ln,True,C_TEXT),(12,STATUS_Y+34))
        if heard:
            cx,cy=36,36
            pygame.draw.circle(s,C_GREEN,(cx,cy),22)
            pygame.draw.lines(s,C_BG,False,[(cx-10,cy),(cx-3,cy+9),(cx+12,cy-11)],5)
        pygame.display.flip()
