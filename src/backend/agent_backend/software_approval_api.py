"""Exact-action approval API for backend-registered software evidence.

This endpoint authorizes a proposal only. It deliberately has no installer
dispatch, package-manager call, background-job enqueue, or machine side effect.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from agent_backend.auth_audit import record_auth_audit_event
from agent_backend.authenticator import SecretStoreError
from agent_backend.plan_api import _plan_store
from agent_backend.plans import PlanExpiredError, PlanNotFoundError
from agent_backend.software_approval import InstallApprovalBinding
from agent_backend.software_evidence import (
    EvidenceNotFound,
    EvidenceRejected,
    software_evidence_registry,
)

router = APIRouter()
_lock = threading.RLock()
_bindings: dict[str, tuple[str, str, InstallApprovalBinding]] = {}
MAX_BINDINGS = 128
_consumed_bindings: dict[str, datetime] = {}


def _prune_bindings() -> None:
    now = datetime.now(UTC)
    expired = [
        plan_id for plan_id, (_owner, _session, binding) in _bindings.items()
        if now >= binding.evidence.expires_at
    ]
    for plan_id in expired:
        _bindings.pop(plan_id, None)
    expired_consumed = [plan_id for plan_id, expires_at in _consumed_bindings.items() if now >= expires_at]
    for plan_id in expired_consumed:
        _consumed_bindings.pop(plan_id, None)


class SoftwareApprovalChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    evidence_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")


class SoftwareApprovalProofRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    challenge_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    totp_code: str = Field(pattern=r"^[0-9]{6}$")


class SoftwareApprovalChallengeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    plan_id: str
    challenge_id: str
    expires_at: float
    package_id: str
    package_name: str
    publisher: str
    version: str
    architecture: Literal["x86", "x64", "arm64"]
    scope: Literal["user"]
    installer_type: Literal["exe", "msi", "msix", "appx"]
    installer_url: str
    official_release_url: str
    manifest_source_url: str
    repository_commit: str
    installer_sha256: str
    manifest_sha256: str
    signature_subject: str
    evidence_expires_at: str
    approval_digest: str
    notice: Literal["APPROVAL_ONLY_NOT_EXECUTED"] = "APPROVAL_ONLY_NOT_EXECUTED"


class SoftwareApprovalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    plan_id: str
    approved: Literal[True] = True
    approval_digest: str
    package_id: str
    version: str
    notice: Literal["APPROVED_NOT_EXECUTED"] = "APPROVED_NOT_EXECUTED"


def _authenticated_context(request: Request):
    services = getattr(request.app.state, "auth_services", None)
    principal = getattr(request.state, "principal", None)
    if services is None or principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        secret = services.secret_store.load(owner_sub=principal.owner_sub)
    except SecretStoreError:
        raise HTTPException(status_code=503, detail="Authenticator storage unavailable.") from None
    if secret is None:
        raise HTTPException(status_code=403, detail="Authenticator enrollment required.")
    return services, principal, secret


def _get_install_plan(plan_id: str):
    if len(plan_id) != 32 or any(char not in "0123456789abcdef" for char in plan_id):
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        plan = _plan_store.get(plan_id)
    except PlanExpiredError:
        raise HTTPException(status_code=410, detail="Plan expired.") from None
    except PlanNotFoundError:
        raise HTTPException(status_code=404, detail="Plan not found.") from None
    if (
        plan.tool_id != "software.install"
        or plan.risk_class != "R1"
        or plan.required_permission != "P1"
        or plan.mode != "dry_run"
        or any(item.status != "PLANNED" for item in plan.programs)
    ):
        raise HTTPException(status_code=409, detail="Plan is not eligible for software approval.")
    if len(plan.programs) != 1:
        raise HTTPException(status_code=409, detail="Software evidence must bind to one exact package.")
    return plan


@router.post(
    "/api/plans/{plan_id}/software-approval",
    response_model=SoftwareApprovalChallengeResponse,
)
def create_software_approval_challenge(
    plan_id: str,
    payload: SoftwareApprovalChallengeRequest,
    request: Request,
) -> SoftwareApprovalChallengeResponse:
    """Bind registry evidence to the plan, then create an exact-digest TOTP challenge."""
    services, principal, _secret = _authenticated_context(request)
    plan = _get_install_plan(plan_id)
    try:
        binding = software_evidence_registry.bind_to_plan(
            evidence_id=payload.evidence_id,
            plan_digest=plan.plan_digest,
        )
    except EvidenceNotFound:
        raise HTTPException(status_code=404, detail="Verified software evidence not found or expired.") from None
    except EvidenceRejected:
        raise HTTPException(status_code=409, detail="Verified software evidence cannot be bound to this plan.") from None

    evidence = binding.evidence
    requested_target = plan.programs[0].program.casefold()
    if requested_target not in {evidence.package_id.casefold(), evidence.package_name.casefold()}:
        raise HTTPException(status_code=409, detail="Verified package does not match the requested plan target.")

    with _lock:
        _prune_bindings()
        if plan_id in _consumed_bindings:
            raise HTTPException(status_code=409, detail="This software approval has already been consumed.")
        existing = _bindings.get(plan_id)
        if existing is not None and (
            existing[0] != principal.owner_sub
            or existing[1] != principal.session_id
            or existing[2].approval_digest != binding.approval_digest
        ):
            raise HTTPException(status_code=409, detail="Plan already has a different approval binding.")
        if existing is None and len(_bindings) >= MAX_BINDINGS:
            raise HTTPException(status_code=503, detail="Software approval capacity reached.")
        _bindings[plan_id] = (principal.owner_sub, principal.session_id, binding)

    challenge = services.step_up.create(
        owner_sub=principal.owner_sub,
        session_id=principal.session_id,
        plan_id=plan.plan_id,
        action_digest=binding.approval_digest,
        risk_class="high",
    )
    return SoftwareApprovalChallengeResponse(
        plan_id=plan_id,
        challenge_id=challenge.challenge_id,
        expires_at=challenge.expires_at,
        package_id=evidence.package_id,
        package_name=evidence.package_name,
        publisher=evidence.publisher,
        version=evidence.version,
        architecture=evidence.architecture,
        scope=evidence.scope,
        installer_type=evidence.installer_type,
        installer_url=evidence.installer_url,
        official_release_url=evidence.official_release_url,
        manifest_source_url=evidence.manifest_source_url,
        repository_commit=evidence.repository_commit,
        installer_sha256=evidence.installer_sha256,
        manifest_sha256=evidence.manifest_sha256,
        signature_subject=evidence.signature_subject,
        evidence_expires_at=evidence.expires_at.isoformat(),
        approval_digest=binding.approval_digest,
    )


@router.post(
    "/api/plans/{plan_id}/software-approval/confirm",
    response_model=SoftwareApprovalResult,
)
def confirm_software_approval(
    plan_id: str,
    payload: SoftwareApprovalProofRequest,
    request: Request,
) -> SoftwareApprovalResult:
    """Consume the one-use TOTP challenge for the exact evidence-bound proposal."""
    services, principal, secret = _authenticated_context(request)
    plan = _get_install_plan(plan_id)
    with _lock:
        _prune_bindings()
        if plan_id in _consumed_bindings:
            raise HTTPException(status_code=409, detail="This software approval has already been consumed.")
        stored = _bindings.get(plan_id)
    if stored is None:
        raise HTTPException(status_code=409, detail="Software approval binding is missing.")
    owner_sub, session_id, binding = stored
    if owner_sub != principal.owner_sub or session_id != principal.session_id:
        raise HTTPException(status_code=403, detail="Approval binding belongs to another session.")
    try:
        current = software_evidence_registry.bind_to_plan(
            evidence_id=binding.evidence.evidence_id,
            plan_digest=plan.plan_digest,
        )
    except (EvidenceNotFound, EvidenceRejected):
        with _lock:
            _bindings.pop(plan_id, None)
        raise HTTPException(status_code=409, detail="Verified software evidence expired or was revoked.") from None
    if current.approval_digest != binding.approval_digest:
        with _lock:
            _bindings.pop(plan_id, None)
        raise HTTPException(status_code=409, detail="Software approval digest changed; rediscovery is required.")

    # Serialize confirmation per process: distinct one-use TOTP challenges must not
    # authorize the same plan/evidence binding more than once.
    with _lock:
        if plan_id in _consumed_bindings:
            raise HTTPException(status_code=409, detail="This software approval has already been consumed.")
        accepted = services.step_up.verify_and_consume(
            challenge_id=payload.challenge_id,
            owner_sub=principal.owner_sub,
            session_id=principal.session_id,
            plan_id=plan.plan_id,
            action_digest=binding.approval_digest,
            risk_class="high",
            secret=secret,
            code=payload.totp_code,
        )
        if accepted:
            _consumed_bindings[plan_id] = binding.evidence.expires_at
    if not accepted:
        record_auth_audit_event(
            event_type="auth.step_up",
            outcome="denied",
            reason="invalid_software_approval",
        )
        raise HTTPException(status_code=403, detail="Step-up verification failed.")
    record_auth_audit_event(event_type="auth.step_up", outcome="success")
    return SoftwareApprovalResult(
        plan_id=plan_id,
        approval_digest=binding.approval_digest,
        package_id=binding.evidence.package_id,
        version=binding.evidence.version,
    )
