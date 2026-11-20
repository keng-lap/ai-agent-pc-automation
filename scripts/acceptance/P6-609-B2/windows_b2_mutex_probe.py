"""Manual two-session probe for the B2 Windows global mutex.

This exercises the production WindowsSecureStorage protection lease without
opening SQLite or performing installation operations. It is NOT read-only:
protect_database() creates persistent directories, a database file, and
sidecar files. Use only the dedicated acceptance directory supplied by the
PowerShell runner, never the application's live state directory.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from agent_backend.platform_storage import (
    PlatformStorageUnavailable,
    WindowsSecureStorage,
)


def _session_id() -> int:
    session_id = ctypes.c_ulong()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process_id = kernel32.GetCurrentProcessId()
    if not kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(session_id.value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("hold", "probe", "verify"))
    parser.add_argument("--database", required=True, help="Same absolute acceptance database path in both sessions")
    parser.add_argument("--hold-seconds", type=int, default=90)
    args = parser.parse_args()

    if os.name != "nt":
        print("FAIL: this probe must run on Windows.", flush=True)
        return 2
    if args.hold_seconds < 10 or args.hold_seconds > 300:
        print("FAIL: hold-seconds must be between 10 and 300.", flush=True)
        return 2

    database = Path(args.database)
    if not database.is_absolute():
        print("FAIL: database path must be absolute.", flush=True)
        return 2

    adapter = WindowsSecureStorage()
    sid_text = adapter._api()[5].ConvertSidToStringSid(adapter._sid())
    sid_fingerprint = hashlib.sha256(sid_text.encode("utf-8")).hexdigest()[:16]
    session_id = _session_id()

    def timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    if args.mode == "hold":
        try:
            with adapter.protect_database(database):
                print(json.dumps({
                    "result": "LOCK_ACQUIRED",
                    "mode": "hold",
                    "pid": os.getpid(),
                    "windows_session_id": session_id,
                    "user": os.environ.get("USERNAME", ""),
                    "user_sid_sha256": sid_fingerprint,
                    "timestamp_utc": timestamp(),
                    "database": str(database),
                    "hold_seconds": args.hold_seconds,
                    "filesystem_effects": "Creates persistent acceptance directory, database, and sidecar files.",
                }), flush=True)
                time.sleep(args.hold_seconds)
            print(json.dumps({
                "result": "LOCK_RELEASED",
                "pid": os.getpid(),
                "windows_session_id": session_id,
                "user_sid_sha256": sid_fingerprint,
                "timestamp_utc": timestamp(),
            }), flush=True)
            return 0
        except PlatformStorageUnavailable as exc:
            print(f"FAIL: holder could not acquire the production mutex/lease: {exc}", flush=True)
            return 2

    try:
        with adapter.protect_database(database):
            if args.mode == "probe":
                print(
                    "FAIL: second logon session acquired the lease while session A should hold it.",
                    flush=True,
                )
                return 3
            print(json.dumps({
                "result": "PASS_ACQUIRED_AFTER_RELEASE",
                "mode": "verify",
                "pid": os.getpid(),
                "windows_session_id": session_id,
                "user": os.environ.get("USERNAME", ""),
                "user_sid_sha256": sid_fingerprint,
                "timestamp_utc": timestamp(),
                "database": str(database),
            }), flush=True)
            return 0
    except PlatformStorageUnavailable as exc:
        if args.mode == "probe" and "mutex acquisition timed out" in str(exc).lower():
            print(json.dumps({
                "result": "PASS_CONTENTION_BLOCKED",
                "mode": "probe",
                "pid": os.getpid(),
                "windows_session_id": session_id,
                "user": os.environ.get("USERNAME", ""),
                "user_sid_sha256": sid_fingerprint,
                "timestamp_utc": timestamp(),
                "database": str(database),
                "detail": str(exc),
            }), flush=True)
            return 0
        print(f"FAIL: {args.mode} did not meet its expected mutex result: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
