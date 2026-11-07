"""Keep backend tests isolated from developer runtime settings."""

import os

import pytest

# The app loads the repository .env when imported. Tests use fixed local
# settings so TestClient Host and Origin headers stay valid.
os.environ["BACKEND_HOST"] = "127.0.0.1"
os.environ["BACKEND_PORT"] = "8000"
os.environ["FRONTEND_PORT"] = "4200"
os.environ["LOCAL_AGENT_TOKEN"] = "a" * 64



@pytest.fixture(autouse=True)
def stub_gemini_structured_plans(monkeypatch):
    """Keep API tests offline; provider behavior is tested explicitly in test_chat.py."""
    from agent_backend import plan_api

    def generate(prompt, response_schema):
        request = prompt.split("<user_request>\n", 1)[-1].split("\n</user_request>", 1)[0]
        return response_schema(
            goal=request or "Task plan",
            steps=(
                {
                    "title": "Review the request",
                    "detail": "Prepare a display-only plan for user review.",
                },
            ),
            questions=(),
        ).model_dump_json()

    monkeypatch.setattr(plan_api, "generate_structured_plan", generate)
