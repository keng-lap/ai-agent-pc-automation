# P6-602 — Read-only Job Status API Contract

## Purpose

This contract connects the Frontend Job Monitor to backend-owned operational job records. It replaces the previous hard-coded demonstration runs. The Frontend must never synthesize a job, progress percentage, success result, process identifier, or installer log.

This is a read-only status surface. It does not start, retry, approve, cancel, or otherwise mutate a job.

## Endpoint

`GET /api/jobs?limit=25`

- Requires the same authenticated local session as other protected application APIs.
- Returns only jobs owned by the authenticated principal.
- A missing job belonging to another owner must not be distinguishable from an unknown job.
- `limit` is an integer from 1 through 25; the server applies a safe default and maximum.
- The endpoint must not cause worker dispatch, resume a process, retry a job, or consume an approval.
- The response is bounded. The server returns at most 25 jobs and at most 20 recent events per job.

## Response

```json
{
  "checked_at": "2026-11-13T09:45:00Z",
  "jobs": [
    {
      "job_id": "server-generated-id",
      "tool_id": "software.install",
      "state": "RUNNING",
      "created_at": "2026-11-13T09:40:00Z",
      "started_at": "2026-11-13T09:40:02Z",
      "finished_at": null,
      "progress_message": "กำลังติดตั้งแพ็กเกจที่ได้รับอนุมัติ",
      "result_code": null,
      "reboot_required": false,
      "recent_events": [
        {
          "sequence": 3,
          "occurred_at": "2026-11-13T09:42:00Z",
          "state": "RUNNING",
          "level": "INFO",
          "message": "Process started inside containment"
        }
      ]
    }
  ]
}
```

### Field constraints

- `job_id`: server-generated opaque identifier; never a client-selected path or executable identifier.
- `tool_id`: fixed backend catalog identifier, not a handler name or command.
- `state`: one of `QUEUED`, `STARTING`, `RUNNING`, `VERIFYING`, `REBOOT_REQUIRED`, `CANCEL_REQUESTED`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `UNKNOWN`.
- Timestamps are UTC ISO-8601 strings. `started_at` and `finished_at` may be null.
- `progress_message`: nullable, normalized, redacted, bounded to 160 characters. It is descriptive only; no fabricated percentage is returned.
- `result_code`: nullable normalized code. Never expose raw command lines or arbitrary process output.
- `reboot_required`: boolean.
- `recent_events`: bounded newest-first or oldest-first (the server must document one order consistently); each message is redacted and bounded to 240 characters.
- Event `level` is one of `INFO`, `WARN`, `ERROR`.

## Persistence and platform security boundary

- The backend stores operational records and bounded event summaries in local SQLite using WAL, foreign keys, full synchronous commits, transaction boundaries, owner-scoped idempotency, and version-checked state changes.
- POSIX development/test storage requires a private state directory (0700) and database file (0600), and rejects symlink paths.
- Windows storage intentionally returns unavailable until native DACL, owner SID, reparse-point and handle/path-race protections are implemented and independently reviewed. Do not bypass this guard.
- The API does not yet have a producer connected to the approved plan flow; no worker, approval consumption, WinGet, or installer dispatch is implemented.

## Error behavior

- `401`: no valid authenticated session.
- `503`: authentication or required job-status service is not configured; fail closed.
- `422`: invalid limit.
- Backend storage or integrity failures must not be converted into an empty successful list. Return a non-success response and log the internal diagnostic without exposing sensitive details.

The Frontend polls every five seconds. A failed poll displays an unavailable state and retains no fabricated or stale “success” status. A successful poll replaces the visible snapshot. Polling is read-only and cannot affect execution.

## Frontend behavior

- Active view includes `QUEUED`, `STARTING`, `RUNNING`, `VERIFYING`, `REBOOT_REQUIRED`, and `CANCEL_REQUESTED`.
- History view includes `SUCCEEDED`, `FAILED`, `CANCELLED`, and `UNKNOWN`.
- Display Job ID, tool, state, timestamps, bounded progress message, normalized result code, reboot requirement, and bounded recent events.
- `UNKNOWN` is a warning state. Never offer automatic retry.
- A lost browser connection is not a job failure and must not trigger cancellation.
- Cancellation controls are intentionally absent until the backend can prove complete process-tree termination and exposes an independently reviewed owner-bound cancellation endpoint.

## Current implementation boundary

This PR adds the Frontend client contract and live read-only monitor only. The backend endpoint and durable job store are not implemented by this change. Until that endpoint is delivered, the UI explicitly shows that the API is unavailable and displays no mock jobs.

No worker, WinGet process, installer, or machine-changing action is enabled by this contract.
