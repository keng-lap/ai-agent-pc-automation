---
name: secure-development
description: Apply the repository secure development lifecycle to design, implement, test, and review changes. Use for all non-trivial work, especially authentication, authorization, approvals, secrets, filesystem, process execution, networking, audit, scheduling, background jobs, and Windows integration.
---

# Secure Development Skill

Mandatory for this repository. First read AGENTS.md and docs/SECURE-DEVELOPMENT-STANDARD.md.

## Before coding
1. Confirm task scope, branch/base, relevant decisions, and explicit authorization.
2. Map actors, assets, entry points, trust boundaries, secrets, privileged operations, and data flows.
3. Create a threat model using docs/templates/THREAT-MODEL-TEMPLATE.md.
4. State security invariants, safe defaults, rejection behavior, and residual risks.
5. Define positive, negative, boundary, regression, and failure-injection tests.
6. If a required property cannot be specified, tested, or authorized, stop and report BLOCKED.

## While coding
- Keep the diff minimal and task-scoped.
- Validate and canonicalize untrusted input at backend boundaries.
- Authorize the exact immutable values later consumed by fixed handlers.
- Fail closed on missing identity, user presence, policy, storage, audit, or uncertain state.
- Bind approvals to owner/session, exact tool, parameters, target, expiry, and one-time consumption as applicable.
- Treat Windows ACLs, reparse points, native handles, clock behavior, concurrency, crashes, and restart as explicit design concerns where relevant.
- Never add arbitrary command execution, dynamic dispatch, model-selected handlers, or unapproved data flows.
- Never inspect or mutate the user's live PC; use isolated synthetic fixtures.

## Before PR
- Run documented lint, tests, builds, and applicable security checks.
- Include negative tests proving denied paths cannot reach side-effect handlers.
- Verify platform-specific behavior on its actual CI platform; mocks alone are insufficient evidence.
- Inspect the complete diff for secrets, weakened assertions, skipped checks, unrelated edits, and scope expansion.
- Report exact commands and outcomes. Use PASS only for completed successful checks; otherwise use FAIL, PENDING, or NOT VERIFIED.
- Require independent review for security-sensitive changes.
- Do not merge or enable real execution without separate explicit Product Owner approval.

## Response format
Summarize scope, threat model, invariants, tests added, checks actually run, outstanding risks, and current gate. If blocked, name the precise blocker and required evidence/decision.
