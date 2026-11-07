# P5-515 — A4 QA / Security Review

## Review status

**Focused review completed for the merged P5-515 increments #66, #73, #74, #75, and #77.** This is the A4 QA/security review lane required for P5-515 evidence reconciliation. It is not P5-516, not a third-party penetration test, and not approval for real PC execution.

## Review scope

Reviewed the merged source/test changes and their traceability claims for:

- API boundary negative/abuse tests and P1 dry-run-only behavior (PR #66).
- Static source-level audit-sink transport/telemetry checks and bounded test-harness capability checks (PR #73).
- Handler identity replacement protection between policy decision and final dispatch (PR #74).
- API-safe planner, policy-configuration, and handler exception behavior (PR #75).
- Corresponding Q13, Q20, Q23, Q27, Q34, and Q35 entries in `P5-515-MATRIX-TRACEABILITY.md`.

## Evidence reviewed

| Increment | Merge commit | CI run | Result |
|---|---|---|---|
| PR #66 | `3d661d7e56c431722abf5dd3c0aae23e631c546e` | #42355435380 | Passed |
| PR #73 | `1a4f3a5024bb3ae7f4e9298284ef87d7bcee75a9` | #42357992572 | Passed |
| PR #74 | `eb6e858ad17a3224b3c1f75fcce80bc4e9bc8efe` | #42358505456 | Passed |
| PR #75 | `2f512559bc32221b2559514e94b252036f2a0582` | #42358957033 | Passed |\n| PR #77 | `2ad52b2045f0b7927935d44dae8161ce9369939b` | #42359381703 | Passed |

PR #75 had an earlier failed run (#42358655824) because TestClient re-raised application exceptions. The tests were changed to use `raise_server_exceptions=False`; the updated head passed all four CI steps. The failed run is retained in the verification evidence for transparency.

## Findings

### F1 — Handler identity is checked at the dispatch boundary

**Result: Satisfactory for the tested in-process threat scenario.**

The dispatch path pins the code-owned handler table and selected callable before policy evaluation, then checks both identities again before invocation. The regression test replaces the table after the policy decision and verifies that neither the original nor replacement spy handler is invoked. The failure mode is closed with `handler_unavailable`.

This evidence supports Q13 as Covered. It does not establish protection against arbitrary hostile code already executing in the Python process; that is outside the declared threat boundary.

### F2 — Unexpected planner and handler failures do not expose exception messages or retry

**Result: Satisfactory for the tested API scenarios.**

Synthetic planner and handler exceptions are exercised through the in-process API client. Tests assert a generic `500 Internal server error.` response and call counts of one. A synthetic policy-configuration exception returns the same generic response and a spy confirms that no tool handler is invoked.

This evidence supports Q34 as Covered. Q23 is now Covered after PR #77 added a synthetic malformed handler return value through the API boundary, asserting a generic HTTP 500 response and exactly one handler invocation (no retry).

### F3 — Audit and test-harness capability checks are static, bounded checks

**Result: Satisfactory within the stated source-level scope; do not interpret as sandbox proof.**

The audit-sink test checks selected external telemetry/transport imports and outbound-call names and exercises the in-process sink record/snapshot path. The test-harness audit checks selected Python imports and OS calls plus selected frontend Node host/network imports.

These are static source checks, not a runtime sandbox. They cannot prove absence of indirect, dynamically loaded, unlisted, or transitive capabilities. Q27 is Covered for the explicitly tested source-level conditions; Q35 correctly remains Partial.

### F4 — Remaining matrix gaps are still visible

**Result: Open; no silent closure recommended.**

The reconciled matrix after WP1–WP4 records 33 Covered and 2 Partial items. Remaining Partial items are Q30 and Q35. Their qualifications must remain visible. Any new expected policy, retention rule, or user-consent behavior must be confirmed against existing Product Owner decisions rather than inferred by tests.

## Safety boundary confirmation

The reviewed increments use synthetic inputs, mocks/spy handlers, fake data, static source inspection, and in-process clients. No Windows host operation, OS command, process inspection, registry access, real installer, package manager, filesystem mutation, network-setting change, or real machine-changing action is used or authorized.

P1 remains dry-run/report only. P2/P3 and Phase 6 remain disabled. P5-516 remains a separate task requiring its own explicit Product Owner authorization.

## Review conclusion

**No blocking defect was identified within the narrow scope of the merged P5-515 increments reviewed above.** Q13, Q20, Q23, and Q34 traceability claims are supported by direct tests. Q35 remains Partial with explicit static-check limitations. This review does **not** declare P5-515 complete: the 2 remaining Partial items (Q30 and Q35) require further evidence or an explicit Product Owner disposition, followed by explicit P5-515 closeout approval.

This review is a separate QA/security pass by the A4 lane in the current project workflow. It is not represented as an independent external auditor or as the separately gated P5-516 review.


## Follow-up review — PR #77

A focused follow-up review was performed against the merged PR #77 tests and its successful GitHub Actions run [#42359381703](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/42359381703).

- **Q20:** The fake-clock test asserts the plan remains available one microsecond before expiry and is rejected exactly at `expires_at`. The test then verifies the expired plan reference is no longer available. This supports Q20 as Covered for the exact TTL boundary behavior.
- **Q23:** A synthetic handler returns an invalid object through the in-process API test client. The test asserts the API returns only the generic 500 response and that the handler call count is exactly one. This supports Q23 as Covered for exception and malformed-result API response behavior.
- **Safety:** Both tests are deterministic and in-process. No Windows host calls, filesystem changes, process execution, real network calls, installers, or machine-changing operations are used.

The updated matrix after all WP1–WP4 merges records **33 Covered / 2 Partial / 0 Not covered or not evidenced**. Q26 is Covered after reconciliation to the approved P5-508 option A retention decision: bounded in-memory events, maximum 500, oldest-first eviction, and clear-on-restart. Existing tests directly cover those behaviors. Time-based event expiry and durable storage are not approved requirements and were not added. Remaining Partial items are Q30 and Q35. This follow-up does not declare P5-515 complete; remaining gaps still require evidence or explicit Product Owner disposition. P5-516 remains separately gated.


## Follow-up review — Q26 retention semantics

A4 compared the Q26 matrix wording against the approved P5-508 decision register and the existing audit implementation/tests. The approved option A is bounded ephemeral in-memory events, cleared on process restart; the implementation additionally fixes the capacity at a maximum of 500 and evicts the oldest event first. Existing tests cover the 500-event default, FIFO eviction, and a new empty sink after restart.

The earlier matrix wording “retention cap/expiry/restart” incorrectly implied that a time-based event TTL was required. It is not part of the approved option A decision. Q26 is therefore **Covered** with the explicit qualification that time-based expiry and durable storage are not required or authorized. No new TTL or durable persistence was implemented.


## Follow-up review — WP1–WP4 merged increments (#81, #82, #84, #85)

A4 reviewed the exact merged diffs and successful CI/CodeQL evidence for the four increments:

- WP1 / PR #85 — Q02, Q09–Q12: arbitrary extra fields are rejected on plan creation and refinement; malformed policy matrix containers, entries, and field types fail closed; duplicate risk is rejected; client/model-supplied authority claims are rejected; synthetic P2/P3 policy branches deny before spy handlers run. The P2/P3 tests deliberately isolate the decision branch by bypassing the configuration-consistency validator in the test only. The production catalog remains unchanged, with no P2/P3 handler or route.
- WP2 / PR #81 — Q16: strict type, size, numeric/order, dependency and tool-request boundaries are tested, including exact accepted upper bounds. Tests are model/validation boundary tests, not host actions.
- WP3 / PR #82 — Q25: a synthetic optional audit sink raises OSError; the optional record call returns false, retains no event, and the safe path continues. No external fallback, durable storage, or TTL is added.
- WP4 / PR #84 — Q28 and Q31: nested plan response validation rejects unknown status/missing required fields into a neutral UI error; machine-changing controls are inventoried across empty, loading, error, clarification-plan and restored states. No approval or execution controls were added.

The matrix now records **33 Covered / 2 Partial / 0 Not covered or not evidenced**. Q30 remains Partial because Vitest/jsdom does not provide a real browser layout engine or full screen-reader evidence. Q35 remains Partial because static source-level checks are not a runtime sandbox and cannot prove the absence of indirect/dynamic capabilities.

**Result: WP1–WP4 review complete; P5-515 remains open.** No blocking defect was identified within the narrow synthetic/in-process scope reviewed. Q30 and Q35 require further bounded evidence or explicit Product Owner disposition, followed by a separate explicit P5-515 closeout decision. P5-516 remains separately gated.

