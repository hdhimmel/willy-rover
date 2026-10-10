import re,time,config,logsetup
log=logsetup.setup('logcheck')

# "Hey Willie, check your logs" (owner request 2026-10-10). A spoken summary of his own log: the
# problems of the last LOGCHECK_HOURS, most frequent first, briefly. Read-only; it reads the same
# rotating log the feature-request system reads (feature_requests.collect_evidence) and adds the
# plain WARNING/ERROR lines that are not EVENT= tagged (e.g. "Rear ToF: DROP BEHIND").

_LINE=re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (WARNING|ERROR)\s+(\S+) (.*)$')
_EVENT=re.compile(r'EVENT=(\w+)')
_NAMES={'IMU_FAULT':'IMU faults','ENCODERS_FAULT':'encoder faults','CURRENT_FAULT':'current monitor faults',
        'SONARS_FAULT':'sonar link faults','SONAR_FAULT':'sonar faults','BATTERY_ADC_FAULT':'battery sensor faults',
        'MOTORS_FAULT':'motor driver faults','TICK_OVERRUN':'control-loop overruns','LOW_BATTERY':'low battery warnings',
        'OBSTACLE_STOP':'obstacle stops','OVERCURRENT':'overcurrent trips','THERMAL':'temperature warnings',
        'HAILO_SERVER':'Hailo server problems','BRAKE_NOW':'emergency brakes','UNCOMMANDED_MOTION':'uncommanded motion reports'}
# Expected, not problems: start-up chatter and the voice pipeline's own housekeeping.
_IGNORE=('Self-test retry','Asking permission','No usable floor profile',
         # CONSEQUENCES, not causes: the fault that caused them is already counted. On willie's
         # real log (2026-10-10) "emergency stop" alone was 1168 lines.
         'emergency stop','motion rejected','rotation rejected')
# Plain names for the common untagged warnings, matched on the start of the message.
_PLAIN=(('Rear ToF: DROP','rear drop warnings'),('ToF: DROP AHEAD','front drop warnings'),
        ('INA260','current monitor read failures'),('BNO085','IMU read failures'),
        ('BATTERY SENSE SUSPECT','battery sensor disagreements'),('Rear camera','rear camera problems'),
        ('Hailo','Hailo problems'),('Voice','voice problems'))

def _key(level,msg):
    """(key, spoken name) for one WARNING/ERROR line, or None to skip it."""
    e=_EVENT.search(msg)
    if e:
        ev=e.group(1)
        if ev=='MOTOR_STALL' or 'stall' in msg.lower():
            m=re.search(r"wheels?=?\S*?\[?'?(\w\w)'?",msg)
            return f'stall:{m.group(1) if m else "?"}',f'wheel stalls on {m.group(1) if m else "a wheel"}'
        return ev,_NAMES.get(ev,ev.replace('_',' ').lower()+'s')
    if any(s in msg for s in _IGNORE): return None
    if 'STALL_FAULT' in msg:
        m=re.search(r"\['(\w+)'\]",msg)
        return f'stall:{m.group(1) if m else "?"}',f'wheel stalls on {m.group(1) if m else "a wheel"}'
    if 'Traceback' in msg: return None
    if '->' in msg.split('(')[0]: return None          # a state change caused by something counted
    for prefix,name in _PLAIN:
        if msg.startswith(prefix): return 'plain:'+name,name
    head=re.split(r' -- | \(|: |\.', msg,maxsplit=1)[0]
    head=re.sub(r'[\d.]+','#',head).strip()[:48]
    if not head: return None
    return 'msg:'+head.lower(),head.lower().replace('#','').strip()+(' errors' if level=='ERROR' else ' warnings')

def summarize(lines,now=None,hours=None):
    """[(spoken name, count, last_ts)] for the window, most frequent first."""
    now=time.time() if now is None else now
    hours=config.LOGCHECK_HOURS if hours is None else hours
    cutoff=now-hours*3600; cats={}
    for raw in lines:
        m=_LINE.match(raw.replace('\0','').rstrip('\n'))
        if not m: continue
        try: ts=time.mktime(time.strptime(m.group(1),'%Y-%m-%d %H:%M:%S'))
        except ValueError: continue
        if ts<cutoff or ts>now+60: continue
        k=_key(m.group(2),m.group(4))
        if k is None: continue
        c=cats.setdefault(k[0],[k[1],0,ts]); c[1]+=1; c[2]=max(c[2],ts)
    return sorted((tuple(v) for v in cats.values()),key=lambda c:-c[1])

def spoken(summary,hours=None,top=None):
    """One brief sentence for the voice."""
    hours=config.LOGCHECK_HOURS if hours is None else hours
    top=config.LOGCHECK_TOP if top is None else top
    span='today' if hours==24 else f'in the last {hours} hours'
    if not summary: return f"My logs are clean, no warnings or errors {span}."
    parts=[f'{n} {name}' if n!=1 else f'one of {name}' for name,n,_ in summary[:top]]
    more=len(summary)-top
    said=parts[0] if len(parts)==1 else ', '.join(parts[:-1])+' and '+parts[-1]
    last=max(t for _,_,t in summary)
    tail=f', and {more} other kind{"s" if more>1 else ""}' if more>0 else ''
    return f"{span.capitalize()}: {said}{tail}. The last one was at {time.strftime('%I:%M %p',time.localtime(last)).lstrip('0')}."

def check(now=None):
    """Read the log files: (sentence, found_problems). Never raises."""
    try:
        import os,glob
        root=config.WILLY_LOG_ROOT
        lines=[]
        for path in sorted(glob.glob(os.path.join(root,config.LOG_FILE+'*')),reverse=True)[:config.LOGCHECK_FILES]:
            with open(path,encoding='utf-8',errors='replace') as f: lines.extend(f)
        s=summarize(lines,now=now)
        return spoken(s),bool(s)
    except Exception:
        log.warning('Log check failed',exc_info=True)
        return "I couldn't read my logs just now.",False
