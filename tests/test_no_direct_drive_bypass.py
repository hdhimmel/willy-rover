import ast,os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# §3/§25 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: safety.py::SafetyController is meant
# to be the single authoritative gate between any motion source and the physical motors -- nothing
# else may call DriveBase directly. That's convention, not enforced by the type system (brain.py
# holds both self.motors, a real DriveBase, and self.safety, its SafetyController wrapper, side by
# side -- see brain.py's __init__), so it can silently regress. Static AST scan requested by the
# 2026-08-08 external code audit's "Required regression protection" item.

_REPO_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOTION_METHODS={'forward','reverse','turn_left','turn_right','brake',
                  'forward_for','reverse_for','turn_left_for','turn_right_for'}
# stop() is deliberately excluded: sonars/imu/encoders/current/voice/email/display/detector/
# mapping all have their own unrelated .stop() -- scanning for it would be nothing but false
# positives, not real bypass risk. safety.py's own SafetyController.stop() mirrors DriveBase's
# name on purpose (see safety.py's own comment), which is exactly what makes name-based scanning
# for "stop" useless here -- forward/reverse/turn_*/brake are unambiguous enough to be worth it.

def _production_files():
    for name in sorted(os.listdir(_REPO_DIR)):
        if name.endswith('.py') and name not in ('safety.py','motors.py'):
            yield os.path.join(_REPO_DIR,name)

def _find_motors_bypasses(src,filename):
    violations=[]
    tree=ast.parse(src,filename=filename)
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call): continue
        func=node.func
        if not isinstance(func,ast.Attribute) or func.attr not in _MOTION_METHODS: continue
        obj=func.value
        if isinstance(obj,ast.Attribute) and obj.attr=='motors':
            violations.append(f'{os.path.basename(filename)}:{node.lineno}: '
                               f'.motors.{func.attr}(...) bypasses SafetyController')
    return violations

def test_no_module_besides_safety_calls_drivebase_motion_methods_directly():
    """self.motors is the only place outside safety.py a DriveBase reference is held (brain.py's
    constructor: self.motors=DriveBase(); self.safety=SafetyController(self.motors)) -- no
    production file may call `<anything>.motors.<motion_method>(...)`."""
    violations=[]
    for path in _production_files():
        with open(path) as f: src=f.read()
        violations+=_find_motors_bypasses(src,path)
    assert violations==[],'\n'.join(violations)

def test_scan_actually_detects_a_real_bypass():
    # Proves the scan above isn't vacuously passing -- feed it a synthetic snippet with a real
    # bypass and confirm it's caught, the same way it would catch one accidentally added to
    # brain.py/navigation.py/retrieval_task.py/mapping.py.
    bad_src='def f(self):\n    self.motors.forward(0.5)\n'
    assert _find_motors_bypasses(bad_src,'synthetic.py')!=[]
