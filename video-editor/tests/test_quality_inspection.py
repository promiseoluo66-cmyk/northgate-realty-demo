import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from project_tool_executor import ProjectToolExecutor
from tool_registry import validate_tool_call


def sample_project():
    return {
        "schema_version": 1,
        "id": "project-quality",
        "name": "Quality test",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 1080,
            "height": 1920,
            "frame_rate": {"numerator": 30, "denominator": 1},
        },
        "assets": [{
            "id": "source-video",
            "media_type": "video",
            "file_name": "source.mp4",
            "storage_key": "source.mp4",
            "size_bytes": 128,
            "duration_us": 10_000_000,
        }],
        "tracks": [],
        "transitions": [],
    }


class QualityInspectionTests(unittest.TestCase):
    def test_tool_contract_is_bounded(self):
        args = validate_tool_call("quality.inspect_media", {"media_id": "source-video"})
        self.assertEqual(args, {"media_id": "source-video"})
        with self.assertRaisesRegex(ValueError, "above the allowed maximum"):
            validate_tool_call(
                "quality.inspect_media",
                {"media_id": "source-video", "analysis_seconds": 601},
            )

    def test_reports_measured_intervals_without_mutating_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.mp4").write_bytes(b"fixture")
            executor = ProjectToolExecutor(sample_project(), asset_root=root)
            probe = SimpleNamespace(stdout=json.dumps({
                "format": {"duration": "10.0"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264",
                     "width": 1080, "height": 1920, "avg_frame_rate": "30/1"},
                    {"codec_type": "audio", "codec_name": "aac",
                     "sample_rate": "48000", "channels": 2},
                ],
            }))
            ffmpeg = SimpleNamespace(stderr=(
                "[blackdetect] black_start:1.000 black_end:1.500 black_duration:0.500\n"
                "[silencedetect] silence_start: 2.000\n"
                "[silencedetect] silence_end: 3.000 | silence_duration: 1.000\n"
            ))
            with patch("project_tool_executor.subprocess.run", side_effect=[probe, ffmpeg]):
                result = executor.execute(
                    "quality.inspect_media", {"media_id": "source-video"}
                )
            report = result["results"][0]["result"]
            self.assertEqual(report["measurement_status"], "measured")
            self.assertEqual(report["semantic_visual_assessment"], "not_evaluated")
            self.assertEqual(report["black_intervals"][0]["duration_seconds"], 0.5)
            self.assertEqual(report["silence_intervals"][0]["duration_seconds"], 1.0)
            self.assertTrue(report["full_duration_scanned"])
            self.assertEqual(executor.revision, 1)

    def test_audio_analysis_measures_silence_and_loudness_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.mp4").write_bytes(b"fixture")
            executor = ProjectToolExecutor(sample_project(), asset_root=root)
            probe = SimpleNamespace(stdout=json.dumps({
                "format": {"duration": "10.0"},
                "streams": [{
                    "codec_type": "audio", "codec_name": "aac",
                    "sample_rate": "48000", "channels": 2,
                    "channel_layout": "stereo",
                }],
            }))
            ffmpeg = SimpleNamespace(stderr=(
                "[silencedetect] silence_start: 2.000\\n"
                "[silencedetect] silence_end: 3.000 | silence_duration: 1.000\\n"
                '[Parsed_loudnorm] { "input_i" : "-18.0", "input_tp" : "-1.0", '
                '"input_lra" : "4.0", "input_thresh" : "-28.0", '
                '"target_offset" : "2.0" }\\n'
            ))
            with patch("project_tool_executor.subprocess.run", side_effect=[probe, ffmpeg]):
                result = executor.execute(
                    "audio.analyze_media", {"media_id": "source-video"}
                )
            report = result["results"][0]["result"]
            self.assertEqual(report["measurement_status"], "measured")
            self.assertEqual(report["audio_streams"][0]["sample_rate"], "48000")
            self.assertEqual(report["silence_intervals"][0]["duration_seconds"], 1.0)
            self.assertEqual(report["loudness"]["input_i"], -18.0)
            self.assertEqual(report["semantic_audio_assessment"], "not_evaluated")
            self.assertEqual(executor.revision, 1)

    def test_audio_analysis_reports_missing_audio_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.mp4").write_bytes(b"fixture")
            executor = ProjectToolExecutor(sample_project(), asset_root=root)
            probe = SimpleNamespace(stdout=json.dumps({
                "format": {"duration": "10.0"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }))
            with patch("project_tool_executor.subprocess.run", return_value=probe):
                result = executor.execute(
                    "audio.analyze_media", {"media_id": "source-video"}
                )
            report = result["results"][0]["result"]
            self.assertEqual(report["measurement_status"], "no_audio_stream")
            self.assertIsNone(report["loudness"])
            self.assertEqual(executor.revision, 1)

    def test_detects_scene_change_candidates_with_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.mp4").write_bytes(b"fixture")
            executor = ProjectToolExecutor(sample_project(), asset_root=root)
            detected = SimpleNamespace(stderr=(
                "[Parsed_showinfo] n:0 pts_time:1.200000\n"
                "[Parsed_showinfo] n:1 pts_time:4.500000\n"
            ))
            with patch("project_tool_executor.subprocess.run", return_value=detected):
                result = executor.execute(
                    "media.detect_scenes",
                    {"media_id": "source-video", "threshold": 0.4},
                )
            report = result["results"][0]["result"]
            self.assertEqual(report["candidate_count"], 2)
            self.assertEqual(
                [item["time_seconds"] for item in report["candidate_scene_changes"]],
                [1.2, 4.5],
            )
            self.assertEqual(report["semantic_scene_labels"], "not_evaluated")
            self.assertTrue(report["full_duration_scanned"])

    def test_rejects_path_escape_and_non_video_assets(self):
        project = sample_project()
        project["assets"][0]["storage_key"] = "../outside.mp4"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                ProjectToolExecutor(project, asset_root=directory)


if __name__ == "__main__":
    unittest.main()
