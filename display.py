import pygame,math,time,threading,os,config
os.environ.setdefault('SDL_VIDEODRIVER','wayland')
os.environ.setdefault('SDL_VIDEO_WAYLAND_WMCLASS','willy')
C_BG=(8,8,16);C_FACE=(30,30,45);C_EYE_W=(230,230,240)
C_ROAM=(0,200,80);C_STOP=(255,180,0);C_WARN=(255,80,40);C_IDLE=(80,120,255)
C_MOUTH=(200,200,210);C_ACCENT=(232,93,36);C_TEXT=(180,180,200);C_DIM=(60,60,70)
C_GREEN=(0,210,90);C_RED=(220,50,50);C_AMBER=(255,165,0)
W,H=800,480; FACE_CX=340; FACE_CY=210
EYE_L=250;EYE_R=430;EYE_CY=190;EYE_RX=70;EYE_RY=65;IRIS_R=34;PUPIL_R=15
MOUTH_CX=340;MOUTH_CY=310;MOUTH_W=190;MOUTH_H=55
STATUS_Y=400;HUD_X=560

class WillyFace:
    def __init__(self):
        pygame.init()
        self.screen=pygame.display.set_mode((W,H),pygame.FULLSCREEN|pygame.NOFRAME)
        pygame.display.set_caption('WildWilly'); pygame.mouse.set_visible(False)
        self.f_sm=pygame.font.SysFont('monospace',18)
        self.f_md=pygame.font.SysFont('monospace',26)
        self.f_xl=pygame.font.SysFont(None,80)
        self._state='idle';self._status='Initialising...';self._dists={'front':999,'left':999,'right':999}
        self._tilt=0.0;self._speed=0.0;self._lock=threading.Lock()
        self._t=0.0;self._blink_t=0.0;self._blink_next=3.5
        self._running=False;self._thread=None

    def update_state(self,state,status='',distances=None,tilt=0.0,speed=0.0):
        with self._lock:
            self._state=state
            if status: self._status=status
            if distances: self._dists=distances
            self._tilt=tilt; self._speed=speed

    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()

    def stop(self): self._running=False; pygame.quit()

    def _loop(self):
        clk=pygame.time.Clock()
        while self._running:
            for e in pygame.event.get():
                if e.type==pygame.QUIT or (e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE):
                    self._running=False
            self._t+=1.0/config.DISPLAY_FPS; self._draw(); clk.tick(config.DISPLAY_FPS)

    def _draw(self):
        s=self.screen; t=self._t; s.fill(C_BG)
        with self._lock:
            state=self._state; status=self._status[:44]
            dists=dict(self._dists); tilt=self._tilt; speed=self._speed
        ic={'idle':C_IDLE,'roam':C_ROAM,'slow':C_STOP,'stop':C_WARN,'warn':C_RED,'stuck':C_RED,'think':C_IDLE,'speak':C_ROAM}.get(state,C_IDLE)
        pygame.draw.ellipse(s,C_FACE,pygame.Rect(FACE_CX-220,FACE_CY-170,440,320))
        self._blink_next-=1.0/config.DISPLAY_FPS
        if self._blink_next<=0: self._blink_t=0.12; self._blink_next=3.0+math.sin(t*0.7)*1.5
        bf=0.0
        if self._blink_t>0:
            self._blink_t-=1.0/config.DISPLAY_FPS; h=0.06
            bf=(1.0-(self._blink_t-h)/h) if self._blink_t>h else self._blink_t/h
        pb=math.sin(t*1.2)*5 if state=='roam' else 0
        ps=math.cos(t*0.8)*4 if state in('roam','idle') else 0
        for ex in [EYE_L,EYE_R]:
            ery=max(2,int(EYE_RY*(1.0-bf)))
            pygame.draw.ellipse(s,C_EYE_W,pygame.Rect(ex-EYE_RX,EYE_CY-ery,EYE_RX*2,ery*2))
            if bf<0.9:
                ix=ex+int(ps*(1 if ex<FACE_CX else -1)); iz=EYE_CY+int(pb)
                pygame.draw.circle(s,ic,(ix,iz),IRIS_R)
                pygame.draw.circle(s,(0,0,0),(ix,iz),PUPIL_R)
                pygame.draw.circle(s,(255,255,255),(ix-7,iz-7),5)
            pygame.draw.ellipse(s,C_DIM,pygame.Rect(ex-EYE_RX,EYE_CY-ery,EYE_RX*2,ery*2),2)
        br={'warn':-14,'stuck':-11,'stop':-7,'think':7,'idle':3,'roam':1}.get(state,0)
        for ex,fl in [(EYE_L,1),(EYE_R,-1)]:
            by=EYE_CY-EYE_RY-16+br; mid=by-(9*fl if state in('warn','stuck') else 0)
            pygame.draw.lines(s,C_ACCENT,False,[(ex-52,by+4),(ex,mid),(ex+52,by+4)],4)
        ms={'roam':1.0,'speak':0.8,'idle':0.5,'slow':0.3,'think':0.1,'stop':-0.3,'warn':-0.7,'stuck':-0.9}.get(state,0.3)
        mr=pygame.Rect(MOUTH_CX-MOUTH_W//2,MOUTH_CY-MOUTH_H//2,MOUTH_W,MOUTH_H)
        sa,ea=(math.pi*0.1,math.pi*0.9) if ms>=0 else (math.pi*1.1,math.pi*1.9)
        pygame.draw.arc(s,C_MOUTH,mr,sa,ea,5)
        pygame.draw.line(s,C_DIM,(HUD_X-10,0),(HUD_X-10,STATUS_Y),1)
        bc={'roam':C_GREEN,'slow':C_AMBER,'stop':C_RED,'warn':C_RED,'stuck':C_RED,'idle':C_IDLE,'think':C_IDLE,'speak':C_GREEN}.get(state,C_DIM)
        s.blit(self.f_md.render(f' {state.upper()} ',True,C_BG,bc),(HUD_X,18))
        s.blit(self.f_xl.render('WILLY',True,C_ACCENT),(HUD_X,54))
        for i,(lbl,key) in enumerate([('F','front'),('L','left'),('R','right')]):
            d=dists.get(key,999); col=C_RED if d<config.DIST_STOP else C_AMBER if d<config.DIST_SLOW else C_GREEN
            s.blit(self.f_md.render(f'{lbl} {d:3.0f}cm',True,col),(HUD_X,148+i*36))
        tc=C_RED if tilt>config.IMU_TILT_LIMIT else C_AMBER if tilt>config.IMU_TILT_WARN else C_DIM
        s.blit(self.f_sm.render(f'TILT {tilt:.1f}deg',True,tc),(HUD_X,268))
        pygame.draw.rect(s,C_DIM,pygame.Rect(HUD_X,296,220,14),1)
        sw=int(abs(speed)*220)
        pygame.draw.rect(s,C_GREEN if speed>=0 else C_AMBER,pygame.Rect(HUD_X,296,sw,14))
        pygame.draw.rect(s,(12,12,22),pygame.Rect(0,STATUS_Y,W,H-STATUS_Y))
        pygame.draw.line(s,C_DIM,(0,STATUS_Y),(W,STATUS_Y),1)
        s.blit(self.f_sm.render(status,True,C_TEXT),(12,STATUS_Y+10))
        s.blit(self.f_sm.render(time.strftime('%H:%M:%S'),True,C_DIM),(W-100,STATUS_Y+10))
        pygame.display.flip()
