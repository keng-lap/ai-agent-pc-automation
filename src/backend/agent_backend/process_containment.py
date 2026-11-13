"""Windows Job Object containment primitives (P6-602).

The caller must create a process in a suspended state, assign its process
handle to this Job Object, and only then resume its primary thread. This module
does not create processes and is not wired to any application dispatch path.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Self


class ProcessContainmentError(RuntimeError):
    """A Windows process could not be contained safely."""


# Windows Job Object constants.
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
_ERROR_INVALID_PARAMETER = 87


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsJobObject:
    """Owns a kill-on-close Job Object and accepts only suspended processes."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise ProcessContainmentError("Windows Job Objects are available only on Windows")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_api()
        handle = self._kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise self._last_error("CreateJobObjectW failed")
        self._handle = handle
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | _JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        )
        if not self._kernel32.SetInformationJobObject(
            self._handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = self._last_error("SetInformationJobObject failed")
            self.close()
            raise error

    def _configure_api(self) -> None:
        self._kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._kernel32.TerminateJobObject.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    @staticmethod
    def _last_error(message: str) -> ProcessContainmentError:
        code = ctypes.get_last_error()
        return ProcessContainmentError(f"{message} (Windows error {code})")

    @property
    def is_open(self) -> bool:
        return self._handle is not None

    def assign_suspended_process(self, process_handle: int) -> None:
        """Assign a process before its primary thread is resumed.

        The caller is responsible for creating the process with CREATE_SUSPENDED
        and for not resuming it until this method returns successfully.
        """
        if not self.is_open:
            raise ProcessContainmentError("Job Object is closed")
        if type(process_handle) is not int or process_handle <= 0:
            raise ValueError("a valid native process handle is required")
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise self._last_error("AssignProcessToJobObject failed; process must remain suspended")

    def terminate(self, exit_code: int = 1) -> None:
        if not self.is_open:
            raise ProcessContainmentError("Job Object is closed")
        if type(exit_code) is not int or not 0 <= exit_code <= 0xFFFFFFFF:
            raise ValueError("exit_code must be an unsigned 32-bit integer")
        if not self._kernel32.TerminateJobObject(self._handle, exit_code):
            raise self._last_error("TerminateJobObject failed")

    def close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle is None:
            return
        self._handle = None
        if not self._kernel32.CloseHandle(handle):
            raise self._last_error("CloseHandle failed; contained processes may remain active")

    def __enter__(self) -> Self:
        if not self.is_open:
            raise ProcessContainmentError("Job Object is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
