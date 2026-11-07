# T-601 — Gemini Chat MVP

## Product Owner authorization

Authorized by the Product Owner on 2026-11-03. This is a bounded provider integration exception and does not authorize PC automation, Phase 5 runtime work, or any broader data flow.

## User experience

1. Open the Gemini settings panel in the local web app.
2. Paste a Gemini API key and select Save.
3. Select Test Connection to make a real Gemini API request.
4. Send a message in Chat and display Gemini's text reply.
5. Continue the conversation with recent context, including after a page refresh in the same tab. Select New chat to clear it.

## API and model

- Provider: Google Gemini Developer API.
- Python SDK: `google-genai`.
- SDK call: `client.models.generate_content(model="gemini-3.1-flash-lite", contents=messages, config=GenerateContentConfig(system_instruction=CHAT_SYSTEM_INSTRUCTION))` for chat replies. Structured plan generation uses its separate JSON-schema configuration.
- Model: `gemini-3.1-flash-lite`.
- Official SDK documentation: https://googleapis.github.io/python-genai/
- API key guidance: https://ai.google.dev/gemini-api/docs/api-key
- Pricing and tier terms: https://ai.google.dev/gemini-api/docs/pricing

## Data boundary

- The current message and up to 10 preceding user/assistant pairs from this conversation are sent to Gemini.
- Chat history is held in backend process memory only. It is not written to disk or stored in browser storage; the current conversation ID alone is stored in `sessionStorage` to restore the history after a page refresh in that tab.
- The backend keeps at most 128 conversations and expires conversations after 1 hour of inactivity. Restarting the backend clears all conversation history. New chat deletes the current conversation from backend memory.
- The backend returns history to the browser on refresh. Failed Gemini requests do not add a question or answer to stored history.
- No local files, PC state, tool catalog, or local-agent token is sent to Gemini.
- No function calling, tool calling, or PC action is enabled.
- Context is isolated by conversation ID; concurrent requests for one conversation are serialized.
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

### Product Owner smoke-test record — 2026-11-07

The Product Owner confirmed that a real API key was entered through the local Settings UI, Test Connection succeeded, and a chat message received a Gemini reply. This is a manual real-provider smoke test; it is not a claim about GitHub CI or a public cloud deployment. No credential value is recorded here.

## Out of scope

- Multi-agent orchestration.
- Windows automation or real machine-changing actions.
- Function calling, tool calling, and arbitrary commands.
- Durable chat-history persistence.
- Public Cloud deployment or changing the local security boundary.
