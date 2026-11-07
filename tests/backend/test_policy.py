import pytest

from agent_backend import policy
from agent_backend.tools import TOOL_CATALOG


def test_policy_matrix_is_complete_and_maps_disabled_levels_to_deny():
    policy.validate_policy_configuration()

    assert [(rule.risk, rule.permission, rule.outcome) for rule in policy.POLICY_MATRIX] == [
        ("R0", "P0", "allow_informational"),
        ("R1", "P1", "allow_dry_run"),
        ("R2", "P2", "deny"),
        ("R3", "P3", "deny"),
    ]


def test_current_tool_catalog_is_mapped_only_to_p1_dry_run():
    policy.validate_policy_configuration()

    for definition in TOOL_CATALOG:
        rule = policy.policy_for_tool(definition.id)
        assert rule.risk == "R1"
        assert rule.permission == "P1"
        assert rule.outcome == "allow_dry_run"
        assert definition.execution_mode == "dry_run"


def test_policy_decision_allows_only_catalogued_p1_dry_run_tools():
    for definition in TOOL_CATALOG:
        decision = policy.decide_tool_policy(definition.id)
        assert decision.allowed is True
        assert decision.deny_reason is None
        assert decision.rule is not None
        assert decision.rule.permission == "P1"
        assert decision.rule.outcome == "allow_dry_run"


def test_unknown_tool_has_a_typed_deny_decision():
    decision = policy.decide_tool_policy("shell.run")

    assert decision.allowed is False
    assert decision.deny_reason == "unknown_tool"
    with pytest.raises(policy.PolicyDeniedError) as raised:
        policy.require_tool_allowed("shell.run")
    assert raised.value.reason == "unknown_tool"


def test_policy_matrix_rejects_missing_or_duplicate_risk(monkeypatch):
    monkeypatch.setattr(policy, "POLICY_MATRIX", policy.POLICY_MATRIX[:-1])
    with pytest.raises(policy.PolicyConfigurationError):
        policy.validate_policy_configuration()


def test_policy_matrix_rejects_permission_escalation(monkeypatch):
    invalid = (
        policy.PolicyRule("R0", "P0", "allow_informational"),
        policy.PolicyRule("R1", "P1", "allow_dry_run"),
        policy.PolicyRule("R2", "P1", "allow_dry_run"),
        policy.PolicyRule("R3", "P3", "deny"),
    )
    monkeypatch.setattr(policy, "POLICY_MATRIX", invalid)
    with pytest.raises(policy.PolicyConfigurationError):
        policy.validate_policy_configuration()


def test_catalog_policy_mismatch_fails_closed(monkeypatch):
    monkeypatch.setattr(policy, "_TOOL_POLICY", policy.MappingProxyType({}))
    with pytest.raises(policy.PolicyConfigurationError):
        policy.validate_policy_configuration()


def test_unknown_tool_policy_fails_closed():
    with pytest.raises(policy.PolicyDeniedError) as raised:
        policy.policy_for_tool("shell.run")
    assert raised.value.reason == "unknown_tool"


def test_static_policy_definitions_are_immutable():
    with pytest.raises(TypeError):
        policy._TOOL_POLICY["software.install"] = ("R3", "P3", "execute")
    with pytest.raises((AttributeError, TypeError)):
        policy.POLICY_MATRIX[0].risk = "R3"


def test_policy_matrix_rejects_duplicate_risk_entries(monkeypatch):
    duplicate = (
        policy.POLICY_MATRIX[0],
        policy.POLICY_MATRIX[1],
        policy.POLICY_MATRIX[2],
        policy.POLICY_MATRIX[2],
    )
    monkeypatch.setattr(policy, "POLICY_MATRIX", duplicate)

    with pytest.raises(policy.PolicyConfigurationError):
        policy.validate_policy_configuration()


@pytest.mark.parametrize("malformed", [None, {"risk": "R2", "permission": "P2", "outcome": "deny"}])
def test_policy_matrix_rejects_malformed_entries(monkeypatch, malformed):
    monkeypatch.setattr(
        policy,
        "POLICY_MATRIX",
        (policy.POLICY_MATRIX[0], policy.POLICY_MATRIX[1], malformed, policy.POLICY_MATRIX[3]),
    )

    with pytest.raises(policy.PolicyConfigurationError, match="malformed"):
        policy.validate_policy_configuration()



@pytest.mark.parametrize(
    "malformed_rule",
    [
        policy.PolicyRule(["R2"], "P2", "deny"),
        policy.PolicyRule("R2", ["P2"], "deny"),
        policy.PolicyRule("R2", "P2", ["deny"]),
    ],
)
def test_policy_matrix_rejects_rules_with_malformed_field_types(monkeypatch, malformed_rule):
    monkeypatch.setattr(
        policy,
        "POLICY_MATRIX",
        (policy.POLICY_MATRIX[0], policy.POLICY_MATRIX[1], malformed_rule, policy.POLICY_MATRIX[3]),
    )

    with pytest.raises(policy.PolicyConfigurationError, match="malformed"):
        policy.validate_policy_configuration()
