#!/usr/bin/env bash
set -euo pipefail

echo "=== MLT VERSION ==="
melt --version
/usr/bin/python3 --version

echo
echo "=== PYTHON BINDING ==="
/usr/bin/python3 - <<'PY'
import mlt7

factory = mlt7.Factory()
factory.init(None)
profile = mlt7.Profile()
producer = mlt7.Producer(profile, "color:red")
if not producer.is_valid():
    raise SystemExit("MLT Python binding loaded, but could not create a test producer.")
print("PASS: mlt7 imported, Factory initialized, and a producer was created.")
PY

echo
echo "=== INSTALLED FILTERS / TRANSITIONS / OUTPUT MODULES ==="
filters="$(melt -query filters)"
transitions="$(melt -query transitions)"
consumers="$(melt -query consumers)"

check_service() {
  local category="$1"
  local name="$2"
  local catalogue="$3"
  if grep -Fq -- "$name" <<<"$catalogue"; then
    printf 'AVAILABLE  %-12s %s\n' "$category" "$name"
  else
    printf 'NOT FOUND  %-12s %s\n' "$category" "$name"
  fi
}

for name in brightness chroma subtitle volume; do
  check_service filter "$name" "$filters"
done
for name in opencv.tracker rnnoise vidstab rotoscoping; do
  check_service optional-filter "$name" "$filters"
done
for name in luma mix; do
  check_service transition "$name" "$transitions"
done
check_service consumer avformat "$consumers"

for name in brightness chroma subtitle volume; do
  grep -Fq -- "$name" <<<"$filters" || {
    echo "Required baseline filter missing: $name" >&2
    exit 1
  }
done
grep -Fq -- "luma" <<<"$transitions" || {
  echo "Required luma transition missing." >&2
  exit 1
}
grep -Fq -- "avformat" <<<"$consumers" || {
  echo "Required FFmpeg-backed MLT output consumer missing." >&2
  exit 1
}

echo
echo "=== TWO-TRACK RENDER TEST (GENERATED MEDIA ONLY) ==="
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "color=c=red:s=320x240:r=25:d=1" \
  -an -c:v mpeg4 -q:v 5 "$work_dir/red.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "color=c=blue:s=320x240:r=25:d=1" \
  -an -c:v mpeg4 -q:v 5 "$work_dir/blue.mp4"

melt "$work_dir/red.mp4" \
  -track "$work_dir/blue.mp4" \
  -transition luma in=0 out=24 a_track=0 b_track=1 \
  -consumer "avformat:$work_dir/two-track-output.mp4" \
  vcodec=mpeg4 an=1 real_time=-1

test -s "$work_dir/two-track-output.mp4"

ffprobe -v error -show_entries format=duration:stream=codec_type,width,height \
  -of json "$work_dir/two-track-output.mp4" > "$work_dir/probe.json"

/usr/bin/python3 - "$work_dir/probe.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)

video = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"]
duration = float(data.get("format", {}).get("duration", 0))
if not video or duration <= 0:
    raise SystemExit("Rendered file is missing a valid video stream or duration.")
print(f"PASS: two-track render created; duration={duration:.3f}s; video={video[0]}")
PY

echo
echo "=== PYTHON API RENDER TEST ==="
/usr/bin/python3 video-editor/mlt_research/python_render_probe.py \
  "$work_dir/red.mp4" "$work_dir/python-api-output.mp4"
ffprobe -v error -show_entries format=duration:stream=codec_type,width,height \
  -of json "$work_dir/python-api-output.mp4" > "$work_dir/python-api-probe.json"
/usr/bin/python3 - "$work_dir/python-api-probe.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
video = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"]
duration = float(data.get("format", {}).get("duration", 0))
if not video or duration <= 0:
    raise SystemExit("Python API output is not a valid video.")
print(f"PASS: Python API output probe; duration={duration:.3f}s; video={video[0]}")
PY

echo
echo "MLT_CAPABILITY_PROBE=PASS"
