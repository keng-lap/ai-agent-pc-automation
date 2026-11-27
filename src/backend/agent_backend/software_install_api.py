"""Windows-local API that turns a verified installer into an exact install proposal."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_backend.runtime_diagnostics import emit_event, emit_exception
from agent_backend.software_discovery import DiscoveryNotFound, DiscoveryUnavailable
from agent_backend.software_discovery_api import _repository
from agent_backend.software_evidence import EvidenceRejected, software_evidence_registry
from agent_backend.software_install_plans import (
    InstallPlanCapacityError,
    software_install_plan_store,
)
from agent_backend.software_staging import InstallerStageError, InstallerStager

router = APIRouter()
_stager = InstallerStager()


class SoftwareInstallProposalRequest(BaseModel):
    """Only the exact package lookup key is accepted from the client."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    package_id: str = Field(min_length=3, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    architecture: Literal["x86", "x64", "arm64"] = "x64"
    scope: Literal["user"] = "user"

    @field_validator("package_id", "version")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class SoftwareInstallProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    plan_id: str
    evidence_id: str
    package_id: str
    package_name: str
    publisher: str
    version: str
    architecture: Literal["x86", "x64", "arm64"]
    scope: Literal["user"]
    expires_at: str
    notice: Literal["VERIFIED_PROPOSAL_REQUIRES_EXACT_ACTION_TOTP"] = (
        "VERIFIED_PROPOSAL_REQUIRES_EXACT_ACTION_TOTP"
    )


@router.get("/api/software/install/readiness")
def get_software_install_readiness(request: Request) -> dict:
    """Expose active Windows worker readiness; each release is issued after exact-action TOTP."""
    settings = getattr(request.app.state, "settings", None)
    worker = getattr(request.app.state, "install_worker_thread", None)
    worker_ready = worker is not None and worker.is_alive()
    platform_supported = (
        sys.platform == "win32"
        and getattr(settings, "app_env", "development") != "test"
        and worker_ready
    )
    emit_event(
        event_code="INSTALL_READINESS_CHECKED",
        component="install",
        stage="install_readiness",
        correlation=getattr(request.state, "correlation_id", "unknown"),
        fields={"real_install_enabled": platform_supported},
    )
    return {
        "platform_supported": platform_supported,
        # Real install is enabled as a capability on Windows. Each individual
        # package/version is authorized only after its exact-action TOTP succeeds.
        "real_install_enabled": platform_supported,
        "real_install_release_package_id": None,
        "real_install_release_version": None,
        "real_install_release_expires_at": None,
        "authenticode_verification_available": sys.platform == "win32",
        "installer_trust_mode": "WINGET_MANIFEST_SHA256_AND_AUTHENTICODE_SIGNATURE_INTEGRITY",
        "package_allowlist_enabled": False,
        "supported_package_ids": [],
        "notice": "RELEASE_AUTHORIZATION_CREATED_AFTER_EXACT_ACTION_TOTP",
    }


@router.post(
    "/api/software/install/proposals",
    response_model=SoftwareInstallProposalResponse,
)
def create_software_install_proposal(
    payload: SoftwareInstallProposalRequest,
    request: Request,
) -> SoftwareInstallProposalResponse:
    """Rediscover, stage, hash and verify Authenticode signature integrity before approval."""
    correlation = getattr(request.state, "correlation_id", "unknown")
    started = datetime.now(UTC)
    emit_event(
        event_code="INSTALL_PROPOSAL_STARTED",
        component="install",
        stage="proposal_verification",
        correlation=correlation,
        fields={
            "package_id": payload.package_id,
            "version": payload.version,
            "scope": payload.scope,
        },
    )
    if sys.platform != "win32":
        emit_event(
            event_code="INSTALL_PROPOSAL_BLOCKED_PLATFORM",
            component="install",
            stage="proposal_verification",
            correlation=correlation,
            severity="WARNING",
            fields={"status_code": 503},
        )
        raise HTTPException(
            status_code=503,
            detail="Installer Authenticode verification is available only on Windows.",
        )
    principal = getattr(request.state, "principal", None)
    if (
        principal is None
        or not isinstance(getattr(principal, "owner_sub", None), str)
        or not principal.owner_sub.strip()
    ):
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        discovery = _repository.discover(
            package_id=payload.package_id,
            version=payload.version,
            architecture=payload.architecture,
            scope=payload.scope,
        )
    except DiscoveryNotFound as exc:
        emit_exception(
            event_code="INSTALL_PROPOSAL_MANIFEST_NOT_FOUND",
            component="install",
            stage="proposal_manifest_discovery",
            correlation=correlation,
            error=exc,
            severity="WARNING",
            fields={"status_code": 404},
        )
        raise HTTPException(status_code=404, detail="Package or version not found.") from None
    except DiscoveryUnavailable as exc:
        emit_exception(
            event_code="INSTALL_PROPOSAL_MANIFEST_UNAVAILABLE",
            component="install",
            stage="proposal_manifest_discovery",
            correlation=correlation,
            error=exc,
            fields={"status_code": 503},
        )
        raise HTTPException(status_code=503, detail="Approved package source is unavailable.") from None
    except ValueError:
        emit_event(
            event_code="INSTALL_PROPOSAL_REJECTED",
            component="install",
            stage="proposal_validation",
            correlation=correlation,
            severity="WARNING",
            fields={
                "status_code": 422,
                "failure_code": "invalid_lookup_parameters",
                "package_id": payload.package_id,
                "version": payload.version,
                "scope": payload.scope,
            },
        )
        raise HTTPException(status_code=422, detail="Package lookup parameters are invalid.") from None

    candidate = discovery.candidate
    if (
        discovery.status != "CONDITIONAL"
        or candidate is None
        or candidate.package_id != payload.package_id
        or candidate.version != payload.version
        or candidate.architecture != payload.architecture
        or candidate.scope != payload.scope
        or candidate.publisher_verification not in {"NOT_CHECKED", "VERIFIED"}
        or (
            candidate.publisher_verification == "VERIFIED"
            and (
                candidate.official_version != candidate.version
                or candidate.official_asset_sha256 != candidate.installer_sha256
            )
        )
        or (
            candidate.installer_type == "exe"
            and not candidate.installer_silent_switch
            and not candidate.installer_silent_with_progress_switch
            and (candidate.installer_technology or candidate.installer_type) not in {"nullsoft", "inno", "burn"}
        )
    ):
        mismatch_fields = []
        if discovery.status != "CONDITIONAL" or candidate is None:
            mismatch_fields.append("discovery_candidate")
        else:
            for field_name, actual, expected in (
                ("package_id", candidate.package_id, payload.package_id),
                ("version", candidate.version, payload.version),
                ("architecture", candidate.architecture, payload.architecture),
                ("scope", candidate.scope, payload.scope),
            ):
                if actual != expected:
                    mismatch_fields.append(field_name)
            if candidate.publisher_verification not in {"NOT_CHECKED", "VERIFIED"}:
                mismatch_fields.append("official_release_evidence")
            if (
                candidate.publisher_verification == "VERIFIED"
                and (
                    candidate.official_version != candidate.version
                    or candidate.official_asset_sha256 != candidate.installer_sha256
                )
            ):
                mismatch_fields.append("official_release_version_or_sha256")
            if (
                candidate.installer_type == "exe"
                and not candidate.installer_silent_switch
                and not candidate.installer_silent_with_progress_switch
                and (candidate.installer_technology or candidate.installer_type) not in {"nullsoft", "inno", "burn"}
            ):
                mismatch_fields.append("silent_install_strategy")
        emit_event(
            event_code="INSTALL_PROPOSAL_REJECTED",
            component="install",
            stage="proposal_validation",
            correlation=correlation,
            severity="WARNING",
            fields={
                "status_code": 409,
                "failure_code": "candidate_evidence_mismatch",
                "failure_reason": "The selected manifest candidate failed one or more exact-evidence checks.",
                "mismatch_fields": ",".join(mismatch_fields or ["candidate_contract"]),
                "package_id": payload.package_id,
                "version": payload.version,
                "scope": payload.scope,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="The exact package is not eligible for installer evidence verification.",
        )

    if candidate.installer_type.casefold() not in {"exe", "msi", "msix", "appx"}:
        emit_event(
            event_code="INSTALL_PROPOSAL_REJECTED",
            component="install",
            stage="proposal_validation",
            correlation=correlation,
            severity="WARNING",
            fields={
                "status_code": 409,
                "failure_code": "installer_type_unsupported",
                "failure_reason": "The selected WinGet InstallerType is not supported by the verified install contract.",
                "installer_type": candidate.installer_type,
                "package_id": payload.package_id,
                "version": payload.version,
                "scope": payload.scope,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="The selected installer type is not supported for verified installation.",
        )

    store_path = getattr(request.app.state, "job_store_path", None)
    if store_path is None:
        emit_event(
            event_code="INSTALL_PROPOSAL_REJECTED",
            component="install",
            stage="proposal_validation",
            correlation=correlation,
            severity="ERROR",
            fields={
                "status_code": 503,
                "failure_code": "staging_storage_unavailable",
                "package_id": payload.package_id,
                "version": payload.version,
                "scope": payload.scope,
            },
        )
        raise HTTPException(status_code=503, detail="Local installer staging storage is unavailable.")
    staging_root = Path(store_path).expanduser().absolute().parent / "winget-evidence"

    staged = None
    evidence = None
    try:
        staged = _stager.stage(candidate, staging_root=staging_root)
        evidence = software_evidence_registry.register_staged_candidate(
            candidate=candidate,
            staged=staged,
        )
        plan = software_install_plan_store.create(evidence, owner_id=principal.owner_sub)
    except InstallerStageError as exc:
        emit_exception(
            event_code="INSTALLER_STAGING_FAILED",
            component="install",
            stage="installer_staging",
            correlation=correlation,
            error=exc,
            severity="ERROR",
            fields={
                "status_code": 409,
                "failure_code": exc.failure_code,
                "failure_reason": exc.failure_reason,
                "package_id": payload.package_id,
                "selected_version": payload.version,
                "scope": payload.scope,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="Installer download, hash, or Authenticode verification did not pass.",
        ) from None
    except EvidenceRejected as exc:
        emit_exception(
            event_code="INSTALLER_EVIDENCE_REJECTED",
            component="install",
            stage="installer_evidence",
            correlation=correlation,
            error=exc,
            severity="ERROR",
            fields={
                "status_code": 409,
                "failure_code": exc.failure_code,
                "failure_reason": exc.failure_reason,
                "package_id": payload.package_id,
                "selected_version": payload.version,
                "scope": payload.scope,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="Installer evidence did not satisfy the verification policy.",
        ) from None
    except InstallPlanCapacityError:
        emit_event(
            event_code="INSTALL_PROPOSAL_REJECTED",
            component="install",
            stage="proposal_validation",
            correlation=correlation,
            severity="WARNING",
            fields={
                "status_code": 503,
                "failure_code": "active_proposal_capacity_reached",
                "package_id": payload.package_id,
                "version": payload.version,
                "scope": payload.scope,
            },
        )
        if evidence is not None:
            software_evidence_registry.revoke(evidence.evidence_id)
        raise HTTPException(status_code=503, detail="Active install proposal capacity reached.") from None
    finally:
        if staged is not None:
            try:
                Path(staged.file_path).unlink(missing_ok=True)
            except OSError:
                pass

    emit_event(
        event_code="INSTALL_PROPOSAL_CREATED",
        component="install",
        stage="proposal_verification",
        correlation=correlation,
        fields={
            "duration_ms": round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
            "publisher_verification": candidate.publisher_verification,
            "plan_id": plan.plan_id,
            "package_id": evidence.package_id,
            "version": evidence.version,
            "scope": evidence.scope,
        },
    )
    return SoftwareInstallProposalResponse(
        plan_id=plan.plan_id,
        evidence_id=evidence.evidence_id,
        package_id=evidence.package_id,
        package_name=evidence.package_name,
        publisher=evidence.publisher,
        version=evidence.version,
        architecture=evidence.architecture,
        scope=evidence.scope,
        expires_at=plan.expires_at.isoformat(),
    )
