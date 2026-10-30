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

The approved P-ORDER-1 option A preserves phase order: machine-changing tools remain dry-run/mock until Phase 5 Safety and Permission System is implemented and explicitly approved. No live provider calls, provider credentials, or external data transfer are currently approved. Preserve loopback binding and local API authorization.

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
**Phase 3 closeout approved 2026-10-30. Phase 4 planning authorized; runtime implementation not started.**

See docs/PHASE-3-QA-REVIEW.md for closeout evidence and docs/PHASE-4.md for the active planning baseline. Phase 4 implementation tasks must follow dependencies and safety gates. Phase 5 remains mandatory before any real machine-changing execution.
