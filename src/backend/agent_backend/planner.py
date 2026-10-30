"""Deterministic intent analysis and task planning for Phase 3 (T-308).

This module classifies user text and creates structured, non-executable plans.
It does not call a model, search the network, inspect the computer, or execute
commands. Unknown machine facts are explicitly marked as unavailable.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["th", "en"]
IntentKind = Literal[
    "software_install",
    "software_remove",
    "development_task",
    "general_task",
]
StepKind = Literal[
    "clarify_goal",
    "discover_prerequisites",
    "research_sources",
    "present_plan",
    "request_approval",
    "dry_run",
]
PrerequisiteStatus = Literal[
    "known",
    "user_confirmation_needed",
    "discovery_not_available",
]

_KNOWN_SOFTWARE = {
    "google chrome": "Google Chrome",
    "chrome": "Google Chrome",
    "visual studio code": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "python": "Python",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "git": "Git",
}

_INSTALL_PREFIX = re.compile(r"(?:install|set\\s+up|setup)\\s+(?:the\\s+)?", re.IGNORECASE)
_REMOVE_PREFIX = re.compile(
    r"(?:uninstall|remove)\\s+(?:the\\s+)?", re.IGNORECASE
)
_TH_INSTALL_PREFIX = re.compile(r"(?:ช่วย)?\\s*(?:ติดตั้ง|ลง)\\s*(?:โปรแกรม)?\\s*")
_TH_REMOVE_PREFIX = re.compile(r"(?:ช่วย)?\\s*(?:ถอนการติดตั้ง|ถอน|ลบ)\\s*(?:โปรแกรม)?\\s*")
_DEVELOPMENT_TERMS = (
    "build",
    "create",
    "develop",
    "make a website",
    "make an app",
    "สร้าง",
    "พัฒนา",
    "ทำเว็บ",
    "ทำแอป",
)


class TaskIntent(BaseModel):
    """A bounded interpretation of a user's task; it grants no permission."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    category: IntentKind
    goal: str = Field(min_length=1, max_length=2000)
    target: str | None = Field(default=None, min_length=1, max_length=120)


class Prerequisite(BaseModel):
    """A task-specific prerequisite; never an executable instruction."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,47}$")
    order: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=300)
    status: PrerequisiteStatus
    depends_on: tuple[str, ...] = ()


class PlanStep(BaseModel):
    """A human-readable planning step, not an executable instruction."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    order: int = Field(ge=1)
    kind: StepKind
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=500)


class TaskPlan(BaseModel):
    """A deterministic plan that must be reviewed before any side effects."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    intent: TaskIntent
    language: Language
    prerequisites: tuple[Prerequisite, ...] = Field(min_length=1, max_length=12)
    steps: tuple[PlanStep, ...] = Field(min_length=1, max_length=8)
    approval_required: Literal[True] = True
    execution_mode: Literal["dry_run"] = "dry_run"


def _is_word_boundary(text: str, index: int) -> bool:
    """Return True when the given position is a word boundary."""
    if index < 0 or index >= len(text):
        return True
    char = text[index]
    return not (char.isalnum() or char == "_")


def _contains_alias(text: str, alias: str) -> bool:
    """Check for a known software alias without building a dynamic regex."""
    if alias not in text:
        return False
    start = 0
    while True:
        index = text.find(alias, start)
        if index == -1:
            return False
        before_ok = index == 0 or _is_word_boundary(text, index - 1)
        after_ok = index + len(alias) == len(text) or _is_word_boundary(text, index + len(alias))
        if before_ok and after_ok:
            return True
        start = index + 1


def _canonical_software(message: str) -> str | None:
    lowered = message.casefold()
    for alias, canonical in sorted(_KNOWN_SOFTWARE.items(), key=lambda pair: -len(pair[0])):
        if _contains_alias(lowered, alias):
            return canonical
    return None


def _trim_trailing_punctuation(value: str) -> str:
    """Remove trailing sentence punctuation without regex."""
    trimmed = value.rstrip()
    while trimmed and trimmed[-1] in ".!?。！？":
        trimmed = trimmed[:-1].rstrip()
    return trimmed


def _trim_known_suffix(value: str) -> str:
    """Remove known English/Thai request suffixes without regex."""
    trimmed = value.rstrip()
    suffixes = ["please", "for me", "ให้หน่อย", "ที", "ด้วย"]
    lowered = trimmed.casefold()
    for suffix in suffixes:
        if lowered.endswith(suffix.casefold()):
            trimmed = trimmed[: -len(suffix)].rstrip()
            break
    return trimmed


def _strip_leading_label(value: str) -> str:
    """Remove safe leading labels like 'the program' or 'โปรแกรม'."""
    lowered = value.casefold()
    for prefix in ("the program ", "the app ", "โปรแกรม "):
        if lowered.startswith(prefix):
            return value[len(prefix) :].lstrip()
    return value


def _target_after_prefix(message: str, category: IntentKind) -> str | None:
    prefix_patterns = (
        (_INSTALL_PREFIX, _TH_INSTALL_PREFIX)
        if category == "software_install"
        else (_REMOVE_PREFIX, _TH_REMOVE_PREFIX)
    )
    remainder = message
    for pattern in prefix_patterns:
        match = pattern.search(message)
        if match:
            remainder = message[match.end() :]
            break
    remainder = _trim_trailing_punctuation(remainder)
    remainder = _trim_known_suffix(remainder)
    remainder = _strip_leading_label(remainder)
    if not remainder:
        return None
    return remainder[:120]


def _classify(message: str) -> tuple[IntentKind, str | None]:
    lowered = message.casefold()
    if any(term in lowered for term in ("uninstall", "remove", "ถอนการติดตั้ง", "ถอนโปรแกรม")):
        category: IntentKind = "software_remove"
    elif any(term in lowered for term in ("install", "set up", "setup", "ติดตั้ง", "ลงโปรแกรม")):
        category = "software_install"
    elif any(term in lowered for term in _DEVELOPMENT_TERMS):
        return "development_task", None
    else:
        return "general_task", None
    return category, _canonical_software(message) or _target_after_prefix(message, category)


def _prerequisites(
    language: Language, category: IntentKind, target: str | None
) -> tuple[Prerequisite, ...]:
    """Return relevant prerequisites with reasons, order, and honest knowledge state."""
    if language == "th":
        if category == "software_install":
            rows = [
                ("software_target", "ระบุซอฟต์แวร์เป้าหมาย", "ทราบจากคำขอของผู้ใช้" if target else "ยังไม่ทราบชื่อซอฟต์แวร์ที่ต้องการ ต้องถามให้ชัดเจน", "known" if target else "user_confirmation_needed", ()),
                ("software_version", "ยืนยันรุ่นที่ต้องการ", "รุ่นอาจมีผลต่อความเข้ากันได้และวิธีติดตั้ง", "user_confirmation_needed", ("software_target",)),
                ("windows_compatibility", "ตรวจสอบความเข้ากันได้กับ Windows", "ต้องทราบรุ่น Windows และข้อกำหนดของซอฟต์แวร์ก่อนเลือกวิธีติดตั้ง", "discovery_not_available", ("software_target",)),
                ("existing_installation", "ตรวจสอบว่าติดตั้งอยู่แล้วหรือไม่", "ป้องกันการติดตั้งซ้ำหรือทับการตั้งค่าเดิม", "discovery_not_available", ("software_target",)),
                ("installer_source", "ยืนยันแหล่งติดตั้งทางการ", "ลดความเสี่ยงจากไฟล์ติดตั้งที่ไม่ถูกต้องหรือไม่ปลอดภัย", "discovery_not_available", ("software_target",)),
                ("admin_permission", "ตรวจสอบสิทธิ์ผู้ดูแลระบบ", "บางโปรแกรมต้องใช้สิทธิ์เพิ่มเติมในการติดตั้ง", "discovery_not_available", ("software_target",)),
            ]
        elif category == "software_remove":
            rows = [
                ("software_target", "ระบุซอฟต์แวร์เป้าหมาย", "ทราบจากคำขอของผู้ใช้" if target else "ยังไม่ทราบชื่อซอฟต์แวร์ ต้องถามก่อนวางแผนถอน", "known" if target else "user_confirmation_needed", ()),
                ("removal_scope", "ยืนยันขอบเขตการถอน", "ต้องแยกโปรแกรมหลัก ส่วนเสริม และข้อมูลผู้ใช้เพื่อป้องกันการลบเกินต้องการ", "user_confirmation_needed", ("software_target",)),
                ("existing_installation", "ตรวจสอบสถานะการติดตั้ง", "ต้องทราบว่ามีโปรแกรมและส่วนประกอบใดอยู่จริง", "discovery_not_available", ("software_target",)),
                ("user_data_backup", "ยืนยันการสำรองข้อมูล", "การถอนบางโปรแกรมอาจกระทบข้อมูลหรือการตั้งค่าของผู้ใช้", "user_confirmation_needed", ("software_target",)),
                ("uninstaller_method", "ตรวจสอบวิธีถอนอย่างเป็นทางการ", "ใช้วิธีที่ผู้พัฒนารองรับและลดผลกระทบต่อระบบ", "discovery_not_available", ("existing_installation",)),
            ]
        elif category == "development_task":
            rows = [
                ("task_goal", "ระบุเป้าหมายงาน", "ทราบจากคำขอ แต่รายละเอียดผลลัพธ์ยังอาจไม่ครบ", "known", ()),
                ("task_scope", "ยืนยันขอบเขตและผลลัพธ์", "ช่วยกำหนดงานย่อยและป้องกันการทำเกินความต้องการ", "user_confirmation_needed", ("task_goal",)),
                ("project_location", "ตรวจสอบโฟลเดอร์หรือ repository", "จำเป็นเพื่อรู้โครงสร้างและไฟล์ที่มีอยู่ก่อนวางแผนแก้ไข", "discovery_not_available", ("task_goal",)),
                ("runtime_toolchain", "ตรวจสอบภาษาและเครื่องมือ", "เวอร์ชัน runtime และเครื่องมือมีผลต่อวิธี build และ test", "discovery_not_available", ("project_location",)),
                ("project_dependencies", "ตรวจสอบ dependencies", "ต้องทราบแพ็กเกจที่มีและข้อกำหนดก่อนเลือกขั้นตอนติดตั้งหรือ build", "discovery_not_available", ("project_location",)),
                ("acceptance_criteria", "กำหนดเกณฑ์ตรวจรับ", "ทำให้ตรวจได้ว่างานเสร็จตามเป้าหมายหรือไม่", "user_confirmation_needed", ("task_scope",)),
            ]
        else:
            rows = [
                ("task_goal", "ระบุเป้าหมายงาน", "ทราบจากข้อความ แต่ยังไม่ทราบผลลัพธ์ที่คาดหวังทั้งหมด", "known", ()),
                ("task_context", "ขอข้อมูลบริบทเพิ่มเติม", "ข้อมูลบริบทเป็นตัวกำหนดวิธีดำเนินงานและข้อจำกัด", "user_confirmation_needed", ("task_goal",)),
                ("required_resources", "ระบุทรัพยากรและ dependencies", "ต้องทราบเครื่องมือ ข้อมูล หรือบริการที่จำเป็นก่อนกำหนดขั้นตอน", "discovery_not_available", ("task_goal",)),
            ]
    else:
        if category == "software_install":
            rows = [
                ("software_target", "Identify software target", "Taken from the user's request" if target else "The requested software name is missing and must be clarified", "known" if target else "user_confirmation_needed", ()),
                ("software_version", "Confirm requested version", "Version can affect compatibility and installation steps", "user_confirmation_needed", ("software_target",)),
                ("windows_compatibility", "Check Windows compatibility", "Windows version and software requirements are needed before choosing an installer", "discovery_not_available", ("software_target",)),
                ("existing_installation", "Check existing installation", "Avoid duplicate installation or overwriting existing configuration", "discovery_not_available", ("software_target",)),
                ("installer_source", "Verify official installer source", "Reduce the risk of incorrect or unsafe installation files", "discovery_not_available", ("software_target",)),
                ("admin_permission", "Check administrator permission", "Some software requires elevated permission to install", "discovery_not_available", ("software_target",)),
            ]
        elif category == "software_remove":
            rows = [
                ("software_target", "Identify software target", "Taken from the user's request" if target else "The software name is missing and must be clarified", "known" if target else "user_confirmation_needed", ()),
                ("removal_scope", "Confirm removal scope", "Separate the application, add-ons, and user data to avoid removing more than intended", "user_confirmation_needed", ("software_target",)),
                ("existing_installation", "Check installation state", "Determine which application components are actually present", "discovery_not_available", ("software_target",)),
                ("user_data_backup", "Confirm user-data backup", "Uninstalling some applications may affect user data or settings", "user_confirmation_needed", ("software_target",)),
                ("uninstaller_method", "Verify supported uninstall method", "Use a vendor-supported method and reduce system impact", "discovery_not_available", ("existing_installation",)),
            ]
        elif category == "development_task":
            rows = [
                ("task_goal", "Identify task goal", "Taken from the request, but expected output may need more detail", "known", ()),
                ("task_scope", "Confirm scope and deliverables", "Define subtasks and prevent work beyond the requested outcome", "user_confirmation_needed", ("task_goal",)),
                ("project_location", "Inspect project folder or repository", "Existing structure and files are needed before planning changes", "discovery_not_available", ("task_goal",)),
                ("runtime_toolchain", "Identify language and toolchain", "Runtime and tool versions affect build and test steps", "discovery_not_available", ("project_location",)),
                ("project_dependencies", "Inspect project dependencies", "Existing packages and constraints affect install and build steps", "discovery_not_available", ("project_location",)),
                ("acceptance_criteria", "Define acceptance criteria", "Make it possible to verify that the result meets the goal", "user_confirmation_needed", ("task_scope",)),
            ]
        else:
            rows = [
                ("task_goal", "Identify task goal", "Taken from the message, but the expected outcome is not fully known", "known", ()),
                ("task_context", "Ask for task context", "Context determines the appropriate approach and constraints", "user_confirmation_needed", ("task_goal",)),
                ("required_resources", "Identify resources and dependencies", "Required tools, data, or services must be known before planning execution", "discovery_not_available", ("task_goal",)),
            ]

    return tuple(
        Prerequisite(
            id=item_id,
            order=index,
            title=title,
            reason=reason,
            status=status,
            depends_on=dependencies,
        )
        for index, (item_id, title, reason, status, dependencies) in enumerate(rows, 1)
    )


def _steps(
    language: Language, category: IntentKind, prerequisites: tuple[Prerequisite, ...]
) -> tuple[PlanStep, ...]:
    unavailable_count = sum(item.status == "discovery_not_available" for item in prerequisites)
    confirmation_count = sum(item.status == "user_confirmation_needed" for item in prerequisites)
    if language == "th":
        details = (
            ("ทำความเข้าใจเป้าหมาย", "ใช้ประเภทงานและข้อมูลเป้าหมายจากคำขอ โดยไม่อนุมานข้อมูลที่ไม่มี"),
            ("ตรวจ prerequisite", f"แสดง prerequisite เฉพาะงาน {category} จำนวน {len(prerequisites)} รายการ; ยังต้องค้นข้อมูลอีก {unavailable_count} รายการ และขอคำยืนยัน {confirmation_count} รายการ"),
            ("ระบุข้อจำกัดการค้นข้อมูล", "ขณะนี้ไม่มีความสามารถอ่านข้อมูลในเครื่องหรือค้นเว็บ จึงทำเครื่องหมายข้อมูลที่ยังตรวจไม่ได้อย่างชัดเจน"),
            ("แสดงแผนทั้งหมด", "แสดงเหตุผล ลำดับ dependency และสถานะของ prerequisite แต่ละรายการให้ผู้ใช้ตรวจสอบ"),
            ("ขออนุมัติ", "รอผู้ใช้ยืนยันข้อมูลที่จำเป็นและอนุมัติแผนก่อนดำเนินการใด ๆ"),
            ("ทดลองแบบจำลอง", "จำลองการทำงานเท่านั้น ไม่มีคำสั่งจริงหรือการเปลี่ยนแปลงเครื่องใน Phase 3–4"),
        )
    else:
        details = (
            ("Understand the goal", "Use the task category and target from the request without inventing missing facts"),
            ("Check prerequisites", f"List {len(prerequisites)} task-specific prerequisites for {category}; {unavailable_count} need discovery and {confirmation_count} need user confirmation"),
            ("State discovery limits", "Local inspection and web research are unavailable; unverified facts remain explicitly marked"),
            ("Present complete plan", "Show each prerequisite's reason, dependency order, and knowledge status for review"),
            ("Request approval", "Wait for required user clarification and explicit plan approval before any action"),
            ("Dry run", "Simulation only; no real commands or machine changes in Phases 3–4"),
        )
    kinds: tuple[StepKind, ...] = (
        "clarify_goal",
        "discover_prerequisites",
        "research_sources",
        "present_plan",
        "request_approval",
        "dry_run",
    )
    return tuple(
        PlanStep(order=index, kind=kind, title=title, detail=detail)
        for index, (kind, (title, detail)) in enumerate(zip(kinds, details, strict=True), 1)
    )


def create_task_plan(message: str, language: Language) -> TaskPlan:
    """Analyze a request and build a deterministic, non-executable task plan."""
    if not isinstance(message, str):
        raise TypeError("message must be text")
    normalized = " ".join(message.split())
    if not normalized or len(normalized) > 2000:
        raise ValueError("message length must be between 1 and 2000")
    if language not in ("th", "en"):
        raise ValueError("language must be 'th' or 'en'")

    category, target = _classify(normalized)
    intent = TaskIntent(category=category, goal=normalized, target=target)
    prerequisites = _prerequisites(language, category, target)
    return TaskPlan(
        intent=intent,
        language=language,
        prerequisites=prerequisites,
        steps=_steps(language, category, prerequisites),
    )
