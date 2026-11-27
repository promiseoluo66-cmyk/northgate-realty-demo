# Stage 2 — Text, Captions and Transcript Editing

**Repository:** `promiseoluo66-cmyk/northgate-realty-demo`  
**Working branch:** `video-editor-lab`  
**Stage scope:** 15 capability IDs in the approved 118-entry catalogue  
**Budget:** $0; no paid billing, paid fallback or hidden AI credits  
**Rule:** Reuse the existing project model, tool registry, revisioned executor, MLT renderer and Studio. Do not duplicate registered operations.

## Stage 2 completion rule

A feature is complete only after its data contract, permission and validation rules, renderer/provider path, Studio controls, failure behaviour and relevant tests are present. Timing/text changes must survive save/reopen and undo/redo. Rendering features require generated-media checks, not only menu or unit tests.

## Task ledger

| Task | Capability IDs | Work and acceptance evidence | Status |
|---|---|---|---|
| 2.1 | `manual_subtitles`, `subtitle_import_export` | Edit existing caption text in Studio; import/export SRT/VTT; preserve cue text/timestamps to millisecond precision; reject malformed, overlapping and oversized cues; verify real MLT rendered edits. Reuse `captions.import_subtitles` and `text.update_clip`. | **Offline CI accepted** — run #45983414095 (276 Python, 64 Node, D1 migrations; real MLT caption render passed). Hosted/Android acceptance remains separate. |
| 2.2 | `word_timing` | Define validated source-linked transcript records with word text, start/end timestamps and optional speaker/confidence; ingest user-supplied timing; exact phrase search; map matches to timeline clips at constant speed and flag animated-speed mappings as unsupported. | **Offline CI accepted** — run #45985231376 (296 Python, 64 Node, D1 migrations passed). Hosted/Android acceptance remains separate. |
| 2.3 | `transcript_driven_editing` | Select inclusive timed word ranges on one chosen source clip; preview exact source/timeline range; apply only after explicit confirmation through an atomic split+ripple-delete transaction with undo/redo. Refuses keyframes, linked groups, transitions, locked tracks and overlapping clips. Limitation: one selected clip and its track; automatic multi-track A/V sync and pause/filler removal remain open. | **Offline CI accepted** — run #45986714784 (304 Python, 64 Node, D1 migrations passed). |
| 2.4 | `transcript_driven_editing` | Combine transcript timing with measured silence candidates; never label technical silence as a filler word; show source/timeline bounds and adjacent words; apply only one freshly remeasured cut after explicit approval. | **Offline CI accepted** — final run #46000546362 (314 Python, 69 Node, 0 Node failures, D1 migrations and real MLT silence-cut render passed). |
| 2.5 | `auto_captions` | Evaluate local/free speech-to-text runtimes, licences, model size/download, runner/mobile fit, compute and retention. Enable only after a genuinely $0 route passes real-footage timing tests; otherwise remain visibly gated. | **Feasibility evidence complete — gated_optional**; Whisper/whisper.cpp is a viable local candidate, but real-footage quality/runtime acceptance is still missing. |
| 2.6 | `text_style` | Add validated typography, background, shadow and spacing settings; render generated frame fixtures for every supported control. | **In progress** — existing schema/model/Studio controls and render fixtures are present; audit found advanced-renderer routing is not connected and the ASS helper recurses. Shadow blur is missing. Regression tests added in commit `cd649ad1da4d6b626ef5d8fa952b2d0b6d2bf80f`; execution result is not yet observable through the connected GitHub status tools. |
| 2.7 | `text_animation`, `caption_animations`, `karaoke_lyrics` | Add entrance/exit/loop and word-highlight animation through the canonical timing model; render boundary frames and verify timing. | Planned |
| 2.8 | `title_templates` | Save/load editable title recipes with schema version and compatibility checks; never flatten templates into video. | Planned |
| 2.9 | `stickers_graphics` | Build editable shapes, arrows, frames and imported image overlays; validate dimensions and retain asset provenance/licence. | Planned |
| 2.10 | `ai_stickers` | Research only after model licence, zero-cost quota, privacy and runtime are verified. | **Feasibility evidence complete — gated_optional**; the model licence is conditional and no dependable free GPU runtime is available. |
| 2.11 | `bilingual_captions` | Support two manually supplied language tracks first; translation remains disabled until a free/licensed route is verified. | Planned / provider gated |
| 2.12 | `tts_dubbing` | Evaluate only free, licensed local voice routes; keep disabled until voice rights, language coverage and output quality pass. | **Feasibility evidence complete — gated_optional**; Piper voice rights are model-specific and no voice/output-quality acceptance has been completed. |
| 2.13 | Supports Tasks 2.2–2.4 | Add mobile-friendly transcript search, word/range selection, correction and review controls that call revision-checked operations. | Planned |
| 2.14 | All Stage 2 IDs | Test stale revisions, atomic rollback, confirmation gates, source preservation, malformed inputs, limits and undo/redo. | Planned |
| 2.15 | All Stage 2 IDs | Run Python, Node/Worker, D1 and generated-media suites; verify rendered output and project save/reopen; update catalogue/status totals. | Planned |

## Existing functionality to preserve and reuse

- Basic timed text/title/caption overlays are rendered as transparent RGBA images by MLT.
- Basic text properties are represented in text clips and validated in the project model.
- `captions.import_subtitles` creates timed caption clips from supplied cues.
- `captions.add_word_timed` creates caption clips from supplied verified word timestamps; it does not transcribe audio.
- `text.update_clip` updates an existing caption/title clip without introducing a new operation.
- Studio already imports SRT/VTT, with a 1 MiB file cap and 500-cue cap, but direct text correction and sidecar export were missing.

## Task 2.1 — subtitle editing and sidecar round-trip

1. Extract parsing/serialization to a shared testable module.
2. Support BOM/newline normalization, cue identifiers, WebVTT headers/settings, multiline cue text and safe entity handling.
3. Keep the existing 1 MiB / 500-cue import limits; reject malformed, empty, overlapping or non-positive cues before applying edits.
4. Add an editor for a selected text/caption clip. Save via existing `text.update_clip` and the usual revision-checked manual edit path.
5. Export the selected text track as SRT or VTT. Sidecars preserve text/timing to millisecond precision, not font styling. Reject overlaps/rounding that cannot be safely re-imported.
6. Test import/export round-trips, cue limits, malformed files, overlap handling, UI IDs and existing renderer regressions.

**Non-goals:** no speech-to-text; no translation/TTS; no duplicate caption edit tool; no Worker deployment, live media upload or public Release.

**Completion evidence:** update this ledger and capability catalogue only after the relevant GitHub Actions run passes. Android/hosted acceptance is separate and must not be claimed without an authorized real test.


## Task 2.4 — measured silence review and approval-gated cuts

**Offline implementation and CI accepted on `video-editor-lab`.**

- Added read-only `transcript.review_silence`. It uses the existing FFmpeg/FFprobe audio analyser, with the requested minimum silence duration applied to the actual `silencedetect` filter.
- Review returns only measured silence intervals wholly between adjacent timed transcript words. Each candidate includes source and timeline bounds, measured duration, adjacent words, scan coverage, blockers and a `not_evaluated` semantic assessment. It never calls silence a filler word.
- Added `transcript.apply_silence_cut`, which requires explicit confirmation, a current project revision and a fresh measurement that still covers the exact requested interval.
- The cut uses one atomic split/ripple-delete transaction. Locked tracks, linked groups, keyframed clips, transitions, source-range errors and same-track overlaps block the cut. Source media and transcript words remain unchanged; undo/redo restore the edit as separate revisions.
- Added a Worker analysis-only job path. It returns measured candidates through D1 without rendering a new video. Worker confirmation rules now include transcript word cuts and silence cuts.
- Added mobile Studio controls to select a timed transcript, set scan/threshold/minimum values, inspect each candidate and approve cuts individually.

**GitHub Actions evidence:** run #46000233242 passed on commit `c8bb6b24835a188f689aaf111b84ba7aa9440039`: 314 Python tests, 69 Node tests, 0 Node failures and all checked-in D1 migrations passed. The real MLT integration test generated a video with a 500 ms silent section, reviewed and cut it, rendered the edited project, verified the shorter duration and decoded the expected post-cut 880 Hz audio segment. The original source file was byte-for-byte unchanged.

No Worker deployment, live private Release upload or Android usability test was performed. Multi-track A/V synchronisation and filler-word recognition remain outside this task.


## Task 2.5 — automatic speech-to-text feasibility

**Feasibility evidence complete; capability remains `gated_optional`.**

- Candidate: OpenAI Whisper and the C/C++ `whisper.cpp` implementation. Whisper code and model weights are MIT-licensed. `whisper.cpp` documents CPU-only inference and a tiny model footprint of about 75 MiB on disk and 273 MB memory.
- This repository is public. GitHub documents standard public Linux runners as free and unlimited, with 4 CPU cores, 16 GB RAM and 14 GB SSD for `ubuntu-24.04`. This is a plausible $0 processing route, not a proof of acceptable runtime for arbitrary user videos.
- Cloudflare Workers Free is not an inference host: its documented per-request CPU limit is 10 ms and memory is 128 MB. Heavy ASR must stay on the GitHub runner, not the Worker.
- The model can be downloaded and run locally on the runner, avoiding a paid transcription API. Media still passes through GitHub-hosted processing; workflow logs must never print source audio or transcript contents.
- **Decision:** do not enable automatic captions yet. No representative real-footage benchmark has established acceptable word error rate, timestamp drift, language/accent coverage, noisy-audio behavior or runtime under the existing 30-minute job limit. User-supplied timed transcripts remain supported.

Sources:
- [OpenAI Whisper README and model-size table](https://github.com/openai/whisper)
- [OpenAI Whisper MIT licence](https://github.com/openai/whisper/blob/main/LICENSE)
- [whisper.cpp CPU-only support and memory table](https://github.com/ggml-org/whisper.cpp)
- [GitHub-hosted runner specifications and public-repository pricing](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)

## Task 2.10 — AI sticker feasibility

**Feasibility evidence complete; capability remains `gated_optional`.**

- Stability AI's Community License includes Stable Diffusion 3.5 and permits use by individuals/organisations below USD $1 million annual revenue, subject to the licence terms. This is a conditional model licence, not a free inference service.
- Cloudflare Workers Free has only 10 ms CPU per request and 128 MB memory, so it cannot host this generation workload.
- The public GitHub Actions runner is free but is a CPU-only 4-core/16-GB standard runner. CPU image generation has not been benchmarked against the editor's job timeout and there is no guaranteed free hosted GPU. An external API would introduce uncertain quotas or charges.
- **Decision:** keep AI sticker generation disabled. Continue with editable native graphics first. Reconsider only after a tested $0 compute route, model-specific commercial licence, privacy review, safety checks and acceptable generation latency are demonstrated.

Sources:
- [Stability AI model licensing and Community License terms](https://stability.ai/license)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [GitHub-hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

## Task 2.12 — TTS and dubbing feasibility

**Feasibility evidence complete; capability remains `gated_optional`.**

- Candidate: Piper is a local neural TTS engine. The current `piper1-gpl` engine is GPL-3.0-or-later; distribution would require a GPL compliance review.
- Piper does not grant one blanket licence for all voices. Each voice's `MODEL_CARD` and full fine-tuning chain must be checked. The project's licensing guide warns that common Lessac-derived voices inherit research-only/non-commercial restrictions; it separately lists voice models whose training chains permit commercial use.
- A specific public-domain or permissively licensed voice may be a future candidate, but no voice has been selected, benchmarked or approved for redistribution in this editor.
- Cloudflare Workers Free cannot run TTS inference within 10 ms CPU/128 MB. A GitHub Actions CPU runner could be tested, but runtime, language coverage, pronunciation, naturalness, timing alignment and voice-model download costs in bandwidth/storage have not been accepted.
- **Decision:** keep TTS/dubbing disabled. No voice cloning, external paid API, automatic translation or dubbing is enabled. Reconsider only after the exact engine and voice model chain are verified, commercial rights are clear, and rendered output passes human quality review.

Sources:
- [Piper engine and voice licensing guide](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/LICENSING.md)
- [Piper commercial-use voice list and training-chain requirements](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/COMMERCIAL_USE.md)
- [Piper engine repository and GPL-3.0-or-later licence](https://github.com/OHF-Voice/piper1-gpl)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)

## Task 2.6 — expanded text styling: resumption audit

**Status: In progress; implementation not yet changed in this session.**

- Existing text-style schema fields, project-model validation, `text.update_clip`, Studio controls and rendering assertions cover font weight, background fill/opacity, shadow colour/offset/opacity, letter spacing and line spacing.
- The current renderer audit found `_make_ass_text_overlay_image()` recursively calls itself whenever advanced styling is requested. The normal `_make_text_overlay_image()` path does not dispatch advanced styles to that helper, so the existing advanced style controls are not reliably rendered.
- Shadow blur is not yet represented in the operation schema, project validation, Studio controls or renderer.
- Added regression coverage first in `video-editor/tests/test_project_tool_extensions.py`: shadow-blur schema/persistence/bounds and advanced-renderer routing. Test-first commit: `cd649ad1da4d6b626ef5d8fa952b2d0b6d2bf80f`.
- Fresh execution was not verified. The connected GitHub tool returned no commit status checks, and this environment cannot clone the public repository because outbound DNS/network access is unavailable. No test pass or failure is claimed.
- Next action: obtain observable test execution, then fix renderer routing/recursion and implement bounded shadow blur through the existing ASS/libass path. Keep the existing operation and project model; do not create a duplicate text-edit operation.