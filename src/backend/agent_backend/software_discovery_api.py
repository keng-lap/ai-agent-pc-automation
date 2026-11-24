"""Authenticated, read-only API for exact WinGet package manifest lookup."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_backend.runtime_diagnostics import emit_event
from agent_backend.software_catalog import CatalogUnavailable, MicrosoftWinGetCatalogIndex
from agent_backend.software_discovery import (
    DiscoveryNotFound,
    DiscoveryUnavailable,
    WinGetManifestRepository,
)

router = APIRouter()
_repository = WinGetManifestRepository()
_catalog = MicrosoftWinGetCatalogIndex()


class SoftwareDiscoverySearchRequest(BaseModel):
    """Natural-language product lookup; no AI-provided package data is trusted."""

    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=2, max_length=128)
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized


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


@router.post("/api/software/discovery/search")
def search_software_catalog(payload: SoftwareDiscoverySearchRequest, request: Request) -> dict:
    """Search Microsoft's signed source2 catalog without invoking winget.exe."""
    try:
        result = _catalog.search(payload.query, limit=payload.limit)
    except CatalogUnavailable:
        emit_event(
            event_code="CATALOG_SOURCE_UNAVAILABLE",
            component="catalog",
            stage="catalog_lookup",
            correlation=getattr(request.state, "correlation_id", "unknown"),
            severity="ERROR",
            fields={"status_code": 503},
        )
        raise HTTPException(
            status_code=503,
            detail="Microsoft WinGet catalog is unavailable or failed trust validation.",
        ) from None
    except ValueError:
        emit_event(
            event_code="CATALOG_QUERY_INVALID",
            component="catalog",
            stage="catalog_lookup",
            correlation=getattr(request.state, "correlation_id", "unknown"),
            severity="WARNING",
            fields={"status_code": 422},
        )
        raise HTTPException(status_code=422, detail="Catalog search parameters are invalid.") from None
    emit_event(
        event_code="CATALOG_LOOKUP_COMPLETED",
        component="catalog",
        stage="catalog_lookup",
        correlation=getattr(request.state, "correlation_id", "unknown"),
        fields={"candidate_count": len(result.candidates), "status_code": 200},
    )
    return result.model_dump(mode="json")


@router.post("/api/software/discovery")
def discover_software(payload: SoftwareDiscoveryRequest, request: Request) -> dict:
    """Read official WinGet community manifests; never download or execute installers."""
    try:
        result = _repository.discover(
            package_id=payload.package_id,
            version=payload.version,
            architecture=payload.architecture,
        )
    except DiscoveryNotFound:
        emit_event(
            event_code="MANIFEST_NOT_FOUND",
            component="manifest",
            stage="manifest_discovery",
            correlation=getattr(request.state, "correlation_id", "unknown"),
            severity="WARNING",
            fields={"status_code": 404},
        )
        raise HTTPException(status_code=404, detail="Package or version not found in the approved source.") from None
    except DiscoveryUnavailable:
        emit_event(
            event_code="MANIFEST_SOURCE_UNAVAILABLE_OR_INVALID",
            component="manifest",
            stage="manifest_validation",
            correlation=getattr(request.state, "correlation_id", "unknown"),
            severity="ERROR",
            fields={"status_code": 503},
        )
        raise HTTPException(status_code=503, detail="Approved package source is unavailable or its data failed validation.") from None
    except ValueError:
        emit_event(
            event_code="MANIFEST_LOOKUP_PARAMETERS_INVALID",
            component="manifest",
            stage="manifest_discovery",
            correlation=getattr(request.state, "correlation_id", "unknown"),
            severity="WARNING",
            fields={"status_code": 422},
        )
        raise HTTPException(status_code=422, detail="Package lookup parameters are invalid.") from None
    emit_event(
        event_code="MANIFEST_" + result.status,
        component="manifest",
        stage="manifest_validation",
        correlation=getattr(request.state, "correlation_id", "unknown"),
        fields={"status_code": 200, "available_version_count": len(result.available_versions)},
    )
    return result.model_dump(mode="json")
