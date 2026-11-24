"""Export sanitized runtime diagnostic events for explicit GitHub publishing."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src" / "backend"))

from agent_backend.config import load_settings
from agent_backend.runtime_diagnostics import RuntimeDiagnosticsStore

ALLOWED_FIELDS = {
    "status_code",
    "upstream_status",
    "failure_code",
    "manifest_listing_item_count",
    "manifest_named_yaml_count",
    "manifest_yaml_file_count",
    "manifest_listing_summary",
    "duration_ms",
    "route",
    "method",
    "candidate_count",
    "available_version_count",
    "available_versions",
    "selectable_version_count",
    "selectable_versions",
    "manifest_version_count",
    "manifest_versions",
    "official_version_count",
    "official_versions",
    "latest_available_version",
    "selected_version",
    "version_limit",
    "version_sort_strategy",
    "package_id",
    "version",
    "architecture",
    "requested_architecture",
    "requested_scope",
    "installer_matching_count",
    "installer_architectures",
    "installer_scopes",
    "official_version",
    "response_bytes",
    "provider_error_code",
    "publisher_verification",
    "exception_type",
    "error_type",
    "stack",
}


def sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Apply a second allowlist pass before any event leaves the local machine."""
    fields = event.get("fields")
    safe_fields = {}
    if isinstance(fields, dict):
        for key, value in fields.items():
            if key not in ALLOWED_FIELDS:
                continue
            if isinstance(value, (str, int, float, bool)) or (
                key in {"available_versions", "official_versions", "manifest_versions", "selectable_versions"}
                and isinstance(value, list)
                and len(value) <= 20
                and all(
                    isinstance(item, str)
                    and len(item) <= 80
                    and item
                    and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+!-]{0,79}", item)
                    for item in value
                )
            ):
                safe_fields[key] = value
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
    parser.add_argument("--session-id", required=True)
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

    if not re.fullmatch(r"[0-9a-f-]{36}", args.session_id):
        parser.error("--session-id must be a capture session UUID")

    store = RuntimeDiagnosticsStore(diagnostics_database)
    events = [
        sanitize_event(event)
        for event in store.export_recent(args.limit)
        if event.get("capture_session_id") == args.session_id
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        for event in events:
            output.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
    print(f"Exported {len(events)} sanitized diagnostic events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
