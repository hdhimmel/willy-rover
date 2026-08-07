#!/usr/bin/env python3
import sys,os,signal
sys.path.insert(0,os.path.dirname(__file__))
from brain import RoverBrain
if __name__=='__main__':
    # systemd sends SIGTERM on stop/restart; route it through the same KeyboardInterrupt path
    # run() already handles for SIGINT so shutdown (and RoverBrain.stop()'s cleanup) actually runs.
    signal.signal(signal.SIGTERM,signal.default_int_handler)
    RoverBrain().run()
