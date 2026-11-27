# Threat Model — P6-609-E Universal Conversation Contract

- **Status:** Draft
- **Author:** Implementation agent
- **Reviewer:** Pending independent review
- **Date:** 2026-11-23
- **Base commit:** PR #170 head before P6-609-E changes
- **Scope:** Gemini chat response schema, backend validation, bounded correction, request correlation, and UI visibility.
- **Applicable decisions:** Product Owner direction on 2026-11-23; docs/P6-609-E-UNIVERSAL-CONVERSATION-CONTRACT.md; docs/SECURE-DEVELOPMENT-STANDARD.md.

## 1. Intended behavior and non-goals
Use one strict response envelope for ordinary chat and planning intents. Show the natural-language message and exact Gemini JSON separately from backend verification. No durable transcript/prompt storage, new provider, new external data flow, installation capability, multi-package execution, or machine inspection is added by this task.

## 2. Assets and security objectives
| Asset | Why it matters | Required protection |
|---|---|---|
| Gemini API key | Provider credential | Never return, log, or embed in UI response |
| User message/history | Private conversation context | Existing in-memory-only retention; no new durable storage |
| Gemini raw JSON | Untrusted model output | Strict validation; display only as escaped text |
| Backend trust evidence | Authoritative installation trust | Never accept from Gemini |
| Request ID | Diagnostic correlation | Backend-generated, non-authorizing opaque identifier |

## 3. Actors and trust boundaries
| Actor/component | Trust level | Inputs/outputs | Boundary controls |
|---|---|---|---|
| User/browser | Untrusted | Natural-language request; renders response | Request bounds; no authority from client state |
| Gemini provider | External/untrusted | Candidate JSON and message | Backend-owned system instruction and response schema; strict Pydantic validation |
| Chat API | Trusted policy boundary | Validates response and stores in-memory message | One correction attempt; fail closed |
| Package discovery/evidence | Trusted backend boundary | Catalog/manifest/artifact metadata | Independent backend resolution and verification |
| UI | Presentation only | Displays message/raw JSON/backend result | Angular escaped interpolation; no raw HTML execution |

## 4. Data-flow trace
User message -> bounded ChatRequest -> in-memory conversation context -> Gemini schema-constrained JSON -> strict JSON/Pydantic validation -> one bounded correction on invalid output -> validated message stored in existing in-memory history -> response with backend-generated request ID and raw JSON -> escaped UI rendering. Any package intent remains a suggestion; backend discovery independently resolves and validates package data before any exact-action approval path.

## 5. Threats and abuse cases
| ID | Threat / abuse case | Preconditions | Impact | Mitigation / invariant | Test ID | Residual risk |
|---|---|---|---|---|---|---|
| T-01 | Model emits extra executable fields | Prompt injection or model error | Arbitrary action data could be mistaken as trusted | Strict extra-forbid schema; no execution fields | contract rejects extra fields | Low |
| T-02 | Model claims source/hash/signature is verified | Model hallucination | User may trust false provenance | Gemini fields are explicitly suggestions; backend evidence separate | API/UI separation tests | Medium until UI integration |
| T-03 | Malformed or inconsistent JSON | Provider output drift | Invalid plan reaches UI/backend | One correction attempt then fail closed | chat invalid-output tests | Low |
| T-04 | Raw JSON causes script injection | Malicious model text rendered | XSS | Render as escaped Angular text, never innerHTML | frontend rendering test | Low |
| T-05 | API key/system prompt leaks | Debug output includes secrets | Credential/system-instruction exposure | Return only response JSON and request ID; no prompt logging | response omission tests | Low |
| T-06 | Raw prompts/JSON persisted | Diagnostic convenience | Privacy expansion | Keep raw JSON only in response; existing history stores validated message only | history tests | Low |

## 6. Security invariants
- Gemini output MUST be treated as untrusted.
- Unknown top-level and nested fields MUST be rejected.
- Intent-specific data MUST satisfy the backend-owned contract.
- A failed validation MUST NOT be added to conversation history.
- Correction attempts MUST be bounded to one.
- Gemini output MUST NOT authorize, select a handler, or directly execute software.
- API key and system instruction MUST NOT be returned.
- Raw JSON MUST be rendered as escaped text.
- No new durable storage or logging of prompts/raw output is introduced.

## 7. Design decisions
| Decision | Chosen design | Alternatives rejected | Reason |
|---|---|---|---|
| Contract | Strict Pydantic model + Gemini JSON schema | Free-form text/regex extraction | Stable fields and backend validation |
| Repair | One correction attempt | Unbounded retries or silent fallback | Bounded cost and fail-closed behavior |
| Request ID | Backend-generated UUID | Model-generated correlation ID | Prevent model-controlled trace metadata |
| Raw output | Current response only | Persisted transcript/log | Avoid new retention |
| Execution | Backend discovery/evidence only | Trust Gemini package metadata/commands | Preserve trust boundary |

## 8. Verification plan
| Test ID | Positive / negative / boundary / failure | Expected result | Evidence / runner |
|---|---|---|---|
| C-01 | Valid chat/install/multiple/environment response | Accepted under same envelope | Backend unit tests |
| C-02 | Unknown fields / invalid intent-data pairing | Rejected | Backend unit tests |
| C-03 | First invalid response then valid correction | Accepted after exactly one correction | Chat API unit test |
| C-04 | Two invalid responses | Safe error; no history entry | Chat API unit test |
| C-05 | Raw JSON contains HTML-like text | Displayed as text only | Angular unit test |
| C-06 | API response inspected for prompt/key | Neither is present | API unit test |
| C-07 | Package intent | No install handler called | Backend architecture boundary; existing approval gates |

## 9. Privacy, logging, and retention
No new persistent store, log field, or retention window. Conversation memory continues to store only user text and validated natural-language response. Raw provider JSON is returned to the current UI response and not stored in history or logs. Request ID is not an authorization token.

## 10. Residual risks and decisions required
| Risk | Severity / confidence | Compensating control | Owner | Expiry / revisit trigger |
|---|---|---|---|---|
| Provider schema support may vary by model/SDK | Medium / confirmed compatibility must be tested | Strict server validation and one retry | Product Owner | Before live Gemini acceptance |
| UI and intent-specific backend routing may be incomplete | Medium / implementation pending | Non-executable proposal-only behavior | Product Owner | Before enabling multi-package/environment execution |

## 11. Review disposition
- [x] Scope and governing decisions identified
- [x] Trust boundaries and data flow documented
- [x] Threats and invariants identified
- [x] Positive/negative tests defined
- [ ] Independent review completed
- **Disposition:** PENDING IMPLEMENTATION AND INDEPENDENT REVIEW
