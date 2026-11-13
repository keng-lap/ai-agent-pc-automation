"""FastAPI application for local Gemini chat without PC automation."""

import logging
import os
import re
import shlex
import sys
import traceback

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth_api import build_auth_services, require_session
from .auth_api import router as auth_router
from .chat import router as chat_router
from .config import load_settings
from .plan_api import router as plan_router
from .policy import validate_policy_configuration
from .security import LocalWebSecurityMiddleware
from .software_approval_api import router as software_approval_router
from .software_discovery_api import router as software_discovery_router



def enforce_single_worker(*, environ=None, argv=None) -> None:
    """Reject known multi-worker launch configurations for process-local auth state."""
    env = os.environ if environ is None else environ
    args = list(sys.argv[1:] if argv is None else argv)
    worker_values = []
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        raw = env.get(name)
        if raw is not None and str(raw).strip():
            worker_values.append((name, str(raw).strip()))
    gunicorn_args = env.get("GUNICORN_CMD_ARGS")
    if gunicorn_args:
        args.extend(shlex.split(str(gunicorn_args)))

    index = 0
    while index < len(args):
        token = args[index]
        if token in ("--workers", "-w"):
            if index + 1 >= len(args):
                raise RuntimeError("Worker count argument is incomplete.")
            worker_values.append((token, args[index + 1]))
            index += 1
        elif token.startswith("--workers=") or token.startswith("-w="):
            worker_values.append((token.split("=", 1)[0], token.split("=", 1)[1]))
        index += 1

    for source, raw in worker_values:
        try:
            count = int(raw)
        except (TypeError, ValueError):
            raise RuntimeError(f"Invalid worker count in {source}.") from None
        if count < 1:
            raise RuntimeError(f"Invalid worker count in {source}.")
        if count != 1:
            raise RuntimeError(
                "Multi-worker mode is unsupported while security state is process-local."
            )


def create_app(settings=None, auth_services=None) -> FastAPI:
    enforce_single_worker()
    validate_policy_configuration()
    settings = settings or load_settings()
    if auth_services is None:
        auth_services = build_auth_services(settings)
    docs_enabled = settings.app_env == "development"
    application = FastAPI(
        title="AI Agent PC Automation",
        version="0.0.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    application.state.settings = settings
    application.state.auth_services = auth_services
    application.add_middleware(LocalWebSecurityMiddleware, settings=settings)
    application.include_router(auth_router)
    application.include_router(chat_router, dependencies=[Depends(require_session)])
    application.include_router(plan_router, dependencies=[Depends(require_session)])
    application.include_router(software_discovery_router, dependencies=[Depends(require_session)])
    application.include_router(software_approval_router, dependencies=[Depends(require_session)])
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
        # Expose only fixed, allowlisted plan error codes; never provider messages.
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
