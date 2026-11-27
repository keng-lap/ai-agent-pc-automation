"""Runtime privilege guard for the local Backend / Agent process.

The Backend and in-process Agent must remain non-elevated. This module verifies
the effective process token and fails closed when its elevation state cannot
be inspected.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class BackendPrivilegeError(RuntimeError):
    """The Backend cannot prove that its effective process token is non-elevated."""


_TOKEN_QUERY = 0x0008
_TOKEN_ELEVATION = 20


class _TokenElevation(ctypes.Structure):
    _fields_ = [("TokenIsElevated", wintypes.DWORD)]


def is_current_process_elevated() -> bool:
    """Return the effective Windows TokenElevation flag.

    Non-Windows platforms have no Windows UAC token and return False. On
    Windows, API or token-query failures raise BackendPrivilegeError rather
    than silently allowing the Backend to run.
    """
    if os.name != "nt":
        return False

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    open_process_token = advapi32.OpenProcessToken
    open_process_token.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    open_process_token.restype = wintypes.BOOL

    get_token_information = advapi32.GetTokenInformation
    get_token_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_token_information.restype = wintypes.BOOL

    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    if not open_process_token(kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        raise BackendPrivilegeError(
            f"Backend process token could not be opened (Windows error {ctypes.get_last_error()})"
        )

    try:
        elevation = _TokenElevation()
        returned = wintypes.DWORD()
        if not get_token_information(
            token,
            _TOKEN_ELEVATION,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(returned),
        ):
            raise BackendPrivilegeError(
                "Backend elevation state could not be verified "
                f"(Windows error {ctypes.get_last_error()})"
            )
        if returned.value < ctypes.sizeof(elevation):
            raise BackendPrivilegeError(
                "Windows returned an incomplete process-token elevation record"
            )
        return bool(elevation.TokenIsElevated)
    finally:
        if not close_handle(token):
            raise BackendPrivilegeError(
                "Backend process token handle could not be closed "
                f"(Windows error {ctypes.get_last_error()})"
            )


def enforce_backend_not_elevated() -> None:
    """Fail startup if the Backend / in-process Agent has an elevated token."""
    if is_current_process_elevated():
        raise BackendPrivilegeError(
            "Backend/Agent must run unelevated. No backend or in-process "
            "agent elevation is permitted."
        )
