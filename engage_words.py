"""FR-2400 engagement words (2026-10-15): a topic -> one spoken line; a spoken answer -> facts.

The cloud model writes the line in Willie's persona (CloudAIProvider defaults to
CLAUDE_CHAT_SYSTEM when given no system and no schema) from TEXT facts only -- never an image
(FR-1800). It gets ENGAGE_WORDS_TIMEOUT_S; slow, offline, failing or junk replies fall back to
config.ENGAGE_TEMPLATES. Nothing here raises."""
import json,re,threading,time
import config,logsetup
log=logsetup.setup('engage')

_DESCRIBE={
    'greet_known':'You have just noticed {name}, someone you know, nearby. Greet them.',
    'greet_stranger':"Someone you don't know is here. Say hello, say you are Willie, and ask their name.",
    'ask_room':"You don't know which room you are in. Ask the person what room this is.",
    'ask_thing':'You can see a {thing}. Ask the person whose it is or what it is.',
    'callback':'You remember something: {facts}. Mention it in a friendly way.',
    'change':'You noticed a change in the {room}: {facts}. Mention it.',
    'ask_person':'Ask {name} a friendly question about their day.',
}
_REFUSALS=re.compile(r"\b(i'?m sorry|i can'?t|as an ai|i cannot)\b",re.I)

def when_words(t,now=None):
    now=now or time.time(); d=now-t
    if d<15*60: return 'just now'
    lt,ln=time.localtime(t),time.localtime(now)
    days=(time.mktime(ln[:3]+(0,0,0,0,0,-1))-time.mktime(lt[:3]+(0,0,0,0,0,-1)))/86400
    part='morning' if lt.tm_hour<12 else 'afternoon' if lt.tm_hour<17 else 'evening'
    if days<0.5: return f'this {part}'
    if days<1.5: return 'last night' if lt.tm_hour>=21 else f'yesterday {part}'
    if days<7: return f'{round(days)} days ago'
    return time.strftime('on %B %d',lt)

def _keys(topic):
    about=topic.facts.get('about')
    return ([f'{topic.kind}_{about}'] if about else [])+[topic.kind]

def template(topic,n=0):
    for key in _keys(topic):
        for i in range(len(config.ENGAGE_TEMPLATES.get(key,[]))):
            tpl=config.ENGAGE_TEMPLATES[key][(n+i)%len(config.ENGAGE_TEMPLATES[key])]
            try: return tpl.format(**topic.facts)
            except (KeyError,IndexError): continue
    return "Hello!" if topic.kind.startswith('greet') else "Hi there."

def _capped(fn,timeout_s):
    box={}
    def run():
        try: box['r']=fn()
        except Exception as e: box['e']=e
    t=threading.Thread(target=run,daemon=True,name='engage-words'); t.start(); t.join(timeout_s)
    if t.is_alive(): log.info(f'Engage words: cloud gave nothing in {timeout_s:.0f} s'); return None
    if 'e' in box: log.info(f"Engage words: cloud failed ({box['e']})"); return None
    return box.get('r')

def _usable_line(txt):
    if not isinstance(txt,str): return None
    txt=txt.strip().strip('"').strip()
    if not txt or len(txt)>config.ENGAGE_LINE_MAX_CHARS or txt.startswith('{') or _REFUSALS.search(txt): return None
    return txt

def line(topic,cloud,timeout_s=None):
    fallback=template(topic,n=int(time.time())//60)
    if cloud is None or not getattr(cloud,'available',False): return fallback
    desc=_DESCRIBE.get(topic.kind,'Say something friendly.')
    try: desc=desc.format(facts=json.dumps(topic.facts),**topic.facts)
    except (KeyError,IndexError): desc=desc.replace('{','(').replace('}',')')
    prompt=(f'{desc} Facts: {json.dumps(topic.facts)}. You are speaking first, out loud. Say ONE short '
            f'friendly sentence, under 20 words{", ending with your question" if topic.question else ""}. '
            f'Reply with only the sentence.')
    r=_capped(lambda: cloud.ask_sync(prompt),timeout_s or config.ENGAGE_WORDS_TIMEOUT_S)
    got=_usable_line(getattr(r,'payload',None)) if r is not None and getattr(r,'parse_success',False) else None
    return got or fallback

_SCHEMAS={'greet_stranger':{'name':str},'ask_room':{'room':str},'ask_thing':{'label':str},'ask_person':{'note':str}}
_ASK={'greet_stranger':'the person\'s first name as "name"',
      'ask_room':'the room name, lower case, as "room"',
      'ask_thing':'a short label for the thing as "label" (e.g. "Storm\'s ball") and its owner\'s name as "owner" (null if none)',
      'ask_person':'what they told you, as a short phrase in the second person past tense without "you", as "note"'}
_NOT_A_NAME={'no','yes','what','huh','sorry','i','me','nobody','none','willie'}

def _offline(topic,text):
    t=text.strip().rstrip('.!?').strip()
    if not t: return None
    if topic.kind=='greet_stranger':
        m=re.fullmatch(r"(?:(?:hi|hello|hey)[, ]+)?(?:my name is|i'?m|i am|it'?s|call me)?\s*([A-Za-z][a-z'-]+)",t,re.I)
        name=m.group(1).capitalize() if m else None
        return {'name':name} if name and name.lower() not in _NOT_A_NAME else None
    if topic.kind=='ask_room':
        m=re.fullmatch(r"(?:this is |it'?s |we'?re in |you'?re in )?(?:the |my |our )?([a-z ]{3,30}?)",t.lower())
        room=m.group(1).strip() if m else None
        return {'room':room} if room and room not in ('no','yes','i don\'t know','not sure') else None
    if topic.kind=='ask_thing':
        thing=topic.facts.get('thing','thing')
        m=re.fullmatch(r"(?i:it'?s |that'?s |it belongs to |that belongs to )?([A-Z][a-z]+)'?s?(?: \w+)?",t)
        if m: return {'owner':m.group(1),'label':f"{m.group(1)}'s {thing}"}
        return None
    if topic.kind=='ask_person':
        return {'note':t[0].lower()+t[1:]} if len(t)>=3 else None
    return None

def extract(topic,text,cloud,timeout_s=None):
    text=(text or '').strip()
    if not text or topic.kind not in _SCHEMAS: return None
    if cloud is not None and getattr(cloud,'available',False):
        prompt=(f'Willie asked: "{template(topic)}" The person answered: "{text}". '
                f'Return JSON with {_ASK[topic.kind]}. If the answer does not contain it, return {{}}.')
        r=_capped(lambda: cloud.ask_sync(prompt,schema=_SCHEMAS[topic.kind]),timeout_s or config.ENGAGE_WORDS_TIMEOUT_S)
        if r is not None and getattr(r,'parse_success',False) and isinstance(r.payload,dict):
            out={k:v for k,v in r.payload.items() if k in ('name','room','label','owner','note') and v}
            if out: return out
    return _offline(topic,text)
