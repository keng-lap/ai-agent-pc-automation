import pytest
from pydantic import ValidationError

from agent_backend.conversation_contract import UniversalConversationResponse


def _base(**overrides):
    value = {
        "schema_version": "1.0",
        "message": "Hello",
        "intent": "conversation.chat",
        "status": "completed",
        "data": {"packages": [], "environment": None, "checks": [], "notes": []},
        "needs_clarification": False,
        "clarification": None,
    }
    value.update(overrides)
    return value


def _package(name):
    return {
        "name": name,
        "version": "latest",
        "purpose": "Requested software",
        "suggested_source": "Official vendor source",
        "suggested_method": "Package manager if verified",
    }


def test_conversation_chat_uses_empty_action_data():
    result = UniversalConversationResponse.model_validate(_base())
    assert result.intent == "conversation.chat"
    assert result.data.packages == []


def test_single_and_multiple_software_requests_use_same_envelope():
    single = _base(
        message="Install Chrome",
        intent="software.install",
        status="ready",
        data={"packages": [_package("Chrome")], "environment": None, "checks": [], "notes": []},
    )
    multiple = _base(
        message="Install Chrome and Git",
        intent="software.install_multiple",
        status="ready",
        data={"packages": [_package("Chrome"), _package("Git")], "environment": None, "checks": [], "notes": []},
    )
    assert UniversalConversationResponse.model_validate(single).data.packages[0].name == "Chrome"
    assert len(UniversalConversationResponse.model_validate(multiple).data.packages) == 2


def test_environment_prepare_requires_environment_and_can_propose_many_packages():
    value = _base(
        message="Prepare a .NET environment",
        intent="environment.prepare",
        status="ready",
        data={
            "packages": [_package(".NET SDK"), _package("VS Code")],
            "environment": {
                "name": ".NET development",
                "purpose": "Build and test .NET applications",
                "development_type": "Web API",
                "framework_version": "LTS",
            },
            "checks": [],
            "notes": [],
        },
    )
    assert UniversalConversationResponse.model_validate(value).intent == "environment.prepare"


def test_clarification_requires_consistent_status_and_message():
    value = _base(
        status="needs_clarification",
        needs_clarification=True,
        clarification="Which .NET workload do you need?",
    )
    assert UniversalConversationResponse.model_validate(value).needs_clarification
    with pytest.raises(ValidationError):
        UniversalConversationResponse.model_validate(
            {**value, "needs_clarification": False}
        )


def test_intent_specific_data_mismatch_is_rejected():
    value = _base(
        intent="software.install",
        status="ready",
        data={"packages": [], "environment": None, "checks": [], "notes": []},
    )
    with pytest.raises(ValidationError):
        UniversalConversationResponse.model_validate(value)


def test_unknown_fields_and_untrusted_execution_metadata_are_rejected():
    with pytest.raises(ValidationError):
        UniversalConversationResponse.model_validate(
            _base(executable="powershell.exe", command="winget install --id anything")
        )
    value = _base(data={
        "packages": [],
        "environment": None,
        "checks": [],
        "notes": [],
        "installer_url": "https://attacker.invalid/setup.exe",
    })
    with pytest.raises(ValidationError):
        UniversalConversationResponse.model_validate(value)
