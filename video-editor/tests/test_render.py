import json
import shutil
import subprocess
from pathlib import Path

import pytest
from engine import EditPlan, render_video


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg tools unavailable")
def test_render_creates_vertical_mp4_with_audio(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(source),
    ], check=True, capture_output=True)
    result = render_video(source, output, EditPlan(aspect="9:16", width=360, height=640, speed=1.5))
    assert output.is_file() and output.stat().st_size > 1000
    probe = json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
        "-of", "json", str(output),
    ], check=True, capture_output=True, text=True).stdout)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (360, 640)
    assert any(s["codec_type"] == "audio" for s in probe["streams"])
    assert result["selected_duration"] == 2
