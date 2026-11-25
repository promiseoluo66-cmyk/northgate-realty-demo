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

## Current Stage 1 gaps
- Automatic background autosave, crash recovery and cross-device project lifecycle.
- Media thumbnails/waveforms, relinking and subtitle import.
- Ripple overwrite, cross-track ripple insert, linked clips/groups, persistent markers and broader snapping.
- Full track-level audio routing and crop keyframes.
- More animation presets, interpolation/render precision tests and coordinated speed/audio handling.
- Audio extraction, freeze-frame/hold sections and pitch-preserving speed changes.
- Edited-composite preview, proxy media and low-resolution preview.
- End-to-end acceptance against the actual Worker/renderer configuration.

See [STUDIO_FOUNDATION_STATUS.md](architecture/STUDIO_FOUNDATION_STATUS.md) and [MASTER_CAPABILITY_AUDIT.md](architecture/MASTER_CAPABILITY_AUDIT.md) for the detailed status and 118-capability catalogue.
