"""One reader per Pico. Framed ASCII in, newest frame out, with an age on it.

Master Hardware Design §4.7 moved encoder decode to Pico A over `uart4-pi5` and sonar
to Pico B over `uart2-pi5`. This is the Pi side of `firmware/README.md`'s wire protocol:
`$<body>*<XX>\\n`, XOR of everything between `$` and `*`, 115200 8N1.

WHY EVERY FRAME CARRIES ITS AGE, and why nothing here returns a distance. Software
Design **S-9**: `sensors.py` used to return `999.0` on a sonar timeout and `safety.py`
defaulted to the same value, so *I did not get a reading* and *nothing is in front of
me* were the same number. Over a local pin read that was survivable. Behind a serial
link it is a **fail-open** -- a dropped frame becomes a positive assertion of clear
path, at the layer that is supposed to be the availability floor.

So this class deals only in frames and their age. It never invents a value for a frame
that did not arrive, and it never converts silence into data. The decision about what a
stale frame *means* belongs to the consumer, and for sonar the answer is **stop**.

⚠ TWO DIFFERENT SILENCES, and conflating them is the whole bug:

  * a FRESH frame whose channel reads `-1` -- the Pico pinged and heard nothing back.
    For a sonar pointed at an open room that is the truth, and it means CLEAR.
  * NO FRESH FRAME -- the link is down, the board is unpowered, a wire is out. Nothing
    is known about the world. That means STOP.

The firmware distinguishes them for us by sending `-1` with a per-channel age, so the
Pi never has to guess.
"""
import logging, threading, time
import config

log = logging.getLogger('pico_link')


def checksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return c


def frame(body):
    return '${}*{:02X}\n'.format(body, checksum(body))


class PicoLink:
    """Newest good frame from one Pico, by type, each with the moment it landed.

    Thread-safe. Never raises at the consumer: a link that is down reports stale, which
    is a state the caller must already handle, rather than an exception it might not.
    """

    def __init__(self, device, name, baud=115200):
        self.device = device
        self.name = name
        self._baud = baud
        self._frames = {}          # 'E' / 'S' / 'I' -> (fields, monotonic_timestamp)
        self._lock = threading.Lock()
        self._serial = None
        self._running = False
        self._thread = None
        self._bad_checksums = 0
        self._opened = False

    # --- lifecycle ----------------------------------------------------------------
    def start(self):
        if config.SIMULATE_HARDWARE:
            self._running = True
            return
        try:
            import serial
            self._serial = serial.Serial(self.device, self._baud, timeout=0.2)
            self._opened = True
        except Exception:
            # A missing link must not stop the rover from booting. It reports unhealthy,
            # and the consumer decides -- which for sonar means refusing to drive forward.
            log.warning('%s: could not open %s; link reports stale', self.name, self.device,
                        exc_info=True)
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass

    # --- reading ------------------------------------------------------------------
    def _read_loop(self):
        buf = b''
        while self._running:
            try:
                n = self._serial.in_waiting
                if not n:
                    time.sleep(0.002)
                    continue
                buf += self._serial.read(n)
                if len(buf) > 4096:            # a babbling link must not eat memory
                    buf = buf[-1024:]
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    self._accept(line.strip().decode('ascii', 'replace'))
            except Exception:
                log.warning('%s: read failed', self.name, exc_info=True)
                time.sleep(0.05)

    def _accept(self, line):
        if not line.startswith('$') or '*' not in line:
            return
        body, _, cs = line[1:].rpartition('*')
        if cs.upper() != '{:02X}'.format(checksum(body)):
            self._bad_checksums += 1
            return
        fields = body.split(',')
        with self._lock:
            self._frames[fields[0]] = (fields, time.monotonic())

    # --- consumer API -------------------------------------------------------------
    def latest(self, kind):
        """(fields, age_seconds) for the newest good frame of that kind, or (None, None)."""
        with self._lock:
            got = self._frames.get(kind)
        if got is None:
            return None, None
        fields, t = got
        return fields, time.monotonic() - t

    def fresh(self, kind, max_age_s):
        """Fields if a good frame of that kind arrived within max_age_s, else None.

        This is the only accessor the safety path should use. There is deliberately no
        variant that returns the last known value regardless of age -- that is exactly
        the fail-open S-9 describes, and it must not be one attribute access away.
        """
        fields, age = self.latest(kind)
        if fields is None or age is None or age > max_age_s:
            return None
        return fields

    def send(self, command):
        """Bare command, one per line -- PING, ID, ZERO (A), RST (B). Never framed.

        ⚠ RST asserts the BNO085's reset line. Never send it speculatively.
        """
        if self._serial is None:
            return False
        try:
            self._serial.write((command + '\n').encode('ascii'))
            self._serial.flush()
            return True
        except Exception:
            log.warning('%s: write failed', self.name, exc_info=True)
            return False

    @property
    def bad_checksums(self):
        return self._bad_checksums

    def is_healthy(self, kind, max_age_s):
        return self.fresh(kind, max_age_s) is not None
