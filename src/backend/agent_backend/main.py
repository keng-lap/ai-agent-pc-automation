"""FastAPI application for the local web application.

The chat route returns a deterministic placeholder only. It does not invoke an
Agent, execute tools, or perform PC automation.
"""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .chat import router as chat_router

app = FastAPI(title="AI Agent PC Automation", version="0.0.0")
app.include_router(chat_router)

INVALID_REQUEST = (
    'Invalid request. Send JSON like {"message": "...", "language": "th"} '
    "with 1 to 2000 characters and language th or en."
)


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
