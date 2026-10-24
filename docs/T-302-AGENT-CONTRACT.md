# T-302 — Agent Contract and Provider Boundary

## Status

**Approved by merge of PR #23 (2026-10-24).** This document defines the provider-neutral contract and records the requested account sign-in experience. Provider authorization, external data transfer, model selection, and token storage remain open decisions; no provider-backed request is approved by this document.

## Task

| Field | Content |
|---|---|
| Task ID | T-302 |
| Depends on | T-301 scope approved by merge of PR #22 |
| Purpose | Define the contracts and decisions required before Agent implementation |
| Allowed changes | `docs/PHASE-3.md`, this task document |
| Prohibited changes | Application code, runtime dependencies, provider SDKs, credentials, real machine-changing actions |

## Product Owner decisions recorded

- Provider support must be selectable among OpenAI GPT, Anthropic Claude, and Google Gemini.
- The Product Owner wants to sign in/connect with the selected provider account instead of manually entering an API key, then use the account's authorized AI capability.
- Keep the Agent Core independent of vendor-specific request and response formats. Provider-specific adapters, if approved later, implement the same internal interface.
- Use only each provider's official authorization flow and documented API/product integration. Never read browser cookies, copy web sessions, automate the consumer chat website, or extract data from a provider's website.
- Signing in does not imply access to existing chats/history. Importing account history is a separate capability requiring an official supported scope/API and explicit user approval.
- A provider choice does **not** by itself approve sending chat content outside the computer, selecting a default model, or storing authorization tokens.

## Proposed internal contracts

Contracts are conceptual at this stage; exact Python types and API serialization are to be specified in the implementation task after this document is approved.

| Contract | Required fields / behavior |
|---|---|
| Agent request | User message and UI language. Backend validates limits and creates a request identifier. Authorization is checked before the message is sent to any Agent/provider logic. |
| Provider interface | `analyze(request, tool_catalog) -> structured proposal`. Provider selection is constrained to the configured allowlist: GPT, Claude, or Gemini. Provider-specific SDK objects never cross this boundary. Each adapter uses only the provider's approved account authorization and supported product/API. |
| Intent | A bounded intent category and concise interpretation of the request. It is data, not permission. |
| Plan | Ordered, user-readable steps. Model output is treated as untrusted input and validated by the backend. |
| Tool proposal | Tool identifier and JSON arguments. The backend rejects unknown tools and validates parameters against the backend-owned catalog. |
| Tool result | Status (`success`, `rejected`, `dry_run`, or `failed`), safe user-facing summary, and structured data only where allowed. Machine-changing tools remain mock/dry-run through Phase 4. |
| Agent response | Request identifier, validated plan, execution/result summary, and safe error code when applicable. Never include secrets, provider credentials, raw traceback, or unfiltered provider response. |

## Local authorization decision (D-SEC-1 for Phase 3)

The Product Owner wants to connect to the selected AI provider using its official account sign-in/authorization flow. This is the preferred direction, but it is not yet approved as the backend-enforced local authorization method. Provider login must not be assumed to authorize unrelated PC actions.

Before enabling Agent processing through the application, record how the backend verifies the provider authorization, how tokens are protected and revoked, and what local action enables the Agent. Do not treat a UI-only toggle, model response, or caller-supplied `enabled` flag as authorization. Existing Host and Origin checks remain required.

## Decisions still needed before provider-backed requests

| ID | Decision | Current state |
|---|---|---|
| D-SEC-1-P3 | Define and approve the backend-enforced local Agent authorization flow. | Open; provider-specific feasibility, token handling, and the local enable action must be approved before enabling Agent processing. |
| D-AI-1 | Provider set | Approved set: GPT, Claude, Gemini. |
| D-AI-2 | Provider selection experience | Approved: the user selects GPT, Claude, or Gemini in the UI for each run. The backend validates the selected provider against its allowlist. |
| D-AI-3 | Data handling: may messages be sent to the selected vendor, and what privacy/retention constraints apply? | Open; no external calls until decided. |
| D-AI-4 | Models and fallback behavior | Open; choose model(s), whether automatic fallback is allowed, and how provider failures are reported. |
| D-AI-5 | Account authorization and token storage | Open; use official provider sign-in where supported and decide how tokens are stored securely on the local computer. Do not expose tokens to frontend JavaScript or commit them. |
| D-AI-6 | Initial mode | Open; deterministic local/mock mode can be used for implementation and tests without credentials or network access. |

## Intended task-planning and execution workflow

For a request such as “build a website,” the Agent should think through the whole task before acting and identify the required software, tools, and prerequisites—not only programs explicitly named by the user. It should distinguish what is already available from what may need installation.

1. The Agent interprets the goal and creates an end-to-end plan, including prerequisites, required applications/tools, versions where relevant, dependencies, and execution order.
2. When research is needed, it checks trustworthy current sources and records the source for each proposed install or action.
3. The Agent returns one structured plan showing each proposed action, exact command/tool parameters, source, dependencies, expected effects, and why that item is needed.
4. The backend validates every proposed item against its own tool catalog and safety policy. Model-generated text is never passed directly to a shell.
5. The UI presents the complete plan before execution. Software installations and other sensitive operations require the user's explicit approval of the exact plan/actions.
6. The controlled executor runs only validated and approved operations in dependency order, then reports the actual result and any items it could not complete.

Do not install speculative or unrelated software just because it might be useful. Explain why each prerequisite is needed and let the user review the whole plan before changes are made.

During Phases 3 and 4, the executor is mock/dry-run only. Real execution is enabled only after Phase 5's safety and permission system is implemented and approved, consistent with P-ORDER-1. An unknown, unvalidated, or unapproved action must be rejected, not executed.

## Safety and error requirements

- Treat provider output as untrusted; validate intent, plan, tool identifiers, and arguments on the backend.
- A provider cannot authorize itself or bypass the local authorization check.
- Do not send a request to a vendor before authorization and the data-handling decision are both in force.
- Use fixed, safe public error codes for validation, authorization, provider timeout, provider rejection, and internal failure. Keep provider details and tracebacks out of user responses.
- Tests for the core contract must use deterministic fakes. They must not require API keys or a live network.
- No model-generated command is executed directly; every proposed action is validated against backend-owned tools and parameters.
- Software installation and other sensitive operations require explicit approval of that exact action.
- No tool that changes files, processes, applications, software, or system settings may perform a real action before Phase 5 is implemented and approved.

## Completion criteria

- Product Owner approves the internal request/response and provider interface contract.
- D-SEC-1-P3 is answered and recorded before any Agent capability is enabled.
- Official login feasibility for each provider, data handling, model/fallback policy, token storage, and initial mode are recorded before provider integration.
- The implementation plan splits core contracts, end-to-end prerequisite planning, source-backed software/action proposals, tool validation/mock execution, and provider adapters into reviewable tasks.
- No code, dependency, credential, or external call is added by this documentation task.

## Verification

Documentation review only. No tests run because this task changes no application code.

## References

- `docs/PHASE-3.md` — approved Phase 3 scope (PR #22).
- `docs/PHASE-2.md`, D-SEC-1 — local authorization must be decided before Phase 3 enables Agent capabilities.
- `docs/PROPOSALS.md` — P-SEC-1 to P-SEC-4 and P-ORDER-1.
- [OpenAI: Using your ChatGPT plan in other apps and sites](https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps).
- [Google: Gemini API OAuth quickstart](https://ai.google.dev/gemini-api/docs/oauth).
- [Anthropic: Claude Code authentication options](https://docs.anthropic.com/en/docs/claude-code/getting-started).
- [OpenAI: ChatGPT and API billing are separate](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform).
- [Anthropic: Claude.ai plans and API access are separate](https://support.anthropic.com/en/articles/9876003-i-subscribe-to-a-paid-claude-ai-plan-why-do-i-have-to-pay-separately-for-api-usage-on-console).
