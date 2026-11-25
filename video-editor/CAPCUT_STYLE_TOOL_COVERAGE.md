# CapCut-style editing tool coverage

This is an independent editing-tool compatibility plan. It does not connect to CapCut, use CapCut's private APIs, or copy its proprietary assets/effect library. Feature names describe editing concepts, not a claim of exact CapCut parity.

## Already available as registered editor operations

| Editing capability | Current tool operation(s) | Status |
|---|---|---|
| Project/profile setup | `project.inspect`, `project.set_profile` | Implemented |
| Multi-track timeline | `timeline.add_track`, `timeline.remove_track`, `track.set_state`, `track.rename`, `track.set_locked` | Implemented |
| Import/list project media | `media.list`, `timeline.add_clip` | Implemented |
| Split, trim, move, duplicate, delete clips | `timeline.split_clip`, `timeline.trim_clip`, `timeline.move_clip`, `timeline.duplicate_clip`, `timeline.delete_clip`, `timeline.ripple_delete_clip` | Implemented |
| Text, titles and caption blocks | `timeline.add_text_clip`, `text.update_clip` | Basic timed text implemented; automatic transcription/word sync pending |
| Speed and speed ramps | `clip.set_speed`, `animation.set_keyframe` with `playback_rate` | Constant and keyframed speed implemented |
| Position, scale, rotation, opacity animation | `clip.set_transform`, `animation.set_keyframe` | Implemented |
| Transitions | `timeline.add_transition` | Dissolve and horizontal wipe only |
| Clip framing | `clip.set_framing` | Fit (contain), fill (aspect-preserving crop), stretch (distort), alignment controls; validated with real MLT render pixel checks |
| Basic visual effects | `effect.add`, `effect.remove`, `effect.set_enabled` | Brightness, contrast, saturation and chroma key only |
| Audio level and fades | `audio.set_gain`, `audio.set_fade` | Implemented |
| Export | `render.export` | MP4 export path registered; renderer limitations still apply |
| Post-render technical receipt | runner-level FFprobe/FFmpeg checks | Stream validation, SHA-256, black/freeze/silence review flags; semantic/artistic approval remains human/model review |
| Media/quality analysis | `quality.inspect_media`, `media.detect_scenes`, `audio.analyze_media` | Technical analysis implemented; semantic labels not claimed |

## CapCut-inspired capabilities still to build

| Capability | Why it matters | Required implementation evidence |
|---|---|---|
| Manual crop rectangle and subject-aware aspect-ratio reframing | Control the crop region and keep a detected subject in frame | Crop coordinates, source geometry and subject-track render fixtures; basic clip fit/fill/stretch framing is implemented separately |
| Subject-aware auto reframe and motion tracking | Keep a selected person/object in frame | Visual tracking model/algorithm, timestamped track data, smoothing and render tests |
| Masks and blend modes | Isolate/composite parts of clips | Typed mask/blend schema, supported MLT filters, render fixtures |
| Rich transitions and effect families | More creative control than basic dissolve/wipe | Allowlisted renderer-backed filters, parameter validation, preview/golden renders |
| Colour wheels, curves and LUTs | Professional colour correction | Typed colour model, LUT loading restrictions, renderer and visual test fixtures |
| Automatic captions and transcript editing | Generate accurate, synchronised subtitles | Speech adapter, word timestamps, editable transcript and caption renderer tests |
| Text-to-speech and voice processing | Narration and audio production | Provider/local adapter, cost disclosure, audio render tests |
| Beat detection and beat-synchronised edits | Match cuts/effects to music | Timestamped beat analysis and alignment tests |
| Background removal / chroma key improvements | Isolate foreground subjects | Local or approved model adapter, alpha output and edge-quality tests |
| Export presets and codec controls | Match platform delivery requirements | Explicit encoder allowlist, profile validation and output probe tests |

## Engineering rules

- Every AI-facing tool must have a strict schema, an actual executor, and tests.
- Editing operations must not silently call arbitrary shell commands or fetch untrusted remote media.
- Do not expose a feature as complete until the actual renderer path has been verified.
- Keep technical measurements separate from visual/semantic judgments.
- Preserve undo/redo, revision checks and user approval for destructive/export actions.
- Do not claim exact CapCut parity; implement compatible editing concepts independently.
