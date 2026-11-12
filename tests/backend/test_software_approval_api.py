"""API tests for exact evidence-bound software approval without execution."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from agent_backend import software_approval_api as api
from agent_backend.software_approval import VerifiedPackageEvidence, build_install_approval_binding
from agent_backend.software_evidence import EvidenceNotFound

NOW = datetime.now(UTC)
PLAN_ID = "1" * 32
PLAN_DIGEST = "a" * 64


def make_binding():
    evidence = VerifiedPackageEvidence(
        evidence_id="e" * 32,
        package_id="DBeaver.DBeaver.Community",
        publisher="DBeaver Corp",
        version="26.2.4",
        source="winget",
        installer_url="https://github.com/dbeaver/dbeaver/releases/download/26.2.4/dbeaver.exe",
        installer_sha256="b" * 64,
        manifest_sha256="c" * 64,
        architecture="x64",
        scope="user",
        signature_subject="CN=DBeaver Corporation",
        verified_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    return build_install_approval_binding(plan_digest=PLAN_DIGEST, evidence=evidence)


def setup_context(monkeypatch, *, owner="owner-1", session="session-1", accepted=True):
    class StepUp:
        def __init__(self):
            self.created = []
            self.verified = []

        def create(self, **kwargs):
            self.created.append(kwargs)
            return SimpleNamespace(challenge_id="f" * 32, expires_at=NOW.timestamp() + 120)

        def verify_and_consume(self, **kwargs):
            self.verified.append(kwargs)
            return accepted

    step_up = StepUp()
    principal = SimpleNamespace(owner_sub=owner, session_id=session)
    services = SimpleNamespace(
        step_up=step_up,
        secret_store=SimpleNamespace(load=lambda owner_sub: "test-secret"),
    )
    monkeypatch.setattr(api, "_authenticated_context", lambda _request: (services, principal, "test-secret"))
    monkeypatch.setattr(
        api,
        "_get_install_plan",
        lambda _plan_id: SimpleNamespace(
            plan_id=PLAN_ID,
            plan_digest=PLAN_DIGEST,
            tool_id="software.install",
            risk_class="R1",
            required_permission="P1",
            mode="dry_run",
            programs=(SimpleNamespace(program="DBeaver.DBeaver.Community", status="PLANNED"),),
        ),
    )
    api._bindings.clear()
    return step_up, principal


def test_challenge_binds_exact_evidence_digest_and_returns_no_execution(monkeypatch):
    binding = make_binding()
    step_up, _principal = setup_context(monkeypatch)
    monkeypatch.setattr(
        api.software_evidence_registry,
        "bind_to_plan",
        lambda **_kwargs: binding,
    )

    response = api.create_software_approval_challenge(
        PLAN_ID,
        api.SoftwareApprovalChallengeRequest(evidence_id="e" * 32),
        request=object(),
    )

    assert response.approval_digest == binding.approval_digest
    assert response.package_id == binding.evidence.package_id
    assert response.notice == "APPROVAL_ONLY_NOT_EXECUTED"
    assert step_up.created[0]["action_digest"] == binding.approval_digest
    assert step_up.created[0]["plan_id"] == PLAN_ID


def test_confirm_consumes_exact_digest_and_returns_approved_not_executed(monkeypatch):
    binding = make_binding()
    step_up, _principal = setup_context(monkeypatch)
    monkeypatch.setattr(
        api.software_evidence_registry,
        "bind_to_plan",
        lambda **_kwargs: binding,
    )
    api._bindings[PLAN_ID] = ("owner-1", "session-1", binding)

    response = api.confirm_software_approval(
        PLAN_ID,
        api.SoftwareApprovalProofRequest(challenge_id="f" * 32, totp_code="123456"),
        request=object(),
    )

    assert response.approved is True
    assert response.notice == "APPROVED_NOT_EXECUTED"
    assert response.approval_digest == binding.approval_digest
    assert step_up.verified[0]["action_digest"] == binding.approval_digest
    assert step_up.verified[0]["code"] == "123456"


def test_confirm_rejects_binding_from_another_session(monkeypatch):
    binding = make_binding()
    setup_context(monkeypatch, owner="owner-2", session="session-2")
    api._bindings[PLAN_ID] = ("owner-1", "session-1", binding)

    with pytest.raises(Exception) as error:
        api.confirm_software_approval(
            PLAN_ID,
            api.SoftwareApprovalProofRequest(challenge_id="f" * 32, totp_code="123456"),
            request=object(),
        )
    assert getattr(error.value, "status_code", None) == 403


def test_confirm_rejects_expired_or_revoked_evidence(monkeypatch):
    binding = make_binding()
    setup_context(monkeypatch)
    def expired(**_kwargs):
        raise EvidenceNotFound("expired")
    monkeypatch.setattr(api.software_evidence_registry, "bind_to_plan", expired)
    api._bindings[PLAN_ID] = ("owner-1", "session-1", binding)

    with pytest.raises(Exception) as error:
        api.confirm_software_approval(
            PLAN_ID,
            api.SoftwareApprovalProofRequest(challenge_id="f" * 32, totp_code="123456"),
            request=object(),
        )
    assert getattr(error.value, "status_code", None) == 409
    assert PLAN_ID not in api._bindings


def test_invalid_totp_never_returns_approval(monkeypatch):
    binding = make_binding()
    step_up, _principal = setup_context(monkeypatch, accepted=False)
    monkeypatch.setattr(api.software_evidence_registry, "bind_to_plan", lambda **_kwargs: binding)
    api._bindings[PLAN_ID] = ("owner-1", "session-1", binding)

    with pytest.raises(Exception) as error:
        api.confirm_software_approval(
            PLAN_ID,
            api.SoftwareApprovalProofRequest(challenge_id="f" * 32, totp_code="000000"),
            request=object(),
        )
    assert getattr(error.value, "status_code", None) == 403
    assert step_up.verified[0]["action_digest"] == binding.approval_digest
