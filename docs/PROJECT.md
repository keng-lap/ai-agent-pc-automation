# Project Definition

## 1. Project Name
AI Agent PC Automation

## 2. Purpose
Build a personal AI Agent that receives commands from a local web application and safely performs explicitly approved automation tasks on a Windows 11 PC.

The intended flow is: understand the request, produce a plan, validate a controlled tool request, obtain required approval, execute only an authorized capability, and report the result.

## 3. Target Environment
- Windows 11 local machine
- Local web application (Angular)
- Backend API (Python / FastAPI)
- Git / GitHub
- Future AI provider integration only after explicit provider, account authorization, privacy/data-flow, and credential-storage decisions

## 4. Architecture
User -> Local Web App (loopback) -> Agent Core -> Controlled Tool / Task Layer -> Windows PC (only explicitly approved capabilities)

## 5. Core Requirements
1. Receive natural-language requests.
2. Analyze intent and produce an understandable plan.
3. Select only backend-allowlisted tools.
4. Validate tool inputs against backend-owned schemas.
5. Require explicit confirmation for sensitive operations under the approved safety design.
6. Report success/failure without exposing secrets.
7. Keep auditable records only under an explicitly approved retention policy.
8. Prevent unauthorized or dangerous operations.

## 6. Safety Requirements
The Agent must never have unrestricted control of the computer. All automation passes through a controlled tool/task layer. Sensitive operations include software installation/removal, file deletion/modification, administrator commands, process control, and system/network/security settings.

The approved P-ORDER-1 option A preserves phase order: machine-changing tools remain dry-run/mock until Phase 5 Safety and Permission System is implemented and explicitly approved. The separately approved T-601 Gemini chat flow may send bounded conversation context to Google; no provider call is used for policy, plan creation, audit, or tool dispatch. The Gemini API key is held in backend process memory and used only for provider authentication. Preserve loopback binding and local API authorization.

## 7. Development Philosophy
- Each phase has a clear objective, deliverables, tests, and safety boundary.
- Documentation/planning may proceed when consistent with approved decisions and current scope.
- Runtime changes require bounded tasks, tests, review, and explicit Product Owner merge approval.
- Never silently change requirements or skip a phase.

## 8. Four-Agent Workflow
The current Four-Agent workflow is coordinator-managed with four separated responsibilities: A1 Coordinator/Product Analyst, A2 Backend Engineer, A3 Frontend/UX Engineer, and A4 QA/Security Reviewer. It is not four autonomous LLM processes and no runtime orchestrator has been implemented. See docs/MULTI-AGENT-PLAN.md and docs/MULTI-AGENT-BOARD.md.

## 9. Source of Truth
Primary documents: README.md, docs/PROJECT.md, docs/ROADMAP.md, docs/PHASE-0.md through the active phase document, and docs/PROPOSALS.md for unapproved proposals only.

If sources conflict, stop and reconcile documentation before implementation. Proposals are not requirements until explicitly approved.

## 10. Current Status
**Phase 4 closeout approved 2026-11-02. P5-515 closeout was approved 2026-11-08. P5-516 A4 independent security review is complete (PR #107); follow-up fixes for F-516-02, F-516-03, and F-516-04 are merged (PRs #108–#110). F-516-01 direction is approved: Google OIDC sign-in plus authenticator-app TOTP (RFC 6238, QR enrollment) for high-risk step-up; paid SMS is rejected. The parallel workstream plan is merged (PR #112); implementation and independent A4 verification remain outstanding, and F-516-01 remains a hard prerequisite before any side-effecting capability. P5-517 approval-gated P1 Dry Run is merged. Phase 6 and real PC execution remain unauthorized.**

See docs/PHASE-4.md for Phase 4 closeout scope and docs/PHASE-5.md for the active safety-planning baseline. Phase 5 does not authorize real machine-changing execution; Phase 6 and each individual capability require separate authorization.
