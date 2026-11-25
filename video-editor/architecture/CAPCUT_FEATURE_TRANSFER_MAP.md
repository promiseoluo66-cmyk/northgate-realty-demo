# CapCut Feature Transfer Map — Independent AI Video Editor

**Research date:** 22 November 2026  
**Project branch:** `mlt-integration`  
**Decision status:** Research recommendation; engine has not yet been integrated.  
**Product goal:** Give users a broad professional editing toolset, including capabilities comparable in category to CapCut's Pro features, without charging users a CapCut-style subscription.

## 1. The important distinction

We are transferring **capabilities and workflows**, not copying CapCut's private application, proprietary source code, private APIs, premium binaries, templates, music, stock media or other protected assets. CapCut's published Terms of Service prohibit copying, adapting, reverse engineering and creating derivative works from its Services except where expressly permitted.

The legal and technical route is to use independently available, reusable software components whose own licences permit our intended use, then expose their operations through our AI tool controller and our own Studio.

"Free to our users" is the intended product policy. It does not make server compute, storage, AI inference, licensed assets or third-party services free to operate. Our launch must be limited to verified free resources and quotas unless a future budget is approved.

## 1A. Implementation status update — 22 November 2026

We use this transfer map to build an independent editor from public feature
behaviour and reusable components. We do not obtain or copy CapCut's private
source files, application binaries, private APIs or protected assets.

- Stage 4's isolated MLT rendering-engine milestone has passed its full
  generated-media CI suite:
  [run 45031921304](https://github.com/promiseoluo66-cmyk/sparkle-clean-co/actions/runs/45031921304).
- Verified rendered capabilities include multitrack compositing, still-image
  overlays, transparent text/captions, dissolves, horizontal wipes, static and
  animated transforms, easing/Bezier keyframes, constant and variable speed,
  audio mixing/gain/fades/volume keyframes, and basic brightness, chroma,
  contrast and saturation filters.
- The test suite verifies decoded video pixels and audio samples, not just
  successful function returns.
- The MLT adapter remains isolated on `mlt-integration`; it has not replaced
  the production Cloudflare Worker/FFmpeg path.
- The full CapCut-style Studio timeline, interactive speed/keyframe graph,
  zoom/pan controls and complete editing-tool execution system are not yet
  implemented. The graph UI is planned for Stage 6; Stage 5 now focuses on the
  AI controller and executable project-edit transactions.
- The 112-entry structured capability catalogue currently records 12
  prototype-verified entries, 66 planned entries and 34 optional/dependency-
  gated entries. The status descriptions deliberately identify partial
  implementations rather than claiming full feature-family parity.

Detailed build inventory:
- [CapCut parity feature catalogue](CAPCUT_PARITY_FEATURE_CATALOGUE.md)
- [Structured 112-feature catalogue](CAPCUT_PARITY_CAPABILITIES.json)

## 2. Main engine recommendation

### Primary candidate: MLT Multimedia Framework

**Recommendation: make MLT the first serious multi-track rendering-engine candidate to test.**

Official project information says MLT is a multimedia framework designed for integration into applications, not only a standalone desktop editor. It supports multitrack audio/video compositions, playlists, filters, transitions, project serialization, keyframe/property animation, time/speed effects and scripting-language bindings, including Python. Its framework libraries are LGPL 2.1; individual modules can have different licences, so every module we enable must be audited.

Official evidence:
- MLT framework and feature list: https://www.mltframework.org/features/
- MLT documentation: https://mltframework.org/docs/
- MLT XML project format: https://mltframework.org/docs/mltxml/
- MLT Python bindings: https://mltframework.org/doxygen/group__python__bindings.html
- MLT property animation/keyframes: https://mltframework.org/docs/propertyanimation/
- MLT licence/copyright policy: https://github.com/mltframework/mlt_web/blob/master/CopyrightPolicy.md

**How we should use it:** our app keeps its own stable project document. A new MLT adapter converts that document into an MLT timeline/composition and calls the MLT library for preview/render operations. The AI never constructs MLT XML or arbitrary commands itself; our adapter creates validated structures from approved tool calls.

**Important licence boundary:** the MLT framework/library is LGPL 2.1, but MLT's `melt` command-line application is GPL according to its copyright policy, and some MLT modules are GPL or have other licences. We should initially investigate using the MLT library/Python bindings with a reviewed LGPL-compatible module set. Do not assume every MLT plugin, bundled codec or command-line utility is LGPL. Obtain a file-by-file dependency/licence report before distributing binaries or opening the service to customers.

### Supporting component: FFmpeg

Keep FFmpeg for media probing, format conversion and supported filters/codecs. It is already used by the current MVP. FFmpeg's default licence is LGPL 2.1 or later, but optional components can switch the resulting build to GPL or nonfree restrictions. The exact FFmpeg build and codecs matter: the current runner uses `libx264`, so the runner's actual FFmpeg configuration must be recorded and reviewed instead of assuming the system binary is an LGPL-only build.

Official licence: https://ffmpeg.org/legal.html  
Official filters reference: https://ffmpeg.org/ffmpeg-filters.html

**Architecture choice:** MLT is the preferred candidate for the timeline/composition model; FFmpeg remains a supporting media-processing layer. We should not throw away the existing FFmpeg MVP. We should add an engine adapter and prove MLT can render our canonical project before changing the live render path.

### Optional interchange component: OpenTimelineIO

OpenTimelineIO is an editorial data API/interchange format. It models clips, timing, tracks, transitions, markers and metadata, but does not contain or render the video/audio media itself. It could help with future project interchange; it is not the editing engine and is not a substitute for MLT.

Official documentation: https://opentimelineio.readthedocs.io/en/latest/

### Not recommended as the core to embed: Kdenlive or Shotcut application code

Kdenlive is a full open-source desktop editor based on MLT and is GPL-licensed. Shotcut is also a complete desktop editor using MLT. They are useful references for understanding how a mature application presents MLT capabilities, but our initial direction should be integrating the MLT framework beneath our own Studio, not copying either editor's interface/code into this project. This avoids unnecessarily adopting an entire desktop application's codebase and its licence obligations.

Evidence:
- Kdenlive project/licence: https://github.com/KDE/kdenlive
- Kdenlive feature overview: https://docs.kdenlive.org/en/getting_started/introduction.html
- Shotcut feature list: https://www.shotcut.org/features/

## 3. Feature-by-feature transfer map

| CapCut-style capability | Reusable component or route | What it can provide | Status / limitation |
|---|---|---|---|
| Multiple video tracks and overlays | MLT multitrack framework | Track composition, playlists, clip sequencing and layering | Strong fit; test in a small render prototype |
| Multiple audio tracks and mixing | MLT audio tracks/mixers + FFmpeg audio processing | Audio layers, mixing, gain, fades and audio processing | Strong fit; test synchronisation and mix behaviour |
| Split, trim, move, reorder, ripple-style edits | Our project/tool adapter + MLT timeline model | Real timeline edit operations | The project model and typed tool contracts now exist; handlers are not yet implemented |
| Transitions | MLT transition modules | Track-to-track transitions and compositing | Strong fit; each required transition plugin needs testing/licence review |
| Keyframes and animated properties | MLT property animation | Time-based parameter changes with supported interpolation/easing | Strong fit for supported parameters; test animation types and exact curves |
| Zoom, pan, position, scale, rotation, opacity | MLT filters/property animation + project adapter | Animated transforms and compositing | Strong fit; precise behaviour depends on selected filters and preview/render tests |
| Colour adjustments and common effects | MLT filters; selected FFmpeg filters | Colour, blur/sharpen and other supported image/audio filters | Broad coverage; effect catalogue must be built from actual installed filters |
| Masks, chroma key and compositing | MLT modules/filters | Layer compositing, alpha and selected masking/keying operations | Available categories; advanced subject masks need separate testing |
| Titles, text overlays and subtitles | MLT text/title producers + subtitle-capable FFmpeg filters | Text layers and timed subtitles | Strong base; font and subtitle rendering dependencies must be packaged correctly |
| Automatic captions | Whisper speech-to-text + caption timing adapter | Transcription and timed caption drafts | Whisper code and model weights are MIT-licensed; inference still uses CPU/GPU time and model storage |
| Caption translation/dubbing | Separate translation and speech services/models | Translated subtitle tracks and generated voice tracks | Not supplied by MLT/Whisper alone; provider/model costs and language quality must be evaluated |
| Background removal | A video segmentation model integrated as a frame/mask processor | Foreground masks for subject isolation | Not a built-in MLT feature; experimental. The rembg wrapper is MIT, but each model has its own licence; its documentation notes some weights require paid commercial permission |
| Motion/object/face tracking and auto-reframe | Dedicated tracking/computer-vision model + MLT animation | Tracking data can drive position/scale keyframes | Requires a separate model and integration; do not claim full automatic tracking from MLT alone |
| Stabilization | Dedicated stabilization filter/library where licence-compatible | Camera-shake analysis and correction | Candidate to evaluate separately; some popular FFmpeg/MLT plugin combinations are GPL-licensed |
| Speed changes and speed ramps | MLT time/speed effects + keyframes | Playback speed changes and time effects | Basic speed is already in MVP; keyframed ramps need renderer tests |
| Voice cleanup, noise removal, vocal isolation | Dedicated audio processing models/libraries | Speech cleanup and source separation | Not automatically included in MLT; model quality, licensing and compute still to investigate |
| Templates, stickers, transitions packs, stock clips, music and fonts | Our own authored packs or third-party assets with explicit commercial redistribution rights | A reusable media/effects library with skill presets | Cannot copy CapCut's premium assets. Every pack, font, sound and model must have a documented licence |
| AI video/image generation, avatars, generative expand | Separate generative model or external service | New media generation | Not part of the MLT engine. Usually the highest compute/provider-cost risk; not promised as free until a sustainable model is verified |
| Export profiles and formats | MLT consumer + FFmpeg codecs | Render to selected format/quality/resolution | Codec availability and licence depend on the installed build; test exact export profiles |

Sources for key rows:
- MLT supports multitrack compositions, filters, transitions, keyframes and time effects: https://www.mltframework.org/features/
- MLT XML defines producers, playlists/tracks, multitracks, filters and transitions: https://mltframework.org/docs/mltxml/
- MLT keyframe/property animation: https://mltframework.org/docs/propertyanimation/
- FFmpeg overlays and filter processing: https://ffmpeg.org/ffmpeg-filters.html
- Whisper MIT licence for code and model weights: https://github.com/openai/whisper
- rembg MIT code licence and model-specific notices: https://github.com/danielgatis/rembg

## 4. What "premium features free on our side" means

We can make advanced **editing controls** available to every user when they are powered by our own open, reusable engine and assets. Examples include multiple tracks, transitions, keyframe animation, colour tools, title/caption styling and audio mixing.

We cannot automatically make all CapCut Pro **content and AI services** free:
- CapCut's current public pricing page lists paid plans with AI credits, premium templates/features and cloud storage. The exact offer and price can vary by region/account.
- A proprietary CapCut Pro effect, template, sound or font is not something we can copy into our app.
- AI generation, background removal, speech recognition at scale and high-quality rendering consume compute, storage or provider quota.
- A free software licence does not grant free hosting or unlimited GPU access.

Our intended policy can be "no Pro subscription for core editing tools" while setting fair free usage limits, queue limits, output limits and a defined asset catalogue. We must show users those limits honestly.

CapCut pricing reference: https://www.capcut.com/pricing

## 5. Fit with the current $0 architecture

Keep the existing architecture for now:
- Cloudflare Worker: app/API and job dispatch only; do not render video inside the Worker.
- Cloudflare D1: project/job/skill metadata, not large video binaries.
- GitHub Actions runner: first candidate host for MLT/FFmpeg rendering jobs.
- GitHub private release assets: temporary media transport during the prototype only, with retention/cleanup work still required.
- AI planner: receives user intent and project context; returns structured tool calls.
- Tool executor: validates and applies calls to our project model.
- MLT adapter: converts the validated project into a rendering composition and invokes the selected MLT library API.
- FFmpeg: supporting probe, codec and filter operations.

Current verified published free-plan limits to design around:
- GitHub Free includes 2,000 standard-runner minutes per month for private repositories and 500 MB of Actions/Packages storage. Rendering consumes those minutes; there is no unlimited free cloud rendering.
- Cloudflare Workers Free has a 10 ms CPU limit per request, 100,000 requests/day and 128 MB memory. This reinforces that the Worker is an orchestration/API layer, not our video-rendering server.
- Cloudflare D1 Free has 500 MB maximum per database and daily row read/write quotas. Keep media out of D1.

Official limits:
- GitHub Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- Cloudflare Workers limits (updated 18 November 2026): https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/

**Cost conclusion:** a limited low-volume prototype can remain within free quotas if usage is small and jobs finish within included minutes. We cannot promise unlimited free editing, unlimited storage or free access to expensive AI generation. Paid services and billing activation remain off unless separately approved.

## 6. AI control design

The AI controller must call our own tools, not control CapCut and not generate raw FFmpeg/MLT commands.

Example flow:
1. AI calls `project.inspect` and `media.list`.
2. AI proposes adding clips/tracks, transitions, effects, captions and keyframes.
3. The server validates every call against the project's media IDs, time ranges, supported parameters and user permissions.
4. The project service applies the complete edit as a revisioned transaction.
5. The MLT adapter translates that project revision into a composition.
6. The render worker creates a preview/export and reports actual results.
7. AI inspects the render report and asks for approval or makes another validated pass.

The model never gets unrestricted shell access, arbitrary plugin loading, private API keys or permission to install new modules. Each editing tool maps to a tested engine operation.

## 7. First proof-of-fit experiment — before changing the live renderer

Build a separate GitHub Actions research test on the existing `video-editor-mvp` branch. It must not change the deployed Cloudflare Worker or the current MVP render route.

The experiment should:
1. Install MLT runtime/development/Python-binding packages on a GitHub-hosted Ubuntu runner, without enabling paid billing.
2. Record the MLT version, installed modules, module licences and available services.
3. Create tiny generated test media (not the user's video).
4. Use the MLT library/Python bindings to create a project with at least two video tracks, one audio track, a transition, a keyframed transform and a title/overlay.
5. Render a short MP4 and inspect it with ffprobe.
6. Verify the output has expected dimensions, duration, video/audio streams and non-empty output.
7. Record runtime and minutes used.
8. Fail the experiment if a required feature depends on an unreviewed GPL/proprietary module or if the Python binding cannot be loaded reliably.

Only after this test passes should we decide whether MLT becomes the main backend. The existing FFmpeg MVP remains intact as a fallback until the new path is proven.

## 8. Decisions and open gates

| Decision | Current position |
|---|---|
| Copy CapCut code, Pro binaries or assets | No |
| Use existing reusable editing technology | Yes |
| First timeline engine to evaluate | MLT framework |
| Keep FFmpeg | Yes, as supporting media layer and current MVP fallback |
| Use Kdenlive/Shotcut application code as our base | No; use their feature behaviour only as public references |
| Use OpenTimelineIO | Optional interchange investigation, not renderer |
| Give advanced editing controls to users without a Pro subscription | Target, within sustainable free quotas |
| Promise unlimited cloud rendering or unlimited AI generation for $0 | No |
| Connect to the YouTube automation | No; separate until testing and explicit approval |

## 9. Next implementation step

The next coding task is not to hand-build dozens of filters. It is to create a separate MLT proof-of-fit workflow and an adapter boundary. This will tell us which reusable MLT modules can deliver the needed CapCut-category features under an acceptable licence and within our existing no-billing architecture.

Do not deploy that experiment to production, do not replace the current renderer, do not change `main`, and do not touch the YouTube automation.
