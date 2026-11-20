import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from agent_backend.job_lifecycle import JobLifecycleError, JobState
from agent_backend.job_store import (
    JobStoreCommittedButUnverified,
    JobStoreConflict,
    JobStoreUnavailable,
    SQLiteJobStore,
)
from agent_backend.platform_storage import PlatformStorageUnavailable

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
OWNER = "google-owner-sub"
DIGEST = "a" * 64


class _TestProtectionLease:
    def __init__(self, path):
        self.path = path

    def verify(self):
        if not self.path.is_file():
            raise AssertionError("test database was not created")


class _TestSecureStorage:
    """Test-only adapter; filesystem security is covered by platform adapter tests."""

    from contextlib import contextmanager

    @contextmanager
    def protect_database(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        lease = _TestProtectionLease(path)
        try:
            yield lease
        finally:
            lease.verify()


def make_store(tmp_path):
    return SQLiteJobStore(
        tmp_path / "private-state" / "jobs.sqlite3",
        clock=lambda: NOW,
        secure_storage=_TestSecureStorage(),
    )


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
    store.transition(
        job["job_id"],
        owner_id=OWNER,
        expected_version=0,
        target=JobState.STARTING,
        message="Worker claimed job",
        now=NOW + timedelta(seconds=1),
    )
    store.transition(
        job["job_id"],
        owner_id=OWNER,
        expected_version=1,
        target=JobState.RUNNING,
        message="Process started",
        now=NOW + timedelta(seconds=2),
    )
    store.transition(
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



def test_connection_closes_before_protection_lease_is_released(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    events = []
    original_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        def close(self):
            events.append("connection-close")
            super().close()

    class RecordingStorage:
        @contextmanager
        def protect_database(self, path):
            events.append("lease-enter")

            class Lease:
                def verify(self):
                    events.append("lease-verify")

            try:
                yield Lease()
            finally:
                events.append("lease-exit")

    monkeypatch.setattr(store, "_secure_storage", RecordingStorage())
    def tracked_connect(*args, **kwargs):
        events.append("connection-open")
        return original_connect(*args, factory=TrackingConnection, **kwargs)

    monkeypatch.setattr(
        "agent_backend.job_store.sqlite3.connect",
        tracked_connect,
    )

    with store._connection():
        events.append("connection-in-use")

    assert events == [
        "lease-enter",
        "connection-open",
        "lease-verify",
        "connection-in-use",
        "lease-verify",
        "connection-close",
        "lease-exit",
    ]



def test_initialization_fails_closed_when_sqlite_cannot_enable_wal(tmp_path, monkeypatch):
    original_connect = sqlite3.connect

    class FakeCursor:
        @staticmethod
        def fetchone():
            return ("delete",)

    class ConnectionProxy:
        def __init__(self, *args, **kwargs):
            self._connection = original_connect(*args, **kwargs)

        @property
        def row_factory(self):
            return self._connection.row_factory

        @row_factory.setter
        def row_factory(self, value):
            self._connection.row_factory = value

        def execute(self, sql, *args):
            if sql.strip().upper() == "PRAGMA JOURNAL_MODE = WAL":
                return FakeCursor()
            return self._connection.execute(sql, *args)

        def executescript(self, sql):
            return self._connection.executescript(sql)

        def close(self):
            self._connection.close()

    monkeypatch.setattr(
        "agent_backend.job_store.sqlite3.connect",
        lambda *args, **kwargs: ConnectionProxy(*args, **kwargs),
    )
    with pytest.raises(JobStoreUnavailable, match="WAL mode"):
        SQLiteJobStore(
            tmp_path / "private-state" / "jobs.sqlite3",
            secure_storage=_TestSecureStorage(),
        )


@pytest.mark.parametrize("operation", ["progress", "transition"])
def test_committed_write_reports_unverified_outcome(tmp_path, operation):
    store = make_store(tmp_path)
    job = store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest=DIGEST,
        idempotency_key=f"committed-unverified-{operation}",
    )

    class FailOnOuterLeaseExit:
        def __init__(self):
            self.verifications = 0

        @contextmanager
        def protect_database(self, path):
            path.parent.mkdir(parents=True, exist_ok=True)

            class Lease:
                def verify(inner_self):
                    self.verifications += 1
                    if self.verifications == 4:
                        raise PlatformStorageUnavailable("forced post-commit verification failure")

            yield Lease()

    store._secure_storage = FailOnOuterLeaseExit()
    with pytest.raises(JobStoreCommittedButUnverified) as raised:
        if operation == "progress":
            store.update_progress(
                job["job_id"],
                owner_id=OWNER,
                expected_version=0,
                message="Committed progress",
            )
        else:
            store.transition(
                job["job_id"],
                owner_id=OWNER,
                expected_version=0,
                target=JobState.STARTING,
                message="Committed transition",
            )

    assert raised.value.job_id == job["job_id"]
    assert raised.value.committed_version == 1

    # Reconcile only after the trusted storage adapter is restored.
    store._secure_storage = _TestSecureStorage()
    recovered = store.get_for_owner(job["job_id"], OWNER)
    if operation == "progress":
        assert recovered["progress_message"] == "Committed progress"
    else:
        assert recovered["state"] == JobState.STARTING.value
