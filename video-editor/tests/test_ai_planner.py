from ai_planner import plan_edit


def test_preferred_ai_plan_is_accepted_after_validation():
    plan = plan_edit(
        "make it a short",
        {"aspect": "9:16", "width": 720, "height": 1280, "speed": 1.0},
        {"trim_start": 1, "trim_end": 7, "speed": 1.5, "aspect": "1:1", "width": 720, "height": 720},
    )
    assert plan.trim_start == 1
    assert plan.trim_end == 7
    assert plan.speed == 1.5
    assert plan.aspect == "1:1"


def test_invalid_preferred_plan_falls_back_safely(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    plan = plan_edit(
        "Make a vertical short at 1.5x speed",
        {"aspect": "9:16", "width": 720, "height": 1280, "speed": 1.0},
        {"speed": 99, "aspect": "invalid"},
    )
    assert plan.speed == 1.5
    assert plan.aspect == "9:16"
