import copy

import pytest

from project_model import ProjectValidationError, validate_project


def sample_project():
    return {
        "schema_version": 1,
        "id": "project-demo",
        "name": "Demo edit",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 1920,
            "height": 1080,
            "frame_rate": {"numerator": 30, "denominator": 1},
        },
        "assets": [
            {
                "id": "asset-video",
                "media_type": "video",
                "file_name": "source.mp4",
                "storage_key": "private/projects/project-demo/source.mp4",
                "size_bytes": 1024,
                "duration_us": 10_000_000,
            },
            {
                "id": "asset-audio",
                "media_type": "audio",
                "file_name": "music.mp3",
                "storage_key": "private/projects/project-demo/music.mp3",
                "size_bytes": 512,
                "duration_us": 20_000_000,
            },
        ],
        "tracks": [
            {
                "id": "track-video",
                "type": "video",
                "name": "Main video",
                "order": 0,
                "clips": [
                    {
                        "id": "clip-main",
                        "kind": "video",
                        "media_id": "asset-video",
                        "start_us": 0,
                        "duration_us": 5_000_000,
                        "source_in_us": 0,
                        "source_out_us": 5_000_000,
                        "playback_rate": 1,
                        "transform": {
                            "position": {"x": 0, "y": 0},
                            "scale": {"x": 1, "y": 1},
                            "rotation_deg": 0,
                            "opacity": 1,
                        },
                        "keyframes": [
                            {
                                "property": "scale_x",
                                "time_us": 0,
                                "value": 1,
                                "interpolation": "ease_in_out",
                            },
                            {
                                "property": "scale_x",
                                "time_us": 2_000_000,
                                "value": 1.4,
                            },
                        ],
                        "effects": [],
                    }
                ],
            },
            {
                "id": "track-overlay",
                "type": "overlay",
                "name": "B-roll",
                "order": 1,
                "clips": [
                    {
                        "id": "clip-broll",
                        "kind": "video",
                        "media_id": "asset-video",
                        "start_us": 5_000_000,
                        "duration_us": 2_000_000,
                        "source_in_us": 5_000_000,
                        "source_out_us": 7_000_000,
                        "playback_rate": 1,
                        "keyframes": [],
                        "effects": [],
                    }
                ],
            },
            {
                "id": "track-text",
                "type": "text",
                "name": "Captions",
                "order": 2,
                "clips": [
                    {
                        "id": "clip-title",
                        "kind": "text",
                        "start_us": 500_000,
                        "duration_us": 2_000_000,
                        "text": {"content": "Hello world"},
                        "keyframes": [],
                        "effects": [],
                    }
                ],
            },
            {
                "id": "track-audio",
                "type": "audio",
                "name": "Music",
                "order": 3,
                "clips": [
                    {
                        "id": "clip-music",
                        "kind": "audio",
                        "media_id": "asset-audio",
                        "start_us": 0,
                        "duration_us": 5_000_000,
                        "source_in_us": 0,
                        "source_out_us": 5_000_000,
                        "playback_rate": 1,
                        "keyframes": [],
                        "effects": [],
                    }
                ],
            },
        ],
        "transitions": [
            {
                "id": "transition-1",
                "type": "dissolve",
                "from_clip_id": "clip-main",
                "to_clip_id": "clip-broll",
                "duration_us": 250_000,
                "parameters": {},
            }
        ],
    }


def test_valid_multitrack_project_is_accepted_without_mutating_input():
    project = sample_project()
    original = copy.deepcopy(project)

    validated = validate_project(project)

    assert validated == original
    assert validated is not project
    assert len(validated["tracks"]) == 4


def test_rejects_unknown_project_schema_version():
    project = sample_project()
    project["schema_version"] = 2

    with pytest.raises(ProjectValidationError, match="schema_version"):
        validate_project(project)


def test_rejects_clip_that_references_missing_media():
    project = sample_project()
    project["tracks"][0]["clips"][0]["media_id"] = "missing-asset"

    with pytest.raises(ProjectValidationError, match="does not exist"):
        validate_project(project)


def test_rejects_duplicate_clip_ids_across_tracks():
    project = sample_project()
    project["tracks"][1]["clips"][0]["id"] = "clip-main"

    with pytest.raises(ProjectValidationError, match="duplicated"):
        validate_project(project)


def test_rejects_wrong_track_and_clip_kind():
    project = sample_project()
    project["tracks"][0]["clips"][0]["kind"] = "audio"

    with pytest.raises(ProjectValidationError, match="cannot be placed"):
        validate_project(project)


def test_rejects_keyframes_outside_clip_duration():
    project = sample_project()
    project["tracks"][0]["clips"][0]["keyframes"][0]["time_us"] = 9_000_000

    with pytest.raises(ProjectValidationError, match="outside the clip"):
        validate_project(project)


def test_rejects_duplicate_keyframes_for_same_property_and_time():
    project = sample_project()
    project["tracks"][0]["clips"][0]["keyframes"].append({
        "property": "scale_x",
        "time_us": 0,
        "value": 1.2,
    })

    with pytest.raises(ProjectValidationError, match="duplicates a keyframe"):
        validate_project(project)


def test_rejects_source_range_beyond_known_media_duration():
    project = sample_project()
    project["tracks"][0]["clips"][0]["source_out_us"] = 11_000_000

    with pytest.raises(ProjectValidationError, match="exceeds the source duration"):
        validate_project(project)


def test_rejects_public_url_used_as_internal_storage_key():
    project = sample_project()
    project["assets"][0]["storage_key"] = "https://example.com/video.mp4"

    # Storage keys are opaque internal references; the project format does not
    # permit a URL to be used as a media-storage identifier.
    with pytest.raises(ProjectValidationError, match="storage_key"):
        # This is checked by the explicit URL guard added below.
        validate_project(project)


def test_rejects_transition_to_a_missing_clip():
    project = sample_project()
    project["transitions"][0]["to_clip_id"] = "unknown-clip"

    with pytest.raises(ProjectValidationError, match="two different existing clips"):
        validate_project(project)


def test_media_folder_and_tags_are_validated_and_preserved():
    project = sample_project()
    project["assets"][0]["folder"] = "B-roll"
    project["assets"][0]["tags"] = ["wildlife", "forest"]
    validated = validate_project(project)
    assert validated["assets"][0]["folder"] == "B-roll"
    assert validated["assets"][0]["tags"] == ["wildlife", "forest"]


def test_media_folder_rejects_path_traversal_and_nested_paths():
    import pytest

    for folder in ("../private", "folder/subfolder", r"folder\\subfolder"):
        project = sample_project()
        project["assets"][0]["folder"] = folder
        with pytest.raises(ProjectValidationError, match="simple folder name"):
            validate_project(project)


def test_media_tags_reject_duplicate_and_oversized_lists():
    import pytest

    project = sample_project()
    project["assets"][0]["tags"] = ["Nature", "nature"]
    with pytest.raises(ProjectValidationError, match="duplicate tags"):
        validate_project(project)
    project = sample_project()
    project["assets"][0]["tags"] = ["tag-" + str(index) for index in range(13)]
    with pytest.raises(ProjectValidationError, match="at most 12"):
        validate_project(project)


def test_manual_crop_is_validated_and_preserved():
    project = sample_project()
    project["tracks"][0]["clips"][0]["crop"] = {
        "x": 0.25, "y": 0.1, "width": 0.5, "height": 0.8,
    }
    validated = validate_project(project)
    assert validated["tracks"][0]["clips"][0]["crop"] == {
        "x": 0.25, "y": 0.1, "width": 0.5, "height": 0.8,
    }


def test_manual_crop_rejects_rectangles_outside_source_frame():
    project = sample_project()
    project["tracks"][0]["clips"][0]["crop"] = {
        "x": 0.6, "y": 0.1, "width": 0.5, "height": 0.8,
    }
    with pytest.raises(ProjectValidationError, match="x plus width"):
        validate_project(project)
    project = sample_project()
    project["tracks"][0]["clips"][0]["crop"] = {
        "x": 0.1, "y": 0.4, "width": 0.5, "height": 0.7,
    }
    with pytest.raises(ProjectValidationError, match="y plus height"):
        validate_project(project)


def test_manual_crop_rejects_automatic_framing_combination():
    project = sample_project()
    clip = project["tracks"][0]["clips"][0]
    clip["framing"] = {"mode": "fill"}
    clip["crop"] = {"x": 0, "y": 0, "width": 0.5, "height": 0.5}
    with pytest.raises(ProjectValidationError, match="cannot be combined"):
        validate_project(project)


def test_transform_flip_flags_are_boolean_and_preserved():
    project = sample_project()
    project["tracks"][0]["clips"][0]["transform"] = {
        "position": {"x": 0, "y": 0},
        "scale": {"x": 1, "y": 1},
        "rotation_deg": 0,
        "opacity": 1,
        "flip_horizontal": True,
        "flip_vertical": False,
    }
    validated = validate_project(project)
    transform = validated["tracks"][0]["clips"][0]["transform"]
    assert transform["flip_horizontal"] is True
    assert transform["flip_vertical"] is False


def test_transform_flip_flags_reject_non_boolean_values():
    project = sample_project()
    project["tracks"][0]["clips"][0]["transform"] = {
        "position": {"x": 0, "y": 0},
        "scale": {"x": 1, "y": 1},
        "flip_horizontal": "yes",
    }
    with pytest.raises(ProjectValidationError, match="flip_horizontal must be true or false"):
        validate_project(project)


def test_transform_rotation_pivot_is_normalized_and_preserved():
    project = sample_project()
    project["tracks"][0]["clips"][0]["transform"] = {
        "position": {"x": 0, "y": 0},
        "scale": {"x": 1, "y": 1},
        "rotation_deg": 90,
        "opacity": 1,
        "anchor_x": 0.25,
        "anchor_y": 0.75,
    }
    transform = validate_project(project)["tracks"][0]["clips"][0]["transform"]
    assert transform["anchor_x"] == 0.25
    assert transform["anchor_y"] == 0.75


def test_transform_rotation_pivot_rejects_values_outside_normalized_range():
    project = sample_project()
    project["tracks"][0]["clips"][0]["transform"] = {
        "position": {"x": 0, "y": 0},
        "scale": {"x": 1, "y": 1},
        "anchor_x": 1.1,
        "anchor_y": 0.5,
    }
    with pytest.raises(ProjectValidationError, match="anchor_x"):
        validate_project(project)


def test_track_visual_visibility_is_a_boolean_and_defaults_can_be_preserved():
    project = sample_project()
    project["tracks"][0]["visible"] = False
    validated = validate_project(project)
    assert validated["tracks"][0]["visible"] is False


def test_track_visual_visibility_rejects_non_boolean_values():
    project = sample_project()
    project["tracks"][0]["visible"] = "hidden"
    with pytest.raises(ProjectValidationError, match="visible must be true or false"):
        validate_project(project)


def test_valid_timed_transcript_is_preserved_with_source_asset_and_language():
    project = sample_project()
    project["transcripts"] = [{
        "id": "transcript-main",
        "name": "Interview transcript",
        "source_media_id": "asset-video",
        "language": "en-US",
        "words": [
            {"text": "Hello,", "start_us": 100_000, "end_us": 350_000, "confidence": 0.98},
            {"text": "world!", "start_us": 350_000, "end_us": 600_000, "speaker_id": "speaker-1"},
        ],
    }]
    validated = validate_project(project)
    assert validated["transcripts"] == project["transcripts"]


def test_legacy_project_without_transcripts_remains_unchanged():
    project = sample_project()
    validated = validate_project(project)
    assert "transcripts" not in validated


def test_transcript_requires_existing_audio_or_video_source_asset():
    project = sample_project()
    project["transcripts"] = [{
        "id": "transcript-main", "source_media_id": "missing-asset",
        "language": "en", "words": [{"text": "Hello", "start_us": 0, "end_us": 100_000}],
    }]
    with pytest.raises(ProjectValidationError, match="source_media_id does not exist"):
        validate_project(project)


def test_transcript_rejects_image_or_font_source_asset():
    project = sample_project()
    project["assets"].append({
        "id": "font-asset", "media_type": "font", "file_name": "font.ttf",
        "storage_key": "font.ttf", "size_bytes": 10,
    })
    project["transcripts"] = [{
        "id": "transcript-main", "source_media_id": "font-asset",
        "language": "en", "words": [{"text": "Hello", "start_us": 0, "end_us": 100_000}],
    }]
    with pytest.raises(ProjectValidationError, match="video or audio media"):
        validate_project(project)


def test_transcript_rejects_unsorted_and_out_of_source_timing():
    project = sample_project()
    project["transcripts"] = [{
        "id": "transcript-main", "source_media_id": "asset-video",
        "language": "en", "words": [
            {"text": "later", "start_us": 500_000, "end_us": 600_000},
            {"text": "earlier", "start_us": 200_000, "end_us": 400_000},
        ],
    }]
    with pytest.raises(ProjectValidationError, match="ordered by source start"):
        validate_project(project)
    project["transcripts"][0]["words"] = [
        {"text": "too late", "start_us": 9_900_000, "end_us": 10_100_000},
    ]
    with pytest.raises(ProjectValidationError, match="exceeds the source media duration"):
        validate_project(project)


def test_transcript_rejects_invalid_language_spoken_text_and_word_range():
    project = sample_project()
    project["transcripts"] = [{
        "id": "transcript-main", "source_media_id": "asset-video",
        "language": "english-us", "words": [{"text": "Hello", "start_us": 0, "end_us": 100_000}],
    }]
    with pytest.raises(ProjectValidationError, match="language"):
        validate_project(project)
    project["transcripts"][0]["language"] = "en"
    project["transcripts"][0]["words"] = [{"text": "!!!", "start_us": 0, "end_us": 100_000}]
    with pytest.raises(ProjectValidationError, match="spoken token"):
        validate_project(project)
    project["transcripts"][0]["words"] = [{"text": "Hello", "start_us": 100_000, "end_us": 100_000}]
    with pytest.raises(ProjectValidationError, match="end_us must be after"):
        validate_project(project)


def test_transcript_rejects_duplicate_ids_invalid_confidence_and_unknown_fields():
    project = sample_project()
    item = {
        "id": "transcript-main", "source_media_id": "asset-video", "language": "en",
        "words": [{"text": "Hello", "start_us": 0, "end_us": 100_000, "confidence": 1.2}],
    }
    project["transcripts"] = [item, copy.deepcopy(item)]
    with pytest.raises(ProjectValidationError, match="confidence"):
        validate_project(project)
    valid_item = copy.deepcopy(item)
    valid_item["words"][0]["confidence"] = 0.9
    project["transcripts"] = [valid_item, {**copy.deepcopy(valid_item), "words": [
        {"text": "Again", "start_us": 100_000, "end_us": 200_000}
    ]}]
    with pytest.raises(ProjectValidationError, match="id is duplicated"):
        validate_project(project)
    project["transcripts"] = [{
        **valid_item,
        "words": [{"text": "Hello", "start_us": 0, "end_us": 100_000, "unexpected": True}],
    }]
    with pytest.raises(ProjectValidationError, match="unsupported fields"):
        validate_project(project)


def test_transcript_enforces_project_and_per_transcript_word_limits():
    project = sample_project()
    project["transcripts"] = [{
        "id": "transcript-main", "source_media_id": "asset-video", "language": "en",
        "words": [
            {"text": "word", "start_us": index, "end_us": index + 1}
            for index in range(20_001)
        ],
    }]
    with pytest.raises(ProjectValidationError, match="1 to 20000"):
        validate_project(project)
    project = sample_project()
    project["transcripts"] = [
        {
            "id": f"transcript-{index}", "source_media_id": "asset-video", "language": "en",
            "words": [{"text": "word", "start_us": 0, "end_us": 1}],
        }
        for index in range(101)
    ]
    with pytest.raises(ProjectValidationError, match="at most 100"):
        validate_project(project)


def test_transcript_rejects_unknown_top_level_fields():
    project = sample_project()
    project["transcripts"] = [{
        "id": "transcript-main", "source_media_id": "asset-video",
        "language": "en", "words": [{"text": "Hi", "start_us": 0, "end_us": 100_000}],
        "remote_url": "https://example.invalid/transcript.json",
    }]
    with pytest.raises(ProjectValidationError, match="unsupported fields"):
        validate_project(project)
