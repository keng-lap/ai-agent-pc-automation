"""Local deterministic Agent orchestration for T-305.

The selected agent is ChatGPT, but provider-backed requests stay disabled until
authorization and data-handling decisions are approved. This core runs locally.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agent_backend.planner import Language, TaskPlan, create_task_plan
from agent_backend.tools import ToolResult, execute_tool, select_tool

AgentProvider = Literal["chatgpt"]


class AgentResponse(BaseModel):
    """Safe response contract returned by the local Agent pipeline."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    reply: str
    provider: AgentProvider = "chatgpt"
    provider_connected: Literal[False] = False
    plan: TaskPlan
    tool_result: ToolResult | None = None


def run_agent(message: str, language: Language, provider: AgentProvider) -> AgentResponse:
    """Plan and dry-run a request without contacting an AI provider or the OS."""
    if provider != "chatgpt":
        raise ValueError("Unsupported agent provider")

    plan = create_task_plan(message, language)
    try:
        tool_request = select_tool(plan.intent)
    except ValueError:
        tool_result = None
    else:
        tool_result = execute_tool(tool_request)

    return AgentResponse(
        reply=_format_reply(plan, tool_result),
        provider=provider,
        plan=plan,
        tool_result=tool_result,
    )


def _format_reply(plan: TaskPlan, tool_result: ToolResult | None) -> str:
    if plan.language == "th":
        lines = ["เลือก ChatGPT แล้ว (โหมดจำลองในเครื่อง; ยังไม่ได้เชื่อมต่อผู้ให้บริการ)", "แผนงาน:"]
        lines.extend(
            f"{step.order}. {step.title}: {step.detail}" for step in plan.steps
        )
        if tool_result is not None:
            lines.append(f"ผลจำลอง: {tool_result.summary} ต้องได้รับอนุมัติก่อนดำเนินการจริง")
        else:
            lines.append("ไม่มีเครื่องมือที่อนุญาตสำหรับงานนี้ และไม่มีการเปลี่ยนแปลงเครื่อง")
        return "\n".join(lines)

    lines = [
        "ChatGPT selected (local preview; provider connection is not enabled).",
        "Plan:",
    ]
    lines.extend(f"{step.order}. {step.title}: {step.detail}" for step in plan.steps)
    if tool_result is not None:
        lines.append(f"Dry-run result: {tool_result.summary} Approval is required before real execution.")
    else:
        lines.append("No allowlisted tool applies to this task; no changes were made.")
    return "\n".join(lines)
