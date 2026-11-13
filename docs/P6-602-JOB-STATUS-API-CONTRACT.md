# P6-602 — Read-only Job Status API Contract

## Purpose

This contract connects the Frontend Job Monitor to backend-owned operational job records. It replaces the previous hard-coded demonstration runs. The Frontend must never synthesize a job, progress percentage, success result, process identifier, or installer log.

This is a read-only status surface. It does not start, retry, approve, cancel, or otherwise mutate a job. The SQLite store and endpoints are implemented in the current backend PR; no job producer or worker is connected yet, so the API correctly returns an empty list until a separately reviewed producer creates records.

## Endpoint

`GET /api/jobs?limit=25`

- Requires the same authenticated local session as other protected application APIs.
- Returns only jobs owned by the authenticated principal.
- A missing job belonging to another owner must not be distinguishable from an unknown job.
- `limit` is an integer from 1 through 25; the server applies a safe default and maximum.
- `GET /api/jobs/{job_id}` returns one summary for the authenticated owner; unknown and foreign-owner IDs both return 404.
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

## Persistence implementation boundary

- Operational records and bounded event summaries are stored in a local SQLite database with WAL mode, foreign keys, full synchronous commits, transaction boundaries, owner-scoped unique idempotency, and version-checked state updates.
- The store persists only opaque owner reference, fixed tool ID, action digest, idempotency key, lifecycle state/timestamps, bounded progress/result metadata, and bounded event summaries. It does not persist prompts, Gemini content, secrets, command lines, executable paths, or raw installer output.
- POSIX test/development storage requires a private state directory (0700) and database file (0600), rejects symlink paths, and fails closed on broad permissions.
- **Windows runtime storage is deliberately unavailable at this stage.** The store returns unavailable until native Windows DACL, owner SID, handle/reparse-point and path-race protections are implemented and independently reviewed. Do not bypass this guard or move the database to a less-protected location.
- No worker lease claim, approval consumption, job dispatch, or job producer is wired to the current API. Those remain separate reviewed work.

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
