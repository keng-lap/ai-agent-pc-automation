"""Bounded real WinGet execution for an immutable, approved install (P6-609).

This module is intentionally not an HTTP endpoint or a generic command runner.
It accepts only the backend's exact approval binding and a prepared local
manifest, invokes the fixed per-user WinGet alias without a shell, and places
the suspended process in a kill-on-close Job Object before it can run.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
import subprocess

from agent_backend.process_containment import (
    ProcessContainmentError,
    WindowsJobObject,
)
from agent_backend.software_approval import InstallApprovalBinding
from agent_backend.winget_adapter import (
    PreparedWinGetInstall,
    WinGetAdapterError,
    lock_prepared_manifest,
)

_CREATE_SUSPENDED = 0x00000004
_CREATE_NO_WINDOW = 0x08000000
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_WAIT_FAILED = 0xFFFFFFFF
_STILL_ACTIVE = 259
_MAX_TIMEOUT_SECONDS = 1800


class WinGetExecutionError(RuntimeError):
    """The exact approved WinGet operation could not be safely executed."""


@dataclass(frozen=True, slots=True)
class WinGetExecutionResult:
    """Minimal execution result; no installer output or secrets are retained."""

    executable: str
    package_id: str
    version: str
    approval_digest: str
    exit_code: int | None
    timed_out: bool


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _winget_alias_path(*, environ=None) -> Path:
    """Resolve only the current user's packaged WinGet execution alias."""
    env = os.environ if environ is None else environ
    local_app_data = env.get("LOCALAPPDATA")
    if not isinstance(local_app_data, str) or not local_app_data.strip():
        raise WinGetExecutionError("per-user WinGet alias is unavailable")
    root = Path(local_app_data)
    if not root.is_absolute() or root.is_symlink():
        raise WinGetExecutionError("per-user WinGet alias path is unsafe")
    expected = root / "Microsoft" / "WindowsApps" / "winget.exe"
    try:
        if not expected.is_file() or expected.is_dir():
            raise WinGetExecutionError("WinGet is not installed for the current user")
    except OSError:
        raise WinGetExecutionError("WinGet alias could not be verified") from None
    return expected


def execute_approved_winget_install(
    binding: InstallApprovalBinding,
    prepared: PreparedWinGetInstall,
    *,
    work_root: Path,
    timeout_seconds: int = 900,
) -> WinGetExecutionResult:
    """Invoke WinGet for one exact approved manifest, with suspended containment.

    This function is Windows-only. It never invokes cmd.exe, PowerShell, PATH
    search, or a caller-supplied executable/argument string. A timeout kills
    the entire contained process tree; callers must reconcile installed state
    before any later retry.
    """
    if os.name != "nt":
        raise WinGetExecutionError("real WinGet execution is available only on Windows")
    if not isinstance(binding, InstallApprovalBinding):
        raise TypeError("an immutable install approval binding is required")
    if not isinstance(prepared, PreparedWinGetInstall):
        raise TypeError("a prepared WinGet install is required")
    if (
        type(timeout_seconds) is not int
        or not 1 <= timeout_seconds <= _MAX_TIMEOUT_SECONDS
    ):
        raise ValueError("timeout_seconds must be between 1 and 1800")

    executable = _winget_alias_path()
    try:
        with lock_prepared_manifest(binding, prepared, work_root=work_root) as arguments:
            # list2cmdline performs Windows argv quoting; CreateProcess receives
            # the fixed executable separately and no shell is involved.
            command_line = subprocess.list2cmdline([str(executable), *arguments])
            startup = _StartupInfo()
            startup.cb = ctypes.sizeof(_StartupInfo)
            process_info = _ProcessInformation()

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_process = kernel32.CreateProcessW
            create_process.argtypes = [
                wintypes.LPCWSTR,
                wintypes.LPWSTR,
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.BOOL,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.LPCWSTR,
                ctypes.POINTER(_StartupInfo),
                ctypes.POINTER(_ProcessInformation),
            ]
            create_process.restype = wintypes.BOOL
            resume_thread = kernel32.ResumeThread
            resume_thread.argtypes = [wintypes.HANDLE]
            resume_thread.restype = wintypes.DWORD
            wait_for_single_object = kernel32.WaitForSingleObject
            wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            wait_for_single_object.restype = wintypes.DWORD
            get_exit_code = kernel32.GetExitCodeProcess
            get_exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            get_exit_code.restype = wintypes.BOOL
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL

            mutable_command_line = ctypes.create_unicode_buffer(command_line)
            created = create_process(
                str(executable),
                mutable_command_line,
                None,
                None,
                False,
                _CREATE_SUSPENDED | _CREATE_NO_WINDOW,
                None,
                str(Path(work_root)),
                ctypes.byref(startup),
                ctypes.byref(process_info),
            )
            if not created:
                raise WinGetExecutionError(
                    f"WinGet process creation failed (Windows error {ctypes.get_last_error()})"
                )

            job = None
            try:
                job = WindowsJobObject()
                job.assign_suspended_process(int(process_info.hProcess))
                resumed = resume_thread(process_info.hThread)
                if resumed == 0xFFFFFFFF:
                    raise WinGetExecutionError(
                        f"WinGet process could not be resumed (Windows error {ctypes.get_last_error()})"
                    )

                wait_result = wait_for_single_object(
                    process_info.hProcess,
                    timeout_seconds * 1000,
                )
                if wait_result == _WAIT_TIMEOUT:
                    job.terminate(1)
                    wait_for_single_object(process_info.hProcess, 5000)
                    return WinGetExecutionResult(
                        executable=str(executable),
                        package_id=binding.evidence.package_id,
                        version=binding.evidence.version,
                        approval_digest=binding.approval_digest,
                        exit_code=None,
                        timed_out=True,
                    )
                if wait_result == _WAIT_FAILED:
                    raise WinGetExecutionError(
                        f"WinGet wait failed (Windows error {ctypes.get_last_error()})"
                    )
                if wait_result != _WAIT_OBJECT_0:
                    raise WinGetExecutionError("WinGet returned an unexpected wait status")

                exit_code = wintypes.DWORD()
                if not get_exit_code(process_info.hProcess, ctypes.byref(exit_code)):
                    raise WinGetExecutionError(
                        f"WinGet exit status could not be read (Windows error {ctypes.get_last_error()})"
                    )
                if exit_code.value == _STILL_ACTIVE:
                    raise WinGetExecutionError("WinGet process remained active after signalled exit")
                return WinGetExecutionResult(
                    executable=str(executable),
                    package_id=binding.evidence.package_id,
                    version=binding.evidence.version,
                    approval_digest=binding.approval_digest,
                    exit_code=int(exit_code.value),
                    timed_out=False,
                )
            except (ProcessContainmentError, OSError) as exc:
                if job is not None and job.is_open:
                    try:
                        job.terminate(1)
                    except ProcessContainmentError:
                        pass
                raise WinGetExecutionError("WinGet process containment failed; install was stopped") from exc
            finally:
                if job is not None:
                    job.close()
                close_handle(process_info.hThread)
                close_handle(process_info.hProcess)
    except WinGetAdapterError as exc:
        raise WinGetExecutionError("approved WinGet manifest could not be verified") from exc
