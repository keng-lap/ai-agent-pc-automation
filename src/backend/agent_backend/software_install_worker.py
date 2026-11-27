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
from agent_backend.runtime_diagnostics import (
    emit_event,
    emit_exception,
    reset_workflow_context,
    set_workflow_context,
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


class _CombinedCancellationSignal:
    """Expose shutdown and lease loss as one executor cancellation signal."""

    def __init__(self, *events: threading.Event) -> None:
        self._events = events

    def is_set(self) -> bool:
        return any(event.is_set() for event in self._events)

    def wait(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while not self.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return True


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
    # WinGet localizes table headers (for example, "Nom ID Version" on
    # French systems). Identify data rows by exact package-ID tokens instead
    # of requiring English column labels.
    for line in lines:
        if len(line.split()) < 3:
            continue
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
        workflow_token = set_workflow_context(job.workflow_id)
        emit_event(
            event_code="INSTALL_WORKER_CLAIMED",
            component="install_worker",
            stage="queue_claim",
            correlation=job.correlation_id,
            fields={"plan_id": job.plan_id, "reservation_id": job.reservation_id},
        )
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
            emit_event(
                event_code="INSTALL_PRECHECK_STARTED",
                component="install_worker",
                stage="pre_install_verification",
                correlation=job.correlation_id,
                fields={"plan_id": job.plan_id, "reservation_id": job.reservation_id},
            )
            before = self._verifier(binding.evidence.package_id, binding.evidence.version)
            emit_event(
                event_code="INSTALL_PRECHECK_COMPLETED",
                component="install_worker",
                stage="pre_install_verification",
                correlation=job.correlation_id,
                fields={
                    "plan_id": job.plan_id,
                    "reservation_id": job.reservation_id,
                    "result": "ambiguous" if before is None else "already_present" if before else "not_present",
                },
            )
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

            emit_event(
                event_code="INSTALLER_PREPARATION_STARTED",
                component="install_worker",
                stage="installer_preparation",
                correlation=job.correlation_id,
                fields={"plan_id": job.plan_id, "reservation_id": job.reservation_id},
            )
            prepared = prepare_approved_install(binding, work_root=self._work_root)
            emit_event(
                event_code="INSTALLER_PREPARATION_COMPLETED",
                component="install_worker",
                stage="installer_preparation",
                correlation=job.correlation_id,
                fields={"plan_id": job.plan_id, "reservation_id": job.reservation_id},
            )
            if self._stop_event.is_set() or lease_lost.is_set():
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "WORKER_CANCELLED_BEFORE_EXECUTION"
                ) or job
            try:
                self._store.consume_real_install_release_authorization(
                    task_id="P6-609-C",
                    owner_id=job.owner_id,
                    plan_id=job.plan_id,
                    package_id=binding.evidence.package_id,
                    version=binding.evidence.version,
                    action_digest=binding.approval_digest,
                )
            except (ApprovalReservationConflict, ApprovalReservationExpired):
                emit_event(
                    event_code="REAL_INSTALL_RELEASE_AUTHORIZATION_DENIED",
                    component="install_worker",
                    stage="release_authorization",
                    correlation=job.correlation_id,
                    severity="WARNING",
                    fields={
                        "plan_id": job.plan_id,
                        "reservation_id": job.reservation_id,
                        "package_id": binding.evidence.package_id,
                        "version": binding.evidence.version,
                        "failure_code": "RELEASE_AUTHORIZATION_DENIED",
                    },
                )
                return self._transition(
                    job, token, version, version_lock, "FAILED", "RELEASE_AUTHORIZATION_DENIED"
                ) or job
            except ApprovalReservationError:
                emit_event(
                    event_code="REAL_INSTALL_RELEASE_AUTHORIZATION_DENIED",
                    component="install_worker",
                    stage="release_authorization",
                    correlation=job.correlation_id,
                    severity="ERROR",
                    fields={
                        "plan_id": job.plan_id,
                        "reservation_id": job.reservation_id,
                        "package_id": binding.evidence.package_id,
                        "version": binding.evidence.version,
                        "failure_code": "RELEASE_AUTHORIZATION_UNAVAILABLE",
                    },
                )
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "RELEASE_AUTHORIZATION_UNAVAILABLE"
                ) or job
            emit_event(
                event_code="REAL_INSTALL_RELEASE_AUTHORIZATION_CONSUMED",
                component="install_worker",
                stage="release_authorization",
                correlation=job.correlation_id,
                fields={
                    "plan_id": job.plan_id,
                    "reservation_id": job.reservation_id,
                    "package_id": binding.evidence.package_id,
                    "version": binding.evidence.version,
                    "binding": "exact_package_version_action_digest",
                },
            )
            emit_event(
                event_code="WINGET_EXECUTION_STARTED",
                component="install_worker",
                stage="winget_execution",
                correlation=job.correlation_id,
                fields={
                    "plan_id": job.plan_id,
                    "reservation_id": job.reservation_id,
                    "package_id": binding.evidence.package_id,
                    "version": binding.evidence.version,
                    "scope": binding.evidence.scope,
                },
            )
            result = self._executor(
                binding,
                prepared,
                work_root=self._work_root,
                timeout_seconds=900,
                cancel_event=_CombinedCancellationSignal(self._stop_event, lease_lost),
            )
            emit_event(
                event_code="WINGET_EXECUTION_COMPLETED",
                component="install_worker",
                stage="winget_execution",
                correlation=job.correlation_id,
                severity="WARNING" if result.exit_code != 0 or result.timed_out else "INFO",
                fields={
                    "plan_id": job.plan_id,
                    "reservation_id": job.reservation_id,
                    "exit_code": result.exit_code,
                    "timed_out": bool(result.timed_out),
                    "cancelled": bool(getattr(result, "cancelled", False) or lease_lost.is_set()),
                },
            )
            if getattr(result, "cancelled", False) or lease_lost.is_set():
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "WORKER_CANCELLED_PROCESS_TERMINATED"
                ) or job
            if result.timed_out:
                return self._transition(
                    job, token, version, version_lock, "UNKNOWN", "WINGET_TIMEOUT"
                ) or job
            # A nonzero WinGet exit code is not proof that the installer did
            # nothing. Verify the exact approved package/version before deciding
            # the outcome; never retry the install from this worker.
            nonzero_exit = result.exit_code != 0
            verifying = self._transition(
                job, token, version, version_lock, "VERIFYING", None
            )
            if verifying is None:
                return job
            emit_event(
                event_code="POST_INSTALL_VERIFICATION_STARTED",
                component="install_worker",
                stage="post_install_verification",
                correlation=job.correlation_id,
                fields={"plan_id": job.plan_id, "reservation_id": job.reservation_id},
            )
            verified = self._verifier(binding.evidence.package_id, binding.evidence.version)
            emit_event(
                event_code="POST_INSTALL_VERIFICATION_COMPLETED",
                component="install_worker",
                stage="post_install_verification",
                correlation=job.correlation_id,
                severity="INFO" if verified is True else "WARNING",
                fields={
                    "plan_id": job.plan_id,
                    "reservation_id": job.reservation_id,
                    "result": "verified" if verified is True else "not_confirmed" if verified is False else "ambiguous",
                },
            )
            if verified is True:
                return self._transition(
                    job,
                    token,
                    version,
                    version_lock,
                    "SUCCEEDED",
                    "PACKAGE_VERSION_VERIFIED_AFTER_NONZERO_EXIT" if nonzero_exit else "PACKAGE_VERSION_VERIFIED",
                ) or job
            if nonzero_exit and verified is False:
                failure_code = "WINGET_NONZERO_EXIT"
            else:
                failure_code = (
                    "POST_INSTALL_VERIFICATION_AMBIGUOUS"
                    if verified is None
                    else "PACKAGE_VERSION_NOT_CONFIRMED"
                )
            return self._transition(
                job, token, version, version_lock, "UNKNOWN", failure_code
            ) or job
        except (ValueError, TypeError, WinGetAdapterError):
            return self._transition(
                job, token, version, version_lock, "FAILED", "INVALID_APPROVED_PAYLOAD"
            ) or job
        except (OSError, WinGetExecutionError, ApprovalReservationError):
            return self._transition(
                job, token, version, version_lock, "UNKNOWN", "EXECUTION_OUTCOME_AMBIGUOUS"
            ) or job
        except Exception as exc:  # noqa: BLE001 - record unexpected worker failures without leaking messages
            emit_exception(
                event_code="INSTALL_WORKER_UNEXPECTED_FAILURE",
                component="install_worker",
                stage="install_lifecycle",
                correlation=job.correlation_id,
                error=exc,
                fields={"plan_id": job.plan_id, "reservation_id": job.reservation_id},
            )
            return self._transition(
                job, token, version, version_lock, "UNKNOWN", "WORKER_UNEXPECTED_FAILURE"
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
            reset_workflow_context(workflow_token)

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
            emit_event(
                event_code="INSTALL_JOB_STATE_CHANGED",
                component="install_worker",
                stage="install_lifecycle",
                correlation=job.correlation_id,
                severity="WARNING" if target in {"FAILED", "UNKNOWN"} else "INFO",
                fields={
                    "plan_id": job.plan_id,
                    "reservation_id": job.reservation_id,
                    "state": target,
                    "result_code": result_code,
                },
            )
            return updated
