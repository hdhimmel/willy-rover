import os,logging
log=logging.getLogger('storage')
# Deliberately NOT logsetup.setup('storage') -- config.py needs to import this module (to resolve
# WILLY_*_ROOT at load time) and logsetup.py itself imports config, which would make
# config -> storage -> logsetup -> config a circular import. A bare getLogger still lands in the
# same rotating file once any other module calls logsetup.setup() (they all share one root
# logger's handlers) -- this only differs from logsetup.setup('storage') if a log call somehow
# happened before any module has done that, which doesn't occur in practice (config is always
# imported before anything logs).

# §13 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: "do not hard-code assumptions about
# exact mount paths... create configurable storage paths" (WILLY_DATA_ROOT/MAP_ROOT/MEMORY_ROOT/
# LOG_ROOT). This unit currently has no physically separate SSD/SD split — everything lives on
# one microSD card (confirmed via df/mount 2026-08-08); the master doc's own §13.4 boot-from-SSD
# migration is still a pending item, not done. resolve_root() makes the location genuinely
# overridable via env var for whenever that migration happens, while its *default* (unset env
# var) deliberately anchors to this file's own directory -- exactly matching the
# __file__-relative resolution memory_store.py/world_model.py/logsetup.py each used to do
# independently -- so behavior on this unit is unchanged today, and unlike a CWD-relative
# default, still works correctly for a manual `python3 diagnostics.py` run from any directory,
# not just under systemd's WorkingDirectory=/home/hhimmel/rover.

_REPO_DIR=os.path.dirname(os.path.abspath(__file__))

def resolve_root(env_var,default_relative='.'):
    """env_var set -> used as-is (expected to be an absolute path to wherever that storage tier
    actually lives, e.g. a mounted SSD). Unset -> default_relative resolved against this repo's
    own directory, not the process's current working directory."""
    val=os.environ.get(env_var)
    if val: return val
    return os.path.normpath(os.path.join(_REPO_DIR,default_relative))

def check_storage(roots):
    """§13: "add startup checks for storage availability and permissions." roots is a
    {name:path} dict (e.g. config's WILLY_*_ROOT values). Creates a path if it's missing and
    creatable (a fresh SD card or a first-boot SSD mount won't already have these directories);
    reports a problem if it can't be created, isn't a directory, or isn't writable. Returns
    (ok,problems) matching brain.py::_self_test()'s own (bool,str-list-joinable) shape so the
    caller can fold this straight into its existing problems list."""
    problems=[]
    for name,path in roots.items():
        if not os.path.isdir(path):
            try: os.makedirs(path,exist_ok=True)
            except OSError as e:
                problems.append(f'{name} root {path!r} missing and could not be created: {e}')
                continue
        probe=os.path.join(path,'.willy_write_test')
        try:
            with open(probe,'w') as f: f.write('ok')
            os.remove(probe)
        except OSError as e:
            problems.append(f'{name} root {path!r} not writable: {e}')
    return (not problems),problems
