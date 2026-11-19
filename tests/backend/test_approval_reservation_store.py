import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from agent_backend.approval_reservation_store import (
    ApprovalReservationConflict,
    ApprovalReservationExpired,
    ApprovalReservationNotFound,
    SQLiteApprovalReservationStore,
)

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
OWNER = "google-owner-sub"
SESSION = "session-1"
PLAN_ID = "1" * 32
PLAN_DIGEST = "a" * 64
ACTION_DIGEST = "b" * 64


class _TestSecureStorage:
    def prepare_database_path(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)

    def finalize_database_file(self, path):
        if not path.is_file():
            raise AssertionError("approval database was not created")


def make_store(tmp_path, *, clock=lambda: NOW):
    return SQLiteApprovalReservationStore(
        tmp_path / "private-state" / "approval.sqlite3",
        clock=clock,
        secure_storage=_TestSecureStorage(),
    )


def create_approval(store, *, approval_id="approval-1", expires=None):
    store.create_approval(
        approval_id=approval_id,
        owner_id=OWNER,
        session_id=SESSION,
        plan_id=PLAN_ID,
        plan_digest=PLAN_DIGEST,
        action_digest=ACTION_DIGEST,
        evidence_expires_at=expires or NOW + timedelta(minutes=10),
    )


def reserve(store, *, approval_id="approval-1", key="request-1", now=NOW):
    return store.reserve(
        approval_id=approval_id,
        owner_id=OWNER,
        session_id=SESSION,
        plan_id=PLAN_ID,
        plan_digest=PLAN_DIGEST,
        action_digest=ACTION_DIGEST,
        idempotency_key=key,
        now=now,
    )


def test_reservation_is_durable_and_exactly_idempotent(tmp_path):
    store = make_store(tmp_path)
    create_approval(store)

    first = reserve(store)
    repeated = reserve(store)
    recovered = make_store(tmp_path).get_reservation(
        reservation_id=first.reservation_id,
        owner_id=OWNER,
    )

    assert first == repeated == recovered
    assert first.state == "RESERVED"


def test_idempotency_key_cannot_be_reused_for_another_approval(tmp_path):
    store = make_store(tmp_path)
    create_approval(store)
    create_approval(store, approval_id="approval-2")
    reserve(store)

    with pytest.raises(ApprovalReservationConflict, match="different reservation"):
        reserve(store, approval_id="approval-2")


def test_binding_mismatch_and_cross_owner_access_are_rejected(tmp_path):
    store = make_store(tmp_path)
    create_approval(store)

    with pytest.raises(ApprovalReservationConflict, match="binding"):
        store.reserve(
            approval_id="approval-1",
            owner_id="another-owner",
            session_id=SESSION,
            plan_id=PLAN_ID,
            plan_digest=PLAN_DIGEST,
            action_digest=ACTION_DIGEST,
            idempotency_key="foreign-request",
            now=NOW,
        )

    receipt = reserve(store)
    with pytest.raises(ApprovalReservationNotFound):
        store.get_reservation(
            reservation_id=receipt.reservation_id,
            owner_id="another-owner",
        )


def test_expiry_is_persisted_and_does_not_create_reservation(tmp_path):
    store = make_store(tmp_path)
    create_approval(store, expires=NOW + timedelta(seconds=1))

    with pytest.raises(ApprovalReservationExpired):
        reserve(store, now=NOW + timedelta(seconds=1))

    with sqlite3.connect(store.path) as connection:
        state = connection.execute(
            "SELECT state FROM approval_records WHERE approval_id='approval-1'"
        ).fetchone()[0]
        reservations = connection.execute(
            "SELECT COUNT(*) FROM job_reservations"
        ).fetchone()[0]
        events = connection.execute(
            "SELECT event_type FROM approval_audit_events ORDER BY sequence"
        ).fetchall()

    assert state == "EXPIRED"
    assert reservations == 0
    assert [event[0] for event in events] == [
        "approval.created",
        "approval.expired",
    ]


def test_revocation_and_reservation_have_one_serialized_winner(tmp_path):
    store_a = make_store(tmp_path)
    store_b = make_store(tmp_path)
    create_approval(store_a)

    def try_reserve():
        try:
            return reserve(store_a)
        except ApprovalReservationConflict:
            return "conflict"

    def try_revoke():
        try:
            store_b.revoke(approval_id="approval-1", owner_id=OWNER, now=NOW)
            return "revoked"
        except ApprovalReservationConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda fn: fn(), (try_reserve, try_revoke)))

    assert sum(result != "conflict" for result in results) == 1
    with sqlite3.connect(store_a.path) as connection:
        state = connection.execute(
            "SELECT state FROM approval_records WHERE approval_id='approval-1'"
        ).fetchone()[0]
        reservation_count = connection.execute(
            "SELECT COUNT(*) FROM job_reservations"
        ).fetchone()[0]

    assert (state, reservation_count) in {("RESERVED", 1), ("REVOKED", 0)}


def test_audit_failure_rolls_back_approval_and_reservation(tmp_path):
    store = make_store(tmp_path)
    create_approval(store)

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_reservation_audit
            BEFORE INSERT ON approval_audit_events
            WHEN NEW.event_type = 'approval.reserved'
            BEGIN
                SELECT RAISE(ABORT, 'audit unavailable');
            END
            """
        )

    with pytest.raises(Exception):
        reserve(store)

    with sqlite3.connect(store.path) as connection:
        state = connection.execute(
            "SELECT state FROM approval_records WHERE approval_id='approval-1'"
        ).fetchone()[0]
        reservation_count = connection.execute(
            "SELECT COUNT(*) FROM job_reservations"
        ).fetchone()[0]

    assert state == "ACTIVE"
    assert reservation_count == 0
