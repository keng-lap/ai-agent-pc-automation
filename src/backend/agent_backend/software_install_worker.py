"""One-shot local worker for approved WinGet installs (P6-609-C).

The worker consumes only durable, immutable approval payloads. It does not
accept user/model commands, does not retry an install, and treats any
ambiguous post-execution state as UNKNOWN.
"""

from __future__ import annotations

import re
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from agent_backend.approval_reservation_store import (
    ApprovalReservationConflict,
    ApprovalReservationError,
    ApprovalReservationExpired,
    InstallExecutionJob,
    SQLiteApprovalReservationStore,
)
from agent_backend.config import RealInstallReleaseAuthorization
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
    # WinGet reports an empty exact search with this HRESULT (which may be
    # surfaced as either an unsigned DWORD or its signed 32-bit equivalent).
    if result.returncode in {0x8A150014, -1978335212}:
        return False
    if result.returncode != 0:
        return None

    # Names and column widths are localized/variable. Match the exact package
    # ID token and read the following version token instead of splitting the
    # display table on a fixed number of spaces.
    package_pattern = re.compile(
        rf"(?<!\S){re.escape(package_id)}(?!\S)(?=\s+(\S+))",
        re.IGNORECASE,
    )
    lines = (result.stdout or "").splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"\bName\s+Id\s+Version\b", line, re.IGNORECASE)
        ),
        None,
    )
    if header_index is None:
        return None
    for line in lines[header_index + 1:]:
        matches = list(package_pattern.finditer(line))
        if matches:
            # The display name may itself contain the package ID and a version
            # (for example "Acme.Editor 1.2.3"). The ID column is the final
            # exact ID occurrence in the row; use its following version value.
            return matches[-1].group(1) == version
    # A successful but unparseable/empty table is ambiguous, not proof that
    # the package is absent. Only the explicit no-applications HRESULT means False.
    return None


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
        stop_event: threading.Event | None = None,
        release_authorization: RealInstallReleaseAuthorization | None = None,
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
        self._stop_event = stop_event or threading.Event()
        self._release_authorization = release_authorization

    def run_once(self) -> InstallExecutionJob | None:
        """Claim and process one queue item; no item returns None."""
        if self._stop_event.is_set():
            return None
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
            next_heartbeat = time.monotonic() + self._heartbeat_seconds
            while not stop_heartbeat.wait(0.2):
                if self._stop_event.is_set():
                    lease_lost.set()
                    return
                if time.monotonic() < next_heartbeat:
                    continue
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
                    next_heartbeat = time.monotonic() + self._heartbeat_seconds
                except Exception:  # noqa: BLE001 - any renewal fault invalidates lease ownership
                    # Any unexpected renewal failure means the worker can no
                    # longer prove exclusive ownership. Stop the process rather
                    # than continuing under an unverified lease.
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
            authorization = self._release_authorization
            if (
                authorization is None
                or authorization.task_id != "P6-609-C"
                or authorization.package_id != binding.evidence.package_id
                or authorization.version != binding.evidence.version
            ):
                return self._transition(
                    job, token, version, version_lock, "FAILED", "RELEASE_AUTHORIZATION_DENIED"
                ) or job
            try:
                self._store.consume_real_install_release_authorization(
                    task_id=authorization.task_id,
                    package_id=authorization.package_id,
                    version=authorization.version,
                    action_digest=binding.approval_digest,
                    nonce=authorization.nonce,
                    expires_at=authorization.expires_at,
                )
            except (ApprovalReservationConflict, ApprovalReservationExpired):
                return self._transition(
                    job, token, version, version_lock, "FAILED", "RELEASE_AUTHORIZATION_DENIED"
                ) or job
            except ApprovalReservationError:
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "RELEASE_AUTHORIZATION_UNAVAILABLE"
                ) or job
            if lease_lost.is_set():
                return job
            result = self._executor(
                binding,
                prepared,
                work_root=self._work_root,
                timeout_seconds=900,
                cancel_event=lease_lost,
            )
            if getattr(result, "cancelled", False) or lease_lost.is_set():
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "WORKER_CANCELLED_PROCESS_TERMINATED"
                ) or job
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
            # Do not return while a renewal thread can still mutate lease state.
            # Store operations have bounded SQLite timeouts.
            thread.join()
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
