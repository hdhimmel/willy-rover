import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest

# Lock-in for the Hailo DEVICE SHARING fix, per the 2026-09-14 review's "do not undo these".
# The other three fixes each have a test file already (test_hailo_chatml.py,
# test_hailo_statelessness.py, test_hailo_generation_params.py). This one was described only in a
# comment in hailo_llm.py and never asserted, which makes it the easiest of the four to lose.
#
# WHAT IT PROTECTS. The Hailo-10H is one physical device shared by vision and the LLM. Building a
# second, independently-constructed VDevice collides with vision's -- HAILO_OUT_OF_PHYSICAL_DEVICES(74),
# found live 2026-08-23 -- so hailo_llm.py reuses picamera2's class-level Hailo.TARGET singleton
# instead, and constructs one only when nothing has yet.
#
# THE SUBTLE HALF is the refcount ORDERING. Hailo.TARGET_REF_COUNT is incremented only AFTER
# LLM() returns successfully. Incrementing first would leak the count on a load failure: nothing
# owns that increment, so vision's close() can never drive the count to 0 and the shared VDevice
# is never released. That is a resource leak with no symptom until the next process start, which
# is exactly the kind of bug a passing smoke test hides.

pytest.importorskip('picamera2', reason='hailo_llm needs picamera2; rover-only test')
pytest.importorskip('hailo_platform', reason='hailo_llm needs hailo_platform; rover-only test')


@pytest.fixture
def hl():
    import hailo_llm
    return hailo_llm


@pytest.fixture
def restore(hl):
    """Snapshot and restore the shared singleton -- these tests mutate class-level state that the
    rest of the suite (and the live process) depends on."""
    target, count = hl.Hailo.TARGET, hl.Hailo.TARGET_REF_COUNT
    yield
    hl.Hailo.TARGET, hl.Hailo.TARGET_REF_COUNT = target, count


def _build(hl, monkeypatch, llm_factory, model_exists=True):
    monkeypatch.setattr(hl.os.path, 'exists', lambda p: model_exists)
    monkeypatch.setattr(hl, 'LLM', llm_factory)
    return hl.HailoIntentModel()


def test_an_existing_target_is_reused_not_replaced(hl, monkeypatch, restore):
    """The core of the fix. If vision already opened the device, the LLM must attach to THAT one."""
    sentinel = object()
    hl.Hailo.TARGET = sentinel
    seen = {}

    def fake_llm(target, path):
        seen['target'] = target
        return object()

    m = _build(hl, monkeypatch, fake_llm)
    assert m.available is True
    assert seen['target'] is sentinel, 'constructed a new VDevice instead of reusing Hailo.TARGET'
    assert hl.Hailo.TARGET is sentinel, 'the shared singleton was replaced'


def test_a_successful_load_increments_the_refcount_exactly_once(hl, monkeypatch, restore):
    hl.Hailo.TARGET = object()
    before = hl.Hailo.TARGET_REF_COUNT
    _build(hl, monkeypatch, lambda t, p: object())
    assert hl.Hailo.TARGET_REF_COUNT == before + 1


def test_a_failed_load_does_not_leak_the_refcount(hl, monkeypatch, restore):
    """The ordering bug this guards. An increment before LLM() succeeds is owned by nobody, so
    vision's close() can never reach 0 and the device is never released."""
    hl.Hailo.TARGET = object()
    before = hl.Hailo.TARGET_REF_COUNT

    def boom(target, path):
        raise RuntimeError('HEF load failed')

    m = _build(hl, monkeypatch, boom)
    assert m.available is False
    assert hl.Hailo.TARGET_REF_COUNT == before, 'refcount leaked on a failed load'


def test_a_failed_load_reports_rather_than_raises(hl, monkeypatch, restore):
    """brain.py constructs this at startup. A raise here would take the whole rover down over an
    optional accelerator."""
    hl.Hailo.TARGET = object()

    def boom(target, path):
        raise RuntimeError('HEF load failed')

    m = _build(hl, monkeypatch, boom)          # must not raise
    assert m.available is False


def test_a_missing_model_file_stays_disabled_and_touches_nothing(hl, monkeypatch, restore):
    """The HEF is ~1.6GB and deliberately not tracked in git, so a fresh checkout hits this path.
    It must not construct a device, and must not count one."""
    hl.Hailo.TARGET = None
    before = hl.Hailo.TARGET_REF_COUNT

    def should_not_run(target, path):
        raise AssertionError('LLM() was constructed despite a missing model file')

    m = _build(hl, monkeypatch, should_not_run, model_exists=False)
    assert m.available is False
    assert hl.Hailo.TARGET is None, 'a VDevice was created for a model that does not exist'
    assert hl.Hailo.TARGET_REF_COUNT == before


def test_an_unavailable_model_declines_work_instead_of_failing_open(hl, monkeypatch, restore):
    """The safety-relevant end of it: a provider that could not load must return a REFUSAL, not a
    payload and not an exception, so brain.py falls through to the cloud path."""
    hl.Hailo.TARGET = object()
    m = _build(hl, monkeypatch, lambda t, p: (_ for _ in ()).throw(RuntimeError('nope')))
    r = m._call('anything', schema={'intent': str, 'args': dict, 'reply': str})
    assert r.parse_success is False
    assert r.payload is None
