# Independent Video Editor — CapCut Capability Parity Catalogue

**Benchmark checked:** 23 November 2026  
**Project branch:** \`mlt-integration\`  
**Purpose:** A reusable feature specification for building our own editor with a broad feature set comparable in capability to CapCut.

## 1. What this catalogue means

This is a benchmark of CapCut's publicly documented feature families across its mobile, desktop and web products. It covers the editor, creator tools, AI assistance, image tools, assets, exports and collaboration. It is a product backlog—not a claim that every CapCut feature is available on every device, in every country, or on every account. CapCut changes features and access by platform, region, account, rollout and subscription.

Our goal is **independent functional parity**: users should be able to achieve comparable editing results with our own implementation. This is not a request to extract or reuse CapCut's private source code, APIs, app binaries, model weights, templates, music, fonts, stickers or other protected assets. We will use independently written code and libraries/models whose licences permit our use.

A feature in this catalogue is **not available in our editor merely because it appears here**. It becomes available only after implementation, licensing checks, UI connection and end-to-end tests.

## 2. Current verified starting point

The isolated MLT rendering-engine prototype passed its complete generated-media
CI suite on 22 November 2026:
[run 45031921304](historical source-snapshot CI evidence; not a lab run).

Verified engine capabilities include:
- Multiple visual tracks, gaps, compositing, still-image overlays and dissolves.
- Horizontal luma-map wipes in both directions with softness control.
- Static transforms and animated position, scale, rotation and opacity.
- Linear, hold, ease-in, ease-out, ease-in-out and cubic Bezier transform
  interpolation, with real rendered-frame checks.
- Constant video speed and keyframed variable-speed ramps with source-time
  remapping verified in rendered output.
- Separate audio mixing, gain, fades and clip-level volume keyframes, checked
  using decoded audio samples.
- Basic brightness, chroma-key, contrast and saturation filters, checked using
  decoded pixels.
- Timed text/title/caption overlays with transparent RGBA backgrounds and
  still-image overlays, checked using decoded frames.

The combined master catalogue contains **118 capability entries**. This is a product-scope catalogue, not a count of registered tools. The Stage 1 Studio implementation has 52 unique registered operations, extending the 34-tool Stable baseline.

The combined master catalogue now contains **118 capability entries**:
**12 prototype-verified**, **25 partially implemented**, **1 under test**,
**49 planned**, and **31 gated optional**. It retains 112 CapCut-style entries
and adds six cross-repository capabilities for transcript-driven editing,
audio synchronisation, technical quality inspection, visual review evidence,
reference matching, and workflow receipts. The full per-feature audit is in
[CAPCUT_PARITY_CAPABILITIES.json](CAPCUT_PARITY_CAPABILITIES.json), with the
four-repository comparison in [MASTER_CAPABILITY_AUDIT.md](MASTER_CAPABILITY_AUDIT.md).

"Prototype-verified" means a limited implementation has passed relevant
engine/integration tests; it does not mean the entire feature family is
finished or available in the app. "Partially implemented" means a real
operation exists but the broader workflow remains incomplete.

The interactive keyframe/speed graph UI—including draggable graph points,
zoom in/out, pan, fit and reset—is still planned for the Studio stage. The MLT
engine can render speed curves, but the visual graph editor has not yet been
built.

This code status refers only to the isolated MLT prototype, not a finished
mobile Studio or production rendering service.

## 3. Complete capability backlog

The list below captures the major CapCut-style feature families that our product should target. A particular preset, filter, language, export resolution or AI tool may be platform- or account-dependent in CapCut; we will implement equivalents only where our runtime and licences support them.

### A. Project, media library and timeline
- Create, open, rename, duplicate, save and safely recover projects.
- Autosave, undo/redo, edit history and non-destructive project revisions.
- Import video, audio, still images, graphics and subtitle files.
- Inspect file metadata, thumbnails, duration, frame rate, dimensions, rotation and audio streams.
- Media bin with search, sorting, folders, labels, favourites and missing-media relinking.
- Multi-track video, overlay, image, text, caption, music, voice-over and sound-effect timelines.
- Add, remove, reorder, duplicate, split, trim, slip, move, replace and group clips.
- Insert/overwrite editing, ripple delete, gap closing, snapping, markers and timeline zoom.
- Track lock, hide/show, mute, solo, reorder and track-level controls.
- Detach/extract audio, replace clip audio, capture a still frame and freeze a frame.
- Proxy media and low-resolution previews for weaker devices and lower-cost rendering.

### B. Clip transform, framing and animation
- Position, scale, rotate, flip/mirror, crop, resize, opacity and anchor/pivot controls.
- Picture-in-picture, split-screen, overlay and canvas/background controls.
- Aspect-ratio and canvas presets for portrait, landscape, square and custom dimensions.
- Keyframes for position, scale, rotation, crop, opacity, volume and supported effect properties.
- Easing curves, graph editor, interpolation controls and reusable animation presets.
- Graph viewport controls for keyframe and speed graphs: zoom in, zoom out, pan, fit all keyframes/control points, and reset view; controls must work with touch as well as mouse.
- Animated pan, zoom, rotate, scale, fade, slide and custom motion paths.
- Apply, copy, paste, reset and remove keyframes; show keyframes on the timeline.
- Safe-area guides and reframing guides for common social-media formats.

### C. Speed and time effects
- Constant-speed changes, slow motion, fast motion and reverse playback.
- Speed curves with editable control points and named motion presets.
- A dedicated speed-curve graph with draggable/addable/removable control points, zoom in/out, pan, fit-to-clip and reset-view controls, plus numeric precision editing for exact speed/time values.
- Freeze-frame and hold-frame sections.
- Smooth slow motion using frame blending or optical-flow interpolation where available.
- Time remapping that preserves the relationship between clip timing, keyframes and audio.
- Audio pitch options when changing speed, where technically appropriate.

### D. Transitions, effects and compositing
- Transition library with duration and direction controls.
- Dissolve, fade, wipe, slide, push, split, blur, zoom, mask-based and dip transitions.
- Dip to black, dip to white and dip to a selected colour.
- Video effects, subject/body effects, overlays and effect stacks.
- Per-clip and timeline-level effects with enable/disable, reorder and adjustable parameters.
- Blend modes, transparency, masks and compositing across tracks.
- Shape masks (circle, rectangle and other supported shapes), feathering and mask animation.
- Chroma key / green-screen removal with colour, tolerance, spill and edge controls.
- Automatic subject cutout/background removal as an optional AI module.
- Stabilisation, motion blur, blur, sharpen, glow, vignette and distortion effects where compatible.

### E. Colour, lighting and image quality
- Exposure, brightness, contrast, saturation, temperature, tint and white balance.
- HSL controls, colour curves, colour wheels and selective colour adjustments.
- LUT import/application and reusable colour presets.
- Skin-tone-aware adjustments and selective subject correction where supported.
- Highlights, shadows, blacks, whites, fade, grain, vignette and sharpening.
- Auto enhancement and relighting as optional processing modules.
- Before/after comparison, effect strength controls and non-destructive adjustment stacks.

### F. Text, titles, stickers and graphics
- Text clips, title cards, subtitles, lower thirds, labels and end screens.
- Font, size, weight, alignment, colour, spacing, line height, outline, shadow and background.
- Text position, rotation, scale, opacity and per-word/per-character animation where supported.
- Entrance, exit, loop and text motion presets.
- Editable title templates and reusable brand styles.
- Stickers, emoji, shapes, arrows, frames and graphic overlays.
- Import user images/logos and create reusable overlays.
- AI-generated stickers/graphics only through a separately approved and cost-checked model route.

### G. Captions, transcription and localisation
- Manual subtitle creation and precise caption timing/editing.
- Speech-to-text auto captions with language selection and transcript correction.
- Word-level or phrase-level timing where the transcription engine supports it.
- Bilingual captions and caption translation to a chosen target language.
- Caption styling, templates, keyword highlighting and animated captions.
- Karaoke/lyric-style captions when timing data is available.
- Import/export common subtitle sidecar formats such as SRT; support other formats only after parser tests.
- Export captions separately as subtitle files, as well as burn them into the video.
- Text-to-speech voices and multilingual dubbing as optional modules, with voice/model usage rules checked.

### H. Audio and voice production
- Multiple music, dialogue, narration and sound-effect tracks.
- Import audio, record voice-over, trim/split/position audio and synchronize it to video.
- Clip and track volume, gain, fades, mute/solo, pan and supported volume keyframes.
- Audio waveform display, timeline sync, beat markers and beat-aware editing.
- Music and sound-effect library with per-item licence metadata.
- Voice effects and voice changer presets.
- Noise reduction, voice enhancement, echo/reverb reduction and loudness normalisation.
- Vocal/instrumental separation where a suitable model is available.
- Speech cleanup, filler-word removal and silence detection.
- Text-to-speech and dubbing as optional modules, not assumed free or unlimited.
- Audio-only preview/export and final audio/video mix validation.

### I. AI editing assistants
- Natural-language edit assistant that proposes changes and explains them before applying.
- Auto cut based on music beats, speech pauses or user instructions.
- Silence and filler-word detection with a reviewable cut list.
- Scene/shot detection, shot grouping and suggested edit points.
- Automatic beat detection and beat markers.
- Smart media search by file name, transcript or supported visual metadata.
- Auto reframe for different aspect ratios and subject-aware crop.
- Face, body, hand and object tracking where models can reliably support it.
- Motion tracking for attaching text, stickers or graphics to a moving subject.
- Automatic background removal, stabilisation and relighting.
- AI voice enhancement, vocal isolation and caption generation.
- AI-assisted title, caption, thumbnail and colour suggestions.
- Human review before destructive changes; keep edits reversible.

### J. Generative AI creation
- Script/idea assistance and script-to-video storyboarding.
- Text-to-video and image-to-video generation.
- Start-frame/end-frame guided generation where a model supports it.
- AI image generation and image editing.
- AI presenter/avatar generation, talking-photo or avatar narration where legally and ethically supported.
- Video/image style transfer, animation and cartoon/anime looks.
- Generative expand/outpainting and object removal/inpainting.
- Image and video upscaling/enhancement.
- Scene assets, backgrounds and voice options generated on demand.

**Resource rule:** these tools are separate optional modules. GPU-heavy generation, premium model APIs and paid credits stay disabled unless a genuinely $0 route, usage caps, licence, privacy rules and availability have all been verified. No silent paid fallback.

### K. Photo and thumbnail design tools
- Image crop, resize, rotate, flip, colour and exposure adjustments.
- Image background removal and replacement.
- Object cleanup/removal where an appropriate tool is available.
- Portrait retouching and enhancement with user-controlled intensity.
- Image upscaling, low-light enhancement, restoration and colourisation as optional AI tools.
- Thumbnail, cover, poster and social graphic canvas presets.
- Layered text, shapes, images and brand elements for thumbnail composition.
- Export images separately from video projects.

### L. Templates, stock media and creative assets
- Searchable templates for intros, outros, reels, shorts, promos, slideshows and common formats.
- Editable templates with replaceable media slots and adjustable timing.
- User-created templates that can be saved and reused.
- Effects, transitions, filters, title styles, stickers, fonts, stock footage, music and sound effects.
- Favourites, recently used assets, pack management and preview-before-download.
- Optional brand kit for logos, colours and approved fonts.
- Asset metadata, source attribution and licence/redistribution status.

We must create our own assets or use content whose licence explicitly permits the intended use and redistribution. We must not copy CapCut's premium or community asset library.

### M. Export, delivery and sharing
- Export presets for common social formats and custom output settings.
- User-selectable dimensions/aspect ratio, frame rate, codec, bitrate and quality where supported by the encoder.
- MP4 as the first standard delivery target; add other containers/codecs only after compatibility tests.
- Audio codec, sample rate and channel settings where supported.
- Export progress, estimated size where possible, cancellation, retry and clear error messages.
- Export video with captions burned in or export separate caption files.
- Save/reopen an editable project separately from exporting a flattened video.
- Thumbnail/still-frame export and audio-only export.
- Optional platform-specific presets and direct sharing integrations after authentication/API rules are reviewed.
- Validate the exported file with media probing and sample-frame/audio tests.

High-resolution exports (2K/4K and beyond) are a later capability, gated by source resolution, memory, render capacity and reliable tests. Do not promise 4K/8K just because another editor lists it.

### N. Cloud workspace and collaboration
- Optional account-backed project and asset storage with visible quota.
- Cross-device project sync, backup and restore.
- Share-for-review links, comments and timestamped feedback.
- Team workspaces, invitations, roles and project permissions.
- Shared folders, asset libraries and brand kits.
- Project versions, activity history and conflict-safe editing.
- Presentation/share links and controlled download permissions.

These are later platform features, not part of the current MLT rendering proof. Storage and collaboration must respect the actual free quotas and never store media binaries in D1.

### O. Editing experience and accessibility
- Mobile-first Studio with media bin, preview, timeline and property panels.
- Responsive controls suitable for touch screens as well as larger screens.
- Keyboard shortcuts on supported devices and accessible labels/navigation.
- Preview quality selector, proxy toggle and playback performance controls.
- Clear warnings when a feature is unavailable, too resource-intensive or requires an optional module.
- Recovery after failed render, safe cancellation and cleanup of temporary files.
- Project portability and an understandable capability/status screen.

## 4. Implementation mapping for our architecture

| Feature family | Implementation route | First engineering target |
|---|---|---|
| Project/timeline | Canonical project model + Studio controls | Reliable edit data, clip operations and multi-track timeline |
| Compositing/transitions | MLT adapter where compatible; FFmpeg/specialist filters when suitable | Verified transitions, overlays, masks and transforms |
| Encoding/media inspection | FFmpeg and media probes | Stable MP4 render, metadata checks and controlled export settings |
| Keyframes/speed curves | Canonical animation data + engine adapter | Position/scale/rotation/opacity keyframes and interpolation tests |
| Text/captions | Text renderer + subtitle parser + optional transcription adapter | Manual text/subtitles first; auto captions after model tests |
| Audio | MLT/FFmpeg audio graph or specialist audio adapter | Gain/fades/pan, stream routing and loudness tests |
| CPU AI | Lazy-loaded local or free execution adapters | Scene detection, silence detection and transcription one at a time |
| Heavy AI/generation | Separately gated model/provider adapters | Only after free limits, privacy, licence and real quality are proven |
| Assets/templates | Our own or redistributable packs | Small licensed starter pack and user-created reusable templates |
| Cloud/team features | API, storage and permission layer | Only after storage pricing/quotas and sync conflict behaviour are proven |

MLT is a candidate composition/timeline engine, not the whole product. FFmpeg is used for media inspection, encoding and suitable filters; it is not the user-facing editor. The canonical project model remains the shared source of truth for the human Studio and AI operations. The AI must only use registered, validated operations—not arbitrary shell commands.

## 5. Delivery priorities

- **P0 — Editor foundation:** project persistence, media bin, timeline operations, multiple tracks, trim/split/move, transform controls, preview/export, undo/redo and safe project validation.
- **P1 — Professional editing:** static transforms, keyframes and easing, speed control/curves, common transitions, masks, chroma key, colour controls, titles, captions and audio gain/fades.
- **P2 — Creator workflow:** auto captions, transcription, silence/scene detection, beat detection, tracking, stabilisation, auto reframe, audio cleanup and reusable templates.
- **P3 — AI creation:** image/video generation, avatars, advanced cutout, generative expand, advanced upscaling and style transfer—only when free, licensed, safe execution is proven.
- **P4 — Workspace ecosystem:** project sync, cloud backup, team collaboration, shared asset packs, review links and direct publishing integrations.

The priorities are not a promise to deliver every item in one release. Build and verify each small capability, then connect it to the Studio and AI tool registry.

## 6. Engineering and release rules

1. Do not mark a capability as complete based on a menu, schema, unit test or successful render alone. Its actual output must pass an end-to-end test.
2. Every operation needs validated inputs, a documented runtime/dependency, a licence review, resource tier and clear unavailable/error behaviour.
3. Keyframes and all non-destructive edits must be represented in the canonical project model so they survive save/reopen and can be edited by either the user or AI.
4. Add tests for exact timing/frame boundaries, overlapping layers, audio/video sync, export metadata and decoded pixels/audio.
5. Use generated tiny test media first. Do not ask for the user's large video until mobile data is available and the synthetic tests are stable.
6. Keep the current file/duration/clip and concurrency guards. Raise caps only after benchmark evidence.
7. Use on-demand jobs and lazy-load optional models. Do not run background rendering loops or put media binaries in D1.
8. The free plan must have transparent quotas and a clear pause/reject state. Never activate billing or silently route a job to a paid service.
9. Review third-party software, model and asset licences before redistribution or commercial use. Keep a dependency/licence inventory.
10. Do not merge or deploy the MLT branch as production until runtime compatibility, resource limits, large-file behaviour, licensing and regression tests pass.

## 7. Public CapCut references used for this benchmark

These are official CapCut pages consulted for the feature families above. Their content and feature availability can change:
- [CapCut advanced editing guide: keyframes, masks, transform, blend, adjustment and speed curves](https://www.capcut.com/resource/how-to-use-capcut)
- [CapCut desktop AI editor: script-to-video, auto reframe, auto captions, AI tools and keyframes](https://www.capcut.com/tools/desktop-ai-power)
- [CapCut editing guide: auto cutout, chroma key, text-to-speech, stabilisation, relight, tracking and audio cleanup](https://www.capcut.com/resource/how-to-use-capcut)
- [CapCut captions and translation guide](https://www.capcut.com/resource/how-to-translate-and-edit-video-captions-in-capcut)
- [CapCut audio guide: voiceover, text-to-speech, music and sound effects](https://www.capcut.com/resource/how-to-add-or-replace-voiceovers-music-and-sound-effects-in-capcut)
- [CapCut creative suite: multiple tracks, crop/trim/resize, background removal, image tools and collaboration](https://www.capcut.com/creative-suite)
- [CapCut collaboration and review workflows](https://www.capcut.com/resource/collaborate-on-capcut-online)
- [CapCut export resolution guidance](https://www.capcut.com/help/export-videos-in-capcut)
- [CapCut templates and platform differences](https://www.capcut.com/help/use-and-export-templates-in-capcut)

**Product rule:** we use this catalogue as our independent build checklist. We do not claim CapCut-level parity until the relevant operations are implemented, connected to the Studio, legally cleared and tested.
