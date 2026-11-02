# P5-505 — Dry-run Confirmation UX and API Contract

## Status

**Proposal for Product Owner review. Documentation only.** This document defines a Thai-default, bilingual UX/API proposal for reviewing an exact installation plan and its dry-run report. It does not authorize runtime implementation, machine inspection, downloads, installation, removal, or execution.

Current permission remains P1 — Dry-run / plan and report only. P2 machine inspection and P3 machine-changing execution remain disabled. Acknowledgement is informational only and is never execution authorization.

## 1. UX goals

1. Make the Agent's interpretation visible before the user acknowledges a plan.
2. Explicitly enumerate every program the Agent proposes, one program per item.
3. Show version certainty, reason, proposed source, dependency/order, known impact, disk estimate only when known, and unresolved questions.
4. Distinguish facts from assumptions and unknowns; never imply that live checks were performed.
5. Make it unmistakable that Dry-run does not modify the PC.
6. Provide Thai as the default UI language, with English available and consistent terminology.
7. Support keyboard, screen-reader, narrow mobile, and desktop layouts without relying on color alone.

## 2. Required screen structure

The review screen should present these sections in this order.

### A. Request received / คำขอที่ได้รับ

Show the user's original request as submitted in the current interaction. Do not persist it as chat/task history under this proposal.

### B. Agent interpretation / สิ่งที่ Agent เข้าใจ

Summarize the goal and constraints inferred from the request. Clearly mark any interpretation that is uncertain. Do not silently convert a broad goal into an expanded software bundle.

### C. Proposed installation plan / แผนการติดตั้งที่เสนอ

Show an explicit ordered list. Each program must have its own card/row with the fields below:

| Field | Thai label | Required behavior |
|---|---|---|
| Program | โปรแกรม | Exact product/package identity; if unresolved, mark needs clarification |
| Version | เวอร์ชัน | Exact requested/selected version, or "ยังไม่ได้ระบุ / Not specified" |
| Reason | เหตุผล | Tie directly to the user's stated requirement |
| Source | แหล่งติดตั้งที่เสนอ | Proposed package manager/source only; state not live-verified |
| Order | ลำดับ | Explicit order number |
| Dependencies | Dependencies | List known dependencies or state unknown/not checked |
| Disk space | พื้นที่ดิสก์ | Numeric estimate only when supported; otherwise unavailable/not checked |
| Impact | ผลกระทบ | Known admin/restart/system-wide implications; otherwise unknown/not checked |
| Status | สถานะ | One of the controlled statuses below |

Do not combine multiple programs into a vague category such as "Developer tools". Do not add optional software, extensions, drivers, runtimes, or utilities unless requested. If the request implies a dependency but the dependency is not explicit, mark it for clarification rather than silently adding it.

### D. Dry-run result / ผลการจำลอง

Show the result for each planned item and an overall result. Every result must carry the explicit statement:

**Dry-run only — no changes made. / จำลองเท่านั้น — ไม่มีการเปลี่ยนแปลงใด ๆ กับเครื่อง**

The result must also state that no live installed-state, source availability, compatibility, disk, privilege, or package-version checks were performed unless a future separately approved capability explicitly supports a named check. No such capability is active now.

### E. Questions and blockers / คำถามและสิ่งที่ต้องยืนยัน

Group unresolved decisions, such as ambiguous program identity, version, edition, source, installation scope, or dependencies. Ask concise questions and do not present an incomplete plan as ready for acknowledgement.

### F. Review acknowledgement / การรับทราบแผน

If the Product Owner decides acknowledgement is needed, it must be a separate informational action with wording such as:

- Thai: **รับทราบแผน (Dry-run เท่านั้น)**
- English: **Acknowledge plan (dry-run only)**

The decline action should be equally clear:

- Thai: **ไม่รับทราบ / ยกเลิกแผน**
- English: **Decline / cancel plan**

Acknowledgement must not be styled or worded as permission to install. Do not use "Approve and execute", "Install now", "Run", "Apply changes", or equivalent. Do not show an execution button or a disabled execution button that suggests execution is an available current feature.

## 3. Controlled statuses

Use these exact machine statuses and localized display labels:

| Status | Thai display | English display | Meaning |
|---|---|---|---|
| `PLANNED` | วางแผนแล้ว | Planned | Item is included in the proposed dry-run plan |
| `NEEDS_CLARIFICATION` | ต้องการข้อมูลเพิ่มเติม | Needs clarification | User input is required before plan review can be considered complete |
| `BLOCKED` | ถูกระงับ | Blocked | Policy or supported capability prevents this item |
| `UNSUPPORTED` | ไม่รองรับ | Unsupported | The fixed catalog does not support this request |

Do not invent additional success-like statuses such as `READY_TO_INSTALL`, `APPROVED`, or `INSTALLED` for the current P1 workflow.

## 4. Proposed API contract

Route names are illustrative; P5-504 and the existing API structure must be reconciled before implementation.

### 4.1 Create a dry-run plan

`POST /api/plans`

Request body contains only user-level request data and an allowed language preference. It must not accept trusted policy or authorization metadata.

Illustrative request:

```json
{
  "request": "Install the programs needed for Java development",
  "language": "th"
}
```

The backend validates the request and creates a plan using only the fixed tool catalog and local deterministic planning capability. No provider call, external lookup, package-manager query, machine inspection, or system change is allowed.

### 4.2 Read the plan

`GET /api/plans/{plan_id}`

Returns the exact plan and dry-run report for the current permitted workflow. The API must not expose secrets, local tokens, internal handler names, stack traces, or unbounded internal state.

### 4.3 Optional acknowledgement

`POST /api/plans/{plan_id}/acknowledgement`

This endpoint is optional and remains a Product Owner decision. If implemented, it records only acknowledgement that the displayed P1 plan was reviewed. It does not create an execution grant, change permission, enqueue a task, or dispatch a handler.

### 4.4 Decline/cancel

`POST /api/plans/{plan_id}/cancel`

Cancels the plan/review reference. Cancellation is terminal and idempotent. It does not perform cleanup on the PC because no PC operation has occurred.

### 4.5 No execute endpoint

There must be no `POST /api/execute`, install endpoint, remove endpoint, or generic action-dispatch endpoint in the P1 scope. No UI route or hidden API should provide equivalent behavior.

## 5. Illustrative response shape

The following is a conceptual schema only, not an implementation instruction. Values are illustrative and must not be mistaken for actual software recommendations or live-verified package data.

```json
{
  "plan_id": "opaque-server-generated-id",
  "language": "th",
  "mode": "dry_run",
  "status": "NEEDS_CLARIFICATION",
  "request_summary": "ติดตั้งเครื่องมือสำหรับพัฒนา Java",
  "agent_interpretation": "ต้องการชุดเครื่องมือสำหรับพัฒนา Java แต่ยังไม่ได้ระบุ IDE และเวอร์ชัน JDK",
  "items": [
    {
      "order": 1,
      "program": "JDK",
      "version": "ยังไม่ได้ระบุ",
      "reason": "จำเป็นสำหรับการพัฒนาและรันโปรแกรม Java",
      "proposed_source": "ยังไม่ได้เลือก",
      "source_live_verified": false,
      "dependencies": [],
      "dependencies_checked": false,
      "disk_space": null,
      "disk_space_checked": false,
      "impact": ["อาจต้องใช้สิทธิ์ผู้ดูแลระบบ — ยังไม่ได้ตรวจสอบ"],
      "status": "NEEDS_CLARIFICATION"
    }
  ],
  "dry_run_result": {
    "status": "not_executed",
    "summary": "จำลองแผนเท่านั้น",
    "changes_made": false,
    "live_checks_performed": false
  },
  "questions": [
    "ต้องการ JDK เวอร์ชันใด?"
  ],
  "notice": {
    "th": "จำลองเท่านั้น — ไม่มีการเปลี่ยนแปลงใด ๆ กับเครื่อง",
    "en": "Dry-run only — no changes made."
  }
}
```

The API must validate its own response against a strict schema. The client must not infer missing fields as success or fill unknown values with guesses.

## 6. API validation and security constraints

- Strict typed request and response schemas; reject extra fields.
- Request body limit remains 16 KiB unless a separately approved security review changes it.
- Preserve loopback-only bind, Host/Origin checks, JSON-only state-changing requests, and local API token protections.
- Client cannot submit `risk_class`, `required_permission`, `handler_name`, `approved`, `execution_mode`, or a policy version.
- Backend derives all trusted policy metadata as described in P5-504.
- Plan identifiers are opaque and unguessable, but are not authorization by themselves.
- Plan references expire and are bound to the exact immutable plan as described in P5-503.
- Acknowledgement, if enabled, is informational and one-time; it cannot be replayed to authorize execution.
- Error responses use bounded reason codes and do not leak secrets or internal implementation details.
- No chat/task history, full prompt archive, credentials, or secrets are stored by this contract.
- No provider, network lookup, package manager, OS command, process, file/registry access, installer, or unapproved external service is invoked.

## 7. Accessibility and interaction requirements

- Thai is the default locale; English is selectable without changing the underlying plan.
- Preserve the same item ordering and status meaning across languages.
- Use text labels and icons, not color alone, for status.
- Keyboard navigation and visible focus are required for every interactive control.
- Screen readers must announce section headings, item order, status, and the dry-run/no-change notice.
- On mobile, each program's fields must remain readable without horizontal scrolling.
- Long package names, versions, and source identifiers must wrap safely.
- Confirmation and cancel actions must be visually distinct but neither may resemble an execution action.
- The dry-run/no-change notice must remain visible near the acknowledgement action.

## 8. Acceptance criteria

- User request and Agent interpretation are displayed separately.
- Every proposed program is enumerated individually before acknowledgement.
- Every item includes all required fields or an explicit unknown/not-specified value.
- No optional program is silently added.
- Ambiguity produces `NEEDS_CLARIFICATION`; unsupported capability produces `UNSUPPORTED`; policy denial produces `BLOCKED`.
- Dry-run outcome clearly says no changes were made.
- UI/API never claim live checks that were not performed.
- No execution or install/remove endpoint/control exists in P1.
- Acknowledgement is explicitly informational and cannot grant permission.
- Thai-default bilingual content is consistent and accessible on mobile and desktop.
- Existing API security controls and P5-503/P5-504 invariants are preserved.
- No runtime implementation, tests, machine inspection, download, provider call, external data transfer, or PC operation is part of this task.

## 9. Open decisions for Product Owner

1. Confirm the proposed screen order and mandatory per-program fields.
2. Decide whether plan acknowledgement should be implemented at all, or whether displaying the plan is sufficient.
3. Approve or revise the illustrative API route and response shape.
4. Confirm Thai as default with English selectable.
5. Confirm that the P1 UI must contain no execution control, including disabled execution controls.
6. Confirm whether the plan should be ephemeral only, consistent with no chat/task history and the P5-506 retention proposal.

No decision is assumed from silence.
