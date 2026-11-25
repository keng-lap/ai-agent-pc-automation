"""Run the local, authenticated Runtime Diagnostics publisher asynchronously."""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from .config import REPO_ROOT
from .process_containment import WindowsJobObject
from .runtime_diagnostics import current_capture_session_id

_lock = threading.RLock()
_state: dict[str, Any] = {
    "status": "idle",
    "run_id": None,
    "session_id": None,
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


def _cleanup_publisher_artifacts(run_id: str) -> None:
    """Remove deterministic temp/worktree paths after the contained job exits."""
    suffix = run_id.replace("-", "")
    temp_root = Path(tempfile.gettempdir()) / f"ai-agent-diagnostics-{suffix}"
    worktree = Path(tempfile.gettempdir()) / f"ai-agent-diagnostics-worktree-{suffix}"
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "never"

    if worktree.exists():
        removed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "remove", "--force", str(worktree)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            timeout=30,
            env=environment,
            check=False,
        )
        if removed.returncode != 0 and worktree.exists():
            raise RuntimeError("publisher_worktree_cleanup_failed")

    pruned = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "worktree", "prune"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        timeout=30,
        env=environment,
        check=False,
    )
    if pruned.returncode != 0:
        raise RuntimeError("publisher_worktree_prune_failed")

    if temp_root.exists():
        shutil.rmtree(temp_root)


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
            "-SessionId", str(_state.get("session_id") or ""),
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
        try:
            # PowerShell's finally block is bypassed when the Job Object kills
            # the timed-out publisher. Clean deterministic artifacts here,
            # after the contained process tree has exited.
            _cleanup_publisher_artifacts(run_id)
        except Exception:  # noqa: BLE001 - cleanup details stay local
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
        session_id = _state.get("session_id") if reason == "retry" else current_capture_session_id()
        if not session_id:
            _state.update(
                status="failed",
                run_id=str(uuid.uuid4()),
                session_id=None,
                reason=reason if reason in {"manual", "diagnostics_disabled", "retry"} else "manual",
                url=None,
                error_code="no_events",
            )
            return dict(_state)
        _state.update(
            status="running",
            run_id=run_id,
            session_id=session_id,
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
