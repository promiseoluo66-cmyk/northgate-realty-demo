"""Direct executor coverage for the registered render.export operation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from project_tool_executor import (
    ProjectToolExecutionError,
    ProjectToolExecutor,
    ToolConfirmationRequired,
)
from test_project_tool_extensions import make_project


def make_export_executor(tmp_path: Path, *, configured: bool = True) -> ProjectToolExecutor:
    options = {}
    if configured:
        options = {
            "asset_root": tmp_path / "assets",
            "output_dir": tmp_path / "exports",
            "render_timeout_seconds": 17,
        }
    return ProjectToolExecutor(make_project(), **options)


def export_call(filename: str = "final-cut.mp4") -> list[dict]:
    return [{"name": "render.export", "arguments": {"output_filename": filename}}]


def test_render_export_requires_explicit_confirmation(tmp_path):
    executor = make_export_executor(tmp_path)
    before = executor.get_project()

    with pytest.raises(ToolConfirmationRequired):
        executor.execute_batch(export_call())

    assert executor.get_project() == before
    assert executor.revision == 1
    assert not (tmp_path / "exports").exists()


def test_render_export_executes_renderer_and_returns_receipt(tmp_path):
    executor = make_export_executor(tmp_path)
    output_dir = tmp_path / "exports"
    expected_output = output_dir / "final-cut.mp4"
    receipt = {"duration_seconds": 2.0, "width": 720, "height": 1280}

    def fake_render(project, asset_root, destination, *, timeout_seconds):
        assert project == executor.get_project()
        assert asset_root == (tmp_path / "assets").resolve()
        assert destination == expected_output
        assert timeout_seconds == 17
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"mock mp4 output")
        return receipt

    with patch("mlt_engine.renderer.render_project", side_effect=fake_render) as renderer:
        result = executor.execute_batch(
            export_call(), expected_revision=1,
            confirmed_tools={"render.export"},
        )

    renderer.assert_called_once()
    assert result["ok"] is True
    assert result["changed"] is False
    assert result["revision"] == 1
    assert result["results"][0]["name"] == "render.export"
    assert result["results"][0]["result"]["render"] == receipt
    assert result["results"][0]["result"]["output_path"] == str(expected_output)
    assert expected_output.read_bytes() == b"mock mp4 output"
    assert executor.get_project()["revision"] == 1


@pytest.mark.parametrize("filename", ["../escape.mp4", "folder/output.mp4", "bad name.mp4", ".mp4", "x.mov"])
def test_render_export_rejects_unsafe_or_non_mp4_filename(tmp_path, filename):
    executor = make_export_executor(tmp_path)

    with pytest.raises(ProjectToolExecutionError, match="safe MP4 basename"):
        executor.execute_batch(
            export_call(filename), confirmed_tools={"render.export"}
        )

    assert executor.revision == 1
    assert not (tmp_path / "escape.mp4").exists()


def test_render_export_fails_closed_when_renderer_is_not_configured(tmp_path):
    executor = make_export_executor(tmp_path, configured=False)

    with pytest.raises(ProjectToolExecutionError, match="not configured"):
        executor.execute_batch(
            export_call(), confirmed_tools={"render.export"}
        )

    assert executor.revision == 1


def test_render_export_refuses_to_overwrite_existing_output(tmp_path):
    executor = make_export_executor(tmp_path)
    output = tmp_path / "exports" / "final-cut.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"keep existing file")

    with pytest.raises(ProjectToolExecutionError, match="Refusing to overwrite"):
        executor.execute_batch(
            export_call(), confirmed_tools={"render.export"}
        )

    assert output.read_bytes() == b"keep existing file"
    assert executor.revision == 1


def test_render_export_renderer_failure_does_not_mutate_project(tmp_path):
    executor = make_export_executor(tmp_path)
    before = executor.get_project()

    with patch("mlt_engine.renderer.render_project", side_effect=RuntimeError("render failed")):
        with pytest.raises(RuntimeError, match="render failed"):
            executor.execute_batch(
                export_call(), expected_revision=1,
                confirmed_tools={"render.export"},
            )

    assert executor.get_project() == before
    assert executor.revision == 1
