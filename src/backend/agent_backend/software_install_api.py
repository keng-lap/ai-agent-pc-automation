"""Windows-local API that turns a verified installer into an exact install proposal."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_backend.software_discovery_api import _repository
from agent_backend.software_discovery import DiscoveryNotFound, DiscoveryUnavailable
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
def get_software_install_readiness() -> dict:
    """Expose non-secret readiness flags for the real-install workflow."""
    return {
        "platform_supported": sys.platform == "win32",
        "authenticode_verification_available": sys.platform == "win32",
        "publisher_trust_configured": software_evidence_registry.trust_anchor_configured,
        "supported_package_ids": (
            ["DBeaver.DBeaver.Community"]
            if software_evidence_registry.trust_anchor_configured
            else []
        ),
        "notice": "NO_INSTALL_IS_STARTED_BY_THIS_ENDPOINT",
    }


@router.post(
    "/api/software/install/proposals",
    response_model=SoftwareInstallProposalResponse,
)
def create_software_install_proposal(
    payload: SoftwareInstallProposalRequest,
    request: Request,
) -> SoftwareInstallProposalResponse:
    """Rediscover, stage, hash and Authenticode-check the exact package before approval."""
    if sys.platform != "win32":
        raise HTTPException(
            status_code=503,
            detail="Installer Authenticode verification is available only on Windows.",
        )

    try:
        discovery = _repository.discover(
            package_id=payload.package_id,
            version=payload.version,
            architecture=payload.architecture,
        )
    except DiscoveryNotFound:
        raise HTTPException(status_code=404, detail="Package or version not found.") from None
    except DiscoveryUnavailable:
        raise HTTPException(status_code=503, detail="Approved package source is unavailable.") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="Package lookup parameters are invalid.") from None

    candidate = discovery.candidate
    if (
        discovery.status != "CONDITIONAL"
        or candidate is None
        or candidate.package_id != payload.package_id
        or candidate.version != payload.version
        or candidate.architecture != payload.architecture
        or candidate.publisher_verification != "VERIFIED"
        or candidate.official_version != candidate.version
        or candidate.official_asset_sha256 != candidate.installer_sha256
    ):
        raise HTTPException(
            status_code=409,
            detail="The exact package is not matched to a verified official publisher release.",
        )

    store_path = getattr(request.app.state, "job_store_path", None)
    if store_path is None:
        raise HTTPException(status_code=503, detail="Local installer staging storage is unavailable.")
    staging_root = Path(store_path).parent / "winget-evidence"

    staged = None
    try:
        staged = _stager.stage(candidate, staging_root=staging_root)
        evidence = software_evidence_registry.register_staged_candidate(
            candidate=candidate,
            staged=staged,
        )
        plan = software_install_plan_store.create(evidence)
    except InstallerStageError:
        raise HTTPException(
            status_code=409,
            detail="Installer download, hash, or Authenticode verification did not pass.",
        ) from None
    except EvidenceRejected:
        raise HTTPException(
            status_code=409,
            detail="Publisher certificate is not present in the backend-owned trust policy.",
        ) from None
    except InstallPlanCapacityError:
        raise HTTPException(status_code=503, detail="Active install proposal capacity reached.") from None
    finally:
        if staged is not None:
            try:
                Path(staged.file_path).unlink(missing_ok=True)
            except OSError:
                pass

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
