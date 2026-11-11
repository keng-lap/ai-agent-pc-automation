"""Fixed WinGet install adapter (P6-603).

This module is intentionally not wired into the API or tool dispatch yet.
Callers must supply a server-created, validated request; model text is never
accepted as an executable, argument list, URL, or handler name.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


_PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,79}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
MAX_OUTPUT_CHARS = 4000
INSTALL_TIMEOUT_SECONDS = 1800


class VerifiedInstallRequest(BaseModel):
    """Immutable package selection created only from verified discovery evidence."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    package_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=80)
    architecture: Literal["x64", "x86", "arm64"]
    scope: Literal["user"] = "user"
    source: Literal["winget"] = "winget"
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def validate_identity(cls, value: str, pattern: re.Pattern[str], field: str) -> str:
        if not pattern.fullmatch(value):
            raise ValueError(f"invalid {field}")
        return value

    @classmethod
    def model_validate(cls, obj, **kwargs):
        # Pydantic performs strict shape/type checks; explicit regex checks below
        # are kept in field validators so validation cannot be bypassed by callers.
        return super().model_validate(obj, **kwargs)


class WinGetInstallResult(BaseModel):
    """Bounded result; never exposes a command line or unbounded process output."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    exit_code: int
    timed_out: bool = False
    output_excerpt: str = Field(max_length=MAX_OUTPUT_CHARS)


def _winget_path() -> Path:
    """Resolve only the current user's Windows App Execution Alias location."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("winget_unavailable")
    root = Path(local_app_data)
    if not root.is_absolute():
        raise RuntimeError("winget_unavailable")
    executable = root / "Microsoft" / "WindowsApps" / "winget.exe"
    if not executable.is_file():
        raise RuntimeError("winget_unavailable")
    return executable


def build_install_arguments(request: VerifiedInstallRequest) -> tuple[str, ...]:
    """Build a fixed argv vector; no caller-controlled switches or free-form text."""
    if not isinstance(request, VerifiedInstallRequest):
        raise TypeError("a verified install request is required")
    if not _PACKAGE_ID.fullmatch(request.package_id):
        raise ValueError("invalid package_id")
    if not _VERSION.fullmatch(request.version):
        raise ValueError("invalid version")
    if not _SHA256.fullmatch(request.evidence_sha256):
        raise ValueError("invalid discovery evidence digest")
    return (
        "install",
        "--id",
        request.package_id,
        "--exact",
        "--version",
        request.version,
        "--architecture",
        request.architecture,
        "--scope",
        "user",
        "--source",
        "winget",
        "--silent",
        "--disable-interactivity",
        "--accept-package-agreements",
        "--accept-source-agreements",
    )


def install_verified_package(
    request: VerifiedInstallRequest,
    *,
    runner=subprocess.run,
) -> WinGetInstallResult:
    """Invoke the fixed WinGet executable with shell disabled and bounded runtime."""
    executable = _winget_path()
    arguments = build_install_arguments(request)
    try:
        completed = runner(
            [str(executable), *arguments],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            cwd=str(executable.parent.parent.parent),
            timeout=INSTALL_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or exc.stderr or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return WinGetInstallResult(
            exit_code=-1,
            timed_out=True,
            output_excerpt=str(output)[-MAX_OUTPUT_CHARS:],
        )
    output = (completed.stdout or "") + (completed.stderr or "")
    return WinGetInstallResult(
        exit_code=int(completed.returncode),
        timed_out=False,
        output_excerpt=output[-MAX_OUTPUT_CHARS:],
    )
