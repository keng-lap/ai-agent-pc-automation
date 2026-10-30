# T-405 — Phase 4 QA and Security Matrix

## Purpose
Define verification coverage for Phase 4 Tool / Task System. This is a test plan, not a report of tests executed. No test result is claimed here.

## Threat model

| Threat | Example | Required control | Evidence |
|---|---|---|---|
| Tool ID injection | Client requests shell.run or unknown ID | Backend-owned closed allowlist; reject unknown ID | Unit/API negative test |
| Extra-field injection | Request adds command, args, executable, or script | Strict schema with extra=forbid | Pydantic validation test |
| Intent confusion | Install intent paired with remove tool | Intent-to-tool mapping validation | Unit test |
| Target substitution | Planner target differs from tool target | Backend compares normalized target | Unit test |
| Dynamic dispatch abuse | Request controls module/function/handler | Static mapping to fixed handlers | Source review + negative test |
| Execution-mode escalation | Request asks for real mode | Server-owned dry-run enforcement | Unit test |
| Handler side effects | Handler calls OS/process/network | Deterministic handler; AST/import scan | Source review + test |
| Task-state forgery | Client submits completed/executed state | State owned by backend, not client | API negative test |
| History leakage | Task/chat content written to storage | No persistence; inspect diff and code | Source review |
| Secret exposure | Token in browser bundle/log/commit | Server-only secret handling; scan assets/diff | Build and repository scan |
| Authorization regression | Missing token/origin accepted | Preserve T-306 controls | Security regression tests |
| Local network exposure | Server binds beyond loopback | Preserve loopback-only binding | Config/source review |

## Test matrix

| ID | Area | Test | Expected result | Priority |
|---|---|---|---|---|
| QA-401-01 | Catalog | Enumerate registered tools | Exactly software.install and software.remove unless separately approved | P0 |
| QA-401-02 | Schema | Unknown tool ID | Rejected; no handler called | P0 |
| QA-401-03 | Schema | Extra command/script/path fields | Rejected | P0 |
| QA-401-04 | Schema | Wrong primitive types / oversized target | Rejected | P0 |
| QA-401-05 | Validation | Intent/tool mismatch | Rejected | P0 |
| QA-401-06 | Validation | Target mismatch | Rejected | P0 |
| QA-401-07 | Dispatch | Unregistered handler | Fail closed; no dynamic import/fallback | P0 |
| QA-401-08 | Execution | Machine-changing tool invocation | Dry-run only; no side effect | P0 |
| QA-401-09 | Determinism | Repeat same request | Identical structured result | P1 |
| QA-401-10 | Task lifecycle | Valid transition | Accepted only when transition is defined | P0 |
| QA-401-11 | Task lifecycle | Illegal/client-forged state | Rejected | P0 |
| QA-401-12 | Persistence | Complete request then inspect writes | No chat/task history persistence | P0 |
| QA-401-13 | API compatibility | Existing chat request/response | Existing behavior preserved unless approved | P1 |
| QA-401-14 | Frontend | tool_result null | Clear no-allowlisted-tool state; no crash | P1 |
| QA-401-15 | Frontend | dry_run + approval_required | Clear labels; no real execution button | P0 |
| QA-401-16 | Localization | Thai default and English preference | Correct text and stable layout | P1 |
| QA-401-17 | Security | Missing/invalid local token or Origin | Existing security behavior preserved | P0 |
| QA-401-18 | Network | Bind address | Loopback only | P0 |
| QA-401-19 | Secrets | Production bundle/repository scan | No token or credentials exposed | P0 |
| QA-401-20 | Forbidden capability | Static source scan | No shell/process/network/OS inspection introduced | P0 |

## Test execution policy
- Add tests before or with implementation.
- Run focused unit tests for each task.
- Run full scripts/test.ps1 on Windows 11 before integration.
- Record exact commands, environment, outputs, and tests not run.
- A4 distinguishes Product Owner-supplied output from independently executed output.
- Report GitHub Actions checks only when actual status is available; absence is not a pass.

## A4 review checklist
- [ ] Contract matches implementation and docs.
- [ ] Allowlist is closed and backend-owned.
- [ ] No arbitrary command or dynamic handler selection.
- [ ] No path to real machine-changing behavior.
- [ ] No unapproved PC inspection or external network access.
- [ ] No provider integration or credential handling.
- [ ] No task/chat persistence.
- [ ] Loopback and local API authorization preserved.
- [ ] Frontend cannot bypass backend validation.
- [ ] Tests and limitations accurately reported.

## Exit criteria
T-405 completes only after implementation exists, tests have actually run, failures are resolved or documented, and A4 records source/diff review. This document alone marks no test as passed.
