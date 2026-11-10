#!/usr/bin/env python3
"""Live, read-only smoke test for the Gemini 3.8 Flash Developer API."""
from __future__ import annotations

import os
import sys

from google import genai
from google.genai import errors, types

MODEL = "gemini-3.8-flash"
EXPECTED_MARKER = "AI_AGENT_GEMINI_SMOKE_OK"
REQUEST_TIMEOUT_MS = 30_000


def _is_timeout_error(exc: BaseException) -> bool:
    """Recognize timeout exceptions without exposing provider or request details."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if "timeout" in type(current).__name__.lower():
            return True
        current = current.__cause__ or current.__context__
    return False


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("FAIL: GEMINI_API_KEY secret is not configured.")
        return 2

    print(f"Model: {MODEL}")
    try:
        with genai.Client(
            api_key=api_key,
            vertexai=False,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        ) as client:
            response = client.models.generate_content(
                model=MODEL,
                contents=f"Reply with exactly this token: {EXPECTED_MARKER}",
                config=types.GenerateContentConfig(max_output_tokens=32),
            )
        reply = (response.text or "").strip()
        if EXPECTED_MARKER not in reply:
            print("FAIL: Gemini returned an empty or unexpected response.")
            return 1
    except Exception as exc:  # noqa: BLE001 - suppress provider and credential details
        if _is_timeout_error(exc):
            print(
                "FAIL: Gemini API request timed out "
                f"after {REQUEST_TIMEOUT_MS // 1000} seconds."
            )
        elif isinstance(exc, errors.APIError):
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            print(
                "FAIL: Gemini API request rejected "
                f"(http_code={code}, provider_status={status})."
            )
        else:
            print(
                f"FAIL: Gemini smoke test raised {type(exc).__name__}; "
                "details suppressed."
            )
        return 1

    print("PASS: Gemini API accepted generateContent and returned the expected marker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
