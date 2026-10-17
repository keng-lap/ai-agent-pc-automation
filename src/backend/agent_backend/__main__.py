"""Run the backend: `python -m agent_backend` (from the virtual environment)."""

import uvicorn

from .config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "agent_backend.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        log_level=settings.log_level,
        reload=settings.app_env == "development",
    )


if __name__ == "__main__":
    main()
