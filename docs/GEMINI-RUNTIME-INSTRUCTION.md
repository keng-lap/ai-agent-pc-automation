# Gemini Runtime Working Rules — Follow-up Task

## Purpose

Make the Gemini Chat feature in the local application consistently concise and reduce repeated requests for information across conversations, without weakening the approved safety and privacy boundaries.

## Verified current behavior

The current implementation is documented in `docs/T-601-GEMINI-CHAT-MVP.md` and the current backend source:

- `src/backend/agent_backend/chat.py` builds the conversation contents from the current conversation's in-memory history.
- It sends up to 10 preceding user/assistant pairs plus the current user message.
- `src/backend/agent_backend/providers/gemini.py` calls `client.models.generate_content(model=MODEL_NAME, contents=contents, config=config)`.
- The chat call currently does not supply a backend-owned `system_instruction` / equivalent persistent instruction.
- Conversation history is temporary process memory, capped at 128 conversations and one hour of inactivity. It is not durable memory and must not be described as cross-session memory.

## Required behavior for a future bounded runtime change

A future authorized implementation should:

1. Define a concise, backend-owned system instruction for Gemini Chat and apply it on every chat request, not only once in a browser conversation.
2. Tell Gemini to use the current conversation context and provided project context before asking questions.
3. Prohibit repetitive clarification requests. For non-critical missing details, state a safe assumption and continue.
4. Ask only when a missing detail is genuinely blocking, safety-critical, irreversible, privacy-sensitive, or requires Product Owner approval.
5. Consolidate unavoidable questions into one concise message.
6. Keep answers and plans concise; do not repeat information already supplied.
7. Preserve the existing role separation: Gemini proposes; backend validates; user approves; backend performs DRY RUN only; results are shown to the user.
8. Keep backend policy and validation authoritative. A system instruction is behavioral guidance, not a security control.
9. Preserve the current context limit, expiry, in-memory-only retention, credential handling, and sanitized provider-error behavior unless separately approved.
10. Add focused tests proving the system instruction is supplied on every chat request and that current approval/dry-run boundaries remain unchanged.

## Important limitation

A system instruction can reduce unnecessary questions, but it cannot guarantee that Gemini will never ask. It must not encourage the model to invent facts or proceed when a required safety decision is missing.

## Authorization status

**Documentation only. Runtime implementation is not authorized by this document.** A separate bounded runtime task must be explicitly authorized by the Product Owner before code changes begin. Do not interpret this follow-up specification as permission to modify the backend.
