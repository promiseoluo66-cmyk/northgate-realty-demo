import pytest
from engine import plan_from_instruction, validate_plan, EditPlan


def test_vertical_instruction():
    plan = plan_from_instruction("Make a vertical YouTube Short")
    assert plan.aspect == "9:16"
    assert (plan.width, plan.height) == (720, 1280)


def test_trim_and_speed():
    plan = plan_from_instruction("From 3 seconds to 18 seconds, use 1.5x speed")
    assert plan.trim_start == 3
    assert plan.trim_end == 18
    assert plan.speed == 1.5


def test_square_format():
    assert plan_from_instruction("Make it square 1:1").aspect == "1:1"


def test_reject_unsafe_speed():
    with pytest.raises(ValueError):
        validate_plan(EditPlan(speed=9))
