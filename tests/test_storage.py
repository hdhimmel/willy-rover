import os,sys,tempfile
from unittest.mock import patch
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from storage import resolve_root,check_storage,_REPO_DIR

# Pure-logic tests for storage.py -- no hardware needed (§20/§13 of
# docs/WildWilly_Claude_Fix_Implementation_Plan.md).

def test_resolve_root_uses_env_var_when_set(monkeypatch):
    monkeypatch.setenv('WILLY_TEST_ROOT','/mnt/external_ssd/willy')
    assert resolve_root('WILLY_TEST_ROOT','.')=='/mnt/external_ssd/willy'

def test_resolve_root_falls_back_to_repo_relative_default(monkeypatch):
    monkeypatch.delenv('WILLY_TEST_ROOT',raising=False)
    assert resolve_root('WILLY_TEST_ROOT','logs')==os.path.join(_REPO_DIR,'logs')

def test_resolve_root_default_is_repo_relative_not_cwd_relative(monkeypatch):
    # The whole point of anchoring to _REPO_DIR: a manual `python3 diagnostics.py` run from an
    # unrelated directory must still resolve to the same place a systemd run would.
    monkeypatch.delenv('WILLY_TEST_ROOT',raising=False)
    with tempfile.TemporaryDirectory() as unrelated_cwd:
        old_cwd=os.getcwd()
        try:
            os.chdir(unrelated_cwd)
            assert resolve_root('WILLY_TEST_ROOT','.')==os.path.normpath(_REPO_DIR)
        finally:
            os.chdir(old_cwd)

def test_check_storage_ok_for_writable_dir():
    with tempfile.TemporaryDirectory() as d:
        ok,problems=check_storage({'data':d})
        assert ok is True and problems==[]

def test_check_storage_creates_missing_dir():
    with tempfile.TemporaryDirectory() as d:
        target=os.path.join(d,'not_yet_created')
        ok,problems=check_storage({'data':target})
        assert ok is True and os.path.isdir(target)

def test_check_storage_reports_unwritable_dir():
    # chmod-based denial doesn't work when the test runs as root (root bypasses file permission
    # checks entirely, silently turning this into a false-pass) -- found 2026-08-08 via an external
    # audit. A mocked open() failure is deterministic regardless of which user runs the suite.
    with tempfile.TemporaryDirectory() as d:
        with patch('builtins.open',side_effect=PermissionError('mocked: no write access')):
            ok,problems=check_storage({'data':d})
        assert ok is False and any('data' in p for p in problems)

def test_check_storage_multiple_roots_all_ok():
    with tempfile.TemporaryDirectory() as d:
        roots={'data':os.path.join(d,'a'),'map':os.path.join(d,'b'),'memory':os.path.join(d,'c')}
        ok,problems=check_storage(roots)
        assert ok is True and problems==[] and all(os.path.isdir(p) for p in roots.values())

def test_check_storage_reports_path_that_cannot_be_created():
    # Same root-fragility issue as the unwritable-dir test above -- mocked os.makedirs() failure
    # instead of a chmod-locked parent directory.
    with tempfile.TemporaryDirectory() as d:
        target=os.path.join(d,'locked_parent','child')
        with patch('os.makedirs',side_effect=OSError('mocked: cannot create')):
            ok,problems=check_storage({'data':target})
        assert ok is False and len(problems)==1
