"""Tests for the one-shot local WinGet install worker."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

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
        installer_url="https://example.com/dbeaver.exe",
        official_release_url="https://example.com/releases/26.2.4",
        manifest_source_url="https://github.com/microsoft/winget-pkgs/tree/" + "c" * 40,
        repository_commit="c" * 40,
        installer_sha256="b" * 64,
        manifest_sha256="c" * 64,
        architecture="x64",
        scope="user",
        signature_subject="CN=DBeaver Corporation",
        signature_sha256="d" * 64,
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
        )
        self.transitions = []

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

    def renew_install_lease(self, *_args, **_kwargs):
        self.job = replace(self.job, version=self.job.version + 1)
        return self.job


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

    worker = worker_module.SoftwareInstallWorker(
        store,
        work_root=tmp_path / "work",
        worker_id="worker-1",
        executor=executor,
        verifier=lambda package_id, version: (
            package_id == binding.evidence.package_id and version == binding.evidence.version
        ),
        heartbeat_seconds=5,
    )
    result = worker.run_once()

    assert result.state == "SUCCEEDED"
    assert [item[1] for item in store.transitions] == ["RUNNING", "VERIFYING", "SUCCEEDED"]
    assert executor_calls[0][0].approval_digest == binding.approval_digest
    assert executor_calls[0][1] is prepared


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
        verifier=lambda *_a: True,
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
