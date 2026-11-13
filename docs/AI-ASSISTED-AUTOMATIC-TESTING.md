# AI-Assisted Automatic Testing

**Status:** Proposed workflow for Product Owner review. This document defines how repository coding agents must create and validate tests; it does not add a runtime AI service or authorize new external data flows.

## Objective

Make test design a required part of every code change. AI coding agents should proactively derive tests from requirements and diffs, implement missing tests, run the real test commands, diagnose failures, and report evidence before opening or updating a PR.

AI is the test author and failure analyst, not the authority that declares software correct. Test-runner and CI results are authoritative.

## Operating model

1. **Read the contract.** Read the task, acceptance criteria, applicable decisions, threat model, and existing tests. Identify changed behavior and invariants.
2. **Build a test-impact map.** Map each changed function/API/UI flow to existing tests and uncovered behavior. Include callers, error paths, permissions, persistence, and platform-specific code where relevant.
3. **Write the test plan before implementation.** Select applicable categories:
   - positive / expected behavior;
   - negative / rejection behavior;
   - boundary and malformed input;
   - regression for each known defect or security finding;
   - authorization and trust-boundary abuse cases;
   - concurrency, timeout, retry, restart, and failure injection for lifecycle code;
   - frontend interaction, accessibility-relevant state, and end-to-end flows where applicable.
4. **Generate or update tests.** Prefer the smallest deterministic tests at the lowest useful layer. Reuse project fixtures and conventions. Use synthetic data, mocks, spies, and isolated temporary directories. Never touch the user's live Windows machine.
5. **Check test quality.** Every test must assert an observable requirement, not merely execute code. Avoid tautological assertions, tests that duplicate implementation logic, brittle timing, hidden network dependencies, and assertions weakened only to make a change pass. For a security rejection, assert the side-effect handler was called zero times.
6. **Run tests.** Run focused tests first, then all applicable checks required by the PR/CI. Run the full relevant suite before declaring the change ready. Do not silently skip, xfail, quarantine, or delete a failing test to obtain a green result.
7. **Analyze failures.** Separate product defects, test defects, environment failures, and flaky tests. Show the exact failing test and evidence. Fix the root cause; preserve the original acceptance criteria and test strength. Re-run the failed test and the broader relevant suite after a fix.
8. **Review the diff.** Inspect production code and tests together. Confirm each acceptance criterion maps to evidence and that no unrelated change, secret, unsafe behavior, or test weakening was introduced.
9. **Report evidence.** Record exact commands, exit status, test counts where available, CI run/job links, and checks not run. Use only PASS, FAIL, PENDING, and NOT VERIFIED.

## Automation levels

### Level 1 — Required now: AI-assisted PR testing

For every code PR, the coding agent must:
- produce a test-impact map and test plan;
- add/update tests in the same task branch;
- run the relevant local checks when the environment is available;
- inspect CI after pushing/opening the PR;
- diagnose failures and propose/fix in-scope causes;
- report any check that cannot be run as NOT VERIFIED.

This level uses the already-approved coding assistant and repository CI. It does not require a new AI API integration, provider, secret, or code upload destination.

### Level 2 — Candidate future enhancement: AI review on PR

A future GitHub Actions job may send a bounded PR diff, test metadata, and relevant requirements to an AI provider to identify missing test cases and produce a review report. This is **not enabled by this document**. Before implementation, obtain explicit approval for the provider, credentials, data categories, retention, external destination, cost limits, prompt-injection controls, and failure behavior. The AI job must be advisory; deterministic CI remains the merge gate.

### Level 3 — Candidate future enhancement: test repair agent

Automatic code/test edits in response to CI failures are not enabled. Any future repair agent must work on an isolated branch/worktree, use an allowlisted command runner, have bounded retries and resource limits, preserve test assertions, expose its complete diff, and require human review before merge. It must never install software, alter system settings, access secrets, or run arbitrary commands on the user's PC.

## Required PR evidence

Every code PR should include:

| Evidence | Required result |
|---|---|
| Test-impact map | Changed behavior mapped to tests |
| Test plan | Positive, negative, boundary, and regression cases as applicable |
| Focused tests | Exact command and result |
| Full relevant suite | Exact command and result |
| Static checks/build | Exact command and result |
| CI | Each required job completed successfully, or explicitly PENDING/FAIL |
| Test integrity | No weakened/deleted/skipped assertions without explicit justification and review |
| Gaps | Platform/environment checks not run, clearly marked NOT VERIFIED |

## Rules that prevent false-green results

- A generated test passing does not prove the requirement is correct; verify the expected result against the acceptance criteria or an independent oracle.
- Do not change expected values, remove assertions, broaden mocks, add skip markers, or lower thresholds solely to make tests pass.
- Do not let the same AI claim that its own code and tests are independently certified.
- Never claim tests ran based on reading workflow YAML or seeing a previous commit's green badge.
- A queued or in-progress CI job is PENDING, not PASS.
- A successful mock test is not evidence of native Windows behavior; the relevant Windows CI runner is required.
- If no reliable test oracle or safe test environment exists, report BLOCKED or NOT VERIFIED rather than inventing confidence.

## Scope boundary

This workflow improves test design and execution discipline. It does not authorize real PC-changing operations, new providers, external AI review services, persistent test telemetry, broad repository uploads, or autonomous merging. Existing secure-development, capability approval, and Product Owner gates remain authoritative.
