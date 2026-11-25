#!/usr/bin/env python3
"""Render a tiny two-track composition through MLT's Python API."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import mlt7 as mlt


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python_render_probe.py INPUT OUTPUT")

    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if not source.is_file():
        raise SystemExit(f"Input file does not exist: {source}")

    factory = mlt.Factory()
    factory.init(None)
    profile = mlt.Profile()

    # Build two independent clip instances on separate timeline tracks.
    background = mlt.Producer(profile, str(source))
    foreground = mlt.Producer(profile, str(source))
    if not background.is_valid() or not foreground.is_valid():
        raise SystemExit("MLT Python API could not open the generated input clip.")

    tractor = mlt.Tractor()
    tractor.set_track(background, 0)
    tractor.set_track(foreground, 1)

    # Use MLT's compositing transition to combine the two tracks.
    composite = mlt.Transition(profile, "composite")
    composite.set("fill", 1)
    tractor.plant_transition(composite)

    consumer = mlt.Consumer(profile, "avformat", str(output))
    if not consumer.is_valid():
        raise SystemExit("MLT Python API could not create the FFmpeg output consumer.")

    consumer.set("vcodec", "mpeg4")
    consumer.set("an", 1)
    consumer.set("real_time", -1)

    connect_result = consumer.connect(tractor)
    if connect_result not in (None, 0):
        raise SystemExit(f"MLT Python consumer connection failed: {connect_result}")

    start_result = consumer.start()
    if start_result not in (None, 0):
        raise SystemExit(f"MLT Python consumer failed to start: {start_result}")

    deadline = time.monotonic() + 30
    while not consumer.is_stopped():
        if time.monotonic() >= deadline:
            consumer.stop()
            raise SystemExit("MLT Python render exceeded the 30-second smoke-test limit.")
        time.sleep(0.05)

    consumer.stop()
    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit("MLT Python API did not create a non-empty output file.")

    print(
        "PASS: MLT Python API rendered a two-track composition "
        f"({output.stat().st_size} bytes) using {sys.version.split()[0]}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
