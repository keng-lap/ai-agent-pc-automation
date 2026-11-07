# Gemini Project Instructions

> Read this file at the start of every project session before proposing or changing anything.
> This file governs AI coding assistants working in this repository when their host tool loads repository instructions. It is not automatically sent to the Gemini Chat API used by the running application; see [the runtime instruction task](docs/GEMINI-RUNTIME-INSTRUCTION.md).

## 1. Project context and source of truth

- Repository: `keng-lap/ai-agent-pc-automation`.
- Product: a local web application and backend for a personal Windows 11 AI agent.
- Read the relevant current phase/task document, `docs/PROJECT.md`, `docs/ROADMAP.md`, and relevant approved decision records before acting.
- Check the current `main` branch, open/merged PRs, and the active task branch before reporting project status. Do not rely on an old chat summary.
- If documents conflict, do not guess silently. Prefer explicit Product Owner decisions and current task-specific approved documents; identify the conflict and reconcile documentation before implementation.
- Treat proposals and assumptions as non-binding until approved.
- Default UI language is Thai. Preserve the approved branch convention: `<type>/<task-id>-<short-name>`.

## 2. Minimize user questions — mandatory

**Default: ASSUME, DOCUMENT, AND PROCEED.**

- Do not repeatedly ask the user for additional information.
- Do not ask for information already present in repository files, approved decisions, the current conversation, or available GitHub history.
- Before asking anything, inspect the relevant sources and use the information already available.
- For non-critical missing details, choose a conventional, secure, reversible default; record the assumption briefly and continue.
- Do not ask the user to choose routine implementation details that are within the approved task scope.
- Do not stop progress for minor uncertainty. Continue with safe, reversible work and report the assumption.
- If several genuinely blocking questions remain, consolidate them into one concise message rather than asking one at a time.
- Ask only when proceeding would require a Product Owner decision, change approved scope or architecture, weaken security/privacy, expose data externally, cause an irreversible or machine-changing action, or when no safe reasonable assumption exists.
- Explain exactly why each unavoidable question blocks progress. Do not ask hypothetical or preference questions.

## 3. Approval and safety boundaries

- The Product Owner is the approval authority. An AI assistant cannot approve its own proposal or infer approval from silence.
- Documentation/planning changes may be made and merged when they are consistent with approved decisions and do not alter requirements, scope, security, or runtime behavior.
- Runtime/code changes require a bounded task, tests, review, and explicit Product Owner authorization/merge approval as required by the active phase rules.
- Never perform a real Windows machine-changing action. Installation, removal, file modification/deletion, administrator commands, process control, and system/network/security changes remain prohibited unless separately authorized under the approved phase and capability gates.
- The current product workflow is: user request -> Gemini proposes a plan -> backend validates and processes it -> user explicitly approves -> backend performs DRY RUN only -> show the result. Do not bypass or reorder these gates.
- Gemini output is untrusted input. Backend-owned schemas, allowlists, risk classification, permissions, validation, and approval checks are authoritative.
- Never execute raw model text, arbitrary shell/PowerShell, scripts, dynamic imports, or unapproved tools.
- Preserve loopback-only exposure, local API authorization, Host/Origin checks, request limits, and all existing safety controls.
- Do not introduce new providers, external data flows, credentials, durable chat/task history, or sensitive data retention without explicit approval.
- Do not expose API keys, local tokens, secrets, raw provider errors, or sensitive user content in responses, logs, tests, commits, or documentation.

## 4. Required workflow for every task

1. Read this file and the relevant project/task/decision documents.
2. Inspect current repository state and relevant PRs/CI before deciding what remains.
3. Restate the task scope internally and identify the applicable safety boundary.
4. Reuse existing decisions and defaults; do not ask the user to repeat them.
5. For documentation-only work, make the smallest consistent change and verify links/claims.
6. For runtime work, confirm explicit authorization exists before editing code; add/update tests and request the required review.
7. Report only: what changed, validation evidence, blockers (if any), and the next required approval/action.
8. Do not claim a test, CI run, local Windows test, PR merge, or runtime behavior succeeded unless verified.

## 5. Communication format

- Be concise and use Thai by default when communicating with the Product Owner.
- Do not send long progress narration or repeat project history.
- Report assumptions in one short section only when they materially affect the result.
- Ask at most one consolidated set of essential questions.
- If no approval is needed, proceed instead of asking for confirmation.
- Clearly distinguish: completed, merged, CI-verified, and still requiring local Product Owner testing.

## 6. Session continuity

At the start of a new session:
- Read this file.
- Inspect current `main`, open PRs, and the active task/phase documents.
- Read the latest relevant decision and handoff/status document.
- Summarize the current position in no more than five bullets, then continue the next already-authorized task.
- Do not assume that model memory or a previous chat is available.

At the end of a session:
- Update the existing task/status/handoff document when the task requires it.
- Record decisions only when actually approved; label assumptions and proposals clearly.
- Give the Product Owner a concise handoff that identifies the next concrete step.

## 7. Important runtime distinction

These repository instructions guide coding assistants only when their host environment loads this file. The Gemini Chat API in the running application does not automatically read `GEMINI.md`. Its persistent behavior requires a backend-owned system instruction to be supplied on every relevant provider request. That is a separate runtime change and is tracked in [docs/GEMINI-RUNTIME-INSTRUCTION.md](docs/GEMINI-RUNTIME-INSTRUCTION.md). Do not claim that this file alone changes the application's Gemini chat behavior.
