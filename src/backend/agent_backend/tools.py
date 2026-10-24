"""Backend-owned allowlisted tools with dry-run-only execution (T-304)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_backend.planner import IntentKind, TaskIntent

ToolId = Literal["software.install", "software.remove"]
ToolStatus = Literal["dry_run"]


class ToolRequest(BaseModel):
    """A structured tool request; arbitrary commands and extra fields are rejected."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    tool_id: ToolId
    target: str = Field(min_length=1, max_length=120)


class ToolResult(BaseModel):
    """A preview that explicitly records that nothing was executed."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    tool_id: ToolId
    target: str
    status: ToolStatus = "dry_run"
    approval_required: Literal[True] = True
    summary: str = Field(min_length=1, max_length=300)


_ALLOWED_INTENTS: dict[ToolId, IntentKind] = {
    "software.install": "software_install",
    "software.remove": "software_remove",
}


def select_tool(intent: TaskIntent) -> ToolRequest:
    """Select one backend-owned tool based on the validated planner intent."""
    for tool_id, category in _ALLOWED_INTENTS.items():
        if intent.category == category:
            if intent.target is None:
                raise ValueError("A software target is required before selecting a tool")
            return ToolRequest(tool_id=tool_id, target=intent.target)
    raise ValueError("No allowlisted tool is available for this task")


def validate_tool_request(intent: TaskIntent, request: ToolRequest) -> ToolRequest:
    """Reject proposals that do not match the planner-owned task and target."""
    expected_category = _ALLOWED_INTENTS[request.tool_id]
    if intent.category != expected_category:
        raise ValueError("Tool is not allowed for this task")
    if intent.target is None or request.target.casefold() != intent.target.casefold():
        raise ValueError("Tool target must match the planned target")
    return request


def execute_tool(request: ToolRequest) -> ToolResult:
    """Return a deterministic preview. This function has no machine side effects."""
    action = "install" if request.tool_id == "software.install" else "remove"
    return ToolResult(
        tool_id=request.tool_id,
        target=request.target,
        summary=f"Dry run only: would {action} {request.target}; no changes were made.",
    )
