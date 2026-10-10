"""Firmware update over the Pi UART (owner request 2026-10-10). Shared by Pico A and Pico B.

Installed ONCE over USB, together with launcher.py (as main.py). Neither is ever replaced over
the UART: they are what makes a bad update recoverable. Only app.py -- the board's firmware,
firmware/pico_a.py or pico_b.py -- is updated this way.

Protocol (lines from the Pi, each answered with one $U,... frame):
    UPD BEGIN <size> <adler32 hex>   start: app.new opened for writing          -> U,ready
    UPD DATA <seq> <hex bytes>       chunk <seq>, in order; a repeat is re-acked -> U,ack,<seq>
    UPD END                          size + adler32 checked                      -> U,ok | U,err,...
    UPD COMMIT                       app.py -> app_prev.py, app.new -> app.py,
                                     'trial' written, board resets               -> U,commit
    UPD CONFIRM                      the new firmware is good: 'trial' removed   -> U,confirmed
    UPD ROLLBACK                     app_prev.py back, board resets              -> U,rollback
    UPD ABORT                        app.new discarded                           -> U,aborted
Nothing on the board changes until END has verified the whole file AND the Pi sends COMMIT.
"""
import os
import machine
try:
    import binascii
except ImportError:
    import ubinascii as binascii


def adler32(data, a=1, b=0):
    for x in data:
        a = (a + x) % 65521
        b = (b + a) % 65521
    return a, b


def _rm(name):
    try:
        os.remove(name)
    except OSError:
        pass


class Receiver:
    def __init__(self, send):
        self.send = send
        self.f = None
        self.verified = False

    def handle(self, line):
        """True if `line` (raw bytes, stripped, NOT upper-cased) was an update command."""
        if not line.startswith(b"UPD "):
            return False
        parts = line.split(b" ")
        op = parts[1] if len(parts) > 1 else b""
        try:
            if op == b"BEGIN":
                self._close()
                _rm("app.new")
                self.exp_size = int(parts[2])
                self.exp_sum = int(parts[3], 16)
                self.size = 0
                self.a, self.b = 1, 0
                self.seq = 0
                self.verified = False
                self.f = open("app.new", "wb")
                self.send("U,ready")
            elif op == b"DATA":
                seq = int(parts[2])
                if self.f is None:
                    self.send("U,err,no transfer")
                elif seq == self.seq - 1:
                    self.send("U,ack,{}".format(seq))      # our ack was lost: re-ack, no rewrite
                elif seq != self.seq:
                    self.send("U,err,seq {} expected {}".format(seq, self.seq))
                else:
                    data = binascii.unhexlify(parts[3])
                    self.f.write(data)
                    self.size += len(data)
                    self.a, self.b = adler32(data, self.a, self.b)
                    self.seq += 1
                    self.send("U,ack,{}".format(seq))
            elif op == b"END":
                self._close()
                got = (self.b << 16) | self.a
                if self.size != self.exp_size or got != self.exp_sum:
                    _rm("app.new")
                    self.send("U,err,verify size {} sum {:08x}".format(self.size, got))
                else:
                    self.verified = True
                    self.send("U,ok")
            elif op == b"COMMIT":
                if not self.verified:
                    self.send("U,err,not verified")
                    return True
                _rm("app_prev.py")
                try:
                    os.rename("app.py", "app_prev.py")
                except OSError:
                    pass
                os.rename("app.new", "app.py")
                with open("trial", "w") as t:
                    t.write("0")
                self.send("U,commit")
                self._reset()
            elif op == b"CONFIRM":
                _rm("trial")
                self.send("U,confirmed")
            elif op == b"ROLLBACK":
                if "app_prev.py" not in os.listdir():
                    self.send("U,err,no previous firmware")
                    return True
                _rm("app_bad.py")
                os.rename("app.py", "app_bad.py")
                os.rename("app_prev.py", "app.py")
                _rm("trial")
                self.send("U,rollback")
                self._reset()
            elif op == b"ABORT":
                self._close()
                _rm("app.new")
                self.verified = False
                self.send("U,aborted")
            else:
                self.send("U,err,unknown")
        except Exception as e:
            self._close()
            self.send("U,err,{}".format(str(e)[:40].replace(",", ";")))
        return True

    def _close(self):
        if self.f is not None:
            try:
                self.f.close()
            except Exception:
                pass
            self.f = None

    @staticmethod
    def _reset():
        import time
        time.sleep_ms(100)          # let the reply leave the UART
        machine.reset()
