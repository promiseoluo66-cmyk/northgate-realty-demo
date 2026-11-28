import copy
import math

import pytest

from title_templates import (
    TEMPLATE_SCHEMA_VERSION,
    TitleTemplateValidationError,
    list_title_templates,
    resolve_title_template,
    validate_template_catalogue,
)


def test_builtin_catalogue_has_four_stable_versioned_templates():
    templates = list_title_templates()
    assert len(templates) == 4
    assert {item["name"] for item in templates} == {
        "Clean Centre Title", "Editorial Lower Third",
        "Bold Section Title", "Animated Rise Title",
    }
    assert all(item["schema_version"] == TEMPLATE_SCHEMA_VERSION for item in templates)
    assert len({item["id"] for item in templates}) == 4


def test_template_catalogue_returns_independent_copies():
    first = list_title_templates()
    first[0]["text_defaults"]["size"] = 8
    first[0]["animation_defaults"].append({"bad": True})
    second = list_title_templates()
    assert second[0]["text_defaults"]["size"] == 56
    assert second[0]["animation_defaults"] == []


@pytest.mark.parametrize("mutate", [
    lambda t: t.update(schema_version=99),
    lambda t: t.update(extra="not allowed"),
    lambda t: t.pop("name"),
    lambda t: t.update(id="BAD ID"),
    lambda t: t.update(name=""),
    lambda t: t["text_defaults"].update(size=999),
    lambda t: t["text_defaults"].update(fgcolour="url(javascript:alert(1))"),
    lambda t: t["text_defaults"].update(x_percent=90, width_percent=90),
    lambda t: t["text_defaults"].update(family="x" * 81),
    lambda t: t["animation_defaults"].append({
        "property": "shell", "time_ratio": 0, "value": 1, "interpolation": "linear"
    }),
    lambda t: t["animation_defaults"].append({
        "property": "opacity", "time_ratio": math.nan, "value": 1, "interpolation": "linear"
    }),
    lambda t: t["animation_defaults"].append({
        "property": "opacity", "time_ratio": 0, "value": math.inf, "interpolation": "linear"
    }),
    lambda t: t["animation_defaults"].append({
        "property": "opacity", "time_ratio": 0, "value": 1, "interpolation": "bezier"
    }),
])
def test_catalogue_rejects_unsupported_or_unsafe_fields(mutate):
    template = copy.deepcopy(list_title_templates()[0])
    mutate(template)
    with pytest.raises(TitleTemplateValidationError):
        validate_template_catalogue([template])


def test_catalogue_rejects_duplicate_ids_and_case_insensitive_names():
    templates = list_title_templates()
    duplicate_id = copy.deepcopy(templates)
    duplicate_id[1]["id"] = duplicate_id[0]["id"]
    with pytest.raises(TitleTemplateValidationError, match="IDs"):
        validate_template_catalogue(duplicate_id)
    duplicate_name = copy.deepcopy(templates)
    duplicate_name[1]["name"] = duplicate_name[0]["name"].upper()
    with pytest.raises(TitleTemplateValidationError, match="names"):
        validate_template_catalogue(duplicate_name)


def test_catalogue_rejects_empty_and_oversized_catalogues():
    with pytest.raises(TitleTemplateValidationError):
        validate_template_catalogue([])
    with pytest.raises(TitleTemplateValidationError):
        validate_template_catalogue(list_title_templates() * 6)


def test_resolver_scales_animation_times_to_requested_clip_duration():
    style, frames = resolve_title_template("animated-rise-v1", 2_000_000)
    assert style["size"] == 56
    assert [item["time_us"] for item in frames] == [0, 600_000, 0, 600_000]
    assert all(0 <= item["time_us"] <= 2_000_000 for item in frames)
    assert {item["property"] for item in frames} == {"opacity", "position_y"}


def test_static_template_resolves_without_animation():
    style, frames = resolve_title_template("clean-centre-v1", 1_500_000)
    assert style["halign"] == "center"
    assert frames == []


@pytest.mark.parametrize("template_id,duration", [
    ("missing-template", 1_000_000),
    ("clean-centre-v1", 0),
    ("clean-centre-v1", True),
    ("animated-rise-v1", 1),
])
def test_resolver_rejects_unknown_or_invalid_duration(template_id, duration):
    with pytest.raises(TitleTemplateValidationError):
        resolve_title_template(template_id, duration)
