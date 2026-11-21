"""One-shot local worker for approved WinGet installs (P6-609-C).

The worker consumes only durable, immutable approval payloads. It does not
accept user/model commands, does not retry an install, and treats any
ambiguous post-execution state as UNKNOWN.
"""

from __future__ import annotations

import re
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from agent_backend.approval_reservation_store import (
    ApprovalReservationError,
    InstallExecutionJob,
    SQLiteApprovalReservationStore,
)
from agent_backend.software_approval import InstallApprovalBinding
from agent_backend.winget_adapter import (
    WinGetAdapterError,
    cleanup_prepared_install,
    prepare_approved_install,
)
from agent_backend.winget_execution import (
    WinGetExecutionError,
    _winget_alias_path,
    execute_approved_winget_install,
)

_LEASE_SECONDS = 300
_HEARTBEAT_SECONDS = 30
_VERIFY_TIMEOUT_SECONDS = 45
_WORKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class SoftwareInstallWorkerError(RuntimeError):
    """The worker could not safely process an approved install."""


def verify_exact_user_install(
    package_id: str,
    version: str,
    *,
    timeout_seconds: int = _VERIFY_TIMEOUT_SECONDS,
) -> bool | None:
    """Return True only when WinGet reports the exact package ID and version.

    False means WinGet completed its query but did not report the exact
    requested version. None means verification itself was ambiguous.
    """
    executable = _winget_alias_path()
    try:
        result = subprocess.run(
            [
                str(executable),
                "list",
                "--id",
                package_id,
                "--exact",
                "--scope",
                "user",
                "--disable-interactivity",
                "--accept-source-agreements",
            ],
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    # WinGet's table uses two-or-more spaces between columns. The package ID
    # and version are exact fields; localized column headings are irrelevant.
    for line in (result.stdout or "").splitlines():
        columns = re.split(r"\s{2,}", line.strip())
        if len(columns) >= 3 and columns[1].casefold() == package_id.casefold():
            return columns[2] == version
    return False


class SoftwareInstallWorker:
    """Claims and executes at most one approved install per durable queue row."""

    def __init__(
        self,
        store: SQLiteApprovalReservationStore,
        *,
        work_root: Path,
        worker_id: str | None = None,
        executor: Callable = execute_approved_winget_install,
        verifier: Callable[[str, str], bool | None] = verify_exact_user_install,
        lease_seconds: int = _LEASE_SECONDS,
        heartbeat_seconds: int = _HEARTBEAT_SECONDS,
    ) -> None:
        self._store = store
        self._work_root = Path(work_root)
        self._worker_id = worker_id or f"winget-{uuid.uuid4().hex}"
        if not _WORKER_ID_PATTERN.fullmatch(self._worker_id):
            raise ValueError("worker_id is invalid")
        if type(lease_seconds) is not int or not 30 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 30 and 300")
        if type(heartbeat_seconds) is not int or not 5 <= heartbeat_seconds < lease_seconds:
            raise ValueError("heartbeat_seconds must be below the lease duration")
        self._executor = executor
        self._verifier = verifier
        self._lease_seconds = lease_seconds
        self._heartbeat_seconds = heartbeat_seconds

    def run_once(self) -> InstallExecutionJob | None:
        """Claim and process one queue item; no item returns None."""
        job = self._store.claim_next_install(
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
        )
        if job is None:
            return None
        return self._process(job)

    def _process(self, job: InstallExecutionJob) -> InstallExecutionJob:
        token = job.lease_token
        if not token:
            raise SoftwareInstallWorkerError("claimed install job has no lease token")
        version = {"value": job.version}
        version_lock = threading.Lock()
        stop_heartbeat = threading.Event()
        lease_lost = threading.Event()

        def heartbeat() -> None:
            while not stop_heartbeat.wait(self._heartbeat_seconds):
                try:
                    with version_lock:
                        renewed = self._store.renew_install_lease(
                            job.reservation_id,
                            worker_id=self._worker_id,
                            lease_token=token,
                            expected_version=version["value"],
                            lease_seconds=self._lease_seconds,
                        )
                        version["value"] = renewed.version
                except ApprovalReservationError:
                    lease_lost.set()
                    return

        thread = threading.Thread(
            target=heartbeat,
            name=f"install-lease-{job.reservation_id[:8]}",
            daemon=True,
        )
        thread.start()
        prepared = None
        try:
            binding = InstallApprovalBinding.model_validate_json(job.binding_json)
            if binding.approval_digest != job.action_digest:
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "APPROVAL_BINDING_MISMATCH"
                )
            binding.ensure_fresh(now=datetime.now(UTC))
            running = self._transition(
                job, token, version, version_lock, "RUNNING", None
            )
            if running is None:
                return job
            # Establish the pre-install state first. An already-present exact
            # package satisfies the requested state without launching an installer.
            before = self._verifier(binding.evidence.package_id, binding.evidence.version)
            if before is None:
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "PRE_INSTALL_STATE_AMBIGUOUS"
                ) or job
            if before is True:
                verifying = self._transition(
                    job, token, version, version_lock, "VERIFYING", None
                )
                if verifying is None:
                    return job
                return self._transition(
                    job, token, version, version_lock, "SUCCEEDED", "PACKAGE_ALREADY_PRESENT"
                ) or job

            prepared = prepare_approved_install(binding, work_root=self._work_root)
            if lease_lost.is_set():
                return job
            result = self._executor(
                binding,
                prepared,
                work_root=self._work_root,
                timeout_seconds=900,
            )
            if lease_lost.is_set():
                return job
            if result.timed_out:
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "WINGET_TIMEOUT"
                ) or job
            if result.exit_code != 0:
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "WINGET_NONZERO_EXIT"
                ) or job
            verifying = self._transition(
                job, token, version, version_lock, "VERIFYING", None
            )
            if verifying is None:
                return job
            verified = self._verifier(binding.evidence.package_id, binding.evidence.version)
            if verified is True:
                return self._transition(
                    job, token, version, version_lock, "SUCCEEDED", "PACKAGE_VERSION_VERIFIED"
                ) or job
            return self._transition(
                job,
                token,
                version,
                version_lock,
                "UNKNOWN",
                "POST_INSTALL_VERIFICATION_AMBIGUOUS" if verified is None else "PACKAGE_VERSION_NOT_CONFIRMED",
            ) or job
        except (ValueError, TypeError, WinGetAdapterError):
            return self._transition(
                job, token, version, version_lock, "FAILED", "INVALID_APPROVED_PAYLOAD"
            ) or job
        except (OSError, WinGetExecutionError, ApprovalReservationError):
            return self._transition(
                job, token, version, version_lock, "UNKNOWN", "EXECUTION_OUTCOME_AMBIGUOUS"
            ) or job
        finally:
            stop_heartbeat.set()
            thread.join(timeout=2)
            if prepared is not None:
                try:
                    cleanup_prepared_install(prepared, work_root=self._work_root)
                except (OSError, ValueError, WinGetAdapterError):
                    # The manifest contains only public package metadata; a
                    # cleanup failure is not permission to retry the install.
                    pass

    def _transition(self, job, token, version, version_lock, target, result_code):
        if target == "RUNNING" and job.state != "CLAIMED":
            return None
        with version_lock:
            try:
                updated = self._store.transition_install(
                    job.reservation_id,
                    worker_id=self._worker_id,
                    lease_token=token,
                    expected_version=version["value"],
                    target=target,
                    result_code=result_code,
                )
            except ApprovalReservationError:
                return None
            version["value"] = updated.version
            return updated
