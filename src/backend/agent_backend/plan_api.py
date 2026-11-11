"""Deterministic backend plan review with backend-owned P1 dry-run approval.

This router owns intent, policy, permissions, plan integrity, expiry, approval,
and dry-run dispatch. It never calls Gemini or performs machine changes.
"""

import re
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_backend.audit import record_optional_audit_event
from agent_backend.auth_audit import record_auth_audit_event
from agent_backend.authenticator import SecretStoreError
from agent_backend.planner import TaskIntent, TaskPlan, create_task_plan
from agent_backend.plans import (
    DryRunPlan,
    PlanCapacityError,
    PlanExpiredError,
    PlanNotFoundError,
    PlanStore,
    ProgramPlan,
)
from agent_backend.tools import TOOL_CATALOG, ToolRequest, ToolResult, execute_tool

router = APIRouter()
_plan_store = PlanStore()
_approval_lock = threading.RLock()
_approval_results: dict[str, ToolResult] = {}


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
    tool_result: ToolResult | None = None
    approved: bool = False
    questions: tuple[str, ...]
    notice: Literal["DRY_RUN_ONLY_NO_CHANGES_MADE"] = "DRY_RUN_ONLY_NO_CHANGES_MADE"
    refined_from_plan_id: str | None = None
    clarification: str | None = None


class PlanRefinementRequest(BaseModel):
    """A bounded clarification; it cannot carry policy or execution metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request: str = Field(min_length=1, max_length=2000)
    clarification: str = Field(min_length=1, max_length=500)
    language: Literal["th", "en"] = "th"

    @field_validator("request", "clarification")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("text must not be empty")
        return normalized


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
            # The explicitly named target is sufficient for a P1 preview. Unknown
            # version/source/impact remain visibly unverified; they do not block Dry Run.
            status="PLANNED",
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
    """Create a deterministic backend review plan without calling Gemini or running tools."""
    task_plan = create_task_plan(payload.request, payload.language)
    intent = task_plan.intent
    if intent.category == "development_task" and re.search(r"\bjava\b", payload.request, re.IGNORECASE):
        intent = intent.model_copy(update={"target": "Java"})
        task_plan = task_plan.model_copy(update={"intent": intent})

    # The backend creates the trusted, typed plan deterministically from the
    # user's original request. Gemini's conversational prose is never parsed
    # as policy or used as a second source of plan truth. This also avoids a
    # second provider call with a model-specific JSON schema after chat succeeds.
    dry_run_plan = None
    candidate = _programs_for_review(intent, payload.language)

    if candidate is not None:
        tool_id, programs = candidate
        try:
            # Creating a review plan must never run even the mock dry-run tool.
            dry_run_plan = _plan_store.create(tool_id, programs)
            record_optional_audit_event(
                event_type="plan.created",
                tool_id=tool_id,
                outcome="allowed",
            )
        except PlanCapacityError:
            raise HTTPException(status_code=503, detail="Plan capacity reached.") from None
        except ValueError:
            # A missing or unsupported target remains a clarification, never a fallback.
            dry_run_plan = None

    return PlanReviewResponse(
        request=payload.request,
        interpretation=intent,
        task_plan=task_plan,
        dry_run_plan=dry_run_plan,
        tool_result=None,
        approved=False,
        questions=_questions_for_review(intent, payload.language),
    )


class PlanApprovalRequest(BaseModel):
    """Approval carries only a challenge reference and a six-digit TOTP proof."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    challenge_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    totp_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class StepUpChallengeResponse(BaseModel):
    """Short-lived exact-action challenge metadata; no secret is returned."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    challenge_id: str
    plan_id: str
    expires_at: float


class PlanApprovalResponse(BaseModel):
    """Result of one explicit approval; this is always a mock/dry-run report."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    plan_id: str
    approved: Literal[True] = True
    tool_result: ToolResult
    notice: Literal["DRY_RUN_ONLY_NO_CHANGES_MADE"] = "DRY_RUN_ONLY_NO_CHANGES_MADE"


@router.post("/api/plans/{plan_id}/step-up", response_model=StepUpChallengeResponse)
def create_plan_step_up_challenge(
    plan_id: str,
    request: Request,
) -> StepUpChallengeResponse:
    """Create a TOTP challenge bound to the exact immutable plan and session."""
    services = getattr(request.app.state, "auth_services", None)
    principal = getattr(request.state, "principal", None)
    if services is None or principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if len(plan_id) != 32 or any(char not in "0123456789abcdef" for char in plan_id):
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        plan = _plan_store.get(plan_id)
    except PlanExpiredError:
        raise HTTPException(status_code=410, detail="Plan expired.") from None
    except PlanNotFoundError:
        raise HTTPException(status_code=404, detail="Plan not found.") from None

    if (
        plan.risk_class != "R1"
        or plan.required_permission != "P1"
        or plan.mode != "dry_run"
        or any(item.status != "PLANNED" for item in plan.programs)
    ):
        raise HTTPException(status_code=409, detail="Plan is not ready for step-up approval.")

    try:
        enrolled_secret = services.secret_store.load(owner_sub=principal.owner_sub)
    except SecretStoreError:
        record_auth_audit_event(
            event_type="auth.step_up",
            outcome="denied",
            reason="secret_store_unavailable",
        )
        raise HTTPException(status_code=503, detail="Authenticator storage unavailable.") from None
    if enrolled_secret is None:
        record_auth_audit_event(
            event_type="auth.step_up",
            outcome="denied",
            reason="authenticator_not_enrolled",
        )
        raise HTTPException(status_code=403, detail="Authenticator enrollment required.")

    tool_definition = next(
        (item for item in TOOL_CATALOG if item.id == plan.tool_id),
        None,
    )
    if tool_definition is None or tool_definition.risk_class != "high":
        raise HTTPException(status_code=403, detail="Tool is not eligible for step-up approval.")

    challenge = services.step_up.create(
        owner_sub=principal.owner_sub,
        session_id=principal.session_id,
        plan_id=plan.plan_id,
        action_digest=plan.plan_digest,
        risk_class=tool_definition.risk_class,
    )
    return StepUpChallengeResponse(
        challenge_id=challenge.challenge_id,
        plan_id=challenge.plan_id,
        expires_at=challenge.expires_at,
    )


@router.post("/api/plans/{plan_id}/approve", response_model=PlanApprovalResponse)
def approve_plan_review(
    plan_id: str,
    _payload: PlanApprovalRequest,
    request: Request,
) -> PlanApprovalResponse:
    """Approve one immutable P1 plan and run its dry-run report exactly once."""
    if len(plan_id) != 32 or any(char not in "0123456789abcdef" for char in plan_id):
        raise HTTPException(status_code=404, detail="Plan not found.")
    with _approval_lock:
        try:
            plan = _plan_store.get(plan_id)
        except PlanExpiredError:
            raise HTTPException(status_code=410, detail="Plan expired.") from None
        except PlanNotFoundError:
            raise HTTPException(status_code=404, detail="Plan not found.") from None
        # Do not return a cached approval result before authenticating this request.
        # A plan ID is an opaque reference, not a bearer authorization token.
        # A retry must prove a fresh owner/session-bound TOTP challenge first.

        # These fields are server-generated and digest-bound; never accept them from a client.
        if plan.risk_class != "R1" or plan.required_permission != "P1" or plan.mode != "dry_run":
            raise HTTPException(status_code=403, detail="Plan is not eligible for dry run.")
        if any(item.status != "PLANNED" for item in plan.programs):
            raise HTTPException(status_code=409, detail="Plan requires clarification before approval.")

        services = getattr(request.app.state, "auth_services", None)
        if services is None:
            raise HTTPException(
                status_code=503,
                detail="Google sign-in and authenticator approval are not configured.",
            )
        principal = getattr(request.state, "principal", None)
        if principal is None:
            raise HTTPException(status_code=401, detail="Authentication required.")
        if services is not None:
            if (
                principal is None
                or _payload.challenge_id is None
                or _payload.totp_code is None
            ):
                raise HTTPException(status_code=403, detail="Fresh authenticator approval required.")
            try:
                secret = services.secret_store.load(owner_sub=principal.owner_sub)
            except SecretStoreError:
                raise HTTPException(status_code=503, detail="Authenticator storage unavailable.") from None
            if secret is None:
                raise HTTPException(status_code=403, detail="Authenticator enrollment required.")
            tool_definition = next(
                (item for item in TOOL_CATALOG if item.id == plan.tool_id),
                None,
            )
            if tool_definition is None or tool_definition.risk_class != "high":
                raise HTTPException(status_code=403, detail="Tool is not eligible for approval.")
            accepted = services.step_up.verify_and_consume(
                challenge_id=_payload.challenge_id,
                owner_sub=principal.owner_sub,
                session_id=principal.session_id,
                plan_id=plan.plan_id,
                action_digest=plan.plan_digest,
                risk_class=tool_definition.risk_class,
                secret=secret,
                code=_payload.totp_code,
            )
            if not accepted:
                record_auth_audit_event(
                    event_type="auth.step_up",
                    outcome="denied",
                    reason="invalid_totp",
                )
                raise HTTPException(status_code=403, detail="Step-up verification failed.")
            record_auth_audit_event(event_type="auth.step_up", outcome="success")

        # Idempotency is checked only after a fresh, exact-action authentication.
        # A consumed challenge cannot be replayed to retrieve a cached approval.
        cached = _approval_results.get(plan_id)
        if cached is not None:
            return PlanApprovalResponse(plan_id=plan_id, tool_result=cached)

        action = "ติดตั้ง" if plan.tool_id == "software.install" else "ถอนการติดตั้ง"
        try:
            # A plan can contain several programs. Dry-run every listed item;
            # never report the whole plan as simulated after dispatching only item 1.
            item_results = tuple(
                execute_tool(ToolRequest(tool_id=plan.tool_id, target=item.program))
                for item in plan.programs
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="Plan cannot be dry-run.") from None
        result = item_results[0].model_copy(
            update={
                "target": ", ".join(item.program for item in plan.programs),
                "summary": (
                    "จำลองเท่านั้น: "
                    + "; ".join(
                        f"จะ{action} {item.program}" for item in plan.programs
                    )
                    + "; ไม่มีการเปลี่ยนแปลงใด ๆ กับเครื่อง"
                ),
            }
        )
        if len(_approval_results) >= 128:
            _approval_results.pop(next(iter(_approval_results)))
        _approval_results[plan_id] = result
        return PlanApprovalResponse(plan_id=plan_id, tool_result=result)


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


def _java_refinement_programs(
    clarification: str, language: Literal["th", "en"]
) -> tuple[ProgramPlan, ...]:
    """Extract only a small, explicit Java toolchain allowlist from user text."""
    version_match = re.search(
        r"\b(?:jdk|java)\s*(?:version\s*)?(8|11|17|21|25)(?:\s*lts)?\b",
        clarification,
        re.IGNORECASE,
    )
    if version_match is None:
        version_match = re.search(
            r"\b(8|11|17|21|25)\s*lts\b", clarification, re.IGNORECASE
        )
    version = f"{version_match.group(1)} LTS" if version_match else None

    ide_aliases = (
        (("intellij idea", "intellij"), "IntelliJ IDEA"),
        (("visual studio code", "vs code", "vscode"), "Visual Studio Code"),
        (("eclipse",), "Eclipse"),
        (("netbeans", "net beans"), "Apache NetBeans"),
    )
    selected_ide = next(
        (
            canonical
            for aliases, canonical in ide_aliases
            if any(
                re.search(
                    rf"(?<![a-z]){re.escape(alias)}(?![a-z])",
                    clarification,
                    re.IGNORECASE,
                )
                for alias in aliases
            )
        ),
        None,
    )

    jdk = ProgramPlan(
        order=1,
        program="JDK",
        version=version or ("ยังไม่ได้ระบุ" if language == "th" else "Not specified"),
        purpose=(
            "ชุดพัฒนาและคอมไพเลอร์สำหรับภาษา Java"
            if language == "th"
            else "Java development kit and compiler"
        ),
        reason=(
            "ระบุเวอร์ชันจากคำตอบเพิ่มเติมของผู้ใช้"
            if version and language == "th"
            else "JDK version was explicitly supplied by the user"
            if version
            else "ยังไม่ได้รับเวอร์ชัน JDK จากผู้ใช้"
            if language == "th"
            else "The user has not supplied a JDK version"
        ),
        source="ยังไม่ได้ตรวจสอบ" if language == "th" else "Not checked",
        impact="ยังไม่ได้ตรวจสอบ" if language == "th" else "Unknown / not checked",
        status="PLANNED" if version else "NEEDS_CLARIFICATION",
    )
    programs = [jdk]
    if selected_ide:
        programs.append(
            ProgramPlan(
                order=2,
                program=selected_ide,
                version="ไม่ระบุเวอร์ชัน" if language == "th" else "Not specified",
                purpose="IDE ที่ผู้ใช้เลือก" if language == "th" else "IDE explicitly selected by the user",
                reason=(
                    "ผู้ใช้ระบุ IDE นี้ในคำตอบเพิ่มเติม"
                    if language == "th"
                    else "Explicitly selected in the user's clarification"
                ),
                source="ยังไม่ได้ตรวจสอบ" if language == "th" else "Not checked",
                impact="ยังไม่ได้ตรวจสอบ" if language == "th" else "Unknown / not checked",
                status="PLANNED",
            )
        )
    return tuple(programs)


def _java_refinement_questions(
    programs: tuple[ProgramPlan, ...], language: Literal["th", "en"]
) -> tuple[str, ...]:
    questions: list[str] = []
    jdk = programs[0]
    if jdk.status == "NEEDS_CLARIFICATION":
        questions.append(
            "ต้องการ JDK เวอร์ชันใด เช่น 21 LTS?"
            if language == "th"
            else "Which JDK version do you want, for example 21 LTS?"
        )
    if len(programs) == 1:
        questions.append(
            "ต้องการใช้ IDE ใด เช่น IntelliJ IDEA, Eclipse หรือ VS Code?"
            if language == "th"
            else "Which IDE do you want, such as IntelliJ IDEA, Eclipse, or VS Code?"
        )
    return tuple(questions)


@router.post("/api/plans/{plan_id}/refine", response_model=PlanReviewResponse)
def refine_plan_review(plan_id: str, payload: PlanRefinementRequest) -> PlanReviewResponse:
    """Create a new immutable plan from a valid Java plan and explicit clarification."""
    if len(plan_id) != 32 or any(char not in "0123456789abcdef" for char in plan_id):
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        previous_plan = _plan_store.get(plan_id)
    except PlanExpiredError:
        raise HTTPException(status_code=410, detail="Plan expired.") from None
    except PlanNotFoundError:
        raise HTTPException(status_code=404, detail="Plan not found.") from None

    task_plan = create_task_plan(payload.request, payload.language)
    intent = task_plan.intent
    if intent.category == "development_task" and re.search(r"\bjava\b", payload.request, re.IGNORECASE):
        intent = intent.model_copy(update={"target": "Java"})
        task_plan = task_plan.model_copy(update={"intent": intent})
    baseline = _programs_for_review(intent, payload.language)
    if (
        baseline is None
        or intent.category != "development_task"
        or intent.target != "Java"
        or previous_plan.tool_id != "software.install"
        or previous_plan.programs != baseline[1]
    ):
        raise HTTPException(status_code=409, detail="Plan does not match the supplied original request.")

    programs = _java_refinement_programs(payload.clarification, payload.language)
    try:
        new_plan = _plan_store.create("software.install", programs)
    except PlanCapacityError:
        raise HTTPException(status_code=503, detail="Plan capacity reached.") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="Clarification could not be applied.") from None

    return PlanReviewResponse(
        request=payload.request,
        interpretation=intent,
        task_plan=task_plan,
        dry_run_plan=new_plan,
        tool_result=None,
        approved=False,
        questions=_java_refinement_questions(programs, payload.language),
        refined_from_plan_id=plan_id,
        clarification=payload.clarification,
    )
