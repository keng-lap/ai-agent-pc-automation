# Phase 4 — Tool / Task System

## Status
Planning baseline completed and merged; runtime implementation not started. Phase 3 closeout was approved by the Product Owner on 2026-10-30. The Product Owner has authorized Phase 4 planning. This plan does not authorize real PC actions, provider integration, or changes to the Phase 5 safety gate.

## Objective
Build a predictable, backend-controlled Tool / Task layer that accepts only typed, allowlisted tool requests, validates them, produces deterministic dry-run results, and exposes understandable task/tool status to the local web UI.

The existing Phase 3 software.install and software.remove paths are already allowlisted and dry-run-only. Phase 4 should formalize the framework around those paths, not duplicate them or silently enable real execution.

## Approved constraints
- Preserve phase order (P-ORDER-1, option A).
- Any tool capable of changing the PC remains dry-run/mock only until Phase 5 Safety and Permission System is implemented and explicitly approved.
- No arbitrary shell, PowerShell, command strings, subprocess execution, or raw model output execution.
- No live AI provider, provider sign-in, credentials, external data transfer, or model calls.
- No PC inspection, installed-software discovery, filesystem reads/writes, process inspection, or system-setting access unless separately proposed, risk-reviewed, and explicitly approved.
- Preserve loopback binding and existing local API authorization.
- Do not persist chat messages, chat history, or task history. D-API-2 permits only language preference persistence.
- Thai is the default UI language; bilingual Thai/English remains the target.
- Branch convention for every task, including docs: <type>/<task-id>-<short-name>.
- Documentation/planning may proceed when internally consistent with approved decisions. Runtime behavior changes require a separately reviewed task scope.
- Product Owner approval remains required before merging code/runtime changes and for any change to an approved decision or safety boundary.

## Current implementation baseline
Phase 3 backend currently has:
- ToolId allowlist: software.install and software.remove.
- ToolStatus: dry_run.
- Strict typed ToolRequest and ToolResult models.
- Intent-to-tool selection and request validation.
- Deterministic execute_tool dry-run behavior.
- Planner task plans with execution_mode=dry_run.
- Tests rejecting unknown tools, extra/arbitrary command payloads, category/target mismatch, and asserting dry-run behavior.

Phase 4 must inspect and reuse these contracts before proposing changes. No new tool capability is approved by this plan.

## In scope
1. Formalize tool contract and catalog metadata for currently approved dry-run tools.
2. Centralize allowlist lookup, request validation, and deterministic dispatch behind a narrow interface.
3. Define an in-memory task lifecycle/status contract for a single local request; no persistent task/chat history.
4. Present tool selection, validation outcome, dry-run preview, and approval-required status clearly in Thai-default bilingual UI.
5. Add QA/security coverage for fail-closed behavior, invalid payloads, deterministic outputs, and absence of side effects.
6. Document rules for future tool additions.

## Explicitly out of scope
- Real software installation/removal.
- Arbitrary shell, PowerShell, command prompt, script, or process execution.
- Real file, registry, process, application, network, or system-setting access/modification.
- Read-only machine discovery or inspection until separately approved.
- AI-provider selection/integration, live model calls, account sign-in, credentials, or external data transfer.
- Persistent task history, chat history, message storage, or background task queue.
- Multi-agent runtime/orchestrator implementation.
- Phase 5 permission grants, approval tokens, privileged execution, or audit-log system under another name.
- Any change to loopback binding or local API authorization.

## Proposed task breakdown and dependencies
| Task | Owner | Deliverable | Depends on | Gate |
|---|---|---|---|---|
| T-401 Tool contract/catalog | A1 + A2; A4 review | Document metadata for existing tools: stable ID, description, intent, input/output schema, risk class, execution mode, approval-required flag | Phase 3 baseline | Planning contract merged; implementation scope still requires review |
| T-402 Registry and dispatch | A2; A4 review | Central registry, validation, deterministic dispatch; preserve allowlist and dry-run behavior | T-401 | Read-only gap analysis merged; implementation pending scoped review |
| T-403 Task lifecycle | A1 + A2; A4 review | Request-scoped in-memory states and transitions; no database, background worker, or history persistence | T-401; coordinate with T-402 API | Lifecycle contract merged; implementation pending API decision |
| T-404 Frontend status UX | A3; A4 review | Display selected tool, validation, dry-run preview, approval-required state; Thai default, English option | T-401 and stable T-402/T-403 API | UX specification merged; frontend source inspection/API stability still required |
| T-405 QA/security matrix | A4 | Tests/checklist for allowlist, schemas, unknown tools, malformed requests, deterministic dry-run, status transitions, no side effects | T-401 and implementation as available | Threat model and test matrix merged; execution evidence pending implementation |
| T-406 Integration/closeout | A1 + A4 | Reconcile docs, dependencies, test evidence, Phase 4 closeout recommendation | T-402 through T-405 | Product Owner reviews closeout |

## Parallel planning outputs merged
- PR #40 — T-401 tool contract/catalog: docs/T-401-TOOL-CONTRACT.md.
- PR #41 — T-402 backend gap analysis: docs/T-402-BACKEND-GAP-ANALYSIS.md.
- PR #42 — T-403 request-scoped lifecycle contract: docs/T-403-TASK-LIFECYCLE-CONTRACT.md.
- PR #43 — T-404 tool/task UX specification: docs/T-404-TOOL-TASK-UX-SPEC.md.
- PR #44 — T-405 QA/security matrix: docs/T-405-QA-SECURITY-MATRIX.md.

These PRs completed the documentation/planning outputs only. No Phase 4 runtime implementation has been merged and no Phase 4 runtime tests are claimed.

## Parallel work plan
- A1 finalizes T-401/T-403 contracts and dependencies.
- A2 performs a read-only source gap analysis in parallel; implementation begins only after T-401 is stable.
- A3 prepares UX flow notes against current dry-run behavior; integration waits for stable API contracts.
- A4 prepares threat model and test matrix in parallel; assertions trace to approved contracts.
- Each task has separate branch/file ownership. Integrate in dependency order.
- Four roles are coordinator-managed workflow roles, not four autonomous LLM processes.

## Acceptance criteria
1. Catalog contains only explicitly approved tool IDs and accurately describes capabilities.
2. Every request is validated against backend-owned schemas; unknown tools, extra fields, malformed payloads, and mismatched intent/target fail closed.
3. Dispatch cannot route to arbitrary commands or unregistered handlers.
4. All machine-changing paths return dry-run/mock results and tests prove no side effects.
5. Task lifecycle states/transitions are deterministic, request-scoped, and do not persist chat/task history.
6. UI distinguishes planned, validation-failed, dry-run, and approval-required states; Thai is default and English is available where feasible.
7. Backend/frontend tests cover success, invalid inputs, unknown tools, errors, and regressions; execution evidence is recorded.
8. Security review confirms loopback and local API authorization remain intact; no secrets enter frontend assets/logs/repository; no provider/external data path is added.
9. Documentation, board, and roadmap reflect merged implementation and limitations.
10. Product Owner explicitly approves Phase 4 closeout before any later phase starts.

## Definition of done
- Bounded task scope, owner, dependencies, acceptance criteria, and risk statement.
- Branch follows the repository convention.
- Changes stay within approved scope.
- Tests are added/updated and run; unrun checks are marked pending.
- A4 reviews source, diff, tests, and safety impact.
- PR records changes, evidence, limitations, and safety impact.
- No code/runtime PR is merged without explicit Product Owner approval.

## Open decisions
- Representation of catalog metadata (constants, typed objects, or another small internal form).
- Exact task lifecycle vocabulary and API representation.
- Compact timeline vs simple status panel.
- Any future read-only discovery tools.
- Any future real execution design, which belongs behind Phase 5 and later explicit approvals.

These decisions are not silently selected by this plan.
