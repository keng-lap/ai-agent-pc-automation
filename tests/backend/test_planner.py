import pytest
from agent_backend.planner import create_task_plan


def test_install_chrome_is_classified_and_plans_all_prerequisites():
    plan = create_task_plan("Install Google Chrome", "en")

    assert plan.intent.category == "software_install"
    assert plan.intent.target == "Google Chrome"
    assert [step.order for step in plan.steps] == [1, 2, 3, 4, 5, 6]
    assert [step.kind for step in plan.steps] == [
        "clarify_goal",
        "discover_prerequisites",
        "research_sources",
        "present_plan",
        "request_approval",
        "dry_run",
    ]
    assert plan.approval_required is True
    assert plan.execution_mode == "dry_run"
    assert "official sources" in plan.steps[2].detail


def test_thai_install_request_finds_known_target_and_localized_plan():
    plan = create_task_plan("ช่วยติดตั้ง Chrome ให้หน่อย", "th")

    assert plan.intent.category == "software_install"
    assert plan.intent.target == "Google Chrome"
    assert "Google Chrome" in plan.steps[0].detail
    assert "Phase 3–4" in plan.steps[-1].detail


def test_unknown_install_target_is_preserved_without_guessing():
    plan = create_task_plan("Please install ExampleTool for me", "en")

    assert plan.intent.category == "software_install"
    assert plan.intent.target == "ExampleTool"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Uninstall Python", "software_remove"),
        ("Build a website", "development_task"),
        ("ช่วยพัฒนาเว็บร้านค้า", "development_task"),
        ("What time is it?", "general_task"),
    ],
)
def test_intent_categories(message, expected):
    assert create_task_plan(message, "en" if message.isascii() else "th").intent.category == expected


def test_plan_is_deterministic_and_normalizes_whitespace():
    first = create_task_plan("  build   a website ", "en").model_dump_json()
    second = create_task_plan("build a website", "en").model_dump_json()

    assert first == second


@pytest.mark.parametrize("message", ["", "  \t\n", "x" * 2001])
def test_invalid_message_is_rejected(message):
    with pytest.raises(ValueError):
        create_task_plan(message, "en")


def test_invalid_language_is_rejected():
    with pytest.raises(ValueError):
        create_task_plan("hello", "fr")  # type: ignore[arg-type]


@pytest.mark.parametrize("message", [None, 42, ["hello"]])
def test_non_text_message_is_rejected(message):
    with pytest.raises(TypeError):
        create_task_plan(message, "en")
