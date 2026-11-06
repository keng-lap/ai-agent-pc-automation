# P5-512 — Immutable Dry-run Plan/Report Contract

## Status

**Runtime implementation authorized by the Product Owner on 2026-11-07.** Draft implementation is available in [PR #63](https://github.com/keng-lap/ai-agent-pc-automation/pull/63). It is not merged. Automated verification and explicit Product Owner code-review/merge approval remain outstanding.

## Scope delivered in this task

- Strict, frozen Pydantic models for a complete, ordered per-program plan.
- Only the existing fixed tool IDs are accepted: `software.install` and `software.remove`; the backend policy guard is evaluated before a plan is created.
- Controlled item statuses are exactly `PLANNED`, `NEEDS_CLARIFICATION`, `BLOCKED`, and `UNSUPPORTED`.
- Server-owned schema/tool-contract versions, risk `R1`, permission `P1`, and `dry_run` mode.
- Opaque server-generated plan ID and a canonical SHA-256 digest.
- Backend-owned expiry exactly 10 minutes after creation.
- Thread-safe, process-local plan store capped at 128 active plans. It rejects new plans at capacity rather than silently evicting a live reference.
- Expired references are removed. Restart creates a new empty store, so prior references cannot be recovered.
- A backward or invalid backend clock clears references and permanently fails closed for that store instance; restart is required.
- Explicit evidence limits: source and dependency checks are marked `NOT_CHECKED`; live checks are fixed to false; the report notice is fixed to `DRY_RUN_ONLY_NO_CHANGES_MADE`.

## Identity and digest

Canonical identity uses UTF-8 JSON with sorted keys, compact separators, and stable field serialization. SHA-256 covers:

- schema and tool-contract versions;
- fixed tool ID, risk, permission, and dry-run mode;
- ordered program list and every material per-program field, including program, version, purpose, reason, proposed source, dependencies, disk estimate, impact, status, and verification flags.

The digest deliberately excludes the random plan ID and timestamps. A new plan with identical material content has the same digest but a different opaque plan ID. Any material content or ordering change produces a different digest. The digest is an integrity/binding aid, not authentication or human approval.

## Privacy and safety boundaries

- The schema rejects unknown fields; it has no prompt, chat-history, secret, acknowledgement, confirmation, or execution field.
- No prompt or secret is copied into the plan or digest.
- No API route, frontend control, acknowledgement flow, execute endpoint, or real handler is added by P5-512.
- No shell, process, filesystem, registry, OS inspection, network lookup, package-manager, download, provider, install, or uninstall capability is introduced.
- P1 dry-run/report only remains the sole active permission. P2/P3 and Phase 6 remain disabled and unauthorized.

## Verification

Tests are added in `tests/backend/test_plans.py` for immutability, strict schema rejection, all material-field digest binding, ordering, expiry, restart invalidation, clock rollback, tamper detection, and bounded capacity.

**No test or CI pass is claimed in this document until the corresponding GitHub Actions result is available.** The Product Owner must review the runtime diff and explicitly approve PR #63 before merge.

## Remaining integration

P5-512 supplies the backend plan/report contract and ephemeral reference store. P5-514 remains responsible for reconciling the existing chat/API route and Thai-default bilingual UI to this contract. P5-512 does not silently add that integration.
