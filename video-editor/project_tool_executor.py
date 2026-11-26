"""Safe, revision-aware execution for registered AI editing tools.

Every batch is applied to a private copy of the canonical project, validated,
and committed as one undoable transaction. No shell or arbitrary code execution
is available to the AI.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from project_model import ProjectValidationError, validate_project
from tool_registry import (
    ToolValidationError,
    get_tool_definition,
    validate_tool_call,
)


class ProjectToolExecutionError(RuntimeError):
    """Raised when an approved project operation cannot be applied safely."""


class ProjectRevisionConflict(ProjectToolExecutionError):
    """Raised when a caller attempts to edit a stale project revision."""


class ToolConfirmationRequired(ProjectToolExecutionError):
    """Raised before any mutation when one or more calls need user approval."""

    def __init__(self, tool_names: list[str]):
        self.tool_names = list(tool_names)
        super().__init__(
            "User confirmation is required for: " + ", ".join(self.tool_names)
        )


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _prune_clip_groups(project: dict[str, Any], removed_clip_ids: set[str]) -> None:
    """Keep linked-group metadata consistent after clips or tracks are removed."""
    groups = project.get("clip_groups", [])
    for group in list(groups):
        group["clip_ids"] = [clip_id for clip_id in group["clip_ids"] if clip_id not in removed_clip_ids]
        if len(group["clip_ids"]) < 2:
            remaining = set(group["clip_ids"])
            for track in project["tracks"]:
                for clip in track["clips"]:
                    if clip["id"] in remaining:
                        clip.pop("group_id", None)
            groups.remove(group)


class ProjectToolExecutor:
    """Execute only the registered project tools against one in-memory project.

    The host application is responsible for persisting get_project() after a
    successful transaction. This class supplies optimistic revision checks,
    atomic batches, and undo/redo snapshots.
    """

    def __init__(
        self,
        project: dict[str, Any],
        *,
        asset_root: str | Path | None = None,
        output_dir: str | Path | None = None,
        render_timeout_seconds: int = 300,
        history_state: dict[str, Any] | None = None,
    ):
        self._project = validate_project(project)
        self._asset_root = Path(asset_root).resolve() if asset_root is not None else None
        self._output_dir = Path(output_dir).resolve() if output_dir is not None else None
        self._render_timeout_seconds = max(1, int(render_timeout_seconds))
        history_state = history_state if isinstance(history_state, dict) else {}
        undo = history_state.get("undo", [])
        redo = history_state.get("redo", [])
        if not isinstance(undo, list) or not isinstance(redo, list):
            raise ProjectToolExecutionError("Saved project history is invalid.")
        # Bounded validated snapshots keep D1 history small and reject corrupt data.
        self._undo_stack = [validate_project(item) for item in undo[-10:]]
        self._redo_stack = [validate_project(item) for item in redo[-10:]]

    @property
    def revision(self) -> int:
        return int(self._project.get("revision", 1))

    def get_project(self) -> dict[str, Any]:
        return deepcopy(self._project)

    def get_history_state(self) -> dict[str, Any]:
        """Return bounded JSON-safe snapshots for durable undo/redo persistence."""
        return {
            "undo": deepcopy(self._undo_stack[-10:]),
            "redo": deepcopy(self._redo_stack[-10:]),
        }

    def inspect(self) -> dict[str, Any]:
        project = self._project
        duration = max(
            (
                int(clip["start_us"]) + int(clip["duration_us"])
                for track in project["tracks"]
                for clip in track["clips"]
            ),
            default=0,
        )
        return {
            "id": project["id"],
            "name": project["name"],
            "revision": self.revision,
            "profile": deepcopy(project["video_profile"]),
            "duration_us": duration,
            "asset_count": len(project["assets"]),
            "track_count": len(project["tracks"]),
            "clip_count": sum(len(track["clips"]) for track in project["tracks"]),
            "tracks": [
                {
                    "id": track["id"],
                    "name": track["name"],
                    "type": track["type"],
                    "order": track["order"],
                    "enabled": track.get("enabled", True),
                    "muted": track.get("muted", False),
                    "solo": track.get("solo", False),
                    "visible": track.get("visible", True),
                    "locked": track.get("locked", False),
                    "clips": [
                        {
                            "id": clip["id"],
                            "kind": clip["kind"],
                            "media_id": clip.get("media_id"),
                            "start_us": clip["start_us"],
                            "duration_us": clip["duration_us"],
                            "source_in_us": clip.get("source_in_us"),
                            "source_out_us": clip.get("source_out_us"),
                            "playback_rate": clip.get("playback_rate", 1.0),
                            "transform": deepcopy(clip.get("transform")),
                            "keyframes": deepcopy(clip.get("keyframes", [])),
                            "effects": deepcopy(clip.get("effects", [])),
                            "text": deepcopy(clip.get("text")),
                        }
                        for clip in track["clips"]
                    ],
                }
                for track in sorted(project["tracks"], key=lambda item: item["order"])
            ],
        }

    def _find_track(self, project: dict[str, Any], track_id: str) -> dict[str, Any]:
        for track in project["tracks"]:
            if track["id"] == track_id:
                return track
        raise ProjectToolExecutionError(f"Track {track_id!r} does not exist.")

    def _find_clip(
        self, project: dict[str, Any], clip_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        for track in project["tracks"]:
            for clip in track["clips"]:
                if clip["id"] == clip_id:
                    if track.get("locked", False):
                        raise ProjectToolExecutionError(
                            f"Track {track['id']!r} is locked."
                        )
                    return track, clip
        raise ProjectToolExecutionError(f"Clip {clip_id!r} does not exist.")

    @staticmethod
    def _ensure_track_compatibility(track: dict[str, Any], kind: str) -> None:
        allowed = {
            "video": {"video"},
            "overlay": {"video", "image"},
            "text": {"text"},
            "audio": {"audio"},
        }
        if kind not in allowed[track["type"]]:
            raise ProjectToolExecutionError(
                f"A {kind} clip cannot be placed on a {track['type']} track."
            )

    @staticmethod
    def _asset(project: dict[str, Any], media_id: str) -> dict[str, Any]:
        for asset in project["assets"]:
            if asset["id"] == media_id:
                return asset
        raise ProjectToolExecutionError(f"Media asset {media_id!r} does not exist.")

    def _inspect_media_quality(
        self, project: dict[str, Any], media_id: str, analysis_seconds: int
    ) -> dict[str, Any]:
        """Return bounded FFprobe/FFmpeg measurements without changing the project."""
        if self._asset_root is None:
            raise ProjectToolExecutionError(
                "Media quality inspection requires a configured asset directory."
            )
        asset = self._asset(project, media_id)
        if asset.get("media_type") != "video":
            raise ProjectToolExecutionError("quality.inspect_media requires a video asset.")
        storage_key = asset.get("storage_key")
        if not isinstance(storage_key, str) or not storage_key.strip():
            raise ProjectToolExecutionError("The selected video has no local storage reference.")
        root = self._asset_root.resolve()
        media_path = (root / storage_key).resolve()
        try:
            media_path.relative_to(root)
        except ValueError as exc:
            raise ProjectToolExecutionError("The media storage reference escapes the asset directory.") from exc
        if not media_path.is_file():
            raise ProjectToolExecutionError("The selected video file is not available to the renderer.")

        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
                "-of", "json", str(media_path),
            ],
            check=True, capture_output=True, text=True, timeout=60,
        )
        try:
            metadata = json.loads(probe.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProjectToolExecutionError("FFprobe returned invalid media metadata.") from exc
        streams = metadata.get("streams", [])
        if not isinstance(streams, list):
            raise ProjectToolExecutionError("FFprobe returned an invalid stream list.")
        video_streams = [item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"]
        if not video_streams:
            raise ProjectToolExecutionError("The selected asset contains no video stream.")
        audio_streams = [item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"]
        try:
            duration = float(metadata.get("format", {}).get("duration", 0))
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= 0:
            raise ProjectToolExecutionError("FFprobe could not determine a positive video duration.")
        scan_seconds = min(duration, float(analysis_seconds))
        filters = ["-vf", "blackdetect=d=0.10:pix_th=0.10"]
        if audio_streams:
            filters.extend(["-af", "silencedetect=n=-50dB:d=0.20"])
        else:
            filters.append("-an")
        measured = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostats", "-i", str(media_path),
                "-t", f"{scan_seconds:.3f}", *filters, "-f", "null", "-",
            ],
            check=True, capture_output=True, text=True, timeout=240,
        )
        diagnostics = measured.stderr or ""
        black = [
            {"start_seconds": float(start), "end_seconds": float(end), "duration_seconds": float(length)}
            for start, end, length in re.findall(
                r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)",
                diagnostics,
            )
        ]
        silence_starts = re.findall(r"silence_start:\s*([0-9.]+)", diagnostics)
        silence_ends = re.findall(
            r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)",
            diagnostics,
        )
        silence = [
            {"start_seconds": float(start), "end_seconds": float(end), "duration_seconds": float(length)}
            for start, (end, length) in zip(silence_starts, silence_ends)
        ]
        stream = video_streams[0]
        return {
            "media_id": media_id,
            "duration_seconds": round(duration, 3),
            "analysis_coverage_seconds": round(scan_seconds, 3),
            "full_duration_scanned": scan_seconds >= duration,
            "video": {
                "codec": stream.get("codec_name"),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "frame_rate": stream.get("avg_frame_rate"),
            },
            "audio": [
                {
                    "codec": item.get("codec_name"),
                    "sample_rate": item.get("sample_rate"),
                    "channels": item.get("channels"),
                }
                for item in audio_streams
            ],
            "black_intervals": black,
            "silence_intervals": silence,
            "measurement_status": "measured",
            "semantic_visual_assessment": "not_evaluated",
            "limitations": [
                "Black and silence intervals are signal-level heuristics, not judgments about story or artistic intent.",
                "A scan shorter than the source duration is partial.",
                "No semantic visual quality verdict was produced.",
            ],
        }

    def _analyze_audio_media(
        self, project: dict[str, Any], media_id: str,
        analysis_seconds: int, silence_threshold_db: float,
    ) -> dict[str, Any]:
        """Measure audio metadata, silence and loudness without project mutation."""
        if self._asset_root is None:
            raise ProjectToolExecutionError(
                "Audio analysis requires a configured asset directory."
            )
        asset = self._asset(project, media_id)
        if asset.get("media_type") not in {"video", "audio"}:
            raise ProjectToolExecutionError(
                "audio.analyze_media requires a video or audio asset."
            )
        storage_key = asset.get("storage_key")
        if not isinstance(storage_key, str) or not storage_key.strip():
            raise ProjectToolExecutionError("The selected asset has no local storage reference.")
        root = self._asset_root.resolve()
        media_path = (root / storage_key).resolve()
        try:
            media_path.relative_to(root)
        except ValueError as exc:
            raise ProjectToolExecutionError(
                "The media storage reference escapes the asset directory."
            ) from exc
        if not media_path.is_file():
            raise ProjectToolExecutionError("The selected media file is not available.")

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,sample_rate,channels,channel_layout",
             "-of", "json", str(media_path)],
            check=True, capture_output=True, text=True, timeout=60,
        )
        try:
            metadata = json.loads(probe.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProjectToolExecutionError("FFprobe returned invalid audio metadata.") from exc
        streams = metadata.get("streams", [])
        if not isinstance(streams, list):
            raise ProjectToolExecutionError("FFprobe returned an invalid stream list.")
        audio_streams = [
            item for item in streams
            if isinstance(item, dict) and item.get("codec_type") == "audio"
        ]
        try:
            duration = float(metadata.get("format", {}).get("duration", 0))
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= 0:
            duration = float(asset.get("duration_us") or 0) / 1_000_000
        if duration <= 0:
            raise ProjectToolExecutionError("FFprobe could not determine a positive media duration.")
        scan_seconds = min(duration, float(analysis_seconds))
        base = {
            "media_id": media_id,
            "duration_seconds": round(duration, 3),
            "analysis_coverage_seconds": round(scan_seconds, 3),
            "full_duration_scanned": scan_seconds >= duration,
            "audio_streams": [
                {
                    "codec": item.get("codec_name"),
                    "sample_rate": item.get("sample_rate"),
                    "channels": item.get("channels"),
                    "channel_layout": item.get("channel_layout"),
                }
                for item in audio_streams
            ],
            "silence_intervals": [],
            "loudness": None,
            "measurement_status": "no_audio_stream" if not audio_streams else "measured",
            "semantic_audio_assessment": "not_evaluated",
        }
        if not audio_streams:
            base["limitations"] = [
                "The selected media contains no audio stream.",
                "Speech, music, beat and emotional context were not evaluated.",
            ]
            return base

        filter_chain = (
            f"silencedetect=n={silence_threshold_db:.2f}dB:d=0.20,"
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json"
        )
        measured = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(media_path),
             "-t", f"{scan_seconds:.3f}", "-vn", "-af", filter_chain,
             "-f", "null", "-"],
            check=True, capture_output=True, text=True, timeout=240,
        )
        diagnostics = measured.stderr or ""
        silence_starts = re.findall(r"silence_start:\s*([0-9.]+)", diagnostics)
        silence_ends = re.findall(
            r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)",
            diagnostics,
        )
        base["silence_intervals"] = [
            {"start_seconds": float(start), "end_seconds": float(end),
             "duration_seconds": float(length)}
            for start, (end, length) in zip(silence_starts, silence_ends)
        ]
        loudness_blocks = re.findall(r"\{[^{}]*\}", diagnostics, flags=re.DOTALL)
        if loudness_blocks:
            try:
                values = json.loads(loudness_blocks[-1])
                keys = (
                    "input_i", "input_tp", "input_lra", "input_thresh",
                    "target_offset", "output_i", "output_tp", "output_lra",
                )
                base["loudness"] = {
                    key: (float(values[key]) if values.get(key) not in (None, " -inf", "-inf") else None)
                    for key in keys if key in values
                }
            except (TypeError, ValueError, json.JSONDecodeError):
                base["loudness"] = None
        base["limitations"] = [
            "Silence and loudness are signal measurements, not speech or music recognition.",
            "A scan shorter than the source duration is partial.",
            "Speech transcription, beat positions and semantic audio context are not evaluated.",
            "Loudness values are included only when FFmpeg returns valid measurement data.",
        ]
        return base

    def set_persisted_asset_id(self, media_id: str, release_asset_id: int) -> None:
        """Attach private Release storage metadata without creating a new edit revision."""
        if isinstance(release_asset_id, bool) or not isinstance(release_asset_id, int) or release_asset_id < 1:
            raise ProjectToolExecutionError("The private media storage returned an invalid asset ID.")
        found = False
        for document in [self._project, *self._undo_stack, *self._redo_stack]:
            for asset in document.get("assets", []):
                if asset.get("id") == media_id:
                    asset["release_asset_id"] = release_asset_id
                    found = True
        if not found:
            raise ProjectToolExecutionError("The generated project asset no longer exists.")
        self._project = validate_project(self._project)
        self._undo_stack = [validate_project(item) for item in self._undo_stack]
        self._redo_stack = [validate_project(item) for item in self._redo_stack]

    def _local_asset_path(self, project: dict[str, Any], media_id: str, expected_type: str) -> tuple[dict[str, Any], Path]:
        if self._asset_root is None:
            raise ProjectToolExecutionError("Media generation requires a configured asset directory.")
        asset = self._asset(project, media_id)
        if asset.get("media_type") != expected_type:
            raise ProjectToolExecutionError(f"This operation requires a {expected_type} asset.")
        storage_key = asset.get("storage_key")
        if not isinstance(storage_key, str) or not storage_key.strip():
            raise ProjectToolExecutionError("The selected media has no local storage reference.")
        root = self._asset_root.resolve()
        path = (root / storage_key).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ProjectToolExecutionError("The media storage reference escapes the asset directory.") from exc
        if not path.is_file():
            raise ProjectToolExecutionError("The selected media file is not available to the renderer.")
        return asset, path

    def _extract_audio_asset(self, project: dict[str, Any], media_id: str, output_format: str) -> dict[str, Any]:
        source_asset, source_path = self._local_asset_path(project, media_id, "video")
        if self._asset_root is None:
            raise ProjectToolExecutionError("Audio extraction requires a configured asset directory.")
        extension = output_format if output_format in {"m4a", "mp3", "wav"} else "m4a"
        media_id_new = _new_id("audio")
        filename = f"{media_id_new}.{extension}"
        output_path = self._asset_root / filename
        if output_path.exists():
            raise ProjectToolExecutionError("The generated audio filename already exists.")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
             "-of", "json", str(source_path)],
            check=True, capture_output=True, text=True, timeout=60,
        )
        metadata = json.loads(probe.stdout)
        if not any(item.get("codec_type") == "audio" for item in metadata.get("streams", []) if isinstance(item, dict)):
            raise ProjectToolExecutionError("The selected video contains no audio stream to extract.")
        codec_args = {
            "m4a": ["-c:a", "aac", "-b:a", "192k"],
            "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
            "wav": ["-c:a", "pcm_s16le"],
        }[extension]
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-i", str(source_path),
                 "-map", "0:a:0", "-vn", *codec_args, str(output_path)],
                check=True, capture_output=True, text=True, timeout=300,
            )
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise ProjectToolExecutionError("FFmpeg produced an empty audio file.")
            output_probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                 "-of", "json", str(output_path)],
                check=True, capture_output=True, text=True, timeout=60,
            )
            output_data = json.loads(output_probe.stdout)
            duration = float(output_data.get("format", {}).get("duration") or 0)
            if duration <= 0 or not any(item.get("codec_type") == "audio" for item in output_data.get("streams", []) if isinstance(item, dict)):
                raise ProjectToolExecutionError("The extracted file failed audio-stream or duration verification.")
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            if isinstance(exc, ProjectToolExecutionError):
                raise
            raise ProjectToolExecutionError("Audio extraction failed: " + str(exc)[:240]) from exc
        asset = {
            "id": media_id_new, "media_type": "audio", "file_name": filename,
            "storage_key": filename, "size_bytes": output_path.stat().st_size,
            "duration_us": max(1, int(round(duration * 1_000_000))),
            "generated": True, "generated_from_media_id": source_asset["id"],
        }
        project["assets"].append(asset)
        return {"media_id": media_id_new, "file_name": filename,
                "duration_us": asset["duration_us"], "size_bytes": asset["size_bytes"],
                "storage_status": "pending_private_upload"}

    def _create_proxy_asset(self, project: dict[str, Any], media_id: str) -> dict[str, Any]:
        source_asset, source_path = self._local_asset_path(project, media_id, "video")
        if self._asset_root is None:
            raise ProjectToolExecutionError("Proxy generation requires a configured asset directory.")
        if any(item.get("proxy_for_media_id") == media_id for item in project["assets"]):
            raise ProjectToolExecutionError("A proxy already exists for this video asset.")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height",
             "-of", "json", str(source_path)],
            check=True, capture_output=True, text=True, timeout=60,
        )
        metadata = json.loads(probe.stdout)
        video = next(
            (item for item in metadata.get("streams", [])
             if isinstance(item, dict) and item.get("codec_type") == "video"),
            None,
        )
        duration = float(metadata.get("format", {}).get("duration") or 0)
        if video is None or duration <= 0 or duration > 1800:
            raise ProjectToolExecutionError(
                "Proxy source must contain readable video with a duration up to 30 minutes."
            )
        proxy_id = _new_id("proxy")
        filename = proxy_id + ".mp4"
        output_path = self._asset_root / filename
        if output_path.exists():
            raise ProjectToolExecutionError("The generated proxy filename already exists.")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                    "-i", str(source_path), "-map", "0:v:0", "-map", "0:a?",
                    "-vf",
                    "scale=w='min(640,iw)':h='min(360,ih)':"
                    "force_original_aspect_ratio=decrease:force_divisible_by=2",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-b:v", "150k", "-maxrate", "200k", "-bufsize", "400k",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "48k",
                    "-ac", "2", "-movflags", "+faststart", str(output_path),
                ],
                check=True, capture_output=True, text=True, timeout=600,
            )
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise ProjectToolExecutionError("FFmpeg produced an empty proxy file.")
            if output_path.stat().st_size > 50 * 1024 * 1024:
                raise ProjectToolExecutionError("The generated proxy exceeds the 50 MB per-file storage limit.")
            proxy_probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration:stream=codec_type,width,height",
                 "-of", "json", str(output_path)],
                check=True, capture_output=True, text=True, timeout=60,
            )
            proxy_metadata = json.loads(proxy_probe.stdout)
            proxy_video = next(
                (item for item in proxy_metadata.get("streams", [])
                 if isinstance(item, dict) and item.get("codec_type") == "video"),
                None,
            )
            proxy_duration = float(proxy_metadata.get("format", {}).get("duration") or 0)
            if (
                proxy_video is None
                or int(proxy_video.get("width") or 0) < 1
                or int(proxy_video.get("height") or 0) < 1
                or int(proxy_video.get("width") or 0) > 640
                or int(proxy_video.get("height") or 0) > 360
                or proxy_duration <= 0
                or abs(proxy_duration - duration) > max(0.25, duration * 0.02)
            ):
                raise ProjectToolExecutionError("The generated proxy failed video, dimension or duration verification.")
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            if isinstance(exc, ProjectToolExecutionError):
                raise
            raise ProjectToolExecutionError("Proxy generation failed: " + str(exc)[:240]) from exc

        asset = {
            "id": proxy_id,
            "media_type": "video",
            "file_name": filename,
            "storage_key": filename,
            "size_bytes": output_path.stat().st_size,
            "duration_us": max(1, int(round(proxy_duration * 1_000_000))),
            "generated": True,
            "generated_from_media_id": source_asset["id"],
            "proxy_for_media_id": source_asset["id"],
            "proxy_profile": {"max_width": 640, "max_height": 360, "video_bitrate": 150000},
        }
        project["assets"].append(asset)
        return {
            "proxy_media_id": proxy_id,
            "source_media_id": source_asset["id"],
            "file_name": filename,
            "duration_us": asset["duration_us"],
            "width": int(proxy_video["width"]),
            "height": int(proxy_video["height"]),
            "size_bytes": asset["size_bytes"],
            "storage_status": "pending_private_upload",
        }

    def _create_freeze_frame(self, project: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        source_asset, source_path = self._local_asset_path(project, args["media_id"], "video")
        track = self._find_track(project, args["track_id"])
        if track.get("locked", False) or track.get("type") != "overlay":
            raise ProjectToolExecutionError("A freeze-frame hold must be placed on an unlocked overlay track.")
        timestamp_us = int(args["timestamp_us"])
        duration_us = int(args["duration_us"])
        if duration_us <= 0 or duration_us > 600_000_000:
            raise ProjectToolExecutionError("Freeze-frame hold duration must be between 1 microsecond and 10 minutes.")
        if timestamp_us < 0:
            raise ProjectToolExecutionError("Freeze-frame timestamp cannot be negative.")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
             "-of", "json", str(source_path)],
            check=True, capture_output=True, text=True, timeout=60,
        )
        metadata = json.loads(probe.stdout)
        video = next((item for item in metadata.get("streams", []) if isinstance(item, dict) and item.get("codec_type") == "video"), None)
        source_duration = float(metadata.get("format", {}).get("duration") or 0)
        if video is None or source_duration <= 0:
            raise ProjectToolExecutionError("The selected source does not contain readable video.")
        if timestamp_us >= int(source_duration * 1_000_000):
            raise ProjectToolExecutionError("Freeze-frame timestamp must be inside the source video duration.")
        if self._asset_root is None:
            raise ProjectToolExecutionError("Freeze-frame generation requires a configured asset directory.")
        image_id = _new_id("frame")
        filename = image_id + ".png"
        output_path = self._asset_root / filename
        if output_path.exists():
            raise ProjectToolExecutionError("The generated freeze-frame filename already exists.")
        timestamp = timestamp_us / 1_000_000
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-i", str(source_path),
                 "-ss", f"{timestamp:.6f}", "-frames:v", "1", "-an", str(output_path)],
                check=True, capture_output=True, text=True, timeout=120,
            )
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise ProjectToolExecutionError("FFmpeg did not produce a readable freeze-frame image.")
            image_probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height", "-of", "json", str(output_path)],
                check=True, capture_output=True, text=True, timeout=60,
            )
            image_stream = json.loads(image_probe.stdout).get("streams", [])
            if not image_stream or int(image_stream[0].get("width") or 0) < 1 or int(image_stream[0].get("height") or 0) < 1:
                raise ProjectToolExecutionError("The generated freeze-frame image failed verification.")
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            if isinstance(exc, ProjectToolExecutionError):
                raise
            raise ProjectToolExecutionError("Freeze-frame generation failed: " + str(exc)[:240]) from exc
        asset = {
            "id": image_id, "media_type": "image", "file_name": filename,
            "storage_key": filename, "size_bytes": output_path.stat().st_size,
            "generated": True, "generated_from_media_id": source_asset["id"],
        }
        project["assets"].append(asset)
        clip = {
            "id": _new_id("clip"), "kind": "image", "media_id": image_id,
            "start_us": int(args["start_us"]), "duration_us": duration_us,
            "source_in_us": 0, "playback_rate": 1.0, "effects": [], "keyframes": [],
        }
        track["clips"].append(clip)
        return {"media_id": image_id, "clip_id": clip["id"], "track_id": track["id"],
                "timestamp_us": timestamp_us, "start_us": clip["start_us"],
                "duration_us": duration_us, "width": int(image_stream[0]["width"]),
                "height": int(image_stream[0]["height"]),
                "storage_status": "pending_private_upload"}

    def _apply(
        self, project: dict[str, Any], name: str, args: dict[str, Any]
    ) -> tuple[Any, bool]:
        if name == "project.inspect":
            # This reports the candidate document, including earlier calls in
            # the same batch, without exposing server filesystem paths.
            return self._inspect_document(project), False

        if name == "media.list":
            media_type = args.get("media_type")
            folder = args.get("folder")
            items = [
                {
                    key: value
                    for key, value in asset.items()
                    if key not in {"storage_key"}
                }
                for asset in project["assets"]
                if (media_type is None or asset["media_type"] == media_type)
                and (folder is None or asset.get("folder", "Unsorted") == folder)
            ]
            return items, False

        if name == "media.organize_asset":
            asset = self._asset(project, args["media_id"])
            folder = args["folder"].strip()
            tags = args.get("tags", asset.get("tags", []))
            if not folder:
                raise ProjectToolExecutionError("Enter a non-empty media folder name.")
            asset["folder"] = folder
            asset["tags"] = list(tags)
            return {
                "media_id": asset["id"],
                "folder": asset["folder"],
                "tags": deepcopy(asset["tags"]),
            }, True

        if name == "quality.inspect_media":
            return self._inspect_media_quality(
                project, args["media_id"], int(args.get("analysis_seconds", 600))
            ), False

        if name == "audio.analyze_media":
            return self._analyze_audio_media(
                project, args["media_id"],
                int(args.get("analysis_seconds", 600)),
                float(args.get("silence_threshold_db", -50)),
            ), False

        if name == "media.create_proxy":
            return self._create_proxy_asset(project, args["media_id"]), True

        if name == "media.extract_audio":
            return self._extract_audio_asset(
                project, args["media_id"], args.get("format", "m4a")
            ), True

        if name == "timeline.create_freeze_frame":
            return self._create_freeze_frame(project, args), True

        if name == "media.detect_scenes":
            if self._asset_root is None:
                raise ProjectToolExecutionError(
                    "Scene detection requires a configured asset directory."
                )
            asset = self._asset(project, args["media_id"])
            if asset.get("media_type") != "video":
                raise ProjectToolExecutionError("media.detect_scenes requires a video asset.")
            storage_key = asset.get("storage_key")
            if not isinstance(storage_key, str) or not storage_key.strip():
                raise ProjectToolExecutionError("The selected video has no local storage reference.")
            root = self._asset_root.resolve()
            media_path = (root / storage_key).resolve()
            try:
                media_path.relative_to(root)
            except ValueError as exc:
                raise ProjectToolExecutionError(
                    "The media storage reference escapes the asset directory."
                ) from exc
            if not media_path.is_file():
                raise ProjectToolExecutionError("The selected video file is not available to the renderer.")
            duration = float(asset.get("duration_us") or 0) / 1_000_000
            if duration <= 0:
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)],
                    check=True, capture_output=True, text=True, timeout=60,
                )
                try:
                    duration = float(probe.stdout.strip())
                except (TypeError, ValueError) as exc:
                    raise ProjectToolExecutionError("FFprobe could not determine video duration.") from exc
            if duration <= 0:
                raise ProjectToolExecutionError("The video duration must be positive.")
            scan_seconds = min(duration, float(args.get("analysis_seconds", 600)))
            threshold = float(args.get("threshold", 0.35))
            filter_expression = f"select='gt(scene,{threshold:.3f})',showinfo"
            detected = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(media_path),
                 "-t", f"{scan_seconds:.3f}", "-vf", filter_expression, "-an",
                 "-f", "null", "-"],
                check=True, capture_output=True, text=True, timeout=240,
            )
            timestamps = sorted({
                round(float(value), 3)
                for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", detected.stderr or "")
                if 0 <= float(value) <= scan_seconds
            })
            return {
                "media_id": args["media_id"],
                "threshold": threshold,
                "analysis_coverage_seconds": round(scan_seconds, 3),
                "full_duration_scanned": scan_seconds >= duration,
                "candidate_scene_changes": [
                    {"time_seconds": value, "confidence": "heuristic"}
                    for value in timestamps[:200]
                ],
                "candidate_count": min(len(timestamps), 200),
                "semantic_scene_labels": "not_evaluated",
                "limitations": [
                    "FFmpeg scene scores identify visual-change candidates, not confirmed story or shot boundaries.",
                    "A scan shorter than the source duration is partial.",
                    "No objects, actions or narrative meaning were classified.",
                ],
            }, False

        if name == "project.set_profile":
            project["video_profile"] = {
                "width": args["width"],
                "height": args["height"],
                "frame_rate": {
                    "numerator": args["fps_numerator"],
                    "denominator": args["fps_denominator"],
                },
            }
            return {"updated": "video_profile"}, True

        if name == "timeline.add_track":
            order = args.get(
                "order",
                max((int(track["order"]) for track in project["tracks"]), default=-1) + 1,
            )
            if any(track["order"] == order for track in project["tracks"]):
                raise ProjectToolExecutionError(
                    f"Track order {order} is already in use."
                )
            track = {
                "id": _new_id("track"),
                "type": args["track_type"],
                "name": args["name"],
                "order": order,
                "enabled": True,
                "locked": False,
                "muted": False,
                "solo": False,
                "visible": True,
                "clips": [],
            }
            project["tracks"].append(track)
            return {"track_id": track["id"], "order": order}, True

        if name == "timeline.remove_track":
            track = self._find_track(project, args["track_id"])
            if track.get("locked", False):
                raise ProjectToolExecutionError("The selected track is locked.")
            clip_ids = {clip["id"] for clip in track["clips"]}
            project["tracks"].remove(track)
            _prune_clip_groups(project, clip_ids)
            project["transitions"] = [
                item for item in project.get("transitions", [])
                if item["from_clip_id"] not in clip_ids
                and item["to_clip_id"] not in clip_ids
            ]
            return {"removed_track_id": args["track_id"], "removed_clips": len(clip_ids)}, True

        if name == "timeline.replace_clip_media":
            track, clip = self._find_clip(project, args["clip_id"])
            if track.get("locked", False):
                raise ProjectToolExecutionError("The selected track is locked.")
            asset = self._asset(project, args["media_id"])
            if asset.get("media_type") != clip["kind"]:
                raise ProjectToolExecutionError(
                    f"Replace requires a {clip['kind']} asset; selected asset is {asset.get('media_type')!r}."
                )
            if any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                raise ProjectToolExecutionError(
                    "Replacing a clip with an animated speed curve is not supported yet."
                )
            rate = float(clip.get("playback_rate", 1.0))
            if clip["kind"] == "image" and rate != 1.0:
                raise ProjectToolExecutionError("Still-image clips must use normal speed.")
            old_source_in = int(clip.get("source_in_us", 0))
            if "source_out_us" in clip:
                required_source_duration = int(clip["source_out_us"]) - old_source_in
            else:
                required_source_duration = round(int(clip["duration_us"]) * rate)
            if required_source_duration < 1:
                raise ProjectToolExecutionError("The selected clip has an invalid source range.")
            known_duration = asset.get("duration_us")
            if (
                clip["kind"] != "image"
                and known_duration is not None
                and required_source_duration > int(known_duration)
            ):
                raise ProjectToolExecutionError(
                    "The replacement asset is too short for the selected clip's current duration and speed."
                )
            clip["media_id"] = asset["id"]
            clip["source_in_us"] = 0
            if clip["kind"] == "image":
                clip.pop("source_out_us", None)
            else:
                clip["source_out_us"] = required_source_duration
            return {
                "clip_id": clip["id"],
                "track_id": track["id"],
                "media_id": asset["id"],
                "file_name": asset.get("file_name"),
                "preserved_start_us": clip["start_us"],
                "preserved_duration_us": clip["duration_us"],
                "preserved_playback_rate": rate,
            }, True

        if name == "timeline.ripple_overwrite_clip":
            track, clip = self._find_clip(project, args["clip_id"])
            if track.get("locked", False):
                raise ProjectToolExecutionError("The selected track is locked.")
            asset = self._asset(project, args["media_id"])
            if asset.get("media_type") != clip["kind"]:
                raise ProjectToolExecutionError(
                    f"Ripple overwrite requires a {clip['kind']} asset; selected asset is {asset.get('media_type')!r}."
                )
            if any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                raise ProjectToolExecutionError("Ripple overwrite does not support animated speed curves.")
            old_start = int(clip["start_us"])
            old_duration = int(clip["duration_us"])
            old_end = old_start + old_duration
            rate = float(clip.get("playback_rate", 1.0))
            new_duration = int(args.get("duration_us") or asset.get("duration_us") or old_duration)
            if new_duration < 1 or old_start + new_duration > 2**53 - 1:
                raise ProjectToolExecutionError("The replacement duration is outside safe timeline limits.")
            required_source = round(new_duration * rate)
            known_duration = asset.get("duration_us")
            if clip["kind"] != "image" and known_duration is not None and required_source > int(known_duration):
                raise ProjectToolExecutionError("The replacement media is too short for the selected duration and speed.")
            for other in track["clips"]:
                if other["id"] == clip["id"]:
                    continue
                other_start = int(other["start_us"])
                other_end = other_start + int(other["duration_us"])
                if other_start < old_end and other_end > old_start:
                    raise ProjectToolExecutionError("Ripple overwrite requires non-overlapping clips on the target track.")
            delta = new_duration - old_duration
            for other in track["clips"]:
                if other["id"] != clip["id"] and int(other["start_us"]) >= old_end:
                    next_start = int(other["start_us"]) + delta
                    if next_start < old_start + new_duration or next_start < 0 or next_start > 2**53 - 1:
                        raise ProjectToolExecutionError("Ripple overwrite would cause a clip overlap or unsafe time.")
            clip["media_id"] = asset["id"]
            clip["duration_us"] = new_duration
            clip["source_in_us"] = 0
            if clip["kind"] == "image":
                clip.pop("source_out_us", None)
            else:
                clip["source_out_us"] = required_source
            shifted_ids = []
            for other in track["clips"]:
                if other["id"] != clip["id"] and int(other["start_us"]) >= old_end:
                    other["start_us"] = int(other["start_us"]) + delta
                    shifted_ids.append(other["id"])
            return {
                "clip_id": clip["id"], "media_id": asset["id"],
                "old_duration_us": old_duration, "new_duration_us": new_duration,
                "shifted_clip_ids": shifted_ids,
            }, True

        if name == "timeline.ripple_insert_clip":
            track = self._find_track(project, args["track_id"])
            kind = args["kind"]
            if track.get("locked", False):
                raise ProjectToolExecutionError("The selected track is locked.")
            self._ensure_track_compatibility(track, kind)
            asset = self._asset(project, args["media_id"])
            expected_type = {"video": "video", "image": "image", "audio": "audio"}[kind]
            if asset.get("media_type") != expected_type:
                raise ProjectToolExecutionError(
                    f"Asset type {asset.get('media_type')!r} cannot be inserted as {kind}."
                )
            rate = float(args.get("playback_rate", 1.0))
            if kind == "image" and rate != 1.0:
                raise ProjectToolExecutionError("Still images use normal playback speed.")
            insert_at = int(args["start_us"])
            duration = int(args["duration_us"])
            if duration < 1 or insert_at + duration > 2**53 - 1:
                raise ProjectToolExecutionError("Inserted clip duration is outside safe timeline limits.")
            requested_ids = args.get("ripple_track_ids") or [track["id"]]
            if len(requested_ids) != len(set(requested_ids)):
                raise ProjectToolExecutionError("Ripple track IDs must be unique.")
            if track["id"] not in requested_ids:
                raise ProjectToolExecutionError("The insertion track must be included in ripple_track_ids.")
            ripple_tracks = [self._find_track(project, track_id) for track_id in requested_ids]
            for affected in ripple_tracks:
                if affected.get("locked", False):
                    raise ProjectToolExecutionError(f"Ripple insertion cannot shift locked track {affected['id']!r}.")
                for existing in affected["clips"]:
                    existing_start = int(existing["start_us"])
                    existing_end = existing_start + int(existing["duration_us"])
                    if existing_start < insert_at < existing_end:
                        raise ProjectToolExecutionError(
                            f"Ripple insert cannot split through an existing clip {existing['id']!r} on track {affected['id']!r}; split it first."
                        )
            affected_clip_ids = {
                clip["id"] for affected in ripple_tracks for clip in affected["clips"]
            }
            clip_by_id = {
                clip["id"]: clip for affected in ripple_tracks for clip in affected["clips"]
            }
            for transition in project.get("transitions", []):
                from_id, to_id = transition["from_clip_id"], transition["to_clip_id"]
                if from_id not in affected_clip_ids or to_id not in affected_clip_ids:
                    continue
                from_start = int(clip_by_id[from_id]["start_us"])
                to_start = int(clip_by_id[to_id]["start_us"])
                if (from_start < insert_at <= to_start) or (to_start < insert_at <= from_start):
                    raise ProjectToolExecutionError("Ripple insert cannot split through an existing transition.")
            shifted_ids = []
            for affected in ripple_tracks:
                for existing in affected["clips"]:
                    if int(existing["start_us"]) >= insert_at:
                        existing["start_us"] = int(existing["start_us"]) + duration
                        shifted_ids.append(existing["id"])
            clip = {
                "id": _new_id("clip"), "kind": kind, "media_id": args["media_id"],
                "start_us": insert_at, "duration_us": duration,
                "source_in_us": int(args.get("source_in_us", 0)),
                "playback_rate": rate, "effects": [], "keyframes": [],
            }
            if kind != "image" and "source_out_us" in args:
                clip["source_out_us"] = int(args["source_out_us"])
            track["clips"].append(clip)
            return {
                "clip_id": clip["id"], "track_id": track["id"],
                "ripple_track_ids": [item["id"] for item in ripple_tracks],
                "inserted_start_us": insert_at, "inserted_duration_us": duration,
                "shifted_clip_ids": sorted(shifted_ids),
            }, True

        if name == "timeline.add_clip":
            track = self._find_track(project, args["track_id"])
            if track.get("locked", False):
                raise ProjectToolExecutionError("The selected track is locked.")
            kind = args["kind"]
            self._ensure_track_compatibility(track, kind)
            asset = self._asset(project, args["media_id"])
            expected_media_type = {"video": "video", "image": "image", "audio": "audio"}[kind]
            if asset["media_type"] != expected_media_type:
                raise ProjectToolExecutionError(
                    f"Asset type {asset['media_type']!r} cannot be used as {kind}."
                )
            rate = float(args.get("playback_rate", 1.0))
            if kind == "image" and rate != 1.0:
                raise ProjectToolExecutionError("Still images use normal playback speed.")
            clip = {
                "id": _new_id("clip"),
                "kind": kind,
                "media_id": args["media_id"],
                "start_us": args["start_us"],
                "duration_us": args["duration_us"],
                "source_in_us": args.get("source_in_us", 0),
                "playback_rate": rate,
                "effects": [],
                "keyframes": [],
            }
            if "source_out_us" in args:
                clip["source_out_us"] = args["source_out_us"]
            track["clips"].append(clip)
            return {"clip_id": clip["id"], "track_id": track["id"]}, True

        if name == "timeline.add_text_clip":
            track = self._find_track(project, args["track_id"])
            if track.get("locked", False) or track["type"] != "text":
                raise ProjectToolExecutionError(
                    "A text clip must be placed on an unlocked text track."
                )
            text = {
                "content": args["content"],
                "size": 48,
                "weight": 700,
                "fgcolour": "#FFFFFF",
                "outline": 0,
                "halign": "center",
                "valign": "middle",
                "x_percent": 5,
                "y_percent": 68,
                "width_percent": 90,
                "height_percent": 25,
            }
            text.update(args.get("text_style", {}))
            clip = {
                "id": _new_id("text"),
                "kind": "text",
                "start_us": args["start_us"],
                "duration_us": args["duration_us"],
                "text": text,
                "effects": [],
                "keyframes": [],
            }
            track["clips"].append(clip)
            return {"clip_id": clip["id"], "track_id": track["id"]}, True

        if name == "captions.add_word_timed":
            track = self._find_track(project, args["track_id"])
            if track.get("locked", False) or track["type"] != "text":
                raise ProjectToolExecutionError(
                    "Word-timed captions require an unlocked text track."
                )
            words = args["words"]
            previous_end = -1
            for index, word in enumerate(words):
                start_us = word["start_us"]
                end_us = word["end_us"]
                if end_us <= start_us:
                    raise ProjectToolExecutionError(
                        f"Caption word {index} must end after it starts."
                    )
                if start_us < previous_end:
                    raise ProjectToolExecutionError(
                        "Word timestamps must be chronological and must not overlap."
                    )
                previous_end = end_us
            style = {
                "size": 48,
                "weight": 700,
                "fgcolour": "#FFFFFF",
                "outline": 0,
                "halign": "center",
                "valign": "middle",
                "x_percent": 5,
                "y_percent": 68,
                "width_percent": 90,
                "height_percent": 25,
            }
            style.update(args.get("text_style", {}))
            created = []
            for word in words:
                clip = {
                    "id": _new_id("caption"),
                    "kind": "text",
                    "start_us": word["start_us"],
                    "duration_us": word["end_us"] - word["start_us"],
                    "text": {"content": word["text"], **deepcopy(style)},
                    "effects": [],
                    "keyframes": [],
                }
                track["clips"].append(clip)
                created.append({
                    "clip_id": clip["id"],
                    "text": word["text"],
                    "start_us": word["start_us"],
                    "end_us": word["end_us"],
                })
            return {
                "track_id": track["id"],
                "word_clip_count": len(created),
                "caption_clips": created,
                "transcription_performed": False,
            }, True

        if name == "captions.import_subtitles":
            track = self._find_track(project, args["track_id"])
            if track.get("locked", False) or track["type"] != "text":
                raise ProjectToolExecutionError("Subtitle import requires an unlocked text track.")
            cues = args["cues"]
            previous_end = -1
            total_text = 0
            for index, cue in enumerate(cues):
                start_us, end_us = int(cue["start_us"]), int(cue["end_us"])
                text_value = str(cue["text"]).strip()
                if not text_value or end_us <= start_us:
                    raise ProjectToolExecutionError(f"Subtitle cue {index} has invalid text or timing.")
                if start_us < previous_end:
                    raise ProjectToolExecutionError("Subtitle cues must be chronological and must not overlap.")
                previous_end = end_us
                total_text += len(text_value)
            if total_text > 100000:
                raise ProjectToolExecutionError("Imported subtitle text exceeds the 100,000-character project limit.")
            style = {
                "size": 42, "weight": 700, "fgcolour": "#FFFFFF", "outline": 1,
                "halign": "center", "valign": "middle",
                "x_percent": 5, "y_percent": 70, "width_percent": 90, "height_percent": 22,
            }
            style.update(deepcopy(args.get("text_style", {})))
            created = []
            for cue in cues:
                caption_text = str(cue["text"]).strip()
                caption = {
                    "id": _new_id("caption"), "kind": "text",
                    "start_us": int(cue["start_us"]),
                    "duration_us": int(cue["end_us"]) - int(cue["start_us"]),
                    "text": {"content": caption_text, **deepcopy(style)},
                    "effects": [], "keyframes": [],
                }
                track["clips"].append(caption)
                created.append(caption["id"])
            return {
                "track_id": track["id"], "cue_count": len(created),
                "created_clip_ids": created, "transcription_performed": False,
            }, True

        if name == "text.update_clip":
            _, clip = self._find_clip(project, args["clip_id"])
            if clip["kind"] != "text":
                raise ProjectToolExecutionError("text.update_clip requires a text/title clip.")
            text_spec = clip.get("text")
            if not isinstance(text_spec, dict):
                raise ProjectToolExecutionError("The selected text clip has no valid text specification.")
            if "content" in args:
                text_spec["content"] = args["content"]
            if "text_style" in args:
                text_spec.update(deepcopy(args["text_style"]))
            return {"clip_id": clip["id"], "text": deepcopy(text_spec)}, True

        if name == "timeline.move_clip":
            source_track, clip = self._find_clip(project, args["clip_id"])
            target_track = self._find_track(project, args.get("track_id", source_track["id"]))
            if target_track.get("locked", False):
                raise ProjectToolExecutionError("The destination track is locked.")
            self._ensure_track_compatibility(target_track, clip["kind"])
            new_start = int(args["start_us"])
            delta = new_start - int(clip["start_us"])
            group = next((item for item in project.get("clip_groups", [])
                          if item.get("id") == clip.get("group_id")), None)
            member_ids = set(group["clip_ids"]) if group else {clip["id"]}
            members = []
            for member_track in project["tracks"]:
                for member_clip in member_track["clips"]:
                    if member_clip["id"] not in member_ids:
                        continue
                    if member_track.get("locked", False):
                        raise ProjectToolExecutionError("A linked clip is on a locked track.")
                    destination = target_track if member_clip["id"] == clip["id"] else member_track
                    if destination["id"] == target_track["id"]:
                        self._ensure_track_compatibility(destination, member_clip["kind"])
                    proposed = new_start if member_clip["id"] == clip["id"] else int(member_clip["start_us"]) + delta
                    proposed_end = proposed + int(member_clip["duration_us"])
                    for other in destination["clips"]:
                        if other["id"] in member_ids:
                            continue
                        other_start = int(other["start_us"])
                        other_end = other_start + int(other["duration_us"])
                        if proposed < other_end and proposed_end > other_start:
                            raise ProjectToolExecutionError("Moving this clip or linked group would overlap another clip.")
                    members.append((member_track, destination, member_clip, proposed))
            if len(members) != len(member_ids):
                raise ProjectToolExecutionError("The linked group references a missing clip.")
            # All validation completes before any member is moved.
            for old_track, destination, member_clip, proposed in members:
                if old_track is not destination:
                    old_track["clips"].remove(member_clip)
                    destination["clips"].append(member_clip)
                member_clip["start_us"] = proposed
            return {
                "clip_id": clip["id"], "from_track_id": source_track["id"],
                "to_track_id": target_track["id"], "start_us": clip["start_us"],
                "moved_clip_ids": sorted(member_ids),
            }, True

        if name == "timeline.group_clips":
            member_ids = args["clip_ids"]
            if len(member_ids) != len(set(member_ids)):
                raise ProjectToolExecutionError("A linked group cannot contain duplicate clip IDs.")
            members = []
            for clip_id in member_ids:
                member_track, member_clip = self._find_clip(project, clip_id)
                if member_track.get("locked", False):
                    raise ProjectToolExecutionError("Clips on locked tracks cannot be grouped.")
                if member_clip.get("group_id"):
                    raise ProjectToolExecutionError("A selected clip already belongs to a linked group.")
                members.append(member_clip)
            group_id = _new_id("group")
            group = {
                "id": group_id,
                "name": str(args.get("name") or "Linked group").strip()[:80] or "Linked group",
                "clip_ids": list(member_ids),
            }
            for member in members:
                member["group_id"] = group_id
            project.setdefault("clip_groups", []).append(group)
            return {"group_id": group_id, "clip_ids": list(member_ids), "name": group["name"]}, True

        if name == "timeline.ungroup_clips":
            requested = set(args["clip_ids"])
            groups = project.setdefault("clip_groups", [])
            affected = []
            for group in list(groups):
                removed = requested.intersection(group["clip_ids"])
                if not removed:
                    continue
                affected.extend(sorted(removed))
                group["clip_ids"] = [item for item in group["clip_ids"] if item not in removed]
                for track_item in project["tracks"]:
                    for member in track_item["clips"]:
                        if member["id"] in removed:
                            member.pop("group_id", None)
                if len(group["clip_ids"]) < 2:
                    for track_item in project["tracks"]:
                        for member in track_item["clips"]:
                            if member["id"] in group["clip_ids"]:
                                member.pop("group_id", None)
                    groups.remove(group)
            if not affected:
                raise ProjectToolExecutionError("None of the selected clips belongs to a linked group.")
            return {"ungrouped_clip_ids": affected}, True

        if name == "timeline.add_marker":
            marker = {
                "id": _new_id("marker"),
                "time_us": int(args["time_us"]),
                "label": args["label"].strip(),
                "colour": args.get("colour", "#F5C542"),
            }
            if not marker["label"]:
                raise ProjectToolExecutionError("Enter a marker label.")
            return_value = deepcopy(marker)
            project.setdefault("markers", []).append(marker)
            return return_value, True

        if name == "timeline.move_marker":
            marker = next((item for item in project.get("markers", [])
                           if item["id"] == args["marker_id"]), None)
            if marker is None:
                raise ProjectToolExecutionError("The selected marker does not exist.")
            marker["time_us"] = int(args["time_us"])
            if "label" in args:
                marker["label"] = args["label"].strip()
                if not marker["label"]:
                    raise ProjectToolExecutionError("Enter a marker label.")
            return deepcopy(marker), True

        if name == "timeline.remove_marker":
            markers = project.setdefault("markers", [])
            marker = next((item for item in markers if item["id"] == args["marker_id"]), None)
            if marker is None:
                raise ProjectToolExecutionError("The selected marker does not exist.")
            markers.remove(marker)
            return {"removed_marker_id": args["marker_id"]}, True

        if name == "timeline.duplicate_clip":
            source_track, source_clip = self._find_clip(project, args["clip_id"])
            target_track = self._find_track(
                project, args.get("track_id", source_track["id"])
            )
            if target_track.get("locked", False):
                raise ProjectToolExecutionError("The destination track is locked.")
            self._ensure_track_compatibility(target_track, source_clip["kind"])
            duplicate = deepcopy(source_clip)
            duplicate["id"] = _new_id("clip")
            # A duplicate is independent until the user explicitly links it.
            duplicate.pop("group_id", None)
            duplicate["start_us"] = args["start_us"]
            end_us = int(duplicate["start_us"]) + int(duplicate["duration_us"])
            for existing in target_track["clips"]:
                existing_start = int(existing["start_us"])
                existing_end = existing_start + int(existing["duration_us"])
                if duplicate["start_us"] < existing_end and end_us > existing_start:
                    raise ProjectToolExecutionError(
                        "The duplicate would overlap another clip on the destination track."
                    )
            target_track["clips"].append(duplicate)
            return {
                "source_clip_id": source_clip["id"],
                "new_clip_id": duplicate["id"],
                "track_id": target_track["id"],
                "start_us": duplicate["start_us"],
            }, True

        if name == "timeline.slip_clip":
            track, clip = self._find_clip(project, args["clip_id"])
            if track.get("locked", False):
                raise ProjectToolExecutionError("The selected track is locked.")
            if clip["kind"] not in {"video", "audio"}:
                raise ProjectToolExecutionError("Slip editing is currently available for video/audio clips only.")
            if any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                raise ProjectToolExecutionError(
                    "Slip editing for animated speed curves is not supported yet."
                )
            delta = int(args["delta_us"])
            if delta == 0:
                raise ProjectToolExecutionError("Slip offset must be non-zero.")
            source_in = int(clip.get("source_in_us", 0))
            rate = float(clip.get("playback_rate", 1.0))
            if "source_out_us" in clip:
                source_out = int(clip["source_out_us"])
            else:
                source_out = source_in + round(int(clip["duration_us"]) * rate)
            next_in = source_in + delta
            next_out = source_out + delta
            if next_in < 0:
                raise ProjectToolExecutionError("Slip would move the source in-point before the beginning of the asset.")
            asset = self._asset(project, clip["media_id"])
            known_duration = asset.get("duration_us")
            if known_duration is not None and next_out > int(known_duration):
                raise ProjectToolExecutionError("Slip would move the source out-point beyond the media asset duration.")
            if next_out <= next_in:
                raise ProjectToolExecutionError("Slip would create an empty source range.")
            clip["source_in_us"] = next_in
            clip["source_out_us"] = next_out
            return {
                "clip_id": clip["id"],
                "source_in_us": next_in,
                "source_out_us": next_out,
                "preserved_start_us": clip["start_us"],
                "preserved_duration_us": clip["duration_us"],
            }, True

        if name == "timeline.trim_clip":
            _, clip = self._find_clip(project, args["clip_id"])
            if clip["kind"] == "text":
                raise ProjectToolExecutionError("Text clips do not have source in/out points.")
            if any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                raise ProjectToolExecutionError(
                    "Trim a speed-ramped clip only after the speed curve has been simplified."
                )
            source_in = args["source_in_us"]
            source_out = args["source_out_us"]
            if source_out <= source_in:
                raise ProjectToolExecutionError("Source out must be after source in.")
            rate = float(clip.get("playback_rate", 1.0))
            new_duration = round((source_out - source_in) / rate)
            if new_duration < 1:
                raise ProjectToolExecutionError("The selected source range is too short.")
            if any(item["time_us"] > new_duration for item in clip.get("keyframes", [])):
                raise ProjectToolExecutionError(
                    "The trim would remove existing keyframes; move or remove them first."
                )
            clip["source_in_us"] = source_in
            clip["source_out_us"] = source_out
            clip["duration_us"] = new_duration
            return {
                "clip_id": clip["id"],
                "source_in_us": source_in,
                "source_out_us": source_out,
                "duration_us": new_duration,
            }, True

        if name == "timeline.split_clip":
            track, clip = self._find_clip(project, args["clip_id"])
            if args["at_us"] >= clip["duration_us"]:
                raise ProjectToolExecutionError("Split position must be inside the clip.")
            if clip.get("keyframes"):
                raise ProjectToolExecutionError(
                    "This split handler preserves static clip settings only; "
                    "remove or bake keyframes before splitting."
                )
            offset = args["at_us"]
            left = clip
            right = deepcopy(clip)
            right["id"] = _new_id("clip")
            right["start_us"] = int(clip["start_us"]) + offset
            right["duration_us"] = int(clip["duration_us"]) - offset
            left["duration_us"] = offset
            if clip["kind"] != "text":
                rate = float(clip.get("playback_rate", 1.0))
                source_in = int(clip.get("source_in_us", 0))
                source_split = source_in + round(offset * rate)
                old_source_out = clip.get("source_out_us")
                if old_source_out is None:
                    old_source_out = source_in + round(
                        int(clip["duration_us"]) * rate
                    )
                if source_split >= old_source_out:
                    raise ProjectToolExecutionError(
                        "The split falls outside the selected source range."
                    )
                left["source_out_us"] = source_split
                right["source_in_us"] = source_split
                right["source_out_us"] = old_source_out
            track["clips"].append(right)
            if right.get("group_id"):
                group = next((item for item in project.get("clip_groups", [])
                              if item["id"] == right["group_id"]), None)
                if group is None:
                    raise ProjectToolExecutionError("The split clip references a missing linked group.")
                group["clip_ids"].append(right["id"])
            return {
                "left_clip_id": left["id"],
                "right_clip_id": right["id"],
                "split_at_us": offset,
            }, True

        if name == "timeline.delete_clip":
            track, clip = self._find_clip(project, args["clip_id"])
            track["clips"].remove(clip)
            _prune_clip_groups(project, {clip["id"]})
            project["transitions"] = [
                item for item in project.get("transitions", [])
                if item["from_clip_id"] != clip["id"]
                and item["to_clip_id"] != clip["id"]
            ]
            return {"deleted_clip_id": clip["id"]}, True

        if name == "timeline.ripple_delete_clip":
            track, clip = self._find_clip(project, args["clip_id"])
            deleted_start = int(clip["start_us"])
            deleted_end = deleted_start + int(clip["duration_us"])
            deleted_duration = int(clip["duration_us"])
            # Refuse ambiguous overlaps rather than silently changing other edits.
            for other in track["clips"]:
                if other["id"] == clip["id"]:
                    continue
                other_start = int(other["start_us"])
                other_end = other_start + int(other["duration_us"])
                if other_start < deleted_end and other_end > deleted_start:
                    raise ProjectToolExecutionError(
                        "Ripple delete requires non-overlapping clips on the target track."
                    )
            track["clips"].remove(clip)
            _prune_clip_groups(project, {clip["id"]})
            shifted = []
            for other in track["clips"]:
                if int(other["start_us"]) >= deleted_end:
                    other["start_us"] = int(other["start_us"]) - deleted_duration
                    shifted.append(other["id"])
            project["transitions"] = [
                item for item in project.get("transitions", [])
                if item["from_clip_id"] != clip["id"]
                and item["to_clip_id"] != clip["id"]
            ]
            return {
                "deleted_clip_id": clip["id"],
                "removed_duration_us": deleted_duration,
                "shifted_clip_ids": shifted,
                "track_id": track["id"],
            }, True

        if name == "track.set_state":
            track = self._find_track(project, args["track_id"])
            if "enabled" in args:
                track["enabled"] = args["enabled"]
            if "muted" in args:
                track["muted"] = args["muted"]
            if "solo" in args:
                if track["type"] == "text":
                    raise ProjectToolExecutionError("Text tracks do not support solo mode.")
                track["solo"] = args["solo"]
            if "visible" in args:
                if track["type"] == "audio":
                    raise ProjectToolExecutionError("Audio tracks do not support visual visibility.")
                track["visible"] = args["visible"]
            if "audio_gain_db" in args or "audio_pan" in args:
                if track["type"] == "text":
                    raise ProjectToolExecutionError("Text tracks do not carry an audio signal.")
                if "audio_gain_db" in args:
                    track["audio_gain_db"] = float(args["audio_gain_db"])
                if "audio_pan" in args:
                    track["audio_pan"] = float(args["audio_pan"])
            if not any(key in args for key in ("enabled", "muted", "solo", "visible", "audio_gain_db", "audio_pan")):
                raise ProjectToolExecutionError("Specify a track state or audio mix setting.")
            return {
                "track_id": track["id"],
                "enabled": track.get("enabled", True),
                "muted": track.get("muted", False),
                "solo": track.get("solo", False),
                "visible": track.get("visible", True),
                "audio_gain_db": track.get("audio_gain_db", 0),
                "audio_pan": track.get("audio_pan", 0),
            }, True

        if name == "track.rename":
            track = self._find_track(project, args["track_id"])
            track["name"] = args["name"]
            return {"track_id": track["id"], "name": track["name"]}, True

        if name == "track.reorder":
            track = self._find_track(project, args["track_id"])
            tracks = sorted(project["tracks"], key=lambda item: int(item["order"]))
            requested_order = min(int(args["order"]), len(tracks) - 1)
            tracks.remove(track)
            tracks.insert(requested_order, track)
            for index, item in enumerate(tracks):
                item["order"] = index
            return {
                "track_id": track["id"],
                "order": track["order"],
                "track_order": [item["id"] for item in tracks],
            }, True

        if name == "track.set_locked":
            track = self._find_track(project, args["track_id"])
            track["locked"] = args["locked"]
            return {"track_id": track["id"], "locked": track["locked"]}, True

        if name == "clip.set_speed":
            _, clip = self._find_clip(project, args["clip_id"])
            if clip["kind"] not in {"video", "audio"}:
                raise ProjectToolExecutionError("Constant playback speed requires a video or audio clip.")
            if any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                raise ProjectToolExecutionError("Remove the existing speed curve before setting constant speed.")
            clip["playback_rate"] = args["playback_rate"]
            return {"clip_id": clip["id"], "playback_rate": clip["playback_rate"]}, True

        if name == "clip.set_transform":
            _, clip = self._find_clip(project, args["clip_id"])
            if clip["kind"] not in {"video", "image"}:
                raise ProjectToolExecutionError("Only video/image clips support visual transforms.")
            transform = deepcopy(clip.get("transform") or {
                "position": {"x": 0.0, "y": 0.0},
                "scale": {"x": 1.0, "y": 1.0},
                "rotation_deg": 0.0,
                "opacity": 1.0,
                "anchor_x": 0.5,
                "anchor_y": 0.5,
                "flip_horizontal": False,
                "flip_vertical": False,
            })
            if "position_x" in args:
                transform["position"]["x"] = args["position_x"]
            if "position_y" in args:
                transform["position"]["y"] = args["position_y"]
            if "scale_x" in args:
                transform["scale"]["x"] = args["scale_x"]
            if "scale_y" in args:
                transform["scale"]["y"] = args["scale_y"]
            if "rotation_deg" in args:
                transform["rotation_deg"] = args["rotation_deg"]
            if "opacity" in args:
                transform["opacity"] = args["opacity"]
            if "anchor_x" in args:
                transform["anchor_x"] = args["anchor_x"]
            if "anchor_y" in args:
                transform["anchor_y"] = args["anchor_y"]
            if "flip_horizontal" in args:
                transform["flip_horizontal"] = args["flip_horizontal"]
            if "flip_vertical" in args:
                transform["flip_vertical"] = args["flip_vertical"]
            clip["transform"] = transform
            return {"clip_id": clip["id"], "transform": transform}, True

        if name == "clip.set_framing":
            _, clip = self._find_clip(project, args["clip_id"])
            if clip["kind"] not in {"video", "image"}:
                raise ProjectToolExecutionError("Only video/image clips support framing.")
            mode = args["mode"]
            if mode == "none":
                clip.pop("framing", None)
                return {"clip_id": clip["id"], "mode": "none"}, True
            previous = clip.get("framing") or {}
            framing = {
                "mode": mode,
                "horizontal_alignment": args.get(
                    "horizontal_alignment",
                    previous.get("horizontal_alignment", "center"),
                ),
                "vertical_alignment": args.get(
                    "vertical_alignment",
                    previous.get("vertical_alignment", "middle"),
                ),
            }
            clip["framing"] = framing
            return {"clip_id": clip["id"], "framing": framing}, True

        if name == "clip.set_crop":
            _, clip = self._find_clip(project, args["clip_id"])
            if clip["kind"] not in {"video", "image"}:
                raise ProjectToolExecutionError("Only video/image clips support manual crop.")
            mode = args["mode"]
            if mode == "none":
                removed = clip.pop("crop", None) is not None
                return {"clip_id": clip["id"], "mode": "none", "changed": removed}, removed
            if clip.get("framing"):
                raise ProjectToolExecutionError(
                    "Clear automatic framing before applying a manual crop."
                )
            required = ("x", "y", "width", "height")
            if any(key not in args for key in required):
                raise ProjectToolExecutionError(
                    "A custom crop requires x, y, width and height fractions."
                )
            crop = {key: float(args[key]) for key in required}
            if crop["x"] + crop["width"] > 1.000000001 or crop["y"] + crop["height"] > 1.000000001:
                raise ProjectToolExecutionError("The manual crop rectangle must stay inside the source frame.")
            if crop["width"] <= 0 or crop["height"] <= 0:
                raise ProjectToolExecutionError("The manual crop width and height must be greater than zero.")
            clip["crop"] = crop
            return {"clip_id": clip["id"], "crop": crop}, True

        if name == "animation.set_keyframe":
            track, clip = self._find_clip(project, args["clip_id"])
            prop = args["property"]
            if prop == "volume_db":
                if clip["kind"] != "audio":
                    raise ProjectToolExecutionError("volume_db keyframes require an audio clip.")
            elif prop in {"crop_x", "crop_y", "crop_width", "crop_height"}:
                if clip["kind"] not in {"video", "image"}:
                    raise ProjectToolExecutionError("Animated crop requires a video or image clip.")
                if clip.get("framing"):
                    raise ProjectToolExecutionError("Clear automatic framing before animating the crop.")
                if any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                    raise ProjectToolExecutionError("Animated crop cannot be combined with speed ramps.")
            elif prop == "playback_rate":
                if clip["kind"] != "video":
                    raise ProjectToolExecutionError("Playback-speed curves currently require video clips.")
                if clip.get("effects") or any(
                    item["property"] in {
                        "position_x", "position_y", "scale_x", "scale_y",
                        "rotation_deg", "opacity",
                    }
                    for item in clip.get("keyframes", [])
                ):
                    raise ProjectToolExecutionError(
                        "Speed curves cannot yet be combined with clip effects or animated transforms."
                    )
            else:
                if clip["kind"] not in {"video", "image"}:
                    raise ProjectToolExecutionError("Visual keyframes require a video/image clip.")
                if any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                    raise ProjectToolExecutionError(
                        "Animated transforms cannot yet be combined with speed ramps."
                    )
            if track["type"] == "text":
                raise ProjectToolExecutionError("Animated text is not enabled in this engine.")
            item = {
                "property": prop,
                "time_us": args["time_us"],
                "value": args["value"],
                "interpolation": args.get("interpolation", "linear"),
            }
            if "bezier" in args:
                item["bezier"] = deepcopy(args["bezier"])
            if item["time_us"] > clip["duration_us"]:
                raise ProjectToolExecutionError("Keyframe time is outside the clip.")
            keyframes = clip.setdefault("keyframes", [])
            keyframes[:] = [
                existing for existing in keyframes
                if not (
                    existing["property"] == prop
                    and existing["time_us"] == item["time_us"]
                )
            ]
            keyframes.append(item)
            keyframes.sort(key=lambda entry: (entry["property"], entry["time_us"]))
            return {"clip_id": clip["id"], "keyframe": item}, True

        if name == "animation.clear_keyframes":
            _, clip = self._find_clip(project, args["clip_id"])
            property_name = args.get("property")
            before = clip.get("keyframes", [])
            if property_name is None:
                removed = len(before)
                clip["keyframes"] = []
            else:
                clip["keyframes"] = [
                    item for item in before if item["property"] != property_name
                ]
                removed = len(before) - len(clip["keyframes"])
            return {
                "clip_id": clip["id"],
                "property": property_name,
                "removed": removed,
            }, bool(removed)

        if name == "animation.remove_keyframe":
            _, clip = self._find_clip(project, args["clip_id"])
            prop = args["property"]
            at = args["time_us"]
            keyframes = clip.get("keyframes", [])
            matching = [
                item for item in keyframes
                if item["property"] == prop and int(item["time_us"]) == at
            ]
            if not matching:
                raise ProjectToolExecutionError(
                    "No keyframe exists for that property at the selected time."
                )
            clip["keyframes"] = [
                item for item in keyframes
                if not (item["property"] == prop and int(item["time_us"]) == at)
            ]
            return {"clip_id": clip["id"], "removed": len(matching),
                    "property": prop, "time_us": at}, True

        if name == "effect.add":
            _, clip = self._find_clip(project, args["clip_id"])
            effect_type = args["effect_type"]
            parameters = deepcopy(args["parameters"])
            visual_effects = {"brightness", "contrast", "saturation", "chroma"}
            audio_effects = {"gain", "fade"}
            if clip["kind"] == "audio":
                if effect_type not in audio_effects:
                    raise ProjectToolExecutionError(
                        "Audio clips support gain and fade effects in this renderer."
                    )
            elif clip["kind"] in {"video", "image"}:
                if effect_type not in visual_effects:
                    raise ProjectToolExecutionError(
                        "Visual clips support brightness, contrast, saturation and chroma key."
                    )
                if any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                    raise ProjectToolExecutionError(
                        "Clip effects cannot yet be combined with animated speed curves."
                    )
            else:
                raise ProjectToolExecutionError("This clip kind does not support effects.")
            self._validate_effect_parameters(effect_type, parameters, clip["duration_us"])
            effect = {
                "id": _new_id("effect"),
                "type": effect_type,
                "enabled": True,
                "parameters": parameters,
            }
            clip.setdefault("effects", []).append(effect)
            return {"clip_id": clip["id"], "effect": effect}, True

        if name == "effect.remove":
            _, clip = self._find_clip(project, args["clip_id"])
            existing = len(clip.get("effects", []))
            clip["effects"] = [
                item for item in clip.get("effects", [])
                if item["id"] != args["effect_id"]
            ]
            if len(clip["effects"]) == existing:
                raise ProjectToolExecutionError("The selected effect ID does not exist on this clip.")
            return {"clip_id": clip["id"], "removed_effect_id": args["effect_id"]}, True

        if name == "effect.set_enabled":
            _, clip = self._find_clip(project, args["clip_id"])
            effect = next(
                (item for item in clip.get("effects", [])
                 if item["id"] == args["effect_id"]),
                None,
            )
            if effect is None:
                raise ProjectToolExecutionError(
                    "The selected effect ID does not exist on this clip."
                )
            effect["enabled"] = args["enabled"]
            return {
                "clip_id": clip["id"],
                "effect_id": effect["id"],
                "enabled": effect["enabled"],
            }, True

        if name == "timeline.add_transition":
            from_track, from_clip = self._find_clip(project, args["from_clip_id"])
            to_track, to_clip = self._find_clip(project, args["to_clip_id"])
            if from_track["id"] != to_track["id"] or from_track["type"] not in {"video", "overlay"}:
                raise ProjectToolExecutionError("Transitions require clips on the same visual track.")
            ordered = sorted(from_track["clips"], key=lambda item: (item["start_us"], item["id"]))
            positions = {item["id"]: index for index, item in enumerate(ordered)}
            if positions[to_clip["id"]] != positions[from_clip["id"]] + 1:
                raise ProjectToolExecutionError("A transition must connect adjacent clips.")
            overlap = (
                int(from_clip["start_us"]) + int(from_clip["duration_us"])
                - int(to_clip["start_us"])
            )
            if overlap != args["duration_us"]:
                raise ProjectToolExecutionError(
                    "Transition duration must exactly match the clips' timeline overlap."
                )
            used = {
                clip_id
                for transition in project.get("transitions", [])
                for clip_id in (transition["from_clip_id"], transition["to_clip_id"])
            }
            if from_clip["id"] in used or to_clip["id"] in used:
                raise ProjectToolExecutionError("A clip can belong to only one transition in this engine.")
            parameters = deepcopy(args.get("parameters", {}))
            if args["transition_type"] == "wipe":
                direction = parameters.get("direction", "left_to_right")
                softness = parameters.get("softness", 0.08)
                if direction not in {"left_to_right", "right_to_left"}:
                    raise ProjectToolExecutionError("Wipe direction is not supported.")
                if isinstance(softness, bool) or not isinstance(softness, (int, float)) or not 0 <= softness <= 1:
                    raise ProjectToolExecutionError("Wipe softness must be between 0 and 1.")
                parameters = {"direction": direction, "softness": float(softness)}
            elif parameters:
                raise ProjectToolExecutionError("Dissolve transitions do not accept parameters.")
            transition = {
                "id": _new_id("transition"),
                "type": args["transition_type"],
                "from_clip_id": from_clip["id"],
                "to_clip_id": to_clip["id"],
                "duration_us": args["duration_us"],
                "parameters": parameters,
            }
            project.setdefault("transitions", []).append(transition)
            return {"transition": transition}, True

        if name == "audio.set_gain":
            _, clip = self._find_clip(project, args["clip_id"])
            if clip["kind"] != "audio":
                raise ProjectToolExecutionError("Audio gain requires an audio clip.")
            self._replace_effect(
                clip, "gain", {"gain_db": args["gain_db"]}
            )
            return {"clip_id": clip["id"], "gain_db": args["gain_db"]}, True

        if name == "audio.set_fade":
            _, clip = self._find_clip(project, args["clip_id"])
            if clip["kind"] != "audio":
                raise ProjectToolExecutionError("Audio fades require an audio clip.")
            parameters = {
                "fade_in_us": args.get("fade_in_us", 0),
                "fade_out_us": args.get("fade_out_us", 0),
            }
            self._validate_effect_parameters("fade", parameters, clip["duration_us"])
            self._replace_effect(clip, "fade", parameters)
            return {"clip_id": clip["id"], **parameters}, True

        if name == "render.export":
            if self._asset_root is None or self._output_dir is None:
                raise ProjectToolExecutionError(
                    "Rendering is not configured for this executor instance."
                )
            filename = args["output_filename"]
            if (
                Path(filename).name != filename
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,94}\.mp4", filename)
            ):
                raise ProjectToolExecutionError("Output filename must be a safe MP4 basename.")
            self._output_dir.mkdir(parents=True, exist_ok=True)
            destination = self._output_dir / filename
            if destination.exists():
                raise ProjectToolExecutionError("Refusing to overwrite an existing export.")
            from mlt_engine.renderer import render_project

            report = render_project(
                project, self._asset_root, destination,
                timeout_seconds=self._render_timeout_seconds,
            )
            return {"render": report, "output_path": str(destination)}, False

        raise ProjectToolExecutionError(f"No execution handler exists for tool {name!r}.")

    @staticmethod
    def _inspect_document(project: dict[str, Any]) -> dict[str, Any]:
        duration = max(
            (
                int(clip["start_us"]) + int(clip["duration_us"])
                for track in project["tracks"]
                for clip in track["clips"]
            ),
            default=0,
        )
        return {
            "id": project["id"],
            "name": project["name"],
            "revision": project.get("revision", 1),
            "profile": deepcopy(project["video_profile"]),
            "duration_us": duration,
            "asset_count": len(project["assets"]),
            "track_count": len(project["tracks"]),
            "clip_count": sum(len(track["clips"]) for track in project["tracks"]),
            "tracks": [
                {
                    "id": track["id"],
                    "name": track["name"],
                    "type": track["type"],
                    "order": track["order"],
                    "clips": [
                        {"id": clip["id"], "kind": clip["kind"],
                         "start_us": clip["start_us"], "duration_us": clip["duration_us"]}
                        for clip in track["clips"]
                    ],
                }
                for track in sorted(project["tracks"], key=lambda item: item["order"])
            ],
        }

    @staticmethod
    def _validate_effect_parameters(
        effect_type: str, parameters: dict[str, Any], duration_us: int
    ) -> None:
        if effect_type == "brightness":
            value = parameters.get("level", 1.0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 15:
                raise ProjectToolExecutionError("Brightness level must be between 0 and 15.")
        elif effect_type in {"contrast", "saturation"}:
            value = parameters.get("value", 1.0)
            maximum = 4.0 if effect_type == "contrast" else 3.0
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= maximum:
                raise ProjectToolExecutionError(
                    f"{effect_type} value must be between 0 and {maximum:g}."
                )
        elif effect_type == "chroma":
            key = parameters.get("key", "#00ff00")
            variance = parameters.get("variance", 0.15)
            if not isinstance(key, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", key):
                raise ProjectToolExecutionError("Chroma key must use #RRGGBB.")
            if isinstance(variance, bool) or not isinstance(variance, (int, float)) or not 0 <= variance <= 1:
                raise ProjectToolExecutionError("Chroma variance must be between 0 and 1.")
        elif effect_type == "gain":
            value = parameters.get("gain_db", 0.0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not -96 <= value <= 24:
                raise ProjectToolExecutionError("Audio gain must be between -96 and 24 dB.")
        elif effect_type == "fade":
            fade_in = parameters.get("fade_in_us", 0)
            fade_out = parameters.get("fade_out_us", 0)
            for value in (fade_in, fade_out):
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ProjectToolExecutionError("Audio fade durations must be non-negative integers.")
            if fade_in + fade_out > duration_us or fade_in + fade_out == 0:
                raise ProjectToolExecutionError("Audio fade durations must fit within the clip and not both be zero.")
        else:
            raise ProjectToolExecutionError(f"Effect {effect_type!r} is not supported.")

    @staticmethod
    def _replace_effect(clip: dict[str, Any], effect_type: str, parameters: dict[str, Any]) -> None:
        effects = clip.setdefault("effects", [])
        existing = next((item for item in effects if item["type"] == effect_type), None)
        if existing:
            existing["parameters"] = deepcopy(parameters)
            existing["enabled"] = True
        else:
            effects.append({
                "id": _new_id("effect"),
                "type": effect_type,
                "enabled": True,
                "parameters": deepcopy(parameters),
            })

    def execute_batch(
        self,
        calls: list[dict[str, Any]],
        *,
        expected_revision: int | None = None,
        confirmed_tools: set[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a whole AI plan atomically as one undoable transaction."""
        if not isinstance(calls, list) or not calls or len(calls) > 40:
            raise ProjectToolExecutionError("A tool batch must contain between 1 and 40 calls.")
        if expected_revision is not None and expected_revision != self.revision:
            raise ProjectRevisionConflict(
                f"Project revision changed: expected {expected_revision}, current {self.revision}."
            )

        normalized: list[tuple[str, dict[str, Any]]] = []
        pending: list[str] = []
        approvals = confirmed_tools or set()
        for call in calls:
            if not isinstance(call, dict) or set(call) - {"name", "arguments"}:
                raise ProjectToolExecutionError("Each tool call must contain only name and arguments.")
            name = call.get("name")
            if not isinstance(name, str):
                raise ProjectToolExecutionError("Tool call name must be text.")
            args = validate_tool_call(name, call.get("arguments", {}))
            definition = get_tool_definition(name)
            if definition.requires_confirmation and name not in approvals:
                pending.append(name)
            normalized.append((name, args))

        if pending:
            raise ToolConfirmationRequired(sorted(set(pending)))

        export_positions = [i for i, (name, _) in enumerate(normalized) if name == "render.export"]
        if export_positions and export_positions != [len(normalized) - 1]:
            raise ProjectToolExecutionError("Render export must be the final call in a tool batch.")

        if any(name in {"history.undo", "history.redo"} for name, _ in normalized):
            if len(normalized) != 1:
                raise ProjectToolExecutionError("Undo/redo must be requested as a separate transaction.")
            return self._history_action(normalized[0][0], expected_revision)

        before = deepcopy(self._project)
        candidate = deepcopy(self._project)
        results: list[dict[str, Any]] = []
        changed = False
        try:
            for name, args in normalized:
                result, did_change = self._apply(candidate, name, args)
                results.append({"name": name, "result": result})
                changed = changed or did_change
            candidate = validate_project(candidate)
        except (ProjectValidationError, ToolValidationError):
            raise
        except Exception:
            # No partially applied candidate is assigned to self._project.
            raise

        if changed:
            candidate["revision"] = self.revision + 1
            candidate = validate_project(candidate)
            self._undo_stack.append(before)
            self._undo_stack = self._undo_stack[-10:]
            self._redo_stack.clear()
            self._project = candidate

        return {
            "ok": True,
            "revision": self.revision,
            "changed": changed,
            "results": results,
            "project": self.get_project(),
        }

    def _history_action(
        self, name: str, expected_revision: int | None
    ) -> dict[str, Any]:
        if name == "history.undo":
            if not self._undo_stack:
                raise ProjectToolExecutionError("There is no edit transaction to undo.")
            previous = self._undo_stack.pop()
            self._redo_stack.append(deepcopy(self._project))
            self._redo_stack = self._redo_stack[-10:]
            previous["revision"] = self.revision + 1
            self._project = validate_project(previous)
        else:
            if not self._redo_stack:
                raise ProjectToolExecutionError("There is no edit transaction to redo.")
            following = self._redo_stack.pop()
            self._undo_stack.append(deepcopy(self._project))
            self._undo_stack = self._undo_stack[-10:]
            following["revision"] = self.revision + 1
            self._project = validate_project(following)
        return {
            "ok": True,
            "revision": self.revision,
            "changed": True,
            "results": [{"name": name, "result": {"revision": self.revision}}],
            "project": self.get_project(),
        }

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        expected_revision: int | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        approvals = {name} if confirmed else set()
        return self.execute_batch(
            [{"name": name, "arguments": arguments}],
            expected_revision=expected_revision,
            confirmed_tools=approvals,
        )
