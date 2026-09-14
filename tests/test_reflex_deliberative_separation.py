import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

# P0, 2026-09-14 review: "No Hailo output should be capable of bypassing deterministic safety
# controls." The review asked for this separation to be MAINTAINED, which means it needs a test
# rather than a convention -- the layering is currently held up by nothing but the fact that
# nobody has imported the wrong module yet.
#
#   REFLEX (deterministic, must never consult a model):
#       sensors.py   sonar, encoders, IMU, current monitoring
#       safety.py    the single authoritative gate to the motors
#       motors.py    the hardware itself
#
#   DELIBERATIVE (may be wrong, may be slow, may be unavailable):
#       hailo_llm.py  ai_provider.py  cloud_ai.py  vision.py  world_model.py  navigation.py
#
# The rule is directional. Deliberative code may call INTO safety.py -- that is exactly how an AI
# decision is meant to reach the wheels, through SafetyController.request() with its clamps. What
# must never happen is the reverse: a reflex module consulting a model, because then a model
# failure becomes a safety failure, and the deterministic layer stops being deterministic.
#
# tests/test_no_direct_drive_bypass.py covers the other half -- that nothing skips safety.py on
# the way to DriveBase. Together they say: everything goes through safety.py, and safety.py asks
# no model for permission.

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REFLEX_MODULES = ['sensors.py', 'safety.py', 'motors.py']

DELIBERATIVE_MODULES = {
    'hailo_llm', 'ai_provider', 'cloud_ai', 'vision', 'hailo_stt',
    'world_model', 'navigation', 'mapping', 'retrieval_task', 'pursuit_task',
}


def _imports(path):
    """Every module name imported by a file, by either import form."""
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.add(node.module.split('.')[0])
    return names


def test_no_reflex_module_imports_a_deliberative_one():
    """The core of the rule. A sonar reading must never depend on a model being loaded, awake,
    or correct."""
    offenders = []
    for name in REFLEX_MODULES:
        path = os.path.join(_REPO, name)
        if not os.path.exists(path):
            continue
        bad = _imports(path) & DELIBERATIVE_MODULES
        if bad:
            offenders.append(f'{name} imports {sorted(bad)}')
    assert not offenders, 'reflex layer reaching into the deliberative layer: ' + '; '.join(offenders)


def test_no_reflex_module_mentions_an_ai_backend_even_in_a_string():
    """Catches the import-inside-a-function and importlib dodges that an import scan misses.
    Deliberately crude: any occurrence of these names in a reflex module is worth a human look,
    and there is no legitimate reason for one to appear."""
    offenders = []
    for name in REFLEX_MODULES:
        path = os.path.join(_REPO, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            src = f.read().lower()
        for token in ('hailo', 'ai_provider', 'cloud_ai', 'generate_all', 'ask_sync'):
            if token in src:
                offenders.append(f'{name} mentions {token!r}')
    assert not offenders, '; '.join(offenders)


def test_safety_controller_needs_no_ai_to_construct_or_stop():
    """The property stated behaviourally rather than structurally: the emergency path works with
    no model present anywhere. If this ever needs an AI object to be importable, the deterministic
    layer has acquired a dependency on the probabilistic one."""
    from motors import DriveBase
    from safety import SafetyController
    sc = SafetyController(DriveBase())
    sc.update_context(front_cm=5.0, tilt_deg=0.0, motion_enabled=True)
    sc.emergency_stop('test')          # must not raise, must not consult anything
    assert sc is not None


def test_the_ai_reaches_the_motors_only_through_safety():
    """The permitted direction, asserted so the rule is not misread as "AI must not touch motion".
    It may -- via SafetyController, which clamps duration and speed regardless of what was asked
    for. brain.py::_apply_ai_motion calls self.safety.request(...), never self.motors.*, and
    tests/test_no_direct_drive_bypass.py enforces that repo-wide."""
    with open(os.path.join(_REPO, 'brain.py'), encoding='utf-8') as f:
        src = f.read()
    start = src.index('def _apply_ai_motion')
    body = src[start:start + 1400]
    assert 'self.safety.request' in body, 'AI motion no longer goes through SafetyController'
    assert 'self.motors.' not in body, 'AI motion path touches DriveBase directly'


def test_safety_clamps_are_not_advisory():
    """A model may ask for anything; the clamp is what makes the request safe, which is the
    review's "Hailo may recommend an action; Hailo must not be the authority that makes the
    action safe." Pinned against the config the clamp reads."""
    import config
    assert config.MAX_COMMAND_DURATION_S > 0
    assert 0 < config.SPEED_MAX <= 1.0
