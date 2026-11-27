import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const htmlUrl = new URL("../public/index.html", import.meta.url);
const scriptUrl = new URL("../public/studio.js", import.meta.url);
const [html, studioScript] = await Promise.all([
  readFile(htmlUrl, "utf8"),
  readFile(scriptUrl, "utf8")
]);

test("Studio loads the separate mobile editor script", () => {
  assert.match(html, /<script src="\/studio\.js" defer><\/script>/);
});

test("Studio controls have unique element IDs", () => {
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
  assert.ok(ids.includes("studio-editor"));
  assert.ok(ids.includes("timeline-canvas"));
  assert.ok(ids.includes("studio-media-bin"));
  assert.ok(ids.includes("studio-clip-inspector"));
  assert.match(html, /aria-controls="studio-timeline-view"/);
  assert.match(html, /aria-controls="studio-media-view"/);
  assert.match(html, /aria-labelledby="studio-tab-timeline"/);
  assert.match(html, /aria-labelledby="studio-tab-media"/);
  assert.equal(ids.length, new Set(ids).size, "HTML element IDs must not be duplicated");
});

test("Timeline, media bin, zoom and clip selection are wired", () => {
  assert.match(studioScript, /project\.tracks/);
  assert.match(studioScript, /track\.clips/);
  assert.match(studioScript, /currentProject\.assets/);
  assert.match(studioScript, /timeline-zoom/);
  assert.match(studioScript, /selectedClipId/);
  assert.match(studioScript, /studioSelectedClipInstruction/);
});

test("Project strings are inserted as text, not executable HTML", () => {
  assert.match(studioScript, /textContent/);
  assert.doesNotMatch(studioScript, /\.innerHTML\s*=/);
});

test("Current approval-aware project and AI edit routes remain connected", () => {
  assert.match(html, /\/api\/v1\/jobs\/\x22\+activeJobId\+\x22\/project/);
  assert.match(html, /\/api\/v1\/jobs\/\x22\+activeJobId\+\x22\/ai-edit/);
  assert.match(html, /ai-edit\/confirm/);
});

test("Studio switches from source footage to the authenticated edited-composite preview after render", () => {
  assert.match(html, /id="studio-preview-caption"/);
  assert.match(html, /loadCompositePreview\(data\.project_revision\|\|0\)/);
  assert.match(html, /jobs.*download/);
  assert.match(html, /video\.dataset\.previewMode="composite"/);
  assert.match(html, /Edited-composite preview/);
  assert.match(html, /loadSourcePreview\(true\)/);
});

test("Studio exposes real source preview, playhead and direct editing controls", () => {
  for (const id of [
    "studio-preview", "timeline-seek", "playhead-time",
    "studio-media-files", "studio-import-media", "studio-import-status", "media-bin-search", "media-bin-folder-filter",
    "studio-safe-guides-toggle", "studio-safe-guides", "open-project-id", "studio-open-project",
    "studio-move-clip", "studio-trim-clip", "studio-slip-clip", "clip-slip-offset", "studio-apply-speed",
    "studio-split-clip", "studio-duplicate-clip", "studio-delete-clip",
    "studio-apply-framing", "studio-apply-transform", "studio-add-keyframe",
    "studio-add-track", "studio-rename-track", "studio-lock-track",
    "studio-remove-track", "studio-set-profile", "studio-reorder-track", "track-order", "studio-undo", "studio-redo",
    "studio-toggle-track-visible",
    "clip-crop-x", "clip-crop-y", "clip-crop-width", "clip-crop-height",
    "studio-apply-crop", "studio-reset-crop",
    "clip-flip-horizontal", "clip-flip-vertical", "clip-anchor-x", "clip-anchor-y",
    "keyframe-graph", "keyframe-graph-zoom", "keyframe-graph-pan",
    "studio-remove-keyframe", "studio-reset-keyframes", "studio-reset-all-keyframes",
    "rename-project-name", "studio-rename-project", "saved-project-list",
    "refresh-saved-projects", "saved-project-status", "studio-copy-keyframes", "studio-paste-keyframes",
    "studio-apply-motion-preset", "studio-text-shadow-blur"
  ]) assert.match(html, new RegExp('id="' + id + '"'));
  assert.match(studioScript, /setPlayhead/);
  assert.match(studioScript, /setPointerCapture/);
  assert.match(studioScript, /timeline\.move_clip/);
  assert.match(studioScript, /timeline\.trim_clip/);
  assert.match(studioScript, /animation\.set_keyframe/);
  assert.match(studioScript, /animation\.clear_keyframes/);
  assert.match(studioScript, /dataset.nextTime/);
  assert.match(studioScript, /window\.applyStudioOperations/);
});

test("Direct Studio editing uses authenticated manual operation and source preview routes", () => {
  assert.match(html, /\/manual-edit/);
  assert.match(html, /\/source-url/);
  assert.match(html, /expected_revision/);
  assert.match(html, /confirmed_tools/);
  assert.match(studioScript, /studio-preview/);
  assert.match(studioScript, /studioSelectedClipInstruction/);
});

test("Keyframe graph supports editing, clipboard and motion presets", () => {
  assert.match(studioScript, /renderKeyframeGraph/);
  assert.match(studioScript, /setPointerCapture/);
  assert.match(studioScript, /animation\.remove_keyframe/);
  assert.match(studioScript, /keyframeClipboard/);
  assert.match(studioScript, /fade_in/);
  assert.match(studioScript, /speed_ramp/);
});

test("Task 2 media previews, relinking and subtitle import are wired", () => {
  assert.match(studioScript, /thumbnail_data_url/);
  assert.match(studioScript, /waveform.samples/);
  assert.match(studioScript, /\/relink/);
  assert.match(html, /captions.import_subtitles/);
  assert.match(html, /\.SRT or \.VTT/);
});

test("Task 3 linked groups, cross-track ripple, markers and snapping are wired", () => {
  assert.match(studioScript, /timeline\.ripple_overwrite_clip/);
  assert.match(studioScript, /ripple_track_ids/);
  assert.match(studioScript, /timeline\.group_clips/);
  assert.match(studioScript, /timeline\.ungroup_clips/);
  assert.match(studioScript, /timeline\.move_marker/);
  assert.match(studioScript, /timeline\.add_marker/);
  assert.match(studioScript, /timeline\.remove_marker/);
  assert.match(studioScript, /snapStart/);
});

test("Track reorder is wired to a registered editor operation", () => {
  assert.match(html, /id="studio-reorder-track"/);
  assert.match(studioScript, /track\.reorder/);
});

test("Project media import and searchable media-bin placement are wired", () => {
  assert.match(html, /multiple accept="video/);
  assert.match(html, /\/assets/);
  assert.match(html, /200 MB total/);
  assert.match(studioScript, /studioAddMediaAtPlayhead/);
  assert.match(studioScript, /media-bin-search/);
  assert.match(studioScript, /timeline\.add_clip/);
});

test("Track solo control is connected to registered track state", () => {
  assert.match(html, /id="studio-toggle-track-solo"/);
  assert.match(studioScript, /solo:!Boolean\(track\.solo\)/);
  assert.match(studioScript, /track\.type === "text"/);
});

test("Saved-project manager lists, reopens and revision-safely renames projects", () => {
  assert.match(html, /\/api\/v1\/projects/);
  assert.match(html, /method:"PATCH"/);
  assert.match(html, /expected_revision/);
  assert.match(html, /openProjectById/);
  assert.match(html, /renderSavedProjects/);
  assert.match(html, /saved-project-list/);
});

test("Media bin supports persisted folders, searchable tags and folder filtering", () => {
  assert.match(studioScript, /media\.organize_asset/);
  assert.match(studioScript, /asset\.folder/);
  assert.match(studioScript, /asset\.tags/);
  assert.match(studioScript, /media-bin-folder-filter/);
  assert.match(studioScript, /Save folder and tags/);
});

test("Manual source crop is wired to the registered crop operation", () => {
  assert.match(studioScript, /clip\.set_crop/);
  assert.match(studioScript, /studio-apply-crop/);
  assert.match(studioScript, /studio-reset-crop/);
  assert.match(studioScript, /clip-crop-width/);
  assert.match(html, /Applying a crop clears automatic Fit\/Fill\/Stretch framing first/);
  assert.match(html, /Manual crop uses percentages of the original source frame/);
});

test("Clip flip controls are persisted and rendered with MLT flip filters", () => {
  assert.match(html, /id="clip-flip-horizontal"/);
  assert.match(html, /id="clip-flip-vertical"/);
  assert.match(studioScript, /flip_horizontal:Boolean/);
  assert.match(studioScript, /flip_vertical:Boolean/);
});

test("Custom rotation pivot controls are bound to persisted transform fields", () => {
  assert.match(html, /id="clip-anchor-x"/);
  assert.match(html, /id="clip-anchor-y"/);
  assert.match(studioScript, /anchor_x:numeric\("clip-anchor-x"\)\/100/);
  assert.match(studioScript, /anchor_y:numeric\("clip-anchor-y"\)\/100/);
});

test("Track visibility is independent from mute and connected to render state", () => {
  assert.match(html, /id="studio-toggle-track-visible"/);
  assert.match(studioScript, /visible:track\.visible===false/);
  assert.match(studioScript, /HIDDEN/);
  assert.match(studioScript, /Audio tracks do not have a visual layer/);
});

test("Media-bin source replacement is guarded and uses the registered operation", () => {
  assert.match(studioScript, /Replace selected clip source/);
  assert.match(studioScript, /timeline\.replace_clip_media/);
  assert.match(studioScript, /selected\.clip\.kind !== asset\.media_type/);
  assert.match(studioScript, /selected\.track\.locked/);
  assert.match(studioScript, /preserving its timeline position/);
});

test("Studio slip control sends signed source-window offsets", () => {
  assert.match(studioScript, /timeline\.slip_clip/);
  assert.match(studioScript, /clip-slip-offset/);
  assert.match(studioScript, /delta_us:deltaUs/);
  assert.match(studioScript, /non-zero slip offset/);
});

test("Media-bin ripple insert is wired to the current playhead and selected compatible track", () => {
  assert.match(studioScript, /Insert & ripple/);
  assert.match(studioScript, /timeline\.ripple_insert_clip/);
  assert.match(studioScript, /start_us:Math\.max\(0, Math\.round\(playheadUs\)\)/);
  assert.match(studioScript, /targetTrack\.id/);
  assert.match(studioScript, /renderMediaBin\(\);/);
});


test("Studio restores the latest saved project checkpoint while a cloud edit is running", () => {
  assert.match(html, /let loadedProjectRevision=0/);
  assert.match(html, /loadedProjectRevision=Number\(data\.revision\)/);
  assert.match(html, /if\(data\.project_revision&&Number\(data\.project_revision\)!==loadedProjectRevision\)/);
  assert.match(html, /A saved checkpoint can be reopened while a cloud edit is still running/);
});


test("Failed renders with saved checkpoints remain editable for recovery", () => {
  assert.match(html, /data\.status==="failed"\)\&\&data\.project_revision/);
  assert.match(html, /Recovery checkpoint available/);
  assert.match(html, /project\.status\|\|"saved"/);
});


test("Stage 1 Tasks 4 and 5 expose track audio routing and animated crop controls", () => {
  assert.match(html, /id="track-audio-gain"/);
  assert.match(html, /id="track-audio-pan"/);
  assert.match(studioScript, /audio_gain_db:numeric\("track-audio-gain"\)/);
  assert.match(studioScript, /audio_pan:numeric\("track-audio-pan"\)/);
  assert.match(studioScript, /crop_reveal/);
  assert.match(studioScript, /crop_width/);
  assert.match(html, /value="crop_x"/);
  assert.match(html, /ease_in_quad/);
  assert.match(html, /ease_in_out_quart/);
});


test("Studio can create a stored video proxy and switch between source/proxy and edited composite previews", () => {
  assert.match(studioScript, /media\.create_proxy/);
  assert.match(studioScript, /Create 640×360 proxy/);
  assert.match(html, /id="studio-source-preview"/);
  assert.match(html, /id="studio-composite-preview"/);
  assert.match(html, /proxy_for_media_id/);
  assert.match(html, /encodeURIComponent\(proxy\?proxy\.id:targetMediaId\)/);
});


test("Selected video clip can use its private low-resolution proxy for source preview", () => {
  assert.match(studioScript, /getStudioPreviewMediaId/);
  assert.match(studioScript, /video\.dataset\.mediaId/);
  assert.match(html, /targetMediaId=window\.getStudioPreviewMediaId/);
  assert.match(html, /proxy_for_media_id===targetMediaId/);
});


test("Stage 2 Task 2.1 exposes selected-caption editing and SRT/VTT sidecar export", () => {
  for (const id of [
    "studio-text-content", "studio-text-family", "studio-text-size",
    "studio-text-fgcolour", "studio-text-highlight-colour", "studio-text-olcolour", "studio-text-outline",
    "studio-text-halign", "studio-text-valign", "studio-text-x", "studio-text-y",
    "studio-text-width", "studio-text-height", "studio-save-text",
    "studio-subtitle-format", "studio-export-subtitles"
  ]) assert.match(html, new RegExp('id="' + id + '"'));
  assert.match(html, /caption_io\.js/);
  assert.match(studioScript, /text\.update_clip/);
  assert.match(studioScript, /highlight_colour: byId\("studio-text-highlight-colour"\)/);
  assert.match(studioScript, /textData\.highlight_colour/);
  assert.match(studioScript, /captionIO\.exportSubtitleTrack/);
  assert.match(studioScript, /studio-text-content/);
});



test("Studio exposes measured silence review with individual human approval", () => {
  for (const id of [
    "studio-silence-transcript", "studio-silence-analysis-seconds",
    "studio-silence-threshold", "studio-silence-minimum-ms",
    "studio-review-silence", "studio-silence-status", "studio-silence-candidates"
  ]) assert.match(html, new RegExp('id="' + id + '"'));
  assert.match(studioScript, /transcript\.review_silence/);
  assert.match(studioScript, /transcript\.apply_silence_cut/);
  assert.match(studioScript, /handleStudioAnalysisResult/);
  assert.match(studioScript, /window\.confirm/);
  assert.match(studioScript, /semantic_assessment/);
  assert.match(html, /Silence is a measured signal, not a filler-word verdict/);
  assert.match(html, /analysis_result/);
});


test("Studio exposes expanded editable title styling controls", () => {
  for (const id of [
    "studio-text-weight", "studio-text-background-fill", "studio-text-bgcolour",
    "studio-text-bgopacity", "studio-text-pad", "studio-text-shadow-color",
    "studio-text-shadow-x", "studio-text-shadow-y", "studio-text-shadow-opacity",
    "studio-text-letter-spacing", "studio-text-line-spacing"
  ]) assert.match(html, new RegExp('id="' + id + '"'));
  for (const property of [
    "weight", "background_fill", "bgcolour", "bgopacity", "shadow_color",
    "shadow_x", "shadow_y", "shadow_opacity", "letter_spacing_px", "line_spacing_px"
  ]) assert.ok(studioScript.includes(property), "Missing style property " + property);
});


test("Text opacity interpolation is restricted to its supported linear mode", () => {
  assert.match(studioScript, /function syncKeyframeInterpolationControl\(\)/);
  assert.match(studioScript, /linearOnly = selected\?\.clip\.kind === "text" && property === "opacity"/);
  assert.match(studioScript, /option\.disabled = linearOnly && option\.value !== "linear"/);
  assert.match(studioScript, /syncKeyframeInterpolationControl\(\)/);
});

test("Text clips expose canonical transform keyframes and bounded loop presets", () => {
  assert.match(studioScript, /textAnimationProperties = new Set/);
  for (const property of ["position_x", "position_y", "scale_x", "scale_y", "rotation_deg", "opacity"]) {
    assert.ok(studioScript.includes(property), "Missing text animation property " + property);
  }
  assert.match(studioScript, /preset==="pulse_loop"\|\|preset==="float_loop"/);
  assert.match(studioScript, /for\(let cycle=0;cycle<3;cycle\+\+\)/);
  assert.match(html, /value="pulse_loop"/);
  assert.match(html, /value="float_loop"/);
  assert.match(studioScript, /fade_in/);
});

test("Expanded text shadow blur is loaded and saved through the existing text update operation", () => {
  assert.match(html, /id="studio-text-shadow-blur" type="number" min="0" max="10"/);
  assert.match(studioScript, /setValue\("studio-text-shadow-blur", textData\.shadow_blur \?\? 0\)/);
  assert.match(studioScript, /shadow_blur: numeric\("studio-text-shadow-blur"\)/);
  assert.match(studioScript, /name: "text\.update_clip"/);
});
