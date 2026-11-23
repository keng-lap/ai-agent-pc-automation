from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from agent_backend.approval_reservation_store import (
    ApprovalReservationConflict,
    SQLiteApprovalReservationStore,
)
from agent_backend.software_approval import (
    VerifiedPackageEvidence,
    build_install_approval_binding,
)

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
OWNER = "google-owner-sub"
SESSION = "windows-session-1"
PLAN_ID = "1" * 32
PLAN_DIGEST = "a" * 64


class TestSecureStorage:
    @contextmanager
    def protect_database(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)

        class Lease:
            @staticmethod
            def verify():
                if not path.is_file():
                    raise AssertionError("database is missing")

        yield Lease()


def make_binding():
    evidence = VerifiedPackageEvidence(
        evidence_id="e" * 32,
        package_id="DBeaver.DBeaver.Community",
        package_name="DBeaver Community",
        publisher="DBeaver Corp",
        version="26.2.5",
        source="winget",
        installer_type="exe",
        installer_silent_switch="/S",
        installer_url=(
            "https://github.com/dbeaver/dbeaver/releases/download/26.2.5/"
            "dbeaver-ce-26.2.5-windows-x86_64.exe"
        ),
        official_release_url="https://github.com/dbeaver/dbeaver/releases/tag/26.2.5",
        manifest_source_url=(
            "https://github.com/microsoft/winget-pkgs/tree/"
            + "a" * 40
            + "/manifests/d/DBeaver/DBeaver/Community/26.2.5"
        ),
        repository_commit="b" * 40,
        installer_sha256="c" * 64,
        manifest_sha256="d" * 64,
        architecture="x64",
        scope="user",
        signature_subject="CN=DBeaver Corp",
        signature_sha256="f" * 64,
        verified_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    return build_install_approval_binding(plan_digest=PLAN_DIGEST, evidence=evidence)


def make_store(tmp_path):
    return SQLiteApprovalReservationStore(
        tmp_path / "private-state" / "approval.sqlite3",
        clock=lambda: NOW,
        secure_storage=TestSecureStorage(),
    )


def make_reservation(store, binding):
    store.create_approval(
        approval_id="approval-1",
        owner_id=OWNER,
        session_id=SESSION,
        plan_id=PLAN_ID,
        plan_digest=PLAN_DIGEST,
        action_digest=binding.approval_digest,
        evidence_expires_at=binding.evidence.expires_at,
        now=NOW,
    )
    return store.reserve(
        approval_id="approval-1",
        owner_id=OWNER,
        session_id=SESSION,
        plan_id=PLAN_ID,
        plan_digest=PLAN_DIGEST,
        action_digest=binding.approval_digest,
        idempotency_key="install-request-1",
        binding_json=binding.model_dump_json(),
        now=NOW,
    )


def test_worker_claim_is_durable_and_payload_is_exact(tmp_path):
    binding = make_binding()
    store = make_store(tmp_path)
    receipt = make_reservation(store, binding)

    claimed = store.claim_next_install(
        worker_id="worker-1",
        now=NOW + timedelta(seconds=1),
        lease_seconds=60,
    )

    assert claimed is not None
    assert claimed.reservation_id == receipt.reservation_id
    assert claimed.state == "CLAIMED"
    assert claimed.attempts == 1
    assert claimed.binding_json == binding.model_dump_json()
    assert claimed.action_digest == binding.approval_digest

    recovered = make_store(tmp_path).get_install_job(
        reservation_id=receipt.reservation_id,
        owner_id=OWNER,
    )
    assert recovered == claimed


def test_worker_lease_allows_only_exact_monotonic_transitions(tmp_path):
    binding = make_binding()
    store = make_store(tmp_path)
    receipt = make_reservation(store, binding)
    claimed = store.claim_next_install(worker_id="worker-1", now=NOW, lease_seconds=60)
    assert claimed is not None and claimed.lease_token is not None

    running = store.transition_install(
        receipt.reservation_id,
        worker_id="worker-1",
        lease_token=claimed.lease_token,
        expected_version=claimed.version,
        target="RUNNING",
        now=NOW + timedelta(seconds=1),
    )
    verifying = store.transition_install(
        receipt.reservation_id,
        worker_id="worker-1",
        lease_token=claimed.lease_token,
        expected_version=running.version,
        target="VERIFYING",
        now=NOW + timedelta(seconds=2),
    )
    completed = store.transition_install(
        receipt.reservation_id,
        worker_id="worker-1",
        lease_token=claimed.lease_token,
        expected_version=verifying.version,
        target="SUCCEEDED",
        result_code="INSTALLED_VERIFIED",
        now=NOW + timedelta(seconds=3),
    )

    assert completed.state == "SUCCEEDED"
    assert completed.lease_token is None
    assert completed.result_code == "INSTALLED_VERIFIED"


def test_expired_worker_lease_becomes_unknown_and_is_never_requeued(tmp_path):
    binding = make_binding()
    store = make_store(tmp_path)
    receipt = make_reservation(store, binding)
    claimed = store.claim_next_install(worker_id="worker-1", now=NOW, lease_seconds=1)
    assert claimed is not None

    next_claim = store.claim_next_install(
        worker_id="worker-2",
        now=NOW + timedelta(seconds=2),
        lease_seconds=60,
    )

    assert next_claim is None
    recovered = store.get_install_job(reservation_id=receipt.reservation_id, owner_id=OWNER)
    assert recovered.state == "UNKNOWN"
    assert recovered.attempts == 1
    assert recovered.result_code == "WORKER_LEASE_EXPIRED"


def test_invalid_payload_cannot_be_queued(tmp_path):
    binding = make_binding()
    store = make_store(tmp_path)
    store.create_approval(
        approval_id="approval-1",
        owner_id=OWNER,
        session_id=SESSION,
        plan_id=PLAN_ID,
        plan_digest=PLAN_DIGEST,
        action_digest=binding.approval_digest,
        evidence_expires_at=binding.evidence.expires_at,
        now=NOW,
    )

    with pytest.raises(ValueError, match="valid install approval"):
        store.reserve(
            approval_id="approval-1",
            owner_id=OWNER,
            session_id=SESSION,
            plan_id=PLAN_ID,
            plan_digest=PLAN_DIGEST,
            action_digest=binding.approval_digest,
            idempotency_key="bad-payload",
            binding_json='{"action":"software.remove"}',
            now=NOW,
        )


def test_worker_cannot_transition_with_stale_lease(tmp_path):
    binding = make_binding()
    store = make_store(tmp_path)
    receipt = make_reservation(store, binding)
    claimed = store.claim_next_install(worker_id="worker-1", now=NOW, lease_seconds=60)
    assert claimed is not None and claimed.lease_token is not None

    with pytest.raises(ApprovalReservationConflict, match="lease"):
        store.transition_install(
            receipt.reservation_id,
            worker_id="worker-2",
            lease_token=claimed.lease_token,
            expected_version=claimed.version,
            target="RUNNING",
            now=NOW + timedelta(seconds=1),
        )


def test_worker_can_renew_live_lease_with_version_cas(tmp_path):
    binding = make_binding()
    store = make_store(tmp_path)
    receipt = make_reservation(store, binding)
    claimed = store.claim_next_install(worker_id="worker-1", now=NOW, lease_seconds=30)
    assert claimed is not None

    renewed = store.renew_install_lease(
        receipt.reservation_id,
        worker_id="worker-1",
        lease_token=claimed.lease_token,
        expected_version=claimed.version,
        lease_seconds=90,
        now=NOW + timedelta(seconds=10),
    )

    assert renewed.version == claimed.version + 1
    assert renewed.lease_expires_at == (NOW + timedelta(seconds=100)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    assert renewed.attempts == 1


def test_existing_install_reservation_can_be_recovered_by_owner_and_plan(tmp_path):
    binding = make_binding()
    store = make_store(tmp_path)
    receipt = make_reservation(store, binding)

    recovered = store.get_install_job_for_plan(plan_id=PLAN_ID, owner_id=OWNER)

    assert recovered.reservation_id == receipt.reservation_id
    assert recovered.state == "QUEUED"
    assert recovered.binding_json == binding.model_dump_json()
    with pytest.raises(Exception):
        store.get_install_job_for_plan(plan_id=PLAN_ID, owner_id="another-owner")


def test_expired_reboot_required_lease_becomes_unknown_without_retry(tmp_path):
    binding = make_binding()
    store = make_store(tmp_path)
    receipt = make_reservation(store, binding)
    claimed = store.claim_next_install(worker_id="worker-1", now=NOW, lease_seconds=1)
    running = store.transition_install(
        receipt.reservation_id,
        worker_id="worker-1",
        lease_token=claimed.lease_token,
        expected_version=claimed.version,
        target="RUNNING",
        now=NOW,
    )
    reboot = store.transition_install(
        receipt.reservation_id,
        worker_id="worker-1",
        lease_token=claimed.lease_token,
        expected_version=running.version,
        target="REBOOT_REQUIRED",
        result_code="REBOOT_REQUIRED",
        now=NOW,
    )
    assert reboot.state == "REBOOT_REQUIRED"

    assert store.claim_next_install(
        worker_id="worker-2",
        now=NOW + timedelta(seconds=2),
        lease_seconds=60,
    ) is None
    recovered = store.get_install_job_for_plan(plan_id=PLAN_ID, owner_id=OWNER)
    assert recovered.state == "UNKNOWN"
    assert recovered.attempts == 1
    assert recovered.result_code == "WORKER_LEASE_EXPIRED"