# Task 6 — Audio Extraction, Freeze-Frame and Persistence

**Repository:** `promiseoluo66-cmyk/northgate-realty-demo`  
**Working branch:** `video-editor-lab`  
**Status:** **IMPLEMENTED — AUTOMATED ACCEPTANCE TESTS PASS**  
**Last implementation commit before this report:** `5d24e6fc6ee475e66353fb452a9a250a02fe7d87`  
**Successful full CI run:** [#90 — 45876486322](https://github.com/promiseoluo66-cmyk/northgate-realty-demo/actions/runs/45876486322)

## Delivered

### Audio extraction

- Added registered operation `media.extract_audio`.
- Extracts the first audio stream from a project video as M4A, MP3 or WAV using FFmpeg.
- Uses FFprobe to confirm an audio stream and positive output duration.
- Registers a new project audio asset with a unique ID, filename, storage key, byte size and duration.
- Rejects videos without audio, missing source files and filename collisions.
- Removes partial output when FFmpeg fails.

### Freeze-frame and hold

- Added registered operation `timeline.create_freeze_frame`.
- Extracts a real PNG still at a validated source timestamp.
- Adds the still as an image clip on an unlocked overlay track for the requested timeline duration.
- Rejects timestamps outside the source duration and invalid targets.
- The generated image is a normal project asset, not a temporary placeholder.

### Permanent generated-media storage

- Generated audio and still images are uploaded as GitHub Release assets.
- The returned Release asset IDs are attached to project asset records before the project checkpoint is sent to the Worker.
- The runner downloads media referenced by the current project and undo/redo history when a later job starts.
- Uploads are bounded by the 50 MB per-file and 200 MB project media limits.
- Multi-asset upload failure deletes already-uploaded assets and does not attach dead Release IDs.
- Both the Worker and runner now check that the configured GitHub storage repository is private before uploading. Uploads fail closed if the repository is public or its privacy cannot be verified.

### Undo, redo and recovery

- Audio extraction and freeze-frame insertion are project transactions.
- Undo removes generated assets/clips from the active project.
- Redo restores their project references.
- Release IDs are retained in current and history snapshots.
- Worker checkpoint tests verify that generated Release asset IDs and history are saved together.

## Verification

Successful full CI run #90 tested commit `5d24e6fc6ee475e66353fb452a9a250a02fe7d87`.

| Check | Result |
|---|---:|
| Python editor, executor, registry, catalogue and MLT tests | **257 passed** |
| Node Worker and Studio tests | **46 passed, 0 failed, 0 skipped** |
| D1 migrations applied to in-memory SQLite | **Passed** |
| Complete GitHub Actions workflow | **Passed** |

### Actual MLT freeze-frame render

The suite includes an end-to-end render test using the installed MLT Python API and FFmpeg:

1. Creates a blue base video and a separate red source video.
2. Runs the freeze-frame operation to extract a red still.
3. Adds it as a 1.5-second overlay hold.
4. Renders the project through `render_project`.
5. Decodes output pixels to verify blue before the hold, red during the hold at 1.25s and 2.4s, and blue after the hold.

This test passed in CI run #90.

### Persistence and failure tests

Automated tests cover:
- Private Release upload request format and MIME type.
- Refusal to upload to a public repository.
- Generated asset Release ID registration.
- Runner callback payload containing the project and undo/redo history.
- Worker callback persistence of generated asset references and history.
- Re-download of assets referenced by redo history.
- Failed multi-file upload cleanup.
- Project storage cap enforcement.
- Missing source, no-audio source, partial FFmpeg output cleanup and no-overwrite behavior.

These use mocked GitHub network calls and the Worker test harness. They do not constitute a live upload to the configured private repository or a live deployed Worker checkpoint.

## Live deployment verification — not performed

No Cloudflare Worker was deployed and no live GitHub Release asset was uploaded. This remains deliberately pending explicit deployment authorization.

Before live testing, verify that both configurations point to the intended private storage repository:

- Worker: `GITHUB_OWNER` and `GITHUB_REPO`.
- Runner: `GITHUB_OWNER` and `GITHUB_REPOSITORY_NAME`.

The code now rejects a public storage repository, protecting generated media from accidental public exposure. The public code repository itself must not be used as the media-storage repository.

Once deployment is explicitly authorized, the remaining live acceptance is:
1. Confirm the configured storage repository is private.
2. Deploy the Worker and run one controlled test job.
3. Verify the generated audio and PNG appear as private Release assets.
4. Verify the Worker checkpoint stores their Release IDs and history.
5. Start a later runner job and verify it downloads and renders those assets.
6. Remove the test job and test assets safely.

## Repository safety

- All changes remain on `video-editor-lab`.
- `main` remains untouched.
- No public media links were created.
- No Worker deployment was performed.

**Conclusion:** Task 6's code and automated acceptance tests are implemented and passing. Only the live private GitHub Release and deployed Worker round-trip remains pending explicit authorization.
