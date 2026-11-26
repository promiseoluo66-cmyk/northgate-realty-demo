# 52-Operation Implementation Audit — Stage 1 Lab

**Repository:** promiseoluo66-cmyk/northgate-realty-demo  
**Branch:** video-editor-lab  
**Audit basis:** registered tool definitions, executor dispatch source, test-file references and current Studio UI references.

## Summary

- 52 unique registered operations found.
- Executor dispatch reference found for all 52.
- 49 operations have a feature/subsystem test-file reference in addition to any registry-contract tests.
- `render.export` now has direct executor tests for confirmation, valid export dispatch, unsafe filenames, missing configuration, overwrite protection and failure isolation. A generated-video integration test exercises the real MLT renderer and probes the MP4 output.
- 34 operations are referenced by direct Studio UI code. The remaining operations are available through the AI/backend tool path rather than dedicated direct controls.
- This is a source-and-test-reference audit, not a claim that every edge case or live render outcome has been independently proven. All entries remain subject to the edge-case review below.

## Operation-by-operation inventory

Status meaning:
- **PASS (first-pass):** an executor dispatch reference and at least one feature/subsystem test-file reference were found. This does not mean every edge case is covered.
- **PARTIAL:** an executor dispatch reference exists, but only contract/registry evidence was found; dedicated end-to-end tool execution evidence remains to be added.
- **MISSING:** no executor dispatch reference was found.
- Studio **Yes** means direct Studio source references the operation. **AI/backend** means the tool is available through the registered AI/backend pathway, not a dedicated Studio button.

| # | Operation | Executor | Test references | Studio path | First-pass status |
|---:|---|---|---|---|---|
| 1 | `project.inspect` | Found | test_ai_tool_controller.py; test_tool_registry.py | AI/backend | PASS |
| 2 | `media.list` | Found | test_project_tool_extensions.py; test_tool_registry.py | AI/backend | PASS |
| 3 | `media.organize_asset` | Found | test_project_tool_extensions.py; test_capability_catalogue.py; test_tool_registry.py | Yes | PASS |
| 4 | `quality.inspect_media` | Found | test_quality_inspection.py; test_tool_registry.py | AI/backend | PASS |
| 5 | `audio.analyze_media` | Found | test_quality_inspection.py; test_tool_registry.py | AI/backend | PASS |
| 6 | `media.detect_scenes` | Found | test_quality_inspection.py; test_tool_registry.py | AI/backend | PASS |
| 7 | `project.set_profile` | Found | test_stage1_tasks_4_5.py | Yes | PASS |
| 8 | `timeline.add_track` | Found | test_stage1_tasks_4_5.py; test_tool_registry.py | Yes | PASS |
| 9 | `timeline.remove_track` | Found | test_stage1_tasks_4_5.py; test_tool_registry.py | Yes | PASS |
| 10 | `timeline.replace_clip_media` | Found | test_project_tool_extensions.py; test_capability_catalogue.py; test_tool_registry.py | Yes | PASS |
| 11 | `timeline.ripple_insert_clip` | Found | test_stage1_tasks_2_3.py; test_project_tool_extensions.py; test_capability_catalogue.py; test_tool_registry.py | Yes | PASS |
| 12 | `timeline.ripple_overwrite_clip` | Found | test_stage1_tasks_2_3.py; test_capability_catalogue.py | Yes | PASS |
| 13 | `timeline.add_clip` | Found | test_ai_tool_controller.py; test_tool_registry.py | Yes | PASS |
| 14 | `timeline.add_text_clip` | Found | test_ai_tool_controller.py; test_dual_ai_controller.py; test_tool_registry.py | AI/backend | PASS |
| 15 | `captions.import_subtitles` | Found | test_stage1_tasks_2_3.py; test_capability_catalogue.py | Yes | PASS |
| 16 | `captions.add_word_timed` | Found | test_project_tool_extensions.py | AI/backend | PASS |
| 17 | `text.update_clip` | Found | test_project_tool_extensions.py | AI/backend | PASS |
| 18 | `timeline.move_clip` | Found | test_stage1_tasks_2_3.py; test_tool_registry.py | Yes | PASS |
| 19 | `timeline.group_clips` | Found | test_stage1_tasks_2_3.py; test_capability_catalogue.py | Yes | PASS |
| 20 | `timeline.ungroup_clips` | Found | test_stage1_tasks_2_3.py; test_capability_catalogue.py | Yes | PASS |
| 21 | `timeline.add_marker` | Found | test_stage1_tasks_2_3.py; test_capability_catalogue.py | Yes | PASS |
| 22 | `timeline.move_marker` | Found | test_stage1_tasks_2_3.py; test_capability_catalogue.py | Yes | PASS |
| 23 | `timeline.remove_marker` | Found | test_stage1_tasks_2_3.py; test_capability_catalogue.py | Yes | PASS |
| 24 | `timeline.duplicate_clip` | Found | test_project_tool_extensions.py | Yes | PASS |
| 25 | `timeline.slip_clip` | Found | test_project_tool_extensions.py; test_capability_catalogue.py; test_tool_registry.py | Yes | PASS |
| 26 | `timeline.trim_clip` | Found | test_stage1_tasks_4_5.py; test_tool_registry.py | Yes | PASS |
| 27 | `timeline.split_clip` | Found | test_ai_tool_controller.py; test_stage1_tasks_2_3.py; test_tool_registry.py | Yes | PASS |
| 28 | `timeline.delete_clip` | Found | test_ai_tool_controller.py; test_stage1_tasks_2_3.py; test_tool_registry.py | Yes | PASS |
| 29 | `timeline.ripple_delete_clip` | Found | test_project_tool_extensions.py | AI/backend | PASS |
| 30 | `track.set_state` | Found | test_project_tool_extensions.py; test_stage1_tasks_4_5.py; test_tool_registry.py | Yes | PASS |
| 31 | `track.reorder` | Found | test_project_tool_extensions.py; test_capability_catalogue.py; test_tool_registry.py | Yes | PASS |
| 32 | `track.rename` | Found | test_project_tool_extensions.py | Yes | PASS |
| 33 | `track.set_locked` | Found | test_project_tool_extensions.py; test_stage1_tasks_2_3.py | Yes | PASS |
| 34 | `clip.set_speed` | Found | test_project_tool_extensions.py; test_ai_tool_controller.py; test_cloudflare_runner.py; test_dual_ai_controller.py | Yes | PASS |
| 35 | `clip.set_transform` | Found | test_project_tool_extensions.py; test_ai_tool_controller.py; test_tool_registry.py | Yes | PASS |
| 36 | `clip.set_framing` | Found | test_project_tool_extensions.py; test_tool_registry.py | Yes | PASS |
| 37 | `clip.set_crop` | Found | test_project_tool_extensions.py; test_capability_catalogue.py; test_tool_registry.py | Yes | PASS |
| 38 | `animation.set_keyframe` | Found | test_project_tool_extensions.py; test_ai_tool_controller.py; test_stage1_tasks_4_5.py; test_tool_registry.py | Yes | PASS |
| 39 | `animation.clear_keyframes` | Found | test_project_tool_extensions.py; test_capability_catalogue.py; test_tool_registry.py | Yes | PASS |
| 40 | `animation.remove_keyframe` | Found | test_project_tool_extensions.py; test_capability_catalogue.py; test_tool_registry.py | Yes | PASS |
| 41 | `effect.add` | Found | test_ai_tool_controller.py; test_tool_registry.py | AI/backend | PASS |
| 42 | `effect.remove` | Found | test_stage1_tasks_4_5.py | AI/backend | PASS |
| 43 | `effect.set_enabled` | Found | test_project_tool_extensions.py | AI/backend | PASS |
| 44 | `timeline.add_transition` | Found | test_ai_tool_controller.py; test_tool_registry.py | AI/backend | PASS |
| 45 | `audio.set_gain` | Found | test_ai_tool_controller.py; test_tool_registry.py | AI/backend | PASS |
| 46 | `audio.set_fade` | Found | test_ai_tool_controller.py; test_tool_registry.py | AI/backend | PASS |
| 47 | `history.undo` | Found | test_ai_tool_controller.py | Yes | PASS |
| 48 | `history.redo` | Found | test_ai_tool_controller.py | Yes | PASS |
| 49 | `render.export` | Found | test_render_export_operation.py; test_tool_registry.py | AI/backend | PASS |
| 50 | `media.extract_audio` | Found | test_project_tool_extensions.py | AI/backend | PASS (automated generated-media test) |
| 51 | `timeline.create_freeze_frame` | Found | test_project_tool_extensions.py | AI/backend | PASS (automated generated-media test) |
| 52 | `media.create_proxy` | Found | test_project_tool_extensions.py; test_cloudflare_runner.py; test_tool_registry.py | Yes | PASS (generated-media, private upload and undo/redo tests; latest CI pending) |

## Edge-case and integration audit still required

The source/test-reference scan does not establish all of the following for every operation. The remaining audit must test these dimensions operation by operation:

1. Valid inputs, missing IDs/assets, malformed identifiers, numeric/string boundaries and unsupported combinations.
2. Locked/disabled tracks, overlap conditions, cross-track consistency and atomic rollback after failure.
3. Confirmation gates for destructive calls, plus undo/redo history behaviour and stale-revision handling.
4. Renderer integration and generated output for operations that affect media, not only the resulting project JSON.
5. UI/AI/backend integration and error reporting, including operations intentionally exposed only to the AI/backend pathway.
6. The Python executor's `render.export` path is now directly exercised, including a real generated-media MLT export. The hosted Cloudflare Worker-to-GitHub-runner job lifecycle remains unverified because this lab has no deployed Worker.

The operation audit now checks all 52 registered operations for closed schemas, required fields, numeric bounds, unknown arguments, malformed track-ID arrays and confirmation gates. Generated proxy coverage includes FFmpeg output dimensions/duration, duplicate rejection, undo/redo and private Release persistence. Task 4/5 tests cover track gain/pan validation and filter configuration, crop-keyframe validation, animated affine geometry, source-boundary rejection, and additional easing curves. The live Worker/renderer configuration is still not deployed in this test-only lab.

## Safety boundary

All work remains on `video-editor-lab`. Do not merge to Stable, change Northgate main, or deploy the Worker as part of this audit.
