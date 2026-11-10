# Gemini AI Pull Request Test Review

Status: Approved for implementation by the Product Owner on 2026-11-10. Advisory only.

## Workflow
1. A minimal pull_request workflow receives PR open/update events with empty token permissions; it does not check out or execute PR content.
2. A separate workflow_run workflow runs from the trusted default branch after that trigger completes.
3. The trusted reviewer fetches changed-file patches through the GitHub API, filters eligible source/test/workflow files, redacts common secret formats, and applies strict limits.
4. It sends one bounded request to Google Gemini API using gemini-2.5-flash.
5. The result is written to the GitHub Actions run summary. It does not post PR comments, create checks, modify files, run generated commands, or merge.

## Trust boundaries
- The privileged workflow_run job never checks out the PR head, downloads PR artifacts, installs PR dependencies, or executes PR code.
- The low-trust trigger has no token permissions and no secrets.
- The trusted job uses only actions: read, contents: read, and pull-requests: read.
- The Gemini API key is available only to the trusted review step and is sent in the x-goog-api-key header, never in the prompt or logs.
- PR diff text is untrusted input. The prompt treats it as data, not instructions. Model output is escaped and bounded before appearing in the run summary.
- Gemini output is advisory. It cannot satisfy deterministic CI, certify security, change tests, run commands, write to GitHub, or approve/merge a PR.
- Gemini/API failures do not fail or weaken existing CI.

## Data minimization
- Only patches for selected source, test, and workflow extensions are considered.
- Sensitive path components, environment files, lockfiles, and non-reviewable files are excluded.
- Common private-key/token formats and secret-like assignments are redacted before transmission.
- At most 20 files and 28,000 patch characters are sent; individual patches are capped at 4,000 characters.
- The workflow does not send repository history, full files, test logs, artifacts, issue comments, PR descriptions, or secrets.
- Redaction is heuristic, not a guarantee. Do not add credentials or personal data to source diffs.

## Configure the API key
A repository administrator must add a GitHub Actions repository secret:
1. Open repository Settings.
2. Go to Secrets and variables → Actions.
3. Select New repository secret.
4. Name it GEMINI_API_KEY and paste the Google AI Studio Gemini API key as the value.

The key is not committed and cannot be configured by this workflow. If absent, the review is reported as SKIPPED.

## Limits
- The first associated PR is reviewed; unusual runs associated with multiple PRs are not expanded into multiple paid requests.
- GitHub may omit patches for large/binary files; these are counted, not fetched as full files.
- Redaction is heuristic and cannot guarantee detection of every secret format.
- The reviewer does not execute tests and cannot certify generated suggestions.
- The report is in the Actions run summary, not a PR comment. This preserves read-only GitHub permissions.
- Model and endpoint changes require reviewed repository changes.

## References
- Google Gemini API: https://ai.google.dev/api/generate-content
- GitHub secure use: https://docs.github.com/en/actions/reference/security/secure-use
