# Gemini Runtime Instructions and Universal Response Contract

## Product Owner authorization

- 2026-11-07: backend-owned runtime instruction for natural-language chat.
- 2026-11-23: universal schema-constrained response contract, raw response visibility, and request correlation as part of PR #170.
- These changes do not authorize a merge, live software installation, multi-package execution, environment inspection, new provider, or durable chat/prompt retention.

## Runtime behavior

- `src/backend/agent_backend/providers/gemini.py` supplies a backend-owned system instruction on every Gemini chat generation request.
- Chat generation uses `generate_universal_response()` with the backend-owned `UniversalConversationResponse` Pydantic JSON schema.
- Users continue to communicate naturally in Thai or English. They never need to type JSON or follow fixed command syntax.
- Every chat turn uses the same versioned envelope: `schema_version`, `message`, `intent`, `status`, `data`, `needs_clarification`, and `clarification`.
- Supported intents include ordinary conversation/help, one or multiple software requests, software removal, environment preparation, and environment inspection.
- Intent-specific package/environment/check data is validated by the same backend model. Unknown fields are rejected.
- The backend allows one bounded correction attempt for invalid model output. A second invalid response fails closed and is not saved to conversation history.
- The backend adds its own request ID and returns the exact Gemini JSON text separately from the parsed/validated response. The system instruction and API key are never returned.
- The frontend displays the natural-language message, a collapsible raw JSON view, and a backend-generated Request ID. Gemini proposals are labeled unverified. Backend discovery/evidence is shown separately.

## Trust and execution boundaries

- Gemini may propose package names, requested versions, rationale, source hints, and installation-method hints. Those values are not trust evidence.
- Gemini must not provide trusted Package IDs, installer URLs, hashes, certificate fingerprints, executable paths, shell commands, permissions, handlers, or approval results.
- Backend independently resolves package identity and source, verifies manifest/artifact evidence, and enforces exact-action approval.
- A single-package install intent may enter the existing backend WinGet discovery path only after contract validation. The discovery/evidence/TOTP/queue gates remain authoritative.
- Multi-package installation and environment preparation are currently proposals only. They do not start package discovery for every package, create an approval, or execute installation.
- Environment inspection is descriptive only; Gemini cannot inspect the PC and the current contract does not grant a machine-inspection capability.
- Ordinary chat/help never invokes software discovery, approval, or execution.
- This system instruction and JSON schema are behavioral/format controls, not security controls. Backend validation and capability-specific gates remain authoritative.

## Privacy and retention

- No new durable storage is introduced.
- Existing in-memory conversation history remains capped at 128 conversations, 10 successful user/assistant pairs per conversation, and one hour of inactivity.
- History stores only user text and the validated natural-language `message`; raw JSON and system instructions are not persisted in conversation history or logs.
- Raw JSON is included only in the immediate API response for UI inspection. It is not an authorization artifact.

## Verification

Tests must cover:
- Same envelope for greeting/chat, help, single/multiple install, environment preparation, and inspection intents.
- Strict rejection of extra fields and mismatched intent/data combinations.
- One correction attempt followed by fail-closed behavior if still invalid.
- Conversation history stores only validated natural-language messages.
- Raw JSON, request ID, parsed response, and backend verification remain distinct.
- API responses never expose system instructions or provider credentials.
- UI renders raw JSON as escaped text, not executable HTML.
- Gemini package suggestions cannot bypass backend package discovery and exact-action approval.

Provider schema compatibility and live Gemini behavior remain NOT VERIFIED until the relevant tests and Windows/user acceptance are completed.
