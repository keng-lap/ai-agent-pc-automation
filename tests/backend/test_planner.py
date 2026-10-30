import pytest

from agent_backend.planner import create_task_plan


def test_install_chrome_has_task_specific_prerequisites():
    plan = create_task_plan("Install Google Chrome", "en")

    assert plan.intent.category == "software_install"
    assert plan.intent.target == "Google Chrome"
    assert [item.id for item in plan.prerequisites] == [
        "software_target",
        "software_version",
        "windows_compatibility",
        "existing_installation",
        "installer_source",
        "admin_permission",
    ]
    assert plan.prerequisites[0].status == "known"
    assert plan.prerequisites[1].status == "user_confirmation_needed"
    assert plan.prerequisites[2].status == "discovery_not_available"
    assert plan.prerequisites[2].reason
    assert plan.prerequisites[2].depends_on == ("software_target",)
    assert [item.order for item in plan.prerequisites] == list(range(1, 7))
    assert plan.approval_required is True
    assert plan.execution_mode == "dry_run"
    assert "unavailable" in plan.steps[2].detail


def test_thai_install_request_has_localized_prerequisites():
    plan = create_task_plan("ช่วยติดตั้ง Chrome ให้หน่อย", "th")

    assert plan.intent.category == "software_install"
    assert plan.intent.target == "Google Chrome"
    assert plan.prerequisites[0].title == "ระบุซอฟต์แวร์เป้าหมาย"
    assert plan.prerequisites[2].status == "discovery_not_available"
    assert "ยังไม่มี" in plan.steps[-1].detail or "ไม่มีคำสั่งจริง" in plan.steps[-1].detail


def test_unknown_install_target_is_preserved_and_not_guessed():
    plan = create_task_plan("Please install ExampleTool for me", "en")

    assert plan.intent.category == "software_install"
    assert plan.intent.target == "ExampleTool"
    assert plan.prerequisites[0].status == "known"


def test_install_without_target_requires_user_clarification():
    plan = create_task_plan("Install", "en")

    assert plan.intent.category == "software_install"
    assert plan.intent.target is None
    assert plan.prerequisites[0].status == "user_confirmation_needed"


def test_removal_plan_requires_scope_and_backup_confirmation():
    plan = create_task_plan("Uninstall Python", "en")

    assert plan.intent.category == "software_remove"
    assert "removal_scope" in [item.id for item in plan.prerequisites]
    assert "user_data_backup" in [item.id for item in plan.prerequisites]
    assert all(
        item.status != "known"
        for item in plan.prerequisites
        if item.id in {"removal_scope", "user_data_backup"}
    )


def test_development_plan_lists_project_and_toolchain_dependencies():
    plan = create_task_plan("Build a website", "en")

    items = {item.id: item for item in plan.prerequisites}
    assert plan.intent.category == "development_task"
    assert items["project_location"].status == "discovery_not_available"
    assert items["runtime_toolchain"].depends_on == ("project_location",)
    assert items["project_dependencies"].depends_on == ("project_location",)
    assert items["acceptance_criteria"].status == "user_confirmation_needed"


def test_general_task_has_safe_clarification_and_unknown_resource_steps():
    plan = create_task_plan("What time is it?", "en")

    assert plan.intent.category == "general_task"
    assert [item.id for item in plan.prerequisites] == [
        "task_goal",
        "task_context",
        "required_resources",
    ]
    assert plan.prerequisites[1].status == "user_confirmation_needed"
    assert plan.prerequisites[2].status == "discovery_not_available"


@pytest.mark.parametrize(
    ("message", "expected", "language"),
    [
        ("Uninstall Python", "software_remove", "en"),
        ("Build a website", "development_task", "en"),
        ("ช่วยพัฒนาเว็บร้านค้า", "development_task", "th"),
        ("What time is it?", "general_task", "en"),
    ],
)
def test_intent_categories(message, expected, language):
    assert create_task_plan(message, language).intent.category == expected


def test_plan_is_deterministic_and_normalizes_whitespace():
    first = create_task_plan("  build   a website ", "en").model_dump_json()
    second = create_task_plan("build a website", "en").model_dump_json()

    assert first == second


@pytest.mark.parametrize("message", ["", "  \\t\\n", "x" * 2001])
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
