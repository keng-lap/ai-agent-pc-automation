import pytest
from pydantic import ValidationError

from agent_backend import agent_core, policy, tools
from agent_backend.planner import create_task_plan
from agent_backend.tools import (
    _HANDLERS,
    ToolRequest,
    execute_tool,
    list_tools,
    select_tool,
    validate_tool_request,
)


@pytest.mark.parametrize(
    ("message", "tool_id", "target"),
    [
        ("Install Google Chrome", "software.install", "Google Chrome"),
        ("Uninstall Python", "software.remove", "Python"),
    ],
)
def test_selection_uses_only_the_allowlisted_tool_for_the_planned_intent(
    message, tool_id, target
):
    intent = create_task_plan(message, "en").intent

    assert select_tool(intent) == ToolRequest(tool_id=tool_id, target=target)


@pytest.mark.parametrize("message", ["Build a website", "What time is it?"])
def test_tasks_without_allowlisted_tools_are_rejected(message):
    intent = create_task_plan(message, "en").intent

    with pytest.raises(ValueError, match="No allowlisted tool"):
        select_tool(intent)


def test_unknown_tool_and_arbitrary_command_payload_are_rejected():
    with pytest.raises(ValidationError):
        ToolRequest.model_validate({"tool_id": "shell.run", "target": "whoami"})
    with pytest.raises(ValidationError):
        ToolRequest.model_validate(
            {"tool_id": "software.install", "target": "Chrome", "command": "whoami"}
        )


def test_model_proposal_must_match_planner_category_and_target():
    intent = create_task_plan("Install Google Chrome", "en").intent

    with pytest.raises(ValueError, match="not allowed"):
        validate_tool_request(
            intent, ToolRequest(tool_id="software.remove", target="Google Chrome")
        )
    with pytest.raises(ValueError, match="target"):
        validate_tool_request(
            intent, ToolRequest(tool_id="software.install", target="ExampleTool")
        )


def test_machine_changing_tool_returns_dry_run_without_execution():
    request = ToolRequest(tool_id="software.install", target="Google Chrome")

    result = execute_tool(request)

    assert result.status == "dry_run"
    assert result.approval_required is True
    assert result.summary == (
        "Dry run only: would install Google Chrome; no changes were made."
    )



def test_catalog_contains_only_static_dry_run_tools():
    catalog = list_tools()

    assert [item.id for item in catalog] == ["software.install", "software.remove"]
    assert all(item.risk_class == "high" for item in catalog)
    assert all(item.execution_mode == "dry_run" for item in catalog)
    assert all(item.approval_required is True for item in catalog)


def test_dispatch_result_is_validated_and_remains_dry_run():
    request = ToolRequest(tool_id="software.remove", target="ExampleTool")

    result = execute_tool(request)

    assert result.tool_id == "software.remove"
    assert result.status == "dry_run"
    assert result.approval_required is True
    assert "no changes were made" in result.summary


def test_handler_dispatch_map_is_immutable():
    with pytest.raises(TypeError):
        _HANDLERS["software.install"] = lambda request: request


@pytest.mark.parametrize(
    "reason",
    ["risk_denied", "permission_denied", "execution_mode_denied"],
)
def test_denied_policy_never_reaches_a_spy_handler(monkeypatch, reason):
    handler_calls = []

    def spy_handler(request):
        handler_calls.append(request)

    monkeypatch.setattr(
        "agent_backend.tools._HANDLERS",
        {"software.install": spy_handler},
    )

    def deny(_tool_id):
        raise policy.PolicyDeniedError(reason)

    monkeypatch.setattr(policy, "require_tool_allowed", deny)
    request = ToolRequest(tool_id="software.install", target="Example")

    with pytest.raises(policy.PolicyDeniedError) as raised:
        execute_tool(request)

    assert raised.value.reason == reason
    assert handler_calls == []


def test_unknown_constructed_tool_never_reaches_a_spy_handler(monkeypatch):
    handler_calls = []
    request = ToolRequest.model_construct(tool_id="shell.run", target="whoami")
    monkeypatch.setattr(
        tools,
        "_HANDLERS",
        {"shell.run": lambda item: handler_calls.append(item)},
    )

    with pytest.raises(policy.PolicyDeniedError) as raised:
        execute_tool(request)

    assert raised.value.reason == "unknown_tool"
    assert handler_calls == []


def test_invalid_policy_configuration_never_reaches_a_spy_handler(monkeypatch):
    handler_calls = []
    monkeypatch.setattr(policy, "_TOOL_POLICY", {})
    monkeypatch.setattr(
        tools,
        "_HANDLERS",
        {"software.install": lambda item: handler_calls.append(item)},
    )
    request = ToolRequest(tool_id="software.install", target="Example")

    with pytest.raises(policy.PolicyConfigurationError):
        execute_tool(request)

    assert handler_calls == []


def test_agent_core_policy_decision_denies_before_dispatch(monkeypatch):
    handler_calls = []

    def deny(_tool_id):
        raise policy.PolicyDeniedError("permission_denied")

    monkeypatch.setattr(agent_core, "require_tool_allowed", deny)
    monkeypatch.setattr(
        "agent_backend.tools._HANDLERS",
        {"software.install": lambda item: handler_calls.append(item)},
    )

    with pytest.raises(policy.PolicyDeniedError) as raised:
        agent_core.run_agent("Install Example", "en", "chatgpt")

    assert raised.value.reason == "permission_denied"
    assert handler_calls == []
