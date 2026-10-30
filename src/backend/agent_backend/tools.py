"""Backend-owned static tool catalog and dry-run-only dispatch (T-402)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_backend.planner import IntentKind, TaskIntent

ToolId = Literal["software.install", "software.remove"]
ToolStatus = Literal["dry_run"]
RiskClass = Literal["high"]
ExecutionMode = Literal["dry_run"]


class ToolRequest(BaseModel):
    """Structured request; arbitrary commands and extra fields are rejected."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    tool_id: ToolId
    target: str = Field(min_length=1, max_length=120)


class ToolResult(BaseModel):
    """Preview explicitly records that nothing was executed."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    tool_id: ToolId
    target: str
    status: ToolStatus = "dry_run"
    approval_required: Literal[True] = True
    summary: str = Field(min_length=1, max_length=300)


class ToolDefinition(BaseModel):
    """Descriptive, immutable metadata; never accepted from a client request."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: ToolId
    description: str = Field(min_length=1, max_length=160)
    supported_intents: tuple[IntentKind, ...] = Field(min_length=1)
    risk_class: RiskClass = "high"
    execution_mode: ExecutionMode = "dry_run"
    approval_required: Literal[True] = True


TOOL_CATALOG: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        id="software.install",
        description="Preview a requested software installation; no system changes.",
        supported_intents=("software_install",),
    ),
    ToolDefinition(
        id="software.remove",
        description="Preview a requested software removal; no system changes.",
        supported_intents=("software_remove",),
    ),
)

_ALLOWED_INTENTS: dict[ToolId, IntentKind] = {
    definition.id: definition.supported_intents[0]
    for definition in TOOL_CATALOG
}


def list_tools() -> tuple[ToolDefinition, ...]:
    """Return the immutable backend-owned catalog."""
    return TOOL_CATALOG


def select_tool(intent: TaskIntent) -> ToolRequest:
    """Select a registered tool based on the validated planner intent."""
    for definition in TOOL_CATALOG:
        if intent.category in definition.supported_intents:
            if intent.target is None:
                raise ValueError("A software target is required before selecting a tool")
            return ToolRequest(tool_id=definition.id, target=intent.target)
    raise ValueError("No allowlisted tool is available for this task")


def validate_tool_request(intent: TaskIntent, request: ToolRequest) -> ToolRequest:
    """Reject proposals that do not match the planner-owned task and target."""
    expected_category = _ALLOWED_INTENTS.get(request.tool_id)
    if expected_category is None or intent.category != expected_category:
        raise ValueError("Tool is not allowed for this task")
    if intent.target is None or request.target.casefold() != intent.target.casefold():
        raise ValueError("Tool target must match the planned target")
    return request


def _preview_install(request: ToolRequest) -> ToolResult:
    return ToolResult(
        tool_id=request.tool_id,
        target=request.target,
        summary=f"Dry run only: would install {request.target}; no changes were made.",
    )


def _preview_remove(request: ToolRequest) -> ToolResult:
    return ToolResult(
        tool_id=request.tool_id,
        target=request.target,
        summary=f"Dry run only: would remove {request.target}; no changes were made.",
    )


# Fixed code-owned dispatch map. Request data can never supply a callable/module name.
_HANDLERS = {
    "software.install": _preview_install,
    "software.remove": _preview_remove,
}


def execute_tool(request: ToolRequest) -> ToolResult:
    """Dispatch only to a fixed dry-run handler and validate its typed result."""
    handler = _HANDLERS.get(request.tool_id)
    if handler is None:
        raise ValueError("No registered handler is available for this tool")
    result = handler(request)
    return ToolResult.model_validate(result.model_dump())
