# Independent AI Video Editor — Professional Editor Blueprint

**Status:** Architecture baseline — first design stage  
**Product direction:** An AI-operated professional video editor  
**Scope boundary:** This project remains separate from the existing YouTube automation. No integration, authentication sharing, repository changes, or workflow changes are authorized by this blueprint.

## 1. Product definition

Build an independent video-editing application with a professional editing toolset. A person describes the desired result in natural language; the AI plans the work and operates explicit, validated editing tools. The editing engine performs the actual media operations and renders the result.

This is not a CapCut clone and does not depend on reverse-engineering another editor. We build our own project format, timeline, tools, AI controller, Studio and rendering pipeline.

The target is both:
- **AI-operated editing:** the AI can assemble and revise an edit by calling tools.
- **Human-operated editing:** the Studio will expose the same underlying project and operations through timeline and property controls.

The AI and the Studio must operate on the same project model. They must not maintain separate, conflicting versions of an edit.

## 2. Core architecture

1. **Studio (mobile-friendly web app):** media bin, preview, multitrack timeline, clip properties, effects, keyframes, captions, audio controls, project history and export controls.
2. **Project service:** saves versioned project documents, asset metadata, edit history and job state.
3. **AI controller:** interprets the user's request, inspects the project, selects tools, creates a proposed edit, validates it and requests execution.
4. **Tool registry and executor:** exposes a controlled catalogue of typed editing operations. Every tool has a defined input schema, validation rules, permission boundary and result.
5. **Editing engine:** converts the project into a render graph and performs the media operations. The first renderer can continue using Python and FFmpeg while the architecture keeps the rendering backend replaceable.
6. **Cloud job service and API:** accepts jobs, stores project/job metadata, dispatches rendering and reports progress. The browser does not need to remain open after a cloud job has been accepted.

The AI controller must never receive unrestricted shell access or execute model-generated commands. It can only request registered tools. Tool arguments are validated by the server before the project or media is changed.

## 3. The project data model

All editing state belongs to one versioned project document. The following is the logical model; it is a design contract, not yet implemented code.

### Project
- `schema_version`: version of the project format.
- `project_id`, `name`, `created_at`, `updated_at`.
- `video_profile`: width, height, frame-rate numerator/denominator, pixel aspect ratio and colour profile.
- `timeline_timebase`: a precise integer time unit used for clip positions and durations. Video frame boundaries are snapped using the project's frame rate; audio retains finer timing.
- `assets[]`: imported video, audio, image, font and generated media records.
- `tracks[]`: ordered video, overlay, text, audio and supported auxiliary tracks.
- `transitions[]`, `markers[]`, `sequence_settings`.
- `history`: project revision and transaction references.

### Asset
Each asset has a stable ID, media type, original filename, storage reference, size, checksum, duration, dimensions, frame rate, codecs, audio stream information and processing status. Optional derived assets include thumbnails, low-resolution proxies, audio waveforms and extracted metadata. Original uploads are preserved; edits refer to assets rather than overwriting them.

### Track
A track has an ID, type, name, order, enabled/locked/muted/solo state, opacity or volume where relevant, compositing/blend settings where supported, and an ordered list of clip references. Track order defines compositing priority for visual layers.

### Clip
A clip has an ID, asset reference, track reference, timeline start, source in/out points, duration, playback rate, enabled state, transform, crop, opacity, volume/pan where relevant, effects and keyframe animation data. A clip may reference a video, audio, image, text or generated asset.

### Keyframes
A keyframe targets a named clip property such as position, scale, rotation, opacity, volume or effect parameter. It stores a precise timeline time, value, interpolation mode and easing parameters. The data model must allow multiple animated properties on one clip and must preserve keyframes when a clip is moved or retimed according to explicit timing rules.

### Effects and transitions
Effects are typed records with an effect ID, parameters, enabled state and optional keyframes. Transitions are explicit timeline objects that define the relationship between outgoing and incoming clips, their overlap/duration and transition type. Unsupported effect types must be rejected clearly, not silently ignored.

## 4. Editing tool catalogue

The AI can use only registered tools. This catalogue is the initial scope; each operation will later receive a precise JSON input/output schema and automated tests.

### A. Project and media tools
- Create, open, inspect, duplicate and save a project.
- List/import media; inspect duration, streams, dimensions and frame rate.
- Generate thumbnails, proxies and audio waveforms.
- Relink missing media and validate that referenced assets exist.

### B. Timeline and track tools
- Add, rename, reorder, lock, unlock, enable and disable tracks.
- Add, remove, split, trim, move, duplicate and group clips.
- Set source in/out points, timeline positions and playback rates.
- Ripple delete, insert edit, overwrite edit and close gaps.
- Add markers and inspect timeline ranges.
- Validate track compatibility and prevent accidental overlaps where a track's rules prohibit them.

### C. Transform and compositing tools
- Set position, scale, rotation, anchor point, crop, opacity and fit/fill behaviour.
- Set supported blend modes and layer order.
- Add masks and chroma-key/green-screen operations where the renderer supports them.
- Create picture-in-picture layouts and multi-layer compositions.

### D. Animation tools
- Add, update and delete keyframes.
- Animate position, scale, rotation, opacity, crop, volume and supported effect parameters.
- Set interpolation and easing.
- Create motion paths, animated zooms and supported speed ramps.
- Inspect keyframes and return property values at a requested time.

### E. Effects and colour tools
- Add, configure, reorder, enable, disable and remove effects.
- Support a staged library of blur, sharpen, denoise, colour correction, grading, vignette and other validated effects.
- Keep effect parameters and their supported ranges explicit.
- Do not claim an effect is supported until the selected renderer has a tested implementation.

### F. Transition tools
- Create, adjust, replace and remove transitions.
- Support an initial set such as cut, dissolve, fade, wipe and dip-to-colour.
- Validate clip overlap and available source frames before applying a transition.

### G. Audio tools
- Add and arrange multiple audio tracks and clips.
- Set gain, fades, pan, mute, solo and keyframed volume.
- Mix voice, music and sound effects; synchronize audio; apply supported fades and filters.
- Add ducking and loudness-normalization operations as tested capabilities.
- Preserve source audio and make mixing decisions reversible.

### H. Text, titles and captions
- Add and edit text/title clips, fonts, size, colour, outline, background and position.
- Create subtitle/caption tracks, edit words and timings, and style caption groups.
- Support animated text through the same keyframe system.
- Treat transcription as a separate capability that may require an approved speech-to-text provider or a local/cloud model; do not assume it is free or available until verified.

### I. Export and quality tools
- Set output format, resolution, frame rate, video/audio codec, bitrate or quality target.
- Validate the project before rendering.
- Render a preview range or full export.
- Inspect render errors and basic output metadata.
- Produce a render report and retain the project separately from the exported video.

## 5. How an AI editing request is executed

1. **Understand:** parse the user's instruction and identify the desired outcome.
2. **Inspect:** inspect available assets, project profile, tracks, clip durations and existing edits.
3. **Plan:** create a structured edit proposal with references to registered tools and their arguments.
4. **Validate:** check IDs, media availability, time ranges, track types, parameter ranges, resource limits and tool support.
5. **Preview the changes:** present a readable summary or preview where practical. Ambiguous media selection or destructive actions require clarification or explicit approval.
6. **Apply as a transaction:** apply a group of validated operations against a known project revision. Either commit the complete transaction or roll it back; do not leave half-applied edits.
7. **Render and inspect:** render a preview or export, check the result and report any unsupported or failed operations honestly.
8. **Revise:** the AI can make another validated edit pass while preserving project history.

Every tool call should return a structured result: success/failure, changed project revision, affected IDs, warnings and a concise explanation. The AI must not claim an edit succeeded merely because it requested the tool.

## 6. Skill system

A reusable editing skill is a versioned recipe, not executable code. It can include:
- style description and intended use;
- preferred project profile and export defaults;
- allowed tool categories;
- reusable timeline/effect/caption/audio settings;
- constraints and required user choices;
- skill version and compatibility information.

A skill can be imported from validated JSON, created from a natural-language description, edited, saved, selected for a future job and upgraded. The AI may adapt a skill to the current footage, but it must explain important deviations. Skills cannot grant permissions or bypass tool validation.

## 7. Rendering strategy

The project document is the source of truth. A renderer converts it into an execution graph:
- resolve source assets and metadata;
- prepare trims, time changes and transforms;
- build video layers and transitions;
- build text, caption and graphics layers;
- build audio mixes;
- encode and validate the output.

The existing Python/FFmpeg renderer is a starting backend for simple operations and will be expanded in tested steps. FFmpeg can perform many compositing, filter, subtitle and audio operations, but the complete professional feature set must not be assumed to exist until implemented and tested. The renderer interface must allow another backend or specialized processing component later without changing the project format or AI tool contracts.

Rendering is asynchronous. A job has queued/running/completed/failed states, progress where available, logs, output metadata and a retry-safe job ID. Temporary media requires retention and cleanup rules. Free cloud execution has finite resource/time limits; the system must report limits and must not imply unlimited rendering or free high-end GPU processing.

## 8. Safety, reliability and cost rules

- No arbitrary model-generated code, shell commands or direct database writes.
- Validate all tool inputs on the server; enforce file-size, duration, resolution, concurrency and render-time limits.
- Keep credentials in server-side secrets, never in project JSON or browser storage.
- Preserve source media and project history; use reversible transactions.
- Restrict external URLs and media downloads to prevent server-side request abuse.
- Use private access and job ownership checks before exposing projects or media.
- Clean up temporary media according to a documented policy.
- Prefer the existing $0 prototype infrastructure until its actual limits are checked. No paid service, billing activation or new provider is assumed by this design.
- Keep the editor's credentials, workflows and repositories separate from the YouTube automation.

## 9. Implementation sequence

**Stage 1 — Project foundation:** finalize the project schema, asset/track/clip/keyframe records, versioning rules and validation tests.

**Stage 2 — Tool foundation:** implement the registry, typed schemas, permission checks, transaction system, undo/redo model and test harness.

**Stage 3 — Timeline engine:** implement multiple tracks, clips, trims, splits, moves, ordering and compositing.

**Stage 4 — Animation and media tools:** add keyframes, transforms, effects, transitions, text/captions and audio mixing in tested groups.

**Stage 5 — AI controller:** connect model tool-calling to the registry, add inspect-plan-validate-apply-preview-revise behaviour and a deterministic fallback for supported operations.

**Stage 6 — Studio:** build the mobile-friendly media bin, preview, multitrack timeline, property panels, keyframe editor, effects/audio/text panels and project history.

**Stage 7 — Cloud/API hardening:** project persistence, asynchronous rendering, authentication, quotas, retention, retry handling and documented API contracts.

**Stage 8 — Full validation:** test each tool, combinations of tools, project reopen/edit round trips, render quality, failed jobs, mobile usability and resource limits.

## 10. Definition of done

The product is not considered a professional AI editor just because an AI can write an edit plan. It must demonstrate that:
- projects can be saved, reopened and edited without losing tracks or keyframes;
- multiple video/audio/text/overlay tracks render in the correct order;
- tools perform real, repeatable operations and reject invalid inputs;
- the AI can inspect a project, call several tools in sequence and explain the result;
- changes can be revised or undone without damaging original media;
- preview and final exports match the project within documented renderer limits;
- cloud jobs continue after the phone/browser closes;
- the mobile Studio remains usable on an Android phone;
- authentication, cost limits, cleanup and failure handling are tested;
- the separate YouTube automation remains untouched unless a future integration is explicitly approved.

---

**Current implementation reality:** the existing prototype is an early single-video trim/speed/reframe pipeline with a Studio, API, D1 metadata and cloud job dispatch. It does not yet implement the professional project model, multitrack timeline, animation/keyframe system, or the complete tool catalogue above. This blueprint defines the target; each capability will be marked complete only after code and tests verify it.
