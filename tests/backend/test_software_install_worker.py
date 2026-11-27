"""Tests for the one-shot local WinGet install worker."""

import json
import logging
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_backend import runtime_diagnostics as diagnostics
from agent_backend import software_install_worker as worker_module
from agent_backend.approval_reservation_store import InstallExecutionJob
from agent_backend.software_approval import VerifiedPackageEvidence, build_install_approval_binding


def make_binding():
    now = datetime.now(UTC)
    evidence = VerifiedPackageEvidence(
        evidence_id="e" * 32,
        package_id="DBeaver.DBeaver.Community",
        package_name="DBeaver Community Edition",
        publisher="DBeaver Corp",
        version="26.2.4",
        source="winget",
        installer_type="exe",
        installer_silent_switch="/S",
        installer_url="https://example.com/dbeaver.exe",
        official_release_url="https://example.com/releases/26.2.4",
        manifest_source_url="https://github.com/microsoft/winget-pkgs/tree/" + "c" * 40,
        repository_commit="c" * 40,
        installer_sha256="b" * 64,
        manifest_sha256="c" * 64,
        architecture="x64",
        scope="user",
        verified_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=10),
    )
    return build_install_approval_binding(plan_digest="a" * 64, evidence=evidence)


class FakeStore:
    def __init__(self, binding):
        self.job = InstallExecutionJob(
            reservation_id="reservation-1",
            owner_id="owner-1",
            action_digest=binding.approval_digest,
            binding_json=binding.model_dump_json(),
            state="CLAIMED",
            worker_id="worker-1",
            lease_token="lease-token",
            lease_expires_at="2099-01-01T00:00:00.000Z",
            attempts=1,
            version=1,
            result_code=None,
            plan_id="1" * 32,
        )
        self.transitions = []
        self.release_consumptions = []
        self.release_error = None

    def claim_next_install(self, **_kwargs):
        return self.job

    def transition_install(self, reservation_id, **kwargs):
        self.transitions.append((reservation_id, kwargs["target"], kwargs["result_code"]))
        self.job = replace(
            self.job,
            state=kwargs["target"],
            version=self.job.version + 1,
            result_code=kwargs["result_code"],
        )
        return self.job

    def consume_real_install_release_authorization(self, **kwargs):
        if self.release_error is not None:
            raise self.release_error
        self.release_consumptions.append(kwargs)

    def renew_install_lease(self, *_args, **_kwargs):
        self.job = replace(self.job, version=self.job.version + 1)
        return self.job


def test_worker_does_not_claim_jobs_after_shutdown_requested(tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    stop = threading.Event()
    stop.set()
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        stop_event=stop,
    )

    assert worker.run_once() is None
    assert store.job.state == "CLAIMED"
    assert store.transitions == []


def test_worker_executes_only_approved_binding_and_verifies_exact_package(monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    prepared = SimpleNamespace()
    executor_calls = []
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: prepared)
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)

    def executor(actual_binding, actual_prepared, **kwargs):
        executor_calls.append((actual_binding, actual_prepared, kwargs))
        return SimpleNamespace(timed_out=False, exit_code=0)

    verification_results = iter([False, True])
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=executor,
        verifier=lambda *_args: next(verification_results),
        heartbeat_seconds=5,
    )
    result = worker.run_once()

    assert result.state == "SUCCEEDED"
    assert [item[1] for item in store.transitions] == ["RUNNING", "VERIFYING", "SUCCEEDED"]
    assert executor_calls[0][0].approval_digest == binding.approval_digest
    assert executor_calls[0][1] is prepared
    assert store.release_consumptions == [{
        "task_id": "P6-609-C",
        "owner_id": store.job.owner_id,
        "plan_id": store.job.plan_id,
        "package_id": binding.evidence.package_id,
        "version": binding.evidence.version,
        "action_digest": binding.approval_digest,
    }]


def test_worker_emits_correlated_runtime_diagnostics_for_complete_install(caplog, monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    store.job = replace(
        store.job,
        plan_id="1" * 32,
        workflow_id="11111111-2222-4333-8444-555555555555",
        correlation_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    )
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: object())
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)
    verification_results = iter([False, True])
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=lambda *_a, **_k: SimpleNamespace(timed_out=False, exit_code=0),
        verifier=lambda *_a: next(verification_results),
        heartbeat_seconds=5,
    )

    diagnostics.set_enabled(True)
    try:
        with caplog.at_level(logging.INFO, logger="agent_backend.runtime_diagnostics"):
            result = worker.run_once()
    finally:
        diagnostics.set_enabled(False)

    events = [json.loads(record.message) for record in caplog.records]
    event_codes = {event["event_code"] for event in events}
    assert result.state == "SUCCEEDED"
    assert {
        "INSTALL_WORKER_CLAIMED",
        "INSTALL_JOB_STATE_CHANGED",
        "INSTALL_PRECHECK_STARTED",
        "INSTALLER_PREPARATION_COMPLETED",
        "REAL_INSTALL_RELEASE_AUTHORIZATION_CONSUMED",
        "WINGET_EXECUTION_STARTED",
        "WINGET_EXECUTION_COMPLETED",
        "POST_INSTALL_VERIFICATION_COMPLETED",
    }.issubset(event_codes)
    for event in events:
        assert event["workflow_id"] == "11111111-2222-4333-8444-555555555555"
        assert event["correlation_id"] == "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        assert event["fields"]["plan_id"] == "1" * 32
        assert event["fields"]["reservation_id"] == "reservation-1"
        assert "installer_url" not in event["fields"]
        assert "api_key" not in event["fields"]


def test_worker_does_not_emit_detailed_events_when_diagnostics_are_off(caplog, monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: object())
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)
    verification_results = iter([False, True])
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=lambda *_a, **_k: SimpleNamespace(timed_out=False, exit_code=0),
        verifier=lambda *_a: next(verification_results),
        heartbeat_seconds=5,
    )

    diagnostics.set_enabled(False)
    with caplog.at_level(logging.DEBUG, logger="agent_backend.runtime_diagnostics"):
        result = worker.run_once()

    assert result.state == "SUCCEEDED"
    assert not [record for record in caplog.records if record.name == "agent_backend.runtime_diagnostics"]


def test_worker_records_unknown_after_execution_timeout(monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: object())
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=lambda *_a, **_k: SimpleNamespace(timed_out=True, exit_code=None),
        verifier=lambda *_a: False,
        heartbeat_seconds=5,
    )

    result = worker.run_once()

    assert result.state == "UNKNOWN"
    assert store.transitions[-1][1:] == ("UNKNOWN", "WINGET_TIMEOUT")


def test_verifier_requires_exact_package_and_version(monkeypatch):
    monkeypatch.setattr(worker_module, "_winget_alias_path", lambda: Path("C:/winget.exe"))
    monkeypatch.setattr(
        worker_module.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=0,
            stdout="Name  Id  Version  Available  Source\nDBeaver  DBeaver.DBeaver.Community  26.2.4  26.2.5  winget\n",
        ),
    )

    assert worker_module.verify_exact_user_install("DBeaver.DBeaver.Community", "26.2.4") is True
    assert worker_module.verify_exact_user_install("DBeaver.DBeaver.Community", "26.2.5") is False



def test_worker_does_not_reinstall_an_exact_package_already_present(monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    executor_calls = []
    monkeypatch.setattr(
        worker_module,
        "prepare_approved_install",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not prepare installer")),
    )
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=lambda *_a, **_k: executor_calls.append(True),
        verifier=lambda *_a: True,
        heartbeat_seconds=5,
    )

    result = worker.run_once()

    assert result.state == "SUCCEEDED"
    assert result.result_code == "PACKAGE_ALREADY_PRESENT"
    assert executor_calls == []
    assert [item[1] for item in store.transitions] == ["RUNNING", "VERIFYING", "SUCCEEDED"]


def test_worker_never_marks_success_when_winget_exits_nonzero(monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: object())
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=lambda *_a, **_k: SimpleNamespace(timed_out=False, exit_code=1),
        verifier=lambda *_a: False,
        heartbeat_seconds=5,
    )

    result = worker.run_once()

    assert result.state == "UNKNOWN"
    assert result.result_code == "WINGET_NONZERO_EXIT"
    assert [item[1] for item in store.transitions] == ["RUNNING", "UNKNOWN"]


def test_worker_marks_outcome_unknown_when_lease_loss_terminates_process(monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: object())
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)
    observed_cancellation = threading.Event()
    renewal_attempted = threading.Event()

    def fail_renewal(*_args, **_kwargs):
        renewal_attempted.set()
        raise RuntimeError("lease renewal rejected")

    store.renew_install_lease = fail_renewal

    def executor(*_args, **kwargs):
        cancel_event = kwargs["cancel_event"]
        assert renewal_attempted.wait(timeout=7)
        assert cancel_event.wait(timeout=2)
        observed_cancellation.set()
        return SimpleNamespace(timed_out=False, cancelled=cancel_event.is_set(), exit_code=None)

    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=executor,
        verifier=lambda *_a: False,
        heartbeat_seconds=5,
    )

    result = worker.run_once()

    assert observed_cancellation.is_set()
    assert result.state == "UNKNOWN"
    assert result.result_code == "WORKER_CANCELLED_PROCESS_TERMINATED"


@pytest.mark.parametrize("returncode", [0x8A150014, -1978335212])
def test_verifier_treats_winget_no_applications_result_as_absent(monkeypatch, returncode):
    monkeypatch.setattr(worker_module, "_winget_alias_path", lambda: Path("C:/winget.exe"))
    monkeypatch.setattr(
        worker_module.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=returncode, stdout=""),
    )
    assert worker_module.verify_exact_user_install("Acme.Editor", "1.2.3") is False


def test_verifier_parses_exact_id_with_single_space_column_boundaries(monkeypatch):
    monkeypatch.setattr(worker_module, "_winget_alias_path", lambda: Path("C:/winget.exe"))
    monkeypatch.setattr(
        worker_module.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=0,
            stdout="Name Id Version Available Source\nAcme Editor Acme.Editor 1.2.3 1.2.4 winget\n",
        ),
    )
    assert worker_module.verify_exact_user_install("Acme.Editor", "1.2.3") is True


def test_verifier_uses_version_after_package_id_when_display_name_contains_id(monkeypatch):
    monkeypatch.setattr(worker_module, "_winget_alias_path", lambda: Path("C:/winget.exe"))
    monkeypatch.setattr(
        worker_module.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=0,
            stdout=(
                "Name Id Version Available Source\n"
                "Acme.Editor 1.2.3 Acme.Editor 9.9.9 winget\n"
            ),
        ),
    )
    assert worker_module.verify_exact_user_install("Acme.Editor", "9.9.9") is True
    assert worker_module.verify_exact_user_install("Acme.Editor", "1.2.3") is False


def test_verifier_parses_version_when_display_name_equals_package_id(monkeypatch):
    monkeypatch.setattr(worker_module, "_winget_alias_path", lambda: Path("C:/winget.exe"))
    monkeypatch.setattr(
        worker_module.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=0,
            stdout=(
                "Name Id Version Available Source\n"
                "Acme.Editor  Acme.Editor  9.9.9  10.0.0  winget\n"
            ),
        ),
    )
    assert worker_module.verify_exact_user_install("Acme.Editor", "9.9.9") is True
    assert worker_module.verify_exact_user_install("Acme.Editor", "10.0.0") is False


def test_verifier_parses_localized_winget_inventory_header(monkeypatch):
    monkeypatch.setattr(worker_module, "_winget_alias_path", lambda: Path("C:/winget.exe"))
    monkeypatch.setattr(
        worker_module.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=0,
            stdout="Nom ID Version\nAcme Editor Acme.Editor 1.2.3 winget\n",
        ),
    )
    assert worker_module.verify_exact_user_install("Acme.Editor", "1.2.3") is True


def test_verifier_returns_ambiguous_for_unparseable_success_output(monkeypatch):
    monkeypatch.setattr(worker_module, "_winget_alias_path", lambda: Path("C:/winget.exe"))
    monkeypatch.setattr(
        worker_module.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="unexpected output"),
    )
    assert worker_module.verify_exact_user_install("Acme.Editor", "1.2.3") is None

def test_worker_executor_observes_shutdown_directly(monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    stop = threading.Event()
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: object())
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)

    def executor(*_args, **kwargs):
        stop.set()
        cancel_event = kwargs["cancel_event"]
        assert cancel_event.is_set()
        return SimpleNamespace(timed_out=False, cancelled=True, exit_code=None)

    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=executor,
        verifier=lambda *_a: False,
        heartbeat_seconds=5,
        stop_event=stop,
    )
    # The test calls the claimed-job path directly because run_once correctly
    # refuses to claim work after shutdown has already been requested.
    result = worker._process(store.job)
    assert result.state == "UNKNOWN"
    assert result.result_code == "WORKER_CANCELLED_PROCESS_TERMINATED"


def test_worker_denies_when_no_exact_persisted_release_matches(monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    store.release_error = worker_module.ApprovalReservationConflict(
        "no exact package/version/action authorization"
    )
    executor_calls = []
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: object())
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=lambda *_a, **_k: executor_calls.append(True),
        verifier=lambda *_a: False,
        heartbeat_seconds=5,
    )

    result = worker.run_once()

    assert result.state == "FAILED"
    assert result.result_code == "RELEASE_AUTHORIZATION_DENIED"
    assert executor_calls == []
    assert store.release_consumptions == []

@pytest.mark.parametrize(
    ("denial", "expected_state", "expected_code"),
    [
        ("missing", "FAILED", "RELEASE_AUTHORIZATION_DENIED"),
        ("task", "FAILED", "RELEASE_AUTHORIZATION_DENIED"),
        ("version", "FAILED", "RELEASE_AUTHORIZATION_DENIED"),
        ("replay", "FAILED", "RELEASE_AUTHORIZATION_DENIED"),
        ("expired", "FAILED", "RELEASE_AUTHORIZATION_DENIED"),
        ("unavailable", "UNKNOWN", "RELEASE_AUTHORIZATION_UNAVAILABLE"),
    ],
)
def test_worker_denial_paths_never_reach_executor(monkeypatch, tmp_path, denial, expected_state, expected_code):
    binding = make_binding()
    store = FakeStore(binding)
    executor_calls = []
    monkeypatch.setattr(worker_module, "prepare_approved_install", lambda *_a, **_k: object())
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)
    if denial in {"missing", "task", "version", "replay"}:
        store.release_error = worker_module.ApprovalReservationConflict(
            "no unused exact release authorization"
        )
    elif denial == "expired":
        store.release_error = worker_module.ApprovalReservationExpired("authorization expired")
    elif denial == "unavailable":
        store.release_error = worker_module.ApprovalReservationError("reservation store unavailable")

    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=lambda *_a, **_k: executor_calls.append(True),
        verifier=lambda *_a: False,
        heartbeat_seconds=5,
    )

    result = worker.run_once()

    assert result.state == expected_state
    assert result.result_code == expected_code
    assert executor_calls == []
    assert store.release_consumptions == []


def test_worker_does_not_consume_release_when_shutdown_arrives_before_execution(monkeypatch, tmp_path):
    binding = make_binding()
    store = FakeStore(binding)
    stop = threading.Event()
    executor_calls = []

    def prepare(*_args, **_kwargs):
        stop.set()
        return object()

    monkeypatch.setattr(worker_module, "prepare_approved_install", prepare)
    monkeypatch.setattr(worker_module, "cleanup_prepared_install", lambda *_a, **_k: None)
    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=lambda *_a, **_k: executor_calls.append(True),
        verifier=lambda *_a: False,
        heartbeat_seconds=5,
        stop_event=stop,
    )

    result = worker.run_once()

    assert result.state == "UNKNOWN"
    assert result.result_code == "WORKER_CANCELLED_BEFORE_EXECUTION"
    assert store.release_consumptions == []
    assert executor_calls == []
