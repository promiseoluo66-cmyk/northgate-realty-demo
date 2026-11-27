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
| 2.3 | `transcript_driven_editing` | Select inclusive timed word ranges on a chosen source clip; preview exact source/timeline range; apply by explicit confirmation through an atomic split+ripple-delete transaction with undo/redo. Refuse keyframes, linked groups, transitions, locked tracks and ambiguous overlap. Current scope: one selected clip and its track; no automatic multi-track A/V sync yet. | In progress |
| 2.4 | `transcript_driven_editing` | Combine transcript timing with measured silence candidates; never label technical silence as a filler word; show before/after timing in a reviewable cut list. | Planned |
| 2.5 | `auto_captions` | Evaluate local/free speech-to-text runtimes, licences, model size/download, runner/mobile fit, compute and retention. Enable only after a genuinely $0 route passes real-footage timing tests; otherwise remain visibly gated. | Gated pending evidence |
| 2.6 | `text_style` | Add validated typography, background, shadow and spacing settings; render generated frame fixtures for every supported control. | Planned |
| 2.7 | `text_animation`, `caption_animations`, `karaoke_lyrics` | Add entrance/exit/loop and word-highlight animation through the canonical timing model; render boundary frames and verify timing. | Planned |
| 2.8 | `title_templates` | Save/load editable title recipes with schema version and compatibility checks; never flatten templates into video. | Planned |
| 2.9 | `stickers_graphics` | Build editable shapes, arrows, frames and imported image overlays; validate dimensions and retain asset provenance/licence. | Planned |
| 2.10 | `ai_stickers` | Research only after model licence, zero-cost quota, privacy and runtime are verified. | Gated pending evidence |
| 2.11 | `bilingual_captions` | Support two manually supplied language tracks first; translation remains disabled until a free/licensed route is verified. | Planned / provider gated |
| 2.12 | `tts_dubbing` | Evaluate only free, licensed local voice routes; keep disabled until voice rights, language coverage and output quality pass. | Gated pending evidence |
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
