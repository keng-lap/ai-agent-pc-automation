"""Export sanitized runtime diagnostic events for explicit GitHub publishing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src" / "backend"))

from agent_backend.config import load_settings  # noqa: E402
from agent_backend.runtime_diagnostics import RuntimeDiagnosticsStore  # noqa: E402

ALLOWED_FIELDS = {
    "status_code",
    "duration_ms",
    "route",
    "method",
    "candidate_count",
    "available_version_count",
    "official_version",
    "response_bytes",
    "provider_error_code",
    "publisher_verification",
    "exception_type",
    "stack",
}


def sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Apply a second allowlist pass before any event leaves the local machine."""
    fields = event.get("fields")
    safe_fields = {
        key: value
        for key, value in fields.items()
        if key in ALLOWED_FIELDS
        and isinstance(value, (str, int, float, bool))
    } if isinstance(fields, dict) else {}
    return {
        "timestamp": str(event.get("timestamp", ""))[:40],
        "severity": event.get("severity") if event.get("severity") in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO",
        "event_code": str(event.get("event_code", "UNKNOWN"))[:64],
        "component": str(event.get("component", "unknown"))[:64],
        "stage": str(event.get("stage", "unknown"))[:64],
        "correlation_id": str(event.get("correlation_id", ""))[:36],
        "workflow_id": str(event.get("workflow_id", ""))[:36],
        "fields": safe_fields,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 20000:
        parser.error("--limit must be between 1 and 20000")

    settings = load_settings()
    job_directory = Path(settings.job_store_path).parent
    diagnostics_database = job_directory.with_name(
        job_directory.name + "-Diagnostics"
    ) / "runtime.sqlite3"
    if not diagnostics_database.is_file():
        print("No runtime diagnostics database exists.", file=sys.stderr)
        return 2

    store = RuntimeDiagnosticsStore(diagnostics_database)
    events = [sanitize_event(event) for event in store.export_recent(args.limit)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        for event in events:
            output.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
    print(f"Exported {len(events)} sanitized diagnostic events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
