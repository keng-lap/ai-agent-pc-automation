from fastapi.testclient import TestClient

from agent_backend.auth_api import require_session
from agent_backend.config import load_settings
from agent_backend.job_lifecycle import JobState
from agent_backend.job_store import SQLiteJobStore
from agent_backend.main import create_app
from agent_backend.oidc import SessionPrincipal

HEADERS = {
    "origin": "http://127.0.0.1:4200",
    "x-local-agent-token": "a" * 64,
}
OWNER = "google-owner-sub"


class _TestSecureStorage:
    """Test-only adapter; production platform gates remain unchanged."""

    def prepare_database_path(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)

    def finalize_database_file(self, path):
        if not path.is_file():
            raise AssertionError("test database was not created")


def build_client(tmp_path, *, authenticated=True):
    settings = load_settings(load_env_file=False)
    store = SQLiteJobStore(
        tmp_path / "private-state" / "jobs.sqlite3",
        secure_storage=_TestSecureStorage(),
    )
    app = create_app(settings, auth_services=None, job_store=store)
    if authenticated:
        app.dependency_overrides[require_session] = lambda: SessionPrincipal(
            owner_sub=OWNER,
            session_id="session-1",
        )
    return TestClient(
        app,
        base_url="http://127.0.0.1:8000",
        headers=HEADERS,
    ), store


def test_job_status_api_returns_real_persisted_job_summary(tmp_path):
    client, store = build_client(tmp_path)
    job = store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest="a" * 64,
        idempotency_key="request-1",
    )
    store.update_progress(
        job["job_id"],
        owner_id=OWNER,
        expected_version=0,
        message="Validating pinned installer evidence",
    )

    response = client.get("/api/jobs?limit=25")
    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs"][0]["job_id"] == job["job_id"]
    assert payload["jobs"][0]["state"] == "QUEUED"
    assert payload["jobs"][0]["progress_message"] == "Validating pinned installer evidence"
    assert payload["jobs"][0]["recent_events"][0]["message"] == (
        "Validating pinned installer evidence"
    )
    assert payload["checked_at"].endswith("Z")

    detail = client.get(f"/api/jobs/{job['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["job_id"] == job["job_id"]


def test_job_status_api_hides_jobs_owned_by_another_user(tmp_path):
    client, store = build_client(tmp_path)
    foreign = store.create(
        owner_id="different-owner",
        tool_id="software.install",
        action_digest="b" * 64,
        idempotency_key="foreign-request",
    )

    assert client.get(f"/api/jobs/{foreign['job_id']}").status_code == 404
    assert client.get("/api/jobs").json()["jobs"] == []


def test_job_status_api_fails_closed_when_authentication_is_disabled(tmp_path):
    client, _store = build_client(tmp_path, authenticated=False)

    response = client.get("/api/jobs")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Authentication is not configured."
    }


def test_job_status_api_rejects_invalid_limits(tmp_path):
    client, _store = build_client(tmp_path)

    assert client.get("/api/jobs?limit=0").status_code == 422
    assert client.get("/api/jobs?limit=26").status_code == 422


def test_job_status_api_does_not_dispatch_or_change_job_state(tmp_path):
    client, store = build_client(tmp_path)
    job = store.create(
        owner_id=OWNER,
        tool_id="software.install",
        action_digest="c" * 64,
        idempotency_key="request-1",
    )

    for _ in range(3):
        assert client.get("/api/jobs").status_code == 200

    persisted = store.get_for_owner(job["job_id"], OWNER)
    assert persisted["state"] == JobState.QUEUED.value
    assert len(persisted["recent_events"]) == 1
