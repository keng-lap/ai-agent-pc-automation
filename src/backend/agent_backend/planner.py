"""Deterministic intent analysis and task planning for Phase 3 (T-303).

This module only classifies text and builds a plan. It does not call a model,
search the network, inspect the computer, or execute commands.
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

_INSTALL_PREFIX = re.compile(r"(?:install|set\s+up|setup)\s+(?:the\s+)?", re.IGNORECASE)
_REMOVE_PREFIX = re.compile(
    r"(?:uninstall|remove)\s+(?:the\s+)?", re.IGNORECASE
)
_TH_INSTALL_PREFIX = re.compile(r"(?:ช่วย)?\s*(?:ติดตั้ง|ลง)\s*(?:โปรแกรม)?\s*")
_TH_REMOVE_PREFIX = re.compile(r"(?:ช่วย)?\s*(?:ถอนการติดตั้ง|ถอน|ลบ)\s*(?:โปรแกรม)?\s*")
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


def _steps(language: Language, category: IntentKind, target: str | None) -> tuple[PlanStep, ...]:
    if language == "th":
        target_text = f" ({target})" if target else ""
        details = (
            (
                ("ตรวจเป้าหมาย", f"ยืนยันซอฟต์แวร์ที่ร้องขอ{target_text}"),
                ("ตรวจ prerequisite", "ตรวจว่าเครื่องมือและ dependency ที่จำเป็นมีอยู่แล้วหรือไม่"),
                ("ค้นแหล่งข้อมูล", "ค้นคำแนะนำปัจจุบันจากแหล่งทางการและบันทึกการอ้างอิง"),
                ("แสดงแผนทั้งหมด", "สรุปซอฟต์แวร์ ลำดับงาน คำสั่งที่เสนอ และผลกระทบเพื่อให้ผู้ใช้ตรวจสอบ"),
                ("ขออนุมัติ", "รอผู้ใช้ยืนยันแผนและการเปลี่ยนแปลงแต่ละรายการก่อนทำงานจริง"),
                ("ทดลองแบบจำลอง", "จำลองการทำงานเท่านั้น ยังไม่มีการเปลี่ยนแปลงเครื่องใน Phase 3–4"),
            )
            if category in ("software_install", "software_remove")
            else (
                ("ทำความเข้าใจงาน", "แยกเป้าหมายออกเป็นงานย่อยและตรวจข้อมูลที่จำเป็น"),
                ("ตรวจ prerequisite", "ระบุโปรแกรม เครื่องมือ และ dependency ที่จำเป็น แล้วตรวจว่ามีอยู่แล้วหรือไม่"),
                ("ค้นแหล่งข้อมูล", "ค้นแหล่งข้อมูลปัจจุบันที่น่าเชื่อถือและบันทึกการอ้างอิง"),
                ("แสดงแผนทั้งหมด", "แสดงงานย่อย ลำดับ dependency ซอฟต์แวร์ที่จำเป็น และผลกระทบ"),
                ("ขออนุมัติ", "รอผู้ใช้ตรวจและยืนยันก่อนเริ่มการเปลี่ยนแปลง"),
                ("ทดลองแบบจำลอง", "จำลองการทำงานเท่านั้น ยังไม่มีการเปลี่ยนแปลงเครื่องใน Phase 3–4"),
            )
        )
        kinds: tuple[StepKind, ...] = (
            "clarify_goal",
            "discover_prerequisites",
            "research_sources",
            "present_plan",
            "request_approval",
            "dry_run",
        )
    else:
        target_text = f" ({target})" if target else ""
        details = (
            (
                ("Confirm target", f"Confirm the requested software{target_text}"),
                ("Check prerequisites", "Check whether required tools and dependencies are already available"),
                ("Research sources", "Find current instructions from official sources and record citations"),
                ("Present complete plan", "Show required software, order, proposed commands, and effects for review"),
                ("Request approval", "Wait for explicit approval of the plan and each proposed change"),
                ("Dry run", "Simulate the operation only; no real machine changes in Phases 3–4"),
            )
            if category in ("software_install", "software_remove")
            else (
                ("Understand the task", "Break the goal into tasks and identify missing information"),
                ("Check prerequisites", "Identify required software, tools, and dependencies and check availability"),
                ("Research sources", "Find current, trustworthy information and record citations"),
                ("Present complete plan", "Show subtasks, dependency order, required software, and effects"),
                ("Request approval", "Wait for the user to review and approve before making changes"),
                ("Dry run", "Simulate the operation only; no real machine changes in Phases 3–4"),
            )
        )
        kinds = (
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
    return TaskPlan(
        intent=TaskIntent(category=category, goal=normalized, target=target),
        language=language,
        steps=_steps(language, category, target),
    )
