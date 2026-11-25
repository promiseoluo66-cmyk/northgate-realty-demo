# Professional Feature Roadmap and Free-Plan Guardrails

**Date checked:** 20 November 2026  
**Project:** Independent AI Video Editor  
**Applies to:** `mlt-integration` planning and the later production build  
**Budget rule:** $0 only. Do not enable paid billing, buy credits, or silently fall back to paid services.

## 1. Product target

Build a broad, mobile-friendly professional video editor with an AI assistant that can use the same editing tools as a human using the Studio. We will study the features and workflows available in CapCut, including its Pro-category capabilities, then independently implement comparable results with reusable libraries, models and our own code.

We reuse technology whose licence permits our intended use. We do not copy CapCut source code, private APIs, proprietary binaries, premium templates, stock assets, music, fonts or other protected content.

The product target is broad. The first release is deliberately selective so that the free infrastructure does not become overloaded.

## 2. Main capability catalogue

This is the full product scope to research and build in modules. A capability is not advertised as available until its implementation, licence and tests are complete. The detailed CapCut-style feature inventory and machine-readable planning catalogue are maintained in [CAPCUT_PARITY_FEATURE_CATALOGUE.md](CAPCUT_PARITY_FEATURE_CATALOGUE.md) and [CAPCUT_PARITY_CAPABILITIES.json](CAPCUT_PARITY_CAPABILITIES.json).

### A. Editing foundation — first priority
- Import and inspect video, audio and images; show duration, dimensions, frame rate and audio streams.
- Save/reopen projects without losing edits.
- Multiple video, overlay and audio tracks.
- Trim, split, move, reorder, duplicate, delete, ripple operations and timeline gaps.
- Crop, resize, rotate, position, scale, opacity, aspect-ratio presets and picture-in-picture.
- Basic speed changes, then speed ramps.
- Undo/redo and non-destructive edits.
- Preview and export profiles with accurate progress and error reporting.

### B. Professional visual editing
- Dissolves, fades, wipes and dip-to-colour transitions.
- Keyframes, easing and animated zoom, pan, position, scale, rotation and opacity.
- Brightness, contrast, saturation, colour correction, grading, blur, sharpen, vignette and selected effects.
- Green-screen/chroma key, masks, overlays, blend modes and compositing.
- Stabilisation and advanced motion effects after their modules and licences are checked.

### C. Text, captions and graphics
- Text layers, titles, lower thirds, font styling, outlines, backgrounds and animations.
- Manual captions and subtitle-file import/export.
- Automatic speech transcription and word-level caption timing as an optional processing module.
- Reusable title styles, graphics and templates created by us or licensed for redistribution.

### D. Audio production
- Multiple music, voice and sound-effect tracks.
- Volume/gain, fades, mute/solo, pan and keyframed volume.
- Mixing and synchronization.
- Noise reduction, voice enhancement, speech/music separation and loudness normalisation as optional modules.
- Voice-over, text-to-speech and dubbing only after model/provider and usage costs are verified.

### E. AI-assisted and Pro-category workflows
- Natural-language editing with inspect → plan → validate → apply → render → inspect.
- Auto captions, silence removal, scene detection, beat markers and suggested cuts.
- Background removal, object/face tracking, motion tracking and automatic reframing.
- Subject-aware masks, smart crop, image/video generation, generative expand and upscaling.
- AI-assisted colour, audio cleanup, title suggestions and reusable editing skills.

### F. Product and workflow features
- A mobile-friendly media bin, preview, multi-track timeline and property panels.
- Proxy/low-resolution preview files for slower phones and lower-cost rendering.
- Project history, autosave, export queue, job status and safe retry.
- Optional batch operations and reusable user presets.
- Asset packs with explicit licences and a clear feature-availability screen.

## 3. Release tiers: what we build first

### Tier 1 — Core editor (always the first target)
Prioritise features that can run on ordinary CPU resources and use existing engine modules: project/media inspection, timeline editing, multiple tracks, trim/split, crop/resize/rotate, basic keyframes, common transitions, basic effects, titles/subtitles, audio mixing, undo/redo and standard export.

This tier should provide a genuinely useful editor even when all optional AI services are switched off.

### Tier 2 — Optional CPU-heavy tools
Add one at a time behind explicit actions and runtime checks: transcription, silence/scene detection, stabilisation, denoising and selected tracking. Use short samples or capped durations for previews. Run a full job only when a user requests it.

### Tier 3 — Heavy AI / GPU-dependent tools
Background segmentation, advanced tracking, speech separation, generative video/image, high-end upscaling and similar workloads are separate modules. They stay disabled until a genuinely $0, licence-compatible execution route and realistic limits have been verified. Never assume a free API has unlimited credits or GPU time.

### Tier 4 — Content library
Templates, music, stickers, fonts, transitions and stock media are separate downloadable packs. Only our own or explicitly redistributable material is allowed. Packs are loaded when selected rather than bundling a huge library into the editor.

## 4. Free-plan protection rules

1. **Separate the control plane from rendering.** Cloudflare Worker handles the web app/API, authentication, job creation and status only. Never render video, load large AI models or process full media inside a Worker request.
2. **Keep D1 small.** Store project metadata, job state, skill definitions and references. Store video binaries, proxy files and exports outside D1.
3. **Render only on demand.** No always-running workers, polling loops or background GPU jobs. A submitted job enters a queue and runs only when a suitable free execution slot is available.
4. **Start with one active render.** Queue other jobs. Raise concurrency only after real duration, memory and free-quota measurements show that it is safe.
5. **Keep current input/render caps.** The current upload maximum is 50 MB; the isolated MLT adapter has a 30-minute project-duration and 250-clip guard. Do not raise these simply because a larger feature is requested. Benchmark first.
6. **Use preview modes.** Generate small/short previews and lower-resolution proxies before full exports where that saves CPU time. Do not create proxies unless requested or clearly useful.
7. **Load capabilities on demand.** Keep core MLT/FFmpeg modules small. Do not install or load every optional AI model/plugin for every job. Heavy modules are separate, lazy-loaded adapters with explicit health/licence checks.
8. **Make AI resource-aware.** The planner labels operations light, medium or heavy, checks file duration/resolution and available quota, and asks before a heavy job. If unavailable, explain the limit and offer a lighter/manual route.
9. **Budget Actions carefully.** On GitHub Free, the current included Actions compute is $12/month of usage value; for a standard Linux 2-core runner at $0.006/minute this is equivalent to about 2,000 minutes. Artifact storage is 500 MB shared with GitHub Packages. When included usage is exhausted and there is no valid payment method, GitHub blocks more usage rather than providing unlimited free execution. Use path-filtered CI, concurrency cancellation, short jobs and generated tiny test media. Do not treat GitHub Actions as unlimited production video hosting.
10. **Protect Cloudflare limits.** Workers Free currently allows 100,000 requests/day but only 10 ms CPU per HTTP request and 128 MB memory. It is an orchestration layer, not a video renderer.
11. **Protect D1 limits.** D1 Free currently allows 500 MB per database and 5 GB total account storage, with 50 queries per Worker invocation. Metadata only; batch and index database operations.
12. **No automatic paid fallback.** If a free quota, provider key, model or runtime is unavailable, pause or reject the job clearly. Never activate billing, purchase credits or silently switch to a paid API.

## 5. How the modules fit together

- **Studio:** mobile-friendly controls and preview.
- **Canonical project model:** one versioned source of truth for human and AI edits.
- **AI planner:** translates natural language into proposed registered tool calls.
- **Tool registry/executor:** validates arguments, permissions and project revisions.
- **Capability manifest:** reports which editing operations are available in the current runtime, their licences, dependencies and resource tier.
- **Engine adapters:** MLT for multi-track timeline/compositing where compatible; FFmpeg for probing, encoding and supported media operations; specialist adapters for optional AI tasks.
- **Job queue/resource governor:** one active render at first, queue, duration/file caps, timeout, cancellation, quota accounting and cleanup.
- **Storage:** metadata in D1; large media outside D1, with a production storage choice only after its free limits and retention rules are verified.

The AI cannot run arbitrary shell commands or install modules. It can only request a registered capability that the manifest says is available.

## 6. Implementation order after the Stage 4 engine milestone

Stage 4's isolated MLT rendering-engine milestone passed its full generated-media
CI suite on 22 November 2026:
[run 45031921304](https://github.com/promiseoluo66-cmyk/sparkle-clean-co/actions/runs/45031921304).

The verified engine subset includes:
- Multitrack video/overlay compositing, still-image overlays and transparent
  text/title/caption overlays.
- Dissolve and horizontal luma-map wipes in both directions with softness.
- Static transforms and rendered position, scale, rotation and opacity
  keyframes using linear, hold, ease-in/out and cubic Bezier interpolation.
- Constant playback speed and keyframed video speed ramps.
- Audio mixing, gain, fades and clip-level volume keyframes.
- Basic brightness, chroma-key, contrast and saturation effects.

Stage 4 is complete at the **isolated rendering-engine prototype** scope only.
Known combinations and advanced features remain disabled and are rejected
rather than silently ignored. In particular, speed ramps cannot yet be combined
with animated visual transforms or clip effects; audio volume keyframes cannot
yet be combined with speed ramps; and fade-to-colour, dip-to-colour, advanced
masks, stabilization, tracking and denoise remain future work.

Stage 5 repository integration is now implemented on `mlt-integration`:
the authenticated Worker endpoints, D1 project/revision/undo-redo fields, Studio
follow-up edit and approval controls, Gemini tool planner/executor path and MLT
render runner are connected in code. The 23 registered operations remain the
actual AI capability boundary; roadmap features without implementations are
not exposed as tools. New runner/Worker/history tests are now part of CI.

**Stage 5 acceptance is not yet complete:** the updated GitHub Actions suite must
pass, then the Cloudflare Worker must be deployed from this branch with D1
migration 0002 applied, and a real Gemini-to-MLT job must succeed using the
user's configured secrets. Offline tests cannot prove account-backed execution.

Next stages:

1. **Stage 5 acceptance:** pass the integrated test suite, deploy the Worker
   from `mlt-integration`, apply migration 0002 and verify an actual AI edit,
   approval pause, saved-project reload and MLT export.
2. **Stage 6 — Studio:** build the mobile media bin, preview, multitrack
   timeline, property panels and touch-friendly keyframe/speed graph editor.
   The graph must support draggable points, zoom in/out, pan, fit and reset.
3. **Stage 7 — Cloud/API hardening:** multi-file media ownership, quota
   accounting, retries, cancellation, release cleanup and retention controls.
4. **Stage 8 — Full validation:** Android/mobile usability, saved-project
   round trips, tool combinations, export correctness, failure/retry behaviour,
   Python compatibility and measured free-quota use.

Do not merge the MLT branch into the live Worker or replace the current renderer
until Python-version compatibility, required modules, licensing, large-file
behaviour and full regression tests have passed. Keep the separate YouTube
automation repository untouched.

## 7. Official free-plan checks (20 November 2026)

- GitHub Actions billing and included usage: https://docs.github.com/en/billing/concepts/product-billing/github-actions
  - GitHub Free: $12/month included compute usage; this is usage-value, not an unlimited number of render jobs.
  - Standard Linux 2-core runner: $0.006/minute, so $12 is approximately 2,000 minutes.
  - Artifact storage: 500 MB, shared with GitHub Packages.
  - GitHub says usage beyond the included amount is blocked when there is no valid payment method.
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
  - Workers Free: 100,000 requests/day, 10 ms CPU per HTTP request and 128 MB memory.
  - Free-zone incoming request body limit: 100 MB. The editor's own 50 MB cap remains lower.
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
  - Free database size: 500 MB per database; 5 GB maximum total account storage; 50 queries per Worker invocation.

These are provider account limits, not a promise that a video render will fit. Real render capacity must be measured in the isolated test workflow. Re-check official limits before any public launch because providers can change plans.

## 8. Definition of a safe feature release

A feature can be called ready only when:
- its library/model and dependencies have a recorded licence review;
- its runtime requirement and resource tier are documented;
- the user-facing operation is available only when the capability check passes;
- valid and invalid input tests pass;
- a generated-media end-to-end test proves the actual result;
- the job respects file/duration/time/concurrency limits;
- failure, cancellation and cleanup are handled;
- no paid service or hidden billing fallback is required.

**Product promise:** a wide professional toolset, released progressively and responsibly—not every heavy AI capability running at once, and not an unlimited free cloud-rendering promise.
