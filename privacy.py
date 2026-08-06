import os,time,glob,config,logsetup
log=logsetup.setup('privacy')

# FR-1800: microphone/camera data handling and retention. This module holds no mic/camera
# access itself — voice.py and vision.py must each check mic_enabled()/camera_enabled() before
# opening their device, and re-check periodically while running (a disable during an active
# session must take effect promptly, not just at next startup).

def _flag_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),config.MIC_CAMERA_DISABLE_FLAG_PATH)

def mic_camera_disabled():
    # FR-1800-005: independent of and in addition to E-stop — presence of the file is the only
    # signal that matters, its content is ignored.
    return os.path.exists(_flag_path())

def mic_enabled(): return not mic_camera_disabled()
def camera_enabled(): return not mic_camera_disabled()

def disable_mic_camera(reason=''):
    path=_flag_path(); os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w') as f: f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {reason}\n')
    log.warning(f'Mic/camera disabled for privacy: {reason or "no reason given"}')

def enable_mic_camera():
    path=_flag_path()
    if os.path.exists(path): os.remove(path)
    log.info('Mic/camera re-enabled.')

def note_cloud_send(display,voice,what):
    # FR-1800-003: explicit indication (voice and/or display) whenever data leaves the device
    # via the FR-1400 cloud AI fallback path. Callers pass their live display/voice handles (may
    # be None) rather than this module importing them, to avoid a circular import with brain.py.
    msg=f'Sending {what} to cloud AI'
    log.info(msg)
    if display is not None:
        try: display.update_state(state='think',status=msg)
        except Exception: pass
    if voice is not None:
        try: voice.speak('One moment, checking with a cloud service for this one.',tone='neutral')
        except Exception: pass

def purge_expired(dir_path,max_age_days=None,pattern='*'):
    # FR-1800-004: generic retention sweep — delete files under dir_path older than
    # max_age_days. Used by memory_store.py for any on-disk demonstration snapshots and by
    # anything else that persists raw audio/camera artifacts (default is not to persist them
    # at all per RAW_AUDIO_CAMERA_PERSIST, but diagnostic mode can opt in per FR-1800-002).
    max_age_days=config.DATA_RETENTION_DAYS if max_age_days is None else max_age_days
    if not os.path.isdir(dir_path): return 0
    cutoff=time.time()-max_age_days*86400
    removed=0
    for path in glob.glob(os.path.join(dir_path,pattern)):
        try:
            if os.path.isfile(path) and os.path.getmtime(path)<cutoff:
                os.remove(path); removed+=1
        except OSError as e:
            log.warning(f'purge_expired could not remove {path}: {e}')
    if removed: log.info(f'Retention purge: removed {removed} file(s) older than {max_age_days}d from {dir_path}')
    return removed
