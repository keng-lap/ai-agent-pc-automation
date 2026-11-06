from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from agent_backend.plans import (
    MAX_ACTIVE_PLANS,
    PLAN_TTL,
    DryRunPlan,
    PlanCapacityError,
    PlanExpiredError,
    PlanNotFoundError,
    PlanStore,
    ProgramPlan,
    create_dry_run_plan,
)


NOW = datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)


def program(**changes):
    values = {
        "order": 1,
        "program": "Google Chrome",
        "version": "Not specified",
        "purpose": "Web browser",
        "reason": "Requested by the user",
        "source": "Not checked",
        "dependencies": (),
        "disk_space_estimate": None,
        "impact": "Unknown / not checked",
        "status": "NEEDS_CLARIFICATION",
    }
    values.update(changes)
    return ProgramPlan(**values)


def test_plan_is_immutable_and_explicitly_dry_run_only():
    plan = create_dry_run_plan("software.install", [program()], now=NOW)

    assert plan.mode == "dry_run"
    assert plan.risk_class == "R1"
    assert plan.required_permission == "P1"
    assert plan.expires_at - plan.created_at == PLAN_TTL
    assert plan.programs[0].program == "Google Chrome"
    with pytest.raises(ValidationError):
        plan.mode = "execute"


def test_equivalent_plan_content_has_same_digest_but_distinct_opaque_ids():
    first = create_dry_run_plan("software.install", [program()], now=NOW)
    second = create_dry_run_plan("software.install", [program()], now=NOW)

    assert first.plan_digest == second.plan_digest
    assert first.plan_id != second.plan_id


@pytest.mark.parametrize(
    "change",
    [
        {"program": "Firefox"},
        {"version": "Stable"},
        {"purpose": "Different purpose"},
        {"reason": "Different reason"},
        {"source": "Vendor website (not checked)"},
        {"dependencies": ("JRE",)},
        {"disk_space_estimate": "500 MB (estimate)"},
        {"impact": "May require restart"},
        {"status": "PLANNED"},
    ],
)
def test_every_material_program_field_changes_digest(change):
    original = program()
    changed = original.model_copy(update=change)

    first = create_dry_run_plan("software.install", [original], now=NOW)
    second = create_dry_run_plan("software.install", [changed], now=NOW)

    assert first.plan_digest != second.plan_digest


def test_tool_identity_changes_digest():
    install = create_dry_run_plan("software.install", [program()], now=NOW)
    remove = create_dry_run_plan("software.remove", [program()], now=NOW)

    assert install.plan_digest != remove.plan_digest


def test_plan_order_is_bound_to_digest_and_must_be_contiguous():
    first_item = program(order=1, program="Git")
    second_item = program(order=2, program="JDK")
    original = create_dry_run_plan(
        "software.install", [first_item, second_item], now=NOW
    )
    reordered = create_dry_run_plan(
        "software.install",
        [program(order=1, program="JDK"), program(order=2, program="Git")],
        now=NOW,
    )

    assert original.plan_digest != reordered.plan_digest
    with pytest.raises(ValidationError):
        create_dry_run_plan(
            "software.install",
            [program(order=2), program(order=3, program="JDK")],
            now=NOW,
        )


def test_unknown_fields_and_non_contract_statuses_are_rejected():
    with pytest.raises(ValidationError):
        ProgramPlan.model_validate({**program().model_dump(), "command": "whoami"})
    with pytest.raises(ValidationError):
        program(status="INSTALLED")
    with pytest.raises(ValidationError):
        DryRunPlan.model_validate(
            {
                **create_dry_run_plan("software.install", [program()], now=NOW).model_dump(),
                "prompt": "Install Chrome",
            }
        )


def test_duplicate_program_names_and_empty_plan_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        create_dry_run_plan(
            "software.install",
            [program(order=1), program(order=2, program="google chrome")],
            now=NOW,
        )
    with pytest.raises(ValueError, match="between 1 and 50"):
        create_dry_run_plan("software.install", [], now=NOW)


def test_plan_rejects_naive_or_non_utc_creation_time():
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        create_dry_run_plan(
            "software.install", [program()], now=datetime(2026, 11, 7, 0, 0)
        )


def test_store_returns_plan_until_expiry_then_rejects_it():
    clock_value = [NOW]
    store = PlanStore(clock=lambda: clock_value[0])
    plan = store.create("software.install", [program()])

    assert store.get(plan.plan_id) == plan
    clock_value[0] = NOW + PLAN_TTL

    with pytest.raises(PlanExpiredError):
        store.get(plan.plan_id)
    with pytest.raises(PlanNotFoundError):
        store.get(plan.plan_id)


def test_new_store_cannot_recover_a_plan_from_a_previous_process():
    first_process_store = PlanStore(clock=lambda: NOW)
    plan = first_process_store.create("software.install", [program()])

    restarted_process_store = PlanStore(clock=lambda: NOW)
    with pytest.raises(PlanNotFoundError):
        restarted_process_store.get(plan.plan_id)


def test_store_rejects_tampered_plan_and_removes_reference():
    store = PlanStore(clock=lambda: NOW)
    plan = store.create("software.install", [program()])
    store._plans[plan.plan_id] = plan.model_copy(update={"plan_digest": "0" * 64})

    from agent_backend.plans import PlanIntegrityError

    with pytest.raises(PlanIntegrityError):
        store.get(plan.plan_id)
    with pytest.raises(PlanNotFoundError):
        store.get(plan.plan_id)


def test_store_is_bounded_and_does_not_evict_live_plans_silently():
    store = PlanStore(clock=lambda: NOW)
    plans = [
        store.create("software.install", [program()])
        for _ in range(MAX_ACTIVE_PLANS)
    ]

    with pytest.raises(PlanCapacityError):
        store.create("software.install", [program()])

    assert store.get(plans[0].plan_id) == plans[0]


def test_expired_plans_are_pruned_before_capacity_is_checked():
    clock_value = [NOW]
    store = PlanStore(clock=lambda: clock_value[0])
    plan = store.create("software.install", [program()])
    clock_value[0] = NOW + timedelta(minutes=10)

    replacement = store.create("software.install", [program()])

    assert replacement.plan_id != plan.plan_id
    assert store.get(replacement.plan_id) == replacement
