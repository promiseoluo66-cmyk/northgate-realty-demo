# Task 6 — Audio Extraction and Freeze-Frame Implementation Report

**Repository:** `promiseoluo66-cmyk/northgate-realty-demo`  
**Working branch:** `video-editor-lab`  
**Report date:** 26 November 2026  
**Implementation status:** **IMPLEMENTED ON THE WORKING BRANCH — FULL REGRESSION RERUN PENDING**  
**Current working branch HEAD at report update:** `fdd305615619541b7b01f63ee37a179e1355969a`  
**Latest Task 6 CI evidence:** run #74, ID `45873752276`, executed 252 Python tests: 251 passed and one capability-catalogue count assertion failed because the catalogue still expected 49 operations. That count was corrected to 51 in commit `fdd305615619541b7b01f63ee37a179e1355969a`. Run #76, ID `45873968405`, is queued for the corrected full regression. The Task 6 feature tests were among the 251 passing tests in run #74.

## 1. Scope and safety decisions

Task 6 covers:

1. Extracting the audio stream from a project video into a separate project audio asset.
2. Creating a freeze-frame/hold section from a selected source frame for a specified timeline duration.
3. Persisting generated media so it remains available after the GitHub Actions runner shuts down.
4. Keeping generated assets consistent with project revisions and undo/redo.
5. Verifying success and failure cases with automated tests and generated-media checks.

Implementation constraints:

- All code changes must stay on `video-editor-lab`.
- The repository's `main` branch must remain untouched.
- Reuse the existing FFmpeg/FFprobe, project asset model, project executor, and history system.
- Generated media must remain private in the existing private GitHub Release asset storage.
- Do not deploy the Cloudflare Worker, publish generated media, or expose public download links.
- A feature is not complete merely because code exists or source inspection looks correct. Completion requires tests that exercise the generated media, persistence/reload path, and undo/redo behaviour.
- Do not add duplicate operations if an existing registered operation can safely support the capability. If new registered operations are necessary, update the registry count and the audit deliberately.

## 2. Verified baseline

At the last inspection:

- The tool registry contains 49 unique operations. It includes audio analysis, gain and fade operations, but no dedicated audio-extraction or freeze-frame operation.
- The project model supports `video`, `image`, `audio` and `font` assets, and video/image/audio timeline clips.
- `ProjectToolExecutor` already accepts a guarded asset directory, applies project edits transactionally, and keeps bounded undo/redo snapshots.
- FFmpeg and FFprobe are already used for media analysis and validation.
- The runner downloads project assets from private GitHub Release assets using each asset's `release_asset_id`.
- The runner currently uploads the final rendered MP4 to the job's private Release and sends project JSON and history snapshots to the Worker callback.
- The Worker already has a private media-relink upload route. That route replaces an existing asset; it is not a general generated-asset creation route.
- No complete generated-asset upload-and-register path was found in the inspected runner/Worker flow.
- The current CI workflow installs FFmpeg, FFprobe and MLT on Ubuntu 24.04 and runs the Python, Node/Worker/UI and offline D1 migration tests.

These are source-inspection findings, not proof that Task 6 works. No Task 6 implementation or Task 6 test has been run.

## 3. Required implementation design

### 3.1 Audio extraction

The implementation must:

- Accept a valid project video asset and a supported output audio format.
- Use FFmpeg with an explicit audio-stream map so the correct source stream is selected.
- Fail clearly if the source is missing, invalid, or has no audio stream.
- Probe the generated file with FFprobe and verify it contains an audio stream and a positive duration.
- Write to a safe temporary path, reject empty output, avoid overwriting existing assets, and clean up partial files on failure.
- Register the result as a new project audio asset with a unique ID, safe storage key, filename, byte size, duration and private storage reference.
- Preserve project revision and undo/redo integrity.

### 3.2 Freeze-frame / hold section

The implementation must:

- Identify the source video, source timestamp/frame and requested hold duration.
- Validate that the source exists and that the selected timestamp is within its readable video duration.
- Produce a real still image or an equivalently verifiable freeze-frame render path; a metadata-only placeholder is not acceptable.
- Register or reference the still through the existing project image-asset model.
- Create a timeline image/hold clip with the requested duration and correct placement.
- Verify the still can be rendered by the existing MLT renderer.
- Reject invalid timestamps, invalid durations and missing source files without partially changing the project.

### 3.3 Private generated-asset persistence

This is a required part of Task 6, not optional cleanup.

The current runner can download private Release assets and upload the final MP4, but its inspected flow does not provide a complete path for uploading a newly generated audio/image asset and registering its Release asset ID in the saved project.

Before either feature can be called complete, implement and test a secure generated-asset persistence path that:

- Uploads generated media to the existing private job Release.
- Records the returned Release asset ID, storage key, filename, media type, byte size and duration in the project asset record.
- Enforces the existing per-file and per-project size limits.
- Commits project JSON, revision and history consistently.
- Deletes an uploaded Release asset if the associated project update fails.
- Allows a later runner session to download the generated asset and render the project.
- Does not make the Release public or deploy the Worker.

The exact API boundary must follow the existing callback and private media-storage architecture. Do not assume that a temporary runner file or a project JSON reference alone makes generated media persistent.

### 3.4 Undo, redo and recovery

Tests must prove that:

- Adding the generated asset and its timeline clip is one atomic, undoable edit transaction where appropriate.
- Undo removes the asset/clip from the active project state.
- Redo restores valid references to the same persisted media.
- Saving and reloading the project preserves the generated asset metadata and history.
- A failed FFmpeg process, failed upload or failed project checkpoint does not leave a broken project reference.
- Cleanup of unreferenced private Release assets is handled safely; do not delete an asset still referenced by the current project or its supported history.

## 4. Test and acceptance checklist

Task 6 cannot be marked complete until all applicable checks below pass.

### Audio extraction
- [x] Extract audio from a valid video containing audio.
- [x] Confirm output is non-empty and FFprobe reports an audio stream.
- [x] Confirm duration and expected stream selection.
- [x] Reject a video with no audio stream.
- [ ] Reject missing/corrupt source media and invalid format/options.
- [ ] Simulate FFmpeg failure and verify partial output cleanup.
- [ ] Verify duplicate names do not overwrite existing assets.

### Freeze-frame / hold
- [x] Extract a still at a known source timestamp.
- [x] Verify the generated image is readable and has expected dimensions.
- [x] Insert a hold clip with the requested duration.
- [ ] Render a test project and inspect the resulting frames around the hold.
- [ ] Reject timestamps outside the source duration and invalid durations.
- [ ] Verify missing/corrupt input and render failures do not partially mutate the project.

### Persistence and history
- [x] Implement private Release upload for generated audio and image assets (mocked upload acceptance test).
- [x] Verify project records contain Release asset IDs and safe storage keys.
- [x] Verify current/undo/redo history assets are included in runner media hydration (mocked download test).
- [x] Verify undo and redo preserve generated asset references.
- [x] Verify failed multi-asset upload cleanup and no dangling Release IDs (mocked upload failure test). Checkpoint failure/live Worker conflict path remains unverified without a deployed Worker.
- [ ] Verify project storage limits are enforced.

### Full regression
- [ ] Run all Python tests on the corrected 51-operation catalogue (queued in CI run #76).
- [ ] Run all Node, Worker and Studio UI tests on the corrected branch.
- [ ] Run D1 migration validation on the corrected branch.
- [ ] Run generated-media MLT integration tests.
- [ ] Run the complete GitHub Actions workflow on `video-editor-lab`.
- [ ] Inspect the actual run result and relevant logs.
- [ ] Update the 49-operation audit if the registry or editor integration changes.

## 5. Current blockers and open engineering work

1. Complete the corrected full GitHub Actions regression and fix any failures.
2. Add a rendered MLT acceptance test proving the still image remains visible for the full hold duration.
3. Add an explicit partial-FFmpeg-output cleanup test.
4. Verify the live Worker checkpoint and Release upload path when a Worker deployment is explicitly authorized; no Worker has been deployed.

## 6. Change log

| Date | Change | Evidence |
|---|---|---|
| 26 Nov 2026 | Created this Task 6 report after inspecting the current branch, project model/executor, tool registry, runner, Worker media routes and CI workflow. | Branch HEAD `b1f4d5a`; report status explicitly remains NOT STARTED. |

## 7. Completion rule

**Task 6 remains OPEN until every required implementation and acceptance check is completed and verified.** Do not infer completion from source references, a successful unrelated CI run, or the existence of a generated file on a temporary runner.

All work remains confined to `video-editor-lab`. The `main` branch and deployed Worker remain untouched.


## 8. Implementation change log

| Change | Commit |
|---|---|
| Registered `media.extract_audio` and `timeline.create_freeze_frame`; implemented FFmpeg extraction, still generation, image hold clips, and executor persistence metadata attachment. | `579e03fa` / `98f9f93e` |
| Added private generated-media Release upload, cleanup on upload failure, 200 MB project media limit enforcement, and history-aware asset hydration. | `c652303e` / `513dfc38` / `5290104d` |
| Added generated-media, undo/redo, private-storage and failure-path tests. | `aacbf71e` / `84867cec` / `9816c5a0` |
| Updated operation inventory and capability catalogue from 49 to 51. | `bc1032a8` / `fdd30561` |
