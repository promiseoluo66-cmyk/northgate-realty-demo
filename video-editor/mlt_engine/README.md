# MLT integration (isolated prototype)

This branch contains the editor's isolated adapter from the canonical project
document to the MLT Python API. It is a verified engine prototype, not the
production renderer and not the complete Studio application.

## Implemented and verified in the adapter

- Multiple video and overlay tracks, sequential clips, timeline gaps and
  cross-track visual compositing.
- Adjacent-clip dissolves and horizontal luma-map wipes in both directions,
  with validated edge-softness controls. The packaged maps are binary P5 PGM;
  the MLT PGM loader does not correctly use the former ASCII P2 map.
- Static affine transforms and animated position, scale, rotation and opacity.
- Keyframe interpolation: hold, linear, ease-in, ease-out, ease-in-out and
  cubic Bezier. Non-linear transform curves are sampled into bounded MLT
  animation points.
- Constant playback speed and keyframed variable-speed ramps on video clips.
  Speed curves are compiled into bounded contiguous MLT timewarp segments.
- Visual effect allowlist: brightness, chroma key, contrast and saturation.
- Separate audio tracks and audio embedded in unmuted video clips, mixed with
  MLT's core `mix` transition.
- Audio gain, fade-in/fade-out and clip-level `volume_db` keyframes.
- Still-image overlays and timed text/title/caption overlays. Transparent title
  PNGs are generated with FFmpeg drawtext onto an RGBA canvas, alpha-checked,
  and composited over the MLT base render. The overlay probe verifies decoded
  pixels against a known-red background point.
- MP4 output with AAC audio through the MLT Python API and `avformat`.
- Strict project/media/effect/transition validation; unsupported operations
  and unapproved external wipe-map paths are rejected rather than silently
  ignored.

## Latest verification

[MLT adapter CI run 45031921304](https://github.com/promiseoluo66-cmyk/sparkle-clean-co/actions/runs/45031921304)
passed every step on 22 November 2026.

It runs pure-Python compiler/safety tests and generated-media runtime probes.
The probes inspect decoded video pixels, output metadata and decoded audio;
they do not rely only on successful function return values.

## Known limits (not claimed as implemented)

- Speed ramps cannot yet be combined with animated visual transforms or clip
  effects. Audio volume keyframes cannot yet be combined with speed ramps.
- Speed ramps currently apply to video clips; speed values are bounded from
  0.05x to 16x and the compiler caps a curve at 1,024 segments.
- Dissolve and horizontal luma-map wipes are supported; fade-to-colour,
  dip-to-colour and additional wipe shapes/patterns are not.
- The visual effect allowlist is limited to brightness, chroma key, contrast
  and saturation. Advanced effect stacks, blur/sharpen, masks, stabilization,
  tracking, denoise, voice processing and AI generation are not implemented.
- Crop/flip/anchor editing, audio pan/solo, advanced text animation and full
  title-template systems are not implemented.
- The interactive speed/keyframe graph UI (draggable graph points, zoom in/out,
  pan, fit and reset) is a Studio-stage feature. The engine accepts and renders
  speed curves, but the visual graph editor is not built yet.

See
[`PROFESSIONAL_FEATURE_ROADMAP_AND_FREE_LIMITS.md`](../architecture/PROFESSIONAL_FEATURE_ROADMAP_AND_FREE_LIMITS.md)
for the broader product scope and $0 resource guardrails.

## Isolated checks

The GitHub Actions workflow
`.github/workflows/mlt-adapter-ci.yml` installs Ubuntu's MLT Python binding,
MLT service data and FFmpeg. It uses tiny generated red, blue, green, cyan and
magenta test clips plus generated audio. It does not require a personal video
upload and does not deploy the Worker.

Pure-Python compiler tests do not need MLT installed:

```bash
cd video-editor
python -m unittest discover -s tests -p 'test_mlt_renderer.py' -v
```

The runtime probe uses `/usr/bin/python3` and its `mlt7` binding (Python
3.14 on the tested Ubuntu 26.04 runner). The current production FFmpeg worker
uses Python 3.12; the Ubuntu-provided `mlt7` binding has not been verified in
that production interpreter. Keep these environments separate until
compatibility is proven or the production runner is intentionally changed.

## Render guardrails

- Maximum 250 clips per project and 30 minutes of timeline duration.
- Dissolve and wipe transitions require adjacent clips on one visual track,
  a frame-aligned overlap matching the transition length, and no clip shared
  between two transitions.
- Wipes use only the two packaged directional maps; arbitrary external map
  paths are rejected. Direction is left-to-right or right-to-left; softness
  is 0 through 1.
- Speed ramps are bounded to 1,024 segments and 0.05x–16x.
- Unsupported media, effects and project elements are rejected.
- These limits do not guarantee every project will fit the free Actions quota.

## Licensing guardrails

- MLT framework libraries and the reviewed brightness/chroma services are
  LGPL-compatible; confirm the exact installed package and linked dependencies.
- FFmpeg libavfilter `volume`, `afade` and `eq` are used for audio gain/fades
  and contrast/saturation. Inspect the exact linked FFmpeg build and enabled
  components before distribution; do not infer licence status from a filter
  name alone.
- Audit `composite`, codecs and all FFmpeg modules before shipping.
- Do not bundle GPL `melt` or expose GPL-only filters without a deliberate
  licence decision.

The workflow invokes the MLT Python API directly and does not install or invoke
the `melt` command-line application.

## Production boundary

- This adapter remains isolated on `mlt-integration`.
- The deployed Worker and FFmpeg production path are unchanged.
- The separate YouTube automation repository is untouched.
- Do not switch production rendering until Python compatibility, licensing,
  large-file behaviour, free-quota use and end-to-end regression tests pass.
