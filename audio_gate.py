import collections,struct,time,config,logsetup
log=logsetup.setup('audio_gate')

# CPU savings on the listening path (owner 2026-10-11). py-spy on the idle service: the wake-word
# model (openWakeWord, ~29% of busy samples) scores every 80 ms block, in a silent room too.
#
# WakeGate: score only while there is sound. Quiet blocks are kept in a short pre-roll instead of
# being scored; when sound starts, the model is reset and the pre-roll is scored first, so the
# start of "Hey Willie" is not lost. A HANG keeps scoring for a while after the sound stops (the
# word's tail, a pause between words). Sound = the cheap RMS the loop already computes, compared
# with the tracked noise floor -- or, with a ReSpeaker array plugged in, its hardware VAD flag.
#
# pick_input: with a ReSpeaker array present, capture it at 16 kHz, channel 0 (its beamformed,
# echo-cancelled, noise-suppressed output), so the 48 kHz -> 16 kHz decimation disappears.


class WakeGate:
    def __init__(self,preroll_blocks=None,hang_s=None,margin=None,floor=None,clock=time.monotonic):
        self.preroll=collections.deque(maxlen=preroll_blocks or config.WAKE_GATE_PREROLL_BLOCKS)
        self.hang_s=config.WAKE_GATE_HANG_S if hang_s is None else hang_s
        self.margin=config.WAKE_GATE_MARGIN if margin is None else margin
        self.floor=config.WAKE_GATE_MIN_RMS if floor is None else floor
        self.clock=clock; self.open_until=0.0
        self.skipped=0; self.opened=0

    def sound(self,rms,noise_rms,vad=None):
        """True if this block counts as sound. A hardware VAD, when given, decides."""
        if vad is not None: return bool(vad)
        return rms>max(self.floor,(noise_rms or 0.0)*self.margin)

    def feed(self,block,rms,noise_rms,vad=None):
        """Blocks to score now (possibly several: the pre-roll on onset), and whether the wake
        model must be reset first (True only at an onset, before the pre-roll)."""
        now=self.clock()
        if self.sound(rms,noise_rms,vad):
            was_open=now<self.open_until
            self.open_until=now+self.hang_s
            if was_open: return [block],False
            self.opened+=1
            out=list(self.preroll)+[block]; self.preroll.clear()
            return out,True
        if now<self.open_until: return [block],False
        self.preroll.append(block); self.skipped+=1
        return [],False


class ReSpeakerVAD:
    """Hardware voice activity from a Seeed ReSpeaker Mic Array v2.0 (XVF-3000, USB 2886:0018),
    read with the vendor control request its tuning.py uses: parameter VOICEACTIVITY = (id 19,
    offset 32, int). Built 2026-10-11 WITHOUT the array on hand -- unverified on hardware; any
    failure makes read() return None and the energy gate takes over."""
    VID,PID=0x2886,0x0018
    def __init__(self,dev=None):
        self.dev=dev
        if dev is None:
            try:
                import usb.core; self.dev=usb.core.find(idVendor=self.VID,idProduct=self.PID)
            except Exception: self.dev=None
        self._failed=False
    @property
    def present(self): return self.dev is not None and not self._failed
    def read(self):
        if not self.present: return None
        try:
            cmd=0x80|32|0x40                         # read | offset 32 | int
            resp=self.dev.ctrl_transfer(0xC0,0,cmd,19,8,100)   # IN | VENDOR | DEVICE
            return struct.unpack('<ii',bytes(resp))[0]
        except Exception as e:
            self._failed=True
            log.warning(f'ReSpeaker VAD read failed ({e}); using the energy gate')
            return None


def pick_input(devices=None):
    """(device, samplerate, label). A ReSpeaker array (name contains one of AUDIO_ARRAY_NAMES)
    is captured at 16 kHz; otherwise the configured mic at its configured rate."""
    if devices is None:
        try:
            import sounddevice as sd; devices=sd.query_devices()
        except Exception: devices=[]
    for d in devices:
        name=d.get('name','') if isinstance(d,dict) else ''
        if d.get('max_input_channels',0)>0 and any(k.lower() in name.lower() for k in config.AUDIO_ARRAY_NAMES):
            return name,16000,'array'
    return config.AUDIO_INPUT_DEVICE,int(config.AUDIO_INPUT_RATE),'mic'
