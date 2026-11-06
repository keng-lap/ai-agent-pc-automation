"""Local deterministic plan-review API for P5-514.

This router never calls Gemini, inspects Windows, downloads software, or executes
machine-changing actions. It composes the existing deterministic planner and
P1 dry-run-only plan/tool contracts.
"""

import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_backend.planner import TaskIntent, TaskPlan, create_task_plan
from agent_backend.plans import (
    DryRunPlan,
    PlanCapacityError,
    PlanExpiredError,
    PlanNotFoundError,
    PlanStore,
    ProgramPlan,
)
from agent_backend.tools import ToolRequest, ToolResult, execute_tool, select_tool

router = APIRouter()
_plan_store = PlanStore()


class PlanReviewRequest(BaseModel):
    """Only user-level request text and display language are accepted."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request: str = Field(min_length=1, max_length=2000)
    language: Literal["th", "en"] = "th"

    @field_validator("request")
    @classmethod
    def normalize_request(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("request must not be empty")
        return normalized


class PlanReviewResponse(BaseModel):
    """User-facing deterministic review; never an execution grant."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    request: str
    interpretation: TaskIntent
    task_plan: TaskPlan
    dry_run_plan: DryRunPlan | None
    tool_result: ToolResult | None
    questions: tuple[str, ...]
    notice: Literal["DRY_RUN_ONLY_NO_CHANGES_MADE"] = "DRY_RUN_ONLY_NO_CHANGES_MADE"


def _programs_for_review(
    intent: TaskIntent, language: Literal["th", "en"]
) -> tuple[str, tuple[ProgramPlan, ...]] | None:
    """Return only a clearly requested/safely implied core program, never optional tools."""
    if intent.category in ("software_install", "software_remove"):
        if intent.target is None:
            return None
        tool_id = "software.install" if intent.category == "software_install" else "software.remove"
        purpose = "ซอฟต์แวร์ตามคำขอ" if language == "th" else "Software requested by the user"
        reason = (
            "ระบุไว้ในคำขอของผู้ใช้"
            if language == "th"
            else "Explicitly named in the user's request"
        )
        item = ProgramPlan(
            order=1,
            program=intent.target,
            version="ยังไม่ได้ระบุ" if language == "th" else "Not specified",
            purpose=purpose,
            reason=reason,
            source="ยังไม่ได้ตรวจสอบ" if language == "th" else "Not checked",
            impact="ยังไม่ได้ตรวจสอบ" if language == "th" else "Unknown / not checked",
            status="NEEDS_CLARIFICATION",
        )
        return tool_id, (item,)

    if intent.category == "development_task" and intent.target == "Java":
        item = ProgramPlan(
            order=1,
            program="JDK",
            version="ยังไม่ได้ระบุ" if language == "th" else "Not specified",
            purpose=(
                "ชุดพัฒนาและคอมไพเลอร์สำหรับภาษา Java"
                if language == "th"
                else "Java development kit and compiler"
            ),
            reason=(
                "JDK เป็นเครื่องมือหลักที่จำเป็นสำหรับคอมไพล์และรันโปรแกรม Java"
                if language == "th"
                else "A JDK is the core tool required to compile and run Java applications"
            ),
            source="ยังไม่ได้ตรวจสอบ" if language == "th" else "Not checked",
            impact="ยังไม่ได้ตรวจสอบ" if language == "th" else "Unknown / not checked",
            status="NEEDS_CLARIFICATION",
        )
        return "software.install", (item,)

    return None


def _questions_for_review(
    intent: TaskIntent, language: Literal["th", "en"]
) -> tuple[str, ...]:
    if intent.category == "development_task" and intent.target == "Java":
        if language == "th":
            return (
                "ต้องการ JDK เวอร์ชันใด (เช่น 21 LTS)?",
                "ต้องการใช้ IDE ใด หรือให้แนะนำตัวเลือกก่อน?",
            )
        return (
            "Which JDK version do you want (for example, 21 LTS)?",
            "Which IDE would you like, or should options be presented first?",
        )
    return ()


@router.post("/api/plans", response_model=PlanReviewResponse)
def create_plan_review(payload: PlanReviewRequest) -> PlanReviewResponse:
    """Create a deterministic plan review and optional P1 dry-run report."""
    task_plan = create_task_plan(payload.request, payload.language)
    intent = task_plan.intent
    if intent.category == "development_task" and re.search(r"\bjava\b", payload.request, re.IGNORECASE):
        intent = intent.model_copy(update={"target": "Java"})
        task_plan = task_plan.model_copy(update={"intent": intent})
    dry_run_plan = None
    tool_result = None
    candidate = _programs_for_review(intent, payload.language)

    if candidate is not None:
        tool_id, programs = candidate
        try:
            dry_run_plan = _plan_store.create(tool_id, programs)
            tool_request = ToolRequest(tool_id=tool_id, target=programs[0].program)
            tool_result = execute_tool(tool_request)
        except PlanCapacityError:
            raise HTTPException(status_code=503, detail="Plan capacity reached.") from None
        except ValueError:
            # A missing or unsupported target remains a clarification, never a fallback.
            dry_run_plan = None
            tool_result = None

    return PlanReviewResponse(
        request=payload.request,
        interpretation=intent,
        task_plan=task_plan,
        dry_run_plan=dry_run_plan,
        tool_result=tool_result,
        questions=_questions_for_review(intent, payload.language),
    )


@router.get("/api/plans/{plan_id}", response_model=DryRunPlan)
def get_plan_review(plan_id: str) -> DryRunPlan:
    """Read an exact short-lived plan; no acknowledgement or execution transition exists."""
    if len(plan_id) != 32 or any(char not in "0123456789abcdef" for char in plan_id):
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        return _plan_store.get(plan_id)
    except PlanExpiredError:
        raise HTTPException(status_code=410, detail="Plan expired.") from None
    except PlanNotFoundError:
        raise HTTPException(status_code=404, detail="Plan not found.") from None
