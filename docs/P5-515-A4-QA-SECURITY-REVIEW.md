# P5-515 — A4 QA / Security Review

## Review status

**Focused review completed for the merged P5-515 increments #66, #73, #74, and #75.** This is the A4 QA/security review lane required for P5-515 evidence reconciliation. It is not P5-516, not a third-party penetration test, and not approval for real PC execution.

## Review scope

Reviewed the merged source/test changes and their traceability claims for:

- API boundary negative/abuse tests and P1 dry-run-only behavior (PR #66).
- Static source-level audit-sink transport/telemetry checks and bounded test-harness capability checks (PR #73).
- Handler identity replacement protection between policy decision and final dispatch (PR #74).
- API-safe planner, policy-configuration, and handler exception behavior (PR #75).
- Corresponding Q13, Q23, Q27, Q34, and Q35 entries in `P5-515-MATRIX-TRACEABILITY.md`.

## Evidence reviewed

| Increment | Merge commit | CI run | Result |
|---|---|---|---|
| PR #66 | `3d661d7e56c431722abf5dd3c0aae23e631c546e` | #42355435380 | Passed |
| PR #73 | `1a4f3a5024bb3ae7f4e9298284ef87d7bcee75a9` | #42357992572 | Passed |
| PR #74 | `eb6e858ad17a3224b3c1f75fcce80bc4e9bc8efe` | #42358505456 | Passed |
| PR #75 | `2f512559bc32221b2559514e94b252036f2a0582` | #42358957033 | Passed |

PR #75 had an earlier failed run (#42358655824) because TestClient re-raised application exceptions. The tests were changed to use `raise_server_exceptions=False`; the updated head passed all four CI steps. The failed run is retained in the verification evidence for transparency.

## Findings

### F1 — Handler identity is checked at the dispatch boundary

**Result: Satisfactory for the tested in-process threat scenario.**

The dispatch path pins the code-owned handler table and selected callable before policy evaluation, then checks both identities again before invocation. The regression test replaces the table after the policy decision and verifies that neither the original nor replacement spy handler is invoked. The failure mode is closed with `handler_unavailable`.

This evidence supports Q13 as Covered. It does not establish protection against arbitrary hostile code already executing in the Python process; that is outside the declared threat boundary.

### F2 — Unexpected planner and handler failures do not expose exception messages or retry

**Result: Satisfactory for the tested API scenarios.**

Synthetic planner and handler exceptions are exercised through the in-process API client. Tests assert a generic `500 Internal server error.` response and call counts of one. A synthetic policy-configuration exception returns the same generic response and a spy confirms that no tool handler is invoked.

This evidence supports Q34 as Covered. Q23 remains Partial because malformed handler return values are not yet directly exercised through the API boundary, even though normal dispatch result validation has separate tests.

### F3 — Audit and test-harness capability checks are static, bounded checks

**Result: Satisfactory within the stated source-level scope; do not interpret as sandbox proof.**

The audit-sink test checks selected external telemetry/transport imports and outbound-call names and exercises the in-process sink record/snapshot path. The test-harness audit checks selected Python imports and OS calls plus selected frontend Node host/network imports.

These are static source checks, not a runtime sandbox. They cannot prove absence of indirect, dynamically loaded, unlisted, or transitive capabilities. Q27 is Covered for the explicitly tested source-level conditions; Q35 correctly remains Partial.

### F4 — Remaining matrix gaps are still visible

**Result: Open; no silent closure recommended.**

The reconciled matrix records 22 Covered and 13 Partial items. Remaining Partial items are Q02, Q09–Q12, Q16, Q20, Q23, Q25–Q26, Q28, and Q30–Q31. Their qualifications must remain visible. Any new expected policy, retention rule, or user-consent behavior must be confirmed against existing Product Owner decisions rather than inferred by tests.

## Safety boundary confirmation

The reviewed increments use synthetic inputs, mocks/spy handlers, fake data, static source inspection, and in-process clients. No Windows host operation, OS command, process inspection, registry access, real installer, package manager, filesystem mutation, network-setting change, or real machine-changing action is used or authorized.

P1 remains dry-run/report only. P2/P3 and Phase 6 remain disabled. P5-516 remains a separate task requiring its own explicit Product Owner authorization.

## Review conclusion

**No blocking defect was identified within the narrow scope of the merged P5-515 increments reviewed above.** Q13 and Q34 traceability claims are supported by direct tests. Q23 and Q35 remain Partial with explicit limitations. This review does **not** declare P5-515 complete: the 13 remaining Partial items require further evidence or an explicit Product Owner deferral, followed by explicit P5-515 closeout approval.

This review is a separate QA/security pass by the A4 lane in the current project workflow. It is not represented as an independent external auditor or as the separately gated P5-516 review.
