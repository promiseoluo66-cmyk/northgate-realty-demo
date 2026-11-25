# Independent AI Video Editor — Stage 1 Lab

This folder contains the independently implemented video editor prototype and its Stage 1 mobile Studio foundation.

## Lab safety
- Work is isolated to the `video-editor-lab` branch.
- The repository's `main` branch and Northgate Realty demo files are unchanged.
- This branch is for source review and automated testing only; it has no production deployment configuration.
- Production database identifiers, deployment workflows and provider credentials are intentionally excluded.
- Automated tests must not call paid services or deploy infrastructure.

## Stage 1 scope
Mobile Studio and editing foundation: multi-track timeline, media bin, clip inspector, crop/framing, keyframes, track management, project history and editing operations.

The implementation currently has 42 unique registered operations. The separate product catalogue contains 118 capability entries; these numbers are not interchangeable.

## Run tests locally
From the `video-editor` folder:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

For Worker/UI tests:

```bash
cd cloudflare
node --check public/studio.js
node --check src/index.js
node --test tests/*.test.mjs
```

The GitHub Actions workflow on this branch runs the automated checks on GitHub-hosted runners. A green run is required before Stage 1 can be accepted.

## Stage 1 — Task 1: project lifecycle

**Status: implemented and automated tests passing.**

- The initial validated project is saved to the server as soon as the renderer initializes it.
- Every successful edit transaction is checkpointed, including its revision and undo/redo history, before video export begins.
- If rendering or output upload fails, the runner reports its latest in-memory project and history so the last successful edit remains recoverable.
- Running jobs with checkpoints appear in the saved-project list as read-only while the renderer is active.
- Failed jobs with checkpoints can be reopened, renamed, receive imported media, and continue with another manual or AI edit.
- Projects are stored server-side and listed through the authenticated API, so another device using the same Worker and API token can reopen them. The last-opened job shortcut remains device-local.
- Revision checks prevent stale devices from silently overwriting a newer project revision.

Automated validation covers checkpoint persistence, failed-project listing, and resuming manual edits. A live two-device browser test is not claimed: this branch intentionally has no production Worker deployment configuration.

## Remaining Stage 1 gaps
- Media thumbnails/waveforms, relinking and subtitle import.
- Ripple overwrite, cross-track ripple insert, linked clips/groups, persistent markers and broader snapping.
- Full track-level audio routing and crop keyframes.
- More animation presets, interpolation/render precision tests and coordinated speed/audio handling.
- Audio extraction, freeze-frame/hold sections and pitch-preserving speed changes.
- Edited-composite preview, proxy media and low-resolution preview.
- End-to-end acceptance against the actual Worker/renderer configuration.

See [STUDIO_FOUNDATION_STATUS.md](architecture/STUDIO_FOUNDATION_STATUS.md) and [MASTER_CAPABILITY_AUDIT.md](architecture/MASTER_CAPABILITY_AUDIT.md) for the detailed status and 118-capability catalogue.
