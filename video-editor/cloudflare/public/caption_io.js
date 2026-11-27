const MAX_CUES = 500;
const MAX_CUE_TEXT_LENGTH = 2000;

function decodeEntities(value) {
  const named = {
    amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: "\u00a0"
  };
  return String(value).replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (match, entity) => {
    if (entity[0] !== "#") return named[entity.toLowerCase()] ?? match;
    const hexadecimal = entity[1]?.toLowerCase() === "x";
    const number = Number.parseInt(entity.slice(hexadecimal ? 2 : 1), hexadecimal ? 16 : 10);
    if (!Number.isFinite(number) || number <= 0 || number > 0x10ffff ||
        (number >= 0xd800 && number <= 0xdfff)) return "\uFFFD";
    return String.fromCodePoint(number);
  });
}

function parseTimestamp(value) {
  const token = String(value).trim();
  let match = token.match(/^(\d+):([0-5]\d):([0-5]\d)[,.](\d{1,3})$/);
  let hours = 0;
  let minutes;
  let seconds;
  let fraction;
  if (match) {
    hours = Number(match[1]);
    minutes = Number(match[2]);
    seconds = Number(match[3]);
    fraction = match[4];
  } else {
    match = token.match(/^(\d{2,}):([0-5]\d)\.(\d{1,3})$/);
    if (!match) throw new Error("Unsupported subtitle timestamp: " + token);
    minutes = Number(match[1]);
    seconds = Number(match[2]);
    fraction = match[3];
  }
  const result = (((hours * 60 + minutes) * 60 + seconds) * 1000 +
    Number(fraction.padEnd(3, "0"))) * 1000;
  if (!Number.isSafeInteger(result)) throw new Error("Subtitle timestamp is too large.");
  return result;
}

function cleanCueText(lines) {
  const joined = lines.join("\n");
  return decodeEntities(joined.replace(/<[^>]*>/g, "").replace(/\u0000/g, "")).trim();
}

function validateCueList(cues) {
  if (!Array.isArray(cues) || cues.length < 1 || cues.length > MAX_CUES) {
    throw new Error("Subtitle files must contain 1 to " + MAX_CUES + " non-empty cues.");
  }
  let previousEnd = -1;
  for (let index = 0; index < cues.length; index += 1) {
    const cue = cues[index];
    if (!cue || typeof cue.text !== "string" || !cue.text.trim() ||
        cue.text.length > MAX_CUE_TEXT_LENGTH) {
      throw new Error("Subtitle cue " + (index + 1) + " has missing or overlong text.");
    }
    if (!Number.isSafeInteger(cue.start_us) || !Number.isSafeInteger(cue.end_us) ||
        cue.start_us < 0 || cue.end_us <= cue.start_us) {
      throw new Error("Subtitle cue " + (index + 1) + " has invalid timing.");
    }
    if (cue.start_us < previousEnd) {
      throw new Error("Subtitle cues overlap. Resolve the timing before importing or exporting.");
    }
    previousEnd = cue.end_us;
  }
  return cues;
}

export function parseSubtitleFile(source, filename = "captions.srt") {
  const name = String(filename).toLowerCase();
  if (!name.endsWith(".srt") && !name.endsWith(".vtt")) {
    throw new Error("Choose an .SRT or .VTT subtitle file.");
  }
  const raw = String(source ?? "").replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
  if (!raw.trim()) throw new Error("The subtitle file is empty.");
  const blocks = raw.split(/\n[ \t]*\n+/);
  const cues = [];

  for (const block of blocks) {
    const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
    if (!lines.length) continue;
    if (/^(WEBVTT|NOTE(?:\s|$)|STYLE(?:\s|$)|REGION(?:\s|$))/.test(lines[0])) continue;
    const timingIndex = lines.findIndex((line) => line.includes("-->"));
    if (timingIndex < 0) continue;
    const timing = lines[timingIndex].match(/^(\S+)\s+-->\s+(\S+)(?:\s+.*)?$/);
    if (!timing) throw new Error("Subtitle timing line is malformed.");
    const start_us = parseTimestamp(timing[1]);
    const end_us = parseTimestamp(timing[2]);
    const text = cleanCueText(lines.slice(timingIndex + 1));
    if (!text) continue;
    cues.push({text, start_us, end_us});
    if (cues.length > MAX_CUES) throw new Error("Import up to " + MAX_CUES + " subtitle cues at a time.");
  }

  if (!cues.length) {
    throw new Error("No valid subtitle cues were found. Check the SRT/VTT timing format.");
  }
  cues.sort((left, right) => left.start_us - right.start_us || left.end_us - right.end_us);
  return validateCueList(cues).map((cue) => ({...cue}));
}

export function formatSubtitleTimestamp(timeUs, format = "srt") {
  if (!Number.isSafeInteger(timeUs) || timeUs < 0) {
    throw new Error("Subtitle timestamp must be a non-negative whole number of microseconds.");
  }
  const milliseconds = Math.round(timeUs / 1000);
  const hours = Math.floor(milliseconds / 3600000);
  const minutes = Math.floor((milliseconds % 3600000) / 60000);
  const seconds = Math.floor((milliseconds % 60000) / 1000);
  const fraction = milliseconds % 1000;
  const time = [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
  return time + (String(format).toLowerCase() === "vtt" ? "." : ",") +
    String(fraction).padStart(3, "0");
}

function escapeCueText(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function serializeSubtitleCues(inputCues, format = "srt") {
  const kind = String(format).toLowerCase();
  if (!["srt", "vtt"].includes(kind)) throw new Error("Subtitle export format must be SRT or VTT.");
  // SRT and WebVTT only preserve milliseconds. Round first, then revalidate to
  // prevent two close microsecond cues from becoming overlapping/zero-length cues.
  const cues = validateCueList(inputCues.map((cue) => ({
    text: String(cue.text ?? "").trim(),
    start_us: Math.round(cue.start_us / 1000) * 1000,
    end_us: Math.round(cue.end_us / 1000) * 1000
  })));
  const blocks = cues.map((cue, index) => {
    const start = formatSubtitleTimestamp(cue.start_us, kind);
    const end = formatSubtitleTimestamp(cue.end_us, kind);
    return (kind === "srt" ? String(index + 1) + "\n" : "") +
      start + " --> " + end + "\n" + escapeCueText(cue.text);
  });
  return (kind === "vtt" ? "WEBVTT\n\n" : "") + blocks.join("\n\n") + "\n";
}

export function exportSubtitleTrack(track, format = "srt") {
  if (!track || track.type !== "text" || !Array.isArray(track.clips)) {
    throw new Error("Choose a text track before exporting subtitles.");
  }
  const cues = track.clips
    .filter((clip) => clip && clip.kind === "text" && clip.text && String(clip.text.content ?? "").trim())
    .map((clip) => {
      const start_us = clip.start_us;
      const duration_us = clip.duration_us;
      if (!Number.isSafeInteger(start_us) || !Number.isSafeInteger(duration_us) ||
          start_us < 0 || duration_us < 1 || !Number.isSafeInteger(start_us + duration_us)) {
        throw new Error("A text clip has invalid timing and cannot be exported.");
      }
      return {text: String(clip.text.content), start_us, end_us: start_us + duration_us};
    })
    .sort((left, right) => left.start_us - right.start_us || left.end_us - right.end_us);
  if (!cues.length) throw new Error("The selected text track has no caption text to export.");
  return serializeSubtitleCues(cues, format);
}

export const SUBTITLE_LIMITS = Object.freeze({
  maxCues: MAX_CUES,
  maxCueTextLength: MAX_CUE_TEXT_LENGTH
});

if (typeof window !== "undefined") {
  window.VideoEditorCaptionIO = {
    parseSubtitleFile, formatSubtitleTimestamp, serializeSubtitleCues,
    exportSubtitleTrack, SUBTITLE_LIMITS
  };
}
