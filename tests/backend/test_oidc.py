import pytest

from agent_backend.oidc import (
    GOOGLE_AUTHORIZATION_ENDPOINT,
    GOOGLE_TOKEN_ENDPOINT,
    GoogleIdentity,
    GoogleOidcClient,
    MasterUserAllowlist,
    OidcAuthenticationError,
    OidcTransactionStore,
)


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def valid_claims(nonce):
    return {
        "iss": "https://accounts.google.com",
        "aud": "test-client-id",
        "sub": "stable-google-sub",
        "email": "owner@example.test",
        "email_verified": True,
        "nonce": nonce,
        "iat": 1000,
        "auth_time": 1000,
        "exp": 1600,
    }


def build_client(*, now=1100, claims=None, response=None, transactions=None):
    claims = claims or valid_claims("expected-nonce")
    http = FakeHttp(response or FakeResponse({"id_token": "signed-id-token"}))
    def verifier(_token):
        return claims
    client = GoogleOidcClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="http://127.0.0.1:8000/api/auth/google/callback",
        transaction_store=transactions or OidcTransactionStore(clock=lambda: now),
        http_session=http,
        token_verifier=verifier,
        clock=lambda: now,
    )
    return client, http


def test_begin_login_uses_code_flow_pkce_nonce_and_minimal_scopes():
    client, _http = build_client()
    result = client.begin_login().authorization_url

    assert result.startswith(f"{GOOGLE_AUTHORIZATION_ENDPOINT}?")
    assert "response_type=code" in result
    assert "scope=openid+email+profile" in result
    assert "code_challenge_method=S256" in result
    assert "code_challenge=" in result
    assert "state=" in result
    assert "nonce=" in result
    assert "prompt=select_account" in result
    assert "max_age=0" not in result


def test_begin_login_can_request_fresh_authentication_only_when_needed():
    client, _http = build_client()
    result = client.begin_login(require_recent_auth=True).authorization_url

    assert "prompt=login" in result
    assert "max_age=0" in result


def test_oidc_transaction_is_one_time_and_expires():
    now = [1000.0]
    store = OidcTransactionStore(clock=lambda: now[0])
    transaction = store.create()

    assert store.consume(transaction.state) == transaction
    assert store.consume(transaction.state) is None

    expired = store.create()
    now[0] = expired.expires_at
    assert store.consume(expired.state) is None


def test_complete_login_exchanges_code_with_pkce_and_discards_provider_tokens():
    claims = valid_claims("nonce-from-transaction")
    http = FakeHttp(
        FakeResponse(
            {
                "id_token": "signed-id-token",
                "access_token": "must-not-be-retained",
                "refresh_token": "must-not-be-retained",
                "scope": "openid email profile",
            }
        )
    )
    store = OidcTransactionStore(clock=lambda: 1100)
    transaction = store.create()
    claims["nonce"] = transaction.nonce
    client = GoogleOidcClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="http://127.0.0.1:8000/api/auth/google/callback",
        transaction_store=store,
        http_session=http,
        token_verifier=lambda _token: claims,
        clock=lambda: 1100,
    )

    identity = client.complete_login(state=transaction.state, code="authorization-code")

    assert identity == GoogleIdentity(sub="stable-google-sub", email="owner@example.test")
    url, kwargs = http.calls[0]
    assert url == GOOGLE_TOKEN_ENDPOINT
    assert kwargs["data"]["code_verifier"] == transaction.code_verifier
    assert kwargs["data"]["client_secret"] == "test-client-secret"
    assert "refresh_token" not in kwargs["data"]


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://evil.example"},
        {"aud": "another-client"},
        {"nonce": "wrong-nonce"},
        {"email_verified": False},
        {"sub": ""},
        {"exp": 999},
        {"iat": 0},
        {"auth_time": 700},
        {"auth_time": 1200},
        {"azp": "another-client"},
    ],
)
def test_invalid_identity_claims_are_rejected(change):
    claims = valid_claims("expected-nonce")
    claims.update(change)
    client, _http = build_client(claims=claims)

    with pytest.raises(OidcAuthenticationError):
        client._validate_identity_token(
            "signed-id-token",
            expected_nonce="expected-nonce",
            require_recent_auth="auth_time" in change,
        )


def test_invalid_state_and_missing_code_fail_closed():
    client, _http = build_client()

    with pytest.raises(OidcAuthenticationError, match="state"):
        client.complete_login(state="unknown-state-value-123456", code="code")

    result = client.begin_login()
    state = result.authorization_url.split("state=", 1)[1].split("&", 1)[0]
    # URL-safe state contains no characters requiring form decoding.
    with pytest.raises(OidcAuthenticationError, match="authorization code"):
        client.complete_login(state=state, code="")


def test_google_master_allowlist_uses_stable_sub_not_email():
    allowlist = MasterUserAllowlist("stable-google-sub")

    assert allowlist.is_master_user(
        GoogleIdentity(sub="stable-google-sub", email="changed@example.test")
    )
    assert not allowlist.is_master_user(
        GoogleIdentity(sub="another-sub", email="owner@example.test")
    )


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://127.0.0.1:8000/callback",
        "http://evil.example:8000/callback",
        "http://127.0.0.1/callback",
        "http://user@127.0.0.1:8000/callback",
    ],
)
def test_redirect_uri_must_be_loopback_http(redirect_uri):
    with pytest.raises(ValueError, match="loopback"):
        GoogleOidcClient(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri=redirect_uri,
            token_verifier=lambda _token: {},
        )



def test_oidc_transaction_expiry_uses_monotonic_time_after_wall_clock_rollback():
    wall_time = [100000.0]
    monotonic_time = [50.0]
    store = OidcTransactionStore(
        clock=lambda: wall_time[0],
        monotonic_clock=lambda: monotonic_time[0],
    )
    transaction = store.create()

    wall_time[0] -= 86_400
    monotonic_time[0] += 300

    assert store.consume(transaction.state) is None


def test_session_expiry_uses_monotonic_time_after_wall_clock_rollback():
    from agent_backend.oidc import ApplicationSessionStore

    wall_time = [100000.0]
    monotonic_time = [80.0]
    store = ApplicationSessionStore(
        ttl_seconds=60,
        clock=lambda: wall_time[0],
        monotonic_clock=lambda: monotonic_time[0],
    )
    identity = GoogleIdentity(sub="stable-google-sub", email="owner@example.test")
    allowlist = MasterUserAllowlist("stable-google-sub")
    credential = store.create(identity=identity, allowlist=allowlist)

    wall_time[0] -= 86_400
    monotonic_time[0] += 60

    assert store.resolve(credential.token) is None


def test_session_store_requires_explicit_ttl_and_master_allowlist():
    from agent_backend.oidc import ApplicationSessionStore

    with pytest.raises(ValueError, match="session TTL"):
        ApplicationSessionStore(ttl_seconds=0)

    store = ApplicationSessionStore(ttl_seconds=1800, clock=lambda: 1100)
    allowlist = MasterUserAllowlist("stable-google-sub")
    identity = GoogleIdentity(sub="stable-google-sub", email="owner@example.test")
    credential = store.create(identity=identity, allowlist=allowlist)

    principal = store.resolve(credential.token)
    assert principal.owner_sub == identity.sub
    assert principal.session_id == credential.session_id
    assert credential.token not in store._sessions


def test_session_store_rejects_non_master_identity():
    from agent_backend.oidc import ApplicationSessionStore

    store = ApplicationSessionStore(ttl_seconds=1800, clock=lambda: 1100)
    allowlist = MasterUserAllowlist("stable-google-sub")
    identity = GoogleIdentity(sub="another-sub", email="owner@example.test")

    with pytest.raises(OidcAuthenticationError, match="Master User"):
        store.create(identity=identity, allowlist=allowlist)


def test_session_store_expires_and_revokes_tokens():
    from agent_backend.oidc import ApplicationSessionStore

    now = [1100.0]
    store = ApplicationSessionStore(ttl_seconds=60, clock=lambda: now[0])
    identity = GoogleIdentity(sub="stable-google-sub", email="owner@example.test")
    allowlist = MasterUserAllowlist("stable-google-sub")
    credential = store.create(identity=identity, allowlist=allowlist)

    assert store.resolve(credential.token) is not None
    assert store.revoke(credential.token)
    assert store.resolve(credential.token) is None

    second = store.create(identity=identity, allowlist=allowlist)
    now[0] = second.expires_at
    assert store.resolve(second.token) is None


def test_only_fresh_google_auth_session_satisfies_recent_auth_gate():
    from agent_backend.oidc import ApplicationSessionStore

    now = [1100.0]
    store = ApplicationSessionStore(
        ttl_seconds=1800,
        clock=lambda: now[0],
        monotonic_clock=lambda: now[0],
    )
    allowlist = MasterUserAllowlist("stable-google-sub")
    ordinary = GoogleIdentity(sub="stable-google-sub", email="owner@example.test")
    fresh = GoogleIdentity(
        sub="stable-google-sub",
        email="owner@example.test",
        recently_authenticated=True,
    )

    ordinary_credential = store.create(identity=ordinary, allowlist=allowlist)
    ordinary_principal = store.resolve(ordinary_credential.token)
    assert not store.is_recently_authenticated(ordinary_principal, max_age_seconds=300)

    fresh_credential = store.create(identity=fresh, allowlist=allowlist)
    assert store.resolve(ordinary_credential.token) is None
    fresh_principal = store.resolve(fresh_credential.token)
    assert store.is_recently_authenticated(fresh_principal, max_age_seconds=300)

    now[0] += 301
    assert not store.is_recently_authenticated(fresh_principal, max_age_seconds=300)


def test_session_store_capacity_is_bounded():
    from agent_backend.oidc import ApplicationSessionStore

    store = ApplicationSessionStore(ttl_seconds=1800, clock=lambda: 1100, capacity=1)
    identity = GoogleIdentity(sub="stable-google-sub", email="owner@example.test")
    allowlist = MasterUserAllowlist("stable-google-sub")
    store.create(identity=identity, allowlist=allowlist)

    with pytest.raises(OidcAuthenticationError, match="capacity"):
        store.create(identity=identity, allowlist=allowlist)
