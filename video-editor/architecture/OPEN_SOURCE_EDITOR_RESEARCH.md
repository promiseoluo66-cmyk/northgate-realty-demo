# Open-Source Video Editor Research

**Checked:** 22 November 2026  
**Target repository:** promiseoluo66-cmyk/sparkle-clean-co  
**Target branch:** mlt-integration  
**Product constraint:** independent Android-first editor; $0 operating budget; no paid billing activation.

This is a feature and architecture review of four public repositories. It is not a claim that their projects have been installed in our app, and it is not a complete security audit of every source file or dependency. No third-party source code, models, fonts, templates or media assets were copied into this editor as part of this research.

## Executive decision

The four repositories are useful in different ways:

| Repository | Project licence | Most useful lesson for our editor | Use decision |
|---|---|---|---|
| [OpenKatana](https://github.com/rk0neki/OpenKatana) | Apache-2.0 | Agent and human edit the same revisioned timeline; real-frame preview; capability discovery; contract validation | Adopt the design ideas. Consider small code reuse only after file-level licence and dependency review. |
| [Showhow](https://github.com/sirioberati/showhow) | MIT | Exact word-to-frame caption timing, speech-synced scenes, visual motion and cut checks | Adapt the caption timing and QA ideas. Do not make its paid voice service a requirement. |
| [SynthCut](https://github.com/Relo-video/SynthCut) | GPL-3.0 | AI-operated frame-based EDL, live timeline UI, undo/redo, snapping, waveform, jobs and transcript editing | Study the product behaviour, but do not copy its implementation into our repository unless we deliberately accept GPL obligations for the combined distribution. |
| [Kinocut](https://github.com/KyaniteLabs/kinocut) | Apache-2.0 | Typed tool contracts, capability reports, immutable asset identity, receipts, output-safety rules and evidence-based review | Strong architecture reference for our later AI, storage and release stages. Adapt the patterns rather than bringing in the whole package. |

**Important:** project licence does not automatically cover every dependency, model, bundled asset or downloadable runtime. Before copying any file or adding any dependency, check that item's own licence, version, redistribution terms and runtime requirements.

## 1. OpenKatana — agent/human editing and real preview

Repository: https://github.com/rk0neki/OpenKatana  
Licence: Apache-2.0 (repository licence and NOTICE are present).

### Useful features found

- One canonical project timeline is used by the human Studio and agent-facing tools. Mutations are revision-aware; a stale save is rejected instead of silently overwriting newer work.
- The agent workflow is explicit: discover capabilities, inspect the source, preview actual frames, import media, author the complete timeline, validate, save, preview key points, render, inspect the output and record a review.
- Preview tools return actual rendered images and metadata. A timeline description alone is not treated as evidence that the edit looks correct.
- Captions accept supplied word timings or SRT/VTT. The caption helper can group words into readable phrases, provide styles such as clean, bold-pop, karaoke, lower-third and title-card, and export subtitle files. It does not pretend that grouping is transcription; word timings still need checking against the audio.
- Audio uses one shared planner for validation and rendering. Missing audio, invalid trims, fades longer than a clip and other known errors are caught before the full render.
- The effect preview operation produces a short sample and contact sheet for one effect before the editor applies it to the larger project.
- Capability discovery reports which tools and dependencies are actually ready, rather than assuming every optional engine is installed.

### What we should adapt

1. **AI and human must mutate the same canonical project.** Our future mobile Studio should not have a separate edit state from the AI tool controller.
2. Add a strict **inspect → preview → edit → validate → preview → render → review** flow.
3. Let the project accept supplied per-word timings and SRT/VTT before adding an optional local transcription module.
4. Add short, generated-media effect previews and actual output-frame checks.
5. Use one audio planning/validation routine for both render planning and execution.

### Limitations for our $0 Android project

OpenKatana is a local Python/browser/CLI workflow. It is not a drop-in Android editor or an always-available cloud rendering backend. It has optional Blender and ComfyUI workflows; their services, weights and runtime costs must be checked separately. Its architecture is useful, but copying its broad dependency set would be a poor fit for our current phone-first and $0 constraints.

## 2. Showhow — speech-synchronised captions and video quality checks

Repository: https://github.com/sirioberati/showhow  
Licence: MIT.

### Useful features found

- A caption alignment file stores word start/end timings. The timeline converts times to integer frames at the chosen frame rate.
- Scene changes can be placed at the midpoint of real silence between the previous spoken word and the next one, rather than choosing scene starts by eye.
- Captions show the word currently being spoken, distinguish it visually from already-spoken words and group words into short readable blocks.
- Planning checks reject overlong caption blocks and scene boundaries that do not land in silence. Render checks look for long frozen sections and empty backgrounds at changes.
- Separate motion and join checks inspect rendered frames to identify excessive movement, abrupt one-frame cuts, freezes and jumps. These are technical warning signals and still need visual review.

### What we should adapt

1. Add a **word-timing caption format** to our project model: word text, source start/end, confidence when known, and a caption style/group.
2. Support phrase grouping and karaoke/active-word highlighting as an optional visual style.
3. Use measured speech gaps as suggestions for scene handovers; never invent timing for speech that was not heard.
4. Add generated-video checks for freezes, sudden jumps and motion that is too fast to follow.
5. Keep SRT/VTT import/export so captions can be supplied without running speech recognition.

### Cost and fit

Showhow is built for code-authored explainer reels, not a general-purpose timeline editor. Its sample voice generation uses ElevenLabs, which requires an external account/key and is not our default free path. The useful idea for us is the local caption timing and deterministic QA; voice generation must remain optional and must never be required for ordinary editing.

## 3. SynthCut — AI-operated timeline workstation

Repository: https://github.com/Relo-video/SynthCut  
Licence: GPL-3.0.

### Useful features found

- A non-destructive, frame-based edit decision list is the source of truth. Integer project frames are used for clip positions, trims, fades, caption windows and transitions; seconds are converted only at the render boundary.
- The AI edits that project through typed tools. The desktop UI listens to the same state and reflects those edits, so the person and the AI do not each maintain a different version of the timeline.
- The timeline design includes multi-track clip blocks, drag-to-move, edge trimming, snapping to the playhead and clip edges, split, delete and ripple-delete operations.
- It provides undo/redo, background render jobs, autosave/recovery, waveform display, proxy media for preview and a cache so a small change does not have to re-render the whole project.
- It includes transcript-based editing ideas: removing filler words and pauses, deleting word ranges, and assembling a cut from an edited transcript.
- Its feature surface includes transforms/keyframes, caption tracks, effects, audio fades/crossfades, motion graphics and output presets.

### What we should adapt

1. Keep time in integer project frames in the canonical project model and convert only at renderer boundaries.
2. Build the eventual Studio timeline with zoom, playhead seeking, snap guides, clip move/trim/split and separate video/audio/caption lanes.
3. Make the AI's tool operations the same operations the Studio invokes.
4. Add undo/redo and project autosave before exposing destructive editing to the AI.
5. Add transcript-based editing only after we have reliable timed words and a review step.

### Licensing and platform warning

Do not copy SynthCut source files into our project under our current licensing assumptions. GPL-3.0 is strong copyleft; combining or distributing derivative work can impose GPL obligations on the combined program. A deliberate decision to distribute our editor under GPL would be required before considering source-code reuse. Its Electron desktop app is also not a ready-made Android interface. We will study its interaction patterns, not transplant its desktop UI or renderer.

Its own third-party licence notes also identify dependencies with separate terms, including Remotion. A project-level GPL badge does not make every dependency interchangeable or automatically free for every commercial use.

## 4. Kinocut — safe AI tools, asset records and quality evidence

Repository: https://github.com/KyaniteLabs/kinocut  
Licence: Apache-2.0.

### Useful features found

- Typed operation contracts are shared across MCP, Python and CLI. Unknown fields and invalid values are rejected instead of being silently ignored.
- A capability report distinguishes available, unavailable and degraded features, including missing dependencies and supported formats. Optional features do not become available merely because a tool name exists.
- The MCP tool surface is grouped into operation families. The default tool list stays compact, while the agent can discover one operation and fetch its exact schema when needed.
- Source media can be stored by content hash. Asset identity is based on the original bytes, cache hits verify the bytes, and missing or corrupt media fails closed.
- Project records are append-only and revisioned. Corrections supersede prior records rather than rewriting history.
- Output paths are guarded: source media should remain immutable, outputs use a new path unless an explicit strict-boolean overwrite permission is supplied, and overwrite consent is scoped to the current operation.
- Preflight checks inspect metadata, streams, rotation, loudness, colour and full-decode integrity. Error messages are stable and do not leak internal host paths or raw FFmpeg stderr.
- A Video Receipt records the requested operation, what actually ran and the measured output evidence. Technical measurement is not presented as proof of creative quality or human approval.
- Crossfades require real source handles on both sides. The system rejects missing audio handles instead of fabricating overlap by repeating samples.

### What we should adapt

1. Build a structured **capability manifest** before connecting the AI to more editing tools.
2. Require exact project revision numbers for mutations and reject stale edits.
3. Add content hashes and durable project/media ownership when we implement save/reopen and cloud project APIs.
4. Add render receipts for source hashes, operations, output metadata and quality checks.
5. Protect input files and require explicit confirmation before overwriting or performing heavy/destructive operations.
6. Check final audio/video with actual measurements; separate technical pass, AI review and human approval.
7. Group tool discovery into a small number of families so our future agent can request exactly the operation schema it needs.

### Cost and fit

Kinocut is a large Python/FFmpeg/MCP toolkit with optional transcription, image and audio dependencies. It is not a mobile app and should not be installed wholesale as a dependency of our Worker. Its architecture and selected small utilities can be studied independently; every dependency and code file must still be reviewed before reuse.

## 5. Feature recommendations for our project

Priorities below are based on what benefits our own editor, the existing MLT branch, the Android-first requirement and the $0 rule.

| Priority | Feature to build | Best reference | Target stage | Reason |
|---|---|---|---|---|
| 1 | Timed title/caption track with SRT/VTT and supplied word-timing import | Showhow, OpenKatana, Kinocut | 4 | Completes a major editing function without requiring a paid speech API. |
| 2 | Karaoke/active-word caption mode and phrase grouping | Showhow, Kinocut | 4 | Makes captions readable and accurately synchronised. |
| 3 | Audio crossfade with validated source handles; keep measured gain/fades | Kinocut, OpenKatana | 4 | Prevents clicks and rejects fake overlaps. |
| 4 | Preview-one-effect and decoded-pixel regression checks | OpenKatana, Showhow | 4 / 8 | Lets us see an effect before a full render and catches black/blank/broken output. |
| 5 | Capability manifest and strict tool discovery | Kinocut, OpenKatana | 5 | The AI must know exactly which tools and dependencies are ready. |
| 6 | Revision-safe edit transactions, undo/redo and receipts | SynthCut, OpenKatana, Kinocut | 1 / 2 / 5 | Makes AI edits inspectable and reversible. |
| 7 | Mobile multitrack timeline with snap, zoom, trim, split, move, ripple and caption lane | SynthCut | 6 | This is essential to the main promise: edit inside our own app. |
| 8 | Content-hashed media records and safe project recovery | Kinocut | 1 / 7 | Protects user media and supports reliable save/reopen. |
| 9 | Motion/freeze/cut/loudness quality report | Showhow, OpenKatana, Kinocut | 8 | Adds measurable QA without pretending measurements equal artistic approval. |

### First addition after the caption renderer is verified

Create a strict caption event in the existing project schema, with:
- clip-local start/end in project frames;
- text and optional per-word start/end timing;
- confidence when known;
- explicit style (clean, lower-third, karaoke/active-word);
- safe position, size, colour, outline and opacity fields;
- source reference when the words came from a transcript or subtitle file.

The renderer should turn each event into timed title/caption overlays using the same project timeline. Add tests for non-overlapping word timing, clip bounds, frame rounding, empty text, unsupported styles and actual rendered pixels. SRT/VTT import/export must work without any speech-recognition API key.

## 6. What we are not importing

- No GPL SynthCut code, Electron application or bundled FFmpeg build.
- No paid ElevenLabs requirement, paid model endpoint, paid cloud render or automatic cloud fallback.
- No ComfyUI, Blender, Whisper, CLIP or large AI models as mandatory editor dependencies.
- No third-party fonts, stickers, audio, templates, models or sample media without checking each asset's own licence and redistribution permission.
- No assumption that another project's feature list proves the same feature works in our MLT build.

## 7. Integration rule

The existing mlt-integration branch remains our implementation. Each feature is added to our own project model, registered editing tools and MLT/FFmpeg adapter only after:
1. its exact project contract and capability limits are defined;
2. the code and every dependency have a compatible licence and $0 runtime path;
3. a generated-media test verifies actual decoded frames/audio;
4. unsupported combinations fail with a clear error;
5. the existing production Worker remains unchanged until a separate integration and regression review passes.

The product stays an independent editor: human controls and AI tools must operate the same canonical timeline, with preview, undo/review and export inside our own editor workflow.
