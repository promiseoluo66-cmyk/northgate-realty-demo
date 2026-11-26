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
        "clip.set_speed"
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



def _executor_with_generated_assets(tmp_path, count=1):
    from cloudflare.runner import _build_initial_project
    from project_tool_executor import ProjectToolExecutor
    project = _build_initial_project(
        {"job_id": "f" * 32, "input_filename": "source.mp4", "skill": {}},
        duration_us=2_000_000, fps_num=30, fps_den=1,
        source_width=640, source_height=360, size_bytes=1024,
    )
    for index in range(count):
        filename = f"generated-{index}.m4a"
        (tmp_path / filename).write_bytes(b"generated-audio")
        project["assets"].append({
            "id": f"generated-{index}", "media_type": "audio",
            "file_name": filename, "storage_key": filename,
            "size_bytes": len(b"generated-audio"), "duration_us": 1_000_000,
            "generated": True,
        })
    return ProjectToolExecutor(project)


def test_generated_media_upload_is_private_and_release_id_is_saved(tmp_path, monkeypatch):
    from cloudflare.runner import persist_generated_project_assets
    executor = _executor_with_generated_assets(tmp_path)
    calls = []

    def fake_upload(owner, repo, release_id, token, path, asset_name=None, content_type="video/mp4"):
        calls.append((owner, repo, release_id, path.name, content_type, asset_name))
        return 98765

    monkeypatch.setattr("cloudflare.runner.upload_release_asset", fake_upload)
    uploaded = persist_generated_project_assets(
        executor, tmp_path, "owner", "repo", 1234, "secret"
    )
    assert uploaded == [98765]
    assert calls[0][:5] == ("owner", "repo", 1234, "generated-0.m4a", "audio/mp4")
    asset = next(item for item in executor.get_project()["assets"] if item["id"] == "generated-0")
    assert asset["release_asset_id"] == 98765


def test_generated_media_upload_failure_cleans_up_and_does_not_attach_dead_ids(tmp_path, monkeypatch):
    import pytest
    from cloudflare.runner import persist_generated_project_assets
    executor = _executor_with_generated_assets(tmp_path, count=2)
    upload_count = {"value": 0}
    deleted = []

    def fake_upload(*args, **kwargs):
        upload_count["value"] += 1
        if upload_count["value"] == 1:
            return 45678
        raise RuntimeError("simulated GitHub upload failure")

    monkeypatch.setattr("cloudflare.runner.upload_release_asset", fake_upload)
    monkeypatch.setattr(
        "cloudflare.runner.delete_release_asset",
        lambda owner, repo, asset_id, token: deleted.append(asset_id),
    )
    with pytest.raises(RuntimeError, match="simulated GitHub upload failure"):
        persist_generated_project_assets(executor, tmp_path, "owner", "repo", 1234, "secret")
    assert deleted == [45678]
    assert all("release_asset_id" not in item for item in executor.get_project()["assets"]
               if item.get("generated"))


def test_project_media_download_includes_generated_assets_in_redo_history(tmp_path, monkeypatch):
    from cloudflare.runner import download_project_media_assets
    downloaded = []

    def fake_download(owner, repo, asset_id, token, path):
        downloaded.append((asset_id, path.name))
        path.write_bytes(b"history-audio")

    monkeypatch.setattr("cloudflare.runner.download_release_asset", fake_download)
    monkeypatch.setattr(
        "cloudflare.runner._probe_project_asset_duration_us",
        lambda path, media_type: 1_000_000,
    )
    project = {"assets": []}
    job = {"history_state": {"undo": [], "redo": [{
        "assets": [{
            "id": "generated-redo", "media_type": "audio",
            "file_name": "redo.m4a", "storage_key": "redo.m4a",
            "size_bytes": 13, "release_asset_id": 76543,
        }]
    }]}}
    download_project_media_assets(job, project, tmp_path, "owner", "repo", "secret")
    assert downloaded == [(76543, "redo.m4a")]
    assert (tmp_path / "redo.m4a").read_bytes() == b"history-audio"


def test_private_release_upload_sends_generated_media_with_mime_type(tmp_path, monkeypatch):
    from cloudflare.runner import upload_release_asset

    media = tmp_path / "freeze-frame.png"
    media.write_bytes(b"png-image-bytes")
    captured = {}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"id":54321}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = request.headers
        captured["body"] = request.data
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("cloudflare.runner.urllib.request.urlopen", fake_urlopen)
    asset_id = upload_release_asset(
        "owner", "repo", 1234, "release-token", media,
        asset_name="project-frame-frame-123.png", content_type="image/png",
    )
    assert asset_id == 54321
    assert captured["url"] == (
        "https://uploads.github.com/repos/owner/repo/releases/1234/assets"
        "?name=project-frame-frame-123.png"
    )
    assert captured["method"] == "POST"
    assert captured["headers"]["Authorization"] == "Bearer release-token"
    assert captured["headers"]["Content-type"] == "image/png"
    assert captured["body"] == b"png-image-bytes"


def test_runner_callback_sends_project_and_undo_redo_checkpoint(monkeypatch):
    from cloudflare.runner import callback

    captured = {}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"ok":true,"project_revision":8}'

    def fake_urlopen(request, timeout):
        import json
        captured["url"] = request.full_url
        captured["secret"] = request.get_header("X-Callback-Secret")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr("cloudflare.runner.urllib.request.urlopen", fake_urlopen)
    project = {
        "revision": 8,
        "assets": [{
            "id": "generated-frame", "media_type": "image",
            "storage_key": "frame.png", "release_asset_id": 54321,
        }],
    }
    history = {"undo": [{"revision": 7, "assets": []}], "redo": []}
    callback(
        "https://worker.example", "callback-secret", "a" * 32,
        "running", "Generated media checkpoint saved.",
        project_json=project, project_revision=8, history_state=history,
    )
    assert captured["url"] == "https://worker.example/api/internal/jobs/" + "a" * 32
    assert captured["secret"] == "callback-secret"
    assert captured["body"]["project_json"]["assets"][0]["release_asset_id"] == 54321
    assert captured["body"]["project_revision"] == 8
    assert captured["body"]["history_state"] == history
