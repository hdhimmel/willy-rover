import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

import config
from identity import IdentityStore, RECOGNISED, UNCERTAIN, UNKNOWN

# FR-2100-001..006. identity.py is the store and the matcher only -- no camera, no models, no
# frames, pure vectors in and names out. That is deliberate (design §4): it makes this the one
# part of person recognition that is fully unit-testable off the rover, which matters because
# the rover has been powered down for days and the laptop cannot import brain.py at all.
#
# Everything here is about the BANDS and about PENDING. Those two carry the safety properties:
#
#   - Three bands, not two. The design's §5 records why: with only "match / no match", every
#     uncertain result becomes a loud "Stranger Danger!" at an enrolled person in bad lighting.
#     The middle band exists to be silent.
#   - A pending identity is INERT. Enrolment is gated on an email confirmation the rover cannot
#     verify locally, so until approval lands, the row must take no part in matching at all.
#     That is what keeps a soft-gate bypass embarrassing rather than dangerous (FR-2100-006).


def _vec(seed, dim=128):
    """A deterministic unit vector. Distinct seeds give near-orthogonal vectors."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=dim)
    return v / np.linalg.norm(v)


def _nudge(v, amount, seed=99):
    """Move a vector slightly off its original direction, staying normalised."""
    rng = np.random.default_rng(seed)
    out = v + rng.normal(size=v.shape) * amount
    return out / np.linalg.norm(out)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'WILLY_MEMORY_ROOT', str(tmp_path))
    return IdentityStore(db_path='identities.db')


# --- enrolment and the pending gate ------------------------------------------------

def test_a_pending_identity_never_matches(store):
    """The safety property behind FR-2100-006. Enrolment is authorised by an email the rover
    cannot check locally, so an unapproved row must be completely inert -- not merely unnamed."""
    carolyn = _vec(1)
    store.enrol('carolyn', [carolyn])           # pending by default
    r = store.match(carolyn)
    assert r.name is None, 'a pending identity must not match'
    assert r.band != RECOGNISED
    # Note it lands in UNCERTAIN, not UNKNOWN: with no ACTIVE vectors there is nothing to be
    # confident about, and the empty-store rule below says silence beats accusation.


def test_approval_activates_the_identity(store):
    carolyn = _vec(1)
    store.enrol('carolyn', [carolyn])
    assert store.approve('carolyn') is True
    r = store.match(carolyn)
    assert r.name == 'carolyn' and r.band == RECOGNISED


def test_enrolment_defaults_to_pending_not_active(store):
    """Stated explicitly: a future refactor that flips the default would silently remove the
    email gate without touching anything named 'approval'."""
    store.enrol('carolyn', [_vec(1)])
    assert store.is_pending('carolyn') is True


def test_approving_an_unknown_name_fails_rather_than_creating(store):
    """A spoken name may RESOLVE an identity; it may never CREATE one (design §5)."""
    assert store.approve('nobody') is False
    assert 'nobody' not in store.names()


# --- the three bands ---------------------------------------------------------------

def test_a_close_vector_is_recognised(store):
    carolyn = _vec(1)
    store.enrol('carolyn', [carolyn]); store.approve('carolyn')
    r = store.match(_nudge(carolyn, 0.05))
    assert r.band == RECOGNISED and r.name == 'carolyn'


def test_a_far_vector_is_confidently_unknown(store):
    store.enrol('carolyn', [_vec(1)]); store.approve('carolyn')
    r = store.match(_vec(2))                     # near-orthogonal: a different person
    assert r.band == UNKNOWN and r.name is None


def test_a_middling_vector_is_uncertain_and_unnamed(store):
    """The band that protects an enrolled person in poor light. It must NOT name them -- naming
    the wrong person is the failure that stings -- and must NOT trigger the stranger response."""
    carolyn = _vec(1)
    store.enrol('carolyn', [carolyn]); store.approve('carolyn')
    mid = (config.FACE_MATCH_MAX_DISTANCE + config.FACE_STRANGER_MIN_DISTANCE) / 2
    r = store.match(store.vector_at_distance(carolyn, mid))
    assert r.band == UNCERTAIN
    assert r.name is None, 'uncertain must not name a person'


def test_an_empty_store_never_reports_a_stranger(store):
    """With nobody enrolled everyone is confidently unknown, and shouting at the whole household
    because enrolment has not happened yet is a bad first impression of the feature (design §5)."""
    r = store.match(_vec(1))
    assert r.band == UNCERTAIN, 'an empty store must be silent, not accusatory'


# --- multiple vectors, and strengthening -------------------------------------------

def test_matching_uses_the_nearest_of_several_vectors(store):
    """Multiple poses per identity is the whole reason enrolment captures several frames."""
    a, b = _vec(1), _vec(2)
    store.enrol('carolyn', [a, b]); store.approve('carolyn')
    assert store.match(_nudge(b, 0.05)).name == 'carolyn'


def test_vectors_per_identity_are_capped_oldest_evicted(store):
    """Without a cap an identity accumulates hundreds over time and matching slows for no gain."""
    store.enrol('carolyn', [_vec(1)]); store.approve('carolyn')
    for i in range(config.FACE_MAX_VECTORS_PER_IDENTITY + 5):
        store.add_vector('carolyn', _vec(100 + i))
    assert store.vector_count('carolyn') == config.FACE_MAX_VECTORS_PER_IDENTITY


def test_a_pending_identity_cannot_be_strengthened(store):
    """Otherwise an unapproved row quietly accumulates evidence while claiming to be inert."""
    store.enrol('carolyn', [_vec(1)])
    assert store.add_vector('carolyn', _vec(2)) is False


# --- presence ----------------------------------------------------------------------

def test_last_seen_records_name_time_and_room(store):
    store.enrol('carolyn', [_vec(1)]); store.approve('carolyn')
    store.note_seen('carolyn', room='kitchen')
    seen = store.last_seen('carolyn')
    assert seen.room == 'kitchen' and seen.at > 0


def test_last_seen_is_none_for_someone_never_seen(store):
    store.enrol('carolyn', [_vec(1)]); store.approve('carolyn')
    assert store.last_seen('carolyn') is None


# --- persistence and wipe ----------------------------------------------------------

def test_identities_survive_a_reopen(store, tmp_path, monkeypatch):
    carolyn = _vec(1)
    store.enrol('carolyn', [carolyn]); store.approve('carolyn')
    store.close()
    monkeypatch.setattr(config, 'WILLY_MEMORY_ROOT', str(tmp_path))
    again = IdentityStore(db_path='identities.db')
    assert again.match(carolyn).name == 'carolyn'


def test_forget_all_deletes_the_file_not_just_the_rows(store):
    """Design §4: a wipe must be a file delete, which is what makes the privacy position
    defensible -- biometric data on a visibly separate boundary from ordinary learned facts."""
    store.enrol('carolyn', [_vec(1)]); store.approve('carolyn')
    path = store.path
    store.forget_all()
    assert not os.path.exists(path), 'the wipe must remove the file, not just the rows'
    assert store.names() == []          # store stays usable; the db is recreated lazily
    assert os.path.exists(path)         # ...and only once something actually asks for it


def test_the_store_is_its_own_file_not_memory_db(store):
    assert os.path.basename(store.path) == 'identities.db'
    assert 'memory.db' not in store.path
