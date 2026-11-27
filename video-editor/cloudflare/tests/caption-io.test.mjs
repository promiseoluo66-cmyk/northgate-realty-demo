import test from "node:test";
import assert from "node:assert/strict";
import {
  parseSubtitleFile,
  serializeSubtitleCues,
  exportSubtitleTrack
} from "../public/caption_io.js";

test("SRT parser handles BOM, cue identifiers, markup, entities and multiline text", () => {
  const source = "\uFEFF1\r\n00:00:01,250 --> 00:00:02,500\r\nHello &amp; <b>welcome</b>\r\nsecond line\r\n\r\n2\r\n00:00:02,750 --> 00:00:03,000\r\nNext cue\r\n";
  assert.deepEqual(parseSubtitleFile(source, "captions.srt"), [
    {text: "Hello & welcome\nsecond line", start_us: 1_250_000, end_us: 2_500_000},
    {text: "Next cue", start_us: 2_750_000, end_us: 3_000_000}
  ]);
});

test("WebVTT parser accepts headers, cue identifiers, timestamp settings and short timestamps", () => {
  const source = "WEBVTT - example\n\nintro\n00:01.125 --> 00:02.250 align:start position:10%\n<v Speaker>First &lt;word&gt;</v>\n\n00:00:03.000 --> 00:00:04.000\nSecond line\n";
  assert.deepEqual(parseSubtitleFile(source, "captions.vtt"), [
    {text: "First <word>", start_us: 1_125_000, end_us: 2_250_000},
    {text: "Second line", start_us: 3_000_000, end_us: 4_000_000}
  ]);
});

test("SRT export preserves caption text and timing to millisecond precision", () => {
  const cues = [
    {text: "Hello & <world>\nagain", start_us: 1_250_000, end_us: 2_500_000},
    {text: "Second cue", start_us: 2_750_000, end_us: 3_500_000}
  ];
  const exported = serializeSubtitleCues(cues, "srt");
  assert.match(exported, /00:00:01,250 --> 00:00:02,500/);
  assert.deepEqual(parseSubtitleFile(exported, "roundtrip.srt"), cues);
});

test("VTT export preserves captions and includes the WEBVTT header", () => {
  const cues = [{text: "A caption", start_us: 61_250_000, end_us: 62_500_000}];
  const exported = serializeSubtitleCues(cues, "vtt");
  assert.match(exported, /^WEBVTT\n\n/);
  assert.match(exported, /00:01:01\.250 --> 00:01:02\.500/);
  assert.deepEqual(parseSubtitleFile(exported, "roundtrip.vtt"), cues);
});

test("track export sorts text clips and ignores non-text clips", () => {
  const track = {
    type: "text",
    clips: [
      {id: "later", kind: "text", start_us: 2_000_000, duration_us: 1_000_000, text: {content: "Later"}},
      {id: "first", kind: "text", start_us: 0, duration_us: 1_000_000, text: {content: "First"}},
      {id: "visual", kind: "image", start_us: 0, duration_us: 1_000_000}
    ]
  };
  assert.deepEqual(
    parseSubtitleFile(exportSubtitleTrack(track, "srt"), "captions.srt").map((cue) => cue.text),
    ["First", "Later"]
  );
});

test("track export rejects overlapping cues so exports remain re-importable", () => {
  const track = {type: "text", clips: [
    {id: "a", kind: "text", start_us: 0, duration_us: 2_000_000, text: {content: "First"}},
    {id: "b", kind: "text", start_us: 1_000_000, duration_us: 1_000_000, text: {content: "Overlap"}}
  ]};
  assert.throws(() => exportSubtitleTrack(track, "vtt"), /overlap/);
});

test("parser rejects malformed timestamps, empty cues and non-positive durations", () => {
  assert.throws(() => parseSubtitleFile("1\n00:00:70,000 --> 00:00:71,000\nBad", "bad.srt"), /timestamp/);
  assert.throws(() => parseSubtitleFile("1\n00:00:01,000 --> 00:00:01,000\nBad", "bad.srt"), /invalid timing/);
  assert.throws(() => parseSubtitleFile("1\n00:00:01,000 --> 00:00:02,000\n<b></b>", "bad.srt"), /No valid subtitle cues/);
});

test("parser rejects overlapping cues and unsupported extensions", () => {
  const source = "1\n00:00:00,000 --> 00:00:02,000\nOne\n\n2\n00:00:01,000 --> 00:00:03,000\nTwo";
  assert.throws(() => parseSubtitleFile(source, "bad.srt"), /overlap/);
  assert.throws(() => parseSubtitleFile(source, "captions.txt"), /SRT or VTT/);
});

test("parser enforces 500-cue and 2,000-character limits", () => {
  const blocks = Array.from({length: 501}, (_, index) => {
    const start = String(index * 2).padStart(2, "0");
    const end = String(index * 2 + 1).padStart(2, "0");
    return (index + 1) + "\n00:00:" + start + ",000 --> 00:00:" + end + ",000\ntext";
  });
  assert.throws(() => parseSubtitleFile(blocks.join("\n\n"), "many.srt"), /500/);
  const long = "1\n00:00:00,000 --> 00:00:01,000\n" + "x".repeat(2001);
  assert.throws(() => parseSubtitleFile(long, "long.srt"), /overlong/);
});

test("export rejects invalid tracks, empty tracks and invalid timing", () => {
  assert.throws(() => exportSubtitleTrack({type: "video", clips: []}, "srt"), /text track/);
  assert.throws(() => exportSubtitleTrack({type: "text", clips: []}, "srt"), /no caption text/);
  assert.throws(() => exportSubtitleTrack({type: "text", clips: [
    {kind: "text", start_us: -1, duration_us: 0, text: {content: "Bad"}}
  ]}, "srt"), /invalid timing/);
});

test("export rejects timings that collapse or overlap after millisecond rounding", () => {
  const close = [{text: "A", start_us: 100, end_us: 400}, {text: "B", start_us: 500, end_us: 900}];
  assert.throws(() => serializeSubtitleCues(close, "srt"), /invalid timing|overlap/);
});
