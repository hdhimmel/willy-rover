import csv,json,os,subprocess,threading,time,urllib.request,config,logsetup
log=logsetup.setup('battery_log')

# Battery log (owner, 2026-10-13): every BATTERY_LOG_INTERVAL_S (2 h) Willie records the time,
# pack voltage and estimated % to a local CSV -- always, online or not -- and then publishes it:
#   * GitHub: the CSV is committed to the 'battery-log' branch of the willy-rover repo (public, by
#     the owner's choice) from a separate clone at BATTERY_LOG_CLONE, so main is never touched.
#   * Home Assistant: sensor.willie_battery_voltage / sensor.willie_battery_level via HA's REST
#     API, if the HA token file (GOOGLE_HOME_CREDS_PATH) exists. Inert without it.
# A publish that fails (no internet) is NOT retried (owner): the CSV keeps growing locally and the
# next 2-hour cycle pushes everything. 'hours_on_charge' is the time he has been RUNNING since the voltage last jumped up
# by BATTERY_LOG_CHARGE_JUMP_V (a charge), so the log shows how long one charge lasts.
# Publishing runs on its own thread: git and HTTP must never block the 20 Hz tick.
# The % is the same display-only linear estimate as the HUD (sensors.ADC.battery_pct), not a
# state-of-charge model.

FIELDS=('time','volts','percent','hours_on_charge','bus_volts','bus_amps')

def _csv_path(): return os.path.join(config.WILLY_LOG_ROOT,config.BATTERY_LOG_CSV)


class BatteryLogger:
    def __init__(self,read,clock=time.time,publish=None,start_thread=True):
        """read() -> dict with FIELDS minus 'time'. publish(path) -> bool (default: GitHub + HA)."""
        self._read=read; self._clock=clock; self._publish=publish or self._publish_all
        self._next_publish=None; self._busy=False; self._start_thread=start_thread
        self._t0=clock(); self._last_beat=None
        # 2026-10-14: a restart no longer writes a row of its own -- the next row is due one
        # interval after the last one (it wrote a row 2 min after every service restart).
        last=self._load().get('last_record_t')
        due=clock()+config.BATTERY_LOG_FIRST_S
        if last and clock()-last<config.BATTERY_LOG_INTERVAL_S: due=max(due,last+config.BATTERY_LOG_INTERVAL_S)
        self._next_record=due

    @staticmethod
    def _state_path(): return os.path.join(config.WILLY_LOG_ROOT,'battery_charge_state.json')
    def _load(self):
        try:
            with open(self._state_path()) as f: return json.load(f)
        except (OSError,ValueError): return {}
    def _save(self,st):
        with open(self._state_path(),'w') as f: json.dump(st,f)

    def heartbeat(self,now):
        """Add this process's running time to hours_on_charge (2026-10-14). Every
        BATTERY_LOG_HEARTBEAT_S: the time since the last beat, or since start; nothing for time
        switched off. The old count only ever added the 2 min before a restart's first row."""
        st=self._load()
        st['on_h']=st.get('on_h',0.0)+max(0.0,now-(self._last_beat or self._t0))/3600.0
        self._last_beat=now; self._save(st)

    def tick(self):
        now=self._clock()
        if self._last_beat is None or now-self._last_beat>=config.BATTERY_LOG_HEARTBEAT_S:
            try: self.heartbeat(now)
            except Exception: log.warning('Battery log: heartbeat failed',exc_info=True)
        if now>=self._next_record:
            self._next_record=now+config.BATTERY_LOG_INTERVAL_S
            try:
                self.record(now)
                self._next_publish=now
            except Exception:
                log.warning('Battery log: reading failed',exc_info=True)
        if self._next_publish is not None and now>=self._next_publish and not self._busy:
            self._busy=True
            if self._start_thread:
                threading.Thread(target=self._do_publish,daemon=True,name='battery-log').start()
            else:
                self._do_publish()

    def _charge_state(self,now,volts):
        """Hours RUNNING since the last charge, persisted across reboots: heartbeat() adds the
        running time; a voltage jump of BATTERY_LOG_CHARGE_JUMP_V since the last row = a charge,
        and the count restarts from zero."""
        self.heartbeat(now)
        st=self._load()
        if 'last_v' not in st or volts-st['last_v']>=config.BATTERY_LOG_CHARGE_JUMP_V:
            st['on_h']=0.0
        st['last_v']=volts; st['last_t']=now; st['last_record_t']=now
        self._save(st)
        return round(st['on_h'],2)

    def record(self,now):
        r=dict(self._read())
        r['hours_on_charge']=self._charge_state(now,r['volts'])
        row={'time':time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(now)),
             **{k:(round(r[k],3) if isinstance(r.get(k),float) else r.get(k)) for k in FIELDS[1:]}}
        path=_csv_path(); new=not os.path.exists(path)
        with open(path,'a',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS)
            if new: w.writeheader()
            w.writerow(row)
        log.info(f'Battery log: {row["volts"]} V, {row["percent"]}%')
        self._last=row
        return row

    def _do_publish(self):
        try:
            ok=self._publish(_csv_path())
        except Exception:
            log.warning('Battery log: publish failed',exc_info=True); ok=False
        now=self._clock()
        self._next_publish=None            # offline: wait for the next cycle (owner)
        self._busy=False

    # ---- default publishers
    def _publish_all(self,path):
        gh=publish_github(path)
        publish_ha(getattr(self,'_last',None))      # best effort; never holds up the retry
        return gh


def _git(args,cwd,timeout=60):
    return subprocess.run(['git',*args],cwd=cwd,capture_output=True,text=True,timeout=timeout)

def publish_github(path):
    """Copy the CSV into the battery-log clone, commit if changed, push. True when GitHub has it."""
    clone=os.path.expanduser(config.BATTERY_LOG_CLONE)
    if not os.path.isdir(os.path.join(clone,'.git')):
        r=subprocess.run(['git','clone','--branch',config.BATTERY_LOG_BRANCH,'--single-branch',
                          config.BATTERY_LOG_REPO,clone],capture_output=True,text=True,timeout=120)
        if r.returncode!=0:
            log.info(f'Battery log: clone failed (offline?): {r.stderr.strip()[-200:]}'); return False
    else:
        _git(['pull','--rebase','-q'],clone)
    with open(path,'rb') as src, open(os.path.join(clone,config.BATTERY_LOG_CSV),'wb') as dst:
        dst.write(src.read())
    _git(['add',config.BATTERY_LOG_CSV],clone)
    if _git(['diff','--cached','--quiet'],clone).returncode!=0:
        _git(['-c','user.name=Willie','-c','user.email=willie@rover.local',
              'commit','-q','-m',f'battery {time.strftime("%Y-%m-%d %H:%M")}'],clone)
    r=_git(['push','-q','origin',f'HEAD:{config.BATTERY_LOG_BRANCH}'],clone,timeout=120)
    if r.returncode!=0:
        log.info(f'Battery log: push failed (offline?): {r.stderr.strip()[-200:]}'); return False
    log.info('Battery log: pushed to GitHub')
    return True

def publish_ha(row):
    if not row: return False
    path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.GOOGLE_HOME_CREDS_PATH)
    try:
        with open(path) as f: c=json.load(f)
        base,token=c['base_url'].rstrip('/'),c['token']
    except (OSError,KeyError,ValueError):
        return False                                  # no HA token: GitHub only
    ok=True
    for ent,state,unit,dc in (('sensor.willie_battery_voltage',row['volts'],'V','voltage'),
                              ('sensor.willie_battery_level',row['percent'],'%','battery')):
        body=json.dumps({'state':state,'attributes':{'unit_of_measurement':unit,'device_class':dc,
                         'state_class':'measurement','friendly_name':ent.split('.',1)[1].replace('_',' ').title()}}).encode()
        req=urllib.request.Request(f'{base}/api/states/{ent}',data=body,method='POST',
                                   headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=5): pass
        except Exception as e:
            log.info(f'Battery log: HA post failed: {e}'); ok=False
    return ok
