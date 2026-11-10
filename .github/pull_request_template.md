## Summary

<!-- What changes and why? -->

## Scope and authorization
- Task / milestone:
- Governing phase and decision documents:
- Explicit non-goals:
- Product Owner authorization (if required):

## Security design
- [ ] No security-sensitive behavior changed
- [ ] Threat model completed: docs/templates/THREAT-MODEL-TEMPLATE.md
- [ ] Trust boundaries and data flows reviewed
- [ ] Security invariants and fail-closed behavior documented
- [ ] No arbitrary command execution, dynamic handler selection, or unapproved data flow introduced
- [ ] Capability remains Dry Run unless separately authorized

## Tests and evidence
- [ ] Positive tests
- [ ] Negative / abuse tests
- [ ] Boundary and regression tests
- [ ] Denied paths proven not to reach side-effect handlers
- [ ] Relevant Windows/platform-specific tests
- [ ] Lint / format
- [ ] Backend tests
- [ ] Frontend tests/build (if applicable)
- [ ] Configured security / dependency / secret checks

Commands actually run and results:

| Check | Command / CI job | Result (PASS / FAIL / PENDING / NOT VERIFIED) | Evidence |
|---|---|---|---|
| | | | |

## Review and residual risk
- Independent reviewer:
- Findings and disposition:
- Residual risks / accepted exceptions:
- Checks not run and why:

## Product Owner gate
- [ ] Runtime changes are not merged without explicit Product Owner approval
- [ ] No real machine-changing capability is enabled by this PR unless separately approved
