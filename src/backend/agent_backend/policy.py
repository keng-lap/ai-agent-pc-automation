"""Backend-owned, immutable Phase 5 risk/permission policy (P5-510)."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from agent_backend.tools import TOOL_CATALOG, ToolId

RiskLevel = Literal["R0", "R1", "R2", "R3"]
PermissionLevel = Literal["P0", "P1", "P2", "P3"]
PolicyOutcome = Literal["allow_informational", "allow_dry_run", "deny"]

POLICY_VERSION = "phase5-policy-v1"


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """One immutable risk-to-permission decision in the approved matrix."""

    risk: RiskLevel
    permission: PermissionLevel
    outcome: PolicyOutcome


# A tuple and read-only mapping prevent runtime mutation by callers.
POLICY_MATRIX: tuple[PolicyRule, ...] = (
    PolicyRule("R0", "P0", "allow_informational"),
    PolicyRule("R1", "P1", "allow_dry_run"),
    PolicyRule("R2", "P2", "deny"),
    PolicyRule("R3", "P3", "deny"),
)
_RULE_BY_RISK = MappingProxyType({rule.risk: rule for rule in POLICY_MATRIX})

# Current tools can only produce a plan/report. Their real machine-changing
# capability is not registered here and remains outside the Phase 5 boundary.
_TOOL_POLICY = MappingProxyType(
    {
        "software.install": ("R1", "P1", "dry_run"),
        "software.remove": ("R1", "P1", "dry_run"),
    }
)


class PolicyConfigurationError(RuntimeError):
    """Raised when static policy or catalog configuration is unsafe."""


def validate_policy_configuration() -> None:
    """Fail startup if the static matrix and fixed dry-run catalog disagree."""
    expected = {"R0", "R1", "R2", "R3"}
    risks = [rule.risk for rule in POLICY_MATRIX]
    if len(risks) != len(set(risks)) or set(risks) != expected:
        raise PolicyConfigurationError("Policy matrix has missing or duplicate risk entries")

    expected_pairs = {
        "R0": ("P0", "allow_informational"),
        "R1": ("P1", "allow_dry_run"),
        "R2": ("P2", "deny"),
        "R3": ("P3", "deny"),
    }
    if dict(_RULE_BY_RISK) != {rule.risk: rule for rule in POLICY_MATRIX}:
        raise PolicyConfigurationError("Policy lookup does not match the approved matrix")

    for rule in POLICY_MATRIX:
        if (rule.permission, rule.outcome) != expected_pairs[rule.risk]:
            raise PolicyConfigurationError("Policy matrix contains an invalid permission mapping")

    catalog_ids = [definition.id for definition in TOOL_CATALOG]
    if len(catalog_ids) != len(set(catalog_ids)):
        raise PolicyConfigurationError("Tool catalog contains duplicate identifiers")
    if set(catalog_ids) != set(_TOOL_POLICY):
        raise PolicyConfigurationError("Tool catalog and policy mapping do not match")

    for definition in TOOL_CATALOG:
        mapping = _TOOL_POLICY.get(definition.id)
        if mapping is None:
            raise PolicyConfigurationError("Tool has no policy mapping")
        risk, permission, mode = mapping
        rule = _RULE_BY_RISK.get(risk)
        if rule is None or rule.permission != permission or rule.outcome != "allow_dry_run":
            raise PolicyConfigurationError("Tool policy is missing or not allowed for dry-run")
        if mode != "dry_run" or definition.execution_mode != "dry_run":
            raise PolicyConfigurationError("Only fixed dry-run handlers may be registered")
        if definition.approval_required is not True or definition.risk_class != "high":
            raise PolicyConfigurationError("Tool catalog metadata is inconsistent with Phase 5")


def policy_for_tool(tool_id: ToolId) -> PolicyRule:
    """Return the fixed P1 dry-run rule; never accept policy from a caller."""
    validate_policy_configuration()
    mapping = _TOOL_POLICY.get(tool_id)
    if mapping is None:
        raise PolicyConfigurationError("Unknown tool has no policy")
    rule = _RULE_BY_RISK.get(mapping[0])
    if rule is None or rule.permission != mapping[1] or rule.outcome != "allow_dry_run":
        raise PolicyConfigurationError("Tool policy is not allowed")
    return rule
