# Proposals (Pending Project Owner Approval)

## Status of this document

Everything in this file is a **proposal**. None of it is a requirement, and none of it is approved.

- This file is **not** a source of truth (see `docs/PROJECT.md`, Section 9).
- Nothing here may be implemented until the project owner approves it and it is moved into the appropriate phase document.
- Nothing here changes `docs/ROADMAP.md`. The roadmap order is unchanged.
- Nothing here is implemented in Phase 0. Phase 0 only records the proposals.

Proposed on: 2026-10-09

---

# 1. Security Proposals

The Agent will eventually control a real Windows computer, and it will be reachable through a local web application. The following proposals describe how that exposure could be limited. The "Suggested phase" column follows the existing roadmap and is only a suggestion.

## P-SEC-1: Local-only binding

- The web application and backend listen only on the loopback interface (`127.0.0.1` / `::1`).
- They must never listen on `0.0.0.0` or any LAN-facing address by default.
- Changing this requires explicit project owner approval and documentation.

Suggested phase: Phase 1 (configuration) and Phase 2 (web application).

## P-SEC-2: Protection against requests from other websites

A page open in the user's browser on any website can send requests to `localhost`. A local-only listener alone does not stop this. Proposed measures:

- Validate the `Origin` header on state-changing requests, and on WebSocket handshakes, against an allowlist of the app's own local origins.
- Validate the `Host` header against an allowlist (protects against DNS rebinding).
- No permissive CORS (no wildcard origins, no credentialed wildcard).
- CSRF protection for state-changing requests.
- No GET endpoint may trigger an action or change state.
- A random per-session secret token, generated at startup, required on every API call. This also stops other local processes and arbitrary web pages from driving the Agent.

Suggested phase: Phase 2 (web application), verified again in Phase 5.

## P-SEC-3: Permission and confirmation

- Every tool declares a risk level and the permission it requires.
- Confirmation is enforced by the backend, not by the AI model. The model cannot approve its own actions.
- A confirmation applies to one specific action with its exact parameters, and expires. It cannot be reused for a different action.
- Sensitive operations listed in `PROJECT.md` Section 6 (delete files, install/uninstall software, administrator commands, system/network/security settings) always require explicit user approval unless a future phase defines a safe automated policy.

Suggested phase: Phase 5 (per the current roadmap). See Proposal P-ORDER-1 about when this protection is needed.

## P-SEC-4: Dry-run and mock mode for tools that change the machine

- Every tool that modifies the machine supports a **dry-run** mode that reports what it would do without doing it.
- Until the permission and confirmation system exists, such tools run only in dry-run or against a **mock** implementation.
- Real execution must be an explicit, separately approved switch, not the default.

Suggested phase: Phase 3 and Phase 4 (tool design), with real execution enabled no earlier than the phase the owner approves.

---

# 2. Roadmap Order Proposal (Requires Owner Decision)

## P-ORDER-1: Safety protection before real tool execution

**Observation.** `ROADMAP.md` defines Phase 3 (Agent Core: "Execute controlled tool") and Phase 4 (Tool / Task System: software installation, software removal, command execution) before Phase 5 (Safety and Permission System). `README.md` principle 2 and `PROJECT.md` Section 6 say dangerous operations must not run without explicit authorization. If Phase 4 tools were implemented with real execution before Phase 5, that principle would not yet be enforced.

**Options**

- **A. Keep the order, constrain Phase 3 and Phase 4.** Tools that change the machine are dry-run or mock only (see P-SEC-4). Real execution is enabled only after Phase 5 is complete. No phase is moved.
- **B. Split Phase 5.** Move a minimal permission and confirmation mechanism into Phase 4, and leave the rest of Phase 5 where it is.
- **C. Swap Phase 4 and Phase 5.** The safety system is designed before the tools are built.

**Suggestion.** Option A, because it keeps the approved phase order and needs only a constraint added to the Phase 3 and Phase 4 descriptions.

**Decision needed from the project owner.** `ROADMAP.md` is not changed until the owner decides.

---

# 3. Other Open Items

These are not proposals to change anything yet. They are items found during the Phase 0 review that need an owner decision or a later phase.

| Item | Notes |
|------|-------|
| Programming language, backend and frontend frameworks | Selected in Phase 1 (per roadmap). Not decided. |
| AI model / provider | Not defined. Phase 3 (Agent Core) per roadmap. |
| License | Repository has no license file. |
| Branch naming convention | Rule is "no direct commits to `main`". A naming convention is not defined. The Phase 0 close-out branch used `chore/phase-0-closeout`. |
| "Task history" listed twice | Appears in Phase 7 and Phase 9 in `ROADMAP.md`. |
| Phase 0 title differs | `ROADMAP.md` says "Phase 0 — Foundation"; other documents say "Phase 0 — Project Foundation". |
| `.gitignore` is language-agnostic | Review it when the language and framework are chosen in Phase 1. It currently ignores `.vscode/` and `.idea/`; revisit if shared editor settings are wanted. |
