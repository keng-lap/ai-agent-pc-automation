import os
from datetime import UTC, datetime, timedelta

import pytest

from agent_backend.job_lifecycle import (
    InMemoryJobStore,
    JobLifecycleError,
    JobState,
)
from agent_backend.process_containment import ProcessContainmentError, WindowsJobObject


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64


def _create(store=None, **overrides):
    store = store or InMemoryJobStore()
    values = {
        "owner_id": "owner-1",
        "tool_id": "software.install",
        "action_digest": DIGEST,
        "idempotency_key": "request-1",
        "now": NOW,
    }
    values.update(overrides)
    return store, store.create(**values)


def _claim(store, job):
    claimed, lease = store.claim_next(worker_id="worker-1", now=NOW)
    assert claimed.job_id == job.job_id
    return claimed, lease


def test_create_job_starts_queued_and_is_idempotent():
    store, job = _create()
    repeated = store.create(
        owner_id="owner-1",
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="request-1",
        now=NOW,
    )

    assert job.state is JobState.QUEUED
    assert repeated.job_id == job.job_id
    assert repeated.version == job.version


def test_idempotency_key_cannot_be_reused_for_different_action():
    store, _job = _create()
    with pytest.raises(JobLifecycleError, match="different action"):
        store.create(
            owner_id="owner-1",
            tool_id="software.install",
            action_digest="b" * 64,
            idempotency_key="request-1",
            now=NOW,
        )


def test_claim_is_atomic_and_creates_worker_lease():
    store, job = _create()
    claimed, lease = _claim(store, job)

    assert claimed.state is JobState.STARTING
    assert claimed.version == 1
    assert lease.worker_id == "worker-1"
    assert store.claim_next(worker_id="worker-2", now=NOW) is None


def test_worker_can_advance_only_with_current_lease_and_version():
    store, job = _create()
    claimed, lease = _claim(store, job)
    running = store.transition(
        job.job_id,
        worker_id=lease.worker_id,
        lease_token=lease.token,
        expected_version=claimed.version,
        target=JobState.RUNNING,
        now=NOW + timedelta(seconds=1),
    )

    assert running.state is JobState.RUNNING
    assert running.version == 2
    with pytest.raises(JobLifecycleError, match="invalid"):
        store.transition(
            job.job_id,
            worker_id=lease.worker_id,
            lease_token=lease.token,
            expected_version=claimed.version,
            target=JobState.VERIFYING,
            now=NOW + timedelta(seconds=2),
        )



def test_worker_can_renew_a_live_lease_with_compare_and_swap_version():
    store, job = _create()
    claimed, lease = _claim(store, job)
    renewed = store.renew_lease(
        job.job_id,
        worker_id=lease.worker_id,
        lease_token=lease.token,
        expected_version=claimed.version,
        now=NOW + timedelta(seconds=10),
        lease_seconds=60,
    )

    assert renewed.version == claimed.version + 1
    assert renewed.lease.expires_at == NOW + timedelta(seconds=70)
    with pytest.raises(JobLifecycleError, match="invalid"):
        store.renew_lease(
            job.job_id,
            worker_id=lease.worker_id,
            lease_token=lease.token,
            expected_version=claimed.version,
            now=NOW + timedelta(seconds=11),
        )

def test_invalid_state_transition_is_rejected():
    store, job = _create()
    claimed, lease = _claim(store, job)
    with pytest.raises(JobLifecycleError, match="not allowed"):
        store.transition(
            job.job_id,
            worker_id=lease.worker_id,
            lease_token=lease.token,
            expected_version=claimed.version,
            target=JobState.SUCCEEDED,
            now=NOW + timedelta(seconds=1),
        )


def test_cancel_queued_job_without_worker_dispatch():
    store, job = _create()
    cancelled = store.request_cancel(job.job_id, owner_id="owner-1", now=NOW)

    assert cancelled.state is JobState.CANCELLED
    assert store.claim_next(worker_id="worker-1", now=NOW) is None


def test_running_cancel_requires_worker_confirmation_before_cancelled():
    store, job = _create()
    claimed, lease = _claim(store, job)
    running = store.transition(
        job.job_id,
        worker_id=lease.worker_id,
        lease_token=lease.token,
        expected_version=claimed.version,
        target=JobState.RUNNING,
        now=NOW + timedelta(seconds=1),
    )
    requested = store.request_cancel(job.job_id, owner_id="owner-1", now=NOW + timedelta(seconds=2))

    assert requested.state is JobState.CANCEL_REQUESTED
    assert requested.lease == lease
    cancelled = store.transition(
        job.job_id,
        worker_id=lease.worker_id,
        lease_token=lease.token,
        expected_version=requested.version,
        target=JobState.CANCELLED,
        now=NOW + timedelta(seconds=3),
        result_code="PROCESS_TREE_TERMINATED",
    )
    assert cancelled.state is JobState.CANCELLED
    assert cancelled.lease is None


def test_expired_worker_lease_becomes_unknown_and_is_never_requeued():
    store, job = _create()
    claimed, _lease = _claim(store, job)
    expired = store.expire_leases(now=NOW + timedelta(seconds=31))

    assert expired == (job.job_id,)
    assert store.get_for_owner(job.job_id, "owner-1").state is JobState.UNKNOWN
    assert store.claim_next(worker_id="worker-2", now=NOW + timedelta(seconds=32)) is None


def test_owner_is_bound_to_job_status():
    store, job = _create()
    with pytest.raises(JobLifecycleError, match="not found"):
        store.get_for_owner(job.job_id, "another-owner")


def test_invalid_digest_and_lease_are_rejected():
    store = InMemoryJobStore()
    with pytest.raises(ValueError, match="SHA-256"):
        store.create(
            owner_id="owner-1",
            tool_id="software.install",
            action_digest="not-a-digest",
            idempotency_key="request-1",
            now=NOW,
        )
    with pytest.raises(ValueError, match="lease_seconds"):
        store.claim_next(worker_id="worker-1", now=NOW, lease_seconds=0)


def test_windows_job_object_is_explicitly_unavailable_off_windows():
    import os

    if os.name == "nt":
        pytest.skip("this assertion applies only to non-Windows hosts")
    with pytest.raises(ProcessContainmentError, match="only on Windows"):
        WindowsJobObject()

@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object APIs are required")
def test_windows_job_object_creates_and_closes_with_kill_on_close_policy():
    with WindowsJobObject() as job:
        assert job.is_open
        with pytest.raises(ValueError, match="native process handle"):
            job.assign_suspended_process(0)
    assert not job.is_open
