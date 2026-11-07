#!/usr/bin/env python
"""Diagnose Gemini structured-output compatibility without calling the local agent API.

The API key is read from GEMINI_API_KEY or prompted with hidden input. It is never
written to disk, printed, or saved into the backend's in-memory configuration.
This script makes read-only Gemini generation requests only. It never creates,
approves, or dry-runs an agent plan and never accesses Windows settings or files.
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402

from agent_backend.plan_api import GeminiPlanDraft  # noqa: E402

MODEL_NAME = "gemini-3.1-flash-lite"
TEST_PROMPT = (
    "Return a short display-only plan for preparing a computer for Java development. "
    "Do not provide commands or claim that any action was performed."
)


def safe_failure(label: str, exc: Exception) -> None:
    """Print only exception metadata; never print provider messages or request data."""
    print(f"[FAIL] {label}")
    print(f"       exception_type: {type(exc).__name__}")
    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None)
        status = getattr(exc, "status", None)
        if code is not None:
            print(f"       http_code: {code}")
        if status:
            safe_status = str(status)
            if safe_status.replace("_", "").replace("-", "").isalnum():
                print(f"       provider_status: {safe_status[:80]}")
    else:
        print("       detail: suppressed to avoid exposing credentials or request data")


def run_variant(client: genai.Client, label: str, config: Any) -> bool:
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=TEST_PROMPT,
            config=config,
        )
        text = (response.text or "").strip()
        if not text:
            print(f"[FAIL] {label}: provider returned an empty response")
            return False
        print(f"[PASS] {label}: Gemini accepted the structured-output request")
        print("       response content suppressed")
        return True
    except Exception as exc:  # provider SDK may raise multiple typed errors
        safe_failure(label, exc)
        return False


def main() -> int:
    print("")
    print("AI Agent - Gemini Structured Plan Diagnostics")
    print(f"Model: {MODEL_NAME}")
    print("Safety: no local agent API, no approval, no dry-run, no Windows changes.")
    print("The script sends a harmless structured-output test request directly to Gemini.")
    print("")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        api_key = getpass.getpass("Gemini API key (hidden input; not saved): ").strip()
    if not api_key:
        print("[FAIL] No API key supplied.")
        return 2

    try:
        client = genai.Client(api_key=api_key, vertexai=False)
    except Exception as exc:
        safe_failure("Gemini SDK client initialization", exc)
        return 2
    finally:
        # Drop the local variable as soon as the client has been initialized.
        # The SDK client necessarily retains credentials for the requests below.
        pass

    schema = GeminiPlanDraft.model_json_schema()
    print(f"[INFO] Pydantic schema generated; top-level keys: {', '.join(sorted(schema))}")
    print(f"[INFO] google-genai SDK: {getattr(__import__('google.genai', fromlist=['__version__']), '__version__', 'version not exposed')}")
    print("")

    exact_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=GeminiPlanDraft,
    )
    exact_ok = run_variant(
        client,
        "Backend-equivalent config (response_schema=Pydantic model)",
        exact_config,
    )

    config_fields = getattr(types.GenerateContentConfig, "model_fields", {})
    if "response_json_schema" in config_fields:
        raw_schema_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        raw_schema_ok = run_variant(
            client,
            "JSON Schema config (response_json_schema)",
            raw_schema_config,
        )
    else:
        raw_schema_ok = False
        print("[SKIP] response_json_schema is not exposed by this installed SDK version.")

    print("")
    if exact_ok:
        print("RESULT: The backend-equivalent Gemini request is accepted by Google.")
        print("Next: investigate backend runtime/configuration and compare SDK versions.")
        return 0
    if raw_schema_ok:
        print("RESULT: Pydantic response_schema was rejected, but response_json_schema passed.")
        print("Next: review the backend schema submission format before changing production code.")
        return 1
    print("RESULT: Both available structured-output checks failed or were unavailable.")
    print("Send this sanitized output for the next diagnosis step.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
