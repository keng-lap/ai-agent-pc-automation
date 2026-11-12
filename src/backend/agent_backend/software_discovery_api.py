"""Authenticated, read-only API for exact WinGet package manifest lookup."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_backend.software_discovery import (
    DiscoveryNotFound,
    DiscoveryUnavailable,
    WinGetManifestRepository,
)

router = APIRouter()
_repository = WinGetManifestRepository()


class SoftwareDiscoveryRequest(BaseModel):
    """An untrusted package lookup key; never installer evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    package_id: str = Field(min_length=3, max_length=160)
    version: str | None = Field(default=None, min_length=1, max_length=80)
    architecture: Literal["x86", "x64", "arm64"] = "x64"

    @field_validator("package_id")
    @classmethod
    def normalize_package_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("package_id must not be blank")
        return normalized


@router.post("/api/software/discovery")
def discover_software(payload: SoftwareDiscoveryRequest) -> dict:
    """Read official WinGet community manifests; never download or execute installers."""
    try:
        result = _repository.discover(
            package_id=payload.package_id,
            version=payload.version,
            architecture=payload.architecture,
        )
    except DiscoveryNotFound:
        raise HTTPException(status_code=404, detail="Package or version not found in the approved source.") from None
    except DiscoveryUnavailable:
        raise HTTPException(status_code=503, detail="Approved package source is unavailable or its data failed validation.") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="Package lookup parameters are invalid.") from None
    return result.model_dump(mode="json")
