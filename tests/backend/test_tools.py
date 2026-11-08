import pytest
from pydantic import ValidationError

from agent_backend import agent_core, policy, tools
from agent_backend.audit import AUDIT_SINK
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


def test_handler_identity_replacement_after_policy_decision_fails_closed(monkeypatch):
    handler_calls = []
    replacement_calls = []

    def original_handler(request):
        handler_calls.append(request)

    def replacement_handler(request):
        replacement_calls.append(request)
        raise AssertionError("replacement handler must not be dispatched")

    original_handlers = {"software.install": original_handler}
    replacement_handlers = {"software.install": replacement_handler}
    monkeypatch.setattr(tools, "_HANDLERS", original_handlers)
    original_require = policy.require_tool_allowed

    def decide_then_replace_handler(tool_id):
        decision = original_require(tool_id)
        monkeypatch.setattr(tools, "_HANDLERS", replacement_handlers)
        return decision

    monkeypatch.setattr(policy, "require_tool_allowed", decide_then_replace_handler)
    request = ToolRequest(tool_id="software.install", target="Example")

    with pytest.raises(policy.PolicyDeniedError) as raised:
        execute_tool(request)

    assert raised.value.reason == "handler_unavailable"
    assert handler_calls == []
    assert replacement_calls == []



@pytest.mark.parametrize(
    "payload",
    [
        {"tool_id": "software.install", "target": ""},
        {"tool_id": "software.install", "target": "x" * 121},
        {"tool_id": "software.install", "target": 123},
        {"tool_id": "software.install", "target": "Chrome", "extra": "not-allowed"},
        {"tool_id": "shell.run", "target": "whoami"},
    ],
)
def test_tool_request_rejects_invalid_type_extra_and_out_of_range_values(payload):
    with pytest.raises(ValidationError):
        ToolRequest.model_validate(payload)


def test_tool_request_accepts_exact_target_length_boundary():
    request = ToolRequest(tool_id="software.install", target="C" * 120)

    assert len(request.target) == 120


def test_tool_request_rejects_model_supplied_risk_or_permission_claims():
    with pytest.raises(ValidationError):
        ToolRequest.model_validate(
            {
                "tool_id": "software.install",
                "target": "Example",
                "risk_class": "low",
                "permission": "P0",
                "execution_mode": "execute",
            }
        )

    decision = policy.decide_tool_policy("software.install")
    assert decision.allowed is True
    assert decision.rule is not None
    assert (decision.rule.risk, decision.rule.permission, decision.rule.outcome) == (
        "R1",
        "P1",
        "allow_dry_run",
    )


@pytest.mark.parametrize(
    ("tool_id", "risk", "permission"),
    [
        ("synthetic.inspect", "R2", "P2"),
        ("synthetic.execute", "R3", "P3"),
    ],
)
def test_disabled_p2_p3_policy_never_invokes_a_spy_handler(
    monkeypatch, tool_id, risk, permission
):
    handler_calls = []

    def spy_handler(request):
        handler_calls.append(request)
        raise AssertionError("disabled P2/P3 handler must never be invoked")

    # Isolate the decision branch for a synthetic disabled capability. The
    # production catalog remains unchanged and no real handler is registered.
    monkeypatch.setattr(policy, "validate_policy_configuration", lambda: None)
    monkeypatch.setattr(
        policy,
        "_TOOL_POLICY",
        policy.MappingProxyType(
            {
                tool_id: (risk, permission, "inspect" if permission == "P2" else "execute")
            }
        ),
    )
    monkeypatch.setattr(tools, "_HANDLERS", {tool_id: spy_handler})
    request = ToolRequest.model_construct(tool_id=tool_id, target="Synthetic")

    with pytest.raises(policy.PolicyDeniedError) as raised:
        execute_tool(request)

    assert raised.value.reason == "risk_denied"
    assert handler_calls == []



def test_legacy_agent_entrypoint_only_plans_and_never_dispatches(monkeypatch):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append("called")
        raise AssertionError("legacy entry point must never dispatch")

    monkeypatch.setattr(agent_core, "execute_tool", forbidden, raising=False)
    monkeypatch.setattr(agent_core, "require_tool_allowed", forbidden, raising=False)

    response = agent_core.run_agent("Install Example", "en", "chatgpt")

    assert response.task_status == "planned"
    assert response.tool_result is None
    assert calls == []


def test_dispatch_records_allowlisted_policy_event():
    AUDIT_SINK.clear()

    result = execute_tool(ToolRequest(tool_id="software.install", target="Example"))

    events = AUDIT_SINK.snapshot()
    assert result.status == "dry_run"
    assert len(events) == 1
    assert events[0].event_type == "policy.allowed"
    assert events[0].tool_id == "software.install"
    assert events[0].outcome == "allowed"
    assert events[0].deny_reason is None


def test_policy_denial_records_reason_without_blocking_denial(monkeypatch):
    AUDIT_SINK.clear()

    def deny(_tool_id):
        raise policy.PolicyDeniedError("permission_denied")

    monkeypatch.setattr(policy, "require_tool_allowed", deny)
    request = ToolRequest(tool_id="software.install", target="Example")

    with pytest.raises(policy.PolicyDeniedError):
        execute_tool(request)

    events = AUDIT_SINK.snapshot()
    assert len(events) == 1
    assert events[0].event_type == "policy.denied"
    assert events[0].outcome == "denied"
    assert events[0].deny_reason == "permission_denied"


def test_audit_sink_failure_does_not_block_dry_run(monkeypatch):
    def unavailable(_event):
        raise OSError("synthetic sink failure")

    monkeypatch.setattr(AUDIT_SINK, "record", unavailable)
    result = execute_tool(ToolRequest(tool_id="software.install", target="Example"))

    assert result.status == "dry_run"
