"""Run the local, authenticated Runtime Diagnostics publisher asynchronously."""

from __future__ import annotations

import re
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

_lock = threading.RLock()
_state: dict[str, Any] = {
    "status": "idle",
    "run_id": None,
    "reason": None,
    "url": None,
    "error_code": None,
}
_publisher_thread: threading.Thread | None = None
_URL_PATTERN = re.compile(r"LOG PUSHED: (https://github\\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/tree/diagnostics/runtime-logs/runs/[A-Za-z0-9_.-]+)")


def get_publish_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def _run_publisher(run_id: str) -> None:
    global _publisher_thread
    script = REPO_ROOT / "scripts" / "publish-runtime-diagnostics.ps1"
    try:
        if not script.is_file():
            raise FileNotFoundError("publisher_script_missing")
        completed = subprocess.run(
            [
                "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-RepoRoot", str(REPO_ROOT),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        output = completed.stdout or ""
        match = _URL_PATTERN.search(output)
        if completed.returncode == 0 and match:
            with _lock:
                _state.update(status="succeeded", url=match.group(1), error_code=None)
        else:
            with _lock:
                _state.update(
                    status="failed",
                    url=None,
                    error_code="no_events" if "No diagnostic events" in (completed.stderr or "") else "publish_failed",
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
