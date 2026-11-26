# Independent AI Video Editor — Stage 1 Lab

This folder contains the independently implemented video editor prototype and its Stage 1 mobile Studio foundation.

## Lab safety
- Work is isolated to the video-editor-lab branch.
- The repository's main branch and Northgate Realty demo files are unchanged.
- This branch is for source review and automated testing only; it has no production deployment configuration.
- Production database identifiers, deployment workflows and provider credentials are intentionally excluded.
- Automated tests must not call paid services or deploy infrastructure.

## Stage 1 scope
Mobile Studio and editing foundation: multi-track timeline, media bin, clip inspector, crop/framing, keyframes, track management, project history and editing operations.

The implementation currently has 49 unique registered operations (the original 42 plus seven Stage 1 Task 2–3 operations). The separate product catalogue contains 118 capability entries; these numbers are not interchangeable.

## Run tests locally
From the video-editor folder:

    python -m pip install -r requirements-dev.txt
    python -m pytest tests -q

For Worker/UI tests:

    cd cloudflare
    node --check public/studio.js
    node --check src/index.js
    node --test tests/*.test.mjs

The GitHub Actions workflow on this branch runs the automated checks on GitHub-hosted runners. A green run is required before Stage 1 can be accepted.

## Stage 1 — Task 1: project lifecycle

**Status: implemented; automated acceptance checks pass.**

- The initial validated project is saved to the server as soon as the renderer initializes it.
- Every successful edit transaction is checkpointed, including its revision and undo/redo history, before video export begins.
- If rendering or output upload fails, the runner reports its latest in-memory project and history so the last successful edit remains recoverable.
- Running jobs with checkpoints appear in the saved-project list as read-only while the renderer is active.
- Failed jobs with checkpoints can be reopened, renamed, receive imported media, and continue with another manual or AI edit.
- Projects are stored server-side and listed through the authenticated API, so another device using the same Worker and API token can reopen them. The last-opened job shortcut remains device-local.
- Revision checks prevent stale devices from silently overwriting a newer project revision.

Automated validation covers checkpoint persistence, failed-project listing, and resuming manual edits. A live two-device browser test is not claimed: this branch intentionally has no production Worker deployment configuration.

## Stage 1 — Task 2: media management

**Status: implemented; automated Python, Worker and Studio UI checks pass.**

- Browser-side preview generation creates small JPEG thumbnails for images and video, and 96-peak audio waveforms for supported audio files up to 8 MiB.
- Preview metadata is validated and saved against the current project revision. Preview generation is optional and does not block a successful media import.
- Media relinking uploads a replacement to private storage and updates the existing asset record, preserving its ID so timeline clips keep their media references.
- Relinking validates media type, extension, file size, duration metadata and expected project revision.
- The media bin exposes the preview, searchable metadata, folders, tags and relinking controls.
- Existing .SRT and .VTT files can be imported into an unlocked text track. The importer uses supplied timestamps; it does not perform speech recognition. Files are limited to 1 MiB and 500 cues per import, and malformed, overlapping or invalid cues are rejected before editing.

Known limits: waveform generation is skipped for audio files larger than 8 MiB or where browser audio decoding is unavailable. Preview generation is best-effort; the original media remains imported if a preview cannot be generated.

## Stage 1 — Task 3: timeline editing

**Status: implemented; automated Python and Studio UI acceptance checks pass.**

- Ripple overwrite replaces a clip's source and shifts later clips on that track by the duration difference. It rejects incompatible media, unsafe duration changes, unsupported animated speed curves and overlapping clips on the target track.
- Cross-track ripple insert inserts at the requested time and shifts later clips on the explicitly selected tracks. It validates every affected track before mutation, rejects locked tracks and clips crossing the insertion point, and avoids partial changes on validation failure.
- Linked clip groups support cross-track movement. Group moves are validated atomically; split, delete, ungroup and track-removal paths maintain valid group membership.
- Timeline markers can be added, moved, renamed, removed and used to position the playhead.
- Snapping considers the playhead, markers and clip edges across unlocked tracks, with a 150 ms snap threshold. It can be disabled in the Studio controls.

Automated acceptance checks cover core ripple operations, locked-track rejection, linked-group movement and cleanup, marker lifecycle, subtitle cue creation and validation, and the mobile Studio wiring.

## Remaining Stage 1 acceptance gaps
1. Full track-level audio routing.
2. Crop keyframes and expanded animation presets/interpolation precision tests.
3. Audio extraction, freeze-frame/hold sections and pitch-preserving speed changes.
4. Edited-composite preview, proxy media and low-resolution preview.
5. End-to-end acceptance against the actual Worker/renderer configuration.

The original 42 registered Studio operations still require the separate full audit: implementation, individual tests, edge cases and editor integration. The current registry has 49 operations, but registration is not proof that every operation is complete.

Optical-flow slow motion remains optional and gated. It must not introduce a paid dependency or hidden fallback. Do not merge into Stable or deploy a Worker as part of this lab setup.

See the architecture/STUDIO_FOUNDATION_STATUS.md and architecture/MASTER_CAPABILITY_AUDIT.md files for the detailed status and 118-capability catalogue.
