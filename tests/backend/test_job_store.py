from datetime import UTC, datetime, timedelta

import pytest

from agent_backend.job_lifecycle import JobLifecycleError, JobState
from agent_backend.job_store import JobStoreConflict, SQLiteJobStore

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
OWNER = "google-owner-sub"
DIGEST = "a" * 64


def make_store(tmp_path):
    return SQLiteJobStore(tmp_path / "private-state" / "jobs.sqlite3", clock=lambda: NOW)


def test_job_is_durable_and_idempotent_across_store_instances(tmp_path):
    first = make_store(tmp_path)
    created = first.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="request-1",
    )
    repeated = first.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="request-1",
    )
    restarted = make_store(tmp_path)
    recovered = restarted.get_for_owner(created["job_id"], OWNER)

    assert created["job_id"] == repeated["job_id"] == recovered["job_id"]
    assert recovered["state"] == JobState.QUEUED.value
    assert recovered["recent_events"][0]["message"] == "Job accepted into the local queue"


def test_idempotency_key_cannot_be_reused_for_another_action(tmp_path):
    store = make_store(tmp_path)
    store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="request-1",
    )

    with pytest.raises(JobStoreConflict, match="another action"):
        store.create(
            owner_id=OWNER,
            tool_id="software.remove",
            action_digest="b" * 64,
            idempotency_key="request-1",
        )


def test_owner_scoped_listing_and_get_hide_other_owners(tmp_path):
    store = make_store(tmp_path)
    own = store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="owner-a",
    )
    store.create(
        owner_id="another-owner",
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="owner-b",
    )

    assert [job["job_id"] for job in store.list_for_owner(OWNER)] == [own["job_id"]]
    with pytest.raises(JobLifecycleError, match="not found"):
        store.get_for_owner(own["job_id"], "another-owner")


def test_progress_and_transition_are_atomic_versioned_and_bounded(tmp_path):
    store = make_store(tmp_path)
    job = store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="request-1",
    )
    progressed = store.update_progress(
        job["job_id"],
        owner_id=OWNER,
        expected_version=0,
        message="Checking approved installer evidence",
        now=NOW + timedelta(seconds=1),
    )
    started = store.transition(
        job["job_id"],
        owner_id=OWNER,
        expected_version=1,
        target=JobState.STARTING,
        message="Worker claimed job",
        now=NOW + timedelta(seconds=2),
    )

    assert progressed["progress_message"] == "Checking approved installer evidence"
    assert started["state"] == JobState.STARTING.value
    assert started["started_at"] == "2026-11-13T10:00:02.000Z"
    assert [event["message"] for event in started["recent_events"]] == [
        "Worker claimed job",
        "Checking approved installer evidence",
        "Job accepted into the local queue",
    ]

    with pytest.raises(JobStoreConflict, match="stale"):
        store.update_progress(
            job["job_id"],
            owner_id=OWNER,
            expected_version=1,
            message="stale update",
        )


def test_invalid_transition_and_oversized_or_unbounded_data_are_rejected(tmp_path):
    store = make_store(tmp_path)
    job = store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="request-1",
    )

    with pytest.raises(JobStoreConflict, match="not allowed"):
        store.transition(
            job["job_id"],
            owner_id=OWNER,
            expected_version=0,
            target=JobState.SUCCEEDED,
            message="must not skip execution and verification",
        )
    with pytest.raises(ValueError, match="exceeds"):
        store.update_progress(
            job["job_id"],
            owner_id=OWNER,
            expected_version=0,
            message="x" * 161,
        )
    with pytest.raises(ValueError, match="between 1 and 25"):
        store.list_for_owner(OWNER, limit=26)


def test_terminal_transition_records_finish_time_and_reboot_flag(tmp_path):
    store = make_store(tmp_path)
    job = store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="request-1",
    )
    store.transition(
        job["job_id"], owner_id=OWNER, expected_version=0,
        target=JobState.STARTING, message="Claimed", now=NOW + timedelta(seconds=1),
    )
    store.transition(
        job["job_id"], owner_id=OWNER, expected_version=1,
        target=JobState.RUNNING, message="Started", now=NOW + timedelta(seconds=2),
    )
    store.transition(
        job["job_id"], owner_id=OWNER, expected_version=2,
        target=JobState.VERIFYING, message="Verifying package identity",
        now=NOW + timedelta(seconds=3),
    )
    complete = store.transition(
        job["job_id"], owner_id=OWNER, expected_version=3,
        target=JobState.SUCCEEDED, message="Post-install verification passed",
        result_code="VERIFIED", reboot_required=False, now=NOW + timedelta(seconds=4),
    )

    assert complete["state"] == JobState.SUCCEEDED.value
    assert complete["finished_at"] == "2026-11-13T10:00:04.000Z"
    assert complete["result_code"] == "VERIFIED"
    assert complete["reboot_required"] is False


def test_durable_job_store_allows_cancelled_process_to_finish_verification(tmp_path):
    store = make_store(tmp_path)
    job = store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key="cancel-race",
    )
    started = store.transition(
        job["job_id"],
        owner_id=OWNER,
        expected_version=0,
        target=JobState.STARTING,
        message="Worker claimed job",
        now=NOW + timedelta(seconds=1),
    )
    running = store.transition(
        job["job_id"],
        owner_id=OWNER,
        expected_version=1,
        target=JobState.RUNNING,
        message="Process started",
        now=NOW + timedelta(seconds=2),
    )
    cancel_requested = store.transition(
        job["job_id"],
        owner_id=OWNER,
        expected_version=2,
        target=JobState.CANCEL_REQUESTED,
        message="Cancellation requested",
        now=NOW + timedelta(seconds=3),
    )
    verifying = store.transition(
        job["job_id"],
        owner_id=OWNER,
        expected_version=3,
        target=JobState.VERIFYING,
        message="Process completed; verify final state",
        result_code="PROCESS_COMPLETED",
        now=NOW + timedelta(seconds=4),
    )
    assert verifying["state"] == JobState.VERIFYING.value
