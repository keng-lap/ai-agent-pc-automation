"""Minimal Gemini adapter for the local Chat MVP.

The API key is held in process memory only. It is never returned by an API
endpoint, written to disk, or included in logs. Restarting the backend clears it.
"""
from __future__ import annotations

from threading import RLock

from google import genai

MODEL_NAME = "gemini-3.1-flash-lite"
_lock = RLock()
_api_key: str | None = None


class GeminiNotConfiguredError(RuntimeError):
    """Raised when a user has not configured a Gemini API key."""


def save_api_key(api_key: str) -> None:
    value = api_key.strip()
    if not 20 <= len(value) <= 512:
        raise ValueError("API key length is invalid")
    with _lock:
        global _api_key
        _api_key = value


def is_configured() -> bool:
    with _lock:
        return _api_key is not None


def _client(api_key: str | None = None) -> genai.Client:
    with _lock:
        key = api_key or _api_key
    if not key:
        raise GeminiNotConfiguredError("Gemini API key is not configured")
    return genai.Client(api_key=key)


def test_connection() -> None:
    response = _client().models.generate_content(
        model=MODEL_NAME,
        contents="Reply with the single word OK.",
    )
    if not (response.text or "").strip():
        raise RuntimeError("Gemini returned an empty response")


def generate_reply(message: str) -> str:
    response = _client().models.generate_content(
        model=MODEL_NAME,
        contents=message,
    )
    reply = (response.text or "").strip()
    if not reply:
        raise RuntimeError("Gemini returned an empty response")
    return reply
