"""FastAPI application for local Gemini chat without PC automation."""

import logging
import re
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .chat import router as chat_router
from .config import load_settings
from .plan_api import router as plan_router
from .policy import validate_policy_configuration
from .security import LocalWebSecurityMiddleware


def create_app(settings=None) -> FastAPI:
    validate_policy_configuration()
    settings = settings or load_settings()
    docs_enabled = settings.app_env == "development"
    application = FastAPI(
        title="AI Agent PC Automation",
        version="0.0.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    application.add_middleware(LocalWebSecurityMiddleware, settings=settings)
    application.include_router(chat_router)
    application.include_router(plan_router)
    return application


settings = load_settings()
app = create_app(settings)

INVALID_REQUEST = (
    'Invalid request. Send JSON like {"message": "...", "language": "th"} '
    "with 1 to 2000 characters and language th or en."
)
SAFE_GEMINI_ERROR_CODES = frozenset(
    {
        "key_or_access",
        "quota_exceeded",
        "model_unavailable",
        "provider_unavailable",
        "request_rejected",
        "request_timeout",
        "network_error",
        "invalid_response",
        "empty_response",
        "google_cloud_auth_missing",
        "sdk_runtime_error",
        "unknown",
    }
)
SAFE_PLAN_ERROR_CODES = frozenset({"gemini_plan_unavailable", "invalid_structured_plan"})
SAFE_ERROR_TYPE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": INVALID_REQUEST})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code == 405:
        detail = "Method Not Allowed"
    elif exc.status_code == 404:
        detail = "Not Found"
    elif (
        exc.status_code == 502
        and request.url.path in {"/api/chat", "/api/settings/gemini/test"}
        and isinstance(exc.detail, dict)
        and set(exc.detail).issubset({"code", "error_type", "stage", "trace"})
        and "code" in exc.detail
        and isinstance(exc.detail["code"], str)
        and exc.detail["code"] in SAFE_GEMINI_ERROR_CODES
        and (
            "error_type" not in exc.detail
            or (
                isinstance(exc.detail["error_type"], str)
                and SAFE_ERROR_TYPE_PATTERN.fullmatch(exc.detail["error_type"])
            )
        )
        and (
            "stage" not in exc.detail
            or (
                isinstance(exc.detail["stage"], str)
                and SAFE_ERROR_TYPE_PATTERN.fullmatch(exc.detail["stage"])
            )
        )
        and (
            "trace" not in exc.detail
            or (
                isinstance(exc.detail["trace"], str)
                and len(exc.detail["trace"]) <= 256
                and re.fullmatch(r"[A-Za-z0-9_.,-]+", exc.detail["trace"])
            )
        )
    ):
        detail = exc.detail
    elif (
        exc.status_code == 502
        and request.url.path == "/api/plans"
        and isinstance(exc.detail, dict)
        and set(exc.detail).issubset({"code", "provider_code"})
        and exc.detail.get("code") in SAFE_PLAN_ERROR_CODES
        and (
            "provider_code" not in exc.detail
            or exc.detail["provider_code"] in SAFE_GEMINI_ERROR_CODES
        )
    ):
        # Plan errors expose fixed allowlisted codes only, never provider messages.
        detail = exc.detail
    else:
        detail = "Internal server error."
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Do not include request data or exception text, which could contain a message.
    frames = traceback.extract_tb(exc.__traceback__)
    safe_frames = [
        traceback.FrameSummary(frame.filename, frame.lineno, frame.name, line="")
        for frame in frames
    ]
    logging.getLogger(__name__).error(
        "Unexpected request failure\n%s", "".join(traceback.format_list(safe_frames))
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
