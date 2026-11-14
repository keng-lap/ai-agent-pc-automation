import pytest

from agent_backend.webauthn_security import (
    CEREMONY_TTL_SECONDS,
    WebAuthnCeremonyError,
    WebAuthnCeremonyStore,
    WebAuthnPlatformAuthenticator,
)

OWNER = "stable-google-sub"
SESSION = "session-id-that-is-long-enough"
ORIGIN = "http://127.0.0.1:4200"
RP_ID = "127.0.0.1"


def test_ceremony_is_bound_to_owner_session_purpose_origin_and_rp_id():
    store = WebAuthnCeremonyStore()
    ceremony = store.create(
        owner_sub=OWNER,
        session_id=SESSION,
        purpose="bootstrap",
        origin=ORIGIN,
        rp_id=RP_ID,
    )

    with pytest.raises(WebAuthnCeremonyError):
        store.consume(
            ceremony.ceremony_id,
            owner_sub=OWNER,
            session_id="another-session-id-that-is-long",
            purpose="bootstrap",
            origin=ORIGIN,
            rp_id=RP_ID,
        )

    # A failed cross-session attempt consumes the one-use challenge.
    with pytest.raises(WebAuthnCeremonyError):
        store.consume(
            ceremony.ceremony_id,
            owner_sub=OWNER,
            session_id=SESSION,
            purpose="bootstrap",
            origin=ORIGIN,
            rp_id=RP_ID,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner_sub", "another-owner"),
        ("purpose", "recovery"),
        ("origin", "http://localhost:4200"),
        ("rp_id", "localhost"),
    ],
)
def test_ceremony_rejects_mismatched_bindings(field, value):
    store = WebAuthnCeremonyStore()
    ceremony = store.create(
        owner_sub=OWNER,
        session_id=SESSION,
        purpose="bootstrap",
        origin=ORIGIN,
        rp_id=RP_ID,
    )
    bindings = {
        "owner_sub": OWNER,
        "session_id": SESSION,
        "purpose": "bootstrap",
        "origin": ORIGIN,
        "rp_id": RP_ID,
    }
    bindings[field] = value

    with pytest.raises(WebAuthnCeremonyError):
        store.consume(ceremony.ceremony_id, **bindings)


def test_ceremony_expires_using_monotonic_clock():
    wall = [1000.0]
    monotonic = [50.0]
    store = WebAuthnCeremonyStore(
        clock=lambda: wall[0],
        monotonic_clock=lambda: monotonic[0],
    )
    ceremony = store.create(
        owner_sub=OWNER,
        session_id=SESSION,
        purpose="recovery",
        origin=ORIGIN,
        rp_id=RP_ID,
    )
    wall[0] += CEREMONY_TTL_SECONDS * 10
    monotonic[0] += CEREMONY_TTL_SECONDS

    with pytest.raises(WebAuthnCeremonyError):
        store.consume(
            ceremony.ceremony_id,
            owner_sub=OWNER,
            session_id=SESSION,
            purpose="recovery",
            origin=ORIGIN,
            rp_id=RP_ID,
        )


def test_registration_options_require_platform_authenticator_and_user_verification():
    service = WebAuthnPlatformAuthenticator(rp_id=RP_ID)
    ceremony_id, options = service.begin_registration(
        owner_sub=OWNER,
        session_id=SESSION,
        purpose="bootstrap",
        origin=ORIGIN,
    )

    assert ceremony_id
    assert options["rp"]["id"] == RP_ID
    assert options["authenticatorSelection"]["authenticatorAttachment"] == "platform"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["challenge"]
    assert options["user"]["id"]
