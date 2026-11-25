import io
import urllib.error
from pathlib import Path

from cloudflare.runner import download_release_asset, download_project_media_assets, _probe_project_asset_duration_us


def test_download_uses_signed_redirect_without_forwarding_github_token(tmp_path, monkeypatch):
    class NoRedirectOpener:
        def open(self, request, timeout):
            assert request.headers.get("Authorization") == "Bearer private-token"
            raise urllib.error.HTTPError(
                request.full_url, 302, "Found",
                {"Location": "https://signed-assets.example/video"}, io.BytesIO()
            )

    class DownloadResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, _size=-1):
            if not hasattr(self, "done"):
                self.done = True
                return b"video-bytes"
            return b""

    requested = []
    monkeypatch.setattr(
        "cloudflare.runner.urllib.request.build_opener",
        lambda handler: NoRedirectOpener()
    )

    def fake_urlopen(url, timeout):
        requested.append(url)
        return DownloadResponse()

    monkeypatch.setattr("cloudflare.runner.urllib.request.urlopen", fake_urlopen)
    output = tmp_path / "source.mp4"
    download_release_asset("owner", "repo", 123, "private-token", output)
    assert requested == ["https://signed-assets.example/video"]
    assert output.read_bytes() == b"video-bytes"


import unittest
from cloudflare.runner import _build_initial_project

class CanonicalProjectRunnerTests(unittest.TestCase):
    def test_uploaded_video_becomes_valid_canonical_project(self):
        job = {"job_id": "a" * 32, "input_filename": "sample.mp4",
               "skill": {"default_settings": {"width": 720, "height": 1280}}}
        project = _build_initial_project(
            job, duration_us=4_000_000, fps_num=30, fps_den=1,
            source_width=1920, source_height=1080, size_bytes=4096)
        self.assertEqual(project["revision"], 1)
        self.assertEqual(project["assets"][0]["storage_key"], "input-video")
        self.assertEqual(project["tracks"][0]["clips"][0]["duration_us"], 4_000_000)
        self.assertEqual(project["video_profile"]["height"], 1280)

    def test_initial_project_retains_source_frame_rate(self):
        project = _build_initial_project(
            {"job_id": "b" * 32, "input_filename": "source.mov", "skill": {}},
            duration_us=2_500_000, fps_num=30000, fps_den=1001,
            source_width=1280, source_height=720, size_bytes=2048)
        self.assertEqual(project["video_profile"]["frame_rate"],
                         {"numerator": 30000, "denominator": 1001})


import hashlib
import json
from types import SimpleNamespace

from cloudflare.runner import inspect_render_output


def test_render_receipt_probes_output_and_records_hash_and_review_flags(tmp_path, monkeypatch):
    output = tmp_path / "render.mp4"
    output.write_bytes(b"verified-render-fixture")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == "ffprobe":
            return SimpleNamespace(stdout=json.dumps({
                "format": {"duration": "4.0"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264",
                     "width": 720, "height": 1280},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
            }), stderr="")
        if "-vf" in command:
            return SimpleNamespace(
                stdout="",
                stderr="black_start:0.000000 black_end:0.600000 "
                       "freeze_start:1.000000 freeze_end:3.200000",
            )
        return SimpleNamespace(
            stdout="",
            stderr="silence_start:0.000000 silence_end:0.700000",
        )

    monkeypatch.setattr("cloudflare.runner.subprocess.run", fake_run)
    receipt = inspect_render_output(output)

    assert receipt["technical_status"] == "passed"
    assert receipt["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt["video"] == {"codec": "h264", "width": 720, "height": 1280}
    assert receipt["review_flags"] == [
        "black_intervals_detected",
        "freeze_intervals_detected",
        "silence_intervals_detected",
    ]
    assert receipt["semantic_visual_assessment"] == "not_evaluated"
    assert receipt["semantic_audio_assessment"] == "not_evaluated"
    assert len(calls) == 3


def test_render_receipt_rejects_output_without_video_stream(tmp_path, monkeypatch):
    output = tmp_path / "audio-only.mp4"
    output.write_bytes(b"not-a-valid-video")
    monkeypatch.setattr(
        "cloudflare.runner.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=json.dumps({"format": {"duration": "2"}, "streams": [
                {"codec_type": "audio", "codec_name": "aac"}
            ]}),
            stderr="",
        ),
    )
    import pytest
    with pytest.raises(ValueError, match="no readable video stream"):
        inspect_render_output(output)

from cloudflare.runner import _make_plan
from project_tool_executor import ProjectToolExecutor


def test_manual_studio_plan_is_validated_without_requesting_ai(tmp_path):
    project = _build_initial_project(
        {"job_id": "c" * 32, "input_filename": "source.mp4", "skill": {}},
        duration_us=5_000_000, fps_num=30, fps_den=1,
        source_width=1280, source_height=720, size_bytes=1024)
    executor = ProjectToolExecutor(project, output_dir=tmp_path)
    manual = {
        "mode": "manual",
        "summary": "Set the selected clip to 1.5x speed.",
        "tool_calls": [{
            "name": "clip.set_speed",
            "arguments": {"clip_id": "main-clip", "playback_rate": 1.5}
        }]
    }
    plan, analysis = _make_plan("Apply the selected speed control.", executor, manual,
                                tmp_path / "input-video")
    assert [item["name"] for item in plan["tool_calls"]] == [
        "clip.set_speed", "render.export"
    ]
    assert analysis["analysis_provider"] == "not_run_manual_registered_operation"
    assert analysis["analysis_status"] == "not_run"


def test_download_project_media_assets_stores_imported_assets_safely(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import json

    calls = []

    def fake_download(owner, repo, asset_id, token, path):
        calls.append((owner, repo, asset_id, token, path.name))
        path.write_bytes(b"imported-video")

    monkeypatch.setattr("cloudflare.runner.download_release_asset", fake_download)
    monkeypatch.setattr(
        "cloudflare.runner.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps({
            "format": {"duration": "3.25"},
            "streams": [{"codec_type": "video"}],
        })),
    )
    project = {"assets": [{
        "id": "media-asset-1",
        "media_type": "video",
        "file_name": "b-roll.mp4",
        "storage_key": "media-asset-1.mp4",
        "size_bytes": 20,
        "release_asset_id": 765,
    }]}
    download_project_media_assets(
        {"job_id": "d" * 32}, project, tmp_path, "owner", "repo", "private-token"
    )
    assert calls == [("owner", "repo", 765, "private-token", "media-asset-1.mp4")]
    assert (tmp_path / "media-asset-1.mp4").read_bytes() == b"imported-video"
    assert project["assets"][0]["duration_us"] == 3_250_000


def test_download_project_media_assets_rejects_storage_path_traversal(tmp_path):
    import pytest

    project = {"assets": [{
        "id": "media-asset-2",
        "media_type": "image",
        "file_name": "image.png",
        "storage_key": "../escape.png",
        "size_bytes": 20,
        "release_asset_id": 766,
    }]}
    with pytest.raises(ValueError, match="unsafe storage key"):
        download_project_media_assets(
            {"job_id": "e" * 32}, project, tmp_path, "owner", "repo", "private-token"
        )
