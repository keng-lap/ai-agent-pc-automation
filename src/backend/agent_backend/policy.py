"""Backend-owned, immutable Phase 5 risk/permission policy (P5-510)."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from agent_backend.tools import TOOL_CATALOG

RiskLevel = Literal["R0", "R1", "R2", "R3"]
PermissionLevel = Literal["P0", "P1", "P2", "P3"]
PolicyOutcome = Literal["allow_informational", "allow_dry_run", "deny"]
PolicyDenyReason = Literal[
    "unknown_tool",
    "risk_denied",
    "permission_denied",
    "execution_mode_denied",
    "handler_unavailable",
]

POLICY_VERSION = "phase5-policy-v1"


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """One immutable risk-to-permission decision in the approved matrix."""

    risk: RiskLevel
    permission: PermissionLevel
    outcome: PolicyOutcome


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """A backend-derived allow or deny result for a registered tool."""

    allowed: bool
    rule: PolicyRule | None = None
    deny_reason: PolicyDenyReason | None = None


class PolicyDeniedError(RuntimeError):
    """Raised when a tool request is denied by the backend policy."""

    def __init__(self, reason: PolicyDenyReason) -> None:
        self.reason = reason
        super().__init__(reason)


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
    if not isinstance(POLICY_MATRIX, tuple) or any(
        type(rule) is not PolicyRule for rule in POLICY_MATRIX
    ):
        raise PolicyConfigurationError("Policy matrix contains malformed rule entries")

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


def decide_tool_policy(tool_id: str) -> PolicyDecision:
    """Evaluate a tool against backend-owned policy; callers cannot supply a grant."""
    validate_policy_configuration()
    mapping = _TOOL_POLICY.get(tool_id)
    if mapping is None:
        return PolicyDecision(allowed=False, deny_reason="unknown_tool")

    risk, permission, mode = mapping
    rule = _RULE_BY_RISK.get(risk)
    if rule is None or rule.permission != permission:
        raise PolicyConfigurationError("Tool policy does not match the approved matrix")
    if rule.outcome == "deny":
        return PolicyDecision(allowed=False, rule=rule, deny_reason="risk_denied")
    if permission != "P1":
        return PolicyDecision(allowed=False, rule=rule, deny_reason="permission_denied")
    if rule.outcome != "allow_dry_run" or mode != "dry_run":
        return PolicyDecision(allowed=False, rule=rule, deny_reason="execution_mode_denied")
    return PolicyDecision(allowed=True, rule=rule)


def require_tool_allowed(tool_id: str) -> PolicyDecision:
    """Fail closed with a typed reason unless static policy allows P1 dry-run."""
    decision = decide_tool_policy(tool_id)
    if not decision.allowed:
        if decision.deny_reason is None:
            raise PolicyConfigurationError("Denied policy result has no typed reason")
        raise PolicyDeniedError(decision.deny_reason)
    return decision


def policy_for_tool(tool_id: str) -> PolicyRule:
    """Return the fixed rule for a tool only when policy permits its dry-run."""
    decision = require_tool_allowed(tool_id)
    if decision.rule is None:
        raise PolicyConfigurationError("Allowed policy result has no rule")
    return decision.rule
