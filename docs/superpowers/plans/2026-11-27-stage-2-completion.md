# Stage 2 Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the approved Stage 2 editor capabilities on `video-editor-lab`, including transcript-aware silence review, text/graphics/caption enhancements, evidence-based optional AI gates, mobile Studio controls, and full offline verification, then stop before Stage 3.

**Architecture:** Extend the existing canonical project model, registered tool operations, revision-checked executor, MLT renderer, Cloudflare Worker and mobile Studio. Keep optional AI services disabled unless a documented, genuinely $0 and licensed route passes real-footage tests. Use one task per independently reviewable capability group, with Python/Node regression tests and actual MLT renders for visual behaviour.

**Tech Stack:** Python 3.12-compatible code, pytest, FFmpeg/FFprobe, MLT, JavaScript ES modules, Node.js 22, Cloudflare Worker/D1 offline tests, existing GitHub Actions workflow.

**Spec:** `video-editor/architecture/STAGE_2_EXECUTION_PLAN.md` and the approved Stage 2 completion design recorded in the 2026-11-27 conversation.

## Global Constraints

- Repository: `promiseoluo66-cmyk/northgate-realty-demo`; working branch: `video-editor-lab`.
- Never modify `main`; do not merge, deploy, publish, or create a public release.
- Budget is $0: no paid APIs, billing activation, paid fallback, hidden credits, or recurring costs.
- Reuse the canonical project model, tool registry, revisioned executor, MLT renderer, private asset lifecycle and existing Studio; do not duplicate operations.
- Destructive edits require explicit human confirmation, revision checks, atomic mutation, and undo/redo.
- Preserve source media and transcript data; never interpret measured silence as proof of a filler word or unwanted content.
- Every claimed render feature requires decoded output-frame/audio evidence, not just UI or unit tests.
- AI transcription, translation, generated stickers and TTS/dubbing remain disabled unless free limits, licence, privacy, mobile/runner feasibility and real-footage quality are verified.
- Do not change CI workflow configuration or trigger GitHub Actions just to check progress. Run existing suites only at planned verification gates; Actions may run naturally on a relevant push.
- Keep the Android-first Studio usable on narrow screens, keyboard accessible, and clear about unsupported cases.
- Preserve existing project JSON compatibility; migrations or schema changes require backwards-compatibility tests.

## Review Focus

- Stale project revisions during review/apply: reject without partial mutation.
- Partial audio scans and unmatched silence boundaries: label coverage accurately and never invent an end time.
- Silence crossing clip boundaries, non-1x playback, and transcript/source timestamp offsets: block unsupported mappings rather than cutting the wrong section.
- Malformed, oversized, hostile or unsupported image/font/template assets: reject before project mutation or rendering.
- Missing optional models, offline runtime, expired quotas or licence uncertainty: keep the feature gated and retain a working manual workflow.

---

## Existing file map

- `video-editor/project_model.py`: canonical project and feature-data validation.
- `video-editor/tool_registry.py`: closed operation schemas, descriptions and confirmation metadata.
- `video-editor/project_tool_executor.py`: read-only analysis, atomic project edits, revision/undo/redo behaviour.
- `video-editor/mlt_engine/renderer.py`: MLT render compilation and supported visual/audio effects.
- `video-editor/tests/test_project_tool_extensions.py`, `test_project_model.py`, `test_mlt_renderer.py`, and dedicated integration tests: Python acceptance.
- `video-editor/cloudflare/public/index.html`, `studio.js`, and `caption_io.js`: mobile Studio UI and subtitle utilities.
- `video-editor/cloudflare/tests/studio-ui.test.mjs`, `caption-io.test.mjs`, and `worker.test.mjs`: Node acceptance.
- `video-editor/architecture/CAPCUT_PARITY_CAPABILITIES.json`, `STAGE_2_EXECUTION_PLAN.md`, and `STUDIO_FOUNDATION_STATUS.md`: capability and status evidence.

## Task 2.4 — Measured silence review and approved silence cuts

**Files:**
- Modify: `video-editor/tool_registry.py`
- Modify: `video-editor/project_tool_executor.py`
- Modify: `video-editor/tests/test_project_tool_extensions.py`
- Modify: `video-editor/cloudflare/public/index.html`
- Modify: `video-editor/cloudflare/public/studio.js`
- Modify: `video-editor/cloudflare/tests/studio-ui.test.mjs`

**Interfaces:**
- Reuse `_analyze_audio_media(project, media_id, analysis_seconds, silence_threshold_db)`.
- Add read-only `transcript.review_silence` with `transcript_id`, `clip_id`, `analysis_seconds` (1–600), `silence_threshold_db` (-80 to -10 dB), and `minimum_silence_us` (bounded positive integer).
- Add confirmed `transcript.apply_silence_cut` with `transcript_id`, `clip_id`, `source_start_us`, and `source_end_us`.
- Review returns candidate IDs, exact source/timeline bounds, adjacent transcript words, measured duration, scan coverage, applicability and blockers. Apply revalidates the source interval against a fresh measurement and current project revision before editing.

- [ ] Add tests for real measured gaps between adjacent words, no gap without measured silence, partial scans, no-audio assets, clip/source offsets, playback rates other than 1x, unsupported overlaps, locked tracks, transitions, linked groups, keyframes, stale revisions, confirmation, atomic rollback, undo and redo.
- [ ] Run focused Python tests and confirm new tests fail for the intended missing behaviour.
- [ ] Implement bounded server-side review and a shared atomic time-range cut helper; do not mutate during review.
- [ ] Implement confirmed apply with fresh silence verification; preserve transcript and source asset; reject any ambiguous mapping.
- [ ] Add Studio controls for choosing transcript/clip, running analysis, reviewing each candidate and approving one cut at a time. Display measured/partial coverage and adjacent words; label silence as a signal measurement, not a filler-word verdict.
- [ ] Add UI tests for candidate rendering, blocked candidates, confirmation, errors and narrow-screen controls.
- [ ] Run focused Python and Node tests; verify undo/redo and source preservation.
- [ ] Commit the task.

## Task 2.5 — Automatic speech-to-text feasibility and gated integration

**Files:**
- Create: `video-editor/architecture/STAGE_2_SPEECH_TO_TEXT_EVIDENCE.md`
- Modify only if a qualifying provider is proven: `video-editor/tool_registry.py`, `project_tool_executor.py`, `project_model.py`, Studio UI and their tests.

**Interfaces:** Candidate transcription must produce the existing transcript word schema: `text`, `start_us`, `end_us`, optional `speaker_id` and `confidence`. The existing `transcript.import_words` remains the manual fallback.

- [ ] Compare local/offline speech-to-text candidates using official licence, model size, download, runtime, hardware, privacy and maintenance evidence.
- [ ] Record whether the whole workflow can run without paid billing, recurring usage, hidden credits or requiring the Android phone to remain on.
- [ ] Define a repeatable real-footage benchmark: word error rate, word-boundary timing error, language coverage, noisy speech, music/background speech and failure handling.
- [ ] If no candidate meets every gate, add evidence and keep `auto_captions` explicitly `gated_optional`; do not add a fake or placeholder transcription button.
- [ ] If a candidate qualifies, write failing tests first, implement behind an explicit capability flag, and verify real-footage output and manual correction before enabling it.
- [ ] Commit evidence and any qualifying implementation.

## Task 2.6 — Expanded text styling

**Files:**
- Modify: `video-editor/project_model.py`
- Modify: `video-editor/tool_registry.py`
- Modify: `video-editor/project_tool_executor.py`
- Modify: `video-editor/mlt_engine/renderer.py`
- Modify: `video-editor/tests/test_project_model.py`
- Modify: `video-editor/tests/test_project_tool_extensions.py`
- Modify: `video-editor/tests/test_mlt_renderer.py`
- Modify: `video-editor/cloudflare/public/index.html`, `studio.js`, and `cloudflare/tests/studio-ui.test.mjs`

**Interfaces:** Extend the existing `text.update_clip` operation and text object. Do not add a duplicate text-edit operation. New fields must be optional with stable defaults for older projects.

- [ ] Add failing model/registry tests for bounded background fill/opacity, shadow colour/blur/offset, letter spacing, line spacing and supported font weight; reject unknown fields and out-of-range values.
- [ ] Add renderer tests that decode generated title/caption PNG frames and verify background, shadow and spacing are visible.
- [ ] Implement only properties supported by the existing MLT/text-image path; define exact numeric bounds in tests and schema.
- [ ] Extend inspector controls and ensure selected text values load/save through revision-checked `text.update_clip`.
- [ ] Verify old projects without the new fields render identically; verify save/reopen, undo/redo and invalid-input atomicity.
- [ ] Commit the task.

## Task 2.7 — Text, caption and word-highlight animation

**Files:**
- Modify: `video-editor/project_model.py`, `tool_registry.py`, `project_tool_executor.py`, `mlt_engine/renderer.py`
- Modify: `video-editor/tests/test_project_model.py`, `test_project_tool_extensions.py`, `test_mlt_renderer.py`
- Modify: `video-editor/cloudflare/public/index.html`, `studio.js`, `cloudflare/tests/studio-ui.test.mjs`

**Interfaces:** Use the canonical clip-local microsecond timebase and existing keyframe conventions. Keep animation data editable in project JSON.

- [ ] Test entrance, exit, loop and word-highlight boundaries, missing/overlapping ranges, zero-duration clips, frame rounding and unsupported combinations.
- [ ] Implement a bounded animation schema and registry/executor operation only if existing generic keyframes cannot express the required text properties cleanly.
- [ ] Compile animation into MLT filters/overlay timing without flattening editable text.
- [ ] Add simple mobile presets and controls; preserve manual static text as the fallback.
- [ ] Render actual clips and decode frames immediately before, at and after each animation boundary.
- [ ] Verify save/reopen and undo/redo; commit.


## Task 2.8 — Editable title templates

**Status: Complete — offline CI accepted.** Implementation commit b5e58d793c5859b3d70e0bf7a6e5bc1eec187492; GitHub Actions [run #46122647203](https://github.com/promiseoluo66-cmyk/northgate-realty-demo/actions/runs/46122647203).

**Files:**
- Create: video-editor/title_templates.py
- Create: video-editor/tests/test_title_templates.py
- Create: video-editor/tests/test_title_templates_mlt_integration.py
- Modify: video-editor/tool_registry.py, project_tool_executor.py, cloudflare/public/index.html, cloudflare/public/studio.js, cloudflare/tests/studio-ui.test.mjs
- Modify: video-editor/tests/test_project_tool_extensions.py, test_capability_catalogue.py, test_operation_audit.py, architecture/STAGE_2_EXECUTION_PLAN.md, architecture/CAPCUT_PARITY_CAPABILITIES.json

**Implemented:** Four original built-in version-1 templates. Strict data-only schema validation. Read-only title_templates.list. Optional template_id on existing timeline.add_text_clip; copied style and duration-resolved keyframes become an ordinary editable text clip. Legacy calls remain compatible. Mobile Studio insertion controls use existing revision-checked operations and text inspector.

**Acceptance evidence:**
- [x] Test schema version, invalid fields, unsupported versions, duplicate IDs/names, size limits and project portability.
- [x] Implement deterministic template validation and apply-to-new-clip behaviour.
- [x] Add four original templates with no third-party brand assets.
- [x] Add mobile template selection and preserve normal editing of inserted clips.
- [x] Verify actual MLT-generated static and animated output frames, clip boundaries, save/reopen, undo/redo and revision conflicts.
- [x] Full CI: 368 Python tests, 74 Node tests, 0 Node failures and all checked-in D1 migrations passed.
- [x] No new runtime dependencies or D1 migrations; no deployment or merge.

Hosted Worker/live-media and Android acceptance remain separate and were not performed.

## Task 2.9 — Editable stickers and graphics

**Files:**
- Create: `video-editor/graphics.py`
- Create: `video-editor/tests/test_graphics.py`
- Modify: `video-editor/project_model.py`, `tool_registry.py`, `project_tool_executor.py`, `mlt_engine/renderer.py`
- Modify: `video-editor/tests/test_project_model.py`, `test_project_tool_extensions.py`, `test_mlt_renderer.py`
- Modify: `video-editor/cloudflare/public/index.html`, `studio.js`, `cloudflare/tests/studio-ui.test.mjs`

**Interfaces:** Graphics are editable overlay clips with a bounded type (shape, arrow, frame or imported image), geometry, fill/stroke, timing and optional project asset reference. Imported files use the existing private media asset lifecycle.

- [ ] Test allowed geometry, dimensions, opacity, colour, path complexity, unsupported SVG/script content, MIME mismatch, decompression bombs and asset-size caps.
- [ ] Implement simple native shapes using renderer-owned drawing primitives; do not execute imported SVG or HTML.
- [ ] Add imported raster overlay support using validated image assets and provenance metadata.
- [ ] Add mobile controls for create, position, resize, colour and duration.
- [ ] Render and decode fixtures; verify project asset save/reopen and undo/redo; commit.

## Task 2.10 — AI sticker feasibility gate

**Files:**
- Create: `video-editor/architecture/STAGE_2_AI_STICKER_EVIDENCE.md`
- Modify capability catalogue only after evidence review.

- [ ] Research official model and service terms, zero-cost quota, commercial-use rights, privacy, model download size, hardware/runtime needs and output provenance.
- [ ] Do not add a runtime dependency or UI control unless every gate passes and the user explicitly approves any external service connection.
- [ ] Otherwise preserve `ai_stickers` as `gated_optional`, document why, and keep native editable graphics available.
- [ ] Commit evidence.

## Task 2.11 — Bilingual captions

**Files:**
- Modify: `video-editor/project_model.py`, `tool_registry.py`, `project_tool_executor.py`
- Modify: `video-editor/tests/test_project_model.py`, `test_project_tool_extensions.py`, `test_mlt_renderer.py`
- Modify: `video-editor/cloudflare/public/index.html`, `studio.js`, `cloudflare/tests/studio-ui.test.mjs`

**Interfaces:** Use two independent editable text tracks with language tags and existing caption timing. No automatic translation is implied.

- [ ] Test language tag validation, two-track creation, independent edits, matching/unaligned cue timing, track locking and export.
- [ ] Add a bilingual setup operation only if the existing track and caption operations cannot express the workflow without unsafe multi-step partial writes.
- [ ] Add side-by-side language track selection and preview controls; clearly identify each language.
- [ ] Verify both tracks render at correct times, remain editable and survive save/reopen/undo/redo; commit.

## Task 2.12 — Text-to-speech and dubbing feasibility gate

**Files:**
- Create: `video-editor/architecture/STAGE_2_TTS_DUBBING_EVIDENCE.md`
- Modify capability catalogue only after evidence review.

- [ ] Evaluate local/free TTS candidates against official licences, voice rights, language quality, model size, runtime, privacy and storage.
- [ ] Do not clone a real person's voice or enable voice generation without explicit rights and user approval.
- [ ] Keep `tts_dubbing` gated if any cost, licence or runtime question remains unresolved.
- [ ] If a qualifying route exists, propose its exact data flow and tests separately before implementation; commit evidence.

## Task 2.13 — Mobile transcript and caption review interface

**Files:**
- Modify: `video-editor/cloudflare/public/index.html`, `studio.js`
- Modify: `video-editor/cloudflare/tests/studio-ui.test.mjs`
- Modify: `video-editor/cloudflare/public/caption_io.js` and `caption-io.test.mjs` only if subtitle utilities need extension.

**Interfaces:** Consume the existing transcript import/search/propose/apply operations and the Task 2.4 review/apply operations. Keep all destructive actions revision checked and confirmation gated.

- [ ] Test transcript list/loading, search result selection, word/range selection, text correction, candidate review, blocked states and API errors.
- [ ] Implement narrow-screen word list and range selection with accessible labels, clear selection state and bounded rendering for large transcripts.
- [ ] Add manual transcript correction using existing import/edit operations; do not silently rewrite source timestamps.
- [ ] Verify all actions use the selected transcript and clip IDs, and that stale revisions refresh rather than overwrite.
- [ ] Commit.

## Task 2.14 — Cross-feature reliability and security audit

**Files:**
- Modify: `video-editor/tests/test_operation_audit.py`
- Modify: `video-editor/tests/test_project_model.py`
- Modify: `video-editor/tests/test_project_tool_extensions.py`
- Modify: `video-editor/cloudflare/tests/worker.test.mjs`
- Add focused security regression tests where required.

- [ ] Extend closed-schema, required-field, type/range, confirmation and stale-revision tests to every new operation.
- [ ] Test batch rollback when a later operation fails, undo/redo across each new feature, and project reopening from persisted JSON.
- [ ] Test untrusted imported assets, path traversal, malformed image data, resource exhaustion limits and private storage references.
- [ ] Test that optional providers fail closed and manual workflows remain usable when unavailable.
- [ ] Run the full existing Python, Node/Worker and D1 migration suites; resolve failures without weakening existing assertions.
- [ ] Perform a security review of permissions, data retention, asset validation, external requests and generated-media storage; commit.

## Task 2.15 — Final Stage 2 verification and status closeout

**Files:**
- Modify: `video-editor/architecture/STAGE_2_EXECUTION_PLAN.md`
- Modify: `video-editor/architecture/STUDIO_FOUNDATION_STATUS.md`
- Modify: `video-editor/architecture/CAPCUT_PARITY_CAPABILITIES.json`
- Modify: `video-editor/architecture/CAPCUT_PARITY_FEATURE_CATALOGUE.md`
- Modify: `video-editor/architecture/49_OPERATION_IMPLEMENTATION_AUDIT.md` only if operation counts or audit scope changed.

- [ ] Run `/usr/bin/python3 -m pytest tests -q` from `video-editor/`.
- [ ] Run `node --check public/studio.js`, `node --check src/index.js`, and `node --test tests/*.test.mjs` from `video-editor/cloudflare/`.
- [ ] Apply all checked-in D1 migrations to an in-memory SQLite database using the existing workflow procedure.
- [ ] Run each real MLT render integration test, including silence/caption/text/animation/graphics fixtures, and decode the output frames/audio for assertions.
- [ ] Verify save/reopen, undo/redo, private generated-asset persistence and recovery paths for all newly added media types.
- [ ] Update each capability to `prototype_verified`, `partially_implemented`, `gated_optional` or `planned` based only on evidence; never mark an unimplemented/provider-gated feature complete.
- [ ] Update status and task ledger with exact test counts, command results, commit SHAs and unresolved hosted/Android limitations.
- [ ] Perform final code review and confirm the branch diff contains only intended files.
- [ ] Stop at the Stage 2 boundary. Do not start Stage 3, merge, deploy, publish or release.

---

## Execution protocol

For every implementation task: write the failing test first; run it and record the expected failure; implement the smallest compatible change; rerun the focused test; run relevant regression suites; inspect the diff; perform the role-based review; then commit. If a test fails unexpectedly, use systematic debugging and preserve the failure evidence. Never change CI configuration or trigger a workflow merely to create activity.

**Completion means:** all implementable Stage 2 tasks have passing evidence, provider-dependent features are honestly gated where required, the capability/status documents match the code, and the working branch is left ready for a separate Stage 3 approval.
