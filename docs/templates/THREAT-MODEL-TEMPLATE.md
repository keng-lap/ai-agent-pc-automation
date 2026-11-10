# Threat Model — [Task ID / Feature]

- **Status:** Draft / Reviewed / Accepted
- **Author:**
- **Reviewer:**
- **Date:**
- **Base commit:**
- **Scope:**
- **Applicable decisions / phase documents:**

## 1. Intended behavior and non-goals
Describe intended outcome, exact components, and explicit exclusions.

## 2. Assets and security objectives
| Asset | Why it matters | Required protection |
|---|---|---|
| | | |

## 3. Actors and trust boundaries
| Actor/component | Trust level | Inputs/outputs | Boundary controls |
|---|---|---|---|
| | | | |

Include browser, backend, provider/model, local OS, filesystem, worker, scheduler, and external services where relevant.

## 4. Data-flow trace
Trace untrusted input through ingress, parsing, canonicalization, validation, identity, policy, approval, dispatch, side effect, verification, and audit. Identify every point where data or authority changes.

## 5. Threats and abuse cases
Use STRIDE where applicable. Include replay, TOCTOU, races, confused deputy, fail-open, clock rollback, restart/crash, partial failure, resource exhaustion, and privilege boundaries where relevant.

| ID | Threat / abuse case | Preconditions | Impact | Mitigation / invariant | Test ID | Residual risk |
|---|---|---|---|---|---|---|
| T-01 | | | | | | |

## 6. Security invariants
Write testable MUST/MUST NOT statements. Examples:
- An unapproved request MUST NOT invoke a side-effect handler.
- Authorization MUST apply to the exact canonical parameters later consumed.
- Missing or uncertain policy/audit state MUST fail closed.

## 7. Design decisions
| Decision | Chosen design | Alternatives rejected | Reason |
|---|---|---|---|
| | | | |

## 8. Verification plan
| Test ID | Positive / negative / boundary / failure | Expected result | Evidence / runner |
|---|---|---|---|
| | | | |

Include proof denied paths make zero side-effect handler calls. Identify native Windows/platform tests that mocks cannot replace.

## 9. Privacy, logging, and retention
Specify collected data, redaction, output bounds, storage location/ACL, retention, and failure behavior. Do not add persistence or external data flows without approval.

## 10. Residual risks and decisions required
| Risk | Severity / confidence | Compensating control | Owner | Expiry / revisit trigger |
|---|---|---|---|---|
| | | | | |

## 11. Review disposition
- [ ] Scope and source-of-truth decisions reconciled
- [ ] Trust boundaries and data flow reviewed
- [ ] Threats and abuse cases covered
- [ ] Security invariants are testable
- [ ] Negative tests are defined
- [ ] Platform-specific evidence is identified
- [ ] Residual risks and approvals are explicit
- **Disposition:** APPROVED / CHANGES REQUIRED / BLOCKED
- **Reviewer rationale:**
