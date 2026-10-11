#!/usr/bin/env python3
"""Set Willie's GPS home from coordinates, with no fix needed (2026-10-11: he lives in a basement
where the GPS sees no sky). Get them from Google Maps: long-press the house, copy the numbers.

    venv/bin/python3 scripts/set_gps_home.py 40.712776 -74.005974 --address "1 Main St, Town NJ 00000"
    venv/bin/python3 scripts/set_gps_home.py --show

The address is what he says to "what's your address?". It is stored only on the rover, in the
gitignored gps_home.json, never in the repository.

Restart the service afterwards so it reads the new home. "This is home", said outdoors with a
fix, replaces it with an averaged measured position.
"""
import json,os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def main(argv):
    path=os.path.join(config.WILLY_MEMORY_ROOT,config.GPS_HOME_PATH)
    if len(argv)==2 and argv[1]=='--show':
        try: print(open(path).read())
        except OSError: print('No home set.')
        return 0
    address=None
    if '--address' in argv:
        i=argv.index('--address')
        if i+1>=len(argv): print(__doc__); return 2
        address=argv[i+1]; argv=argv[:i]+argv[i+2:]
    if len(argv)!=3:
        print(__doc__); return 2
    lat,lon=float(argv[1].rstrip(',')),float(argv[2])
    if not (-90<=lat<=90 and -180<=lon<=180):
        print('Out of range: latitude -90..90, longitude -180..180.'); return 2
    with open(path,'w') as f:
        home={'lat':lat,'lon':lon,'fixes':0,'spread_m':None,'source':'entered','t':time.time()}
        if address: home['address']=address
        json.dump(home,f)
    print(f'Home set to {lat:.6f}, {lon:.6f} -> {path}. Restart willy-rover to use it.')
    return 0

if __name__=='__main__':
    sys.exit(main(sys.argv))
