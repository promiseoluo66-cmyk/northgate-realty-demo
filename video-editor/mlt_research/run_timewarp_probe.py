"""Probe MLT's native timewarp producer using generated media only."""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

import mlt7 as mlt


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mlt-timewarp-") as folder:
        root = Path(folder)
        source = root / "source.mp4"
        output = root / "timewarp-2x.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=2",
            "-an", "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p",
            str(source),
        ], check=True, capture_output=True)

        factory = mlt.Factory()
        factory.init(None)
        profile = mlt.Profile()
        profile.set_width(320)
        profile.set_height(240)
        profile.set_frame_rate(25, 1)
        profile.set_progressive(1)
        profile.set_explicit(1)

        producer = mlt.Producer(profile, "timewarp", f"2.0:{source}")
        if not producer.is_valid():
            raise SystemExit("MLT timewarp producer is unavailable.")
        producer.set("warp_pitch", 1)
        producer.set("eof", "pause")
        source_frames_after_warp = int(producer.get_length())
        if source_frames_after_warp < 1:
            raise SystemExit(
                f"MLT timewarp producer reported invalid length: {source_frames_after_warp}"
            )
        producer.set("in", 0)
        producer.set("out", source_frames_after_warp - 1)

        playlist = mlt.Playlist(profile)
        result = playlist.append(producer, 0, source_frames_after_warp - 1)
        if result not in (None, 0):
            raise SystemExit(f"Could not append MLT timewarp producer: {result}")
        playtime = int(playlist.get_playtime())
        if playtime < 1:
            raise SystemExit(f"Timewarp playlist has invalid playtime: {playtime}")

        tractor = mlt.Tractor()
        tractor.set_track(playlist, 0)
        tractor.refresh()
        tractor.set_in_and_out(0, playtime - 1)

        consumer = mlt.Consumer(profile, "avformat", str(output))
        if not consumer.is_valid():
            raise SystemExit("MLT avformat consumer is unavailable.")
        consumer.set("vcodec", "mpeg4")
        consumer.set("pix_fmt", "yuv420p")
        consumer.set("real_time", -1)
        if consumer.connect(tractor) not in (None, 0):
            raise SystemExit("Could not connect MLT timewarp composition.")
        if consumer.start() not in (None, 0):
            raise SystemExit("Could not start MLT timewarp render.")
        deadline = time.monotonic() + 30
        while not consumer.is_stopped():
            if time.monotonic() >= deadline:
                consumer.stop()
                raise SystemExit("MLT timewarp probe timed out.")
            time.sleep(0.05)
        consumer.stop()
        if not output.is_file() or output.stat().st_size == 0:
            raise SystemExit("MLT timewarp probe produced no output.")

        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(output),
        ], check=True, capture_output=True, text=True)
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        print(json.dumps({
            "producer_in": producer.get_in(),
            "producer_out": producer.get_out(),
            "producer_length": producer.get_length(),
            "producer_playtime": producer.get_playtime(),
            "source_frames_after_warp": source_frames_after_warp,
            "producer_speed": producer.get_speed(),
            "playlist_playtime": playtime,
            "rendered_duration_seconds": duration,
            "expected_duration_seconds": 1.0,
        }, indent=2, sort_keys=True))
        if not 0.92 <= duration <= 1.08:
            raise SystemExit(
                f"Expected 2x playback to render about 1.0 second, got {duration:.3f}s."
            )
        print("PASS: MLT native timewarp renders 2x playback at the expected duration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
