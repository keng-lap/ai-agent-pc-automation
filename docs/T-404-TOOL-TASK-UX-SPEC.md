# T-404 — Tool / Task Status UX Specification

## Status
UX specification only. No frontend source was changed. Inspect actual Angular component/service mapping before implementation.

## UX goals
- Distinguish plan, validated tool request, and dry-run result.
- Make clear that dry-run means no change was made.
- Show approval_required without offering a real-execution button.
- Thai is default; English uses the existing language preference.
- Keep the interface compact and readable on desktop/mobile.

## Existing frontend baseline
- App component currently accepts any response with a string reply field and appends only response.reply to the conversation.
- The view renders message text only; structured plan, prerequisites, tool_result, approval_required, and provider_connected are not yet displayed.
- Chat entries live in the current Angular signal/session and disappear on reload; only the language preference is persisted in localStorage.
- The empty-state hint currently says the Agent is not implemented / replies are placeholders. This should be corrected when the structured response UX is integrated, because the backend already runs a deterministic local planner and dry-run pipeline.
- The backend main.py module docstring still calls the chat route a placeholder; it should be reconciled in a separate code/documentation review, not silently changed in this UX task.

## Existing API facts
AgentResponse currently contains:
- reply
- provider (currently chatgpt)
- provider_connected (literal false)
- plan (intent, language, prerequisites, steps, approval_required, execution_mode)
- tool_result (nullable; tool_id, target, status, approval_required, summary)

Do not imply provider_connected=true or real execution. Do not infer a task state that the backend does not return.

## Proposed display sections

1. Request plan
   - Task category and target when known.
   - Ordered planner steps.
   - Prerequisite list with status: known, user_confirmation_needed, discovery_not_available.
   - Explain that unavailable discovery is not a failed check; it means the application cannot inspect the PC or research sources in this phase.

2. Tool preview
   - Show selected tool ID as localized friendly label.
   - Show target.
   - Show status as “Dry-run / จำลองเท่านั้น”.
   - Show backend summary.
   - Show approval_required as “ต้องได้รับอนุมัติก่อนดำเนินการจริง”.
   - If tool_result is null, show “ไม่มีเครื่องมือที่อนุญาตสำหรับงานนี้” and do not invent a tool.

3. Provider connection
   - Current state is not connected; label as local deterministic preview.
   - Do not show provider connection actions or request credentials.

## Status vocabulary

| API concept | Thai label | English label | UI treatment |
|---|---|---|---|
| Plan exists | วางแผนแล้ว | Planned | Neutral |
| Validation rejection (future typed response only) | ตรวจสอบไม่ผ่าน | Validation failed | Warning |
| status=dry_run | จำลองเท่านั้น | Dry run | Neutral with explanation |
| approval_required=true | ต้องอนุมัติก่อนดำเนินการจริง | Approval required before real execution | Informational warning |
| tool_result=null | ไม่มีเครื่องมือที่อนุญาต | No allowlisted tool | Neutral |
| provider_connected=false | ยังไม่เชื่อมต่อ AI Provider | AI provider not connected | Neutral |

Do not fabricate queued, running, completed, cancelled, or executed states until the backend contract provides them.

## Interaction rules
- No Run, Install now, Uninstall now, Approve and execute, or equivalent button in Phase 4.
- User may review plan and clarify through existing chat request flow.
- A future confirmation interaction belongs to Phase 5 and must not be simulated as granting machine permissions.
- Language preference follows D-API-2; do not persist messages, task records, or history.
- Do not store or expose local API token in browser storage or UI.

## Accessibility and responsive behavior
- Status labels include text, not color alone.
- Use semantic headings and ordered lists.
- Preserve keyboard navigation and visible focus.
- Do not rely on hover-only explanations.
- Keep long summaries and prerequisite reasons readable on narrow screens.
- Never show raw internal exception text.

## Acceptance criteria
- Thai appears by default; English can be selected through existing preference.
- Plan, prerequisites, tool preview, and provider state are visually distinct.
- Dry-run is explicit and explains no changes were made.
- Approval-required is visible but no real-execution control is offered.
- Null tool_result is handled without errors or fabricated details.
- No task history or chat messages are persisted.
- UI does not expose credentials or bypass backend validation.
- Component tests cover response variants, including no tool result and both languages.
- UI tests assert that the structured plan and dry-run result are visible after integration.
- Empty-state copy no longer incorrectly claims that the Agent is unimplemented.

## Dependencies
T-404 implementation depends on T-401 metadata/display contract and stable T-402/T-403 response fields. This document does not authorize API changes.
