# T-302 — Agent Contract and Provider Boundary

## Status

**Draft for Product Owner decision.** This document defines a provider-neutral contract and proposes the local authorization boundary. No application code, provider SDK, API key, or external request is introduced by this task.

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

## Proposed local authorization decision (D-SEC-1 for Phase 3)

**Recommendation for Product Owner approval:** before enabling Agent processing, the backend creates a random, short-lived capability secret at startup and makes it available only to the owner through the local development console. The owner enters it into the local UI to enable the Agent for that run. The backend validates the secret on every Agent request, keeps it in memory only, and invalidates it when the backend stops. Existing Host and Origin checks remain required. Do not log the secret.

This is a proposal, not an implemented control. It avoids treating a button, model response, or caller-supplied `enabled` flag as authorization. Before implementation, confirm whether this startup-secret flow is acceptable or specify another local authorization method.

## Decisions still needed before provider-backed requests

| ID | Decision | Current state |
|---|---|---|
| D-SEC-1-P3 | Approve provider account authorization as the local Agent enablement flow, with a separate explicit user action to connect a provider. | Proposed; provider-specific feasibility and backend enforcement must be approved before enabling Agent processing. |
| D-AI-1 | Provider set | Approved set: GPT, Claude, Gemini. |
| D-AI-2 | Provider selection experience | Approved: the user selects GPT, Claude, or Gemini in the UI for each run. The backend validates the selected provider against its allowlist. |
| D-AI-3 | Data handling: may messages be sent to the selected vendor, and what privacy/retention constraints apply? | Open; no external calls until decided. |
| D-AI-4 | Models and fallback behavior | Open; choose model(s), whether automatic fallback is allowed, and how provider failures are reported. |
| D-AI-5 | Account authorization and token storage | Open; use official provider sign-in where supported and decide how tokens are stored securely on the local computer. Do not expose tokens to frontend JavaScript or commit them. |
| D-AI-6 | Initial mode | Open; deterministic local/mock mode can be used for implementation and tests without credentials or network access. |

## Safety and error requirements

- Treat provider output as untrusted; validate intent, plan, tool identifiers, and arguments on the backend.
- A provider cannot authorize itself or bypass the local authorization check.
- Do not send a request to a vendor before authorization and the data-handling decision are both in force.
- Use fixed, safe public error codes for validation, authorization, provider timeout, provider rejection, and internal failure. Keep provider details and tracebacks out of user responses.
- Tests for the core contract must use deterministic fakes. They must not require API keys or a live network.
- No tool that changes files, processes, applications, software, or system settings may perform a real action before Phase 5 is implemented and approved.

## Completion criteria

- Product Owner approves the internal request/response and provider interface contract.
- D-SEC-1-P3 is answered and recorded before any Agent capability is enabled.
- Official login feasibility for each provider, data handling, model/fallback policy, token storage, and initial mode are recorded before provider integration.
- The implementation plan splits core contracts, deterministic planning, tool validation/mock execution, and provider adapters into reviewable tasks.
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
