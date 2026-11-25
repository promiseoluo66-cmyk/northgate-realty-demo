# MLT Capability Audit

**Research date:** 20 November 2026  
**Branch:** `mlt-capability-audit`  
**Purpose:** Verify whether MLT is a suitable reusable editing engine before any change to the current renderer.

## Scope and safety

- This experiment is isolated from the deployed Worker and the current FFmpeg render route.
- It uses tiny synthetic red/blue clips generated inside GitHub Actions. It does not need the user's 28 MB video or any upload from a phone.
- It does not edit the YouTube automation.
- It does not copy CapCut code, private APIs, templates, sounds, fonts, or other protected assets.
- It uses a standard GitHub-hosted runner and does not request paid billing.
- The workflow is limited to this research branch.

## Verified upstream facts

1. The latest MLT release listed by its official documentation on this research date is **MLT 7.42.0**, released 3 October 2026.
2. MLT is a framework for multitrack audio/video compositions. Its official documentation separates producers, filters, transitions, links, and consumers.
3. Official MLT Python bindings exist. They wrap the C++ API through SWIG and are imported as `mlt7`.
4. The official filter catalogue documents (among many others):
   - brightness, crop, blur, colour and image adjustments;
   - chroma key;
   - subtitles and text;
   - audio volume and other processing;
   - `opencv.tracker` for object tracking;
   - `rnnoise` for speech noise reduction;
   - rotoscoping and video-stabilization filters.
5. The official transition catalogue documents video compositing/transitions and audio mixing. The `luma` transition and `mix` audio transition are documented examples.

## Licensing findings — important

MLT is modular; there is no single licence that safely describes every plugin.

| Component | Upstream licence / finding | Project decision |
|---|---|---|
| MLT framework and client libraries | LGPL 2.1 | Preferred base, subject to dependency review |
| `melt` command-line application | GPL (MLT copyright policy says GPLv2) | Use only as an internal diagnostic/test tool for now; do not bundle it into the product without a licence decision |
| `chroma` filter | LGPL 2.1 | Candidate for the reusable baseline |
| `opencv.tracker` filter | LGPL 2.1 | Strong candidate for object tracking, subject to installed-module and behaviour tests |
| `rnnoise` filter | LGPL 2.1 | Candidate for voice-noise reduction |
| `vidstab` / `deshake` filters | GPL / GPLv2 | Do not include in the first LGPL-first product module set |
| `rotoscoping` filter | GPL | Do not include in the first LGPL-first product module set |
| FFmpeg | Usually LGPL 2.1+, but optional GPL/nonfree components change the result | Inspect the exact build and enabled codecs; do not assume every system FFmpeg build is LGPL-only |

A plugin's presence in the upstream catalogue does **not** prove it is installed on our runner. The workflow reports the actual installed services. Licence review must be tied to the exact package/module build that we choose to ship or operate.

## AI abilities: separate engines, not MLT magic

- Speech-to-text/caption generation can be added using Whisper. Its repository code is MIT-licensed; model storage and CPU/GPU runtime still have costs.
- Background removal can be added with a segmentation model. The `rembg` wrapper is MIT-licensed, but its README explicitly warns that model weights have separate licences. In particular, BRIA RMBG-2.0 requires a paid agreement for commercial use. We must not use that model unless a commercial licence is obtained.
- Generative video, image generation, translation, dubbing and advanced AI effects require their own model/provider and cost/licence checks. MLT does not provide them automatically.

## Runner/package compatibility

- GitHub announced that `ubuntu-latest` migrated to Ubuntu 26.04 between 19 October and 19 November 2026. This experiment pins `ubuntu-26.04` so the OS does not silently change under the test.
- Ubuntu 26.04's package archive lists MLT 7.36.1 and includes the `melt`, `libmlt`, and `python3-mlt` packages.
- This Ubuntu package is behind upstream MLT 7.42.0. Therefore, a passing package test proves a practical packaged integration path, not that every feature in 7.42.0 is present.
- Ubuntu 24.04's published package is MLT 7.22.0, so it is not the better current package target for this test.
- GitHub Free currently includes 2,000 standard-runner minutes/month for private repositories and 500 MB of shared Actions/Packages storage. This small test consumes included Actions minutes; it is not unlimited rendering capacity.

## Actual automated results — verified 20 November 2026

GitHub Actions run **44796441162** completed successfully on branch `mlt-capability-audit`:
https://github.com/promiseoluo66-cmyk/sparkle-clean-co/actions/runs/44796441162

The runner was Ubuntu 26.04 and installed MLT **7.36.1** from the Ubuntu package archive.

| Check | Actual result |
|---|---|
| System Python binding | PASS — Ubuntu's `/usr/bin/python3` is Python 3.14.4; `import mlt7`, factory initialization and producer creation succeeded |
| Native MLT Python render | PASS — Python API built a two-track `Tractor` composition with a compositing transition, then rendered a valid 1-second 720×576 MP4 through the `avformat` consumer |
| Two video tracks and transition | PASS — generated red/blue clips rendered as a valid 1-second 320×240 MP4 with MLT's `luma` transition |
| Baseline installed filters | PASS — `brightness`, `chroma`, `subtitle`, and `volume` were found |
| Object tracking module | FOUND — `opencv.tracker` is installed; its tracking behaviour has not yet been exercised on footage |
| Audio mix transition | FOUND — `mix` is installed; an actual two-audio-track mix test remains |
| RNNoise denoising filter | NOT INSTALLED in this Ubuntu package set; the upstream MLT plugin exists and is LGPL, but it requires the RNNoise development library and an MLT build with `MOD_RNNOISE` enabled |
| GPL-only modules | `vidstab` and `rotoscoping` were present in the generic package; do not expose them in the first LGPL-first product build |
| Current renderer Python compatibility | NOT AVAILABLE — the existing renderer uses Python 3.12.16, and that interpreter could not import the Ubuntu `mlt7` binding. The OS Python 3.14.4 binding worked |

**Important integration discovery:** We have proved the MLT library can render through its Python API, not just that the command-line program starts. But we have also found a Python-version mismatch with the current renderer. The safe next design is either (a) run MLT as a separate, tightly controlled system-Python 3.14 worker while leaving the current Python 3.12 renderer untouched, or (b) build/install MLT's Python bindings specifically for Python 3.12 and test that setup. We must not change the production renderer until one of these routes is proven.

The two-track test emitted a warning that the MLT Qt module has no X11/Wayland display. The generated output was valid, but headless title/Qt graphics rendering still needs a dedicated test (likely with a virtual display or an offscreen-safe configuration).

The use of the `melt` GPL command-line application for the separate luma-transition probe above was limited to this isolated test. The native Python API test used the MLT library and its `avformat` consumer directly. The product integration should use the LGPL MLT libraries/bindings and an allowlisted set of reviewed plugins, not bundle the GPL command-line tool.

## How additional MLT abilities can be added

MLT is designed to be extended with optional modules. The official MLT build system exposes switches such as:

- `MOD_OPENCV` — build the OpenCV module (it requires OpenCV's tracking component).
- `MOD_RNNOISE` — build the RNNoise noise-reduction module (it requires the RNNoise development library).
- `GPL=OFF` — turn off a group of GPL-only modules in MLT's build configuration, including the GPL video-stabilization module and several other GPL extras.

This is the route for adding a missing compatible plugin: obtain the dependency, compile the selected module against the chosen MLT version, then verify the built service appears in MLT's plugin catalogue and passes its own render test. We should not simply copy a plugin binary from an unrelated build.

### What the installed tracking ability actually does

The installed `opencv.tracker` service is a real object-following tracker, not a general AI object detector. MLT's documentation says it starts with a rectangle around the target in the first frame and recommends a two-pass analysis/render process in a non-linear editor. That means our AI controller would first need to identify the object and set the starting rectangle; MLT can then follow it. This is useful for effects such as following or blurring a selected object, but automatic person/object detection is an additional AI capability.

### RNNoise installation result

The upstream RNNoise MLT filter is LGPLv2.1 and performs speech-background-noise reduction. The current Ubuntu 26.04 MLT package did not include the `rnnoise` service, and the Ubuntu package search at this research date did not list `librnnoise-dev` for Ubuntu 26.04 (it is listed for the later 26.10 suite). We can still build RNNoise and enable `MOD_RNNOISE` in a custom MLT build, but that needs a separate dependency/build test; it is not a one-click plugin we can turn on in the present runner.

### Practical shortlist from this audit

| Ability | Current state | Next action |
|---|---|---|
| Multi-track timeline and basic transitions | Python API and two-track transition render passed | Build our MLT adapter around the project timeline |
| Green-screen keying | LGPL filter installed | Test a generated green-screen clip and foreground composite |
| Object tracking | LGPL OpenCV tracker installed | Test the documented two-pass workflow with a moving synthetic object; AI detection remains separate |
| Subtitles | Subtitle filter installed | Test subtitle overlay and font/rendering in headless mode |
| Audio mixing | Mix transition installed | Test two synthetic audio tracks and sync |
| Speech denoising | Not installed in current package | Evaluate a custom RNNoise-enabled build |
| Video stabilization | GPL module present in generic package | Exclude from initial LGPL-first build unless licensing strategy changes |
| Rotoscoping | GPL module present in generic package | Exclude from initial LGPL-first build unless licensing strategy changes |
| Background removal / generative AI | Not supplied by MLT | Integrate separate models only after model-weight licences, compute and commercial use are checked |

## What the automated proof checks

1. Installed MLT version.
2. The Python `mlt7` binding loads and can create an MLT producer.
3. Which core and optional filters/transitions/output modules are actually installed.
4. A tiny generated two-track project renders through MLT's FFmpeg-backed output consumer.
5. FFprobe can read the rendered video stream and duration.

## What a passing test will NOT prove

A pass is not yet proof that every Pro-category feature works, that preview is fast, that all codecs are legally distributable, or that MLT will be our final engine. We still need targeted tests for the exact chosen effects, tracking, captions, keyframes, audio, export profiles, rendering speed, and licence/attribution obligations.

## Official references

- MLT documentation and release notices: https://mltframework.org/docs/
- MLT filter catalogue: https://mltframework.org/plugins/PluginsFilters/
- MLT transition catalogue: https://mltframework.org/plugins/PluginsTransitions/
- MLT Python bindings: https://mltframework.org/doxygen/group__python__bindings.html
- MLT copyright policy: https://mltframework.org/docs/copyrightpolicy/
- Chroma key licence: https://mltframework.org/plugins/FilterChroma/
- OpenCV tracker licence and behaviour: https://mltframework.org/plugins/FilterOpencv-tracker/
- RNNoise licence and behaviour: https://mltframework.org/plugins/FilterRnnoise/
- Rotoscoping licence: https://mltframework.org/plugins/FilterRotoscoping/
- Video stabilization licence: https://mltframework.org/plugins/FilterVidstab/
- FFmpeg legal/licensing page: https://ffmpeg.org/legal.html
- Whisper licence: https://github.com/openai/whisper/blob/main/LICENSE
- rembg model/licensing notice: https://github.com/danielgatis/rembg#models
- Ubuntu 26.04 MLT packages: https://packages.ubuntu.com/en/source/resolute/mlt
- GitHub Actions runner migration: https://github.blog/changelog/2026-09-17-ubuntu-26-generally-available-and-latest-migration/
- GitHub Actions included usage: https://docs.github.com/en/actions/reference/limits

## Current result

**Initial MLT proof of fit: PASS.** The Python library render and a synthetic two-track render both succeeded. MLT is now a technically credible candidate, but it is not yet approved as the production engine. The Python 3.12/3.14 mismatch, headless title rendering, actual object-tracking behaviour, keyframes, chroma-key behaviour, audio mixing, exact LGPL-only package composition, and performance on larger files remain open gates. Do not replace the current FFmpeg renderer or deploy MLT until those are resolved.
