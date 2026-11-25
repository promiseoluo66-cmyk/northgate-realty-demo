# Master Capability Audit — Independent AI Video Editor

**Audit date:** 23 November 2026  
**Repository:** `promiseoluo66-cmyk/northgate-realty-demo`  
**Audit branch:** `video-editor-lab`  
**Base branch:** `video-editor-lab`  
**Base commit:** `3eb65ef23791bd9cd12dce29b050b103948d048c`  
**Scope:** Current implementation, public CapCut feature families, and four named open-source reference repositories.  
**Cost policy:** $0-only; no paid billing, hidden paid fallback, or unapproved model/download route.

## 1. Executive result

The audit retains the original 112-entry CapCut-style feature catalogue and adds six capabilities that were made clear by the reference projects but were not explicitly represented in the original catalogue:

1. Transcript-driven editing.
2. Audio-based clip synchronisation.
3. Technical media-quality inspection.
4. Visual review evidence (frames, contact sheets and playable review segments).
5. Reference matching and comparison.
6. Workflow receipts, quality gates and review checkpoints.

The combined master catalogue therefore contains **118 capability entries**. It is a product scope, not a count of AI tools.

| Coverage state | Entries | Meaning |
|---|---:|---|
| Prototype-verified | 12 | A limited subset has passed a relevant generated-media/render or integration test |
| Partially implemented | 25 | A real operation exists, but the wider capability is incomplete |
| Under test | 1 | Offline integration exists; live provider/account-backed acceptance is outstanding |
| Planned | 49 | No usable implementation is currently verified |
| Gated optional | 31 | Depends on optional models, external services, licences or compute and stays disabled until a free, approved route is verified |
| **Total** | **118** | |

**How to read the counts:** 12 entries have a verified limited prototype. Another 25 have working partial coverage. The 49 planned and 31 gated entries do not currently have a verified usable implementation. The one under-test entry still needs its live acceptance gate. None of these numbers means the corresponding feature is already exposed as a finished Studio control.

The machine-readable source of truth for these entries and states is [CAPCUT_PARITY_CAPABILITIES.json](CAPCUT_PARITY_CAPABILITIES.json). Feature IDs are unique; the audit found **zero duplicate feature IDs**.

## 2. Current stable implementation

Stable branch at audit start: `video-editor-lab`, commit `3eb65ef23791bd9cd12dce29b050b103948d048c`.

### 34 unique registered editor tools

The stable registry now contains 34 unique tool names. The original 23 remain; 11 additions were merged without adding duplicate names.

| Area | Registered tools |
|---|---|
| Project/media/analysis | `project.inspect`, `media.list`, `project.set_profile`, `quality.inspect_media`, `audio.analyze_media`, `media.detect_scenes` |
| Timeline/tracks | `timeline.add_track`, `timeline.remove_track`, `timeline.add_clip`, `timeline.add_text_clip`, `timeline.move_clip`, `timeline.duplicate_clip`, `timeline.trim_clip`, `timeline.split_clip`, `timeline.delete_clip`, `timeline.ripple_delete_clip`, `track.set_state`, `track.rename`, `track.set_locked` |
| Text/captions | `text.update_clip`, `captions.add_word_timed` |
| Clip motion/framing | `clip.set_speed`, `clip.set_transform`, `clip.set_framing`, `animation.set_keyframe` |
| Effects/transitions | `effect.add`, `effect.remove`, `effect.set_enabled`, `timeline.add_transition` |
| Audio/history/export | `audio.set_gain`, `audio.set_fade`, `history.undo`, `history.redo`, `render.export` |

The 11 tools added to the original 23 are:

- `timeline.duplicate_clip`
- `track.rename`
- `track.set_locked`
- `effect.set_enabled`
- `text.update_clip`
- `quality.inspect_media`
- `media.detect_scenes`
- `audio.analyze_media`
- `captions.add_word_timed`
- `timeline.ripple_delete_clip`
- `clip.set_framing`

The complete contracts are in [tool_registry.py](../tool_registry.py), with execution in [project_tool_executor.py](../project_tool_executor.py). These are backend/AI tool operations; the registry count must not be mistaken for the number of visible buttons or fully built Studio controls.

### Post-merge CI evidence

Both workflows ran successfully on the merged stable commit:

- [MLT adapter integration — run 45264154509](historical source-snapshot run (not a lab CI result)) — success. The job checked the canonical MLT project render, D1 migrations against SQLite, compiler/safety tests, AI tool execution, Worker API/authentication, generated test video renders, fit/fill/stretch output pixels, keyframes, constant speed, speed-curve source-time remapping, audio volume keyframes, contrast/saturation pixels, still-image overlays and transparent text.
- [Editor tool expansion tests — run 45264154652](historical source-snapshot run (not a lab CI result)) — success. The job ran runner-helper tests, tool contract tests, new tool execution tests and measured-media inspection tests.
- [Capability audit validation — run 45267196772](historical source-snapshot run (not a lab CI result)) — success on the audit branch. It validated the 118-entry catalogue, unique feature IDs, status totals and the registered tool count against the real registry.

**Important test boundary:** several new technical-analysis tests use mocked FFprobe/FFmpeg process output to verify parsing, validation and safe behavior. That is useful unit-test evidence, but it is not a broad real-world media benchmark. Scene detection returns candidates, not semantic shot labels. Audio analysis measures signal properties, not speech meaning or beats. Quality inspection does not decide whether footage visually matches a narration.

### What the new tools do — and do not do

| Tool | Verified scope | Not included |
|---|---|---|
| `quality.inspect_media` | Stream/format metadata, black intervals and silence intervals | Artistic or semantic visual approval |
| `audio.analyze_media` | Audio-stream metadata, silence and loudness measurements | ASR, beat grid, music recognition or emotion |
| `media.detect_scenes` | FFmpeg scene-change candidate timestamps | Semantic shot labels or guaranteed editorial cuts |
| `captions.add_word_timed` | Creates sequential caption clips from supplied word text and start/end timestamps | Speech recognition or automatic timestamp generation |
| `timeline.ripple_delete_clip` | Deletes one clip and shifts later clips on the same track; rejects unsafe overlaps | Cross-track ripple editing, ripple insert/overwrite, snapping or markers |
| `clip.set_framing` | Source-aware fit, fill and stretch with alignment for video/image clips | Manual crop rectangle, subject tracking or smart auto-reframe |

Other existing limits remain: effects are allowlisted and basic; only dissolve and horizontal wipe transitions are supported; the visible Studio does not yet contain a complete multi-track touch timeline, media bin, preview/property panels or graph editor.

## Stage 1 registry extension

The 34-tool figure above records the audited Stable baseline. The Stage 1 Studio implementation in this branch extends it to 42 unique registered operations, adding track reorder, keyframe removal/clearing, media organization, crop, media replacement, slip editing and ripple insert. The 118 catalogue entries remain product capabilities, not a claim of 118 registered tools.

## 3. Capability areas with the largest gaps

The complete per-feature status is in the JSON catalogue. These are the most important implementation gaps found in the code and references:

| Priority | Capability area | Current position | Next proof required |
|---|---|---|---|
| P0 | Full Studio workflow | A mobile upload/AI-instruction/job page exists; a complete interactive multitrack editor is missing | Touch timeline, media bin, preview, clip/track properties, history and save/reopen on Android |
| P0 | Speech recognition and transcript editing | Timed captions accept supplied timestamps; no integrated ASR/transcript editor | Local or explicitly approved free ASR adapter, word timing accuracy, transcript search/edit and render tests |
| P0 | Cropping and intelligent framing | Fit/fill/stretch exist; manual crop, subject tracking and auto-reframe do not | Normalised crop geometry, timestamped subject tracks, smoothing and actual rendered-motion fixtures |
| P1 | Visual inspection and reference review | Technical probing and scene candidates exist; visual evidence/review comparison is missing | Frame/contact sheets, sampled video review, source-to-output comparison and recorded human/model decisions |
| P1 | Quality receipts and render loop | Technical checks and job metadata exist; complete provenance/review/retry loop is incomplete | Immutable input/output hashes, detailed quality receipt, review checkpoint and bounded retry/re-render tests |
| P1 | Stabilisation, masks and blend modes | Not implemented as complete user-facing operations | Licence-reviewed backend, typed schemas, safe parameters and real output-frame tests |
| P1 | Colour grading and LUTs | Basic brightness/contrast/saturation only | White balance, HSL, curves, wheels, LUT parser and reference colour tests |
| P1 | Audio intelligence | Gain/fades/volume keyframes and signal measurements exist | Word-level ASR, waveform, beat detection, audio sync, ducking and transcript-aware cuts |
| P1 | Rich effects/transitions | Small allowlisted effect set and two transitions | Effect/transition catalogue with per-filter dependency/licence checks and render fixtures |
| P2 | Media intelligence | Project media listing and technical detection exist | Transcript/visual indexing, semantic search, thumbnails, proxy generation and missing-media recovery |
| P2 | Export controls/interchange | MP4 path and project profile exist | Codec/bitrate/audio controls, SRT/VTT import/export, platform presets and optional OTIO |
| P2 | Dual-AI live acceptance | Offline structured planning/execution path exists | Verify Gemini visual analysis and DeepSeek edit reasoning separately, then test the full approved tool-to-render loop |

The next build phase should not start by adding many effect names to the registry. The biggest system-level blocker is the lack of a complete Studio editing surface and end-to-end validation of the live AI-to-render workflow.

## 4. Reference repository comparison

The reference repositories were checked against their current public default branches and documentation on 23 November 2026. Their tool counts are not directly comparable: some expose each operation as a separate MCP tool, while others use family dispatch or combine many operations behind one tool.

| Reference | Current public licence | Documented tool surface | Most useful capability patterns | Reuse boundary |
|---|---|---:|---|---|
| [OpenKatana](https://github.com/rk0neki/OpenKatana) | Apache-2.0 (GitHub repository metadata) | 75 shared CLI/MCP operations in its tool guide | Contact sheets, footage inspection, beat/music analysis, speech transcription, caption assembly, reference plans, motion review/revision, mattes/tracking, effect packs, advanced typography, 3D/HDR workflows | Apache-2.0 permits reuse subject to its notice/conditions; audit each bundled model, font, module and dependency separately |
| [Showhow](https://github.com/sirioberati/showhow) | MIT | 10 named MCP operations in its README | Word/character voice timing, cues tied to spoken words, deterministic frame rendering, plan checks, render checks, motion/cut/freeze/loudness quality tests | MIT permits reuse subject to its notice/conditions; its example voice route uses ElevenLabs and must not become a hidden paid dependency |
| [SynthCut](https://github.com/Relo-video/SynthCut) | GPL-3.0 | 94 entries in its current full tool-list file; README also contains an older 85-tool statement | Transcript-indexed editing, semantic visual search, crop, subject-aware reframe, stabilization, colour wheels/curves/LUTs, effects stack, adjustment layers, text motion graphics, background jobs, proxy/cache and export presets | Do not copy its implementation into this project unless a deliberate GPL-3.0 compatibility decision is made; use public behaviour as a reference or design an independent implementation |
| [Kinocut](https://github.com/KyaniteLabs/kinocut) | Apache-2.0 | Current docs describe 206 full MCP tools, with 18 listed by default through family dispatch | Typed FFmpeg operations, preflight/doctor, quality gates, receipts/provenance, resumable workflows, guarded overwrite, review/approval checkpoints, media ingest and audio/shorts workflows | Apache-2.0 permits reuse subject to its notice/conditions; inspect operation dependencies and keep all optional model/provider routes off until cost/licence approval |

### What the comparison changes in our plan

- **OpenKatana** adds a strong reference-review workflow: inspect frames before choosing shots, compare a render with a reference, review mattes and use measured motion/shot sheets. This is not currently covered by our 34 registered operations.
- **Showhow** demonstrates that caption timing should be tied to verified speech timing and that a failed render check must remain a failure, not be silently skipped. Our word-timed caption tool receives timestamps; it does not produce them.
- **SynthCut** highlights the value of transcript-driven editing, semantic media search, manual crop, subject-aware auto-reframe, stabilization, proxies and background render jobs. Its GPL-3.0 licence prevents casual code incorporation.
- **Kinocut** provides patterns for strict tool schemas, preflight checks, non-overwrite defaults, provenance receipts, review gates and resumable jobs. Its 206-tool count is a catalogue/dispatch design, not a target we should copy.
- We should reuse only code whose exact licence and third-party dependencies are compatible with this project's distribution model. A permissive top-level repository licence does not automatically relicense every model, font, codec, effect module or bundled asset.

## 5. CapCut public feature benchmark

This audit uses CapCut's public feature descriptions as a functional benchmark, not as permission to copy CapCut code, assets, binaries, private APIs, models, templates, fonts, music or stickers.

Official public references consulted:

- [How to use CapCut](https://www.capcut.com/resource/how-to-use-capcut) describes advanced editing concepts including keyframes, masks, transform, blend modes, adjustment controls, colour curves and speed curves. It also identifies platform/account-dependent advanced tools such as camera tracking and auto-reframe.
- [CapCut Creative Suite](https://www.capcut.com/creative-suite) lists auto captions, music/sound effects, multitrack editing, crop/trim/resize, background removal and cloud/team collaboration.
- [CapCut video tools](https://www.capcut.com/tools) lists public video, audio, text and AI tool families; individual tools and entitlements may vary over time and by account/region.

CapCut's own documentation says some advanced tools are Pro/platform dependent. We should target independent editing outcomes and enforce our own $0 infrastructure limits rather than promise unlimited AI, storage or cloud rendering.

## 6. Licence and dependency policy

- Reuse MIT and Apache-2.0 code only with required copyright/licence notices and an audit of transitive dependencies.
- Do not incorporate SynthCut GPL-3.0 source files into the current codebase without an explicit distribution/licensing decision. Its workflows and public behavior may still inform an independent implementation.
- Review FFmpeg/MLT build options and the licence of each enabled module/codec; do not assume all optional filters carry the same licence.
- Audit model weights separately from wrapper-library licences.
- Keep external provider calls, downloads, paid model APIs and GPU-dependent workflows disabled unless the free route, licence, privacy behavior and usage limits have been verified.
- No repository currently contains copied code as a result of this audit; this phase is research, comparison and status correction only.

## 7. Acceptance rules for future work

A capability may move to **prototype-verified** only when it has:

1. A strict, typed tool schema and a real executor/renderer path.
2. Input validation, path/resource bounds, safe failure handling and confirmation for destructive actions.
3. A generated-media test that proves the actual output where the feature changes pixels, timing or audio.
4. Save/reopen and regression tests where project state is affected.
5. Documented limitations, dependency licences, free-tier/resource assumptions and cost controls.
6. UI exposure when it is presented as a Studio feature; API registration alone is not finished user functionality.

AI analysis claims must be separated from measurements: candidate scene changes are not semantic labels, silence is not filler-word recognition, and a frame preview is not proof that a model or human reviewed the complete video.

## 8. Full remaining-work roadmap

All 118 capability entries are assigned exactly once to these eight stages. Counts are feature families, not new registry tool names. Existing operations must be reused; add a new tool only when the required operation is genuinely absent.

| Stage | Scope | Entries | Catalogue categories |
|---|---|---:|---|
| 1 | Mobile Studio and editing foundation | 25 | Project/timeline 10 + transforms/animation 8 + speed/time 7 |
| 2 | Text, captions and transcript editing | 15 | Text/graphics 6 + captions/localisation 9 |
| 3 | Effects, compositing and colour | 15 | Transitions/effects 9 + colour/image quality 6 |
| 4 | Full audio production | 12 | Audio/voice production 12 |
| 5 | Dual-AI editing, visual understanding and quality review | 14 | AI assistance 10 + quality/review/provenance 4 |
| 6 | Generative AI and photo/thumbnail tools | 15 | Generative AI 8 + photo design 7 |
| 7 | Templates, asset packs and brand resources | 6 | Templates/assets 6 |
| 8 | Export, delivery, projects and collaboration | 16 | Export/delivery 9 + cloud/collaboration 7 |
| **Total** | | **118** | **Every catalogue category included once** |

### Stage 1 — Mobile Studio and editing foundation (25)

**In progress:** [PR #5](https://github.com/promiseoluo66-cmyk/northgate-realty-demo/pull/5) builds the first mobile Studio foundation: scrollable multitrack timeline, zoom, clip selection, read-only inspector, media-bin view and selected-clip context for AI instructions.

Still required:
- Playhead, scrub/seek and frame preview.
- Direct clip move, trim, split, duplicate and delete controls, plus track add/remove/reorder, wired to existing safe executor tools and confirmation checks.
- Transform/framing controls, manual crop, canvas/aspect presets and safe-area guides.
- Touch-friendly keyframe list/graph: add, move and remove points; zoom, pan, fit and reset.
- Editable speed graph, freeze/hold and supported time-remapping controls.
- Full project create/open/save/recover flow, autosave/history UI and multi-file asset intake.

**Exit test:** On a phone, the user can create/open a project, import media, edit clips across tracks, preview frames, save/reopen, undo/redo and render a verified result without needing an AI instruction for every basic edit.

### Stage 2 — Text, captions and transcript editing (15)

- Speech recognition with word/phrase timestamps, transcript retrieval/search and editable word ranges.
- Transcript-based cutting, reviewable filler-word removal and pause tightening.
- Subtitle import/export including SRT/VTT; caption styling, cue placement, bilingual captions and karaoke/word-highlight animation.
- Text/graphic styling: fonts, outlines, shadows, backgrounds, titles, stickers, animated text and reusable title styles.
- TTS and dubbing remain optional until a genuinely free, licensed route is verified.

**Exit test:** A real clip can be transcribed, corrected, edited from selected transcript words, captioned, rendered and checked against spoken audio.

### Stage 3 — Effects, compositing and colour (15)

- Complete effect stacks and parameter editing, not just effect-name registration.
- Shape masks, feathering, animated masks, blend modes, opacity/compositing and full chroma-key controls.
- Expand transitions beyond the tested dissolve and horizontal wipe.
- Stabilisation with motion/edge-crop review and safe failure handling.
- Exposure, temperature/tint, HSL, curves, colour wheels, highlights/shadows, grain, vignette, sharpening and .cube LUT support.
- Effect preview plus rendered-pixel regression fixtures.

**Exit test:** Each effect, transition and grade is verified on generated media and representative clips, with bounded parameters and before/after visual checks.

### Stage 4 — Full audio production (12)

- Waveforms, beat/onset detection, beat grids and beat-aligned edit suggestions.
- Audio synchronisation for separate recordings and camera angles.
- Voiceover import/recording, music/SFX handling, audio offsets, ducking, track solo/pan/automation and mix controls.
- Voice effects, noise reduction, vocal separation and speech cleanup only where free, licence-compatible local routes are available.
- Improve UI and rendered-output tests for existing gain, fade and volume-keyframe tools.

**Exit test:** A multitrack project can synchronise audio, mix dialogue/music/SFX, pass loudness checks and render without clipping or unintended silence.

### Stage 5 — Dual-AI editing, visual understanding and quality review (14)

- Preserve the intended split: Gemini analyses visual content/frames; DeepSeek reasons over findings and produces validated edit plans.
- Visual media indexing/search, semantic shot discovery, scene descriptions and reviewable auto-cut suggestions.
- Subject/face/body/object tracking and smart reframing after the tracking path is proven.
- Frame sampling, contact sheets, shot sheets, reference-video comparison and explicit human/model review evidence.
- Render receipts with input/output hashes, operation history, measured quality findings, review decisions and a bounded retry/re-render loop.
- Keep measurements separate from semantic judgement: silence is not filler-word recognition; scene-change timestamps are not semantic labels; a preview is not proof of full-video review.

**Exit test:** Gemini and DeepSeek pass separate tests and a combined real-footage test; plans validate against the registry, destructive operations require approval and output review is traceable.

### Stage 6 — Generative AI and photo/thumbnail tools (15)

- Text-to-video, image-to-video, image generation/editing, avatars/presenters, style transfer, generative expand/object removal and AI upscaling.
- Photo crop/resize/rotate/flip/colour, background replacement, object cleanup, portrait enhancement and photo restoration.
- Thumbnail/cover/poster canvas and separate image export.

**Cost gate:** Keep features disabled or clearly unavailable until a zero-cost route, provider limits, model licence, compute needs, privacy and output rights are verified. No silent paid fallback, billing activation or automatic model download.

### Stage 7 — Templates, asset packs and brand resources (6)

- Searchable intro/outro/short-form/promo/slideshow templates.
- Editable templates with replaceable media slots and reusable user templates.
- Effect/transition/filter/title/font/stock/music/SFX packs with attribution and redistribution metadata.
- Brand kit for logos, colours and approved fonts.

**Exit test:** Every bundled asset has verified licence/provenance metadata, and templates remain editable rather than being flattened into one video.

### Stage 8 — Export, delivery, projects and collaboration (16)

- Export dimensions, aspect ratio, FPS, codecs, bitrate, quality, audio codec/sample rate/channels and high-resolution output within verified runner limits.
- Render queue progress, safe cancellation, retry and useful error states.
- Burned-in and sidecar captions, project-versus-video packaging, still-frame/audio-only export and platform presets.
- Cloud project/asset storage, quotas, backup/sync, review links/comments, team roles, shared brand assets, version conflict handling and presentation/download links.

**Cost gate:** Cloud collaboration, storage and high-resolution compute must fit verified free limits. No paid hosting, paid storage/CDN, always-on workers or billing-enabled APIs are assumed.

## 9. Build and merge rules for every stage

1. Keep video-editor-lab as the protected stable base and work on separate feature branches.
2. Before adding an operation, compare the need with all 34 existing tool names, schemas, handlers, renderer support and tests. Reuse what already exists; do not add duplicate names.
3. Build a complete vertical slice: schema, executor, renderer/provider, UI, tests and documentation. A registered name alone is not a finished feature.
4. Test real generated-media output for pixel, audio or timing changes. Unit mocks alone are insufficient for production claims.
5. Verify dependency and asset licences. Keep optional/model-dependent routes disabled until free-tier and licence gates pass.
6. Run CI and fix failures before a PR. Merge only after verification; never deploy the Worker automatically.
7. Update the catalogue and status totals after each accepted implementation.

**Current position:** Stage 1 is underway in PR #5. The audit and stage plan are in PR #4. Both are drafts; neither is merged. Stable remains at the audited base commit and no deployment has been performed.
