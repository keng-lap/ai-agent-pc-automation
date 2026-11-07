# Gemini Runtime Working Rules — T-602 Implementation

## Product Owner authorization

Authorized by the Product Owner on 2026-11-07. Scope is limited to supplying a backend-owned system instruction on every Gemini Chat generation request and adding regression tests. This does not authorize PC automation, function/tool calling, real machine-changing actions, new data flows, or changes to chat retention.

## Implementation

- `src/backend/agent_backend/providers/gemini.py` defines `CHAT_SYSTEM_INSTRUCTION` in backend-owned code.
- `generate_reply()` constructs a `GenerateContentConfig` with that instruction and passes it to every chat generation request.
- The instruction asks Gemini to use supplied conversation history, avoid repeated/optional clarification questions, make safe reversible assumptions, consolidate genuinely essential questions, answer concisely, and avoid inventing access or actions.
- It explicitly preserves the adviser/planner role and the existing backend validation, user approval, and DRY RUN boundary.
- Structured plan generation remains separate and does not inherit the chat instruction.

## Important limitations

- This is behavioral guidance, not a security control. Backend validation, allowlists, risk controls, and approval checks remain authoritative.
- The instruction does not grant Gemini access to `GEMINI.md`, GitHub, local files, PC state, or previous conversations. Only the current request and conversation history already supplied by the application are available.
- Conversation history remains in process memory, capped at 128 conversations and one hour of inactivity; it is not durable cross-session memory.
- The instruction can reduce unnecessary questions but cannot guarantee that Gemini will never ask when a detail is genuinely essential.

## Verification

Regression tests verify that the same system instruction is included in each chat generation call and that structured plan generation does not inherit the chat instruction. Existing chat history, retention, error-sanitization, and approval boundaries remain unchanged.
