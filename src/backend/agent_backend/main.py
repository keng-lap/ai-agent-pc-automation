"""FastAPI application (Phase 1 skeleton).

Only a health endpoint exists. No agent, tool, or PC-automation logic belongs
here until the roadmap phase that defines it has been explicitly started.
"""

from fastapi import FastAPI

app = FastAPI(title="AI Agent PC Automation", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
