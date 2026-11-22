# P6-609-E — Universal Conversation Response Contract

## Status
Implementation in progress on `feat/P6-609-C-winget-execution`. This document records the Product Owner-approved direction from 2026-11-23; it does not authorize merge or live installation.

## Product requirement
Users communicate naturally in Thai or English. They never need to know or type JSON. Every Gemini chat turn, including greetings, general questions, help, single/multiple software requests, environment preparation, and environment inspection, uses one stable response envelope. Only the intent and intent-specific data vary.

## Contract
The backend-owned Pydantic model is `agent_backend.conversation_contract.UniversalConversationResponse` and its version is `1.0`.

Required top-level fields:
- `schema_version`
- `message`
- `intent`
- `status`
- `data`
- `needs_clarification`
- `clarification`

The API adds a backend-generated `request_id`, the parsed `gemini_response`, and the exact `gemini_raw_json` for diagnostics/display. Provider metadata is separate. The application must never expose the system instruction, API key, or provider credentials.

## Supported intents
- `conversation.chat`: greetings and ordinary conversation.
- `system.help`: help using this application.
- `software.install`: one software package request.
- `software.install_multiple`: two or more package requests.
- `software.remove`: one explicitly named removal request; existing preview-only rules remain.
- `environment.prepare`: a development/work environment proposal, including a proposed package list.
- `environment.inspect`: a list of checks to request from a backend-owned inspection capability. The current contract does not grant such a capability.

## Trust boundary and responsibilities
- Gemini interprets natural language and proposes package names, requested versions, purposes, and human-readable source/method hints.
- Gemini does not choose trusted Package IDs, installer URLs, hashes, certificates, executable paths, shell commands, handlers, permissions, or approval outcomes.
- Backend validates strict schema and intent/data consistency, then independently resolves package identity, source, exact manifest, installer evidence, and allowed installation method.
- Backend result and evidence are displayed separately from Gemini's response. Gemini text is never proof of verification.
- A malformed response receives at most one bounded correction attempt. If validation still fails, the request fails closed and is not added to conversation history.
- Ordinary chat/help responses do not invoke discovery, approval, or execution.
- Multi-package and environment plans are proposals only until a separate backend implementation validates each item and defines per-item approval/execution semantics.

## UI requirement
Show the natural-language `message` as the chat response. Provide a collapsible view of the exact JSON text returned by Gemini, plus backend-generated Request ID. Display backend discovery/trust results in a separate section. Never label a Gemini suggestion as backend-verified.

## Privacy
No new durable storage is introduced. The existing in-memory conversation history stores only user text and the validated natural-language message, not raw prompts or raw JSON. Raw JSON is returned to the current UI response for inspection and is not added to conversation history or logs.

## Acceptance criteria
1. Thai/English natural-language messages are accepted without command syntax.
2. Greetings/general chat use `conversation.chat` and the same envelope.
3. Single and multiple package requests use the same envelope with different intent/data.
4. Environment preparation returns environment details and a bounded proposed package list in the same envelope.
5. Extra keys, malformed JSON, mismatched intent/data, execution fields, and oversized collections are rejected.
6. At most one correction attempt occurs; a second invalid response fails closed.
7. API exposes the exact Gemini JSON separately from backend-generated Request ID and verification result.
8. System prompt and credentials are never returned.
9. No installation occurs from Gemini output alone.
10. Unit and frontend tests cover the above; live Gemini/Windows acceptance remains separately NOT VERIFIED until run on the user's machine.
