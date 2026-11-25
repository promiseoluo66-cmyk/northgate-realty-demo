# Four-repository capability integration plan

Status: active engineering plan. This document records ideas to implement in the existing editor; it does not claim that unimplemented capabilities are available.

## Non-negotiable architecture

- Visual-intelligence agent: Gemini until a replacement passes real-video tests. It observes the source and reports scenes, objects, movement, audio context where supported, and edit opportunities.
- Editing-reasoning agent: DeepSeek via the configured router. It reconciles the visual analysis with the user's request and the registered tool catalogue, then emits a validated edit plan.
- Execution engine: only registered, schema-validated tools with real handlers. Mutations are atomic, revision-aware and undoable. Destructive operations require approval.
- Verification: technical measurements and semantic review are reported separately. A successful render or tool call is not proof of visual quality.
- Human review remains available; never silently publish or send output.

## Repository findings and adaptation policy

### OpenKatana (MIT)
Study/adapt ideas: broad tool discovery, effect preview before application, effect families (distortion, light, blur, time, stylize), beat/energy analysis, reference analysis and comparison, shot sheets, identity/reference binding.
Implementation policy: independently implement against our project model and MLT/FFmpeg adapter. Do not expose an effect until a renderer handler and tests exist.

### Showhow (MIT)
Study/adapt ideas: word-level speech alignment, cue-driven animation, caption block limits, scene-boundary checks, pacing checks, freeze/hold detection, render review reports.
Implementation policy: speech recognition/alignment is a separately gated capability. Do not claim word timing from plain caption text.

### SynthCut (GPL-3.0)
Study/adapt ideas only unless the whole distributed derivative is intentionally relicensed and all obligations are accepted: AI-native editing surface, multi-track timeline, subject-aware reframing, stabilization, transcript editing, grading, proxy/cache and job progress.
Implementation policy: do not copy source code or GPL-only components into this repository. Reimplement independent interfaces/algorithms or choose compatible alternatives. Keep licensing review before any source reuse.

### Kinocut (Apache-2.0)
Study/adapt ideas: typed operation contracts, safe preflight, black/silence/loudness checks, technical evidence, fail-closed release gates, hashes and video receipts, resumable workflows.
Implementation policy: use our own contracts and implementation; preserve Apache notices if any source is ever reused.

## Capability roadmap

| Workstream | Target capabilities | Acceptance evidence |
|---|---|---|
| A. Tool foundation | discovery/catalogue, duplicate/move/ripple operations, track/text/effect controls, strict schemas | registry and executor tests; invalid calls rejected |
| B. Media intelligence | probe streams, shot/scene candidates, representative frame sheets, motion/energy signals, audio stream/silence/loudness analysis, waveform/beat | bounded deterministic outputs with timestamps and tests |
| C. Captions and transcript | speech-to-text adapter, word timestamps, transcript search/edit, caption styling and safe line wrapping | timing fixture tests and rendered caption proof |
| D. Framing and motion | crop/reframe, subject tracking, stabilization, keyframes, speed ramps | renderer-specific tests and preview comparisons |
| E. Effects and colour | effect families, colour controls/LUT support, effect preview and reference matching | each effect has a verified renderer path and golden render |
| F. Quality and provenance | black/freeze/silence/loudness checks, technical-vs-semantic statuses, render receipts, source/output hashes, release gate | fixture-based QC tests; no false PASS when not evaluated |
| G. AI collaboration | shared tool catalogue, visual analysis contract, DeepSeek plan reconciliation, execution feedback loop, review checkpoints | mocked collaboration tests plus real provider tests |

## Implementation order

1. Keep the five already-added editing operations on the feature branch and test them. (Implemented.) (Implemented on the feature branch; draft PR #2.)
2. Add measured media-quality inspection and a truthful report contract. (Implemented: `quality.inspect_media`.)
3. Add scene-change candidate analysis with timestamps. (Implemented: `media.detect_scenes`; semantic scene labels remain not evaluated.)
4. Add bounded audio stream, silence and loudness inspection. (Implemented: `audio.analyze_media`; speech, music and beat recognition remain not evaluated.)
5. Add word-timed caption clip generation from supplied transcript timestamps. (Implemented: `captions.add_word_timed`; automatic speech recognition is not included.)
6. Add post-render quality gates and receipts. (Implemented in the render runner: FFprobe validation, black/freeze/silence review flags, SHA-256, and explicit semantic-not-evaluated fields. This is a technical receipt, not an artistic approval gate.)
7. Add automatic speech recognition/transcription and editable word-aligned captions.
8. Add manual crop rectangles, subject-aware aspect-ratio reframing and stabilization only after source geometry and renderer behavior are proven with real-video fixtures. Basic fit/fill/stretch framing is implemented through the existing LGPL MLT affine filter and receives a generated-video render/pixel check in CI.
9. Add waveform/beat analysis, shot/reference analysis, richer effects and colour tools.
10. Freeze the shared tool catalogue and complete dual-core orchestration only after the underlying operations are proven.

Additional tested timeline operations: `timeline.ripple_delete_clip` (33rd registered operation) and `clip.set_framing` (34th registered operation). CI run 45232497850 passed, including both ripple-delete tests and the full existing editor test workflow.

## Current baseline

The stable `mlt-integration` branch has 23 registered tools. Draft PR #2 adds five editing operations; this dependent branch adds `quality.inspect_media`, `media.detect_scenes`, `audio.analyze_media` and `captions.add_word_timed`, for 33 registered operations on the combined feature branch. The additional `timeline.ripple_delete_clip` operation deletes a clip and shifts later non-overlapping clips on that same track left to close the gap; overlapping cases fail closed, and destructive execution requires explicit confirmation. New media-analysis and render-receipt tests use mocked FFprobe/FFmpeg output; caption tool tests verify timeline clip creation and word timestamps. The render receipt validates stream metadata, hashes the output and reports black/freeze/silence candidates as review flags; it does not make semantic or artistic judgments. Real-media integration and actual subtitle-render fixture verification are still required. They are not deployed or merged into `mlt-integration`.

## CapCut-style editing coverage

The current engine already exposes core timeline editing, split/trim/move/duplicate, multitrack audio/video/text, text styling, speed, transform/keyframes, basic effects, dissolve/wipe transitions, gain/fades and MP4 export. These are independently implemented operations, not a connection to CapCut or its proprietary effect library. Additional CapCut-inspired work remains: manual crop rectangles and subject-aware aspect-ratio reframing, motion tracking, masks/blend modes, richer transition/effect families, colour wheels/LUTs, automatic captions and word-level transcript editing, beat sync, and more export controls. Basic fit/fill/stretch framing is implemented separately through `clip.set_framing`. Each will be added only after its project-model and renderer path are verified.

## Explicit non-goals

- No placeholder tool names without executable handlers.
- No unbounded shell or arbitrary-code tool for either model.
- No automatic outreach, publishing or distribution.
- No change to the Gemini/DeepSeek division of responsibility while visual-provider experiments are underway.
- No paid API or model dependency assumed; optional provider-dependent features must disclose cost and limits.
