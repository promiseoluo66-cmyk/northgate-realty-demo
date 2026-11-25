"""Run a small end-to-end MLT adapter render using generated clips only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
VIDEO_EDITOR_ROOT = HERE.parents[1]
if str(VIDEO_EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VIDEO_EDITOR_ROOT))

from mlt_engine.renderer import render_project  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: run_adapter_probe.py ASSET_ROOT OUTPUT_MP4")

    asset_root = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2]).resolve()
    background = asset_root / "background-red.mp4"
    overlay = asset_root / "overlay-blue.mp4"
    green = asset_root / "background-green.mp4"
    cyan = asset_root / "wipe-cyan.mp4"
    magenta = asset_root / "wipe-magenta.mp4"
    music = asset_root / "music-tone.wav"

    if not all(path.is_file() for path in (background, overlay, green, cyan, magenta, music)):
        raise SystemExit("The generated colour clips, overlay and audio tone must exist.")

    project = {
        "schema_version": 1,
        "id": "mlt-adapter-ci-project",
        "name": "Generated MLT adapter integration test",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 320,
            "height": 240,
            "frame_rate": {"numerator": 25, "denominator": 1},
        },
        "assets": [
            {
                "id": "asset-background",
                "media_type": "video",
                "file_name": background.name,
                "storage_key": background.name,
                "size_bytes": background.stat().st_size,
                "duration_us": 2_000_000,
            },
            {
                "id": "asset-green",
                "media_type": "video",
                "file_name": green.name,
                "storage_key": green.name,
                "size_bytes": green.stat().st_size,
                "duration_us": 1_200_000,
            },
            {
                "id": "asset-overlay",
                "media_type": "video",
                "file_name": overlay.name,
                "storage_key": overlay.name,
                "size_bytes": overlay.stat().st_size,
                "duration_us": 800_000,
            },
            {
                "id": "asset-cyan",
                "media_type": "video",
                "file_name": cyan.name,
                "storage_key": cyan.name,
                "size_bytes": cyan.stat().st_size,
                "duration_us": 1_200_000,
            },
            {
                "id": "asset-magenta",
                "media_type": "video",
                "file_name": magenta.name,
                "storage_key": magenta.name,
                "size_bytes": magenta.stat().st_size,
                "duration_us": 1_200_000,
            },
            {
                "id": "asset-music",
                "media_type": "audio",
                "file_name": music.name,
                "storage_key": music.name,
                "size_bytes": music.stat().st_size,
                "duration_us": 4_800_000,
            },
        ],
        "tracks": [
            {
                "id": "track-background",
                "type": "video",
                "name": "Background",
                "order": 0,
                "clips": [
                    {
                        "id": "clip-background",
                        "kind": "video",
                        "media_id": "asset-background",
                        "start_us": 0,
                        "duration_us": 2_000_000,
                        "source_in_us": 0,
                        "source_out_us": 2_000_000,
                        "playback_rate": 1,
                        "effects": [
                            {
                                "id": "brightness-background",
                                "type": "brightness",
                                "enabled": True,
                                "parameters": {"level": 1.1},
                            }
                        ],
                        "keyframes": [],
                    },
                    {
                        "id": "clip-green",
                        "kind": "video",
                        "media_id": "asset-green",
                        "start_us": 1_600_000,
                        "duration_us": 1_200_000,
                        "source_in_us": 0,
                        "source_out_us": 1_200_000,
                        "playback_rate": 1,
                        "effects": [],
                        "keyframes": [],
                    }
                ],
            },
            {
                "id": "track-overlay",
                "type": "overlay",
                "name": "Overlay",
                "order": 1,
                "clips": [
                    {
                        "id": "clip-overlay",
                        "kind": "video",
                        "media_id": "asset-overlay",
                        "start_us": 400_000,
                        "duration_us": 800_000,
                        "source_in_us": 0,
                        "source_out_us": 800_000,
                        "playback_rate": 1,
                        "effects": [],
                        "keyframes": [],
                    }
                ],
            },
            {
                "id": "track-wipe",
                "type": "overlay",
                "name": "Wipe transition test",
                "order": 2,
                "clips": [
                    {
                        "id": "clip-cyan",
                        "kind": "video",
                        "media_id": "asset-cyan",
                        "start_us": 2_800_000,
                        "duration_us": 1_200_000,
                        "source_in_us": 0,
                        "source_out_us": 1_200_000,
                        "playback_rate": 1,
                        "effects": [],
                        "keyframes": [],
                    },
                    {
                        "id": "clip-magenta",
                        "kind": "video",
                        "media_id": "asset-magenta",
                        "start_us": 3_600_000,
                        "duration_us": 1_200_000,
                        "source_in_us": 0,
                        "source_out_us": 1_200_000,
                        "playback_rate": 1,
                        "effects": [],
                        "keyframes": [],
                    },
                ],
            },
            {
                "id": "track-music",
                "type": "audio",
                "name": "Music",
                "order": 3,
                "clips": [
                    {
                        "id": "clip-music",
                        "kind": "audio",
                        "media_id": "asset-music",
                        "start_us": 0,
                        "duration_us": 4_800_000,
                        "source_in_us": 0,
                        "source_out_us": 4_800_000,
                        "playback_rate": 1,
                        "effects": [
                            {"id": "music-gain", "type": "gain",
                             "parameters": {"gain_db": -6}},
                            {"id": "music-fades", "type": "fade",
                             "parameters": {"fade_in_us": 400_000,
                                            "fade_out_us": 500_000}},
                        ],
                        "keyframes": [],
                    }
                ],
            },
        ],
        "transitions": [
            {
                "id": "transition-dissolve",
                "type": "dissolve",
                "from_clip_id": "clip-background",
                "to_clip_id": "clip-green",
                "duration_us": 400_000,
                "parameters": {},
            },
            {
                "id": "transition-wipe",
                "type": "wipe",
                "from_clip_id": "clip-cyan",
                "to_clip_id": "clip-magenta",
                "duration_us": 400_000,
                "parameters": {"direction": "right_to_left", "softness": 0.30},
            }
        ],
    }

    result = render_project(
        project,
        asset_root,
        output,
        timeout_seconds=90,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
