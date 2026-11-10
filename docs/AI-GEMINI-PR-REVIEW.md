# Gemini AI Pull Request Test Review

Status: Approved for implementation by the Product Owner on 2026-11-10. Advisory only.

## Workflow
1. A minimal pull_request workflow receives PR open/update events with empty token permissions; it does not check out or execute PR content.
2. A separate workflow_run workflow runs from the trusted default branch after that trigger completes.
3. The trusted reviewer fetches changed-file patches through the GitHub API, filters eligible source/test/workflow files, redacts common secret formats, and applies strict limits.
4. It sends one bounded request to Google Gemini API using the same `gemini-3.1-flash-lite` model as the local application's Gemini provider.
5. The result is written to the GitHub Actions run summary. It does not post PR comments, create checks, modify files, run generated commands, or merge.

## Trust boundaries
- The privileged workflow_run job never checks out the PR head, downloads PR artifacts, installs PR dependencies, or executes PR code.
- The low-trust trigger has no token permissions and no secrets.
- The trusted job uses only actions: read, contents: read, and pull-requests: read.
- The Gemini API key is available only to the trusted review step and is sent in the x-goog-api-key header, never in the prompt or logs.
- PR diff text is untrusted input. The prompt treats it as data, not instructions. Model output is escaped and bounded before appearing in the run summary.
- Gemini output is advisory. It cannot satisfy deterministic CI, certify security, change tests, run commands, write to GitHub, or approve/merge a PR.
- Gemini/API failures do not fail or weaken deterministic CI. The separate AI review workflow reports provider/network failures as a failed AI-review job so the status is not confused with a successful review.

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
4. Create a new Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey). Prefer the current authorization-key type and restrict it to the Gemini API.
5. Name the GitHub secret GEMINI_API_KEY and paste the key as its value.

The key is not committed and cannot be configured by this workflow. If absent, the review is reported as SKIPPED. Monitor usage and quotas in AI Studio.

## Failure reporting
- HTTP failures are reported with the HTTP status, provider code/status/message, and a small allowlist of structured detail identifiers; arbitrary metadata, response headers, credentials, and raw bodies are never printed.
- Network failures and malformed/unexpected responses receive distinct GEMINI_NETWORK_ERROR or GEMINI_REVIEW_ERROR statuses.
- A Gemini API or network failure exits the AI-review step unsuccessfully. This marks only the separate advisory AI-review workflow as failed; it does not change deterministic CI results or merge requirements.
- A failed AI-review job is not evidence that the PR's deterministic tests failed. Conversely, a successful job is only meaningful when its summary contains a Gemini review, not SKIPPED or an error status.

## Limits
- The first associated PR is reviewed; unusual runs associated with multiple PRs are not expanded into multiple paid requests.
- GitHub may omit patches for large/binary files; these are counted, not fetched as full files.
- Redaction is heuristic and cannot guarantee detection of every secret format.
- The reviewer does not execute tests and cannot certify generated suggestions.
- The report is in the Actions run summary, not a PR comment. This preserves read-only GitHub permissions.
- The reviewer model is `gemini-3.1-flash-lite`, intentionally aligned with `src/backend/agent_backend/providers/gemini.py` so the app and GitHub Actions exercise the same Gemini model. The reviewer still uses the documented Gemini Developer API REST `generateContent` endpoint; the app uses the Google `google-genai` SDK.
- The Gemini 3.5 request omits deprecated sampling parameters such as `temperature`, `top_p`, and `top_k`.
- Model and endpoint changes require reviewed repository changes.

## References
- Google Gemini models: https://ai.google.dev/gemini-api/docs/models
- Gemini 3.5 Flash-Lite migration: https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6
- Google Gemini API: https://ai.google.dev/api/generate-content
- GitHub secure use: https://docs.github.com/en/actions/reference/security/secure-use
