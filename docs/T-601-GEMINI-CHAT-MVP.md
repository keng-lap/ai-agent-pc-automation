# T-601 — Gemini Chat MVP

## Product Owner authorization

Authorized by the Product Owner on 2026-11-03. This is a bounded provider integration exception and does not authorize PC automation, Phase 5 runtime work, or any broader data flow.

## User experience

1. Open the Gemini settings panel in the local web app.
2. Paste a Gemini API key and select Save.
3. Select Test Connection to make a real Gemini API request.
4. Send a message in Chat and display Gemini's text reply.

## API and model

- Provider: Google Gemini Developer API.
- Python SDK: `google-genai`.
- SDK call: `client.models.generate_content(model="gemini-3.1-flash-lite", contents=message)`.
- Model: `gemini-3.1-flash-lite`.
- Official SDK documentation: https://googleapis.github.io/python-genai/
- API key guidance: https://ai.google.dev/gemini-api/docs/api-key
- Pricing and tier terms: https://ai.google.dev/gemini-api/docs/pricing

## Data boundary

- Only the current message text is sent to Gemini.
- No prior messages, chat history, local files, PC state, tool catalog, or local-agent token is sent.
- No function calling, tool calling, or PC action is enabled.
- Each request is stateless.
- Provider errors are returned as sanitized categories (key/access, quota, model availability, provider availability, network, timeout, invalid/empty response, or rejected request); unclassified failures may include only the exception type, operation stage, and Google SDK module/function names. Raw upstream error details and API keys are not returned to the browser or written to application logs.
- Users should not submit secrets or sensitive personal information. Gemini API Free Tier data handling may differ from paid-tier terms; review Google's current terms and pricing before use.

## Credential handling

- The user enters the key in the local Settings UI.
- The key is sent over the existing loopback-only authenticated API.
- The backend holds the key in process memory only.
- The key is not returned by status endpoints, stored in browser storage, written to disk, or committed to Git.
- Restarting the backend clears the key; the user must enter it again.
- The key previously pasted into ChatGPT should be revoked and replaced before use.

## Hosting and verification

- Preserve the approved loopback-only binding, Host/Origin validation, local API token, and request-size limit.
- Do not expose the backend publicly for a hosted demo under this task.
- GitHub Actions runs automated backend and frontend checks for the pull request. This is cloud CI, not a publicly hosted interactive server.
- Real Gemini smoke testing requires the Product Owner to enter a newly created API key in the local Settings UI after running the branch.

## Out of scope

- Multi-agent orchestration.
- Windows automation or real machine-changing actions.
- Function calling, tool calling, and arbitrary commands.
- Chat-history persistence or sending previous turns to Gemini.
- Public Cloud deployment or changing the local security boundary.
