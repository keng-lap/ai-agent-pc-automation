"""Run the local, authenticated Runtime Diagnostics publisher asynchronously."""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import threading
import uuid
from typing import Any

from .config import REPO_ROOT
from .process_containment import WindowsJobObject

_lock = threading.RLock()
_state: dict[str, Any] = {
    "status": "idle",
    "run_id": None,
    "reason": None,
    "url": None,
    "error_code": None,
}
_publisher_thread: threading.Thread | None = None
_URL_PATTERN = re.compile(
    r"LOG PUSHED: (https://github\.com/"
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/tree/diagnostics/runtime-logs/runs/"
    r"[A-Za-z0-9_.-]+)"
)


def get_publish_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def _run_publisher(run_id: str) -> None:
    global _publisher_thread
    script = REPO_ROOT / "scripts" / "publish-runtime-diagnostics.ps1"
    try:
        if not script.is_file():
            raise FileNotFoundError("publisher_script_missing")
        process_environment = os.environ.copy()
        process_environment["GIT_TERMINAL_PROMPT"] = "0"
        process_environment["GCM_INTERACTIVE"] = "never"
        command = [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-RepoRoot", str(REPO_ROOT), "-RunId", run_id,
        ]
        # Start suspended, assign to a kill-on-close Job Object, then resume.
        # This prevents Git descendants from escaping the timeout boundary.
        with WindowsJobObject() as job:
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=process_environment,
                creationflags=0x00000004,  # CREATE_SUSPENDED
            )
            try:
                job.assign_suspended_process(int(process._handle))
                ntdll = ctypes.WinDLL("ntdll")
                resume_process = ntdll.NtResumeProcess
                resume_process.argtypes = [ctypes.c_void_p]
                resume_process.restype = ctypes.c_long
                if resume_process(int(process._handle)) != 0:
                    raise RuntimeError("publisher_process_resume_failed")
                try:
                    stdout, stderr = process.communicate(timeout=180)
                except subprocess.TimeoutExpired:
                    job.terminate()
                    try:
                        stdout, stderr = process.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        stdout, stderr = process.communicate()
                    job.wait_for_empty(timeout_ms=10_000)
                    raise
                job.wait_for_empty(timeout_ms=10_000)
            except Exception:
                if process.poll() is None:
                    job.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                raise
        output = stdout or ""
        match = _URL_PATTERN.search(output)
        if process.returncode == 0 and match:
            with _lock:
                _state.update(status="succeeded", url=match.group(1), error_code=None)
        else:
            with _lock:
                _state.update(
                    status="failed",
                    url=None,
                    error_code="no_events" if "No diagnostic events" in (stderr or "") else "publish_failed",
                )
    except subprocess.TimeoutExpired:
        with _lock:
            _state.update(status="failed", url=None, error_code="publish_timeout")
    except FileNotFoundError:
        with _lock:
            _state.update(status="failed", url=None, error_code="publisher_unavailable")
    except Exception:  # noqa: BLE001 - never expose process details or secrets to the browser
        with _lock:
            _state.update(status="failed", url=None, error_code="publish_failed")
    finally:
        with _lock:
            _publisher_thread = None


def start_publish(reason: str = "manual") -> dict[str, Any]:
    global _publisher_thread
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        run_id = str(uuid.uuid4())
        _state.update(
            status="running",
            run_id=run_id,
            reason=reason if reason in {"manual", "diagnostics_disabled", "retry"} else "manual",
            url=None,
            error_code=None,
        )
        _publisher_thread = threading.Thread(
            target=_run_publisher,
            args=(run_id,),
            name="runtime-diagnostics-publisher",
            daemon=True,
        )
        _publisher_thread.start()
        return dict(_state)
