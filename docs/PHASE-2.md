# Phase 2 — Local Web Application

## Status

**Draft — Awaiting Product Owner Approval**

Phase 2 has not been started. This document is a specification only. No Phase 2 implementation exists. No implementation task (T-202 to T-205) may start until the Product Owner approves this document and explicitly starts that task.

| Item | Value |
|------|-------|
| Prepared by | Implementation Engineer (Claude) |
| Reviewers | Product Owner; System Architect and Technical Reviewer (ChatGPT) |
| Prepared on | 2026-10-19 |
| Baseline | `main` at `cbb3c8d` (Phase 0 and Phase 1 complete) |
| Product Owner approval | Pending. To be recorded in Section 14 |

Markers used in this document:

- **[Carried forward]** A decision already made by the Product Owner and recorded elsewhere or in this chat history. It is confirmed when this document is approved.
- **[Proposed]** A proposal by the Implementation Engineer. It is not a requirement until approved.
- **[Open]** A decision the Product Owner must make. See Section 14.

---

# 1. Objective and Measurable Outcomes

## Objective

Give the user a local web application in which they can type a message to the Agent, see it sent to the backend, and see the reply, with clear behavior when something goes wrong.

The Agent does not exist in this phase (it belongs to Phase 3). The backend returns a **deterministic mock reply**. Phase 2 does not call any AI model and does not execute any PC automation.

## Measurable outcomes

| ID | Outcome | How it is measured |
|----|---------|--------------------|
| M-1 | A user can open the app, send a message and see the reply in the browser | Manual verification MV-01 and MV-02 on the Product Owner's Windows 11 machine |
| M-2 | A reply appears within 1 second on the local machine, 20 consecutive sends | Integration check I-01 timing and manual verification MV-02 |
| M-3 | Every defined failure (Section 6.4 and Section 8) shows its own readable message, and the user can send again afterwards | Frontend tests F-08, F-09 and F-16, manual verification MV-07 and MV-08 |
| M-4 | The same message always produces a byte-identical reply, across 100 requests and across a backend restart | Backend test B-08 and integration check I-01 |
| M-5 | The backend has no capability to execute system-changing actions or make outbound network calls | Backend test B-12 and dependency review |
| M-6 | Every security requirement in Section 11 has a passing negative test. Backend security controls have mutation evidence in the T-205 report; integration and frontend checks are evidenced in their owning task reports | ST-01 to ST-21 and ST-23 in T-205; ST-22 in T-204; ST-24 in T-202 |
| M-7 | No regression: the existing 14 backend tests and 2 frontend tests (baseline) still pass, and `GET /health` is unchanged | `scripts\test.ps1` and test B-11 |
| M-8 | `scripts\setup.ps1`, `scripts\dev.ps1` and `scripts\test.ps1` work unchanged for the Product Owner | Manual verification MV-12 |

---

# 2. Governing Decisions

| ID | Decision | Source | Marker |
|----|----------|--------|--------|
| G-1 | Frontend is Angular (TypeScript). Backend is Python with FastAPI. Scripts are PowerShell. Target is Windows 11 | `docs/PHASE-1.md`, Section 1 | [Carried forward] |
| G-2 | Backend and the Angular dev server bind to loopback (`127.0.0.1`) only | Proposal P-SEC-1, approved for Phase 1 in `docs/PHASE-1.md` | [Carried forward] |
| G-3 | The backend reply is a fixed, deterministic placeholder that acknowledges the message and says the Agent is not implemented yet | Product Owner, 2026-10-17 | [Carried forward] |
| G-4 | Minimal security set for Phase 2: Host and Origin checks, JSON-only state-changing requests, no permissive CORS, no state-changing GET | Product Owner, 2026-10-17 (subset of proposal P-SEC-2) | [Carried forward] |
| G-5 | The frontend reaches the backend through the Angular dev-server proxy (`/api`), so the browser uses one origin and the backend needs no CORS | Product Owner, 2026-10-17 | [Carried forward] |
| G-6 | A per-session secret token was **not** approved: the minimal security set was approved without one. A token is presented as an option in Section 11.4 | Product Owner, 2026-10-17 (set approved without a token); option requested 2026-10-19 | [Carried forward] |
| G-7 | Option A for P-ORDER-1: keep the phase order. Tools that can modify the machine are dry-run or mock only until the safety system is implemented and approved | Product Owner, 2026-10-19 (recorded in `docs/PROPOSALS.md` by the change that adds this document) | [Carried forward] |
| G-8 | One implementation task at a time. No task starts without explicit Product Owner approval | Product Owner, 2026-10-19 | [Carried forward] |
| G-9 | An earlier, unmerged implementation attempt of Phase 2 was discarded by the Product Owner on 2026-10-19. This specification is the new starting point. Nothing from that attempt is part of the repository | Product Owner, 2026-10-19 | [Carried forward] |
| G-10 | The chat UI supports Thai and English with a visible language switch. Thai is the default on first visit; the selected UI language may be stored in `localStorage`. Chat messages and history must never be stored in browser storage | Product Owner, 2026-10-20 | [Carried forward] |

Not approved and not part of Phase 2: any AI provider or model, API keys, a database, tool execution, an authentication framework, and every other proposal in `docs/PROPOSALS.md`.

---

# 3. Current Architecture and Baseline

Verified by reading the repository at `cbb3c8d` on 2026-10-19.

```text
Browser (Angular page, http://127.0.0.1:4200)
        |   (Phase 2 adds this link)
        v
Angular dev server (127.0.0.1:4200)  ---- Phase 2: proxy /api ---->  FastAPI (127.0.0.1:8000)
                                                                       GET /health
```

## What exists today

| Area | Baseline |
|------|----------|
| Backend | `src/backend/agent_backend/`: `main.py` creates the `FastAPI` app and defines only `GET /health` (returns `{"status": "ok"}`). `__main__.py` starts uvicorn on `BACKEND_HOST:BACKEND_PORT` with auto-reload when `APP_ENV=development`. `config.py` reads `APP_ENV`, `BACKEND_HOST`, `BACKEND_PORT`, `FRONTEND_PORT`, `LOG_LEVEL` and refuses to start if `BACKEND_HOST` is not a loopback address. `FRONTEND_PORT` is read but not used by the backend yet |
| Backend dependencies | Runtime: `fastapi`, `uvicorn`, `python-dotenv`. Development: `pytest`, `httpx2`, `ruff`. Python 3.11 or newer |
| Frontend | `src/frontend/`: Angular 22. One placeholder page (`app.html`), no chat, no `HttpClient` provider, no proxy configuration, no routes. The dev server is bound to `127.0.0.1` in `angular.json` |
| Scripts | `scripts\setup.ps1`, `scripts\dev.ps1` (starts backend and frontend, ports from `.env`), `scripts\test.ps1` (pytest, ruff, Angular unit tests) |
| Tests | 14 backend tests (`tests/backend/`) and 2 frontend tests (`src/frontend/src/app/app.spec.ts`), all passing as recorded in `docs/PHASE-1.md` |
| Not present | Any `/api` route, request validation, error handling beyond FastAPI defaults, Host or Origin checks, CORS handling, API-level security, chat UI |

## Facts observed while preparing this document

These are observations from a Linux sandbox, not from the Product Owner's machine. They must be re-verified in T-204.

- With the Angular dev server proxying `/api` to a backend that is not running, the dev server returns **HTTP 502 Bad Gateway with an empty body**. The browser therefore does not see a network error (status 0). The disconnected state in Section 6.4 is written for this case.
- The Angular dev server (Vite) adds its own `Access-Control-Allow-Origin` header on responses, only for localhost origins. This is outside the project's control (Section 11.5).
- In FastAPI 0.143.1, routes added through an included router do not appear in `app.routes`. A test that must see every route has to read the OpenAPI schema (`app.openapi()`), not `app.routes` (Section 11.3, SEC-07).

---

# 4. Scope

## In scope

- A chat page in the existing Angular app: message list, input box, Send button, status and error display
- One backend endpoint, `POST /api/chat`, with request validation, a deterministic mock reply and consistent error responses
- Frontend-to-backend communication through the Angular dev-server proxy
- The security controls in Section 11 that the Product Owner approves
- Unit, contract, integration and manual tests defined in Section 9
- Documentation updates for Phase 2

## Out of scope (not implemented in Phase 2)

- Any Agent logic: intent analysis, task planning, tool selection, tool execution
- Any AI model or provider, API keys, prompts
- Any capability that changes the machine: processes, files, registry, installers, network settings
- Persistent chat history or any database. History lives in the page and is lost on reload
- Login, user accounts, sessions or cookies, an authentication framework
- Permission and confirmation flows (Phase 5)
- Streaming replies, Markdown or rich-text rendering, file upload, voice
- Multi-user support, remote access, HTTPS, production deployment and serving of the built frontend
- Changes to the technology stack, new runtime dependencies, changes to `docs/ROADMAP.md` phase order

---

# 5. User Stories and Acceptance Criteria

| ID | Story | Acceptance criteria |
|----|-------|---------------------|
| US-1 | As a user, I open the app and see a chat page | **AC-1.1** Given the backend and frontend are running, when I open `http://127.0.0.1:4200/`, then I see the page title, an empty message list with the hint MSG-01, an empty input box and a disabled Send button. **AC-1.2** The page needs no backend response to render |
| US-2 | As a user, I send a message and see the reply | **AC-2.1** Given I typed a non-empty message, when I press Enter or click Send, then my message appears as a "You" entry, the input is cleared, a pending indicator (MSG-02) is shown and Send is disabled. **AC-2.2** When the reply arrives, it appears as an "Agent" entry, the indicator disappears and Send is enabled again. **AC-2.3** The reply text is exactly the text defined in Section 7.3 for that message. **AC-2.4** Entries stay in the order they happened. The newest entry is visible |
| US-3 | As a user, I cannot send invalid input | **AC-3.1** Send is disabled while the input is empty or only whitespace. **AC-3.2** The input does not accept more than 2000 characters. **AC-3.3** If an invalid message still reaches the backend, the user sees MSG-04 and can send again |
| US-4 | As a user, I understand when the backend is not reachable | **AC-4.1** Given the backend is not running, when I send a message, then I see the disconnected message MSG-03 as an "Error" entry. **AC-4.2** Send is enabled again. **AC-4.3** After the backend is started again, sending works without reloading the page |
| US-5 | As a user, I see a clear message for every other failure | **AC-5.1** Each failure class in Section 6.4 shows its own message and never shows a stack trace, file path or internal detail. **AC-5.2** After any failure, the user can send another message. **AC-5.3** A request that does not finish within the timeout ends with MSG-07 |
| US-6 | As a Thai-speaking user, I can write in Thai and other Unicode text | **AC-6.1** Thai and other Unicode text is sent and counted correctly (Section 7.2). **AC-6.2** Pressing Enter while an input method (IME) is composing does not send the message. **AC-6.3** Shift+Enter inserts a new line |
| US-7 | As the Product Owner, I need Phase 2 to be unable to change the PC | **AC-7.1** The reply is clearly a placeholder (MSG-01 and the reply text say the Agent is not implemented). **AC-7.2** The backend code contains no process execution, file writing or outbound network access (test B-12). **AC-7.3** No new runtime dependency is added without approval |
| US-8 | As the Product Owner, I need other websites and programs to be unable to misuse the local API through the browser | **AC-8.1** Requests with a foreign Origin or Host are rejected with the defined status. **AC-8.2** All security tests ST-01 to ST-24 pass. **AC-8.3** The backend sends no CORS headers and no cookies |

---

# 6. Frontend Behavior and UI States

## 6.1 Layout and elements

- Title (existing) and one chat section below it
- Message list: entries of three kinds: **You**, **Agent**, **Error**
- Composer: one multi-line text box with a visible label for screen readers, and a Send button
- All text on the page is rendered as plain text. HTML and Markdown in a message or reply are shown literally

## 6.2 Interaction rules

| ID | Rule |
|----|------|
| FR-1 | Enter sends. Shift+Enter inserts a new line. Enter pressed during IME composition is ignored |
| FR-2 | The text is trimmed before sending. Send is disabled when the trimmed text is empty |
| FR-3 | The input accepts at most 2000 characters. The browser counts UTF-16 units, so it can stop earlier than the backend, never later. The backend is authoritative |
| FR-4 | Only one request is in flight. Send is disabled while a request is pending. The input stays editable |
| FR-5 | A request has a timeout (Open decision D-API-1, proposed 10 seconds). On timeout the request is cancelled and the state is MSG-07 |
| FR-6 | The newest entry is scrolled into view after each change |
| FR-7 | The message list uses `role="log"` with polite live announcements. The input has a programmatic label |
| FR-8 | Chat history exists only in the page. It is not written to local storage, session storage, IndexedDB or cookies. A reload clears it |
| FR-9 | All user-visible UI text and system messages are localized in Thai and English. Provide a visible language switch; default to Thai on first visit and remember the selected UI language in `localStorage`. This preference is the only permitted browser-storage value. Unicode input of any language must work |
| FR-10 | The page is readable in light and dark system themes |

## 6.3 UI states

| State | When | What the user sees |
|-------|------|--------------------|
| S-1 Empty | No entries yet | Hint MSG-01. Send disabled |
| S-2 Composing | Input has non-whitespace text, no request pending | Send enabled |
| S-3 Sending | Request in flight | The "You" entry, pending indicator MSG-02, Send disabled |
| S-4 Success | Reply received | "Agent" entry with the reply, Send enabled when the input has text |
| S-5 Validation failure | Backend answers 422 | "Error" entry MSG-04 |
| S-6 Disconnected | Backend not reachable (see 6.4) | "Error" entry MSG-03 |
| S-7 Rejected | Backend answers 400, 403 or 415 | "Error" entry MSG-05 |
| S-8 Server failure | Backend answers 500 with its own error body | "Error" entry MSG-06 |
| S-9 Timeout | No answer within the timeout | "Error" entry MSG-07 |
| S-10 Unexpected response | 200 with a body that is not `{"reply": <string>}` | "Error" entry MSG-08 |
| S-11 Too large | Backend answers 413 (only if D-SEC-4 is approved) | "Error" entry MSG-09 |
| S-12 Other | Any other status | "Error" entry MSG-10 |

From every state S-4 to S-12, the user can send another message without reloading.

## 6.4 Error classification (first match wins)

| Order | Condition | State | Message |
|-------|-----------|-------|---------|
| 1 | The request exceeded the timeout | S-9 | MSG-07 |
| 2 | Status 0 (the browser could not reach the dev server) | S-6 | MSG-03 |
| 3 | Status 502, 503 or 504 | S-6 | MSG-03 |
| 4 | Status 200 and the body is a JSON object with a string `reply` | S-4 | the reply |
| 5 | Status 200 with any other body | S-10 | MSG-08 |
| 6 | Status 400, 403 or 415 | S-7 | MSG-05 |
| 7 | Status 413 | S-11 | MSG-09 |
| 8 | Status 422 | S-5 | MSG-04 |
| 9 | Status 500 or any other 5xx whose body is JSON with a string `detail` | S-8 | MSG-06 |
| 10 | Any other 5xx (no `detail`): it did not come from the backend | S-6 | MSG-03 |
| 11 | Anything else | S-12 | MSG-10 with the status code |

The backend never returns 502, 503 or 504 itself, and every 500 it returns carries a `detail` (Section 8). That is why a 5xx without a `detail` is treated as "disconnected". The UI shows its own fixed texts. It does not display backend `detail` text.

## 6.5 User-visible text (frozen in T-201)
| ID | Text |
|----|------|
| MSG-01 | TH: เริ่มพิมพ์ข้อความได้เลย Agent ยังไม่พร้อมใช้งาน คำตอบในตอนนี้เป็นเพียงตัวอย่างจำลอง. / EN: Type a message to start. The Agent is not implemented yet, so replies are placeholders. |
| MSG-02 | TH: กำลังรอคำตอบจาก Agent… / EN: Waiting for the Agent… |
| MSG-03 | TH: เชื่อมต่อ Backend ไม่ได้ โปรดตรวจสอบว่า Backend ทำงานอยู่ (`scripts\dev.ps1`). / EN: Cannot reach the backend. Check that it is running (`scripts\dev.ps1`). |
| MSG-04 | TH: ไม่รับข้อความนี้ ข้อความต้องมีความยาว 1 ถึง 2000 อักขระ / EN: The message was not accepted. Messages must be 1 to 2000 characters. |
| MSG-05 | TH: Backend ปฏิเสธคำขอ (ไม่ผ่านการตรวจสอบความปลอดภัย) / EN: The backend rejected the request (security check). |
| MSG-06 | TH: Backend พบข้อผิดพลาดภายใน โปรดลองอีกครั้ง / EN: The backend reported an internal error. Please try again. |
| MSG-07 | TH: Agent ไม่ตอบกลับภายในเวลาที่กำหนด โปรดลองอีกครั้ง / EN: The Agent did not respond in time. Please try again. |
| MSG-08 | TH: Backend ส่งคำตอบในรูปแบบที่ไม่คาดคิด / EN: The backend sent an unexpected response. |
| MSG-09 | TH: ข้อความมีขนาดใหญ่เกินไป / EN: The message is too large. |
| MSG-10 | TH: เกิดข้อผิดพลาดที่ไม่คาดคิด (HTTP <status>) / EN: Unexpected error (HTTP <status>). |

Entry labels: TH: "คุณ", "Agent", "ข้อผิดพลาด"; EN: "You", "Agent", "Error". The language switch and all labels, hints, pending states, and error messages must use the selected language.

---

# 7. Backend API Contract

## 7.1 Endpoints

| Method and path | Purpose | State-changing |
|-----------------|---------|----------------|
| `GET /health` | Health check (exists, unchanged) | No |
| `POST /api/chat` | Send one message, receive one reply | No (the mock has no side effects) but uses POST because it carries input |

No other route is added in Phase 2. No GET route may change state.

## 7.2 `POST /api/chat` request

Headers:

- `Content-Type: application/json` (required; see Section 11)
- `Origin`: see Section 11

Body: a JSON object with exactly two properties:

```json
{"message": "Install Google Chrome", "language": "en"}
```

Rules:

- `message` is required and must be a string
- `language` is required and must be exactly `th` or `en`; it selects the language of the mock reply, not the UI preference itself
- The string is trimmed of leading and trailing Unicode whitespace
- After trimming it must contain 1 to 2000 Unicode characters. Length is counted in Unicode code points, not bytes, not UTF-16 units and not grapheme clusters
- No other property is allowed
- The body must be valid UTF-8 JSON

## 7.3 `POST /api/chat` success response

Status `200`, `Content-Type: application/json`:

```json
{"reply": "Message received (length: 21). The Agent is not implemented yet (planned for Phase 3)."}
```

The reply is produced by the selected language and the trimmed message length, and by nothing else:

- `en`: `"Message received (length: " + N + "). The Agent is not implemented yet (planned for Phase 3)."`
- `th`: `"รับข้อความแล้ว (ความยาว: " + N + " ตัวอักษร) Agent ยังไม่พร้อมใช้งาน (วางแผนไว้ใน Phase 3)."`

Here N is the number of Unicode code points of the trimmed message, written in decimal digits.

Properties:

- Deterministic: the same `message` and `language` always produce the same reply. No time, randomness, host data or earlier requests are used
- The reply never repeats the message text
- No state is stored between requests

Examples:

| Request body | Reply |
|--------------|-------|
| `{"message": "Install Google Chrome", "language": "en"}` | `Message received (length: 21). The Agent is not implemented yet (planned for Phase 3).` |
| `{"message": "สวัสดี", "language": "th"}` | `รับข้อความแล้ว (ความยาว: 6 ตัวอักษร) Agent ยังไม่พร้อมใช้งาน (วางแผนไว้ใน Phase 3).` |
| `{"message": "  hi  ", "language": "en"}` | `Message received (length: 2). The Agent is not implemented yet (planned for Phase 3).` |

## 7.4 Error responses

Every error response is JSON of the form `{"detail": "<text>"}` and never contains a stack trace, file path, library name or version, or the message text.

| Status | Condition | `detail` |
|--------|-----------|----------|
| 400 | Host header not allowed | `Host not allowed.` |
| 403 | Origin not allowed (or missing, if D-SEC-2 chooses to reject) | `Origin not allowed.` |
| 415 | A state-changing request whose content type is not `application/json` | `Content-Type must be application/json.` |
| 413 | Body larger than the limit (only if D-SEC-4 is approved) | `Request body too large.` |
| 404 | Unknown path | `Not Found` |
| 405 | Method not allowed on a known path, for example `GET /api/chat` | `Method Not Allowed` |
| 422 | Validation failure or malformed JSON (Section 8) | `Invalid request. Send JSON like {"message": "..."} with 1 to 2000 characters.` |
| 500 | Unexpected error | `Internal server error.` |

Example, invalid request:

```json
{"detail": "Invalid request. Send JSON like {\"message\": \"...\"} with 1 to 2000 characters."}
```

## 7.5 Order of checks

The checks run in this order, and the first failure decides the response. Tests rely on this order.

1. Host (400)
2. Origin (403)
3. Content type of state-changing requests (415)
4. Body size (413, if approved)
5. Routing (404, 405)
6. Body validation (422)
7. Handler (200, or 500 on an unexpected error)

## 7.6 Response headers

- `Content-Type: application/json`
- No `Access-Control-*` headers
- No `Set-Cookie`

---

# 8. Input Validation and Error Handling

| ID | Rule | Result on violation |
|----|------|---------------------|
| V-1 | Body is a JSON object | 422 |
| V-2 | The only property is `message` | 422 |
| V-3 | `message` is a string | 422 |
| V-4 | Trimmed `message` has 1 to 2000 Unicode code points | 422 |
| V-5 | Body size is at most 16 KiB (proposal D-SEC-4) | 413 |
| V-6 | Request content type is `application/json` (parameters such as `charset=utf-8` are allowed) | 415 |

Error handling rules:

- **EH-1** A single error format is used everywhere (Section 7.4)
- **EH-2** An unexpected exception is logged on the server with its traceback, without the message text, and the client receives the generic 500 body
- **EH-3** The message text is not written to any log at any level
- **EH-4** The frontend never displays backend text. It maps status codes to the fixed texts in Section 6.5
- **EH-5** The frontend never leaves the user blocked: every end state of a request re-enables Send
- **EH-6** The server fails closed: invalid or missing security configuration prevents startup instead of falling back to a permissive default

---

# 9. Integration and Testing Strategy

## 9.1 Levels

| Level | Tool | What it covers |
|-------|------|----------------|
| Backend contract and unit | pytest with the FastAPI test client | Section 7 and 8 behavior, security checks, static guard |
| Frontend component and unit | Angular unit tests (current builder) with a fake `ChatApi` | UI states, interaction rules, error classification |
| Integration | Real backend and real Angular dev server, driven by HTTP requests | Proxy path, security through the proxy, ports from `.env`, backend-down behavior |
| Manual | Product Owner on Windows 11 in a real browser | Layout, typing, IME, dark mode, end-to-end feel |

## 9.2 Rules

- A test result may be reported only if the test was actually run. Reports state what was run and where
- Test counts must not fall below the baseline (14 backend, 2 frontend)
- A frontend component depends on a `ChatApi` abstraction. Tests use fakes. The real HTTP implementation is added in T-204
- For backend security controls owned by T-205, each applicable ST test must be shown to **fail** when its control is removed (mutation check); record this evidence in the T-205 report. ST-22 is verified end-to-end in T-204, and ST-24 is verified in T-202.
- Integration checks must not depend on the Agent. The mock reply is the oracle
- Tests do not call the internet

## 9.3 Backend tests (T-203)

| ID | Test |
|----|------|
| B-01 | Valid ASCII message with `language: en` returns 200 and the exact English reply |
| B-02 | Thai message `สวัสดี` with `language: th` returns the exact Thai reply with length 6 (code points) |
| B-03 | Leading and trailing whitespace is trimmed and not counted |
| B-04 | 2000 characters are accepted, 2001 returns 422 |
| B-05 | Empty and whitespace-only messages return 422 |
| B-06 | Missing `message` or `language`, wrong types, unsupported language and extra properties return 422 |
| B-07 | Malformed JSON returns 422 |
| B-08 | The same message and language give the identical reply 100 times; different messages with the same length and language give the identical reply |
| B-09 | An unexpected exception returns 500 with the generic body and no internal detail |
| B-10 | `GET /api/chat` returns 405 |
| B-11 | `GET /health` is unchanged (existing test) |
| B-12 | Static guard: the backend package imports none of `subprocess`, `ctypes`, `winreg`, `multiprocessing`, `shutil`, `socket`, `urllib`, `http.client`, `requests`, `httpx` |

## 9.4 Frontend tests (T-202 uses a fake `ChatApi`; F-15 and F-16 belong to T-204)

| ID | Test |
|----|------|
| F-01 | Empty state shows MSG-01 and Send is disabled |
| F-02 | Whitespace-only input keeps Send disabled |
| F-03 | Successful send: "You" entry, pending indicator, "Agent" entry, input cleared, Send enabled |
| F-04 | The trimmed text is what is sent |
| F-05 | A second send while one is pending is ignored |
| F-06 | Enter sends, Shift+Enter does not, Enter during IME composition does not |
| F-07 | The input limit of 2000 is enforced |
| F-08 | Each failure class (MSG-03 to MSG-10) is shown as an "Error" entry and re-enables Send |
| F-09 | A timeout shows MSG-07 and re-enables Send |
| F-10 | HTML in the user text and in the reply is displayed as text |
| F-11 | Entry order is preserved and the newest entry is scrolled into view |
| F-12 | The input has a label and the list has `role="log"` with a polite live region |
| F-13 | Chat messages and history are never written to browser storage; `localStorage` may be used only for the selected UI language |
| F-14 | The placeholder `ChatApi` shipped by T-202 reports "not connected" and the UI shows MSG-03 |
| F-15 | The HTTP implementation posts JSON `{"message": <text>}` to `/api/chat` |
| F-16 | Table-driven error classification covers every row of Section 6.4, including 502 with an empty body, 500 with `detail`, 500 without `detail` |

## 9.5 Integration checks (T-204)
These run against the real servers started by `scripts\dev.ps1` or an equivalent harness.

| ID | Check |
|----|-------|
| I-01 | A message through the frontend address (proxy), with the selected language, returns the exact localized reply 20 times, each within 1 second |
| I-02 | With the backend stopped, a request through the proxy produces the status the frontend classifies as S-6. Re-verify the observation in Section 3 on Windows |
| I-03 | A request through the proxy with a foreign Origin returns 403 |
| I-04 | A direct request to the backend with a foreign Host returns 400 |
| I-05 | Both ports are unreachable on the machine's non-loopback address (where the machine has one) |
| I-06 | With custom `BACKEND_PORT` and `FRONTEND_PORT` in `.env`, the proxy reaches the backend, the matching Origin is accepted and the old Origin is rejected |
| I-07 | `scripts\test.ps1` passes and counts are not below baseline |

---

# 10. Local Development and Manual Verification

## 10.1 Run

From the repository root in PowerShell:

```text
scripts\setup.ps1
scripts\test.ps1
scripts\dev.ps1
```

Open `http://127.0.0.1:4200/`. These are the existing scripts. Phase 2 does not change how they are used. Ports come from `.env` (`BACKEND_PORT`, `FRONTEND_PORT`).

## 10.2 Manual verification checklist (Product Owner, Windows 11)

| ID | Steps | Expected |
|----|-------|----------|
| MV-01 | Open the page | Title, hint MSG-01, Send disabled |
| MV-02 | Type `Install Google Chrome`, press Enter with English selected | "You" entry, then the English "Agent" entry with `length: 21`, input cleared; repeat with Thai selected and verify a Thai reply |
| MV-03 | Click Send with an empty or space-only box | Send is disabled, nothing is sent |
| MV-04 | Type Thai text, press Enter while choosing a word with the Thai input method | The message is not sent until the word is confirmed. Then `length` is the number of characters |
| MV-05 | Paste 2000 characters, then try to add one more | The 2001st character is not accepted. The 2000 are sent and accepted |
| MV-06 | Use Shift+Enter | A new line is added, nothing is sent |
| MV-07 | Stop only the backend, send a message | "Error" entry MSG-03. Send is enabled again |
| MV-08 | Start the backend again (or restart `scripts\dev.ps1`) and send without reloading | The reply appears |
| MV-09 | Reload the page | History is empty |
| MV-10 | Switch Windows between light and dark mode | The page stays readable |
| MV-11 | Run the negative checks in 10.3 | Each returns the expected status |
| MV-12 | Run `scripts\test.ps1` | All checks pass, counts at least 14 backend and 2 frontend |

## 10.3 Negative checks (MV-11)

Windows 11 includes `curl.exe`. Use a body file to avoid quoting problems:

```text
Set-Content -Path $env:TEMP\chat.json -Value '{"message":"hi"}' -NoNewline
curl.exe -s -o NUL -w "%{http_code}`n" -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -H "Origin: https://evil.com" --data-binary "@$env:TEMP\chat.json"
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/health -H "Host: evil.com"
curl.exe -s -o NUL -w "%{http_code}`n" -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: text/plain" -H "Origin: http://127.0.0.1:4200" --data-binary "@$env:TEMP\chat.json"
```

Expected: `403`, `400`, `415` (with the default ports). A request with a correct `Origin` header and `Content-Type: application/json` returns `200`.

---

# 11. Security Requirements and Design

Binding to `127.0.0.1` alone does not protect the backend. Any website open in the user's browser can send requests to `localhost`, and any program on the computer can connect to a loopback port. Phase 2 is the first phase where a browser talks to the backend, so these controls are requirements for it.

**Nothing in this section is implemented yet.** Implementation is task T-205, after the Product Owner approves Section 11 and the open decisions in Section 14.

## 11.1 Requirements

| ID | Requirement | Marker |
|----|-------------|--------|
| SEC-01 | **Loopback only.** The backend and the Angular dev server bind to loopback. The backend refuses to start with a non-loopback `BACKEND_HOST` (exists today) | [Carried forward] |
| SEC-02 | **Exact Host validation.** The `Host` header must equal one of `127.0.0.1:<BACKEND_PORT>`, `localhost:<BACKEND_PORT>`, `[::1]:<BACKEND_PORT>` (case-insensitive host, exact port). No suffix, prefix or pattern matching. A missing or empty Host is rejected with 400. This blocks DNS-rebinding names | [Carried forward] |
| SEC-03 | **Exact Origin validation.** When an `Origin` header is present it must equal `http://127.0.0.1:<FRONTEND_PORT>` or `http://localhost:<FRONTEND_PORT>`. Scheme, host and port are compared exactly. No wildcards, no regular expressions, no suffix matching. `null` is rejected. Handling of a missing Origin is D-SEC-2 | [Carried forward] |
| SEC-04 | **No CORS.** The backend sends no `Access-Control-*` headers, has no CORS middleware and does not handle preflight requests. The browser uses one origin through the dev proxy | [Carried forward] |
| SEC-05 | **JSON only.** `POST`, `PUT`, `PATCH` and `DELETE` require `Content-Type: application/json`, otherwise 415. A cross-site page cannot send this content type without a CORS preflight, which SEC-04 refuses | [Carried forward] |
| SEC-06 | **Cross-site request protection.** SEC-02 to SEC-05 together protect against cross-site requests. The application uses no cookies and no ambient credentials, so there is nothing for a forged request to ride on. No separate CSRF token is added unless D-SEC-1 introduces a session | [Proposed] |
| SEC-07 | **No state-changing GET.** The only GET routes are read-only. A test enumerates every route from the OpenAPI schema and fails when a GET route is not on an explicit allow-list, and when an `/api` route accepts any method other than POST | [Carried forward] |
| SEC-08 | **No information leaks.** Error bodies follow Section 7.4. No traceback, path, library or version appears in a response | [Proposed] |
| SEC-09 | **No message content in logs** at any level. Metadata (method, path, status) is allowed | [Proposed] |
| SEC-10 | **Plain-text rendering.** User and reply text are rendered as text. No `innerHTML`, no markdown renderer, no `bypassSecurityTrust*` | [Proposed] |
| SEC-11 | **No secrets and no new dependencies.** No API key, token or secret in the repository or `.env.example`. No new runtime dependency without approval | [Carried forward] |
| SEC-12 | **Fail closed.** If the allowed hosts or origins cannot be built from the configuration (for example an invalid `FRONTEND_PORT`), the backend refuses to start | [Proposed] |
| SEC-13 | **No system-changing capability** in Phase 2 (Section 12) | [Carried forward] |
| SEC-14 | **Docs endpoints** (`/docs`, `/redoc`, `/openapi.json`) follow D-SEC-3 | [Open] |
| SEC-15 | **Request size limit** follows D-SEC-4 | [Open] |
| SEC-16 | **Local authorization** (token) follows D-SEC-1 | [Open] |

## 11.2 Explicit failure behavior and security tests (T-205)

ST-01 to ST-21 and ST-23 are backend security tests owned by T-205 unless a row says otherwise. ST-22 is an integration check owned by T-204; ST-24 is a frontend rendering test owned by T-202. Ports shown are the defaults.

| ID | Request | Expected |
|----|---------|----------|
| ST-01 | `Host: evil.com` | 400 `Host not allowed.` |
| ST-02 | `Host: 127.0.0.1.evil.com:8000` | 400 |
| ST-03 | `Host: 127.0.0.1:9999` (wrong port) | 400 |
| ST-04 | Missing or empty Host | 400 |
| ST-05 | `Origin: https://evil.com` | 403 `Origin not allowed.` |
| ST-06 | `Origin: http://127.0.0.1:9999` (wrong port) | 403 |
| ST-07 | `Origin: https://127.0.0.1:4200` (wrong scheme) | 403 |
| ST-08 | `Origin: null` | 403 |
| ST-09 | `Origin: http://127.0.0.1.evil.com:4200` | 403 |
| ST-10 | `POST` without an Origin header | Per D-SEC-2: 403, or 200 |
| ST-11 | `Origin: http://127.0.0.1:4200` and `http://localhost:4200` | 200 |
| ST-12 | `Content-Type: text/plain`, form types and multipart on POST | 415. `application/json; charset=utf-8` returns 200 |
| ST-13 | `OPTIONS /api/chat` preflight | Not 2xx, no `Access-Control-*` headers |
| ST-14 | Any direct backend response (not a response generated by the Angular dev server proxy) | No `Access-Control-*` and no `Set-Cookie` header |
| ST-15 | `GET /api/chat` | 405, and 403 first when the Origin is foreign |
| ST-16 | Enumerated GET routes (OpenAPI) | Equal to the allow-list |
| ST-17 | Body over the limit | 413 (only if D-SEC-4 is approved) |
| ST-18 | Malformed JSON and schema violations | 422 with the Section 7.4 body |
| ST-19 | Forced internal exception | 500 generic body, no leak, message text not in logs |
| ST-20 | Invalid `FRONTEND_PORT` or `BACKEND_PORT` at startup | Backend refuses to start |
| ST-21 | Non-loopback `BACKEND_HOST` at startup | Backend refuses to start (exists) |
| ST-22 | Integration: foreign Origin sent through the frontend proxy | 403 |
| ST-23 | Every `/api` route in the OpenAPI schema | POST only |
| ST-24 | Frontend: `<img src=x onerror=...>` as user text and as reply | Shown as text, no element created |

## 11.3 Notes for implementers

- Checks run in the order in Section 7.5
- To list routes, use `app.openapi()["paths"]`. `app.routes` does not show routes of included routers in FastAPI 0.143.1 (Section 3)
- For backend security controls owned by T-205, a test that still passes after its control is removed is a defect. Record mutation evidence in T-205's report. ST-22 is verified end-to-end in T-204; ST-24 is verified in T-202 and is not a backend mutation test.

## 11.4 Material security decisions for the Product Owner

### D-SEC-1: Local authorization (per-session token)

**Why it matters.** Host and Origin checks stop other websites. They do not stop another program on the same computer, because such a program can send any headers it likes. On a shared Windows computer, another logged-in user can also connect to a loopback port.

| Option | What it is | Protects against | Does not protect against | Cost |
|--------|------------|------------------|--------------------------|------|
| A. No token (current approved set) | Host + Origin + JSON only | Other websites in the browser | Any local program or other local user | None |
| B. Token injected by the dev proxy | `scripts\dev.ps1` creates a random token per run; backend requires it; the Angular proxy adds it to proxied requests | Direct calls to the backend port by programs that do not know the token | Anyone who calls the frontend port instead (the proxy adds the token for them) | Script and proxy changes. Partial benefit |
| C. Token fetched by the page | The page requests a token at start and sends it with each call | Little: any local program can request the token too | Same as A in practice | Adds a handshake endpoint and state |
| D. Token passed only to the launched browser | A launcher opens the browser with the token in the URL fragment; the page keeps it in memory | Programs and other users that did not launch the page and cannot read its start-up arguments | A same-user program that can read process arguments | A launcher, new startup flow |

**Recommendation.** **Option A for Phase 2.** In Phase 2 the backend only returns a fixed mock reply and exposes no data or action, so the impact of another local caller is negligible, and options B and C add complexity with little real protection. **A real local-authorization decision is mandatory before Phase 3 enables any Agent capability**, and before any tool that changes the machine is enabled (see Section 12). Option D is the candidate to evaluate then. Approve A, or choose another option now.

### D-SEC-2: Request with no `Origin` header on state-changing requests

| Option | Behavior | Trade-off |
|--------|----------|-----------|
| Accept | A POST without Origin is processed (curl, scripts, tests work without extra headers) | Any non-browser caller works. Browsers are still protected because they always send Origin on POST |
| Reject | A POST without Origin returns 403 | Failure is explicit and non-browser callers must declare an Origin. This does not stop a local program, which can send any Origin, so it is a guard against accidental callers only |

**Recommendation.** Reject for state-changing requests (403), accept for `GET /health`. It makes failure behavior explicit, at the cost of adding `-H "Origin: ..."` to manual `curl.exe` calls. The integration checks and MV-11 are written for either choice.

### D-SEC-3: API documentation endpoints (`/docs`, `/redoc`, `/openapi.json`)

| Option | Trade-off |
|--------|-----------|
| Always enabled (current FastAPI default) | Convenient. Exposes the API description |
| Enabled only when `APP_ENV=development` | Same convenience during development, closed otherwise |
| Disabled | Smallest surface. No interactive docs |

**Recommendation.** Enabled only when `APP_ENV=development`. Note that the route-enumeration test (SEC-07) reads the schema from the application object, so it works with any option.

### D-SEC-4: Request body size limit

| Option | Trade-off |
|--------|-----------|
| 16 KiB limit checked before parsing (413) | 2000 characters is at most about 8 KiB in UTF-8, so 16 KiB leaves room. Needs a small middleware and tests |
| Rely on validation only (422) | Simpler. The server still reads an arbitrarily large body before rejecting it |

**Recommendation.** 16 KiB limit.

### D-SEC-5: Scope of P-SEC-1

P-SEC-1 (loopback binding) was approved for Phase 1 only. The code still enforces it. **Recommendation:** confirm it as a standing rule for all phases.

## 11.5 Known limits that remain even with all recommendations

- Another program on the same computer can call the API (D-SEC-1)
- The Angular dev server adds its own CORS headers for localhost origins on its own responses. They are not wildcards, and the backend decides requests through its own Origin check, which receives the original `Origin` through the proxy. This must be shown by integration check I-03
- The proxy exists only in the dev server. How the application is served outside development is undefined and out of scope
- Communication is plain HTTP on loopback. Traffic is not encrypted

---

# 12. Safety Constraint (P-ORDER-1, option A)

The Product Owner selected option A for P-ORDER-1: the phase order does not change, and tools that can modify the machine are dry-run or mock only until the safety system (Phase 5) is implemented and approved.

For Phase 2:

- No capability that executes a system-changing action is introduced, directly or indirectly
- The mock reply must not depend on, trigger or simulate any real action
- Test B-12 and the dependency rule (SEC-11) enforce this
- Nothing in Phase 2 may be reused later as a way to bypass the safety system. Phase 3 and Phase 4 carry the same constraint, recorded in `docs/ROADMAP.md`

---

# 13. Task Breakdown

## 13.1 Rules for all tasks

- **WIP limit: 1.** Only one implementation task may be in progress. The next task starts only after the previous one is merged into `main`, verified, and the Product Owner explicitly starts the next one
- Each task uses its own branch and its own pull request (Section 16)
- A task changes only the paths listed under "Allowed changes". Anything else is a stop-and-ask- Every task ends with the completion report in Section 17
- No task may add a runtime dependency, an AI provider, API key, database, tool execution or authentication framework
- No task changes `docs/ROADMAP.md` phase order or the technology stack

## 13.2 Execution order and dependency graph

```text
T-201 (this specification, approved)
  |
  v
T-202  Chat UI  ---------------------------+
  |                                         |
  v                                         |
T-203  Backend endpoint                     |
  |                                         |
  v                                         |
T-205  Local web security  (needs approved Section 11 decisions)
  |                                         |
  v                                         v
T-204  Frontend/backend integration  <------+
```

Execution order: **T-201, T-202, T-203, T-205, T-204.**

**Reason for adjusting the proposed order.** The IDs are kept as proposed. Only the order changes: T-205 runs before T-204. T-204 is the task that connects the browser to the backend. Connecting them before the security controls exist would expose an unprotected endpoint to browser requests, even if only for a mock. T-205 can run after T-203 because the controls live in the backend and do not need the UI.

## 13.3 T-201: Phase 2 UI and API contract

| Field | Content |
|-------|---------|
| Status | Drafted in this document. Complete when the Product Owner approves it and answers every open decision (Section 14) |
| Scope | Define and freeze: user stories and acceptance criteria, UI states and texts (Sections 5, 6), API contract (Sections 7, 8), test matrix (Section 9), security requirements (Section 11), task breakdown. Record the safety decision (Section 12) |
| Allowed changes | `docs/PHASE-2.md`, navigation references in `README.md`, `docs/PROJECT.md`, `docs/ROADMAP.md`, decision records in `docs/PROPOSALS.md` |
| Prohibited changes | Any file under `src/`, `tests/`, `scripts/`; `.env.example`; `.gitignore`; dependency files |
| Dependencies | Phase 0 and Phase 1 complete (done) |
| Acceptance criteria | (1) Product Owner approval recorded in Section 14. (2) Every open decision D-* has an explicit answer. (3) Every acceptance criterion is testable by a test or check ID. (4) Links and file references in the changed documents are valid. (5) Consistent with `docs/PHASE-0.md` and `docs/PHASE-1.md` |
| Tests | Documentation review checklist: link and reference check, consistency check, confirmation that no application source file changed |
| Definition of Done | Approved specification merged into `main` and verified on GitHub. Status changed from Draft to Approved by a follow-up documentation change |

## 13.4 T-202: Chat UI

| Field | Content |
|-------|---------|
| Scope | Chat page in the Angular app (message list, composer, all UI states in Section 6.3, interaction rules FR-1 to FR-10, texts in Section 6.5). The UI depends on a `ChatApi` abstraction. This task ships a placeholder `ChatApi` that reports "not connected", so the page shows MSG-03 when used. Tests use fake implementations |
| Allowed changes | New files under `src/frontend/src/app/chat/`; `app.ts`, `app.html`, `app.css`, `app.spec.ts`, `src/frontend/src/styles.css`; documentation status |
| Prohibited changes | `HttpClient` and its provider; proxy configuration; backend files; browser storage for messages/history (the UI-language preference in `localStorage` is allowed); Markdown or HTML rendering; new dependencies; routing changes |
| Dependencies | T-201 approved |
| Acceptance criteria | AC-1.1, AC-1.2, AC-2.1 (up to the request), AC-2.2 to AC-2.4 with a fake, AC-3.1, AC-3.2, AC-4.1 and AC-4.2 with a fake, AC-5.1 to AC-5.3 with a fake, AC-6.1 (frontend part), AC-6.2, AC-6.3 |
| Tests | F-01 to F-14 plus existing tests. Manual MV-01, MV-03, MV-04 to MV-06, MV-09, MV-10 against the placeholder |
| Definition of Done | Tests pass in `scripts\test.ps1` (counts at least baseline plus F-01 to F-14). Manual checks reported by the Product Owner. No file outside Allowed changes. Report delivered. Merged and verified |

## 13.5 T-203: Backend message endpoint with deterministic mock response

| Field | Content |
|-------|---------|
| Scope | `POST /api/chat` with the request rules in Section 7.2, the deterministic reply in Section 7.3 and the errors 405, 422, 500 in Section 7.4. Unified error format. A static guard test (B-12). The backend remains testable without a browser |
| Allowed changes | New module(s) under `src/backend/agent_backend/` for the endpoint; `main.py`; `tests/backend/`; documentation status |
| Prohibited changes | Host, Origin or content-type checks (T-205); CORS middleware; any AI call; storage of messages; logging of message text; subprocess, file writing or network calls; new dependencies; frontend files |
| Dependencies | T-201 approved (T-202 is not required) |
| Acceptance criteria | AC-2.3, AC-3.3 (backend side), AC-7.1, AC-7.2, AC-7.3; Section 7.2 to 7.4 behavior for 200, 405, 422, 500; M-4 and M-5 |
| Tests | B-01 to B-12 plus existing tests |
| Definition of Done | All B tests pass. `GET /health` unchanged. Static guard passes. Report delivered. Merged and verified |

Note: until T-205 is merged, the endpoint must not be called from a browser. T-204 enforces this by its dependency on T-205.

## 13.6 T-205: Local web security implementation and verification

| Field | Content |
|-------|---------|
| Scope | Implement the backend security controls SEC-01 to SEC-09, SEC-11, SEC-12, and the approved choices for SEC-14 to SEC-16. SEC-10 (plain-text rendering) is owned by T-202; SEC-13 (no system-changing capability) is enforced by T-203 and B-12. Verify backend controls with the applicable ST tests and mutation evidence |
| Allowed changes | New security module and its wiring under `src/backend/agent_backend/`; `config.py` only if needed; `tests/backend/`; comments in `.env.example`; documentation status and a security verification record |
| Prohibited changes | CORS middleware; cookies or sessions; an authentication framework; a token unless D-SEC-1 approves one; new dependencies; frontend files; endpoint behavior defined in T-203 |
| Dependencies | T-203 merged. **Product Owner approval of Section 11 and the answers to D-SEC-1 to D-SEC-5** (this task must not start without them) |
| Acceptance criteria | AC-8.1 to AC-8.3; M-6; every ST test in Section 11.2 that applies to the approved options passes; mutation evidence for each |
| Tests | ST-01 to ST-21 and ST-23 (backend). ST-22 belongs to T-204; ST-24 belongs to T-202. T-205 records only its own backend tests and mutation evidence |
| Definition of Done | All applicable backend ST tests pass. Mutation evidence is recorded for each backend security control owned by T-205. Existing tests pass. Report lists each control and its test. ST-22 and ST-24 are reported by their owning tasks. Merged and verified |

## 13.7 T-204: Frontend/backend integration and error handling

| Field | Content |
|-------|---------|
| Scope | Real `ChatApi` using `HttpClient` to `POST /api/chat`. Dev-server proxy for `/api` with the backend port from `BACKEND_PORT`. Error classification in Section 6.4 against real responses. Request timeout. Integration checks. A scripted smoke check is optional and, if added, is a new script and does not change the existing three |
| Allowed changes | `src/frontend/proxy.conf.js` (new); `angular.json` (`proxyConfig` only); `src/frontend/src/app/**`; optional new script under `scripts/`; documentation status and the Phase 2 verification record |
| Prohibited changes | Backend behavior changes (a defect found here goes back to its own task); CORS; new dependencies; changes to the existing scripts' behavior |
| Dependencies | T-202, T-203 and T-205 merged and verified |
| Acceptance criteria | AC-2.1 to AC-2.4, AC-4.1 to AC-4.3, AC-5.1 to AC-5.3 end to end; M-1 to M-3, M-7, M-8 |
| Tests | F-15, F-16, I-01 to I-07, ST-22, and manual MV-01 to MV-12 on the Product Owner's machine. ST-24 is owned and reported by T-202 |
| Definition of Done | All automated checks pass. Product Owner reports MV-01 to MV-12. Observation in Section 3 re-verified on Windows (I-02). Report delivered. Merged and verified |

After T-204 is merged, Phase 2 closes with a documentation-only change (Section 15), as in Phase 0 and Phase 1.

---

# 14. Open Decisions for Product Owner Approval

Approval of this document does not approve a decision unless the decision is answered here. Where the Product Owner accepts the recommendation, write "Accept".

| ID | Question | Alternatives | Recommendation | Product Owner answer |
|----|----------|--------------|----------------|----------------------|
| D-SEC-1 | Local authorization (token) in Phase 2 | A none, B proxy-injected token, C page-fetched token, D launcher-passed token (Section 11.4) | A for Phase 2, with a mandatory decision before Phase 3 enables any Agent capability | Accept A — no token in Phase 2; revisit before Phase 3 enables any Agent capability |
| D-SEC-2 | POST without Origin | Accept / Reject (Section 11.4) | Reject | Reject |
| D-SEC-3 | API docs endpoints | Always / Development only / Disabled | Development only | Development only |
| D-SEC-4 | Request size limit | 16 KiB (413) / Validation only | 16 KiB | 16 KiB (413) |
| D-SEC-5 | P-SEC-1 beyond Phase 1 | Standing rule / Phase by phase | Standing rule | Standing rule for all phases |
| D-API-1 | Frontend request timeout | 10 s / other | 10 s | 10 seconds |
| D-API-2 | UI language | English / Thai / Thai and English | Thai and English with a visible language switch; Thai default on first visit; persist only the selected UI language in `localStorage` | Accept — bilingual UI; no chat history or messages stored |
| D-API-3 | Mock reply content | Reply includes the message length (Section 7.3) / Constant text only | Includes the length: it proves the message reached the backend and was counted correctly, without echoing user text | Accept — include the trimmed message's Unicode code-point length |
| D-GIT-1 | Branch naming | `<type>/<task-id>-<short-name>` for all work, including docs | Product Owner selected this convention on 2026-10-20 | Accept — use `<type>/<task-id>-<short-name>` for every task, including docs |
| D-APP-1 | Approval of this specification (T-201) | Approve / Request changes | Approve after the answers above | Pending — updated specification is awaiting Product Owner review |

---

# 15. Definition of Done (Phase 2)

Phase 2 is complete only when all of these are true and evidenced:

- [ ] This specification is approved by the Product Owner and open decisions are answered (T-201)
- [ ] T-202, T-203, T-205 and T-204 are each merged into `main`, one at a time, each with its report
- [ ] A user can open the web application, send a message and see the mock reply (MV-01, MV-02)
- [ ] All failure states in Section 6.3 behave as specified (MV-07, MV-08, F-08, F-09, F-16)
- [ ] All applicable security tests pass (ST-01 to ST-24). Mutation evidence is required for backend security controls owned by T-205; ST-22 is evidenced by T-204 and ST-24 by T-202
- [ ] No capability to execute system-changing actions exists (B-12)
- [ ] No new runtime dependency, AI provider, API key, database or authentication framework was added
- [ ] Existing tests still pass and counts are not below baseline (M-7)
- [ ] `scripts\test.ps1` passes on the Product Owner's Windows 11 machine, and manual checks MV-01 to MV-12 are reported (M-8)
- [ ] `README.md`, `docs/PROJECT.md`, `docs/ROADMAP.md` and this document show the true status, backed by evidence
- [ ] The completion report (Section 17) is delivered and the Product Owner has approved Phase 2
- [ ] Phase 3 has not been started. It requires an explicit start from the Product Owner

Do not mark any item before it has been verified. Do not mark Phase 2 complete before the Product Owner approves.

---

# 16. Git Workflow

- The repository defines one rule: **do not commit directly to `main`**. Work on a branch, push it, and merge only after the Product Owner has reviewed it (`docs/PHASE-0.md`). The approved naming convention is `<type>/<task-id>-<short-name>` for all work, including docs.
- **Product Owner decision (2026-10-20):** Use `<type>/<task-id>-<short-name>` for every branch, including documentation branches. Examples: `docs/t-201-phase-2-spec`, `feat/t-202-chat-ui`, `feat/t-203-chat-endpoint`, `feat/t-205-local-web-security`, `feat/t-204-integration`. Do not use a separate naming format for documentation branches.
- One task is one branch and one pull request. Branch from the latest `main`
- Commit messages use the existing style: `type: short summary` with a body listing the changes
- Before each commit: review the full diff, run the tests that apply, check that only allowed paths changed, and scan the diff for secrets
- Do not claim a push, merge or test result that has not been verified. After a push, verify the branch on the remote. After a merge, verify `main` from a fresh clone
- When the Implementation Engineer has no push access, the change is delivered as a patch file and the Product Owner pushes it. The Implementation Engineer then verifies the remote before reporting
- Do not rewrite shared history. Do not merge into `main` without the Product Owner's approval
- After the last task is merged and verified, a documentation-only change updates the status of this document, `README.md`, `docs/PROJECT.md` and `docs/ROADMAP.md`. Historical completion records of Phase 0 and Phase 1 are not changed

---

# 17. Completion Report Template

Used at the end of every task and at the end of Phase 2.

```text
PHASE 2 TASK REPORT

Task ID and title:
Branch:
Base commit (main):
Final commit hash:
Date:

1. Summary of what was done:
2. Files created or changed (path and purpose):
3. Files confirmed unchanged that are outside Allowed changes: yes / no (list any exception)
4. Acceptance criteria (ID, met / not met, evidence):
5. Tests actually run (command, environment, result with counts):
6. Tests not run, and why:
7. Mutation or negative-test evidence (for security tasks):
8. Manual verification performed by the Product Owner (ID, result):
9. New dependencies added: none / list (requires prior approval)
10. Security decisions applied (D-SEC IDs and answers):
11. Deviations from the specification, and who approved them:
12. Git: branch pushed (yes / no, verified how), pull request, merge status, main verified (yes / no)
13. Open issues and risks:
14. Status of the next task: not started (requires explicit Product Owner start)
```

At the end of Phase 2, add: results of MV-01 to MV-12, the final test counts, a list of every merged task with commit hashes, and the statement that Phase 3 is not started.