# Stage 1 — Mobile Studio and Editing Foundation

**Lab branch:** `video-editor-lab`  
**Repository:** `promiseoluo66-cmyk/northgate-realty-demo`  
**Status:** Task 1 is complete in the isolated lab; the remaining acceptance gaps are listed below.

## Implemented in this snapshot
- Responsive mobile Studio workspace with multi-track timeline, ruler, zoom, clip selection and inspector.
- Source-video preview, pointer/touch clip move and trim, cross-track drop targets and near-edge snapping.
- Direct move, trim, slip, split, duplicate, delete, source replacement, insert-and-ripple, speed, framing, transform, keyframes, profile, track operations, undo and redo.
- Project open/list/rename APIs, revision checks and bounded undo/redo history.
- Track add, rename, reorder, lock, enable, mute, solo, hide/show and remove operations.
- Multi-file media import, project media bin, filename/type/folder/tag search, folder assignment and insertion at playhead.
- Manual crop rectangle, flip controls and custom rotation pivot.
- Keyframe graph interactions, copy/paste, remove/clear and motion presets.
- 49 unique registered editing operations: the 34-tool Stable baseline, eight original Studio additions and seven Task 2–3 additions.

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

## Remaining Stage 1 acceptance gaps
1. Media thumbnails/waveforms, relinking and subtitle-file import.
2. Ripple overwrite, cross-track ripple insert, groups/linked clips, persistent markers and broader snapping.
3. Full track-level audio routing.
4. Crop keyframes and expanded animation presets/interpolation precision tests.
5. Audio extraction, freeze-frame/hold sections and pitch-preserving speed changes.
6. Edited-composite preview, proxy media and low-resolution preview.
7. Successful end-to-end hosted tests against the actual Worker/renderer configuration.

Optical-flow slow motion remains optional and gated. It must not introduce a paid dependency or hidden fallback.

## Validation rules
- The 118-entry catalogue is the product capability target, not 118 implemented tools.
- The original 42 registered operations remain the required full-audit set. The registry now contains 49 unique operations after seven Task 2–3 additions; all 49 must be included in the final audit.
- Run Python, Node, Worker/UI and generated-media MLT tests on this public lab branch.
- Do not merge into Stable or deploy a Worker as part of this lab setup.
- Do not mark Stage 1 complete until all required acceptance gaps are resolved or explicitly deferred with user approval.
