"""Runtime-toggleable, privacy-conscious diagnostics primitives."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .platform_storage import create_platform_secure_storage

logger = logging.getLogger("agent_backend.runtime_diagnostics")
_lock = threading.RLock()
_enabled = False
_store_lock = threading.RLock()
_store: RuntimeDiagnosticsStore | None = None



class RuntimeDiagnosticsStore:
    """Append-only bounded event store protected by the platform storage adapter."""

    def __init__(self, path: Path) -> None:
        self._lock = threading.RLock()
        self._path = path
        self._protection = create_platform_secure_storage().protect_database(path)
        self._lease = self._protection.__enter__()
        try:
            self._connection = sqlite3.connect(path, check_same_thread=False)
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostic_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    event_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_diagnostic_correlation "
                "ON diagnostic_events(correlation_id, sequence)"
            )
            self._connection.commit()
            self._lease.verify()
        except Exception:
            self._protection.__exit__(*__import__("sys").exc_info())
            raise

    def append(self, record: dict[str, Any]) -> None:
        serialized = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        with self._lock:
            self._lease.verify()
            self._connection.execute(
                "INSERT INTO diagnostic_events(occurred_at, correlation_id, event_json) VALUES (?, ?, ?)",
                (record["timestamp"], record["correlation_id"], serialized),
            )
            self._connection.execute(
                "DELETE FROM diagnostic_events WHERE sequence NOT IN "
                "(SELECT sequence FROM diagnostic_events ORDER BY sequence DESC LIMIT 20000)"
            )
            self._connection.commit()
            self._lease.verify()

    def export_recent(self, limit: int = 5000) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 20000))
        with self._lock:
            self._lease.verify()
            rows = self._connection.execute(
                "SELECT event_json FROM diagnostic_events ORDER BY sequence DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
            self._protection.__exit__(None, None, None)


def configure_store(path: Path) -> None:
    """Configure persistent diagnostics storage without making app startup fatal."""
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
            _store = None
        try:
            _store = RuntimeDiagnosticsStore(path)
        except Exception as exc:
            logger.warning(
                "Runtime diagnostics persistence unavailable error_type=%s",
                type(exc).__name__,
            )


def close_store() -> None:
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
            _store = None


def is_enabled() -> bool:
    with _lock:
        return _enabled


def set_enabled(enabled: bool) -> bool:
    global _enabled
    with _lock:
        _enabled = bool(enabled)
        return _enabled


def correlation_id(candidate: str | None = None) -> str:
    """Accept only UUID correlation IDs; otherwise create a server-owned ID."""
    if candidate:
        try:
            return str(UUID(candidate))
        except (ValueError, TypeError, AttributeError):
            pass
    return str(uuid4())


def emit_event(
    *,
    event_code: str,
    component: str,
    stage: str,
    correlation: str,
    severity: str = "INFO",
    fields: dict[str, Any] | None = None,
) -> None:
    """Write bounded structured details only while diagnostics are enabled."""
    if not is_enabled():
        return
    safe_fields: dict[str, Any] = {}
    for key, value in (fields or {}).items():
        normalized_key = key.casefold().replace("-", "_")
        sensitive_markers = ("authorization", "cookie", "password", "token", "api_key", "secret", "totp", "body")
        if any(marker in normalized_key for marker in sensitive_markers):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe_fields[key[:64]] = str(value)[:256] if isinstance(value, str) else value
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity if severity in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO",
        "event_code": event_code[:64],
        "component": component[:64],
        "stage": stage[:64],
        "correlation_id": correlation[:36],
        "fields": safe_fields,
    }
    serialized = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
    logger.log(getattr(logging, record["severity"]), "%s", serialized)
    with _store_lock:
        if _store is not None:
            try:
                _store.append(record)
            except Exception as exc:
                logger.error(
                    "Runtime diagnostics persistence failed error_type=%s",
                    type(exc).__name__,
                )


def emit_exception(
    *,
    event_code: str,
    component: str,
    stage: str,
    correlation: str,
    error: BaseException,
    severity: str = "ERROR",
    fields: dict[str, Any] | None = None,
) -> None:
    """Record exception type and bounded frame locations, never exception text."""
    frames = traceback.extract_tb(error.__traceback__)
    safe_stack = " | ".join(
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        for frame in frames[-12:]
    )
    safe_fields = dict(fields or {})
    safe_fields["exception_type"] = type(error).__name__
    safe_fields["stack"] = safe_stack
    emit_event(
        event_code=event_code,
        component=component,
        stage=stage,
        correlation=correlation,
        severity=severity,
        fields=safe_fields,
    )
