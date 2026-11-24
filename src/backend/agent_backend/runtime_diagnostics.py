"""Runtime-toggleable, privacy-conscious diagnostics primitives."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger("agent_backend.runtime_diagnostics")
_lock = threading.RLock()
_enabled = False


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
    logger.log(
        getattr(logging, record["severity"]),
        "%s",
        json.dumps(record, ensure_ascii=True, separators=(",", ":")),
    )
