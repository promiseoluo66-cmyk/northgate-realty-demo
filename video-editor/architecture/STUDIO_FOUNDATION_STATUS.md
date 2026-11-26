# Stage 1 — Mobile Studio and Editing Foundation

**Lab branch:** video-editor-lab  
**Repository:** promiseoluo66-cmyk/northgate-realty-demo  
**Status:** Stage 1 Tasks 1–10 have implementation and offline automated acceptance coverage on `video-editor-lab`. Latest full workflow run #118 passed: 275 Python tests, 51 Node tests and all checked-in D1 migrations. Stage 1 is ready to progress to Stage 2 at the offline/code level. Live Worker-to-runner verification remains pending because deployment has not been authorized.

## Implemented in this snapshot
- Responsive mobile Studio workspace with multi-track timeline, ruler, zoom, clip selection and inspector.
- Source-video preview, pointer/touch clip move and trim, cross-track drop targets and near-edge snapping.
- Direct move, trim, slip, split, duplicate, delete, source replacement, insert-and-ripple, speed, framing, transform, keyframes, profile, track operations, undo and redo.
- Project open/list/rename APIs, revision checks and bounded undo/redo history.
- Track add, rename, reorder, lock, enable, mute, solo, hide/show and remove operations.
- Multi-file media import, project media bin, filename/type/folder/tag search, folder assignment and insertion at playhead.
- Small browser-generated image/video thumbnails and audio waveform metadata, revision-guarded preview persistence, and media relinking that preserves asset IDs and clip references.
- .SRT and .VTT subtitle import into unlocked text tracks, with cue timing validation.
- Ripple overwrite and cross-track ripple insert with validation before project mutation.
- Linked clip groups with atomic movement and cleanup during split, delete, ungroup and track removal.
- Persistent timeline markers with add, move, rename, remove and playhead navigation.
- Cross-track snapping to clip edges, markers and playhead, with a user toggle.
- Manual crop rectangle, flip controls and custom rotation pivot.
- Keyframe graph interactions, copy/paste, remove/clear and motion presets.
- Track-level audio gain and stereo pan on video/overlay/audio tracks, with project validation and renderer filters.
- Animated crop X/Y/width/height keyframes for video/image clips, expanded easing functions and Studio motion presets.
- 52 unique registered editing operations: the 34-tool Stable baseline, eight original Studio additions and seven Task 2–3 additions.

## Stage 1 task status

### Task 1 — Project saving, autosave, crash recovery and cross-device lifecycle

**Implemented; automated acceptance checks pass.**

- The renderer saves the initialized project and bounded undo/redo history before AI planning.
- Each validated edit transaction is checkpointed to the server before the separate video-export transaction begins.
- Runner exceptions preserve the latest in-memory project revision and history in the failure callback.
- Projects with checkpoints are discoverable while a job is running or failed.
- A failed project can be reopened and edited again from its last saved revision; manual edits, AI edits, project renaming and media import accept failed jobs only when a saved checkpoint exists.
- Server-side project listing and open-by-ID provide cross-device access when the same Worker and API token are used. The last-opened shortcut is local to each browser/device.
- Revision-guarded writes protect against stale concurrent edits.

Automated tests cover checkpoint persistence, failed-checkpoint discovery, and resuming a manual edit from a failed project. A live two-device browser test remains unperformed because this branch is intentionally test-only and has no production Worker deployment configuration.

### Task 2 — Media management

**Implemented; automated Python, Worker and Studio UI checks pass.**

- Image/video thumbnails are generated in the browser as small JPEG previews.
- Audio waveforms are generated as 96 normalized peak samples for supported files up to 8 MiB.
- Preview metadata is validated, saved against the expected project revision and preserved in the canonical project document. Preview generation is optional and cannot invalidate a successful media import.
- Media relinking validates type, extension, size, duration and expected revision. It replaces the private stored source while preserving the existing asset ID, so timeline references remain intact.
- The media bin displays available previews and exposes relinking.
- .SRT and .VTT imports create phrase-timed text clips on an unlocked text track. The importer does not transcribe audio; it validates timestamp format, cue order, non-overlap, file size and cue count before applying the edit.

Known limits: waveform generation is skipped for audio files larger than 8 MiB or when browser audio decoding is unavailable. Preview generation is best-effort. Subtitle files are limited to 1 MiB and 500 cues per import.

### Task 3 — Timeline editing

**Implemented; automated Python and Studio UI checks pass.**

- Ripple overwrite replaces a clip source and shifts following clips on that track by the duration difference. It rejects incompatible media, unsupported animated speed curves, invalid source duration and overlaps.
- Cross-track ripple insert shifts later clips on the explicitly selected unlocked tracks. All affected tracks are validated before mutation; locked tracks and clips crossing the insertion point are rejected without partial edits.
- Linked groups move across tracks together. Group movement is validated atomically, and group membership remains valid through split, delete, ungroup and track removal.
- Markers support add, move/rename, remove and playhead navigation.
- Snapping considers the playhead, markers and clip edges across unlocked tracks, using a 150 ms threshold and a Studio toggle.

Automated tests cover ripple insert/overwrite, locked-track and incompatible-source rejection, group movement and cleanup, marker lifecycle, subtitle cue validation and creation, project metadata validation, and UI wiring.

### Task 4 — Track-level audio routing

**Implemented in the lab; automated acceptance checks pass in GitHub Actions run #61.**

- Video, overlay and audio tracks can store gain in dB (-96 to +24) and stereo pan (-1 left to +1 right).
- Track mix settings are saved with the canonical project and validated. Text tracks reject audio-routing settings.
- The MLT renderer applies track volume and panning filters to audio-bearing video/audio clips. Neutral settings avoid unnecessary filters; unavailable required filters fail clearly.

### Task 5 — Animation and crop keyframes

**Implemented in the lab; automated acceptance checks pass in run #106.**

- Crop X/Y/width/height can be animated on video and image clips.
- The MLT adapter samples animated crop geometry into affine transform keyframes and checks each sampled crop rectangle against the source frame.
- Animated crop requires source dimensions and cannot be combined with automatic framing or playback-speed ramp keyframes in this adapter stage.
- Added quadratic, cubic, quartic and smoothstep easing, plus Studio zoom-out, pan-left/right and animated crop-reveal presets.


### Task 6 — Audio extraction, freeze-frame and durable generated-media storage

**Implemented; automated acceptance checks pass in GitHub Actions run #104.**

- `media.extract_audio` creates verified M4A, MP3 or WAV project assets using FFmpeg/FFprobe.
- `timeline.create_freeze_frame` extracts a real PNG and inserts an image hold on an unlocked overlay track.
- Generated audio/still assets are uploaded as private Release assets, with IDs checkpointed in the project and undo/redo history.
- Runner recovery downloads assets referenced by the current project and history. Upload failures clean up partial uploads and do not persist dead IDs.
- The real MLT freeze-frame test renders a blue base with a red still overlay, then decodes output frames before, during and after the hold to verify the visible pixels.

### Task 7 — Pitch-preserving speed changes

**Implemented; real-render acceptance test passes in run #104.**

- The MLT render path avoids an extra `warp_pitch` correction that produced a 220.5 Hz tone from a 440 Hz source.
- The integration test renders a 2x-speed clip and measures the output tone near 440 Hz.
- The render output remains on the stable 48 kHz audio clock.

### Task 8 — Edited-composite preview

**Implemented; Studio UI acceptance tests pass in run #106.**

- The Studio player starts with source footage while a render is queued or running.
- Once the Worker reports a completed render, the player authenticates to the Worker and receives a short-lived signed URL for the private rendered MP4.
- The player switches to the edited-composite output and labels the revision. A later edit switches back to source footage while rendering.
- The ordinary download action remains separate from the preview player.

### Task 9 — Proxy media and low-resolution preview

**Implemented and verified in GitHub Actions run #118.**

- Added `media.create_proxy` for video assets, producing an H.264 MP4 proxy at a maximum of 640×360 while preserving the original file and duration.
- Proxy generation rejects missing/invalid sources, duplicate proxies, projects at the 100-asset limit, output above 50 MB and sources longer than 30 minutes. Partial files are removed on failure.
- Proxies are normal generated project assets and use the existing private Release upload/checkpoint path. MP4 is now an explicitly supported generated-asset MIME type (`video/mp4`).
- Studio media cards expose proxy generation and identify existing proxies. Source preview can use the stored proxy for the selected video clip; the edited-composite preview remains separate.
- The Worker provides authenticated signed-URL lookup for project media assets. The original source remains unchanged and is used for final export.

### Task 10 — Complete 52-operation edge-case audit

**Offline audit complete; GitHub Actions run #118 passed.**

- 52 unique operations have executor dispatch references.
- The shared audit tests check closed schemas, required fields, numeric boundaries, unknown arguments, malformed track-ID arrays and confirmation gates.
- A stale-revision rejection check runs against all 52 operations.
- Transaction tests verify that a later failing operation rolls back an earlier valid change, and that undo/redo restore project state as separate revisions.
- Feature/subsystem tests cover supported operation behaviour; generated-media integration tests cover MLT freeze-frame rendering, pitch-preserving speed, audio extraction and proxy creation/storage.
- This is offline acceptance evidence. It does not claim every possible parameter combination has been tested or prove a live Worker deployment.


## Remaining Stage 1 production acceptance gate

- Successful end-to-end hosted tests against the actual Worker/renderer configuration, including a real private Release upload and Worker checkpoint. Deployment remains gated on explicit user authorization. Tasks 1–10 are complete at the offline implementation and CI level.

Optical-flow slow motion remains optional and gated. It must not introduce a paid dependency or hidden fallback.

## Validation rules
- The 118-entry catalogue is the product capability target, not 118 implemented tools.
- The original 42 registered operations remain part of the expanded full-audit set. The current 52-operation registry has passed the offline schema, revision, transaction, confirmation and feature-test audit.
- Run Python, Node, Worker/UI and generated-media MLT tests on this public lab branch.
- Do not merge into Stable or deploy a Worker as part of this lab setup.
- Stage 1 offline implementation is complete. Do not claim production acceptance until the hosted Worker-to-runner test is completed after explicit deployment authorization.
