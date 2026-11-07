# P5-515 Q30 — Mobile and Screen Reader Verification

## Purpose

Close the Q30 evidence gap with browser-emulated mobile layout checks and a repeatable manual screen-reader protocol. Automated browser assertions are supporting evidence only; they do not claim physical-device or screen-reader verification.

## Automated mobile viewport coverage

Run from `src/frontend`:

```powershell
npm run test:e2e
```

The opt-in Playwright suite includes:
- 320×568 small viewport
- 375×667 iPhone SE-sized viewport
- 390×844 iPhone-sized viewport
- 430×932 large mobile viewport
- Horizontal overflow assertions
- Visibility and accessible-name checks for the chat heading, language controls, message textbox, send button, and conversation log
- Keyboard focus assertions for the message textbox and send button

These are Chromium viewport-emulation checks on the local web app. They are **not** tests on a physical phone and do not establish full assistive-technology compatibility.

## Physical mobile device test — required evidence

Use a real phone connected to the same trusted local network as the Windows host. Keep the app bound to the approved local network/loopback design; do not expose it to the public internet or enable remote PC control. If the current app only binds to 127.0.0.1, perform the physical-device check only after the Product Owner has separately approved and configured a safe local-network test path. Do not weaken the loopback or authentication controls as an ad-hoc workaround.

Record:
1. Device model and OS version.
2. Browser name and version.
3. Screen size / orientation.
4. Whether the app loads using the approved local test path.
5. Whether heading, language controls, conversation log, message field, and send button are visible and usable.
6. Whether there is horizontal scrolling, clipped text, overlapping controls, or inaccessible content.
7. Result, date, and tester.

Do not record API keys, local authentication tokens, chat content, or personal information in screenshots or reports.

## Screen-reader manual protocol

### iPhone — VoiceOver + Safari

1. Enable VoiceOver in iOS Settings → Accessibility → VoiceOver.
2. Open the local app in Safari using the approved local test path.
3. Swipe through the page in reading order.
4. Confirm the app title and chat heading are announced meaningfully.
5. Confirm the language selector is announced as a group and each language button exposes its selected state.
6. Confirm the conversation area is announced as the conversation log; verify new content is announced when a harmless test reply is available.
7. Confirm the message field is announced as “ข้อความของคุณ” (or the selected language equivalent).
8. Confirm the send control is announced as “ส่งข้อความ” and its disabled state is conveyed when the field is empty.
9. Confirm focus/reading position remains understandable after changing language and moving between controls.
10. Record pass/fail per item, iOS/Safari versions, and any issue. Do not submit real machine-changing requests.

### Windows — Narrator or NVDA + supported browser

1. Start Narrator or NVDA and open the app in the supported browser.
2. Navigate by headings and interactive controls.
3. Confirm the page title, chat heading, language buttons, conversation log, message field, and send button have meaningful names/roles/states.
4. Use Tab and Shift+Tab to traverse controls; confirm visible focus and logical order.
5. Confirm disabled controls are announced as disabled.
6. Record the screen reader/browser versions, pass/fail results, and issues.

## Evidence status rules

- Playwright mobile viewport pass = **automated emulation evidence only**.
- A completed physical phone run = **physical mobile evidence**.
- A completed VoiceOver/Narrator/NVDA run = **manual screen-reader evidence**.
- Do not mark Q30 Covered until the physical-device and at least one screen-reader protocol have actual recorded results. If the environment cannot safely expose the local app to a phone, record the limitation and request a Product Owner decision; do not change host binding or security controls to force a pass.

## Safety boundary

No machine-changing action, OS inspection, shell execution by the Agent, public exposure, new provider, telemetry, or persistent chat storage is introduced by these tests or this protocol.
