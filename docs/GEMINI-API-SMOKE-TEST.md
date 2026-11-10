# Gemini 3.8 Flash API Smoke Test

This workflow verifies real access to the Gemini 3.8 Flash Developer API before changing the application's configured model.

## Run the test

1. Merge the PR that adds this workflow and script.
2. In GitHub, open **Actions → Gemini API Live Smoke Test**.
3. Select **Run workflow** on the default branch.
4. Open the run and inspect the **Call Gemini 3.8 Flash generateContent** step.

The workflow uses the existing repository Actions secret named `GEMINI_API_KEY`. It never prints the key, request headers, raw provider response, or arbitrary provider error messages.

## Time limits

- The Gemini SDK request has a 30-second HTTP timeout.
- The workflow step has a 2-minute timeout as a final guard.
- The whole job has a 5-minute timeout, including checkout and SDK installation.

A timeout is reported as a sanitized timeout failure instead of waiting for the job-level limit.

## Pass criteria

The run passes only when the Google Gemini Developer API accepts a real `generateContent` request for `gemini-3.8-flash` and the response contains the expected marker.

A passing run proves that this repository secret can call this model at that time. It does not by itself prove the local application's configuration, chat flow, or structured-plan request.

## Failure handling

- Missing secret: configure `GEMINI_API_KEY` in repository Actions secrets; do not paste it into an issue, PR, or chat.
- HTTP 401/403: inspect key validity, API restrictions, and project access.
- HTTP 404: inspect the model ID, API endpoint, and model availability for this key.
- HTTP 429: inspect quota and rate limits.
- Timeout: check API availability, network conditions, and provider latency; the request is capped at 30 seconds.
- Other failures: use the sanitized exception type/status from the run; do not expose credentials or raw response bodies.

Do not change the application's model until this live test passes. If it fails, keep the current application model and diagnose the reported category first.
